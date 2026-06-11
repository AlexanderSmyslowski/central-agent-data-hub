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
from agent_hub.retrieval import fetch_brief_rows, fetch_drafts_awaiting_review
from agent_hub.statuses import (
    agent_read_excluded_statuses,
    agent_read_excluded_statuses_by_type,
    format_open_question_count,
)


def fetch_brief_payload(
    cur,
    project: dict[str, object],
    limit: int,
    *,
    with_relations: bool = False,
) -> dict[str, object]:
    open_question_excluded = agent_read_excluded_statuses("open_question")
    placeholders = ", ".join(
        f"%(open_question_excluded_{index})s"
        for index, _status in enumerate(open_question_excluded)
    )
    status_filter = f"AND status NOT IN ({placeholders})" if placeholders else ""
    params = {"project_id": project["id"]}
    params.update(
        {
            f"open_question_excluded_{index}": status
            for index, status in enumerate(open_question_excluded)
        }
    )
    cur.execute(
        f"""
        SELECT
          (SELECT count(*) FROM documents WHERE project_id = %(project_id)s) AS documents,
          (SELECT count(*) FROM facts WHERE project_id = %(project_id)s) AS facts,
          (SELECT count(*) FROM decisions WHERE project_id = %(project_id)s) AS decisions,
          (
            SELECT count(*)
            FROM open_questions
            WHERE project_id = %(project_id)s
              {status_filter}
          ) AS open_questions,
          (SELECT count(*) FROM open_questions WHERE project_id = %(project_id)s) AS open_questions_total,
          (SELECT count(*) FROM risks WHERE project_id = %(project_id)s) AS risks,
          (SELECT count(*) FROM reports WHERE project_id = %(project_id)s) AS reports,
          (SELECT count(*) FROM agent_actions aa
            JOIN agents a ON a.id = aa.agent_id
            WHERE a.project_id = %(project_id)s) AS agent_actions
        """,
        params,
    )
    counts = cur.fetchone()
    drafts_awaiting_review = fetch_drafts_awaiting_review(cur, project["id"])

    decisions = fetch_brief_rows(
        cur,
        "decisions",
        project["id"],
        "id, decision, rationale",
        limit=limit,
    )
    facts = fetch_brief_rows(
        cur,
        "facts",
        project["id"],
        "id, statement, source, confidence",
        limit=limit,
    )
    questions = fetch_brief_rows(
        cur,
        "open_questions",
        project["id"],
        "id, question, answer",
        limit=limit,
    )
    risks = fetch_brief_rows(
        cur,
        "risks",
        project["id"],
        "id, title, severity, impact, mitigation",
        limit=limit,
    )
    reports = fetch_brief_rows(
        cur,
        "reports",
        project["id"],
        "id, title, report_type, summary",
        limit=limit,
    )
    relations = []
    if with_relations:
        relations = fetch_project_relations(
            cur,
            project["id"],
            limit=limit,
            excluded_statuses_by_type=agent_read_excluded_statuses_by_type(),
        )

    return {
        "project": project,
        "counts": counts,
        "drafts_awaiting_review": drafts_awaiting_review,
        "decisions": decisions,
        "facts": facts,
        "open_questions": questions,
        "risks": risks,
        "reports": reports,
        "relations": relations,
    }


def run_brief(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                brief = fetch_brief_payload(
                    cur,
                    project,
                    args.limit,
                    with_relations=args.with_relations,
                )
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
    print(f"- {brief['drafts_awaiting_review']['label']}")
    print()
    print("## Counts")
    counts = brief["counts"]
    for key, value in counts.items():
        if key == "open_questions_total":
            continue
        if key == "open_questions":
            value = format_open_question_count(value, counts.get("open_questions_total"))
        print(f"- {key}: {value}")
    print()
    print_rows("Decisions", brief["decisions"], "decision")
    print_rows("Facts", brief["facts"], "statement")
    print_rows("Open Questions", brief["open_questions"], "question")
    print_rows("Risks", brief["risks"], "title")
    print_rows("Reports", brief["reports"], "title")
    if args.with_relations:
        print("## Relations")
        print_relations(brief["relations"])
        print()
    return 0
