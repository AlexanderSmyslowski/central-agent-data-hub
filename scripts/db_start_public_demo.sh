#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/db_start_public_demo.sh

Starts the local Agent Data Hub database for the neutral public demo path,
applies migrations, seeds only seed/demo.sql, and prints a demo-focused
readiness check.

This path does not wipe an existing local database. For the calmest public demo
experience, use it against a fresh local database or Docker volume.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "Error: db_start_public_demo.sh takes no arguments." >&2
  usage >&2
  exit 2
fi

mkdir -p "$OBSIDIAN_EXPORT_DIR"

echo "Starting public demo Hub database..."
echo "Container: $DB_CONTAINER"
echo "Volume:    $DB_VOLUME"
echo "URL:       $DEFAULT_DATABASE_URL"
echo

compose up -d "$DB_SERVICE"
wait_for_postgres

cd "$ROOT_DIR"
run_agent_hub migrate --apply
apply_sql_file "seed/demo.sql"

echo
echo "Public demo readiness check:"
run_agent_hub status
echo
run_agent_hub check
echo
run_agent_hub brief --project central-agent-data-hub-demo --limit 4
echo
run_agent_hub compile --project central-agent-data-hub-demo --limit 4
echo
run_agent_hub quality --project central-agent-data-hub-demo

echo
echo "Public demo Hub database is ready."
echo "Next:"
echo "  .venv/bin/python -m agent_hub.cli export"
echo "  scripts/hub_view.sh"
