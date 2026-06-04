"""Shared status helpers for memory rendering and retrieval."""

from __future__ import annotations

INACTIVE_OPEN_QUESTION_STATUSES = ("answered", "closed", "resolved", "archived")


def unresolved_open_questions(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if row.get("status") not in INACTIVE_OPEN_QUESTION_STATUSES
    ]


def format_open_question_count(unresolved: int, total: int | None = None) -> str:
    if total is None:
        total = unresolved
    if total <= 0:
        return "0 unresolved"
    if unresolved == total:
        return f"{unresolved} unresolved"
    return f"{unresolved} unresolved ({total} total)"
