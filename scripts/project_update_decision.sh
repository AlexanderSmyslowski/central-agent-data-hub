#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/project_update_decision.sh --project <slug> --decision-id <uuid> [options]

Safe wrapper for reviewed, non-sensitive decision updates.

Required:
  --project <slug>
  --decision-id <uuid>

At least one of:
  --rationale <text>
  --consequences <text>
  --status proposed|accepted|rejected|superseded|archived
  --metadata key=value

Allowed options:
  --source <value>
  --dry-run                  Preflight, safety-scan, and show planned update.

Exit codes:
  0  updated or dry-run passed
  1  project, data, or writeback error
  2  usage, safety, or operational readiness error
EOF
}

PROJECT=""
DECISION_ID=""
DRY_RUN=0
HAS_CHANGE=0
declare -a UPDATE_ARGS=()
declare -a SAFETY_VALUES=()
declare -a FIELD_NAMES=()

add_option() {
  local option="$1"
  local value="$2"
  UPDATE_ARGS+=("$option" "$value")
  SAFETY_VALUES+=("$value")
  FIELD_NAMES+=("$option")
  HAS_CHANGE=1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --decision-id)
      DECISION_ID="${2:-}"
      shift 2
      ;;
    --rationale|--consequences|--status|--source|--metadata)
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

if [[ -z "$PROJECT" || -z "$DECISION_ID" ]]; then
  echo "Error: --project and --decision-id are required." >&2
  usage >&2
  exit 2
fi

if [[ "$HAS_CHANGE" -eq 0 ]]; then
  echo "Error: provide at least one change such as --rationale, --consequences, --status, or --metadata." >&2
  exit 2
fi

if [[ ! "$DECISION_ID" =~ ^[0-9a-fA-F-]{36}$ ]]; then
  echo "Error: --decision-id must be a UUID." >&2
  exit 2
fi

SAFETY_VALUES+=("$PROJECT" "$DECISION_ID")

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
  echo "Dry run: decision update was not executed."
  echo "Project:      $PROJECT"
  echo "Decision ID:  $DECISION_ID"
  echo "Planned command: agent-hub update-decision --project '$PROJECT' --decision-id '$DECISION_ID' <provided changes>"
  echo "Quality gates:"
  echo "- safety scan: ok"
  echo "- change set: ok"
  if [[ "${#FIELD_NAMES[@]}" -gt 0 ]]; then
    echo "Forwarded option names:"
    printf -- "- %s\n" "${FIELD_NAMES[@]}"
  fi
  echo "Project decision update result: dry-run ok"
  exit 0
fi

update_command=(update-decision --project "$PROJECT" --decision-id "$DECISION_ID")
if [[ "${#UPDATE_ARGS[@]}" -gt 0 ]]; then
  update_command+=("${UPDATE_ARGS[@]}")
fi
update_command+=(--format json)

update_output="$(run_agent_hub "${update_command[@]}")"

object_id="$(
  printf '%s\n' "$update_output" | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
print(payload["object"]["id"])
'
)"

echo "Updated decision for project '$PROJECT': $object_id"
echo "Project decision update result: wrote reviewed decision update"
