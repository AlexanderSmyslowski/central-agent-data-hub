"""Hub View data loading and render view models."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import sys

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
from agent_hub.hub_view_i18n import (
    DEFAULT_LANGUAGE,
    language_switch_links,
    localize_ui_text,
    resolve_language,
    translator,
    with_language,
)
from agent_hub.quality import fetch_project_quality
from agent_hub.rendering import truncate
from agent_hub.repo_agent_memory import (
    DEFAULT_TARGET_FILE,
    RepoAgentMemoryError,
    plan_repo_agent_memory,
)
from agent_hub.reviewers import resolve_responsible_reviewer
from agent_hub.writeback_routing import card_for_item


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

DEFAULT_AGENT_TASK = "Use reviewed Agent Data Hub context for this project."
PROJECT_CARD_COUNT_KEYS = (
    "documents",
    "facts",
    "decisions",
    "open_questions",
    "risks",
    "reports",
)
MISSING_LATEST_REPORT = object()

def _compat_attr(name: str, fallback):
    module = sys.modules.get("agent_hub.hub_view")
    return getattr(module, name, fallback) if module is not None else fallback

def hub_view_templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "hub_view"

def load_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(hub_view_templates_dir())),
        autoescape=select_autoescape(("html", "xml")),
    )

def format_timestamp(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    text = str(value)
    return text.replace("T", " ").replace("+00:00", " UTC")

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
    cur.execute(
        f"""
        WITH project_ids(project_id) AS (
          VALUES {values_clause}
        ),
        memory_counts AS (
          SELECT project_id, 'documents' AS item_type, count(*)::int AS item_count
          FROM documents
          WHERE project_id IN (SELECT project_id FROM project_ids)
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'facts' AS item_type, count(*)::int AS item_count
          FROM facts
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND status NOT IN ('draft', 'archived')
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'decisions' AS item_type, count(*)::int AS item_count
          FROM decisions
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND status NOT IN ('draft', 'archived')
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'open_questions' AS item_type, count(*)::int AS item_count
          FROM open_questions
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND status NOT IN ('draft', 'answered', 'closed', 'resolved', 'archived')
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'risks' AS item_type, count(*)::int AS item_count
          FROM risks
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND status NOT IN ('draft', 'resolved', 'archived')
          GROUP BY project_id
          UNION ALL
          SELECT project_id, 'reports' AS item_type, count(*)::int AS item_count
          FROM reports
          WHERE project_id IN (SELECT project_id FROM project_ids)
            AND status NOT IN ('draft', 'archived')
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
        project_ids,
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


def build_detail_view(
    cur,
    project: dict[str, object],
    *,
    draft_count: int = 0,
) -> dict[str, object]:
    metadata = project.get("metadata") or {}
    compiled = fetch_compiled_payload(cur, project, limit=8)
    quality = fetch_project_quality(cur, project)

    return {
        "name": project["name"],
        "slug": project["slug"],
        "description": project.get("description") or "",
        "status": project["status"],
        "project_type": metadata.get("project_type"),
        "work_mode": metadata.get("work_mode"),
        "counts": compiled["counts"],
        "draft_count": draft_count,
        "quality": {
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
        },
        "facts": compiled["facts"],
        "decisions": compiled["decisions"],
        "risks": compiled["risks"],
        "open_questions": compiled["open_questions"],
        "reports": compiled["reports"],
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
    }

def translate_card_line_for_ui(line: str) -> str:
    for source, target in CARD_LINE_PREFIXES.items():
        if line.startswith(source):
            return f"{target}{line.removeprefix(source)}"
    return line

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

            selected = selected_slug or str(projects[0]["slug"])
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
                ),
                "not_found_slug": None,
                "draft_total": draft_total,
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
        ui_text=lambda text: localize_ui_text(text, resolved_language),
        url_for=lambda url: with_language(url, resolved_language),
        language_links=language_switch_links(current_path, query_string),
        **view_model,
    ).encode("utf-8")
