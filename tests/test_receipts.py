from __future__ import annotations

import uuid
from datetime import datetime, timezone

from agent_hub.receipts import fetch_receipt_rows


class FakeReceiptCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.calls.append((query, params))

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


def test_receipt_rows_for_memory_types_filter_to_reviewed_statuses() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    project_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    cur = FakeReceiptCursor(
        [
            {
                "id": uuid.UUID("10000000-0000-4000-8000-000000000201"),
                "statement": "Reviewed memory has a source.",
                "source": "test",
                "confidence": 0.9,
                "status": "verified",
                "metadata": {},
                "created_at": now,
                "updated_at": now,
            }
        ]
    )

    rows = fetch_receipt_rows(
        cur,
        {"id": project_id},
        since=now,
        memory_type="fact",
        limit=3,
        export_dir=None,
    )

    query, params = cur.calls[0]
    assert "status IN (%s)" in query
    assert params == (project_id, now, "verified", 3)
    assert rows[0]["status"] == "verified"


def test_receipt_rows_for_agent_actions_remain_audit_evidence() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    project_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    cur = FakeReceiptCursor(
        [
            {
                "id": uuid.UUID("10000000-0000-4000-8000-000000000701"),
                "action": "inbox_accept",
                "object_type": "fact",
                "object_id": uuid.UUID("10000000-0000-4000-8000-000000000201"),
                "status": "succeeded",
                "metadata": {},
                "agent_slug": "codex",
                "created_at": now,
                "updated_at": now,
            }
        ]
    )

    rows = fetch_receipt_rows(
        cur,
        {"id": project_id},
        since=now,
        memory_type="agent_action",
        limit=5,
        export_dir=None,
    )

    query, params = cur.calls[0]
    assert "status IN" not in query
    assert params == (project_id, now, 5)
    assert rows[0]["status"] == "succeeded"
