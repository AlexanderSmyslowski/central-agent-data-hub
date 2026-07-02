#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

SETUP_FILE_REL=".local/agent-hub-setup.json"
WIKI_ROOT=""
SIGNAL_INBOX_CHOICE=""
PUBLIC_DEMO_CHOICE=""
HUB_VIEW_CHOICE=""
REGISTER_PROJECT_CHOICE=""
FIRST_PROJECT_NAME=""
FIRST_PROJECT_SLUG=""
FIRST_PROJECT_REPO=""
TRIAGE_ORCHESTRATOR="human_or_agent"
DRY_RUN=0
USE_DEFAULTS=0

usage() {
  cat <<'EOF'
Usage: scripts/setup_assistant.sh [--dry-run] [--defaults]

Guided local setup for Agent Data Hub. The assistant asks only a few questions,
shows a summary, and then prepares local paths and configuration.

Options:
  --dry-run    Show the plan without writing files or creating folders.
  --defaults   Use recommended defaults without interactive prompts.
  -h, --help   Show this help text.

This assistant does not:
- write secrets
- modify an existing database
- move existing wiki or inbox files
- force a specific agent model or product
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --defaults)
      USE_DEFAULTS=1
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

prompt_with_default() {
  local prompt="$1"
  local default="$2"
  local answer=""

  if [[ "$USE_DEFAULTS" -eq 1 ]]; then
    printf '%s\n' "$default"
    return 0
  fi

  read -r -p "$prompt [$default]: " answer
  if [[ -z "$answer" ]]; then
    answer="$default"
  fi
  printf '%s\n' "$answer"
}

expand_path() {
  local value="$1"
  if [[ "$value" == "~" ]]; then
    printf '%s\n' "$HOME"
    return 0
  fi
  if [[ "${value#\~/}" != "$value" ]]; then
    printf '%s\n' "$HOME/${value#\~/}"
    return 0
  fi
  printf '%s\n' "$value"
}

normalize_yes_no() {
  local value="${1:-}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    y|yes|j|ja|true|1) printf 'yes\n' ;;
    n|no|nein|false|0) printf 'no\n' ;;
    *) return 1 ;;
  esac
}

ask_yes_no() {
  local prompt="$1"
  local default="$2"
  local raw=""
  local normalized=""

  while true; do
    raw="$(prompt_with_default "$prompt" "$default")"
    if normalized="$(normalize_yes_no "$raw")"; then
      printf '%s\n' "$normalized"
      return 0
    fi
    echo "Please answer yes or no."
    if [[ "$USE_DEFAULTS" -eq 1 ]]; then
      return 1
    fi
  done
}

json_escape() {
  "$PYTHON_BIN" -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

print_intro() {
  cat <<'EOF'
Agent Data Hub setup assistant

This guided setup prepares a calm local starting point:
- review/wiki paths
- optional Signal Inbox
- optional public demo path
- optional first project registration plan

It keeps the Hub model-independent.
The "Triage Orchestrator" is simply the human or agent process that reviews
Signal Inbox entries before anything becomes reviewed memory.
EOF
}

default_wiki_root="$HOME/Documents/Agent-Data-Hub"
default_export_dir=".local/obsidian-export"

print_intro
echo

WIKI_ROOT="$(expand_path "$(prompt_with_default "Wiki/review root" "$default_wiki_root")")"
SIGNAL_INBOX_CHOICE="$(ask_yes_no "Create a Signal Inbox?" "yes")"
PUBLIC_DEMO_CHOICE="$(ask_yes_no "Include the public demo path in next steps?" "yes")"
HUB_VIEW_CHOICE="$(ask_yes_no "Use Hub View?" "yes")"
REGISTER_PROJECT_CHOICE="$(ask_yes_no "Prepare a first real project registration?" "no")"

if [[ "$REGISTER_PROJECT_CHOICE" == "yes" ]]; then
  FIRST_PROJECT_NAME="$(prompt_with_default "First project name" "My Project")"
  FIRST_PROJECT_SLUG="$(prompt_with_default "First project slug" "my-project")"
  FIRST_PROJECT_REPO="$(expand_path "$(prompt_with_default "First project repo path" "$HOME/Projects/my-project")")"
fi

signal_inbox_dir=""
if [[ "$SIGNAL_INBOX_CHOICE" == "yes" ]]; then
  signal_inbox_dir="$WIKI_ROOT/inbox/signals"
fi

echo
echo "Planned setup"
echo "  wiki_root:         $WIKI_ROOT"
echo "  obsidian_export:   $default_export_dir"
echo "  signal_inbox:      ${signal_inbox_dir:-disabled}"
echo "  public_demo:       $PUBLIC_DEMO_CHOICE"
echo "  hub_view:          $HUB_VIEW_CHOICE"
echo "  triage_orchestrator: $TRIAGE_ORCHESTRATOR"
if [[ "$REGISTER_PROJECT_CHOICE" == "yes" ]]; then
  echo "  first_project:     $FIRST_PROJECT_NAME ($FIRST_PROJECT_SLUG)"
  echo "  first_repo:        $FIRST_PROJECT_REPO"
fi
echo "  local_setup_file:  $ROOT_DIR/$SETUP_FILE_REL"

if [[ "$DRY_RUN" -eq 1 ]]; then
  has_next_steps=0
  echo
  echo "Dry run: no files or folders were written."
  echo
  echo "Next commands after a real run:"
  if [[ "$PUBLIC_DEMO_CHOICE" == "yes" ]]; then
    has_next_steps=1
    echo "  scripts/db_start_public_demo.sh"
    echo "  scripts/smoke_public_demo.sh"
  fi
  if [[ "$HUB_VIEW_CHOICE" == "yes" ]]; then
    has_next_steps=1
    if [[ "$PUBLIC_DEMO_CHOICE" == "yes" ]]; then
      echo "  AGENT_HUB_PUBLIC_DEMO=1 AGENT_HUB_REVIEWERS=demo-reviewer HUB_VIEW_REVIEWER=demo-reviewer scripts/hub_view.sh"
    else
      echo "  scripts/hub_view.sh"
    fi
  fi
  if [[ "$SIGNAL_INBOX_CHOICE" == "yes" ]]; then
    has_next_steps=1
    echo "  scripts/init_signal_inbox.sh --path \"$signal_inbox_dir\""
  fi
  if [[ "$REGISTER_PROJECT_CHOICE" == "yes" ]]; then
    has_next_steps=1
    echo "  agent-hub register-project --repo \"$FIRST_PROJECT_REPO\" --slug \"$FIRST_PROJECT_SLUG\" --name \"$FIRST_PROJECT_NAME\""
  fi
  if [[ "$has_next_steps" -eq 0 ]]; then
    echo "  none selected"
  fi
  exit 0
fi

if [[ "$(ask_yes_no "Write this local setup now?" "yes")" != "yes" ]]; then
  echo
  echo "Setup canceled. No files or folders were written."
  exit 0
fi

mkdir -p "$WIKI_ROOT"
mkdir -p "$(dirname "$ROOT_DIR/$SETUP_FILE_REL")"

if [[ "$SIGNAL_INBOX_CHOICE" == "yes" ]]; then
  "$ROOT_DIR/scripts/init_signal_inbox.sh" --path "$signal_inbox_dir"
fi

if [[ "$REGISTER_PROJECT_CHOICE" == "yes" ]]; then
  run_agent_hub register-project \
    --repo "$FIRST_PROJECT_REPO" \
    --slug "$FIRST_PROJECT_SLUG" \
    --name "$FIRST_PROJECT_NAME" \
    --dry-run
fi

cat >"$ROOT_DIR/$SETUP_FILE_REL" <<EOF
{
  "wiki_root": $(json_escape "$WIKI_ROOT"),
  "obsidian_export_dir": $(json_escape "$default_export_dir"),
  "signal_inbox_dir": $(json_escape "$signal_inbox_dir"),
  "use_signal_inbox": $([[ "$SIGNAL_INBOX_CHOICE" == "yes" ]] && echo "true" || echo "false"),
  "use_public_demo": $([[ "$PUBLIC_DEMO_CHOICE" == "yes" ]] && echo "true" || echo "false"),
  "use_hub_view": $([[ "$HUB_VIEW_CHOICE" == "yes" ]] && echo "true" || echo "false"),
  "triage_orchestrator": $(json_escape "$TRIAGE_ORCHESTRATOR"),
  "first_project": {
    "enabled": $([[ "$REGISTER_PROJECT_CHOICE" == "yes" ]] && echo "true" || echo "false"),
    "name": $(json_escape "$FIRST_PROJECT_NAME"),
    "slug": $(json_escape "$FIRST_PROJECT_SLUG"),
    "repo_path": $(json_escape "$FIRST_PROJECT_REPO")
  }
}
EOF

echo
echo "Setup written:"
echo "  $ROOT_DIR/$SETUP_FILE_REL"
echo
echo "Recommended next steps:"
has_next_steps=0
if [[ "$PUBLIC_DEMO_CHOICE" == "yes" ]]; then
  has_next_steps=1
  echo "  scripts/db_start_public_demo.sh"
  echo "  scripts/smoke_public_demo.sh"
fi
if [[ "$HUB_VIEW_CHOICE" == "yes" ]]; then
  has_next_steps=1
  if [[ "$PUBLIC_DEMO_CHOICE" == "yes" ]]; then
    echo "  AGENT_HUB_PUBLIC_DEMO=1 AGENT_HUB_REVIEWERS=demo-reviewer HUB_VIEW_REVIEWER=demo-reviewer scripts/hub_view.sh"
  else
    echo "  scripts/hub_view.sh"
  fi
fi
if [[ "$REGISTER_PROJECT_CHOICE" == "yes" ]]; then
  has_next_steps=1
  echo "  agent-hub register-project --repo \"$FIRST_PROJECT_REPO\" --slug \"$FIRST_PROJECT_SLUG\" --name \"$FIRST_PROJECT_NAME\""
fi
if [[ "$SIGNAL_INBOX_CHOICE" == "yes" ]]; then
  has_next_steps=1
  echo "  scripts/init_signal_inbox.sh --path \"$signal_inbox_dir\""
fi
if [[ "$has_next_steps" -eq 0 ]]; then
  echo "  none selected"
fi
