from datetime import datetime, timezone

from agent_hub.rendering import (
    daily_markdown,
    compiled_markdown,
    handoff_markdown,
    recommended_steps_markdown,
)
from agent_hub.statuses import format_open_question_count


def test_recommended_steps_ignore_answered_questions() -> None:
    payload = {
        "open_questions": [
            {"question": "Already answered?", "status": "answered"},
            {"question": "Still open?", "status": "open"},
            {"question": "Closed?", "status": "closed"},
        ],
        "risks": [],
    }

    rendered = recommended_steps_markdown(payload)

    assert "Still open?" in rendered
    assert "Already answered?" not in rendered
    assert "Closed?" not in rendered


def test_handoff_what_is_open_ignores_answered_questions() -> None:
    payload = {
        "project": {"name": "Demo", "slug": "demo"},
        "since": datetime(2026, 5, 31, tzinfo=timezone.utc),
        "decisions": [],
        "risks": [],
        "open_questions": [
            {"question": "Already answered?", "status": "answered"},
            {"question": "Still open?", "status": "open"},
        ],
        "facts": [],
        "relations": [],
    }

    rendered = handoff_markdown(payload)

    assert "Still open?" in rendered
    assert "Already answered?" not in rendered


def test_format_open_question_count_distinguishes_total_from_unresolved() -> None:
    assert format_open_question_count(0, 0) == "0 unresolved"
    assert format_open_question_count(2, 2) == "2 unresolved"
    assert format_open_question_count(0, 1) == "0 unresolved (1 total)"
    assert format_open_question_count(1, 3) == "1 unresolved (3 total)"


def test_compiled_memory_counts_label_open_questions_as_unresolved() -> None:
    payload = {
        "project": {"name": "Demo", "slug": "demo", "status": "active", "description": "Desc"},
        "counts": {
            "documents": 0,
            "facts": 1,
            "decisions": 0,
            "open_questions": 0,
            "risks": 0,
            "reports": 0,
        },
        "decisions": [],
        "risks": [],
        "open_questions": [],
        "facts": [],
        "relations": [],
        "reports": [],
    }

    rendered = compiled_markdown(payload)

    assert "open_questions=0 unresolved" in rendered


def test_daily_markdown_compacts_fully_quiet_window() -> None:
    payload = {
        "project": {"name": "Demo", "slug": "demo"},
        "since": datetime(2026, 5, 31, tzinfo=timezone.utc),
        "facts": [],
        "decisions": [],
        "risks": [],
        "open_questions": [],
        "reports": [],
        "relations": [],
        "agent_actions": [],
        "sync_events": [],
    }

    rendered = daily_markdown(payload)

    assert "## Activity Summary" in rendered
    assert "No new reviewed facts" in rendered
    assert "## New Facts" not in rendered


def test_handoff_markdown_compacts_fully_quiet_window() -> None:
    payload = {
        "project": {"name": "Demo", "slug": "demo"},
        "since": datetime(2026, 5, 31, tzinfo=timezone.utc),
        "decisions": [],
        "risks": [],
        "open_questions": [],
        "facts": [],
        "relations": [],
    }

    rendered = handoff_markdown(payload)

    assert "## Handoff Summary" in rendered
    assert "No new decisions, risks, open questions, evidence, or relation changes" in rendered
    assert "## What Is Decided" not in rendered
