# CI/CD Automation

Surge is well-suited for automated deploys from CI. The key: mint a token once
and inject it via `SURGE_TOKEN`.

## Mint a token

In a local terminal (interactive):

```bash
surge login        # email + password, one time
surge token        # prints a long-lived token
```

Copy the token.

## Set it in CI

GitHub Actions example:

```yaml
- name: Deploy to Surge
  env:
    SURGE_TOKEN: ${{ secrets.SURGE_TOKEN }}
    SURGE_LOGIN: ${{ secrets.SURGE_LOGIN }}   # the email used to mint the token
  run: |
    npm install --global surge
    python skills/surge-publish/scripts/surge_cli.py publish ./dist --domain ${{ env.DOMAIN }}
```

Store `SURGE_TOKEN` and `SURGE_LOGIN` as repository secrets.

## Preview deploys per PR

```yaml
- name: Preview deploy
  env:
    SURGE_TOKEN: ${{ secrets.SURGE_TOKEN }}
    SURGE_LOGIN: ${{ secrets.SURGE_LOGIN }}
  run: |
    python skills/surge-publish/scripts/surge_cli.py publish ./build --preview --format json > deploy.json
    # Extract the preview URL and post it as a PR comment.
```

## Non-interactive safety

The skill's `run_surge` wrapper:
- Always sets `CI=true`
- Redirects stdin from `/dev/null` so surge can never hang on a prompt
- Pre-checks auth and fails fast (≈0.4s) if `SURGE_TOKEN` is missing

## Common CI checklist

Before the deploy step:
1. Build artifacts exist (`dist/`, `build/`, `out/`, etc.)
2. `CNAME` is in the build dir, or `--domain` is passed
3. `.surgeignore` excludes `node_modules/`, source files, `.env`
4. For SPAs: build renames `index.html` to `200.html` (or includes both)

Run `python scripts/surge_cli.py check ./dist --strict` as a CI gate before publish.
