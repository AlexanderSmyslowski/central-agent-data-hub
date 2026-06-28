"""Local review surface for Agent Data Hub."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import sys
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse
from wsgiref.simple_server import make_server

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent_hub.codex_projects import with_project_display_names
from agent_hub.commands.common import fetch_project
from agent_hub.commands.inbox import (
    fetch_drafts,
    review_draft_by_id,
)
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
    install_repo_agent_memory,
    plan_repo_agent_memory,
)
from agent_hub.reviewers import resolve_required_reviewer, resolve_responsible_reviewer
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
        "markdown": prepare_markdown(payload),
    }


def load_agent_context_view_model(selected_slug: str, task: str) -> tuple[int, dict[str, object]]:
    clean_task = task.strip() or DEFAULT_AGENT_TASK
    with connect() as conn:
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
            project = fetch_project(cur, selected_slug)
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


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    lowered = host.lower()
    if lowered == "localhost":
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def origin_is_loopback(origin: str | None) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and is_loopback_host(parsed.hostname)


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
    with connect() as conn:
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
            project = fetch_project(cur, selected)
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
    with connect() as conn:
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


def text_response(
    start_response: Callable[[str, list[tuple[str, str]]], Any],
    status_line: str,
    text: str,
) -> list[bytes]:
    body = text.encode("utf-8")
    start_response(
        status_line,
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def html_response(
    start_response: Callable[[str, list[tuple[str, str]]], Any],
    status_code: int,
    body: bytes,
) -> list[bytes]:
    status_line = "200 OK" if status_code == 200 else "404 Not Found"
    start_response(
        status_line,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def redirect_response(
    start_response: Callable[[str, list[tuple[str, str]]], Any],
    location: str,
) -> list[bytes]:
    body = b"See Other"
    start_response(
        "303 See Other",
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Location", location),
        ],
    )
    return [body]


def read_post_form(environ: dict[str, object]) -> dict[str, str]:
    try:
        length = int(str(environ.get("CONTENT_LENGTH") or "0"))
    except ValueError:
        length = 0
    stream = environ.get("wsgi.input")
    body = stream.read(length) if hasattr(stream, "read") else b""
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def query_value(environ: dict[str, object], key: str) -> str | None:
    parsed = parse_qs(str(environ.get("QUERY_STRING") or ""), keep_blank_values=True)
    values = parsed.get(key)
    return values[-1] if values else None


def inbox_redirect(param: str, message: str) -> str:
    return f"/inbox?{param}={quote(message)}"


def agent_context_redirect(slug: str, task: str, param: str, message: str) -> str:
    return (
        f"/projects/{quote(slug, safe='')}/agent-context"
        f"?task={quote(task)}&{param}={quote(message)}"
    )


def project_action_slug(path: str, suffix: str) -> str | None:
    if not path.startswith("/projects/") or not path.endswith(suffix):
        return None
    slug = path.removeprefix("/projects/").removesuffix(suffix).strip("/")
    return slug or None


class HubViewApplication:
    def __init__(
        self,
        *,
        bind_host: str,
        csrf_token: str,
        reviewer_handle: str | None,
        reviewer_error: str | None,
    ) -> None:
        self.bind_host = bind_host
        self.csrf_token = csrf_token
        self.inbox_enabled = is_loopback_host(bind_host)
        self.reviewer_handle = reviewer_handle
        self.reviewer_error = reviewer_error

    def __call__(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], Any],
    ) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        path = str(environ.get("PATH_INFO") or "/")

        if method == "GET":
            return self.handle_get(path, environ, start_response)
        if method == "POST" and path in {"/inbox/accept", "/inbox/reject"}:
            return self.handle_inbox_post(path, environ, start_response)
        if method == "POST" and project_action_slug(path, "/codex-setup") is not None:
            return self.handle_codex_setup_post(path, environ, start_response)
        if method == "POST":
            return text_response(start_response, "405 Method Not Allowed", "Method Not Allowed")

        return text_response(start_response, "405 Method Not Allowed", "Method Not Allowed")

    def handle_get(
        self,
        path: str,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], Any],
    ) -> list[bytes]:
        selected_slug: str | None = None
        view_name = "projects"
        if path == "/":
            selected_slug = None
        elif path.startswith("/projects/") and path.endswith("/agent-context"):
            view_name = "agent_context"
            selected_slug = path.removeprefix("/projects/").removesuffix("/agent-context").strip("/")
            if not selected_slug:
                return text_response(start_response, "404 Not Found", "Not Found")
            status_code, view_model = load_agent_context_view_model(
                selected_slug,
                query_value(environ, "task") or DEFAULT_AGENT_TASK,
            )
            if view_model.get("agent_context"):
                view_model["agent_context"]["setup_message"] = query_value(environ, "setup_message")
                view_model["agent_context"]["setup_error"] = query_value(environ, "setup_error")
            body = render_page(
                view_model,
                status_code,
                view_name=view_name,
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
            )
            return html_response(start_response, status_code, body)
        elif path.startswith("/projects/"):
            selected_slug = path.removeprefix("/projects/").strip("/") or None
        elif path == "/inbox":
            view_name = "inbox"
            status_code, view_model = load_inbox_view_model(
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
                reviewer_handle=self.reviewer_handle,
                reviewer_error=self.reviewer_error,
                message=query_value(environ, "message"),
                error_message=query_value(environ, "error"),
            )
            body = render_page(
                view_model,
                status_code,
                view_name=view_name,
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
            )
            return html_response(start_response, status_code, body)
        else:
            return text_response(start_response, "404 Not Found", "Not Found")

        status_code, view_model = load_view_model(selected_slug)
        body = render_page(
            view_model,
            status_code,
            view_name=view_name,
            csrf_token=self.csrf_token,
            inbox_enabled=self.inbox_enabled,
        )
        return html_response(start_response, status_code, body)

    def handle_inbox_post(
        self,
        path: str,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], Any],
    ) -> list[bytes]:
        if not self.inbox_enabled:
            return text_response(
                start_response,
                "403 Forbidden",
                "Review actions are only available on loopback.",
            )
        if self.reviewer_handle is None:
            return text_response(
                start_response,
                "403 Forbidden",
                self.reviewer_error or "Reviewer handle is required for this review action.",
            )
        if not origin_is_loopback(environ.get("HTTP_ORIGIN")):
            return text_response(
                start_response,
                "403 Forbidden",
                "Origin is not allowed for this local review action.",
            )

        form = read_post_form(environ)
        if form.get("csrf_token") != self.csrf_token:
            return text_response(
                start_response,
                "403 Forbidden",
                "Review token is missing or invalid.",
            )

        draft_id = form.get("draft_id", "").strip()
        item_type = form.get("type", "").strip()
        decision = "accept" if path == "/inbox/accept" else "reject"
        if not draft_id or not item_type:
            return redirect_response(
                start_response,
                inbox_redirect("error", "The draft could not be reviewed."),
            )

        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    result = review_draft_by_id(
                        cur,
                        draft_id,
                        decision=decision,
                        item_type=item_type,
                        agent_slug="hub-view",
                        agent_name="Hub View",
                        review_source="hub_view",
                        reviewed_by=self.reviewer_handle,
                    )
        except ValueError:
            return redirect_response(
                start_response,
                inbox_redirect("error", "The draft does not match this review action."),
            )
        except Exception:
            return redirect_response(
                start_response,
                inbox_redirect("error", "The review action could not be saved."),
            )

        if not result:
            return redirect_response(
                start_response,
                inbox_redirect("error", "This draft is no longer open."),
            )

        label = "Accepted" if decision == "accept" else "Rejected"
        return redirect_response(
            start_response,
            inbox_redirect("message", f"{label}: draft {result['id']}."),
        )

    def handle_codex_setup_post(
        self,
        path: str,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], Any],
    ) -> list[bytes]:
        selected_slug = project_action_slug(path, "/codex-setup")
        if selected_slug is None:
            return text_response(start_response, "404 Not Found", "Not Found")

        form = read_post_form(environ)
        task = (form.get("task") or DEFAULT_AGENT_TASK).strip() or DEFAULT_AGENT_TASK

        if not self.inbox_enabled:
            return text_response(
                start_response,
                "403 Forbidden",
                "Codex setup actions are only available on loopback.",
            )
        if not origin_is_loopback(environ.get("HTTP_ORIGIN")):
            return text_response(
                start_response,
                "403 Forbidden",
                "Origin is not allowed for this local setup action.",
            )

        if form.get("csrf_token") != self.csrf_token:
            return text_response(
                start_response,
                "403 Forbidden",
                "Setup token is missing or invalid.",
            )

        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    project = fetch_project(cur, selected_slug)
            if project is None or project.get("status") != "active":
                return redirect_response(
                    start_response,
                    agent_context_redirect(selected_slug, task, "setup_error", "Project not found."),
                )
            repo_root = Path(__file__).resolve().parents[1]
            project_path = metadata_project_local_path(project)
            if project_path is None:
                return redirect_response(
                    start_response,
                    agent_context_redirect(
                        selected_slug,
                        task,
                        "setup_error",
                        "Codex setup needs a registered project folder.",
                    ),
                )
            plan = plan_repo_agent_memory(
                repo_path=project_path,
                project_slug=str(project["slug"]),
                hub_root=repo_root,
                target_file=DEFAULT_TARGET_FILE,
            )
            install_repo_agent_memory(plan)
        except (OSError, RepoAgentMemoryError):
            return redirect_response(
                start_response,
                agent_context_redirect(
                    selected_slug,
                    task,
                    "setup_error",
                    "Codex setup could not be installed.",
                ),
            )

        if plan.action == "unchanged":
            message = f"Codex setup already up to date in {plan.target_file}."
        else:
            message = f"Codex setup installed in {plan.target_file}."
        return redirect_response(
            start_response,
            agent_context_redirect(selected_slug, task, "setup_message", message),
        )


def create_application(
    *,
    bind_host: str = "127.0.0.1",
    csrf_token: str | None = None,
    reviewer_handle: str | None = None,
    reviewer_error: str | None = None,
) -> HubViewApplication:
    if reviewer_handle is None and reviewer_error is None:
        try:
            reviewer_handle = resolve_required_reviewer(env_var="HUB_VIEW_REVIEWER")
        except ValueError as exc:
            reviewer_error = str(exc)
    return HubViewApplication(
        bind_host=bind_host,
        csrf_token=csrf_token or secrets.token_urlsafe(32),
        reviewer_handle=reviewer_handle,
        reviewer_error=reviewer_error,
    )


application = create_application()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hub-view",
        description="Local review surface for Agent Data Hub.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument(
        "--allow-lan-read",
        action="store_true",
        help=(
            "Allow Hub View to bind to a non-loopback host. This exposes "
            "reviewed memory read-only on the local network."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HUB_VIEW_PORT", "8765")),
        help="Bind port.",
    )
    return parser


def validate_lan_read_bind(host: str, *, allow_lan_read: bool) -> str | None:
    if is_loopback_host(host):
        return None

    message = (
        f"binding Hub View to non-loopback host '{host}' exposes reviewed "
        "memory read-only on the local network; review and setup writes stay "
        "disabled unless Hub View is bound to loopback"
    )
    if not allow_lan_read:
        raise ValueError(f"{message}; re-run with --allow-lan-read to confirm")
    return message


def port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                return False
            raise
    return True


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL is not set")

    try:
        lan_read_warning = validate_lan_read_bind(
            args.host,
            allow_lan_read=args.allow_lan_read,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if not port_is_available(args.host, args.port):
        parser.error(
            f"port {args.port} is already in use; retry with --port {args.port + 1}"
        )

    app = create_application(bind_host=args.host)
    with make_server(args.host, args.port, app) as server:
        if lan_read_warning:
            print(f"Warning: {lan_read_warning}.", file=sys.stderr, flush=True)
        print(f"Hub View running on http://{args.host}:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nHub View stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
