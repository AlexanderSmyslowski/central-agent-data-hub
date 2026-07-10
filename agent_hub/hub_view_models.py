"""Hub View data loading and render view models."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import sys
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent_hub.codex_projects import with_project_display_names
from agent_hub.commands.common import fetch_project
from agent_hub.commands.inbox import fetch_drafts
from agent_hub.commands.prepare import (
    build_prepare_payload,
    fetch_prepare_payload as fetch_agent_prepare_payload,
    prepare_markdown,
)
from agent_hub.commands.summaries import fetch_compiled_payload
from agent_hub.context_receipt import INFLUENCE_LINES, prepare_context_counts
from agent_hub.db import connect
from agent_hub.hub_view_formatting import format_timestamp
from agent_hub.hub_view_i18n import (
    DEFAULT_LANGUAGE,
    language_switch_links,
    localize_ui_text,
    pluralizer,
    resolve_language,
    translator,
    with_language,
)
from agent_hub.quality import fetch_project_quality
from agent_hub.relations import fetch_project_relations
from agent_hub.rendering import truncate
from agent_hub.repo_agent_memory import (
    DEFAULT_TARGET_FILE,
    RepoAgentMemoryError,
    plan_repo_agent_memory,
)
from agent_hub.reviewers import resolve_responsible_reviewer
from agent_hub.statuses import (
    REVIEWED_MEMORY_STATUSES,
    agent_read_excluded_statuses,
    agent_read_excluded_statuses_by_type,
    current_memory_statuses_for,
    sql_status_in_clause,
)
from agent_hub.writeback_routing import card_for_item, primary_text, source_value
from agent_hub.workspace_overview import (
    WORKSPACE_MEMORY_COUNT_KEYS,
    build_workspace_inventory,
)


DRAFT_TYPE_LABELS = {
    "fact": "Fact",
    "decision": "Decision",
    "risk": "Risk",
    "open_question": "Open question",
    "report": "Report",
}

CARD_LINE_PREFIXES = {
    "Was merke ich mir:": "Remember:",
    "Quelle:": "Source:",
    "Folge bei Irrtum:": "If wrong:",
}
CARD_SECTION_PREFIXES = {
    "Was merke ich mir:": (
        "draft_section_remember",
        "draft_section_remember_help",
    ),
    "Quelle:": (
        "draft_section_source",
        "draft_section_source_help",
    ),
    "Folge bei Irrtum:": (
        "draft_section_if_wrong",
        "draft_section_if_wrong_help",
    ),
}
DRAFT_REMEMBER_TEXT_KEYS = {
    "fact": "draft_remember_fact_text",
    "decision": "draft_remember_decision_text",
    "risk": "draft_remember_risk_text",
    "open_question": "draft_remember_open_question_text",
    "report": "draft_remember_report_text",
}

DEFAULT_AGENT_TASK = "Use reviewed Agent Data Hub context for this project."
HUB_VIEW_STATIC_ASSET_MANIFEST = {
    "stylesheets": (
        "base.css",
        "layout.css",
        "project_overview.css",
        "workspace_overview.css",
        "workbench.css",
        "memory_library.css",
        "memory_search.css",
        "review_surfaces.css",
        "agent_handoff.css",
        "quality_detail.css",
        "memory_detail.css",
        "responsive.css",
    ),
    "scripts": (
        "shared.js",
        "copy.js",
        "memory_search.js",
        "project_nav.js",
        "inbox_filter.js",
        "connection_checklist.js",
    ),
}
HUB_VIEW_STYLESHEET_ASSETS = HUB_VIEW_STATIC_ASSET_MANIFEST["stylesheets"]
HUB_VIEW_SCRIPT_ASSETS = HUB_VIEW_STATIC_ASSET_MANIFEST["scripts"]
PROJECT_CARD_COUNT_KEYS = WORKSPACE_MEMORY_COUNT_KEYS
MISSING_LATEST_REPORT = object()

MEMORY_DETAIL_SPECS = {
    "fact": {
        "table": "facts",
        "columns": "id, statement, source, confidence, status, created_at, updated_at",
        "title_column": "statement",
        "type_label_key": "agent_status_facts",
        "anchor": "reviewed-memory",
        "fields": (
            ("source", "memory_item_source"),
            ("confidence", "memory_item_confidence"),
        ),
    },
    "decision": {
        "table": "decisions",
        "columns": "id, decision, rationale, consequences, status, created_at, updated_at",
        "title_column": "decision",
        "type_label_key": "agent_status_decisions",
        "anchor": "reviewed-memory",
        "fields": (
            ("rationale", "memory_item_rationale"),
            ("consequences", "memory_item_consequences"),
        ),
    },
    "risk": {
        "table": "risks",
        "columns": "id, title, severity, impact, mitigation, status, created_at, updated_at",
        "title_column": "title",
        "type_label_key": "agent_status_risks",
        "anchor": "risks-and-questions",
        "fields": (
            ("severity", "memory_item_severity"),
            ("impact", "memory_item_impact"),
            ("mitigation", "memory_item_mitigation"),
        ),
    },
    "open_question": {
        "table": "open_questions",
        "columns": "id, question, answer, status, created_at, updated_at",
        "title_column": "question",
        "type_label_key": "agent_status_open_questions",
        "anchor": "risks-and-questions",
        "fields": (
            ("answer", "memory_item_answer"),
        ),
    },
    "report": {
        "table": "reports",
        "columns": "id, title, report_type, summary, body, status, created_at, updated_at",
        "title_column": "title",
        "type_label_key": "agent_status_reports",
        "anchor": "latest-status",
        "fields": (
            ("report_type", "memory_item_report_type"),
            ("summary", "memory_item_summary"),
            ("body", "memory_item_body"),
        ),
    },
}

MEMORY_DETAIL_URL_TYPES = {"open_question": "open-question"}
MEMORY_DETAIL_PATH_TYPES = {
    **{item_type: item_type for item_type in MEMORY_DETAIL_SPECS},
    "open-question": "open_question",
}

MEMORY_LIBRARY_ITEM_TYPES = (
    "fact",
    "decision",
    "risk",
    "open_question",
    "report",
)

MEMORY_LIBRARY_FILTER_PATHS = {
    "fact": "fact",
    "decision": "decision",
    "risk": "risk",
    "open_question": "open-question",
    "report": "report",
}

RELATION_OBJECT_LABEL_KEYS = {
    "project": "nav_project",
    "agent": "memory_relation_agent",
    "document": "memory_relation_document",
    "agent_action": "memory_relation_agent_action",
    **{
        item_type: spec["type_label_key"]
        for item_type, spec in MEMORY_DETAIL_SPECS.items()
    },
}

RELATION_TYPE_LABEL_KEYS = {
    "supports": "relation_supports",
    "contradicts": "relation_contradicts",
    "supersedes": "relation_supersedes",
    "mitigates": "relation_mitigates",
    "answers": "relation_answers",
    "raises": "relation_raises",
    "references": "relation_references",
    "derived_from": "relation_derived_from",
    "blocks": "relation_blocks",
    "depends_on": "relation_depends_on",
}

def _compat_attr(name: str, fallback):
    module = sys.modules.get("agent_hub.hub_view")
    return getattr(module, name, fallback) if module is not None else fallback

def hub_view_templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "hub_view"

def hub_view_static_dir() -> Path:
    return hub_view_templates_dir() / "static"

def static_url(asset_name: str) -> str:
    return f"/static/{asset_name}"

def load_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(hub_view_templates_dir())),
        autoescape=select_autoescape(("html", "xml")),
    )

def memory_detail_path_type(item_type: str) -> str:
    return MEMORY_DETAIL_URL_TYPES.get(item_type, item_type)

def memory_detail_url(project_slug: object, item_type: str, item_id: object) -> str:
    path_type = memory_detail_path_type(item_type)
    return f"/projects/{project_slug}/memory/{path_type}/{item_id}"

def rows_with_memory_detail_links(
    rows: list[dict[str, object]],
    *,
    project_slug: object,
    item_type: str,
) -> list[dict[str, object]]:
    linked_rows: list[dict[str, object]] = []
    for row in rows:
        linked = dict(row)
        if linked.get("id"):
            linked["detail_url"] = memory_detail_url(project_slug, item_type, linked["id"])
        linked_rows.append(linked)
    return linked_rows

def memory_library_path_type(item_type: str) -> str:
    return MEMORY_LIBRARY_FILTER_PATHS.get(item_type, item_type)

def normalize_memory_library_filter(value: object | None) -> str | None:
    text = str(value or "").strip()
    if not text or text == "all":
        return None
    return MEMORY_DETAIL_PATH_TYPES.get(text)

def memory_library_url(
    project_slug: object,
    *,
    item_type: str | None = None,
) -> str:
    base = f"/projects/{project_slug}/memory"
    if item_type is None:
        return base
    return f"{base}?type={memory_library_path_type(item_type)}"

def memory_status_clause(item_type: str) -> tuple[str, tuple[str, ...]]:
    excluded_statuses = agent_read_excluded_statuses(item_type)
    if not excluded_statuses:
        return "", ()
    placeholders = ", ".join(["%s"] * len(excluded_statuses))
    return f"AND status NOT IN ({placeholders})", excluded_statuses

def relation_object_label_key(object_type: object) -> str:
    return RELATION_OBJECT_LABEL_KEYS.get(str(object_type), "memory_relation_item")

def relation_type_label_key(relation_type: object) -> str:
    return RELATION_TYPE_LABEL_KEYS.get(str(relation_type), "memory_relation_type")

def relation_object_url(
    *,
    project_slug: object,
    object_type: object,
    object_id: object,
) -> str | None:
    item_type = str(object_type)
    if item_type not in MEMORY_DETAIL_SPECS:
        return None
    return memory_detail_url(project_slug, item_type, object_id)

def related_memory_cards(
    rows: list[dict[str, object]],
    *,
    current_type: str,
    current_id: object,
    project_slug: object,
) -> list[dict[str, object]]:
    current_id_text = str(current_id)
    cards: list[dict[str, object]] = []
    for row in rows:
        source_matches = (
            row.get("source_type") == current_type
            and str(row.get("source_id")) == current_id_text
        )
        target_matches = (
            row.get("target_type") == current_type
            and str(row.get("target_id")) == current_id_text
        )
        if not source_matches and not target_matches:
            continue

        other_type = row["target_type"] if source_matches else row["source_type"]
        other_id = row["target_id"] if source_matches else row["source_id"]
        other_summary = (
            row.get("target_summary") if source_matches else row.get("source_summary")
        )
        cards.append(
            {
                "id": str(row["id"]),
                "direction": "out" if source_matches else "in",
                "direction_key": (
                    "memory_relation_outgoing"
                    if source_matches
                    else "memory_relation_incoming"
                ),
                "relation_type": row["relation_type"],
                "relation_label_key": relation_type_label_key(row["relation_type"]),
                "other_type": other_type,
                "other_label_key": relation_object_label_key(other_type),
                "other_summary": truncate(other_summary or other_type, 160),
                "other_url": relation_object_url(
                    project_slug=project_slug,
                    object_type=other_type,
                    object_id=other_id,
                ),
            }
        )
    return cards

def fetch_active_projects(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, name, slug, description, status, metadata, created_at, updated_at
        FROM projects
        WHERE status = 'active'
        ORDER BY slug
        """
    )
    return with_project_display_names(list(cur.fetchall()))


def empty_project_card_counts() -> dict[str, int]:
    return {key: 0 for key in PROJECT_CARD_COUNT_KEYS}


def project_ids_values_clause(project_ids: list[object]) -> str:
    return ", ".join(["(%s)"] * len(project_ids))


def fetch_project_card_counts(
    cur,
    project_ids: list[object],
) -> dict[object, dict[str, int]]:
    if not project_ids:
        return {}

    values_clause = project_ids_values_clause(project_ids)
    document_clause, document_statuses = sql_status_in_clause(
        "status",
        current_memory_statuses_for("document"),
    )
    fact_clause, fact_statuses = sql_status_in_clause(
        "status",
        current_memory_statuses_for("fact"),
    )
    decision_clause, decision_statuses = sql_status_in_clause(
        "status",
        current_memory_statuses_for("decision"),
    )
    open_question_clause, open_question_statuses = sql_status_in_clause(
        "status",
        current_memory_statuses_for("open_question"),
    )
    risk_clause, risk_statuses = sql_status_in_clause(
        "status",
        current_memory_statuses_for("risk"),
    )
    report_clause, report_statuses = sql_status_in_clause(
        "status",
        current_memory_statuses_for("report"),
    )
    cur.execute(
        f"""
        WITH project_ids(project_id) AS (
          VALUES {values_clause}
        ),
        memory_counts AS (
          SELECT project_id, 'documents' AS item_type, count(*)::int AS item_count
          FROM documents
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND {document_clause}
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'facts' AS item_type, count(*)::int AS item_count
          FROM facts
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND {fact_clause}
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'decisions' AS item_type, count(*)::int AS item_count
          FROM decisions
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND {decision_clause}
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'open_questions' AS item_type, count(*)::int AS item_count
          FROM open_questions
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND {open_question_clause}
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'risks' AS item_type, count(*)::int AS item_count
          FROM risks
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND {risk_clause}
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'reports' AS item_type, count(*)::int AS item_count
          FROM reports
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND {report_clause}
          GROUP BY project_id
        )
        SELECT
          p.project_id,
          COALESCE(SUM(item_count) FILTER (WHERE item_type = 'documents'), 0)::int AS documents,
          COALESCE(SUM(item_count) FILTER (WHERE item_type = 'facts'), 0)::int AS facts,
          COALESCE(SUM(item_count) FILTER (WHERE item_type = 'decisions'), 0)::int AS decisions,
          COALESCE(SUM(item_count) FILTER (WHERE item_type = 'open_questions'), 0)::int AS open_questions,
          COALESCE(SUM(item_count) FILTER (WHERE item_type = 'risks'), 0)::int AS risks,
          COALESCE(SUM(item_count) FILTER (WHERE item_type = 'reports'), 0)::int AS reports
        FROM project_ids p
        LEFT JOIN memory_counts m ON m.project_id = p.project_id
        GROUP BY p.project_id
        """,
        (
            *project_ids,
            *document_statuses,
            *fact_statuses,
            *decision_statuses,
            *open_question_statuses,
            *risk_statuses,
            *report_statuses,
        ),
    )
    return {
        row["project_id"]: {key: int(row[key]) for key in PROJECT_CARD_COUNT_KEYS}
        for row in cur.fetchall()
    }


def fetch_latest_reports_by_project(
    cur,
    project_ids: list[object],
) -> dict[object, dict[str, object]]:
    if not project_ids:
        return {}

    values_clause = project_ids_values_clause(project_ids)
    cur.execute(
        f"""
        WITH project_ids(project_id) AS (
          VALUES {values_clause}
        ),
        ranked_reports AS (
          SELECT
            r.project_id,
            r.title,
            r.summary,
            r.updated_at,
            row_number() OVER (
              PARTITION BY r.project_id
              ORDER BY r.updated_at DESC, r.created_at DESC, r.id DESC
            ) AS report_rank
          FROM reports r
          JOIN project_ids p ON p.project_id = r.project_id
          WHERE r.status <> 'archived'
        )
        SELECT project_id, title, summary, updated_at
        FROM ranked_reports
        WHERE report_rank = 1
        """,
        project_ids,
    )
    return {row["project_id"]: row for row in cur.fetchall()}


def fetch_latest_report(cur, project_id: object) -> dict[str, object] | None:
    return fetch_latest_reports_by_project(cur, [project_id]).get(project_id)

def build_project_card(
    cur,
    project: dict[str, object],
    *,
    draft_count: int = 0,
    counts: dict[str, int] | None = None,
    latest_report: dict[str, object] | None | object = MISSING_LATEST_REPORT,
) -> dict[str, object]:
    metadata = project.get("metadata") or {}
    project_id = project["id"]
    if counts is None:
        counts = fetch_project_card_counts(cur, [project_id]).get(
            project_id,
            empty_project_card_counts(),
        )
    if latest_report is MISSING_LATEST_REPORT:
        latest_report = fetch_latest_report(cur, project_id)
    latest_report = latest_report if isinstance(latest_report, dict) else None
    reviewed_count = sum(
        counts.get(key, 0)
        for key in ("facts", "decisions", "risks", "open_questions", "reports")
    )
    attention_count = counts.get("risks", 0) + counts.get("open_questions", 0)
    if draft_count:
        signal_key = "project_overview_signal_review"
        signal_state = "review"
        next_step_key = "project_overview_next_review"
        next_step_action_key = "project_overview_next_review_action"
        next_step_href = "/inbox"
    elif attention_count:
        signal_key = "project_overview_signal_attention"
        signal_state = "attention"
        next_step_key = "project_overview_next_attention"
        next_step_action_key = "project_overview_next_attention_action"
        next_step_href = f"/projects/{project['slug']}#risks-and-questions"
    elif latest_report:
        signal_key = "project_overview_signal_ready"
        signal_state = "ready"
        next_step_key = "project_overview_next_latest"
        next_step_action_key = "project_overview_next_latest_action"
        next_step_href = f"/projects/{project['slug']}#latest-status"
    else:
        signal_key = "project_overview_signal_empty"
        signal_state = "quiet"
        next_step_key = "project_overview_next_open"
        next_step_action_key = "project_overview_next_open_action"
        next_step_href = f"/projects/{project['slug']}"
    return {
        "name": project["name"],
        "slug": project["slug"],
        "status": project["status"],
        "description": truncate(project.get("description") or "", 120),
        "project_type": metadata.get("project_type"),
        "counts": counts,
        "draft_count": draft_count,
        "latest_report_title": latest_report["title"] if latest_report else None,
        "latest_report_summary": (
            truncate(latest_report.get("summary") or "", 96) if latest_report else None
        ),
        "reviewed_count": reviewed_count,
        "attention_count": attention_count,
        "signal_key": signal_key,
        "signal_state": signal_state,
        "next_step_key": next_step_key,
        "next_step_action_key": next_step_action_key,
        "next_step_href": next_step_href,
        "updated_at": format_timestamp(project.get("updated_at")),
    }


def build_project_cards(
    cur,
    projects: list[dict[str, object]],
    draft_counts: dict[str, int],
) -> list[dict[str, object]]:
    project_ids = [project["id"] for project in projects]
    counts_by_project = fetch_project_card_counts(cur, project_ids)
    latest_reports = fetch_latest_reports_by_project(cur, project_ids)
    return [
        build_project_card(
            cur,
            project,
            draft_count=draft_counts.get(str(project["slug"]), 0),
            counts=counts_by_project.get(project["id"], empty_project_card_counts()),
            latest_report=latest_reports.get(project["id"]),
        )
        for project in projects
    ]


def build_quality_check_cards(quality: dict[str, object]) -> list[dict[str, object]]:
    checks = (
        (
            "facts_without_source",
            "quality_facts_without_source",
            "quality_facts_without_source_meaning",
            "quality_facts_without_source_action",
        ),
        (
            "decisions_without_rationale",
            "quality_decisions_without_rationale",
            "quality_decisions_without_rationale_meaning",
            "quality_decisions_without_rationale_action",
        ),
        (
            "risks_without_mitigation",
            "quality_risks_without_mitigation",
            "quality_risks_without_mitigation_meaning",
            "quality_risks_without_mitigation_action",
        ),
        (
            "open_questions",
            "quality_open_questions",
            "quality_open_questions_meaning",
            "quality_open_questions_action",
        ),
        (
            "schema_friction_questions",
            "quality_schema_friction",
            "quality_schema_friction_meaning",
            "quality_schema_friction_action",
        ),
    )
    cards = []
    for key, title_key, meaning_key, action_key in checks:
        rows = quality.get(key)
        count = len(rows) if isinstance(rows, list) else 0
        cards.append(
            {
                "count": count,
                "state": "needs-review" if count else "ok",
                "title_key": title_key,
                "meaning_key": meaning_key,
                "action_key": action_key,
            }
        )
    return cards

def build_work_state_cards(
    *,
    reports: list[dict[str, object]],
    risks: list[dict[str, object]],
    open_questions: list[dict[str, object]],
    quality: dict[str, object],
    draft_count: int,
) -> list[dict[str, object]]:
    attention_count = len(risks) + len(open_questions)
    first_attention = None
    if risks:
        first_attention = risks[0].get("title")
    elif open_questions:
        first_attention = open_questions[0].get("question")

    quality_attention = next(
        (
            card
            for card in quality["check_cards"]
            if card.get("state") == "needs-review"
            and int(card.get("count") or 0) > 0
        ),
        None,
    )

    return [
        {
            "kind": "latest",
            "priority": "1",
            "label_key": "work_state_latest_label",
            "href": "#latest-status",
            "title": reports[0]["title"] if reports else None,
            "title_key": None if reports else "latest_status_empty",
            "body": reports[0].get("summary") if reports else None,
            "body_key": (
                "work_state_latest_body" if reports else "work_state_latest_empty"
            ),
            "action_key": "work_state_latest_action",
            "state": "ready" if reports else "quiet",
            "report_count": len(reports),
        },
        {
            "kind": "attention",
            "priority": "2",
            "label_key": "work_state_attention_label",
            "href": "#risks-and-questions",
            "title": first_attention,
            "title_key": None if first_attention else "needs_attention_empty",
            "body": None,
            "body_key": "work_state_attention_body",
            "action_key": "work_state_attention_action",
            "state": "needs-review" if attention_count else "quiet",
            "risk_count": len(risks),
            "question_count": len(open_questions),
        },
        {
            "kind": "review",
            "priority": "3",
            "label_key": "work_state_review_label",
            "href": "/inbox",
            "title": None,
            "title_key": (
                "work_state_review_waiting"
                if draft_count
                else "work_state_review_empty"
            ),
            "body": None,
            "body_key": "work_state_review_body",
            "action_key": "work_state_review_action",
            "state": "needs-review" if draft_count else "quiet",
            "review_count": draft_count,
        },
        {
            "kind": "quality",
            "priority": "4",
            "label_key": "work_state_quality_label",
            "href": "#quality",
            "title": None,
            "title_key": (
                quality_attention["title_key"]
                if quality_attention
                else "work_state_quality_ok"
            ),
            "body": None,
            "body_key": (
                quality_attention["meaning_key"]
                if quality_attention
                else "quality_snapshot_note"
            ),
            "action_key": "work_state_quality_action",
            "state": "needs-review" if quality_attention else "quiet",
            "quality_score": quality["score"],
        },
    ]


def build_detail_view(
    cur,
    project: dict[str, object],
    *,
    draft_count: int = 0,
    draft_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    metadata = project.get("metadata") or {}
    compiled = fetch_compiled_payload(cur, project, limit=8)
    quality = fetch_project_quality(cur, project)
    quality_view = {
        "score": quality["score"],
        "status": quality["status"],
        "relation_count": quality["relation_count"],
        "relation_coverage": f"{quality['relation_coverage']:.2f}",
        "gaps": [
            ("facts without source", len(quality["facts_without_source"])),
            ("decisions without rationale", len(quality["decisions_without_rationale"])),
            ("risks without mitigation", len(quality["risks_without_mitigation"])),
            ("open questions", len(quality["open_questions"])),
            ("schema friction", len(quality["schema_friction_questions"])),
        ],
        "check_cards": build_quality_check_cards(quality),
    }
    facts = rows_with_memory_detail_links(
        compiled["facts"],
        project_slug=project["slug"],
        item_type="fact",
    )
    decisions = rows_with_memory_detail_links(
        compiled["decisions"],
        project_slug=project["slug"],
        item_type="decision",
    )
    risks = rows_with_memory_detail_links(
        compiled["risks"],
        project_slug=project["slug"],
        item_type="risk",
    )
    open_questions = rows_with_memory_detail_links(
        compiled["open_questions"],
        project_slug=project["slug"],
        item_type="open_question",
    )
    reports = rows_with_memory_detail_links(
        compiled["reports"],
        project_slug=project["slug"],
        item_type="report",
    )
    memory_total = sum(
        int(compiled["counts"].get(key, 0) or 0)
        for key in ("facts", "decisions", "risks", "open_questions", "reports")
    )

    return {
        "name": project["name"],
        "slug": project["slug"],
        "description": project.get("description") or "",
        "status": project["status"],
        "project_type": metadata.get("project_type"),
        "work_mode": metadata.get("work_mode"),
        "counts": compiled["counts"],
        "memory_total": memory_total,
        "is_empty": memory_total == 0 and draft_count == 0,
        "has_project_folder": bool(metadata.get("local_path")),
        "draft_count": draft_count,
        "draft_preview": build_project_draft_preview(
            draft_rows or [],
            project["slug"],
        ),
        "quality": quality_view,
        "work_state": build_work_state_cards(
            reports=reports,
            risks=risks,
            open_questions=open_questions,
            quality=quality_view,
            draft_count=draft_count,
        ),
        "facts": facts,
        "decisions": decisions,
        "risks": risks,
        "open_questions": open_questions,
        "reports": reports,
        "relations": [
            {
                "source": truncate(row.get("source_summary") or row["source_type"], 88),
                "relation_type": row["relation_type"],
                "target": truncate(row.get("target_summary") or row["target_type"], 88),
            }
            for row in compiled["relations"]
        ],
        "updated_at": format_timestamp(project.get("updated_at")),
    }

def fetch_memory_item(
    cur,
    *,
    project_id: object,
    item_type: str,
    item_id: object,
) -> dict[str, object] | None:
    spec = MEMORY_DETAIL_SPECS[item_type]
    status_clause, status_params = memory_status_clause(item_type)
    cur.execute(
        f"""
        SELECT {spec["columns"]}
        FROM {spec["table"]}
        WHERE project_id = %s
          AND id = %s
          {status_clause}
        """,
        (project_id, item_id, *status_params),
    )
    row = cur.fetchone()
    return dict(row) if row else None

def build_memory_item_view(
    item_type: str,
    row: dict[str, object],
    *,
    project_slug: object,
    relation_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    spec = MEMORY_DETAIL_SPECS[item_type]
    fields = []
    for field, label_key in spec["fields"]:
        value = row.get(field)
        if value is not None and str(value).strip():
            fields.append({"label_key": label_key, "value": value})
    status = row.get("status")
    if status is not None and str(status).strip():
        fields.append({"label_key": "memory_item_status", "value": status})
    updated_at = format_timestamp(row.get("updated_at"))
    if updated_at:
        fields.append({"label_key": "memory_item_updated", "value": updated_at})
    source = row.get("source")
    source_text = str(source).strip() if source is not None else ""
    return {
        "id": str(row["id"]),
        "item_type": item_type,
        "type_label_key": spec["type_label_key"],
        "title": row.get(str(spec["title_column"])) or row["id"],
        "source": source_text,
        "status": status,
        "updated_at": updated_at,
        "fields": fields,
        "relations": related_memory_cards(
            relation_rows or [],
            current_type=item_type,
            current_id=row["id"],
            project_slug=project_slug,
        ),
        "library_url": memory_library_url(project_slug),
        "type_library_url": memory_library_url(project_slug, item_type=item_type),
        "back_url": f"/projects/{project_slug}#{spec['anchor']}",
        "anchor": spec["anchor"],
    }

def memory_library_card(
    item_type: str,
    row: dict[str, object],
    *,
    project_slug: object,
) -> dict[str, object]:
    spec = MEMORY_DETAIL_SPECS[item_type]
    title = row.get(str(spec["title_column"])) or row["id"]
    summary = None
    if item_type == "fact":
        source = row.get("source")
        confidence = row.get("confidence")
        parts = []
        if source:
            parts.append(str(source))
        if confidence is not None:
            parts.append(f"confidence {confidence}")
        summary = " · ".join(parts)
    elif item_type == "decision":
        summary = row.get("rationale")
    elif item_type == "risk":
        parts = [str(row.get("severity") or "").strip()]
        if row.get("impact"):
            parts.append(str(row["impact"]))
        summary = " · ".join(part for part in parts if part)
    elif item_type == "open_question":
        summary = row.get("answer")
    elif item_type == "report":
        summary = row.get("summary")

    return {
        "id": str(row["id"]),
        "item_type": item_type,
        "type_label_key": spec["type_label_key"],
        "title": title,
        "summary": summary,
        "status": row.get("status"),
        "updated_at": format_timestamp(row.get("updated_at")),
        "detail_url": memory_detail_url(project_slug, item_type, row["id"]),
    }

def fetch_memory_library_cards(
    cur,
    *,
    project_id: object,
    project_slug: object,
) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for item_type in MEMORY_LIBRARY_ITEM_TYPES:
        spec = MEMORY_DETAIL_SPECS[item_type]
        statuses = REVIEWED_MEMORY_STATUSES[item_type]
        placeholders = ", ".join(["%s"] * len(statuses))
        cur.execute(
            f"""
            SELECT {spec["columns"]}
            FROM {spec["table"]}
            WHERE project_id = %s
              AND status IN ({placeholders})
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
            """,
            (project_id, *statuses),
        )
        groups[item_type] = [
            memory_library_card(item_type, dict(row), project_slug=project_slug)
            for row in cur.fetchall()
        ]
    return groups

def memory_library_filters(
    *,
    groups: dict[str, list[dict[str, object]]],
    selected_type: str | None,
    project_slug: object,
) -> list[dict[str, object]]:
    total = sum(len(rows) for rows in groups.values())
    filters = [
        {
            "label_key": "memory_library_filter_all",
            "href": memory_library_url(project_slug),
            "count": total,
            "active": selected_type is None,
        }
    ]
    for item_type in MEMORY_LIBRARY_ITEM_TYPES:
        filters.append(
            {
                "label_key": MEMORY_DETAIL_SPECS[item_type]["type_label_key"],
                "href": memory_library_url(project_slug, item_type=item_type),
                "count": len(groups.get(item_type, [])),
                "active": selected_type == item_type,
            }
        )
    return filters

def build_memory_library_view(
    *,
    groups: dict[str, list[dict[str, object]]],
    selected_type: str | None,
    project_slug: object,
) -> dict[str, object]:
    visible_types = (
        [selected_type]
        if selected_type in MEMORY_LIBRARY_ITEM_TYPES
        else list(MEMORY_LIBRARY_ITEM_TYPES)
    )
    sections = [
        {
            "item_type": item_type,
            "label_key": MEMORY_DETAIL_SPECS[item_type]["type_label_key"],
            "entries": groups.get(item_type, []),
            "count": len(groups.get(item_type, [])),
        }
        for item_type in visible_types
    ]
    total = sum(len(rows) for rows in groups.values())
    visible_count = sum(section["count"] for section in sections)
    return {
        "selected_type": selected_type,
        "filters": memory_library_filters(
            groups=groups,
            selected_type=selected_type,
            project_slug=project_slug,
        ),
        "sections": sections,
        "total_count": total,
        "visible_count": visible_count,
    }

def load_memory_library_view_model(
    selected_slug: str,
    selected_filter: object | None = None,
) -> tuple[int, dict[str, object]]:
    selected_type = normalize_memory_library_filter(selected_filter)
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            drafts = fetch_drafts(cur, limit=None)
            draft_counts = draft_counts_by_project(drafts)
            draft_total = sum(draft_counts.values())
            cards = build_project_cards(cur, projects, draft_counts)
            project = _compat_attr("fetch_project", fetch_project)(cur, selected_slug)
            if project is None or project.get("status") != "active":
                return 404, {
                    "projects": cards,
                    "selected_project": None,
                    "not_found_slug": selected_slug,
                    "draft_total": draft_total,
                    "memory_library": None,
                }
            selected_project = build_detail_view(
                cur,
                project,
                draft_count=draft_counts.get(str(project["slug"]), 0),
                draft_rows=drafts,
            )
            groups = fetch_memory_library_cards(
                cur,
                project_id=project["id"],
                project_slug=project["slug"],
            )
            return 200, {
                "projects": cards,
                "selected_project": selected_project,
                "not_found_slug": None,
                "draft_total": draft_total,
                "memory_library": build_memory_library_view(
                    groups=groups,
                    selected_type=selected_type,
                    project_slug=project["slug"],
                ),
            }

def load_memory_item_view_model(
    selected_slug: str,
    item_type_path: str,
    item_id: object,
) -> tuple[int, dict[str, object]]:
    item_type = MEMORY_DETAIL_PATH_TYPES.get(item_type_path)
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            drafts = fetch_drafts(cur, limit=None)
            draft_counts = draft_counts_by_project(drafts)
            draft_total = sum(draft_counts.values())
            cards = build_project_cards(cur, projects, draft_counts)
            project = _compat_attr("fetch_project", fetch_project)(cur, selected_slug)
            if project is None or project.get("status") != "active":
                return 404, {
                    "projects": cards,
                    "selected_project": None,
                    "not_found_slug": selected_slug,
                    "draft_total": draft_total,
                    "memory_item": None,
                }
            selected_project = build_detail_view(
                cur,
                project,
                draft_count=draft_counts.get(str(project["slug"]), 0),
                draft_rows=drafts,
            )
            try:
                parsed_item_id = UUID(str(item_id))
            except ValueError:
                parsed_item_id = None
            if item_type is None or parsed_item_id is None:
                memory_item = None
            else:
                memory_row = fetch_memory_item(
                    cur,
                    project_id=project["id"],
                    item_type=item_type,
                    item_id=parsed_item_id,
                )
                relation_rows = (
                    fetch_project_relations(
                        cur,
                        project["id"],
                        object_type=item_type,
                        object_id=parsed_item_id,
                        limit=12,
                        excluded_statuses_by_type=agent_read_excluded_statuses_by_type(),
                    )
                    if memory_row
                    else []
                )
                memory_item = (
                    build_memory_item_view(
                        item_type,
                        memory_row,
                        project_slug=project["slug"],
                        relation_rows=relation_rows,
                    )
                    if memory_row
                    else None
                )
            return 200 if memory_item else 404, {
                "projects": cards,
                "selected_project": selected_project,
                "not_found_slug": None,
                "draft_total": draft_total,
                "memory_item": memory_item,
            }

def agent_context_counts(payload: dict[str, object]) -> dict[str, int]:
    counts = prepare_context_counts(payload)
    drafts = payload.get("drafts_pending_review") or {}
    pending_drafts = 0
    if isinstance(drafts, dict):
        pending_drafts = sum(len(rows) for rows in drafts.values() if isinstance(rows, list))
    counts["relations"] = len(payload.get("relations") or [])
    counts["pending_drafts"] = pending_drafts
    return counts

def shell_command(parts: list[object]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)

def metadata_project_local_path(project: dict[str, object]) -> str | None:
    metadata = project.get("metadata") or {}
    if isinstance(metadata, dict):
        local_path = metadata.get("local_path")
        if isinstance(local_path, str) and local_path.strip():
            return local_path
    return None

def known_project_local_path(project: dict[str, object], repo_root: Path) -> str | None:
    local_path = metadata_project_local_path(project)
    if local_path is not None:
        return local_path
    if os.environ.get("AGENT_HUB_PUBLIC_DEMO") == "1" and project.get("slug") == "central-agent-data-hub-demo":
        return str(repo_root)
    return None

def build_codex_setup_view(project: dict[str, object], repo_root: Path) -> dict[str, object]:
    metadata_local_path = metadata_project_local_path(project)
    project_repo_path = known_project_local_path(project, repo_root)
    if project_repo_path is None:
        return {
            "project_path": None,
            "command": None,
            "target_path": None,
            "target_file": DEFAULT_TARGET_FILE,
            "action": None,
            "preview": None,
            "error": None,
            "can_install": False,
            "demo_only": False,
            "verification": {
                "state": "unknown",
                "label": "Cannot verify yet",
                "detail": "Register a local project folder before ADH can check Codex setup.",
            },
        }

    codex_command_parts = [
        str(repo_root / "scripts" / "install_repo_agent_memory.sh"),
        "--repo",
        project_repo_path,
        "--project",
        project["slug"],
    ]
    if metadata_local_path is None:
        codex_command_parts.append("--dry-run")
    codex_command = shell_command(codex_command_parts)
    try:
        plan = plan_repo_agent_memory(
            repo_path=project_repo_path,
            project_slug=str(project["slug"]),
            hub_root=repo_root,
            target_file=DEFAULT_TARGET_FILE,
        )
    except RepoAgentMemoryError as exc:
        return {
            "project_path": project_repo_path,
            "command": codex_command,
            "target_path": None,
            "target_file": DEFAULT_TARGET_FILE,
            "action": None,
            "preview": None,
            "error": str(exc),
            "can_install": False,
            "demo_only": metadata_local_path is None,
            "verification": {
                "state": "error",
                "label": "Cannot verify Codex setup",
                "detail": str(exc),
            },
        }

    can_install = metadata_local_path is not None
    if not can_install:
        verification = {
            "state": "demo",
            "label": "Demo preview only",
            "detail": "Demo mode shows the target only; it does not write an AGENTS.md block.",
        }
    elif plan.action == "unchanged":
        verification = {
            "state": "connected",
            "label": "Codex setup verified",
            "detail": f"{plan.target_file} contains the ADH block for this project.",
        }
    else:
        verification = {
            "state": "missing",
            "label": "Codex setup not installed yet",
            "detail": f"Install the ADH block into {plan.target_file} so Codex reads ADH context before work.",
        }
    return {
        "project_path": str(plan.repo_path),
        "command": codex_command,
        "target_path": str(plan.target_path),
        "target_file": plan.target_file,
        "action": plan.action,
        "preview": plan.block,
        "error": None,
        "can_install": can_install,
        "demo_only": not can_install,
        "verification": verification,
    }

def build_agent_context_view(payload: dict[str, object]) -> dict[str, object]:
    project = payload["project"]
    trail = payload.get("context_trail") or {}
    gap_summary = trail.get("gap_summary") if isinstance(trail, dict) else {}
    if not isinstance(gap_summary, dict):
        gap_summary = {}
    counts = agent_context_counts(payload)
    task = str(payload["task"])
    repo_root = Path(__file__).resolve().parents[1]
    codex_setup = build_codex_setup_view(project, repo_root)
    mcp_server_command = [sys.executable, "-m", "agent_hub.cli", "mcp-serve"]
    install_mcp_command = [sys.executable, "-m", "pip", "install", "-e", ".[mcp]"]
    mcp_json = {
        "mcpServers": {
            "agent-data-hub": {
                "command": sys.executable,
                "args": ["-m", "agent_hub.cli", "mcp-serve"],
            }
        }
    }
    startup_instruction = "\n".join(
        [
            "At the start of ADH-related work:",
            f'- request reviewed context from Agent Data Hub for project "{project["slug"]}"',
            f'- use the current task as the context-pack task: "{task}"',
            "- show the ADH Context Loaded receipt or equivalent counts before acting",
            "- treat reviewed decisions as constraints",
            "- keep drafts and gaps labelled as unconfirmed",
        ]
    )
    return {
        "project_slug": project["slug"],
        "project_name": project["name"],
        "task": task,
        "counts": counts,
        "source_count": len(trail.get("sources") or []) if isinstance(trail, dict) else 0,
        "gap_summary": {
            "stale": gap_summary.get("stale", 0),
            "unanswered": gap_summary.get("unanswered", 0),
            "blind_spots": gap_summary.get("blind_spots", 0),
            "pending_drafts": gap_summary.get("pending_drafts", 0),
        },
        "influence": list(INFLUENCE_LINES),
        "commands": {
            "prepare": shell_command(
                [
                    "agent-hub",
                    "prepare",
                    "--project",
                    project["slug"],
                    "--task",
                    task,
                ]
            ),
            "agent_start": shell_command(
                [
                    "scripts/agent_start.sh",
                    "--project",
                    project["slug"],
                    "--query",
                    task,
                    "--review",
                ]
            ),
        },
        "local_agent": {
            "setup_command": (
                f"{shell_command(install_mcp_command)} && "
                f"{shell_command(['claude', 'mcp', 'add', 'agent-data-hub', '--', *mcp_server_command])}"
            ),
            "codex": codex_setup,
            "codex_command": codex_setup["command"],
            "codex_project_path": codex_setup["project_path"],
            "install_mcp": shell_command(install_mcp_command),
            "claude_mcp": shell_command(
                [
                    "claude",
                    "mcp",
                    "add",
                    "agent-data-hub",
                    "--",
                    *mcp_server_command,
                ]
            ),
            "mcp_json": json.dumps(mcp_json, indent=2),
            "startup_instruction": startup_instruction,
        },
        "markdown": _compat_attr("prepare_markdown", prepare_markdown)(payload),
    }

def load_agent_context_view_model(selected_slug: str, task: str) -> tuple[int, dict[str, object]]:
    clean_task = task.strip() or DEFAULT_AGENT_TASK
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            drafts = fetch_drafts(cur, limit=None)
            draft_counts = draft_counts_by_project(drafts)
            draft_total = sum(draft_counts.values())
            cards = build_project_cards(cur, projects, draft_counts)
            project = _compat_attr("fetch_project", fetch_project)(cur, selected_slug)
            if project is None or project.get("status") != "active":
                return 404, {
                    "projects": cards,
                    "selected_project": None,
                    "not_found_slug": selected_slug,
                    "draft_total": draft_total,
                    "agent_context": None,
                }
            compiled = fetch_agent_prepare_payload(cur, project, clean_task, limit=8)
            payload = build_prepare_payload(
                project=project,
                task=clean_task,
                compiled=compiled,
            )
            return 200, {
                "projects": cards,
                "selected_project": build_detail_view(
                    cur,
                    project,
                    draft_count=draft_counts.get(str(project["slug"]), 0),
                    draft_rows=drafts,
                ),
                "not_found_slug": None,
                "draft_total": draft_total,
                "agent_context": build_agent_context_view(payload),
            }

def draft_counts_by_project(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        slug = str(row["project"])
        counts[slug] = counts.get(slug, 0) + 1
    return counts

def build_project_draft_preview(
    rows: list[dict[str, object]],
    project_slug: object,
    *,
    limit: int = 2,
) -> list[dict[str, object]]:
    return [
        draft_card(row)
        for row in rows
        if str(row.get("project")) == str(project_slug)
    ][:limit]

def draft_card(row: dict[str, object]) -> dict[str, object]:
    card = card_for_item(row)
    resolution = (
        None
        if "responsible_reviewer" in row and "resolution_reason" in row
        else resolve_responsible_reviewer(row)
    )
    responsible_reviewer = row.get("responsible_reviewer")
    resolution_reason = row.get("resolution_reason")
    if resolution is not None:
        responsible_reviewer = resolution.handle
        resolution_reason = resolution.reason
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "type_label": DRAFT_TYPE_LABELS.get(str(row["type"]), str(row["type"])),
        "project": row["project"],
        "project_name": row["project_name"],
        "updated_at": format_timestamp(row.get("updated_at")),
        "responsible_reviewer": responsible_reviewer or "unassigned",
        "resolution_reason": resolution_reason or "no reviewer assigned",
        "card": card,
        "card_lines": [translate_card_line_for_ui(line) for line in card.splitlines()],
        "card_sections": draft_card_sections_for_item(row),
    }

def translate_card_line_for_ui(line: str) -> str:
    for source, target in CARD_LINE_PREFIXES.items():
        if line.startswith(source):
            return f"{target}{line.removeprefix(source)}"
    return line

def draft_card_sections(card: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for line in card.splitlines():
        for prefix, (label_key, help_key) in CARD_SECTION_PREFIXES.items():
            if line.startswith(prefix):
                sections.append(
                    {
                        "label_key": label_key,
                        "help_key": help_key,
                        "text": line.removeprefix(prefix).strip(),
                    }
                )
                break
        else:
            sections.append(
                {
                    "label_key": "draft_section_detail",
                    "help_key": "draft_section_detail_help",
                    "text": line.strip(),
                }
            )
    return sections

def draft_card_sections_for_item(row: dict[str, object]) -> list[dict[str, str]]:
    item_type = str(row.get("type") or "")
    source = source_value(row)
    source_text_key = (
        "draft_source_text"
        if source and source != "Quelle nicht angegeben"
        else "draft_source_missing_text"
    )
    return [
        {
            "label_key": "draft_section_remember",
            "help_key": "draft_section_remember_help",
            "text_key": DRAFT_REMEMBER_TEXT_KEYS.get(
                item_type,
                "draft_remember_generic_text",
            ),
            "text_value": primary_text(row),
        },
        {
            "label_key": "draft_section_source",
            "help_key": "draft_section_source_help",
            "text_key": source_text_key,
            "text_value": source if source_text_key == "draft_source_text" else "",
        },
        {
            "label_key": "draft_section_if_wrong",
            "help_key": "draft_section_if_wrong_help",
            "text_key": "draft_if_wrong_default_text",
            "text_value": "",
        },
    ]

def group_draft_cards(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        slug = str(row["project"])
        group = groups.setdefault(
            slug,
            {
                "project": slug,
                "project_name": row.get("project_name") or slug,
                "drafts": [],
            },
        )
        group["drafts"].append(draft_card(row))
    return list(groups.values())

def fetch_recent_review_actions(cur, *, limit: int = 5) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT
          aa.id,
          aa.action,
          aa.object_type,
          aa.object_id,
          aa.output,
          aa.metadata,
          aa.updated_at,
          p.slug AS project,
          p.name AS project_name
        FROM agent_actions AS aa
        LEFT JOIN agents AS a ON a.id = aa.agent_id
        LEFT JOIN projects AS p ON p.id = a.project_id
        WHERE aa.action IN ('inbox_accept', 'inbox_reject')
        ORDER BY aa.updated_at DESC, aa.created_at DESC, aa.id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return list(cur.fetchall())

def review_activity_card(row: dict[str, object]) -> dict[str, object]:
    output = row.get("output") if isinstance(row.get("output"), dict) else {}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    decision = "accepted" if row.get("action") == "inbox_accept" else "rejected"
    item_type = str(row.get("object_type") or "")
    source = output.get("review_source") or metadata.get("review_source") or ""
    return {
        "decision": decision,
        "decision_key": (
            "review_activity_accepted"
            if decision == "accepted"
            else "review_activity_rejected"
        ),
        "type": item_type,
        "type_label": DRAFT_TYPE_LABELS.get(item_type, item_type),
        "project": row.get("project") or output.get("project") or "",
        "project_name": row.get("project_name") or row.get("project") or output.get("project") or "",
        "reviewed_by": output.get("reviewed_by") or metadata.get("reviewed_by") or "",
        "review_source": "Hub View" if source == "hub_view" else source,
        "status": output.get("next_status") or "",
        "updated_at": format_timestamp(row.get("updated_at")),
    }

def review_activity_cards(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [review_activity_card(row) for row in rows]

def load_workspace_overview_view_model() -> tuple[int, dict[str, object]]:
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            drafts = fetch_drafts(cur, limit=None)
            draft_counts = draft_counts_by_project(drafts)
            draft_total = sum(draft_counts.values())
            project_ids = [project["id"] for project in projects]
            counts_by_project = fetch_project_card_counts(cur, project_ids)
            latest_reports = fetch_latest_reports_by_project(cur, project_ids)
            cards = [
                build_project_card(
                    cur,
                    project,
                    draft_count=draft_counts.get(str(project["slug"]), 0),
                    counts=counts_by_project.get(
                        project["id"],
                        empty_project_card_counts(),
                    ),
                    latest_report=latest_reports.get(project["id"]),
                )
                for project in projects
            ]
            return 200, {
                "projects": cards,
                "selected_project": None,
                "not_found_slug": None,
                "draft_total": draft_total,
                "workspace_overview": build_workspace_inventory(
                    projects,
                    draft_counts,
                    counts_by_project=counts_by_project,
                    latest_reports=latest_reports,
                ),
            }


def load_view_model(selected_slug: str | None) -> tuple[int, dict[str, object]]:
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            drafts = fetch_drafts(cur, limit=None)
            draft_counts = draft_counts_by_project(drafts)
            draft_total = sum(draft_counts.values())
            cards = build_project_cards(cur, projects, draft_counts)
            if not projects:
                return 200, {
                    "projects": [],
                    "selected_project": None,
                    "not_found_slug": None,
                    "draft_total": draft_total,
                }

            if selected_slug is None:
                return 200, {
                    "projects": cards,
                    "selected_project": None,
                    "not_found_slug": None,
                    "draft_total": draft_total,
                }

            selected = selected_slug
            project = _compat_attr("fetch_project", fetch_project)(cur, selected)
            if project is None or project.get("status") != "active":
                return 404, {
                    "projects": cards,
                    "selected_project": None,
                    "not_found_slug": selected,
                    "draft_total": draft_total,
                }

            return 200, {
                "projects": cards,
                "selected_project": build_detail_view(
                    cur,
                    project,
                    draft_count=draft_counts.get(str(project["slug"]), 0),
                    draft_rows=drafts,
                ),
                "not_found_slug": None,
                "draft_total": draft_total,
            }

def load_project_onboarding_view_model(
    *,
    csrf_token: str,
    registration_enabled: bool,
    message: str | None = None,
    error_message: str | None = None,
) -> tuple[int, dict[str, object]]:
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            drafts = fetch_drafts(cur, limit=None)
            draft_counts = draft_counts_by_project(drafts)
            draft_total = sum(draft_counts.values())
            cards = build_project_cards(cur, projects, draft_counts)
    return 200, {
        "projects": cards,
        "selected_project": None,
        "not_found_slug": None,
        "draft_total": draft_total,
        "registration": {
            "csrf_token": csrf_token,
            "enabled": registration_enabled,
            "message": message,
            "error": error_message,
        },
    }

def load_inbox_view_model(
    *,
    csrf_token: str,
    inbox_enabled: bool,
    reviewer_handle: str | None,
    reviewer_error: str | None,
    message: str | None = None,
    error_message: str | None = None,
    review_result: str | None = None,
    review_item: str | None = None,
    review_type: str | None = None,
    review_status: str | None = None,
    review_project: str | None = None,
    reviewed_by: str | None = None,
    review_source: str | None = None,
) -> tuple[int, dict[str, object]]:
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            drafts = fetch_drafts(cur, limit=None)
            review_activity = fetch_recent_review_actions(cur)
    result_card = None
    if review_result in {"accepted", "rejected"}:
        result_card = {
            "result": review_result,
            "item_id": review_item or "",
            "type": review_type or "",
            "type_label": DRAFT_TYPE_LABELS.get(str(review_type or ""), review_type or ""),
            "status": review_status or "",
            "project": review_project or "",
            "reviewed_by": reviewed_by or "",
            "review_source": "Hub View" if review_source == "hub_view" else review_source or "",
        }
    return 200, {
        "projects": [],
        "selected_project": None,
        "not_found_slug": None,
        "draft_total": len(drafts),
        "inbox": {
            "groups": group_draft_cards(drafts),
            "csrf_token": csrf_token,
            "enabled": inbox_enabled,
            "review_enabled": inbox_enabled and reviewer_handle is not None,
            "reviewer": reviewer_handle,
            "reviewer_error": reviewer_error,
            "message": message,
            "error": error_message,
            "review_result": result_card,
            "recent_reviews": review_activity_cards(review_activity),
            "review_activity_url": "/inbox/activity",
        },
    }

def load_review_activity_view_model() -> tuple[int, dict[str, object]]:
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            drafts = fetch_drafts(cur, limit=None)
            review_activity = fetch_recent_review_actions(cur, limit=50)
    return 200, {
        "projects": [],
        "selected_project": None,
        "not_found_slug": None,
        "draft_total": len(drafts),
        "inbox": {
            "groups": [],
            "recent_reviews": review_activity_cards(review_activity),
            "review_activity_url": None,
        },
    }

def render_page(
    view_model: dict[str, object],
    status_code: int,
    *,
    view_name: str = "projects",
    csrf_token: str = "",
    inbox_enabled: bool = True,
    language: str = DEFAULT_LANGUAGE,
    current_path: str = "/",
    query_string: str = "",
) -> bytes:
    env = load_environment()
    template = env.get_template("page.html")
    resolved_language = resolve_language(language)
    t = translator(resolved_language)
    tn = pluralizer(resolved_language)
    return template.render(
        page_title=t("hub_view"),
        app_name=t("hub_view"),
        claim=t("local_review_surface"),
        status_code=status_code,
        view_name=view_name,
        csrf_token=csrf_token,
        inbox_enabled=inbox_enabled,
        language=resolved_language,
        t=t,
        tn=tn,
        ui_text=lambda text: localize_ui_text(text, resolved_language),
        url_for=lambda url: with_language(url, resolved_language),
        static_url=static_url,
        stylesheet_assets=HUB_VIEW_STYLESHEET_ASSETS,
        script_assets=HUB_VIEW_SCRIPT_ASSETS,
        language_links=language_switch_links(current_path, query_string),
        **view_model,
    ).encode("utf-8")
