#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_preflight.sh [--compact]

Read-only operational readiness check for Codex/Hermes before Hub writeback.

Options:
  --compact  Print only successful check summaries; print full output on failure.

Exit codes:
  0  ready
  1  data or consistency error
  2  configuration or operational dependency missing
EOF
}

COMPACT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compact)
      COMPACT=1
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

if ! command -v docker >/dev/null 2>&1; then
  echo "Operational error: docker is not available." >&2
  exit 2
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Operational error: docker compose is not available." >&2
  exit 2
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Operational error: compose file missing: $COMPOSE_FILE" >&2
  exit 2
fi

if ! docker inspect "$DB_CONTAINER" >/dev/null 2>&1; then
  echo "Operational error: durable DB container is missing." >&2
  echo "Run scripts/db_start.sh first." >&2
  exit 2
fi

if [[ "$(docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null)" != "true" ]]; then
  echo "Operational error: durable DB container is not running." >&2
  echo "Run scripts/db_start.sh first." >&2
  exit 2
fi

if ! compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
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
  echo "Run scripts/db_start.sh or agent-hub migrate --apply before agent writeback." >&2
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
    echo "Data error: backup checksum or remote parity failed." >&2
    exit 1
  fi
  echo "Operational error: backup health is not ready." >&2
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
if ! commcats_brief="$(run_agent_hub brief --project commcats-de --limit 4 2>&1)"; then
  echo "$commcats_brief"
  echo "Data error: commcats-de brief is unavailable." >&2
  exit 1
fi
if [[ "$COMPACT" -eq 0 ]]; then
  echo "$commcats_brief"
fi

if ! the_one_brief="$(run_agent_hub brief --project the-one-catering --limit 4 2>&1)"; then
  echo "$the_one_brief"
  echo "Data error: the-one-catering brief is unavailable." >&2
  exit 1
fi
if [[ "$COMPACT" -eq 0 ]]; then
  echo
  echo "$the_one_brief"
else
  echo "Project briefs: ok"
fi

echo
echo "Agent preflight result: ready"
