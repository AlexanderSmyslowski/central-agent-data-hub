from __future__ import annotations

from pathlib import Path

from agent_hub.import_obsidian import (
    hash_payload,
    load_allowlist,
    normalize_import_item,
    sync_markdown,
)
from import_helpers import write_allowlist, write_note


def test_sync_plan_reports_create(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: demo-website
import_key: demo-website-static-fact
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
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
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
project_slug: demo-website
import_key: demo-website-static-fact
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
project_slug: demo-website
import_key: demo-website-static-fact
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
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
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
                            "import_key": "demo-website-static-fact",
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
project_slug: demo-website
import_key: demo-website-static-fact
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
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
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
                            "import_key": "demo-website-static-fact",
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
project_slug: demo-website
import_key: demo-website-static-fact
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
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
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
                            "import_key": "demo-website-static-fact",
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
project_slug: demo-website
import_key: demo-website-static-fact
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
                self.sync_event_statuses.append(params[2])

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "demo-website", "name": "Demo Website"}
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
                            "import_key": "demo-website-static-fact",
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
