"""Relation vocabulary and query helpers for Agent Data Hub."""

from __future__ import annotations

from datetime import datetime

RELATION_TARGETS = {
    "project": "projects",
    "agent": "agents",
    "document": "documents",
    "report": "reports",
    "decision": "decisions",
    "fact": "facts",
    "open_question": "open_questions",
    "risk": "risks",
    "agent_action": "agent_actions",
}

RELATION_TYPES = (
    "supports",
    "contradicts",
    "supersedes",
    "mitigates",
    "answers",
    "raises",
    "references",
    "derived_from",
    "blocks",
    "depends_on",
)

RELATION_SUMMARY_COLUMNS = {
    "project": "name",
    "agent": "name",
    "document": "title",
    "report": "title",
    "decision": "decision",
    "fact": "statement",
    "open_question": "question",
    "risk": "title",
    "agent_action": "action",
}


def fetch_relation_object(
    cur, object_type: str, object_id: str
) -> dict[str, object] | None:
    table = RELATION_TARGETS[object_type]
    summary_column = RELATION_SUMMARY_COLUMNS[object_type]
    if object_type == "agent_action":
        cur.execute(
            f"""
            SELECT aa.id, a.project_id, aa.{summary_column} AS summary
            FROM agent_actions aa
            LEFT JOIN agents a ON a.id = aa.agent_id
            WHERE aa.id = %s
            """,
            (object_id,),
        )
    else:
        select_project_id = (
            "id AS project_id" if object_type == "project" else "project_id"
        )
        cur.execute(
            f"""
            SELECT id, {select_project_id}, {summary_column} AS summary
            FROM {table}
            WHERE id = %s
            """,
            (object_id,),
        )
    return cur.fetchone()


def validate_relation_object(
    object_type: str,
    row: dict[str, object] | None,
    project: dict[str, object],
    role: str,
) -> None:
    if not row:
        raise RuntimeError(f"{role} {object_type} not found")

    project_id = row.get("project_id")
    if object_type == "agent" and project_id is None:
        return
    if project_id != project["id"]:
        raise RuntimeError(
            f"{role} {object_type}:{row['id']} does not belong to project "
            f"{project['slug']}"
        )


def relation_project_filter(project_id: object) -> tuple[str, dict[str, object]]:
    filters = []
    params: dict[str, object] = {"project_id": project_id}
    for side in ("source", "target"):
        side_filters = []
        for object_type, table in RELATION_TARGETS.items():
            if object_type == "project":
                side_filters.append(
                    f"(r.{side}_type = 'project' AND r.{side}_id = %(project_id)s)"
                )
            elif object_type == "agent":
                side_filters.append(
                    f"""
                    (r.{side}_type = 'agent' AND EXISTS (
                      SELECT 1 FROM agents a
                      WHERE a.id = r.{side}_id
                        AND a.project_id = %(project_id)s
                    ))
                    """
                )
            elif object_type == "agent_action":
                side_filters.append(
                    f"""
                    (r.{side}_type = 'agent_action' AND EXISTS (
                      SELECT 1 FROM agent_actions aa
                      LEFT JOIN agents a ON a.id = aa.agent_id
                      WHERE aa.id = r.{side}_id
                        AND a.project_id = %(project_id)s
                    ))
                    """
                )
            else:
                side_filters.append(
                    f"""
                    (r.{side}_type = '{object_type}' AND EXISTS (
                      SELECT 1 FROM {table} t
                      WHERE t.id = r.{side}_id
                        AND t.project_id = %(project_id)s
                    ))
                    """
                )
        filters.append("(" + " OR ".join(side_filters) + ")")
    return "(" + " OR ".join(filters) + ")", params


def relation_summary_expression(side: str) -> str:
    parts = []
    for object_type, table in RELATION_TARGETS.items():
        summary_column = RELATION_SUMMARY_COLUMNS[object_type]
        if object_type == "agent_action":
            parts.append(
                f"""
                WHEN r.{side}_type = 'agent_action' THEN (
                  SELECT aa.{summary_column}
                  FROM agent_actions aa
                  WHERE aa.id = r.{side}_id
                )
                """
            )
        else:
            parts.append(
                f"""
                WHEN r.{side}_type = '{object_type}' THEN (
                  SELECT t.{summary_column}
                  FROM {table} t
                  WHERE t.id = r.{side}_id
                )
                """
            )
    return "CASE " + " ".join(parts) + " END"


def fetch_project_relations(
    cur,
    project_id: object,
    object_type: str | None = None,
    object_id: str | None = None,
    since: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    project_where, params = relation_project_filter(project_id)
    clauses = [project_where]
    if object_type and object_id:
        clauses.append(
            """
            (
              (r.source_type = %(object_type)s AND r.source_id = %(object_id)s)
              OR
              (r.target_type = %(object_type)s AND r.target_id = %(object_id)s)
            )
            """
        )
        params["object_type"] = object_type
        params["object_id"] = object_id
    elif object_type or object_id:
        raise RuntimeError("--object-type and --object-id must be used together")

    if since:
        clauses.append("r.updated_at >= %(since)s")
        params["since"] = since

    limit_sql = ""
    if limit:
        limit_sql = "LIMIT %(limit)s"
        params["limit"] = limit

    cur.execute(
        f"""
        SELECT
          r.id,
          r.source_type,
          r.source_id,
          {relation_summary_expression("source")} AS source_summary,
          r.relation_type,
          r.target_type,
          r.target_id,
          {relation_summary_expression("target")} AS target_summary,
          r.metadata,
          r.created_at,
          r.updated_at
        FROM relations r
        WHERE {" AND ".join(clauses)}
        ORDER BY r.updated_at DESC, r.created_at DESC, r.id
        {limit_sql}
        """,
        params,
    )
    return list(cur.fetchall())
