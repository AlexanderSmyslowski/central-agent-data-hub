#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

export TMPDIR="${AGENT_HUB_RELEASE_TMPDIR:-/var/tmp/agent-data-hub-release-candidate-${USER:-user}}"
mkdir -p "$TMPDIR"

usage() {
  cat <<'EOF'
Usage: scripts/release_candidate_check.sh

Runs the local v0.7 release-candidate evidence set:
  - whitespace, shell syntax, Python compile, and pytest
  - public demo startup
  - public demo smoke
  - first external-developer smoke
  - multi-agent trust-loop smoke
  - offline-agent smoke
  - baseline-to-head upgrade drill
  - agent-hub status and check

The runner uses its own temp directory outside the repository so Pytest
temporary repos do not accidentally inherit this checkout's Git or .env state.

This script does not tag, publish, recover, or change release metadata.
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

run_step() {
  local title="$1"
  shift

  echo
  echo "== $title =="
  "$@"
  echo "ok: $title"
}

require_release_docker_runtime() {
  echo "Release Docker runtime gate:"
  if ! command -v docker >/dev/null 2>&1; then
    echo "  Docker: error (docker command not found)" >&2
    echo "  Recovery: install or start Docker Desktop, then rerun this release check." >&2
    return 2
  fi
  if ! docker_quick info >/dev/null 2>&1; then
    echo "  Docker: error (daemon did not answer within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s)" >&2
    echo "  Recovery: restart Docker Desktop, then rerun this release check." >&2
    echo "  Diagnose: $ROOT_DIR/scripts/db_doctor.sh" >&2
    return 2
  fi
  if ! run_with_timeout "$AGENT_HUB_DOCKER_TIMEOUT_SECONDS" docker compose version >/dev/null 2>&1; then
    echo "  Docker Compose: error (not available or not responding within ${AGENT_HUB_DOCKER_TIMEOUT_SECONDS}s)" >&2
    echo "  Recovery: install/enable Docker Compose, then rerun this release check." >&2
    echo "  Diagnose: $ROOT_DIR/scripts/db_doctor.sh" >&2
    return 2
  fi
  echo "  Docker: ok"
  echo "  Docker Compose: ok"
}

run_docker_step() {
  require_release_docker_runtime
  "$@"
}

run_python_tests() {
  (
    cd "$ROOT_DIR"
    env \
      -u DATABASE_URL \
      -u OBSIDIAN_EXPORT_DIR \
      -u AGENT_HUB_BACKUP_DIR \
      "$PYTHON_BIN" -m pytest -q
  )
}

clean_demo_env() {
  env \
    -u DATABASE_URL \
    -u AGENT_HUB_PUBLIC_DEMO \
    -u AGENT_HUB_COMPOSE_PROJECT_NAME \
    -u AGENT_HUB_DB_CONTAINER \
    -u AGENT_HUB_DB_VOLUME \
    -u AGENT_HUB_DB_NAME \
    -u AGENT_HUB_DB_PORT \
    "$@"
}

release_demo_env() {
  env \
    -u DATABASE_URL \
    AGENT_HUB_COMPOSE_PROJECT_NAME=central-agent-data-hub-release-demo \
    AGENT_HUB_DB_CONTAINER=central-agent-data-hub-release-demo-postgres \
    AGENT_HUB_DB_VOLUME=central-agent-data-hub-release-demo-pgdata \
    AGENT_HUB_DB_NAME=agent_hub_release_demo \
    AGENT_HUB_DB_PORT=55438 \
    "$@"
}

run_public_demo_start() {
  release_demo_env "$ROOT_DIR/scripts/db_start_public_demo.sh"
}

run_public_demo_smoke() {
  release_demo_env "$ROOT_DIR/scripts/smoke_public_demo.sh"
}

echo "Agent Data Hub release-candidate evidence check"
echo "Repository: $ROOT_DIR"
echo "Head:       $(git -C "$ROOT_DIR" rev-parse --short HEAD)"
echo "Temp dir:   $TMPDIR"

status_short="$(git -C "$ROOT_DIR" status --short)"
if [[ -n "$status_short" ]]; then
  echo
  echo "Note: working tree has local changes. This is fine for a pre-commit check;"
  echo "commit before tagging a release candidate."
fi

run_step "Git whitespace check" git -C "$ROOT_DIR" diff --check
run_step "Shell syntax" bash -n "$ROOT_DIR"/scripts/*.sh
run_step "Python compile" "$PYTHON_BIN" -m compileall "$ROOT_DIR/agent_hub"
run_step "Python tests" run_python_tests
run_step "Public demo startup" run_docker_step run_public_demo_start
run_step "Public demo smoke" run_docker_step run_public_demo_smoke
run_step "External-developer smoke" run_docker_step clean_demo_env "$ROOT_DIR/scripts/smoke_external_developer.sh"
run_step "Trust-loop smoke" run_docker_step clean_demo_env "$ROOT_DIR/scripts/smoke_trust_loop.sh"
run_step "Offline-agent smoke" clean_demo_env "$ROOT_DIR/scripts/smoke_agent_offline.sh"
run_step "Upgrade drill" run_docker_step clean_demo_env "$ROOT_DIR/scripts/upgrade_drill.sh"
run_step "Agent Hub status" run_agent_hub status
run_step "Agent Hub check" run_agent_hub check

echo
echo "Release-candidate evidence check: ok"
