"""Project memory retrieval queries for Agent Data Hub."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from agent_hub.relations import fetch_project_relations
from agent_hub.statuses import (
    DRAFT_STATUS,
    INBOX_REVIEW_TYPES,
    agent_read_excluded_statuses,
    agent_read_excluded_statuses_by_type,
    format_draft_review_count,
    item_type_for_table,
    search_excluded_statuses,
    table_for_item_type,
)


def _status_filter(
    column: str,
    excluded_statuses: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    if not excluded_statuses:
        return "", ()
    placeholders = ", ".join(["%s"] * len(excluded_statuses))
    return f"AND {column} NOT IN ({placeholders})", excluded_statuses


def fetch_recent_rows(
    cur,
    table: str,
    project_id: object,
    columns: str,
    since: datetime,
    limit: int,
    excluded_statuses: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    status_clause, status_params = _status_filter("status", excluded_statuses)
    cur.execute(
        f"""
        SELECT id, {columns}, status, created_at, updated_at
        FROM {table}
        WHERE project_id = %s
          AND updated_at >= %s
          {status_clause}
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (project_id, since, *status_params, limit),
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
    *,
    surface: str = "daily",
) -> dict[str, object]:
    project_id = project["id"]
    agent_surface = surface != "daily"
    relation_exclusions = agent_read_excluded_statuses_by_type() if agent_surface else None
    return {
        "project": project,
        "since": since,
        "drafts_awaiting_review": fetch_drafts_awaiting_review(cur, project_id),
        "facts": fetch_recent_rows(
            cur,
            "facts",
            project_id,
            "statement, source, confidence",
            since,
            limit,
            agent_read_excluded_statuses("fact") if agent_surface else (),
        ),
        "decisions": fetch_recent_rows(
            cur,
            "decisions",
            project_id,
            "decision, rationale, consequences",
            since,
            limit,
            agent_read_excluded_statuses("decision") if agent_surface else (),
        ),
        "risks": fetch_recent_rows(
            cur,
            "risks",
            project_id,
            "title, severity, impact, mitigation",
            since,
            limit,
            agent_read_excluded_statuses("risk") if agent_surface else (),
        ),
        "open_questions": fetch_recent_rows(
            cur,
            "open_questions",
            project_id,
            "question, answer",
            since,
            limit,
            agent_read_excluded_statuses("open_question") if agent_surface else (),
        ),
        "reports": fetch_recent_rows(
            cur,
            "reports",
            project_id,
            "title, report_type, summary",
            since,
            limit,
            agent_read_excluded_statuses("report") if agent_surface else (),
        ),
        "relations": fetch_project_relations(
            cur,
            project_id,
            since=since,
            limit=limit,
            excluded_statuses_by_type=relation_exclusions,
        ),
        "agent_actions": fetch_recent_agent_actions(cur, project_id, since, limit),
        "sync_events": fetch_recent_sync_events(cur, since, limit),
    }


def fetch_brief_rows(
    cur,
    table: str,
    project_id: object,
    columns: str,
    excluded_statuses: tuple[str, ...] | None = None,
    limit: int = 8,
) -> list[dict[str, object]]:
    if excluded_statuses is None:
        excluded_statuses = agent_read_excluded_statuses(item_type_for_table(table))
    status_clause, status_params = _status_filter("status", excluded_statuses)
    cur.execute(
        f"""
        SELECT {columns}, status, updated_at
        FROM {table}
        WHERE project_id = %s
          {status_clause}
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s
        """,
        (project_id, *status_params, limit),
    )
    return list(cur.fetchall())


def fetch_drafts_awaiting_review(cur, project_id: object) -> dict[str, object]:
    by_type: dict[str, int] = {}
    for item_type in INBOX_REVIEW_TYPES:
        table = table_for_item_type(item_type)
        cur.execute(
            f"""
            SELECT count(*) AS count
            FROM {table}
            WHERE project_id = %s
              AND status = %s
            """,
            (project_id, DRAFT_STATUS),
        )
        count_key = "open_questions" if item_type == "open_question" else f"{item_type}s"
        by_type[count_key] = int(cur.fetchone()["count"])
    total = sum(by_type.values())
    return {
        "total": total,
        "by_type": by_type,
        "label": format_draft_review_count(total),
    }


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
    *,
    include_drafts: bool = False,
    include_archived: bool = False,
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
        excluded_statuses = search_excluded_statuses(
            item_type,
            include_drafts=include_drafts,
            include_archived=include_archived,
        )
        status_clause, status_params = _status_filter("status", excluded_statuses)
        cur.execute(
            f"""
            SELECT id, %s AS type, {select_expr}, status, updated_at
            FROM {table}
            WHERE project_id = %s
              AND {where_expr}
              {status_clause}
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            (item_type, project_id, *([like] * param_count), *status_params, limit),
        )
        results.extend(cur.fetchall())
    results.sort(key=lambda row: row["updated_at"], reverse=True)
    return results[:limit]
