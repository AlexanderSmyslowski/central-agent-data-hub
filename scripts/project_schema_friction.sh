#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/project_schema_friction.sh --project <slug> --observed <text> --why <text> [options]

Record a reviewed structure question when useful information does not fit the
existing Hub categories. This does not create a new memory type. It writes an
open question marked with schema_friction metadata.

Required:
  --project <slug>
  --observed <text>      What did not fit cleanly?
  --why <text>           Why fact/decision/risk/report/question is insufficient.

Options:
  --suggestion <text>    Possible category or handling rule.
  --source <value>       Non-sensitive source or review note.
  --dry-run              Run checks and show planned write only.

Exit codes:
  0  wrote or dry-run passed
  1  project, data, or writeback error
  2  usage, safety, or operational readiness error
EOF
}

PROJECT=""
OBSERVED=""
WHY=""
SUGGESTION=""
SOURCE="schema friction review"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --observed)
      OBSERVED="${2:-}"
      shift 2
      ;;
    --why)
      WHY="${2:-}"
      shift 2
      ;;
    --suggestion)
      SUGGESTION="${2:-}"
      shift 2
      ;;
    --source)
      SOURCE="${2:-}"
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

if [[ -z "$PROJECT" || -z "$OBSERVED" || -z "$WHY" ]]; then
  echo "Error: --project, --observed, and --why are required." >&2
  usage >&2
  exit 2
fi

TEXT="Schema friction: how should the Hub classify this information? Observed: $OBSERVED Reason: $WHY"

remember_args=(
  --project "$PROJECT"
  --type open-question
  --text "$TEXT"
  --source "$SOURCE"
  --metadata schema_friction=true
  --metadata observed="$OBSERVED"
  --metadata why="$WHY"
)

if [[ -n "$SUGGESTION" ]]; then
  remember_args+=(--metadata suggestion="$SUGGESTION")
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  remember_args+=(--dry-run)
fi

"$ROOT_DIR/scripts/project_remember.sh" "${remember_args[@]}"
