"""Command line interface for Central Agent Data Hub."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agent_hub.db import connect
from agent_hub.export_obsidian import export_all

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
        WHERE status <> 'resolved'
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

    for name in ("init", "import"):
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
