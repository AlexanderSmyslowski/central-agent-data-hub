from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
import re
import sys
from urllib.parse import urlencode
import uuid

import pytest

from agent_hub import hub_view
from agent_hub.hub_view_i18n import language_switch_links, localize_ui_text
from agent_hub import hub_view_models
from agent_hub.commands import inbox
from agent_hub.writeback_routing import lint_card_text


DRAFT_ID = uuid.UUID("10000000-0000-4000-8000-000000000701")


def draft_row(*, status: str = "draft") -> dict[str, object]:
    return {
        "id": DRAFT_ID,
        "project_id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
        "project": "central-agent-data-hub",
        "project_name": "Central Agent Data Hub",
        "type": "fact",
        "statement": "Drafts require explicit review.",
        "source": "test",
        "confidence": 0.9,
        "status": status,
        "metadata": {"created_by": "test", "assigned_reviewer": "alice"},
        "created_at": "2026-06-10T10:00:00Z",
        "updated_at": "2026-06-10T10:00:00Z",
    }

def review_action_row(*, action: str = "inbox_accept") -> dict[str, object]:
    return {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000801"),
        "action": action,
        "object_type": "fact",
        "object_id": DRAFT_ID,
        "output": {
            "next_status": "verified" if action == "inbox_accept" else "archived",
            "reviewed_by": "bob",
            "review_source": "hub_view",
        },
        "metadata": {
            "reviewed_by": "bob",
            "review_source": "hub_view",
        },
        "project": "central-agent-data-hub",
        "project_name": "Central Agent Data Hub",
        "updated_at": datetime(2026, 6, 10, 11, 15, tzinfo=timezone.utc),
    }


def call_app(
    app,
    *,
    method: str = "GET",
    path: str = "/",
    form: dict[str, str] | None = None,
    query: str = "",
    origin: str | None = None,
) -> tuple[dict[str, object], str]:
    captured: dict[str, object] = {}
    body = urlencode(form or {}).encode("utf-8")

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    environ: dict[str, object] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "wsgi.input": BytesIO(body),
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
    }
    if origin:
        environ["HTTP_ORIGIN"] = origin

    response = b"".join(app(environ, start_response)).decode("utf-8")
    return captured, response


def test_hub_view_localizes_dynamic_codex_status_text() -> None:
    assert localize_ui_text("Demo preview only", "de") == "Nur Demo-Vorschau"
    assert (
        localize_ui_text(
            "Demo mode shows the target only; it does not write an AGENTS.md block.",
            "de",
        )
        == "Der Demo-Modus zeigt nur das Ziel; er schreibt keinen AGENTS.md-Block."
    )
    assert localize_ui_text("Demo preview only", "en") == "Demo preview only"


def test_quality_check_cards_turn_existing_quality_rows_into_review_signals() -> None:
    cards = hub_view_models.build_quality_check_cards(
        {
            "facts_without_source": [{"id": "fact-1"}],
            "decisions_without_rationale": [],
            "risks_without_mitigation": [{"id": "risk-1"}, {"id": "risk-2"}],
            "open_questions": [],
            "schema_friction_questions": [{"id": "question-1"}],
        }
    )

    assert cards[0] == {
        "count": 1,
        "state": "needs-review",
        "title_key": "quality_facts_without_source",
        "meaning_key": "quality_facts_without_source_meaning",
        "action_key": "quality_facts_without_source_action",
    }
    assert cards[1]["state"] == "ok"
    assert cards[2]["count"] == 2
    assert cards[4]["title_key"] == "quality_schema_friction"


def test_work_state_cards_prioritize_status_attention_review_and_quality() -> None:
    quality = {
        "score": 74,
        "check_cards": [
            {
                "count": 0,
                "state": "ok",
                "title_key": "quality_facts_without_source",
                "meaning_key": "quality_facts_without_source_meaning",
            },
            {
                "count": 2,
                "state": "needs-review",
                "title_key": "quality_risks_without_mitigation",
                "meaning_key": "quality_risks_without_mitigation_meaning",
            },
        ],
    }

    cards = hub_view_models.build_work_state_cards(
        reports=[{"title": "Daily report", "summary": ""}],
        risks=[{"title": "Deployment risk"}],
        open_questions=[{"question": "Who reviews adapter output?"}],
        quality=quality,
        draft_count=3,
    )

    assert [card["kind"] for card in cards] == [
        "latest",
        "attention",
        "review",
        "quality",
    ]
    assert [card["priority"] for card in cards] == ["1", "2", "3", "4"]
    assert cards[0]["title"] == "Daily report"
    assert cards[0]["body_key"] == "work_state_latest_body"
    assert cards[1]["title"] == "Deployment risk"
    assert cards[1]["risk_count"] == 1
    assert cards[1]["question_count"] == 1
    assert cards[2]["review_count"] == 3
    assert cards[2]["state"] == "needs-review"
    assert cards[3]["quality_score"] == 74
    assert cards[3]["title_key"] == "quality_risks_without_mitigation"


class ReviewCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.last_sql = ""
        self.params = None
        self.update_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=None) -> None:
        self.last_sql = sql
        self.params = params
        if sql.lstrip().upper().startswith("UPDATE"):
            self.update_count += 1

    def fetchone(self):
        if "FROM facts" in self.last_sql and "memory.id = %s" in self.last_sql:
            return self.row if self.row["status"] == "draft" else None
        if self.last_sql.lstrip().upper().startswith("UPDATE"):
            if self.row["status"] != "draft":
                return None
            self.row["status"] = self.params[0]
            return {"id": self.row["id"], "status": self.params[0]}
        return None


class ReviewConnection:
    def __init__(self, cursor: ReviewCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.cursor_obj


def test_render_page_includes_local_review_claim() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
        },
        200,
    ).decode("utf-8")

    assert "Hub View" in body
    assert 'class="brand-home" href="/"' in body
    assert "local review surface for Agent Data Hub" in body
    assert "Read surface + review actions" in body
    assert "Prototype language: English." in body
    assert 'aria-label="App navigation"' in body
    assert "Projects" in body
    assert "Review" in body


def test_render_page_can_switch_to_german_chrome() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
        },
        200,
        language="de",
        current_path="/",
        query_string="lang=de",
    ).decode("utf-8")

    assert '<html lang="de">' in body
    assert "lokale Prüfoberfläche für Agent Data Hub" in body
    assert "Leseoberfläche + Prüfaktionen" in body
    assert "Aktive Projekte" in body
    assert 'aria-label="App-Navigation"' in body
    assert "Projekte" in body
    assert "Prüfung" in body
    assert "Deutsch" in body
    assert '<form method="get" action="/">' in body
    assert '<button type="submit" aria-current="true">Deutsch</button>' in body


def test_language_switch_forms_preserve_existing_query_params() -> None:
    links = language_switch_links(
        "/projects/demo/agent-context",
        "task=Review+demo&setup_message=Done&lang=de",
    )

    english = links[0]
    german = links[1]

    assert english["path"] == "/projects/demo/agent-context"
    assert english["params"] == [
        {"name": "task", "value": "Review demo"},
        {"name": "setup_message", "value": "Done"},
    ]
    assert german["params"] == [
        {"name": "task", "value": "Review demo"},
        {"name": "setup_message", "value": "Done"},
        {"name": "lang", "value": "de"},
    ]


def test_application_rejects_non_get_requests() -> None:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        hub_view.application(
            {"REQUEST_METHOD": "POST", "PATH_INFO": "/"},
            start_response,
        )
    )

    assert captured["status"] == "405 Method Not Allowed"
    assert body == b"Method Not Allowed"


def test_build_project_cards_batches_counts_and_latest_reports(monkeypatch) -> None:
    projects = [
        {
            "id": "project-1",
            "name": "Project One",
            "slug": "project-one",
            "status": "active",
            "description": "First project",
            "metadata": {"project_type": "demo"},
            "updated_at": "2026-06-28T10:00:00+00:00",
        },
        {
            "id": "project-2",
            "name": "Project Two",
            "slug": "project-two",
            "status": "active",
            "description": "Second project",
            "metadata": {},
            "updated_at": "2026-06-28T11:00:00+00:00",
        },
    ]
    calls: list[tuple[str, list[object]]] = []

    def fake_counts(_cur, project_ids):
        calls.append(("counts", list(project_ids)))
        return {
            "project-1": {
                "documents": 0,
                "facts": 3,
                "decisions": 1,
                "open_questions": 0,
                "risks": 1,
                "reports": 2,
            },
            "project-2": {
                "documents": 0,
                "facts": 0,
                "decisions": 0,
                "open_questions": 1,
                "risks": 0,
                "reports": 0,
            },
        }

    def fake_latest_reports(_cur, project_ids):
        calls.append(("latest_reports", list(project_ids)))
        return {
            "project-1": {
                "title": "Latest report",
                "summary": "A compact summary.",
                "updated_at": "2026-06-28T12:00:00+00:00",
            }
        }

    monkeypatch.setattr(hub_view_models, "fetch_project_card_counts", fake_counts)
    monkeypatch.setattr(
        hub_view_models,
        "fetch_latest_reports_by_project",
        fake_latest_reports,
    )

    cards = hub_view_models.build_project_cards(
        object(),
        projects,
        {"project-two": 4},
    )

    assert calls == [
        ("counts", ["project-1", "project-2"]),
        ("latest_reports", ["project-1", "project-2"]),
    ]
    assert cards[0]["counts"]["facts"] == 3
    assert cards[0]["latest_report_title"] == "Latest report"
    assert cards[0]["reviewed_count"] == 7
    assert cards[0]["attention_count"] == 1
    assert cards[0]["signal_key"] == "project_overview_signal_attention"
    assert cards[0]["signal_state"] == "attention"
    assert cards[1]["counts"]["open_questions"] == 1
    assert cards[1]["draft_count"] == 4
    assert cards[1]["latest_report_title"] is None
    assert cards[1]["reviewed_count"] == 1
    assert cards[1]["attention_count"] == 1
    assert cards[1]["signal_key"] == "project_overview_signal_review"
    assert cards[1]["signal_state"] == "review"


def test_project_overview_renders_as_work_center() -> None:
    body = hub_view.render_page(
        {
            "projects": [
                {
                    "name": "Central Agent Data Hub Demo",
                    "slug": "central-agent-data-hub-demo",
                    "status": "active",
                    "description": "Neutral demo project.",
                    "project_type": "demo",
                    "counts": {
                        "facts": 3,
                        "decisions": 1,
                        "risks": 1,
                        "open_questions": 2,
                        "reports": 1,
                    },
                    "reviewed_count": 8,
                    "attention_count": 3,
                    "draft_count": 2,
                    "signal_key": "project_overview_signal_review",
                    "signal_state": "review",
                    "latest_report_title": "Latest demo report",
                    "latest_report_summary": "A compact project status.",
                    "updated_at": "2026-06-28 10:00 UTC",
                }
            ],
            "selected_project": None,
            "not_found_slug": None,
            "draft_total": 2,
        },
        200,
    ).decode("utf-8")

    assert "Project work center" in body
    assert "Central Agent Data Hub Demo" in body
    assert "Review waiting" in body
    assert "Latest demo report" in body
    assert "Attention" in body
    assert "3 risks/questions" in body
    assert "Review queue" in body
    assert "2 items" in body
    assert "Reviewed memory" in body
    assert "8 items" in body
    assert "Next actions" in body
    assert "Open project" in body
    assert "Prepare agent" in body
    assert "Review suggestions" in body
    assert "Read latest status" in body
    assert 'href="/projects/central-agent-data-hub-demo#risks-and-questions"' in body
    assert 'href="/projects/central-agent-data-hub-demo#project-memory"' in body
    assert 'href="/projects/central-agent-data-hub-demo/agent-context"' in body
    assert 'href="/inbox"' in body
    assert 'href="/projects/central-agent-data-hub-demo#latest-status"' in body
    assert 'href="/projects/central-agent-data-hub-demo"' in body


def test_project_overview_renders_german_work_center() -> None:
    body = hub_view.render_page(
        {
            "projects": [
                {
                    "name": "Central Agent Data Hub Demo",
                    "slug": "central-agent-data-hub-demo",
                    "status": "active",
                    "description": "Neutral demo project.",
                    "project_type": "demo",
                    "counts": {
                        "facts": 1,
                        "decisions": 0,
                        "risks": 0,
                        "open_questions": 1,
                        "reports": 0,
                    },
                    "reviewed_count": 2,
                    "attention_count": 1,
                    "draft_count": 0,
                    "signal_key": "project_overview_signal_attention",
                    "signal_state": "attention",
                    "latest_report_title": None,
                    "latest_report_summary": None,
                    "updated_at": "2026-06-28 10:00 UTC",
                }
            ],
            "selected_project": None,
            "not_found_slug": None,
            "draft_total": 0,
        },
        200,
        language="de",
        current_path="/",
        query_string="lang=de",
    ).decode("utf-8")

    assert "Projekt-Arbeitszentrale" in body
    assert "Braucht Aufmerksamkeit" in body
    assert "Noch kein Bericht." in body
    assert "1 Risiken/Fragen" in body
    assert "Geprüftes Gedächtnis" in body
    assert "Nächste Schritte" in body
    assert "Agent vorbereiten" in body
    assert "Vorschläge prüfen" in body
    assert "Letzten Stand lesen" in body
    assert "Projekt öffnen" in body


def test_inbox_page_lists_drafts_as_plain_cards() -> None:
    groups = hub_view.group_draft_cards([draft_row()])
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": groups,
                "csrf_token": "token",
                "enabled": True,
                "message": None,
                "error": None,
            },
            "draft_total": 1,
        },
        200,
        view_name="inbox",
    ).decode("utf-8")

    card = groups[0]["drafts"][0]["card"]
    assert lint_card_text(card) == []
    assert "Review queue" in body
    assert "Review one suggested memory change at a time." in body
    assert "Next step" in body
    assert "Open one card, check the sentence and source" in body
    assert "Nothing here becomes reviewed memory until a human clicks Accept." in body
    assert "How to review" in body
    assert "Would you want an agent to rely on this later?" in body
    assert "Is the origin concrete enough to trust?" in body
    assert "Accept stores it as reviewed memory. Reject archives it." in body
    assert "Filter review queue" in body
    assert "project, fact, source, reviewer..." in body
    assert "Visible review items: 1." in body
    assert "No review item matches this filter." in body
    assert "data-inbox-filter" in body
    assert "data-inbox-item" in body
    assert "data-inbox-group" in body
    assert "Suggested change · Fact" in body
    assert "Human decision needed" in body
    assert "Project queue" in body
    assert "Reviewer" in body
    assert "Review is ready" in body
    assert "Remember:" in body
    assert "Source: test." in body
    assert "If wrong:" in body
    assert "Reviewer: alice" in body
    assert "Why this card is here" in body
    assert 'action="/inbox/accept"' in body
    assert 'action="/inbox/reject"' in body
    assert 'name="csrf_token" value="token"' in body
    assert "Accept" in body
    assert "Reject" in body
    assert "Store as reviewed memory" in body
    assert "Archive without promoting" in body
    assert "Merken" not in body
    assert "Verwerfen" not in body


def test_inbox_page_empty_state() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": [],
                "csrf_token": "token",
                "enabled": True,
                "message": None,
                "error": None,
            },
        },
        200,
        view_name="inbox",
    ).decode("utf-8")

    assert "No items to review." in body
    assert "When agents suggest memory changes" in body
    assert "Nothing needs review right now." in body
    assert "When a card appears, check the sentence and source" in body
    assert "Suggested memory changes stay unconfirmed" in body
    assert "Review queue" in body
    assert "Reviewer not set" in body
    assert "Nothing here becomes reviewed memory" in body
    assert "Review actions are disabled because Hub View is not bound to a loopback address." not in body
    assert "Drafts stay unconfirmed" not in body
    assert 'href="/">Back to project overview</a>' in body


def test_inbox_page_renders_accept_result_card() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": [],
                "csrf_token": "token",
                "enabled": True,
                "message": None,
                "error": None,
                "review_result": {
                    "result": "accepted",
                    "item_id": str(DRAFT_ID),
                    "type": "fact",
                    "type_label": "Fact",
                    "status": "verified",
                    "project": "central-agent-data-hub",
                    "reviewed_by": "bob",
                    "review_source": "Hub View",
                },
            },
        },
        200,
        view_name="inbox",
    ).decode("utf-8")

    assert "Review result" in body
    assert 'id="review-result"' in body
    assert "Saved as reviewed memory" in body
    assert "This Fact is no longer a draft. ADH can now hand it to agents as reviewed context." in body
    assert "What changed" in body
    assert "What did not happen" in body
    assert "ADH did not edit other memory, run an agent, or silently promote anything else." in body
    assert "New status: verified." in body
    assert "Audit trail: bob via Hub View." in body
    assert "Review another item" in body
    assert 'href="/projects/central-agent-data-hub">Open project</a>' in body


def test_inbox_page_renders_german_reject_result_card() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": [],
                "csrf_token": "token",
                "enabled": True,
                "message": None,
                "error": None,
                "review_result": {
                    "result": "rejected",
                    "item_id": str(DRAFT_ID),
                    "type": "fact",
                    "type_label": "Fact",
                    "status": "archived",
                    "project": "central-agent-data-hub",
                    "reviewed_by": "bob",
                    "review_source": "hub_view",
                },
            },
        },
        200,
        view_name="inbox",
        language="de",
        current_path="/inbox",
        query_string="lang=de",
    ).decode("utf-8")

    assert "Prüfergebnis" in body
    assert "Vorschlag verworfen" in body
    assert "Dieser Eintrag vom Typ Fakt wurde archiviert" in body
    assert "Was sich geändert hat" in body
    assert "Was nicht passiert ist" in body
    assert "ADH hat kein anderes Gedächtnis geändert" in body
    assert "Neuer Status: archiviert." in body
    assert "Prüfspur: bob über Hub View." in body
    assert "Weiteren Eintrag prüfen" in body
    assert 'href="/projects/central-agent-data-hub?lang=de">Projekt öffnen</a>' in body


def test_review_activity_cards_summarize_audit_rows() -> None:
    cards = hub_view.review_activity_cards([review_action_row(action="inbox_reject")])

    assert cards == [
        {
            "decision": "rejected",
            "decision_key": "review_activity_rejected",
            "type": "fact",
            "type_label": "Fact",
            "project": "central-agent-data-hub",
            "project_name": "Central Agent Data Hub",
            "reviewed_by": "bob",
            "review_source": "Hub View",
            "status": "archived",
            "updated_at": "2026-06-10 11:15 UTC",
        }
    ]


def test_inbox_page_renders_german_recent_review_activity() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": [],
                "csrf_token": "token",
                "enabled": True,
                "message": None,
                "error": None,
                "recent_reviews": hub_view.review_activity_cards([review_action_row()]),
                "review_activity_url": "/inbox/activity",
            },
        },
        200,
        view_name="inbox",
        language="de",
        current_path="/inbox",
        query_string="lang=de",
    ).decode("utf-8")

    assert "Zuletzt geprüft" in body
    assert "Letzte menschliche Prüfentscheidungen aus der lokalen Prüfspur." in body
    assert "Gesamten Prüfverlauf öffnen" in body
    assert 'href="/inbox/activity?lang=de"' in body
    assert "Gemerkt · Fakt" in body
    assert "Central Agent Data Hub" in body
    assert "Status: geprüft." in body
    assert "Von bob." in body
    assert "Über Hub View." in body


def test_review_activity_page_renders_read_only_history() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": [],
                "recent_reviews": hub_view.review_activity_cards(
                    [review_action_row(action="inbox_reject")]
                ),
                "review_activity_url": None,
            },
            "draft_total": 0,
        },
        200,
        view_name="review_activity",
        language="de",
        current_path="/inbox/activity",
        query_string="lang=de",
    ).decode("utf-8")

    assert "Prüfverlauf" in body
    assert "Diese reine Leseansicht zeigt letzte menschliche Entscheidungen" in body
    assert 'href="/inbox?lang=de">Zurück zum Prüfungseingang</a>' in body
    assert "Verworfen · Fakt" in body
    assert "Status: archiviert." in body
    assert "Gesamten Prüfverlauf öffnen" not in body


def test_review_activity_page_empty_state() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": [],
                "recent_reviews": [],
                "review_activity_url": None,
            },
            "draft_total": 0,
        },
        200,
        view_name="review_activity",
    ).decode("utf-8")

    assert "Review history" in body
    assert "No review history yet." in body
    assert "Once a human accepts or rejects" in body
    assert 'href="/inbox">Back to Review Inbox</a>' in body


def test_inbox_page_renders_german_queue_language() -> None:
    groups = hub_view.group_draft_cards([draft_row()])
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": groups,
                "csrf_token": "token",
                "enabled": True,
                "review_enabled": True,
                "reviewer": "alice",
                "reviewer_error": None,
                "message": None,
                "error": None,
            },
            "draft_total": 1,
        },
        200,
        view_name="inbox",
        language="de",
        current_path="/inbox",
        query_string="lang=de",
    ).decode("utf-8")

    assert "Prüf-Warteschlange" in body
    assert "Prüfe jeweils eine vorgeschlagene Änderung." in body
    assert "Nächster Schritt" in body
    assert "Öffne eine Karte, prüfe Satz und Quelle" in body
    assert "Nichts hier wird zu geprüftem Projektgedächtnis" in body
    assert "So prüfst du" in body
    assert "Soll ein Agent sich später darauf verlassen?" in body
    assert "Ist die Herkunft konkret genug" in body
    assert "Merken übernimmt es ins geprüfte Projektgedächtnis." in body
    assert "Prüf-Warteschlange filtern" in body
    assert "Projekt, Fakt, Quelle, Zuständig..." in body
    assert "Sichtbare Prüfeinträge: 1." in body
    assert "Kein Prüfeintrag passt zu diesem Filter." in body
    assert "Vorgeschlagene Änderung · Fakt" in body
    assert "Projekt-Warteschlange" in body
    assert "Zuständig: alice" in body
    assert "Warum diese Karte hier ist" in body
    assert "Als geprüftes Projektgedächtnis speichern" in body
    assert "Archivieren, ohne zu übernehmen" in body
    assert "Merken" in body
    assert "Verwerfen" in body


def test_inbox_accept_promotes_and_audits(monkeypatch) -> None:
    row = draft_row()
    cur = ReviewCursor(row)
    audit_calls = []
    monkeypatch.setattr(hub_view, "connect", lambda: ReviewConnection(cur))
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )
    captured, _body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
        origin="http://127.0.0.1:8765",
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "review_result=accepted" in headers["Location"]
    assert "review_type=fact" in headers["Location"]
    assert "review_status=verified" in headers["Location"]
    assert "reviewed_by=bob" in headers["Location"]
    assert "review_source=hub_view" in headers["Location"]
    assert headers["Location"].endswith("#review-result")
    assert row["status"] == "verified"
    assert cur.update_count == 1
    assert audit_calls[0][2] == "inbox_accept"
    assert audit_calls[0][5]["review_source"] == "hub_view"
    assert audit_calls[0][5]["reviewed_by"] == "bob"
    assert audit_calls[0][5]["responsible_reviewer"] == "alice"
    assert audit_calls[0][7]["review_source"] == "hub_view"
    assert audit_calls[0][7]["reviewed_by"] == "bob"


def test_inbox_reject_archives_and_audits(monkeypatch) -> None:
    row = draft_row()
    cur = ReviewCursor(row)
    audit_calls = []
    monkeypatch.setattr(hub_view, "connect", lambda: ReviewConnection(cur))
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )
    captured, _body = call_app(
        app,
        method="POST",
        path="/inbox/reject",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "review_result=rejected" in headers["Location"]
    assert "review_type=fact" in headers["Location"]
    assert "review_status=archived" in headers["Location"]
    assert "reviewed_by=bob" in headers["Location"]
    assert "review_source=hub_view" in headers["Location"]
    assert headers["Location"].endswith("#review-result")
    assert row["status"] == "archived"
    assert cur.update_count == 1
    assert audit_calls[0][2] == "inbox_reject"
    assert audit_calls[0][5]["review_source"] == "hub_view"
    assert audit_calls[0][5]["reviewed_by"] == "bob"
    assert audit_calls[0][7]["review_source"] == "hub_view"
    assert audit_calls[0][7]["reviewed_by"] == "bob"


def test_inbox_post_without_or_wrong_csrf_is_forbidden_without_write(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("CSRF failure must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )

    for form in (
        {"draft_id": str(DRAFT_ID), "type": "fact"},
        {"csrf_token": "wrong", "draft_id": str(DRAFT_ID), "type": "fact"},
    ):
        captured, body = call_app(
            app,
            method="POST",
            path="/inbox/accept",
            form=form,
        )

        assert captured["status"] == "403 Forbidden"
        assert "Review token is missing or invalid." in body


def test_inbox_post_with_bad_origin_is_forbidden_without_write(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("bad origin must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )

    captured, body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
        origin="https://example.com",
    )

    assert captured["status"] == "403 Forbidden"
    assert "Origin is not allowed" in body


def test_inbox_post_on_non_draft_shows_error_without_write(monkeypatch) -> None:
    row = draft_row(status="verified")
    cur = ReviewCursor(row)
    audit_calls = []
    monkeypatch.setattr(hub_view, "connect", lambda: ReviewConnection(cur))
    monkeypatch.setattr(inbox, "ensure_agent", lambda *_args: {"id": "agent-id"})
    monkeypatch.setattr(inbox, "log_agent_action", lambda *args: audit_calls.append(args))

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_handle="bob",
    )
    captured, _body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "This%20draft%20is%20no%20longer%20open" in headers["Location"]
    assert row["status"] == "verified"
    assert cur.update_count == 0
    assert audit_calls == []


class EmptyCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args):
        raise AssertionError("test should patch fetch_project instead of querying")


class EmptyConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return EmptyCursor()


def test_codex_setup_post_installs_agents_block_with_explicit_click(monkeypatch, tmp_path) -> None:
    project = {
        "id": "project-id",
        "slug": "central-agent-data-hub-demo",
        "name": "Central Agent Data Hub Demo",
        "status": "active",
        "metadata": {"local_path": str(tmp_path)},
    }
    monkeypatch.setattr(hub_view, "connect", lambda: EmptyConnection())
    monkeypatch.setattr(hub_view, "fetch_project", lambda _cur, slug: project if slug == project["slug"] else None)

    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")
    captured, _body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "token", "task": "Review demo"},
        origin="http://127.0.0.1:8765",
    )

    headers = dict(captured["headers"])
    target = tmp_path / "AGENTS.md"
    assert captured["status"] == "303 See Other"
    assert "setup_message=Codex%20setup%20installed%20in%20AGENTS.md" in headers["Location"]
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "<!-- CENTRAL-AGENT-DATA-HUB:START -->" in text
    assert "Project slug: `central-agent-data-hub-demo`" in text
    assert "agent_start.sh --project central-agent-data-hub-demo" in text


def test_codex_setup_post_without_csrf_is_forbidden_without_write(monkeypatch, tmp_path) -> None:
    def fail_connect():
        raise AssertionError("CSRF failure must not touch project lookup or files")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")
    captured, body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "wrong", "task": "Review demo"},
    )

    assert captured["status"] == "403 Forbidden"
    assert "Setup token is missing or invalid." in body
    assert not (tmp_path / "AGENTS.md").exists()


def test_codex_setup_post_on_non_loopback_is_forbidden_without_write(monkeypatch, tmp_path) -> None:
    def fail_connect():
        raise AssertionError("non-loopback setup must not touch project lookup or files")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(bind_host="0.0.0.0", csrf_token="token")
    captured, body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "token", "task": "Review demo"},
    )

    assert captured["status"] == "403 Forbidden"
    assert "only available on loopback" in body
    assert not (tmp_path / "AGENTS.md").exists()


def test_codex_setup_post_with_unknown_project_path_redirects_without_write(monkeypatch, tmp_path) -> None:
    project = {
        "id": "project-id",
        "slug": "central-agent-data-hub-demo",
        "name": "Central Agent Data Hub Demo",
        "status": "active",
        "metadata": {},
    }
    monkeypatch.setenv("AGENT_HUB_PUBLIC_DEMO", "1")
    monkeypatch.setattr(hub_view, "connect", lambda: EmptyConnection())
    monkeypatch.setattr(hub_view, "fetch_project", lambda _cur, _slug: project)

    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")
    captured, _body = call_app(
        app,
        method="POST",
        path="/projects/central-agent-data-hub-demo/codex-setup",
        form={"csrf_token": "token", "task": "Review demo"},
    )

    headers = dict(captured["headers"])
    assert captured["status"] == "303 See Other"
    assert "setup_error=Codex%20setup%20needs%20a%20registered%20project%20folder" in headers["Location"]
    assert not (tmp_path / "AGENTS.md").exists()


def test_hub_view_without_reviewer_disables_buttons_and_blocks_post(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("missing reviewer POST must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    groups = hub_view.group_draft_cards([draft_row()])
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": groups,
                "csrf_token": "token",
                "enabled": True,
                "review_enabled": False,
                "reviewer": None,
                "reviewer_error": "reviewer handle is required; set HUB_VIEW_REVIEWER",
                "message": None,
                "error": None,
            },
        },
        200,
        view_name="inbox",
    ).decode("utf-8")

    app = hub_view.create_application(
        bind_host="127.0.0.1",
        csrf_token="token",
        reviewer_error="reviewer handle is required; set HUB_VIEW_REVIEWER",
    )
    captured, post_body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    assert "Set HUB_VIEW_REVIEWER or start Hub View with --reviewer" in body
    assert "Reviewer required" in body
    assert "disabled>Accept</button>" in body
    assert captured["status"] == "403 Forbidden"
    assert "HUB_VIEW_REVIEWER" in post_body


def test_inbox_get_paths_do_not_write(monkeypatch) -> None:
    class ReadOnlyCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_params) -> None:
            if re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql.upper()):
                raise AssertionError("GET /inbox must stay read-only")

        def fetchall(self):
            return []

    class ReadOnlyConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return ReadOnlyCursor()

    monkeypatch.setattr(hub_view, "connect", lambda: ReadOnlyConnection())
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")

    captured, body = call_app(app, method="GET", path="/inbox")

    assert captured["status"] == "200 OK"
    assert "No items to review." in body


def test_review_activity_get_path_does_not_write(monkeypatch) -> None:
    class ReadOnlyCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, *_params) -> None:
            if re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql.upper()):
                raise AssertionError("GET /inbox/activity must stay read-only")

        def fetchall(self):
            return []

    class ReadOnlyConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return ReadOnlyCursor()

    monkeypatch.setattr(hub_view, "connect", lambda: ReadOnlyConnection())
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")

    captured, body = call_app(app, method="GET", path="/inbox/activity")

    assert captured["status"] == "200 OK"
    assert "Review history" in body
    assert "No review history yet." in body


def test_inbox_action_get_path_does_not_touch_database(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("GET action path must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")

    captured, body = call_app(app, method="GET", path="/inbox/accept")

    assert captured["status"] == "404 Not Found"
    assert body == "Not Found"


def test_non_loopback_bind_disables_inbox_actions(monkeypatch) -> None:
    def fail_connect():
        raise AssertionError("disabled POST must not touch the database")

    monkeypatch.setattr(hub_view, "connect", fail_connect)
    groups = hub_view.group_draft_cards([draft_row()])
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
            "inbox": {
                "groups": groups,
                "csrf_token": "token",
                "enabled": False,
                "message": None,
                "error": None,
            },
        },
        200,
        view_name="inbox",
        inbox_enabled=False,
    ).decode("utf-8")
    app = hub_view.create_application(bind_host="0.0.0.0", csrf_token="token")
    captured, _post_body = call_app(
        app,
        method="POST",
        path="/inbox/accept",
        form={"csrf_token": "token", "draft_id": str(DRAFT_ID), "type": "fact"},
    )

    assert 'action="/inbox/accept"' not in body
    assert "disabled>Accept</button>" in body
    assert "Review actions are disabled" in body
    assert captured["status"] == "403 Forbidden"


def test_lan_read_bind_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="--allow-lan-read"):
        hub_view.validate_lan_read_bind("0.0.0.0", allow_lan_read=False)


def test_lan_read_bind_allows_loopback_without_opt_in() -> None:
    assert hub_view.validate_lan_read_bind(
        "127.0.0.1",
        allow_lan_read=False,
    ) is None


def test_lan_read_bind_returns_warning_when_explicitly_allowed() -> None:
    warning = hub_view.validate_lan_read_bind("0.0.0.0", allow_lan_read=True)

    assert warning is not None
    assert "exposes reviewed memory read-only on the local network" in warning
    assert "writes stay disabled unless Hub View is bound to loopback" in warning


def test_hub_view_parser_accepts_explicit_reviewer() -> None:
    args = hub_view.build_parser().parse_args(["--reviewer", "demo-reviewer"])

    assert args.reviewer == "demo-reviewer"


def test_application_renders_project_detail(monkeypatch) -> None:
    def fake_load_view_model(
        selected_slug: str | None,
    ) -> tuple[int, dict[str, object]]:
        assert selected_slug == "central-agent-data-hub"
        return 200, {
            "projects": [
                {
                    "name": "Central Agent Data Hub",
                    "slug": "central-agent-data-hub",
                    "status": "active",
                    "description": "Shared memory.",
                    "project_type": "ops",
                    "counts": {
                        "facts": 3,
                        "decisions": 1,
                        "risks": 1,
                        "open_questions": 0,
                        "reports": 1,
                    },
                    "latest_report_title": "Daily",
                    "latest_report_summary": "summary",
                    "updated_at": "2026-06-05 08:00 UTC",
                    "draft_count": 2,
                }
            ],
            "selected_project": {
                "name": "Central Agent Data Hub",
                "slug": "central-agent-data-hub",
                "description": "Shared memory.",
                "status": "active",
                "project_type": "ops",
                "updated_at": "2026-06-05 08:00 UTC",
                "draft_count": 2,
                "counts": {
                    "facts": 3,
                    "decisions": 1,
                    "risks": 1,
                    "open_questions": 0,
                    "reports": 1,
                },
                "quality": {
                    "score": 92,
                    "status": "healthy",
                    "relation_count": 3,
                    "relation_coverage": "0.60",
                    "gaps": [("facts without source", 0)],
                    "check_cards": [
                        {
                            "count": 0,
                            "state": "ok",
                            "title_key": "quality_facts_without_source",
                            "meaning_key": "quality_facts_without_source_meaning",
                            "action_key": "quality_facts_without_source_action",
                        },
                        {
                            "count": 1,
                            "state": "needs-review",
                            "title_key": "quality_open_questions",
                            "meaning_key": "quality_open_questions_meaning",
                            "action_key": "quality_open_questions_action",
                        },
                    ],
                },
                "work_state": [
                    {
                        "kind": "latest",
                        "priority": "1",
                        "label_key": "work_state_latest_label",
                        "href": "#latest-status",
                        "report_count": 1,
                        "title": "Daily report",
                        "title_key": None,
                        "body": "A compact review.",
                        "body_key": None,
                        "action_key": "work_state_latest_action",
                        "state": "ready",
                    },
                    {
                        "kind": "attention",
                        "priority": "2",
                        "label_key": "work_state_attention_label",
                        "href": "#risks-and-questions",
                        "risk_count": 1,
                        "question_count": 0,
                        "title": "Skipped preflight",
                        "title_key": None,
                        "body": None,
                        "body_key": "work_state_attention_body",
                        "action_key": "work_state_attention_action",
                        "state": "needs-review",
                    },
                    {
                        "kind": "review",
                        "priority": "3",
                        "label_key": "work_state_review_label",
                        "href": "/inbox",
                        "review_count": 2,
                        "title": None,
                        "title_key": "work_state_review_waiting",
                        "body": None,
                        "body_key": "work_state_review_body",
                        "action_key": "work_state_review_action",
                        "state": "needs-review",
                    },
                    {
                        "kind": "quality",
                        "priority": "4",
                        "label_key": "work_state_quality_label",
                        "href": "#quality",
                        "quality_score": 92,
                        "title": None,
                        "title_key": "quality_open_questions",
                        "body": None,
                        "body_key": "quality_open_questions_meaning",
                        "action_key": "work_state_quality_action",
                        "state": "needs-review",
                    },
                ],
                "decisions": [
                    {
                        "id": "10000000-0000-4000-8000-000000000401",
                        "decision": "Treat the Hub as verified context.",
                        "rationale": "Shared trust.",
                        "detail_url": (
                            "/projects/central-agent-data-hub/memory/decision/"
                            "10000000-0000-4000-8000-000000000401"
                        ),
                    }
                ],
                "facts": [
                    {
                        "id": "10000000-0000-4000-8000-000000000201",
                        "statement": "Reviewed facts are visible in Hub View.",
                        "source": "demo",
                        "confidence": 0.9,
                        "detail_url": (
                            "/projects/central-agent-data-hub/memory/fact/"
                            "10000000-0000-4000-8000-000000000201"
                        ),
                    }
                ],
                "risks": [
                    {
                        "id": "10000000-0000-4000-8000-000000000501",
                        "title": "Skipped preflight",
                        "severity": "medium",
                        "impact": "stale context",
                        "detail_url": (
                            "/projects/central-agent-data-hub/memory/risk/"
                            "10000000-0000-4000-8000-000000000501"
                        ),
                    }
                ],
                "open_questions": [],
                "reports": [
                    {
                        "id": "10000000-0000-4000-8000-000000000601",
                        "title": "Daily report",
                        "summary": "A compact review.",
                        "detail_url": (
                            "/projects/central-agent-data-hub/memory/report/"
                            "10000000-0000-4000-8000-000000000601"
                        ),
                    }
                ],
                "relations": [{"source": "Fact A", "relation_type": "supports", "target": "Decision B"}],
            },
            "not_found_slug": None,
            "draft_total": 2,
        }

    monkeypatch.setattr(hub_view, "load_view_model", fake_load_view_model)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        hub_view.application(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/projects/central-agent-data-hub"},
            start_response,
        )
    ).decode("utf-8")

    assert captured["status"] == "200 OK"
    assert "Central Agent Data Hub" in body
    assert 'href="#main-content"' in body
    assert 'id="main-content" tabindex="-1"' in body
    assert "Skip to main content" in body
    assert "Selected" in body
    assert "2 review items" in body
    assert 'aria-label="App navigation"' in body
    assert 'href="/projects/central-agent-data-hub" aria-current="page"' in body
    assert "Work state" in body
    assert "Memory" in body
    assert "Agent handoff" in body
    assert 'href="/projects/central-agent-data-hub#current-state-title"' in body
    assert 'href="/projects/central-agent-data-hub#project-memory"' in body
    assert 'href="/projects/central-agent-data-hub#connect-agent"' in body
    assert 'aria-label="Workspace areas"' in body
    assert 'class="action-strip area-map"' in body
    assert "Project workspace" in body
    assert "Use these areas like a local app" in body
    assert "Recommended next" in body
    assert "Current work state" in body
    assert "Read this first. It shows the latest report" in body
    assert "Step 1" in body
    assert "Reports: 1" in body
    assert "Open latest status" in body
    assert "Needs attention" in body
    assert "Risks: 1 · Questions: 0" in body
    assert "Skipped preflight" in body
    assert "Review queue" in body
    assert "Review items: 2" in body
    assert "Suggested changes are waiting for a human decision." in body
    assert "Open Review Inbox" in body
    assert "Quality signals" in body
    assert "Quality score: 92" in body
    assert "Quality snapshot" in body
    assert "Quality score" in body
    assert "These are review signals" in body
    assert "Facts without source" in body
    assert "Open questions" in body
    assert "These are reviewed uncertainties" in body
    assert "Next: answer, keep, or convert them into decisions when ready." in body
    assert "Use ADH with an agent" in body
    assert "Prepare reviewed context before a chatbot or local agent starts work." in body
    assert "Review suggested changes" in body
    assert "2 items wait for a human decision across projects." in body
    assert "Find reviewed memory" in body
    assert "Search facts, decisions, risks, questions, reports, and relations already on this page." in body
    assert "Check memory quality" in body
    assert body.index("Project workspace") < body.index("Current work state")
    assert 'href="#connect-agent"' in body
    assert 'href="#memory-explorer"' in body
    assert 'href="#current-state-title"' in body
    assert 'id="project-memory"' in body
    assert "Project memory" in body
    assert "Search and inspect the reviewed context this project can hand to a chatbot or local agent." in body
    assert 'aria-label="Project memory types"' in body
    assert 'class="memory-kind-grid"' in body
    assert "Rules for work" in body
    assert "Choices that constrain future agent work." in body
    assert "Known facts" in body
    assert "Checked assumptions the agent may rely on." in body
    assert "Work state" in body
    assert "Compact snapshots of the latest project state." in body
    assert "Watch points" in body
    assert "Things the agent must not guess away." in body
    assert "Still unclear" in body
    assert "Reviewed uncertainties that should stay visible." in body
    assert "Agent handoff and review" in body
    assert "Prepare context for a chatbot or local agent, then handle suggested memory changes separately." in body
    assert "Memory details" in body
    assert "Start with latest status, then check risks and questions" in body
    assert "Use these entries as the verified base." in body
    assert "Read the newest report first." in body
    assert "Check whether an active risk or open question" in body
    assert "Fix or consciously accept the visible signals" in body
    assert body.index('id="latest-status"') < body.index('id="risks-and-questions"')
    assert body.index('id="risks-and-questions"') < body.index('id="reviewed-memory"')
    assert body.index('id="reviewed-memory"') < body.index('id="quality"')
    assert 'href="#reviewed-memory"' in body
    assert 'href="#risks-and-questions"' in body
    assert 'href="#latest-status"' in body
    assert 'href="#quality"' in body
    assert 'id="reviewed-memory"' in body
    assert 'id="memory-explorer"' in body
    assert 'id="risks-and-questions"' in body
    assert 'id="latest-status"' in body
    assert 'id="quality"' in body
    assert 'id="relations"' in body
    assert 'data-memory-explorer' in body
    assert 'data-memory-filter' in body
    assert 'data-memory-clear' in body
    assert 'data-memory-results' in body
    assert 'data-memory-hits' in body
    assert 'data-memory-empty' in body
    assert 'enterkeyhint="done"' in body
    assert "Search this page" in body
    assert "Matches appear below while the page sections are filtered." in body
    assert "Showing visible reviewed memory on this page." in body
    assert "No visible memory matches this search." in body
    assert "itemHaystack" in body
    assert "reviewSearchAliases" in body
    assert 'risiko: ["risk", "risks", "risiken"]' in body
    assert 'arbeitsstand: ["status", "latest status", "report", "bericht"]' in body
    assert "searchTerms(query)" in body
    assert 'getAttribute("data-memory-type")' in body
    assert "memory-filter-hit" in body
    assert 'event.key === "Enter"' in body
    assert "filter.blur()" in body
    assert 'data-memory-type="decision"' in body
    assert 'data-memory-type="fact"' in body
    assert 'data-memory-type="risk"' in body
    assert 'data-memory-type="report"' in body
    assert 'data-memory-type="latest status"' in body
    assert 'data-memory-type="relation"' in body
    assert 'data-memory-label="Decisions"' in body
    assert 'data-memory-label="Risks"' in body
    assert 'getAttribute("data-memory-label")' in body
    assert "Connect an agent" in body
    assert 'action="/projects/central-agent-data-hub/agent-context"' in body
    assert "Prepare agent handoff" in body
    assert "The next screen shows what ADH would give the agent" in body
    assert "Task for the agent" in body
    assert "primary-button" in body
    assert "Latest status" in body
    assert "Review suggested changes" in body
    assert "suggested memory changes" in body
    assert "Drafts are proposed memory changes across projects. They are not reviewed memory until accepted." in body
    assert 'href="/inbox"' in body
    assert "Treat the Hub as verified context." in body
    assert "Reviewed facts are visible in Hub View." in body
    assert "Open detail" in body
    assert 'href="/projects/central-agent-data-hub/memory/fact/10000000-0000-4000-8000-000000000201"' in body
    assert 'href="/projects/central-agent-data-hub/memory/risk/10000000-0000-4000-8000-000000000501"' in body
    assert "Fact A" in body
    assert "supports" in body
    assert "alexander" not in body.lower()
    assert "ronak" not in body.lower()


def test_project_detail_can_render_german_chrome_without_translating_memory() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": {
                "name": "Central Agent Data Hub Demo",
                "slug": "central-agent-data-hub-demo",
                "description": (
                    "Neutral demo project for showing how reviewed context is "
                    "stored and read locally."
                ),
                "status": "active",
                "project_type": "demo",
                "updated_at": "2026-06-05 08:00 UTC",
                "counts": {
                    "facts": 1,
                    "decisions": 0,
                    "risks": 1,
                    "open_questions": 0,
                    "reports": 0,
                },
                "quality": {
                    "score": 80,
                    "status": "ok",
                    "relation_count": 0,
                    "relation_coverage": "0.00",
                    "gaps": [],
                    "check_cards": [
                        {
                            "count": 1,
                            "state": "needs-review",
                            "title_key": "quality_risks_without_mitigation",
                            "meaning_key": "quality_risks_without_mitigation_meaning",
                            "action_key": "quality_risks_without_mitigation_action",
                        }
                    ],
                },
                "work_state": [
                    {
                        "kind": "latest",
                        "priority": "1",
                        "label_key": "work_state_latest_label",
                        "href": "#latest-status",
                        "report_count": 0,
                        "title": None,
                        "title_key": "latest_status_empty",
                        "body": None,
                        "body_key": "work_state_latest_empty",
                        "action_key": "work_state_latest_action",
                        "state": "quiet",
                    },
                    {
                        "kind": "attention",
                        "priority": "2",
                        "label_key": "work_state_attention_label",
                        "href": "#risks-and-questions",
                        "risk_count": 1,
                        "question_count": 0,
                        "title": "Demo risk stays in the original stored language.",
                        "title_key": None,
                        "body": None,
                        "body_key": "work_state_attention_body",
                        "action_key": "work_state_attention_action",
                        "state": "needs-review",
                    },
                    {
                        "kind": "review",
                        "priority": "3",
                        "label_key": "work_state_review_label",
                        "href": "/inbox",
                        "review_count": 0,
                        "title": None,
                        "title_key": "work_state_review_empty",
                        "body": None,
                        "body_key": "work_state_review_body",
                        "action_key": "work_state_review_action",
                        "state": "quiet",
                    },
                    {
                        "kind": "quality",
                        "priority": "4",
                        "label_key": "work_state_quality_label",
                        "href": "#quality",
                        "quality_score": 80,
                        "title": None,
                        "title_key": "quality_risks_without_mitigation",
                        "body": None,
                        "body_key": "quality_risks_without_mitigation_meaning",
                        "action_key": "work_state_quality_action",
                        "state": "needs-review",
                    },
                ],
                "decisions": [],
                "facts": [
                    {
                        "id": "10000000-0000-4000-8000-000000000201",
                        "statement": "Reviewed facts are visible in Hub View.",
                        "source": "demo",
                        "confidence": 0.9,
                        "detail_url": (
                            "/projects/central-agent-data-hub-demo/memory/fact/"
                            "10000000-0000-4000-8000-000000000201"
                        ),
                    }
                ],
                "risks": [
                    {
                        "id": "10000000-0000-4000-8000-000000000501",
                        "title": "Demo risk stays in the original stored language.",
                        "severity": "low",
                        "impact": "test",
                        "detail_url": (
                            "/projects/central-agent-data-hub-demo/memory/risk/"
                            "10000000-0000-4000-8000-000000000501"
                        ),
                    }
                ],
                "open_questions": [],
                "reports": [],
                "relations": [],
            },
            "not_found_slug": None,
            "draft_total": 0,
        },
        200,
        language="de",
        current_path="/projects/central-agent-data-hub-demo",
        query_string="lang=de",
    ).decode("utf-8")

    assert '<html lang="de">' in body
    assert "Zum Hauptinhalt springen" in body
    assert "Geprüftes Projektgedächtnis finden" in body
    assert "Neutrales Demo-Projekt: Es zeigt, wie geprüfter Kontext lokal" in body
    assert "Neutral demo project for showing" not in body
    assert 'aria-label="App-Navigation"' in body
    assert "Arbeitsstand" in body
    assert "Gedächtnis" in body
    assert "Agentenübergabe" in body
    assert 'href="/projects/central-agent-data-hub-demo?lang=de#current-state-title"' in body
    assert 'href="/projects/central-agent-data-hub-demo?lang=de#project-memory"' in body
    assert 'href="/projects/central-agent-data-hub-demo?lang=de#connect-agent"' in body
    assert "Diese Seite durchsuchen" in body
    assert "Projekt-Arbeitsfläche" in body
    assert "Nutze diese Bereiche wie eine lokale App" in body
    assert "Projektgedächtnis" in body
    assert "Durchsuche und prüfe den bestätigten Kontext" in body
    assert "Arten von Projektgedächtnis" in body
    assert "Vorgaben für Arbeit" in body
    assert "Festlegungen, die spätere Agentenarbeit begrenzen." in body
    assert "Bekannte Fakten" in body
    assert "Geprüfte Annahmen, auf die sich der Agent stützen darf." in body
    assert "Im Blick behalten" in body
    assert "Punkte, die der Agent nicht wegvermuten darf." in body
    assert "Noch unklar" in body
    assert "Geprüfte Unsicherheiten, die sichtbar bleiben sollen." in body
    assert "Agentenübergabe und Prüfung" in body
    assert "Detailansicht" in body
    assert "Beginne mit dem letzten Stand, prüfe dann Risiken und Fragen" in body
    assert "Nutze diese Einträge als geprüfte Grundlage." in body
    assert "Lies zuerst den neuesten Bericht." in body
    assert "Prüfe, ob ein aktives Risiko oder eine offene Frage" in body
    assert "Behebe oder akzeptiere die sichtbaren Signale bewusst" in body
    assert body.index('id="latest-status"') < body.index('id="risks-and-questions"')
    assert body.index('id="risks-and-questions"') < body.index('id="reviewed-memory"')
    assert body.index('id="reviewed-memory"') < body.index('id="quality"')
    assert "Empfohlen" in body
    assert "Aktueller Arbeitsstand" in body
    assert "Lies das zuerst. Hier siehst du letzten Bericht" in body
    assert "Schritt 1" in body
    assert "Berichte: 0" in body
    assert "Für dieses Projekt ist noch kein Bericht erfasst." in body
    assert "Letzten Stand öffnen" in body
    assert "Braucht Aufmerksamkeit" in body
    assert "Risiken: 1 · Fragen: 0" in body
    assert "Risiken und Fragen öffnen" in body
    assert "Prüf-Warteschlange" in body
    assert "Prüfeinträge: 0" in body
    assert "Keine vorgeschlagenen Änderungen warten." in body
    assert "Qualitätswert" in body
    assert "Qualitätswert: 80" in body
    assert "Qualitätssignale öffnen" in body
    assert "Das sind Prüfsignale" in body
    assert "Risiken ohne Gegenmaßnahme" in body
    assert "Nächster Schritt: Auswirkung und Gegenmaßnahme ergänzen" in body
    assert "Agent verbinden" in body
    assert "Dieses Projekt mit ADH-Kontext prüfen" in body
    assert "Arbeitsstand" in body
    assert "Reviewed facts are visible in Hub View." in body
    assert "Demo risk stays in the original stored language." in body
    assert "Detail öffnen" in body
    assert 'href="/projects/central-agent-data-hub-demo/memory/fact/10000000-0000-4000-8000-000000000201?lang=de"' in body
    assert 'href="/inbox?lang=de"' in body
    assert 'action="/projects/central-agent-data-hub-demo/agent-context"' in body
    assert 'name="lang" value="de"' in body
    assert '<form method="get" action="/projects/central-agent-data-hub-demo">' in body
    assert '<button type="submit" aria-current="true">Deutsch</button>' in body


def test_memory_item_page_renders_read_only_german_detail() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": {
                "name": "Central Agent Data Hub Demo",
                "slug": "central-agent-data-hub-demo",
            },
            "memory_item": {
                "id": "10000000-0000-4000-8000-000000000201",
                "item_type": "fact",
                "type_label_key": "agent_status_facts",
                "title": "Reviewed facts are visible in Hub View.",
                "back_url": (
                    "/projects/central-agent-data-hub-demo#reviewed-memory"
                ),
                "fields": [
                    {"label_key": "memory_item_source", "value": "demo"},
                    {"label_key": "memory_item_status", "value": "verified"},
                    {"label_key": "memory_item_updated", "value": "2026-06-05 08:00 UTC"},
                ],
                "relations": [
                    {
                        "id": "10000000-0000-4000-8000-000000000701",
                        "direction": "out",
                        "direction_key": "memory_relation_outgoing",
                        "relation_label_key": "relation_supports",
                        "other_label_key": "agent_status_decisions",
                        "other_summary": "Use reviewed memory as task constraints.",
                        "other_url": (
                            "/projects/central-agent-data-hub-demo/memory/decision/"
                            "10000000-0000-4000-8000-000000000401"
                        ),
                    }
                ],
            },
            "not_found_slug": None,
            "draft_total": 0,
        },
        200,
        view_name="memory_item",
        language="de",
        current_path="/projects/central-agent-data-hub-demo/memory/fact/10000000-0000-4000-8000-000000000201",
        query_string="lang=de",
    ).decode("utf-8")

    assert '<html lang="de">' in body
    assert "Zurück zu Central Agent Data Hub Demo" in body
    assert "Fakten" in body
    assert "Reviewed facts are visible in Hub View." in body
    assert "Diese Seite liest nur den ausgewählten Eintrag" in body
    assert "Quelle" in body
    assert "demo" in body
    assert "Zusammenhänge" in body
    assert "Diese Verbindungen zeigen" in body
    assert "Von diesem Eintrag aus" in body
    assert "Dieser Eintrag" in body
    assert "stützt" in body
    assert "Entscheidungen: Use reviewed memory as task constraints." in body
    assert 'href="/projects/central-agent-data-hub-demo/memory/decision/10000000-0000-4000-8000-000000000401?lang=de"' in body
    assert "Status" in body
    assert "geprüft" in body
    assert "Aktualisiert" in body
    assert 'href="/projects/central-agent-data-hub-demo?lang=de#reviewed-memory"' in body


def test_memory_item_route_renders_read_only_detail(monkeypatch) -> None:
    def fake_load_memory_item_view_model(
        selected_slug: str,
        item_type: str,
        item_id: str,
    ) -> tuple[int, dict[str, object]]:
        assert selected_slug == "central-agent-data-hub-demo"
        assert item_type == "fact"
        assert item_id == "10000000-0000-4000-8000-000000000201"
        return 200, {
            "projects": [],
            "selected_project": {
                "name": "Central Agent Data Hub Demo",
                "slug": "central-agent-data-hub-demo",
            },
            "memory_item": {
                "id": item_id,
                "item_type": "fact",
                "type_label_key": "agent_status_facts",
                "title": "Reviewed facts are visible in Hub View.",
                "back_url": "/projects/central-agent-data-hub-demo#reviewed-memory",
                "fields": [{"label_key": "memory_item_status", "value": "verified"}],
                "relations": [],
            },
            "not_found_slug": None,
            "draft_total": 0,
        }

    monkeypatch.setattr(
        hub_view,
        "load_memory_item_view_model",
        fake_load_memory_item_view_model,
    )
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")
    captured, body = call_app(
        app,
        path=(
            "/projects/central-agent-data-hub-demo/memory/fact/"
            "10000000-0000-4000-8000-000000000201"
        ),
    )

    assert captured["status"] == "200 OK"
    assert "Reviewed facts are visible in Hub View." in body
    assert "This page only reads the selected project memory item" in body
    assert "Related memory" in body
    assert "No direct relation is visible for this item." in body


def test_build_memory_item_view_summarizes_incoming_and_outgoing_relations() -> None:
    row = {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000201"),
        "statement": "Reviewed facts are visible in Hub View.",
        "source": "demo",
        "confidence": 0.9,
        "status": "verified",
        "updated_at": datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
    }
    relations = [
        {
            "id": uuid.UUID("10000000-0000-4000-8000-000000000701"),
            "source_type": "fact",
            "source_id": row["id"],
            "source_summary": "Reviewed facts are visible in Hub View.",
            "relation_type": "supports",
            "target_type": "decision",
            "target_id": uuid.UUID("10000000-0000-4000-8000-000000000401"),
            "target_summary": "Treat the Hub as verified context.",
        },
        {
            "id": uuid.UUID("10000000-0000-4000-8000-000000000702"),
            "source_type": "document",
            "source_id": uuid.UUID("10000000-0000-4000-8000-000000000101"),
            "source_summary": "Concept: Reviewed Context",
            "relation_type": "references",
            "target_type": "fact",
            "target_id": row["id"],
            "target_summary": "Reviewed facts are visible in Hub View.",
        },
    ]

    view = hub_view_models.build_memory_item_view(
        "fact",
        row,
        project_slug="central-agent-data-hub-demo",
        relation_rows=relations,
    )

    assert view["relations"][0]["direction"] == "out"
    assert view["relations"][0]["relation_label_key"] == "relation_supports"
    assert view["relations"][0]["other_label_key"] == "agent_status_decisions"
    assert view["relations"][0]["other_url"] == (
        "/projects/central-agent-data-hub-demo/memory/decision/"
        "10000000-0000-4000-8000-000000000401"
    )
    assert view["relations"][1]["direction"] == "in"
    assert view["relations"][1]["relation_label_key"] == "relation_references"
    assert view["relations"][1]["other_label_key"] == "memory_relation_document"
    assert view["relations"][1]["other_url"] is None


def test_agent_context_route_renders_visible_context_handoff(monkeypatch) -> None:
    def fake_load_agent_context_view_model(
        selected_slug: str,
        task: str,
    ) -> tuple[int, dict[str, object]]:
        assert selected_slug == "central-agent-data-hub"
        assert task == "Review release readiness"
        return 200, {
            "projects": [],
            "selected_project": {
                "name": "Central Agent Data Hub",
                "slug": "central-agent-data-hub",
            },
            "not_found_slug": None,
            "draft_total": 0,
            "agent_context": {
                "project_slug": "central-agent-data-hub",
                "project_name": "Central Agent Data Hub",
                "task": task,
                "counts": {
                    "facts": 3,
                    "decisions": 2,
                    "risks": 1,
                    "open_questions": 1,
                    "reports": 1,
                    "relations": 2,
                    "pending_drafts": 0,
                },
                "source_count": 7,
                "gap_summary": {
                    "stale": 0,
                    "unanswered": 1,
                    "blind_spots": 0,
                    "pending_drafts": 0,
                },
                "influence": [
                    "Reviewed decisions become task constraints for the agent.",
                    "Verified facts may be used as project assumptions.",
                ],
                "commands": {
                    "prepare": (
                        "agent-hub prepare --project central-agent-data-hub "
                        "--task 'Review release readiness'"
                    ),
                    "agent_start": (
                        "scripts/agent_start.sh --project central-agent-data-hub "
                        "--query 'Review release readiness' --review"
                    ),
                },
                "local_agent": {
                    "setup_command": (
                        "python -m pip install -e '.[mcp]' && "
                        "claude mcp add agent-data-hub -- python -m agent_hub.cli mcp-serve"
                    ),
                    "codex": {
                        "can_install": True,
                        "project_path": "/demo/project",
                        "target_path": "/demo/project/AGENTS.md",
                        "target_file": "AGENTS.md",
                        "action": "create",
                        "preview": "<!-- CENTRAL-AGENT-DATA-HUB:START -->\nProject slug: `central-agent-data-hub`\n",
                        "error": None,
                        "verification": {
                            "state": "missing",
                            "label": "Codex setup not installed yet",
                            "detail": "Install the ADH block into AGENTS.md so Codex reads it before work.",
                        },
                    },
                    "codex_command": (
                        "scripts/install_repo_agent_memory.sh --repo /demo/project "
                        "--project central-agent-data-hub"
                    ),
                    "codex_project_path": "/demo/project",
                    "install_mcp": "pip install -e '.[mcp]'",
                    "claude_mcp": "claude mcp add agent-data-hub -- agent-hub mcp-serve",
                    "mcp_json": '{"mcpServers": {"agent-data-hub": {"command": "agent-hub"}}}',
                    "startup_instruction": (
                        "At the start of ADH-related work:\n"
                        "- request reviewed context from Agent Data Hub"
                    ),
                },
                "markdown": "# Agent Context Pack\n\n## Goal\nReview release readiness\n",
            },
        }

    monkeypatch.setattr(
        hub_view,
        "load_agent_context_view_model",
        fake_load_agent_context_view_model,
    )
    app = hub_view.create_application(bind_host="127.0.0.1", csrf_token="token")

    captured, body = call_app(
        app,
        path="/projects/central-agent-data-hub/agent-context",
        query=urlencode({"task": "Review release readiness"}),
    )

    assert captured["status"] == "200 OK"
    assert "ADH context loaded" in body
    assert "This is the visible handoff" in body
    assert 'href="/projects/central-agent-data-hub#connect-agent" aria-current="page"' in body
    assert "Review release readiness" in body
    assert "Source of truth: local Agent Data Hub database" in body
    assert "How this should influence the agent" in body
    assert "Reviewed decisions become task constraints" in body
    assert "Known gaps" in body
    assert "1 unanswered questions" in body
    assert "Connect your agent" in body
    assert 'aria-label="Agent connection steps"' in body
    assert "Choose agent" in body
    assert "Connect once" in body
    assert "Check the handoff" in body
    assert "Which agent do you use?" in body
    assert 'href="#agent-chatbot"' in body
    assert 'href="#agent-codex"' in body
    assert 'href="#agent-claude"' in body
    assert 'href="#agent-custom"' in body
    assert 'href="#agent-mcp"' in body
    assert 'href="#agent-terminal"' in body
    assert "Claude Code" in body
    assert "Codex" in body
    assert 'aria-label="Connection verification"' in body
    assert "ADH can check Codex here" in body
    assert "Codex setup not installed yet" in body
    assert "Manual check needed" in body
    assert "Persistent rule needed" in body
    assert "Per-task copy/paste" in body
    assert "must be checked in their own app" in body
    assert "Start Claude Code after setup" in body
    assert body.index("<h3>Codex</h3>") < body.index("<h3>Claude Code</h3>")
    assert "Hermes or custom agent" in body
    assert "Other MCP-compatible agent" in body
    assert "Manual every task" in body
    assert "One local click" in body
    assert "One copied command" in body
    assert "Persistent instruction" in body
    assert "Copy MCP config" in body
    assert "Temporary fallback" in body
    assert "One-time setup" in body
    assert "Copy Claude setup" in body
    assert "Install Codex setup" in body
    assert "Copy fallback command" in body
    assert "Copy startup rule" in body
    assert "Copy MCP config" in body
    assert "Jump to chatbot text" in body
    assert "Use this when ADH knows the local project folder" in body
    assert "Check: Codex shows an ADH Context Loaded receipt at task start" in body
    assert "Check: the context pack is visible in the chat before the task" in body
    assert "Check: the agent shows an ADH receipt or matching counts" in body
    assert "Check: the terminal prints one visible ADH-backed run" in body
    assert "Show Claude manual setup pieces" in body
    assert "it never runs an agent" in body
    assert "writes only after an explicit local click" in body
    assert "is instructed to request ADH context" in body
    assert "AGENTS.md" in body
    assert "ADH knows this project" in body
    assert "Project folder:" in body
    assert "Target file:" in body
    assert "Planned action:" in body
    assert "Preview AGENTS.md block" in body
    assert "/demo/project" in body
    assert "Run this from the project repository" not in body
    assert "$PWD" not in body
    assert "project-repo-path" not in body
    assert "Add ADH as a local MCP server once" in body
    assert "claude mcp add agent-data-hub" in body
    assert "Manual fallback" in body
    assert "it is not automation" in body
    assert "For local agents: start a new task" in body
    assert "ADH cannot prove that an unconnected agent read the context" in body
    assert body.index("<h2>Connect your agent</h2>") < body.index("<h2>Task</h2>")
    assert body.index('id="agent-choices"') < body.index('id="agent-chatbot"')
    assert body.index('id="agent-chatbot"') < body.index('id="test-handoff"')
    assert body.index('id="test-handoff"') < body.index('aria-label="Connection verification"')
    assert body.index('aria-label="Connection verification"') < body.index("<h2>Task</h2>")
    assert body.index("<h2>Known gaps</h2>") < body.index("<h2>Text to paste into a chatbot</h2>")
    assert 'data-copy-target="claude-code-setup-command"' in body
    assert 'data-copy-target="codex-setup-command"' in body
    assert 'data-copy-target="custom-startup-instruction"' in body
    assert 'data-copy-target="install-mcp-command"' in body
    assert 'data-copy-target="claude-mcp-command"' in body
    assert 'data-copy-target="mcp-json-config"' in body
    assert 'data-copy-target="startup-instruction"' in body
    assert 'data-copy-target="agent-start-command"' in body
    assert 'data-copy-target="prepare-command"' in body
    assert 'data-copy-target="chatbot-context-pack"' in body
    assert "Copy chatbot text" in body
    assert "agent-hub prepare --project central-agent-data-hub" in body
    assert "scripts/agent_start.sh --project central-agent-data-hub" in body
    assert "# Agent Context Pack" in body
    assert 'href="/projects/central-agent-data-hub"' in body


def test_agent_context_commands_are_shell_quoted_for_copy_paste(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hub_view, "prepare_markdown", lambda _payload: "# Agent Context Pack")
    project_path = str(tmp_path)

    view = hub_view.build_agent_context_view(
        {
            "project": {
                "id": "project-id",
                "slug": "central-agent-data-hub",
                "name": "Central Agent Data Hub",
                "metadata": {"local_path": project_path},
            },
            "task": "Review Ronak's release notes",
            "verified_project_state": [],
            "relevant_decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
            "relations": [],
            "drafts_pending_review": {},
            "context_trail": {
                "included_counts": {
                    "facts": 0,
                    "decisions": 0,
                    "risks": 0,
                    "open_questions": 0,
                    "reports": 0,
                    "relations": 0,
                },
                "sources": [],
                "excluded": {"note": "none"},
                "task_selection": {
                    "mode": "deterministic",
                    "note": "test",
                    "tie_breaking": "test",
                },
                "gap_summary": {},
            },
            "goal": "Review Ronak's release notes",
            "constraints": [],
            "allowed_actions": [],
            "requires_human_approval": [],
            "suggested_checks": [],
            "gaps": {"summary": {}},
        }
    )

    assert (
        view["commands"]["prepare"]
        == "agent-hub prepare --project central-agent-data-hub --task 'Review Ronak'\"'\"'s release notes'"
    )
    assert (
        view["commands"]["agent_start"]
        == "scripts/agent_start.sh --project central-agent-data-hub --query 'Review Ronak'\"'\"'s release notes' --review"
    )
    assert (
        view["local_agent"]["setup_command"]
        == f"{hub_view.shell_command([sys.executable, '-m', 'pip', 'install', '-e', '.[mcp]'])} && "
        f"{hub_view.shell_command(['claude', 'mcp', 'add', 'agent-data-hub', '--', sys.executable, '-m', 'agent_hub.cli', 'mcp-serve'])}"
    )
    assert view["local_agent"]["install_mcp"] == hub_view.shell_command(
        [sys.executable, "-m", "pip", "install", "-e", ".[mcp]"]
    )
    install_script = (
        hub_view.Path(hub_view.__file__).resolve().parents[1] / "scripts" / "install_repo_agent_memory.sh"
    )
    assert view["local_agent"]["codex_command"] == hub_view.shell_command(
        [
            str(install_script),
            "--repo",
            project_path,
            "--project",
            "central-agent-data-hub",
        ]
    )
    assert view["local_agent"]["codex_project_path"] == project_path
    assert view["local_agent"]["codex"]["project_path"] == project_path
    assert view["local_agent"]["codex"]["target_file"] == "AGENTS.md"
    assert view["local_agent"]["codex"]["action"] == "create"
    assert "<!-- CENTRAL-AGENT-DATA-HUB:START -->" in view["local_agent"]["codex"]["preview"]
    assert (
        view["local_agent"]["claude_mcp"]
        == hub_view.shell_command(
            [
                "claude",
                "mcp",
                "add",
                "agent-data-hub",
                "--",
                sys.executable,
                "-m",
                "agent_hub.cli",
                "mcp-serve",
            ]
        )
    )
    assert '"mcpServers"' in view["local_agent"]["mcp_json"]
    assert sys.executable in view["local_agent"]["mcp_json"]
    assert '"agent_hub.cli"' in view["local_agent"]["mcp_json"]
    assert '"agent-data-hub"' in view["local_agent"]["mcp_json"]
    assert "request reviewed context from Agent Data Hub" in view["local_agent"]["startup_instruction"]
    assert "Review Ronak's release notes" in view["local_agent"]["startup_instruction"]


def test_codex_setup_view_reports_connection_status(tmp_path) -> None:
    repo_root = hub_view.Path(hub_view.__file__).resolve().parents[1]
    project = {
        "id": "project-id",
        "slug": "central-agent-data-hub",
        "name": "Central Agent Data Hub",
        "metadata": {"local_path": str(tmp_path)},
    }

    missing = hub_view.build_codex_setup_view(project, repo_root)

    assert missing["action"] == "create"
    assert missing["verification"]["state"] == "missing"
    assert missing["verification"]["label"] == "Codex setup not installed yet"

    (tmp_path / "AGENTS.md").write_text(str(missing["preview"]).rstrip() + "\n", encoding="utf-8")
    connected = hub_view.build_codex_setup_view(project, repo_root)

    assert connected["action"] == "unchanged"
    assert connected["verification"]["state"] == "connected"
    assert connected["verification"]["label"] == "Codex setup verified"


def test_agent_context_omits_codex_setup_when_project_path_is_unknown(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_HUB_PUBLIC_DEMO", raising=False)
    monkeypatch.setattr(hub_view, "prepare_markdown", lambda _payload: "# Agent Context Pack")

    view = hub_view.build_agent_context_view(
        {
            "project": {
                "id": "project-id",
                "slug": "unknown-project",
                "name": "Unknown Project",
            },
            "task": "Review setup",
            "verified_project_state": [],
            "relevant_decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
            "relations": [],
            "drafts_pending_review": {},
            "context_trail": {
                "included_counts": {},
                "sources": [],
                "excluded": {},
                "task_selection": {},
                "gap_summary": {},
            },
            "goal": "Review setup",
            "constraints": [],
            "allowed_actions": [],
            "requires_human_approval": [],
            "suggested_checks": [],
            "gaps": {"summary": {}},
        }
    )

    assert view["local_agent"]["codex_command"] is None
    assert view["local_agent"]["codex_project_path"] is None
    assert view["local_agent"]["codex"]["can_install"] is False
    assert view["local_agent"]["codex"]["verification"]["state"] == "unknown"


def test_agent_context_uses_public_demo_checkout_for_codex_setup(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HUB_PUBLIC_DEMO", "1")
    monkeypatch.setattr(hub_view, "prepare_markdown", lambda _payload: "# Agent Context Pack")

    view = hub_view.build_agent_context_view(
        {
            "project": {
                "id": "project-id",
                "slug": "central-agent-data-hub-demo",
                "name": "Central Agent Data Hub Demo",
            },
            "task": "Review demo",
            "verified_project_state": [],
            "relevant_decisions": [],
            "risks": [],
            "open_questions": [],
            "reports": [],
            "relations": [],
            "drafts_pending_review": {},
            "context_trail": {
                "included_counts": {},
                "sources": [],
                "excluded": {},
                "task_selection": {},
                "gap_summary": {},
            },
            "goal": "Review demo",
            "constraints": [],
            "allowed_actions": [],
            "requires_human_approval": [],
            "suggested_checks": [],
            "gaps": {"summary": {}},
        }
    )

    repo_root = str(hub_view.Path(hub_view.__file__).resolve().parents[1])
    assert view["local_agent"]["codex_project_path"] == repo_root
    assert view["local_agent"]["codex"]["can_install"] is False
    assert view["local_agent"]["codex"]["demo_only"] is True
    assert view["local_agent"]["codex"]["verification"]["state"] == "demo"
    assert view["local_agent"]["codex"]["target_path"] == f"{repo_root}/AGENTS.md"
    install_script = (
        hub_view.Path(hub_view.__file__).resolve().parents[1] / "scripts" / "install_repo_agent_memory.sh"
    )
    assert view["local_agent"]["codex_command"] == hub_view.shell_command(
        [
            str(install_script),
            "--repo",
            repo_root,
            "--project",
            "central-agent-data-hub-demo",
            "--dry-run",
        ]
    )


def test_format_timestamp_for_datetime() -> None:
    value = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    assert hub_view.format_timestamp(value) == "2026-06-05 08:00 UTC"


def test_port_is_available_detects_bound_socket() -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
        assert hub_view.port_is_available(host, port) is False
