#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

INCLUDE_DEMO=0

usage() {
  cat <<'EOF'
Usage: scripts/db_start.sh [--demo]

Starts the durable local Central Agent Data Hub database, waits for readiness,
applies the schema, and seeds the maintainer's local working set.

For the neutral public demo path, use scripts/db_start_public_demo.sh instead.

Options:
  --demo    Also apply seed/demo.sql, the neutral public sample dataset.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo)
      INCLUDE_DEMO=1
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

mkdir -p "$OBSIDIAN_EXPORT_DIR"

echo "Starting durable local Hub database..."
echo "Container: $DB_CONTAINER"
echo "Volume:    $DB_VOLUME"
echo "URL:       $DISPLAY_DATABASE_URL"
echo

compose up -d "$DB_SERVICE"
wait_for_postgres

cd "$ROOT_DIR"
run_agent_hub migrate --apply
if [[ "$INCLUDE_DEMO" -eq 1 ]]; then
  apply_sql_file "seed/demo.sql"
else
  echo "Skipping seed/demo.sql. Pass --demo to include sample demo records."
fi
apply_sql_file "seed/business_sites.sql"
apply_sql_file "seed/agentic_projects.sql"

echo
echo "Readiness check:"
run_agent_hub status
echo
run_agent_hub brief --project commcats-de --limit 4
echo
run_agent_hub brief --project catering-agents-platform --limit 4

echo
echo "Durable local Hub database is ready."
echo "This is the maintainer local ops path."
