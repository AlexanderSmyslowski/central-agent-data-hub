from __future__ import annotations

import json
import uuid

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
        "metadata": {"created_by": "test"},
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
    )

    assert result["status"] == "verified"
    assert cur.params[0] == "verified"
    metadata = json.loads(cur.params[1])
    assert metadata["agent_hub_review"] == {
        "decision": "accept",
        "previous_status": "draft",
        "next_status": "verified",
    }
    assert audit_calls[0][2] == "inbox_accept"


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
    )

    assert result["status"] == "archived"
    assert cur.params[0] == "archived"
    metadata = json.loads(cur.params[1])
    assert metadata["agent_hub_review"]["decision"] == "reject"
    assert audit_calls[0][2] == "inbox_reject"


def test_inbox_cards_include_source_and_plain_consequence() -> None:
    card = inbox.card_for_item(draft_row())

    assert "Was merke ich mir:" in card
    assert "Quelle: test." in card
    assert "Folge bei Irrtum:" in card
