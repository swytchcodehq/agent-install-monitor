"""Agent Install Monitor -- Hermes plugin entry point.

Records every install/integration action performed through the ``terminal``
tool during a Hermes session, so it can be reviewed later with the
``agent-monitor`` CLI. Visibility only -- no blocking, no rollback, no
uninstall.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from . import db
from .detector import detect

logger = logging.getLogger(__name__)

__version__ = "0.1.0"


def _extract_exit_code(result: Any) -> Optional[int]:
    try:
        payload = json.loads(result) if isinstance(result, str) else result
        if isinstance(payload, dict):
            code = payload.get("exit_code")
            if isinstance(code, int):
                return code
    except Exception:
        pass
    return None


def _on_post_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_: Any,
) -> None:
    if tool_name != "terminal" or not isinstance(args, dict):
        return

    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        return

    try:
        events = detect(command)
        if not events:
            return

        exit_code = _extract_exit_code(result)
        session_key = session_id or task_id or "default"
        cwd = args.get("workdir")

        for event in events:
            db.record_event(
                session_id=session_key,
                agent="hermes",
                category=event.category,
                manager=event.manager,
                action=event.action,
                name=event.name,
                version=event.version,
                command=event.command,
                cwd=cwd if isinstance(cwd, str) else None,
                exit_code=exit_code,
                success=(exit_code == 0),
                tool_call_id=tool_call_id or None,
            )
    except Exception:
        # Never let a tracking bug break the agent's actual tool call.
        logger.debug("agent-monitor: failed to record terminal command", exc_info=True)


def register(ctx) -> None:
    ctx.register_hook("post_tool_call", _on_post_tool_call)
