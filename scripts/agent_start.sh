#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_start.sh --project <slug> [--query <focus>] [--limit <n>]
       scripts/agent_start.sh --all-projects [--limit <n>]
       scripts/agent_start.sh --all-websites [--limit <n>]

Read-only start wrapper for Codex/Hermes work. It runs the operational
preflight through project_context.sh, loads the daily project context, and
optionally prints a focused context pack.

Options:
  --project <slug>   Project slug to load.
  --query <focus>    Optional focused context query. Requires --project.
  --all-projects     Load all active projects.
  --all-websites     Domain shortcut for commcats-de, the-one-catering, lamour.
  --limit <n>        Maximum rows per section, default 8.

Exit codes:
  0  start context loaded
  1  project or data error
  2  usage or operational readiness error
EOF
}

PROJECT=""
QUERY=""
ALL_PROJECTS=0
ALL_WEBSITES=0
LIMIT=8

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --query)
      QUERY="${2:-}"
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

if [[ -n "$QUERY" && -z "$PROJECT" ]]; then
  echo "Error: --query requires --project." >&2
  exit 2
fi

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || (( LIMIT < 1 )); then
  echo "Error: --limit must be a positive integer." >&2
  exit 2
fi

context_args=(--limit "$LIMIT" --daily)
if [[ -n "$PROJECT" ]]; then
  context_args=(--project "$PROJECT" "${context_args[@]}")
elif [[ "$ALL_PROJECTS" -eq 1 ]]; then
  context_args=(--all-projects "${context_args[@]}")
else
  context_args=(--all-websites "${context_args[@]}")
fi

"$ROOT_DIR/scripts/project_context.sh" "${context_args[@]}"

if [[ -n "$QUERY" ]]; then
  echo
  echo "== Focused Context Pack: $PROJECT =="
  run_agent_hub context --project "$PROJECT" --query "$QUERY" --limit "$LIMIT"
fi

echo
echo "Agent start result: ready"
if [[ -n "$PROJECT" ]]; then
  echo "Recommended finish:"
  echo "  scripts/agent_finish.sh --project $PROJECT"
fi
