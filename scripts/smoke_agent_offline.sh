#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

offline_env=(
  env
  AGENT_HUB_COMPOSE_PROJECT_NAME=central-agent-data-hub-offline-smoke
  AGENT_HUB_DB_CONTAINER=central-agent-data-hub-offline-smoke-postgres-missing
  AGENT_HUB_DB_VOLUME=central-agent-data-hub-offline-smoke-pgdata
  AGENT_HUB_DB_NAME=agent_hub_offline_smoke
  AGENT_HUB_DB_PORT=55999
  AGENT_HUB_DOCKER_TIMEOUT_SECONDS=5
  AGENT_HUB_OFFLINE_FINISH_DIR="$tmp_dir/offline-finish"
)

run_expect_operational_failure() {
  local output_path="$1"
  shift
  set +e
  "${offline_env[@]}" "$@" >"$output_path" 2>&1
  local status=$?
  set -e
  if [[ "$status" -ne 2 ]]; then
    echo "Expected operational exit code 2, got $status" >&2
    cat "$output_path" >&2
    return 1
  fi
}

require_output() {
  local output_path="$1"
  local expected="$2"
  if ! grep -Fq "$expected" "$output_path"; then
    echo "Expected output to contain: $expected" >&2
    cat "$output_path" >&2
    return 1
  fi
}

echo "Running Agent Data Hub offline-agent smoke..."

preflight_output="$tmp_dir/preflight.txt"
run_expect_operational_failure \
  "$preflight_output" \
  "$ROOT_DIR/scripts/agent_preflight.sh" --compact

require_output "$preflight_output" "Der zentrale Agent Data Hub laeuft lokal gerade nicht."
require_output "$preflight_output" "Operational error: durable DB container is missing."
require_output "$preflight_output" "$ROOT_DIR/scripts/db_doctor.sh"
require_output "$preflight_output" "$ROOT_DIR/scripts/db_start.sh"

start_output="$tmp_dir/start.txt"
run_expect_operational_failure \
  "$start_output" \
  "$ROOT_DIR/scripts/agent_start.sh" \
    --project central-agent-data-hub-demo \
    --query "offline reliability smoke" \
    --review \
    --no-lock

require_output "$start_output" "Der zentrale Agent Data Hub laeuft lokal gerade nicht."
require_output "$start_output" "Operational error: durable DB container is missing."
require_output "$start_output" "$ROOT_DIR/scripts/db_doctor.sh"
require_output "$start_output" "$ROOT_DIR/scripts/db_start.sh"

finish_output="$tmp_dir/finish.txt"
run_expect_operational_failure \
  "$finish_output" \
  "$ROOT_DIR/scripts/agent_finish.sh" \
    --project central-agent-data-hub-demo \
    --review \
    --no-lock

require_output "$finish_output" "Operational error: agent preflight failed."
require_output "$finish_output" "== Offline Finish Protocol =="
require_output "$finish_output" "No reviewed memory was written by this finish attempt."
require_output "$finish_output" "Do not mark Hub writeback, export, backup, or review-memory as complete."
require_output "$finish_output" "Retry:"
require_output "$finish_output" "$ROOT_DIR/scripts/agent_finish.sh --project central-agent-data-hub-demo --review"
require_output "$finish_output" "Recovery note:"
recovery_note="$tmp_dir/offline-finish/central-agent-data-hub-demo-latest.md"
if [[ ! -f "$recovery_note" ]]; then
  echo "Expected offline finish recovery note: $recovery_note" >&2
  cat "$finish_output" >&2
  exit 1
fi
require_output "$recovery_note" "# Offline Finish Recovery"
require_output "$recovery_note" "reviewed_memory_written: no"
require_output "$recovery_note" "export_completed: no"
require_output "$recovery_note" "backup_completed: no"
require_output "$recovery_note" "$ROOT_DIR/scripts/agent_finish.sh --project central-agent-data-hub-demo --review"
require_output "$recovery_note" "This file is a local recovery note only."

echo "Offline-agent smoke: ok"
