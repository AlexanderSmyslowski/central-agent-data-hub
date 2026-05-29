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
apply_sql migrations/001_init.sql
apply_sql seed/demo.sql
apply_sql seed/business_sites.sql

cat > "$TMP_DIR/import_allowlist.yml" <<EOF
projects:
  - commcats-de
  - the-one-catering
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
project_slug: commcats-de
import_key: smoke/commcats/static-context
statement: Smoke test confirms CommCats remains a static Alfahosting context.
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
project_slug: the-one-catering
import_key: smoke/the-one/framer-live
decision: Keep THE ONE live on Framer during smoke testing.
rationale: The smoke test must not imply live migration.
consequences: Static migration work remains preparatory.
status: accepted
metadata:
  smoke: true
---
EOF

cat > "$TMP_DIR/notes/open-question.md" <<EOF
---
type: open_question
project_slug: commcats-de
import_key: smoke/commcats/future-check
question: Which future smoke checks should cover the CommCats static source?
status: open
metadata:
  smoke: true
---
EOF

cat > "$TMP_DIR/notes/risk.md" <<EOF
---
type: risk
project_slug: the-one-catering
import_key: smoke/the-one/context-mix-risk
title: Smoke imports could mix website project context if slugs are wrong.
severity: medium
impact: Agents may act on the wrong website state.
mitigation: Keep explicit project_slug and allowlist checks.
status: open
metadata:
  smoke: true
---
EOF

cat > "$TMP_DIR/notes/report.md" <<EOF
---
type: report
project_slug: commcats-de
import_key: smoke/commcats/report
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
run_agent_hub brief --project commcats-de --limit 4
run_agent_hub brief --project the-one-catering --limit 4

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
        "Smoke test confirms CommCats remains a static Alfahosting context.",
        "Smoke test confirms CommCats remains a static Alfahosting context after sync apply.",
    ),
    encoding="utf-8",
)
PY
run_agent_hub sync --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --plan
run_agent_hub sync --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --apply
run_agent_hub sync --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --plan
"$PYTHON_BIN" - <<PY
import os
from pathlib import Path

import psycopg

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(
        """
        UPDATE facts
        SET statement = 'Database-only smoke conflict value.'
        WHERE metadata #>> '{agent_hub_import,import_key}' = 'smoke/commcats/static-context'
        """
    )

path = Path("$TMP_DIR/notes/fact.md")
text = path.read_text(encoding="utf-8")
path.write_text(
    text.replace(
        "Smoke test confirms CommCats remains a static Alfahosting context after sync apply.",
        "Markdown-only smoke conflict value.",
    ),
    encoding="utf-8",
)
PY
if run_agent_hub sync --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --plan; then
  echo "Error: conflict plan unexpectedly succeeded" >&2
  exit 1
else
  echo "Conflict plan blocked as expected."
fi
if run_agent_hub sync --path "$TMP_DIR/notes" --allowlist "$TMP_DIR/import_allowlist.yml" --apply; then
  echo "Error: conflict apply unexpectedly succeeded" >&2
  exit 1
else
  echo "Conflict apply blocked as expected."
fi

echo
echo "== Export and Human Notes retention =="
run_agent_hub export
PROJECT_NOTE="$OBSIDIAN_EXPORT_DIR/Projects/commcats-de.md"
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
