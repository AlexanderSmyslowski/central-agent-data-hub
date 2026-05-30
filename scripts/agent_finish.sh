#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_finish.sh --project <slug> [--since <duration|date>] [--write-report] [--limit <n>] [--review] [--export] [--backup]

Finish wrapper for Codex/Hermes work. It runs read-only operational preflight,
prints a daily summary, handoff, and recent audited agent actions, and optionally
stores a daily report, exports Obsidian Markdown, and creates a verified backup.

This script does not write facts, decisions, risks, or questions. Use
scripts/project_remember.sh for reviewed, non-sensitive memory writeback.

Options:
  --project <slug>   Project slug to finish.
  --since <value>    Duration like 24h, 7d, 2w or ISO date. Default: 24h.
  --write-report     Store the daily summary as a published report row.
  --limit <n>        Maximum rows per section, default 8.
  --review           Also print decision/risk/open-question review.
  --export           Export current Hub memory to Obsidian Markdown after finish.
  --backup           Create local/remote DB backup after finish.

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
REVIEW=0
EXPORT=0
BACKUP=0

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
    --review)
      REVIEW=1
      shift
      ;;
    --export)
      EXPORT=1
      shift
      ;;
    --backup)
      BACKUP=1
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

if [[ "$REVIEW" -eq 1 ]]; then
  echo
  echo "== Review: $PROJECT =="
  if ! run_agent_hub review --project "$PROJECT" --limit "$LIMIT"; then
    echo "Data error: review failed for '$PROJECT'." >&2
    exit 1
  fi
fi

echo
echo "== Memory Triage =="
echo "Store less, but better. Write back only reviewed memory that will help a later agent."
echo
echo "Usually worth remembering:"
echo "- Fact: stable, checked information with source and confidence."
echo "- Decision: chosen direction with rationale or tradeoff."
echo "- Risk: active risk with impact or mitigation."
echo "- Open question: real blocker or unknown that needs a later answer."
echo "- Report: compact handoff, audit, daily summary, or review note."
echo
echo "Usually not worth remembering:"
echo "- Raw chat history, temporary guesses, transient todo noise, private data, credentials, raw invoices."
echo
echo "Suggested dry-runs:"
echo "  scripts/project_remember.sh --project $PROJECT --type fact --text '<reviewed fact>' --source '<source>' --confidence 0.9 --dry-run"
echo "  scripts/project_remember.sh --project $PROJECT --type decision --text '<decision>' --rationale '<why>' --dry-run"
echo "  scripts/project_remember.sh --project $PROJECT --type open-question --text '<question>' --dry-run"

if [[ "$EXPORT" -eq 1 ]]; then
  echo
  echo "== Obsidian Export =="
  if ! run_agent_hub export; then
    echo "Operational error: Obsidian export failed." >&2
    exit 2
  fi
fi

if [[ "$BACKUP" -eq 1 ]]; then
  echo
  echo "== Database Backup =="
  if ! "$ROOT_DIR/scripts/db_backup.sh"; then
    echo "Operational error: database backup failed." >&2
    exit 2
  fi
fi

echo
echo "== Recent Agent Actions: $PROJECT =="
if ! run_agent_hub actions --project "$PROJECT" --since "$SINCE" --limit "$LIMIT"; then
  echo "Data error: recent agent actions failed for '$PROJECT'." >&2
  exit 1
fi

echo
echo "Agent finish result: ready for reviewed writeback or handoff"
