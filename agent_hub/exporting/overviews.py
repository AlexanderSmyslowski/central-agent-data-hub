"""Compiled project and Hub home export contexts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_hub.exporting.helpers import slugify, wikilink

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
