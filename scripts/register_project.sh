#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

PROJECT=""
NAME=""
DESCRIPTION=""
REPO_PATH=""
PROJECT_TYPE="product"
MEMORY_SCOPE="project"
DOMAIN_PROFILE=""
TARGET_FILE="AGENTS.md"
DRY_RUN=0
NO_INSTALL=0

usage() {
  cat <<'EOF'
Usage: scripts/register_project.sh --repo <path> --slug <slug> --name <name> [options]

Registers a project in the Central Agent Data Hub, stores metadata.local_path,
and installs the repo-local Hub block. This is the preferred bootstrap for new
project repos.

Options:
  --repo <path>          Target repo/project directory.
  --slug <slug>          Stable Hub project slug.
  --name <name>          Human-readable project name.
  --description <text>   Project description. Default is generated.
  --type <type>          Project type. Default: product.
  --memory-scope <text>  Memory scope metadata. Default: project.
  --domain-profile <x>   Optional domain profile metadata.
  --file <name>          Target agent instruction file. Default: AGENTS.md.
  --no-install           Register in DB but do not write repo-local file.
  --dry-run              Print planned actions; do not write DB or files.

Exit codes:
  0  registered or dry-run completed
  1  project or data error
  2  usage or operational readiness error
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --slug)
      PROJECT="${2:-}"
      shift 2
      ;;
    --name)
      NAME="${2:-}"
      shift 2
      ;;
    --description)
      DESCRIPTION="${2:-}"
      shift 2
      ;;
    --type)
      PROJECT_TYPE="${2:-}"
      shift 2
      ;;
    --memory-scope)
      MEMORY_SCOPE="${2:-}"
      shift 2
      ;;
    --domain-profile)
      DOMAIN_PROFILE="${2:-}"
      shift 2
      ;;
    --file)
      TARGET_FILE="${2:-}"
      shift 2
      ;;
    --no-install)
      NO_INSTALL=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$REPO_PATH" || -z "$PROJECT" || -z "$NAME" ]]; then
  echo "Error: --repo, --slug, and --name are required." >&2
  usage >&2
  exit 2
fi

if [[ ! "$PROJECT" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$ ]]; then
  echo "Error: --slug must use lowercase letters, numbers, and hyphens." >&2
  exit 2
fi

case "$PROJECT_TYPE" in
  website|ops|research|product|business|personal|learning) ;;
  *)
    echo "Error: unsupported --type '$PROJECT_TYPE'." >&2
    echo "Allowed: website, ops, research, product, business, personal, learning." >&2
    exit 2
    ;;
esac

case "$TARGET_FILE" in
  /*|*../*|../*|"")
    echo "Error: --file must be a simple relative file path inside the repo." >&2
    exit 2
    ;;
esac

if [[ ! -d "$REPO_PATH" ]]; then
  echo "Error: repo path not found: $REPO_PATH" >&2
  exit 2
fi

repo_abs="$(cd "$REPO_PATH" && pwd)"
if [[ -z "$DESCRIPTION" ]]; then
  DESCRIPTION="Agentic project work for $NAME."
fi

repo_remote=""
if git -C "$repo_abs" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  raw_remote="$(git -C "$repo_abs" config --get remote.origin.url || true)"
  if [[ "$raw_remote" =~ ^git@github.com:([^/]+/[^/]+)(\.git)?$ ]]; then
    repo_remote="${BASH_REMATCH[1]%.git}"
  elif [[ "$raw_remote" =~ ^https://github.com/([^/]+/[^/]+)(\.git)?$ ]]; then
    repo_remote="${BASH_REMATCH[1]%.git}"
  fi
fi

echo "Central Agent Data Hub project registration"
echo "Project:      $PROJECT"
echo "Name:         $NAME"
echo "Type:         $PROJECT_TYPE"
echo "Repo path:    $repo_abs"
echo "Target file:  $TARGET_FILE"
if [[ -n "$repo_remote" ]]; then
  echo "Repo remote:  $repo_remote"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "Dry run: no DB rows or repo files were written."
  if [[ "$NO_INSTALL" -eq 0 ]]; then
    echo
    echo "Planned repo-local Hub block:"
    cat <<EOF
<!-- CENTRAL-AGENT-DATA-HUB:START -->

## Central Agent Data Hub

Project slug: \`$PROJECT\`

Run Card:
\`$ROOT_DIR/docs/agent-run-card.md\`

Use the Run Card rhythm for substantial work: start with Hub context, work inside
one project boundary, finish with review, and write back only reviewed,
non-sensitive memory.

Use the shared Hub before and after substantial project work:

\`\`\`bash
$ROOT_DIR/scripts/agent_start.sh --project $PROJECT --query "<current focus>"
$ROOT_DIR/scripts/agent_start.sh --project $PROJECT --query "<current focus>" --review
$ROOT_DIR/scripts/agent_finish.sh --project $PROJECT --review
\`\`\`

For reviewed, non-sensitive memory candidates, dry-run first:

\`\`\`bash
$ROOT_DIR/scripts/project_remember.sh \\
  --project $PROJECT \\
  --type fact \\
  --text "Reviewed memory candidate." \\
  --source "non-sensitive source" \\
  --dry-run
\`\`\`

Then write only curated memory:

\`\`\`bash
$ROOT_DIR/scripts/project_remember.sh \\
  --project $PROJECT \\
  --type fact \\
  --text "Reviewed memory candidate." \\
  --source "non-sensitive source"
\`\`\`

Never store passwords, API keys, tokens, FTP credentials, private customer data,
raw invoice data, deployment secrets, unreviewed claims, or assumptions copied
from another project.

<!-- CENTRAL-AGENT-DATA-HUB:END -->
EOF
  fi
  exit 0
fi

if ! "$ROOT_DIR/scripts/agent_preflight.sh" >/dev/null; then
  echo "Operational error: agent preflight failed." >&2
  exit 2
fi

"$PYTHON_BIN" - "$PROJECT" "$NAME" "$DESCRIPTION" "$repo_abs" "$PROJECT_TYPE" "$MEMORY_SCOPE" "$DOMAIN_PROFILE" "$repo_remote" <<'PY'
from __future__ import annotations

import json
import sys

from agent_hub.db import connect

slug, name, description, local_path, project_type, memory_scope, domain_profile, repo_remote = sys.argv[1:]

metadata = {
    "local_path": local_path,
    "project_type": project_type,
    "memory_scope": memory_scope,
    "work_mode": "central-hub-start-finish",
    "registered_by": "scripts/register_project.sh",
}
if domain_profile:
    metadata["domain_profile"] = domain_profile
if repo_remote:
    metadata["repo"] = repo_remote

with connect() as conn:
    with conn.cursor() as cur:
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
            (name, slug, description, json.dumps(metadata)),
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
                f"Coding and implementation agent for {name}.",
                json.dumps({"interface": "codex", "registered_by": "scripts/register_project.sh"}),
            ),
        )
    conn.commit()
PY

echo "Registered Hub project: $PROJECT"

if [[ "$NO_INSTALL" -eq 0 ]]; then
  "$ROOT_DIR/scripts/install_repo_agent_memory.sh" \
    --repo "$repo_abs" \
    --project "$PROJECT" \
    --file "$TARGET_FILE"
fi

echo "Project registration result: ready"
