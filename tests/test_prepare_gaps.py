from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from agent_hub.commands.prepare import build_prepare_payload, prepare_markdown
from agent_hub.gaps import (
    collect_prepare_gaps,
    fetch_pending_draft_counts,
    gap_markdown_lines,
)
from agent_hub.writeback_routing import lint_card_text


NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
PROJECT = {
    "id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
    "slug": "central-agent-data-hub",
    "name": "Central Agent Data Hub",
}


def memory_id(suffix: str) -> uuid.UUID:
    return uuid.UUID(f"10000000-0000-4000-8000-000000000{suffix}")


def counts(
    *,
    facts: int = 0,
    decisions: int = 0,
    risks: int = 0,
    open_questions: int = 0,
    reports: int = 0,
) -> dict[str, int]:
    return {
        "facts": facts,
        "decisions": decisions,
        "risks": risks,
        "open_questions": open_questions,
        "reports": reports,
    }


def fact(
    suffix: str,
    *,
    updated_at: str,
    status: str = "verified",
    reason: str = (
        "included as recent fallback because task text matched no reviewed "
        "items in this type"
    ),
) -> dict[str, object]:
    return {
        "id": memory_id(suffix),
        "statement": f"Fact {suffix}",
        "source": "test",
        "confidence": 0.9,
        "status": status,
        "updated_at": updated_at,
        "prepare_reason": reason,
    }


def question(suffix: str, *, updated_at: str) -> dict[str, object]:
    return {
        "id": memory_id(suffix),
        "question": f"Question {suffix}?",
        "answer": None,
        "status": "open",
        "updated_at": updated_at,
        "prepare_reason": "included by safety floor for unresolved open questions",
    }


def compiled(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "facts": [],
        "decisions": [],
        "risks": [],
        "open_questions": [],
        "reports": [],
        "relations": [],
        "active_counts": counts(),
        "pending_draft_counts": counts(),
    }
    payload.update(overrides)
    return payload


def test_stale_fact_is_listed_but_fresh_fact_is_not() -> None:
    gaps = collect_prepare_gaps(
        compiled(
            facts=[
                fact("101", updated_at="2026-04-01T00:00:00+00:00"),
                fact("102", updated_at="2026-06-01T00:00:00+00:00"),
            ],
            active_counts=counts(facts=2),
        ),
        "review release",
        NOW,
        stale_after_days=42,
    )

    assert [item["id"] for item in gaps["stale_items"]] == [memory_id("101")]
    assert gaps["stale_items"][0]["age_days"] == 71


def test_stale_threshold_boundary_is_still_fresh() -> None:
    # Exactly at the threshold is not older than the threshold, so it remains fresh.
    gaps = collect_prepare_gaps(
        compiled(
            facts=[fact("103", updated_at="2026-04-29T12:00:00+00:00")],
            active_counts=counts(facts=1),
        ),
        "review release",
        NOW,
        stale_after_days=42,
    )

    assert gaps["stale_items"] == []


def test_empty_type_reports_missing_risks_only_when_count_is_zero() -> None:
    missing = collect_prepare_gaps(
        compiled(active_counts=counts(facts=1, decisions=1, open_questions=1, reports=1)),
        "review release",
        NOW,
    )
    present = collect_prepare_gaps(
        compiled(
            active_counts=counts(
                facts=1,
                decisions=1,
                risks=1,
                open_questions=1,
                reports=1,
            )
        ),
        "review release",
        NOW,
    )

    assert {"type": "risk", "reason": "no active risk items are recorded"} in missing["empty_types"]
    assert all(item["type"] != "risk" for item in present["empty_types"])


def test_task_blind_spot_when_type_has_no_task_match() -> None:
    gaps = collect_prepare_gaps(
        compiled(
            facts=[fact("104", updated_at="2026-06-01T00:00:00+00:00")],
            active_counts=counts(facts=1),
        ),
        "gap staleness",
        NOW,
    )

    assert gaps["task_blind_spots"][0] == {
        "type": "fact",
        "task": "gap staleness",
        "reason": "task matched no reviewed items in this type",
    }


def test_task_blind_spot_not_reported_when_task_matched() -> None:
    gaps = collect_prepare_gaps(
        compiled(
            facts=[
                fact(
                    "105",
                    updated_at="2026-06-01T00:00:00+00:00",
                    reason="included by deterministic task text match",
                )
                | {"task_score": 1.0}
            ],
            active_counts=counts(facts=1),
        ),
        "gap staleness",
        NOW,
    )

    assert all(item["type"] != "fact" for item in gaps["task_blind_spots"])


def test_pending_drafts_counted_and_draft_itself_is_not_stale() -> None:
    gaps = collect_prepare_gaps(
        compiled(
            facts=[fact("106", updated_at="2026-01-01T00:00:00+00:00", status="draft")],
            pending_draft_counts=counts(facts=1, open_questions=1),
        ),
        "review release",
        NOW,
    )

    assert gaps["pending_drafts"]["total"] == 2
    assert gaps["stale_items"] == []


def test_unanswered_question_lists_age() -> None:
    gaps = collect_prepare_gaps(
        compiled(
            open_questions=[question("201", updated_at="2026-06-01T00:00:00+00:00")],
            active_counts=counts(open_questions=1),
        ),
        "review release",
        NOW,
    )

    assert gaps["unanswered_questions"][0]["id"] == memory_id("201")
    assert gaps["unanswered_questions"][0]["age_days"] == 10


def test_markdown_section_trail_counts_and_gap_lines_are_plain_language() -> None:
    draft = fact("301", updated_at="2026-01-01T00:00:00+00:00", status="draft")
    payload = build_prepare_payload(
        project=PROJECT,
        task="release review",
        compiled=compiled(
            facts=[fact("302", updated_at="2026-04-01T00:00:00+00:00"), draft],
            open_questions=[question("303", updated_at="2026-06-01T00:00:00+00:00")],
            active_counts=counts(facts=2, open_questions=1),
            pending_draft_counts=counts(facts=1),
        ),
        now=NOW,
        stale_after_days=42,
    )
    markdown = prepare_markdown(payload)

    assert "## Known Gaps" in markdown
    assert "stale_after_days: 42" in markdown
    assert payload["context_trail"]["gap_summary"] == {
        "stale": 1,
        "unanswered": 1,
        "empty_types": 3,
        "blind_spots": 2,
        "pending_drafts": 1,
        "thresholds": {"stale_after_days": 42},
    }
    for line in gap_markdown_lines(payload["gaps"]):
        assert lint_card_text(line) == []


def test_pending_draft_count_query_is_read_only() -> None:
    class ReadOnlyCursor:
        def __init__(self) -> None:
            self.last_sql = ""

        def execute(self, sql, _params) -> None:
            if re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql.upper()):
                raise AssertionError("gap counts must stay read-only")
            self.last_sql = sql

        def fetchone(self) -> dict[str, int]:
            return {"count": 0}

    counts = fetch_pending_draft_counts(
        ReadOnlyCursor(),
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
    )

    assert counts == {
        "facts": 0,
        "decisions": 0,
        "risks": 0,
        "open_questions": 0,
        "reports": 0,
    }
