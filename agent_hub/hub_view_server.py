"""Hub View WSGI application and command-line server."""

from __future__ import annotations

import argparse
import errno
import ipaddress
import os
from pathlib import Path
import secrets
import socket
import sys
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlencode, urlparse
from wsgiref.simple_server import make_server

from agent_hub.commands.common import fetch_project
from agent_hub.commands.inbox import review_draft_by_id
from agent_hub.db import connect
from agent_hub.hub_view_models import (
    DEFAULT_AGENT_TASK,
    load_agent_context_view_model,
    load_inbox_view_model,
    load_memory_library_view_model,
    load_memory_item_view_model,
    load_review_activity_view_model,
    load_view_model,
    metadata_project_local_path,
    render_page,
    hub_view_static_dir,
)
from agent_hub.hub_view_i18n import resolve_language, with_language
from agent_hub.repo_agent_memory import (
    DEFAULT_TARGET_FILE,
    RepoAgentMemoryError,
    install_repo_agent_memory,
    plan_repo_agent_memory,
)
from agent_hub.reviewers import resolve_required_reviewer

def _compat_attr(name: str, fallback):
    module = sys.modules.get("agent_hub.hub_view")
    return getattr(module, name, fallback) if module is not None else fallback

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

def static_response(
    start_response: Callable[[str, list[tuple[str, str]]], Any],
    asset_name: str,
) -> list[bytes]:
    content_types = {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
    }
    asset_path = Path(asset_name)
    if asset_path.name != asset_name or asset_path.suffix not in content_types:
        return text_response(start_response, "404 Not Found", "Not Found")

    path = hub_view_static_dir() / asset_name
    if not path.is_file():
        return text_response(start_response, "404 Not Found", "Not Found")

    body = path.read_bytes()
    start_response(
        "200 OK",
        [
            ("Content-Type", content_types[path.suffix]),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
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

def inbox_redirect(param: str, message: str, *, language: str = "en") -> str:
    return with_language(f"/inbox?{param}={quote(message)}", language)

def inbox_result_redirect(
    result: dict[str, Any],
    *,
    decision: str,
    language: str = "en",
) -> str:
    params = {
        "review_result": "accepted" if decision == "accept" else "rejected",
        "review_item": str(result.get("id") or ""),
        "review_type": str(result.get("type") or ""),
        "review_status": str(result.get("status") or ""),
        "review_project": str(result.get("project") or ""),
        "reviewed_by": str(result.get("reviewed_by") or ""),
        "review_source": str(result.get("review_source") or ""),
    }
    return with_language(f"/inbox?{urlencode(params)}#review-result", language)

def agent_context_redirect(
    slug: str,
    task: str,
    param: str,
    message: str,
    *,
    language: str = "en",
) -> str:
    return with_language(
        f"/projects/{quote(slug, safe='')}/agent-context"
        f"?task={quote(task)}&{param}={quote(message)}",
        language,
    )

def project_action_slug(path: str, suffix: str) -> str | None:
    if not path.startswith("/projects/") or not path.endswith(suffix):
        return None
    slug = path.removeprefix("/projects/").removesuffix(suffix).strip("/")
    return slug or None

def memory_item_path(path: str) -> tuple[str, str, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) != 5 or parts[0] != "projects" or parts[2] != "memory":
        return None
    slug, item_type, item_id = parts[1], parts[3], parts[4]
    if not slug or not item_type or not item_id:
        return None
    return slug, item_type, item_id

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
        language = resolve_language(query_value(environ, "lang"))

        if method == "GET":
            return self.handle_get(path, environ, start_response, language=language)
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
        *,
        language: str,
    ) -> list[bytes]:
        selected_slug: str | None = None
        view_name = "projects"
        if path == "/":
            selected_slug = None
        elif path.startswith("/static/"):
            return static_response(
                start_response,
                path.removeprefix("/static/"),
            )
        elif path.startswith("/projects/") and path.endswith("/memory"):
            view_name = "memory_library"
            selected_slug = path.removeprefix("/projects/").removesuffix("/memory").strip("/")
            if not selected_slug:
                return text_response(start_response, "404 Not Found", "Not Found")
            status_code, view_model = _compat_attr(
                "load_memory_library_view_model",
                load_memory_library_view_model,
            )(selected_slug, query_value(environ, "type"))
            body = _compat_attr("render_page", render_page)(
                view_model,
                status_code,
                view_name=view_name,
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
                language=language,
                current_path=path,
                query_string=str(environ.get("QUERY_STRING") or ""),
            )
            return html_response(start_response, status_code, body)
        elif path.startswith("/projects/") and path.endswith("/agent-context"):
            view_name = "agent_context"
            selected_slug = path.removeprefix("/projects/").removesuffix("/agent-context").strip("/")
            if not selected_slug:
                return text_response(start_response, "404 Not Found", "Not Found")
            status_code, view_model = _compat_attr(
                "load_agent_context_view_model",
                load_agent_context_view_model,
            )(
                selected_slug,
                query_value(environ, "task") or DEFAULT_AGENT_TASK,
            )
            if view_model.get("agent_context"):
                view_model["agent_context"]["setup_message"] = query_value(environ, "setup_message")
                view_model["agent_context"]["setup_error"] = query_value(environ, "setup_error")
            body = _compat_attr("render_page", render_page)(
                view_model,
                status_code,
                view_name=view_name,
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
                language=language,
                current_path=path,
                query_string=str(environ.get("QUERY_STRING") or ""),
            )
            return html_response(start_response, status_code, body)
        elif (memory_path := memory_item_path(path)) is not None:
            view_name = "memory_item"
            selected_slug, item_type, item_id = memory_path
            status_code, view_model = _compat_attr(
                "load_memory_item_view_model",
                load_memory_item_view_model,
            )(selected_slug, item_type, item_id)
            body = _compat_attr("render_page", render_page)(
                view_model,
                status_code,
                view_name=view_name,
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
                language=language,
                current_path=path,
                query_string=str(environ.get("QUERY_STRING") or ""),
            )
            return html_response(start_response, status_code, body)
        elif path.startswith("/projects/"):
            selected_slug = path.removeprefix("/projects/").strip("/") or None
        elif path == "/inbox":
            view_name = "inbox"
            status_code, view_model = _compat_attr(
                "load_inbox_view_model",
                load_inbox_view_model,
            )(
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
                reviewer_handle=self.reviewer_handle,
                reviewer_error=self.reviewer_error,
                message=query_value(environ, "message"),
                error_message=query_value(environ, "error"),
                review_result=query_value(environ, "review_result"),
                review_item=query_value(environ, "review_item"),
                review_type=query_value(environ, "review_type"),
                review_status=query_value(environ, "review_status"),
                review_project=query_value(environ, "review_project"),
                reviewed_by=query_value(environ, "reviewed_by"),
                review_source=query_value(environ, "review_source"),
            )
            body = _compat_attr("render_page", render_page)(
                view_model,
                status_code,
                view_name=view_name,
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
                language=language,
                current_path=path,
                query_string=str(environ.get("QUERY_STRING") or ""),
            )
            return html_response(start_response, status_code, body)
        elif path == "/inbox/activity":
            view_name = "review_activity"
            status_code, view_model = _compat_attr(
                "load_review_activity_view_model",
                load_review_activity_view_model,
            )()
            body = _compat_attr("render_page", render_page)(
                view_model,
                status_code,
                view_name=view_name,
                csrf_token=self.csrf_token,
                inbox_enabled=self.inbox_enabled,
                language=language,
                current_path=path,
                query_string=str(environ.get("QUERY_STRING") or ""),
            )
            return html_response(start_response, status_code, body)
        else:
            return text_response(start_response, "404 Not Found", "Not Found")

        status_code, view_model = _compat_attr("load_view_model", load_view_model)(
            selected_slug
        )
        body = _compat_attr("render_page", render_page)(
            view_model,
            status_code,
            view_name=view_name,
            csrf_token=self.csrf_token,
            inbox_enabled=self.inbox_enabled,
            language=language,
            current_path=path,
            query_string=str(environ.get("QUERY_STRING") or ""),
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
        language = resolve_language(form.get("lang"))
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
                inbox_redirect("error", "The draft could not be reviewed.", language=language),
            )

        try:
            with _compat_attr("connect", connect)() as conn:
                with conn.cursor() as cur:
                    result = _compat_attr("review_draft_by_id", review_draft_by_id)(
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
                inbox_redirect(
                    "error",
                    "The draft does not match this review action.",
                    language=language,
                ),
            )
        except Exception:
            return redirect_response(
                start_response,
                inbox_redirect(
                    "error",
                    "The review action could not be saved.",
                    language=language,
                ),
            )

        if not result:
            return redirect_response(
                start_response,
                inbox_redirect("error", "This draft is no longer open.", language=language),
            )

        return redirect_response(
            start_response,
            inbox_result_redirect(result, decision=decision, language=language),
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
        language = resolve_language(form.get("lang"))

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
            with _compat_attr("connect", connect)() as conn:
                with conn.cursor() as cur:
                    project = _compat_attr("fetch_project", fetch_project)(
                        cur,
                        selected_slug,
                    )
            if project is None or project.get("status") != "active":
                return redirect_response(
                    start_response,
                    agent_context_redirect(
                        selected_slug,
                        task,
                        "setup_error",
                        "Project not found.",
                        language=language,
                    ),
                )
            repo_root = Path(__file__).resolve().parents[1]
            project_path = _compat_attr(
                "metadata_project_local_path",
                metadata_project_local_path,
            )(project)
            if project_path is None:
                return redirect_response(
                    start_response,
                    agent_context_redirect(
                        selected_slug,
                        task,
                        "setup_error",
                        "Codex setup needs a registered project folder.",
                        language=language,
                    ),
                )
            plan = _compat_attr("plan_repo_agent_memory", plan_repo_agent_memory)(
                repo_path=project_path,
                project_slug=str(project["slug"]),
                hub_root=repo_root,
                target_file=DEFAULT_TARGET_FILE,
            )
            _compat_attr("install_repo_agent_memory", install_repo_agent_memory)(plan)
        except (OSError, RepoAgentMemoryError):
            return redirect_response(
                start_response,
                agent_context_redirect(
                    selected_slug,
                    task,
                    "setup_error",
                    "Codex setup could not be installed.",
                    language=language,
                ),
            )

        if plan.action == "unchanged":
            message = f"Codex setup already up to date in {plan.target_file}."
        else:
            message = f"Codex setup installed in {plan.target_file}."
        return redirect_response(
            start_response,
            agent_context_redirect(selected_slug, task, "setup_message", message, language=language),
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
    parser.add_argument(
        "--reviewer",
        help=(
            "Reviewer handle for local Review Inbox actions. This is "
            "attribution, not authentication."
        ),
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

    reviewer_handle = None
    if args.reviewer:
        try:
            reviewer_handle = resolve_required_reviewer(
                args.reviewer,
                env_var="HUB_VIEW_REVIEWER",
            )
        except ValueError as exc:
            parser.error(str(exc))

    app = create_application(bind_host=args.host, reviewer_handle=reviewer_handle)
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
