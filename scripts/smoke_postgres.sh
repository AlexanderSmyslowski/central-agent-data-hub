#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Error: DATABASE_URL is required for the PostgreSQL smoke test." >&2
  echo "Use a disposable local/test database only. Do not run this against production." >&2
  exit 2
fi

TMP_PARENT="${TMPDIR:-/tmp}"
TMP_PARENT="${TMP_PARENT%/}"
TMP_DIR="$(mktemp -d "$TMP_PARENT/agent-hub-smoke.XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

export OBSIDIAN_EXPORT_DIR="${OBSIDIAN_EXPORT_DIR:-$TMP_DIR/export}"
mkdir -p "$OBSIDIAN_EXPORT_DIR" "$TMP_DIR/notes"
PYTHON_BIN="${PYTHON:-python3}"
if [[ -x "$ROOT_DIR/.venv/bin/python" && -z "${PYTHON:-}" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

run_agent_hub() {
  "$PYTHON_BIN" -m agent_hub.cli "$@"
}

apply_sql() {
  "$PYTHON_BIN" - "$1" <<'PY'
import os
import sys
from pathlib import Path

import psycopg

path = Path(sys.argv[1])
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(path.read_text(encoding="utf-8"))
PY
}

echo "Central Agent Data Hub PostgreSQL smoke test"
echo "Using DATABASE_URL=(set, redacted)"
echo "Using OBSIDIAN_EXPORT_DIR=$OBSIDIAN_EXPORT_DIR"
echo "WARNING: this script applies migrations, seeds, and test imports. Use a disposable DB."
echo

echo "== Applying migration and seeds =="
run_agent_hub migrate --apply
apply_sql seed/demo.sql

cat > "$TMP_DIR/import_allowlist.yml" <<EOF
projects:
  - central-agent-data-hub-demo
roots:
  - notes
types:
  - fact
  - decision
  - open_question
  - risk
  - report
fields:
  fact: [statement, source, confidence, status, metadata]
  decision: [decision, rationale, consequences, status, metadata]
  open_question: [question, answer, status, metadata]
  risk: [title, severity, impact, mitigation, status, metadata]
  report: [title, report_type, summary, body, status, metadata]
EOF

cat > "$TMP_DIR/notes/fact.md" <<EOF
---
type: fact
project_slug: central-agent-data-hub-demo
import_key: smoke/demo/reviewed-context
statement: Smoke test confirms the neutral demo keeps reviewed context separate from drafts.
source: scripts/smoke_postgres.sh
confidence: 0.91
status: verified
metadata:
  smoke: true
---
EOF

cat > "$TMP_DIR/notes/decision.md" <<EOF
---
type: decision
project_slug: central-agent-data-hub-demo
import_key: smoke/demo/review-boundary
decision: Keep smoke data neutral and project-bound.
rationale: The smoke test should exercise write paths without maintainer-local examples.
consequences: Public test output stays safe for outside developers.
status: accepted
metadata:
  smoke: true
---
EOF

cat > "$TMP_DIR/notes/open-question.md" <<EOF
---
type: open_question
project_slug: central-agent-data-hub-demo
import_key: smoke/demo/future-check
question: Which future smoke checks should cover the neutral demo path?
status: open
metadata:
  smoke: true
---
EOF

cat > "$TMP_DIR/notes/risk.md" <<EOF
---
type: risk
project_slug: central-agent-data-hub-demo
import_key: smoke/demo/context-mix-risk
title: Smoke imports could mix project context if slugs are wrong.
severity: medium
impact: Agents may act on the wrong project state.
mitigation: Keep explicit project_slug and allowlist checks.
status: open
metadata:
  smoke: true
---
EOF

cat > "$TMP_DIR/notes/report.md" <<EOF
---
type: report
project_slug: central-agent-data-hub-demo
import_key: smoke/demo/report
title: PostgreSQL smoke report
report_type: smoke
summary: Smoke test exercised import, sync plan, export, and Human Notes.
status: published
metadata:
  smoke: true
---
The report body is sourced from Markdown.
EOF

echo
echo "== CLI diagnostics =="
run_agent_hub status
run_agent_hub check
run_agent_hub brief --project central-agent-data-hub-demo --limit 4
run_agent_hub daily --project central-agent-data-hub-demo --since 30d --limit 4 --write-report
run_agent_hub handoff --project central-agent-data-hub-demo --since 30d --limit 4
run_agent_hub review --project central-agent-data-hub-demo --limit 4
run_agent_hub search --project central-agent-data-hub-demo --query reviewed --limit 4
run_agent_hub context --project central-agent-data-hub-demo --query reviewed --limit 4

echo
echo "== Relation graph checks =="
run_agent_hub relate \
  --project central-agent-data-hub-demo \
  --source-type fact \
  --source-id 00000000-0000-4000-8000-000000000201 \
  --relation supports \
  --target-type decision \
  --target-id 00000000-0000-4000-8000-000000000401 \
  --metadata smoke=true
run_agent_hub relate \
  --project central-agent-data-hub-demo \
  --source-type fact \
  --source-id 00000000-0000-4000-8000-000000000201 \
  --relation supports \
  --target-type decision \
  --target-id 00000000-0000-4000-8000-000000000401 \
  --metadata repeated=true
run_agent_hub relate \
  --project central-agent-data-hub-demo \
  --source-type decision \
  --source-id 00000000-0000-4000-8000-000000000401 \
  --relation mitigates \
  --target-type risk \
  --target-id 00000000-0000-4000-8000-000000000501
run_agent_hub relate \
  --project central-agent-data-hub-demo \
  --source-type decision \
  --source-id 00000000-0000-4000-8000-000000000401 \
  --relation answers \
  --target-type open_question \
  --target-id 00000000-0000-4000-8000-000000000301
run_agent_hub relations --project central-agent-data-hub-demo
run_agent_hub brief --project central-agent-data-hub-demo --limit 4 --with-relations
"$PYTHON_BIN" - <<'PY'
import os

import psycopg

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    count = conn.execute(
        """
        SELECT count(*)
        FROM relations
        WHERE source_type = 'fact'
          AND source_id = '00000000-0000-4000-8000-000000000201'
          AND relation_type = 'supports'
          AND target_type = 'decision'
          AND target_id = '00000000-0000-4000-8000-000000000401'
          AND metadata @> '{"repeated": true}'::jsonb
        """
    ).fetchone()[0]
    if count != 1:
        raise SystemExit("expected idempotent supports relation with merged metadata")
PY
"$PYTHON_BIN" - <<'PY'
import os

import psycopg

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(
        """
        INSERT INTO relations (
          source_type, source_id, relation_type, target_type, target_id, metadata
        )
        VALUES (
          'fact',
          'ffffffff-ffff-4fff-8fff-ffffffffffff',
          'supports',
          'decision',
          '00000000-0000-4000-8000-000000000401',
          '{"smoke": "broken-relation"}'::jsonb
        )
        """
    )
PY
if run_agent_hub check; then
  echo "Error: broken relation check unexpectedly succeeded" >&2
  exit 1
else
  echo "Broken relation check failed as expected."
fi
"$PYTHON_BIN" - <<'PY'
import os

import psycopg

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(
        """
        DELETE FROM relations
        WHERE metadata @> '{"smoke": "broken-relation"}'::jsonb
        """
    )
PY

echo
echo "== Import and sync checks =="
run_agent_hub import --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --dry-run
run_agent_hub import --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml"
run_agent_hub import --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml"
"$PYTHON_BIN" - <<PY
from pathlib import Path
path = Path("$TMP_DIR/notes/fact.md")
text = path.read_text(encoding="utf-8")
path.write_text(
    text.replace(
        "Smoke test confirms the neutral demo keeps reviewed context separate from drafts.",
        "Smoke test confirms the neutral demo keeps reviewed context separate from drafts after sync apply.",
    ),
    encoding="utf-8",
)
PY
sync_plan="$TMP_DIR/sync-plan.txt"
set +e
run_agent_hub sync --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --plan | tee "$sync_plan"
sync_plan_status="${PIPESTATUS[0]}"
set -e
if [[ "$sync_plan_status" -eq 0 ]]; then
  echo "Error: review-gated sync plan unexpectedly succeeded without a blocker" >&2
  exit 1
fi
grep -q "review required before sync --apply" "$sync_plan"
if run_agent_hub sync --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --apply; then
  echo "Error: review-gated sync apply unexpectedly succeeded" >&2
  exit 1
else
  echo "Review-gated sync apply blocked as expected."
fi

echo
echo "== Export and Human Notes retention =="
run_agent_hub export
PROJECT_NOTE="$OBSIDIAN_EXPORT_DIR/Projects/central-agent-data-hub-demo.md"
if [[ ! -f "$PROJECT_NOTE" ]]; then
  echo "Error: expected project note not found: $PROJECT_NOTE" >&2
  exit 1
fi

"$PYTHON_BIN" - <<PY
from pathlib import Path
path = Path("$PROJECT_NOTE")
text = path.read_text(encoding="utf-8")
needle = "<!-- HUMAN-NOTES:START -->\\n"
if "Smoke human note survives export." not in text:
    path.write_text(
        text.replace(needle, needle + "\\nSmoke human note survives export.\\n", 1),
        encoding="utf-8",
    )
PY

run_agent_hub export >/dev/null
grep -q "Smoke human note survives export." "$PROJECT_NOTE"
find "$OBSIDIAN_EXPORT_DIR" -type f -name '*.md' | sort

echo
echo "Smoke test complete."
