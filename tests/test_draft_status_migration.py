from __future__ import annotations

import inspect

from agent_hub.commands.inbox import INBOX_TABLES
from agent_hub.commands.prepare import PREPARE_SPECS
from agent_hub.importing.constants import STATUS_VALUES
from agent_hub.migrations import migration_file_by_id, migration_parts
from agent_hub.quality import fetch_memory_quality_warnings, fetch_project_counts
from agent_hub.statuses import (
    DRAFT_STATUS,
    INBOX_REVIEW_TYPES,
    MEMORY_STATUS_VALUES,
    REVIEWED_MEMORY_STATUSES,
)


PLURAL_TO_TYPE = {
    "facts": "fact",
    "decisions": "decision",
    "risks": "risk",
    "open_questions": "open_question",
    "reports": "report",
}


def test_status_lists_include_draft_for_all_prepare_and_inbox_types() -> None:
    prepare_types = {PLURAL_TO_TYPE[key] for key in PREPARE_SPECS}
    inbox_types = set(INBOX_TABLES)
    review_types = set(INBOX_REVIEW_TYPES)

    assert prepare_types == review_types
    assert inbox_types == review_types
    assert set(MEMORY_STATUS_VALUES) == review_types | {"document"}
    for memory_type, values in MEMORY_STATUS_VALUES.items():
        assert DRAFT_STATUS in values
        assert STATUS_VALUES[memory_type] == set(values)
        if memory_type in INBOX_TABLES:
            assert INBOX_TABLES[memory_type]["reviewed_status"] in values
        for reviewed_status in REVIEWED_MEMORY_STATUSES[memory_type]:
            assert reviewed_status in values


def test_migration_004_is_discovered_by_migration_runner() -> None:
    path = migration_file_by_id("004")

    assert path is not None
    migration_id, name = migration_parts(path)
    assert migration_id == "004"
    assert name == "draft_status"


def test_draft_status_migration_only_extends_status_constraints() -> None:
    path = migration_file_by_id("004")
    assert path is not None
    sql = path.read_text(encoding="utf-8")
    sql_body = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )

    assert "pg_constraint" in sql
    assert "pg_get_constraintdef" in sql
    assert "resolved_at CHECK" in sql
    for table in ("facts", "decisions", "risks", "open_questions"):
        assert f"'public.{table}'::regclass" in sql
        assert f"ALTER TABLE public.{table}" in sql
        assert f"ADD CONSTRAINT {table}_status_check" in sql
    assert "'draft'" in sql
    assert "ALTER COLUMN" not in sql_body.upper()
    assert "SET DEFAULT" not in sql_body.upper()
    assert "CREATE TABLE" not in sql_body.upper()
    assert "UPDATE " not in sql_body.upper()
    assert "INSERT INTO" not in sql_body.upper()


def test_quality_queries_exclude_drafts_from_reviewed_quality() -> None:
    counts_source = inspect.getsource(fetch_project_counts)
    warnings_source = inspect.getsource(fetch_memory_quality_warnings)

    assert "status NOT IN ('draft', 'archived')" in counts_source
    assert "'draft', 'answered', 'closed', 'resolved', 'archived'" in counts_source
    assert "status NOT IN ('draft', 'resolved', 'archived')" in counts_source
    assert "status NOT IN ('draft', 'archived')" in warnings_source
    assert (
        "oq.status NOT IN ('draft', 'answered', 'closed', 'resolved', 'archived')"
        in warnings_source
    )
