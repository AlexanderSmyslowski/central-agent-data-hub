"""Command line interface for Agent Data Hub."""

from __future__ import annotations

import os
import subprocess
from datetime import timezone
from pathlib import Path

from agent_hub.commands.common import (
    concise_error,
    confidence_value,
    fetch_project,
    json_default,
    parse_metadata,
    parse_since,
    positive_int,
    print_relations,
    print_rows,
)
from agent_hub.commands.parser import build_parser, not_implemented
from agent_hub.commands.read import fetch_compiled_payload, get_export_dir_or_none
from agent_hub.commands.write import print_sync_result
from agent_hub.db import connect
from agent_hub.migrations import MIGRATIONS_DIR, migration_parts
from agent_hub.quality import fetch_memory_quality_warnings
from agent_hub.receipts import export_path_for_object
from agent_hub.relations import validate_relation_object
from agent_hub.rendering import agent_actions_markdown, limit_markdown_chars, truncate


def _shared_root(current_dir: Path, repo_root: Path) -> Path:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(current_dir),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve().parent
    return repo_root


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ("'", '"')
        ):
            value = value[1:-1]
        values[key] = value
    return values


def bootstrap_local_environment(
    *, cwd: Path | None = None, repo_root: Path | None = None
) -> None:
    if os.environ.get("AGENT_HUB_DISABLE_ENV_AUTOLOAD") == "1":
        return

    current_dir = (cwd or Path.cwd()).resolve()
    repo_dir = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    shared_root = _shared_root(current_dir, repo_dir)

    env_file: Path | None = None
    for candidate_root in (current_dir, repo_dir, shared_root):
        candidate = candidate_root / ".env"
        if candidate.is_file():
            env_file = candidate
            break

    if env_file is not None:
        for key, value in _parse_env_file(env_file).items():
            if key in os.environ:
                continue
            if key in ("OBSIDIAN_EXPORT_DIR", "AGENT_HUB_BACKUP_DIR"):
                expanded = Path(value).expanduser()
                if not expanded.is_absolute():
                    expanded = (shared_root / expanded).resolve()
                os.environ[key] = str(expanded)
            else:
                os.environ[key] = value

        os.environ.setdefault(
            "DATABASE_URL", "postgresql://postgres:changeme@localhost:55432/agent_hub"
        )
        os.environ.setdefault(
            "OBSIDIAN_EXPORT_DIR", str(shared_root / ".local/obsidian-export")
        )
        os.environ.setdefault(
            "AGENT_HUB_BACKUP_DIR", str(shared_root / ".local/backups")
        )


def main(argv: list[str] | None = None) -> int:
    bootstrap_local_environment()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
