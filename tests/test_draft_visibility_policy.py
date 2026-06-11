from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
import uuid

from agent_hub.commands import graph
from agent_hub.commands import summaries
from agent_hub.exporting.helpers import filename_for, normalize_row
from agent_hub.exporting.overviews import hub_home_context, project_overview_context
from agent_hub.markdown import render_markdown
from agent_hub.rendering import compiled_markdown, daily_markdown, handoff_markdown
from agent_hub.commands.search import fetch_search_payload
from agent_hub.retrieval import (
    fetch_activity_snapshot,
    fetch_brief_rows,
)
from agent_hub.statuses import (
    DRAFT_STATUS,
    agent_read_excluded_statuses,
    prepare_excluded_statuses,
    search_excluded_statuses,
)


PROJECT_ID = uuid.UUID("30000000-0000-4000-8000-000000000001")
FACT_ID = uuid.UUID("30000000-0000-4000-8000-000000000101")
DECISION_ID = uuid.UUID("30000000-0000-4000-8000-000000000201")
NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
PROJECT = {
    "id": PROJECT_ID,
    "slug": "demo",
    "name": "Demo",
    "description": "Demo project.",
    "status": "active",
}


class PolicyCursor:
    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []
        self.queries: list[str] = []
        self.params: list[object] = []

    def execute(self, query: str, params: object = None) -> None:
        self.queries.append(query)
        self.params.append(params)
        if "SELECT count(*) AS count" in query:
            self.results = [{"count": 2}]
        elif "%s AS type" in query:
            item_type = params[0] if isinstance(params, tuple) else "fact"
            self.results = [
                {
                    "id": FACT_ID,
                    "type": item_type,
                    "title": "Reviewed fact",
                    "text": "Reviewed fact",
                    "status": "verified",
                    "updated_at": NOW,
                }
            ]
        elif "FROM relations r" in query:
            self.results = []
        elif "FROM facts" in query:
            self.results = [
                {
                    "id": FACT_ID,
                    "statement": "Reviewed fact",
                    "source": "test",
                    "confidence": 0.9,
                    "status": "verified",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            ]
        elif "FROM decisions" in query:
            self.results = [
                {
                    "id": DECISION_ID,
                    "decision": "Reviewed decision",
                    "rationale": "test",
                    "consequences": None,
                    "status": "accepted",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            ]
        else:
            self.results = []

    def fetchone(self) -> dict[str, object] | None:
        return self.results[0] if self.results else None

    def fetchall(self) -> list[dict[str, object]]:
        return self.results


def draft_count() -> dict[str, object]:
    return {
        "total": 1,
        "by_type": {"facts": 1},
        "label": "1 drafts awaiting review (agent-hub inbox)",
    }


def test_status_policy_excludes_drafts_and_inactive_by_default() -> None:
    assert search_excluded_statuses("fact") == (
        DRAFT_STATUS,
        "archived",
        "deprecated",
    )
    assert search_excluded_statuses("fact", include_drafts=True) == (
        "archived",
        "deprecated",
    )
    assert search_excluded_statuses("fact", include_archived=True) == (DRAFT_STATUS,)
    assert search_excluded_statuses(
        "fact",
        include_drafts=True,
        include_archived=True,
    ) == ()


def test_prepare_policy_keeps_drafts_visible_to_prepare() -> None:
    assert DRAFT_STATUS not in prepare_excluded_statuses("fact")
    assert prepare_excluded_statuses("fact") == ("archived", "deprecated")


def test_no_read_surface_status_tuples_are_hardcoded_outside_statuses() -> None:
    root = Path(__file__).resolve().parents[1]
    checked = [
        root / "agent_hub" / "commands" / "briefs.py",
        root / "agent_hub" / "commands" / "summaries.py",
        root / "agent_hub" / "commands" / "prepare.py",
        root / "agent_hub" / "retrieval.py",
        root / "agent_hub" / "exporting" / "overviews.py",
    ]
    forbidden = [
        "('archived'",
        '("archived"',
        "status = 'draft'",
        "status <> 'draft'",
    ]
    for path in checked:
        text = path.read_text(encoding="utf-8")
        assert not any(pattern in text for pattern in forbidden), path


def test_search_payload_defaults_hide_drafts_and_counts_inbox() -> None:
    cur = PolicyCursor()

    payload = fetch_search_payload(cur, PROJECT, "fact", "fact", 5)

    search_params = next(params for params in cur.params if isinstance(params, tuple) and params[0] == "fact")
    assert DRAFT_STATUS in search_params
    assert "archived" in search_params
    assert "deprecated" in search_params
    assert payload["drafts_awaiting_review"]["total"] == 10
    assert payload["results"][0]["status"] == "verified"


def test_search_include_flags_remove_policy_exclusions() -> None:
    cur = PolicyCursor()

    fetch_search_payload(
        cur,
        PROJECT,
        "fact",
        "fact",
        5,
        include_drafts=True,
        include_archived=True,
    )

    search_params = next(params for params in cur.params if isinstance(params, tuple) and params[0] == "fact")
    assert DRAFT_STATUS not in search_params
    assert "archived" not in search_params
    assert "deprecated" not in search_params


def test_brief_rows_use_agent_read_policy_by_default() -> None:
    cur = PolicyCursor()

    fetch_brief_rows(cur, "facts", PROJECT_ID, "id, statement", limit=3)

    params = cur.params[-1]
    assert isinstance(params, tuple)
    assert DRAFT_STATUS in params
    assert "archived" in params
    assert "deprecated" in params


def test_activity_snapshot_daily_keeps_drafts_but_handoff_filters_them() -> None:
    daily_cur = PolicyCursor()
    fetch_activity_snapshot(daily_cur, PROJECT, NOW, 3, surface="daily")
    daily_fact_params = next(
        params
        for query, params in zip(daily_cur.queries, daily_cur.params)
        if "FROM facts" in query and "updated_at >= %s" in query
    )

    handoff_cur = PolicyCursor()
    fetch_activity_snapshot(handoff_cur, PROJECT, NOW, 3, surface="handoff")
    handoff_fact_params = next(
        params
        for query, params in zip(handoff_cur.queries, handoff_cur.params)
        if "FROM facts" in query and "updated_at >= %s" in query
    )

    assert DRAFT_STATUS not in daily_fact_params
    assert DRAFT_STATUS in handoff_fact_params


def test_daily_markdown_shows_draft_questions_and_count_line() -> None:
    rendered = daily_markdown(
        {
            "project": PROJECT,
            "since": NOW,
            "drafts_awaiting_review": draft_count(),
            "facts": [],
            "decisions": [],
            "risks": [],
            "open_questions": [
                {"id": FACT_ID, "question": "Draft question?", "status": "draft"}
            ],
            "reports": [],
            "relations": [],
            "agent_actions": [],
            "sync_events": [],
        }
    )

    assert "1 drafts awaiting review (agent-hub inbox)" in rendered
    assert "[draft] Draft question?" in rendered


def test_daily_write_report_does_not_publish_draft_text(monkeypatch, capsys) -> None:
    sentinel = "UNREVIEWED_DRAFT_SENTINEL_123"

    class DailyWriteCursor:
        inserted_body = ""

        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []

        def __enter__(self) -> "DailyWriteCursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            if "FROM relations r" in query:
                self.results = []
            elif "FROM projects" in query and "WHERE slug" in query:
                self.results = [PROJECT]
            elif "SELECT count(*) AS count" in query:
                self.results = [
                    {"count": 1 if "FROM facts" in query else 0}
                ]
            elif "INSERT INTO reports" in query:
                assert isinstance(params, tuple)
                DailyWriteCursor.inserted_body = str(params[3])
                self.results = [
                    {
                        "id": uuid.UUID("30000000-0000-4000-8000-000000000901"),
                        "title": "Daily Report",
                        "report_type": "daily",
                        "summary": "safe",
                        "status": "published",
                        "created_at": NOW,
                    }
                ]
            elif "FROM facts" in query and "updated_at >= %s" in query:
                if isinstance(params, tuple) and DRAFT_STATUS in params:
                    self.results = []
                else:
                    self.results = [
                        {
                            "id": FACT_ID,
                            "statement": sentinel,
                            "source": "test",
                            "confidence": 0.9,
                            "status": "draft",
                            "created_at": NOW,
                            "updated_at": NOW,
                        }
                    ]
            else:
                self.results = []

        def fetchone(self) -> dict[str, object] | None:
            return self.results[0] if self.results else None

        def fetchall(self) -> list[dict[str, object]]:
            return self.results

    class DailyWriteConnection:
        def __enter__(self) -> "DailyWriteConnection":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> DailyWriteCursor:
            return DailyWriteCursor()

    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setattr(summaries, "connect", lambda: DailyWriteConnection())

    code = summaries.run_daily(
        Namespace(
            project="demo",
            since="24h",
            limit=5,
            write_report=True,
            format="text",
        )
    )

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert sentinel in captured.out
    assert "Written report:" in captured.out
    assert sentinel not in DailyWriteCursor.inserted_body
    assert "1 drafts awaiting review (agent-hub inbox)" in DailyWriteCursor.inserted_body


def test_handoff_and_compile_markdown_show_count_line() -> None:
    handoff = handoff_markdown(
        {
            "project": PROJECT,
            "since": NOW,
            "drafts_awaiting_review": draft_count(),
            "decisions": [],
            "risks": [],
            "open_questions": [],
            "facts": [],
            "relations": [],
        }
    )
    compiled = compiled_markdown(
        {
            "project": PROJECT,
            "counts": {"facts": 0, "decisions": 0, "open_questions": 0},
            "drafts_awaiting_review": draft_count(),
            "decisions": [],
            "risks": [],
            "open_questions": [],
            "facts": [],
            "relations": [],
            "reports": [],
        }
    )

    assert "1 drafts awaiting review (agent-hub inbox)" in handoff
    assert "1 drafts awaiting review (agent-hub inbox)" in compiled


def test_export_draft_page_gets_review_status_warning_and_stable_filename() -> None:
    row = normalize_row(
        {
            "id": FACT_ID,
            "project_id": PROJECT_ID,
            "statement": "Draft exported fact",
            "source": "test",
            "confidence": 0.9,
            "status": "draft",
            "created_at": NOW,
            "updated_at": NOW,
        }
    )

    rendered = render_markdown("fact.md.j2", row)

    assert filename_for(row, ("statement",)) == "draft-exported-fact-00000101.md"
    assert 'review_status: "draft"' in rendered
    assert "Unreviewed draft — not part of reviewed memory" in rendered
    assert "## Human Notes" in rendered


def test_project_overview_filters_drafts_from_main_lists_and_counts_them() -> None:
    context = project_overview_context(
        PROJECT,
        {
            "facts": [
                {
                    "id": FACT_ID,
                    "project_id": PROJECT_ID,
                    "statement": "Draft fact",
                    "status": "draft",
                },
                {
                    "id": uuid.UUID("30000000-0000-4000-8000-000000000102"),
                    "project_id": PROJECT_ID,
                    "statement": "Verified fact",
                    "status": "verified",
                },
            ],
            "decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
        },
        [],
        NOW.isoformat(),
    )

    assert [row["statement"] for row in context["facts"]] == ["Verified fact"]
    assert context["drafts_awaiting_review"]["total"] == 1


def test_hub_home_filters_drafts_from_overview_lists_and_counts_them(tmp_path: Path) -> None:
    context = hub_home_context(
        tmp_path,
        {
            "projects": [PROJECT],
            "open_questions": [
                {
                    "id": FACT_ID,
                    "project_id": PROJECT_ID,
                    "question": "Draft question?",
                    "status": "draft",
                }
            ],
            "reports": [
                {
                    "id": DECISION_ID,
                    "project_id": PROJECT_ID,
                    "title": "Draft report",
                    "status": "draft",
                }
            ],
            "facts": [],
            "decisions": [],
            "risks": [],
        },
        NOW.isoformat(),
    )

    assert context["open_questions"] == []
    assert context["recent_reports"] == []
    assert context["drafts_awaiting_review"]["total"] == 2


def test_relate_warns_when_source_or_target_is_draft(monkeypatch, capsys) -> None:
    class RelateCursor:
        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []

        def __enter__(self) -> "RelateCursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            if "FROM projects" in query:
                self.results = [PROJECT]
            elif "FROM facts" in query:
                self.results = [
                    {
                        "id": FACT_ID,
                        "project_id": PROJECT_ID,
                        "summary": "Draft fact",
                        "status": "draft",
                    }
                ]
            elif "FROM decisions" in query:
                self.results = [
                    {
                        "id": DECISION_ID,
                        "project_id": PROJECT_ID,
                        "summary": "Reviewed decision",
                        "status": "accepted",
                    }
                ]
            elif "INSERT INTO relations" in query:
                self.results = [
                    {
                        "id": uuid.UUID("30000000-0000-4000-8000-000000000301"),
                        "source_type": "fact",
                        "source_id": FACT_ID,
                        "relation_type": "supports",
                        "target_type": "decision",
                        "target_id": DECISION_ID,
                        "metadata": {},
                        "created_at": NOW,
                        "updated_at": NOW,
                    }
                ]
            else:
                self.results = []

        def fetchone(self) -> dict[str, object] | None:
            return self.results[0] if self.results else None

        def fetchall(self) -> list[dict[str, object]]:
            return self.results

    class RelateConnection:
        def __enter__(self) -> "RelateConnection":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> RelateCursor:
            return RelateCursor()

    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.setattr(graph, "connect", lambda: RelateConnection())

    code = graph.run_relate(
        Namespace(
            project="demo",
            source_type="fact",
            source_id=str(FACT_ID),
            relation="supports",
            target_type="decision",
            target_id=str(DECISION_ID),
            metadata=[],
            format="text",
        )
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "Relation stored:" in captured.out
    assert "Warning: source fact" in captured.out
    assert "status=draft" in captured.out
