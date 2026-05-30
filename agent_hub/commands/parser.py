"""Argument parser registration for the Agent Data Hub CLI."""

from __future__ import annotations

import argparse
import sys

from agent_hub.commands.common import confidence_value, positive_int
from agent_hub.commands.graph import run_relate, run_relations
from agent_hub.commands.read import (
    run_actions,
    run_brief,
    run_compile,
    run_context,
    run_daily,
    run_handoff,
    run_quality,
    run_receipt,
    run_review,
    run_search,
)
from agent_hub.commands.system import (
    run_check,
    run_export,
    run_migrate,
    run_projects,
    run_status,
)
from agent_hub.commands.write import run_import, run_remember, run_sync
from agent_hub.memory import REMEMBER_TYPES
from agent_hub.receipts import RECEIPT_TYPES
from agent_hub.relations import RELATION_TARGETS, RELATION_TYPES


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

    actions_parser = subparsers.add_parser(
        "actions",
        help="List recent agent audit actions for a project.",
    )
    actions_parser.add_argument("--project", required=True, help="Project slug.")
    actions_parser.add_argument(
        "--since",
        default="7d",
        help="Duration like 24h, 7d, 2w or ISO date. Default: 7d.",
    )
    actions_parser.add_argument(
        "--limit",
        type=positive_int,
        default=12,
        help="Maximum agent action rows.",
    )
    actions_parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    actions_parser.set_defaults(func=run_actions)

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
