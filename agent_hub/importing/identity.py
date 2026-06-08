"""Import identity, hashing, metadata, and diff helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from agent_hub.errors import ValidationError
from agent_hub.importing.allowlist import relative_import_path
from agent_hub.importing.constants import FIELD_OWNERS, TYPE_COLUMNS, TYPE_DEFAULT_VALUES
from agent_hub.importing.models import ImportAllowlist, ImportItem

def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        normalize_value(value),
        default=json_default,
        ensure_ascii=False,
        sort_keys=True,
    )


def hash_payload(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def item_values(item: ImportItem) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in TYPE_COLUMNS[item.memory_type]:
        values[column] = item.data.get(
            column,
            TYPE_DEFAULT_VALUES[item.memory_type].get(column),
        )
    return values


def row_values(memory_type: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        column: normalize_value(row.get(column))
        for column in TYPE_COLUMNS[memory_type]
    }


def user_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key != "agent_hub_import"}


def import_metadata(item: ImportItem, existing_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(user_metadata(existing_metadata or {}))
    metadata.update(dict(item.data.get("metadata") or {}))
    now = datetime.now(timezone.utc).isoformat()
    metadata["agent_hub_import"] = {
        "import_key": item.import_key,
        "source_path": item.source_path,
        "content_hash": item.content_hash,
        "data_hash": hash_payload(item_values(item)),
        "data": normalize_value(item_values(item)),
        "last_imported_at": now,
        "imported_by": "agent-hub import",
    }
    return metadata


def derive_import_key(
    path: Path,
    allowlist: ImportAllowlist,
    frontmatter: dict[str, Any],
    memory_type: str,
    project_slug: str,
) -> str:
    explicit = frontmatter.get("import_key")
    if explicit is not None:
        if not isinstance(explicit, str) or not explicit.strip():
            raise ValidationError("import_key must be a non-empty string")
        return explicit.strip()

    db_id = frontmatter.get("db_id")
    if db_id is not None:
        return f"{memory_type}:{db_id}"

    relative_path = relative_import_path(path, allowlist)
    return f"{project_slug}:{memory_type}:{relative_path}"
def values_equal(left: Any, right: Any) -> bool:
    return canonical_json(left) == canonical_json(right)


def build_field_diffs(item: ImportItem, existing: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = existing.get("metadata") or {}
    import_state = metadata.get("agent_hub_import") or {}
    last_data = import_state.get("data")
    if not isinstance(last_data, dict):
        last_data = {}

    database_values = row_values(item.memory_type, existing)
    markdown_values = item_values(item)
    diffs: list[dict[str, Any]] = []
    for field in TYPE_COLUMNS[item.memory_type]:
        database_value = normalize_value(database_values.get(field))
        markdown_value = normalize_value(markdown_values.get(field))
        last_value = normalize_value(last_data.get(field)) if field in last_data else None
        changed = not values_equal(database_value, markdown_value)
        changed_from_last = (
            field in last_data
            and (
                not values_equal(database_value, last_value)
                or not values_equal(markdown_value, last_value)
            )
        )
        if changed or changed_from_last:
            diffs.append(
                {
                    "field": field,
                    "database_value": database_value,
                    "markdown_value": markdown_value,
                    "last_imported_value": last_value,
                    "owner": FIELD_OWNERS[item.memory_type].get(field, "postgres"),
                }
            )
    return diffs


def changed_fields_from_last(
    memory_type: str,
    current_values: dict[str, Any],
    last_values: dict[str, Any],
) -> set[str]:
    return {
        field
        for field in TYPE_COLUMNS[memory_type]
        if field in last_values
        and not values_equal(current_values.get(field), last_values.get(field))
    }
