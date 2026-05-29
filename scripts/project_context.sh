#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/project_context.sh --project <slug>
       scripts/project_context.sh --all-websites

Runs the read-only agent preflight, then prints the project memory brief that an
agent should read before website work.

Options:
  --project <slug>   Project slug to brief.
  --all-websites     Brief commcats-de, the-one-catering, and lamour.
  --limit <n>        Maximum rows per brief section, default 8.

Exit codes:
  0  context loaded
  1  project or data error
  2  usage or operational readiness error
EOF
}

PROJECT=""
ALL_WEBSITES=0
LIMIT=8

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
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

if [[ -z "$PROJECT" && "$ALL_WEBSITES" -eq 0 ]]; then
  echo "Error: choose --project <slug> or --all-websites." >&2
  usage >&2
  exit 2
fi

if [[ -n "$PROJECT" && "$ALL_WEBSITES" -eq 1 ]]; then
  echo "Error: --project and --all-websites are mutually exclusive." >&2
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
}

if [[ "$ALL_WEBSITES" -eq 1 ]]; then
  for project_slug in commcats-de the-one-catering lamour; do
    print_brief "$project_slug" || exit 1
  done
else
  print_brief "$PROJECT" || exit 1
fi

echo
echo "Project context result: ready"
