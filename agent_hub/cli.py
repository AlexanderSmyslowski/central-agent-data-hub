"""Command line interface for Agent Data Hub."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
import json
import os
import re
import sys
from pathlib import Path

from agent_hub.db import connect
from agent_hub.export_obsidian import EXPORTS, export_all, filename_for, normalize_row
from agent_hub.import_obsidian import import_markdown, sync_markdown
from agent_hub.memory import REMEMBER_TYPES, remember
from agent_hub.migrations import (
    BASELINE_MIGRATION_ID,
    MIGRATIONS_DIR,
    TRACKING_MIGRATION_ID,
    apply_migrations,
    base_schema_exists,
    describe_migrations,
    execute_migration_file,
    migration_checksum,
    migration_file_by_id,
    migration_files,
    migration_parts,
    migration_records,
    print_migration_report,
    record_migration,
    schema_migrations_exists,
    table_exists,
)
from agent_hub.relations import (
    RELATION_TARGETS,
    RELATION_TYPES,
    fetch_project_relations,
    fetch_relation_object,
    validate_relation_object,
)
from agent_hub.quality import (
    fetch_latest_sync_event,
    fetch_low_confidence_facts,
    fetch_memory_quality_warnings,
    fetch_open_questions,
    fetch_project_counts,
    fetch_project_quality,
    fetch_table_counts,
    find_broken_relation_side,
    find_missing_project_references,
    find_unknown_relation_types,
)
from agent_hub.rendering import (
    actions_markdown,
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

RECEIPT_TYPES = (
    "all",
    "fact",
    "decision",
    "risk",
    "open_question",
    "report",
    "agent_action",
)

EXPORT_SPECS_BY_TYPE = {
    "project": next(spec for spec in EXPORTS if spec["table"] == "projects"),
    "document": next(spec for spec in EXPORTS if spec["table"] == "documents"),
    "report": next(spec for spec in EXPORTS if spec["table"] == "reports"),
    "decision": next(spec for spec in EXPORTS if spec["table"] == "decisions"),
    "fact": next(spec for spec in EXPORTS if spec["table"] == "facts"),
    "open_question": next(spec for spec in EXPORTS if spec["table"] == "open_questions"),
    "risk": next(spec for spec in EXPORTS if spec["table"] == "risks"),
    "agent_action": next(spec for spec in EXPORTS if spec["table"] == "agent_actions"),
}


def concise_error(exc: Exception) -> str:
    return str(exc).splitlines()[0]


def json_default(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def confidence_value(value: str) -> float:
    try:
        confidence = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "confidence must be a number from 0 to 1"
        ) from exc
    if confidence < 0 or confidence > 1:
        raise argparse.ArgumentTypeError("confidence must be between 0 and 1")
    return confidence


def parse_metadata(values: list[str] | None) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(
                f"Metadata entry must use key=value format: {value}"
            )
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("Metadata key must not be empty")
        try:
            metadata[key] = json.loads(raw)
        except json.JSONDecodeError:
            metadata[key] = raw
    return metadata


def fetch_project(cur, slug: str) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT id, name, slug, description, status, metadata, created_at, updated_at
        FROM projects
        WHERE slug = %s
        """,
        (slug,),
    )
    return cur.fetchone()


def print_relations(rows: list[dict[str, object]]) -> None:
    if not rows:
        print("- none")
        return
    for row in rows:
        source = (
            f"{row['source_type']}:{row['source_id']} "
            f"({truncate(row.get('source_summary') or '', 72)})"
        )
        target = (
            f"{row['target_type']}:{row['target_id']} "
            f"({truncate(row.get('target_summary') or '', 72)})"
        )
        print(f"- {source} --{row['relation_type']}--> {target}")
        if row.get("metadata"):
            print(
                "  metadata: "
                + json.dumps(row["metadata"], default=json_default, ensure_ascii=False)
            )


def print_rows(title: str, rows: list[dict[str, object]], text_key: str) -> None:
    print(f"## {title}")
    if not rows:
        print("- none")
        print()
        return
    for row in rows:
        status = row.get("status", "unknown")
        updated_at = row.get("updated_at")
        text = truncate(row[text_key], 180)
        print(f"- [{status}] {text}")
        if updated_at:
            print(f"  updated_at: {updated_at}")
    print()


def run_export(_args: argparse.Namespace) -> int:
    missing = [
        name
        for name in ("DATABASE_URL", "OBSIDIAN_EXPORT_DIR")
        if not os.environ.get(name)
    ]
    if missing:
        print(
            "Error: missing required environment variable(s): "
            + ", ".join(missing),
            file=sys.stderr,
        )
        print(
            "Set DATABASE_URL to your PostgreSQL connection string and "
            "OBSIDIAN_EXPORT_DIR to the target Obsidian export directory.",
            file=sys.stderr,
        )
        return 2

    try:
        written = export_all()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Export complete: wrote {len(written)} Markdown files.")
    for path in written:
        print(path)
    return 0


def run_migrate(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        with connect() as conn:
            if args.apply:
                applied, errors = apply_migrations(conn)
                for item in applied:
                    print(f"Applied migration: {item}")
                if errors:
                    for error in errors:
                        print(f"Error: {error}", file=sys.stderr)
                    return 1
                if not applied:
                    print("No migrations to apply.")
                print()

            report = describe_migrations(conn)
            print_migration_report(report)
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    return 0


def run_status(_args: argparse.Namespace) -> int:
    healthy = True
    database_url = os.environ.get("DATABASE_URL")
    export_dir = os.environ.get("OBSIDIAN_EXPORT_DIR")

    print("Central Agent Data Hub status")
    print()

    if not database_url:
        print("Database: missing (DATABASE_URL is not set)")
        healthy = False
    else:
        try:
            with connect() as conn:
                print("Database: ok")
                print()
                print("Table counts:")
                with conn.cursor() as cur:
                    for table, count in fetch_table_counts(cur).items():
                        print(f"  {table}: {count}")
                print()
                migration_report = describe_migrations(conn)
                print_migration_report(migration_report)
                if migration_report["failed_count"]:
                    healthy = False
        except Exception as exc:
            print(f"Database: error ({concise_error(exc)})")
            healthy = False

    if not export_dir:
        print("Obsidian export dir: missing (OBSIDIAN_EXPORT_DIR is not set)")
        healthy = False
    else:
        path = Path(export_dir)
        if path.is_dir():
            print(f"Obsidian export dir: ok ({path})")
        else:
            print(f"Obsidian export dir: not found ({path})")
            healthy = False

    return 0 if healthy else 1


def run_projects(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                params: tuple[object, ...] = ()
                type_filter = ""
                if args.project_type:
                    type_filter = "AND metadata->>'project_type' = %s"
                    params = (args.project_type,)
                cur.execute(
                    f"""
                    SELECT slug, name, status, description, metadata
                    FROM projects
                    WHERE status = 'active'
                    {type_filter}
                    ORDER BY slug
                    """,
                    params,
                )
                projects = list(cur.fetchall())
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(projects, indent=2, default=json_default, ensure_ascii=False))
        return 0

    if not projects:
        print("No active projects found.")
        return 0

    print("Active projects:")
    for project in projects:
        metadata = project.get("metadata") or {}
        project_type = metadata.get("project_type")
        type_label = f" ({project_type})" if project_type else ""
        print(
            f"- {project['slug']} [{project['status']}]{type_label} "
            f"{project['name']}"
        )
    return 0


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_since(value: str | None, default: str = "24h") -> datetime:
    raw = value or default
    match = re.fullmatch(r"\s*(\d+)\s*([hdw])\s*", raw, flags=re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        else:
            delta = timedelta(weeks=amount)
        return datetime.now(timezone.utc) - delta

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "--since must be a duration like 24h, 7d, 2w or an ISO date"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        parsed = datetime.combine(parsed.date(), time.min, tzinfo=parsed.tzinfo)
    return parsed


def fetch_recent_rows(
    cur,
    table: str,
    project_id: object,
    columns: str,
    since: datetime,
    limit: int,
) -> list[dict[str, object]]:
    cur.execute(
        f"""
        SELECT id, {columns}, status, created_at, updated_at
        FROM {table}
        WHERE project_id = %s
          AND updated_at >= %s
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (project_id, since, limit),
    )
    return list(cur.fetchall())


def fetch_recent_agent_actions(
    cur, project_id: object, since: datetime, limit: int
) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT
          aa.id,
          aa.action,
          aa.object_type,
          aa.object_id,
          aa.status,
          aa.created_at,
          aa.updated_at,
          a.slug AS agent_slug
        FROM agent_actions aa
        LEFT JOIN agents a ON a.id = aa.agent_id
        WHERE a.project_id = %s
          AND aa.updated_at >= %s
        ORDER BY aa.updated_at DESC, aa.created_at DESC, aa.id DESC
        LIMIT %s
        """,
        (project_id, since, limit),
    )
    return list(cur.fetchall())


def fetch_recent_sync_events(cur, since: datetime, limit: int) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, source, direction, status, error, created_at, updated_at
        FROM sync_events
        WHERE updated_at >= %s
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (since, limit),
    )
    return list(cur.fetchall())


def fetch_activity_snapshot(
    cur,
    project: dict[str, object],
    since: datetime,
    limit: int,
) -> dict[str, object]:
    project_id = project["id"]
    return {
        "project": project,
        "since": since,
        "facts": fetch_recent_rows(
            cur,
            "facts",
            project_id,
            "statement, source, confidence",
            since,
            limit,
        ),
        "decisions": fetch_recent_rows(
            cur,
            "decisions",
            project_id,
            "decision, rationale, consequences",
            since,
            limit,
        ),
        "risks": fetch_recent_rows(
            cur,
            "risks",
            project_id,
            "title, severity, impact, mitigation",
            since,
            limit,
        ),
        "open_questions": fetch_recent_rows(
            cur,
            "open_questions",
            project_id,
            "question, answer",
            since,
            limit,
        ),
        "reports": fetch_recent_rows(
            cur,
            "reports",
            project_id,
            "title, report_type, summary",
            since,
            limit,
        ),
        "relations": fetch_project_relations(
            cur,
            project_id,
            since=since,
            limit=limit,
        ),
        "agent_actions": fetch_recent_agent_actions(cur, project_id, since, limit),
        "sync_events": fetch_recent_sync_events(cur, since, limit),
    }


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


def write_daily_report(
    cur,
    project: dict[str, object],
    payload: dict[str, object],
    body: str,
) -> dict[str, object]:
    counts = {
        key: len(payload[key])
        for key in ("facts", "decisions", "risks", "open_questions", "relations")
    }
    summary = (
        f"Daily summary: {counts['facts']} facts, {counts['decisions']} decisions, "
        f"{counts['risks']} risks, {counts['open_questions']} open questions, "
        f"{counts['relations']} relations."
    )
    cur.execute(
        """
        INSERT INTO reports (
          project_id, title, report_type, summary, body, status, metadata
        )
        VALUES (%s, %s, 'daily', %s, %s, 'published', %s::jsonb)
        RETURNING id, title, report_type, summary, status, created_at
        """,
        (
            project["id"],
            f"Daily Report - {project['name']} - {datetime.now(timezone.utc).date()}",
            summary,
            body,
            json.dumps(
                {
                    "created_by": "agent-hub daily",
                    "since": payload["since"].isoformat(),
                    "counts": counts,
                }
            ),
        ),
    )
    return cur.fetchone()


def search_project_memory(
    cur,
    project_id: object,
    query: str,
    memory_type: str,
    limit: int,
) -> list[dict[str, object]]:
    like = f"%{query}%"
    specs = {
        "fact": (
            "facts",
            "statement AS title, statement AS text",
            "(statement ILIKE %s OR COALESCE(source, '') ILIKE %s)",
        ),
        "decision": (
            "decisions",
            "decision AS title, decision || COALESCE(E'\n' || rationale, '') AS text",
            "(decision ILIKE %s OR COALESCE(rationale, '') ILIKE %s OR COALESCE(consequences, '') ILIKE %s)",
        ),
        "risk": (
            "risks",
            "title, title || COALESCE(E'\n' || impact, '') || COALESCE(E'\n' || mitigation, '') AS text",
            "(title ILIKE %s OR COALESCE(impact, '') ILIKE %s OR COALESCE(mitigation, '') ILIKE %s)",
        ),
        "open_question": (
            "open_questions",
            "question AS title, question || COALESCE(E'\n' || answer, '') AS text",
            "(question ILIKE %s OR COALESCE(answer, '') ILIKE %s)",
        ),
        "report": (
            "reports",
            "title, title || COALESCE(E'\n' || summary, '') || COALESCE(E'\n' || body, '') AS text",
            "(title ILIKE %s OR COALESCE(summary, '') ILIKE %s OR COALESCE(body, '') ILIKE %s)",
        ),
    }
    selected = specs.keys() if memory_type == "all" else (memory_type,)
    results: list[dict[str, object]] = []
    for item_type in selected:
        table, select_expr, where_expr = specs[item_type]
        param_count = where_expr.count("%s")
        cur.execute(
            f"""
            SELECT id, %s AS type, {select_expr}, status, updated_at
            FROM {table}
            WHERE project_id = %s
              AND {where_expr}
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            (item_type, project_id, *([like] * param_count), limit),
        )
        results.extend(cur.fetchall())
    results.sort(key=lambda row: row["updated_at"], reverse=True)
    return results[:limit]


def export_path_for_object(
    export_dir: Path | None,
    memory_type: str,
    row: dict[str, object],
) -> Path | None:
    if export_dir is None:
        return None
    spec = EXPORT_SPECS_BY_TYPE[memory_type]
    normalized = normalize_row(dict(row))
    return export_dir / str(spec["folder"]) / filename_for(
        normalized,
        spec["title_fields"],
    )


def get_export_dir_or_none() -> Path | None:
    export_dir_env = os.environ.get("OBSIDIAN_EXPORT_DIR")
    return Path(export_dir_env) if export_dir_env else None


def receipt_title(row: dict[str, object]) -> str:
    for key in (
        "title",
        "statement",
        "decision",
        "question",
        "action",
    ):
        value = row.get(key)
        if value:
            return str(value)
    return str(row.get("id", "untitled"))


def fetch_receipt_rows(
    cur,
    project: dict[str, object],
    since: datetime,
    memory_type: str,
    limit: int,
    export_dir: Path | None,
) -> list[dict[str, object]]:
    project_id = project["id"]
    specs = {
        "fact": (
            """
            SELECT id, statement, source, confidence, status, metadata, created_at, updated_at
            FROM facts
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "statement",
        ),
        "decision": (
            """
            SELECT id, decision, rationale, consequences, status, metadata, created_at, updated_at
            FROM decisions
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "decision",
        ),
        "risk": (
            """
            SELECT id, title, severity, impact, mitigation, status, metadata, created_at, updated_at
            FROM risks
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "title",
        ),
        "open_question": (
            """
            SELECT id, question, answer, status, metadata, created_at, updated_at
            FROM open_questions
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "question",
        ),
        "report": (
            """
            SELECT id, title, report_type, summary, body, status, metadata, created_at, updated_at
            FROM reports
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "title",
        ),
    }
    selected = (
        ("fact", "decision", "risk", "open_question", "report", "agent_action")
        if memory_type == "all"
        else (memory_type,)
    )
    rows: list[dict[str, object]] = []
    for item_type in selected:
        if item_type == "agent_action":
            cur.execute(
                """
                SELECT aa.id, aa.action, aa.object_type, aa.object_id, aa.status,
                       aa.metadata, aa.created_at, aa.updated_at,
                       a.slug AS agent_slug
                FROM agent_actions aa
                JOIN agents a ON a.id = aa.agent_id
                WHERE a.project_id = %s AND aa.updated_at >= %s
                ORDER BY aa.updated_at DESC, aa.created_at DESC, aa.id DESC
                LIMIT %s
                """,
                (project_id, since, limit),
            )
            fetched = list(cur.fetchall())
        else:
            query, _title_key = specs[item_type]
            cur.execute(query, (project_id, since, limit))
            fetched = list(cur.fetchall())

        for raw in fetched:
            row = dict(raw)
            path = export_path_for_object(export_dir, item_type, row)
            rows.append(
                {
                    "type": item_type,
                    "id": row["id"],
                    "title": receipt_title(row),
                    "status": row.get("status"),
                    "updated_at": row.get("updated_at"),
                    "created_at": row.get("created_at"),
                    "export_path": str(path) if path else None,
                    "exported": bool(path and path.exists()),
                    "object": row,
                }
            )
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows[:limit]


def run_check(_args: argparse.Namespace) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    database_url = os.environ.get("DATABASE_URL")

    print("Central Agent Data Hub check")
    print()

    if not database_url:
        print("Database: missing (DATABASE_URL is not set)")
        print()
        print("Check result: errors")
        return 1

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                print("Database: ok")
                print()

                print("Core table counts:")
                counts = fetch_table_counts(cur)
                for table, count in counts.items():
                    print(f"  {table}: {count}")
                print()

                migration_report = describe_migrations(conn)
                print_migration_report(migration_report)
                for item in migration_report["migrations"]:
                    if item["status"] == "pending":
                        warnings.append(
                            f"migration {item['migration_id']} is pending"
                        )
                    elif item["status"] in ("failed", "changed"):
                        errors.append(
                            f"migration {item['migration_id']} is {item['status']}"
                        )
                print()

                missing_projects = find_missing_project_references(cur)
                print("Missing project references:")
                if missing_projects:
                    for table, count in missing_projects:
                        message = f"{table}: {count} row(s) with project_id missing"
                        errors.append(message)
                        print(f"  error: {message}")
                else:
                    print("  ok")
                print()

                broken_relations = (
                    find_broken_relation_side(cur, "source")
                    + find_broken_relation_side(cur, "target")
                )
                print("Broken polymorphic relations:")
                if broken_relations:
                    for relation in broken_relations:
                        message = (
                            f"{relation['relation_id']} {relation['side']} "
                            f"{relation['object_type']}:{relation['object_id']} "
                            f"({relation['relation_type']})"
                        )
                        errors.append(message)
                        print(f"  error: {message}")
                else:
                    print("  ok")
                print()

                unknown_relation_types = find_unknown_relation_types(cur)
                print("Unknown relation types:")
                if unknown_relation_types:
                    for relation in unknown_relation_types:
                        message = (
                            f"{relation['id']} relation_type="
                            f"{relation['relation_type']} "
                            f"{relation['source_type']}:{relation['source_id']} -> "
                            f"{relation['target_type']}:{relation['target_id']}"
                        )
                        warnings.append(message)
                        print(f"  warning: {message}")
                else:
                    print("  ok")
                print()

                low_confidence_facts = fetch_low_confidence_facts(cur)
                print("Low-confidence facts (< 0.6):")
                if low_confidence_facts:
                    for fact in low_confidence_facts:
                        message = (
                            f"{fact['id']} confidence={fact['confidence']} "
                            f"status={fact['status']} "
                            f"statement={truncate(fact['statement'])}"
                        )
                        warnings.append(message)
                        print(f"  warning: {message}")
                else:
                    print("  ok")
                print()

                quality_warnings = fetch_memory_quality_warnings(cur)
                print("Memory quality:")
                if quality_warnings:
                    for item in quality_warnings:
                        message = (
                            f"{item['type']}:{item['id']} "
                            f"{item['issue']} "
                            f"title={truncate(item['title'])}"
                        )
                        warnings.append(message)
                        print(f"  warning: {message}")
                else:
                    print("  ok")
                print()

                questions = fetch_open_questions(cur)
                print("Open questions (status != resolved):")
                if questions:
                    for question in questions:
                        message = (
                            f"{question['id']} status={question['status']} "
                            f"question={truncate(question['question'])}"
                        )
                        warnings.append(message)
                        print(f"  warning: {message}")
                else:
                    print("  ok")
                print()

                sync_event = fetch_latest_sync_event(cur)
                print("Latest sync event:")
                if sync_event:
                    print(
                        "  "
                        f"{sync_event['status']} "
                        f"source={sync_event['source']} "
                        f"direction={sync_event['direction']} "
                        f"updated_at={sync_event['updated_at']}"
                    )
                else:
                    print("  none")

    except Exception as exc:
        print(f"Database: error ({concise_error(exc)})")
        print()
        print("Check result: errors")
        return 1

    print()
    if errors:
        print("Check result: errors")
        return 1
    if warnings:
        print("Check result: warnings")
        return 0
    print("Check result: ok")
    return 0


def fetch_brief_rows(
    cur,
    table: str,
    project_id: object,
    columns: str,
    excluded_statuses: tuple[str, ...] = ("archived",),
    limit: int = 8,
) -> list[dict[str, object]]:
    placeholders = ", ".join(["%s"] * len(excluded_statuses))
    cur.execute(
        f"""
        SELECT {columns}, status, updated_at
        FROM {table}
        WHERE project_id = %s
          AND status NOT IN ({placeholders})
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (project_id, *excluded_statuses, limit),
    )
    return list(cur.fetchall())


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


def run_remember(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        metadata = parse_metadata(args.metadata)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    metadata.setdefault("created_by", "agent-hub remember")
    if args.source:
        metadata.setdefault("source", args.source)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project, agent, object_type, row = remember(cur, args, metadata)
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    result = {
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
        "type": object_type,
        "object": row,
    }

    if args.format == "json":
        print(json.dumps(result, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(
        f"Remembered {object_type} for project '{project['slug']}': "
        f"{row['id']}"
    )
    return 0


def run_import(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

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
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(result.__dict__, indent=2, default=json_default))
    else:
        action = "Planned" if args.dry_run else "Imported"
        rows = result.planned if args.dry_run else result.imported
        print(f"{action} {len(rows)} Markdown note(s).")
        for row in rows:
            suffix = f" -> {row['id']}" if "id" in row else ""
            row_action = row.get("action", "import")
            print(
                f"- {row_action} {row['type']} {row['project']}: "
                f"{row['path']}{suffix}"
            )
        if result.errors:
            print()
            print(f"Errors: {len(result.errors)}")
            for error in result.errors:
                print(f"- {error['path']}: {error['error']}")

    return 1 if result.errors else 0


def print_sync_result(result) -> None:
    print(f"Planned {len(result.planned)} Markdown note(s).")
    for row in result.planned:
        label = row.get("type", "unknown")
        project = row.get("project", "unknown")
        reason = f" ({row['reason']})" if row.get("reason") else ""
        print(f"- {row['action']} {label} {project}: {row['path']}{reason}")
        if row.get("diffs"):
            fields = ", ".join(diff["field"] for diff in row["diffs"])
            print(f"  fields: {fields}")
            if row["action"] == "conflict":
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
        for error in result.errors:
            print(f"- {error['path']}: {error['error']}")


def run_sync(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    if args.watch:
        print(
            "Error: sync --watch is intentionally not implemented yet. "
            "Use --plan or --apply first.",
            file=sys.stderr,
        )
        return 2
    if args.plan == args.apply:
        print("Error: choose exactly one of --plan or --apply", file=sys.stderr)
        return 2

    try:
        with connect() as conn:
            result = sync_markdown(
                Path(args.path),
                Path(args.allowlist),
                conn,
                apply=args.apply,
            )
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(result.__dict__, indent=2, default=json_default))
    else:
        print_sync_result(result)

    blockers = result.blocking_actions
    if result.errors or blockers:
        return 1
    return 0


def run_relations(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2
    if bool(args.object_type) != bool(args.object_id):
        print(
            "Error: --object-type and --object-id must be used together",
            file=sys.stderr,
        )
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
                rows = fetch_project_relations(
                    cur,
                    project["id"],
                    object_type=args.object_type,
                    object_id=args.object_id,
                )
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    payload = {"project": project, "relations": rows}
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"Relations for {project['slug']}:")
    print_relations(rows)
    return 0


def run_relate(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        metadata = parse_metadata(args.metadata)
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

                source = fetch_relation_object(cur, args.source_type, args.source_id)
                target = fetch_relation_object(cur, args.target_type, args.target_id)
                validate_relation_object(args.source_type, source, project, "source")
                validate_relation_object(args.target_type, target, project, "target")

                cur.execute(
                    """
                    INSERT INTO relations (
                      source_type, source_id, relation_type,
                      target_type, target_id, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (
                      source_type, source_id, relation_type, target_type, target_id
                    ) DO UPDATE SET
                      metadata = relations.metadata || EXCLUDED.metadata
                    RETURNING id, source_type, source_id, relation_type,
                              target_type, target_id, metadata, created_at, updated_at
                    """,
                    (
                        args.source_type,
                        args.source_id,
                        args.relation,
                        args.target_type,
                        args.target_id,
                        json.dumps(metadata),
                    ),
                )
                relation = cur.fetchone()
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    payload = {
        "project": project,
        "relation": relation,
        "source_summary": source["summary"],
        "target_summary": target["summary"],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print("Relation stored:")
    print(
        f"- {relation['source_type']}:{relation['source_id']} "
        f"({truncate(source['summary'], 72)}) "
        f"--{relation['relation_type']}--> "
        f"{relation['target_type']}:{relation['target_id']} "
        f"({truncate(target['summary'], 72)})"
    )
    return 0


def not_implemented(args: argparse.Namespace) -> int:
    print(f"Command '{args.command}' is not implemented yet.", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hub",
        description="Agent Data Hub command line tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export",
        help="Export database rows to Obsidian Markdown files.",
    )
    export_parser.set_defaults(func=run_export)

    status_parser = subparsers.add_parser(
        "status",
        help="Show a quick database and export-directory diagnostic.",
    )
    status_parser.set_defaults(func=run_status)

    check_parser = subparsers.add_parser(
        "check",
        help="Run consistency checks for export and review readiness.",
    )
    check_parser.set_defaults(func=run_check)

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Show or apply database schema migrations.",
    )
    migrate_mode = migrate_parser.add_mutually_exclusive_group(required=True)
    migrate_mode.add_argument(
        "--status",
        action="store_true",
        help="Show applied, pending, and failed migrations.",
    )
    migrate_mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply pending migrations in file order.",
    )
    migrate_parser.set_defaults(func=run_migrate)

    projects_parser = subparsers.add_parser(
        "projects",
        help="List active project slugs available for agent work.",
    )
    projects_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    projects_parser.add_argument(
        "--type",
        dest="project_type",
        help="Filter by projects.metadata.project_type, for example website.",
    )
    projects_parser.set_defaults(func=run_projects)

    brief_parser = subparsers.add_parser(
        "brief",
        help="Print a concise project memory brief for agents.",
    )
    brief_parser.add_argument(
        "--project",
        required=True,
        help="Project slug to summarize, for example commcats-de.",
    )
    brief_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum rows per memory section.",
    )
    brief_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    brief_parser.add_argument(
        "--with-relations",
        action="store_true",
        help="Include relevant project relations in the brief.",
    )
    brief_parser.set_defaults(func=run_brief)

    daily_parser = subparsers.add_parser(
        "daily",
        help="Summarize recent project memory for a daily working brief.",
    )
    daily_parser.add_argument("--project", required=True, help="Project slug.")
    daily_parser.add_argument(
        "--since",
        default="24h",
        help="Duration like 24h, 7d, 2w or ISO date. Default: 24h.",
    )
    daily_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum rows per daily section.",
    )
    daily_parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    daily_parser.add_argument(
        "--write-report",
        action="store_true",
        help="Store the daily summary as a published report row.",
    )
    daily_parser.set_defaults(func=run_daily)

    handoff_parser = subparsers.add_parser(
        "handoff",
        help="Print a project handoff report for the next agent or session.",
    )
    handoff_parser.add_argument("--project", required=True, help="Project slug.")
    handoff_parser.add_argument(
        "--since",
        default="7d",
        help="Duration like 24h, 7d, 2w or ISO date. Default: 7d.",
    )
    handoff_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum rows per handoff section.",
    )
    handoff_parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    handoff_parser.set_defaults(func=run_handoff)

    review_parser = subparsers.add_parser(
        "review",
        help="Review decisions, risks, open questions, and relations.",
    )
    review_parser.add_argument("--project", required=True, help="Project slug.")
    review_parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum rows per review section.",
    )
    review_parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    review_parser.set_defaults(func=run_review)

    search_parser = subparsers.add_parser(
        "search",
        help="Search project memory with simple PostgreSQL text matching.",
    )
    search_parser.add_argument("--project", required=True, help="Project slug.")
    search_parser.add_argument("--query", required=True, help="Text to search for.")
    search_parser.add_argument(
        "--type",
        dest="memory_type",
        choices=("all", "fact", "decision", "risk", "open_question", "report"),
        default="all",
        help="Memory type filter.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum search results.",
    )
    search_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    search_parser.set_defaults(func=run_search)

    context_parser = subparsers.add_parser(
        "context",
        help="Build a compact project context pack from brief, search, and relations.",
    )
    context_parser.add_argument("--project", required=True, help="Project slug.")
    context_parser.add_argument("--query", required=True, help="Focus query.")
    context_parser.add_argument(
        "--since",
        default="30d",
        help="Recent activity window. Default: 30d.",
    )
    context_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum rows per context section.",
    )
    context_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    context_parser.set_defaults(func=run_context)

    compile_parser = subparsers.add_parser(
        "compile",
        help="Build a compact token-efficient project memory for agent starts.",
    )
    compile_parser.add_argument("--project", required=True, help="Project slug.")
    compile_parser.add_argument(
        "--limit",
        type=positive_int,
        default=5,
        help="Maximum rows per compiled section.",
    )
    compile_parser.add_argument(
        "--since",
        help="Include a recent-change count since a duration like 24h, 7d, 2w or ISO date.",
    )
    compile_parser.add_argument(
        "--with-receipt-status",
        action="store_true",
        help="Include recent memory export receipt counts.",
    )
    compile_parser.add_argument(
        "--max-chars",
        type=positive_int,
        help="Maximum markdown characters to print. JSON output is unaffected.",
    )
    compile_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    compile_parser.set_defaults(func=run_compile)

    quality_parser = subparsers.add_parser(
        "quality",
        help="Show project memory quality, gaps, and relation coverage.",
    )
    quality_parser.add_argument("--project", required=True, help="Project slug.")
    quality_parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    quality_parser.set_defaults(func=run_quality)

    receipt_parser = subparsers.add_parser(
        "receipt",
        help="Verify recent project memory writes and Obsidian export files.",
    )
    receipt_parser.add_argument("--project", required=True, help="Project slug.")
    receipt_parser.add_argument(
        "--since",
        default="24h",
        help="Duration like 24h, 7d, 2w or ISO date. Default: 24h.",
    )
    receipt_parser.add_argument(
        "--type",
        dest="memory_type",
        choices=RECEIPT_TYPES,
        default="all",
        help="Memory type to verify.",
    )
    receipt_parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum receipt rows.",
    )
    receipt_parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    receipt_parser.add_argument(
        "--require-results",
        action="store_true",
        help="Exit 1 if no matching memory rows are found.",
    )
    receipt_parser.add_argument(
        "--require-exported",
        action="store_true",
        help="Exit 1 if matching rows do not have exported Markdown files.",
    )
    receipt_parser.set_defaults(func=run_receipt)

    relations_parser = subparsers.add_parser(
        "relations",
        help="List curated relations for a project graph.",
    )
    relations_parser.add_argument(
        "--project",
        required=True,
        help="Project slug to inspect.",
    )
    relations_parser.add_argument(
        "--object-type",
        choices=tuple(RELATION_TARGETS),
        help="Limit to relations touching this object type.",
    )
    relations_parser.add_argument(
        "--object-id",
        help="Limit to relations touching this object id.",
    )
    relations_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    relations_parser.set_defaults(func=run_relations)

    relate_parser = subparsers.add_parser(
        "relate",
        help="Create or update a curated relation between two Hub objects.",
    )
    relate_parser.add_argument(
        "--project",
        required=True,
        help="Project slug that owns the relation context.",
    )
    relate_parser.add_argument(
        "--source-type",
        required=True,
        choices=tuple(RELATION_TARGETS),
        help="Source object type.",
    )
    relate_parser.add_argument(
        "--source-id",
        required=True,
        help="Source object UUID.",
    )
    relate_parser.add_argument(
        "--relation",
        required=True,
        choices=RELATION_TYPES,
        help="Curated relation type.",
    )
    relate_parser.add_argument(
        "--target-type",
        required=True,
        choices=tuple(RELATION_TARGETS),
        help="Target object type.",
    )
    relate_parser.add_argument(
        "--target-id",
        required=True,
        help="Target object UUID.",
    )
    relate_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Additional metadata in key=value form; repeatable.",
    )
    relate_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    relate_parser.set_defaults(func=run_relate)

    remember_parser = subparsers.add_parser(
        "remember",
        help="Store a reviewed fact, decision, question, risk, or report.",
    )
    remember_parser.add_argument(
        "--project",
        required=True,
        help="Project slug, for example the-one-catering.",
    )
    remember_parser.add_argument(
        "--create-project",
        action="store_true",
        help="Create the project when it does not exist.",
    )
    remember_parser.add_argument(
        "--project-name",
        help="Project name to use with --create-project.",
    )
    remember_parser.add_argument(
        "--project-description",
        help="Project description to use with --create-project.",
    )
    remember_parser.add_argument(
        "--agent",
        default="codex",
        help="Agent slug to attribute the write to.",
    )
    remember_parser.add_argument(
        "--agent-name",
        default="Codex",
        help="Agent display name to attribute the write to.",
    )
    remember_parser.add_argument(
        "--type",
        dest="memory_type",
        required=True,
        choices=REMEMBER_TYPES,
        help="Memory object type.",
    )
    remember_parser.add_argument(
        "--text",
        required=True,
        help="Primary memory text.",
    )
    remember_parser.add_argument(
        "--status",
        help="Status override; defaults depend on the memory type.",
    )
    remember_parser.add_argument(
        "--source",
        help="Source path, URL, or short provenance note.",
    )
    remember_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Additional metadata in key=value form; repeatable.",
    )
    remember_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    remember_parser.add_argument(
        "--confidence",
        type=confidence_value,
        default=0.9,
        help="Fact confidence from 0 to 1.",
    )
    remember_parser.add_argument("--rationale", help="Decision rationale.")
    remember_parser.add_argument(
        "--consequences",
        help="Decision consequences or operational effect.",
    )
    remember_parser.add_argument("--answer", help="Answer for open-question rows.")
    remember_parser.add_argument(
        "--severity",
        choices=("low", "medium", "high", "critical"),
        default="medium",
        help="Risk severity.",
    )
    remember_parser.add_argument("--impact", help="Risk impact.")
    remember_parser.add_argument("--mitigation", help="Risk mitigation.")
    remember_parser.add_argument("--title", help="Report title.")
    remember_parser.add_argument(
        "--report-type",
        default="status",
        help="Report type, for example status, audit, handoff.",
    )
    remember_parser.add_argument("--summary", help="Report summary.")
    remember_parser.add_argument("--body", help="Report body.")
    remember_parser.set_defaults(func=run_remember)

    import_parser = subparsers.add_parser(
        "import",
        help="Import allowlisted Obsidian Markdown notes into Postgres.",
    )
    import_parser.add_argument(
        "--path",
        required=True,
        help="Markdown file or directory to import.",
    )
    import_parser.add_argument(
        "--allowlist",
        default="import_allowlist.yml",
        help="YAML allowlist path. Defaults to import_allowlist.yml.",
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show planned imports without writing to Postgres.",
    )
    import_parser.add_argument(
        "--on-duplicate",
        choices=("skip", "error", "update"),
        default="skip",
        help="How to handle an existing import target. Defaults to skip.",
    )
    import_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    import_parser.set_defaults(func=run_import)

    sync_parser = subparsers.add_parser(
        "sync",
        help="Plan or apply allowlisted Obsidian-to-Postgres sync.",
    )
    sync_parser.add_argument(
        "--path",
        required=True,
        help="Markdown file or directory to sync.",
    )
    sync_parser.add_argument(
        "--allowlist",
        default="import_allowlist.yml",
        help="YAML allowlist path. Defaults to import_allowlist.yml.",
    )
    sync_parser.add_argument(
        "--plan",
        action="store_true",
        help="Show create/update/skip/conflict/reject actions without writing.",
    )
    sync_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply create/update actions only when the plan has no blockers.",
    )
    sync_parser.add_argument(
        "--watch",
        action="store_true",
        help="Reserved for a future defensive automation mode.",
    )
    sync_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    sync_parser.set_defaults(func=run_sync)

    for name in ("init",):
        placeholder = subparsers.add_parser(
            name,
            help="Not implemented yet.",
        )
        placeholder.set_defaults(func=not_implemented)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
