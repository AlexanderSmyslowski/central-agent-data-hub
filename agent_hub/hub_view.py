"""Local review surface for Agent Data Hub."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import ipaddress
import os
from pathlib import Path
import secrets
import socket
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
from agent_hub.commands.summaries import fetch_compiled_payload
from agent_hub.db import connect
from agent_hub.quality import fetch_project_quality
from agent_hub.rendering import truncate
from agent_hub.writeback_routing import card_for_item


DRAFT_TYPE_LABELS = {
    "fact": "Fakt",
    "decision": "Entscheidung",
    "risk": "Risiko",
    "open_question": "Offene Frage",
    "report": "Bericht",
}


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
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "type_label": DRAFT_TYPE_LABELS.get(str(row["type"]), str(row["type"])),
        "project": row["project"],
        "project_name": row["project_name"],
        "updated_at": format_timestamp(row.get("updated_at")),
        "card": card,
        "card_lines": card.splitlines(),
    }


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


def load_inbox_view_model(
    *,
    csrf_token: str,
    inbox_enabled: bool,
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
        "inbox": {
            "groups": group_draft_cards(drafts),
            "csrf_token": csrf_token,
            "enabled": inbox_enabled,
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


class HubViewApplication:
    def __init__(self, *, bind_host: str, csrf_token: str) -> None:
        self.bind_host = bind_host
        self.csrf_token = csrf_token
        self.inbox_enabled = is_loopback_host(bind_host)

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
        elif path.startswith("/projects/"):
            selected_slug = path.removeprefix("/projects/").strip("/") or None
        elif path == "/inbox":
            view_name = "inbox"
            status_code, view_model = load_inbox_view_model(
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
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
                inbox_redirect("error", "Der Entwurf konnte nicht geprüft werden."),
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
                    )
        except ValueError:
            return redirect_response(
                start_response,
                inbox_redirect("error", "Der Entwurf passt nicht zur Review-Aktion."),
            )
        except Exception:
            return redirect_response(
                start_response,
                inbox_redirect("error", "Die Review-Aktion konnte nicht gespeichert werden."),
            )

        if not result:
            return redirect_response(
                start_response,
                inbox_redirect("error", "Dieser Entwurf ist nicht mehr offen."),
            )

        label = "Gemerkt" if decision == "accept" else "Verworfen"
        return redirect_response(
            start_response,
            inbox_redirect("message", f"{label}: Entwurf {result['id']}."),
        )


def create_application(
    *,
    bind_host: str = "127.0.0.1",
    csrf_token: str | None = None,
) -> HubViewApplication:
    return HubViewApplication(
        bind_host=bind_host,
        csrf_token=csrf_token or secrets.token_urlsafe(32),
    )


application = create_application()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hub-view",
        description="Local review surface for Agent Data Hub.",
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

    app = create_application(bind_host=args.host)
    with make_server(args.host, args.port, app) as server:
        print(f"Hub View running on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nHub View stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
