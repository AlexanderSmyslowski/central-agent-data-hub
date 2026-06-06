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
                    "/Users/example/Documents/commcats.de 2": "commcats.de",
                    "/Users/example/Documents/old": "",
                }
            }
        ),
        encoding="utf-8",
    )

    labels = load_workspace_labels(state_path)

    assert labels == {"/Users/example/Documents/commcats.de 2": "commcats.de"}


def test_project_display_name_prefers_explicit_codex_workspace_label() -> None:
    project = {
        "slug": "commcats-de",
        "name": "CommCats",
        "metadata": {
            "codex_workspace_root": "/Users/example/Documents/commcats.de 2"
        },
    }

    display_name = project_display_name(
        project,
        {"/Users/example/Documents/commcats.de 2": "commcats.de"},
    )

    assert display_name == "commcats.de"


def test_project_display_name_falls_back_to_workspace_folder_name() -> None:
    label = codex_workspace_label("/Users/example/Documents/the-one.catering", {})

    assert label == "the-one.catering"


def test_with_project_display_name_keeps_original_when_no_codex_root() -> None:
    project = {"slug": "lamour", "name": "L'Amour", "metadata": {}}

    renamed = with_project_display_name(project, {})

    assert renamed["name"] == "L'Amour"
