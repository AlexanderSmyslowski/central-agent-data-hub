#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

VERIFY_CONTAINER="central-agent-data-hub-backup-verify"
VERIFY_DB="agent_hub_verify"
VERIFY_PORT="${AGENT_HUB_VERIFY_PORT:-55433}"
VERIFY_DATABASE_URL="postgresql://postgres@localhost:${VERIFY_PORT}/${VERIFY_DB}"

usage() {
  cat <<'EOF'
Usage: scripts/db_verify_backup.sh [dump-file]

Restores the newest local backup, or the provided dump file, into a temporary
Postgres container and runs agent-hub check plus a project brief.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

dump_path="${1:-}"
if [[ -z "$dump_path" ]]; then
  dump_path="$(find "$AGENT_HUB_BACKUP_DIR" -maxdepth 1 -type f -name '*.dump' -print 2>/dev/null | sort | tail -n 1)"
fi

if [[ -z "$dump_path" || ! -f "$dump_path" ]]; then
  echo "Error: no backup dump found. Run scripts/db_backup.sh first." >&2
  exit 1
fi

cleanup() {
  docker rm -f "$VERIFY_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup

echo "Verifying backup in temporary Postgres container..."
echo "Dump:      $dump_path"
echo "Container: $VERIFY_CONTAINER"
echo "URL:       $VERIFY_DATABASE_URL"
echo

docker run -d \
  --name "$VERIFY_CONTAINER" \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB="$VERIFY_DB" \
  -p "127.0.0.1:${VERIFY_PORT}:5432" \
  postgres:16 >/dev/null

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

echo
echo "Running verification checks..."
(
  cd "$ROOT_DIR"
  DATABASE_URL="$VERIFY_DATABASE_URL" OBSIDIAN_EXPORT_DIR="$OBSIDIAN_EXPORT_DIR" \
    "$PYTHON_BIN" -m agent_hub.cli check
)
echo
(
  cd "$ROOT_DIR"
  DATABASE_URL="$VERIFY_DATABASE_URL" OBSIDIAN_EXPORT_DIR="$OBSIDIAN_EXPORT_DIR" \
    "$PYTHON_BIN" -m agent_hub.cli brief --project commcats-de --limit 4
)

echo
echo "Backup verification succeeded."
