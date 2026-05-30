from __future__ import annotations

from pathlib import Path

import pytest

from agent_hub.errors import ValidationError
from agent_hub.import_obsidian import iter_markdown_files, load_allowlist
from import_helpers import write_allowlist


def test_load_allowlist_resolves_roots(tmp_path: Path) -> None:
    path = write_allowlist(tmp_path)

    allowlist = load_allowlist(path)

    assert "commcats-de" in allowlist.projects
    assert "fact" in allowlist.types
    assert allowlist.roots == [(tmp_path / "notes").resolve()]


def test_iter_markdown_files_blocks_paths_outside_roots(tmp_path: Path) -> None:
    allowlist = load_allowlist(write_allowlist(tmp_path))
    outside = tmp_path / "outside.md"
    outside.write_text("---\ntype: fact\n---\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="outside allowlisted"):
        iter_markdown_files(outside, allowlist)
