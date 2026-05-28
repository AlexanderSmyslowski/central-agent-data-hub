from __future__ import annotations

from pathlib import Path

import pytest

from agent_hub import cli
from agent_hub.import_obsidian import (
    contains_secret,
    import_markdown,
    iter_markdown_files,
    load_allowlist,
    normalize_import_item,
    parse_markdown,
)


ALLOWLIST = """
projects:
  - commcats-de
roots:
  - notes
types:
  - fact
  - decision
  - open_question
  - risk
  - report
fields:
  fact: [statement, source, confidence, status, metadata]
  decision: [decision, rationale, consequences, status, metadata]
  open_question: [question, answer, status, metadata]
  risk: [title, severity, impact, mitigation, status, metadata]
  report: [title, report_type, summary, body, status, metadata]
"""


def write_allowlist(tmp_path: Path) -> Path:
    (tmp_path / "notes").mkdir()
    path = tmp_path / "import_allowlist.yml"
    path.write_text(ALLOWLIST, encoding="utf-8")
    return path


def write_note(path: Path, frontmatter: str, body: str = "") -> Path:
    path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return path


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

    with pytest.raises(RuntimeError, match="outside allowlisted"):
        iter_markdown_files(outside, allowlist)


def test_parse_markdown_requires_frontmatter(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("No frontmatter", encoding="utf-8")

    with pytest.raises(RuntimeError, match="YAML frontmatter"):
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

    with pytest.raises(RuntimeError, match="not allowlisted"):
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

    with pytest.raises(RuntimeError, match="Unsupported"):
        normalize_import_item(note, allowlist)


def test_secret_scan_blocks_sensitive_content() -> None:
    assert contains_secret({"type": "fact"}, "api_key = abc123")
    assert contains_secret({"note": "BEGIN RSA PRIVATE KEY"}, "")
    assert contains_secret({"note": "ftp credentials"}, "")
    assert contains_secret({"note": "raw invoice data"}, "")


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
statement: Dry run fact.
source: smoke test
""",
    )

    class ReadOnlyCursor:
        statements: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_args):
            self.statements.append(sql)
            if "INSERT" in sql.upper():
                raise AssertionError("dry run should not execute writes")

        def fetchone(self):
            return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}

    class DryRunConnection:
        def cursor(self):
            return ReadOnlyCursor()

    result = import_markdown(note, allowlist_path, DryRunConnection(), dry_run=True)

    assert result.errors == []
    assert result.imported == []
    assert result.planned[0]["type"] == "fact"


def test_dry_run_rejects_missing_database_project(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
statement: Dry run fact.
source: smoke test
""",
    )

    class MissingProjectCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, *_args):
            return None

        def fetchone(self):
            return None

    class DryRunConnection:
        def cursor(self):
            return MissingProjectCursor()

    result = import_markdown(note, allowlist_path, DryRunConnection(), dry_run=True)

    assert result.planned == []
    assert result.errors[0]["error"] == "Project not found: commcats-de"


def test_import_cli_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["import", "--path", "notes"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_import_cli_missing_allowlist_has_clear_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/agent_hub")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(cli, "connect", lambda: FakeConnection())

    code = cli.main(
        [
            "import",
            "--path",
            str(notes),
            "--allowlist",
            str(tmp_path / "missing.yml"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "Import allowlist not found" in captured.err
    assert "Traceback" not in captured.err
