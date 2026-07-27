#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

mkdir -p "$AGENT_HUB_BACKUP_DIR"
select_database_runtime

echo "Creating Central Agent Data Hub backup..."
echo "Database runtime: $(database_runtime_label)"
echo "Backup dir: $AGENT_HUB_BACKUP_DIR"
echo "Remote:     ${AGENT_HUB_BACKUP_REMOTE:-not configured}"
echo

if database_runtime_is_direct; then
  postgres_ready
else
  wait_for_postgres
fi

timestamp="$(date +"%Y%m%d-%H%M%S")"
dump_path="$AGENT_HUB_BACKUP_DIR/agent_hub-${timestamp}.dump"
sha_path="${dump_path}.sha256"

database_pg_dump --format=custom > "$dump_path"

sha256_file "$dump_path" > "$sha_path"

echo "Backup written: $dump_path"
echo "Checksum:       $sha_path"

if [[ -n "${AGENT_HUB_BACKUP_REMOTE:-}" ]]; then
  if ! command -v rsync >/dev/null 2>&1; then
    echo "Error: AGENT_HUB_BACKUP_REMOTE is set, but rsync is not available." >&2
    exit 1
  fi
  echo "Copying backup to remote..."
  rsync -av "$dump_path" "$sha_path" "$AGENT_HUB_BACKUP_REMOTE"
  echo "Remote backup complete."
else
  echo "Remote backup skipped; AGENT_HUB_BACKUP_REMOTE is not set."
fi
