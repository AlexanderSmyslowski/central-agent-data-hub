"""Database persistence for Obsidian imports and sync."""

from __future__ import annotations

import json
from typing import Any

from agent_hub.errors import NotFoundError, ValidationError
from agent_hub.importing.constants import TYPE_COLUMNS, TYPE_TABLES
from agent_hub.importing.identity import (
    build_field_diffs,
    changed_fields_from_last,
    hash_payload,
    import_metadata,
    item_values,
    json_default,
    row_values,
)
from agent_hub.importing.models import ImportItem

def fetch_project(cur, project_slug: str) -> dict[str, Any]:
    cur.execute("SELECT id, name, slug FROM projects WHERE slug = %s", (project_slug,))
    project = cur.fetchone()
    if not project:
        raise NotFoundError(f"Project not found: {project_slug}")
    return project


def ensure_import_agent(cur, project_id: Any) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO agents (project_id, name, slug, role, status, metadata)
        VALUES (%s, 'Agent Hub Import', 'agent-hub-import', 'Obsidian import agent',
                'active', '{"interface": "agent-hub import"}'::jsonb)
        ON CONFLICT (project_id, slug) DO UPDATE SET
          name = EXCLUDED.name,
          role = EXCLUDED.role,
          status = EXCLUDED.status,
          metadata = agents.metadata || EXCLUDED.metadata
        RETURNING id
        """,
        (project_id,),
    )
    return cur.fetchone()


def log_import_action(
    cur,
    agent_id: Any,
    action: str,
    object_type: str,
    object_id: Any,
    item: ImportItem,
    output: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO agent_actions (
          agent_id, action, object_type, object_id, input, output, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb,
                'succeeded', %s::jsonb)
        """,
        (
            agent_id,
            action,
            object_type,
            object_id,
            json.dumps(
                {
                    "path": str(item.path),
                    "type": item.memory_type,
                    "import_key": item.import_key,
                }
            ),
            json.dumps(output, default=json_default),
            json.dumps({"created_by": "agent-hub import"}),
        ),
    )


def insert_import_item(cur, item: ImportItem) -> dict[str, Any]:
    project = fetch_project(cur, item.project_slug)
    agent = ensure_import_agent(cur, project["id"])
    metadata = import_metadata(item)

    if item.memory_type == "fact":
        cur.execute(
            """
            INSERT INTO facts (project_id, statement, source, confidence, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["statement"],
                item.data["source"],
                item.data.get("confidence", 0.9),
                item.data.get("status", "verified"),
                json.dumps(metadata),
            ),
        )
        object_type = "fact"
    elif item.memory_type == "decision":
        cur.execute(
            """
            INSERT INTO decisions (project_id, decision, rationale, consequences, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["decision"],
                item.data.get("rationale"),
                item.data.get("consequences"),
                item.data.get("status", "accepted"),
                json.dumps(metadata),
            ),
        )
        object_type = "decision"
    elif item.memory_type == "open_question":
        status = item.data.get("status", "open")
        cur.execute(
            """
            INSERT INTO open_questions (project_id, question, answer, status, resolved_at, metadata)
            VALUES (%s, %s, %s, %s,
                    CASE WHEN %s IN ('answered', 'closed', 'resolved') THEN now() ELSE NULL END,
                    %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["question"],
                item.data.get("answer"),
                status,
                status,
                json.dumps(metadata),
            ),
        )
        object_type = "open_question"
    elif item.memory_type == "risk":
        cur.execute(
            """
            INSERT INTO risks (project_id, title, severity, impact, mitigation, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["title"],
                item.data.get("severity", "medium"),
                item.data.get("impact"),
                item.data.get("mitigation"),
                item.data.get("status", "open"),
                json.dumps(metadata),
            ),
        )
        object_type = "risk"
    elif item.memory_type == "report":
        cur.execute(
            """
            INSERT INTO reports (project_id, title, report_type, summary, body, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["title"],
                item.data.get("report_type", "status"),
                item.data.get("summary"),
                item.data.get("body", item.body),
                item.data.get("status", "published"),
                json.dumps(metadata),
            ),
        )
        object_type = "report"
    else:
        raise ValidationError(f"Unsupported import type: {item.memory_type}")

    row = cur.fetchone()
    log_import_action(
        cur,
        agent["id"],
        "import_obsidian_note",
        object_type,
        row["id"],
        item,
        {"project_id": str(project["id"]), "object_id": str(row["id"])},
    )
    return {
        "action": "create",
        "path": str(item.path),
        "project": project["slug"],
        "type": object_type,
        "id": str(row["id"]),
        "import_key": item.import_key,
    }


def fetch_existing_import(cur, item: ImportItem, project_id: Any) -> dict[str, Any] | None:
    table = TYPE_TABLES[item.memory_type]
    columns = ", ".join(TYPE_COLUMNS[item.memory_type])
    if item.db_id:
        cur.execute(
            f"""
            SELECT id, project_id, metadata, updated_at, {columns}
            FROM {table}
            WHERE id = %s AND project_id = %s
            """,
            (item.db_id, project_id),
        )
        row = cur.fetchone()
        if not row:
            raise NotFoundError(f"db_id not found for {item.memory_type}: {item.db_id}")
        return row

    cur.execute(
        f"""
        SELECT id, project_id, metadata, updated_at, {columns}
        FROM {table}
        WHERE project_id = %s
          AND metadata #>> '{{agent_hub_import,import_key}}' = %s
        ORDER BY updated_at DESC, id
        """,
        (project_id, item.import_key),
    )
    rows = cur.fetchall()
    if len(rows) > 1:
        raise ValidationError(f"Multiple rows found for import_key: {item.import_key}")
    return rows[0] if rows else None


def plan_import_item(
    cur,
    item: ImportItem,
    on_duplicate: str = "skip",
) -> dict[str, Any]:
    project = fetch_project(cur, item.project_slug)
    existing = fetch_existing_import(cur, item, project["id"])
    base = {
        "path": str(item.path),
        "project": project["slug"],
        "type": item.memory_type,
        "import_key": item.import_key,
    }
    if not existing:
        return {**base, "action": "create"}

    base["id"] = str(existing["id"])
    if on_duplicate == "error":
        return {**base, "action": "error", "reason": "duplicate import target"}
    if on_duplicate == "skip":
        return {**base, "action": "skip", "reason": "duplicate import target"}

    metadata = existing.get("metadata") or {}
    import_state = metadata.get("agent_hub_import") or {}
    previous_content_hash = import_state.get("content_hash")
    previous_data_hash = import_state.get("data_hash")
    last_data = import_state.get("data")
    if not isinstance(last_data, dict):
        last_data = {}
    database_values = row_values(item.memory_type, existing)
    markdown_values = item_values(item)
    current_data_hash = hash_payload(database_values)
    note_changed = previous_content_hash != item.content_hash
    database_changed = bool(previous_data_hash and previous_data_hash != current_data_hash)
    diffs = build_field_diffs(item, existing)

    if previous_content_hash == item.content_hash:
        if database_changed:
            database_fields = sorted(
                changed_fields_from_last(item.memory_type, database_values, last_data)
            )
            return {
                **base,
                "action": "skip",
                "reason": "database changed since last import; markdown unchanged",
                "database_changed_fields": database_fields,
            }
        return {**base, "action": "skip", "reason": "unchanged import content"}
    if note_changed and database_changed:
        database_fields = changed_fields_from_last(
            item.memory_type,
            database_values,
            last_data,
        )
        markdown_fields = changed_fields_from_last(
            item.memory_type,
            markdown_values,
            last_data,
        )
        conflicting_fields = sorted(database_fields & markdown_fields)
        return {
            **base,
            "action": "conflict",
            "reason": "database and markdown changed since last import",
            "diffs": diffs,
            "conflicting_fields": conflicting_fields,
        }
    return {**base, "action": "update", "diffs": diffs}


def update_import_item(
    cur,
    item: ImportItem,
    planned: dict[str, Any],
) -> dict[str, Any]:
    project = fetch_project(cur, item.project_slug)
    agent = ensure_import_agent(cur, project["id"])
    existing = fetch_existing_import(cur, item, project["id"])
    if not existing:
        raise NotFoundError(f"Import target disappeared: {item.import_key}")

    values = item_values(item)
    columns = list(values)
    set_clause = ", ".join([f"{column} = %s" for column in columns])
    metadata = import_metadata(item, existing.get("metadata") or {})
    params = [values[column] for column in columns]
    params.extend([json.dumps(metadata, default=json_default), existing["id"]])
    table = TYPE_TABLES[item.memory_type]
    if item.memory_type == "open_question":
        set_clause += (
            ", resolved_at = CASE "
            "WHEN status IN ('answered', 'closed') THEN COALESCE(resolved_at, now()) "
            "ELSE NULL END"
        )
    cur.execute(
        f"""
        UPDATE {table}
        SET {set_clause}, metadata = %s::jsonb
        WHERE id = %s
        RETURNING id
        """,
        params,
    )
    row = cur.fetchone()
    log_import_action(
        cur,
        agent["id"],
        "sync_obsidian_note",
        item.memory_type,
        row["id"],
        item,
        {"project_id": str(project["id"]), "object_id": str(row["id"])},
    )
    return {
        **planned,
        "action": "update",
        "id": str(row["id"]),
    }


def apply_import_item(cur, item: ImportItem, planned: dict[str, Any]) -> dict[str, Any]:
    if planned["action"] == "create":
        return insert_import_item(cur, item)
    if planned["action"] == "update":
        return update_import_item(cur, item, planned)
    return planned
