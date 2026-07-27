#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

VERIFY_CONTAINER="${AGENT_HUB_VERIFY_CONTAINER:-central-agent-data-hub-backup-verify-$$}"
VERIFY_DB="agent_hub_verify"
VERIFY_PORT="${AGENT_HUB_VERIFY_PORT:-}"
VERIFY_DB_PASSWORD="${AGENT_HUB_VERIFY_POSTGRES_PASSWORD:-changeme}"
VERIFY_DATABASE_CREATED=0

usage() {
  cat <<'EOF'
Usage: scripts/db_verify_backup.sh [dump-file]

Restores the newest local backup, or the provided dump file, into an isolated
temporary database and runs agent-hub check plus one active project brief when
the restored database contains active projects. A direct/native runtime uses a
process-scoped database on the configured server; the Compose runtime uses a
temporary Postgres container.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

dump_path="${1:-}"
if [[ -z "$dump_path" ]]; then
  dump_path="$(latest_backup_dump)"
fi

if [[ -z "$dump_path" || ! -f "$dump_path" ]]; then
  echo "Error: no backup dump found. Run scripts/db_backup.sh first." >&2
  exit 1
fi

select_database_runtime
if database_runtime_is_direct; then
  VERIFY_DB="agent_hub_verify_$$_${RANDOM}"
fi

cleanup() {
  if database_runtime_is_direct; then
    if [[ "$VERIFY_DATABASE_CREATED" -eq 1 ]]; then
      database_client psql -X -v ON_ERROR_STOP=1 -d postgres \
        -c "DROP DATABASE IF EXISTS \"$VERIFY_DB\" WITH (FORCE);" \
        >/dev/null 2>&1 || true
    fi
  else
    docker rm -f "$VERIFY_CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Verifying backup in an isolated temporary database..."
echo "Database runtime: $(database_runtime_label)"
echo "Dump:      $dump_path"
echo

if database_runtime_is_direct; then
  if [[ ! "$VERIFY_DB" =~ ^agent_hub_verify_[0-9]+_[0-9]+$ ]]; then
    echo "Error: unsafe temporary verification database name." >&2
    exit 2
  fi
  require_native_postgres_command psql
  require_native_postgres_command pg_restore
  VERIFY_DATABASE_URL="$(database_client database-url "$VERIFY_DB")"
  VERIFY_DISPLAY_DATABASE_URL="$(mask_database_url "$VERIFY_DATABASE_URL")"
  echo "Database:  $VERIFY_DB"
  echo "URL:       $VERIFY_DISPLAY_DATABASE_URL"
  echo

  database_client psql -X -v ON_ERROR_STOP=1 -d postgres \
    -c "CREATE DATABASE \"$VERIFY_DB\";"
  VERIFY_DATABASE_CREATED=1
  database_client pg_restore --exit-on-error --no-owner \
    --dbname="$VERIFY_DB" "$dump_path"
else
  cleanup
  echo "Container: $VERIFY_CONTAINER"

  # A process-scoped container and Docker-assigned port let independent agent
  # finishes verify backups without stopping or replacing each other's verifier.
  VERIFY_PORT_BINDING="127.0.0.1::5432"
  if [[ -n "$VERIFY_PORT" ]]; then
    VERIFY_PORT_BINDING="127.0.0.1:${VERIFY_PORT}:5432"
  fi

  docker run -d \
    --name "$VERIFY_CONTAINER" \
    -e POSTGRES_DB="$VERIFY_DB" \
    -e POSTGRES_PASSWORD="$VERIFY_DB_PASSWORD" \
    -p "$VERIFY_PORT_BINDING" \
    postgres:16 >/dev/null

  if [[ -z "$VERIFY_PORT" ]]; then
    published_address="$(docker port "$VERIFY_CONTAINER" 5432/tcp | head -n 1)"
    VERIFY_PORT="${published_address##*:}"
  fi
  if [[ ! "$VERIFY_PORT" =~ ^[0-9]+$ ]]; then
    echo "Error: could not determine the temporary verification port." >&2
    exit 2
  fi

  VERIFY_DATABASE_URL="postgresql://postgres:${VERIFY_DB_PASSWORD}@localhost:${VERIFY_PORT}/${VERIFY_DB}"
  VERIFY_DISPLAY_DATABASE_URL="postgresql://postgres:***@localhost:${VERIFY_PORT}/${VERIFY_DB}"
  echo "URL:       $VERIFY_DISPLAY_DATABASE_URL"
  echo

  echo "Waiting for verify database..."
  for _ in $(seq 1 60); do
    if docker exec "$VERIFY_CONTAINER" pg_isready -U postgres -d "$VERIFY_DB" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  docker exec "$VERIFY_CONTAINER" pg_isready -U postgres -d "$VERIFY_DB" >/dev/null
  docker exec -i "$VERIFY_CONTAINER" \
    pg_restore -U postgres -d "$VERIFY_DB" --no-owner \
    < "$dump_path"
fi

echo
echo "Running verification checks..."
(
  cd "$ROOT_DIR"
  DATABASE_URL="$VERIFY_DATABASE_URL" OBSIDIAN_EXPORT_DIR="$OBSIDIAN_EXPORT_DIR" \
    "$PYTHON_BIN" -m agent_hub.cli check
)
echo
brief_project="$(
  cd "$ROOT_DIR"
  DATABASE_URL="$VERIFY_DATABASE_URL" OBSIDIAN_EXPORT_DIR="$OBSIDIAN_EXPORT_DIR" \
    "$PYTHON_BIN" -m agent_hub.cli projects --format json \
    | "$PYTHON_BIN" -c '
import json
import sys

projects = json.load(sys.stdin)
print(projects[0]["slug"] if projects else "")
'
)"
if [[ -n "$brief_project" ]]; then
  echo "Project brief smoke: $brief_project"
  (
    cd "$ROOT_DIR"
    DATABASE_URL="$VERIFY_DATABASE_URL" OBSIDIAN_EXPORT_DIR="$OBSIDIAN_EXPORT_DIR" \
      "$PYTHON_BIN" -m agent_hub.cli brief --project "$brief_project" --limit 4
  )
else
  echo "Project brief smoke skipped: restored backup has no active projects."
fi

echo
echo "Backup verification succeeded."
