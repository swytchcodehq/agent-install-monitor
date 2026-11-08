"""Remove secrets from a command before it's saved to the history.

Agents sometimes put a token straight into a command: an install URL with
credentials, a TOKEN=... prefix, or a --password flag. The history only needs
to know what was installed, so those values are replaced with ***.
"""

from __future__ import annotations

import re

# https://user:token@host/... -> https://***@host/...
# Up to the last @ before the path, so a password containing @ is masked whole.
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s]*@")

# GITHUB_TOKEN=abc npm install ..., export NPM_AUTH=abc
_SECRET_NAME = r"[A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|PASS|AUTH|API_?KEY|ACCESS_?KEY|CREDENTIALS?)[A-Za-z0-9_]*"
_SECRET_ASSIGN = re.compile(r"(?i)\b(" + _SECRET_NAME + r")=(\"[^\"]*\"|'[^']*'|\S+)")

# --token abc, --password=abc, --api-key abc, -p abc is too ambiguous to touch
_SECRET_FLAG = re.compile(
    r"(?i)(--(?:[a-z0-9\-]*-)?(?:token|secret|password|passwd|api-key|apikey|auth|access-key)(?:[ =]))(\"[^\"]*\"|'[^']*'|\S+)"
)


def redact(text):
    """Return *text* with credentials replaced by ***. ``None`` stays ``None``."""
    if not text:
        return text
    text = _URL_CREDENTIALS.sub(r"\1***@", text)
    text = _SECRET_ASSIGN.sub(r"\1=***", text)
    text = _SECRET_FLAG.sub(r"\1***", text)
    return text
