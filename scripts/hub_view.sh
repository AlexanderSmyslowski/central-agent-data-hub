#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/db_common.sh"

if ! run_agent_hub check >/dev/null; then
  echo "Error: Agent Data Hub check failed." >&2
  echo "Start the public demo database first:" >&2
  echo "  scripts/db_start_public_demo.sh" >&2
  exit 1
fi

exec "$PYTHON_BIN" -m agent_hub.hub_view "$@"
