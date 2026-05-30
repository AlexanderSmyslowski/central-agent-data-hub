"""Import data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any



@dataclass
class ImportAllowlist:
    projects: set[str]
    roots: list[Path]
    types: set[str]
    fields: dict[str, set[str]]
    path: Path


@dataclass
class ImportItem:
    path: Path
    frontmatter: dict[str, Any]
    body: str
    project_slug: str
    memory_type: str
    data: dict[str, Any]
    db_id: str | None
    import_key: str
    content_hash: str


@dataclass
class ImportResult:
    imported: list[dict[str, Any]] = field(default_factory=list)
    planned: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


@dataclass
class SyncResult:
    planned: list[dict[str, Any]] = field(default_factory=list)
    applied: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def blocking_actions(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.planned
            if item.get("action") in {"conflict", "reject", "error"}
        ]
