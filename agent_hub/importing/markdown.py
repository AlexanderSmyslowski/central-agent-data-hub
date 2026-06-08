"""Markdown frontmatter parsing and import item normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from agent_hub.errors import SafetyError, ValidationError
from agent_hub.importing.allowlist import relative_import_path
from agent_hub.importing.constants import REQUIRED_FIELDS, STATUS_VALUES
from agent_hub.importing.identity import derive_import_key, hash_payload
from agent_hub.importing.models import ImportAllowlist, ImportItem
from agent_hub.importing.constants import SENSITIVE_PATTERN

def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValidationError("Markdown file must start with YAML frontmatter")
    try:
        _, frontmatter_text, body = text.split("---", 2)
    except ValueError as exc:
        raise ValidationError("Markdown file is missing closing frontmatter delimiter") from exc
    frontmatter = yaml.safe_load(frontmatter_text)
    if not isinstance(frontmatter, dict):
        raise ValidationError("YAML frontmatter must be a mapping")
    return frontmatter, body.strip()


def contains_secret(frontmatter: dict[str, Any], body: str) -> bool:
    haystack = json.dumps(frontmatter, default=str, ensure_ascii=False) + "\n" + body
    return bool(SENSITIVE_PATTERN.search(haystack))

def normalize_import_item(path: Path, allowlist: ImportAllowlist) -> ImportItem:
    frontmatter, body = parse_markdown(path)
    if contains_secret(frontmatter, body):
        raise SafetyError("Potential secret detected; refusing import")

    memory_type = frontmatter.get("type")
    if memory_type not in allowlist.types:
        raise ValidationError(f"Unsupported or non-allowlisted type: {memory_type}")

    project_slug = frontmatter.get("project_slug") or frontmatter.get("project")
    if not isinstance(project_slug, str) or not project_slug:
        raise ValidationError("Frontmatter requires project or project_slug")
    if project_slug not in allowlist.projects:
        raise ValidationError(f"Project is not allowlisted: {project_slug}")

    allowed_fields = allowlist.fields[memory_type]
    data = {
        key: value
        for key, value in frontmatter.items()
        if key in allowed_fields and value is not None
    }
    if "metadata" in data and not isinstance(data["metadata"], dict):
        raise ValidationError("metadata must be a mapping")
    if memory_type == "fact" and "confidence" in data:
        try:
            confidence = float(data["confidence"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("confidence must be a number from 0 to 1") from exc
        if confidence < 0 or confidence > 1:
            raise ValidationError("confidence must be between 0 and 1")
        data["confidence"] = confidence
    if "status" in data and data["status"] not in STATUS_VALUES[memory_type]:
        raise ValidationError(
            f"Unsupported status for {memory_type}: {data['status']}"
        )
    if memory_type == "report" and "body" in allowed_fields and "body" not in data:
        data["body"] = body

    missing = REQUIRED_FIELDS[memory_type] - data.keys()
    if missing:
        raise ValidationError(
            f"Missing required field(s) for {memory_type}: {', '.join(sorted(missing))}"
        )

    db_id = frontmatter.get("db_id")
    if db_id is not None and not isinstance(db_id, str):
        raise ValidationError("db_id must be a string when provided")
    source_path = relative_import_path(path, allowlist)
    import_key = derive_import_key(path, allowlist, frontmatter, memory_type, project_slug)
    content_hash = hash_payload(
        {
            "type": memory_type,
            "project": project_slug,
            "data": data,
        }
    )

    return ImportItem(
        path=path,
        source_path=source_path,
        frontmatter=frontmatter,
        body=body,
        project_slug=project_slug,
        memory_type=memory_type,
        data=data,
        db_id=db_id,
        import_key=import_key,
        content_hash=content_hash,
    )
