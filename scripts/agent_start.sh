#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/agent_run_lock.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_start.sh --project <slug> [--query <focus>] [--limit <n>] [--review] [--no-lock] [--force-lock]
       scripts/agent_start.sh --all-projects [--limit <n>]
       scripts/agent_start.sh --all-websites [--limit <n>]

Read-only start wrapper for Codex/Hermes work. It runs the operational
preflight through project_context.sh, then prefers a compact compiled project
memory before optional focused context and project review.

Options:
  --project <slug>   Project slug to load.
  --query <focus>    Optional focused context query. Requires --project.
  --all-projects     Load all active projects.
  --all-websites     Domain shortcut for commcats-de, the-one-catering, lamour.
  --limit <n>        Maximum rows per section, default 8.
  --review           Also print the decision/risk/open-question review.
  --no-lock          Skip the local working-tree run lock.
  --force-lock       Replace an existing local working-tree run lock.

Exit codes:
  0  start context loaded
  1  project or data error
  2  usage or operational readiness error
EOF
}

PROJECT=""
QUERY=""
ALL_PROJECTS=0
ALL_WEBSITES=0
LIMIT=8
REVIEW=0
NO_LOCK=0
FORCE_LOCK=0
LOCK_ACQUIRED=0

cleanup_start_lock_on_error() {
  local exit_code=$?
  if [[ "$exit_code" -ne 0 && "$LOCK_ACQUIRED" -eq 1 ]]; then
    agent_run_lock_release "$PROJECT" >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}

trap cleanup_start_lock_on_error EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --query)
      QUERY="${2:-}"
      shift 2
      ;;
    --all-projects)
      ALL_PROJECTS=1
      shift
      ;;
    --all-websites)
      ALL_WEBSITES=1
      shift
      ;;
    --limit)
      LIMIT="${2:-}"
      shift 2
      ;;
    --review)
      REVIEW=1
      shift
      ;;
    --no-lock)
      NO_LOCK=1
      shift
      ;;
    --force-lock)
      FORCE_LOCK=1
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

selected_modes=0
[[ -n "$PROJECT" ]] && selected_modes=$((selected_modes + 1))
[[ "$ALL_PROJECTS" -eq 1 ]] && selected_modes=$((selected_modes + 1))
[[ "$ALL_WEBSITES" -eq 1 ]] && selected_modes=$((selected_modes + 1))

if [[ "$selected_modes" -eq 0 ]]; then
  echo "Error: choose --project <slug>, --all-projects, or --all-websites." >&2
  usage >&2
  exit 2
fi

if [[ "$selected_modes" -gt 1 ]]; then
  echo "Error: --project, --all-projects, and --all-websites are mutually exclusive." >&2
  usage >&2
  exit 2
fi

if [[ -n "$QUERY" && -z "$PROJECT" ]]; then
  echo "Error: --query requires --project." >&2
  exit 2
fi

if [[ "$REVIEW" -eq 1 && -z "$PROJECT" ]]; then
  echo "Error: --review requires --project." >&2
  exit 2
fi

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || (( LIMIT < 1 )); then
  echo "Error: --limit must be a positive integer." >&2
  exit 2
fi

if [[ "$NO_LOCK" -eq 1 && "$FORCE_LOCK" -eq 1 ]]; then
  echo "Error: --no-lock and --force-lock cannot be combined." >&2
  exit 2
fi

if [[ -n "$PROJECT" ]]; then
  echo "== Agent Guard =="
  "$ROOT_DIR/scripts/agent_guard.sh" --project "$PROJECT" --cwd "$PWD"
  echo
fi

if [[ -n "$PROJECT" && "$NO_LOCK" -eq 0 ]]; then
  echo "== Run Lock =="
  if ! agent_run_lock_acquire "$PROJECT" "$FORCE_LOCK"; then
    exit 2
  fi
  LOCK_ACQUIRED=1
  echo
fi

if [[ -n "$PROJECT" ]]; then
  "$ROOT_DIR/scripts/agent_preflight.sh" --compact --allow-direct-db
  echo
  echo "== Compiled Project Memory: $PROJECT =="
  run_agent_hub compile --project "$PROJECT" --limit "$LIMIT"
elif [[ "$ALL_PROJECTS" -eq 1 ]]; then
  context_args=(--limit "$LIMIT")
  context_args=(--all-projects "${context_args[@]}")
  "$ROOT_DIR/scripts/project_context.sh" "${context_args[@]}"
else
  context_args=(--limit "$LIMIT")
  context_args=(--all-websites "${context_args[@]}")
  "$ROOT_DIR/scripts/project_context.sh" "${context_args[@]}"
fi

if [[ -n "$QUERY" ]]; then
  echo
  echo "== Focused Context Pack: $PROJECT =="
  run_agent_hub context --project "$PROJECT" --query "$QUERY" --limit "$LIMIT"
fi

if [[ "$REVIEW" -eq 1 ]]; then
  echo
  echo "== Project Review: $PROJECT =="
  run_agent_hub review --project "$PROJECT" --limit "$LIMIT"
fi

echo
echo "== Agent Working Contract =="
echo "- Work only inside the selected project context."
echo "- Do not transfer assumptions from another project without explicit evidence."
echo "- Do not store secrets, credentials, private customer data, or raw invoice data."
echo "- Treat uncertain information as an open question, not as a fact."
echo "- Prefer one focused task, one reviewed outcome, and one clean handoff."

if [[ -n "$PROJECT" ]]; then
  echo
  echo "== Start Decision =="
  echo "- Status: ready for scoped project work."
  if [[ -n "$QUERY" ]]; then
    echo "- Focus: work on the requested query only unless the user expands scope."
  else
    echo "- Focus: no query was provided; ask for a concrete focus before substantial changes."
  fi
  if [[ "$REVIEW" -eq 1 ]]; then
    echo "- Review loaded: treat visible risks and open questions as constraints."
  else
    echo "- Review not loaded: use --review before risky, broad, or write-heavy work."
  fi
  echo "- If the project context feels wrong or missing: stop and register or clarify the project first."
fi

echo
echo "Agent start result: ready"
if [[ -n "$PROJECT" ]]; then
  echo "Recommended finish:"
  echo "  scripts/agent_finish.sh --project $PROJECT --review"
fi
