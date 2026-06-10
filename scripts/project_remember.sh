#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/project_remember.sh --project <slug> --type <type> --text <text> [options]

Review-routed wrapper for non-sensitive project memory candidates. The project
must already exist; this wrapper never creates projects.

Required:
  --project <slug>
  --type fact|decision|open-question|risk|report
  --text <text>

Allowed options:
  --source <value>
  --confidence <0..1>
  --status <value>
  --metadata key=value        Repeatable.
  --rationale <text>
  --consequences <text>
  --answer <text>
  --severity low|medium|high|critical
  --impact <text>
  --mitigation <text>
  --title <text>
  --report-type <value>
  --summary <text>
  --body <text>
  --relate-to <type:uuid>     Relate the new memory to an existing Hub object.
  --relation <relation_type>  Relation type for --relate-to.
  --dry-run                  Preflight, safety-scan, and show planned write.

Exit codes:
  0  remembered or dry-run passed
  1  project, data, review, or write error
  2  usage, safety, or operational readiness error
EOF
}

PROJECT=""
MEMORY_TYPE=""
TEXT_VALUE=""
DRY_RUN=0
HAS_SOURCE=0
HAS_RATIONALE=0
RELATE_TO=""
RELATION=""
declare -a REMEMBER_ARGS=()
declare -a SAFETY_VALUES=()
declare -a FIELD_NAMES=()

add_option() {
  local option="$1"
  local value="$2"
  REMEMBER_ARGS+=("$option" "$value")
  SAFETY_VALUES+=("$value")
  FIELD_NAMES+=("$option")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --type)
      MEMORY_TYPE="${2:-}"
      shift 2
      ;;
    --text)
      TEXT_VALUE="${2:-}"
      shift 2
      ;;
    --source|--confidence|--status|--metadata|--rationale|--consequences|--answer|--severity|--impact|--mitigation|--title|--report-type|--summary|--body)
      if [[ -z "${2:-}" ]]; then
        echo "Error: $1 requires a value." >&2
        exit 2
      fi
      [[ "$1" == "--source" ]] && HAS_SOURCE=1
      [[ "$1" == "--rationale" ]] && HAS_RATIONALE=1
      add_option "$1" "$2"
      shift 2
      ;;
    --relate-to)
      if [[ -z "${2:-}" ]]; then
        echo "Error: --relate-to requires a value." >&2
        exit 2
      fi
      RELATE_TO="$2"
      SAFETY_VALUES+=("$2")
      shift 2
      ;;
    --relation)
      if [[ -z "${2:-}" ]]; then
        echo "Error: --relation requires a value." >&2
        exit 2
      fi
      RELATION="$2"
      SAFETY_VALUES+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --create-project)
      echo "Error: --create-project is blocked by project_remember.sh." >&2
      echo "Create projects only through reviewed seed/migration changes." >&2
      exit 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown or blocked argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PROJECT" || -z "$MEMORY_TYPE" || -z "$TEXT_VALUE" ]]; then
  echo "Error: --project, --type, and --text are required." >&2
  usage >&2
  exit 2
fi

case "$MEMORY_TYPE" in
  fact|decision|open-question|risk|report) ;;
  *)
    echo "Error: unsupported --type '$MEMORY_TYPE'." >&2
    exit 2
    ;;
esac

if [[ -n "$RELATE_TO" || -n "$RELATION" ]]; then
  if [[ -z "$RELATE_TO" || -z "$RELATION" ]]; then
    echo "Error: --relate-to and --relation must be used together." >&2
    exit 2
  fi
  if [[ ! "$RELATE_TO" =~ ^(project|agent|document|report|decision|fact|open_question|risk|agent_action):[0-9a-fA-F-]{36}$ ]]; then
    echo "Error: --relate-to must use <type:uuid>, for example fact:00000000-0000-4000-8000-000000000000." >&2
    exit 2
  fi
  case "$RELATION" in
    supports|contradicts|supersedes|mitigates|answers|raises|references|derived_from|blocks|depends_on) ;;
    *)
      echo "Error: unsupported --relation '$RELATION'." >&2
      exit 2
      ;;
  esac
fi

SAFETY_VALUES+=("$PROJECT" "$MEMORY_TYPE" "$TEXT_VALUE")

safety_pattern='password|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|ftp://|ftp[[:space:]_-]*(credentials?|user|password|pass|host)|raw invoice data|private customer data|private kundendaten|private kunden|rechnungsdaten'

shopt -s nocasematch
for value in "${SAFETY_VALUES[@]}"; do
  if [[ "$value" =~ $safety_pattern ]]; then
    echo "Safety error: potential secret or private data detected; refusing writeback." >&2
    echo "Store only curated, non-sensitive project memory in the Hub." >&2
    exit 2
  fi
done
shopt -u nocasematch

if [[ "$MEMORY_TYPE" == "fact" && "$HAS_SOURCE" -eq 0 ]]; then
  echo "Quality error: facts require --source for traceability." >&2
  exit 2
fi

DECISION_RATIONALE_WARNING=0
if [[ "$MEMORY_TYPE" == "decision" && "$HAS_RATIONALE" -eq 0 ]]; then
  DECISION_RATIONALE_WARNING=1
  echo "Quality warning: decisions should include --rationale." >&2
fi

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
  dry_run_command=(remember --project "$PROJECT" --type "$MEMORY_TYPE" --text "$TEXT_VALUE" --dry-run --format json)
  if [[ "${#REMEMBER_ARGS[@]}" -gt 0 ]]; then
    dry_run_command+=("${REMEMBER_ARGS[@]}")
  fi
  if ! dry_run_output="$(run_agent_hub "${dry_run_command[@]}")"; then
    printf '%s\n' "$dry_run_output"
    exit 1
  fi
  dry_run_summary="$(
    printf '%s\n' "$dry_run_output" | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
print(f"Route:  {payload[\"tier\"]}")
print(f"Status: {payload[\"status\"] or \"default\"}")
print(f"Reason: {payload[\"reason\"]}")
'
  )"
  echo
  echo "Dry run: memory was not written."
  echo "Project: $PROJECT"
  echo "Type:    $MEMORY_TYPE"
  echo "Planned command: agent-hub remember --project '$PROJECT' --type '$MEMORY_TYPE' --text '<provided text>'"
  printf '%s\n' "$dry_run_summary"
  echo "Quality gates:"
  if [[ "$MEMORY_TYPE" == "fact" ]]; then
    echo "- source: ok"
  fi
  if [[ "$MEMORY_TYPE" == "decision" && "$DECISION_RATIONALE_WARNING" -eq 0 ]]; then
    echo "- rationale: ok"
  elif [[ "$MEMORY_TYPE" == "decision" ]]; then
    echo "- rationale: warning"
  fi
  echo "- safety scan: ok"
  if [[ "${#FIELD_NAMES[@]}" -gt 0 ]]; then
    echo "Forwarded option names:"
    printf -- "- %s\n" "${FIELD_NAMES[@]}"
  fi
  if [[ -n "$RELATE_TO" ]]; then
    echo "Planned relation:"
    echo "- new $MEMORY_TYPE --$RELATION--> $RELATE_TO"
  fi
  echo "Project remember result: dry-run ok"
  exit 0
fi

remember_command=(remember --project "$PROJECT" --type "$MEMORY_TYPE" --text "$TEXT_VALUE")
if [[ "${#REMEMBER_ARGS[@]}" -gt 0 ]]; then
  remember_command+=("${REMEMBER_ARGS[@]}")
fi
remember_command+=(--format json)

if ! remember_output="$(run_agent_hub "${remember_command[@]}")"; then
  printf '%s\n' "$remember_output"
  exit 1
fi

object_type="$(
  printf '%s\n' "$remember_output" | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
print(payload["type"])
'
)"
object_id="$(
  printf '%s\n' "$remember_output" | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
print(payload["object"]["id"])
'
)"
object_status="$(
  printf '%s\n' "$remember_output" | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
print(payload["object"].get("status", "unknown"))
'
)"

echo "Remembered $object_type for project '$PROJECT': $object_id ($object_status)"
echo "Project remember result: wrote memory candidate"

if [[ -n "$RELATE_TO" ]]; then
  target_type="${RELATE_TO%%:*}"
  target_id="${RELATE_TO#*:}"
  run_agent_hub relate \
    --project "$PROJECT" \
    --source-type "$object_type" \
    --source-id "$object_id" \
    --relation "$RELATION" \
    --target-type "$target_type" \
    --target-id "$target_id" \
    --metadata created_by=project_remember.sh
  echo "Project remember relation result: wrote curated relation"
fi
