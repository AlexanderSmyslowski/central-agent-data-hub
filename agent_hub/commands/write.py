"""Write and sync command handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_hub.commands.common import (
    error,
    exception_error,
    json_default,
    parse_metadata,
    require_database_url,
)
from agent_hub.db import connect
from agent_hub.import_obsidian import import_markdown, sync_markdown
from agent_hub.importing.models import SyncResult
from agent_hub.memory import (
    HumanReviewRequired,
    answer_question,
    remember,
    remember_plan,
    update_decision,
)
from agent_hub.writeback_routing import card_for_item


def _write_result(project, agent, type_: str, row) -> dict:
    return {
        "project": {
            "id": project["id"],
            "slug": project["slug"],
            "name": project["name"],
        },
        "agent": {
            "id": agent["id"],
            "slug": agent["slug"],
            "name": agent["name"],
        },
        "type": type_,
        "object": row,
    }


def run_remember(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        metadata = parse_metadata(args.metadata)
    except ValueError as exc:
        return error(exc, 2)
    metadata.setdefault("created_by", "agent-hub remember")
    if args.source:
        metadata.setdefault("source", args.source)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                if getattr(args, "dry_run", False):
                    planned = remember_plan(cur, args, metadata)
                    if args.format == "json":
                        print(
                            json.dumps(
                                planned,
                                indent=2,
                                default=json_default,
                                ensure_ascii=False,
                            )
                        )
                    else:
                        print(
                            f"Planned {planned['type']} for project "
                            f"'{planned['project']['slug']}'."
                        )
                        print(f"status: {planned['status'] or 'default'}")
                        print(f"reason: {planned['reason']}")
                        print()
                        print(planned["card"])
                    return 0
                project, agent, object_type, row = remember(cur, args, metadata)
    except HumanReviewRequired as exc:
        result = {
            "tier": "ask",
            "reason": exc.reason,
            "card": card_for_item(exc.candidate),
        }
        if args.format == "json":
            print(json.dumps(result, indent=2, default=json_default, ensure_ascii=False))
        else:
            print("Human review required.")
            print(f"reason: {exc.reason}")
            print()
            print(result["card"])
        return 1
    except Exception as exc:
        return exception_error(exc)

    result = _write_result(project, agent, object_type, row)

    if args.format == "json":
        print(json.dumps(result, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(
        f"Remembered {object_type} for project '{project['slug']}': "
        f"{row['id']} ({row.get('status', 'unknown')})"
    )
    return 0


def run_answer_question(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        metadata = parse_metadata(args.metadata)
    except ValueError as exc:
        return error(exc, 2)
    metadata.setdefault("created_by", "agent-hub answer-question")
    if args.source:
        metadata.setdefault("source", args.source)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project, agent, row = answer_question(cur, args, metadata)
    except Exception as exc:
        return exception_error(exc)

    result = _write_result(project, agent, "open_question", row)

    if args.format == "json":
        print(json.dumps(result, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(
        f"Answered open_question for project '{project['slug']}': "
        f"{row['id']}"
    )
    return 0


def run_update_decision(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        metadata = parse_metadata(args.metadata)
    except ValueError as exc:
        return error(exc, 2)
    metadata.setdefault("created_by", "agent-hub update-decision")
    if args.source:
        metadata.setdefault("source", args.source)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project, agent, row = update_decision(cur, args, metadata)
    except Exception as exc:
        return exception_error(exc)

    result = _write_result(project, agent, "decision", row)

    if args.format == "json":
        print(json.dumps(result, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"Updated decision for project '{project['slug']}': {row['id']}")
    return 0


def run_import(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        with connect() as conn:
            result = import_markdown(
                Path(args.path),
                Path(args.allowlist),
                conn,
                dry_run=args.dry_run,
                on_duplicate=args.on_duplicate,
            )
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(json.dumps(result.__dict__, indent=2, default=json_default))
    else:
        action = "Planned" if args.dry_run else "Imported"
        rows = result.planned if args.dry_run else result.imported
        print(f"{action} {len(rows)} Markdown note(s).")
        for row in rows:
            suffix = f" -> {row['id']}" if "id" in row else ""
            row_action = row.get("action", "import")
            reason = f" ({row['reason']})" if row.get("reason") else ""
            print(
                f"- {row_action} {row['type']} {row['project']}: "
                f"{row['path']}{suffix}{reason}"
            )
        if result.errors:
            print()
            print(f"Errors: {len(result.errors)}")
            for import_error in result.errors:
                print(f"- {import_error['path']}: {import_error['error']}")

    return 1 if result.errors else 0


def print_sync_result(result: SyncResult) -> None:
    print(f"Planned {len(result.planned)} Markdown note(s).")
    for row in result.planned:
        label = row.get("type", "unknown")
        project = row.get("project", "unknown")
        reason = f" ({row['reason']})" if row.get("reason") else ""
        print(f"- {row['action']} {label} {project}: {row['path']}{reason}")
        if row.get("diffs"):
            fields = ", ".join(diff["field"] for diff in row["diffs"])
            print(f"  fields: {fields}")
            if row["action"] in {"ask", "conflict"}:
                print("  blocker: review required before sync --apply")
            for diff in row["diffs"]:
                print(
                    "  - "
                    f"{diff['field']} [{diff['owner']}]: "
                    f"db={diff['database_value']!r} "
                    f"markdown={diff['markdown_value']!r} "
                    f"last={diff['last_imported_value']!r}"
                )
        elif row.get("database_changed_fields"):
            fields = ", ".join(row["database_changed_fields"])
            print(f"  database changed fields: {fields}")
    if result.applied:
        print()
        print(f"Applied {len(result.applied)} change(s).")
        for row in result.applied:
            print(f"- {row['action']} {row['type']} {row['project']}: {row['id']}")
    if result.errors:
        print()
        print(f"Errors: {len(result.errors)}")
        for sync_error in result.errors:
            print(f"- {sync_error['path']}: {sync_error['error']}")


def run_sync(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    if args.watch:
        return error(
            "sync --watch is intentionally not implemented yet. "
            "Use --plan or --apply first.",
            2,
        )
    if args.plan == args.apply:
        return error("choose exactly one of --plan or --apply", 2)

    try:
        with connect() as conn:
            result = sync_markdown(
                Path(args.path),
                Path(args.allowlist),
                conn,
                apply=args.apply,
            )
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(json.dumps(result.__dict__, indent=2, default=json_default))
    else:
        print_sync_result(result)

    blockers = result.blocking_actions
    if result.errors or blockers:
        return 1
    return 0
