#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/agent_run_lock.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_lock_status.sh [--repo <path>] [--all] [--clean-orphaned]

Show local Agent Data Hub working-tree run locks. This is read-only; it does
not create, replace, or remove locks unless --clean-orphaned is explicitly set.

Options:
  --repo <path>       Show lock status for one repository or worktree. Default: cwd.
  --all               List all local run locks under .local/run-locks.
  --clean-orphaned    With --all, remove only locks whose recorded repo path no
                      longer exists. Existing repo paths are never removed.

Exit codes:
  0  no active lock for --repo, or all locks listed
  1  active lock exists for --repo
  2  usage error
EOF
}

REPO_PATH="$PWD"
ALL=0
CLEAN_ORPHANED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --all)
      ALL=1
      shift
      ;;
    --clean-orphaned)
      CLEAN_ORPHANED=1
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

if [[ -z "$REPO_PATH" ]]; then
  echo "Error: --repo requires a path." >&2
  exit 2
fi

if [[ "$CLEAN_ORPHANED" -eq 1 && "$ALL" -ne 1 ]]; then
  echo "Error: --clean-orphaned can only be used with --all." >&2
  exit 2
fi

print_lock() {
  local lock_path="$1"
  local project
  local repo
  local cwd
  local branch
  local head
  local created_at
  local stale="no"
  local orphaned="no"

  project="$(agent_run_lock_field "$lock_path" "project")"
  repo="$(agent_run_lock_field "$lock_path" "repo")"
  cwd="$(agent_run_lock_field "$lock_path" "cwd")"
  branch="$(agent_run_lock_field "$lock_path" "branch")"
  head="$(agent_run_lock_field "$lock_path" "head")"
  created_at="$(agent_run_lock_field "$lock_path" "created_at")"

  if agent_run_lock_is_stale "$lock_path"; then
    stale="yes"
  fi
  if agent_run_lock_is_orphaned "$lock_path"; then
    orphaned="yes"
  fi

  echo "- lock: $lock_path"
  echo "  project: ${project:-unknown}"
  echo "  repo: ${repo:-unknown}"
  echo "  cwd: ${cwd:-unknown}"
  echo "  branch: ${branch:-unknown}"
  echo "  head: ${head:-unknown}"
  echo "  created_at: ${created_at:-unknown}"
  echo "  stale: $stale"
  echo "  orphaned: $orphaned"
}

if [[ "$ALL" -eq 1 ]]; then
  echo "Agent Data Hub run locks"
  if [[ ! -d "$AGENT_HUB_RUN_LOCK_DIR" ]] || ! find "$AGENT_HUB_RUN_LOCK_DIR" -type f -name '*.lock' -print -quit | grep -q .; then
    echo "none"
    exit 0
  fi

  removed_count=0
  while IFS= read -r lock_path; do
    print_lock "$lock_path"
    if [[ "$CLEAN_ORPHANED" -eq 1 ]] && agent_run_lock_is_orphaned "$lock_path"; then
      rm -f "$lock_path"
      removed_count=$((removed_count + 1))
      echo "  cleanup: removed orphaned lock"
    fi
  done < <(find "$AGENT_HUB_RUN_LOCK_DIR" -type f -name '*.lock' -print | sort)
  if [[ "$CLEAN_ORPHANED" -eq 1 ]]; then
    echo "Orphaned cleanup: removed $removed_count lock(s)."
  fi
  exit 0
fi

REPO_ROOT="$(agent_run_repo_root "$REPO_PATH")"
LOCK_PATH="$(agent_run_lock_path "$REPO_ROOT")"

echo "Agent Data Hub run lock status"
echo "repo: $REPO_ROOT"

if [[ ! -f "$LOCK_PATH" ]]; then
  echo "status: unlocked"
  exit 0
fi

echo "status: locked"
print_lock "$LOCK_PATH"
exit 1
