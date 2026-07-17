# Project Configuration Files

Surge's core idea: **your project directory is the configuration**. Behavior is
controlled by files that deploy with your code, so every revision carries its
own complete configuration.

## CNAME — target domain

A single line with the domain. Lets you run `surge <path>` (or the skill's
`publish <path>`) without passing `--domain` every time.

```bash
echo "example.com" > CNAME
```

Or use a free surge.sh subdomain:

```bash
echo "my-project.surge.sh" > CNAME
```

## .surgeignore — exclude files

Same syntax as `.gitignore`. Surge only reads `.surgeignore` (NOT `.gitignore`),
so if your project relies on `.gitignore` exclusions you must mirror them here.
The skill's `check --fix-ignore` command does this automatically by merging
`.gitignore` + `.surgeignore`.

```gitignore
# Build tooling
node_modules/
package-lock.json

# Source files
src/
*.md
*.log

# Version control
.git
.gitignore

# Editor / OS
.DS_Store
Thumbs.db
.vscode/
```

**Critical**: never publish `.env`, credentials, or `.git/` — add them to
`.surgeignore`. The skill's `check` command flags these as issues.

## 200.html — SPA routing shell

For single-page apps (React/Vue/Angular/etc.), name your app shell `200.html`.
When a visitor hits a URL that doesn't match a static file, Surge serves
`200.html` instead of a 404, so your client-side router can take over. Without
this, deep links break on refresh.

```bash
# Typical SPA build output
dist/
  200.html      # your index.html, renamed (or symlinked)
  index.html
  assets/...
```

## 404.html — custom not-found page

A static fallback served when no file matches and no `200.html` exists.

## ROUTER — redirect rules (paid plan)

One rule per line: `source destination [code]`.

```
/old-path /new-path 301
/legacy/* /archive/$1 302
```

## AUTH — HTTP basic auth (paid plan)

```
username:password
```

## CORS — cross-origin headers (paid plan)

One header per line, applied to every response.

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, HEAD
```

## Control files are never served

`ROUTER`, `AUTH`, `CORS` are read by the platform but **never** delivered to
visitors, so they're safe to commit.
