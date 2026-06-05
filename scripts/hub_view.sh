#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/db_common.sh"

"$ROOT_DIR/scripts/agent_preflight.sh" --compact

exec "$PYTHON_BIN" -m agent_hub.hub_view "$@"
