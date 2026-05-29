#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/project_remember.sh --project <slug> --type <type> --text <text> [options]

Safe writeback wrapper for reviewed, non-sensitive project memory. The project
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
  --dry-run                  Preflight, safety-scan, and show planned write.

Exit codes:
  0  remembered or dry-run passed
  1  project, data, or writeback error
  2  usage, safety, or operational readiness error
EOF
}

PROJECT=""
MEMORY_TYPE=""
TEXT_VALUE=""
DRY_RUN=0
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
      add_option "$1" "$2"
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

SAFETY_VALUES+=("$PROJECT" "$MEMORY_TYPE" "$TEXT_VALUE")
FIELD_NAMES+=("--project" "--type" "--text")

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

if ! "$ROOT_DIR/scripts/agent_preflight.sh"; then
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
  echo "Dry run: writeback was not executed."
  echo "Planned command: agent-hub remember --project '$PROJECT' --type '$MEMORY_TYPE' --text '<provided text>'"
  if [[ "${#FIELD_NAMES[@]}" -gt 3 ]]; then
    echo "Forwarded option names:"
    printf -- "- %s\n" "${FIELD_NAMES[@]:0:${#FIELD_NAMES[@]}-3}"
  fi
  echo "Project remember result: dry-run ok"
  exit 0
fi

run_agent_hub remember \
  --project "$PROJECT" \
  --type "$MEMORY_TYPE" \
  --text "$TEXT_VALUE" \
  "${REMEMBER_ARGS[@]}"

echo "Project remember result: wrote reviewed memory"
