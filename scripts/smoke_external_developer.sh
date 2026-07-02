#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1
export AGENT_HUB_COMPOSE_PROJECT_NAME="${AGENT_HUB_COMPOSE_PROJECT_NAME:-central-agent-data-hub-external-dev}"
export AGENT_HUB_DB_CONTAINER="${AGENT_HUB_DB_CONTAINER:-central-agent-data-hub-external-dev-postgres}"
export AGENT_HUB_DB_VOLUME="${AGENT_HUB_DB_VOLUME:-central-agent-data-hub-external-dev-pgdata}"
export AGENT_HUB_DB_NAME="${AGENT_HUB_DB_NAME:-agent_hub_external_dev_demo}"
export AGENT_HUB_DB_PORT="${AGENT_HUB_DB_PORT:-55437}"
export AGENT_HUB_REVIEWERS=demo-reviewer

tmp_dir="$(mktemp -d)"
export AGENT_HUB_BACKUP_DIR="$tmp_dir/backups"
export AGENT_HUB_BACKUP_REMOTE=""
export AGENT_HUB_REQUIRE_REMOTE_BACKUP=0

cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

if [[ "$DB_NAME" != *demo* ]]; then
  echo "Error: external-developer smoke refused non-demo database: $DB_NAME" >&2
  exit 2
fi

project_slug="external-developer-demo"
project_name="External Developer Demo"
external_repo="$tmp_dir/external-project"

echo "Running Agent Data Hub external-developer smoke..."
echo "Container: $DB_CONTAINER"
echo "Database:  $DB_NAME"
echo "URL:       $DISPLAY_DATABASE_URL"
echo

compose up -d "$DB_SERVICE"
wait_for_postgres

echo "Resetting public schema in isolated external-developer demo database..."
compose exec -T "$DB_SERVICE" \
  psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

run_agent_hub migrate --apply >/dev/null
apply_sql_file "seed/demo.sql" >/dev/null
run_agent_hub check >/dev/null

mkdir -p "$AGENT_HUB_BACKUP_DIR"
backup_path="$AGENT_HUB_BACKUP_DIR/agent_hub-external-developer-demo.dump"
compose exec -T "$DB_SERVICE" \
  pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom \
  > "$backup_path"
sha256_file "$backup_path" >"${backup_path}.sha256"
"$ROOT_DIR/scripts/db_backup_health.sh" --require >/dev/null

mkdir -p "$external_repo"
git -C "$external_repo" init >/dev/null
cat >"$external_repo/README.md" <<'EOF'
# External Developer Demo

This small local project is used to prove that a first external developer can
register a real repository, load reviewed ADH context, review one draft, and
finish with a handoff.
EOF

"$ROOT_DIR/scripts/register_project.sh" \
  --repo "$external_repo" \
  --slug "$project_slug" \
  --name "$project_name" \
  --description "Temporary local project for the first external developer proof." \
  --type product >/dev/null

if [[ ! -f "$external_repo/AGENTS.md" ]]; then
  echo "Error: register_project did not install AGENTS.md in the external repo." >&2
  exit 1
fi
if ! grep -q "Project slug: \`$project_slug\`" "$external_repo/AGENTS.md"; then
  echo "Error: installed AGENTS.md does not mention the registered project slug." >&2
  exit 1
fi

(
  cd "$external_repo"
  "$ROOT_DIR/scripts/agent_start.sh" \
    --project "$project_slug" \
    --query "first external developer proof" \
    --review \
    --no-lock
) >"$tmp_dir/agent-start.txt"

grep -q "Agent guard: ok" "$tmp_dir/agent-start.txt"
grep -q "ADH Context Loaded" "$tmp_dir/agent-start.txt"
grep -q "Agent start result: ready" "$tmp_dir/agent-start.txt"

candidate_text="External developer proof candidate becomes reviewed context only after explicit review."
draft_json="$tmp_dir/draft.json"
inbox_json="$tmp_dir/inbox.json"
accept_json="$tmp_dir/accept.json"
prepare_json="$tmp_dir/prepare.json"
handoff_json="$tmp_dir/handoff.json"

run_agent_hub remember \
  --project "$project_slug" \
  --type fact \
  --text "$candidate_text" \
  --source "$external_repo/README.md" \
  --metadata assigned_reviewer=demo-reviewer \
  --metadata first_external_developer_proof=true \
  --format json >"$draft_json"

draft_id="$(
  "$PYTHON_BIN" - "$draft_json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
obj = payload["object"]
if payload["type"] != "fact":
    raise SystemExit("expected fact candidate")
if obj["status"] != "draft":
    raise SystemExit(f"expected draft status, got {obj['status']!r}")
print(obj["id"])
PY
)"

run_agent_hub inbox \
  --project "$project_slug" \
  --for demo-reviewer \
  --format json >"$inbox_json"

"$PYTHON_BIN" - "$draft_id" "$inbox_json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

draft_id = sys.argv[1]
rows = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if not any(row["id"] == draft_id and row["responsible_reviewer"] == "demo-reviewer" for row in rows):
    raise SystemExit("draft is not visible in the reviewer-filtered inbox")
PY

run_agent_hub inbox \
  --project "$project_slug" \
  --accept "$draft_id" \
  --reviewer demo-reviewer \
  --format json >"$accept_json"

run_agent_hub prepare \
  --project "$project_slug" \
  --task "use the reviewed external developer context" \
  --format json >"$prepare_json"

run_agent_hub handoff \
  --project "$project_slug" \
  --since 1d \
  --limit 12 \
  --format json >"$handoff_json"

"$PYTHON_BIN" - "$draft_id" "$accept_json" "$prepare_json" "$handoff_json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

draft_id = sys.argv[1]
accept = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
prepare = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
handoff = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))

reviewed = accept.get("reviewed", [])
if len(reviewed) != 1:
    raise SystemExit("expected one accepted draft")
review = reviewed[0]
if review["id"] != draft_id or review["status"] != "verified":
    raise SystemExit("accepted draft did not become verified")
if review["reviewed_by"] != "demo-reviewer" or review["review_source"] != "cli":
    raise SystemExit("review attribution missing from accept result")

verified = prepare.get("verified_project_state", [])
if not any(row["id"] == draft_id and row["status"] == "verified" for row in verified):
    raise SystemExit("accepted fact missing from prepare reviewed state")
trail_sources = prepare.get("context_trail", {}).get("sources", [])
if not any(row["id"] == draft_id and row["review_status"] == "verified" for row in trail_sources):
    raise SystemExit("accepted fact missing from prepare context trail")
if "gaps" not in prepare:
    raise SystemExit("prepare output does not include known gaps")

handoff_facts = handoff.get("facts", [])
if not any(row["id"] == draft_id and row["status"] == "verified" for row in handoff_facts):
    raise SystemExit("accepted fact missing from handoff")
PY

(
  cd "$external_repo"
  "$ROOT_DIR/scripts/agent_finish.sh" \
    --project "$project_slug" \
    --review \
    --no-lock
) >"$tmp_dir/agent-finish.txt"

grep -q "Daily Finish Summary: $project_slug" "$tmp_dir/agent-finish.txt"
grep -q "Handoff: $project_slug" "$tmp_dir/agent-finish.txt"
grep -q "Agent finish result: ready" "$tmp_dir/agent-finish.txt"

echo
echo "External-developer smoke: ok"
