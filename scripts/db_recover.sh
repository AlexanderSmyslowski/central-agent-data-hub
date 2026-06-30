#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

APPLY=0
SNAPSHOT_DIR="$SHARED_ROOT/.local/volume-snapshots"

usage() {
  cat <<'EOF'
Usage: scripts/db_recover.sh [--apply]

Safely recovers the local Docker Postgres runtime after known stale lock-file
failures. The script never removes Docker volumes, drops databases, or modifies
Hub rows.

Default mode is a dry run. Use --apply to:
  1. stop the configured Postgres container
  2. create a compressed snapshot of the Docker volume
  3. remove only empty or NUL-only postmaster.pid from the data volume
  4. recreate the service container without deleting the data volume
  5. wait for Postgres and run agent-hub status
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
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

echo "Central Agent Data Hub DB recovery"
echo
echo "Target:"
echo "  Container: $DB_CONTAINER"
echo "  Volume:    $DB_VOLUME"
echo "  URL:       $(mask_database_url "$DATABASE_URL")"
echo

if [[ "$APPLY" -eq 0 ]]; then
  cat <<'EOF'
Dry run only. No container or volume changes were made.

This recovery path is intentionally narrow:
- it creates a local volume snapshot before changes
- it removes only empty or NUL-only postmaster.pid files
- it recreates the Docker container to clear runtime socket locks
- it never removes Docker volumes or drops database objects

Run:
  scripts/db_recover.sh --apply
EOF
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker command not found." >&2
  exit 2
fi

if ! run_with_timeout "$AGENT_HUB_DOCKER_TIMEOUT_SECONDS" docker info >/dev/null 2>&1; then
  echo "Error: docker is not responding within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s." >&2
  exit 2
fi

if ! docker_quick volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
  echo "Error: Docker volume not found: $DB_VOLUME" >&2
  echo "Run scripts/db_start.sh if this is a new checkout." >&2
  exit 2
fi

mkdir -p "$SNAPSHOT_DIR"
timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
safe_volume_name="$(printf '%s' "$DB_VOLUME" | tr -c 'A-Za-z0-9_.-' '-')"
snapshot_path="$SNAPSHOT_DIR/${safe_volume_name}-${timestamp}.tar.gz"

echo "Stopping container if present..."
docker_quick stop "$DB_CONTAINER" >/dev/null 2>&1 || true

echo "Creating volume snapshot..."
docker run --rm \
  -v "${DB_VOLUME}:/var/lib/postgresql/data:ro" \
  -v "${SNAPSHOT_DIR}:/backup" \
  postgres:16 \
  bash -lc "tar -C /var/lib/postgresql -czf '/backup/$(basename "$snapshot_path")' data"
echo "Snapshot written: $snapshot_path"

echo "Checking data-volume postmaster.pid..."
docker run --rm \
  -v "${DB_VOLUME}:/var/lib/postgresql/data" \
  postgres:16 \
  bash -lc '
    set -euo pipefail
    pid=/var/lib/postgresql/data/postmaster.pid
    if [[ ! -f "$pid" ]]; then
      echo "postmaster.pid absent"
      exit 0
    fi
    if [[ ! -s "$pid" ]]; then
      rm "$pid"
      echo "removed empty postmaster.pid"
      exit 0
    fi
    nonnul="$(tr -d "\000" < "$pid" | wc -c | tr -d " ")"
    if [[ "$nonnul" == "0" ]]; then
      rm "$pid"
      echo "removed NUL-only postmaster.pid"
      exit 0
    fi
    echo "postmaster.pid contains non-NUL data; leaving it in place"
  '

echo "Recreating Postgres service container without removing the volume..."
compose rm -sf "$DB_SERVICE" >/dev/null
compose up -d "$DB_SERVICE"
wait_for_postgres

echo
echo "Recovery status check:"
run_agent_hub status

echo
echo "DB recovery complete."
