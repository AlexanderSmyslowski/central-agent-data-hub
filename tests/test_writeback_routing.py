from __future__ import annotations

import argparse

import pytest

from agent_hub.memory import HumanReviewRequired, remember
from agent_hub.writeback_routing import card_for_item, lint_card_text, route_candidate


def test_route_auto_for_receipt_report() -> None:
    tier, reason = route_candidate(
        {
            "type": "report",
            "report_type": "receipt",
            "title": "Checks passed.",
            "source": "local pytest",
        }
    )

    assert tier == "auto"
    assert "receipt" in reason


def test_route_draft_for_new_unreviewed_fact() -> None:
    tier, reason = route_candidate(
        {
            "type": "fact",
            "statement": "Prepare includes draft memory separately.",
            "source": "local review",
        }
    )

    assert tier == "draft"
    assert "explicit acceptance" in reason


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Budget is $100.", "money amount"),
        ("api_key = abc123", "secret or credential"),
        ("Private customer email changed.", "customer data"),
        ("Delete old project state.", "deletion"),
    ],
)
def test_route_ask_for_safety_triggers(text: str, expected: str) -> None:
    tier, reason = route_candidate(
        {
            "type": "fact",
            "statement": text,
            "source": "external note",
        }
    )

    assert tier == "ask"
    assert expected in reason


def test_route_ask_for_contradiction_to_existing_reviewed_memory() -> None:
    item = {
        "type": "fact",
        "import_key": "same-fact",
        "statement": "The preview is private.",
        "source": "new note",
    }
    existing = {
        "type": "fact",
        "import_key": "same-fact",
        "statement": "The preview is public.",
        "source": "old note",
        "status": "verified",
    }

    tier, reason = route_candidate(item, [existing])

    assert tier == "ask"
    assert "contradicts existing reviewed memory" in reason


def test_route_auto_for_same_source_refresh() -> None:
    item = {
        "type": "fact",
        "import_key": "same-fact",
        "statement": "The preview is public v0.1.",
        "source": "release notes",
    }
    existing = {
        "type": "fact",
        "import_key": "same-fact",
        "statement": "The preview is public.",
        "source": "release notes",
        "status": "verified",
    }

    tier, reason = route_candidate(item, [existing])

    assert tier == "auto"
    assert "same-source refresh" in reason


def test_memory_ask_stops_before_database_write() -> None:
    class NoWriteCursor:
        def execute(self, *_args):
            raise AssertionError("ask routing should not touch the database")

    args = argparse.Namespace(
        project="central-agent-data-hub",
        create_project=False,
        project_name=None,
        project_description=None,
        agent="codex",
        agent_name="Codex",
        memory_type="fact",
        text="The token is abc123.",
        status=None,
        source="chat",
        confidence=0.9,
    )

    with pytest.raises(HumanReviewRequired):
        remember(NoWriteCursor(), args, {"created_by": "test"})


def test_card_language_lint_accepts_plain_cards_for_all_review_types() -> None:
    samples = [
        {"type": "fact", "statement": "Local setup uses Docker.", "source": "README"},
        {
            "type": "decision",
            "decision": "Use explicit review for drafts.",
            "source": "architecture note",
        },
        {"type": "risk", "title": "Setup may be stale.", "source": "review"},
        {
            "type": "open_question",
            "question": "Who reviews drafts weekly?",
            "source": "triage note",
        },
    ]

    for sample in samples:
        assert lint_card_text(card_for_item(sample)) == []


def test_card_does_not_double_terminal_punctuation() -> None:
    card = card_for_item(
        {
            "type": "fact",
            "statement": "Dry-run draft smoke.",
            "source": "local smoke",
        }
    )

    assert "smoke.." not in card


def test_card_language_lint_requires_concrete_source() -> None:
    card = card_for_item({"type": "risk", "title": "Review cadence is unclear."})

    assert "missing concrete source" in lint_card_text(card)
