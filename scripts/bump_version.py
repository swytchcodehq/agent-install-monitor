#!/usr/bin/env python3
"""Bump the `version` field in pyproject.toml.

Usage: python3 scripts/bump_version.py {major,minor,patch}

Prints the new version to stdout. If run inside GitHub Actions ($GITHUB_OUTPUT
is set), also writes `version=X.Y.Z` there so a workflow step can reference it
as `steps.<id>.outputs.version`.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
_VERSION_RE = re.compile(r'(?m)^version = "(\d+)\.(\d+)\.(\d+)"$')


def bump(part: str, pyproject_path: Path = _PYPROJECT) -> str:
    text = pyproject_path.read_text()
    match = _VERSION_RE.search(text)
    if not match:
        raise SystemExit(f'no `version = "X.Y.Z"` line found in {pyproject_path}')

    major, minor, patch = (int(g) for g in match.groups())
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    elif part == "patch":
        patch += 1
    else:
        raise SystemExit(f"unknown version part {part!r} (expected major, minor, or patch)")

    new_version = f"{major}.{minor}.{patch}"
    new_text = text[: match.start()] + f'version = "{new_version}"' + text[match.end() :]
    pyproject_path.write_text(new_text)
    return new_version


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: bump_version.py {major,minor,patch}", file=sys.stderr)
        return 2

    new_version = bump(sys.argv[1])
    print(new_version)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"version={new_version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
