from __future__ import annotations

from agent_hub.context_receipt import (
    INFLUENCE_LINES,
    context_receipt_markdown,
    context_receipt_text,
    count_line,
    prepare_context_counts,
)


def test_context_receipt_text_is_visible_and_honest() -> None:
    receipt = context_receipt_text(
        project_slug="central-agent-data-hub",
        task="review release",
        counts={
            "facts": 3,
            "decisions": 2,
            "risks": 1,
            "open_questions": 4,
            "reports": 1,
        },
    )

    assert "== ADH Context Loaded ==" in receipt
    assert "Project: central-agent-data-hub" in receipt
    assert "Task: review release" in receipt
    assert "Using reviewed memory: 3 facts · 2 decisions · 1 risks · 4 open questions · 1 reports" in receipt
    assert "How this influences the work:" in receipt
    for line in INFLUENCE_LINES:
        assert f"- {line}" in receipt
    assert "has used" not in receipt
    assert "is now using" not in receipt


def test_context_receipt_markdown_matches_terminal_language() -> None:
    markdown = context_receipt_markdown(
        project_slug="central-agent-data-hub",
        task="review release",
        counts={
            "facts": 3,
            "decisions": 2,
            "risks": 1,
            "open_questions": 4,
            "reports": 1,
        },
    )

    assert "## ADH Context Loaded" in markdown
    assert "- project: central-agent-data-hub" in markdown
    assert "- task: review release" in markdown
    assert "- using reviewed memory: 3 facts · 2 decisions · 1 risks · 4 open questions · 1 reports" in markdown
    for line in INFLUENCE_LINES:
        assert f"- {line}" in markdown


def test_prepare_context_counts_use_loaded_prepare_rows() -> None:
    counts = prepare_context_counts(
        {
            "verified_project_state": [{}, {}],
            "relevant_decisions": [{}],
            "risks": [{}, {}, {}],
            "open_questions": [],
            "reports": [{}],
        }
    )

    assert counts == {
        "facts": 2,
        "decisions": 1,
        "risks": 3,
        "open_questions": 0,
        "reports": 1,
    }
    assert count_line(counts) == "2 facts · 1 decisions · 3 risks · 0 open questions · 1 reports"
