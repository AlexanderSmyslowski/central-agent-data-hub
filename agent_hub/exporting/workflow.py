"""Obsidian export workflow orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_hub.db import connect
from agent_hub.exporting.helpers import (
    append_unique,
    display_title,
    filename_for,
    get_export_dir,
    normalize_row,
    relation_link_line,
    slugify,
)
from agent_hub.exporting.overviews import hub_home_context, project_overview_context
from agent_hub.exporting.relations import fetch_relations
from agent_hub.exporting.specs import EXPORTS, TYPE_BY_TABLE
from agent_hub.markdown import render_markdown, write_markdown

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
