#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NO_HUB_VIEW=0

usage() {
  cat <<'EOF'
Usage: scripts/first_run_demo.sh [--no-hub-view]

Runs the public Agent Data Hub demo path from a fresh clone:
  - checks Python and Docker
  - creates .venv if needed
  - installs the local CLI
  - creates .env from .env.example if missing
  - starts the isolated public demo database
  - runs the public demo smoke
  - starts the local Hub View unless --no-hub-view is passed

Options:
  --no-hub-view    Run setup, demo database start, and smoke, then exit.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-hub-view)
      NO_HUB_VIEW=1
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

echo "Installing Agent Data Hub into .venv"
"$ROOT_DIR/.venv/bin/python" -m pip install -e "$ROOT_DIR"

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

echo
echo "Public demo first run is ready."
echo "Open this URL:"
echo "  http://127.0.0.1:${hub_view_port}"
echo
echo "Press Ctrl-C in this terminal to stop Hub View."
echo

AGENT_HUB_PUBLIC_DEMO=1 "$ROOT_DIR/scripts/hub_view.sh" --host 127.0.0.1
