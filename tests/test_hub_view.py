from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
import re
import sys
from urllib.parse import urlencode
import uuid

import pytest

from agent_hub import hub_view
from agent_hub import hub_view_models
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


def test_build_project_cards_batches_counts_and_latest_reports(monkeypatch) -> None:
    projects = [
        {
            "id": "project-1",
            "name": "Project One",
            "slug": "project-one",
            "status": "active",
            "description": "First project",
            "metadata": {"project_type": "demo"},
            "updated_at": "2026-06-28T10:00:00+00:00",
        },
        {
            "id": "project-2",
            "name": "Project Two",
            "slug": "project-two",
            "status": "active",
            "description": "Second project",
            "metadata": {},
            "updated_at": "2026-06-28T11:00:00+00:00",
        },
    ]
    calls: list[tuple[str, list[object]]] = []

    def fake_counts(_cur, project_ids):
        calls.append(("counts", list(project_ids)))
        return {
            "project-1": {
                "documents": 0,
                "facts": 3,
                "decisions": 1,
                "open_questions": 0,
                "risks": 1,
                "reports": 2,
            },
            "project-2": {
                "documents": 0,
                "facts": 0,
                "decisions": 0,
                "open_questions": 1,
                "risks": 0,
                "reports": 0,
            },
        }

    def fake_latest_reports(_cur, project_ids):
        calls.append(("latest_reports", list(project_ids)))
        return {
            "project-1": {
                "title": "Latest report",
                "summary": "A compact summary.",
                "updated_at": "2026-06-28T12:00:00+00:00",
            }
        }

    monkeypatch.setattr(hub_view_models, "fetch_project_card_counts", fake_counts)
    monkeypatch.setattr(
        hub_view_models,
        "fetch_latest_reports_by_project",
        fake_latest_reports,
    )

    cards = hub_view_models.build_project_cards(
        object(),
        projects,
        {"project-two": 4},
    )

    assert calls == [
        ("counts", ["project-1", "project-2"]),
        ("latest_reports", ["project-1", "project-2"]),
    ]
    assert cards[0]["counts"]["facts"] == 3
    assert cards[0]["latest_report_title"] == "Latest report"
    assert cards[1]["counts"]["open_questions"] == 1
    assert cards[1]["draft_count"] == 4
    assert cards[1]["latest_report_title"] is None


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


class EmptyCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args):
        raise AssertionError("test should patch fetch_project instead of querying")


class EmptyConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return EmptyCursor()


def test_codex_setup_post_installs_agents_block_with_explicit_click(monkeypatch, tmp_path) -> None:
    project = {
        "id": "project-id",
        "slug": "central-agent-data-hub-demo",
        "name": "Central Agent Data Hub Demo",
        "status": "active",
        "metadata": {"local_path": str(tmp_path)},
    }
    monkeypatch.setattr(hub_view, "connect", lambda: EmptyConnection())
    monkeypatch.setattr(hub_view, "fetch_project", lambda _cur, slug: project if slug == project["slug"] else None)

    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")
    captured, _body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "token", "task": "Review demo"},
        origin="http://127.0.0.1:8765",
    )

    headers = dict(captured["headers"])
    target = tmp_path / "AGENTS.md"
    assert captured["status"] == "303 See Other"
    assert "setup_message=Codex%20setup%20installed%20in%20AGENTS.md" in headers["Location"]
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "<!-- CENTRAL-AGENT-DATA-HUB:START -->" in text
    assert "Project slug: `central-agent-data-hub-demo`" in text
    assert "agent_start.sh --project central-agent-data-hub-demo" in text


def test_codex_setup_post_without_csrf_is_forbidden_without_write(monkeypatch, tmp_path) -> None:
    def fail_connect():
        raise AssertionError("CSRF failure must not touch project lookup or files")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")
    captured, body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "wrong", "task": "Review demo"},
    )

    assert captured["status"] == "403 Forbidden"
    assert "Setup token is missing or invalid." in body
    assert not (tmp_path / "AGENTS.md").exists()


def test_codex_setup_post_on_non_loopback_is_forbidden_without_write(monkeypatch, tmp_path) -> None:
    def fail_connect():
        raise AssertionError("non-loopback setup must not touch project lookup or files")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(bind_host="0.0.0.0", csrf_token="token")
    captured, body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "token", "task": "Review demo"},
    )

    assert captured["status"] == "403 Forbidden"
    assert "only available on loopback" in body
    assert not (tmp_path / "AGENTS.md").exists()


def test_codex_setup_post_with_unknown_project_path_redirects_without_write(monkeypatch, tmp_path) -> None:
    project = {
        "id": "project-id",
        "slug": "central-agent-data-hub-demo",
        "name": "Central Agent Data Hub Demo",
        "status": "active",
        "metadata": {},
    }
    monkeypatch.setenv("AGENT_HUB_PUBLIC_DEMO", "1")
    monkeypatch.setattr(hub_view, "connect", lambda: EmptyConnection())
    monkeypatch.setattr(hub_view, "fetch_project", lambda _cur, _slug: project)

    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")
    captured, _body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "token", "task": "Review demo"},
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "setup_error=Codex%20setup%20needs%20a%20registered%20project%20folder" in headers["Location"]
    assert not (tmp_path / "AGENTS.md").exists()


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


def test_lan_read_bind_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="--allow-lan-read"):
        hub_view.validate_lan_read_bind("0.0.0.0", allow_lan_read=False)


def test_lan_read_bind_allows_loopback_without_opt_in() -> None:
    assert hub_view.validate_lan_read_bind(
        "127.0.0.1",
        allow_lan_read=False,
    ) is None


def test_lan_read_bind_returns_warning_when_explicitly_allowed() -> None:
    warning = hub_view.validate_lan_read_bind("0.0.0.0", allow_lan_read=True)

    assert warning is not None
    assert "exposes reviewed memory read-only on the local network" in warning
    assert "writes stay disabled unless Hub View is bound to loopback" in warning


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
                "facts": [{"statement": "Reviewed facts are visible in Hub View.", "source": "demo", "confidence": 0.9}],
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
    assert 'aria-label="Project actions"' in body
    assert "Use ADH with an agent" in body
    assert "Prepare the reviewed context before work starts." in body
    assert "Review suggested changes" in body
    assert "Find reviewed memory" in body
    assert "Filter visible facts, decisions, risks, questions, reports, and relations." in body
    assert "Check memory quality" in body
    assert 'href="#connect-agent"' in body
    assert 'href="#memory-explorer"' in body
    assert 'href="#reviewed-memory"' in body
    assert 'href="#risks-and-questions"' in body
    assert 'href="#latest-status"' in body
    assert 'href="#quality"' in body
    assert 'id="reviewed-memory"' in body
    assert 'id="memory-explorer"' in body
    assert 'id="risks-and-questions"' in body
    assert 'id="latest-status"' in body
    assert 'id="quality"' in body
    assert 'id="relations"' in body
    assert 'data-memory-explorer' in body
    assert 'data-memory-filter' in body
    assert 'data-memory-clear' in body
    assert 'data-memory-results' in body
    assert 'data-memory-hits' in body
    assert 'data-memory-empty' in body
    assert "Search this page" in body
    assert "Matches appear below while the page sections are filtered." in body
    assert "Showing visible reviewed memory on this page." in body
    assert "No visible memory matches this filter." in body
    assert "itemHaystack" in body
    assert 'getAttribute("data-memory-type")' in body
    assert "memory-filter-hit" in body
    assert 'data-memory-type="decision"' in body
    assert 'data-memory-type="fact"' in body
    assert 'data-memory-type="risk"' in body
    assert 'data-memory-type="report"' in body
    assert 'data-memory-type="latest status"' in body
    assert 'data-memory-type="relation"' in body
    assert "Connect an agent" in body
    assert 'action="/projects/central-agent-data-hub/agent-context"' in body
    assert "Prepare agent handoff" in body
    assert "The next screen shows what ADH would give the agent" in body
    assert "Task for the agent" in body
    assert "primary-button" in body
    assert "Latest status" in body
    assert "all items to review" in body
    assert "Review suggested memory changes" in body
    assert "suggested memory changes" in body
    assert "Drafts are proposed memory changes across projects. They are not reviewed memory until accepted." in body
    assert 'href="/inbox"' in body
    assert "Treat the Hub as verified context." in body
    assert "Reviewed facts are visible in Hub View." in body
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
                    "setup_command": (
                        "python -m pip install -e '.[mcp]' && "
                        "claude mcp add agent-data-hub -- python -m agent_hub.cli mcp-serve"
                    ),
                    "codex": {
                        "can_install": True,
                        "project_path": "/demo/project",
                        "target_path": "/demo/project/AGENTS.md",
                        "target_file": "AGENTS.md",
                        "action": "create",
                        "preview": "<!-- CENTRAL-AGENT-DATA-HUB:START -->\nProject slug: `central-agent-data-hub`\n",
                        "error": None,
                        "verification": {
                            "state": "missing",
                            "label": "Codex setup not installed yet",
                            "detail": "Install the ADH block into AGENTS.md so Codex reads it before work.",
                        },
                    },
                    "codex_command": (
                        "scripts/install_repo_agent_memory.sh --repo /demo/project "
                        "--project central-agent-data-hub"
                    ),
                    "codex_project_path": "/demo/project",
                    "install_mcp": "pip install -e '.[mcp]'",
                    "claude_mcp": "claude mcp add agent-data-hub -- agent-hub mcp-serve",
                    "mcp_json": '{"mcpServers": {"agent-data-hub": {"command": "agent-hub"}}}',
                    "startup_instruction": (
                        "At the start of ADH-related work:\n"
                        "- request reviewed context from Agent Data Hub"
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
    assert "Connect your agent" in body
    assert 'aria-label="Agent connection steps"' in body
    assert "Choose agent" in body
    assert "Connect once" in body
    assert "Check handoff" in body
    assert "Choose your agent" in body
    assert 'href="#agent-chatbot"' in body
    assert 'href="#agent-codex"' in body
    assert 'href="#agent-claude"' in body
    assert 'href="#agent-custom"' in body
    assert 'href="#agent-mcp"' in body
    assert 'href="#agent-terminal"' in body
    assert "Claude Code" in body
    assert "Codex" in body
    assert 'aria-label="Connection verification"' in body
    assert "ADH can check Codex here" in body
    assert "Codex setup not installed yet" in body
    assert "Manual check needed" in body
    assert "Persistent rule needed" in body
    assert "Per-task copy/paste" in body
    assert "must be checked in their own app" in body
    assert "Start Claude Code after setup" in body
    assert body.index("<h3>Codex</h3>") < body.index("<h3>Claude Code</h3>")
    assert "Hermes or custom agent" in body
    assert "Other MCP-compatible agent" in body
    assert "Manual every task" in body
    assert "One local click" in body
    assert "One copied command" in body
    assert "Persistent instruction" in body
    assert "Config shape" in body
    assert "Temporary fallback" in body
    assert "One-time setup" in body
    assert "Copy Claude setup" in body
    assert "Install Codex setup" in body
    assert "Copy fallback command" in body
    assert "Copy startup rule" in body
    assert "Copy MCP config" in body
    assert "Jump to chatbot text" in body
    assert "ADH can check this setup here" in body
    assert "Show Claude manual setup pieces" in body
    assert "It never runs an agent" in body
    assert "writes only after an explicit local click" in body
    assert "is instructed to request ADH context" in body
    assert "AGENTS.md" in body
    assert "ADH knows this project" in body
    assert "Project folder:" in body
    assert "Target file:" in body
    assert "Planned action:" in body
    assert "Preview AGENTS.md block" in body
    assert "/demo/project" in body
    assert "Run this from the project repository" not in body
    assert "$PWD" not in body
    assert "project-repo-path" not in body
    assert "Add ADH as a local MCP server once" in body
    assert "claude mcp add agent-data-hub" in body
    assert "Manual fallback" in body
    assert "it is not automation" in body
    assert "For local agents: start a new task" in body
    assert "ADH cannot prove that an unconnected agent read the context" in body
    assert 'data-copy-target="claude-code-setup-command"' in body
    assert 'data-copy-target="codex-setup-command"' in body
    assert 'data-copy-target="custom-startup-instruction"' in body
    assert 'data-copy-target="install-mcp-command"' in body
    assert 'data-copy-target="claude-mcp-command"' in body
    assert 'data-copy-target="mcp-json-config"' in body
    assert 'data-copy-target="startup-instruction"' in body
    assert 'data-copy-target="agent-start-command"' in body
    assert 'data-copy-target="prepare-command"' in body
    assert 'data-copy-target="chatbot-context-pack"' in body
    assert "Copy chatbot text" in body
    assert "agent-hub prepare --project central-agent-data-hub" in body
    assert "scripts/agent_start.sh --project central-agent-data-hub" in body
    assert "# Agent Context Pack" in body
    assert 'href="/projects/central-agent-data-hub"' in body


def test_agent_context_commands_are_shell_quoted_for_copy_paste(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hub_view, "prepare_markdown", lambda _payload: "# Agent Context Pack")
    project_path = str(tmp_path)

    view = hub_view.build_agent_context_view(
        {
            "project": {
                "id": "project-id",
                "slug": "central-agent-data-hub",
                "name": "Central Agent Data Hub",
                "metadata": {"local_path": project_path},
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
    assert (
        view["local_agent"]["setup_command"]
        == f"{hub_view.shell_command([sys.executable, '-m', 'pip', 'install', '-e', '.[mcp]'])} && "
        f"{hub_view.shell_command(['claude', 'mcp', 'add', 'agent-data-hub', '--', sys.executable, '-m', 'agent_hub.cli', 'mcp-serve'])}"
    )
    assert view["local_agent"]["install_mcp"] == hub_view.shell_command(
        [sys.executable, "-m", "pip", "install", "-e", ".[mcp]"]
    )
    install_script = (
        hub_view.Path(hub_view.__file__).resolve().parents[1] / "scripts" / "install_repo_agent_memory.sh"
    )
    assert view["local_agent"]["codex_command"] == hub_view.shell_command(
        [
            str(install_script),
            "--repo",
            project_path,
            "--project",
            "central-agent-data-hub",
        ]
    )
    assert view["local_agent"]["codex_project_path"] == project_path
    assert view["local_agent"]["codex"]["project_path"] == project_path
    assert view["local_agent"]["codex"]["target_file"] == "AGENTS.md"
    assert view["local_agent"]["codex"]["action"] == "create"
    assert "<!-- CENTRAL-AGENT-DATA-HUB:START -->" in view["local_agent"]["codex"]["preview"]
    assert (
        view["local_agent"]["claude_mcp"]
        == hub_view.shell_command(
            [
                "claude",
                "mcp",
                "add",
                "agent-data-hub",
                "--",
                sys.executable,
                "-m",
                "agent_hub.cli",
                "mcp-serve",
            ]
        )
    )
    assert '"mcpServers"' in view["local_agent"]["mcp_json"]
    assert sys.executable in view["local_agent"]["mcp_json"]
    assert '"agent_hub.cli"' in view["local_agent"]["mcp_json"]
    assert '"agent-data-hub"' in view["local_agent"]["mcp_json"]
    assert "request reviewed context from Agent Data Hub" in view["local_agent"]["startup_instruction"]
    assert "Review Ronak's release notes" in view["local_agent"]["startup_instruction"]


def test_codex_setup_view_reports_connection_status(tmp_path) -> None:
    repo_root = hub_view.Path(hub_view.__file__).resolve().parents[1]
    project = {
        "id": "project-id",
        "slug": "central-agent-data-hub",
        "name": "Central Agent Data Hub",
        "metadata": {"local_path": str(tmp_path)},
    }

    missing = hub_view.build_codex_setup_view(project, repo_root)

    assert missing["action"] == "create"
    assert missing["verification"]["state"] == "missing"
    assert missing["verification"]["label"] == "Codex setup not installed yet"

    (tmp_path / "AGENTS.md").write_text(str(missing["preview"]).rstrip() + "\n", encoding="utf-8")
    connected = hub_view.build_codex_setup_view(project, repo_root)

    assert connected["action"] == "unchanged"
    assert connected["verification"]["state"] == "connected"
    assert connected["verification"]["label"] == "Codex setup verified"


def test_agent_context_omits_codex_setup_when_project_path_is_unknown(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_HUB_PUBLIC_DEMO", raising=False)
    monkeypatch.setattr(hub_view, "prepare_markdown", lambda _payload: "# Agent Context Pack")

    view = hub_view.build_agent_context_view(
        {
            "project": {
                "id": "project-id",
                "slug": "unknown-project",
                "name": "Unknown Project",
            },
            "task": "Review setup",
            "verified_project_state": [],
            "relevant_decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
            "relations": [],
            "drafts_pending_review": {},
            "context_trail": {
                "included_counts": {},
                "sources": [],
                "excluded": {},
                "task_selection": {},
                "gap_summary": {},
            },
            "goal": "Review setup",
            "constraints": [],
            "allowed_actions": [],
            "requires_human_approval": [],
            "suggested_checks": [],
            "gaps": {"summary": {}},
        }
    )

    assert view["local_agent"]["codex_command"] is None
    assert view["local_agent"]["codex_project_path"] is None
    assert view["local_agent"]["codex"]["can_install"] is False
    assert view["local_agent"]["codex"]["verification"]["state"] == "unknown"


def test_agent_context_uses_public_demo_checkout_for_codex_setup(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HUB_PUBLIC_DEMO", "1")
    monkeypatch.setattr(hub_view, "prepare_markdown", lambda _payload: "# Agent Context Pack")

    view = hub_view.build_agent_context_view(
        {
            "project": {
                "id": "project-id",
                "slug": "central-agent-data-hub-demo",
                "name": "Central Agent Data Hub Demo",
            },
            "task": "Review demo",
            "verified_project_state": [],
            "relevant_decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
            "relations": [],
            "drafts_pending_review": {},
            "context_trail": {
                "included_counts": {},
                "sources": [],
                "excluded": {},
                "task_selection": {},
                "gap_summary": {},
            },
            "goal": "Review demo",
            "constraints": [],
            "allowed_actions": [],
            "requires_human_approval": [],
            "suggested_checks": [],
            "gaps": {"summary": {}},
        }
    )

    repo_root = str(hub_view.Path(hub_view.__file__).resolve().parents[1])
    assert view["local_agent"]["codex_project_path"] == repo_root
    assert view["local_agent"]["codex"]["can_install"] is False
    assert view["local_agent"]["codex"]["demo_only"] is True
    assert view["local_agent"]["codex"]["verification"]["state"] == "demo"
    assert view["local_agent"]["codex"]["target_path"] == f"{repo_root}/AGENTS.md"
    install_script = (
        hub_view.Path(hub_view.__file__).resolve().parents[1] / "scripts" / "install_repo_agent_memory.sh"
    )
    assert view["local_agent"]["codex_command"] == hub_view.shell_command(
        [
            str(install_script),
            "--repo",
            repo_root,
            "--project",
            "central-agent-data-hub-demo",
            "--dry-run",
        ]
    )


def test_format_timestamp_for_datetime() -> None:
    value = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    assert hub_view.format_timestamp(value) == "2026-06-05 08:00 UTC"


def test_port_is_available_detects_bound_socket() -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
        assert hub_view.port_is_available(host, port) is False
