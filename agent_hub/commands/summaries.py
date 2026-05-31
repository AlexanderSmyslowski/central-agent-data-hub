"""Daily, handoff, review, and compiled-memory command handlers."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path

from agent_hub.commands.common import (
    error,
    exception_error,
    fetch_project,
    json_default,
    require_database_url,
    parse_since,
    project_not_found,
)
from agent_hub.db import connect
from agent_hub.quality import fetch_project_counts
from agent_hub.receipts import fetch_receipt_rows
from agent_hub.relations import fetch_project_relations
from agent_hub.retrieval import (
    fetch_activity_snapshot,
    fetch_brief_rows,
    write_daily_report,
)
from agent_hub.statuses import INACTIVE_OPEN_QUESTION_STATUSES
from agent_hub.rendering import (
    compiled_markdown,
    daily_markdown,
    handoff_markdown,
    limit_markdown_chars,
    markdown_list,
    relations_markdown,
)


def fetch_compiled_payload(
    cur,
    project: dict[str, object],
    limit: int,
    since: datetime | None = None,
    with_receipt_status: bool = False,
) -> dict[str, object]:
    project_id = project["id"]
    payload = {
        "project": project,
        "counts": fetch_project_counts(cur, project_id),
        "facts": fetch_brief_rows(
            cur,
            "facts",
            project_id,
            "id, statement, source, confidence",
            excluded_statuses=("archived", "deprecated"),
            limit=limit,
        ),
        "decisions": fetch_brief_rows(
            cur,
            "decisions",
            project_id,
            "id, decision, rationale, consequences",
            excluded_statuses=("archived", "rejected"),
            limit=limit,
        ),
        "risks": fetch_brief_rows(
            cur,
            "risks",
            project_id,
            "id, title, severity, impact, mitigation",
            excluded_statuses=("archived", "resolved"),
            limit=limit,
        ),
        "open_questions": fetch_brief_rows(
            cur,
            "open_questions",
            project_id,
            "id, question, answer",
            excluded_statuses=INACTIVE_OPEN_QUESTION_STATUSES,
            limit=limit,
        ),
        "reports": fetch_brief_rows(
            cur,
            "reports",
            project_id,
            "id, title, report_type, summary",
            excluded_statuses=("archived",),
            limit=max(3, min(limit, 5)),
        ),
        "relations": fetch_project_relations(cur, project_id, limit=limit),
    }
    if since:
        payload["since"] = since
        payload["recent_changes"] = fetch_activity_snapshot(cur, project, since, limit)
    if with_receipt_status:
        export_dir = get_export_dir_or_none()
        receipt_since = since or parse_since("24h")
        rows = fetch_receipt_rows(cur, project, receipt_since, "all", limit, export_dir)
        payload["receipt_status"] = {
            "since": receipt_since,
            "export_dir": str(export_dir) if export_dir else None,
            "checked": len(rows),
            "exported": sum(1 for row in rows if row["exported"]),
            "missing_exports": [
                {
                    "type": row["type"],
                    "id": row["id"],
                    "title": row["title"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
                if not row["exported"]
            ],
        }
    return payload


def get_export_dir_or_none() -> Path | None:
    export_dir_env = os.environ.get("OBSIDIAN_EXPORT_DIR")
    return Path(export_dir_env) if export_dir_env else None


def run_daily(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        since = parse_since(args.since)
    except ValueError as exc:
        return error(exc, 2)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                payload = fetch_activity_snapshot(cur, project, since, args.limit)
                report = None
                body = daily_markdown(payload)
                if args.write_report:
                    report = write_daily_report(cur, project, payload, body)
                    payload["written_report"] = report
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
    else:
        print(daily_markdown(payload))
        if args.write_report and payload.get("written_report"):
            print()
            print(f"Written report: {payload['written_report']['id']}")
    return 0


def run_handoff(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        since = parse_since(args.since, default="7d")
    except ValueError as exc:
        return error(exc, 2)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                payload = fetch_activity_snapshot(cur, project, since, args.limit)
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
    else:
        print(handoff_markdown(payload))
    return 0


def run_review(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                decisions = fetch_brief_rows(
                    cur,
                    "decisions",
                    project["id"],
                    "id, decision, rationale",
                    excluded_statuses=("archived", "rejected"),
                    limit=args.limit,
                )
                risks = fetch_brief_rows(
                    cur,
                    "risks",
                    project["id"],
                    "id, title, severity, impact, mitigation",
                    excluded_statuses=("archived", "resolved"),
                    limit=args.limit,
                )
                questions = fetch_brief_rows(
                    cur,
                    "open_questions",
                    project["id"],
                    "id, question, answer",
                    excluded_statuses=INACTIVE_OPEN_QUESTION_STATUSES,
                    limit=args.limit,
                )
                relations = fetch_project_relations(cur, project["id"], limit=args.limit)
    except Exception as exc:
        return exception_error(exc)

    payload = {
        "project": project,
        "decisions": decisions,
        "risks": risks,
        "open_questions": questions,
        "relations": relations,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"# Review: {project['name']}")
    print()
    print("## Decisions")
    print(markdown_list(decisions, "decision", ("rationale",)))
    print()
    print("## Risks")
    print(markdown_list(risks, "title", ("severity", "impact", "mitigation")))
    print()
    print("## Open Questions")
    print(markdown_list(questions, "question", ("answer",)))
    print()
    print("## Relations")
    print(relations_markdown(relations))
    return 0


def run_compile(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        since = parse_since(args.since) if args.since else None
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                payload = fetch_compiled_payload(
                    cur,
                    project,
                    args.limit,
                    since=since,
                    with_receipt_status=args.with_receipt_status,
                )
    except ValueError as exc:
        return error(exc, 2)
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(limit_markdown_chars(compiled_markdown(payload), args.max_chars))
    return 0
