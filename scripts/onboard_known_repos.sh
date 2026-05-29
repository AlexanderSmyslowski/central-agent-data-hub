#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

APPLY=0
PROJECT_TYPE=""
TARGET_FILE="AGENTS.md"

usage() {
  cat <<'EOF'
Usage: scripts/onboard_known_repos.sh [--dry-run|--apply] [options]

Onboards active Hub projects that explicitly define metadata.local_path. Default
mode is --dry-run. No filesystem scan is performed.

Options:
  --dry-run          Show which known repos would be updated. Default.
  --apply            Install/update repo-local Hub blocks.
  --type <type>      Filter by projects.metadata.project_type.
  --file <name>      Target file inside each repo. Default: AGENTS.md.

Exit codes:
  0  completed
  1  project or data error
  2  usage or operational readiness error
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      APPLY=0
      shift
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --type)
      PROJECT_TYPE="${2:-}"
      shift 2
      ;;
    --file)
      TARGET_FILE="${2:-}"
      shift 2
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

case "$TARGET_FILE" in
  /*|*../*|../*|"")
    echo "Error: --file must be a simple relative file path inside each repo." >&2
    exit 2
    ;;
esac

if ! "$ROOT_DIR/scripts/agent_preflight.sh" >/dev/null; then
  echo "Operational error: agent preflight failed." >&2
  exit 2
fi

project_args=(--format json)
if [[ -n "$PROJECT_TYPE" ]]; then
  project_args+=(--type "$PROJECT_TYPE")
fi

projects_json="$(run_agent_hub projects "${project_args[@]}")" || {
  echo "Data error: active project list unavailable." >&2
  exit 1
}

project_rows=()
while IFS= read -r project_row; do
  project_rows+=("$project_row")
done < <(
  printf '%s\n' "$projects_json" | "$PYTHON_BIN" -c '
import json
import sys

for project in json.load(sys.stdin):
    metadata = project.get("metadata") or {}
    slug = project["slug"]
    local_path = metadata.get("local_path")
    if local_path:
        print(f"{slug}\t{local_path}")
'
)

echo "Central Agent Data Hub known repo onboarding"
if [[ "$APPLY" -eq 1 ]]; then
  echo "Mode:   apply"
else
  echo "Mode:   dry-run"
fi
echo "Target: $TARGET_FILE"
if [[ -n "$PROJECT_TYPE" ]]; then
  echo "Type:   $PROJECT_TYPE"
fi
echo

if [[ "${#project_rows[@]}" -eq 0 ]]; then
  echo "No active projects with metadata.local_path found."
  exit 0
fi

updated=0
skipped=0

for row in "${project_rows[@]}"; do
  project_slug="${row%%$'\t'*}"
  repo_path="${row#*$'\t'}"

  if [[ ! -d "$repo_path" ]]; then
    echo "skip: $project_slug local_path not found: $repo_path"
    skipped=$((skipped + 1))
    continue
  fi

  if [[ "$APPLY" -eq 1 ]]; then
    echo "apply: $project_slug -> $repo_path/$TARGET_FILE"
    "$ROOT_DIR/scripts/install_repo_agent_memory.sh" \
      --repo "$repo_path" \
      --project "$project_slug" \
      --file "$TARGET_FILE"
    updated=$((updated + 1))
  else
    echo "would update: $project_slug -> $repo_path/$TARGET_FILE"
    updated=$((updated + 1))
  fi
done

echo
if [[ "$APPLY" -eq 1 ]]; then
  echo "Known repo onboarding result: applied=$updated skipped=$skipped"
else
  echo "Known repo onboarding result: dry-run=$updated skipped=$skipped"
  echo "Run with --apply to write repo-local Hub blocks."
fi
