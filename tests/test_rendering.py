from datetime import datetime, timezone

from agent_hub.rendering import handoff_markdown, recommended_steps_markdown


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
