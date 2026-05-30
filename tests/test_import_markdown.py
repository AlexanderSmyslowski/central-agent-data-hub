from __future__ import annotations

from pathlib import Path

import pytest

from agent_hub.errors import SafetyError, ValidationError
from agent_hub.import_obsidian import (
    contains_secret,
    load_allowlist,
    normalize_import_item,
    parse_markdown,
)
from import_helpers import write_allowlist, write_note


def test_parse_markdown_requires_frontmatter(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("No frontmatter", encoding="utf-8")

    with pytest.raises(ValidationError, match="YAML frontmatter"):
        parse_markdown(note)


def test_normalize_import_item_accepts_fact(tmp_path: Path) -> None:
    allowlist = load_allowlist(write_allowlist(tmp_path))
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project: commcats-de
statement: CommCats is static.
source: smoke test
confidence: 0.9
metadata:
  topic: hosting
""",
    )

    item = normalize_import_item(note, allowlist)

    assert item.memory_type == "fact"
    assert item.project_slug == "commcats-de"
    assert item.data["confidence"] == 0.9


def test_normalize_import_item_rejects_unknown_project(tmp_path: Path) -> None:
    allowlist = load_allowlist(write_allowlist(tmp_path))
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project: the-one-catering
statement: Example.
source: smoke test
""",
    )

    with pytest.raises(ValidationError, match="not allowlisted"):
        normalize_import_item(note, allowlist)


def test_normalize_import_item_rejects_unsupported_type(tmp_path: Path) -> None:
    allowlist = load_allowlist(write_allowlist(tmp_path))
    note = write_note(
        tmp_path / "notes" / "doc.md",
        """
type: document
project: commcats-de
title: Nope
""",
    )

    with pytest.raises(ValidationError, match="Unsupported"):
        normalize_import_item(note, allowlist)


def test_secret_scan_blocks_sensitive_content() -> None:
    assert contains_secret({"type": "fact"}, "api_key = abc123")
    assert contains_secret({"note": "BEGIN RSA PRIVATE KEY"}, "")
    assert contains_secret({"note": "ftp credentials"}, "")
    assert contains_secret({"note": "raw invoice data"}, "")


def test_normalize_import_item_rejects_sensitive_content(tmp_path: Path) -> None:
    allowlist = load_allowlist(write_allowlist(tmp_path))
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project: commcats-de
statement: Do not store this.
source: smoke test
""",
        "api_key = abc123",
    )

    with pytest.raises(SafetyError, match="Potential secret"):
        normalize_import_item(note, allowlist)
