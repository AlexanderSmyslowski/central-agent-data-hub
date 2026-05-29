#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

mkdir -p "$OBSIDIAN_EXPORT_DIR"

echo "Central Agent Data Hub durable DB status"
echo "Container: $DB_CONTAINER"
echo "Volume:    $DB_VOLUME"
echo "URL:       $DEFAULT_DATABASE_URL"
echo

echo "== Docker Compose =="
compose ps

echo
echo "== Volume =="
if docker volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
  docker volume inspect "$DB_VOLUME" --format 'Name={{ .Name }} Mountpoint={{ .Mountpoint }}'
else
  echo "Volume not found: $DB_VOLUME"
fi

echo
echo "== Port =="
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"$DB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    lsof -nP -iTCP:"$DB_PORT" -sTCP:LISTEN
  else
    echo "No listener found on localhost:$DB_PORT"
  fi
else
  echo "lsof unavailable; skipping port listener details."
fi

echo
echo "== Healthcheck =="
if compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME"; then
  echo "Healthcheck: ok"
else
  echo "Healthcheck: not ready"
  exit 1
fi

echo
echo "== Latest Backup =="
"$ROOT_DIR/scripts/db_backup_latest.sh"

echo
echo "== Agent Hub Status =="
run_agent_hub status

echo
echo "== Readiness Brief =="
run_agent_hub brief --project commcats-de --limit 4
