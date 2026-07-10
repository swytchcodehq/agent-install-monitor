#!/usr/bin/env python3
"""One-shot installer for agent-install-monitor.

Finds the Hermes Agent venv, installs agent-install-monitor into it (not your
shell's pip -- that's what makes Hermes able to discover it as a plugin),
enables the plugin, and offers to put the `agent-monitor` CLI on PATH.

Safe to re-run: every step is idempotent.

Usage:
    macOS/Linux/WSL:  curl -fsSL <raw-url>/install.py | python3
    Windows:          irm <raw-url>/install.py | python -
    Local:            python3 install.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

PACKAGE = "agent-install-monitor"
PLUGIN_NAME = "agent-monitor"


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# Step 1: find the Hermes venv
# ---------------------------------------------------------------------------

def find_hermes_venv() -> Path:
    hermes = shutil.which("hermes")
    if not hermes:
        _fail("`hermes` not found on PATH. Install Hermes Agent first: "
              "https://github.com/NousResearch/hermes-agent")

    try:
        result = subprocess.run(
            [hermes, "--version"], capture_output=True, text=True,
            check=True, timeout=15,
        )
    except Exception as exc:
        _fail(f"couldn't run `hermes --version`: {exc}")

    # The label has already changed across Hermes releases ("Project:" in
    # v0.17.x -> "Install directory:" from v0.18.x on) -- match either so
    # this doesn't go stale the next time it changes.
    match = re.search(r"(?:Project|Install directory):\s*(.+)", result.stdout)
    if not match:
        _fail(
            "couldn't find a project/install directory in `hermes --version` "
            "output:\n" + result.stdout
        )

    root = Path(match.group(1).strip())
    venv = root / "venv"
    if not venv.is_dir():
        _fail(f"expected a venv at {venv}, but it doesn't exist.")
    return venv


def venv_bin(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def venv_python(venv: Path) -> Path:
    return venv_bin(venv) / ("python.exe" if os.name == "nt" else "python3")


# ---------------------------------------------------------------------------
# Step 2: install + enable
# ---------------------------------------------------------------------------

def pip_install(venv: Path) -> None:
    _run([str(venv_python(venv)), "-m", "pip", "install", "--quiet", "--upgrade", PACKAGE])


def enable_plugin() -> None:
    hermes = shutil.which("hermes")
    result = subprocess.run(
        [hermes, "plugins", "enable", PLUGIN_NAME, "--no-allow-tool-override"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(
            f"  ! `hermes plugins enable {PLUGIN_NAME}` failed -- your Hermes "
            "version may be too old to auto-discover pip-installed plugins.\n"
            f"    Add it by hand to ~/.hermes/config.yaml instead:\n"
            f"      plugins:\n        enabled:\n          - {PLUGIN_NAME}\n"
            f"    ({result.stderr.strip() or result.stdout.strip()})"
        )
        return
    print(f"  OK: {PLUGIN_NAME} enabled")


# ---------------------------------------------------------------------------
# Step 3: offer to put the CLI on PATH
# ---------------------------------------------------------------------------

def _prompt_yes(question: str) -> bool:
    """Ask a yes/no question, defaulting to yes on non-interactive stdin.

    This script is designed to be run via `curl | python3` / `irm | python -`,
    which means Python's own stdin is the pipe carrying the script source --
    by the time this runs, there's nothing left to read from it interactively.
    ``sys.stdin.isatty()`` tells us which situation we're in: a real terminal
    gets a real prompt; a pipe gets the sensible default applied automatically
    (matching how installers like rustup/nvm behave), with the action clearly
    printed so it's never a silent surprise.
    """
    if not sys.stdin.isatty():
        return True
    answer = input(f"{question} [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def _guess_shell_rc() -> Optional[Path]:
    shell = os.environ.get("SHELL", "")
    home = Path.home()
    if "zsh" in shell:
        return home / ".zshrc"
    if "bash" in shell:
        bashrc = home / ".bashrc"
        return bashrc if bashrc.exists() else home / ".bash_profile"
    return None


def _offer_path_unix(bin_dir: Path) -> None:
    line = f'export PATH="{bin_dir}:$PATH"'
    rc = _guess_shell_rc()

    # `shutil.which` alone isn't enough here: it reflects the *current*
    # shell's PATH, which can already resolve the CLI from a one-off
    # `export` earlier in this session without that surviving a new
    # terminal. Check the rc file's actual contents instead -- that's what
    # determines whether this persists.
    if rc is not None and rc.exists() and str(bin_dir) in rc.read_text():
        print(f"OK: `{PLUGIN_NAME}` is already set up on PATH in {rc}.")
        return

    print(f"\n`{PLUGIN_NAME}` isn't set up on your PATH permanently yet.")
    if rc is None:
        print(f"  Add this line to your shell's rc file:\n  {line}")
        return
    if not _prompt_yes(f"  Add it to {rc}?"):
        print(f"  Skipped. Add manually:\n  {line}")
        return
    with rc.open("a") as f:
        f.write(f"\n# added by the agent-install-monitor installer\n{line}\n")
    print(f"  OK: appended to {rc} -- restart your shell, or run: source {rc}")


def _windows_user_path_contains(bin_dir: Path) -> bool:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Environment]::GetEnvironmentVariable('Path', 'User')"],
            capture_output=True, text=True, check=True,
        )
    except Exception:
        return False
    return str(bin_dir).lower() in result.stdout.lower()


def _offer_path_windows(bin_dir: Path) -> None:
    # Same reasoning as _offer_path_unix: check the persisted User PATH in
    # the registry, not just whether the CLI resolves in this process.
    if _windows_user_path_contains(bin_dir):
        print(f"OK: `{PLUGIN_NAME}` is already set up on your User PATH.")
        return

    print(f"\n`{PLUGIN_NAME}` isn't set up on your PATH permanently yet.")
    if not _prompt_yes("  Add it to your user PATH permanently?"):
        print(
            "  Skipped. Add manually via System Properties > Environment "
            f"Variables:\n  {bin_dir}"
        )
        return
    # [Environment]::SetEnvironmentVariable writes straight to the registry
    # via .NET, unlike `setx` -- avoids setx's well-known silent truncation
    # of PATH values over 1024 characters.
    ps_cmd = (
        "$old = [Environment]::GetEnvironmentVariable('Path', 'User'); "
        f"$new = $old + ';{bin_dir}'; "
        "[Environment]::SetEnvironmentVariable('Path', $new, 'User')"
    )
    try:
        _run(["powershell", "-NoProfile", "-Command", ps_cmd])
        print("  OK: added to your User PATH -- restart your terminal for it to take effect.")
    except Exception as exc:
        print(f"  Couldn't update PATH automatically ({exc}). Add manually:\n  {bin_dir}")


def offer_path_setup(venv: Path) -> None:
    bin_dir = venv_bin(venv)
    cli = bin_dir / (f"{PLUGIN_NAME}.exe" if os.name == "nt" else PLUGIN_NAME)
    if not cli.exists():
        return  # console script didn't get installed for some reason; nothing to add
    if os.name == "nt":
        _offer_path_windows(bin_dir)
    else:
        _offer_path_unix(bin_dir)


# ---------------------------------------------------------------------------

def main() -> int:
    print("Agent Install Monitor - installer")
    print("-" * 36)

    print("-> Locating Hermes Agent...")
    venv = find_hermes_venv()
    print(f"  OK: found venv: {venv}")

    print(f"-> Installing {PACKAGE} into that venv...")
    pip_install(venv)
    print("  OK: installed")

    print("-> Enabling plugin...")
    enable_plugin()

    offer_path_setup(venv)

    print(f"\nDone. Use Hermes normally, then run:\n  {PLUGIN_NAME} history")
    return 0


if __name__ == "__main__":
    sys.exit(main())
