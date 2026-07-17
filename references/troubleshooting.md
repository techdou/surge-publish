# Troubleshooting

## "Not authenticated. Set SURGE_TOKEN..."

The skill refused to run surge because you're not logged in and no token env
var is set. Surge's upstream CLI would otherwise hang on an interactive prompt.

Fix:
1. In a real terminal (not the agent): `surge login` (email + password, one time)
2. `surge token` — copy the printed token
3. Export in your shell: `export SURGE_TOKEN=<token>` (and `export SURGE_LOGIN=<your-email>`)
4. Re-run the skill command

## "surge CLI is not installed"

Fix: `npm install --global surge` (requires Node.js).

## Publish hangs / agent stalls

This should never happen — the skill forces non-interactive mode and redirects
stdin from /dev/null. If it does, you may be calling the upstream `surge` binary
directly instead of the skill's `surge_cli.py`. Always go through the skill.

## Sensitive file would be published

The `check` command flagged `.env`, `.npmrc`, or similar. Either:
- Add to `.surgeignore`: `echo '.env' >> .surgeignore`
- Or use `check --fix-ignore` to auto-generate a merged ignore file

Then re-run `check`.

## Deep links break on refresh (SPA)

You're missing `200.html`. Your SPA build likely produces only `index.html`.
Surge serves `index.html` for `/` but returns 404 for deep links like `/users/42`.

Fix: copy or symlink your build's `index.html` to `200.html` in the publish dir:

```bash
cp dist/index.html dist/200.html
```

## Custom domain shows Surge's page / not my site

DNS isn't pointing at Surge yet. Either:
- Use Surge's nameservers (`ns1.surge.world` ... `ns4.surge.world`) — set at your registrar
- Or add a `CNAME` record pointing your domain to `YOUR-PROJECT.surge.sh`

Check with `python scripts/surge_cli.py dns view yourdomain.com`.

## SSL not working on custom domain

Surge subdomains get HTTPS automatically. Custom domains need a one-shot
provisioning step:

```bash
python scripts/surge_cli.py encrypt yourdomain.com
```

After DNS propagates (minutes to hours), the certificate is issued.

## "domain already taken"

Free surge.sh subdomains are first-come. Pick a different subdomain, or use
your own custom domain (free with surge).

## Accidentally published a bad deploy

Roll back in seconds:

```bash
python scripts/surge_cli.py rollback yourdomain.com
```

Every deploy is a revision with its own permanent preview URL. Use `list <domain>`
to see all revisions.
