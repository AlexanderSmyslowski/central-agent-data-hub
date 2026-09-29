#!/usr/bin/env bash

AGENT_HUB_RUN_LOCK_ROOT="${SHARED_ROOT:-$ROOT_DIR}"
AGENT_HUB_RUN_LOCK_DIR="${AGENT_HUB_RUN_LOCK_ROOT}/.local/run-locks"
AGENT_HUB_RUN_LOCK_MAX_AGE_SECONDS="${AGENT_HUB_RUN_LOCK_MAX_AGE_SECONDS:-43200}"

agent_run_lock_command() {
  "$PYTHON_BIN" "$ROOT_DIR/scripts/agent_run_lock.py" \
    --lock-dir "$AGENT_HUB_RUN_LOCK_DIR" \
    --max-age "$AGENT_HUB_RUN_LOCK_MAX_AGE_SECONDS" "$@"
}

agent_run_repo_root() {
  agent_run_lock_command repo --repo "${1:-$PWD}"
}

agent_run_lock_acquire() {
  local project="$1"
  local owner_pid="${2:-}"
  local payload
  local args=(acquire --project "$project" --repo "$PWD")
  [[ -z "$owner_pid" ]] || args+=(--owner-pid "$owner_pid")
  payload="$(agent_run_lock_command "${args[@]}")" || return $?
  AGENT_RUN_ID="$(printf '%s' "$payload" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')" || return $?
  AGENT_RUN_DIGEST="$(printf '%s' "$payload" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["digest"])')" || return $?
  AGENT_RUN_REPO="$(printf '%s' "$payload" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["repo"])')" || return $?
  echo "Run lock: acquired"
  echo "run_id: $AGENT_RUN_ID"
  echo "repo: $AGENT_RUN_REPO"
}

agent_run_lock_validate() {
  agent_run_lock_command validate --project "$1" --run-id "$2" --repo "$PWD"
}

agent_run_lock_release() {
  agent_run_lock_command release --project "$1" --run-id "$2" --digest "$3" --repo "${4:-$PWD}"
}
