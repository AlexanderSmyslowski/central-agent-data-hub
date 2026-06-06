#!/usr/bin/env bash
set -euo pipefail

TARGET_PATH=""
SCAFFOLD_SOURCE=""
FORCE=0

usage() {
  cat <<'EOF'
Usage: scripts/init_signal_inbox.sh --path <directory> [--scaffold-source <name>] [--force]

Creates a minimal local Signal Inbox root for unreviewed cross-agent signals.
This is intentionally outside PostgreSQL and does not write to Agent Data Hub
memory.

Options:
  --path <directory>   Target Signal Inbox root, for example
                       /path/to/wiki/inbox/signals
  --scaffold-source <name>
                       Optionally create a first source file, for example
                       x-research -> /path/to/wiki/inbox/signals/x-research.md
  --force              Overwrite existing scaffold files
  -h, --help           Show this help text

Exit codes:
  0  structure created or updated
  2  usage or path error
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      TARGET_PATH="${2:-}"
      shift 2
      ;;
    --scaffold-source)
      SCAFFOLD_SOURCE="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
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

if [[ -z "$TARGET_PATH" ]]; then
  echo "Error: --path is required." >&2
  usage >&2
  exit 2
fi

target_abs="$(mkdir -p "$TARGET_PATH" && cd "$TARGET_PATH" && pwd)"

slugify_source() {
  local value="${1:-}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  value="$(printf '%s' "$value" | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  printf '%s\n' "$value"
}

write_file() {
  local path="$1"
  local content="$2"

  if [[ -e "$path" && "$FORCE" -ne 1 ]]; then
    echo "skip  $path"
    return 0
  fi

  printf '%s' "$content" >"$path"
  echo "write $path"
}

readme_content=$'# Signal Inbox\n\nThis folder collects unreviewed but potentially useful signals before they reach Agent Data Hub.\n\nThe rule is simple:\n\n- signals may be captured here\n- triage happens here\n- reviewed memory belongs in Agent Data Hub, not here\n\nStart small:\n\n- keep this folder nearly empty by default\n- create a source file only when the first real signal appears\n- a single file such as `x-research.md` is enough unless a source later needs its own folder\n\nSuggested file shapes:\n\n- `x-research.md`\n- `gmail.md`\n- `hermes.md`\n- `codex.md`\n\nIf a source becomes busy, it can later grow into its own folder with `inbox.md` and extra notes.\n\nDo not store secrets, passwords, tokens, private customer data, or raw logs here.\n\nIf an older inbox file already exists elsewhere, keep it until the source agent can be pointed at this structure. Do not destroy legacy input just to rename it.\n'
inbox_template=$'# Signal Inbox\n\nAdd short signals here only when they may matter later but are not yet reviewed memory.\n\nTemplate:\n\n## YYYY-MM-DD HH:MM TZ\n- source: \n- link: \n- summary: \n- why_interesting: \n- project_hint: \n- triage_hint: keep_in_wiki\n- sensitivity: public\n- status: new\n'

write_file "$target_abs/README.md" "$readme_content"

if [[ -n "$SCAFFOLD_SOURCE" ]]; then
  source_slug="$(slugify_source "$SCAFFOLD_SOURCE")"
  if [[ -z "$source_slug" ]]; then
    echo "Error: --scaffold-source must contain at least one letter or digit." >&2
    exit 2
  fi
  write_file "$target_abs/${source_slug}.md" "$inbox_template"
fi

echo
echo "Signal Inbox ready at:"
echo "  $target_abs"
