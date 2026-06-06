#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/agent_guard.sh --project <slug> [--cwd <path>]

Checks that an agent is starting in a working directory explicitly connected to
the selected Hub project. This is read-only and writes no Hub memory.

Exit codes:
  0  project and working directory match
  1  project exists, but the working directory does not match
  2  usage, configuration, or Hub access error
EOF
}

PROJECT=""
CHECK_CWD="$PWD"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-}"
      shift 2
      ;;
    --cwd)
      CHECK_CWD="${2:-}"
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

if [[ -z "$PROJECT" ]]; then
  echo "Error: --project is required." >&2
  usage >&2
  exit 2
fi

canonical_path() {
  local path="$1"
  if [[ -d "$path" ]]; then
    (cd "$path" && pwd -P)
  else
    local parent
    parent="$(dirname "$path")"
    if [[ -d "$parent" ]]; then
      printf '%s/%s\n' "$(cd "$parent" && pwd -P)" "$(basename "$path")"
    else
      printf '%s\n' "$path"
    fi
  fi
}

path_is_inside() {
  local candidate="$1"
  local root="$2"
  [[ "$candidate" == "$root" || "$candidate" == "$root"/* ]]
}

git_origin_url() {
  local path="$1"
  if [[ -d "$path" ]]; then
    git -C "$path" config --get remote.origin.url 2>/dev/null || true
  fi
}

projects_json="$(run_agent_hub projects --format json)" || {
  echo "Guard error: Hub projects unavailable." >&2
  exit 2
}

project_json="$(printf '%s' "$projects_json" | "$PYTHON_BIN" -c '
import json
import sys

slug = sys.argv[1]
projects = json.load(sys.stdin)
for project in projects:
    if project.get("slug") == slug:
        print(json.dumps(project, ensure_ascii=False))
        raise SystemExit(0)
raise SystemExit(1)
' "$PROJECT")" || {
  echo "Guard error: Hub project not found: $PROJECT" >&2
  exit 2
}

allowed_roots=()
while IFS= read -r allowed_root; do
  [[ -n "$allowed_root" ]] && allowed_roots+=("$allowed_root")
done < <(
  printf '%s' "$project_json" | "$PYTHON_BIN" -c '
import json
import sys

project = json.load(sys.stdin)
metadata = project.get("metadata") or {}
for key in ("local_path", "codex_workspace_root"):
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        print(value.strip())
'
)

if [[ "${#allowed_roots[@]}" -eq 0 ]]; then
  echo "Guard error: project '$PROJECT' has no metadata.local_path or metadata.codex_workspace_root." >&2
  echo "Register or update the project before agent work." >&2
  exit 2
fi

actual_cwd="$(canonical_path "$CHECK_CWD")"
actual_origin="$(git_origin_url "$actual_cwd")"
matched_root=""
matched_reason=""

for root in "${allowed_roots[@]}"; do
  canonical_root="$(canonical_path "$root")"
  if path_is_inside "$actual_cwd" "$canonical_root"; then
    matched_root="$canonical_root"
    matched_reason="path"
    break
  fi
  root_origin="$(git_origin_url "$canonical_root")"
  if [[ -n "$actual_origin" && -n "$root_origin" && "$actual_origin" == "$root_origin" ]]; then
    matched_root="$canonical_root"
    matched_reason="git remote"
    break
  fi
done

if [[ -z "$matched_root" ]]; then
  echo "Agent guard: project/workdir mismatch." >&2
  echo "  project: $PROJECT" >&2
  echo "  cwd:     $actual_cwd" >&2
  echo "  allowed:" >&2
  for root in "${allowed_roots[@]}"; do
    echo "    - $(canonical_path "$root")" >&2
  done
  echo "Stop: choose the correct Codex project or cd into the project repo before work." >&2
  exit 1
fi

echo "Agent guard: ok"
echo "  project: $PROJECT"
echo "  cwd:     $actual_cwd"
echo "  matched: $matched_root"
echo "  reason:  $matched_reason"
