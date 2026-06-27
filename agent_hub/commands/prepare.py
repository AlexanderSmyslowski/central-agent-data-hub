"""Task-specific read-only context pack command."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from agent_hub.commands.common import (
    exception_error,
    fetch_project,
    json_default,
    require_database_url,
    project_not_found,
)
from agent_hub.context_receipt import context_receipt_markdown, prepare_context_counts
from agent_hub.db import connect
from agent_hub.gaps import (
    DEFAULT_STALE_AFTER_DAYS,
    collect_prepare_gaps,
    fetch_pending_draft_counts,
    known_gaps_markdown,
)
from agent_hub.quality import fetch_project_counts
from agent_hub.relations import fetch_project_relations
from agent_hub.rendering import markdown_list
from agent_hub.statuses import (
    DRAFT_STATUS,
    prepare_excluded_statuses,
    unresolved_open_questions,
)


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

TASK_SELECTION_MODE = "deterministic_full_text"
TASK_SELECTION_NOTE = (
    "Facts, decisions, and reports are ranked by PostgreSQL full-text task "
    "matches, then filled with deterministic recent context. Active risks and "
    "open questions stay on a safety floor and are not filtered out by task text."
)
TASK_SELECTION_TIE_BREAKING = "task_score DESC, created_at DESC, id DESC"
DRAFT_PREPARE_REASON = "included as unconfirmed draft"


PREPARE_SPECS = {
    "facts": {
        "table": "facts",
        "columns": "id, statement, source, confidence",
        "search": "concat_ws(' ', statement, source)",
        "excluded_statuses": prepare_excluded_statuses("fact"),
    },
    "decisions": {
        "table": "decisions",
        "columns": "id, decision, rationale, consequences",
        "search": "concat_ws(' ', decision, rationale, consequences)",
        "excluded_statuses": prepare_excluded_statuses("decision"),
    },
    "risks": {
        "table": "risks",
        "columns": "id, title, severity, impact, mitigation",
        "search": "concat_ws(' ', title, severity, impact, mitigation)",
        "excluded_statuses": prepare_excluded_statuses("risk"),
    },
    "open_questions": {
        "table": "open_questions",
        "columns": "id, question, answer",
        "search": "concat_ws(' ', question, answer)",
        "excluded_statuses": prepare_excluded_statuses("open_question"),
    },
    "reports": {
        "table": "reports",
        "columns": "id, title, report_type, summary",
        "search": "concat_ws(' ', title, report_type, summary, body)",
        "excluded_statuses": prepare_excluded_statuses("report"),
    },
}


def row_id(row: dict[str, object]) -> str:
    return str(row["id"])


def annotate_prepare_row(
    row: dict[str, object],
    *,
    reason: str,
    task_score: object | None = None,
) -> dict[str, object]:
    annotated = dict(row)
    annotated["prepare_reason"] = (
        DRAFT_PREPARE_REASON if row.get("status") == DRAFT_STATUS else reason
    )
    if task_score is not None:
        annotated["task_score"] = float(task_score)
    return annotated


def review_status(row: dict[str, object]) -> str:
    return DRAFT_STATUS if row.get("status") == DRAFT_STATUS else "verified"


def non_draft_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if review_status(row) != DRAFT_STATUS]


def draft_rows_by_type(
    compiled: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    return {
        "facts": [row for row in compiled["facts"] if review_status(row) == DRAFT_STATUS],
        "decisions": [
            row for row in compiled["decisions"] if review_status(row) == DRAFT_STATUS
        ],
        "risks": [row for row in compiled["risks"] if review_status(row) == DRAFT_STATUS],
        "open_questions": [
            row
            for row in compiled["open_questions"]
            if review_status(row) == DRAFT_STATUS
        ],
        "reports": [
            row for row in compiled["reports"] if review_status(row) == DRAFT_STATUS
        ],
    }


def merge_prepare_rows(
    primary: list[dict[str, object]],
    fallback: list[dict[str, object]],
    *,
    limit: int,
    primary_reason: str,
    fallback_reason: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in primary:
        rows.append(
            annotate_prepare_row(
                row,
                reason=primary_reason,
                task_score=row.get("task_score"),
            )
        )
        seen.add(row_id(row))
        if len(rows) >= limit:
            return rows
    for row in fallback:
        if row_id(row) in seen:
            continue
        rows.append(annotate_prepare_row(row, reason=fallback_reason))
        if len(rows) >= limit:
            return rows
    return rows


def fetch_recent_prepare_rows(
    cur,
    *,
    project_id: object,
    key: str,
    limit: int,
) -> list[dict[str, object]]:
    spec = PREPARE_SPECS[key]
    placeholders = ", ".join(["%s"] * len(spec["excluded_statuses"]))
    cur.execute(
        f"""
        SELECT {spec['columns']}, status, updated_at
        FROM {spec['table']}
        WHERE project_id = %s
          AND status NOT IN ({placeholders})
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (project_id, *spec["excluded_statuses"], limit),
    )
    return list(cur.fetchall())


def fetch_task_match_prepare_rows(
    cur,
    *,
    project_id: object,
    key: str,
    task: str,
    limit: int,
) -> list[dict[str, object]]:
    spec = PREPARE_SPECS[key]
    placeholders = ", ".join(["%s"] * len(spec["excluded_statuses"]))
    cur.execute(
        f"""
        WITH task_query AS (
          SELECT plainto_tsquery('simple', %s) AS query
        )
        SELECT
          {spec['columns']},
          status,
          updated_at,
          ts_rank_cd(to_tsvector('simple', {spec['search']}), task_query.query)
            AS task_score
        FROM {spec['table']}, task_query
        WHERE project_id = %s
          AND status NOT IN ({placeholders})
          AND to_tsvector('simple', {spec['search']}) @@ task_query.query
        ORDER BY task_score DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (task, project_id, *spec["excluded_statuses"], limit),
    )
    return list(cur.fetchall())


def select_ranked_prepare_rows(
    cur,
    *,
    project_id: object,
    key: str,
    task: str,
    limit: int,
) -> list[dict[str, object]]:
    task_matches = fetch_task_match_prepare_rows(
        cur,
        project_id=project_id,
        key=key,
        task=task,
        limit=limit,
    )
    recent_rows = fetch_recent_prepare_rows(
        cur,
        project_id=project_id,
        key=key,
        limit=limit,
    )
    fallback_reason = (
        "included as recent fallback after task-ranked context"
        if task_matches
        else "included as recent fallback because task text matched no reviewed items in this type"
    )
    return merge_prepare_rows(
        task_matches,
        recent_rows,
        limit=limit,
        primary_reason="included by deterministic task text match",
        fallback_reason=fallback_reason,
    )


def select_safety_floor_rows(
    cur,
    *,
    project_id: object,
    key: str,
    task: str,
    limit: int,
) -> list[dict[str, object]]:
    recent_rows = fetch_recent_prepare_rows(
        cur,
        project_id=project_id,
        key=key,
        limit=limit,
    )
    task_matches = fetch_task_match_prepare_rows(
        cur,
        project_id=project_id,
        key=key,
        task=task,
        limit=limit,
    )
    scores_by_id = {row_id(row): row.get("task_score") for row in task_matches}
    reason_by_key = {
        "risks": "included by safety floor for active risks",
        "open_questions": "included by safety floor for unresolved open questions",
    }
    rows = []
    for row in recent_rows:
        score = scores_by_id.get(row_id(row))
        reason = reason_by_key[key]
        if score is not None:
            reason = f"{reason}; also matched task text"
        rows.append(annotate_prepare_row(row, reason=reason, task_score=score))
    return rows


def fetch_prepare_payload(
    cur,
    project: dict[str, object],
    task: str,
    limit: int,
) -> dict[str, object]:
    project_id = project["id"]
    report_limit = max(3, min(limit, 5))
    relations = fetch_project_relations(cur, project_id, limit=limit)
    for relation in relations:
        relation["prepare_reason"] = "included as recent project relation context"
    return {
        "project": project,
        "facts": select_ranked_prepare_rows(
            cur, project_id=project_id, key="facts", task=task, limit=limit
        ),
        "decisions": select_ranked_prepare_rows(
            cur, project_id=project_id, key="decisions", task=task, limit=limit
        ),
        "risks": select_safety_floor_rows(
            cur, project_id=project_id, key="risks", task=task, limit=limit
        ),
        "open_questions": select_safety_floor_rows(
            cur, project_id=project_id, key="open_questions", task=task, limit=limit
        ),
        "reports": select_ranked_prepare_rows(
            cur, project_id=project_id, key="reports", task=task, limit=report_limit
        ),
        "relations": relations,
        "active_counts": fetch_project_counts(cur, project_id),
        "pending_draft_counts": fetch_pending_draft_counts(cur, project_id),
    }


def build_context_trail(payload: dict[str, object]) -> dict[str, object]:
    included_counts = {}
    sources = []
    for payload_key, count_key, item_type in TRAIL_SOURCES:
        rows = list(payload[payload_key])
        draft_key = count_key
        if count_key == "open questions":
            draft_key = "open_questions"
        drafts = payload.get("drafts_pending_review", {})
        if isinstance(drafts, dict) and draft_key in drafts:
            rows.extend(drafts[draft_key])
        included_counts[count_key] = len(rows)
        for row in rows:
            sources.append(
                {
                    "type": item_type,
                    "id": row["id"],
                    "status": row.get("status", "not available"),
                    "review_status": review_status(row)
                    if item_type != "relation"
                    else "not applicable",
                    "reason": row.get(
                        "prepare_reason",
                        "included by deterministic prepare selection",
                    ),
                    "task_score": row.get("task_score"),
                }
            )

    trail = {
        "included_counts": included_counts,
        "sources": sources,
        "excluded": {
            "note": "not tracked by current prepare implementation",
        },
        "task_selection": {
            "mode": TASK_SELECTION_MODE,
            "note": TASK_SELECTION_NOTE,
            "tie_breaking": TASK_SELECTION_TIE_BREAKING,
        },
    }
    gaps = payload.get("gaps")
    if isinstance(gaps, dict):
        trail["gap_summary"] = gaps.get("summary", {})
    return trail


def build_prepare_payload(
    *,
    project: dict[str, object],
    task: str,
    compiled: dict[str, object],
    now: datetime | None = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> dict[str, object]:
    drafts = draft_rows_by_type(compiled)
    current_time = now or datetime.now(timezone.utc)
    gaps = collect_prepare_gaps(
        {**compiled, "drafts_pending_review": drafts},
        task,
        current_time,
        stale_after_days=stale_after_days,
    )
    payload = {
        "context_pack_version": 1,
        "project": project,
        "task": task,
        "goal": task,
        "verified_project_state": non_draft_rows(compiled["facts"]),
        "relevant_decisions": non_draft_rows(compiled["decisions"]),
        "constraints": [
            "Use only reviewed, project-bound Hub memory as durable context.",
            "Treat Signal Inbox and triage output as suggestions until reviewed.",
            "Do not store secrets, credentials, private customer data, raw invoices, raw logs, or deployment secrets.",
            "PostgreSQL remains the reviewed source of truth; Hub View and Markdown exports are review surfaces.",
        ],
        "risks": non_draft_rows(compiled["risks"]),
        "open_questions": unresolved_open_questions(non_draft_rows(compiled["open_questions"])),
        "allowed_actions": ALLOWED_ACTIONS,
        "requires_human_approval": HUMAN_APPROVAL_ACTIONS,
        "suggested_checks": SUGGESTED_CHECKS,
        "reports": non_draft_rows(compiled["reports"]),
        "drafts_pending_review": drafts,
        "gaps": gaps,
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
    gap_summary = trail.get("gap_summary", {})

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
                    f"  review_status: {source['review_status']}",
                    f"  reason: {source['reason']}",
                ]
            )
            if source.get("task_score") is not None:
                lines.append(f"  task_score: {source['task_score']:.6f}")
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
            f"- tie_breaking: {task_selection['tie_breaking']}",
        ]
    )
    if isinstance(gap_summary, dict):
        thresholds = gap_summary.get("thresholds", {})
        stale_after_days = (
            thresholds.get("stale_after_days")
            if isinstance(thresholds, dict)
            else None
        )
        lines.extend(
            [
                "",
                "Gap Summary:",
                f"- stale: {gap_summary.get('stale', 0)}",
                f"- unanswered: {gap_summary.get('unanswered', 0)}",
                f"- empty_types: {gap_summary.get('empty_types', 0)}",
                f"- blind_spots: {gap_summary.get('blind_spots', 0)}",
                f"- pending_drafts: {gap_summary.get('pending_drafts', 0)}",
            ]
        )
        if stale_after_days is not None:
            lines.append(f"- stale_after_days: {stale_after_days}")
    return "\n".join(lines)


def draft_section_markdown(drafts: dict[str, list[dict[str, object]]]) -> str:
    sections = [
        ("Facts", drafts.get("facts", []), "statement", ("source", "confidence")),
        ("Decisions", drafts.get("decisions", []), "decision", ("rationale",)),
        ("Risks", drafts.get("risks", []), "title", ("severity", "impact", "mitigation")),
        ("Open Questions", drafts.get("open_questions", []), "question", ("answer",)),
        ("Reports", drafts.get("reports", []), "title", ("report_type", "summary")),
    ]
    if not any(rows for _title, rows, _primary, _extra in sections):
        return "- none"
    lines: list[str] = []
    for title, rows, primary, extras in sections:
        if not rows:
            continue
        lines.append(f"### {title}")
        lines.append(markdown_list(rows, primary, extras))
        lines.append("")
    return "\n".join(lines).rstrip()


def prepare_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    return "\n".join(
        [
            "# Agent Context Pack",
            "",
            f"- project: {project['slug']}",
            f"- context_pack_version: {payload['context_pack_version']}",
            f"- task: {payload['task']}",
            "",
            context_receipt_markdown(
                project_slug=str(project["slug"]),
                task=str(payload["task"]),
                counts=prepare_context_counts(payload),
            ),
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
            "## Drafts Pending Review",
            draft_section_markdown(payload["drafts_pending_review"]),
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
            "",
            "## Known Gaps",
            known_gaps_markdown(payload["gaps"]),
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
                compiled = fetch_prepare_payload(cur, project, args.task, args.limit)
    except Exception as exc:
        return exception_error(exc)

    payload = build_prepare_payload(
        project=project,
        task=args.task,
        compiled=compiled,
        stale_after_days=args.stale_after_days,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(prepare_markdown(payload))
    return 0
