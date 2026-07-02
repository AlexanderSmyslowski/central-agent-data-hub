"""Visible context receipts for agent-facing Hub handoffs."""

from __future__ import annotations

import argparse

from agent_hub.commands.common import fetch_project, project_not_found, require_database_url
from agent_hub.commands.summaries import fetch_compiled_payload
from agent_hub.db import connect


INFLUENCE_LINES = (
    "Reviewed decisions become task constraints for the agent.",
    "Reviewed facts may be used as project assumptions.",
    "Active risks and open questions stay visible instead of being guessed away.",
    "Drafts stay labelled as unconfirmed until a human reviews them.",
)


def context_counts(payload: dict[str, object]) -> dict[str, int]:
    counts = payload.get("counts") or {}
    return {
        "facts": int(counts.get("facts", 0)),
        "decisions": int(counts.get("decisions", 0)),
        "risks": int(counts.get("risks", 0)),
        "open_questions": int(counts.get("open_questions", 0)),
        "reports": int(counts.get("reports", 0)),
    }


def prepare_context_counts(payload: dict[str, object]) -> dict[str, int]:
    return {
        "facts": len(payload.get("verified_project_state") or []),
        "decisions": len(payload.get("relevant_decisions") or []),
        "risks": len(payload.get("risks") or []),
        "open_questions": len(payload.get("open_questions") or []),
        "reports": len(payload.get("reports") or []),
    }


def count_line(counts: dict[str, int]) -> str:
    return (
        f"{counts['facts']} facts · "
        f"{counts['decisions']} decisions · "
        f"{counts['risks']} risks · "
        f"{counts['open_questions']} open questions · "
        f"{counts['reports']} reports"
    )


def context_receipt_markdown(
    *,
    project_slug: str,
    task: str | None,
    counts: dict[str, int],
    heading: str = "ADH Context Loaded",
) -> str:
    task_text = task.strip() if task and task.strip() else "no focus provided"
    return "\n".join(
        [
            f"## {heading}",
            "",
            f"- project: {project_slug}",
            f"- task: {task_text}",
            f"- using reviewed memory: {count_line(counts)}",
            "",
            "How this influences the work:",
            *[f"- {line}" for line in INFLUENCE_LINES],
        ]
    )


def context_receipt_text(
    *,
    project_slug: str,
    task: str | None,
    counts: dict[str, int],
) -> str:
    task_text = task.strip() if task and task.strip() else "no focus provided"
    return "\n".join(
        [
            "== ADH Context Loaded ==",
            f"Project: {project_slug}",
            f"Task: {task_text}",
            f"Using reviewed memory: {count_line(counts)}",
            "How this influences the work:",
            *[f"- {line}" for line in INFLUENCE_LINES],
        ]
    )


def build_compiled_context_receipt(
    cur,
    *,
    project_slug: str,
    task: str | None,
    limit: int,
) -> str | None:
    project = fetch_project(cur, project_slug)
    if not project:
        project_not_found(project_slug)
        return None
    payload = fetch_compiled_payload(cur, project, limit)
    return context_receipt_text(
        project_slug=str(project["slug"]),
        task=task,
        counts=context_counts(payload),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent_hub.context_receipt",
        description="Render an internal read-only ADH context receipt.",
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)

    if error_code := require_database_url():
        return error_code

    with connect() as conn:
        with conn.cursor() as cur:
            receipt = build_compiled_context_receipt(
                cur,
                project_slug=args.project,
                task=args.task,
                limit=args.limit,
            )
    if receipt is None:
        return 1
    print(receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
