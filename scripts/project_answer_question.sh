#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/project_answer_question.sh --project <slug> --question-id <uuid> --answer <text> [options]

Safe wrapper for reviewed, non-sensitive open-question resolution.

Required:
  --project <slug>
  --question-id <uuid>
  --answer <text>

Allowed options:
  --status answered|closed   Default: answered.
  --source <value>
  --metadata key=value       Repeatable.
  --dry-run                  Preflight, safety-scan, and show planned update.

Exit codes:
  0  updated or dry-run passed
  1  project, data, or writeback error
  2  usage, safety, or operational readiness error
EOF
}

PROJECT=""
QUESTION_ID=""
ANSWER_TEXT=""
STATUS="answered"
DRY_RUN=0
declare -a ANSWER_ARGS=()
declare -a SAFETY_VALUES=()
declare -a FIELD_NAMES=()

add_option() {
  local option="$1"
  local value="$2"
  ANSWER_ARGS+=("$option" "$value")
  SAFETY_VALUES+=("$value")
  FIELD_NAMES+=("$option")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --question-id)
      QUESTION_ID="${2:-}"
      shift 2
      ;;
    --answer)
      ANSWER_TEXT="${2:-}"
      shift 2
      ;;
    --status)
      STATUS="${2:-}"
      shift 2
      ;;
    --source|--metadata)
      if [[ -z "${2:-}" ]]; then
        echo "Error: $1 requires a value." >&2
        exit 2
      fi
      add_option "$1" "$2"
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

if [[ -z "$PROJECT" || -z "$QUESTION_ID" || -z "$ANSWER_TEXT" ]]; then
  echo "Error: --project, --question-id, and --answer are required." >&2
  usage >&2
  exit 2
fi

case "$STATUS" in
  answered|closed) ;;
  *)
    echo "Error: --status must be answered or closed." >&2
    exit 2
    ;;
esac

if [[ ! "$QUESTION_ID" =~ ^[0-9a-fA-F-]{36}$ ]]; then
  echo "Error: --question-id must be a UUID." >&2
  exit 2
fi

SAFETY_VALUES+=("$PROJECT" "$QUESTION_ID" "$ANSWER_TEXT" "$STATUS")

safety_pattern='password|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|ftp://|ftp[[:space:]_-]*(credentials?|user|password|pass|host)|raw invoice data|private customer data|private kundendaten|private kunden|rechnungsdaten'

shopt -s nocasematch
for value in "${SAFETY_VALUES[@]}"; do
  if [[ "$value" =~ $safety_pattern ]]; then
    echo "Safety error: potential secret or private data detected; refusing update." >&2
    echo "Store only curated, non-sensitive project memory in the Hub." >&2
    exit 2
  fi
done
shopt -u nocasematch

if ! "$ROOT_DIR/scripts/agent_preflight.sh" --compact; then
  echo "Operational error: agent preflight failed." >&2
  exit 2
fi

echo
echo "== Target Project Brief =="
if ! run_agent_hub brief --project "$PROJECT" --limit 4; then
  echo "Data error: project brief unavailable for '$PROJECT'." >&2
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "Dry run: question update was not executed."
  echo "Project:     $PROJECT"
  echo "Question ID: $QUESTION_ID"
  echo "Status:      $STATUS"
  echo "Planned command: agent-hub answer-question --project '$PROJECT' --question-id '$QUESTION_ID' --answer '<provided answer>' --status '$STATUS'"
  echo "Quality gates:"
  echo "- safety scan: ok"
  if [[ "${#FIELD_NAMES[@]}" -gt 0 ]]; then
    echo "Forwarded option names:"
    printf -- "- %s\n" "${FIELD_NAMES[@]}"
  fi
  echo "Project answer result: dry-run ok"
  exit 0
fi

answer_command=(answer-question --project "$PROJECT" --question-id "$QUESTION_ID" --answer "$ANSWER_TEXT" --status "$STATUS")
if [[ "${#ANSWER_ARGS[@]}" -gt 0 ]]; then
  answer_command+=("${ANSWER_ARGS[@]}")
fi
answer_command+=(--format json)

answer_output="$(run_agent_hub "${answer_command[@]}")"

object_id="$(
  printf '%s\n' "$answer_output" | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
print(payload["object"]["id"])
'
)"

echo "Answered open_question for project '$PROJECT': $object_id"
echo "Project answer result: wrote reviewed question update"
