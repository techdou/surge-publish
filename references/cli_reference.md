# Surge CLI Reference

Complete reference for every subcommand exposed by `surge_cli.py`. All commands
accept `--format json`, `--token`, and `--timeout`.

## check

Pre-flight project validation. No surge call, no auth needed.

```bash
python scripts/surge_cli.py check <path>
python scripts/surge_cli.py check <path> --fix-ignore   # write .surgeignore from .gitignore
python scripts/surge_cli.py check <path> --strict        # exit 1 on any issue
python scripts/surge_cli.py check <path> --format json
```

Verifies:
- `index.html` exists (or `200.html` SPA shell as substitute)
- Reads `CNAME` if present
- Flags sensitive files that would be published (`.env`, `.npmrc`, etc.) unless covered by `.surgeignore`
- Warns about `node_modules` without `.surgeignore`

## publish

Deploy a directory. Runs `check` first unless `--no-check`.

```bash
python scripts/surge_cli.py publish <path>
python scripts/surge_cli.py publish <path> --domain example.com
python scripts/surge_cli.py publish <path> --domain example.com --preview
python scripts/surge_cli.py publish <path> --no-check --force
```

- Without `--domain`, surge reads `CNAME` or prompts (skill blocks the prompt — always pass `--domain` or have a `CNAME`).
- `--preview` publishes a revision with its own URL without touching production.
- `--force` overrides pre-flight issues.

Output includes `url` (extracted live URL), `ok`, and `returncode`.

## list

List all your projects, or revisions for one project.

```bash
python scripts/surge_cli.py list
python scripts/surge_cli.py list example.com
```

## rollback / rollfore / cutover

Move between revisions.

```bash
python scripts/surge_cli.py rollback example.com   # previous revision
python scripts/surge_cli.py rollfore example.com   # next revision
python scripts/surge_cli.py cutover example.com    # latest revision
```

## teardown

Permanently remove a published project. Requires `--yes`.

```bash
python scripts/surge_cli.py teardown example.com --yes
```

## encrypt

Provision a managed SSL certificate for a custom domain.

```bash
python scripts/surge_cli.py encrypt example.com
```

For surge.sh subdomains, HTTPS is automatic — `encrypt` is only needed for custom domains.

## dns

View / add / remove DNS records.

```bash
python scripts/surge_cli.py dns view example.com
python scripts/surge_cli.py dns add example.com --type A --name www --value 1.2.3.4
python scripts/surge_cli.py dns add example.com --type CNAME --name @ --value example.surge.sh
python scripts/surge_cli.py dns rem example.com --record-id <id>
```

Record IDs come from `dns view`.

## token

Mint an automation token. Printed once — store it immediately.

```bash
python scripts/surge_cli.py token
```

Then export in your shell: `export SURGE_TOKEN=<token>`

## whoami / login / logout

```bash
python scripts/surge_cli.py whoami    # structured auth state
python scripts/surge_cli.py login     # verifies SURGE_TOKEN/SURGE_LOGIN (does NOT do interactive login)
python scripts/surge_cli.py logout
```

The upstream `surge login` is interactive (email/password prompt). In agent
mode, set `SURGE_TOKEN` instead. The skill's `login` subcommand only checks
whether the env-based auth is usable.
