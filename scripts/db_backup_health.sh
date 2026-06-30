#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

LABEL="de.alexandersmyslowski.central-agent-data-hub.backup"
MAX_AGE_HOURS="${AGENT_HUB_BACKUP_MAX_AGE_HOURS:-36}"
REQUIRE=0
REQUIRE_REMOTE="${AGENT_HUB_REQUIRE_REMOTE_BACKUP:-0}"

usage() {
  cat <<'EOF'
Usage: scripts/db_backup_health.sh [--require] [--require-remote] [--max-age-hours HOURS]

Checks local backup freshness, local SHA256, optional remote backup parity, and
macOS LaunchAgent scheduling status.

Options:
  --require              Exit non-zero when local freshness or checksum fails.
  --require-remote       Also exit non-zero when configured remote parity fails.
  --max-age-hours HOURS  Maximum allowed local backup age. Default: 36.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require)
      REQUIRE=1
      shift
      ;;
    --require-remote)
      REQUIRE_REMOTE=1
      shift
      ;;
    --max-age-hours)
      MAX_AGE_HOURS="${2:-}"
      shift 2
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

if ! [[ "$MAX_AGE_HOURS" =~ ^[0-9]+$ ]] || (( MAX_AGE_HOURS < 1 )); then
  echo "Error: --max-age-hours must be a positive integer." >&2
  exit 2
fi

if [[ "$REQUIRE_REMOTE" != "0" && "$REQUIRE_REMOTE" != "1" ]]; then
  echo "Error: AGENT_HUB_REQUIRE_REMOTE_BACKUP must be 0 or 1." >&2
  exit 2
fi

fail_code=0
remote_warning=0

mark_problem() {
  local code="$1"
  fail_code="$code"
}

mark_remote_problem() {
  local code="$1"
  remote_warning=1
  if [[ "$REQUIRE_REMOTE" -eq 1 ]]; then
    mark_problem "$code"
  fi
}

echo "Central Agent Data Hub backup health"
echo "Backup dir:       $AGENT_HUB_BACKUP_DIR"
echo "Max age hours:    $MAX_AGE_HOURS"
echo "Remote:           ${AGENT_HUB_BACKUP_REMOTE:-not configured}"
echo "Require remote:   $REQUIRE_REMOTE"
echo

dump_path="$(latest_backup_dump)"
if [[ -z "$dump_path" ]]; then
  echo "Local backup:     missing"
  if [[ "$REQUIRE" -eq 1 ]]; then
    exit 2
  fi
  exit 0
fi

sha_path="${dump_path}.sha256"
base_name="$(basename "$dump_path")"

echo "Local backup:     $dump_path"
echo "Local checksum:   $sha_path"

age_hours="$("$PYTHON_BIN" - "$dump_path" <<'PY'
import os
import sys
import time

path = sys.argv[1]
age_seconds = max(0, time.time() - os.path.getmtime(path))
print(int(age_seconds // 3600))
PY
)"
echo "Local age hours:  $age_hours"

if (( age_hours > MAX_AGE_HOURS )); then
  echo "Freshness:        stale"
  mark_problem 2
else
  echo "Freshness:        ok"
fi

if verify_backup_checksum "$dump_path"; then
  echo "Local checksum:   ok"
else
  echo "Local checksum:   error"
  exit 1
fi

if [[ -n "${AGENT_HUB_BACKUP_REMOTE:-}" ]]; then
  remote_spec="${AGENT_HUB_BACKUP_REMOTE%/}"
  if [[ "$remote_spec" != *:* ]]; then
    echo "Remote backup:    unsupported remote format"
    mark_remote_problem 2
  else
    remote_host="${remote_spec%%:*}"
    remote_dir="${remote_spec#*:}"
    remote_path="${remote_dir}/${base_name}"
    echo "Remote path:      ${remote_host}:${remote_path}"

    set +e
    remote_sha="$(
      ssh -o BatchMode=yes -o ConnectTimeout=10 "$remote_host" \
        "test -f '$remote_path' && { if command -v sha256sum >/dev/null 2>&1; then sha256sum '$remote_path'; else shasum -a 256 '$remote_path'; fi; }" \
        2>/dev/null | awk '{print $1}'
    )"
    remote_code=$?
    set -e

    if [[ "$remote_code" -ne 0 || -z "$remote_sha" ]]; then
      echo "Remote backup:    missing or unreachable"
      mark_remote_problem 2
    else
      local_sha="$(awk '{print $1}' "$sha_path")"
      if [[ "$local_sha" == "$remote_sha" ]]; then
        echo "Remote checksum:  ok"
      else
        echo "Remote checksum:  mismatch"
        mark_remote_problem 1
      fi
    fi
  fi
else
  echo "Remote backup:    not configured"
fi

if command -v launchctl >/dev/null 2>&1; then
  plist_path="$HOME/Library/LaunchAgents/${LABEL}.plist"
  if [[ -f "$plist_path" ]] && launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    echo "LaunchAgent:      installed"
  elif [[ -f "$plist_path" ]]; then
    echo "LaunchAgent:      plist present but not loaded"
    mark_problem 2
  else
    echo "LaunchAgent:      not installed"
  fi
else
  echo "LaunchAgent:      launchctl unavailable"
fi

if [[ "$fail_code" -eq 0 ]]; then
  echo
  if [[ "$remote_warning" -eq 1 ]]; then
    echo "Backup health:    ok (remote warning)"
  else
    echo "Backup health:    ok"
  fi
  exit 0
fi

echo
if [[ "$fail_code" -eq 1 ]]; then
  echo "Backup health:    error"
else
  echo "Backup health:    not ready"
fi

if [[ "$REQUIRE" -eq 1 ]]; then
  exit "$fail_code"
fi
exit 0
