"""Project registration helpers shared by scripts and Hub View."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


VALID_PROJECT_TYPES = frozenset(
    {"website", "ops", "research", "product", "business", "personal", "learning"}
)
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


class ProjectRegistrationError(ValueError):
    """Raised when a project registration request is not safe to apply."""


def validate_project_slug(slug: str) -> str:
    value = slug.strip()
    if not SLUG_PATTERN.fullmatch(value):
        raise ProjectRegistrationError(
            "Use a slug with lowercase letters, numbers, and hyphens."
        )
    return value


def validate_project_type(project_type: str) -> str:
    value = project_type.strip() or "product"
    if value not in VALID_PROJECT_TYPES:
        allowed = ", ".join(sorted(VALID_PROJECT_TYPES))
        raise ProjectRegistrationError(f"Unsupported project type. Allowed: {allowed}.")
    return value


def resolve_project_path(repo_path: str) -> str:
    value = repo_path.strip()
    if not value:
        raise ProjectRegistrationError("Choose a local project folder.")
    path = Path(value).expanduser()
    if not path.is_dir():
        raise ProjectRegistrationError("The project folder was not found.")
    return str(path.resolve())


def detect_github_remote(repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""

    remote = result.stdout.strip()
    patterns = (
        re.compile(r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$"),
        re.compile(r"^https://github\.com/([^/]+/[^/]+?)(?:\.git)?$"),
    )
    for pattern in patterns:
        match = pattern.fullmatch(remote)
        if match:
            return match.group(1).removesuffix(".git")
    return ""


def register_project(
    cur,
    *,
    slug: str,
    name: str,
    repo_path: str,
    description: str = "",
    project_type: str = "product",
    memory_scope: str = "project",
    domain_profile: str = "",
    repo_remote: str = "",
    registered_by: str = "agent_hub.project_registration",
) -> dict[str, object]:
    """Register or update one active Hub project without writing repo files."""
    project_slug = validate_project_slug(slug)
    project_name = name.strip()
    if not project_name:
        raise ProjectRegistrationError("Name the project.")

    local_path = resolve_project_path(repo_path)
    resolved_type = validate_project_type(project_type)
    resolved_description = description.strip() or f"Agentic project work for {project_name}."
    resolved_scope = memory_scope.strip() or "project"
    resolved_remote = repo_remote.strip() or detect_github_remote(local_path)

    metadata = {
        "local_path": local_path,
        "project_type": resolved_type,
        "memory_scope": resolved_scope,
        "work_mode": "central-hub-start-finish",
        "registered_by": registered_by,
    }
    if domain_profile.strip():
        metadata["domain_profile"] = domain_profile.strip()
    if resolved_remote:
        metadata["repo"] = resolved_remote

    cur.execute(
        """
        INSERT INTO projects (name, slug, description, status, metadata)
        VALUES (%s, %s, %s, 'active', %s::jsonb)
        ON CONFLICT (slug) DO UPDATE SET
          name = EXCLUDED.name,
          description = EXCLUDED.description,
          status = EXCLUDED.status,
          metadata = projects.metadata || EXCLUDED.metadata,
          updated_at = now()
        RETURNING id
        """,
        (project_name, project_slug, resolved_description, json.dumps(metadata)),
    )
    project_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO agents (project_id, name, slug, role, status, metadata)
        VALUES (%s, 'Codex', 'codex', %s, 'active', %s::jsonb)
        ON CONFLICT (project_id, slug) DO UPDATE SET
          name = EXCLUDED.name,
          role = EXCLUDED.role,
          status = EXCLUDED.status,
          metadata = agents.metadata || EXCLUDED.metadata,
          updated_at = now()
        """,
        (
            project_id,
            f"Coding and implementation agent for {project_name}.",
            json.dumps({"interface": "codex", "registered_by": registered_by}),
        ),
    )
    return {
        "id": project_id,
        "slug": project_slug,
        "name": project_name,
        "description": resolved_description,
        "local_path": local_path,
        "project_type": resolved_type,
        "repo_remote": resolved_remote,
    }
