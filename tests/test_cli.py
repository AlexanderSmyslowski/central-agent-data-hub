from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from agent_hub import cli
from agent_hub import export_obsidian


def test_confidence_value_accepts_range_edges() -> None:
    assert cli.confidence_value("0") == 0
    assert cli.confidence_value("0.75") == 0.75
    assert cli.confidence_value("1") == 1


@pytest.mark.parametrize("value", ["-0.01", "1.01", "not-a-number"])
def test_confidence_value_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli.confidence_value(value)


def test_parse_metadata_parses_json_and_strings() -> None:
    assert cli.parse_metadata(["flag=true", "count=3", "topic=seo"]) == {
        "flag": True,
        "count": 3,
        "topic": "seo",
    }


@pytest.mark.parametrize("value", ["missing-separator", "=empty-key"])
def test_parse_metadata_rejects_invalid_entries(value: str) -> None:
    with pytest.raises(ValueError):
        cli.parse_metadata([value])


def test_truncate_keeps_short_text_and_shortens_long_text() -> None:
    assert cli.truncate("short", 10) == "short"
    assert cli.truncate("abcdefghijklmnopqrstuvwxyz", 10) == "abcdefg..."


def test_limit_markdown_chars_adds_truncation_marker() -> None:
    text = "a" * 120

    limited = cli.limit_markdown_chars(text, 80)

    assert len(limited) <= 80
    assert "output truncated by --max-chars" in limited


def test_positive_int_rejects_zero() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli.positive_int("0")


def test_parse_since_accepts_duration_and_iso_date() -> None:
    assert cli.parse_since("24h") < datetime.now(cli.timezone.utc)
    parsed = cli.parse_since("2026-05-29")
    assert parsed.isoformat() == "2026-05-29T00:00:00+00:00"


def test_parse_since_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        cli.parse_since("yesterday-ish")


def test_brief_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["brief", "--project", "commcats-de"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_remember_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(
        [
            "remember",
            "--project",
            "commcats-de",
            "--type",
            "fact",
            "--text",
            "Smoke fact",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_sync_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["sync", "--path", "notes", "--plan"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_projects_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["projects"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_compile_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["compile", "--project", "central-agent-data-hub"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_quality_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["quality", "--project", "central-agent-data-hub"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_migrate_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["migrate", "--status"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_relations_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(["relations", "--project", "commcats-de"])

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_relate_without_database_url_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(
        [
            "relate",
            "--project",
            "commcats-de",
            "--source-type",
            "fact",
            "--source-id",
            "10000000-0000-4000-8000-000000000201",
            "--relation",
            "supports",
            "--target-type",
            "decision",
            "--target-id",
            "10000000-0000-4000-8000-000000000301",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "command",
    [
        ["daily", "--project", "commcats-de"],
        ["handoff", "--project", "commcats-de"],
        ["review", "--project", "commcats-de"],
        ["search", "--project", "commcats-de", "--query", "Alfahosting"],
        ["context", "--project", "commcats-de", "--query", "Alfahosting"],
        ["receipt", "--project", "commcats-de"],
    ],
)
def test_retrieval_commands_without_database_url_have_clear_error(
    command: list[str], monkeypatch, capsys
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = cli.main(command)

    captured = capsys.readouterr()
    assert code == 2
    assert "DATABASE_URL is not set" in captured.err
    assert "Traceback" not in captured.err


def test_receipt_export_path_uses_obsidian_filename(tmp_path: Path) -> None:
    path = cli.export_path_for_object(
        tmp_path,
        "report",
        {
            "id": uuid.UUID("10000000-0000-4000-8000-000000000601"),
            "title": "Demo Report",
        },
    )

    assert path == tmp_path / "Reports" / "demo-report-00000601.md"


def test_obsidian_wikilink_uses_relative_path_without_suffix(tmp_path: Path) -> None:
    path = tmp_path / "Facts" / "demo-fact-00000201.md"

    link = export_obsidian.wikilink(tmp_path, path, "fact: Demo | Fact")

    assert link == "[[Facts/demo-fact-00000201|fact: Demo - Fact]]"


def test_hub_home_context_links_compiled_project_pages(tmp_path: Path) -> None:
    project_id = uuid.UUID("10000000-0000-4000-8000-000000000001")

    context = export_obsidian.hub_home_context(
        tmp_path,
        {
            "projects": [
                {
                    "id": str(project_id),
                    "name": "Project A",
                    "slug": "project-a",
                    "status": "active",
                    "description": "Demo project.",
                }
            ],
            "open_questions": [
                {
                    "project_id": str(project_id),
                    "question": "What remains open?",
                    "status": "open",
                }
            ],
            "reports": [],
        },
        "2026-05-29T00:00:00+00:00",
    )

    assert context["projects"][0]["link"] == "[[Compiled/project-a|Project A]]"
    assert context["open_questions"][0]["question"] == "What remains open?"


def test_relations_requires_object_type_and_id_together(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")

    code = cli.main(
        [
            "relations",
            "--project",
            "commcats-de",
            "--object-type",
            "fact",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "--object-type and --object-id must be used together" in captured.err


def test_validate_relation_object_allows_projectless_agent() -> None:
    project = {"id": uuid.UUID("10000000-0000-4000-8000-000000000001"), "slug": "demo"}
    row = {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000011"),
        "project_id": None,
        "summary": "Codex",
    }

    cli.validate_relation_object("agent", row, project, "source")


def test_validate_relation_object_rejects_project_mismatch() -> None:
    project = {"id": uuid.UUID("10000000-0000-4000-8000-000000000001"), "slug": "demo"}
    row = {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000201"),
        "project_id": uuid.UUID("10000000-0000-4000-8000-000000000002"),
        "summary": "Wrong project fact",
    }

    with pytest.raises(RuntimeError, match="does not belong to project demo"):
        cli.validate_relation_object("fact", row, project, "source")


def test_migration_parts_reads_id_and_name() -> None:
    migration_id, name = cli.migration_parts(cli.MIGRATIONS_DIR / "002_schema_migrations.sql")

    assert migration_id == "002"
    assert name == "schema_migrations"


def test_sync_requires_plan_or_apply(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")

    code = cli.main(["sync", "--path", "notes"])

    captured = capsys.readouterr()
    assert code == 2
    assert "choose exactly one of --plan or --apply" in captured.err


def test_sync_json_output_includes_diffs(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")

    class SyncResult:
        def __init__(self):
            self.planned = [
                {
                    "action": "update",
                    "path": "notes/fact.md",
                    "project": "commcats-de",
                    "type": "fact",
                    "import_key": "fact-key",
                    "diffs": [
                        {
                            "field": "statement",
                            "database_value": "Old",
                            "markdown_value": "New",
                            "last_imported_value": "Old",
                            "owner": "obsidian",
                        }
                    ],
                }
            ]
            self.applied = []
            self.errors = []

        @property
        def blocking_actions(self):
            return []

    class FakeConnectionContext:
        def __enter__(self):
            return SimpleNamespace()

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(cli, "connect", lambda: FakeConnectionContext())
    monkeypatch.setattr(
        cli,
        "sync_markdown",
        lambda *_args, **_kwargs: SyncResult(),
    )

    code = cli.main(
        [
            "sync",
            "--path",
            "notes",
            "--plan",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert '"diffs"' in captured.out
    assert '"field": "statement"' in captured.out


class FakeCursor:
    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, _params: object = None) -> None:
        if "FROM projects" in query and "WHERE slug" in query:
            self.results = [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
                    "name": "CommCats",
                    "slug": "commcats-de",
                    "description": "Static website memory.",
                    "status": "active",
                    "metadata": {"memory_scope": "website"},
                    "created_at": "2026-05-28T00:00:00Z",
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]
        elif "SELECT" in query and "AS documents" in query:
            self.results = [
                {
                    "documents": 0,
                    "facts": 1,
                    "decisions": 1,
                    "open_questions": 0,
                    "risks": 0,
                    "reports": 0,
                    "agent_actions": 0,
                }
            ]
        elif "FROM decisions" in query:
            self.results = [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000301"),
                    "decision": "Keep static hosting.",
                    "rationale": "It is already live.",
                    "status": "accepted",
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]
        elif "FROM facts" in query:
            self.results = [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000201"),
                    "statement": "CommCats is static.",
                    "source": "seed/business_sites.sql",
                    "confidence": 0.95,
                    "status": "verified",
                    "updated_at": "2026-05-28T00:00:00Z",
                }
            ]
        else:
            self.results = []

    def fetchone(self) -> dict[str, object] | None:
        return self.results[0] if self.results else None

    def fetchall(self) -> list[dict[str, object]]:
        return self.results


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor()


def test_brief_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setattr(cli, "connect", lambda: FakeConnection())

    code = cli.main(["brief", "--project", "commcats-de", "--format", "json"])

    captured = capsys.readouterr()
    assert code == 0
    assert '"slug": "commcats-de"' in captured.out
    assert '"decisions"' in captured.out
    assert '"facts"' in captured.out


class FakeProjectsCursor:
    last_params: object = None

    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []

    def __enter__(self) -> "FakeProjectsCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _query: str, _params: object = None) -> None:
        FakeProjectsCursor.last_params = _params
        self.results = [
            {
                "slug": "commcats-de",
                "name": "CommCats",
                "status": "active",
                "description": "Static site work.",
                "metadata": {"memory_scope": "website", "project_type": "website"},
            },
            {
                "slug": "lamour",
                "name": "L'Amour",
                "status": "active",
                "description": "Planned future project.",
                "metadata": {"project_type": "website"},
            },
        ]

    def fetchall(self) -> list[dict[str, object]]:
        return self.results


class FakeProjectsConnection:
    def __enter__(self) -> "FakeProjectsConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeProjectsCursor:
        return FakeProjectsCursor()


def test_projects_text_output(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setattr(cli, "connect", lambda: FakeProjectsConnection())

    code = cli.main(["projects"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Active projects:" in captured.out
    assert "commcats-de [active] (website) CommCats" in captured.out
    assert "lamour [active] (website) L'Amour" in captured.out


def test_projects_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setattr(cli, "connect", lambda: FakeProjectsConnection())

    code = cli.main(["projects", "--format", "json"])

    captured = capsys.readouterr()
    assert code == 0
    assert '"slug": "commcats-de"' in captured.out
    assert '"name": "L\'Amour"' in captured.out


def test_projects_type_filter_passes_project_type(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setattr(cli, "connect", lambda: FakeProjectsConnection())

    code = cli.main(["projects", "--type", "website"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Active projects:" in captured.out
    assert FakeProjectsCursor.last_params == ("website",)


class FakeQualityCursor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, _query: str, _params: object = None) -> None:
        self.calls += 1

    def fetchall(self) -> list[dict[str, object]]:
        if self.calls == 1:
            return [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000201"),
                    "type": "fact",
                    "title": "Fact without source.",
                    "issue": "missing source",
                }
            ]
        if self.calls == 2:
            return [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000301"),
                    "type": "decision",
                    "title": "Decision without rationale.",
                    "issue": "missing rationale",
                }
            ]
        if self.calls == 3:
            return [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000501"),
                    "type": "risk",
                    "title": "Risk without mitigation.",
                    "issue": "missing impact or mitigation",
                }
            ]
        if self.calls == 4:
            return [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000601"),
                    "type": "report",
                    "title": "Report without summary.",
                    "issue": "missing summary",
                }
            ]
        if self.calls == 5:
            return [
                {
                    "id": uuid.UUID("10000000-0000-4000-8000-000000000401"),
                    "type": "open_question",
                    "title": "Answered without answer?",
                    "issue": "answered or closed without answer",
                }
            ]
        return []


def test_fetch_memory_quality_warnings_collects_curated_quality_gaps() -> None:
    rows = cli.fetch_memory_quality_warnings(FakeQualityCursor())

    assert [row["type"] for row in rows] == [
        "fact",
        "decision",
        "risk",
        "report",
        "open_question",
    ]
    assert rows[0]["issue"] == "missing source"
    assert rows[-1]["issue"] == "answered or closed without answer"
