"""Project graph command handlers."""

from __future__ import annotations

import argparse
import json

from agent_hub.commands.common import (
    error,
    exception_error,
    fetch_project,
    json_default,
    require_database_url,
    parse_metadata,
    print_relations,
    project_not_found,
)
from agent_hub.db import connect
from agent_hub.relations import (
    fetch_project_relations,
    fetch_relation_object,
    validate_relation_object,
)
from agent_hub.rendering import truncate
from agent_hub.statuses import DRAFT_STATUS


def run_relations(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code
    if bool(args.object_type) != bool(args.object_id):
        return error("--object-type and --object-id must be used together", 2)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)
                rows = fetch_project_relations(
                    cur,
                    project["id"],
                    object_type=args.object_type,
                    object_id=args.object_id,
                )
    except Exception as exc:
        return exception_error(exc)

    payload = {"project": project, "relations": rows}
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print(f"Relations for {project['slug']}:")
    print_relations(rows)
    return 0


def run_relate(args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        metadata = parse_metadata(args.metadata)
    except ValueError as exc:
        return error(exc, 2)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                project = fetch_project(cur, args.project)
                if not project:
                    return project_not_found(args.project)

                source = fetch_relation_object(cur, args.source_type, args.source_id)
                target = fetch_relation_object(cur, args.target_type, args.target_id)
                validate_relation_object(args.source_type, source, project, "source")
                validate_relation_object(args.target_type, target, project, "target")

                cur.execute(
                    """
                    INSERT INTO relations (
                      source_type, source_id, relation_type,
                      target_type, target_id, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (
                      source_type, source_id, relation_type, target_type, target_id
                    ) DO UPDATE SET
                      metadata = relations.metadata || EXCLUDED.metadata
                    RETURNING id, source_type, source_id, relation_type,
                              target_type, target_id, metadata, created_at, updated_at
                    """,
                    (
                        args.source_type,
                        args.source_id,
                        args.relation,
                        args.target_type,
                        args.target_id,
                        json.dumps(metadata),
                    ),
                )
                relation = cur.fetchone()
    except Exception as exc:
        return exception_error(exc)

    payload = {
        "project": project,
        "relation": relation,
        "source_summary": source["summary"],
        "target_summary": target["summary"],
        "warnings": [
            f"{role} {item_type}:{item_id} has status=draft; relation stored but not part of reviewed memory until review."
            for role, item_type, item_id, row in (
                ("source", args.source_type, args.source_id, source),
                ("target", args.target_type, args.target_id, target),
            )
            if row.get("status") == DRAFT_STATUS
        ],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=json_default, ensure_ascii=False))
        return 0

    print("Relation stored:")
    print(
        f"- {relation['source_type']}:{relation['source_id']} "
        f"({truncate(source['summary'], 72)}) "
        f"--{relation['relation_type']}--> "
        f"{relation['target_type']}:{relation['target_id']} "
        f"({truncate(target['summary'], 72)})"
    )
    for warning in payload["warnings"]:
        print(f"Warning: {warning}")
    return 0
