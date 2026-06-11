from __future__ import annotations

import pytest

from agent_hub.reviewers import (
    resolve_required_reviewer,
    resolve_responsible_reviewer,
    validate_reviewer_handle,
)


def test_reviewer_handle_normalizes_and_validates(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_HUB_REVIEWERS", raising=False)

    assert validate_reviewer_handle(" Alice-1 ") == "alice-1"


@pytest.mark.parametrize("handle", ["alice_1", "alice.1", ""])
def test_reviewer_handle_rejects_invalid_syntax(monkeypatch, handle: str) -> None:
    monkeypatch.delenv("AGENT_HUB_REVIEWERS", raising=False)

    with pytest.raises(ValueError):
        validate_reviewer_handle(handle)


def test_reviewer_allowlist_rejects_unknown_handle(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HUB_REVIEWERS", "alice,bob")

    with pytest.raises(ValueError, match="not allowed"):
        validate_reviewer_handle("charlie")


def test_required_reviewer_uses_explicit_then_env(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HUB_REVIEWER", "bob")

    assert resolve_required_reviewer("alice") == "alice"
    assert resolve_required_reviewer() == "bob"


def test_responsible_reviewer_prefers_item_project_env_then_unassigned(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HUB_DEFAULT_REVIEWER", "reviewer-a")
    project = {"metadata": {"default_reviewer": "bob"}}

    item_resolution = resolve_responsible_reviewer(
        {"metadata": {"assigned_reviewer": "alice"}},
        project,
    )
    project_resolution = resolve_responsible_reviewer({"metadata": {}}, project)
    env_resolution = resolve_responsible_reviewer({"metadata": {}}, {"metadata": {}})
    monkeypatch.delenv("AGENT_HUB_DEFAULT_REVIEWER", raising=False)
    empty_resolution = resolve_responsible_reviewer({"metadata": {}}, {"metadata": {}})

    assert item_resolution.handle == "alice"
    assert item_resolution.reason == "item metadata assigned_reviewer"
    assert project_resolution.handle == "bob"
    assert project_resolution.reason == "project metadata default_reviewer"
    assert env_resolution.handle == "reviewer-a"
    assert env_resolution.reason == "environment default reviewer"
    assert empty_resolution.handle == "unassigned"
    assert empty_resolution.reason == "no reviewer assigned"


def test_invalid_metadata_override_becomes_unassigned(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HUB_REVIEWERS", "alice,bob")
    resolution = resolve_responsible_reviewer(
        {"metadata": {"assigned_reviewer": "charlie"}},
        {"metadata": {"default_reviewer": "alice"}},
    )

    assert resolution.handle == "unassigned"
    assert resolution.reason == "invalid item override"
