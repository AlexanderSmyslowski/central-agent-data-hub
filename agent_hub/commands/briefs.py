"""Brief command handler."""

from __future__ import annotations

import argparse
import json

from agent_hub.commands.common import (
    exception_error,
    fetch_project,
    json_default,
    require_database_url,
    print_relations,
    print_rows,
    project_not_found,
)
from agent_hub.db import connect
from agent_hub.relations import fetch_project_relations
from agent_hub.retrieval import fetch_brief_rows
from agent_hub.statuses import INACTIVE_OPEN_QUESTION_STATUSES


def run_brief(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)

                cur.execute(
                    """
                    SELECT
                      (SELECT count(*) FROM documents WHERE project_id = %(project_id)s) AS documents,
                      (SELECT count(*) FROM facts WHERE project_id = %(project_id)s) AS facts,
                      (SELECT count(*) FROM decisions WHERE project_id = %(project_id)s) AS decisions,
                      (SELECT count(*) FROM open_questions WHERE project_id = %(project_id)s) AS open_questions,
                      (SELECT count(*) FROM risks WHERE project_id = %(project_id)s) AS risks,
                      (SELECT count(*) FROM reports WHERE project_id = %(project_id)s) AS reports,
                      (SELECT count(*) FROM agent_actions aa
                        JOIN agents a ON a.id = aa.agent_id
                        WHERE a.project_id = %(project_id)s) AS agent_actions
                    """,
                    {"project_id": project["id"]},
                )
                counts = cur.fetchone()

                decisions = fetch_brief_rows(
                    cur,
                    "decisions",
                    project["id"],
                    "id, decision, rationale",
                    limit=args.limit,
                )
                facts = fetch_brief_rows(
                    cur,
                    "facts",
                    project["id"],
                    "id, statement, source, confidence",
                    excluded_statuses=("archived", "deprecated"),
                    limit=args.limit,
                )
                questions = fetch_brief_rows(
                    cur,
                    "open_questions",
                    project["id"],
                    "id, question, answer",
                    excluded_statuses=INACTIVE_OPEN_QUESTION_STATUSES,
                    limit=args.limit,
                )
                risks = fetch_brief_rows(
                    cur,
                    "risks",
                    project["id"],
                    "id, title, severity, impact, mitigation",
                    excluded_statuses=("archived", "resolved"),
                    limit=args.limit,
                )
                reports = fetch_brief_rows(
                    cur,
                    "reports",
                    project["id"],
                    "id, title, report_type, summary",
                    limit=args.limit,
                )
                relations = []
                if args.with_relations:
                    relations = fetch_project_relations(
                        cur,
                        project["id"],
                        limit=args.limit,
                    )

        brief = {
            "project": project,
            "counts": counts,
            "decisions": decisions,
            "facts": facts,
            "open_questions": questions,
            "risks": risks,
            "reports": reports,
            "relations": relations,
        }
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(json.dumps(brief, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"# Agent Brief: {project['name']}")
    print()
    print(f"- slug: {project['slug']}")
    print(f"- status: {project['status']}")
    if project.get("description"):
        print(f"- description: {project['description']}")
    print()
    print("## Counts")
    for key, value in counts.items():
        print(f"- {key}: {value}")
    print()
    print_rows("Decisions", decisions, "decision")
    print_rows("Facts", facts, "statement")
    print_rows("Open Questions", questions, "question")
    print_rows("Risks", risks, "title")
    print_rows("Reports", reports, "title")
    if args.with_relations:
        print("## Relations")
        print_relations(relations)
        print()
    return 0
