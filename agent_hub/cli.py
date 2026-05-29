"""Command line interface for Central Agent Data Hub."""

from __future__ import annotations

import argparse
import hashlib
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

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BASELINE_MIGRATION_ID = "001"
TRACKING_MIGRATION_ID = "002"

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

RELATION_TYPES = (
    "supports",
    "contradicts",
    "supersedes",
    "mitigates",
    "answers",
    "raises",
    "references",
    "derived_from",
    "blocks",
    "depends_on",
)

RELATION_SUMMARY_COLUMNS = {
    "project": "name",
    "agent": "name",
    "document": "title",
    "report": "title",
    "decision": "decision",
    "fact": "statement",
    "open_question": "question",
    "risk": "title",
    "agent_action": "action",
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


def fetch_relation_object(
    cur, object_type: str, object_id: str
) -> dict[str, object] | None:
    table = RELATION_TARGETS[object_type]
    summary_column = RELATION_SUMMARY_COLUMNS[object_type]
    if object_type == "agent_action":
        cur.execute(
            f"""
            SELECT aa.id, a.project_id, aa.{summary_column} AS summary
            FROM agent_actions aa
            LEFT JOIN agents a ON a.id = aa.agent_id
            WHERE aa.id = %s
            """,
            (object_id,),
        )
    else:
        select_project_id = "id AS project_id" if object_type == "project" else "project_id"
        cur.execute(
            f"""
            SELECT id, {select_project_id}, {summary_column} AS summary
            FROM {table}
            WHERE id = %s
            """,
            (object_id,),
        )
    return cur.fetchone()


def validate_relation_object(
    object_type: str,
    row: dict[str, object] | None,
    project: dict[str, object],
    role: str,
) -> None:
    if not row:
        raise RuntimeError(f"{role} {object_type} not found")

    project_id = row.get("project_id")
    if object_type == "agent" and project_id is None:
        return
    if project_id != project["id"]:
        raise RuntimeError(
            f"{role} {object_type}:{row['id']} does not belong to project "
            f"{project['slug']}"
        )


def relation_project_filter(project_id: object) -> tuple[str, dict[str, object]]:
    filters = []
    params: dict[str, object] = {"project_id": project_id}
    for side in ("source", "target"):
        side_filters = []
        for object_type, table in RELATION_TARGETS.items():
            if object_type == "project":
                side_filters.append(
                    f"(r.{side}_type = 'project' AND r.{side}_id = %(project_id)s)"
                )
            elif object_type == "agent":
                side_filters.append(
                    f"""
                    (r.{side}_type = 'agent' AND EXISTS (
                      SELECT 1 FROM agents a
                      WHERE a.id = r.{side}_id
                        AND a.project_id = %(project_id)s
                    ))
                    """
                )
            elif object_type == "agent_action":
                side_filters.append(
                    f"""
                    (r.{side}_type = 'agent_action' AND EXISTS (
                      SELECT 1 FROM agent_actions aa
                      LEFT JOIN agents a ON a.id = aa.agent_id
                      WHERE aa.id = r.{side}_id
                        AND a.project_id = %(project_id)s
                    ))
                    """
                )
            else:
                side_filters.append(
                    f"""
                    (r.{side}_type = '{object_type}' AND EXISTS (
                      SELECT 1 FROM {table} t
                      WHERE t.id = r.{side}_id
                        AND t.project_id = %(project_id)s
                    ))
                    """
                )
        filters.append("(" + " OR ".join(side_filters) + ")")
    return "(" + " OR ".join(filters) + ")", params


def relation_summary_expression(side: str) -> str:
    parts = []
    for object_type, table in RELATION_TARGETS.items():
        summary_column = RELATION_SUMMARY_COLUMNS[object_type]
        if object_type == "agent_action":
            parts.append(
                f"""
                WHEN r.{side}_type = 'agent_action' THEN (
                  SELECT aa.{summary_column}
                  FROM agent_actions aa
                  WHERE aa.id = r.{side}_id
                )
                """
            )
        else:
            parts.append(
                f"""
                WHEN r.{side}_type = '{object_type}' THEN (
                  SELECT t.{summary_column}
                  FROM {table} t
                  WHERE t.id = r.{side}_id
                )
                """
            )
    return "CASE " + " ".join(parts) + " END"


def fetch_project_relations(
    cur,
    project_id: object,
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    project_where, params = relation_project_filter(project_id)
    clauses = [project_where]
    if object_type and object_id:
        clauses.append(
            """
            (
              (r.source_type = %(object_type)s AND r.source_id = %(object_id)s)
              OR
              (r.target_type = %(object_type)s AND r.target_id = %(object_id)s)
            )
            """
        )
        params["object_type"] = object_type
        params["object_id"] = object_id
    elif object_type or object_id:
        raise RuntimeError("--object-type and --object-id must be used together")

    limit_sql = ""
    if limit:
        limit_sql = "LIMIT %(limit)s"
        params["limit"] = limit

    cur.execute(
        f"""
        SELECT
          r.id,
          r.source_type,
          r.source_id,
          {relation_summary_expression("source")} AS source_summary,
          r.relation_type,
          r.target_type,
          r.target_id,
          {relation_summary_expression("target")} AS target_summary,
          r.metadata,
          r.created_at,
          r.updated_at
        FROM relations r
        WHERE {" AND ".join(clauses)}
        ORDER BY r.updated_at DESC, r.created_at DESC, r.id
        {limit_sql}
        """,
        params,
    )
    return list(cur.fetchall())


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


def migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def migration_parts(path: Path) -> tuple[str, str]:
    migration_id, separator, name = path.stem.partition("_")
    if not separator or not migration_id:
        return path.stem, path.stem
    return migration_id, name


def migration_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT to_regclass(%s) IS NOT NULL AS exists",
        (f"public.{table_name}",),
    )
    row = cur.fetchone()
    return bool(row and row["exists"])


def base_schema_exists(cur) -> bool:
    return table_exists(cur, "projects")


def schema_migrations_exists(cur) -> bool:
    return table_exists(cur, "schema_migrations")


def migration_records(cur) -> dict[str, dict[str, object]]:
    if not schema_migrations_exists(cur):
        return {}
    cur.execute(
        """
        SELECT migration_id, name, checksum, status, applied_at, error
        FROM schema_migrations
        ORDER BY migration_id
        """
    )
    return {row["migration_id"]: row for row in cur.fetchall()}


def record_migration(
    cur,
    migration_id: str,
    name: str,
    checksum: str,
    status: str,
    error: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO schema_migrations (
          migration_id, name, checksum, status, applied_at, error
        )
        VALUES (%s, %s, %s, %s, now(), %s)
        ON CONFLICT (migration_id) DO UPDATE SET
          name = EXCLUDED.name,
          checksum = EXCLUDED.checksum,
          status = EXCLUDED.status,
          applied_at = EXCLUDED.applied_at,
          error = EXCLUDED.error
        """,
        (migration_id, name, checksum, status, error),
    )


def execute_migration_file(conn, path: Path) -> None:
    conn.commit()
    previous_autocommit = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = previous_autocommit


def migration_file_by_id(migration_id: str) -> Path | None:
    for path in migration_files():
        if migration_parts(path)[0] == migration_id:
            return path
    return None


def describe_migrations(conn) -> dict[str, object]:
    files = migration_files()
    with conn.cursor() as cur:
        tracking_exists = schema_migrations_exists(cur)
        base_exists = base_schema_exists(cur)
        records = migration_records(cur) if tracking_exists else {}

    migrations: list[dict[str, object]] = []
    for path in files:
        migration_id, name = migration_parts(path)
        checksum = migration_checksum(path)
        record = records.get(migration_id)
        status = "pending"
        applied_at = None
        error = None

        if record:
            status = str(record["status"])
            applied_at = record["applied_at"]
            error = record["error"]
            if record["checksum"] != checksum and status == "applied":
                status = "changed"
                error = "Migration file checksum differs from applied record."
        elif migration_id == BASELINE_MIGRATION_ID and base_exists:
            status = "applied-untracked"

        migrations.append(
            {
                "migration_id": migration_id,
                "name": name,
                "checksum": checksum,
                "status": status,
                "applied_at": applied_at,
                "error": error,
                "path": str(path),
            }
        )

    applied = [
        item
        for item in migrations
        if item["status"] in ("applied", "applied-untracked")
    ]
    open_items = [
        item
        for item in migrations
        if item["status"] in ("pending", "failed", "changed")
    ]
    failed_items = [
        item
        for item in migrations
        if item["status"] in ("failed", "changed")
    ]
    latest = applied[-1] if applied else None
    return {
        "tracking": "installed" if tracking_exists else "missing",
        "base_schema": base_exists,
        "current_version": latest["migration_id"] if latest else None,
        "open_count": len(open_items),
        "failed_count": len(failed_items),
        "latest": latest,
        "migrations": migrations,
    }


def print_migration_report(report: dict[str, object]) -> None:
    print("Schema migrations:")
    print(f"  Tracking: {report['tracking']}")
    current_version = report["current_version"] or "none"
    print(f"  Current version: {current_version}")
    print(f"  Open migrations: {report['open_count']}")
    latest = report["latest"]
    if latest:
        print(
            "  Last migration status: "
            f"{latest['status']} "
            f"({latest['migration_id']} {latest['name']})"
        )
    else:
        print("  Last migration status: none")
    print("  Migrations:")
    for item in report["migrations"]:
        print(f"    - {item['migration_id']} {item['name']}: {item['status']}")
        if item["error"]:
            print(f"      error: {item['error']}")


def apply_migrations(conn) -> tuple[list[str], list[str]]:
    files = migration_files()
    if not files:
        return [], [f"No migration files found in {MIGRATIONS_DIR}"]

    applied: list[str] = []
    errors: list[str] = []

    with conn.cursor() as cur:
        tracking_exists = schema_migrations_exists(cur)
        base_exists = base_schema_exists(cur)

    baseline_path = migration_file_by_id(BASELINE_MIGRATION_ID)
    tracking_path = migration_file_by_id(TRACKING_MIGRATION_ID)

    if not tracking_exists:
        if not tracking_path:
            return applied, [
                f"Tracking migration {TRACKING_MIGRATION_ID} is missing."
            ]

        if base_exists:
            try:
                execute_migration_file(conn, tracking_path)
            except Exception as exc:
                return applied, [
                    f"{TRACKING_MIGRATION_ID} failed: {concise_error(exc)}"
                ]
            with conn.cursor() as cur:
                if baseline_path:
                    baseline_id, baseline_name = migration_parts(baseline_path)
                    record_migration(
                        cur,
                        baseline_id,
                        baseline_name,
                        migration_checksum(baseline_path),
                        "applied",
                    )
                tracking_id, tracking_name = migration_parts(tracking_path)
                record_migration(
                    cur,
                    tracking_id,
                    tracking_name,
                    migration_checksum(tracking_path),
                    "applied",
                )
            conn.commit()
            applied.append(
                f"{TRACKING_MIGRATION_ID} schema_migrations "
                "(bootstrapped existing schema)"
            )
        else:
            if not baseline_path:
                return applied, [
                    f"Baseline migration {BASELINE_MIGRATION_ID} is missing."
                ]
            try:
                execute_migration_file(conn, baseline_path)
                execute_migration_file(conn, tracking_path)
            except Exception as exc:
                return applied, [f"Migration failed: {concise_error(exc)}"]
            with conn.cursor() as cur:
                for path in (baseline_path, tracking_path):
                    migration_id, name = migration_parts(path)
                    record_migration(
                        cur,
                        migration_id,
                        name,
                        migration_checksum(path),
                        "applied",
                    )
                    applied.append(f"{migration_id} {name}")
            conn.commit()

    with conn.cursor() as cur:
        records = migration_records(cur)
        base_exists = base_schema_exists(cur)
        if base_exists and baseline_path and BASELINE_MIGRATION_ID not in records:
            baseline_id, baseline_name = migration_parts(baseline_path)
            record_migration(
                cur,
                baseline_id,
                baseline_name,
                migration_checksum(baseline_path),
                "applied",
            )
            applied.append(f"{baseline_id} {baseline_name} (registered)")
        conn.commit()

    for path in files:
        migration_id, name = migration_parts(path)
        checksum = migration_checksum(path)
        with conn.cursor() as cur:
            records = migration_records(cur)
            record = records.get(migration_id)
        if record and record["status"] == "applied":
            if record["checksum"] != checksum:
                errors.append(
                    f"{migration_id} {name} checksum changed after apply"
                )
                break
            continue

        try:
            execute_migration_file(conn, path)
        except Exception as exc:
            message = concise_error(exc)
            with conn.cursor() as cur:
                if schema_migrations_exists(cur):
                    record_migration(
                        cur,
                        migration_id,
                        name,
                        checksum,
                        "failed",
                        message,
                    )
            conn.commit()
            errors.append(f"{migration_id} {name} failed: {message}")
            break

        with conn.cursor() as cur:
            record_migration(cur, migration_id, name, checksum, "applied")
        conn.commit()
        applied.append(f"{migration_id} {name}")

    return applied, errors


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
                    for table in CORE_TABLES:
                        cur.execute(f"SELECT count(*) AS count FROM {table}")
                        row = cur.fetchone()
                        print(f"  {table}: {row['count']}")
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


def find_unknown_relation_types(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, relation_type, source_type, source_id, target_type, target_id
        FROM relations
        WHERE relation_type <> ALL(%s)
        ORDER BY created_at, id
        """,
        (list(RELATION_TYPES),),
    )
    return list(cur.fetchall())


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
