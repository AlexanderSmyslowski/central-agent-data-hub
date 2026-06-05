from __future__ import annotations

from datetime import datetime, timezone

from agent_hub import hub_view


def test_render_page_includes_read_only_claim() -> None:
    body = hub_view.render_page(
        {
            "projects": [],
            "selected_project": None,
            "not_found_slug": None,
        },
        200,
    ).decode("utf-8")

    assert "Hub View" in body
    assert "read-only review surface for Agent Data Hub" in body
    assert "Read-only review surface" in body


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
                }
            ],
            "selected_project": {
                "name": "Central Agent Data Hub",
                "slug": "central-agent-data-hub",
                "description": "Shared memory.",
                "status": "active",
                "project_type": "ops",
                "updated_at": "2026-06-05 08:00 UTC",
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
                },
                "decisions": [{"decision": "Treat the Hub as verified context.", "rationale": "Shared trust."}],
                "risks": [{"title": "Skipped preflight", "severity": "medium", "impact": "stale context"}],
                "open_questions": [],
                "reports": [{"title": "Daily report", "summary": "A compact review."}],
                "relations": [{"source": "Fact A", "relation_type": "supports", "target": "Decision B"}],
            },
            "not_found_slug": None,
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
    assert "Treat the Hub as verified context." in body
    assert "Fact A" in body
    assert "supports" in body


def test_format_timestamp_for_datetime() -> None:
    value = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    assert hub_view.format_timestamp(value) == "2026-06-05 08:00 UTC"


def test_port_is_available_detects_bound_socket() -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
        assert hub_view.port_is_available(host, port) is False
