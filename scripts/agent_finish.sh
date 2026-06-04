#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/agent_run_lock.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_finish.sh --project <slug> [--since <duration|date>] [--write-report] [--limit <n>] [--review] [--export] [--backup] [--no-lock]

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
  --no-lock          Do not release a local working-tree run lock.

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
NO_LOCK=0
UNRESOLVED_QUESTION_COUNT=""
HAS_RECENT_ACTIVITY=0

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
    --no-lock)
      NO_LOCK=1
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

if ! "$ROOT_DIR/scripts/agent_preflight.sh" --compact; then
  echo "Operational error: agent preflight failed." >&2
  exit 2
fi

if recent_activity_json="$(run_agent_hub daily --project "$PROJECT" --since "$SINCE" --limit "$LIMIT" --format json 2>/dev/null)"; then
  HAS_RECENT_ACTIVITY="$(
    printf '%s' "$recent_activity_json" | "$PYTHON_BIN" -c '
import json, sys
payload = json.load(sys.stdin)
keys = ("facts", "decisions", "risks", "open_questions", "reports", "relations", "agent_actions", "sync_events")
print(1 if any(payload.get(key) for key in keys) else 0)
'
  )"
fi

if unresolved_question_count_json="$(run_agent_hub brief --project "$PROJECT" --format json --limit 1 2>/dev/null)"; then
  UNRESOLVED_QUESTION_COUNT="$(
    printf '%s' "$unresolved_question_count_json" | "$PYTHON_BIN" -c \
      'import json, sys; print(len(json.load(sys.stdin).get("open_questions", [])))'
  )"
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
if [[ "$UNRESOLVED_QUESTION_COUNT" =~ ^[0-9]+$ ]] && (( UNRESOLVED_QUESTION_COUNT > 0 )); then
  echo "  scripts/project_answer_question.sh --project $PROJECT --question-id <open-question-uuid> --answer '<reviewed answer>' --source '<source>' --dry-run"
elif [[ "$UNRESOLVED_QUESTION_COUNT" =~ ^[0-9]+$ ]]; then
  echo "- No unresolved open questions are currently visible for this project."
else
  echo "  scripts/project_answer_question.sh --project $PROJECT --question-id <open-question-uuid> --answer '<reviewed answer>' --source '<source>' --dry-run"
fi

echo
echo "== Next Best Step =="
echo "- If nothing durable changed: store no memory."
echo "- If a useful fact, decision, risk, question, answer, or report emerged: dry-run exactly 1-3 reviewed writebacks."
if [[ "$WRITE_REPORT" -eq 1 ]]; then
  echo "- Because --write-report was used: verify it with scripts/memory_receipt.sh --project $PROJECT --type report --since $SINCE."
elif [[ "$HAS_RECENT_ACTIVITY" == "1" ]]; then
  echo "- If this run needs a durable handoff: rerun with --write-report or store a reviewed report via scripts/project_remember.sh."
else
  echo "- No durable handoff is visible in this window; skip report writeback unless you want a manual checkpoint."
fi
if [[ "$EXPORT" -eq 0 ]]; then
  if [[ "$WRITE_REPORT" -eq 1 ]]; then
    echo "- This finish step wrote a report; export now with scripts/agent_finish.sh --project $PROJECT --review --export, or run agent-hub export directly."
  else
    echo "- Export only if you write reviewed memory after this finish step."
  fi
fi
if [[ "$BACKUP" -eq 0 ]]; then
  if [[ "$WRITE_REPORT" -eq 1 ]]; then
    echo "- This finish step wrote durable memory; run scripts/db_backup.sh after export."
  else
    echo "- Backup only if you write or export important reviewed memory after this finish step."
  fi
fi

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

if [[ "$NO_LOCK" -eq 0 ]]; then
  echo
  echo "== Run Lock =="
  agent_run_lock_release "$PROJECT"
fi

echo
echo "Agent finish result: ready for reviewed writeback or handoff"
