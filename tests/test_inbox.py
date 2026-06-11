from __future__ import annotations

import json
import uuid

from agent_hub import cli
from agent_hub.commands import inbox


def draft_row() -> dict[str, object]:
    return {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000701"),
        "project_id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
        "project": "central-agent-data-hub",
        "project_name": "Central Agent Data Hub",
        "type": "fact",
        "statement": "Drafts require explicit review.",
        "source": "test",
        "confidence": 0.9,
        "status": "draft",
        "metadata": {"created_by": "test", "assigned_reviewer": "alice"},
        "created_at": "2026-06-10T10:00:00Z",
        "updated_at": "2026-06-10T10:00:00Z",
    }


class ReviewCursor:
    def __init__(self) -> None:
        self.params = None

    def execute(self, _sql, params=None) -> None:
        self.params = params

    def fetchone(self):
        return {"id": draft_row()["id"], "status": self.params[0]}


def test_inbox_accept_promotes_draft_and_writes_audit(monkeypatch) -> None:
    audit_calls = []
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(
        inbox,
        "log_agent_action",
        lambda *args: audit_calls.append(args),
    )
    cur = ReviewCursor()

    result = inbox.review_draft(
        cur,
        draft_row(),
        decision="accept",
        agent_slug="codex",
        agent_name="Codex",
        reviewed_by="bob",
        review_source="cli",
    )

    assert result["status"] == "verified"
    assert cur.params[0] == "verified"
    metadata = json.loads(cur.params[1])
    assert metadata["agent_hub_review"] == {
        "decision": "accept",
        "previous_status": "draft",
        "next_status": "verified",
        "reviewed_by": "bob",
        "review_source": "cli",
        "responsible_reviewer": "alice",
        "resolution_reason": "item metadata assigned_reviewer",
    }
    assert audit_calls[0][2] == "inbox_accept"
    assert audit_calls[0][5]["reviewed_by"] == "bob"
    assert audit_calls[0][5]["review_source"] == "cli"
    assert audit_calls[0][5]["responsible_reviewer"] == "alice"
    assert audit_calls[0][6]["reviewed_by"] == "bob"
    assert audit_calls[0][7]["reviewed_by"] == "bob"
    assert audit_calls[0][7]["review_source"] == "cli"
    assert audit_calls[0][7]["responsible_reviewer"] == "alice"


def test_inbox_reject_archives_draft_and_writes_audit(monkeypatch) -> None:
    audit_calls = []
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(
        inbox,
        "log_agent_action",
        lambda *args: audit_calls.append(args),
    )
    cur = ReviewCursor()

    result = inbox.review_draft(
        cur,
        draft_row(),
        decision="reject",
        agent_slug="codex",
        agent_name="Codex",
        reviewed_by="bob",
        review_source="cli",
    )

    assert result["status"] == "archived"
    assert cur.params[0] == "archived"
    metadata = json.loads(cur.params[1])
    assert metadata["agent_hub_review"]["decision"] == "reject"
    assert metadata["agent_hub_review"]["reviewed_by"] == "bob"
    assert metadata["agent_hub_review"]["review_source"] == "cli"
    assert audit_calls[0][2] == "inbox_reject"


def test_inbox_cards_include_source_and_plain_consequence() -> None:
    card = inbox.card_for_item(draft_row())

    assert "Was merke ich mir:" in card
    assert "Quelle: test." in card
    assert "Folge bei Irrtum:" in card


class ListCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def __enter__(self) -> "ListCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql, _params=None) -> None:
        if "FROM facts" in sql:
            self.results = self.rows
        else:
            self.results = []

    def fetchall(self):
        return self.results


class ListConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def __enter__(self) -> "ListConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> ListCursor:
        return ListCursor(self.rows)


class ReviewByIdCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = dict(row)
        self.last_sql = ""
        self.params = None

    def __enter__(self) -> "ReviewByIdCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql, params=None) -> None:
        self.last_sql = sql
        self.params = params

    def fetchone(self):
        if "FROM facts" in self.last_sql and "memory.id = %s" in self.last_sql:
            return self.row if self.row["status"] == "draft" else None
        if self.last_sql.lstrip().upper().startswith("UPDATE"):
            self.row["status"] = self.params[0]
            return {"id": self.row["id"], "status": self.params[0]}
        return None


class ReviewByIdConnection:
    def __init__(self, cursor: ReviewByIdCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self) -> "ReviewByIdConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> ReviewByIdCursor:
        return self.cursor_obj


def test_cli_inbox_accept_records_reviewer_and_responsible_reviewer(
    monkeypatch,
    capsys,
) -> None:
    audit_calls = []
    row = draft_row()
    cur = ReviewByIdCursor(row)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setenv("AGENT_HUB_DISABLE_ENV_AUTOLOAD", "1")
    monkeypatch.setattr(inbox, "connect", lambda: ReviewByIdConnection(cur))
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    code = cli.main(
        [
            "inbox",
            "--accept",
            str(row["id"]),
            "--reviewer",
            "bob",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    metadata = json.loads(cur.params[1])
    assert code == 0
    assert payload["reviewed"][0]["reviewed_by"] == "bob"
    assert payload["reviewed"][0]["review_source"] == "cli"
    assert payload["reviewed"][0]["responsible_reviewer"] == "alice"
    assert metadata["agent_hub_review"]["reviewed_by"] == "bob"
    assert metadata["agent_hub_review"]["review_source"] == "cli"
    assert audit_calls[0][5]["reviewed_by"] == "bob"
    assert audit_calls[0][5]["review_source"] == "cli"
    assert audit_calls[0][7]["reviewed_by"] == "bob"
    assert audit_calls[0][7]["review_source"] == "cli"


def test_inbox_requires_reviewer_for_accept(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setenv("AGENT_HUB_DISABLE_ENV_AUTOLOAD", "1")
    monkeypatch.delenv("AGENT_HUB_REVIEWER", raising=False)

    def fail_connect():
        raise AssertionError("missing reviewer must not touch the database")

    monkeypatch.setattr(inbox, "connect", fail_connect)

    code = cli.main(["inbox", "--accept", str(draft_row()["id"])])

    captured = capsys.readouterr()
    assert code == 1
    assert "reviewer handle is required" in captured.err


def test_inbox_reviewer_allowlist_rejects_unknown_handle(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setenv("AGENT_HUB_DISABLE_ENV_AUTOLOAD", "1")
    monkeypatch.setenv("AGENT_HUB_REVIEWERS", "alice,bob")

    def fail_connect():
        raise AssertionError("invalid reviewer must not touch the database")

    monkeypatch.setattr(inbox, "connect", fail_connect)

    code = cli.main(
        ["inbox", "--accept", str(draft_row()["id"]), "--reviewer", "charlie"]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "reviewer handle is not allowed: charlie" in captured.err


def test_inbox_for_filter_is_display_only(monkeypatch, capsys) -> None:
    alice = draft_row()
    bob = {**draft_row(), "id": uuid.UUID("10000000-0000-4000-8000-000000000702")}
    bob["metadata"] = {"created_by": "test", "assigned_reviewer": "bob"}
    rows = [alice, bob]
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setenv("AGENT_HUB_DISABLE_ENV_AUTOLOAD", "1")
    monkeypatch.setattr(inbox, "connect", lambda: ListConnection(rows))

    code = cli.main(["inbox", "--for", "alice"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Responsible reviewer: alice" in captured.out
    assert "10000000-0000-4000-8000-000000000701" in captured.out
    assert "10000000-0000-4000-8000-000000000702" not in captured.out
