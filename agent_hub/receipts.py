"""Receipt helpers for verifying exported project memory."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agent_hub.export_obsidian import EXPORTS, filename_for, normalize_row

RECEIPT_TYPES = (
    "all",
    "fact",
    "decision",
    "risk",
    "open_question",
    "report",
    "agent_action",
)

EXPORT_SPECS_BY_TYPE = {
    "project": next(spec for spec in EXPORTS if spec["table"] == "projects"),
    "document": next(spec for spec in EXPORTS if spec["table"] == "documents"),
    "report": next(spec for spec in EXPORTS if spec["table"] == "reports"),
    "decision": next(spec for spec in EXPORTS if spec["table"] == "decisions"),
    "fact": next(spec for spec in EXPORTS if spec["table"] == "facts"),
    "open_question": next(spec for spec in EXPORTS if spec["table"] == "open_questions"),
    "risk": next(spec for spec in EXPORTS if spec["table"] == "risks"),
    "agent_action": next(spec for spec in EXPORTS if spec["table"] == "agent_actions"),
}


def export_path_for_object(
    export_dir: Path | None,
    memory_type: str,
    row: dict[str, object],
) -> Path | None:
    if export_dir is None:
        return None
    spec = EXPORT_SPECS_BY_TYPE[memory_type]
    normalized = normalize_row(dict(row))
    return export_dir / str(spec["folder"]) / filename_for(
        normalized,
        spec["title_fields"],
    )


def receipt_title(row: dict[str, object]) -> str:
    for key in (
        "title",
        "statement",
        "decision",
        "question",
        "action",
    ):
        value = row.get(key)
        if value:
            return str(value)
    return str(row.get("id", "untitled"))


def fetch_receipt_rows(
    cur,
    project: dict[str, object],
    since: datetime,
    memory_type: str,
    limit: int,
    export_dir: Path | None,
) -> list[dict[str, object]]:
    project_id = project["id"]
    specs = {
        "fact": (
            """
            SELECT id, statement, source, confidence, status, metadata, created_at, updated_at
            FROM facts
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "statement",
        ),
        "decision": (
            """
            SELECT id, decision, rationale, consequences, status, metadata, created_at, updated_at
            FROM decisions
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "decision",
        ),
        "risk": (
            """
            SELECT id, title, severity, impact, mitigation, status, metadata, created_at, updated_at
            FROM risks
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "title",
        ),
        "open_question": (
            """
            SELECT id, question, answer, status, metadata, created_at, updated_at
            FROM open_questions
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "question",
        ),
        "report": (
            """
            SELECT id, title, report_type, summary, body, status, metadata, created_at, updated_at
            FROM reports
            WHERE project_id = %s AND updated_at >= %s
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            "title",
        ),
    }
    selected = (
        ("fact", "decision", "risk", "open_question", "report", "agent_action")
        if memory_type == "all"
        else (memory_type,)
    )
    rows: list[dict[str, object]] = []
    for item_type in selected:
        if item_type == "agent_action":
            cur.execute(
                """
                SELECT aa.id, aa.action, aa.object_type, aa.object_id, aa.status,
                       aa.metadata, aa.created_at, aa.updated_at,
                       a.slug AS agent_slug
                FROM agent_actions aa
                JOIN agents a ON a.id = aa.agent_id
                WHERE a.project_id = %s AND aa.updated_at >= %s
                ORDER BY aa.updated_at DESC, aa.created_at DESC, aa.id DESC
                LIMIT %s
                """,
                (project_id, since, limit),
            )
            fetched = list(cur.fetchall())
        else:
            query, _title_key = specs[item_type]
            cur.execute(query, (project_id, since, limit))
            fetched = list(cur.fetchall())

        for raw in fetched:
            row = dict(raw)
            path = export_path_for_object(export_dir, item_type, row)
            rows.append(
                {
                    "type": item_type,
                    "id": row["id"],
                    "title": receipt_title(row),
                    "status": row.get("status"),
                    "updated_at": row.get("updated_at"),
                    "created_at": row.get("created_at"),
                    "export_path": str(path) if path else None,
                    "exported": bool(path and path.exists()),
                    "object": row,
                }
            )
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows[:limit]
