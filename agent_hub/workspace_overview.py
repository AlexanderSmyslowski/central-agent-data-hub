"""Pure workspace overview assembly for Hub View."""

from __future__ import annotations

from agent_hub.hub_view_formatting import format_timestamp
from agent_hub.project_taxonomy import (
    WORKSPACE_CATEGORY_BODY_KEYS,
    WORKSPACE_CATEGORY_LABEL_KEYS,
    WORKSPACE_CATEGORY_ORDER,
    WORKSPACE_COMPANY_CATEGORIES,
    WORKSPACE_SEPARATE_CATEGORIES,
    classify_workspace_project,
)
from agent_hub.rendering import truncate


WORKSPACE_MEMORY_COUNT_KEYS = (
    "documents",
    "facts",
    "decisions",
    "open_questions",
    "risks",
    "reports",
)


def empty_workspace_counts() -> dict[str, int]:
    return {key: 0 for key in WORKSPACE_MEMORY_COUNT_KEYS}


def workspace_current_total(counts: dict[str, int]) -> int:
    return sum(int(counts.get(key, 0) or 0) for key in WORKSPACE_MEMORY_COUNT_KEYS)


def workspace_project_row(
    project: dict[str, object],
    *,
    counts: dict[str, int],
    draft_count: int,
    latest_report: dict[str, object] | None = None,
) -> dict[str, object]:
    metadata = project.get("metadata") or {}
    metadata = metadata if isinstance(metadata, dict) else {}
    reviewed_total = workspace_current_total(counts)
    classification = classify_workspace_project(
        project,
        current_total=reviewed_total,
        draft_count=draft_count,
    )
    open_attention = int(counts.get("risks", 0) or 0) + int(
        counts.get("open_questions", 0) or 0
    )
    if draft_count:
        state = "review"
        state_key = "workspace_project_state_review"
    elif open_attention:
        state = "attention"
        state_key = "workspace_project_state_attention"
    elif reviewed_total:
        state = "ready"
        state_key = "workspace_project_state_ready"
    else:
        state = "empty"
        state_key = "workspace_project_state_empty"

    latest_report = latest_report if isinstance(latest_report, dict) else None
    return {
        "slug": project["slug"],
        "name": project["name"],
        "description": truncate(project.get("description") or "", 120),
        "status": project["status"],
        "memory_scope": metadata.get("memory_scope") or "",
        "project_type": metadata.get("project_type") or "",
        "domain": metadata.get("domain") or "",
        "counts": counts,
        "reviewed_total": reviewed_total,
        "draft_count": draft_count,
        "open_attention": open_attention,
        "category": classification["category"],
        "category_label_key": classification["label_key"],
        "category_body_key": classification["body_key"],
        "category_reason_key": classification["reason_key"],
        "state": state,
        "state_key": state_key,
        "latest_report_title": latest_report.get("title") if latest_report else None,
        "latest_report_summary": (
            truncate(latest_report.get("summary") or "", 100)
            if latest_report
            else None
        ),
        "project_url": f"/projects/{project['slug']}",
        "memory_url": f"/projects/{project['slug']}/memory",
        "agent_url": f"/projects/{project['slug']}/agent-context",
        "updated_at": format_timestamp(project.get("updated_at")),
    }


def build_workspace_inventory(
    projects: list[dict[str, object]],
    draft_counts: dict[str, int],
    *,
    counts_by_project: dict[object, dict[str, int]],
    latest_reports: dict[object, dict[str, object]],
) -> dict[str, object]:
    rows = [
        workspace_project_row(
            project,
            counts=counts_by_project.get(project["id"], empty_workspace_counts()),
            draft_count=draft_counts.get(str(project["slug"]), 0),
            latest_report=latest_reports.get(project["id"]),
        )
        for project in projects
    ]
    rows.sort(
        key=lambda row: (
            WORKSPACE_CATEGORY_ORDER.index(str(row["category"])),
            -int(row["draft_count"]),
            -int(row["open_attention"]),
            str(row["slug"]),
        )
    )

    categories = []
    for category in WORKSPACE_CATEGORY_ORDER:
        category_rows = [row for row in rows if row["category"] == category]
        if not category_rows:
            continue
        categories.append(
            {
                "category": category,
                "label_key": WORKSPACE_CATEGORY_LABEL_KEYS[category],
                "body_key": WORKSPACE_CATEGORY_BODY_KEYS[category],
                "count": len(category_rows),
                "reviewed_total": sum(
                    int(row["reviewed_total"]) for row in category_rows
                ),
                "draft_total": sum(int(row["draft_count"]) for row in category_rows),
                "attention_total": sum(
                    int(row["open_attention"]) for row in category_rows
                ),
                "projects": category_rows,
            }
        )

    summary = {
        "project_count": len(rows),
        "reviewed_total": sum(int(row["reviewed_total"]) for row in rows),
        "verified_facts": sum(int(row["counts"].get("facts", 0)) for row in rows),
        "accepted_decisions": sum(
            int(row["counts"].get("decisions", 0)) for row in rows
        ),
        "open_risks": sum(int(row["counts"].get("risks", 0)) for row in rows),
        "open_questions": sum(
            int(row["counts"].get("open_questions", 0)) for row in rows
        ),
        "published_reports": sum(int(row["counts"].get("reports", 0)) for row in rows),
        "draft_total": sum(int(row["draft_count"]) for row in rows),
        "company_relevant_count": sum(
            1 for row in rows if row["category"] in WORKSPACE_COMPANY_CATEGORIES
        ),
        "empty_count": sum(1 for row in rows if row["category"] == "empty_ad_hoc"),
    }

    focus = [
        row
        for row in rows
        if int(row["draft_count"]) > 0 or int(row["open_attention"]) > 0
    ][:6]
    missing = [
        row for row in rows if row["category"] in WORKSPACE_SEPARATE_CATEGORIES
    ][:8]
    return {
        "summary": summary,
        "categories": categories,
        "projects": rows,
        "focus": focus,
        "missing": missing,
    }
