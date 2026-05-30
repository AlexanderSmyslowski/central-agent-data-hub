"""Read-only project memory command handlers."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import sys
from pathlib import Path

from agent_hub.commands.common import (
    concise_error,
    fetch_project,
    json_default,
    parse_since,
    print_relations,
    print_rows,
)
from agent_hub.db import connect
from agent_hub.quality import fetch_project_counts, fetch_project_quality
from agent_hub.receipts import fetch_receipt_rows
from agent_hub.relations import fetch_project_relations
from agent_hub.retrieval import (
    fetch_activity_snapshot,
    fetch_brief_rows,
    fetch_recent_agent_actions,
    search_project_memory,
    write_daily_report,
)
from agent_hub.rendering import (
    agent_actions_markdown,
    compiled_markdown,
    daily_markdown,
    handoff_markdown,
    limit_markdown_chars,
    markdown_list,
    quality_markdown,
    receipt_markdown,
    relations_markdown,
    recommended_steps_markdown,
    search_results_markdown,
    sync_events_markdown,
    truncate,
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
            excluded_statuses=("archived", "closed"),
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


def run_brief(args: argparse.Namespace) -> int:
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

                cur.execute(
                    """
                    SELECT
                      (SELECT count(*) FROM documents WHERE project_id = %(project_id)s) AS documents,
                      (SELECT count(*) FROM facts WHERE project_id = %(project_id)s) AS facts,
                      (SELECT count(*) FROM decisions WHERE project_id = %(project_id)s) AS decisions,
                      (SELECT count(*) FROM open_questions WHERE project_id = %(project_id)s) AS open_questions,
                      (SELECT count(*) FROM risks WHERE project_id = %(project_id)s) AS risks,
                      (SELECT count(*) FROM reports WHERE project_id = %(project_id)s) AS reports,
                      (SELECT count(*) FROM agent_actions aa
                        JOIN agents a ON a.id = aa.agent_id
                        WHERE a.project_id = %(project_id)s) AS agent_actions
                    """,
                    {"project_id": project["id"]},
                )
                counts = cur.fetchone()

                decisions = fetch_brief_rows(
                    cur,
                    "decisions",
                    project["id"],
                    "id, decision, rationale",
                    limit=args.limit,
                )
                facts = fetch_brief_rows(
                    cur,
                    "facts",
                    project["id"],
                    "id, statement, source, confidence",
                    excluded_statuses=("archived", "deprecated"),
                    limit=args.limit,
                )
                questions = fetch_brief_rows(
                    cur,
                    "open_questions",
                    project["id"],
                    "id, question, answer",
                    excluded_statuses=("archived", "closed"),
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
                reports = fetch_brief_rows(
                    cur,
                    "reports",
                    project["id"],
                    "id, title, report_type, summary",
                    limit=args.limit,
                )
                relations = []
                if args.with_relations:
                    relations = fetch_project_relations(
                        cur,
                        project["id"],
                        limit=args.limit,
                    )

        brief = {
            "project": project,
            "counts": counts,
            "decisions": decisions,
            "facts": facts,
            "open_questions": questions,
            "risks": risks,
            "reports": reports,
            "relations": relations,
        }
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(brief, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"# Agent Brief: {project['name']}")
    print()
    print(f"- slug: {project['slug']}")
    print(f"- status: {project['status']}")
    if project.get("description"):
        print(f"- description: {project['description']}")
    print()
    print("## Counts")
    for key, value in counts.items():
        print(f"- {key}: {value}")
    print()
    print_rows("Decisions", decisions, "decision")
    print_rows("Facts", facts, "statement")
    print_rows("Open Questions", questions, "question")
    print_rows("Risks", risks, "title")
    print_rows("Reports", reports, "title")
    if args.with_relations:
        print("## Relations")
        print_relations(relations)
        print()
    return 0


def run_daily(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
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
                payload = fetch_activity_snapshot(cur, project, since, args.limit)
                report = None
                body = daily_markdown(payload)
                if args.write_report:
                    report = write_daily_report(cur, project, payload, body)
                    payload["written_report"] = report
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
    else:
        print(daily_markdown(payload))
        if args.write_report and payload.get("written_report"):
            print()
            print(f"Written report: {payload['written_report']['id']}")
    return 0


def run_handoff(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since, default="7d")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
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
                payload = fetch_activity_snapshot(cur, project, since, args.limit)
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
    else:
        print(handoff_markdown(payload))
    return 0


def run_review(args: argparse.Namespace) -> int:
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
                    excluded_statuses=("archived", "closed"),
                    limit=args.limit,
                )
                relations = fetch_project_relations(cur, project["id"], limit=args.limit)
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

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


def run_search(args: argparse.Namespace) -> int:
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
                results = search_project_memory(
                    cur,
                    project["id"],
                    args.query,
                    args.memory_type,
                    args.limit,
                )
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    payload = {"project": project, "query": args.query, "results": results}
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"Search results for {project['slug']}: {args.query}")
    print(search_results_markdown(results))
    return 0


def run_context(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since, default="30d")
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    print(
                        f"Error: project '{args.project}' not found",
                        file=sys.stderr,
                    )
                    return 2
                snapshot = fetch_activity_snapshot(cur, project, since, args.limit)
                results = search_project_memory(
                    cur,
                    project["id"],
                    args.query,
                    "all",
                    args.limit,
                )
                relations = fetch_project_relations(cur, project["id"], limit=args.limit)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    payload = {
        "project": project,
        "query": args.query,
        "since": since,
        "brief": snapshot,
        "search_results": results,
        "relations": relations,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"# Context Pack: {project['name']}")
    print()
    print(f"- project: {project['slug']}")
    print(f"- query: {args.query}")
    print(f"- since: {since.isoformat()}")
    print()
    print("## Search Results")
    print(search_results_markdown(results))
    print()
    print("## Recent Activity")
    print("### Facts")
    print(markdown_list(snapshot["facts"], "statement", ("source", "confidence")))
    print()
    print("### Decisions")
    print(markdown_list(snapshot["decisions"], "decision", ("rationale",)))
    print()
    print("### Risks")
    print(markdown_list(snapshot["risks"], "title", ("severity", "impact", "mitigation")))
    print()
    print("### Open Questions")
    print(markdown_list(snapshot["open_questions"], "question", ("answer",)))
    print()
    print("### Relations")
    print(relations_markdown(relations))
    return 0


def run_compile(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since) if args.since else None
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    print(
                        f"Error: project '{args.project}' not found",
                        file=sys.stderr,
                    )
                    return 2
                payload = fetch_compiled_payload(
                    cur,
                    project,
                    args.limit,
                    since=since,
                    with_receipt_status=args.with_receipt_status,
                )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(limit_markdown_chars(compiled_markdown(payload), args.max_chars))
    return 0


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
