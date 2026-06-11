"""Search and context command handlers."""

from __future__ import annotations

import argparse
import json

from agent_hub.commands.common import (
    error,
    exception_error,
    fetch_project,
    json_default,
    require_database_url,
    parse_since,
    project_not_found,
)
from agent_hub.db import connect
from agent_hub.relations import fetch_project_relations
from agent_hub.retrieval import (
    fetch_activity_snapshot,
    fetch_drafts_awaiting_review,
    search_project_memory,
)
from agent_hub.rendering import (
    markdown_list,
    relations_markdown,
    search_results_markdown,
)
from agent_hub.statuses import agent_read_excluded_statuses_by_type


def fetch_search_payload(
    cur,
    project: dict[str, object],
    query: str,
    memory_type: str,
    limit: int,
    *,
    include_drafts: bool = False,
    include_archived: bool = False,
) -> dict[str, object]:
    results = search_project_memory(
        cur,
        project["id"],
        query,
        memory_type,
        limit,
        include_drafts=include_drafts,
        include_archived=include_archived,
    )
    return {
        "project": project,
        "query": query,
        "include_drafts": include_drafts,
        "include_archived": include_archived,
        "drafts_awaiting_review": fetch_drafts_awaiting_review(cur, project["id"]),
        "results": results,
    }


def run_search(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                payload = fetch_search_payload(
                    cur,
                    project,
                    args.query,
                    args.memory_type,
                    args.limit,
                    include_drafts=args.include_drafts,
                    include_archived=args.include_archived,
                )
    except Exception as exc:
        return exception_error(exc)

    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"Search results for {project['slug']}: {args.query}")
    print(f"- {payload['drafts_awaiting_review']['label']}")
    print(search_results_markdown(payload["results"]))
    return 0


def run_context(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        since = parse_since(args.since, default="30d")
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                snapshot = fetch_activity_snapshot(
                    cur,
                    project,
                    since,
                    args.limit,
                    surface="context",
                )
                results = search_project_memory(
                    cur,
                    project["id"],
                    args.query,
                    "all",
                    args.limit,
                )
                relations = fetch_project_relations(
                    cur,
                    project["id"],
                    limit=args.limit,
                    excluded_statuses_by_type=agent_read_excluded_statuses_by_type(),
                )
    except ValueError as exc:
        return error(exc, 2)
    except Exception as exc:
        return exception_error(exc)

    payload = {
        "project": project,
        "query": args.query,
        "since": since,
        "brief": snapshot,
        "search_results": results,
        "relations": relations,
        "drafts_awaiting_review": snapshot["drafts_awaiting_review"],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"# Context Pack: {project['name']}")
    print()
    print(f"- project: {project['slug']}")
    print(f"- query: {args.query}")
    print(f"- since: {since.isoformat()}")
    print(f"- {payload['drafts_awaiting_review']['label']}")
    print()
    print("## Search Results")
    print(
        search_results_markdown(
            results,
            "- No direct reviewed memory matched this focus query; showing recent project memory below.",
        )
    )
    print()
    print("## Recent Activity")
    print("### Facts")
    print(markdown_list(snapshot["facts"], "statement", ("source", "confidence")))
    print()
    print("### Decisions")
    print(markdown_list(snapshot["decisions"], "decision", ("rationale",)))
    print()
    print("### Risks")
    print(markdown_list(snapshot["risks"], "title", ("severity", "impact", "mitigation")))
    print()
    print("### Question Updates")
    print(markdown_list(snapshot["open_questions"], "question", ("answer",)))
    print()
    print("### Relations")
    print(relations_markdown(relations))
    return 0
