"""Task-specific read-only context pack command."""

from __future__ import annotations

import argparse
import json

from agent_hub.commands.common import (
    exception_error,
    fetch_project,
    json_default,
    require_database_url,
    project_not_found,
)
from agent_hub.commands.summaries import fetch_compiled_payload
from agent_hub.db import connect
from agent_hub.rendering import markdown_list
from agent_hub.statuses import unresolved_open_questions


ALLOWED_ACTIONS = [
    "read reviewed project context",
    "run local checks and tests",
    "inspect code, docs, scripts, and public demo paths",
    "make scoped docs or code edits inside the selected project",
    "use dry-run writeback paths for reviewed memory candidates",
]

HUMAN_APPROVAL_ACTIONS = [
    "deployment or production changes",
    "deleting data, backups, repositories, or live files",
    "external publishing",
    "using credentials or protected hosting access",
    "handling private customer data, raw invoices, secrets, tokens, or private logs",
    "schema or policy changes that expand write authority",
]

SUGGESTED_CHECKS = [
    "git diff --check",
    "bash -n scripts/*.sh",
    ".venv/bin/python -m compileall agent_hub",
    ".venv/bin/python -m pytest -q",
    ".venv/bin/python -m agent_hub.cli status",
    ".venv/bin/python -m agent_hub.cli check",
]

TRAIL_SOURCES = (
    ("verified_project_state", "facts", "fact"),
    ("relevant_decisions", "decisions", "decision"),
    ("risks", "risks", "risk"),
    ("open_questions", "open_questions", "open_question"),
    ("reports", "reports", "report"),
    ("relations", "relations", "relation"),
)


def build_context_trail(payload: dict[str, object]) -> dict[str, object]:
    included_counts = {}
    sources = []
    for payload_key, count_key, item_type in TRAIL_SOURCES:
        rows = payload[payload_key]
        included_counts[count_key] = len(rows)
        for row in rows:
            sources.append(
                {
                    "type": item_type,
                    "id": row["id"],
                    "status": row.get("status", "not available"),
                    "reason": "included by current deterministic prepare selection",
                }
            )

    return {
        "included_counts": included_counts,
        "sources": sources,
        "excluded": {
            "note": "not tracked by current prepare implementation",
        },
        "task_selection": {
            "mode": "metadata_only",
            "note": (
                "--task is used as the task goal only; it does not filter or rank "
                "reviewed context yet."
            ),
        },
    }


def build_prepare_payload(
    *,
    project: dict[str, object],
    task: str,
    compiled: dict[str, object],
) -> dict[str, object]:
    payload = {
        "project": project,
        "task": task,
        "goal": task,
        "verified_project_state": compiled["facts"],
        "relevant_decisions": compiled["decisions"],
        "constraints": [
            "Use only reviewed, project-bound Hub memory as durable context.",
            "Treat Signal Inbox and triage output as suggestions until reviewed.",
            "Do not store secrets, credentials, private customer data, raw invoices, raw logs, or deployment secrets.",
            "PostgreSQL remains the reviewed source of truth; Hub View and Markdown exports are review surfaces.",
        ],
        "risks": compiled["risks"],
        "open_questions": unresolved_open_questions(compiled["open_questions"]),
        "allowed_actions": ALLOWED_ACTIONS,
        "requires_human_approval": HUMAN_APPROVAL_ACTIONS,
        "suggested_checks": SUGGESTED_CHECKS,
        "reports": compiled["reports"],
        "relations": compiled["relations"],
    }
    payload["context_trail"] = build_context_trail(payload)
    return payload


def simple_list(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def context_trail_markdown(trail: dict[str, object]) -> str:
    counts = trail["included_counts"]
    sources = trail["sources"]
    excluded = trail["excluded"]
    task_selection = trail["task_selection"]

    lines = [
        "Included:",
        f"- facts: {counts['facts']}",
        f"- decisions: {counts['decisions']}",
        f"- risks: {counts['risks']}",
        f"- open questions: {counts['open_questions']}",
        f"- reports: {counts['reports']}",
        f"- relations: {counts['relations']}",
        "",
        "Sources:",
    ]
    if sources:
        for source in sources:
            lines.extend(
                [
                    f"- {source['type']}:{source['id']}",
                    f"  status: {source['status']}",
                    f"  reason: {source['reason']}",
                ]
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "Excluded:",
            f"- {excluded['note']}",
            "",
            "Task Selection:",
            f"- mode: {task_selection['mode']}",
            f"- note: {task_selection['note']}",
        ]
    )
    return "\n".join(lines)


def prepare_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    return "\n".join(
        [
            "# Agent Context Pack",
            "",
            f"- project: {project['slug']}",
            f"- task: {payload['task']}",
            "",
            "## Goal",
            str(payload["goal"]),
            "",
            "## Verified Project State",
            markdown_list(payload["verified_project_state"], "statement", ("source", "confidence")),
            "",
            "## Relevant Decisions",
            markdown_list(payload["relevant_decisions"], "decision", ("rationale",)),
            "",
            "## Constraints",
            simple_list(payload["constraints"]),
            "",
            "## Risks",
            markdown_list(payload["risks"], "title", ("severity", "impact", "mitigation")),
            "",
            "## Open Questions",
            markdown_list(payload["open_questions"], "question", ("answer",)),
            "",
            "## Allowed Actions",
            simple_list(payload["allowed_actions"]),
            "",
            "## Requires Human Approval",
            simple_list(payload["requires_human_approval"]),
            "",
            "## Suggested Checks",
            simple_list(payload["suggested_checks"]),
            "",
            "## Context Trail",
            context_trail_markdown(payload["context_trail"]),
        ]
    )


def run_prepare(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                compiled = fetch_compiled_payload(cur, project, args.limit)
    except Exception as exc:
        return exception_error(exc)

    payload = build_prepare_payload(
        project=project,
        task=args.task,
        compiled=compiled,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(prepare_markdown(payload))
    return 0
