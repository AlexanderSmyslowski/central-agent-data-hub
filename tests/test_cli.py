from __future__ import annotations

import argparse
import uuid

import pytest

from agent_hub import cli


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
