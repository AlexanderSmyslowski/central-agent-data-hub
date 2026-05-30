"""Command line interface for Agent Data Hub."""

from __future__ import annotations

from datetime import timezone

from agent_hub.commands.common import (
    concise_error,
    confidence_value,
    fetch_project,
    json_default,
    parse_metadata,
    parse_since,
    positive_int,
    print_relations,
    print_rows,
)
from agent_hub.commands.parser import build_parser, not_implemented
from agent_hub.commands.read import fetch_compiled_payload, get_export_dir_or_none
from agent_hub.commands.write import print_sync_result
from agent_hub.db import connect
from agent_hub.migrations import MIGRATIONS_DIR, migration_parts
from agent_hub.quality import fetch_memory_quality_warnings
from agent_hub.receipts import export_path_for_object
from agent_hub.relations import validate_relation_object
from agent_hub.rendering import (
    agent_actions_markdown,
    limit_markdown_chars,
    truncate,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
