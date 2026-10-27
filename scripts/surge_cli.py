#!/usr/bin/env python3
"""Unified CLI entrypoint for the surge-publish skill.

Wraps the upstream `surge` Node CLI in a non-interactive, JSON-friendly
Python layer with pre-flight checks. All commands that produce structured
data support `--format json`.

Subcommands map 1:1 to the upstream surge verbs, plus extras:
  check       Pre-flight project check (no surge call)
  whoami      Auth state
  publish     Deploy a directory to a domain (with pre-flight check)
  list        List projects or a project's revisions
  rollback    Roll back to the previous revision
  rollfore    Roll forward to the next revision
  cutover     Cut over to the latest revision
  teardown    Remove a published project
  dns         View / add / remove DNS records
  encrypt     Provision an SSL cert for a custom domain
  token       Mint an automation token
  login       Authenticate (interactive upstream; here only checks token env)
  logout      Expire local token
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import surge_common as sc  # noqa: E402


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _emit(data: Any, *, fmt: str = "text", text_fn=None) -> None:
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        if text_fn:
            print(text_fn(data))
        else:
            print(data if isinstance(data, str) else json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    """Pre-flight project check. No surge call. Never raises."""
    path = Path(args.path).resolve()
    chk = sc.check_project(path)
    if args.fix_ignore and not chk.has_surgeignore:
        body = sc.merge_ignore_files(path)
        if body:
            (path / ".surgeignore").write_text(body, encoding="utf-8")
            chk.has_surgeignore = True
            chk.notes.append("wrote .surgeignore (merged from .gitignore)")
    _emit(chk.as_dict(), fmt=args.format, text_fn=lambda c: _format_check(c))
    # Blocking only on actual issues, not on informational notes.
    return 1 if (chk.issues and args.strict) else 0


def _format_check(c: Dict[str, Any]) -> str:
    lines = [f"project: {c['path']}"]
    lines.append(f"  CNAME: {c.get('cname') or '(none — surge will prompt or assign)'}")
    lines.append(f"  index.html: {'yes' if c['has_index'] else 'NO'}")
    lines.append(f"  200.html (SPA shell): {'yes' if c.get('has_200_shell') else 'no'}")
    lines.append(f"  404.html: {'yes' if c.get('has_404') else 'no'}")
    lines.append(f"  .surgeignore: {'yes' if c.get('has_surgeignore') else 'no'}")
    if c.get("issues"):
        lines.append("issues:")
        for i in c["issues"]:
            lines.append(f"  [ISSUE] {i}")
    if c.get("notes"):
        lines.append("notes:")
        for n in c["notes"]:
            lines.append(f"  [note] {n}")
    if not c.get("issues"):
        lines.append("status: ok (no blocking issues)")
    return "\n".join(lines)


def cmd_whoami(args: argparse.Namespace) -> int:
    state = sc.whoami()
    _emit(state.as_dict(), fmt=args.format, text_fn=lambda s: (
        f"authenticated: {s['authenticated']}\n"
        f"email: {s.get('email') or '-'}\n"
        f"plan: {s.get('plan') or '-'}"
    ))
    return 0 if state.authenticated else 1


def cmd_publish(args: argparse.Namespace) -> int:
    """Publish a directory. Runs pre-flight check unless --no-check.

    Success requires BOTH returncode 0 AND an explicit success marker in
    surge's output ("Success!" / a published URL). surge can exit 0 while
    silently failing (swallowed interactive prompt, network hiccup), so a
    bare returncode is not proof of publication.
    """
    path = Path(args.path).resolve()
    if not args.no_check:
        chk = sc.check_project(path)
        if chk.issues and not args.force:
            _emit({"ok": False, "blocked_by": chk.issues, "check": chk.as_dict()},
                  fmt=args.format)
            return 1
    surge_args = [str(path)]
    if args.domain:
        surge_args.append(args.domain)
    if args.preview:
        surge_args.append("--preview")
    result = sc.run_surge(surge_args, cwd=path, check=False,
                          token=args.token, timeout=args.timeout)
    url = sc.extract_published_url(result.stdout)
    confirmed = bool(url) or ("success" in result.stdout.lower())
    payload = {
        "ok": result.ok and confirmed,
        "confirmed": confirmed,
        "url": url,
        "domain": args.domain,
        "preview": bool(args.preview),
        "returncode": result.returncode,
        "output": result.output(),
    }
    if result.ok and not confirmed:
        payload["hint"] = ("surge exited 0 but printed no success marker — "
                           "treat this as NOT published; re-run and check output")
    _emit(payload, fmt=args.format, text_fn=lambda p: (
        f"{'[OK]' if p['ok'] else '[FAIL]'} {p.get('url') or p.get('domain') or 'publish'}\n"
        + (p.get("hint") or "")
        + (p.get("output") or "")
    ))
    if not payload["ok"]:
        return 1
    if args.verify_contains:
        target = url or args.domain
        return cmd_verify(argparse.Namespace(
            url=("https://" + target if target and not target.startswith("http") else target),
            contains=args.verify_contains, timeout=30, format=args.format))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Content-level verification of a live URL.

    Fetches with a cache-busting query param + no-cache headers, then requires
    every --contains marker to appear in the body. HTTP 200 alone proves
    nothing about which revision is being served.
    """
    import random
    import time
    import urllib.request

    bust = (f"{args.url}{'&' if '?' in args.url else '?'}"
            f"_v={int(time.time())}{random.randint(100, 999)}")
    req = urllib.request.Request(bust, headers={
        "Cache-Control": "no-cache, max-age=0",
        "User-Agent": "surge-cli-verify/1.1",
    })
    status, body, err = None, "", None
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as r:
            status = r.status
            body = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — report any fetch failure verbatim
        err = f"{type(e).__name__}: {e}"
    missing = [m for m in (args.contains or []) if m not in body] if body else list(args.contains or [])
    payload = {
        "ok": err is None and status == 200 and not missing,
        "fetched_url": bust,
        "http_status": status,
        "bytes": len(body),
        "required_markers": args.contains,
        "missing_markers": missing,
        "error": err,
    }
    _emit(payload, fmt=args.format, text_fn=lambda p: (
        f"{'[OK]' if p['ok'] else '[FAIL]'} {p['fetched_url']} "
        f"(http {p['http_status']}, {p['bytes']} bytes)\n"
        + (f"missing markers: {p['missing_markers']}\n" if p["missing_markers"] else "")
        + (f"{p['error']}\n" if p["error"] else "")
        + ("live content verified" if p["ok"] else "live content does NOT match — republish and re-verify")
    ))
    return 0 if payload["ok"] else 2


def cmd_simple(args: argparse.Namespace, surge_args: List[str],
               label: str) -> int:
    """Generic runner for list/rollback/rollfore/cutover/teardown/etc."""
    result = sc.run_surge(surge_args, check=False, token=args.token,
                          timeout=args.timeout)
    payload = {
        "ok": result.ok,
        "command": label,
        "returncode": result.returncode,
        "output": result.output(),
    }
    _emit(payload, fmt=args.format, text_fn=lambda p: p.get("output") or "")
    return 0 if result.ok else 1


def cmd_list(args: argparse.Namespace) -> int:
    surge_args = ["list"]
    if args.domain:
        surge_args.append(args.domain)
    return cmd_simple(args, surge_args, "list")


def cmd_rollback(args: argparse.Namespace) -> int:
    return cmd_simple(args, ["rollback", args.domain], "rollback")


def cmd_rollfore(args: argparse.Namespace) -> int:
    return cmd_simple(args, ["rollfore", args.domain], "rollfore")


def cmd_cutover(args: argparse.Namespace) -> int:
    return cmd_simple(args, ["cutover", args.domain], "cutover")


def cmd_teardown(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to teardown without --yes (this permanently removes the project).",
              file=sys.stderr)
        return 1
    return cmd_simple(args, ["teardown", args.domain], "teardown")


def cmd_encrypt(args: argparse.Namespace) -> int:
    return cmd_simple(args, ["encrypt", args.domain], "encrypt")


def cmd_dns(args: argparse.Namespace) -> int:
    if args.action == "view":
        surge_args = ["dns", args.domain]
    elif args.action == "add":
        if not (args.type and args.name and args.value):
            print("dns add requires --type --name --value", file=sys.stderr)
            return 1
        surge_args = ["dns", args.domain, "add", args.type, args.name, args.value]
    elif args.action == "rem":
        if not args.record_id:
            print("dns rem requires --record-id", file=sys.stderr)
            return 1
        surge_args = ["dns", args.domain, "rem", args.record_id]
    else:
        print(f"unknown dns action: {args.action}", file=sys.stderr)
        return 1
    return cmd_simple(args, surge_args, "dns")


def cmd_token(args: argparse.Namespace) -> int:
    """Mint an automation token. The token is printed once and never again."""
    result = sc.run_surge(["token"], check=False, token=args.token)
    payload = {
        "ok": result.ok,
        "token": result.stdout.strip() if result.ok else None,
        "output": result.output(),
    }
    _emit(payload, fmt=args.format, text_fn=lambda p: (
        p["token"] if p["ok"] else f"[FAIL] {p['output']}"
    ))
    return 0 if result.ok else 1


def cmd_login(args: argparse.Namespace) -> int:
    """The upstream `surge login` is interactive. In agent mode we instead
    verify that SURGE_TOKEN/SURGE_LOGIN are usable via whoami."""
    state = sc.whoami()
    _emit(state.as_dict(), fmt=args.format, text_fn=lambda s: (
        f"authenticated: {s['authenticated']}\n"
        + (f"email: {s['email']}\nplan: {s.get('plan') or '-'}" if s["authenticated"]
           else "Not authenticated. Set SURGE_TOKEN and SURGE_LOGIN env vars, "
                "or run `surge login` interactively in a terminal.")
    ))
    return 0 if state.authenticated else 1


def cmd_logout(args: argparse.Namespace) -> int:
    return cmd_simple(args, ["logout"], "logout")


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--format", choices=("text", "json"), default="text")
    p.add_argument("--token", default=None, help="Surge API token (defaults to SURGE_TOKEN env)")
    p.add_argument("--timeout", type=int, default=300)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="surge_cli.py",
        description="Non-interactive wrapper around the surge CLI for static-site publishing.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # check
    p = sub.add_parser("check", help="Pre-flight project check (no surge call).")
    p.add_argument("path", help="Project directory to check.")
    p.add_argument("--fix-ignore", action="store_true",
                   help="Write a merged .surgeignore if one is missing.")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero if any issues are found.")
    _add_common(p)
    p.set_defaults(func=cmd_check)

    # whoami
    p = sub.add_parser("whoami", help="Show authenticated user.")
    _add_common(p)
    p.set_defaults(func=cmd_whoami)

    # publish
    p = sub.add_parser("publish", help="Publish a directory to a domain.")
    p.add_argument("path", help="Project directory to publish.")
    p.add_argument("--domain", help="Target domain. If omitted, surge uses CNAME or prompts.")
    p.add_argument("--preview", action="store_true", help="Publish a preview without touching production.")
    p.add_argument("--no-check", action="store_true", help="Skip pre-flight project check.")
    p.add_argument("--force", action="store_true",
                   help="Publish even if the pre-flight check reports issues.")
    p.add_argument("--verify-contains", action="append", metavar="MARKER", default=[],
                   help="After publish, fetch the live URL and require this marker "
                        "(repeatable). Content-level verification, not just status codes.")
    _add_common(p)
    p.set_defaults(func=cmd_publish)

    # verify
    p = sub.add_parser("verify", help="Content-level verification of a live URL.")
    p.add_argument("url", help="Live URL to fetch (cache-busted automatically).")
    p.add_argument("--contains", action="append", metavar="MARKER", default=[],
                   help="Marker that must appear in the page body (repeatable; "
                        "all must match). Pick markers unique to the NEW revision.")
    _add_common(p)
    p.set_defaults(func=cmd_verify)

    # list
    p = sub.add_parser("list", help="List projects, or a project's revisions.")
    p.add_argument("domain", nargs="?", help="Optional: list revisions for this domain.")
    _add_common(p)
    p.set_defaults(func=cmd_list)

    # rollback / rollfore / cutover
    for name, fn in (("rollback", cmd_rollback), ("rollfore", cmd_rollfore),
                     ("cutover", cmd_cutover)):
        p = sub.add_parser(name, help=f"{name} a project's revision.")
        p.add_argument("domain")
        _add_common(p)
        p.set_defaults(func=fn)

    # teardown
    p = sub.add_parser("teardown", help="Remove a published project (destructive).")
    p.add_argument("domain")
    p.add_argument("--yes", action="store_true", help="Confirm teardown.")
    _add_common(p)
    p.set_defaults(func=cmd_teardown)

    # encrypt
    p = sub.add_parser("encrypt", help="Provision an SSL certificate for a custom domain.")
    p.add_argument("domain")
    _add_common(p)
    p.set_defaults(func=cmd_encrypt)

    # dns
    p = sub.add_parser("dns", help="View / add / remove DNS records.")
    p.add_argument("action", choices=("view", "add", "rem"))
    p.add_argument("domain")
    p.add_argument("--type", help="Record type (A, CNAME, MX, TXT, ...)")
    p.add_argument("--name", help="Record name (e.g. 'www' or '@')")
    p.add_argument("--value", help="Record value")
    p.add_argument("--record-id", help="ID of the record to remove")
    _add_common(p)
    p.set_defaults(func=cmd_dns)

    # token
    p = sub.add_parser("token", help="Mint an automation token (printed once).")
    _add_common(p)
    p.set_defaults(func=cmd_token)

    # login / logout
    p = sub.add_parser("login", help="Check auth state (upstream login is interactive).")
    _add_common(p)
    p.set_defaults(func=cmd_login)
    p = sub.add_parser("logout", help="Expire local token.")
    _add_common(p)
    p.set_defaults(func=cmd_logout)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except sc.SurgeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
