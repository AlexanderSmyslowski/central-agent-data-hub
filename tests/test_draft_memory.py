from __future__ import annotations

import uuid
from pathlib import Path

from agent_hub.commands.prepare import (
    DRAFT_PREPARE_REASON,
    build_prepare_payload,
    prepare_markdown,
)
from agent_hub.import_obsidian import import_markdown
from import_helpers import write_allowlist, write_note


PROJECT = {
    "id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
    "slug": "central-agent-data-hub",
    "name": "Central Agent Data Hub",
}


def test_prepare_separates_drafts_and_marks_context_trail() -> None:
    verified_fact = {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000101"),
        "statement": "Prepare uses reviewed memory.",
        "source": "test",
        "confidence": 0.9,
        "status": "verified",
        "prepare_reason": "included by deterministic task text match",
    }
    draft_fact = {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000102"),
        "statement": "Drafts are shown separately.",
        "source": "test",
        "confidence": 0.9,
        "status": "draft",
        "prepare_reason": DRAFT_PREPARE_REASON,
    }

    payload = build_prepare_payload(
        project=PROJECT,
        task="review drafts",
        compiled={
            "facts": [verified_fact, draft_fact],
            "decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
            "relations": [],
        },
    )
    markdown = prepare_markdown(payload)

    assert payload["verified_project_state"] == [verified_fact]
    assert payload["drafts_pending_review"]["facts"] == [draft_fact]
    draft_source = next(
        source
        for source in payload["context_trail"]["sources"]
        if source["id"] == draft_fact["id"]
    )
    assert draft_source["review_status"] == "draft"
    assert draft_source["reason"] == DRAFT_PREPARE_REASON
    assert "## Drafts Pending Review" in markdown
    assert "Drafts are shown separately." in markdown


def test_import_dry_run_routes_new_note_to_draft(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
statement: Draft import fact.
source: smoke test
""",
    )

    class DraftCursor:
        def __init__(self):
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_args):
            self.last_sql = sql
            if "INSERT" in sql.upper():
                raise AssertionError("dry run should not write")

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
            return None

        def fetchall(self):
            return []

    class DraftConnection:
        def cursor(self):
            return DraftCursor()

    result = import_markdown(note, allowlist_path, DraftConnection(), dry_run=True)

    assert result.errors == []
    assert result.planned[0]["action"] == "create"
    assert result.planned[0]["tier"] == "draft"
    assert result.planned[0]["status"] == "draft"


def test_import_dry_run_routes_money_note_to_ask(tmp_path: Path) -> None:
    allowlist_path = write_allowlist(tmp_path)
    note = write_note(
        tmp_path / "notes" / "fact.md",
        """
type: fact
project_slug: commcats-de
statement: Budget is $100.
source: smoke test
""",
    )

    class AskCursor:
        def __init__(self):
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_args):
            self.last_sql = sql
            if "INSERT" in sql.upper():
                raise AssertionError("ask dry run should not write")

        def fetchone(self):
            if "FROM projects" in self.last_sql:
                return {"id": "project-id", "slug": "commcats-de", "name": "CommCats"}
            return None

        def fetchall(self):
            return []

    class AskConnection:
        def cursor(self):
            return AskCursor()

    result = import_markdown(note, allowlist_path, AskConnection(), dry_run=True)

    assert result.errors == []
    assert result.planned[0]["action"] == "ask"
    assert "money amount" in result.planned[0]["reason"]
