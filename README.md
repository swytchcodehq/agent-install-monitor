# Agent Install Monitor

![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Hermes Plugin](https://img.shields.io/badge/Hermes-Plugin-6E56CF.svg)
![Local First](https://img.shields.io/badge/local--first-yes-brightgreen.svg)

Track everything your AI agent installs on your machine.

Agent Install Monitor records package installs, Docker images, Git
repositories, services, and other environment changes made by
[Hermes Agent](https://github.com/NousResearch/hermes-agent).

- Works with Hermes
- Planned: Claude Code, OpenClaw, and more
- Local-first: nothing leaves your machine

```
$ agent-monitor history

Session sess-8f3a21 [hermes]
Packages
  1. pip      playwright
  2. pip      openai

Time: 2m 13s   Commands: 2
```

## Why?

AI coding agents frequently install packages, pull Docker images, clone
repositories, and start services on your behalf. A few weeks later it's easy
to lose track:

- Why is Playwright installed?
- Where did this Docker image come from?
- Which repository did the agent clone?
- What changed during that task?

Agent Install Monitor keeps a local history of everything your AI agent
installed, so you can always answer those questions.

It's an observability tool, not a control layer It does **not** modify
execution, uninstall packages, or perform rollback.

## Installation

Run the installer. It finds Hermes's own venv, installs into it (not your
shell's Python, which wouldn't be discoverable as a plugin), enables the
plugin, and offers to put `agent-monitor` on your `$PATH`. Safe to re-run.

It installs from PyPI, and falls back to the same version from the GitHub
release if PyPI isn't available. To pick one, add `--source pypi` or
`--source github` (for example `... | python3 - --source github`).

### macOS / Linux / WSL

```
curl -fsSL https://raw.githubusercontent.com/swytchcodehq/agent-install-monitor/main/install.py | python3
```

### Windows (PowerShell)
```
irm https://raw.githubusercontent.com/swytchcodehq/agent-install-monitor/main/install.py | python -
```

<details>
<summary>Manual install (if you'd rather not pipe a script into your shell)</summary>

Install into the **same Python environment `hermes` runs in**, not your
system/shell Python - that's what makes it discoverable as a plugin.

```bash
# find hermes's project root - the venv lives at <that path>/venv
hermes --version        # look for the "Project:" or "Install directory:" line
                         # (the label has changed across Hermes versions)

# install into that venv's pip (not your shell's pip), from PyPI:
/path/from/above/venv/bin/pip install agent-install-monitor

# or from GitHub (replace 0.1.2 with the latest release):
/path/from/above/venv/bin/pip install https://github.com/swytchcodehq/agent-install-monitor/archive/refs/tags/v0.1.2.tar.gz
```

`which hermes` usually points at a wrapper script (from the standard
installer), not a symlink - `readlink -f` won't resolve it to the venv, so
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

Optional - put the CLI on your `$PATH`:

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


Data lives in `$HERMES_HOME/agent-monitor/monitor.db` (default
`~/.hermes/agent-monitor/monitor.db`). Nothing leaves your machine. On macOS
and Linux the folder and database can only be opened by your own account.
Tokens in a command (an install URL with credentials, `TOKEN=...`,
`--password ...`) are replaced with `***` before it's saved.

## Supported Installations

| Category   | Commands |
| ---------- | -------- |
| Package managers | `npm`, `pnpm`, `yarn`, `pip`, `uv`, `poetry`, `cargo`, `go`, `brew`, `apt`, `dnf`, `apk`, `gem`, `composer`, `dotnet`, `nuget`, `choco`, `winget`, `scoop` |
| Containers | `docker`/`podman pull`, `docker`/`podman run`, `docker compose up` |
| Git | `git clone`, `git submodule add`/`update` |
| Runtimes | `npx`, `uvx`, `cargo run`, `go run` |
| Services | `systemctl start`, `brew services start`, `service start` |
| Databases | `createdb`, `CREATE DATABASE` (creation only) |
| Installer downloads | `curl`/`wget` fetching `.sh`/`.exe`/`.pkg`/`.dmg`/`.deb`/`.rpm`/`.appimage`/`.msi` |

Detection is a best-effort command-string match, not a security boundary.

## Development

```bash
pip install -e ".[dev]"
pytest
```

### Releasing

Bump the version in your PR:

```bash
python3 scripts/bump_version.py patch   # or minor, major
```

This updates `pyproject.toml`, `__version__` and the installer's `VERSION`
together. When the PR is merged, `release-on-merge.yml` tags the new version
and starts `release.yml`, which runs the tests, publishes to PyPI and creates
the GitHub release with the built files. A merge that doesn't change the
version releases nothing. To retry a release, run `release.yml` by hand on
the tag.

