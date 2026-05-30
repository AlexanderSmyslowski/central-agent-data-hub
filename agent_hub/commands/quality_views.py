"""Quality, receipt, and agent-action command handlers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_hub.commands.common import (
    concise_error,
    fetch_project,
    json_default,
    parse_since,
)
from agent_hub.db import connect
from agent_hub.quality import fetch_project_quality
from agent_hub.receipts import fetch_receipt_rows
from agent_hub.retrieval import fetch_recent_agent_actions
from agent_hub.rendering import (
    agent_actions_markdown,
    quality_markdown,
    receipt_markdown,
)


def run_quality(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    print(
                        f"Error: project '{args.project}' not found",
                        file=sys.stderr,
                    )
                    return 2
                payload = fetch_project_quality(cur, project)
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(quality_markdown(payload))
    return 0


def run_receipt(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    export_dir_env = os.environ.get("OBSIDIAN_EXPORT_DIR")
    export_dir = Path(export_dir_env) if export_dir_env else None

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    print(
                        f"Error: project '{args.project}' not found",
                        file=sys.stderr,
                    )
                    return 2
                rows = fetch_receipt_rows(
                    cur,
                    project,
                    since,
                    args.memory_type,
                    args.limit,
                    export_dir,
                )
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    missing_export_count = sum(1 for row in rows if not row["exported"])
    result = "ok"
    exit_code = 0
    if args.require_results and not rows:
        result = "missing"
        exit_code = 1
    elif args.require_exported and (not export_dir or missing_export_count):
        result = "export-missing"
        exit_code = 1

    payload = {
        "project": project,
        "since": since,
        "type": args.memory_type,
        "export_dir": str(export_dir) if export_dir else None,
        "rows": rows,
        "counts": {
            "rows": len(rows),
            "missing_exports": missing_export_count,
        },
        "result": result,
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return exit_code

    print(receipt_markdown(payload))
    return exit_code


def run_actions(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since, default="7d")
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    print(
                        f"Error: project '{args.project}' not found",
                        file=sys.stderr,
                    )
                    return 2
                rows = fetch_recent_agent_actions(cur, project["id"], since, args.limit)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    payload = {"project": project, "since": since, "agent_actions": rows}
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(agent_actions_markdown(payload))
    return 0
