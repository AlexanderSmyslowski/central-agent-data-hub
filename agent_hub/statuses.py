"""Shared status helpers for memory rendering and retrieval."""

from __future__ import annotations

DRAFT_STATUS = "draft"

MEMORY_STATUS_VALUES = {
    "fact": ("draft", "proposed", "verified", "disputed", "deprecated", "archived"),
    "decision": (
        "draft",
        "proposed",
        "accepted",
        "rejected",
        "superseded",
        "archived",
    ),
    "open_question": ("draft", "open", "answered", "deferred", "closed", "archived"),
    "risk": ("draft", "open", "mitigating", "accepted", "resolved", "archived"),
    "report": ("draft", "published", "superseded", "archived"),
}

DRAFT_MEMORY_STATUSES = {
    memory_type: DRAFT_STATUS for memory_type in MEMORY_STATUS_VALUES
}

REVIEWED_MEMORY_STATUSES = {
    "fact": ("verified",),
    "decision": ("accepted",),
    "risk": ("open", "mitigating", "accepted"),
    "open_question": ("open", "answered"),
    "report": ("published",),
}

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
