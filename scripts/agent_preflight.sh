#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_preflight.sh

Read-only operational readiness check for Codex/Hermes before Hub writeback.

Exit codes:
  0  ready
  1  data or consistency error
  2  configuration or operational dependency missing
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "Error: unknown argument: $1" >&2
  usage >&2
  exit 2
fi

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
echo "== Latest Backup =="
set +e
"$ROOT_DIR/scripts/db_backup_latest.sh" --require
backup_code=$?
set -e
if [[ "$backup_code" -ne 0 ]]; then
  if [[ "$backup_code" -eq 1 ]]; then
    echo "Data error: latest backup checksum failed." >&2
    exit 1
  fi
  echo "Operational error: no verified local backup is available." >&2
  exit 2
fi

echo
echo "== Agent Hub Status =="
if ! run_agent_hub status; then
  echo "Operational error: agent-hub status failed." >&2
  exit 2
fi

echo
echo "== Agent Hub Check =="
if ! run_agent_hub check; then
  echo "Data error: agent-hub check reported errors." >&2
  exit 1
fi

echo
echo "== Project Briefs =="
if ! run_agent_hub brief --project commcats-de --limit 4; then
  echo "Data error: commcats-de brief is unavailable." >&2
  exit 1
fi

if ! run_agent_hub brief --project the-one-catering --limit 4; then
  echo "Data error: the-one-catering brief is unavailable." >&2
  exit 1
fi

echo
echo "Agent preflight result: ready"
