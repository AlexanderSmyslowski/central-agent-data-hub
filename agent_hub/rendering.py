"""Markdown rendering helpers for Agent Data Hub CLI output."""

from __future__ import annotations

from agent_hub.statuses import (
    DRAFT_STATUS,
    format_draft_review_count,
    format_open_question_count,
    unresolved_open_questions,
)


def truncate(value: object, limit: int = 96) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def markdown_list(
    rows: list[dict[str, object]],
    primary_key: str,
    extra_keys: tuple[str, ...] = (),
) -> str:
    if not rows:
        return "- none"
    lines = []
    for row in rows:
        status = row.get("status", "unknown")
        lines.append(f"- [{status}] {truncate(row.get(primary_key) or '', 180)}")
        extras = []
        for key in extra_keys:
            value = row.get(key)
            if value not in (None, ""):
                extras.append(f"{key}: {truncate(value, 100)}")
        if extras:
            lines.append("  " + "; ".join(extras))
    return "\n".join(lines)


def relations_markdown(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "- none"
    lines = []
    for row in rows:
        source = f"{row['source_type']}:{row['source_id']}"
        target = f"{row['target_type']}:{row['target_id']}"
        lines.append(f"- {source} --{row['relation_type']}--> {target}")
        if row.get("source_summary") or row.get("target_summary"):
            lines.append(
                "  "
                f"{truncate(row.get('source_summary') or '', 80)} -> "
                f"{truncate(row.get('target_summary') or '', 80)}"
            )
    return "\n".join(lines)


def actions_markdown(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "- none"
    return "\n".join(
        f"- [{row['status']}] {row.get('agent_slug') or 'unknown'} "
        f"{row['action']} {row.get('object_type') or ''}:{row.get('object_id') or ''}"
        for row in rows
    )


def agent_actions_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    return "\n".join(
        [
            f"# Agent Actions: {project['name']}",
            "",
            f"- project: {project['slug']}",
            f"- since: {payload['since'].isoformat()}",
            "",
            "## Actions",
            actions_markdown(payload["agent_actions"]),
        ]
    )


def sync_events_markdown(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "- none"
    return "\n".join(
        f"- [{row['status']}] {row['direction']} {row['source']}"
        for row in rows
    )


def all_empty(*sections: list[dict[str, object]]) -> bool:
    return all(not section for section in sections)


def draft_review_line(payload: dict[str, object]) -> str:
    drafts = payload.get("drafts_awaiting_review")
    if isinstance(drafts, dict) and drafts.get("label"):
        return f"- {drafts['label']}"
    return f"- {format_draft_review_count(0)}"


def daily_open_questions(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    unresolved = unresolved_open_questions(rows)
    unresolved_ids = {row.get("id") for row in unresolved}
    drafts = [
        row
        for row in rows
        if row.get("status") == DRAFT_STATUS and row.get("id") not in unresolved_ids
    ]
    return [*drafts, *unresolved]


def recommended_steps_markdown(payload: dict[str, object]) -> str:
    steps = []
    for row in unresolved_open_questions(payload["open_questions"])[:3]:
        steps.append(f"- resolve open question: {truncate(row['question'], 120)}")
    for row in payload["risks"][:3]:
        mitigation = row.get("mitigation")
        if mitigation:
            steps.append(f"- mitigate risk: {truncate(mitigation, 120)}")
        else:
            steps.append(f"- review risk: {truncate(row['title'], 120)}")
    return "\n".join(steps) if steps else "- none"


def daily_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    since = payload["since"]
    if all_empty(
        payload["facts"],
        payload["decisions"],
        payload["risks"],
        daily_open_questions(payload["open_questions"]),
        payload["reports"],
        payload["relations"],
        payload["agent_actions"],
        payload["sync_events"],
    ):
        return "\n".join(
            [
                f"# Daily: {project['name']}",
                "",
                f"- project: {project['slug']}",
                f"- since: {since.isoformat()}",
                draft_review_line(payload),
                "",
                "## Activity Summary",
                "- No new reviewed facts, decisions, risks, open questions, reports, relations, agent actions, or sync events in this window.",
            ]
        )
    return "\n".join(
        [
            f"# Daily: {project['name']}",
            "",
            f"- project: {project['slug']}",
            f"- since: {since.isoformat()}",
            draft_review_line(payload),
            "",
            "## New Facts",
            markdown_list(payload["facts"], "statement", ("source", "confidence")),
            "",
            "## Decisions",
            markdown_list(payload["decisions"], "decision", ("rationale",)),
            "",
            "## Risks",
            markdown_list(payload["risks"], "title", ("severity", "impact", "mitigation")),
            "",
            "## Open Questions",
            markdown_list(
                daily_open_questions(payload["open_questions"]),
                "question",
                ("answer",),
            ),
            "",
            "## Reports",
            markdown_list(payload["reports"], "title", ("report_type", "summary")),
            "",
            "## Relations",
            relations_markdown(payload["relations"]),
            "",
            "## Agent Actions",
            actions_markdown(payload["agent_actions"]),
            "",
            "## Sync Events",
            sync_events_markdown(payload["sync_events"]),
        ]
    )


def handoff_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    since = payload["since"]
    unresolved_questions = unresolved_open_questions(payload["open_questions"])
    if all_empty(
        payload["decisions"],
        payload["risks"],
        unresolved_questions,
        payload["facts"],
        payload["relations"],
    ):
        return "\n".join(
            [
                f"# Handoff: {project['name']}",
                "",
                f"- project: {project['slug']}",
                f"- since: {since.isoformat()}",
                draft_review_line(payload),
                "",
                "## Handoff Summary",
                "- No new decisions, risks, open questions, evidence, or relation changes need handoff from this window.",
            ]
        )
    return "\n".join(
        [
            f"# Handoff: {project['name']}",
            "",
            f"- project: {project['slug']}",
            f"- since: {since.isoformat()}",
            draft_review_line(payload),
            "",
            "## What Is Decided",
            markdown_list(payload["decisions"], "decision", ("rationale", "consequences")),
            "",
            "## What Is Risky",
            markdown_list(payload["risks"], "title", ("severity", "impact", "mitigation")),
            "",
            "## What Is Open",
            markdown_list(
                unresolved_questions,
                "question",
                ("answer",),
            ),
            "",
            "## Evidence And Context",
            markdown_list(payload["facts"], "statement", ("source", "confidence")),
            "",
            "## Do Not Confuse",
            relations_markdown(payload["relations"]),
            "",
            "## Recommended Next Steps",
            recommended_steps_markdown(payload),
        ]
    )


def quality_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    lines = [
        f"# Memory Quality: {project['name']}",
        "",
        f"- project: {project['slug']}",
        f"- score: {payload['score']}/100",
        f"- status: {payload['status']}",
        f"- relation_count: {payload['relation_count']}",
        f"- relation_coverage: {payload['relation_coverage']:.2f}",
        "",
        "## Counts",
    ]
    for key, value in payload["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Quality Gaps",
            f"- facts_without_source: {len(payload['facts_without_source'])}",
            f"- decisions_without_rationale: {len(payload['decisions_without_rationale'])}",
            f"- risks_without_mitigation: {len(payload['risks_without_mitigation'])}",
            f"- open_questions: {len(payload['open_questions'])}",
            f"- schema_friction_questions: {len(payload.get('schema_friction_questions', []))}",
            "",
            "## Open Questions",
            markdown_list(payload["open_questions"], "question"),
            "",
            "## Schema Friction",
            markdown_list(payload.get("schema_friction_questions", []), "question"),
            "",
            "## Relations",
            relations_markdown(payload["relations"]),
        ]
    )
    return "\n".join(lines)


def limit_markdown_chars(text: str, max_chars: int | None) -> str:
    if not max_chars or len(text) <= max_chars:
        return text
    suffix = "\n\n[output truncated by --max-chars]\n"
    if max_chars <= len(suffix) + 20:
        return text[:max_chars]
    return text[: max_chars - len(suffix)].rstrip() + suffix


def compiled_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    counts = payload["counts"]
    rendered_counts: list[str] = []
    for key, value in counts.items():
        if key == "open_questions":
            rendered_counts.append(f"{key}={format_open_question_count(value)}")
        else:
            rendered_counts.append(f"{key}={value}")
    lines = [
        f"# Compiled Project Memory: {project['name']}",
        "",
        f"- project: {project['slug']}",
        f"- status: {project['status']}",
        draft_review_line(payload),
    ]
    if project.get("description"):
        lines.append(f"- current_state: {truncate(project['description'], 220)}")
    lines.extend(
        [
            "- memory_counts: " + ", ".join(rendered_counts),
            "",
            "## What Is Decided",
            markdown_list(payload["decisions"], "decision", ("rationale",)),
            "",
            "## What Is Risky",
            markdown_list(payload["risks"], "title", ("severity", "impact", "mitigation")),
            "",
            "## What Is Open",
            markdown_list(
                unresolved_open_questions(payload["open_questions"]),
                "question",
                ("answer",),
            ),
            "",
            "## Evidence To Keep In Mind",
            markdown_list(payload["facts"], "statement", ("source", "confidence")),
            "",
            "## Do Not Confuse / Important Links",
            relations_markdown(payload["relations"]),
            "",
            "## Recent Useful Reports",
            markdown_list(payload["reports"], "title", ("report_type", "summary")),
            "",
        ]
    )
    if payload.get("since") and payload.get("recent_changes"):
        recent = payload["recent_changes"]
        lines.extend(
            [
                "## Recent Changes",
                f"- since: {payload['since'].isoformat()}",
                f"- facts: {len(recent['facts'])}",
                f"- decisions: {len(recent['decisions'])}",
                f"- risks: {len(recent['risks'])}",
                f"- open_questions: {len(recent['open_questions'])}",
                f"- reports: {len(recent['reports'])}",
                f"- relations: {len(recent['relations'])}",
                "",
            ]
        )
    if payload.get("receipt_status"):
        receipt = payload["receipt_status"]
        lines.extend(
            [
                "## Receipt Status",
                f"- checked: {receipt['checked']}",
                f"- exported: {receipt['exported']}",
                f"- missing_exports: {len(receipt['missing_exports'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Suggested Next Steps",
            recommended_steps_markdown(payload),
        ]
    )
    return "\n".join(lines)


def search_results_markdown(
    rows: list[dict[str, object]], empty_message: str = "- none"
) -> str:
    if not rows:
        return empty_message
    lines = []
    for row in rows:
        lines.append(
            f"- [{row['type']}/{row['status']}] "
            f"{truncate(row.get('title') or row.get('text') or '', 140)}"
        )
        lines.append(f"  id: {row['id']}")
    return "\n".join(lines)


def receipt_markdown(payload: dict[str, object]) -> str:
    project = payload["project"]
    rows = payload["rows"]
    lines = [
        f"# Memory Receipt: {project['name']}",
        "",
        f"- project: {project['slug']}",
        f"- since: {payload['since'].isoformat()}",
        f"- type: {payload['type']}",
        f"- export_dir: {payload.get('export_dir') or 'not configured'}",
        f"- result: {payload['result']}",
        "",
        "## Recent Memory",
    ]
    if not rows:
        lines.append("- none")
        return "\n".join(lines)

    for row in rows:
        export_state = "yes" if row["exported"] else "no"
        lines.append(
            f"- [{row['type']}/{row.get('status') or 'unknown'}] "
            f"{truncate(row['title'], 140)}"
        )
        lines.append(f"  id: {row['id']}")
        lines.append(f"  updated_at: {row['updated_at']}")
        lines.append(f"  exported: {export_state}")
        if row.get("export_path"):
            lines.append(f"  export_path: {row['export_path']}")
    return "\n".join(lines)
