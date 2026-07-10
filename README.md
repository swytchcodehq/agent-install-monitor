# Agent Install Monitor

Tracks every package install, container pull, git clone, and other
integration action your [Hermes Agent](https://github.com/NousResearch/hermes-agent)
runs through its `terminal` tool. Visibility, not control — no rollback, no
uninstall, no approvals.

## Installation

Run the installer — it finds Hermes's own venv, installs into it (not your
shell's Python, which wouldn't be discoverable as a plugin), enables the
plugin, and offers to put `agent-monitor` on your `$PATH`. Safe to re-run.

```bash
# macOS / Linux / WSL
curl -fsSL https://raw.githubusercontent.com/swytchcodehq/agent-install-monitor/main/install.py | python3

# Windows (PowerShell)
irm https://raw.githubusercontent.com/swytchcodehq/agent-install-monitor/main/install.py | python -
```

<details>
<summary>Manual install (if you'd rather not pipe a script into your shell)</summary>

Install into the **same Python environment `hermes` runs in**, not your
system/shell Python — that's what makes it discoverable as a plugin.

```bash
# find hermes's project root — the venv lives at <that path>/venv
hermes --version        # look for the "Project:" or "Install directory:" line
                         # (the label has changed across Hermes versions)

# install into that venv's pip (not your shell's pip)
/path/from/above/venv/bin/pip install agent-install-monitor
```

`which hermes` usually points at a wrapper script (from the standard
installer), not a symlink — `readlink -f` won't resolve it to the venv, so
use `hermes --version`'s output instead.

Enable the plugin:

```bash
hermes plugins enable agent-monitor
```

> If your Hermes CLI is older and `hermes plugins enable` doesn't recognize
> `agent-monitor` ("plugin not found"), add it to `~/.hermes/config.yaml`
> by hand:
> ```yaml
> plugins:
>   enabled:
>     - agent-monitor
> ```

Optional — put the CLI on your `$PATH`:

```bash
export PATH="/path/from/above/venv/bin:$PATH"
```

</details>

## Usage

Just use Hermes normally. Afterwards, in a regular terminal:

```bash
agent-monitor history          # most recent session
agent-monitor sessions         # list all recorded sessions
agent-monitor session <id>     # a specific session
agent-monitor export [--session ID] [--format json|csv]
```

Example output:

```
Session sess-abc123 [hermes]
Packages
  ✓ npm      discord.js
  ✓ pip      openai
  ✓ brew     ffmpeg
Containers
  ✓ postgres:16
Repositories
  ✓ github.com/foo/bar
Directories
  1. ~/projects/test

Time: 2m 31s   Commands: 18
```

Data lives in `$HERMES_HOME/agent-monitor/monitor.db` (default
`~/.hermes/agent-monitor/monitor.db`). Nothing leaves your machine.

## What's detected

Package managers (npm, pnpm, yarn, pip, uv, poetry, cargo, go, brew, apt,
dnf, apk, gem, composer, dotnet, nuget, choco, winget, scoop), containers (`docker`/`podman
pull|run`, `docker compose up`), git (`clone`, `submodule add/update`),
runtimes (`npx`, `uvx`, `cargo run`, `go run`), services (`systemctl`,
`brew services`, `service`), database creation (`createdb`, `CREATE
DATABASE`), and installer downloads (`curl`/`wget` fetching `.sh`/`.exe`/etc).
Detection is a best-effort command-string match, not a security boundary.

## Development

```bash
pip install -e ".[dev]"
pytest
```
