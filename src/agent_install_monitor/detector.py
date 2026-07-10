"""Detects package-manager installs, container pulls, git clones, runtime
invocations, service starts, database creations, and installer downloads in
a shell command string.

A single ordered list of category matchers is tried per command segment;
the first match wins. No detector framework, no plugin-of-detectors
abstraction -- just a flat table and a handful of plain functions.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Callable, List, NamedTuple, Optional, Tuple

_SEGMENT_SPLIT = {"&&", ";", "||"}

_URL_RE = re.compile(r"^(https?|ftp)://", re.IGNORECASE)
_INSTALLER_EXT_RE = re.compile(r"\.(sh|exe|pkg|dmg|deb|rpm|appimage|msi)(\?|$)", re.IGNORECASE)
_INSTALLER_NAME_RE = re.compile(r"install", re.IGNORECASE)
_CREATE_DB_RE = re.compile(r"create\s+database", re.IGNORECASE)
_CREATE_DB_NAME_RE = re.compile(
    r"create\s+database\s+(?:if\s+not\s+exists\s+)?[`\"]?([\w-]+)", re.IGNORECASE
)


class DetectedEvent(NamedTuple):
    category: str
    manager: str
    action: str
    name: Optional[str]
    version: Optional[str]
    command: str


# ---------------------------------------------------------------------------
# Tokenizing / segmenting
# ---------------------------------------------------------------------------

def _split_segments(command: str) -> List[List[str]]:
    """Tokenize *command* and split into segments on &&, ;, ||.

    Pipes ('|') are intentionally NOT a split point -- ``curl ... | bash``
    is one logical install action, not two.
    """
    try:
        # POSIX mode treats '\' as an escape character, which mangles
        # unquoted Windows paths (`C:\Users\foo` -> `C:Usersfoo`). Windows
        # commands don't rely on backslash-escaping the way POSIX shells do,
        # so fall back to non-POSIX splitting there -- quotes end up left in
        # the tokens, but that's an acceptable trade-off for a visibility
        # tool (see _collect_targets).
        tokens = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        return []

    segments: List[List[str]] = []
    current: List[str] = []
    for tok in tokens:
        if tok in _SEGMENT_SPLIT:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)
    return segments


def _match_prefix(tokens: List[str], prefix: Tuple[str, ...]) -> bool:
    return len(tokens) > len(prefix) and tuple(tokens[: len(prefix)]) == prefix


def _collect_targets(tokens: List[str], start: int) -> List[str]:
    """Non-flag tokens after *start*, stopping at a literal pipe.

    Heuristic: flag *values* (e.g. ``--index-url https://x``) are not
    distinguished from positional targets, so they can occasionally be
    mis-collected. Acceptable for a visibility tool -- not a policy engine.
    """
    targets = []
    for tok in tokens[start:]:
        if tok == "|":
            break
        if tok.startswith("-"):
            continue
        targets.append(tok)
    return targets


def _split_pkg_version(token: str, style: Optional[str]) -> Tuple[str, Optional[str]]:
    if style == "at":
        # Scoped npm packages start with '@' (e.g. @scope/pkg@1.0.0) --
        # search from index 1 so the leading '@' is never mistaken for a
        # version separator.
        idx = token.find("@", 1)
        if idx != -1:
            return token[:idx], token[idx + 1 :]
        return token, None
    if style == "pep":
        for sep in ("==", ">=", "<=", "~=", "!="):
            if sep in token:
                name, _, version = token.partition(sep)
                return name, version
        return token, None
    if style == "eq":
        if "=" in token:
            name, _, version = token.partition("=")
            return name, version
        return token, None
    if style == "colon":
        if ":" in token:
            name, _, version = token.partition(":")
            return name, version
        return token, None
    return token, None


# ---------------------------------------------------------------------------
# Package managers
# ---------------------------------------------------------------------------

# (manager, prefix tokens, version style)
_PKG_MGRS: List[Tuple[str, Tuple[str, ...], Optional[str]]] = [
    ("npm", ("npm", "install"), "at"),
    ("npm", ("npm", "i"), "at"),
    ("pnpm", ("pnpm", "add"), "at"),
    ("yarn", ("yarn", "add"), "at"),
    ("pip", ("pip", "install"), "pep"),
    ("pip", ("pip3", "install"), "pep"),
    ("pip", ("uv", "pip", "install"), "pep"),
    ("uv", ("uv", "add"), "pep"),
    ("poetry", ("poetry", "add"), "pep"),
    ("cargo", ("cargo", "install"), "at"),
    ("cargo", ("cargo", "add"), "at"),
    ("go", ("go", "install"), "at"),
    ("brew", ("brew", "install"), "at"),
    ("apt", ("apt", "install"), "eq"),
    ("apt", ("apt-get", "install"), "eq"),
    ("dnf", ("dnf", "install"), None),
    ("apk", ("apk", "add"), "eq"),
    ("gem", ("gem", "install"), None),
    ("composer", ("composer", "require"), "colon"),
    ("dotnet", ("dotnet", "add", "package"), None),
    ("nuget", ("nuget", "install"), None),
    ("choco", ("choco", "install"), None),
    ("winget", ("winget", "install"), None),
    ("scoop", ("scoop", "install"), "at"),
]


def _detect_package_manager(tokens: List[str], seg_command: str) -> Optional[List[DetectedEvent]]:
    for manager, prefix, version_style in _PKG_MGRS:
        if _match_prefix(tokens, prefix):
            targets = _collect_targets(tokens, len(prefix))
            events = []
            for tok in targets:
                name, version = _split_pkg_version(tok, version_style)
                events.append(DetectedEvent("package_manager", manager, "install", name, version, seg_command))
            return events
    return None


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

def _container_event(image: str, seg_command: str, manager: str = "docker") -> DetectedEvent:
    name, version = _split_pkg_version(image, "colon")
    return DetectedEvent("container", manager, "pull", name, version, seg_command)


def _detect_container(tokens: List[str], seg_command: str) -> Optional[List[DetectedEvent]]:
    if _match_prefix(tokens, ("docker", "pull")):
        return [_container_event(t, seg_command) for t in _collect_targets(tokens, 2)]
    if _match_prefix(tokens, ("podman", "pull")):
        return [_container_event(t, seg_command, "podman") for t in _collect_targets(tokens, 2)]
    if _match_prefix(tokens, ("docker", "run")):
        # `docker run [OPTIONS] IMAGE [COMMAND] [ARG...]` -- only the first
        # non-flag token is the image; the rest belongs to the containerized
        # command, not to the install action.
        targets = _collect_targets(tokens, 2)
        if targets:
            return [DetectedEvent("container", "docker", "run", *_split_pkg_version(targets[0], "colon"), seg_command)]
        return []
    if len(tokens) > 2 and tokens[0] == "docker" and tokens[1] == "compose" and tokens[2] == "up":
        return [DetectedEvent("container", "docker-compose", "up", None, None, seg_command)]
    return None


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def _strip_git_suffix(url: str) -> str:
    return url[:-4] if url.endswith(".git") else url


def _detect_git(tokens: List[str], seg_command: str) -> Optional[List[DetectedEvent]]:
    if _match_prefix(tokens, ("git", "clone")):
        targets = _collect_targets(tokens, 2)
        if not targets:
            return []
        return [DetectedEvent("git", "git", "clone", _strip_git_suffix(targets[0]), None, seg_command)]
    if _match_prefix(tokens, ("git", "submodule", "add")):
        # `git submodule add [options] <repository> [<path>]` -- the
        # repository URL is the first positional target, not the last.
        targets = _collect_targets(tokens, 3)
        if not targets:
            return []
        return [DetectedEvent("git", "git", "submodule_add", _strip_git_suffix(targets[0]), None, seg_command)]
    if _match_prefix(tokens, ("git", "submodule", "update")):
        return [DetectedEvent("git", "git", "submodule_update", None, None, seg_command)]
    return None


# ---------------------------------------------------------------------------
# Language runtimes
# ---------------------------------------------------------------------------

def _detect_runtime(tokens: List[str], seg_command: str) -> Optional[List[DetectedEvent]]:
    if tokens and tokens[0] in ("npx", "uvx"):
        targets = _collect_targets(tokens, 1)
        if not targets:
            return []
        name, version = _split_pkg_version(targets[0], "at")
        return [DetectedEvent("runtime", tokens[0], "run", name, version, seg_command)]
    if _match_prefix(tokens, ("cargo", "run")):
        return [DetectedEvent("runtime", "cargo", "run", None, None, seg_command)]
    if len(tokens) >= 2 and tokens[0] == "go" and tokens[1] == "run":
        targets = _collect_targets(tokens, 2)
        name = targets[0] if targets else None
        return [DetectedEvent("runtime", "go", "run", name, None, seg_command)]
    return None


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def _detect_service(tokens: List[str], seg_command: str) -> Optional[List[DetectedEvent]]:
    if _match_prefix(tokens, ("systemctl", "start")):
        targets = _collect_targets(tokens, 2)
        name = targets[0] if targets else None
        return [DetectedEvent("service", "systemctl", "start", name, None, seg_command)]
    if _match_prefix(tokens, ("brew", "services", "start")):
        targets = _collect_targets(tokens, 3)
        name = targets[0] if targets else None
        return [DetectedEvent("service", "brew-services", "start", name, None, seg_command)]
    if len(tokens) >= 3 and tokens[0] == "service" and tokens[2] == "start":
        return [DetectedEvent("service", "service", "start", tokens[1], None, seg_command)]
    return None


# ---------------------------------------------------------------------------
# Databases -- only creation, per spec
# ---------------------------------------------------------------------------

def _detect_database(tokens: List[str], seg_command: str) -> Optional[List[DetectedEvent]]:
    if tokens and tokens[0] == "createdb":
        targets = _collect_targets(tokens, 1)
        name = targets[0] if targets else None
        return [DetectedEvent("database", "createdb", "create", name, None, seg_command)]
    if tokens and tokens[0] in ("mysql", "psql") and _CREATE_DB_RE.search(seg_command):
        match = _CREATE_DB_NAME_RE.search(seg_command)
        name = match.group(1) if match else None
        return [DetectedEvent("database", tokens[0], "create", name, None, seg_command)]
    return None


# ---------------------------------------------------------------------------
# Installer downloads -- only curl/wget that look like they fetch an installer
# ---------------------------------------------------------------------------

def _looks_like_installer(url: str) -> bool:
    return bool(_INSTALLER_EXT_RE.search(url) or _INSTALLER_NAME_RE.search(url))


def _detect_download(tokens: List[str], seg_command: str) -> Optional[List[DetectedEvent]]:
    if not tokens or tokens[0] not in ("curl", "wget"):
        return None
    for tok in _collect_targets(tokens, 1):
        if _URL_RE.match(tok) and _looks_like_installer(tok):
            return [DetectedEvent("download", tokens[0], "download", tok, None, seg_command)]
    return None


_CATEGORY_MATCHERS: List[Callable[[List[str], str], Optional[List[DetectedEvent]]]] = [
    _detect_package_manager,
    _detect_container,
    _detect_git,
    _detect_runtime,
    _detect_service,
    _detect_database,
    _detect_download,
]


def detect(command: str) -> List[DetectedEvent]:
    """Return every install/integration event found in *command*."""
    if not command or not isinstance(command, str):
        return []

    events: List[DetectedEvent] = []
    for tokens in _split_segments(command):
        seg_command = " ".join(tokens)
        for matcher in _CATEGORY_MATCHERS:
            result = matcher(tokens, seg_command)
            if result is not None:
                events.extend(result)
                break
    return events
