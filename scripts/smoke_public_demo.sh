#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1

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
hub_view_smoke_port="${HUB_VIEW_SMOKE_PORT:-9876}"
hub_view_log="$(mktemp)"
hub_view_pid=""

cleanup() {
  if [[ -n "$hub_view_pid" ]]; then
    kill "$hub_view_pid" >/dev/null 2>&1 || true
    wait "$hub_view_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$hub_view_log"
}
trap cleanup EXIT

if [[ ! -f "$demo_project_export" ]]; then
  echo "Error: missing demo project export: $demo_project_export" >&2
  exit 1
fi

if [[ ! -f "$demo_compiled_export" ]]; then
  echo "Error: missing demo compiled export: $demo_compiled_export" >&2
  exit 1
fi

AGENT_HUB_PUBLIC_DEMO=1 "$ROOT_DIR/scripts/hub_view.sh" --host 127.0.0.1 --port "$hub_view_smoke_port" \
  >"$hub_view_log" 2>&1 &
hub_view_pid="$!"

if ! "$PYTHON_BIN" - "$hub_view_smoke_port" "$hub_view_log" <<'PY'
from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

port = sys.argv[1]
log_path = Path(sys.argv[2])
base_url = f"http://127.0.0.1:{port}"
last_error: Exception | None = None

for _ in range(50):
    try:
        checks = {
            "/": (
                "Hub View",
                "local review surface",
                "central-agent-data-hub-demo",
                "Connect an agent",
                "Create context pack",
                "Local agents need one-time setup",
                "terminal command is only a manual fallback",
                "/projects/central-agent-data-hub-demo/agent-context",
                "Reviewed memory",
                "#reviewed-memory",
                "#risks-and-questions",
                "#latest-status",
                "#quality",
                "Latest status",
                "Review Inbox",
                "suggested memory changes",
                "all items to review",
                "across projects",
            ),
            "/inbox": (
                "Review Inbox",
                "Suggested memory changes stay unconfirmed",
                "No items to review.",
                "When agents suggest memory changes",
                "Back to project overview",
            ),
            (
                "/projects/central-agent-data-hub-demo/agent-context"
                f"?task={quote('Review the public demo with ADH context')}"
            ): (
                "ADH context loaded",
                "Review the public demo with ADH context",
                "Source of truth: local Agent Data Hub database",
                "How this should influence the agent",
                "Known gaps",
                "Claude Code",
                "Codex",
                "Hermes or custom agent",
                "Other MCP-compatible agent",
                "One-time setup",
                "Copy Claude setup",
                "Copy Codex setup",
                "Copy startup rule",
                "Copy MCP config",
                "Show Claude manual setup pieces",
                "is instructed to request ADH context",
                "Add ADH as a local MCP server once",
                "AGENTS.md",
                'Run this from the project repository',
                '$PWD',
                "Manual fallback",
                "claude mcp add agent-data-hub",
                "agent_hub.cli mcp-serve",
                "it is not automation",
                "ADH cannot prove that an unconnected agent read the context",
                "data-copy-target=\"claude-code-setup-command\"",
                "data-copy-target=\"codex-setup-command\"",
                "data-copy-target=\"custom-startup-instruction\"",
                "data-copy-target=\"install-mcp-command\"",
                "data-copy-target=\"startup-instruction\"",
                "Copy context pack",
                "agent-hub prepare --project central-agent-data-hub-demo",
                "scripts/agent_start.sh --project central-agent-data-hub-demo",
                "# Agent Context Pack",
            ),
        }
        for path, expected_texts in checks.items():
            with urlopen(f"{base_url}{path}", timeout=1) as response:
                body = response.read().decode("utf-8", errors="replace")
            missing = [text for text in expected_texts if text not in body]
            if missing:
                print(
                    "Error: Hub View response missing expected text at "
                    f"{path}: {', '.join(missing)}",
                    file=sys.stderr,
                )
                sys.exit(1)
        sys.exit(0)
    except URLError as exc:
        last_error = exc
        time.sleep(0.1)

print(f"Error: Hub View did not answer at {base_url}/.", file=sys.stderr)
if last_error is not None:
    print(f"Last error: {last_error}", file=sys.stderr)
if log_path.exists():
    log = log_path.read_text(encoding="utf-8", errors="replace").strip()
    if log:
        print(log, file=sys.stderr)
print(
    "If the port is in use, retry with HUB_VIEW_SMOKE_PORT=<free-port>.",
    file=sys.stderr,
)
sys.exit(1)
PY
then
  exit 1
fi

echo "Public demo smoke: ok"
