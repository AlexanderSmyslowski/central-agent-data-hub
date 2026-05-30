"""Curated memory write helpers for Agent Data Hub."""

from __future__ import annotations

import argparse
import json

from agent_hub.errors import NotFoundError
from agent_hub.rendering import truncate

REMEMBER_TYPES = (
    "fact",
    "decision",
    "open-question",
    "risk",
    "report",
)


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
    args: argparse.Namespace,
    output: dict[str, object],
) -> None:
    input_payload = {
        "command": "remember",
        "project": args.project,
        "type": args.memory_type,
        "source": args.source,
    }
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
            json.dumps({"created_by": "agent-hub remember"}),
        ),
    )


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
    project = ensure_project(cur, args)
    agent = ensure_agent(cur, project["id"], args.agent, args.agent_name)
    insert_func = REMEMBER_INSERTS[args.memory_type]
    object_type, row = insert_func(cur, project["id"], args, metadata)
    log_agent_action(
        cur,
        agent["id"],
        f"remember_{object_type}",
        object_type,
        row["id"],
        args,
        {"project_id": project["id"], "object": row},
    )
    return project, agent, object_type, row
