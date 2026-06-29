from __future__ import annotations

import json
import uuid

import pytest

from agent_hub.project_registration import (
    ProjectRegistrationError,
    register_project,
    resolve_project_path,
    validate_project_slug,
)


def test_project_registration_validates_project_slug() -> None:
    assert validate_project_slug("my-project-1") == "my-project-1"

    with pytest.raises(ProjectRegistrationError):
        validate_project_slug("My Project")


def test_project_registration_resolves_existing_project_path(tmp_path) -> None:
    assert resolve_project_path(str(tmp_path)) == str(tmp_path.resolve())

    with pytest.raises(ProjectRegistrationError):
        resolve_project_path(str(tmp_path / "missing"))


class RegistrationCursor:
    def __init__(self) -> None:
        self.project_id = uuid.UUID("10000000-0000-4000-8000-000000000901")
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))

    def fetchone(self) -> dict[str, object]:
        return {"id": self.project_id}


def test_register_project_writes_project_and_codex_agent_metadata(tmp_path) -> None:
    cur = RegistrationCursor()

    result = register_project(
        cur,
        slug="my-project",
        name="My Project",
        repo_path=str(tmp_path),
        description="Local project.",
        registered_by="test",
    )

    assert result["id"] == cur.project_id
    assert result["slug"] == "my-project"
    assert result["local_path"] == str(tmp_path.resolve())
    assert len(cur.calls) == 2
    project_sql, project_params = cur.calls[0]
    agent_sql, agent_params = cur.calls[1]
    assert "INSERT INTO projects" in project_sql
    assert "ON CONFLICT (slug) DO UPDATE" in project_sql
    assert "INSERT INTO agents" in agent_sql
    metadata = json.loads(project_params[3])
    assert metadata["local_path"] == str(tmp_path.resolve())
    assert metadata["registered_by"] == "test"
    assert json.loads(agent_params[2]) == {
        "interface": "codex",
        "registered_by": "test",
    }
