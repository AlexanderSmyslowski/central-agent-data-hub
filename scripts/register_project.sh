#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/register_project.sh --repo <path> --slug <slug> --name <name> [options]

Compatibility wrapper for:

  agent-hub register-project --repo <path> --slug <slug> --name <name>

The installed CLI command is the public first-project bootstrap path. This
script remains for existing repo-local automation that still calls the older
script name.

Options are passed through to agent-hub register-project:
  --repo <path>          Target repo/project directory.
  --slug <slug>          Stable Hub project slug.
  --name <name>          Human-readable project name.
  --description <text>   Project description. Default is generated.
  --type <type>          Project type. Default: product.
  --memory-scope <text>  Memory scope metadata. Default: project.
  --domain-profile <x>   Optional domain profile metadata.
  --file <name>          Target agent instruction file. Default: AGENTS.md.
  --no-install           Register in DB but do not write repo-local file.
  --dry-run              Print planned actions; do not write DB or files.
  --format <text|json>   Output format.

Exit codes:
  0  registered or dry-run completed
  1  project or data error
  2  usage or operational readiness error
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
  esac
done

run_agent_hub register-project "$@"
