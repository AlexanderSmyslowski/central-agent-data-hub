#!/usr/bin/env bash

AGENT_HUB_RUN_LOCK_DIR="${ROOT_DIR}/.local/run-locks"
AGENT_HUB_RUN_LOCK_MAX_AGE_SECONDS="${AGENT_HUB_RUN_LOCK_MAX_AGE_SECONDS:-43200}"

agent_run_repo_root() {
  local cwd="${1:-$PWD}"
  local repo_root

  if repo_root="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)"; then
    printf '%s\n' "$repo_root"
  else
    (cd "$cwd" && pwd -P)
  fi
}

agent_run_lock_key() {
  local repo_root="$1"

  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "$repo_root" | shasum -a 256 | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$repo_root" | sha256sum | awk '{print $1}'
  else
    echo "Error: neither shasum nor sha256sum is available." >&2
    return 1
  fi
}

agent_run_lock_path() {
  local repo_root="$1"
  local key

  key="$(agent_run_lock_key "$repo_root")"
  printf '%s/%s.lock\n' "$AGENT_HUB_RUN_LOCK_DIR" "$key"
}

agent_run_lock_field() {
  local lock_path="$1"
  local field="$2"

  sed -n "s/^${field}=//p" "$lock_path" 2>/dev/null | head -n 1
}

agent_run_lock_is_stale() {
  local lock_path="$1"
  local created_epoch
  local now
  local age

  created_epoch="$(agent_run_lock_field "$lock_path" "created_epoch")"
  if ! [[ "$created_epoch" =~ ^[0-9]+$ ]]; then
    return 0
  fi

  now="$(date +%s)"
  age=$((now - created_epoch))
  (( age > AGENT_HUB_RUN_LOCK_MAX_AGE_SECONDS ))
}

agent_run_lock_write() {
  local lock_path="$1"
  local project="$2"
  local repo_root="$3"
  local created_at
  local created_epoch
  local branch
  local head

  mkdir -p "$AGENT_HUB_RUN_LOCK_DIR"
  created_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  created_epoch="$(date +%s)"
  branch="$(git -C "$repo_root" branch --show-current 2>/dev/null || true)"
  head="$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || true)"

  {
    printf 'project=%s\n' "$project"
    printf 'repo=%s\n' "$repo_root"
    printf 'cwd=%s\n' "$PWD"
    printf 'branch=%s\n' "$branch"
    printf 'head=%s\n' "$head"
    printf 'created_at=%s\n' "$created_at"
    printf 'created_epoch=%s\n' "$created_epoch"
  } > "$lock_path"
}

agent_run_lock_acquire() {
  local project="$1"
  local force="${2:-0}"
  local repo_root
  local lock_path
  local lock_project
  local lock_branch
  local lock_created_at

  repo_root="$(agent_run_repo_root "$PWD")"
  lock_path="$(agent_run_lock_path "$repo_root")"

  if [[ -f "$lock_path" ]]; then
    if agent_run_lock_is_stale "$lock_path"; then
      echo "Run lock: removing stale lock for $repo_root"
      rm -f "$lock_path"
    elif [[ "$force" -eq 1 ]]; then
      echo "Run lock: replacing existing lock for $repo_root (--force-lock)"
    else
      lock_project="$(agent_run_lock_field "$lock_path" "project")"
      lock_branch="$(agent_run_lock_field "$lock_path" "branch")"
      lock_created_at="$(agent_run_lock_field "$lock_path" "created_at")"
      echo "Run lock error: another agent run is already active for this working tree." >&2
      echo "  repo:    $repo_root" >&2
      echo "  project: ${lock_project:-unknown}" >&2
      echo "  branch:  ${lock_branch:-unknown}" >&2
      echo "  since:   ${lock_created_at:-unknown}" >&2
      echo "Finish that run first, or use a separate git worktree for parallel work." >&2
      echo "If the lock is stale, rerun agent_start.sh with --force-lock." >&2
      return 2
    fi
  fi

  agent_run_lock_write "$lock_path" "$project" "$repo_root"
  echo "Run lock: acquired"
  echo "  repo: $repo_root"
  echo "  lock: $lock_path"
}

agent_run_lock_release() {
  local project="$1"
  local repo_root
  local lock_path
  local lock_project

  repo_root="$(agent_run_repo_root "$PWD")"
  lock_path="$(agent_run_lock_path "$repo_root")"

  if [[ ! -f "$lock_path" ]]; then
    echo "Run lock: none for $repo_root"
    return 0
  fi

  lock_project="$(agent_run_lock_field "$lock_path" "project")"
  if [[ -n "$lock_project" && "$lock_project" != "$project" ]]; then
    echo "Run lock: kept existing lock for project '$lock_project' in $repo_root"
    return 0
  fi

  rm -f "$lock_path"
  echo "Run lock: released"
  echo "  repo: $repo_root"
}
