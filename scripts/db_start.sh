#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

INCLUDE_DEMO=0

usage() {
  cat <<'EOF'
Usage: scripts/db_start.sh [--demo] [--seed-file <path>]

Starts the durable local Central Agent Data Hub database, waits for readiness,
and applies the schema.

For the neutral public demo path, use scripts/db_start_public_demo.sh instead.

Options:
  --demo    Also apply seed/demo.sql, the neutral public sample dataset.
  --seed-file <path>
            Also apply an explicit local operator seed file. This is for
            private, machine-local setup files kept outside the public repo.
EOF
}

EXTRA_SEED_FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo)
      INCLUDE_DEMO=1
      shift
      ;;
    --seed-file)
      if [[ -z "${2:-}" ]]; then
        echo "Error: --seed-file requires a path." >&2
        usage >&2
        exit 1
      fi
      EXTRA_SEED_FILES+=("${2:-}")
      shift 2
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
if (( ${#EXTRA_SEED_FILES[@]} )); then
  for seed_file in "${EXTRA_SEED_FILES[@]}"; do
    apply_sql_file "$seed_file"
  done
else
  echo "No private operator seed files were applied."
  echo "Register local projects with scripts/register_project.sh or pass --seed-file explicitly."
fi

echo
echo "Readiness check:"
run_agent_hub status
echo
run_agent_hub projects

echo
echo "Durable local Hub database is ready."
echo "This is the configured local ops path."
