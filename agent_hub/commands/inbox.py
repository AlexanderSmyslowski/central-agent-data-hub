"""Review inbox command for draft memory candidates."""

from __future__ import annotations

import argparse
import json
from typing import Any

from agent_hub.commands.common import (
    error,
    exception_error,
    json_default,
    require_database_url,
)
from agent_hub.db import connect
from agent_hub.memory import ensure_agent, log_agent_action
from agent_hub.reviewers import (
    resolve_required_reviewer,
    resolve_responsible_reviewer,
    validate_reviewer_handle,
)
from agent_hub.writeback_routing import card_for_item


INBOX_TABLES = {
    "fact": {
        "table": "facts",
        "columns": "memory.id, memory.project_id, memory.statement, memory.source, memory.confidence, memory.status, memory.metadata, memory.created_at, memory.updated_at",
        "reviewed_status": "verified",
    },
    "decision": {
        "table": "decisions",
        "columns": "memory.id, memory.project_id, memory.decision, memory.rationale, memory.consequences, memory.status, memory.metadata, memory.created_at, memory.updated_at",
        "reviewed_status": "accepted",
    },
    "risk": {
        "table": "risks",
        "columns": "memory.id, memory.project_id, memory.title, memory.severity, memory.impact, memory.mitigation, memory.status, memory.metadata, memory.created_at, memory.updated_at",
        "reviewed_status": "open",
    },
    "open_question": {
        "table": "open_questions",
        "columns": "memory.id, memory.project_id, memory.question, memory.answer, memory.status, memory.metadata, memory.created_at, memory.updated_at",
        "reviewed_status": "open",
    },
    "report": {
        "table": "reports",
        "columns": "memory.id, memory.project_id, memory.title, memory.report_type, memory.summary, memory.body, memory.status, memory.metadata, memory.created_at, memory.updated_at",
        "reviewed_status": "published",
    },
}


def row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("updated_at") or ""),
        str(row.get("created_at") or ""),
        str(row.get("id") or ""),
    )


def row_with_type(row: dict[str, Any], item_type: str) -> dict[str, Any]:
    draft = {**row, "type": item_type}
    resolution = resolve_responsible_reviewer(draft)
    draft["responsible_reviewer"] = resolution.handle
    draft["resolution_reason"] = resolution.reason
    draft.pop("project_metadata", None)
    return draft


def fetch_drafts(
    cur,
    *,
    project_slug: str | None = None,
    for_reviewer: str | None = None,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item_type, spec in INBOX_TABLES.items():
        params: list[Any] = ["draft"]
        project_filter = ""
        if project_slug:
            project_filter = "AND p.slug = %s"
            params.append(project_slug)
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT %s"
            params.append(limit)
        cur.execute(
            f"""
            SELECT {spec['columns']},
                   p.slug AS project,
                   p.name AS project_name,
                   p.metadata AS project_metadata
            FROM {spec['table']} AS memory
            JOIN projects AS p ON p.id = memory.project_id
            WHERE memory.status = %s
              {project_filter}
            ORDER BY memory.updated_at DESC, memory.created_at DESC, memory.id DESC
            {limit_clause}
            """,
            tuple(params),
        )
        rows.extend(row_with_type(row, item_type) for row in cur.fetchall())
    if for_reviewer:
        rows = [row for row in rows if row["responsible_reviewer"] == for_reviewer]
    rows.sort(key=row_sort_key, reverse=True)
    return rows[:limit] if limit is not None else rows


def find_draft(
    cur,
    draft_id: str,
    *,
    project_slug: str | None = None,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for item_type, spec in INBOX_TABLES.items():
        params: list[Any] = [draft_id, "draft"]
        project_filter = ""
        if project_slug:
            project_filter = "AND p.slug = %s"
            params.append(project_slug)
        cur.execute(
            f"""
            SELECT {spec['columns']},
                   p.slug AS project,
                   p.name AS project_name,
                   p.metadata AS project_metadata
            FROM {spec['table']} AS memory
            JOIN projects AS p ON p.id = memory.project_id
            WHERE memory.id = %s
              AND memory.status = %s
              {project_filter}
            """,
            tuple(params),
        )
        row = cur.fetchone()
        if row:
            matches.append(row_with_type(row, item_type))
    if len(matches) > 1:
        raise ValueError(f"draft id is ambiguous across memory types: {draft_id}")
    return matches[0] if matches else None


def review_draft(
    cur,
    row: dict[str, Any],
    *,
    decision: str,
    agent_slug: str,
    agent_name: str,
    reviewed_by: str,
    review_source: str,
) -> dict[str, Any]:
    reviewed_by = validate_reviewer_handle(reviewed_by)
    if not review_source:
        raise ValueError("review_source is required")
    if "responsible_reviewer" not in row or "resolution_reason" not in row:
        resolution = resolve_responsible_reviewer(row)
        row = {
            **row,
            "responsible_reviewer": resolution.handle,
            "resolution_reason": resolution.reason,
        }
    item_type = row["type"]
    spec = INBOX_TABLES[item_type]
    table = spec["table"]
    next_status = spec["reviewed_status"] if decision == "accept" else "archived"
    metadata = dict(row.get("metadata") or {})
    review_state = {
        "decision": decision,
        "previous_status": row["status"],
        "next_status": next_status,
        "reviewed_by": reviewed_by,
        "review_source": review_source,
        "responsible_reviewer": row.get("responsible_reviewer"),
        "resolution_reason": row.get("resolution_reason"),
    }
    metadata["agent_hub_review"] = review_state
    cur.execute(
        f"""
        UPDATE {table}
        SET status = %s,
            metadata = %s::jsonb
        WHERE id = %s
          AND status = 'draft'
        RETURNING id, status
        """,
        (next_status, json.dumps(metadata, default=json_default), row["id"]),
    )
    updated = cur.fetchone()
    if not updated:
        raise ValueError(f"draft disappeared before review: {row['id']}")

    agent = ensure_agent(cur, row["project_id"], agent_slug, agent_name)
    action_metadata = {
        "command": "inbox",
        "decision": decision,
        "project": row["project"],
        "reviewed_by": reviewed_by,
        "review_source": review_source,
        "responsible_reviewer": row.get("responsible_reviewer"),
        "resolution_reason": row.get("resolution_reason"),
    }

    log_agent_action(
        cur,
        agent["id"],
        f"inbox_{decision}",
        item_type,
        row["id"],
        action_metadata,
        {
            "project_id": row["project_id"],
            "previous_status": row["status"],
            "next_status": next_status,
            "reviewed_by": reviewed_by,
            "review_source": review_source,
            "responsible_reviewer": row.get("responsible_reviewer"),
            "resolution_reason": row.get("resolution_reason"),
        },
        {
            "created_by": "agent-hub inbox",
            "reviewed_by": reviewed_by,
            "review_source": review_source,
            "responsible_reviewer": row.get("responsible_reviewer"),
            "resolution_reason": row.get("resolution_reason"),
        },
    )
    return {
        "id": str(row["id"]),
        "project": row["project"],
        "type": item_type,
        "decision": decision,
        "status": next_status,
        "reviewed_by": reviewed_by,
        "review_source": review_source,
        "responsible_reviewer": row.get("responsible_reviewer"),
        "resolution_reason": row.get("resolution_reason"),
    }


def review_draft_by_id(
    cur,
    draft_id: str,
    *,
    decision: str,
    item_type: str | None = None,
    project_slug: str | None = None,
    agent_slug: str,
    agent_name: str,
    reviewed_by: str,
    review_source: str,
) -> dict[str, Any] | None:
    row = find_draft(cur, draft_id, project_slug=project_slug)
    if not row:
        return None
    if item_type and row["type"] != item_type:
        raise ValueError("draft type does not match the selected review action")
    return review_draft(
        cur,
        row,
        decision=decision,
        agent_slug=agent_slug,
        agent_name=agent_name,
        reviewed_by=reviewed_by,
        review_source=review_source,
    )


def print_draft_cards(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No draft memory candidates.")
        return
    for row in rows:
        print(f"{row['id']} [{row['project']} / {row['type']}]")
        print(
            "Responsible reviewer: "
            f"{row['responsible_reviewer']} ({row['resolution_reason']})"
        )
        print(card_for_item(row))
        print()


def run_inbox(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    review_ids = args.accept or args.reject
    decision = "accept" if args.accept else "reject" if args.reject else None

    try:
        for_reviewer = None
        if args.for_reviewer:
            for_reviewer = validate_reviewer_handle(args.for_reviewer)
        reviewed_by = None
        if review_ids:
            reviewed_by = resolve_required_reviewer(args.reviewer)
        with connect() as conn:
            with conn.cursor() as cur:
                if not review_ids:
                    rows = fetch_drafts(
                        cur,
                        project_slug=args.project,
                        for_reviewer=for_reviewer,
                        limit=args.limit,
                    )
                    if args.format == "json":
                        payload = [{**row, "card": card_for_item(row)} for row in rows]
                        print(
                            json.dumps(
                                payload,
                                indent=2,
                                default=json_default,
                                ensure_ascii=False,
                            )
                        )
                    else:
                        print_draft_cards(rows)
                    return 0

                reviewed = []
                missing = []
                for draft_id in review_ids:
                    result = review_draft_by_id(
                        cur,
                        draft_id,
                        decision=decision or "reject",
                        project_slug=args.project,
                        agent_slug=args.agent,
                        agent_name=args.agent_name,
                        review_source="cli",
                        reviewed_by=reviewed_by,
                    )
                    if not result:
                        missing.append(str(draft_id))
                        continue
                    reviewed.append(result)
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(
            json.dumps(
                {"reviewed": reviewed, "missing": missing},
                indent=2,
                default=json_default,
                ensure_ascii=False,
            )
        )
    else:
        for row in reviewed:
            print(
                f"{row['decision']} {row['type']} {row['project']}: "
                f"{row['id']} -> {row['status']}"
            )
        for draft_id in missing:
            print(f"missing draft: {draft_id}")

    return error("some draft ids were not found", 1) if missing else 0
