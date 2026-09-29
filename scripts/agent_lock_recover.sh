#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"
source "$ROOT_DIR/scripts/agent_run_lock.sh"
# Without --digest this previews only. Mutation needs an explicit snapshot/reason.
agent_run_lock_command recover "$@"
