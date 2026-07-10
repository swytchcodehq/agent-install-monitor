"""``agent-monitor`` -- standalone CLI for Agent Install Monitor.

Plain argparse, four subcommands: sessions, session, history, export.
Reads the same SQLite database the Hermes plugin hook writes to.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional

from . import db

_CATEGORY_ORDER = [
    ("package_manager", "Packages"),
    ("container", "Containers"),
    ("git", "Repositories"),
    ("runtime", "Runtimes"),
    ("service", "Services"),
    ("database", "Databases"),
    ("download", "Downloads"),
]


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _format_duration(started_at: str, last_seen_at: str) -> str:
    start = _parse_ts(started_at)
    end = _parse_ts(last_seen_at)
    if start is None or end is None:
        return "?"
    seconds = max(0, int((end - start).total_seconds()))
    minutes, secs = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_item(index: int, event: db.Event) -> str:
    fail = "" if event.success else " (failed)"
    if event.category == "package_manager":
        name = event.name or "?"
        version = f":{event.version}" if event.version else ""
        return f"  {index}. {event.manager or '?':<8} {name}{version}{fail}"
    if event.category == "container":
        name = event.name or "?"
        version = f":{event.version}" if event.version else ""
        suffix = "" if event.action == "pull" else f" ({event.action})"
        return f"  {index}. {name}{version}{suffix}{fail}"
    if event.category == "git":
        return f"  {index}. {event.name or '?'}{fail}"
    if event.category == "runtime":
        name = event.name or "?"
        version = f"@{event.version}" if event.version else ""
        return f"  {index}. {event.manager or '?'} {name}{version}{fail}"
    if event.category == "service":
        return f"  {index}. {event.name or '?'} started{fail}"
    if event.category == "database":
        return f"  {index}. {event.name or '?'} created{fail}"
    if event.category == "download":
        return f"  {index}. {event.name or '?'}{fail}"
    return f"  {index}. {event.name or event.command}{fail}"


def _render_session(session_id: str) -> str:
    summary = db.get_session(session_id)
    if summary is None:
        return f"No activity recorded for session '{session_id}'."

    events = db.events_for_session(session_id)
    lines: List[str] = [f"Session {session_id} [{summary.agent}]"]

    by_category = {}
    for event in events:
        by_category.setdefault(event.category, []).append(event)

    for category, label in _CATEGORY_ORDER:
        items = by_category.get(category)
        if not items:
            continue
        lines.append(label)
        for i, event in enumerate(items, start=1):
            lines.append(_format_item(i, event))

    directories = sorted({e.cwd for e in events if e.cwd})
    if directories:
        lines.append("Directories")
        for i, d in enumerate(directories, start=1):
            lines.append(f"  {i}. {d}")

    duration = _format_duration(summary.started_at, summary.last_seen_at)
    lines.append(f"\nTime: {duration}   Commands: {summary.event_count}")
    return "\n".join(lines)


def cmd_sessions(_args: argparse.Namespace) -> int:
    sessions = db.list_sessions()
    if not sessions:
        print("No sessions recorded yet.")
        return 0
    print(f"{'SESSION':<24} {'AGENT':<10} {'STARTED':<26} {'DURATION':<10} {'EVENTS':>6}")
    for s in sessions:
        duration = _format_duration(s.started_at, s.last_seen_at)
        print(f"{s.session_id:<24} {s.agent:<10} {s.started_at:<26} {duration:<10} {s.event_count:>6}")
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    print(_render_session(args.session_id))
    return 0


def cmd_history(_args: argparse.Namespace) -> int:
    latest = db.latest_session_id()
    if latest is None:
        print("No activity recorded yet. Run `hermes plugins enable agent-monitor` and use Hermes normally.")
        return 0
    print(_render_session(latest))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    events = db.events_for_session(args.session) if args.session else db.all_events()
    rows = [asdict(e) for e in events]

    if args.format == "csv":
        if not rows:
            return 0
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        json.dump(rows, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-monitor", description="Agent Install Monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sessions", help="List recorded sessions").set_defaults(func=cmd_sessions)

    p_session = sub.add_parser("session", help="Show a single session's activity")
    p_session.add_argument("session_id")
    p_session.set_defaults(func=cmd_session)

    sub.add_parser("history", help="Show the most recent session's activity").set_defaults(func=cmd_history)

    p_export = sub.add_parser("export", help="Dump recorded events")
    p_export.add_argument("--session", default=None, help="Limit export to one session id")
    p_export.add_argument("--format", choices=["json", "csv"], default="json")
    p_export.set_defaults(func=cmd_export)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
