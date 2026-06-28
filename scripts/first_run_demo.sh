#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NO_HUB_VIEW=0
MOBILE_PREVIEW=0

usage() {
  cat <<'EOF'
Usage: scripts/first_run_demo.sh [--no-hub-view] [--mobile]

Runs the public Agent Data Hub demo path from a fresh clone:
  - checks Python and Docker
  - creates .venv if needed
  - installs the local CLI if needed
  - creates .env from .env.example if missing
  - starts the isolated public demo database
  - runs the public demo smoke
  - starts the local Hub View unless --no-hub-view is passed

Options:
  --no-hub-view    Run setup, demo database start, and smoke, then exit.
  --mobile         Bind Hub View to the local network and print a phone URL.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-hub-view)
      NO_HUB_VIEW=1
      shift
      ;;
    --mobile)
      MOBILE_PREVIEW=1
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

detect_lan_ip() {
  local iface
  local ip

  if command -v route >/dev/null 2>&1 && command -v awk >/dev/null 2>&1; then
    iface="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}' || true)"
    if [[ -n "$iface" ]] && command -v ipconfig >/dev/null 2>&1; then
      ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
      if [[ -n "$ip" ]]; then
        printf '%s\n' "$ip"
        return 0
      fi
    fi
  fi

  if command -v ipconfig >/dev/null 2>&1; then
    for iface in en0 en1; do
      ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
      if [[ -n "$ip" ]]; then
        printf '%s\n' "$ip"
        return 0
      fi
    done
  fi

  if command -v hostname >/dev/null 2>&1 && command -v awk >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    if [[ -n "$ip" ]]; then
      printf '%s\n' "$ip"
      return 0
    fi
  fi

  return 1
}

install_fingerprint() {
  "$ROOT_DIR/.venv/bin/python" - "$ROOT_DIR" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
digest = hashlib.sha256()
for relative_path in ("pyproject.toml",):
    path = root / relative_path
    digest.update(relative_path.encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
}

local_cli_ready() {
  "$ROOT_DIR/.venv/bin/python" - <<'PY' >/dev/null 2>&1
from importlib.metadata import distribution

distribution("central-agent-data-hub")
import agent_hub.cli  # noqa: F401
import jinja2  # noqa: F401
import psycopg  # noqa: F401
import yaml  # noqa: F401
PY
}

PYTHON_CMD="${PYTHON:-python3}"

echo "Agent Data Hub public demo first run"
echo

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "Error: Python not found: $PYTHON_CMD" >&2
  echo "Install Python 3.11+ and retry, or set PYTHON=/path/to/python." >&2
  exit 1
fi

if ! "$PYTHON_CMD" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  echo "Error: Python 3.11+ is required." >&2
  "$PYTHON_CMD" --version >&2 || true
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker command not found." >&2
  echo "Install Docker Desktop or Docker Engine and retry." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is not running or not reachable." >&2
  echo "Start Docker Desktop or Docker Engine and retry." >&2
  exit 1
fi

cd "$ROOT_DIR"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Creating local virtual environment: .venv"
  "$PYTHON_CMD" -m venv "$ROOT_DIR/.venv"
else
  echo "Using existing local virtual environment: .venv"
fi

INSTALL_STAMP="$ROOT_DIR/.venv/.agent-data-hub-install"
INSTALL_FINGERPRINT="$(install_fingerprint)"
if (
  local_cli_ready &&
    [[ -f "$INSTALL_STAMP" ]] &&
    [[ "$(cat "$INSTALL_STAMP")" == "$INSTALL_FINGERPRINT" ]]
); then
  echo "Using existing Agent Data Hub install in .venv"
else
  echo "Installing Agent Data Hub into .venv"
  "$ROOT_DIR/.venv/bin/python" -m pip install -e "$ROOT_DIR"
  printf '%s\n' "$INSTALL_FINGERPRINT" >"$INSTALL_STAMP"
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "Creating .env from .env.example"
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
else
  echo "Keeping existing .env"
fi

echo
echo "Starting the isolated public demo database..."
"$ROOT_DIR/scripts/db_start_public_demo.sh"

echo
echo "Running the public demo check..."
"$ROOT_DIR/scripts/smoke_public_demo.sh"

if [[ "$NO_HUB_VIEW" -eq 1 ]]; then
  echo
  echo "Public demo first run completed."
  echo "Hub View was not started because --no-hub-view was passed."
  exit 0
fi

hub_view_port="${HUB_VIEW_PORT:-8765}"
hub_view_host="127.0.0.1"
hub_view_args=(--host "$hub_view_host")
hub_view_env=(AGENT_HUB_PUBLIC_DEMO=1)

if [[ -z "${HUB_VIEW_REVIEWER:-}" ]]; then
  hub_view_env+=(HUB_VIEW_REVIEWER=demo-reviewer)
  hub_view_env+=(AGENT_HUB_REVIEWERS=demo-reviewer)
fi

echo
echo "Public demo first run is ready."

if [[ "$MOBILE_PREVIEW" -eq 1 ]]; then
  hub_view_host="0.0.0.0"
  hub_view_args=(--host "$hub_view_host" --allow-lan-read)
  lan_ip="$(detect_lan_ip || true)"
  echo "Mobile preview mode is on."
  echo "Use this only on a trusted local network."
  echo "Hub View read access is explicitly opened to the local network for this run."
  echo "Review and Codex setup actions stay disabled while mobile preview is active."
  echo
  echo "Open on this Mac:"
  echo "  http://127.0.0.1:${hub_view_port}"
  if [[ -n "$lan_ip" ]]; then
    echo "Open on a phone in the same Wi-Fi:"
    echo "  http://${lan_ip}:${hub_view_port}"
  else
    echo "Could not detect the local network address automatically."
    echo "On macOS, try: ipconfig getifaddr en0"
    echo "Then open: http://<that-ip>:${hub_view_port}"
  fi
else
  echo "Open this URL:"
  echo "  http://127.0.0.1:${hub_view_port}"
  echo
  echo "Demo Review Inbox actions use reviewer: ${HUB_VIEW_REVIEWER:-demo-reviewer}"
  echo "This is local demo attribution, not authentication."
fi
echo
echo "Press Ctrl-C in this terminal to stop Hub View."
echo

env "${hub_view_env[@]}" "$ROOT_DIR/scripts/hub_view.sh" "${hub_view_args[@]}"
