"""Curated memory write helpers for Agent Data Hub."""

from __future__ import annotations

import argparse
import copy
import json

from agent_hub.errors import NotFoundError
from agent_hub.importing.constants import TYPE_COLUMNS, TYPE_TABLES
from agent_hub.rendering import truncate
from agent_hub.statuses import DRAFT_MEMORY_STATUSES
from agent_hub.writeback_routing import (
    card_for_item,
    candidate_type,
    identity_value,
    route_candidate,
)

REMEMBER_TYPES = (
    "fact",
    "decision",
    "open-question",
    "risk",
    "report",
)

DRAFT_STATUSES = DRAFT_MEMORY_STATUSES


class HumanReviewRequired(Exception):
    """Raised when a memory candidate needs explicit human review first."""

    def __init__(self, candidate: dict[str, object], reason: str) -> None:
        self.candidate = candidate
        self.reason = reason
        super().__init__(reason)


def json_default(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def ensure_project(cur, args: argparse.Namespace) -> dict[str, object]:
    cur.execute(
        """
        SELECT id, name, slug, description, status, metadata, created_at, updated_at
        FROM projects
        WHERE slug = %s
        """,
        (args.project,),
    )
    project = cur.fetchone()
    if project:
        return project
    if not getattr(args, "create_project", False):
        raise NotFoundError(
            f"Project '{args.project}' not found. "
            "Use --create-project to create it explicitly."
        )

    name = args.project_name or args.project.replace("-", " ").title()
    cur.execute(
        """
        INSERT INTO projects (name, slug, description, metadata)
        VALUES (%s, %s, %s, %s::jsonb)
        RETURNING id, name, slug, description, status, metadata, created_at, updated_at
        """,
        (
            name,
            args.project,
            args.project_description,
            json.dumps({"created_by": "agent-hub remember"}),
        ),
    )
    return cur.fetchone()


def fetch_project(cur, slug: str) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT id, name, slug, description, status, metadata, created_at, updated_at
        FROM projects
        WHERE slug = %s
        """,
        (slug,),
    )
    return cur.fetchone()


def ensure_agent(cur, project_id: object, slug: str, name: str) -> dict[str, object]:
    cur.execute(
        """
        INSERT INTO agents (project_id, name, slug, role, status, metadata)
        VALUES (%s, %s, %s, %s, 'active', %s::jsonb)
        ON CONFLICT (project_id, slug) DO UPDATE SET
          name = EXCLUDED.name,
          role = EXCLUDED.role,
          status = EXCLUDED.status,
          metadata = agents.metadata || EXCLUDED.metadata
        RETURNING id, project_id, name, slug, role, status, metadata
        """,
        (
            project_id,
            name,
            slug,
            "Coding and implementation agent",
            json.dumps({"interface": "agent-hub"}),
        ),
    )
    return cur.fetchone()


def log_agent_action(
    cur,
    agent_id: object,
    action: str,
    object_type: str,
    object_id: object,
    input_payload: dict[str, object],
    output: dict[str, object],
    metadata: dict[str, object] | None = None,
) -> None:
    action_metadata = metadata or {"created_by": "agent-hub remember"}
    cur.execute(
        """
        INSERT INTO agent_actions (
          agent_id, action, object_type, object_id,
          input, output, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, 'succeeded', %s::jsonb)
        """,
        (
            agent_id,
            action,
            object_type,
            object_id,
            json.dumps(input_payload),
            json.dumps(output, default=json_default),
            json.dumps(action_metadata, default=json_default),
        ),
    )


def memory_type_to_object_type(value: str) -> str:
    return value.replace("-", "_")


def candidate_from_args(
    args: argparse.Namespace,
    metadata: dict[str, object],
) -> dict[str, object]:
    object_type = memory_type_to_object_type(args.memory_type)
    candidate: dict[str, object] = {
        "type": object_type,
        "text": args.text,
        "source": args.source,
        "status": args.status,
        "metadata": metadata,
    }
    if object_type == "fact":
        candidate.update(
            {
                "statement": args.text,
                "confidence": getattr(args, "confidence", None),
            }
        )
    elif object_type == "decision":
        candidate.update(
            {
                "decision": args.text,
                "rationale": getattr(args, "rationale", None),
                "consequences": getattr(args, "consequences", None),
            }
        )
    elif object_type == "open_question":
        candidate.update(
            {
                "question": args.text,
                "answer": getattr(args, "answer", None),
            }
        )
    elif object_type == "risk":
        candidate.update(
            {
                "title": args.text,
                "severity": getattr(args, "severity", None),
                "impact": getattr(args, "impact", None),
                "mitigation": getattr(args, "mitigation", None),
            }
        )
    elif object_type == "report":
        candidate.update(
            {
                "title": getattr(args, "title", None) or truncate(args.text, 80),
                "report_type": getattr(args, "report_type", None),
                "summary": getattr(args, "summary", None),
                "body": getattr(args, "body", None) or args.text,
            }
        )
    for key in ("import_key", "identity"):
        if key in metadata:
            candidate[key] = metadata[key]
    return candidate


def fetch_existing_memory(
    cur,
    project_id: object,
    candidate: dict[str, object],
) -> list[dict[str, object]]:
    item_type = candidate_type(candidate)
    item_identity = identity_value(candidate)
    if not item_identity or item_type not in TYPE_TABLES:
        return []

    table = TYPE_TABLES[item_type]
    columns = ", ".join(TYPE_COLUMNS[item_type])
    cur.execute(
        f"""
        SELECT id, project_id, metadata, updated_at, {columns}
        FROM {table}
        WHERE project_id = %s
          AND (
            id::text = %s
            OR metadata #>> '{{agent_hub_import,import_key}}' = %s
            OR metadata #>> '{{agent_hub_writeback,identity}}' = %s
            OR metadata ->> 'import_key' = %s
            OR metadata ->> 'identity' = %s
          )
        ORDER BY updated_at DESC, id DESC
        """,
        (
            project_id,
            item_identity,
            item_identity,
            item_identity,
            item_identity,
            item_identity,
        ),
    )
    rows = []
    for row in cur.fetchall():
        rows.append({**row, "type": item_type})
    return rows


def route_remember_candidate(
    cur,
    project: dict[str, object] | None,
    args: argparse.Namespace,
    metadata: dict[str, object],
) -> tuple[dict[str, object], str, str]:
    candidate = candidate_from_args(args, metadata)
    tier, reason = route_candidate(candidate, [])
    if tier == "ask":
        raise HumanReviewRequired(candidate, reason)
    existing = fetch_existing_memory(cur, project["id"], candidate) if project else []
    tier, reason = route_candidate(candidate, existing)
    if tier == "ask":
        raise HumanReviewRequired(candidate, reason)
    return candidate, tier, reason


def remember_plan(
    cur,
    args: argparse.Namespace,
    metadata: dict[str, object],
) -> dict[str, object]:
    project = fetch_project(cur, args.project)
    if not project:
        if getattr(args, "create_project", False):
            candidate = candidate_from_args(args, metadata)
            tier, reason = route_candidate(candidate, [])
            if tier == "ask":
                raise HumanReviewRequired(candidate, reason)
            object_type = memory_type_to_object_type(args.memory_type)
            status = DRAFT_STATUSES[object_type] if tier == "draft" else args.status
            return {
                "project": {
                    "id": None,
                    "slug": args.project,
                    "name": args.project_name or args.project.replace("-", " ").title(),
                },
                "type": object_type,
                "tier": tier,
                "reason": reason,
                "status": status,
                "card": card_for_item(candidate),
            }
        raise NotFoundError(
            f"Project '{args.project}' not found. "
            "Use --create-project to create it explicitly."
        )
    candidate, tier, reason = route_remember_candidate(cur, project, args, metadata)
    object_type = memory_type_to_object_type(args.memory_type)
    status = getattr(args, "status", None)
    if tier == "draft":
        status = DRAFT_STATUSES[object_type]
    return {
        "project": {
            "id": project["id"],
            "slug": project["slug"],
            "name": project["name"],
        },
        "type": object_type,
        "tier": tier,
        "reason": reason,
        "status": status,
        "card": card_for_item(candidate),
    }


def insert_fact(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "verified"
    cur.execute(
        """
        INSERT INTO facts (project_id, statement, source, confidence, status, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, statement, source, confidence, status, created_at
        """,
        (
            project_id,
            args.text,
            args.source,
            args.confidence,
            status,
            json.dumps(metadata),
        ),
    )
    return "fact", cur.fetchone()


def insert_decision(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "accepted"
    cur.execute(
        """
        INSERT INTO decisions (
          project_id, decision, rationale, consequences, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, decision, rationale, consequences, status, created_at
        """,
        (
            project_id,
            args.text,
            args.rationale,
            args.consequences,
            status,
            json.dumps(metadata),
        ),
    )
    return "decision", cur.fetchone()


def insert_open_question(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "open"
    cur.execute(
        """
        INSERT INTO open_questions (
          project_id, question, answer, status, resolved_at, metadata
        )
        VALUES (
          %s, %s, %s, %s,
          CASE WHEN %s IN ('answered', 'closed') THEN now() ELSE NULL END,
          %s::jsonb
        )
        RETURNING id, question, answer, status, resolved_at, created_at
        """,
        (
            project_id,
            args.text,
            args.answer,
            status,
            status,
            json.dumps(metadata),
        ),
    )
    return "open_question", cur.fetchone()


def insert_risk(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "open"
    cur.execute(
        """
        INSERT INTO risks (
          project_id, title, severity, impact, mitigation, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, title, severity, impact, mitigation, status, created_at
        """,
        (
            project_id,
            args.text,
            args.severity,
            args.impact,
            args.mitigation,
            status,
            json.dumps(metadata),
        ),
    )
    return "risk", cur.fetchone()


def insert_report(
    cur, project_id: object, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[str, dict[str, object]]:
    status = args.status or "published"
    title = args.title or truncate(args.text, 80)
    body = args.body or args.text
    cur.execute(
        """
        INSERT INTO reports (
          project_id, title, report_type, summary, body, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, title, report_type, summary, status, created_at
        """,
        (
            project_id,
            title,
            args.report_type,
            args.summary,
            body,
            status,
            json.dumps(metadata),
        ),
    )
    return "report", cur.fetchone()


REMEMBER_INSERTS = {
    "fact": insert_fact,
    "decision": insert_decision,
    "open-question": insert_open_question,
    "risk": insert_risk,
    "report": insert_report,
}


def remember(
    cur, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], str, dict[str, object]]:
    route_remember_candidate(cur, None, args, metadata)
    project = ensure_project(cur, args)
    _candidate, tier, reason = route_remember_candidate(cur, project, args, metadata)
    metadata = dict(metadata)
    metadata["agent_hub_writeback"] = {
        "tier": tier,
        "reason": reason,
        "original_status": args.status,
    }
    write_args = copy.copy(args)
    object_type = memory_type_to_object_type(args.memory_type)
    if tier == "draft":
        write_args.status = DRAFT_STATUSES[object_type]
    agent = ensure_agent(cur, project["id"], args.agent, args.agent_name)
    insert_func = REMEMBER_INSERTS[args.memory_type]
    object_type, row = insert_func(cur, project["id"], write_args, metadata)
    log_agent_action(
        cur,
        agent["id"],
        f"remember_{object_type}",
        object_type,
        row["id"],
        {
            "command": "remember",
            "project": args.project,
            "type": args.memory_type,
            "source": args.source,
        },
        {
            "project_id": project["id"],
            "object": row,
            "writeback_tier": tier,
            "writeback_reason": reason,
        },
    )
    return project, agent, object_type, row


def answer_question(
    cur, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    project = ensure_project(cur, args)
    agent = ensure_agent(cur, project["id"], args.agent, args.agent_name)

    cur.execute(
        """
        SELECT id, question, answer, status, resolved_at, metadata, created_at
        FROM open_questions
        WHERE id = %s AND project_id = %s
        """,
        (args.question_id, project["id"]),
    )
    existing = cur.fetchone()
    if not existing:
        raise NotFoundError(
            f"open question '{args.question_id}' not found in project '{args.project}'"
        )

    merged_metadata = dict(existing.get("metadata") or {})
    merged_metadata.update(metadata)

    cur.execute(
        """
        UPDATE open_questions
        SET answer = %s,
            status = %s,
            resolved_at = CASE
              WHEN %s IN ('answered', 'closed') THEN COALESCE(resolved_at, now())
              ELSE resolved_at
            END,
            metadata = %s::jsonb
        WHERE id = %s AND project_id = %s
        RETURNING id, question, answer, status, resolved_at, created_at
        """,
        (
            args.answer,
            args.status,
            args.status,
            json.dumps(merged_metadata),
            args.question_id,
            project["id"],
        ),
    )
    row = cur.fetchone()

    log_agent_action(
        cur,
        agent["id"],
        "answer_open_question",
        "open_question",
        row["id"],
        {
            "command": "answer-question",
            "project": args.project,
            "question_id": str(args.question_id),
            "status": args.status,
            "source": args.source,
        },
        {
            "project_id": project["id"],
            "previous_status": existing["status"],
            "object": row,
        },
    )
    return project, agent, row


def update_decision(
    cur, args: argparse.Namespace, metadata: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    project = ensure_project(cur, args)
    agent = ensure_agent(cur, project["id"], args.agent, args.agent_name)

    cur.execute(
        """
        SELECT id, decision, rationale, consequences, status, metadata, created_at
        FROM decisions
        WHERE id = %s AND project_id = %s
        """,
        (args.decision_id, project["id"]),
    )
    existing = cur.fetchone()
    if not existing:
        raise NotFoundError(
            f"decision '{args.decision_id}' not found in project '{args.project}'"
        )

    if (
        args.rationale is None
        and args.consequences is None
        and args.status is None
        and not metadata
    ):
        raise ValueError(
            "update-decision requires at least one change: --rationale, "
            "--consequences, --status, or --metadata"
        )

    merged_metadata = dict(existing.get("metadata") or {})
    merged_metadata.update(metadata)

    cur.execute(
        """
        UPDATE decisions
        SET rationale = COALESCE(%s, rationale),
            consequences = COALESCE(%s, consequences),
            status = COALESCE(%s, status),
            metadata = %s::jsonb
        WHERE id = %s AND project_id = %s
        RETURNING id, decision, rationale, consequences, status, created_at
        """,
        (
            args.rationale,
            args.consequences,
            args.status,
            json.dumps(merged_metadata),
            args.decision_id,
            project["id"],
        ),
    )
    row = cur.fetchone()

    log_agent_action(
        cur,
        agent["id"],
        "update_decision",
        "decision",
        row["id"],
        {
            "command": "update-decision",
            "project": args.project,
            "decision_id": str(args.decision_id),
            "status": args.status,
            "source": args.source,
            "updated_fields": [
                field
                for field, value in (
                    ("rationale", args.rationale),
                    ("consequences", args.consequences),
                    ("status", args.status),
                )
                if value is not None
            ],
        },
        {
            "project_id": project["id"],
            "previous_status": existing["status"],
            "object": row,
        },
    )
    return project, agent, row
