from __future__ import annotations

import inspect
import json
import uuid

import pytest

from agent_hub import review_api
from agent_hub.commands import inbox


DRAFT_ID = uuid.UUID("10000000-0000-4000-8000-000000000701")


def draft_row() -> dict[str, object]:
    return {
        "id": DRAFT_ID,
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


class ReviewApiCursor:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = dict(row or draft_row())
        self.last_sql = ""
        self.params = None
        self.write_count = 0
        self.execute_count = 0

    def execute(self, sql, params=None) -> None:
        self.execute_count += 1
        self.last_sql = sql
        self.params = params
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            self.write_count += 1

    def fetchone(self):
        if "FROM facts" in self.last_sql and "memory.id = %s" in self.last_sql:
            return self.row if self.row["status"] == "draft" else None
        if self.last_sql.lstrip().upper().startswith("UPDATE"):
            self.row["status"] = self.params[0]
            return {"id": self.row["id"], "status": self.params[0]}
        return None


def test_review_api_exports_supported_adapter_surface() -> None:
    for name in [
        "connect",
        "fetch_drafts",
        "resolve_responsible_reviewer",
        "review_draft_by_id",
        "validate_reviewer_handle",
    ]:
        assert hasattr(review_api, name)


def test_review_api_docstring_declares_external_adapter_contract() -> None:
    assert "only supported import surface for external adapters" in (
        review_api.__doc__ or ""
    )
    assert "internal and may change without notice" in (review_api.__doc__ or "")


def test_fetch_drafts_signature_is_pinned_for_external_adapters() -> None:
    # Breaking this signature breaks external review adapters and needs a
    # deliberate compatibility decision.
    signature = inspect.signature(review_api.fetch_drafts)

    assert list(signature.parameters) == [
        "cur",
        "project_slug",
        "for_reviewer",
        "limit",
    ]
    assert signature.parameters["cur"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in ["project_slug", "for_reviewer", "limit"]:
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_review_draft_by_id_signature_is_pinned_for_external_adapters() -> None:
    # Breaking this signature breaks external review adapters and needs a
    # deliberate compatibility decision.
    signature = inspect.signature(review_api.review_draft_by_id)

    assert list(signature.parameters) == [
        "cur",
        "draft_id",
        "decision",
        "item_type",
        "project_slug",
        "agent_slug",
        "agent_name",
        "reviewed_by",
        "review_source",
    ]
    assert signature.parameters["cur"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["draft_id"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in [
        "decision",
        "item_type",
        "project_slug",
        "agent_slug",
        "agent_name",
        "reviewed_by",
        "review_source",
    ]:
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_unknown_review_source_is_rejected_before_write() -> None:
    cur = ReviewApiCursor()

    with pytest.raises(ValueError, match="unknown review_source: banana"):
        review_api.review_draft_by_id(
            cur,
            str(DRAFT_ID),
            decision="accept",
            item_type="fact",
            agent_slug="adapter",
            agent_name="Adapter",
            reviewed_by="bob",
            review_source="banana",
        )

    assert cur.execute_count == 0
    assert cur.write_count == 0


def test_telegram_review_source_is_valid_for_facade_review(monkeypatch) -> None:
    audit_calls = []
    cur = ReviewApiCursor()
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    result = review_api.review_draft_by_id(
        cur,
        str(DRAFT_ID),
        decision="accept",
        item_type="fact",
        agent_slug="telegram-review-adapter",
        agent_name="Telegram Review Adapter",
        reviewed_by="bob",
        review_source="telegram",
    )

    metadata = json.loads(cur.params[1])
    assert result is not None
    assert result["status"] == "verified"
    assert result["reviewed_by"] == "bob"
    assert result["review_source"] == "telegram"
    assert metadata["agent_hub_review"]["review_source"] == "telegram"
    assert metadata["agent_hub_review"]["reviewed_by"] == "bob"
    assert audit_calls[0][2] == "inbox_accept"
    assert audit_calls[0][5]["review_source"] == "telegram"
    assert audit_calls[0][5]["reviewed_by"] == "bob"
