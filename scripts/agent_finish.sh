#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_finish.sh --project <slug> [--since <duration|date>] [--write-report] [--limit <n>]

Finish wrapper for Codex/Hermes work. It runs read-only operational preflight,
prints a daily summary and handoff, and optionally stores a daily report.

This script does not write facts, decisions, risks, or questions. Use
scripts/project_remember.sh for reviewed, non-sensitive memory writeback.

Options:
  --project <slug>   Project slug to finish.
  --since <value>    Duration like 24h, 7d, 2w or ISO date. Default: 24h.
  --write-report     Store the daily summary as a published report row.
  --limit <n>        Maximum rows per section, default 8.

Exit codes:
  0  finish summary completed
  1  project or data error
  2  usage or operational readiness error
EOF
}

PROJECT=""
SINCE="24h"
WRITE_REPORT=0
LIMIT=8

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
    --write-report)
      WRITE_REPORT=1
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

if [[ -z "$PROJECT" ]]; then
  echo "Error: --project is required." >&2
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

echo
echo "== Daily Finish Summary: $PROJECT =="
daily_args=(--project "$PROJECT" --since "$SINCE" --limit "$LIMIT")
if [[ "$WRITE_REPORT" -eq 1 ]]; then
  daily_args+=(--write-report)
fi
if ! run_agent_hub daily "${daily_args[@]}"; then
  echo "Data error: daily finish summary failed for '$PROJECT'." >&2
  exit 1
fi

echo
echo "== Handoff: $PROJECT =="
if ! run_agent_hub handoff --project "$PROJECT" --since "$SINCE" --limit "$LIMIT"; then
  echo "Data error: handoff failed for '$PROJECT'." >&2
  exit 1
fi

echo
echo "Memory writeback reminder:"
echo "- Store only reviewed, non-sensitive memory."
echo "- Facts require --source."
echo "- Prefer dry-run when unsure:"
echo "  scripts/project_remember.sh --project $PROJECT --type fact --text '<reviewed memory>' --source '<source>' --dry-run"
echo
echo "Agent finish result: ready for reviewed writeback or handoff"
