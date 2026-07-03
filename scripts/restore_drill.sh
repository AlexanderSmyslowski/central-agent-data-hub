#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1
export AGENT_HUB_COMPOSE_PROJECT_NAME="${AGENT_HUB_COMPOSE_PROJECT_NAME:-central-agent-data-hub-restore-drill}"
export AGENT_HUB_DB_CONTAINER="${AGENT_HUB_DB_CONTAINER:-central-agent-data-hub-restore-drill-postgres}"
export AGENT_HUB_DB_VOLUME="${AGENT_HUB_DB_VOLUME:-central-agent-data-hub-restore-drill-pgdata}"
export AGENT_HUB_DB_NAME="${AGENT_HUB_DB_NAME:-agent_hub_restore_demo}"
export AGENT_HUB_DB_PORT="${AGENT_HUB_DB_PORT:-55439}"
export AGENT_HUB_IGNORE_ENV_FILE=1
unset AGENT_HUB_BACKUP_REMOTE

DRILL_TMP_PARENT="${AGENT_HUB_RESTORE_DRILL_TMPDIR:-${TMPDIR:-/tmp}}"
DRILL_TMP_DIR="$(mktemp -d "${DRILL_TMP_PARENT%/}/adh-restore-drill.XXXXXX")"
export AGENT_HUB_BACKUP_DIR="$DRILL_TMP_DIR/backups"

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/restore_drill.sh

Runs a non-destructive backup/restore drill against an isolated public demo
database:
  - starts and seeds a separate demo database
  - runs the public demo smoke
  - writes a local pg_dump backup into a temporary directory
  - restores that dump into the existing db_verify_backup.sh temp database
  - runs agent-hub check and a project brief against the restored database

This script never targets the configured operator database.
It also ignores .env for this process, uses a temporary local backup directory,
and never copies drill backups to a remote target.
EOF
}

cleanup() {
  if [[ "${AGENT_HUB_KEEP_RESTORE_DRILL_TMP:-0}" != "1" ]]; then
    rm -rf "$DRILL_TMP_DIR" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "Error: unknown argument: $1" >&2
  usage >&2
  exit 2
fi

if [[ "$DB_NAME" != *demo* ]]; then
  echo "Error: restore drill refused non-demo database: $DB_NAME" >&2
  exit 2
fi

echo "Running Agent Data Hub restore drill..."
echo "Container:  $DB_CONTAINER"
echo "Database:   $DB_NAME"
echo "URL:        $DISPLAY_DATABASE_URL"
echo "Backup dir: $AGENT_HUB_BACKUP_DIR"
echo

"$ROOT_DIR/scripts/db_start_public_demo.sh"
"$ROOT_DIR/scripts/smoke_public_demo.sh"
"$ROOT_DIR/scripts/db_backup.sh"

dump_path="$(latest_backup_dump)"
if [[ -z "$dump_path" || ! -f "$dump_path" ]]; then
  echo "Error: restore drill did not create a backup dump." >&2
  exit 1
fi

echo
echo "Verifying restore from drill backup..."
"$ROOT_DIR/scripts/db_verify_backup.sh" "$dump_path"

echo
echo "Restore drill: ok"
