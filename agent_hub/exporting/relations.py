"""Relation fetch helpers for Obsidian export."""

from __future__ import annotations

from typing import Any

from agent_hub.exporting.helpers import normalize_row

def fetch_relations(cur) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, source_type, source_id, relation_type, target_type, target_id,
               metadata, created_at, updated_at
        FROM relations
        ORDER BY updated_at DESC, created_at DESC, id
        """
    )
    return [normalize_row(dict(row)) for row in cur.fetchall()]

