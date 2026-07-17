#!/usr/bin/env python3
"""Shared helpers for the surge-publish skill.

Wraps the `surge` CLI (a Node.js tool installed via `npm install -g surge`)
in a Python layer so the rest of the skill can call it programmatically,
parse its output, and run pre-flight checks.

The CLI is intentionally invoked non-interactively: every prompt the CLI
might ask for (domain, login, etc.) is supplied via arguments, flags,
or the SURGE_TOKEN / SURGE_LOGIN env vars. This is the only safe mode
for agent-driven automation.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLE_SITE = SKILL_ROOT / "assets" / "sample-site"

# Files Surge reads from the project directory as configuration.
CONFIG_FILES = {
    "CNAME": "Target domain (single line)",
    ".surgeignore": "Files to exclude from deployment (gitignore syntax)",
    "200.html": "SPA shell for unmatched URLs (client-side routing)",
    "404.html": "Custom not-found page",
    "ROUTER": "Redirect rules (paid plan)",
    "AUTH": "HTTP basic auth (paid plan)",
    "CORS": "Cross-origin headers (paid plan)",
}


class SurgeError(RuntimeError):
    """Raised when surge CLI fails or a pre-flight check fails."""


@dataclass
class SurgeResult:
    """Structured result of a surge CLI invocation."""
    command: List[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


def surge_available() -> bool:
    """True if the `surge` binary is on PATH."""
    return shutil.which("surge") is not None


def surge_version() -> Optional[str]:
    """Return the surge CLI version string, or None if unavailable."""
    if not surge_available():
        return None
    r = _run_raw(["surge", "--version"])
    # Output looks like "0.31.1" possibly with ANSI color codes.
    m = re.search(r"\d+\.\d+\.\d+", r.stdout)
    return m.group(0) if m else None


def _run_raw(cmd: Sequence[str], *, cwd: Optional[Path] = None,
             timeout: int = 300, env: Optional[Dict[str, str]] = None) -> SurgeResult:
    """Run a command and capture output. Strips ANSI color codes.

    On Windows, npm-installed CLIs are .CMD/.BAT wrappers that subprocess
    won't resolve from a bare name unless shell=True. We resolve the full
    path via shutil.which first so we can keep shell=False (safer, no shell
    injection surface from arguments).
    """
    full_env = os.environ.copy()
    # Force non-interactive mode so surge never blocks on a prompt.
    full_env.setdefault("CI", "true")
    if env:
        full_env.update(env)

    # Resolve the executable path (handles surge.CMD on Windows).
    resolved = list(cmd)
    if cmd[0] and os.path.sep not in cmd[0] and os.path.altsep not in (cmd[0] or ""):
        which_path = shutil.which(cmd[0])
        if which_path:
            resolved[0] = which_path

    try:
        # Redirect stdin from /dev/null so surge cannot block on an interactive
        # login prompt when no SURGE_TOKEN is set. Without this, surge would
        # hang waiting for email/password input and the agent would stall.
        proc = subprocess.run(
            resolved, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout, env=full_env,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise SurgeError(f"command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SurgeError(f"command timed out after {timeout}s: {' '.join(cmd)}") from exc
    return SurgeResult(
        command=list(cmd),
        returncode=proc.returncode,
        stdout=_strip_ansi(proc.stdout),
        stderr=_strip_ansi(proc.stderr),
    )


def run_surge(args: Sequence[str], *, cwd: Optional[Path] = None,
              timeout: int = 300, token: Optional[str] = None,
              check: bool = True, require_auth: bool = True) -> SurgeResult:
    """Run `surge <args...>`. Injects SURGE_TOKEN if provided.

    Set check=False to suppress the SurgeError on non-zero exit.
    Set require_auth=False for commands that work without login (whoami, --version).
    """
    if not surge_available():
        raise SurgeError(
            "surge CLI is not installed. Install with: npm install --global surge"
        )
    env: Dict[str, str] = {}
    t = token or os.environ.get("SURGE_TOKEN")
    if t:
        env["SURGE_TOKEN"] = t
    login = os.environ.get("SURGE_LOGIN")
    if login:
        env["SURGE_LOGIN"] = login

    # Block early on commands that need auth. Surge's CLI, when unauthenticated,
    # drops into an interactive email/password prompt that would hang the agent.
    if require_auth and not (t or login):
        state = whoami()
        if not state.authenticated:
            raise SurgeError(
                "Not authenticated. Set SURGE_TOKEN (and SURGE_LOGIN) env vars, "
                "or run `surge login` interactively first. "
                "Mint a token with `surge token` in a terminal."
            )

    result = _run_raw(["surge", *args], cwd=cwd, timeout=timeout, env=env)
    if check and not result.ok:
        raise SurgeError(
            f"surge {' '.join(args)} failed (exit {result.returncode}):\n{result.output()}"
        )
    return result


# ---------------------------------------------------------------------------
# ANSI / output parsing
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


_DOMAIN_RE = re.compile(r"https?://([a-z0-9.-]+)", re.IGNORECASE)


def extract_published_url(text: str) -> Optional[str]:
    """Pull the first http(s) URL out of surge's publish output."""
    m = _DOMAIN_RE.search(text or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Auth state
# ---------------------------------------------------------------------------

@dataclass
class AuthState:
    authenticated: bool
    email: Optional[str] = None
    plan: Optional[str] = None
    raw: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "authenticated": self.authenticated,
            "email": self.email,
            "plan": self.plan,
        }


def whoami() -> AuthState:
    """Parse `surge whoami` output into a structured AuthState."""
    if not surge_available():
        return AuthState(authenticated=False, raw="surge CLI not installed")
    r = run_surge(["whoami"], check=False, require_auth=False)
    text = r.output()
    if "Not Authenticated" in text or not r.ok:
        return AuthState(authenticated=False, raw=text)
    # Typical output: "Running as foo@example.com (Standard)"
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    plan_match = re.search(r"\((Standard|Free|Premium|Custom|Pro)\)", text)
    return AuthState(
        authenticated=True,
        email=email_match.group(0) if email_match else None,
        plan=plan_match.group(1) if plan_match else None,
        raw=text,
    )


# ---------------------------------------------------------------------------
# Project config file helpers
# ---------------------------------------------------------------------------

@dataclass
class ProjectCheck:
    path: Path
    issues: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    cname: Optional[str] = None
    has_index: bool = False
    has_200: bool = False
    has_404: bool = False
    has_surgeignore: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "cname": self.cname,
            "has_index": self.has_index,
            "has_200_shell": self.has_200,
            "has_404": self.has_404,
            "has_surgeignore": self.has_surgeignore,
            "issues": self.issues,
            "notes": self.notes,
        }


def check_project(path: Path) -> ProjectCheck:
    """Pre-flight check of a project directory before publishing.

    Returns a ProjectCheck with warnings in .issues (publish-blockers) and
    informational items in .notes. Does not raise on missing files; the
    caller decides whether issues are blocking.
    """
    chk = ProjectCheck(path=path.resolve())
    if not path.exists():
        chk.issues.append(f"path does not exist: {path}")
        return chk
    if not path.is_dir():
        chk.issues.append(f"path is not a directory: {path}")
        return chk

    index = path / "index.html"
    chk.has_index = index.exists()
    if not chk.has_index:
        # A 200.html SPA shell can substitute for index.html.
        if not (path / "200.html").exists():
            chk.issues.append("no index.html and no 200.html — nothing to serve")

    cname = path / "CNAME"
    if cname.exists():
        chk.cname = cname.read_text(encoding="utf-8").strip().splitlines()[0] if cname.read_text(encoding="utf-8").strip() else None
        if chk.cname:
            chk.notes.append(f"CNAME domain: {chk.cname}")
        else:
            chk.issues.append("CNAME file exists but is empty")

    chk.has_200 = (path / "200.html").exists()
    chk.has_404 = (path / "404.html").exists()
    chk.has_surgeignore = (path / ".surgeignore").exists()

    # Heuristic: if node_modules is large and there is no .surgeignore, warn.
    nm = path / "node_modules"
    if nm.exists() and not chk.has_surgeignore:
        chk.notes.append(
            "node_modules present but no .surgeignore — consider adding "
            "'node_modules/' to .surgeignore to avoid uploading dependencies"
        )

    # Heuristic: warn about obviously sensitive files that would be published.
    for sensitive in (".env", ".env.local", ".npmrc", ".git/credentials"):
        sp = path / sensitive
        if sp.exists() and not _ignored_by_surgeignore(path, sensitive):
            chk.issues.append(
                f"sensitive file would be published: {sensitive} "
                f"(add to .surgeignore or delete)"
            )

    return chk


def _ignored_by_surgeignore(project_root: Path, rel_path: str) -> bool:
    """Very small .surgeignore matcher — supports plain name and dir/ entries."""
    si = project_root / ".surgeignore"
    if not si.exists():
        return False
    try:
        lines = [l.strip() for l in si.read_text(encoding="utf-8").splitlines()]
    except Exception:
        return False
    name = rel_path.split("/")[0]
    for line in lines:
        if not line or line.startswith("#"):
            continue
        pattern = line.rstrip("/")
        if pattern == name or pattern == rel_path:
            return True
    return False


def merge_ignore_files(project_root: Path) -> str:
    """Combine .surgeignore + .gitignore into a single surgeignore body.

    Surge only reads .surgeignore. If a project relies on .gitignore but
    doesn't have a .surgeignore, this helper produces a body the caller can
    write to .surgeignore before publishing.
    """
    seen: List[str] = []
    for name in (".surgeignore", ".gitignore"):
        p = project_root / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line not in seen:
                seen.append(line)
    return "\n".join(seen) + ("\n" if seen else "")
