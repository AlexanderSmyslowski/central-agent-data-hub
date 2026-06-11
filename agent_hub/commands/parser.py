"""Argument parser registration for the Agent Data Hub CLI."""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Callable
from typing import Any

from agent_hub.commands.common import confidence_value, positive_int
from agent_hub.commands.graph import run_relate, run_relations
from agent_hub.commands.briefs import run_brief
from agent_hub.commands.inbox import run_inbox
from agent_hub.commands.mcp import run_mcp_serve
from agent_hub.commands.prepare import run_prepare
from agent_hub.commands.quality_views import run_actions, run_quality, run_receipt
from agent_hub.commands.search import run_context, run_search
from agent_hub.commands.summaries import (
    run_compile,
    run_daily,
    run_handoff,
    run_review,
)
from agent_hub.commands.system import (
    run_check,
    run_export,
    run_migrate,
    run_projects,
    run_setup,
    run_status,
)
from agent_hub.commands.write import (
    run_answer_question,
    run_import,
    run_remember,
    run_sync,
    run_update_decision,
)
from agent_hub.memory import REMEMBER_TYPES
from agent_hub.receipts import RECEIPT_TYPES
from agent_hub.relations import RELATION_TARGETS, RELATION_TYPES


def not_implemented(args: argparse.Namespace) -> int:
    print(f"Command '{args.command}' is not implemented yet.", file=sys.stderr)
    return 2


def add_command(
    subparsers: Any,
    name: str,
    help_text: str,
    handler: Callable[[argparse.Namespace], int],
) -> argparse.ArgumentParser:
    command = subparsers.add_parser(name, help=help_text)
    command.set_defaults(func=handler)
    return command


def add_project_argument(
    parser: argparse.ArgumentParser,
    help_text: str = "Project slug.",
) -> None:
    parser.add_argument("--project", required=True, help=help_text)


def add_format_argument(
    parser: argparse.ArgumentParser,
    choices: tuple[str, ...],
    default: str,
) -> None:
    parser.add_argument(
        "--format",
        choices=choices,
        default=default,
        help="Output format.",
    )


def add_limit_argument(
    parser: argparse.ArgumentParser,
    default: int,
    help_text: str,
    *,
    arg_type=int,
) -> None:
    parser.add_argument(
        "--limit",
        type=arg_type,
        default=default,
        help=help_text,
    )


def uuid_value(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a valid UUID") from exc


def add_since_argument(
    parser: argparse.ArgumentParser,
    default: str,
    help_text: str | None = None,
) -> None:
    parser.add_argument(
        "--since",
        default=default,
        help=help_text
        or f"Duration like 24h, 7d, 2w or ISO date. Default: {default}.",
    )


def add_metadata_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Additional metadata in key=value form; repeatable.",
    )


def add_markdown_source_arguments(parser: argparse.ArgumentParser, verb: str) -> None:
    parser.add_argument(
        "--path",
        required=True,
        help=f"Markdown file or directory to {verb}.",
    )
    parser.add_argument(
        "--allowlist",
        default="import_allowlist.yml",
        help="YAML allowlist path. Defaults to import_allowlist.yml.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hub",
        description="Agent Data Hub command line tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_command(
        subparsers,
        "export",
        "Export database rows to Obsidian Markdown files.",
        run_export,
    )
    add_command(
        subparsers,
        "status",
        "Show a quick database and export-directory diagnostic.",
        run_status,
    )
    add_command(
        subparsers,
        "check",
        "Run consistency checks for export and review readiness.",
        run_check,
    )
    setup_parser = subparsers.add_parser(
        "setup",
        help="Run the guided local setup assistant from this repository checkout.",
    )
    setup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the setup plan without writing files or creating folders.",
    )
    setup_parser.add_argument(
        "--defaults",
        action="store_true",
        help="Use the assistant's recommended defaults without prompts.",
    )
    setup_parser.add_argument(
        "setup_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed through to scripts/setup_assistant.sh after --.",
    )
    setup_parser.set_defaults(func=run_setup)

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
    add_project_argument(
        brief_parser,
        "Project slug to summarize, for example commcats-de.",
    )
    add_limit_argument(brief_parser, 8, "Maximum rows per memory section.")
    add_format_argument(brief_parser, ("markdown", "json"), "markdown")
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
    add_project_argument(daily_parser)
    add_since_argument(daily_parser, "24h")
    add_limit_argument(daily_parser, 8, "Maximum rows per daily section.")
    add_format_argument(daily_parser, ("text", "json", "markdown"), "text")
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
    add_project_argument(handoff_parser)
    add_since_argument(handoff_parser, "7d")
    add_limit_argument(handoff_parser, 8, "Maximum rows per handoff section.")
    add_format_argument(handoff_parser, ("text", "json", "markdown"), "text")
    handoff_parser.set_defaults(func=run_handoff)

    review_parser = subparsers.add_parser(
        "review",
        help="Review decisions, risks, open questions, and relations.",
    )
    add_project_argument(review_parser)
    add_limit_argument(review_parser, 12, "Maximum rows per review section.")
    add_format_argument(review_parser, ("text", "json", "markdown"), "text")
    review_parser.set_defaults(func=run_review)

    search_parser = subparsers.add_parser(
        "search",
        help="Search project memory with simple PostgreSQL text matching.",
    )
    add_project_argument(search_parser)
    search_parser.add_argument("--query", required=True, help="Text to search for.")
    search_parser.add_argument(
        "--type",
        dest="memory_type",
        choices=("all", "fact", "decision", "risk", "open_question", "report"),
        default="all",
        help="Memory type filter.",
    )
    search_parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Include unreviewed draft memory in search results.",
    )
    search_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived and inactive memory statuses in search results.",
    )
    add_limit_argument(search_parser, 10, "Maximum search results.")
    add_format_argument(search_parser, ("text", "json"), "text")
    search_parser.set_defaults(func=run_search)

    context_parser = subparsers.add_parser(
        "context",
        help="Build a compact project context pack from brief, search, and relations.",
    )
    add_project_argument(context_parser)
    context_parser.add_argument("--query", required=True, help="Focus query.")
    add_since_argument(context_parser, "30d", "Recent activity window. Default: 30d.")
    add_limit_argument(context_parser, 8, "Maximum rows per context section.")
    add_format_argument(context_parser, ("markdown", "json"), "markdown")
    context_parser.set_defaults(func=run_context)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Build a task-specific read-only agent context pack.",
    )
    add_project_argument(prepare_parser)
    prepare_parser.add_argument("--task", required=True, help="Concrete task focus.")
    add_limit_argument(prepare_parser, 8, "Maximum rows per prepare section.")
    prepare_parser.add_argument(
        "--stale-after-days",
        type=positive_int,
        default=42,
        help="Label reviewed items as stale only when older than this many days.",
    )
    add_format_argument(prepare_parser, ("markdown", "json"), "markdown")
    prepare_parser.set_defaults(func=run_prepare)

    mcp_parser = subparsers.add_parser(
        "mcp-serve",
        help="Serve read-only Agent Data Hub MCP tools over stdio.",
    )
    mcp_parser.set_defaults(func=run_mcp_serve)

    compile_parser = subparsers.add_parser(
        "compile",
        help="Build a compact token-efficient project memory for agent starts.",
    )
    add_project_argument(compile_parser)
    add_limit_argument(
        compile_parser,
        5,
        "Maximum rows per compiled section.",
        arg_type=positive_int,
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
    add_format_argument(compile_parser, ("markdown", "json"), "markdown")
    compile_parser.set_defaults(func=run_compile)

    quality_parser = subparsers.add_parser(
        "quality",
        help="Show project memory quality, gaps, and relation coverage.",
    )
    add_project_argument(quality_parser)
    add_format_argument(quality_parser, ("text", "json", "markdown"), "text")
    quality_parser.set_defaults(func=run_quality)

    receipt_parser = subparsers.add_parser(
        "receipt",
        help="Verify recent project memory writes and Obsidian export files.",
    )
    add_project_argument(receipt_parser)
    add_since_argument(receipt_parser, "24h")
    receipt_parser.add_argument(
        "--type",
        dest="memory_type",
        choices=RECEIPT_TYPES,
        default="all",
        help="Memory type to verify.",
    )
    add_limit_argument(receipt_parser, 12, "Maximum receipt rows.")
    add_format_argument(receipt_parser, ("text", "json", "markdown"), "text")
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
    add_project_argument(actions_parser)
    add_since_argument(actions_parser, "7d")
    add_limit_argument(
        actions_parser,
        12,
        "Maximum agent action rows.",
        arg_type=positive_int,
    )
    add_format_argument(actions_parser, ("text", "json", "markdown"), "text")
    actions_parser.set_defaults(func=run_actions)

    inbox_parser = subparsers.add_parser(
        "inbox",
        help="List or review draft memory candidates.",
    )
    inbox_parser.add_argument(
        "--project",
        help="Optional project slug to inspect.",
    )
    add_limit_argument(
        inbox_parser,
        20,
        "Maximum draft cards to list.",
        arg_type=positive_int,
    )
    inbox_parser.add_argument(
        "--agent",
        default="codex",
        help="Agent slug to attribute accept/reject actions to.",
    )
    inbox_parser.add_argument(
        "--agent-name",
        default="Codex",
        help="Agent display name to attribute accept/reject actions to.",
    )
    inbox_parser.add_argument(
        "--reviewer",
        help="Reviewer handle for accept/reject. Falls back to AGENT_HUB_REVIEWER.",
    )
    inbox_parser.add_argument(
        "--for",
        dest="for_reviewer",
        help="Show drafts assigned to this reviewer handle only.",
    )
    review_group = inbox_parser.add_mutually_exclusive_group()
    review_group.add_argument(
        "--accept",
        action="append",
        type=uuid_value,
        default=[],
        help="Promote a draft by UUID; repeat for batch review.",
    )
    review_group.add_argument(
        "--reject",
        action="append",
        type=uuid_value,
        default=[],
        help="Discard a draft by UUID; repeat for batch review.",
    )
    add_format_argument(inbox_parser, ("text", "json"), "text")
    inbox_parser.set_defaults(func=run_inbox)

    relations_parser = subparsers.add_parser(
        "relations",
        help="List curated relations for a project graph.",
    )
    add_project_argument(relations_parser, "Project slug to inspect.")
    relations_parser.add_argument(
        "--object-type",
        choices=tuple(RELATION_TARGETS),
        help="Limit to relations touching this object type.",
    )
    relations_parser.add_argument(
        "--object-id",
        help="Limit to relations touching this object id.",
    )
    add_format_argument(relations_parser, ("text", "json"), "text")
    relations_parser.set_defaults(func=run_relations)

    relate_parser = subparsers.add_parser(
        "relate",
        help="Create or update a curated relation between two Hub objects.",
    )
    add_project_argument(relate_parser, "Project slug that owns the relation context.")
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
    add_metadata_argument(relate_parser)
    add_format_argument(relate_parser, ("text", "json"), "text")
    relate_parser.set_defaults(func=run_relate)

    remember_parser = subparsers.add_parser(
        "remember",
        help="Submit a routed fact, decision, question, risk, or report candidate.",
    )
    add_project_argument(
        remember_parser,
        "Project slug, for example the-one-catering.",
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
        help="Requested status; unreviewed candidates may still be stored as draft.",
    )
    remember_parser.add_argument(
        "--source",
        help="Source path, URL, or short provenance note.",
    )
    remember_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the deterministic review route without writing.",
    )
    add_metadata_argument(remember_parser)
    add_format_argument(remember_parser, ("text", "json"), "text")
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

    answer_question_parser = subparsers.add_parser(
        "answer-question",
        help="Mark an existing open question as answered or closed.",
    )
    add_project_argument(
        answer_question_parser,
        "Project slug that owns the open question.",
    )
    answer_question_parser.add_argument(
        "--agent",
        default="codex",
        help="Agent slug to attribute the update to.",
    )
    answer_question_parser.add_argument(
        "--agent-name",
        default="Codex",
        help="Agent display name to attribute the update to.",
    )
    answer_question_parser.add_argument(
        "--question-id",
        required=True,
        type=uuid_value,
        help="Existing open question UUID to update.",
    )
    answer_question_parser.add_argument(
        "--answer",
        required=True,
        help="Reviewed answer or closure note.",
    )
    answer_question_parser.add_argument(
        "--status",
        choices=("answered", "closed"),
        default="answered",
        help="Final question status. Default: answered.",
    )
    answer_question_parser.add_argument(
        "--source",
        help="Source path, URL, or short provenance note.",
    )
    add_metadata_argument(answer_question_parser)
    add_format_argument(answer_question_parser, ("text", "json"), "text")
    answer_question_parser.set_defaults(func=run_answer_question)

    update_decision_parser = subparsers.add_parser(
        "update-decision",
        help="Update an existing decision with reviewed rationale, consequences, or status.",
    )
    add_project_argument(
        update_decision_parser,
        "Project slug that owns the decision.",
    )
    update_decision_parser.add_argument(
        "--agent",
        default="codex",
        help="Agent slug to attribute the update to.",
    )
    update_decision_parser.add_argument(
        "--agent-name",
        default="Codex",
        help="Agent display name to attribute the update to.",
    )
    update_decision_parser.add_argument(
        "--decision-id",
        required=True,
        type=uuid_value,
        help="Existing decision UUID to update.",
    )
    update_decision_parser.add_argument(
        "--rationale",
        help="Reviewed rationale to store on the decision.",
    )
    update_decision_parser.add_argument(
        "--consequences",
        help="Reviewed consequences or operational effect.",
    )
    update_decision_parser.add_argument(
        "--status",
        choices=("proposed", "accepted", "rejected", "superseded", "archived"),
        help="Decision status override.",
    )
    update_decision_parser.add_argument(
        "--source",
        help="Source path, URL, or short provenance note.",
    )
    add_metadata_argument(update_decision_parser)
    add_format_argument(update_decision_parser, ("text", "json"), "text")
    update_decision_parser.set_defaults(func=run_update_decision)

    import_parser = subparsers.add_parser(
        "import",
        help="Import allowlisted Obsidian Markdown notes into Postgres.",
    )
    add_markdown_source_arguments(import_parser, "import")
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
    add_format_argument(import_parser, ("text", "json"), "text")
    import_parser.set_defaults(func=run_import)

    sync_parser = subparsers.add_parser(
        "sync",
        help="Plan or apply allowlisted Obsidian-to-Postgres sync.",
    )
    add_markdown_source_arguments(sync_parser, "sync")
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
    add_format_argument(sync_parser, ("text", "json"), "text")
    sync_parser.set_defaults(func=run_sync)

    for name in ("init",):
        placeholder = subparsers.add_parser(
            name,
            help="Not implemented yet.",
        )
        placeholder.set_defaults(func=not_implemented)

    return parser
