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

TYPE_BY_TABLE = {
    "projects": "project",
    "documents": "document",
    "reports": "report",
    "decisions": "decision",
    "facts": "fact",
    "open_questions": "open_question",
    "risks": "risk",
    "agent_actions": "agent_action",
}

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


def fetch_relations(cur) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, source_type, source_id, relation_type, target_type, target_id,
               metadata, created_at, updated_at
        FROM relations
        ORDER BY updated_at DESC, created_at DESC, id
        """
    )
    return [normalize_row(dict(row)) for row in cur.fetchall()]


def project_overview_context(
    project: dict[str, Any],
    rows_by_table: dict[str, list[dict[str, Any]]],
    project_relations: list[str],
    last_exported_at: str,
) -> dict[str, Any]:
    project_id = project["id"]

    def project_rows(table: str, limit: int = 8) -> list[dict[str, Any]]:
        rows = [
            row
            for row in rows_by_table.get(table, [])
            if row.get("project_id") == project_id and row.get("status") != "archived"
        ]
        return rows[:limit]

    return {
        "id": f"compiled-{project['id']}",
        "name": project["name"],
        "slug": project["slug"],
        "description": project.get("description"),
        "status": project.get("status"),
        "last_exported_at": last_exported_at,
        "facts": project_rows("facts", 6),
        "decisions": project_rows("decisions", 6),
        "risks": [
            row
            for row in project_rows("risks", 8)
            if row.get("status") not in ("resolved", "archived")
        ][:6],
        "open_questions": [
            row
            for row in project_rows("open_questions", 8)
            if row.get("status") not in ("closed", "archived")
        ][:6],
        "reports": project_rows("reports", 5),
        "linked_memory": project_relations[:12],
        "source": "database",
    }


def hub_home_context(
    export_dir: Path,
    rows_by_table: dict[str, list[dict[str, Any]]],
    last_exported_at: str,
) -> dict[str, Any]:
    projects = []
    for project in rows_by_table.get("projects", []):
        compiled_path = export_dir / "Compiled" / f"{slugify(str(project['slug']))}.md"
        projects.append(
            {
                "name": project["name"],
                "slug": project["slug"],
                "status": project.get("status"),
                "description": project.get("description"),
                "link": wikilink(export_dir, compiled_path, str(project["name"])),
            }
        )

    active_project_ids = {project["id"] for project in rows_by_table.get("projects", [])}
    open_questions = [
        row
        for row in rows_by_table.get("open_questions", [])
        if row.get("project_id") in active_project_ids
        and row.get("status") not in ("answered", "closed", "archived")
    ][:12]
    recent_reports = [
        row
        for row in rows_by_table.get("reports", [])
        if row.get("project_id") in active_project_ids
        and row.get("status") != "archived"
    ][:12]
    return {
        "id": "agent-data-hub",
        "last_exported_at": last_exported_at,
        "projects": projects,
        "open_questions": open_questions,
        "recent_reports": recent_reports,
        "source": "database",
    }


def export_all() -> list[Path]:
    export_dir = get_export_dir()
    last_exported_at = datetime.now(timezone.utc).isoformat()
    written: list[Path] = []

    with connect() as conn:
        with conn.cursor() as cur:
            rows_by_table: dict[str, list[dict[str, Any]]] = {}
            object_index: dict[tuple[str, str], dict[str, Any]] = {}

            for spec in EXPORTS:
                cur.execute(spec["query"])
                for raw_row in cur.fetchall():
                    row = normalize_row(dict(raw_row))
                    row["last_exported_at"] = last_exported_at
                    row.setdefault("source", "database")
                    row.setdefault("linked_memory", [])

                    filename = filename_for(row, spec["title_fields"])
                    path = export_dir / spec["folder"] / filename
                    row["_export_path"] = path
                    rows_by_table.setdefault(str(spec["table"]), []).append(row)
                    memory_type = TYPE_BY_TABLE[str(spec["table"])]
                    object_index[(memory_type, str(row["id"]))] = {
                        "type": memory_type,
                        "id": str(row["id"]),
                        "title": display_title(memory_type, row),
                        "path": path,
                        "row": row,
                    }

            project_relation_lines: dict[str, list[str]] = {}
            for relation in fetch_relations(cur):
                source = object_index.get(
                    (relation["source_type"], str(relation["source_id"]))
                )
                target = object_index.get(
                    (relation["target_type"], str(relation["target_id"]))
                )
                if not source or not target:
                    continue
                line = relation_link_line(
                    export_dir,
                    source,
                    relation["relation_type"],
                    target,
                )
                append_unique(source["row"].setdefault("linked_memory", []), line)
                append_unique(target["row"].setdefault("linked_memory", []), line)
                for item in (source, target):
                    project_id = item["row"].get("project_id")
                    if not project_id and item["type"] == "project":
                        project_id = item["row"].get("id")
                    if project_id:
                        append_unique(
                            project_relation_lines.setdefault(str(project_id), []),
                            line,
                        )

            for spec in EXPORTS:
                for row in rows_by_table.get(str(spec["table"]), []):
                    rendered = render_markdown(spec["template"], row)
                    path = row["_export_path"]
                    write_markdown(path, rendered)
                    written.append(path)

            for project in rows_by_table.get("projects", []):
                context = project_overview_context(
                    project,
                    rows_by_table,
                    project_relation_lines.get(str(project["id"]), []),
                    last_exported_at,
                )
                rendered = render_markdown("compiled_project.md.j2", context)
                path = export_dir / "Compiled" / f"{slugify(str(project['slug']))}.md"
                write_markdown(path, rendered)
                written.append(path)

            rendered = render_markdown(
                "agent_data_hub_home.md.j2",
                hub_home_context(export_dir, rows_by_table, last_exported_at),
            )
            path = export_dir / "Compiled" / "Agent Data Hub.md"
            write_markdown(path, rendered)
            written.append(path)

    return written


def main() -> None:
    written = export_all()
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
