"""Project memory retrieval queries for Agent Data Hub."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from agent_hub.relations import fetch_project_relations


def fetch_recent_rows(
    cur,
    table: str,
    project_id: object,
    columns: str,
    since: datetime,
    limit: int,
) -> list[dict[str, object]]:
    cur.execute(
        f"""
        SELECT id, {columns}, status, created_at, updated_at
        FROM {table}
        WHERE project_id = %s
          AND updated_at >= %s
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (project_id, since, limit),
    )
    return list(cur.fetchall())


def fetch_recent_agent_actions(
    cur, project_id: object, since: datetime, limit: int
) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT
          aa.id,
          aa.action,
          aa.object_type,
          aa.object_id,
          aa.status,
          aa.created_at,
          aa.updated_at,
          a.slug AS agent_slug
        FROM agent_actions aa
        LEFT JOIN agents a ON a.id = aa.agent_id
        WHERE a.project_id = %s
          AND aa.updated_at >= %s
        ORDER BY aa.updated_at DESC, aa.created_at DESC, aa.id DESC
        LIMIT %s
        """,
        (project_id, since, limit),
    )
    return list(cur.fetchall())


def fetch_recent_sync_events(cur, since: datetime, limit: int) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, source, direction, status, error, created_at, updated_at
        FROM sync_events
        WHERE updated_at >= %s
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (since, limit),
    )
    return list(cur.fetchall())


def fetch_activity_snapshot(
    cur,
    project: dict[str, object],
    since: datetime,
    limit: int,
) -> dict[str, object]:
    project_id = project["id"]
    return {
        "project": project,
        "since": since,
        "facts": fetch_recent_rows(
            cur,
            "facts",
            project_id,
            "statement, source, confidence",
            since,
            limit,
        ),
        "decisions": fetch_recent_rows(
            cur,
            "decisions",
            project_id,
            "decision, rationale, consequences",
            since,
            limit,
        ),
        "risks": fetch_recent_rows(
            cur,
            "risks",
            project_id,
            "title, severity, impact, mitigation",
            since,
            limit,
        ),
        "open_questions": fetch_recent_rows(
            cur,
            "open_questions",
            project_id,
            "question, answer",
            since,
            limit,
        ),
        "reports": fetch_recent_rows(
            cur,
            "reports",
            project_id,
            "title, report_type, summary",
            since,
            limit,
        ),
        "relations": fetch_project_relations(
            cur,
            project_id,
            since=since,
            limit=limit,
        ),
        "agent_actions": fetch_recent_agent_actions(cur, project_id, since, limit),
        "sync_events": fetch_recent_sync_events(cur, since, limit),
    }


def fetch_brief_rows(
    cur,
    table: str,
    project_id: object,
    columns: str,
    excluded_statuses: tuple[str, ...] = ("archived",),
    limit: int = 8,
) -> list[dict[str, object]]:
    placeholders = ", ".join(["%s"] * len(excluded_statuses))
    cur.execute(
        f"""
        SELECT {columns}, status, updated_at
        FROM {table}
        WHERE project_id = %s
          AND status NOT IN ({placeholders})
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (project_id, *excluded_statuses, limit),
    )
    return list(cur.fetchall())


def write_daily_report(
    cur,
    project: dict[str, object],
    payload: dict[str, object],
    body: str,
) -> dict[str, object]:
    counts = {
        key: len(payload[key])
        for key in ("facts", "decisions", "risks", "open_questions", "relations")
    }
    summary = (
        f"Daily summary: {counts['facts']} facts, {counts['decisions']} decisions, "
        f"{counts['risks']} risks, {counts['open_questions']} open questions, "
        f"{counts['relations']} relations."
    )
    cur.execute(
        """
        INSERT INTO reports (
          project_id, title, report_type, summary, body, status, metadata
        )
        VALUES (%s, %s, 'daily', %s, %s, 'published', %s::jsonb)
        RETURNING id, title, report_type, summary, status, created_at
        """,
        (
            project["id"],
            f"Daily Report - {project['name']} - {datetime.now(timezone.utc).date()}",
            summary,
            body,
            json.dumps(
                {
                    "created_by": "agent-hub daily",
                    "since": payload["since"].isoformat(),
                    "counts": counts,
                }
            ),
        ),
    )
    return cur.fetchone()


def search_project_memory(
    cur,
    project_id: object,
    query: str,
    memory_type: str,
    limit: int,
) -> list[dict[str, object]]:
    like = f"%{query}%"
    specs = {
        "fact": (
            "facts",
            "statement AS title, statement AS text",
            "(statement ILIKE %s OR COALESCE(source, '') ILIKE %s)",
        ),
        "decision": (
            "decisions",
            "decision AS title, decision || COALESCE(E'\n' || rationale, '') AS text",
            "(decision ILIKE %s OR COALESCE(rationale, '') ILIKE %s OR COALESCE(consequences, '') ILIKE %s)",
        ),
        "risk": (
            "risks",
            "title, title || COALESCE(E'\n' || impact, '') || COALESCE(E'\n' || mitigation, '') AS text",
            "(title ILIKE %s OR COALESCE(impact, '') ILIKE %s OR COALESCE(mitigation, '') ILIKE %s)",
        ),
        "open_question": (
            "open_questions",
            "question AS title, question || COALESCE(E'\n' || answer, '') AS text",
            "(question ILIKE %s OR COALESCE(answer, '') ILIKE %s)",
        ),
        "report": (
            "reports",
            "title, title || COALESCE(E'\n' || summary, '') || COALESCE(E'\n' || body, '') AS text",
            "(title ILIKE %s OR COALESCE(summary, '') ILIKE %s OR COALESCE(body, '') ILIKE %s)",
        ),
    }
    selected = specs.keys() if memory_type == "all" else (memory_type,)
    results: list[dict[str, object]] = []
    for item_type in selected:
        table, select_expr, where_expr = specs[item_type]
        param_count = where_expr.count("%s")
        cur.execute(
            f"""
            SELECT id, %s AS type, {select_expr}, status, updated_at
            FROM {table}
            WHERE project_id = %s
              AND {where_expr}
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            (item_type, project_id, *([like] * param_count), limit),
        )
        results.extend(cur.fetchall())
    results.sort(key=lambda row: row["updated_at"], reverse=True)
    return results[:limit]
