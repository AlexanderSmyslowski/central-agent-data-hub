"""Compatibility facade for Obsidian export."""

from __future__ import annotations

from agent_hub.exporting.helpers import (
    append_unique,
    display_title,
    filename_for,
    get_export_dir,
    id_suffix,
    normalize_row,
    normalize_value,
    relation_link_line,
    slugify,
    wikilink,
)
from agent_hub.exporting.overviews import hub_home_context, project_overview_context
from agent_hub.exporting.relations import fetch_relations
from agent_hub.exporting.specs import EXPORTS, TYPE_BY_TABLE
from agent_hub.exporting.workflow import export_all

__all__ = [
    "EXPORTS",
    "TYPE_BY_TABLE",
    "append_unique",
    "display_title",
    "export_all",
    "fetch_relations",
    "filename_for",
    "get_export_dir",
    "hub_home_context",
    "id_suffix",
    "normalize_row",
    "normalize_value",
    "project_overview_context",
    "relation_link_line",
    "slugify",
    "wikilink",
]


def main() -> None:
    written = export_all()
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
