"""Repo-local agent memory installer for Codex-style instruction files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


START_MARKER = "<!-- CENTRAL-AGENT-DATA-HUB:START -->"
END_MARKER = "<!-- CENTRAL-AGENT-DATA-HUB:END -->"
DEFAULT_TARGET_FILE = "AGENTS.md"


class RepoAgentMemoryError(ValueError):
    """Raised when a repo-local agent memory block cannot be planned safely."""


@dataclass(frozen=True)
class RepoAgentMemoryPlan:
    repo_path: Path
    project_slug: str
    hub_root: Path
    target_file: str
    target_path: Path
    block: str
    updated_text: str
    action: str


def render_repo_agent_memory_block(project_slug: str, hub_root: Path) -> str:
    root = str(hub_root)
    return f"""\
{START_MARKER}

## Central Agent Data Hub

Project slug: `{project_slug}`

Run Card:
`{root}/docs/agent-run-card.md`

Use the Run Card rhythm for substantial work: start with Hub context, work inside
one project boundary, finish with review, and write back only reviewed,
non-sensitive memory.

If work requires protected hosting, deployment, FTP, or production access,
request a human secure handoff outside the Hub, Git, and Obsidian. Store back
only the reviewed, non-sensitive outcome.

Use the shared Hub before and after substantial project work:

```bash
{root}/scripts/agent_start.sh --project {project_slug} --query "<current focus>"
{root}/scripts/agent_start.sh --project {project_slug} --query "<current focus>" --review
{root}/scripts/agent_finish.sh --project {project_slug} --review
```

For reviewed, non-sensitive memory candidates, dry-run first:

```bash
{root}/scripts/project_remember.sh \\
  --project {project_slug} \\
  --type fact \\
  --text "Reviewed memory candidate." \\
  --source "non-sensitive source" \\
  --dry-run
```

Then write only curated memory:

```bash
{root}/scripts/project_remember.sh \\
  --project {project_slug} \\
  --type fact \\
  --text "Reviewed memory candidate." \\
  --source "non-sensitive source"
```

Never store passwords, API keys, tokens, FTP credentials, private customer data,
raw invoice data, deployment secrets, unreviewed claims, or assumptions copied
from another project.

{END_MARKER}
"""


def validate_target_file(target_file: str) -> str:
    cleaned = target_file.strip()
    if not cleaned:
        raise RepoAgentMemoryError("target file is required")
    rel = Path(cleaned)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise RepoAgentMemoryError("target file must stay inside the repo")
    return cleaned


def resolve_repo_target(repo_path: str | Path, target_file: str = DEFAULT_TARGET_FILE) -> tuple[Path, str, Path]:
    repo = Path(repo_path).expanduser()
    if not repo.is_dir():
        raise RepoAgentMemoryError(f"repo path not found: {repo}")
    repo_abs = repo.resolve()
    target_name = validate_target_file(target_file)
    target_path = (repo_abs / target_name).resolve()
    if not target_path.is_relative_to(repo_abs):
        raise RepoAgentMemoryError("target file resolves outside repo")
    return repo_abs, target_name, target_path


def update_repo_agent_memory_text(original: str, block: str) -> str:
    normalized_block = block.rstrip() + "\n"
    if START_MARKER in original and END_MARKER in original:
        before = original.split(START_MARKER, 1)[0].rstrip()
        after = original.split(END_MARKER, 1)[1].lstrip()
        parts = []
        if before:
            parts.append(before)
        parts.append(normalized_block.rstrip())
        if after:
            parts.append(after.rstrip())
        return "\n\n".join(parts) + "\n"
    if original.strip():
        return original.rstrip() + "\n\n" + normalized_block
    return normalized_block


def plan_repo_agent_memory(
    *,
    repo_path: str | Path,
    project_slug: str,
    hub_root: str | Path,
    target_file: str = DEFAULT_TARGET_FILE,
) -> RepoAgentMemoryPlan:
    if not project_slug.strip():
        raise RepoAgentMemoryError("project slug is required")
    hub_root_path = Path(hub_root).expanduser().resolve()
    repo_abs, target_name, target_path = resolve_repo_target(repo_path, target_file)
    original = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    block = render_repo_agent_memory_block(project_slug.strip(), hub_root_path)
    updated = update_repo_agent_memory_text(original, block)
    if target_path.exists() and original == updated:
        action = "unchanged"
    elif target_path.exists() and START_MARKER in original and END_MARKER in original:
        action = "update"
    elif target_path.exists() and original.strip():
        action = "append"
    else:
        action = "create"
    return RepoAgentMemoryPlan(
        repo_path=repo_abs,
        project_slug=project_slug.strip(),
        hub_root=hub_root_path,
        target_file=target_name,
        target_path=target_path,
        block=block,
        updated_text=updated,
        action=action,
    )


def install_repo_agent_memory(plan: RepoAgentMemoryPlan) -> RepoAgentMemoryPlan:
    plan.target_path.parent.mkdir(parents=True, exist_ok=True)
    plan.target_path.write_text(plan.updated_text, encoding="utf-8")
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agent_hub.repo_agent_memory",
        description="Plan or install a repo-local Agent Data Hub block.",
    )
    parser.add_argument("--repo", required=True, help="Target repository or project directory.")
    parser.add_argument("--project", required=True, help="Agent Data Hub project slug.")
    parser.add_argument("--hub-root", required=True, help="Agent Data Hub repository path.")
    parser.add_argument("--file", default=DEFAULT_TARGET_FILE, help="Target file inside the repo.")
    parser.add_argument("--apply", action="store_true", help="Write the planned block.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run cannot be used together")
    try:
        plan = plan_repo_agent_memory(
            repo_path=args.repo,
            project_slug=args.project,
            hub_root=args.hub_root,
            target_file=args.file,
        )
    except RepoAgentMemoryError as exc:
        parser.exit(2, f"Error: {exc}\n")

    print("Central Agent Data Hub repo memory installer")
    print(f"Repo:    {plan.repo_path}")
    print(f"Project: {plan.project_slug}")
    print(f"Target:  {plan.target_path}")
    print(f"Action:  {plan.action}")

    if not args.apply:
        print()
        print("Dry run: no files were written.")
        print()
        print(plan.block, end="")
        return 0

    install_repo_agent_memory(plan)
    print("Installed or updated Hub memory block.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
