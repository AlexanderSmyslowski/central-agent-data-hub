#!/usr/bin/env bash
set -euo pipefail

TARGET_PATH=""
FORCE=0

usage() {
  cat <<'EOF'
Usage: scripts/init_signal_inbox.sh --path <directory> [--force]

Creates a local Signal Inbox folder structure for unreviewed cross-agent
signals. This is intentionally outside PostgreSQL and does not write to Agent
Data Hub memory.

Options:
  --path <directory>   Target Signal Inbox root, for example
                       /path/to/wiki/inbox/signals
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

mkdir -p \
  "$target_abs/x-research" \
  "$target_abs/gmail" \
  "$target_abs/codex" \
  "$target_abs/hermes" \
  "$target_abs/web-research" \
  "$target_abs/triage"

readme_content=$'# Signal Inbox\n\nThis folder collects unreviewed but potentially useful signals before they reach Agent Data Hub.\n\nThe rule is simple:\n\n- signals may be captured here\n- triage happens here\n- reviewed memory belongs in Agent Data Hub, not here\n\nSuggested source folders:\n\n- `x-research/`\n- `gmail/`\n- `codex/`\n- `hermes/`\n- `web-research/`\n- `triage/`\n\nDo not store secrets, passwords, tokens, private customer data, or raw logs here.\n\nIf an older inbox file already exists elsewhere, keep it until the source agent can be pointed at this structure. Do not destroy legacy input just to rename it.\n'
inbox_template=$'# Inbox\n\nAdd short signals here.\n\nTemplate:\n\n## YYYY-MM-DD HH:MM TZ\n- source: \n- link: \n- summary: \n- why_interesting: \n- project_hint: \n- triage_hint: keep_in_wiki\n- sensitivity: public\n- status: new\n'
queue_template=$'# Triage Queue\n\nUse this file for reviewed triage recommendations.\n\nTemplate:\n\n## YYYY-MM-DD HH:MM TZ\n- source_note: ../x-research/inbox.md\n- signal_ref: YYYY-MM-DD HH:MM TZ\n- project: \n- recommendation: keep_in_wiki\n- rationale: \n- needs_human_review: no\n- status: triaged\n'
reviewed_template=$'# Reviewed Triage Log\n\nRecord completed triage outcomes here.\n\nTemplate:\n\n## YYYY-MM-DD HH:MM TZ\n- source: \n- project: \n- outcome: kept_in_wiki\n- follow_up: \n'
prompt_template=$'# Triage Prompt\n\nRead the source inboxes as unreviewed signals.\n\nFor each signal, decide one of:\n\n- ignore\n- keep_in_wiki\n- open_question\n- fact_candidate\n- decision_candidate\n- risk_candidate\n- skill_candidate\n- project_note\n- needs_human_review\n\nRules:\n\n- do not invent facts\n- do not write directly into Agent Data Hub without review\n- keep project boundaries explicit\n- if the signal is interesting but not yet solid, keep it in the wiki\n- if it clearly belongs to a repo rule or skill, do not force it into memory\n- never copy secrets or sensitive data into triage notes\n'

write_file "$target_abs/README.md" "$readme_content"
write_file "$target_abs/x-research/inbox.md" "$inbox_template"
write_file "$target_abs/gmail/inbox.md" "$inbox_template"
write_file "$target_abs/codex/inbox.md" "$inbox_template"
write_file "$target_abs/hermes/inbox.md" "$inbox_template"
write_file "$target_abs/web-research/inbox.md" "$inbox_template"
write_file "$target_abs/triage/queue.md" "$queue_template"
write_file "$target_abs/triage/reviewed.md" "$reviewed_template"
write_file "$target_abs/triage/prompt.md" "$prompt_template"

echo
echo "Signal Inbox ready at:"
echo "  $target_abs"
