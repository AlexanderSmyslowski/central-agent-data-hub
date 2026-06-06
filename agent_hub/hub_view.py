"""Local read-only review surface for Agent Data Hub."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import os
from pathlib import Path
import socket
from typing import Any, Callable
from wsgiref.simple_server import make_server

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent_hub.codex_projects import with_project_display_names
from agent_hub.commands.common import fetch_project
from agent_hub.commands.summaries import fetch_compiled_payload
from agent_hub.db import connect
from agent_hub.quality import fetch_project_quality
from agent_hub.rendering import truncate


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


def build_project_card(cur, project: dict[str, object]) -> dict[str, object]:
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
        "latest_report_title": latest_report["title"] if latest_report else None,
        "latest_report_summary": (
            truncate(latest_report.get("summary") or "", 96) if latest_report else None
        ),
        "updated_at": format_timestamp(project.get("updated_at")),
    }


def build_detail_view(cur, project: dict[str, object]) -> dict[str, object]:
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


def load_view_model(selected_slug: str | None) -> tuple[int, dict[str, object]]:
    with connect() as conn:
        with conn.cursor() as cur:
            projects = fetch_active_projects(cur)
            cards = [build_project_card(cur, project) for project in projects]
            if not projects:
                return 200, {
                    "projects": [],
                    "selected_project": None,
                    "not_found_slug": None,
                }

            selected = selected_slug or str(projects[0]["slug"])
            project = fetch_project(cur, selected)
            if project is None or project.get("status") != "active":
                return 404, {
                    "projects": cards,
                    "selected_project": None,
                    "not_found_slug": selected,
                }

            return 200, {
                "projects": cards,
                "selected_project": build_detail_view(cur, project),
                "not_found_slug": None,
            }


def render_page(view_model: dict[str, object], status_code: int) -> bytes:
    env = load_environment()
    template = env.get_template("page.html")
    return template.render(
        page_title="Hub View",
        app_name="Hub View",
        claim="read-only review surface for Agent Data Hub",
        status_code=status_code,
        **view_model,
    ).encode("utf-8")


def application(
    environ: dict[str, object],
    start_response: Callable[[str, list[tuple[str, str]]], Any],
) -> list[bytes]:
    if environ.get("REQUEST_METHOD") != "GET":
        body = b"Method Not Allowed"
        start_response(
            "405 Method Not Allowed",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    path = str(environ.get("PATH_INFO") or "/")
    selected_slug: str | None = None
    if path == "/":
        selected_slug = None
    elif path.startswith("/projects/"):
        selected_slug = path.removeprefix("/projects/").strip("/") or None
    else:
        body = b"Not Found"
        start_response(
            "404 Not Found",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    status_code, view_model = load_view_model(selected_slug)
    body = render_page(view_model, status_code)
    status_line = "200 OK" if status_code == 200 else "404 Not Found"
    start_response(
        status_line,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hub-view",
        description="Local read-only review surface for Agent Data Hub.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HUB_VIEW_PORT", "8765")),
        help="Bind port.",
    )
    return parser


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

    if not port_is_available(args.host, args.port):
        parser.error(
            f"port {args.port} is already in use; retry with --port {args.port + 1}"
        )

    with make_server(args.host, args.port, application) as server:
        print(f"Hub View running on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nHub View stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
