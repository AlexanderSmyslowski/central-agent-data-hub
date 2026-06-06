#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

echo "Running public demo smoke..."

run_agent_hub status >/dev/null
run_agent_hub check >/dev/null
run_agent_hub brief --project central-agent-data-hub-demo --limit 4 >/dev/null
run_agent_hub compile --project central-agent-data-hub-demo --limit 4 >/dev/null
run_agent_hub quality --project central-agent-data-hub-demo >/dev/null
run_agent_hub export >/dev/null

demo_project_export="$OBSIDIAN_EXPORT_DIR/Projects/central-agent-data-hub-demo.md"
demo_compiled_export="$OBSIDIAN_EXPORT_DIR/Compiled/central-agent-data-hub-demo.md"

if [[ ! -f "$demo_project_export" ]]; then
  echo "Error: missing demo project export: $demo_project_export" >&2
  exit 1
fi

if [[ ! -f "$demo_compiled_export" ]]; then
  echo "Error: missing demo compiled export: $demo_compiled_export" >&2
  exit 1
fi

echo "Public demo smoke: ok"
