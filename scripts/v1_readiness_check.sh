#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/v1_readiness_check.sh [--contract-only]

Checks that the documented v1.0 local reliability contract is backed by the
current release evidence, then runs the release-candidate evidence check.

This script does not tag, publish, recover, or change release metadata.

Options:
  --contract-only  Check the v1.0 contract wiring without running smokes.
EOF
}

CONTRACT_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --contract-only)
      CONTRACT_ONLY=1
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

V1_DEFINITION="$ROOT_DIR/docs/public/v1.0-definition.md"
RELEASE_CHECK="$ROOT_DIR/scripts/release_candidate_check.sh"
EXTERNAL_SMOKE="$ROOT_DIR/scripts/smoke_external_developer.sh"
OFFLINE_SMOKE="$ROOT_DIR/scripts/smoke_agent_offline.sh"

require_text() {
  local file="$1"
  local expected="$2"

  if ! grep -Fq -- "$expected" "$file"; then
    echo "Error: expected text not found in $file:" >&2
    echo "  $expected" >&2
    return 1
  fi
}

echo "Agent Data Hub v1.0 readiness check"
echo "Repository: $ROOT_DIR"
echo "Head:       $(git -C "$ROOT_DIR" rev-parse --short HEAD)"

echo
echo "== v1.0 contract wiring =="
require_text "$V1_DEFINITION" "boringly reliable reviewed context infrastructure"
require_text "$V1_DEFINITION" "verified context for humans and agents"
require_text "$V1_DEFINITION" "scripts/v1_readiness_check.sh"
require_text "$V1_DEFINITION" "scripts/release_candidate_check.sh"
require_text "$V1_DEFINITION" "scripts/agent_start.sh --project <project-slug> --query \"<focus>\" --review"
require_text "$V1_DEFINITION" "scripts/agent_finish.sh --project <project-slug> --review --export --backup"
require_text "$V1_DEFINITION" "scripts/memory_receipt.sh --project <project-slug> --since 24h"
require_text "$V1_DEFINITION" "agent-hub prepare --project <project-slug> --task \"<task>\" --format json"
require_text "$V1_DEFINITION" "agent-hub doctor"
require_text "$V1_DEFINITION" "agent-hub status"
require_text "$V1_DEFINITION" "agent-hub check"
require_text "$V1_DEFINITION" "latest timestamped local backup was"
require_text "$V1_DEFINITION" "restored and checked"
require_text "$V1_DEFINITION" "If the Hub is offline, stop clearly before claiming writeback"

require_text "$RELEASE_CHECK" "run_step \"Public demo startup\""
require_text "$RELEASE_CHECK" "run_step \"Public demo smoke\""
require_text "$RELEASE_CHECK" "run_step \"Public demo receipt\""
require_text "$RELEASE_CHECK" "run_step \"External-developer smoke\""
require_text "$RELEASE_CHECK" "run_step \"Trust-loop smoke\""
require_text "$RELEASE_CHECK" "run_step \"Offline-agent smoke\""
require_text "$RELEASE_CHECK" "run_step \"Upgrade drill\""
require_text "$RELEASE_CHECK" "run_step \"Agent Hub doctor\""
require_text "$RELEASE_CHECK" "run_step \"Agent Hub status\""
require_text "$RELEASE_CHECK" "run_step \"Agent Hub check\""
require_text "$RELEASE_CHECK" "Release Docker runtime gate:"

require_text "$EXTERNAL_SMOKE" "scripts/agent_start.sh"
require_text "$EXTERNAL_SMOKE" "run_agent_hub remember"
require_text "$EXTERNAL_SMOKE" '--accept "$draft_id"'
require_text "$EXTERNAL_SMOKE" "run_agent_hub prepare"
require_text "$EXTERNAL_SMOKE" "run_agent_hub handoff"
require_text "$EXTERNAL_SMOKE" "--export"
require_text "$EXTERNAL_SMOKE" "--backup"
require_text "$EXTERNAL_SMOKE" "== Database Backup Verification =="
require_text "$EXTERNAL_SMOKE" "scripts/memory_receipt.sh"
require_text "$EXTERNAL_SMOKE" "fact/verified"
require_text "$EXTERNAL_SMOKE" "exported: yes"

require_text "$OFFLINE_SMOKE" "== Offline Finish Protocol =="
require_text "$OFFLINE_SMOKE" "No reviewed memory was written by this finish attempt."
require_text "$OFFLINE_SMOKE" "reviewed_memory_written: no"
require_text "$OFFLINE_SMOKE" "export_completed: no"
require_text "$OFFLINE_SMOKE" "backup_completed: no"
echo "ok: v1.0 contract wiring"

if [[ "$CONTRACT_ONLY" -eq 1 ]]; then
  echo
  echo "v1.0 readiness check: contract-only ok"
  exit 0
fi

echo
echo "== Release evidence =="
"$RELEASE_CHECK"

echo
echo "v1.0 readiness check: ok"
