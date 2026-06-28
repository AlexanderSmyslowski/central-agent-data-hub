from __future__ import annotations

import pytest

from agent_hub.repo_agent_memory import (
    END_MARKER,
    RepoAgentMemoryError,
    START_MARKER,
    install_repo_agent_memory,
    plan_repo_agent_memory,
)


def test_plan_repo_agent_memory_creates_preview_without_writing(tmp_path) -> None:
    plan = plan_repo_agent_memory(
        repo_path=tmp_path,
        project_slug="central-agent-data-hub-demo",
        hub_root="/opt/adh",
    )

    assert plan.action == "create"
    assert plan.target_path == tmp_path / "AGENTS.md"
    assert START_MARKER in plan.block
    assert END_MARKER in plan.block
    assert "Project slug: `central-agent-data-hub-demo`" in plan.block
    assert not plan.target_path.exists()


def test_install_repo_agent_memory_replaces_existing_marked_block(tmp_path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "Keep this intro.\n\n"
        f"{START_MARKER}\nold block\n{END_MARKER}\n\n"
        "Keep this outro.\n",
        encoding="utf-8",
    )

    plan = plan_repo_agent_memory(
        repo_path=tmp_path,
        project_slug="central-agent-data-hub",
        hub_root="/opt/adh",
    )
    install_repo_agent_memory(plan)

    updated = target.read_text(encoding="utf-8")
    assert plan.action == "update"
    assert "Keep this intro." in updated
    assert "Keep this outro." in updated
    assert "old block" not in updated
    assert "Project slug: `central-agent-data-hub`" in updated


def test_install_repo_agent_memory_reports_unchanged_when_block_matches(tmp_path) -> None:
    first = plan_repo_agent_memory(
        repo_path=tmp_path,
        project_slug="central-agent-data-hub",
        hub_root="/opt/adh",
    )
    install_repo_agent_memory(first)

    second = plan_repo_agent_memory(
        repo_path=tmp_path,
        project_slug="central-agent-data-hub",
        hub_root="/opt/adh",
    )

    assert second.action == "unchanged"


def test_plan_repo_agent_memory_rejects_paths_outside_repo(tmp_path) -> None:
    with pytest.raises(RepoAgentMemoryError):
        plan_repo_agent_memory(
            repo_path=tmp_path,
            project_slug="central-agent-data-hub",
            hub_root="/opt/adh",
            target_file="../AGENTS.md",
        )
