"""Allowlist loading and import path selection."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent_hub.errors import ValidationError
from agent_hub.importing.constants import ALLOWED_TYPES, TYPE_DEFAULT_FIELDS
from agent_hub.importing.models import ImportAllowlist

def load_allowlist(path: Path) -> ImportAllowlist:
    if not path.exists():
        raise ValidationError(f"Import allowlist not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidationError("Import allowlist must be a YAML mapping")

    projects = raw.get("projects")
    roots = raw.get("roots")
    types = raw.get("types")
    fields = raw.get("fields")
    if not isinstance(projects, list) or not all(isinstance(v, str) for v in projects):
        raise ValidationError("Import allowlist requires projects as a list of slugs")
    if not isinstance(roots, list) or not all(isinstance(v, str) for v in roots):
        raise ValidationError("Import allowlist requires roots as a list of paths")
    if not isinstance(types, list) or not all(isinstance(v, str) for v in types):
        raise ValidationError("Import allowlist requires types as a list")
    if not isinstance(fields, dict):
        raise ValidationError("Import allowlist requires fields as a mapping")

    type_set = set(types)
    unsupported = type_set - set(ALLOWED_TYPES)
    if unsupported:
        raise ValidationError(f"Unsupported allowlist type(s): {', '.join(sorted(unsupported))}")

    normalized_fields: dict[str, set[str]] = {}
    for memory_type in type_set:
        values = fields.get(memory_type)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValidationError(f"Import allowlist requires fields.{memory_type} as a list")
        allowed_fields = set(values)
        unsupported_fields = allowed_fields - TYPE_DEFAULT_FIELDS[memory_type]
        if unsupported_fields:
            raise ValidationError(
                f"Unsupported field(s) for {memory_type}: "
                f"{', '.join(sorted(unsupported_fields))}"
            )
        normalized_fields[memory_type] = allowed_fields

    base = path.resolve().parent
    root_paths = [
        (base / root).resolve() if not Path(root).is_absolute() else Path(root).resolve()
        for root in roots
    ]

    return ImportAllowlist(
        projects=set(projects),
        roots=root_paths,
        types=type_set,
        fields=normalized_fields,
        path=path.resolve(),
    )


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def ensure_path_allowed(path: Path, allowlist: ImportAllowlist) -> Path:
    resolved = path.resolve()
    if not any(is_relative_to(resolved, root) for root in allowlist.roots):
        raise ValidationError(f"Path is outside allowlisted import roots: {path}")
    return resolved


def iter_markdown_files(path: Path, allowlist: ImportAllowlist) -> list[Path]:
    resolved = ensure_path_allowed(path, allowlist)
    if resolved.is_file():
        if resolved.suffix.lower() != ".md":
            raise ValidationError(f"Import path is not a Markdown file: {path}")
        return [resolved]
    if not resolved.is_dir():
        raise ValidationError(f"Import path not found: {path}")
    return sorted(file for file in resolved.rglob("*.md") if file.is_file())


def relative_import_path(path: Path, allowlist: ImportAllowlist) -> str:
    resolved = path.resolve()
    for root in allowlist.roots:
        if is_relative_to(resolved, root):
            return str(resolved.relative_to(root))
    return str(resolved)
