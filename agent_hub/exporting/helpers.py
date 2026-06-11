"""Export path, title, and Wikilink helpers."""

from __future__ import annotations

import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from agent_hub.errors import ConfigurationError
from agent_hub.statuses import DRAFT_STATUS

def get_export_dir() -> Path:
    export_dir = os.environ.get("OBSIDIAN_EXPORT_DIR")
    if not export_dir:
        raise ConfigurationError(
            "OBSIDIAN_EXPORT_DIR is required, for example /tmp/agent-hub-obsidian"
        )
    return Path(export_dir)


def normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: normalize_value(value) for key, value in row.items()}
    if normalized.get("status") == DRAFT_STATUS:
        normalized["review_status"] = DRAFT_STATUS
        normalized["draft_warning"] = "Unreviewed draft — not part of reviewed memory"
    else:
        normalized["review_status"] = "reviewed"
        normalized["draft_warning"] = ""
    return normalized


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80].strip("-") or "untitled"


def id_suffix(row: dict[str, Any]) -> str:
    compact_id = re.sub(r"[^a-zA-Z0-9]", "", str(row.get("id", "")))
    return compact_id[-8:]


def filename_for(row: dict[str, Any], title_fields: Iterable[str]) -> str:
    if row.get("slug"):
        return f"{slugify(str(row['slug']))}.md"

    for field in title_fields:
        value = row.get(field)
        if value:
            stem = slugify(str(value))
            suffix = id_suffix(row)
            return f"{stem}-{suffix}.md" if suffix else f"{stem}.md"

    suffix = id_suffix(row)
    return f"untitled-{suffix}.md" if suffix else "untitled.md"


def display_title(memory_type: str, row: dict[str, Any]) -> str:
    keys = {
        "project": ("name", "slug"),
        "document": ("title", "slug"),
        "report": ("title",),
        "decision": ("decision",),
        "fact": ("statement",),
        "open_question": ("question",),
        "risk": ("title",),
        "agent_action": ("action",),
    }[memory_type]
    for key in keys:
        value = row.get(key)
        if value:
            text = str(value)
            return text if len(text) <= 80 else text[:77] + "..."
    return str(row.get("id", "untitled"))


def wikilink(export_dir: Path, path: Path, label: str) -> str:
    relative = path.relative_to(export_dir).with_suffix("")
    target = str(relative).replace("\\", "/")
    clean_label = label.replace("[", "(").replace("]", ")").replace("|", "-")
    return f"[[{target}|{clean_label}]]"


def relation_link_line(
    export_dir: Path,
    source: dict[str, Any],
    relation_type: str,
    target: dict[str, Any],
) -> str:
    source_link = wikilink(
        export_dir,
        source["path"],
        f"{source['type']}: {source['title']}",
    )
    target_link = wikilink(
        export_dir,
        target["path"],
        f"{target['type']}: {target['title']}",
    )
    return f"- {source_link} --{relation_type}--> {target_link}"


def append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)
