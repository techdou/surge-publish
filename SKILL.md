---
name: surge-publish
version: 1.0.0
description: Publish static web projects (HTML/CSS/JS, single-page apps, generated sites) to the web via surge.sh. Use whenever the user wants to deploy a static site, publish a build folder, put HTML online, host a landing page, share a dist/ directory, set up a preview URL, roll back a deploy, manage a surge.sh domain, configure DNS, provision SSL, or anything involving surge.sh — even if they don't say "surge" explicitly. Covers project pre-flight checks (CNAME, index.html, 200.html SPA shell, .surgeignore, sensitive-file leaks), non-interactive publishing with SURGE_TOKEN, preview deploys, revisions/rollback, custom domains, DNS, and SSL.
---

# Surge Publish Skill

Use this skill when the user wants to put a static web project on the web using [surge.sh](https://surge.sh). Surge publishes a directory of HTML/CSS/JS to a global CDN with HTTPS, clean URLs, custom domains, free SSL, and instant rollbacks — all from the command line.

## Prerequisites

- Node.js installed
- surge CLI: `npm install --global surge` (skill checks for this and reports clearly if missing)
- Authentication: set `SURGE_TOKEN` env var (mint one with `surge token` in a terminal). The skill **never** runs surge interactively — it fails fast with a clear message if not authenticated.

## Progressive disclosure: pick the smallest command

| Task | Command |
|---|---|
| Check a project before publishing (no surge call) | `python scripts/surge_cli.py check <path>` |
| Publish a directory | `python scripts/surge_cli.py publish <path> --domain <domain>` |
| Publish a preview (separate URL, prod untouched) | `python scripts/surge_cli.py publish <path> --preview` |
| List projects or revisions | `python scripts/surge_cli.py list [domain]` |
| Roll back / forward / cut over | `python scripts/surge_cli.py rollback <domain>` |
| Tear down a project | `python scripts/surge_cli.py teardown <domain> --yes` |
| Provision SSL for a custom domain | `python scripts/surge_cli.py encrypt <domain>` |
| DNS view / add / remove | `python scripts/surge_cli.py dns view <domain>` |
| Mint an automation token | `python scripts/surge_cli.py token` |
| Check auth state | `python scripts/surge_cli.py whoami` |

All commands accept `--format json` for structured output. Pass `--token` or set `SURGE_TOKEN`.

## Core workflow

1. **Pre-flight check**: `check <path>` verifies index.html (or 200.html SPA shell), reads CNAME, flags sensitive files (.env, .git) that would be published, and warns about missing `.surgeignore`. Use `--fix-ignore` to auto-write a merged `.surgeignore` from `.gitignore`.
2. **Publish**: `publish <path> --domain <domain>` runs the check first (unless `--no-check`) and refuses to publish if issues are found (override with `--force`).
3. **Verify**: the publish command extracts the live URL from surge's output.
4. **Roll back if needed**: `rollback <domain>` restores the previous revision.

## What every Surge project gets

- Global CDN, HTTPS out of the box, clean URLs (`/about` serves `about.html`)
- Custom domains (free) + managed SSL via `surge encrypt`
- Every deploy is a revision with its own permanent preview URL
- Client-side routing via `200.html`, custom 404 via `404.html`

## Configuration is files in the project

| File | Purpose |
|---|---|
| `CNAME` | Target domain (single line). With this, `publish <path>` needs no `--domain`. |
| `.surgeignore` | Exclude files from deploy (gitignore syntax). |
| `200.html` | SPA shell for unmatched URLs (client-side routing). |
| `404.html` | Custom not-found page. |
| `ROUTER` | Redirect rules (paid plan). |
| `AUTH` | HTTP basic auth (paid plan). |
| `CORS` | Cross-origin headers (paid plan). |

These travel with the deploy, so every revision carries its own configuration.

## Safety model

The skill is non-interactive by design:

- If `SURGE_TOKEN` / `SURGE_LOGIN` is not set and the user isn't logged in, every command that needs auth **fails fast** (≈0.4s) with a clear message — it never blocks on surge's interactive login prompt.
- `teardown` requires explicit `--yes`.
- `publish` runs the pre-flight check by default and refuses on issues unless `--force`.
- stdin is redirected from /dev/null so surge cannot hang on a prompt.

## Sample site

`assets/sample-site/` contains a minimal valid project (index.html + about.html demonstrating clean URLs + 404.html + .surgeignore). Use it to demonstrate the check command or as a template.

## Details

Load deeper docs only when needed:

- `references/cli_reference.md` — every surge subcommand with flags and examples
- `references/project_config.md` — CNAME, .surgeignore, 200.html, 404.html, ROUTER, AUTH, CORS formats
- `references/ci_automation.md` — token-based deploys from CI/CD pipelines
- `references/troubleshooting.md` — common errors (auth, DNS propagation, SPA routing)
