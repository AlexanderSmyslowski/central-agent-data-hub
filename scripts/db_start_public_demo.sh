#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/db_start_public_demo.sh [--dry-run]

Starts the local Agent Data Hub database for the neutral public demo path,
applies migrations, seeds only seed/demo.sql, and prints a demo-focused
readiness check.

This path forces a separate public demo database and ignores DATABASE_URL from
.env for this process. It does not wipe an existing local database.

Options:
  --dry-run    Print the resolved demo database target without starting Docker.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
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

echo "Starting public demo Hub database..."
echo "Container: $DB_CONTAINER"
echo "Volume:    $DB_VOLUME"
echo "Database:  $DB_NAME"
echo "URL:       $DISPLAY_DATABASE_URL"
echo

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run only. No Docker, migration, or seed command was run."
  exit 0
fi

mkdir -p "$OBSIDIAN_EXPORT_DIR"

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
echo "  scripts/smoke_public_demo.sh"
echo "  AGENT_HUB_PUBLIC_DEMO=1 scripts/hub_view.sh"
