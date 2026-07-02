"""Project registration command handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_hub.commands.common import (
    error,
    exception_error,
    json_default,
    require_database_url,
)
from agent_hub.commands.system import checkout_script_path
from agent_hub.db import connect
from agent_hub.project_registration import (
    ProjectRegistrationError,
    detect_github_remote,
    register_project,
    resolve_project_path,
    validate_project_slug,
    validate_project_type,
)
from agent_hub.repo_agent_memory import (
    RepoAgentMemoryError,
    install_repo_agent_memory,
    plan_repo_agent_memory,
)


def _hub_root_for_agent_block() -> Path | None:
    script_path = checkout_script_path("agent_start.sh", "register-project")
    if script_path is None:
        return None
    return script_path.parents[1]


def _registration_plan(args: argparse.Namespace) -> dict[str, object]:
    slug = validate_project_slug(args.slug)
    name = args.name.strip()
    if not name:
        raise ProjectRegistrationError("Name the project.")
    repo_path = resolve_project_path(args.repo)
    project_type = validate_project_type(args.project_type)
    description = args.description.strip() or f"Agentic project work for {name}."
    memory_scope = args.memory_scope.strip() or "project"
    domain_profile = args.domain_profile.strip()
    repo_remote = detect_github_remote(repo_path)

    return {
        "slug": slug,
        "name": name,
        "description": description,
        "repo_path": repo_path,
        "project_type": project_type,
        "memory_scope": memory_scope,
        "domain_profile": domain_profile,
        "repo_remote": repo_remote,
    }


def _print_text_plan(
    plan: dict[str, object],
    *,
    dry_run: bool,
    no_install: bool,
    install_plan=None,
) -> None:
    print("Central Agent Data Hub project registration")
    print(f"Project:      {plan['slug']}")
    print(f"Name:         {plan['name']}")
    print(f"Type:         {plan['project_type']}")
    print(f"Repo path:    {plan['repo_path']}")
    if not no_install and install_plan is not None:
        print(f"Target file:  {install_plan.target_file}")
    if plan.get("repo_remote"):
        print(f"Repo remote:  {plan['repo_remote']}")
    if dry_run:
        print()
        print("Dry run: no DB rows or repo files were written.")
        if not no_install and install_plan is not None:
            print()
            print("Planned repo-local Hub block:")
            print(install_plan.block, end="")


def _json_payload(
    plan: dict[str, object],
    *,
    dry_run: bool,
    no_install: bool,
    install_plan=None,
    registered: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "dry_run": dry_run,
        "project": registered or plan,
        "install": None,
    }
    if not no_install and install_plan is not None:
        payload["install"] = {
            "target_file": install_plan.target_file,
            "target_path": str(install_plan.target_path),
            "action": install_plan.action,
        }
    return payload


def run_register_project(args: argparse.Namespace) -> int:
    try:
        plan = _registration_plan(args)
    except ProjectRegistrationError as exc:
        return error(exc, 2)

    hub_root: Path | None = None
    install_plan = None
    if not args.no_install:
        hub_root = _hub_root_for_agent_block()
        if hub_root is None:
            return 2
        try:
            install_plan = plan_repo_agent_memory(
                repo_path=str(plan["repo_path"]),
                project_slug=str(plan["slug"]),
                hub_root=hub_root,
                target_file=args.target_file,
            )
        except RepoAgentMemoryError as exc:
            return error(exc, 2)

    if args.dry_run:
        if args.format == "json":
            print(
                json.dumps(
                    _json_payload(
                        plan,
                        dry_run=True,
                        no_install=args.no_install,
                        install_plan=install_plan,
                    ),
                    indent=2,
                    default=json_default,
                    ensure_ascii=False,
                )
            )
        else:
            _print_text_plan(
                plan,
                dry_run=True,
                no_install=args.no_install,
                install_plan=install_plan,
            )
        return 0

    if error_code := require_database_url():
        return error_code

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                registered = register_project(
                    cur,
                    slug=str(plan["slug"]),
                    name=str(plan["name"]),
                    repo_path=str(plan["repo_path"]),
                    description=str(plan["description"]),
                    project_type=str(plan["project_type"]),
                    memory_scope=str(plan["memory_scope"]),
                    domain_profile=str(plan["domain_profile"]),
                    repo_remote=str(plan["repo_remote"]),
                    registered_by="agent-hub register-project",
                )
            conn.commit()
    except Exception as exc:
        return exception_error(exc, 1)

    if install_plan is not None:
        try:
            install_repo_agent_memory(install_plan)
        except OSError as exc:
            return exception_error(exc, 1)

    if args.format == "json":
        print(
            json.dumps(
                _json_payload(
                    plan,
                    dry_run=False,
                    no_install=args.no_install,
                    install_plan=install_plan,
                    registered=registered,
                ),
                indent=2,
                default=json_default,
                ensure_ascii=False,
            )
        )
    else:
        _print_text_plan(
            plan,
            dry_run=False,
            no_install=args.no_install,
            install_plan=install_plan,
        )
        print()
        print(f"Registered Hub project: {registered['slug']}")
        if install_plan is not None:
            print(f"Installed or updated Hub memory block: {install_plan.target_path}")
        print("Project registration result: ready")

    return 0
