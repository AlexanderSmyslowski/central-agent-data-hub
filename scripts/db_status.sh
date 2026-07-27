#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

mkdir -p "$OBSIDIAN_EXPORT_DIR"
select_database_runtime

echo "Central Agent Data Hub durable DB status"
echo "Database runtime: $(database_runtime_label)"
echo "URL:              $DISPLAY_DATABASE_URL"
if ! database_runtime_is_direct; then
  echo "Container:        $DB_CONTAINER"
  echo "Volume:           $DB_VOLUME"
fi
echo

echo "== Docker Compose =="
if database_runtime_is_direct; then
  echo "Docker status: skipped (not required for direct database access)"
else
  if ! compose_quick ps; then
    echo "Docker Compose status unavailable within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s."
  fi
fi

echo
echo "== Volume =="
if database_runtime_is_direct; then
  echo "Docker volume: skipped (direct database access)"
else
  if docker_quick volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
    docker_quick volume inspect "$DB_VOLUME" --format 'Name={{ .Name }} Mountpoint={{ .Mountpoint }}'
  else
    echo "Volume not found: $DB_VOLUME"
  fi
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
if postgres_ready; then
  echo "Healthcheck: ok"
else
  echo "Healthcheck: not ready"
  exit 1
fi

echo
echo "== Backup Health =="
"$ROOT_DIR/scripts/db_backup_health.sh"

echo
echo "== Agent Hub Status =="
run_agent_hub status

echo
echo "== Readiness Brief =="
run_agent_hub projects
