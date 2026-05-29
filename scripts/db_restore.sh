#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/db_restore.sh --confirm <dump-file>

Restores a custom-format pg_dump into the durable local Compose database.
This drops and recreates the public schema in the local agent_hub database.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" != "--confirm" || -z "${2:-}" ]]; then
  echo "Error: restore requires an explicit --confirm and a dump file." >&2
  usage >&2
  exit 2
fi

dump_path="$2"
if [[ ! -f "$dump_path" ]]; then
  echo "Error: dump file not found: $dump_path" >&2
  exit 1
fi

echo "WARNING: this will replace the contents of local database '$DB_NAME'."
echo "Container: $DB_CONTAINER"
echo "Dump:      $dump_path"
echo

compose up -d "$DB_SERVICE"
wait_for_postgres

compose exec -T "$DB_SERVICE" \
  psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

compose exec -T "$DB_SERVICE" \
  pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner \
  < "$dump_path"

echo
echo "Restore complete. Running consistency check..."
run_agent_hub check
