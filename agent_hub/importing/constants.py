"""Import constants and validation tables."""

from __future__ import annotations

import re

ALLOWED_TYPES = ("fact", "decision", "open_question", "risk", "report")
SENSITIVE_PATTERN = re.compile(
    r"("
    r"password|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|"
    r"ftp://|ftp\s*credentials?|ftp[_ -]?(user|password|pass|host)|"
    r"raw[_ -]?invoice|invoice[_ -]?(number|data)|rechnungs(daten|nummer)|"
    r"kundendaten|private[_ -]?customer|customer[_ -]?(email|phone|data)"
    r")",
    re.IGNORECASE,
)
TYPE_DEFAULT_FIELDS = {
    "fact": {"statement", "source", "confidence", "status", "metadata"},
    "decision": {"decision", "rationale", "consequences", "status", "metadata"},
    "open_question": {"question", "answer", "status", "metadata"},
    "risk": {"title", "severity", "impact", "mitigation", "status", "metadata"},
    "report": {"title", "report_type", "summary", "body", "status", "metadata"},
}

TYPE_TABLES = {
    "fact": "facts",
    "decision": "decisions",
    "open_question": "open_questions",
    "risk": "risks",
    "report": "reports",
}

TYPE_COLUMNS = {
    "fact": ("statement", "source", "confidence", "status"),
    "decision": ("decision", "rationale", "consequences", "status"),
    "open_question": ("question", "answer", "status"),
    "risk": ("title", "severity", "impact", "mitigation", "status"),
    "report": ("title", "report_type", "summary", "body", "status"),
}

TYPE_DEFAULT_VALUES = {
    "fact": {"confidence": 0.9, "status": "verified"},
    "decision": {"status": "accepted"},
    "open_question": {"status": "open"},
    "risk": {"severity": "medium", "status": "open"},
    "report": {"report_type": "status", "status": "published"},
}

FIELD_OWNERS = {
    memory_type: {column: "obsidian" for column in columns}
    for memory_type, columns in TYPE_COLUMNS.items()
}

STATUS_VALUES = {
    "fact": {"draft", "proposed", "verified", "disputed", "deprecated", "archived"},
    "decision": {"draft", "proposed", "accepted", "rejected", "superseded", "archived"},
    "open_question": {"draft", "open", "answered", "deferred", "closed", "archived"},
    "risk": {"draft", "open", "mitigating", "accepted", "resolved", "archived"},
    "report": {"draft", "published", "superseded", "archived"},
}

REQUIRED_FIELDS = {
    "fact": {"statement", "source"},
    "decision": {"decision"},
    "open_question": {"question"},
    "risk": {"title"},
    "report": {"title"},
}
