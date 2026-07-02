#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1
export AGENT_HUB_COMPOSE_PROJECT_NAME="${AGENT_HUB_COMPOSE_PROJECT_NAME:-central-agent-data-hub-trust-loop}"
export AGENT_HUB_DB_CONTAINER="${AGENT_HUB_DB_CONTAINER:-central-agent-data-hub-trust-loop-postgres}"
export AGENT_HUB_DB_VOLUME="${AGENT_HUB_DB_VOLUME:-central-agent-data-hub-trust-loop-pgdata}"
export AGENT_HUB_DB_NAME="${AGENT_HUB_DB_NAME:-agent_hub_trust_loop_demo}"
export AGENT_HUB_DB_PORT="${AGENT_HUB_DB_PORT:-55435}"

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

if [[ "$DB_NAME" != *demo* ]]; then
  echo "Error: trust-loop smoke refused non-demo database: $DB_NAME" >&2
  exit 2
fi

export AGENT_HUB_REVIEWERS=demo-reviewer

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

echo "Running Agent Data Hub trust-loop smoke..."
echo "Container: $DB_CONTAINER"
echo "Database:  $DB_NAME"
echo "URL:       $DISPLAY_DATABASE_URL"
echo

compose up -d "$DB_SERVICE"
wait_for_postgres

echo "Resetting public schema in isolated trust-loop demo database..."
compose exec -T "$DB_SERVICE" \
  psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

run_agent_hub migrate --apply >/dev/null
apply_sql_file "seed/demo.sql" >/dev/null
run_agent_hub check >/dev/null

draft_json="$tmp_dir/draft.json"
inbox_json="$tmp_dir/inbox.json"
prepare_before_json="$tmp_dir/prepare-before.json"
accept_json="$tmp_dir/accept.json"
prepare_after_json="$tmp_dir/prepare-after.json"
handoff_json="$tmp_dir/handoff.json"

candidate_text="Trust loop proof candidate should enter reviewed memory only after explicit review."
task_text="trust loop proof reviewed memory"

AGENT_HUB_REVIEWERS=demo-reviewer \
  run_agent_hub remember \
    --project central-agent-data-hub-demo \
    --type fact \
    --text "$candidate_text" \
    --source "docs/public/v0.2-definition.md" \
    --metadata assigned_reviewer=demo-reviewer \
    --metadata signal_origin=trust-loop-proof \
    --agent codex \
    --agent-name Codex \
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
    raise SystemExit("expected remembered object type fact")
if obj["status"] != "draft":
    raise SystemExit(f"expected draft status, got {obj['status']!r}")
print(obj["id"])
PY
)"

AGENT_HUB_REVIEWERS=demo-reviewer \
  run_agent_hub inbox \
    --project central-agent-data-hub-demo \
    --for demo-reviewer \
    --format json >"$inbox_json"

run_agent_hub prepare \
  --project central-agent-data-hub-demo \
  --task "$task_text" \
  --format json >"$prepare_before_json"

"$PYTHON_BIN" - "$draft_id" "$inbox_json" "$prepare_before_json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

draft_id = sys.argv[1]
inbox = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
prepare = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))

if not any(row["id"] == draft_id and row["responsible_reviewer"] == "demo-reviewer" for row in inbox):
    raise SystemExit("draft is not visible in reviewer-filtered inbox")

draft_facts = prepare.get("drafts_pending_review", {}).get("facts", [])
if not any(row["id"] == draft_id and row["status"] == "draft" for row in draft_facts):
    raise SystemExit("draft is not visible as pending review in prepare output")

trail_sources = prepare.get("context_trail", {}).get("sources", [])
if not any(
    row["id"] == draft_id
    and row["review_status"] == "draft"
    and row["reason"] == "included as unconfirmed draft"
    for row in trail_sources
):
    raise SystemExit("context trail does not label the draft correctly")
PY

AGENT_HUB_REVIEWERS=demo-reviewer \
  run_agent_hub inbox \
    --project central-agent-data-hub-demo \
    --accept "$draft_id" \
    --reviewer demo-reviewer \
    --format json >"$accept_json"

run_agent_hub prepare \
  --project central-agent-data-hub-demo \
  --task "$task_text" \
  --format json >"$prepare_after_json"

run_agent_hub handoff \
  --project central-agent-data-hub-demo \
  --since 1d \
  --limit 8 \
  --format json >"$handoff_json"

"$PYTHON_BIN" - "$draft_id" "$accept_json" "$prepare_after_json" "$handoff_json" <<'PY'
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
    raise SystemExit("expected exactly one reviewed draft")
review = reviewed[0]
if review["id"] != draft_id or review["status"] != "verified":
    raise SystemExit("accepted draft did not become a verified fact")
if review["reviewed_by"] != "demo-reviewer" or review["review_source"] != "cli":
    raise SystemExit("review attribution is incomplete")
if review["responsible_reviewer"] != "demo-reviewer":
    raise SystemExit("responsible reviewer was not preserved")

verified_facts = prepare.get("verified_project_state", [])
if not any(row["id"] == draft_id and row["status"] == "verified" for row in verified_facts):
    raise SystemExit("accepted fact is not visible as reviewed project state")
draft_facts = prepare.get("drafts_pending_review", {}).get("facts", [])
if any(row["id"] == draft_id for row in draft_facts):
    raise SystemExit("accepted fact still appears as pending draft")

handoff_facts = handoff.get("facts", [])
if not any(row["id"] == draft_id and row["status"] == "verified" for row in handoff_facts):
    raise SystemExit("accepted fact is missing from handoff")
PY

"$PYTHON_BIN" - "$draft_id" <<'PY'
from __future__ import annotations

import sys

from agent_hub.db import connect

draft_id = sys.argv[1]
with connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT metadata, output
            FROM agent_actions
            WHERE action = 'inbox_accept'
              AND object_type = 'fact'
              AND object_id = %s
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (draft_id,),
        )
        row = cur.fetchone()

if not row:
    raise SystemExit("review audit action was not written")
metadata = row["metadata"] or {}
output = row["output"] or {}
for payload in (metadata, output):
    if payload.get("reviewed_by") != "demo-reviewer":
        raise SystemExit("audit reviewed_by is missing")
    if payload.get("review_source") != "cli":
        raise SystemExit("audit review_source is missing")
    if payload.get("responsible_reviewer") != "demo-reviewer":
        raise SystemExit("audit responsible_reviewer is missing")
PY

echo
echo "Trust-loop smoke: ok"
