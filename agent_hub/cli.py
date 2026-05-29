"""Command line interface for Central Agent Data Hub."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_hub.db import connect
from agent_hub.export_obsidian import export_all
from agent_hub.import_obsidian import import_markdown, sync_markdown

CORE_TABLES = (
    "projects",
    "documents",
    "reports",
    "decisions",
    "facts",
    "open_questions",
    "risks",
    "agent_actions",
    "sync_events",
)

REMEMBER_TYPES = (
    "fact",
    "decision",
    "open-question",
    "risk",
    "report",
)

PROJECT_SCOPED_TABLES = (
    "documents",
    "reports",
    "decisions",
    "facts",
    "open_questions",
    "risks",
    "agent_actions",
)

RELATION_TARGETS = {
    "project": "projects",
    "agent": "agents",
    "document": "documents",
    "report": "reports",
    "decision": "decisions",
    "fact": "facts",
    "open_question": "open_questions",
    "risk": "risks",
    "agent_action": "agent_actions",
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


def ensure_project(cur, args: argparse.Namespace) -> dict[str, object]:
    project = fetch_project(cur, args.project)
    if project:
        return project
    if not getattr(args, "create_project", False):
        raise RuntimeError(
            f"Project '{args.project}' not found. "
            "Use --create-project to create it explicitly."
        )

    name = args.project_name or args.project.replace("-", " ").title()
    cur.execute(
        """
        INSERT INTO projects (name, slug, description, metadata)
        VALUES (%s, %s, %s, %s::jsonb)
        RETURNING id, name, slug, description, status, metadata, created_at, updated_at
        """,
        (
            name,
            args.project,
            args.project_description,
            json.dumps({"created_by": "agent-hub remember"}),
        ),
    )
    return cur.fetchone()


def ensure_agent(cur, project_id: object, slug: str, name: str) -> dict[str, object]:
    cur.execute(
        """
        INSERT INTO agents (project_id, name, slug, role, status, metadata)
        VALUES (%s, %s, %s, %s, 'active', %s::jsonb)
        ON CONFLICT (project_id, slug) DO UPDATE SET
          name = EXCLUDED.name,
          role = EXCLUDED.role,
          status = EXCLUDED.status,
          metadata = agents.metadata || EXCLUDED.metadata
        RETURNING id, project_id, name, slug, role, status, metadata
        """,
        (
            project_id,
            name,
            slug,
            "Coding and implementation agent",
            json.dumps({"interface": "agent-hub"}),
        ),
    )
    return cur.fetchone()


def log_agent_action(
    cur,
    agent_id: object,
    action: str,
    object_type: str,
    object_id: object,
    args: argparse.Namespace,
    output: dict[str, object],
) -> None:
    input_payload = {
        "command": "remember",
        "project": args.project,
        "type": args.memory_type,
        "source": args.source,
    }
    cur.execute(
        """
        INSERT INTO agent_actions (
          agent_id, action, object_type, object_id,
          input, output, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, 'succeeded', %s::jsonb)
        """,
        (
            agent_id,
            action,
            object_type,
            object_id,
            json.dumps(input_payload),
            json.dumps(output, default=json_default),
            json.dumps({"created_by": "agent-hub remember"}),
        ),
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
                    for table in CORE_TABLES:
                        cur.execute(f"SELECT count(*) AS count FROM {table}")
                        row = cur.fetchone()
                        print(f"  {table}: {row['count']}")
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


def fetch_table_counts(cur) -> dict[str, int]:
    counts = {}
    for table in CORE_TABLES:
        cur.execute(f"SELECT count(*) AS count FROM {table}")
        row = cur.fetchone()
        counts[table] = row["count"]
    return counts


def table_has_column(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = %s
            AND column_name = %s
        ) AS exists
        """,
        (table, column),
    )
    return cur.fetchone()["exists"]


def find_missing_project_references(cur) -> list[tuple[str, int]]:
    missing = []
    for table in PROJECT_SCOPED_TABLES:
        if not table_has_column(cur, table, "project_id"):
            continue
        cur.execute(f"SELECT count(*) AS count FROM {table} WHERE project_id IS NULL")
        count = cur.fetchone()["count"]
        if count:
            missing.append((table, count))
    return missing


def find_broken_relation_side(cur, side: str) -> list[dict[str, object]]:
    broken = []
    type_column = f"{side}_type"
    id_column = f"{side}_id"
    for object_type, table in RELATION_TARGETS.items():
        cur.execute(
            f"""
            SELECT r.id, r.relation_type, r.{type_column}, r.{id_column}
            FROM relations r
            LEFT JOIN {table} target ON target.id = r.{id_column}
            WHERE r.{type_column} = %s
              AND target.id IS NULL
            ORDER BY r.created_at, r.id
            """,
            (object_type,),
        )
        for row in cur.fetchall():
            broken.append(
                {
                    "relation_id": row["id"],
                    "relation_type": row["relation_type"],
                    "side": side,
                    "object_type": row[type_column],
                    "object_id": row[id_column],
                }
            )
    return broken


def fetch_low_confidence_facts(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, statement, confidence, status
        FROM facts
        WHERE confidence < 0.6
        ORDER BY confidence, created_at, id
        """
    )
    return list(cur.fetchall())


def fetch_open_questions(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, question, status
        FROM open_questions
        WHERE status NOT IN ('answered', 'closed', 'archived')
        ORDER BY created_at, id
        """
    )
    return list(cur.fetchall())


def fetch_latest_sync_event(cur) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT id, source, direction, status, created_at, updated_at
        FROM sync_events
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    )
    return cur.fetchone()


def truncate(value: object, limit: int = 96) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


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

        brief = {
            "project": project,
            "counts": counts,
            "decisions": decisions,
            "facts": facts,
            "open_questions": questions,
            "risks": risks,
            "reports": reports,
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
    return 0


def insert_fact(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "verified"
    cur.execute(
        """
        INSERT INTO facts (project_id, statement, source, confidence, status, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, statement, source, confidence, status, created_at
        """,
        (
            project_id,
            args.text,
            args.source,
            args.confidence,
            status,
            json.dumps(metadata),
        ),
    )
    return "fact", cur.fetchone()


def insert_decision(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "accepted"
    cur.execute(
        """
        INSERT INTO decisions (
          project_id, decision, rationale, consequences, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, decision, rationale, consequences, status, created_at
        """,
        (
            project_id,
            args.text,
            args.rationale,
            args.consequences,
            status,
            json.dumps(metadata),
        ),
    )
    return "decision", cur.fetchone()


def insert_open_question(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "open"
    cur.execute(
        """
        INSERT INTO open_questions (
          project_id, question, answer, status, resolved_at, metadata
        )
        VALUES (
          %s, %s, %s, %s,
          CASE WHEN %s IN ('answered', 'closed') THEN now() ELSE NULL END,
          %s::jsonb
        )
        RETURNING id, question, answer, status, resolved_at, created_at
        """,
        (
            project_id,
            args.text,
            args.answer,
            status,
            status,
            json.dumps(metadata),
        ),
    )
    return "open_question", cur.fetchone()


def insert_risk(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "open"
    cur.execute(
        """
        INSERT INTO risks (
          project_id, title, severity, impact, mitigation, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, title, severity, impact, mitigation, status, created_at
        """,
        (
            project_id,
            args.text,
            args.severity,
            args.impact,
            args.mitigation,
            status,
            json.dumps(metadata),
        ),
    )
    return "risk", cur.fetchone()


def insert_report(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "published"
    title = args.title or truncate(args.text, 80)
    body = args.body or args.text
    cur.execute(
        """
        INSERT INTO reports (
          project_id, title, report_type, summary, body, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, title, report_type, summary, status, created_at
        """,
        (
            project_id,
            title,
            args.report_type,
            args.summary,
            body,
            status,
            json.dumps(metadata),
        ),
    )
    return "report", cur.fetchone()


REMEMBER_INSERTS = {
    "fact": insert_fact,
    "decision": insert_decision,
    "open-question": insert_open_question,
    "risk": insert_risk,
    "report": insert_report,
}


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
                project = ensure_project(cur, args)
                agent = ensure_agent(cur, project["id"], args.agent, args.agent_name)
                insert_func = REMEMBER_INSERTS[args.memory_type]
                object_type, row = insert_func(cur, project["id"], args, metadata)
                log_agent_action(
                    cur,
                    agent["id"],
                    f"remember_{object_type}",
                    object_type,
                    row["id"],
                    args,
                    {"project_id": project["id"], "object": row},
                )
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


def not_implemented(args: argparse.Namespace) -> int:
    print(f"Command '{args.command}' is not implemented yet.", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hub",
        description="Central Agent Data Hub command line tools.",
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
    brief_parser.set_defaults(func=run_brief)

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
