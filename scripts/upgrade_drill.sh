#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/upgrade_drill.sh

Runs a local upgrade drill against the isolated public demo database:
  - starts the demo Postgres container
  - resets only the demo database public schema
  - applies the untracked 001 baseline schema
  - runs agent-hub migrate --apply to bootstrap tracking and apply later migrations
  - seeds the public demo data
  - runs check and the public demo smoke

This script never targets the configured operator database.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "Error: unknown argument: $1" >&2
  usage >&2
  exit 2
fi

if [[ "$DB_NAME" != *demo* ]]; then
  echo "Error: upgrade drill refused non-demo database: $DB_NAME" >&2
  exit 2
fi

echo "Running Agent Data Hub upgrade drill..."
echo "Container: $DB_CONTAINER"
echo "Database:  $DB_NAME"
echo "URL:       $DISPLAY_DATABASE_URL"
echo

compose up -d "$DB_SERVICE"
wait_for_postgres

echo "Resetting public schema in isolated demo database..."
compose exec -T "$DB_SERVICE" \
  psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

apply_sql_file "migrations/001_init.sql"

echo
echo "Baseline migration status before upgrade:"
baseline_status="$(run_agent_hub migrate --status)"
printf '%s\n' "$baseline_status"
if ! grep -q "Tracking: missing" <<<"$baseline_status"; then
  echo "Error: upgrade drill expected an untracked baseline schema." >&2
  exit 1
fi

echo
echo "Applying upgrade migrations..."
run_agent_hub migrate --apply

echo
echo "Seeding public demo after upgrade..."
apply_sql_file "seed/demo.sql"

echo
echo "Verifying upgraded demo database..."
run_agent_hub check
"$ROOT_DIR/scripts/smoke_public_demo.sh"

echo
echo "Upgrade drill: ok"
