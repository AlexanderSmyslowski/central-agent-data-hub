"""Shared status helpers for memory rendering and retrieval."""

from __future__ import annotations

DRAFT_STATUS = "draft"

ITEM_TABLES = {
    "document": "documents",
    "report": "reports",
    "decision": "decisions",
    "fact": "facts",
    "open_question": "open_questions",
    "risk": "risks",
}

ITEM_TYPE_BY_TABLE = {table: item_type for item_type, table in ITEM_TABLES.items()}

INBOX_REVIEW_TYPES = ("fact", "decision", "risk", "open_question", "report")

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
    "document": ("draft", "active", "superseded", "archived"),
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
    "document": ("active",),
}

INACTIVE_OPEN_QUESTION_STATUSES = ("answered", "closed", "resolved", "archived")
UNRESOLVED_OPEN_QUESTION_STATUSES = ("open", "deferred")

INACTIVE_MEMORY_STATUSES = {
    "fact": ("archived", "deprecated"),
    "decision": ("archived", "rejected", "superseded"),
    "risk": ("archived", "resolved"),
    "open_question": INACTIVE_OPEN_QUESTION_STATUSES,
    "report": ("archived", "superseded"),
    "document": ("archived", "superseded"),
}

CURRENT_MEMORY_STATUSES = {
    "document": REVIEWED_MEMORY_STATUSES["document"],
    "fact": REVIEWED_MEMORY_STATUSES["fact"],
    "decision": REVIEWED_MEMORY_STATUSES["decision"],
    "risk": REVIEWED_MEMORY_STATUSES["risk"],
    "open_question": UNRESOLVED_OPEN_QUESTION_STATUSES,
    "report": REVIEWED_MEMORY_STATUSES["report"],
}

PREPARE_EXCLUDED_STATUSES = {
    "fact": ("archived", "deprecated"),
    "decision": ("archived", "rejected"),
    "risk": ("archived", "resolved"),
    "open_question": INACTIVE_OPEN_QUESTION_STATUSES,
    "report": ("archived",),
}

AGENT_READ_SURFACES = frozenset(
    {
        "brief",
        "compile",
        "context",
        "handoff",
        "mcp_project_brief",
        "search",
    }
)

HUMAN_READ_SURFACES = frozenset({"daily", "export", "prepare"})


def item_type_for_table(table: str) -> str:
    return ITEM_TYPE_BY_TABLE[table]


def table_for_item_type(item_type: str) -> str:
    return ITEM_TABLES[item_type]


def supports_drafts(item_type: str) -> bool:
    return DRAFT_STATUS in MEMORY_STATUS_VALUES.get(item_type, ())


def inactive_statuses_for(item_type: str) -> tuple[str, ...]:
    return INACTIVE_MEMORY_STATUSES.get(item_type, ())


def prepare_excluded_statuses(item_type: str) -> tuple[str, ...]:
    return PREPARE_EXCLUDED_STATUSES[item_type]


def reviewed_statuses_for(item_type: str) -> tuple[str, ...]:
    return REVIEWED_MEMORY_STATUSES[item_type]


def current_memory_statuses_for(item_type: str) -> tuple[str, ...]:
    return CURRENT_MEMORY_STATUSES[item_type]


def sql_status_in_clause(
    column: str,
    statuses: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    placeholders = ", ".join(["%s"] * len(statuses))
    return f"{column} IN ({placeholders})", statuses


def read_surface_excluded_statuses(
    item_type: str,
    *,
    surface: str = "search",
    include_drafts: bool = False,
    include_archived: bool = False,
) -> tuple[str, ...]:
    """Return statuses hidden from agent-facing read surfaces.

    ``include_archived`` is the public flag name, but internally it means:
    include archived and other inactive terminal statuses for that memory type.
    """
    if surface in HUMAN_READ_SURFACES:
        return ()

    excluded: list[str] = []
    if not include_drafts and supports_drafts(item_type):
        excluded.append(DRAFT_STATUS)
    if not include_archived:
        excluded.extend(inactive_statuses_for(item_type))
    return tuple(dict.fromkeys(excluded))


def agent_read_excluded_statuses(item_type: str) -> tuple[str, ...]:
    return read_surface_excluded_statuses(item_type)


def agent_read_excluded_statuses_by_type() -> dict[str, tuple[str, ...]]:
    return {
        item_type: agent_read_excluded_statuses(item_type)
        for item_type in MEMORY_STATUS_VALUES
    }


def search_excluded_statuses(
    item_type: str,
    *,
    include_drafts: bool = False,
    include_archived: bool = False,
) -> tuple[str, ...]:
    return read_surface_excluded_statuses(
        item_type,
        surface="search",
        include_drafts=include_drafts,
        include_archived=include_archived,
    )


def format_draft_review_count(count: int) -> str:
    return f"{count} drafts awaiting review (agent-hub inbox)"


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
