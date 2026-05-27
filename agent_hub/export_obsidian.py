"""Minimal Obsidian exporter."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from agent_hub.db import connect
from agent_hub.markdown import render_markdown, write_markdown

EXPORTS = [
    {
        "table": "projects",
        "template": "project.md.j2",
        "folder": "Projects",
        "title_fields": ("slug", "name"),
        "query": """
            SELECT id, name, slug, description, status, metadata, created_at, updated_at
            FROM projects
            ORDER BY slug
        """,
    },
    {
        "table": "documents",
        "template": "document.md.j2",
        "folder": "Documents",
        "title_fields": ("slug", "title"),
        "query": """
            SELECT id, project_id, title, slug, path, content, frontmatter,
                   content_hash, status, metadata, created_at, updated_at
            FROM documents
            ORDER BY slug
        """,
    },
    {
        "table": "reports",
        "template": "report.md.j2",
        "folder": "Reports",
        "title_fields": ("title",),
        "query": """
            SELECT id, project_id, title, report_type, summary, body, status,
                   metadata, created_at, updated_at
            FROM reports
            ORDER BY title, id
        """,
    },
    {
        "table": "decisions",
        "template": "decision.md.j2",
        "folder": "Decisions",
        "title_fields": ("decision",),
        "query": """
            SELECT id, project_id, decision, rationale, consequences, status,
                   metadata, created_at, updated_at
            FROM decisions
            ORDER BY created_at, id
        """,
    },
    {
        "table": "facts",
        "template": "fact.md.j2",
        "folder": "Facts",
        "title_fields": ("statement",),
        "query": """
            SELECT id, project_id, statement, source, confidence, status,
                   metadata, created_at, updated_at
            FROM facts
            ORDER BY created_at, id
        """,
    },
    {
        "table": "open_questions",
        "template": "open_question.md.j2",
        "folder": "Open Questions",
        "title_fields": ("question",),
        "query": """
            SELECT id, project_id, question, answer, status, resolved_at,
                   metadata, created_at, updated_at
            FROM open_questions
            ORDER BY created_at, id
        """,
    },
    {
        "table": "risks",
        "template": "risk.md.j2",
        "folder": "Risks",
        "title_fields": ("title",),
        "query": """
            SELECT id, project_id, title, severity, impact, mitigation, status,
                   metadata, created_at, updated_at
            FROM risks
            ORDER BY severity, title, id
        """,
    },
    {
        "table": "agent_actions",
        "template": "agent_action.md.j2",
        "folder": "Agent Actions",
        "title_fields": ("action",),
        "query": """
            SELECT id, agent_id, action, object_type, object_id, input, output,
                   status, error, metadata, created_at, updated_at
            FROM agent_actions
            ORDER BY created_at, id
        """,
    },
]


def get_export_dir() -> Path:
    export_dir = os.environ.get("OBSIDIAN_EXPORT_DIR")
    if not export_dir:
        raise RuntimeError(
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
    return {key: normalize_value(value) for key, value in row.items()}


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


def export_all() -> list[Path]:
    export_dir = get_export_dir()
    last_exported_at = datetime.now(timezone.utc).isoformat()
    written: list[Path] = []

    with connect() as conn:
        with conn.cursor() as cur:
            for spec in EXPORTS:
                cur.execute(spec["query"])
                for raw_row in cur.fetchall():
                    row = normalize_row(dict(raw_row))
                    row["last_exported_at"] = last_exported_at
                    row.setdefault("source", "database")

                    rendered = render_markdown(spec["template"], row)
                    filename = filename_for(row, spec["title_fields"])
                    path = export_dir / spec["folder"] / filename
                    write_markdown(path, rendered)
                    written.append(path)

    return written


def main() -> None:
    written = export_all()
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
