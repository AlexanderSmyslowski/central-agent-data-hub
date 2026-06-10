"""Deterministic routing for unreviewed memory candidates."""

from __future__ import annotations

import re
from typing import Any

from agent_hub.importing.constants import SENSITIVE_PATTERN


MONEY_PATTERN = re.compile(
    r"((€|\$|£)\s*\d|\b\d+(?:[.,]\d{2})?\s*(eur|euro|usd|dollar|€|\$)\b)",
    re.IGNORECASE,
)
CUSTOMER_HINT_PATTERN = re.compile(
    r"\b(kunde|kundin|kundendaten|client|customer|mandant|private customer)\b",
    re.IGNORECASE,
)
DELETE_INTENT_PATTERN = re.compile(
    r"\b(delete|remove|erase|drop|löschen|loeschen|entfernen)\b",
    re.IGNORECASE,
)

BANNED_CARD_WORDS = (
    "writeback",
    "sync",
    "import",
    "payload",
    "schema",
    "tier",
    "frontmatter",
    "allowlist",
)
MAX_CARD_SENTENCE_WORDS = 24

TYPE_CARD_PHRASES = {
    "fact": "das merke ich mir als gesichert",
    "decision": "so wurde entschieden",
    "risk": "darauf ein Auge behalten",
    "open_question": "das ist noch unklar",
    "report": "notiere ich als Bericht",
    "agent_action": "notiere ich als Arbeitsnachweis",
    "receipt": "notiere ich als Prüfbeleg",
    "audit": "notiere ich als Prüfbeleg",
}

REVIEWED_STATUSES = {
    "fact": {"verified"},
    "decision": {"accepted"},
    "risk": {"open", "mitigating", "accepted"},
    "open_question": {"open", "answered"},
    "report": {"published"},
}

CORE_FIELDS = {
    "fact": ("statement", "text"),
    "decision": ("decision", "text"),
    "risk": ("title", "impact", "mitigation", "text"),
    "open_question": ("question", "answer", "text"),
    "report": ("title", "summary", "body", "text"),
    "agent_action": ("action", "summary", "text"),
    "receipt": ("title", "summary", "text"),
    "audit": ("title", "summary", "text"),
}


def normalized_type(value: object) -> str:
    return str(value or "").replace("-", "_")


def candidate_from_import_item(item: Any) -> dict[str, object]:
    data = dict(getattr(item, "data", {}) or {})
    data.setdefault("type", getattr(item, "memory_type", None))
    data.setdefault("import_key", getattr(item, "import_key", None))
    data.setdefault("source_path", getattr(item, "source_path", None))
    data.setdefault("body", getattr(item, "body", None))
    return data


def text_value(value: object) -> str:
    return "" if value is None else str(value).strip()


def candidate_type(item: Any) -> str:
    if not isinstance(item, dict):
        item = candidate_from_import_item(item)
    return normalized_type(item.get("type") or item.get("memory_type"))


def source_value(item: Any) -> str:
    if not isinstance(item, dict):
        item = candidate_from_import_item(item)
    for key in ("source", "source_path", "path", "link"):
        value = text_value(item.get(key))
        if value:
            return value
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        value = text_value(metadata.get("source"))
        if value:
            return value
    return "Quelle nicht angegeben"


def primary_text(item: Any) -> str:
    if not isinstance(item, dict):
        item = candidate_from_import_item(item)
    item_type = candidate_type(item)
    for key in CORE_FIELDS.get(item_type, ("text", "summary", "title")):
        value = text_value(item.get(key))
        if value:
            return value
    return "Nicht angegeben."


def core_text(item: Any) -> str:
    if not isinstance(item, dict):
        item = candidate_from_import_item(item)
    item_type = candidate_type(item)
    values = [
        text_value(item.get(key))
        for key in CORE_FIELDS.get(item_type, ("text",))
        if text_value(item.get(key))
    ]
    return "\n".join(values)


def identity_value(item: Any) -> str | None:
    if not isinstance(item, dict):
        item = candidate_from_import_item(item)
    for key in ("import_key", "db_id", "identity"):
        value = text_value(item.get(key))
        if value:
            return value
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        for key in ("import_key", "identity"):
            value = text_value(metadata.get(key))
            if value:
                return value
        import_state = metadata.get("agent_hub_import")
        if isinstance(import_state, dict):
            value = text_value(import_state.get("import_key"))
            if value:
                return value
        writeback_state = metadata.get("agent_hub_writeback")
        if isinstance(writeback_state, dict):
            value = text_value(writeback_state.get("identity"))
            if value:
                return value
    value = text_value(item.get("id"))
    if value:
        return value
    return None


def haystack(item: Any) -> str:
    if not isinstance(item, dict):
        item = candidate_from_import_item(item)
    values: list[str] = []
    for value in item.values():
        if isinstance(value, dict):
            values.extend(text_value(nested) for nested in value.values())
        elif text_value(value):
            values.append(text_value(value))
    return "\n".join(values)


def is_receipt_or_audit(item: Any) -> bool:
    if not isinstance(item, dict):
        item = candidate_from_import_item(item)
    item_type = candidate_type(item)
    report_type = text_value(item.get("report_type")).lower()
    action = text_value(item.get("action")).lower()
    return (
        item_type in {"agent_action", "receipt", "audit"}
        or report_type in {"receipt", "audit"}
        or "receipt" in action
        or "audit" in action
    )


def has_same_identity(left: Any, right: Any) -> bool:
    return bool(identity_value(left) and identity_value(left) == identity_value(right))


def has_same_source(left: Any, right: Any) -> bool:
    return source_value(left) == source_value(right)


def is_reviewed_existing(row: dict[str, object], item_type: str) -> bool:
    return str(row.get("status")) in REVIEWED_STATUSES.get(item_type, set())


def find_matching_existing(
    item: Any, existing: Any
) -> list[dict[str, object]]:
    if not existing:
        return []
    rows = [existing] if isinstance(existing, dict) else list(existing)
    item_type = candidate_type(item)
    return [
        row
        for row in rows
        if candidate_type(row) == item_type
        and has_same_identity(item, row)
        and is_reviewed_existing(row, item_type)
    ]


def has_safety_trigger(item: Any) -> str | None:
    text = haystack(item)
    if MONEY_PATTERN.search(text):
        return "needs human review because it mentions a money amount"
    if CUSTOMER_HINT_PATTERN.search(text):
        return "needs human review because it may mention customer data"
    if DELETE_INTENT_PATTERN.search(text):
        return "needs human review because it appears to describe deletion"
    if SENSITIVE_PATTERN.search(text):
        return "needs human review because it matches a secret or credential safety pattern"
    return None


def route_candidate(item: Any, existing: Any = None) -> tuple[str, str]:
    """Route a candidate to auto, ask, or draft using deterministic rules."""
    safety_reason = has_safety_trigger(item)
    if safety_reason:
        return "ask", safety_reason

    if is_receipt_or_audit(item):
        return "auto", "auto because receipts and audit entries are reversible evidence"

    matches = find_matching_existing(item, existing)
    for row in matches:
        if has_same_source(item, row):
            return (
                "auto",
                "auto because this is a same-source refresh of existing reviewed memory",
            )
        if core_text(item) != core_text(row):
            return (
                "ask",
                "needs human review because it contradicts existing reviewed memory",
            )

    return "draft", "draft because the candidate is unreviewed and needs explicit acceptance"


def card_for_item(
    item: Any,
    *,
    consequence: str = "Spätere Arbeit könnte von einer falschen Annahme ausgehen.",
) -> str:
    item_type = candidate_type(item)
    phrase = TYPE_CARD_PHRASES.get(item_type, "notiere ich zur Prüfung")
    sentence = phrase[:1].upper() + phrase[1:]
    text = primary_text(item)
    ending = "" if text.endswith((".", "!", "?")) else "."
    return "\n".join(
        [
            f"Was merke ich mir: {sentence}: {text}{ending}",
            f"Quelle: {source_value(item)}.",
            f"Folge bei Irrtum: {consequence}",
        ]
    )


def lint_card_text(text: str) -> list[str]:
    errors: list[str] = []
    lowered = text.lower()
    for word in BANNED_CARD_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            errors.append(f"forbidden word: {word}")
    if "quelle:" not in lowered:
        errors.append("missing source line")
    if "quelle nicht angegeben" in lowered:
        errors.append("missing concrete source")
    for sentence in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
        words = re.findall(r"\w+", sentence)
        if len(words) > MAX_CARD_SENTENCE_WORDS:
            errors.append(f"sentence too long: {len(words)} words")
    return errors
