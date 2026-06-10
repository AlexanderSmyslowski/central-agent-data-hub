from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

import pytest

from agent_hub import cli, db, mcp_server
from agent_hub.commands import mcp as mcp_command


PROJECT_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
FACT_ID = uuid.UUID("10000000-0000-4000-8000-000000000201")
DECISION_ID = uuid.UUID("10000000-0000-4000-8000-000000000301")
RISK_ID = uuid.UUID("10000000-0000-4000-8000-000000000401")
QUESTION_ID = uuid.UUID("10000000-0000-4000-8000-000000000501")
REPORT_ID = uuid.UUID("10000000-0000-4000-8000-000000000601")
RELATION_ID = uuid.UUID("10000000-0000-4000-8000-000000000701")
NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def row(**values: object) -> dict[str, object]:
    base = {"created_at": NOW, "updated_at": NOW}
    base.update(values)
    return base


class ReadOnlyFakeCursor:
    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []
        self.queries: list[str] = []

    def __enter__(self) -> "ReadOnlyFakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: object = None) -> None:
        if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER)\b", query.upper()):
            raise AssertionError("MCP server must stay read-only")
        self.queries.append(query)
        if "FROM projects" in query and "WHERE status = 'active'" in query:
            self.results = [
                {
                    "id": PROJECT_ID,
                    "slug": "central-agent-data-hub-demo",
                    "name": "Central Agent Data Hub Demo",
                    "status": "active",
                }
            ]
        elif "FROM projects" in query and "WHERE slug = %s" in query:
            slug = params[0] if isinstance(params, tuple) else None
            self.results = [self.project()] if slug == "central-agent-data-hub-demo" else []
        elif "SELECT" in query and "AS documents" in query:
            self.results = [
                {
                    "documents": 0,
                    "facts": 1,
                    "decisions": 1,
                    "open_questions": 1,
                    "open_questions_total": 1,
                    "risks": 1,
                    "reports": 1,
                    "agent_actions": 0,
                }
            ]
        elif "SELECT count(*) AS count" in query and "status = 'draft'" in query:
            self.results = [{"count": 0}]
        elif "FROM relations r" in query:
            self.results = [self.relation()]
        elif "plainto_tsquery" in query:
            self.results = self.task_match_rows(query)
        elif "%s AS type" in query:
            self.results = self.search_rows(query, params)
        elif "FROM facts" in query:
            self.results = [self.fact()]
        elif "FROM decisions" in query:
            self.results = [self.decision()]
        elif "FROM risks" in query:
            self.results = [self.risk()]
        elif "FROM open_questions" in query:
            self.results = [self.open_question()]
        elif "FROM reports" in query:
            self.results = [self.report()]
        else:
            self.results = []

    def fetchone(self) -> dict[str, object] | None:
        return self.results[0] if self.results else None

    def fetchall(self) -> list[dict[str, object]]:
        return self.results

    def project(self) -> dict[str, object]:
        return {
            "id": PROJECT_ID,
            "name": "Central Agent Data Hub Demo",
            "slug": "central-agent-data-hub-demo",
            "description": "Demo project.",
            "status": "active",
            "metadata": {},
            "created_at": NOW,
            "updated_at": NOW,
        }

    def fact(self) -> dict[str, object]:
        return row(
            id=FACT_ID,
            statement="Agent Data Hub stores reviewed memory.",
            source="README.md",
            confidence=0.95,
            status="verified",
        )

    def decision(self) -> dict[str, object]:
        return row(
            id=DECISION_ID,
            decision="Keep the MCP server read-only.",
            rationale="Writes stay behind human review.",
            consequences=None,
            status="accepted",
        )

    def risk(self) -> dict[str, object]:
        return row(
            id=RISK_ID,
            title="Context drift",
            severity="medium",
            impact="Agents may use stale context.",
            mitigation="Use prepare before scoped work.",
            status="open",
        )

    def open_question(self) -> dict[str, object]:
        return row(
            id=QUESTION_ID,
            question="Should MCP expose writes?",
            answer=None,
            status="open",
        )

    def report(self) -> dict[str, object]:
        return row(
            id=REPORT_ID,
            title="MCP Smoke",
            report_type="status",
            summary="Read-only MCP payload smoke.",
            status="published",
        )

    def relation(self) -> dict[str, object]:
        return row(
            id=RELATION_ID,
            source_type="fact",
            source_id=FACT_ID,
            source_summary="Agent Data Hub stores reviewed memory.",
            relation_type="supports",
            target_type="decision",
            target_id=DECISION_ID,
            target_summary="Keep the MCP server read-only.",
            metadata={},
        )

    def search_rows(self, query: str, params: object) -> list[dict[str, object]]:
        item_type = params[0] if isinstance(params, tuple) else "unknown"
        if "FROM facts" not in query:
            return []
        return [
            row(
                id=FACT_ID,
                type=item_type,
                title="Agent Data Hub stores reviewed memory.",
                text="Agent Data Hub stores reviewed memory.",
                status="verified",
            )
        ]

    def task_match_rows(self, query: str) -> list[dict[str, object]]:
        if "FROM facts" in query:
            matched = dict(self.fact())
            matched["task_score"] = 0.42
            return [matched]
        return []


class FakeConnection:
    def __init__(self, cursor: ReadOnlyFakeCursor | None = None) -> None:
        self.cursor_obj = cursor or ReadOnlyFakeCursor()

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> ReadOnlyFakeCursor:
        return self.cursor_obj


def test_list_projects_tool_payload_is_read_only() -> None:
    cur = ReadOnlyFakeCursor()

    projects = mcp_server.list_projects_payload(cur)

    assert projects == [
        {
            "id": PROJECT_ID,
            "slug": "central-agent-data-hub-demo",
            "name": "Central Agent Data Hub Demo",
            "status": "active",
        }
    ]


def test_search_memory_payload_matches_cli_json_shape() -> None:
    cur = ReadOnlyFakeCursor()

    payload = mcp_server.search_memory_payload(
        cur,
        "central-agent-data-hub-demo",
        "reviewed memory",
        limit=5,
    )

    assert set(payload) == {"project", "query", "results"}
    assert payload["project"]["slug"] == "central-agent-data-hub-demo"
    assert payload["query"] == "reviewed memory"
    assert payload["results"][0]["type"] == "fact"
    assert payload["results"][0]["title"] == "Agent Data Hub stores reviewed memory."


def test_project_brief_payload_uses_compact_brief_shape() -> None:
    cur = ReadOnlyFakeCursor()

    payload = mcp_server.project_brief_payload(
        cur,
        "central-agent-data-hub-demo",
        limit=4,
    )

    assert set(payload) == {
        "project",
        "counts",
        "decisions",
        "facts",
        "open_questions",
        "risks",
        "reports",
        "relations",
    }
    assert payload["project"]["slug"] == "central-agent-data-hub-demo"
    assert payload["facts"][0]["source"] == "README.md"
    assert payload["relations"] == []


def test_prepare_context_pack_payload_keeps_trail_gaps_and_review_labels() -> None:
    cur = ReadOnlyFakeCursor()

    payload = mcp_server.prepare_context_pack_payload(
        cur,
        "central-agent-data-hub-demo",
        "read-only mcp server",
        limit=3,
        stale_after_days=42,
    )

    assert payload["project"]["slug"] == "central-agent-data-hub-demo"
    assert payload["context_trail"]["sources"]
    assert payload["context_trail"]["sources"][0]["review_status"] == "verified"
    assert "gap_summary" in payload["context_trail"]
    assert "gaps" in payload
    assert payload["gaps"]["summary"]["thresholds"]["stale_after_days"] == 42


def test_unknown_project_becomes_clean_tool_failure() -> None:
    cur = ReadOnlyFakeCursor()

    with pytest.raises(mcp_server.MCPToolFailure, match="project 'missing' not found"):
        mcp_server.project_brief_payload(cur, "missing")


def test_invalid_limit_is_rejected_before_query_work() -> None:
    cur = ReadOnlyFakeCursor()

    with pytest.raises(mcp_server.MCPToolFailure, match="limit must be a positive integer"):
        mcp_server.search_memory_payload(cur, "central-agent-data-hub-demo", "memory", 0)


def test_run_read_only_query_requests_read_only_connection(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_connect(*, read_only: bool = False) -> FakeConnection:
        calls.append(read_only)
        return FakeConnection()

    monkeypatch.setattr(mcp_server, "connect", fake_connect)

    payload = mcp_server.run_read_only_query(
        lambda cur: mcp_server.search_memory_payload(
            cur,
            "central-agent-data-hub-demo",
            "reviewed memory",
        )
    )

    assert calls == [True]
    assert payload["project"]["slug"] == "central-agent-data-hub-demo"
    assert isinstance(payload["results"][0]["id"], str)


def test_db_connect_read_only_sets_postgres_session_option(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_psycopg_connect(database_url: str, **kwargs: object) -> object:
        calls.append({"database_url": database_url, **kwargs})
        return object()

    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/agent_hub")
    monkeypatch.setattr(db.psycopg, "connect", fake_psycopg_connect)

    db.connect(read_only=True)

    assert calls[0]["database_url"] == "postgresql://example.invalid/agent_hub"
    assert calls[0]["options"] == "-c default_transaction_read_only=on"
    assert calls[0]["row_factory"] is db.dict_row


def test_mcp_serve_missing_dependency_has_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/agent_hub")

    def missing() -> None:
        raise mcp_server.MissingMCPDependency(
            "MCP support is optional. Install it with: pip install -e '.[mcp]'"
        )

    monkeypatch.setattr(mcp_command, "run_stdio_server", missing)

    code = cli.main(["mcp-serve"])

    captured = capsys.readouterr()
    assert code == 2
    assert "pip install -e '.[mcp]'" in captured.err


def test_create_mcp_server_registers_only_four_read_tools(monkeypatch) -> None:
    registered: list[tuple[str, str]] = []

    class FakeFastMCP:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def tool(self, *, description: str, **_kwargs: object):
            def decorator(fn):
                registered.append((fn.__name__, description))
                return fn

            return decorator

    monkeypatch.setattr(
        mcp_server,
        "load_fastmcp",
        lambda: (FakeFastMCP, RuntimeError),
    )

    mcp_server.create_mcp_server()

    assert [name for name, _description in registered] == [
        "list_projects",
        "prepare_context_pack",
        "search_memory",
        "project_brief",
    ]
    assert all("write" not in name for name, _description in registered)


def test_mcp_server_does_not_import_write_boundaries() -> None:
    names = set(vars(mcp_server))

    assert "run_remember" not in names
    assert "run_inbox" not in names
    assert "run_import" not in names
