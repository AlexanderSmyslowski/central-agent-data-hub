"""Codex Desktop project label integration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_codex_state_path() -> Path:
    return Path.home() / ".codex" / ".codex-global-state.json"


def codex_state_path() -> Path:
    configured = os.environ.get("CODEX_GLOBAL_STATE_PATH")
    return Path(configured).expanduser() if configured else default_codex_state_path()


def load_workspace_labels(path: Path | None = None) -> dict[str, str]:
    state_path = path or codex_state_path()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    labels = payload.get("electron-workspace-root-labels")
    if not isinstance(labels, dict):
        return {}

    clean: dict[str, str] = {}
    for root, label in labels.items():
        if isinstance(root, str) and isinstance(label, str) and label.strip():
            clean[str(Path(root).expanduser())] = label.strip()
    return clean


def codex_workspace_label(root: object, labels: dict[str, str] | None = None) -> str | None:
    if not isinstance(root, str) or not root.strip():
        return None

    normalized = str(Path(root).expanduser())
    workspace_labels = labels if labels is not None else load_workspace_labels()
    label = workspace_labels.get(normalized)
    if label:
        return label
    return Path(normalized).name or None


def project_display_name(
    project: dict[str, Any],
    labels: dict[str, str] | None = None,
) -> str:
    metadata = project.get("metadata") or {}
    if isinstance(metadata, dict):
        label = codex_workspace_label(metadata.get("codex_workspace_root"), labels)
        if label:
            return label
    return str(project.get("name") or project.get("slug") or "")


def with_project_display_name(
    project: dict[str, Any] | None,
    labels: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    if project is None:
        return None
    normalized = dict(project)
    normalized["name"] = project_display_name(normalized, labels)
    return normalized


def with_project_display_names(
    projects: list[dict[str, Any]],
    labels: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    workspace_labels = labels if labels is not None else load_workspace_labels()
    return [
        with_project_display_name(project, workspace_labels) or project
        for project in projects
    ]
