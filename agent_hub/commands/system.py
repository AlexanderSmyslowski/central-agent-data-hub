"""System and diagnostic command handlers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from agent_hub.codex_projects import with_project_display_names
from agent_hub.commands.common import (
    concise_error,
    error,
    exception_error,
    json_default,
    require_database_url,
    truncate,
)
from agent_hub.db import connect
from agent_hub.export_obsidian import export_all
from agent_hub.migrations import apply_migrations, describe_migrations, print_migration_report
from agent_hub.quality import (
    fetch_latest_sync_event,
    fetch_low_confidence_facts,
    fetch_memory_quality_warnings,
    fetch_open_questions,
    fetch_table_counts,
    find_broken_relation_side,
    find_missing_project_references,
    find_unknown_relation_types,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


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
        return error(exc, 2)

    print(f"Export complete: wrote {len(written)} Markdown files.")
    for path in written:
        print(path)
    return 0


def run_migrate(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

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
        return exception_error(exc)

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


def run_setup(args: argparse.Namespace) -> int:
    script_path = REPO_ROOT / "scripts" / "setup_assistant.sh"
    if not script_path.is_file():
        print(
            f"Error: setup assistant script not found: {script_path}",
            file=sys.stderr,
        )
        print(
            "Run the repository checkout directly or use scripts/setup_assistant.sh.",
            file=sys.stderr,
        )
        return 2

    command = [str(script_path)]
    if getattr(args, "dry_run", False):
        command.append("--dry-run")
    if getattr(args, "defaults", False):
        command.append("--defaults")
    command.extend(getattr(args, "setup_args", []))
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        return exception_error(exc)
    return int(result.returncode)


def run_projects(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

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
                projects = with_project_display_names(list(cur.fetchall()))
    except Exception as exc:
        return exception_error(exc)

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
                print("Unresolved open questions:")
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
