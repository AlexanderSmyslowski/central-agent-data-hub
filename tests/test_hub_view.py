from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
import re
from urllib.parse import urlencode
import uuid

from agent_hub import hub_view
from agent_hub.commands import inbox
from agent_hub.writeback_routing import lint_card_text


DRAFT_ID = uuid.UUID("10000000-0000-4000-8000-000000000701")


def draft_row(*, status: str = "draft") -> dict[str, object]:
    return {
        "id": DRAFT_ID,
        "project_id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
        "project": "central-agent-data-hub",
        "project_name": "Central Agent Data Hub",
        "type": "fact",
        "statement": "Drafts require explicit review.",
        "source": "test",
        "confidence": 0.9,
        "status": status,
        "metadata": {"created_by": "test", "assigned_reviewer": "alice"},
        "created_at": "2026-06-10T10:00:00Z",
        "updated_at": "2026-06-10T10:00:00Z",
    }


def call_app(
    app,
    *,
    method: str = "GET",
    path: str = "/",
    form: dict[str, str] | None = None,
    query: str = "",
    origin: str | None = None,
) -> tuple[dict[str, object], str]:
    captured: dict[str, object] = {}
    body = urlencode(form or {}).encode("utf-8")

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    environ: dict[str, object] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "wsgi.input": BytesIO(body),
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
    }
    if origin:
        environ["HTTP_ORIGIN"] = origin

    response = b"".join(app(environ, start_response)).decode("utf-8")
    return captured, response


class ReviewCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.last_sql = ""
        self.params = None
        self.update_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=None) -> None:
        self.last_sql = sql
        self.params = params
        if sql.lstrip().upper().startswith("UPDATE"):
            self.update_count += 1

    def fetchone(self):
        if "FROM facts" in self.last_sql and "memory.id = %s" in self.last_sql:
            return self.row if self.row["status"] == "draft" else None
        if self.last_sql.lstrip().upper().startswith("UPDATE"):
            if self.row["status"] != "draft":
                return None
            self.row["status"] = self.params[0]
            return {"id": self.row["id"], "status": self.params[0]}
        return None


class ReviewConnection:
    def __init__(self, cursor: ReviewCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.cursor_obj


def test_render_page_includes_local_review_claim() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
        },
        200,
    ).decode("utf-8")

    assert "Hub View" in body
    assert 'class="brand-home" href="/"' in body
    assert "local review surface for Agent Data Hub" in body
    assert "Read surface + review actions" in body
    assert "Prototype language: English." in body


def test_application_rejects_non_get_requests() -> None:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        hub_view.application(
            {"REQUEST_METHOD": "POST", "PATH_INFO": "/"},
            start_response,
        )
    )

    assert captured["status"] == "405 Method Not Allowed"
    assert body == b"Method Not Allowed"


def test_inbox_page_lists_drafts_as_plain_cards() -> None:
    groups = hub_view.group_draft_cards([draft_row()])
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": groups,
                "csrf_token": "token",
                "enabled": True,
                "message": None,
                "error": None,
            },
        },
        200,
        view_name="inbox",
    ).decode("utf-8")

    card = groups[0]["drafts"][0]["card"]
    assert lint_card_text(card) == []
    assert "Remember:" in body
    assert "Source: test." in body
    assert "If wrong:" in body
    assert "owner: alice" in body
    assert 'action="/inbox/accept"' in body
    assert 'action="/inbox/reject"' in body
    assert 'name="csrf_token" value="token"' in body
    assert "Accept" in body
    assert "Reject" in body
    assert "Merken" not in body
    assert "Verwerfen" not in body


def test_inbox_page_empty_state() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": [],
                "csrf_token": "token",
                "enabled": True,
                "message": None,
                "error": None,
            },
        },
        200,
        view_name="inbox",
    ).decode("utf-8")

    assert "No items to review." in body
    assert "When agents suggest memory changes" in body
    assert "Suggested memory changes stay unconfirmed" in body
    assert "Drafts stay unconfirmed" not in body
    assert 'href="/">Back to project overview</a>' in body


def test_inbox_accept_promotes_and_audits(monkeypatch) -> None:
    row = draft_row()
    cur = ReviewCursor(row)
    audit_calls = []
    monkeypatch.setattr(hub_view, "connect", lambda: ReviewConnection(cur))
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )
    captured, _body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
        origin="http://127.0.0.1:8765",
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "Accepted" in headers["Location"]
    assert row["status"] == "verified"
    assert cur.update_count == 1
    assert audit_calls[0][2] == "inbox_accept"
    assert audit_calls[0][5]["review_source"] == "hub_view"
    assert audit_calls[0][5]["reviewed_by"] == "bob"
    assert audit_calls[0][5]["responsible_reviewer"] == "alice"
    assert audit_calls[0][7]["review_source"] == "hub_view"
    assert audit_calls[0][7]["reviewed_by"] == "bob"


def test_inbox_reject_archives_and_audits(monkeypatch) -> None:
    row = draft_row()
    cur = ReviewCursor(row)
    audit_calls = []
    monkeypatch.setattr(hub_view, "connect", lambda: ReviewConnection(cur))
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )
    captured, _body = call_app(
        app,
        method="POST",
        path="/inbox/reject",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "Rejected" in headers["Location"]
    assert row["status"] == "archived"
    assert cur.update_count == 1
    assert audit_calls[0][2] == "inbox_reject"
    assert audit_calls[0][5]["review_source"] == "hub_view"
    assert audit_calls[0][5]["reviewed_by"] == "bob"
    assert audit_calls[0][7]["review_source"] == "hub_view"
    assert audit_calls[0][7]["reviewed_by"] == "bob"


def test_inbox_post_without_or_wrong_csrf_is_forbidden_without_write(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("CSRF failure must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )

    for form in (
        {"draft_id": str(DRAFT_ID), "type": "fact"},
        {"csrf_token": "wrong", "draft_id": str(DRAFT_ID), "type": "fact"},
    ):
        captured, body = call_app(
            app,
            method="POST",
            path="/inbox/accept",
            form=form,
        )

        assert captured["status"] == "403 Forbidden"
        assert "Review token is missing or invalid." in body


def test_inbox_post_with_bad_origin_is_forbidden_without_write(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("bad origin must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )

    captured, body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
        origin="https://example.com",
    )

    assert captured["status"] == "403 Forbidden"
    assert "Origin is not allowed" in body


def test_inbox_post_on_non_draft_shows_error_without_write(monkeypatch) -> None:
    row = draft_row(status="verified")
    cur = ReviewCursor(row)
    audit_calls = []
    monkeypatch.setattr(hub_view, "connect", lambda: ReviewConnection(cur))
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )
    captured, _body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "This%20draft%20is%20no%20longer%20open" in headers["Location"]
    assert row["status"] == "verified"
    assert cur.update_count == 0
    assert audit_calls == []


def test_hub_view_without_reviewer_disables_buttons_and_blocks_post(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("missing reviewer POST must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    groups = hub_view.group_draft_cards([draft_row()])
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": groups,
                "csrf_token": "token",
                "enabled": True,
                "review_enabled": False,
                "reviewer": None,
                "reviewer_error": "reviewer handle is required; set HUB_VIEW_REVIEWER",
                "message": None,
                "error": None,
            },
        },
        200,
        view_name="inbox",
    ).decode("utf-8")

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_error="reviewer handle is required; set HUB_VIEW_REVIEWER",
    )
    captured, post_body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    assert "reviewer handle is required; set HUB_VIEW_REVIEWER" in body
    assert "disabled>Accept</button>" in body
    assert captured["status"] == "403 Forbidden"
    assert "HUB_VIEW_REVIEWER" in post_body


def test_inbox_get_paths_do_not_write(monkeypatch) -> None:
    class ReadOnlyCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_params) -> None:
            if re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql.upper()):
                raise AssertionError("GET /inbox must stay read-only")

        def fetchall(self):
            return []

    class ReadOnlyConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return ReadOnlyCursor()

    monkeypatch.setattr(hub_view, "connect", lambda: ReadOnlyConnection())
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")

    captured, body = call_app(app, method="GET", path="/inbox")

    assert captured["status"] == "200 OK"
    assert "No items to review." in body


def test_inbox_action_get_path_does_not_touch_database(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("GET action path must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")

    captured, body = call_app(app, method="GET", path="/inbox/accept")

    assert captured["status"] == "404 Not Found"
    assert body == "Not Found"


def test_non_loopback_bind_disables_inbox_actions(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("disabled POST must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    groups = hub_view.group_draft_cards([draft_row()])
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": groups,
                "csrf_token": "token",
                "enabled": False,
                "message": None,
                "error": None,
            },
        },
        200,
        view_name="inbox",
        inbox_enabled=False,
    ).decode("utf-8")
    app = hub_view.create_application(bind_host="0.0.0.0", csrf_token="token")
    captured, _post_body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    assert 'action="/inbox/accept"' not in body
    assert "disabled>Accept</button>" in body
    assert "Review actions are disabled" in body
    assert captured["status"] == "403 Forbidden"


def test_application_renders_project_detail(monkeypatch) -> None:
    def fake_load_view_model(
        selected_slug: str | None,
    ) -> tuple[int, dict[str, object]]:
        assert selected_slug == "central-agent-data-hub"
        return 200, {
            "projects": [
                {
                    "name": "Central Agent Data Hub",
                    "slug": "central-agent-data-hub",
                    "status": "active",
                    "description": "Shared memory.",
                    "project_type": "ops",
                    "counts": {
                        "facts": 3,
                        "decisions": 1,
                        "risks": 1,
                        "open_questions": 0,
                        "reports": 1,
                    },
                    "latest_report_title": "Daily",
                    "latest_report_summary": "summary",
                    "updated_at": "2026-06-05 08:00 UTC",
                    "draft_count": 2,
                }
            ],
            "selected_project": {
                "name": "Central Agent Data Hub",
                "slug": "central-agent-data-hub",
                "description": "Shared memory.",
                "status": "active",
                "project_type": "ops",
                "updated_at": "2026-06-05 08:00 UTC",
                "draft_count": 2,
                "counts": {
                    "facts": 3,
                    "decisions": 1,
                    "risks": 1,
                    "open_questions": 0,
                    "reports": 1,
                },
                "quality": {
                    "score": 92,
                    "status": "healthy",
                    "relation_count": 3,
                    "relation_coverage": "0.60",
                    "gaps": [("facts without source", 0)],
                },
                "decisions": [{"decision": "Treat the Hub as verified context.", "rationale": "Shared trust."}],
                "risks": [{"title": "Skipped preflight", "severity": "medium", "impact": "stale context"}],
                "open_questions": [],
                "reports": [{"title": "Daily report", "summary": "A compact review."}],
                "relations": [{"source": "Fact A", "relation_type": "supports", "target": "Decision B"}],
            },
            "not_found_slug": None,
            "draft_total": 2,
        }

    monkeypatch.setattr(hub_view, "load_view_model", fake_load_view_model)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        hub_view.application(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/projects/central-agent-data-hub"},
            start_response,
        )
    ).decode("utf-8")

    assert captured["status"] == "200 OK"
    assert "Central Agent Data Hub" in body
    assert "Selected" in body
    assert "2 items to review" in body
    assert 'href="#reviewed-memory"' in body
    assert 'href="#risks-and-questions"' in body
    assert 'href="#latest-status"' in body
    assert 'href="#quality"' in body
    assert 'id="reviewed-memory"' in body
    assert 'id="risks-and-questions"' in body
    assert 'id="latest-status"' in body
    assert 'id="quality"' in body
    assert "Connect an agent" in body
    assert 'action="/projects/central-agent-data-hub/agent-context"' in body
    assert "Create context pack" in body
    assert "Local agents need one-time setup" in body
    assert "terminal command is only a manual fallback" in body
    assert "Latest status" in body
    assert "all items to review" in body
    assert "Review suggested memory changes" in body
    assert "suggested memory changes" in body
    assert "Drafts are proposed memory changes across projects. They are not reviewed memory until accepted." in body
    assert 'href="/inbox"' in body
    assert "Treat the Hub as verified context." in body
    assert "Fact A" in body
    assert "supports" in body
    assert "alexander" not in body.lower()
    assert "ronak" not in body.lower()


def test_agent_context_route_renders_visible_context_handoff(monkeypatch) -> None:
    def fake_load_agent_context_view_model(
        selected_slug: str,
        task: str,
    ) -> tuple[int, dict[str, object]]:
        assert selected_slug == "central-agent-data-hub"
        assert task == "Review release readiness"
        return 200, {
            "projects": [],
            "selected_project": {
                "name": "Central Agent Data Hub",
                "slug": "central-agent-data-hub",
            },
            "not_found_slug": None,
            "draft_total": 0,
            "agent_context": {
                "project_slug": "central-agent-data-hub",
                "project_name": "Central Agent Data Hub",
                "task": task,
                "counts": {
                    "facts": 3,
                    "decisions": 2,
                    "risks": 1,
                    "open_questions": 1,
                    "reports": 1,
                    "relations": 2,
                    "pending_drafts": 0,
                },
                "source_count": 7,
                "gap_summary": {
                    "stale": 0,
                    "unanswered": 1,
                    "blind_spots": 0,
                    "pending_drafts": 0,
                },
                "influence": [
                    "Reviewed decisions become task constraints for the agent.",
                    "Verified facts may be used as project assumptions.",
                ],
                "commands": {
                    "prepare": (
                        "agent-hub prepare --project central-agent-data-hub "
                        "--task 'Review release readiness'"
                    ),
                    "agent_start": (
                        "scripts/agent_start.sh --project central-agent-data-hub "
                        "--query 'Review release readiness' --review"
                    ),
                },
                "local_agent": {
                    "install_mcp": "pip install -e '.[mcp]'",
                    "claude_mcp": "claude mcp add agent-data-hub -- agent-hub mcp-serve",
                    "mcp_json": '{"mcpServers": {"agent-data-hub": {"command": "agent-hub"}}}',
                    "startup_instruction": (
                        "At the start of ADH-related work:\n"
                        "- ask Agent Data Hub for reviewed context"
                    ),
                },
                "markdown": "# Agent Context Pack\n\n## Goal\nReview release readiness\n",
            },
        }

    monkeypatch.setattr(
        hub_view,
        "load_agent_context_view_model",
        fake_load_agent_context_view_model,
    )
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")

    captured, body = call_app(
        app,
        path="/projects/central-agent-data-hub/agent-context",
        query=urlencode({"task": "Review release readiness"}),
    )

    assert captured["status"] == "200 OK"
    assert "ADH context loaded" in body
    assert "This is the visible handoff" in body
    assert "Review release readiness" in body
    assert "Source of truth: local Agent Data Hub database" in body
    assert "How this should influence the agent" in body
    assert "Reviewed decisions become task constraints" in body
    assert "Known gaps" in body
    assert "1 unanswered questions" in body
    assert "Local agent" in body
    assert "One-time setup" in body
    assert "Add ADH as a local MCP server once" in body
    assert "claude mcp add agent-data-hub" in body
    assert "Manual fallback" in body
    assert "it is not automation" in body
    assert "ADH cannot prove that an unconnected agent read the context" in body
    assert "agent-hub prepare --project central-agent-data-hub" in body
    assert "scripts/agent_start.sh --project central-agent-data-hub" in body
    assert "# Agent Context Pack" in body
    assert 'href="/projects/central-agent-data-hub"' in body


def test_agent_context_commands_are_shell_quoted_for_copy_paste(monkeypatch) -> None:
    monkeypatch.setattr(hub_view, "prepare_markdown", lambda _payload: "# Agent Context Pack")

    view = hub_view.build_agent_context_view(
        {
            "project": {
                "id": "project-id",
                "slug": "central-agent-data-hub",
                "name": "Central Agent Data Hub",
            },
            "task": "Review Ronak's release notes",
            "verified_project_state": [],
            "relevant_decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
            "relations": [],
            "drafts_pending_review": {},
            "context_trail": {
                "included_counts": {
                    "facts": 0,
                    "decisions": 0,
                    "risks": 0,
                    "open_questions": 0,
                    "reports": 0,
                    "relations": 0,
                },
                "sources": [],
                "excluded": {"note": "none"},
                "task_selection": {
                    "mode": "deterministic",
                    "note": "test",
                    "tie_breaking": "test",
                },
                "gap_summary": {},
            },
            "goal": "Review Ronak's release notes",
            "constraints": [],
            "allowed_actions": [],
            "requires_human_approval": [],
            "suggested_checks": [],
            "gaps": {"summary": {}},
        }
    )

    assert (
        view["commands"]["prepare"]
        == "agent-hub prepare --project central-agent-data-hub --task 'Review Ronak'\"'\"'s release notes'"
    )
    assert (
        view["commands"]["agent_start"]
        == "scripts/agent_start.sh --project central-agent-data-hub --query 'Review Ronak'\"'\"'s release notes' --review"
    )
    assert view["local_agent"]["install_mcp"] == "pip install -e '.[mcp]'"
    assert (
        view["local_agent"]["claude_mcp"]
        == "claude mcp add agent-data-hub -- agent-hub mcp-serve"
    )
    assert '"mcpServers"' in view["local_agent"]["mcp_json"]
    assert '"agent-data-hub"' in view["local_agent"]["mcp_json"]
    assert "Review Ronak's release notes" in view["local_agent"]["startup_instruction"]


def test_format_timestamp_for_datetime() -> None:
    value = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    assert hub_view.format_timestamp(value) == "2026-06-05 08:00 UTC"


def test_port_is_available_detects_bound_socket() -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
        assert hub_view.port_is_available(host, port) is False
