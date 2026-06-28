#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

DRY_RUN=0

verify_public_demo_hygiene() {
  local finding_count
  finding_count="$(
    compose exec -T "$DB_SERVICE" \
      psql -v ON_ERROR_STOP=1 -At -U "$DB_USER" -d "$DB_NAME" <<'SQL'
WITH searchable AS (
  SELECT 'projects' AS table_name, slug AS item, lower(concat_ws(' ', name, slug, coalesce(description, ''), metadata::text)) AS text
  FROM projects
  UNION ALL
  SELECT 'agents', slug, lower(concat_ws(' ', name, slug, coalesce(role, ''), metadata::text))
  FROM agents
  UNION ALL
  SELECT 'documents', slug, lower(concat_ws(' ', title, slug, path, content, frontmatter::text, metadata::text))
  FROM documents
  UNION ALL
  SELECT 'facts', id::text, lower(concat_ws(' ', statement, coalesce(source, ''), metadata::text))
  FROM facts
  UNION ALL
  SELECT 'decisions', id::text, lower(concat_ws(' ', decision, coalesce(rationale, ''), coalesce(consequences, ''), metadata::text))
  FROM decisions
  UNION ALL
  SELECT 'open_questions', id::text, lower(concat_ws(' ', question, coalesce(answer, ''), metadata::text))
  FROM open_questions
  UNION ALL
  SELECT 'risks', id::text, lower(concat_ws(' ', title, coalesce(impact, ''), coalesce(mitigation, ''), metadata::text))
  FROM risks
  UNION ALL
  SELECT 'reports', id::text, lower(concat_ws(' ', title, report_type, coalesce(summary, ''), body, metadata::text))
  FROM reports
  UNION ALL
  SELECT 'agent_actions', id::text, lower(concat_ws(' ', action, coalesce(object_type, ''), input::text, output::text, coalesce(error, ''), metadata::text))
  FROM agent_actions
  UNION ALL
  SELECT 'event_log', id::text, lower(concat_ws(' ', event_type, coalesce(object_type, ''), payload::text, metadata::text))
  FROM event_log
  UNION ALL
  SELECT 'sync_events', id::text, lower(concat_ws(' ', source, payload::text, coalesce(error, ''), metadata::text))
  FROM sync_events
),
forbidden(term) AS (
  VALUES
    ('hermes'),
    ('ronak'),
    ('telegram'),
    ('review_api'),
    ('review api'),
    ('commcats-de'),
    ('the-one-catering'),
    ('lamour'),
    ('smoke')
)
SELECT count(*)
FROM (
  SELECT 1
  FROM searchable
  CROSS JOIN forbidden
  WHERE text LIKE '%' || term || '%'
  LIMIT 1
) AS matches;
SQL
  )"

  if [[ "$finding_count" != "0" ]]; then
    echo "Error: public demo database contains old smoke or operator traces." >&2
    echo "This script will not clean or overwrite existing local data automatically." >&2
    echo "Use a fresh isolated demo instance, for example:" >&2
    echo >&2
    echo "  AGENT_HUB_COMPOSE_PROJECT_NAME=adh-demo-fresh \\" >&2
    echo "  AGENT_HUB_DB_CONTAINER=adh-demo-fresh-postgres \\" >&2
    echo "  AGENT_HUB_DB_VOLUME=adh-demo-fresh-pgdata \\" >&2
    echo "  AGENT_HUB_DB_PORT=55433 \\" >&2
    echo "  scripts/first_run_demo.sh" >&2
    return 1
  fi
}

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
verify_public_demo_hygiene

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
echo "  AGENT_HUB_PUBLIC_DEMO=1 AGENT_HUB_REVIEWERS=demo-reviewer HUB_VIEW_REVIEWER=demo-reviewer scripts/hub_view.sh"
