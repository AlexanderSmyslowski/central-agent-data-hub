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

def fetch_latest_report(cur, project_id: object) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT title, summary, updated_at
        FROM reports
        WHERE project_id = %s
          AND status <> 'archived'
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (project_id,),
    )
    return cur.fetchone()

def build_project_card(
    cur,
    project: dict[str, object],
    *,
    draft_count: int = 0,
) -> dict[str, object]:
    metadata = project.get("metadata") or {}
    latest_report = fetch_latest_report(cur, project["id"])
    payload = fetch_compiled_payload(cur, project, limit=3)
    return {
        "name": project["name"],
        "slug": project["slug"],
        "status": project["status"],
        "description": truncate(project.get("description") or "", 120),
        "project_type": metadata.get("project_type"),
        "counts": payload["counts"],
        "draft_count": draft_count,
        "latest_report_title": latest_report["title"] if latest_report else None,
        "latest_report_summary": (
            truncate(latest_report.get("summary") or "", 96) if latest_report else None
        ),
        "updated_at": format_timestamp(project.get("updated_at")),
    }

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
        }

    can_install = metadata_local_path is not None
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
            cards = [
                build_project_card(
                    cur,
                    project,
                    draft_count=draft_counts.get(str(project["slug"]), 0),
                )
                for project in projects
            ]
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

def load_view_model(selected_slug: str | None) -> tuple[int, dict[str, object]]:
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            drafts = fetch_drafts(cur, limit=None)
            draft_counts = draft_counts_by_project(drafts)
            draft_total = sum(draft_counts.values())
            cards = [
                build_project_card(
                    cur,
                    project,
                    draft_count=draft_counts.get(str(project["slug"]), 0),
                )
                for project in projects
            ]
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
) -> tuple[int, dict[str, object]]:
    with _compat_attr("connect", connect)() as conn:
        with conn.cursor() as cur:
            drafts = fetch_drafts(cur, limit=None)
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
        },
    }

def render_page(
    view_model: dict[str, object],
    status_code: int,
    *,
    view_name: str = "projects",
    csrf_token: str = "",
    inbox_enabled: bool = True,
) -> bytes:
    env = load_environment()
    template = env.get_template("page.html")
    return template.render(
        page_title="Hub View",
        app_name="Hub View",
        claim="local review surface for Agent Data Hub",
        status_code=status_code,
        view_name=view_name,
        csrf_token=csrf_token,
        inbox_enabled=inbox_enabled,
        **view_model,
    ).encode("utf-8")
