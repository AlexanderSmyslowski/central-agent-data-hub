#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

PROJECT=""
REPO_PATH=""
TARGET_FILE="AGENTS.md"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/install_repo_agent_memory.sh --repo <path> --project <slug> [options]

Installs or updates a marked Central Agent Data Hub block in a repo-local agent
instruction file, without replacing existing project instructions.

Options:
  --repo <path>       Target repository or project directory.
  --project <slug>    Existing Central Agent Data Hub project slug.
  --file <name>       Target file inside the repo. Default: AGENTS.md.
  --dry-run           Print planned target and block, but do not write.

Exit codes:
  0  installed, updated, or dry-run completed
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
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --file)
      TARGET_FILE="${2:-}"
      shift 2
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

if [[ -z "$REPO_PATH" || -z "$PROJECT" ]]; then
  echo "Error: --repo and --project are required." >&2
  usage >&2
  exit 2
fi

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
target_path="$repo_abs/$TARGET_FILE"
target_dir="$(dirname "$target_path")"

if [[ "$target_dir" != "$repo_abs"* ]]; then
  echo "Error: target file resolves outside repo: $TARGET_FILE" >&2
  exit 2
fi

if ! "$ROOT_DIR/scripts/agent_preflight.sh" >/dev/null; then
  echo "Operational error: agent preflight failed." >&2
  exit 2
fi

if ! run_agent_hub brief --project "$PROJECT" --limit 1 >/dev/null; then
  echo "Data error: project brief unavailable for '$PROJECT'." >&2
  exit 1
fi

block="$(
  cat <<EOF
<!-- CENTRAL-AGENT-DATA-HUB:START -->

## Central Agent Data Hub

Project slug: \`$PROJECT\`

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
)"

echo "Central Agent Data Hub repo memory installer"
echo "Repo:    $repo_abs"
echo "Project: $PROJECT"
echo "Target:  $target_path"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "Dry run: no files were written."
  echo
  printf '%s\n' "$block"
  exit 0
fi

mkdir -p "$target_dir"

"$PYTHON_BIN" - "$target_path" "$block" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

target = Path(sys.argv[1])
block = sys.argv[2].rstrip() + "\n"
start = "<!-- CENTRAL-AGENT-DATA-HUB:START -->"
end = "<!-- CENTRAL-AGENT-DATA-HUB:END -->"

if target.exists():
    original = target.read_text(encoding="utf-8")
else:
    original = ""

if start in original and end in original:
    before = original.split(start, 1)[0].rstrip()
    after = original.split(end, 1)[1].lstrip()
    parts = []
    if before:
        parts.append(before)
    parts.append(block.rstrip())
    if after:
        parts.append(after.rstrip())
    updated = "\n\n".join(parts) + "\n"
elif original.strip():
    updated = original.rstrip() + "\n\n" + block
else:
    updated = block

target.write_text(updated, encoding="utf-8")
PY

echo "Installed or updated Hub memory block."
