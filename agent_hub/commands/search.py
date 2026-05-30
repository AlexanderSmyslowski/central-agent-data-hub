"""Search and context command handlers."""

from __future__ import annotations

import argparse
import json
import os
import sys

from agent_hub.commands.common import (
    concise_error,
    fetch_project,
    json_default,
    parse_since,
)
from agent_hub.db import connect
from agent_hub.relations import fetch_project_relations
from agent_hub.retrieval import fetch_activity_snapshot, search_project_memory
from agent_hub.rendering import (
    markdown_list,
    relations_markdown,
    search_results_markdown,
)


def run_search(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    print(
                        f"Error: project '{args.project}' not found",
                        file=sys.stderr,
                    )
                    return 2
                results = search_project_memory(
                    cur,
                    project["id"],
                    args.query,
                    args.memory_type,
                    args.limit,
                )
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    payload = {"project": project, "query": args.query, "results": results}
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"Search results for {project['slug']}: {args.query}")
    print(search_results_markdown(results))
    return 0


def run_context(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since, default="30d")
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    print(
                        f"Error: project '{args.project}' not found",
                        file=sys.stderr,
                    )
                    return 2
                snapshot = fetch_activity_snapshot(cur, project, since, args.limit)
                results = search_project_memory(
                    cur,
                    project["id"],
                    args.query,
                    "all",
                    args.limit,
                )
                relations = fetch_project_relations(cur, project["id"], limit=args.limit)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {concise_error(exc)}", file=sys.stderr)
        return 1

    payload = {
        "project": project,
        "query": args.query,
        "since": since,
        "brief": snapshot,
        "search_results": results,
        "relations": relations,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"# Context Pack: {project['name']}")
    print()
    print(f"- project: {project['slug']}")
    print(f"- query: {args.query}")
    print(f"- since: {since.isoformat()}")
    print()
    print("## Search Results")
    print(search_results_markdown(results))
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
    print("### Open Questions")
    print(markdown_list(snapshot["open_questions"], "question", ("answer",)))
    print()
    print("### Relations")
    print(relations_markdown(relations))
    return 0
