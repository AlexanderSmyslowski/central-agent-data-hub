#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/db_doctor.sh

Diagnoses the local Agent Data Hub Postgres runtime without writing data.

The doctor checks Docker, the compose service, the configured container and
volume, Postgres readiness, recent logs, and the normal agent-hub status/check
commands when the database is reachable.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

healthy=1
operational_issue=0
postgres_ready_now=0

mark_operational_issue() {
  operational_issue=1
  healthy=0
}

echo "Central Agent Data Hub doctor"
echo
echo "Target:"
echo "  Compose project: $COMPOSE_PROJECT_NAME"
echo "  Container:       $DB_CONTAINER"
echo "  Volume:          $DB_VOLUME"
echo "  Database:        $DB_NAME"
echo "  Port:            $DB_PORT"
echo "  URL:             $(mask_database_url "$DATABASE_URL")"
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker: error (docker command not found)"
  echo
  echo "Recovery hint: install or start Docker Desktop, then rerun agent-hub doctor."
  exit 2
fi

if ! run_with_timeout "$AGENT_HUB_DOCKER_TIMEOUT_SECONDS" docker info >/dev/null 2>&1; then
  echo "Docker: error (not responding within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s)"
  echo
  echo "Recovery hint: restart Docker Desktop, then rerun agent-hub doctor."
  exit 2
fi
echo "Docker: ok"

if ! run_with_timeout "$AGENT_HUB_DOCKER_TIMEOUT_SECONDS" docker compose version >/dev/null 2>&1; then
  echo "Docker Compose: error (not responding within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s)"
  echo
  echo "Recovery hint: update Docker Desktop or install the Docker Compose plugin."
  exit 2
fi
echo "Docker Compose: ok"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file: missing ($COMPOSE_FILE)"
  exit 2
fi
echo "Compose file: ok ($COMPOSE_FILE)"

if docker_quick volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
  echo "Volume: ok"
else
  echo "Volume: missing ($DB_VOLUME)"
  mark_operational_issue
fi

state="$(postgres_container_state)"
if [[ -z "$state" ]]; then
  echo "Container: missing"
  mark_operational_issue
else
  echo "Container state: $state"
fi

if postgres_ready; then
  postgres_ready_now=1
  echo "Postgres readiness: ok"
else
  echo "Postgres readiness: not ready"
  mark_operational_issue
fi

echo
echo "Recent log scan:"
log_output="$(docker_quick logs --tail 80 "$DB_CONTAINER" 2>/dev/null || true)"
if [[ -z "$log_output" ]]; then
  echo "  no logs available"
elif grep -q "bogus data in lock file" <<<"$log_output"; then
  echo "  found stale/corrupt Postgres lock-file symptom:"
  grep "bogus data in lock file" <<<"$log_output" | tail -n 5 | sed 's/^/  - /'
  if [[ "$postgres_ready_now" -eq 1 ]]; then
    echo "  current readiness is ok; no recovery needed right now"
  else
    echo
    echo "Recovery hint:"
    echo "  scripts/db_recover.sh --apply"
    mark_operational_issue
  fi
else
  echo "  no known stale-lock symptom found in the latest logs"
fi

if [[ "$postgres_ready_now" -eq 1 ]]; then
  echo
  echo "Agent Hub status:"
  if ! run_agent_hub status; then
    healthy=0
  fi
  echo
  echo "Agent Hub check:"
  if ! run_agent_hub check; then
    healthy=0
  fi
else
  echo
  echo "Agent Hub status/check: skipped because Postgres is not ready"
fi

echo
if [[ "$healthy" -eq 1 ]]; then
  echo "Doctor result: ready"
  exit 0
fi

if [[ "$operational_issue" -eq 1 ]]; then
  echo "Doctor result: operational issue"
  echo "Run scripts/db_recover.sh --apply only for this local Docker Postgres instance."
  exit 2
fi

echo "Doctor result: data or consistency issue"
exit 1
