#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
DB_SERVICE="postgres"
DB_CONTAINER="central-agent-data-hub-postgres"
DB_VOLUME="central-agent-data-hub-pgdata"
DB_NAME="agent_hub"
DB_USER="postgres"
DB_PORT="55432"
DEFAULT_DATABASE_URL="postgresql://postgres@localhost:${DB_PORT}/${DB_NAME}"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

export DATABASE_URL="${DATABASE_URL:-$DEFAULT_DATABASE_URL}"
export OBSIDIAN_EXPORT_DIR="${OBSIDIAN_EXPORT_DIR:-$ROOT_DIR/.local/obsidian-export}"
export AGENT_HUB_BACKUP_DIR="${AGENT_HUB_BACKUP_DIR:-$ROOT_DIR/.local/backups}"

case "$OBSIDIAN_EXPORT_DIR" in
  /*) ;;
  *) OBSIDIAN_EXPORT_DIR="$ROOT_DIR/$OBSIDIAN_EXPORT_DIR" ;;
esac

case "$AGENT_HUB_BACKUP_DIR" in
  /*) ;;
  *) AGENT_HUB_BACKUP_DIR="$ROOT_DIR/$AGENT_HUB_BACKUP_DIR" ;;
esac

export OBSIDIAN_EXPORT_DIR
export AGENT_HUB_BACKUP_DIR

PYTHON_BIN="${PYTHON:-python3}"
if [[ -x "$ROOT_DIR/.venv/bin/python" && -z "${PYTHON:-}" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

run_agent_hub() {
  (cd "$ROOT_DIR" && "$PYTHON_BIN" -m agent_hub.cli "$@")
}

wait_for_postgres() {
  local tries=60
  local delay=2

  echo "Waiting for ${DB_CONTAINER} to become ready..."
  for _ in $(seq 1 "$tries"); do
    if compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
      echo "Postgres is ready."
      return 0
    fi
    sleep "$delay"
  done

  echo "Error: Postgres did not become ready in time." >&2
  compose ps
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
