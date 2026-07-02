#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
COMPOSE_PROJECT_NAME="${AGENT_HUB_COMPOSE_PROJECT_NAME:-central-agent-data-hub}"
AGENT_HUB_DOCKER_TIMEOUT_SECONDS="${AGENT_HUB_DOCKER_TIMEOUT_SECONDS:-15}"
AGENT_HUB_DB_READY_TIMEOUT_SECONDS="${AGENT_HUB_DB_READY_TIMEOUT_SECONDS:-5}"
AGENT_HUB_DB_START_TIMEOUT_SECONDS="${AGENT_HUB_DB_START_TIMEOUT_SECONDS:-60}"
AGENT_HUB_DISK_WARN_MB="${AGENT_HUB_DISK_WARN_MB:-1024}"
AGENT_HUB_DISK_ERROR_MB="${AGENT_HUB_DISK_ERROR_MB:-128}"
PUBLIC_DEMO_REQUESTED="${AGENT_HUB_PUBLIC_DEMO:-0}"
PUBLIC_DEMO_COMPOSE_PROJECT_NAME="${AGENT_HUB_COMPOSE_PROJECT_NAME:-central-agent-data-hub-demo}"
PUBLIC_DEMO_DB_CONTAINER="${AGENT_HUB_DB_CONTAINER:-central-agent-data-hub-demo-postgres}"
PUBLIC_DEMO_DB_VOLUME="${AGENT_HUB_DB_VOLUME:-central-agent-data-hub-demo-pgdata}"
PUBLIC_DEMO_DB_NAME="${AGENT_HUB_DB_NAME:-agent_hub_demo}"
PUBLIC_DEMO_DB_PORT="${AGENT_HUB_DB_PORT:-55434}"
COMMON_GIT_DIR="$(git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
SHARED_ROOT="$ROOT_DIR"
if [[ -n "$COMMON_GIT_DIR" ]]; then
  SHARED_ROOT="$(cd "$COMMON_GIT_DIR/.." && pwd)"
fi

ENV_FILE=""
if [[ -f "$ROOT_DIR/.env" ]]; then
  ENV_FILE="$ROOT_DIR/.env"
elif [[ -f "$SHARED_ROOT/.env" ]]; then
  ENV_FILE="$SHARED_ROOT/.env"
fi

if [[ -n "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

DB_SERVICE="postgres"
DB_CONTAINER="${AGENT_HUB_DB_CONTAINER:-central-agent-data-hub-postgres}"
DB_VOLUME="${AGENT_HUB_DB_VOLUME:-central-agent-data-hub-pgdata}"
DB_NAME="${AGENT_HUB_DB_NAME:-agent_hub}"
DB_USER="${AGENT_HUB_DB_USER:-postgres}"
DB_PORT="${AGENT_HUB_DB_PORT:-55432}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
DEFAULT_DATABASE_URL="postgresql://${DB_USER}:${POSTGRES_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}"
DISPLAY_DATABASE_URL="postgresql://${DB_USER}:***@localhost:${DB_PORT}/${DB_NAME}"

export AGENT_HUB_DB_CONTAINER="$DB_CONTAINER"
export AGENT_HUB_DB_VOLUME="$DB_VOLUME"
export AGENT_HUB_DB_PORT="$DB_PORT"
export POSTGRES_PASSWORD
export DATABASE_URL="${DATABASE_URL:-$DEFAULT_DATABASE_URL}"
export OBSIDIAN_EXPORT_DIR="${OBSIDIAN_EXPORT_DIR:-$SHARED_ROOT/.local/obsidian-export}"
export AGENT_HUB_BACKUP_DIR="${AGENT_HUB_BACKUP_DIR:-$SHARED_ROOT/.local/backups}"

mask_database_url() {
  local url="$1"
  printf '%s\n' "$url" | sed -E 's#(://[^:/@]+):[^@]*@#\1:***@#'
}

database_name_from_url() {
  local url_without_query="${1%%\?*}"
  local path="${url_without_query##*/}"
  printf '%s\n' "$path"
}

configure_public_demo_database() {
  COMPOSE_PROJECT_NAME="$PUBLIC_DEMO_COMPOSE_PROJECT_NAME"
  DB_CONTAINER="$PUBLIC_DEMO_DB_CONTAINER"
  DB_VOLUME="$PUBLIC_DEMO_DB_VOLUME"
  DB_NAME="$PUBLIC_DEMO_DB_NAME"
  DB_PORT="$PUBLIC_DEMO_DB_PORT"
  DEFAULT_DATABASE_URL="postgresql://${DB_USER}:${POSTGRES_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}"
  DISPLAY_DATABASE_URL="postgresql://${DB_USER}:***@localhost:${DB_PORT}/${DB_NAME}"

  export AGENT_HUB_COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME"
  export AGENT_HUB_DB_CONTAINER="$DB_CONTAINER"
  export AGENT_HUB_DB_VOLUME="$DB_VOLUME"
  export AGENT_HUB_DB_NAME="$DB_NAME"
  export AGENT_HUB_DB_PORT="$DB_PORT"
  export DATABASE_URL="$DEFAULT_DATABASE_URL"
}

require_demo_database_target() {
  local expected_db_name="$1"
  local effective_url="$2"
  local effective_db_name
  effective_db_name="$(database_name_from_url "$effective_url")"

  if [[ "$expected_db_name" != *demo* ]]; then
    echo "Error: public demo path expects a demo database name containing 'demo'." >&2
    echo "Expected demo database name: $expected_db_name" >&2
    echo "Effective database name: $effective_db_name" >&2
    echo "Effective URL: $(mask_database_url "$effective_url")" >&2
    return 1
  fi

  if [[ "$effective_db_name" != "$expected_db_name" ]]; then
    echo "Error: public demo path refused to use a non-demo target database." >&2
    echo "Expected demo database name: $expected_db_name" >&2
    echo "Effective database name: $effective_db_name" >&2
    echo "Effective URL: $(mask_database_url "$effective_url")" >&2
    return 1
  fi
}

if [[ "$PUBLIC_DEMO_REQUESTED" == "1" ]]; then
  configure_public_demo_database
  require_demo_database_target "$DB_NAME" "$DATABASE_URL"
fi

case "$OBSIDIAN_EXPORT_DIR" in
  /*) ;;
  *) OBSIDIAN_EXPORT_DIR="$SHARED_ROOT/$OBSIDIAN_EXPORT_DIR" ;;
esac

case "$AGENT_HUB_BACKUP_DIR" in
  /*) ;;
  *) AGENT_HUB_BACKUP_DIR="$SHARED_ROOT/$AGENT_HUB_BACKUP_DIR" ;;
esac

export OBSIDIAN_EXPORT_DIR
export AGENT_HUB_BACKUP_DIR

PYTHON_BIN="${PYTHON:-python3}"
if [[ -x "$ROOT_DIR/.venv/bin/python" && -z "${PYTHON:-}" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [[ -x "$SHARED_ROOT/.venv/bin/python" && -z "${PYTHON:-}" ]]; then
  PYTHON_BIN="$SHARED_ROOT/.venv/bin/python"
fi

compose() {
  docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift

  "$@" &
  local pid=$!
  local elapsed=0

  while kill -0 "$pid" >/dev/null 2>&1; do
    if (( elapsed >= timeout_seconds )); then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 1
      kill -9 "$pid" >/dev/null 2>&1 || true
      wait "$pid" >/dev/null 2>&1 || true
      return 124
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  wait "$pid"
}

compose_quick() {
  run_with_timeout "$AGENT_HUB_DOCKER_TIMEOUT_SECONDS" docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

docker_quick() {
  run_with_timeout "$AGENT_HUB_DOCKER_TIMEOUT_SECONDS" docker "$@"
}

postgres_ready() {
  if command -v pg_isready >/dev/null 2>&1; then
    run_with_timeout "$AGENT_HUB_DB_READY_TIMEOUT_SECONDS" \
      pg_isready -h localhost -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1
    return $?
  fi

  compose_quick exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1
}

postgres_container_state() {
  docker_quick inspect "$DB_CONTAINER" \
    --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}|{{.State.ExitCode}}' \
    2>/dev/null || true
}

print_postgres_start_failure() {
  local state="$1"

  echo "Error: Postgres container did not become ready." >&2
  if [[ -n "$state" ]]; then
    echo "Container state: $state" >&2
  fi
  echo >&2
  echo "Recent container logs:" >&2
  docker_quick logs --tail 40 "$DB_CONTAINER" >&2 || true
  echo >&2
  echo "This script will not delete local Docker volumes automatically." >&2
  echo "Diagnose the local database runtime with:" >&2
  echo >&2
  if [[ "$PUBLIC_DEMO_REQUESTED" == "1" ]]; then
    echo "  scripts/db_doctor.sh --public-demo" >&2
    echo "  Use the same AGENT_HUB_* overrides if this demo run used any." >&2
  else
    echo "  agent-hub doctor" >&2
    echo "  scripts/db_doctor.sh" >&2
  fi
  echo >&2
  echo "If doctor reports stale Postgres lock files, run the guarded recovery path:" >&2
  echo >&2
  echo "  $ROOT_DIR/scripts/db_recover.sh --apply" >&2
  echo >&2
  echo "For a public demo failure, you can also use a fresh isolated demo instance:" >&2
  echo >&2
  echo "  AGENT_HUB_COMPOSE_PROJECT_NAME=adh-demo-fresh \\" >&2
  echo "  AGENT_HUB_DB_CONTAINER=adh-demo-fresh-postgres \\" >&2
  echo "  AGENT_HUB_DB_VOLUME=adh-demo-fresh-pgdata \\" >&2
  echo "  AGENT_HUB_DB_PORT=55433 \\" >&2
  echo "  scripts/first_run_demo.sh" >&2
}

run_agent_hub() {
  (cd "$ROOT_DIR" && "$PYTHON_BIN" -m agent_hub.cli "$@")
}

nearest_existing_path() {
  local path="$1"
  while [[ ! -e "$path" && "$path" != "/" ]]; do
    path="$(dirname "$path")"
  done
  printf '%s\n' "$path"
}

available_mb_for_path() {
  local path
  path="$(nearest_existing_path "$1")"
  df -Pk "$path" 2>/dev/null | awk 'NR == 2 { print int($4 / 1024) }'
}

check_temp_dir_writable() {
  local temp_dir="${TMPDIR:-/tmp}"
  local temp_path

  temp_path="$(mktemp -d "${temp_dir%/}/adh-health.XXXXXX" 2>/dev/null || true)"
  if [[ -z "$temp_path" ]]; then
    return 1
  fi
  rmdir "$temp_path" >/dev/null 2>&1 || true
}

print_host_runtime_health() {
  local compact=0
  local fatal=0
  local warning=0
  local temp_dir="${TMPDIR:-/tmp}"
  local root_free_mb=""
  local temp_free_mb=""
  local root_status="ok"
  local temp_status="ok"
  local temp_write_status="ok"

  if [[ "${1:-}" == "--compact" ]]; then
    compact=1
  fi

  root_free_mb="$(available_mb_for_path "$ROOT_DIR")"
  temp_free_mb="$(available_mb_for_path "$temp_dir")"

  for value_name in root_free_mb temp_free_mb; do
    if [[ -z "${!value_name}" ]]; then
      fatal=1
    elif (( ${!value_name} < AGENT_HUB_DISK_ERROR_MB )); then
      fatal=1
      if [[ "$value_name" == "root_free_mb" ]]; then
        root_status="error"
      else
        temp_status="error"
      fi
    elif (( ${!value_name} < AGENT_HUB_DISK_WARN_MB )); then
      warning=1
      if [[ "$value_name" == "root_free_mb" ]]; then
        root_status="warning"
      else
        temp_status="warning"
      fi
    fi
  done

  if ! check_temp_dir_writable; then
    fatal=1
    temp_write_status="error"
  fi

  if [[ "$compact" -eq 1 ]]; then
    if [[ "$fatal" -eq 1 ]]; then
      echo "Host runtime: error"
    elif [[ "$warning" -eq 1 ]]; then
      echo "Host runtime: warning"
    else
      echo "Host runtime: ok"
    fi
  else
    echo "Host runtime:"
  fi

  echo "  Repo free space: ${root_status} (${root_free_mb:-unknown} MB available; warn below ${AGENT_HUB_DISK_WARN_MB} MB; error below ${AGENT_HUB_DISK_ERROR_MB} MB)"
  echo "  Temp free space: ${temp_status} (${temp_free_mb:-unknown} MB available at ${temp_dir}; warn below ${AGENT_HUB_DISK_WARN_MB} MB; error below ${AGENT_HUB_DISK_ERROR_MB} MB)"
  echo "  Temp writable:   ${temp_write_status} (${temp_dir})"

  if [[ "$fatal" -eq 1 ]]; then
    return 2
  fi
  if [[ "$warning" -eq 1 ]]; then
    return 1
  fi
  return 0
}

wait_for_postgres() {
  local delay=2
  local elapsed=0
  local state

  echo "Waiting for ${DB_CONTAINER} to become ready (up to ${AGENT_HUB_DB_START_TIMEOUT_SECONDS}s)..."
  while (( elapsed < AGENT_HUB_DB_START_TIMEOUT_SECONDS )); do
    if postgres_ready; then
      echo "Postgres is ready."
      return 0
    fi

    state="$(postgres_container_state)"
    case "$state" in
      restarting*|exited*)
        print_postgres_start_failure "$state"
        return 1
        ;;
      *"|unhealthy|"*)
        if (( elapsed >= 10 )); then
          print_postgres_start_failure "$state"
          return 1
        fi
        ;;
    esac

    sleep "$delay"
    elapsed=$((elapsed + delay))
  done

  state="$(postgres_container_state)"
  print_postgres_start_failure "$state"
  return 1
}

apply_sql_file() {
  local sql_file="$1"
  if [[ ! -f "$sql_file" ]]; then
    echo "Error: SQL file not found: $sql_file" >&2
    return 1
  fi

  echo "Applying $sql_file"
  compose exec -T "$DB_SERVICE" \
    psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
    < "$sql_file"
}

schema_exists() {
  local result
  result="$(
    compose exec -T "$DB_SERVICE" \
      psql -At -U "$DB_USER" -d "$DB_NAME" \
      -c "SELECT to_regclass('public.projects') IS NOT NULL;" \
      2>/dev/null
  )"
  [[ "$result" == "t" ]]
}

sha256_file() {
  local path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path"
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path"
  else
    echo "Error: neither shasum nor sha256sum is available." >&2
    return 1
  fi
}

latest_backup_dump() {
  find "$AGENT_HUB_BACKUP_DIR" -maxdepth 1 -type f -name 'agent_hub-*.dump' -print 2>/dev/null \
    | sort \
    | tail -n 1
}

verify_backup_checksum() {
  local dump_path="$1"
  local sha_path="${dump_path}.sha256"

  if [[ ! -f "$sha_path" ]]; then
    echo "missing checksum: $sha_path" >&2
    return 1
  fi

  if command -v shasum >/dev/null 2>&1; then
    shasum -c "$sha_path" >/dev/null
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "$sha_path" >/dev/null
  else
    echo "neither shasum nor sha256sum is available" >&2
    return 1
  fi
}
