#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/project_context.sh --project <slug>
       scripts/project_context.sh --all-projects
       scripts/project_context.sh --all-websites

Runs the read-only agent preflight, then prints the project memory brief that an
agent should read before project work.

Options:
  --project <slug>   Project slug to brief.
  --all-projects     Brief all active projects from the Hub database.
  --all-websites     Domain shortcut for commcats-de, the-one-catering, and lamour.
  --limit <n>        Maximum rows per brief section, default 8.
  --daily            Also print the last 24h project activity summary.

Exit codes:
  0  context loaded
  1  project or data error
  2  usage or operational readiness error
EOF
}

PROJECT=""
ALL_PROJECTS=0
ALL_WEBSITES=0
LIMIT=8
DAILY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --all-projects)
      ALL_PROJECTS=1
      shift
      ;;
    --all-websites)
      ALL_WEBSITES=1
      shift
      ;;
    --limit)
      LIMIT="${2:-}"
      shift 2
      ;;
    --daily)
      DAILY=1
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

selected_modes=0
[[ -n "$PROJECT" ]] && selected_modes=$((selected_modes + 1))
[[ "$ALL_PROJECTS" -eq 1 ]] && selected_modes=$((selected_modes + 1))
[[ "$ALL_WEBSITES" -eq 1 ]] && selected_modes=$((selected_modes + 1))

if [[ "$selected_modes" -eq 0 ]]; then
  echo "Error: choose --project <slug>, --all-projects, or --all-websites." >&2
  usage >&2
  exit 2
fi

if [[ "$selected_modes" -gt 1 ]]; then
  echo "Error: --project, --all-projects, and --all-websites are mutually exclusive." >&2
  usage >&2
  exit 2
fi

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || (( LIMIT < 1 )); then
  echo "Error: --limit must be a positive integer." >&2
  exit 2
fi

if ! "$ROOT_DIR/scripts/agent_preflight.sh"; then
  echo "Operational error: agent preflight failed." >&2
  exit 2
fi

print_brief() {
  local project_slug="$1"
  echo
  echo "== Project Context: $project_slug =="
  if ! run_agent_hub brief --project "$project_slug" --limit "$LIMIT"; then
    echo "Data error: project brief unavailable for '$project_slug'." >&2
    return 1
  fi
  if [[ "$DAILY" -eq 1 ]]; then
    echo
    echo "== Daily Activity: $project_slug =="
    if ! run_agent_hub daily --project "$project_slug" --since 24h --limit "$LIMIT"; then
      echo "Data error: project daily activity unavailable for '$project_slug'." >&2
      return 1
    fi
  fi
}

if [[ "$ALL_PROJECTS" -eq 1 ]]; then
  projects_json="$(run_agent_hub projects --format json)" || {
    echo "Data error: active project list unavailable." >&2
    exit 1
  }
  project_slugs=()
  while IFS= read -r project_slug; do
    project_slugs+=("$project_slug")
  done < <(
    printf '%s\n' "$projects_json" | "$PYTHON_BIN" -c '
import json
import sys

for project in json.load(sys.stdin):
    print(project["slug"])
'
  )
  if [[ "${#project_slugs[@]}" -eq 0 ]]; then
    echo "Data error: no active projects found." >&2
    exit 1
  fi
  for project_slug in "${project_slugs[@]}"; do
    print_brief "$project_slug" || exit 1
  done
elif [[ "$ALL_WEBSITES" -eq 1 ]]; then
  for project_slug in commcats-de the-one-catering lamour; do
    print_brief "$project_slug" || exit 1
  done
else
  print_brief "$PROJECT" || exit 1
fi

echo
echo "Project context result: ready"
