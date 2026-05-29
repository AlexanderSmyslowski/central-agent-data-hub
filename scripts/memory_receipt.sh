#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/memory_receipt.sh --project <slug> [options]

Verifies that recent reviewed project memory exists and has been exported to
Obsidian Markdown. Use this after another agent/channel reports that it wrote
to the Hub.

Options:
  --project <slug>        Project slug to verify.
  --since <value>         Duration like 24h, 7d, 2w or ISO date. Default: 24h.
  --type <type>           all|fact|decision|risk|open_question|report|agent_action.
                          Default: all.
  --limit <n>             Maximum receipt rows. Default: 12.
  --json                  Output JSON from agent-hub receipt.
  --no-require-exported   Do not fail when matching rows lack exported Markdown.

Exit codes:
  0  matching memory exists and export requirements are satisfied
  1  no matching memory, missing export, or data error
  2  usage or operational readiness error
EOF
}

PROJECT=""
SINCE="24h"
MEMORY_TYPE="all"
LIMIT=12
FORMAT="text"
REQUIRE_EXPORTED=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --since)
      SINCE="${2:-}"
      shift 2
      ;;
    --type)
      MEMORY_TYPE="${2:-}"
      shift 2
      ;;
    --limit)
      LIMIT="${2:-}"
      shift 2
      ;;
    --json)
      FORMAT="json"
      shift
      ;;
    --no-require-exported)
      REQUIRE_EXPORTED=0
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

if [[ -z "$PROJECT" ]]; then
  echo "Error: --project is required." >&2
  usage >&2
  exit 2
fi

case "$MEMORY_TYPE" in
  all|fact|decision|risk|open_question|report|agent_action) ;;
  *)
    echo "Error: unsupported --type '$MEMORY_TYPE'." >&2
    exit 2
    ;;
esac

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || (( LIMIT < 1 )); then
  echo "Error: --limit must be a positive integer." >&2
  exit 2
fi

if ! "$ROOT_DIR/scripts/agent_preflight.sh"; then
  echo "Operational error: agent preflight failed." >&2
  exit 2
fi

receipt_args=(
  receipt
  --project "$PROJECT"
  --since "$SINCE"
  --type "$MEMORY_TYPE"
  --limit "$LIMIT"
  --format "$FORMAT"
  --require-results
)

if [[ "$REQUIRE_EXPORTED" -eq 1 ]]; then
  receipt_args+=(--require-exported)
fi

run_agent_hub "${receipt_args[@]}"
