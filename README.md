# Surge Publish Skill | Surge 发布 Skill

[English](#english) | [中文](#中文)

---

<a id="中文"></a>
## 中文

可移植 Agent Skill，把静态 Web 项目（HTML/CSS/JS、单页应用、生成的站点）一键发布到 [surge.sh](https://surge.sh) 全球 CDN。

### 触发场景

- 发布静态站点、部署 dist/ 目录、托管 landing page
- 设置预览 URL、回滚部署、管理 surge.sh 域名
- 配置 DNS、签发 SSL、敏感文件泄露检查

下方英文为完整文档。

---

<a id="english"></a>
## English

A [ZCode](https://zcode.ai) / Claude Code / OpenCode agent skill for publishing static web projects to [surge.sh](https://surge.sh) — a global CDN for HTML/CSS/JS, single-page apps, and generated sites.

## Features

- **Project pre-flight checks**: validates `index.html` / `200.html` SPA shell, reads `CNAME`, flags sensitive files (`.env`, `.git`) that would leak, warns about `node_modules` without `.surgeignore`.
- **Non-interactive publishing**: never hangs on surge's login prompt. Fails fast with a clear message if `SURGE_TOKEN` isn't set.
- **Full CLI surface**: publish, preview, list, rollback/rollfore/cutover, teardown, DNS, SSL encrypt, token, whoami.
- **Auto-merge `.gitignore` → `.surgeignore`** so npm projects don't accidentally ship `node_modules`.
- **JSON output** on every command for programmatic use.
- **Bundled sample site** at `assets/sample-site/` demonstrating clean URLs, custom 404, and `.surgeignore`.

## Prerequisites

- Node.js + npm
- surge CLI: `npm install --global surge`
- A surge account + token. Mint one with `surge token` (in a real terminal, one time), then:
  ```bash
  export SURGE_TOKEN=<token>
  export SURGE_LOGIN=<your-email>
  ```

## Quick Start

```bash
git clone https://github.com/techdou/surge-publish.git ~/.agents/skills/surge-publish
```

Then in any project with an `index.html`:

```bash
# Pre-flight check
python ~/.agents/skills/surge-publish/scripts/surge_cli.py check .

# Publish
python ~/.agents/skills/surge-publish/scripts/surge_cli.py publish . --domain my-project.surge.sh

# Roll back a bad deploy
python ~/.agents/skills/surge-publish/scripts/surge_cli.py rollback my-project.surge.sh
```

## Commands

| Command | What it does |
|---|---|
| `check <path>` | Pre-flight project validation (no surge call, no auth needed) |
| `publish <path> [--domain x] [--preview]` | Deploy a directory |
| `list [domain]` | List projects or revisions |
| `rollback / rollfore / cutover <domain>` | Move between revisions |
| `teardown <domain> --yes` | Permanently remove a project |
| `encrypt <domain>` | Provision SSL for a custom domain |
| `dns view/add/rem <domain>` | Manage DNS records |
| `token` | Mint an automation token |
| `whoami` | Show auth state |

All commands accept `--format json` and `--token`.

## Sample Site

`assets/sample-site/` is a minimal valid Surge project (index.html + about.html demonstrating clean URLs + 404.html + .surgeignore). Use it to demo `check`:

```bash
python scripts/surge_cli.py check assets/sample-site
```

## Repository Structure

```
surge-publish/
├── SKILL.md
├── README.md
├── scripts/
│   ├── surge_cli.py        # Unified CLI: check/publish/list/rollback/dns/encrypt/...
│   └── surge_common.py     # surge wrapper, pre-flight check, ignore-file merge
├── references/
│   ├── cli_reference.md
│   ├── project_config.md
│   ├── ci_automation.md
│   └── troubleshooting.md
├── assets/
│   └── sample-site/        # index.html, about.html, 404.html, .surgeignore
└── tests/
    └── test_surge_skill.py # 22 unit tests, no network calls
```

## Tests

Pure-unit tests (no surge account needed):

```bash
python -m unittest discover -s tests -v
```

## Safety Model

- If `SURGE_TOKEN` / `SURGE_LOGIN` is missing and the user isn't logged in, every auth-requiring command fails in ~0.4s with a clear message — never blocks on surge's interactive prompt.
- `teardown` requires explicit `--yes`.
- `publish` runs the pre-flight check by default; `--force` overrides.
- stdin is redirected from `/dev/null` so surge can never hang.

## License

MIT
