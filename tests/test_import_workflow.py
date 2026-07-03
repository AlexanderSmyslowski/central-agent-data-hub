from __future__ import annotations

from pathlib import Path

from agent_hub import cli
from agent_hub.commands import write as write_commands
from agent_hub.import_obsidian import import_markdown
from import_helpers import write_allowlist, write_note


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: demo-website
statement: Dry run fact.
source: smoke test
""",
    )

    class ReadOnlyCursor:
        def __init__(self):
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_args):
            self.last_sql = sql
            if "INSERT" in sql.upper():
                raise AssertionError("dry run should not execute writes")

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
            return None

        def fetchall(self):
            return []

    class DryRunConnection:
        def cursor(self):
            return ReadOnlyCursor()

    result = import_markdown(note, allowlist_path, DryRunConnection(), dry_run=True)

    assert result.errors == []
    assert result.imported == []
    assert result.planned[0]["type"] == "fact"
    assert result.planned[0]["action"] == "create"


def test_dry_run_rejects_missing_database_project(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: demo-website
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
    assert result.errors[0]["error"] == "Project not found: demo-website"


def test_duplicate_import_defaults_to_skip(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: demo-website
import_key: demo-website-static-fact
statement: Dry run fact.
source: smoke test
""",
    )

    class DuplicateCursor:
        def __init__(self):
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_args):
            self.last_sql = sql
            if "INSERT" in sql.upper():
                raise AssertionError("duplicate skip should not write")

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
            return None

        def fetchall(self):
            return [
                {
                    "id": "fact-id",
                    "project_id": "project-id",
                    "statement": "Dry run fact.",
                    "source": "smoke test",
                    "confidence": 0.9,
                    "status": "verified",
                    "metadata": {
                        "agent_hub_import": {
                            "import_key": "demo-website-static-fact",
                            "content_hash": "old",
                            "data_hash": "old",
                        }
                    },
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]

    class DuplicateConnection:
        def cursor(self):
            return DuplicateCursor()

    result = import_markdown(note, allowlist_path, DuplicateConnection())

    assert result.errors == []
    assert result.imported == []
    assert result.planned[0]["action"] == "skip"


def test_duplicate_import_can_error(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: demo-website
import_key: demo-website-static-fact
statement: Dry run fact.
source: smoke test
""",
    )

    class DuplicateCursor:
        def __init__(self):
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_args):
            self.last_sql = sql

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
            return None

        def fetchall(self):
            return [
                {
                    "id": "fact-id",
                    "project_id": "project-id",
                    "statement": "Dry run fact.",
                    "source": "smoke test",
                    "confidence": 0.9,
                    "status": "verified",
                    "metadata": {
                        "agent_hub_import": {
                            "import_key": "demo-website-static-fact",
                            "content_hash": "old",
                            "data_hash": "old",
                        }
                    },
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]

    class DuplicateConnection:
        def cursor(self):
            return DuplicateCursor()

    result = import_markdown(
        note,
        allowlist_path,
        DuplicateConnection(),
        on_duplicate="error",
    )

    assert result.imported == []
    assert result.errors[0]["error"] == "duplicate import target"


def test_import_cli_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.setenv("AGENT_HUB_DISABLE_ENV_AUTOLOAD", "1")
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

    monkeypatch.setattr(write_commands, "connect", lambda: FakeConnection())

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
