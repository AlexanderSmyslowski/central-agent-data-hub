from __future__ import annotations

from pathlib import Path

import pytest

from agent_hub import cli
from agent_hub.commands import write as write_commands
from agent_hub.import_obsidian import (
    contains_secret,
    hash_payload,
    import_markdown,
    iter_markdown_files,
    load_allowlist,
    normalize_import_item,
    parse_markdown,
    sync_markdown,
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
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
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


def test_duplicate_import_defaults_to_skip(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
import_key: commcats-static-fact
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
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
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
                            "import_key": "commcats-static-fact",
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
project_slug: commcats-de
import_key: commcats-static-fact
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
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
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
                            "import_key": "commcats-static-fact",
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


def test_sync_plan_reports_create(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
import_key: commcats-static-fact
statement: Sync fact.
source: smoke test
""",
    )

    class PlanningCursor:
        def __init__(self):
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_args):
            self.last_sql = sql
            if "INSERT" in sql.upper():
                raise AssertionError("sync plan should not write")

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
            return None

        def fetchall(self):
            return []

    class PlanningConnection:
        def cursor(self):
            return PlanningCursor()

    result = sync_markdown(note, allowlist_path, PlanningConnection(), apply=False)

    assert result.errors == []
    assert result.applied == []
    assert result.planned[0]["action"] == "create"


def test_sync_plan_rejects_sensitive_note(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
import_key: commcats-static-fact
statement: Sync fact.
source: smoke test
""",
        "api_key = abc123",
    )

    class RejectCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class RejectConnection:
        def cursor(self):
            return RejectCursor()

    result = sync_markdown(note, allowlist_path, RejectConnection(), apply=False)

    assert result.planned[0]["action"] == "reject"
    assert result.planned[0]["project"] is None
    assert "Potential secret detected" in result.planned[0]["reason"]


def test_sync_plan_reports_update_with_diff(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    last_data = {
        "statement": "Original fact.",
        "source": "smoke test",
        "confidence": 0.9,
        "status": "verified",
    }
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
import_key: commcats-static-fact
statement: Changed Markdown fact.
source: smoke test
""",
    )

    class UpdateCursor:
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
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
            return None

        def fetchall(self):
            return [
                {
                    "id": "fact-id",
                    "project_id": "project-id",
                    "statement": "Original fact.",
                    "source": "smoke test",
                    "confidence": 0.9,
                    "status": "verified",
                    "metadata": {
                        "agent_hub_import": {
                            "import_key": "commcats-static-fact",
                            "content_hash": "previous-note-hash",
                            "data_hash": hash_payload(last_data),
                            "data": last_data,
                        }
                    },
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]

    class UpdateConnection:
        def cursor(self):
            return UpdateCursor()

    result = sync_markdown(note, allowlist_path, UpdateConnection(), apply=False)

    planned = result.planned[0]
    assert planned["action"] == "update"
    assert planned["diffs"] == [
        {
            "field": "statement",
            "database_value": "Original fact.",
            "markdown_value": "Changed Markdown fact.",
            "last_imported_value": "Original fact.",
            "owner": "obsidian",
        }
    ]


def test_sync_plan_reports_database_only_change_as_skip(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    allowlist = load_allowlist(allowlist_path)
    last_data = {
        "statement": "Original fact.",
        "source": "smoke test",
        "confidence": 0.9,
        "status": "verified",
    }
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
import_key: commcats-static-fact
statement: Original fact.
source: smoke test
""",
    )
    item = normalize_import_item(note, allowlist)

    class DatabaseOnlyCursor:
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
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
            return None

        def fetchall(self):
            return [
                {
                    "id": "fact-id",
                    "project_id": "project-id",
                    "statement": "Database-only change.",
                    "source": "smoke test",
                    "confidence": 0.9,
                    "status": "verified",
                    "metadata": {
                        "agent_hub_import": {
                            "import_key": "commcats-static-fact",
                            "content_hash": item.content_hash,
                            "data_hash": hash_payload(last_data),
                            "data": last_data,
                        }
                    },
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]

    class DatabaseOnlyConnection:
        def cursor(self):
            return DatabaseOnlyCursor()

    result = sync_markdown(note, allowlist_path, DatabaseOnlyConnection(), apply=False)

    planned = result.planned[0]
    assert planned["action"] == "skip"
    assert planned["reason"] == "database changed since last import; markdown unchanged"
    assert planned["database_changed_fields"] == ["statement"]


def test_sync_plan_reports_conflict_with_diff(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    last_data = {
        "statement": "Original fact.",
        "source": "smoke test",
        "confidence": 0.9,
        "status": "verified",
    }
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
import_key: commcats-static-fact
statement: Changed Markdown fact.
source: smoke test
""",
    )

    class ConflictCursor:
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
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
            return None

        def fetchall(self):
            return [
                {
                    "id": "fact-id",
                    "project_id": "project-id",
                    "statement": "Database changed fact.",
                    "source": "smoke test",
                    "confidence": 0.9,
                    "status": "verified",
                    "metadata": {
                        "agent_hub_import": {
                            "import_key": "commcats-static-fact",
                            "content_hash": "previous-note-hash",
                            "data_hash": hash_payload(last_data),
                            "data": last_data,
                        }
                    },
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]

    class ConflictConnection:
        def cursor(self):
            return ConflictCursor()

    result = sync_markdown(note, allowlist_path, ConflictConnection(), apply=False)

    planned = result.planned[0]
    assert planned["action"] == "conflict"
    assert planned["conflicting_fields"] == ["statement"]
    assert planned["diffs"][0] == {
        "field": "statement",
        "database_value": "Database changed fact.",
        "markdown_value": "Changed Markdown fact.",
        "last_imported_value": "Original fact.",
        "owner": "obsidian",
    }
    assert result.blocking_actions == result.planned


def test_sync_apply_conflict_writes_failed_sync_event(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    last_data = {
        "statement": "Original fact.",
        "source": "smoke test",
        "confidence": 0.9,
        "status": "verified",
    }
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
import_key: commcats-static-fact
statement: Changed Markdown fact.
source: smoke test
""",
    )

    class ApplyConflictCursor:
        def __init__(self):
            self.last_sql = ""
            self.sync_event_statuses: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, params=None):
            self.last_sql = sql
            if "INSERT INTO sync_events" in sql:
                self.sync_event_statuses.append(params[0])

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
            return None

        def fetchall(self):
            return [
                {
                    "id": "fact-id",
                    "project_id": "project-id",
                    "statement": "Database changed fact.",
                    "source": "smoke test",
                    "confidence": 0.9,
                    "status": "verified",
                    "metadata": {
                        "agent_hub_import": {
                            "import_key": "commcats-static-fact",
                            "content_hash": "previous-note-hash",
                            "data_hash": hash_payload(last_data),
                            "data": last_data,
                        }
                    },
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]

    class ApplyConflictConnection:
        def __init__(self):
            self.cursor_instance = ApplyConflictCursor()

        def cursor(self):
            return self.cursor_instance

    connection = ApplyConflictConnection()
    result = sync_markdown(note, allowlist_path, connection, apply=True)

    assert result.applied == []
    assert result.planned[0]["action"] == "conflict"
    assert connection.cursor_instance.sync_event_statuses == ["failed"]


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
