from __future__ import annotations

import json

from agent_hub.codex_projects import (
    codex_workspace_label,
    load_workspace_labels,
    project_display_name,
    with_project_display_name,
)


def test_load_workspace_labels_reads_codex_global_state(tmp_path) -> None:
    state_path = tmp_path / "codex-state.json"
    state_path.write_text(
        json.dumps(
            {
                "electron-workspace-root-labels": {
                    "/path/to/demo-website.local 2": "demo-website.local",
                    "/path/to/old": "",
                }
            }
        ),
        encoding="utf-8",
    )

    labels = load_workspace_labels(state_path)

    assert labels == {"/path/to/demo-website.local 2": "demo-website.local"}


def test_project_display_name_prefers_explicit_codex_workspace_label() -> None:
    project = {
        "slug": "demo-website",
        "name": "Demo Website",
        "metadata": {
            "codex_workspace_root": "/path/to/demo-website.local 2"
        },
    }

    display_name = project_display_name(
        project,
        {"/path/to/demo-website.local 2": "demo-website.local"},
    )

    assert display_name == "demo-website.local"


def test_project_display_name_falls_back_to_workspace_folder_name() -> None:
    label = codex_workspace_label("/path/to/demo-catering.local", {})

    assert label == "demo-catering.local"


def test_with_project_display_name_keeps_original_when_no_codex_root() -> None:
    project = {"slug": "future-website", "name": "Future Website", "metadata": {}}

    renamed = with_project_display_name(project, {})

    assert renamed["name"] == "Future Website"
