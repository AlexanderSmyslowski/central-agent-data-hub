"""Internal reviewer handle resolution for draft review attribution."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any


HANDLE_RE = re.compile(r"^[a-z0-9-]+$")
UNASSIGNED_REVIEWER = "unassigned"
VALID_REVIEW_SOURCES = frozenset({"cli", "hub_view", "telegram"})


@dataclass(frozen=True)
class ReviewerResolution:
    handle: str
    reason: str


def normalize_reviewer_handle(value: object) -> str:
    return str(value or "").strip().lower()


def reviewer_allowlist() -> set[str] | None:
    raw = os.environ.get("AGENT_HUB_REVIEWERS")
    if raw is None or not raw.strip():
        return None
    handles = set()
    for item in raw.split(","):
        handle = normalize_reviewer_handle(item)
        if not handle:
            continue
        validate_reviewer_syntax(handle)
        handles.add(handle)
    return handles


def validate_reviewer_syntax(handle: str) -> None:
    if not handle or not HANDLE_RE.fullmatch(handle):
        raise ValueError("reviewer handle must use lowercase letters, numbers, and '-'")


def validate_reviewer_handle(value: object) -> str:
    handle = normalize_reviewer_handle(value)
    validate_reviewer_syntax(handle)
    allowed = reviewer_allowlist()
    if allowed is not None and handle not in allowed:
        raise ValueError(f"reviewer handle is not allowed: {handle}")
    return handle


def validate_review_source(value: object) -> str:
    source = str(value or "").strip()
    if source not in VALID_REVIEW_SOURCES:
        allowed = ", ".join(sorted(VALID_REVIEW_SOURCES))
        raise ValueError(f"unknown review_source: {source or '<empty>'}; expected one of: {allowed}")
    return source


def resolve_required_reviewer(
    explicit: object | None = None,
    *,
    env_var: str = "AGENT_HUB_REVIEWER",
) -> str:
    raw = explicit if explicit not in (None, "") else os.environ.get(env_var)
    if raw in (None, ""):
        raise ValueError(f"reviewer handle is required; set --reviewer or {env_var}")
    return validate_reviewer_handle(raw)


def optional_metadata_handle(value: object) -> str | None:
    try:
        return validate_reviewer_handle(value)
    except ValueError:
        return None


def resolve_responsible_reviewer(
    draft: dict[str, Any],
    project: dict[str, Any] | None = None,
) -> ReviewerResolution:
    metadata = draft.get("metadata") if isinstance(draft.get("metadata"), dict) else {}
    assigned = metadata.get("assigned_reviewer") if isinstance(metadata, dict) else None
    if assigned not in (None, ""):
        handle = optional_metadata_handle(assigned)
        if handle:
            return ReviewerResolution(handle, "item metadata assigned_reviewer")
        return ReviewerResolution(UNASSIGNED_REVIEWER, "invalid item override")

    project_metadata: dict[str, Any] = {}
    if project and isinstance(project.get("metadata"), dict):
        project_metadata = project["metadata"]
    elif isinstance(draft.get("project_metadata"), dict):
        project_metadata = draft["project_metadata"]

    default_reviewer = project_metadata.get("default_reviewer")
    if default_reviewer not in (None, ""):
        handle = optional_metadata_handle(default_reviewer)
        if handle:
            return ReviewerResolution(handle, "project metadata default_reviewer")
        return ReviewerResolution(UNASSIGNED_REVIEWER, "invalid project default")

    env_default = os.environ.get("AGENT_HUB_DEFAULT_REVIEWER")
    if env_default:
        try:
            return ReviewerResolution(
                validate_reviewer_handle(env_default),
                "environment default reviewer",
            )
        except ValueError:
            return ReviewerResolution(UNASSIGNED_REVIEWER, "invalid environment default")

    return ReviewerResolution(UNASSIGNED_REVIEWER, "no reviewer assigned")
