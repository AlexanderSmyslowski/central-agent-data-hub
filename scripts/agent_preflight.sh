#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_preflight.sh [--compact] [--allow-direct-db]

Read-only operational readiness check for Codex/Hermes before Hub writeback.

Options:
  --compact  Print only successful check summaries; print full output on failure.
  --allow-direct-db
             If Docker/Compose is unavailable, allow read-only Hub access when
             DATABASE_URL is reachable and agent-hub check is ok.

Exit codes:
  0  ready
  1  data or consistency error
  2  configuration or operational dependency missing
EOF
}

COMPACT=0
ALLOW_DIRECT_DB=0

hub_unavailable_message() {
  cat >&2 <<EOF
Der zentrale Agent Data Hub laeuft lokal gerade nicht.
Bitte Docker starten oder kurz warten, bis der gemeinsame Projektspeicher wieder bereit ist.

Diagnose:
  $ROOT_DIR/scripts/db_doctor.sh

Start:
  $ROOT_DIR/scripts/db_start.sh
EOF
}

direct_db_preflight() {
  local reason="$1"

  echo "Operational warning: $reason" >&2
  echo "Trying direct read-only Hub check through DATABASE_URL." >&2
  echo >&2

  if ! check_output="$(run_agent_hub check 2>&1)"; then
    echo "$check_output" >&2
    echo "Operational error: direct Hub check failed." >&2
    return 2
  fi

  echo "Database: ok (direct)"
  if [[ "$COMPACT" -eq 0 ]]; then
    echo
    echo "== Agent Hub Check =="
    echo "$check_output"
    echo
    echo "Backup health: skipped (Docker/Compose unavailable for local backup checks)"
  else
    echo
    echo "Agent Hub check: ok"
    echo "Backup health: skipped (direct read-only mode)"
  fi

  echo
  echo "Agent preflight result: ready for read-only context"
  return 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compact)
      COMPACT=1
      shift
      ;;
    --allow-direct-db)
      ALLOW_DIRECT_DB=1
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

echo "Central Agent Data Hub agent preflight"
echo "Mode: read-only"
echo

set +e
host_health_output="$(print_host_runtime_health --compact 2>&1)"
host_health_code=$?
set -e
if [[ "$COMPACT" -eq 0 || "$host_health_code" -ne 0 ]]; then
  echo "$host_health_output"
  echo
fi
if [[ "$host_health_code" -eq 2 ]]; then
  echo "Operational error: host runtime is not ready." >&2
  echo "Free disk space or fix the temp directory, then rerun this preflight." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  if [[ "$ALLOW_DIRECT_DB" -eq 1 ]]; then
    direct_db_preflight "docker is not available."
    exit $?
  fi
  echo "Operational error: docker is not available." >&2
  exit 2
fi

if ! run_with_timeout "$AGENT_HUB_DOCKER_TIMEOUT_SECONDS" docker compose version >/dev/null 2>&1; then
  if [[ "$ALLOW_DIRECT_DB" -eq 1 ]]; then
    direct_db_preflight "docker compose is not available."
    exit $?
  fi
  echo "Operational error: docker compose is not available." >&2
  exit 2
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Operational error: compose file missing: $COMPOSE_FILE" >&2
  exit 2
fi

set +e
docker_quick inspect "$DB_CONTAINER" >/dev/null 2>&1
inspect_code=$?
set -e
if [[ "$inspect_code" -eq 124 ]]; then
  hub_unavailable_message
  echo "Operational error: docker is not responding within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s." >&2
  echo "Restart Docker Desktop, then run $ROOT_DIR/scripts/db_status.sh." >&2
  exit 2
fi
if [[ "$inspect_code" -ne 0 ]]; then
  hub_unavailable_message
  echo "Operational error: durable DB container is missing." >&2
  echo "Run $ROOT_DIR/scripts/db_start.sh first." >&2
  exit 2
fi

set +e
running_state="$(docker_quick inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null)"
running_code=$?
set -e
if [[ "$running_code" -eq 124 ]]; then
  hub_unavailable_message
  echo "Operational error: docker is not responding within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s." >&2
  echo "Restart Docker Desktop, then run $ROOT_DIR/scripts/db_status.sh." >&2
  exit 2
fi
if [[ "$running_state" != "true" ]]; then
  hub_unavailable_message
  echo "Operational error: durable DB container is not running." >&2
  echo "Run $ROOT_DIR/scripts/db_start.sh first." >&2
  exit 2
fi

if ! postgres_ready; then
  hub_unavailable_message
  echo "Operational error: durable DB is not accepting connections." >&2
  exit 2
fi

echo "Database: ok"

echo
if [[ "$COMPACT" -eq 0 ]]; then
  echo "== Schema Migrations =="
fi
if ! migration_status="$(run_agent_hub migrate --status 2>&1)"; then
  echo "$migration_status"
  echo "Operational error: schema migration status failed." >&2
  exit 2
fi
if [[ "$COMPACT" -eq 0 ]]; then
  echo "$migration_status"
fi
if echo "$migration_status" | grep -Eq ': (pending|failed|changed)$'; then
  if [[ "$COMPACT" -eq 1 ]]; then
    echo "$migration_status"
  fi
  echo "Operational error: schema migrations are pending or failed." >&2
  echo "Run $ROOT_DIR/scripts/db_start.sh or agent-hub migrate --apply before agent writeback." >&2
  exit 2
fi
if [[ "$COMPACT" -eq 1 ]]; then
  echo "Schema migrations: ok"
fi

echo
if [[ "$COMPACT" -eq 0 ]]; then
  echo "== Backup Health =="
fi
set +e
backup_output="$("$ROOT_DIR/scripts/db_backup_health.sh" --require 2>&1)"
backup_code=$?
set -e
if [[ "$COMPACT" -eq 0 || "$backup_code" -ne 0 ]]; then
  echo "$backup_output"
fi
if [[ "$backup_code" -ne 0 ]]; then
  if [[ "$backup_code" -eq 1 ]]; then
    echo "Data error: local backup checksum failed." >&2
    exit 1
  fi
  echo "Operational error: backup health is not ready." >&2
  echo "Remote backup parity can be made strict with AGENT_HUB_REQUIRE_REMOTE_BACKUP=1." >&2
  exit 2
fi
if [[ "$COMPACT" -eq 1 ]]; then
  echo "Backup health: ok"
fi

echo
if [[ "$COMPACT" -eq 0 ]]; then
  echo "== Agent Hub Status =="
fi
if ! status_output="$(run_agent_hub status 2>&1)"; then
  echo "$status_output"
  echo "Operational error: agent-hub status failed." >&2
  exit 2
fi
if [[ "$COMPACT" -eq 0 ]]; then
  echo "$status_output"
else
  echo "Agent Hub status: ok"
fi

echo
if [[ "$COMPACT" -eq 0 ]]; then
  echo "== Agent Hub Check =="
fi
if ! check_output="$(run_agent_hub check 2>&1)"; then
  echo "$check_output"
  echo "Data error: agent-hub check reported errors." >&2
  exit 1
fi
if [[ "$COMPACT" -eq 0 ]]; then
  echo "$check_output"
else
  echo "Agent Hub check: ok"
fi

echo
if [[ "$COMPACT" -eq 0 ]]; then
  echo "== Project Briefs =="
fi
if ! projects_output="$(run_agent_hub projects --format json 2>&1)"; then
  echo "$projects_output"
  echo "Operational error: active project list is unavailable." >&2
  exit 2
fi

brief_project_list="$(
  printf '%s\n' "$projects_output" | "$PYTHON_BIN" -c '
import json
import sys

projects = json.load(sys.stdin)
for project in projects[:2]:
    slug = project.get("slug")
    if slug:
        print(slug)
'
)"

if [[ -z "$brief_project_list" ]]; then
  echo "Data error: no active Hub projects are available for brief checks." >&2
  exit 1
fi

brief_count=0
while IFS= read -r project_slug; do
  [[ -z "$project_slug" ]] && continue
  brief_count=$((brief_count + 1))
  if ! project_brief="$(run_agent_hub brief --project "$project_slug" --limit 4 2>&1)"; then
    echo "$project_brief"
    echo "Data error: project brief is unavailable for '$project_slug'." >&2
    exit 1
  fi
  if [[ "$COMPACT" -eq 0 ]]; then
    if (( brief_count > 1 )); then
      echo
    fi
    echo "$project_brief"
  fi
done <<< "$brief_project_list"

if [[ "$COMPACT" -eq 1 ]]; then
  echo "Project briefs: ok ($brief_count checked)"
fi

echo
echo "Agent preflight result: ready"
