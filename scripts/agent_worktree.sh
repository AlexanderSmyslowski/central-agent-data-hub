#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_worktree.sh --repo <path> --branch <name> [--path <path>] [--base <ref>] [--project <slug>] [--start] [--query <focus>] [--review]

Create a separate git worktree for parallel Codex/Hermes work. The helper does
not modify the original working tree and refuses to overwrite existing paths or
reuse a branch that is already checked out in another worktree.

Options:
  --repo <path>      Existing project repository or worktree.
  --branch <name>   Branch to create or check out in the new worktree.
  --path <path>     Worktree path. Default: .local/worktrees/<repo>/<branch>.
  --base <ref>      Base ref when creating a new branch. Default: HEAD.
  --project <slug>  Hub project slug, required with --start.
  --start           Run agent_start.sh inside the new worktree after creation.
  --query <focus>   Focus query passed to agent_start.sh. Requires --start.
  --review          Pass --review to agent_start.sh. Requires --start.

Exit codes:
  0  worktree prepared
  1  git or data error
  2  usage or safety error
EOF
}

REPO_PATH=""
BRANCH=""
WORKTREE_PATH=""
BASE_REF="HEAD"
PROJECT=""
START=0
QUERY=""
REVIEW=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --path)
      WORKTREE_PATH="${2:-}"
      shift 2
      ;;
    --base)
      BASE_REF="${2:-}"
      shift 2
      ;;
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --start)
      START=1
      shift
      ;;
    --query)
      QUERY="${2:-}"
      shift 2
      ;;
    --review)
      REVIEW=1
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
  echo "Error: --repo is required." >&2
  exit 2
fi

if [[ -z "$BRANCH" ]]; then
  echo "Error: --branch is required." >&2
  exit 2
fi

if [[ "$BRANCH" =~ ^- || "$BRANCH" =~ [[:space:]] ]]; then
  echo "Error: --branch must be a normal branch name without whitespace." >&2
  exit 2
fi

if [[ "$START" -eq 0 && -n "$QUERY" ]]; then
  echo "Error: --query requires --start." >&2
  exit 2
fi

if [[ "$START" -eq 0 && "$REVIEW" -eq 1 ]]; then
  echo "Error: --review requires --start." >&2
  exit 2
fi

if [[ "$START" -eq 1 && -z "$PROJECT" ]]; then
  echo "Error: --project is required with --start." >&2
  exit 2
fi

if ! REPO_ROOT="$(git -C "$REPO_PATH" rev-parse --show-toplevel 2>/dev/null)"; then
  echo "Error: --repo is not inside a git repository: $REPO_PATH" >&2
  exit 2
fi

if ! git -C "$REPO_ROOT" check-ref-format --branch "$BRANCH" >/dev/null 2>&1; then
  echo "Error: invalid branch name: $BRANCH" >&2
  exit 2
fi

REPO_NAME="$(basename "$REPO_ROOT")"
SAFE_BRANCH="$(printf '%s' "$BRANCH" | tr '/: ' '---' | tr -cd 'A-Za-z0-9._-')"
if [[ -z "$SAFE_BRANCH" ]]; then
  echo "Error: branch name cannot be converted to a safe path segment." >&2
  exit 2
fi

if [[ -z "$WORKTREE_PATH" ]]; then
  WORKTREE_PATH="$ROOT_DIR/.local/worktrees/$REPO_NAME/$SAFE_BRANCH"
fi

case "$WORKTREE_PATH" in
  /*) ;;
  *) WORKTREE_PATH="$PWD/$WORKTREE_PATH" ;;
esac

if [[ -e "$WORKTREE_PATH" ]]; then
  echo "Error: worktree path already exists: $WORKTREE_PATH" >&2
  exit 2
fi

if git -C "$REPO_ROOT" worktree list --porcelain | grep -Fxq "branch refs/heads/$BRANCH"; then
  echo "Error: branch is already checked out in another worktree: $BRANCH" >&2
  git -C "$REPO_ROOT" worktree list
  exit 2
fi

if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null; then
  echo "Error: base ref does not resolve to a commit: $BASE_REF" >&2
  exit 2
fi

mkdir -p "$(dirname "$WORKTREE_PATH")"

echo "Agent Data Hub worktree"
echo "repo:      $REPO_ROOT"
echo "branch:    $BRANCH"
echo "base:      $BASE_REF"
echo "worktree:  $WORKTREE_PATH"

if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "action:    add existing local branch"
  git -C "$REPO_ROOT" worktree add "$WORKTREE_PATH" "$BRANCH"
else
  echo "action:    create branch and add worktree"
  git -C "$REPO_ROOT" worktree add -b "$BRANCH" "$WORKTREE_PATH" "$BASE_REF"
fi

echo
echo "Worktree ready."
echo "cd $WORKTREE_PATH"

if [[ "$START" -eq 1 ]]; then
  start_args=(--project "$PROJECT")
  if [[ -n "$QUERY" ]]; then
    start_args+=(--query "$QUERY")
  fi
  if [[ "$REVIEW" -eq 1 ]]; then
    start_args+=(--review)
  fi

  echo
  echo "== Agent Start In Worktree =="
  (cd "$WORKTREE_PATH" && "$ROOT_DIR/scripts/agent_start.sh" "${start_args[@]}")
fi
