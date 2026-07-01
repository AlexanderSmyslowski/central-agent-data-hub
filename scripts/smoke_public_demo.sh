#!/usr/bin/env bash
set -euo pipefail

export AGENT_HUB_PUBLIC_DEMO=1

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

echo "Running public demo smoke..."

run_agent_hub status >/dev/null
run_agent_hub check >/dev/null
run_agent_hub brief --project central-agent-data-hub-demo --limit 4 >/dev/null
run_agent_hub compile --project central-agent-data-hub-demo --limit 4 >/dev/null
run_agent_hub quality --project central-agent-data-hub-demo >/dev/null
run_agent_hub export >/dev/null

demo_project_export="$OBSIDIAN_EXPORT_DIR/Projects/central-agent-data-hub-demo.md"
demo_compiled_export="$OBSIDIAN_EXPORT_DIR/Compiled/central-agent-data-hub-demo.md"
smoke_tmp_dir="$(mktemp -d)"
hub_view_smoke_port="${HUB_VIEW_SMOKE_PORT:-9876}"
hub_view_log="$smoke_tmp_dir/hub-view.log"
hub_view_pid=""

cleanup() {
  if [[ -n "$hub_view_pid" ]]; then
    kill "$hub_view_pid" >/dev/null 2>&1 || true
    wait "$hub_view_pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$smoke_tmp_dir"
}
trap cleanup EXIT

if [[ ! -f "$demo_project_export" ]]; then
  echo "Error: missing demo project export: $demo_project_export" >&2
  exit 1
fi

if [[ ! -f "$demo_compiled_export" ]]; then
  echo "Error: missing demo compiled export: $demo_compiled_export" >&2
  exit 1
fi

prepare_json="$smoke_tmp_dir/prepare.json"
prepare_markdown="$smoke_tmp_dir/prepare.md"
run_agent_hub prepare \
  --project central-agent-data-hub-demo \
  --task "review public demo reliability" \
  --format json >"$prepare_json"
run_agent_hub prepare \
  --project central-agent-data-hub-demo \
  --task "review public demo reliability" >"$prepare_markdown"

"$PYTHON_BIN" - "$prepare_json" "$prepare_markdown" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

prepare_json = Path(sys.argv[1])
prepare_markdown = Path(sys.argv[2])
payload = json.loads(prepare_json.read_text(encoding="utf-8"))
markdown = prepare_markdown.read_text(encoding="utf-8")

errors: list[str] = []

def require(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)

trail = payload.get("context_trail") or {}
gaps = payload.get("gaps") or {}
summary = gaps.get("summary") if isinstance(gaps, dict) else {}
task_selection = trail.get("task_selection") if isinstance(trail, dict) else {}

require(payload.get("context_pack_version") == 1, "prepare context version missing")
require(
    (payload.get("project") or {}).get("slug") == "central-agent-data-hub-demo",
    "prepare project slug mismatch",
)
require(payload.get("task") == "review public demo reliability", "prepare task mismatch")
require(bool(trail.get("sources")), "prepare context trail has no sources")
require(trail.get("gap_summary") == summary, "prepare gap summary mismatch")
require(
    (summary.get("thresholds") or {}).get("stale_after_days") == 42,
    "prepare stale threshold missing",
)
require(
    task_selection.get("mode") == "deterministic_full_text",
    "prepare task selection mode mismatch",
)
require("# Agent Context Pack" in markdown, "prepare markdown missing title")
require("## ADH Context Loaded" in markdown, "prepare markdown missing receipt")
require("## Context Trail" in markdown, "prepare markdown missing context trail")
require("## Known Gaps" in markdown, "prepare markdown missing known gaps")

if errors:
    print("Error: public demo prepare smoke failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)
PY

okf_dir_one="$smoke_tmp_dir/okf-one"
okf_dir_two="$smoke_tmp_dir/okf-two"
run_agent_hub export-okf --project central-agent-data-hub-demo --out "$okf_dir_one" >/dev/null
run_agent_hub export-okf --project central-agent-data-hub-demo --out "$okf_dir_two" >/dev/null

if ! diff -ru "$okf_dir_one" "$okf_dir_two" >/dev/null; then
  echo "Error: OKF export is not byte-stable for identical demo input." >&2
  diff -ru "$okf_dir_one" "$okf_dir_two" >&2 || true
  exit 1
fi

if [[ ! -f "$okf_dir_one/index.md" || ! -f "$okf_dir_one/log.md" ]]; then
  echo "Error: OKF export did not write index.md and log.md." >&2
  exit 1
fi

if ! grep -q "Snapshot timestamp:" "$okf_dir_one/index.md"; then
  echo "Error: OKF export index is missing the stable snapshot timestamp." >&2
  exit 1
fi

if grep -q "Generated at" "$okf_dir_one/index.md" "$okf_dir_one/log.md"; then
  echo "Error: OKF export contains a wall-clock generated timestamp." >&2
  exit 1
fi

AGENT_HUB_PUBLIC_DEMO=1 \
AGENT_HUB_REVIEWERS=demo-reviewer \
HUB_VIEW_REVIEWER=demo-reviewer \
  "$ROOT_DIR/scripts/hub_view.sh" --host 127.0.0.1 --port "$hub_view_smoke_port" \
  >"$hub_view_log" 2>&1 &
hub_view_pid="$!"

if ! "$PYTHON_BIN" - "$hub_view_smoke_port" "$hub_view_log" <<'PY'
from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

port = sys.argv[1]
log_path = Path(sys.argv[2])
base_url = f"http://127.0.0.1:{port}"
last_error: Exception | None = None

for _ in range(50):
    try:
        checks = {
            "/static/base.css": (
                ":root",
                ".masthead",
            ),
            "/static/layout.css": (
                ".layout",
                ".workspace-link",
            ),
            "/static/project_overview.css": (
                ".project-overview",
                ".project-overview-focus",
            ),
            "/static/workbench.css": (
                ".workbench-header",
                ".current-state",
            ),
            "/static/memory_library.css": (
                ".memory-library-view",
                ".project-section-nav",
            ),
            "/static/memory_search.css": (
                ".memory-explorer",
                ".memory-filter-match",
                ".memory-filter-note",
                "[data-memory-section][hidden]",
            ),
            "/static/review_surfaces.css": (
                ".review-callout",
                ".review-preview",
            ),
            "/static/agent_handoff.css": (
                ".agent-form",
                ".agent-picker-card",
            ),
            "/static/quality_detail.css": (
                ".quality-overview",
                ".quality-check-grid",
            ),
            "/static/memory_detail.css": (
                ".memory-detail-view",
                ".memory-item-brief",
            ),
            "/static/responsive.css": (
                "@media (max-width: 980px)",
                "body.view-projects.has-selected-project",
            ),
            "/static/shared.js": (
                "reviewSearchAliases",
                "window.ADHHubView.searchTerms",
                "window.ADHHubView.fillTemplate",
            ),
            "/static/copy.js": (
                "data-copy-target",
                "navigator.clipboard",
            ),
            "/static/memory_search.js": (
                "data-memory-filter",
                "memory-filter-match",
                "itemHaystack",
                "openFirstMemoryMatch",
                "filter.blur()",
            ),
            "/static/project_nav.js": (
                "updateProjectSectionNav",
                "aria-current\", \"location\"",
            ),
            "/static/inbox_filter.js": (
                "data-inbox-filter",
                "inboxHaystack",
            ),
            "/static/connection_checklist.js": (
                "data-connection-check",
                "updateConnectionChecklist",
            ),
            "/": (
                "Hub View",
                "/static/base.css",
                "/static/layout.css",
                "/static/project_overview.css",
                "/static/workbench.css",
                "/static/memory_library.css",
                "/static/memory_search.css",
                "/static/review_surfaces.css",
                "/static/agent_handoff.css",
                "/static/quality_detail.css",
                "/static/memory_detail.css",
                "/static/responsive.css",
                "/static/shared.js",
                "/static/copy.js",
                "/static/memory_search.js",
                "/static/project_nav.js",
                "/static/inbox_filter.js",
                "/static/connection_checklist.js",
                "Skip to main content",
                "id=\"main-content\" tabindex=\"-1\"",
                "local review surface",
                "App navigation",
                "1 review item",
                "Projects",
                "Review",
                "central-agent-data-hub-demo",
                "Project work center",
                "Active project",
                "Start here when you want to see what each local project knows",
                "Central Agent Data Hub Demo",
                "Recommended next step",
                "Open Review Inbox",
                "Read project state",
                "Find reviewed memory",
                "Review suggestions",
                "Connect an agent",
                "Use your own project",
                "4 reviewed items",
                "1 review item",
                "Review pending suggestions before using this project with an agent.",
                "/projects/central-agent-data-hub-demo/memory",
                "/projects/central-agent-data-hub-demo/agent-context",
                "/projects/new",
                "/projects/central-agent-data-hub-demo",
            ),
            "/?lang=de": (
                "<html lang=\"de\">",
                "Projekt-Arbeitszentrale",
                "Was kann ich jetzt tun?",
                "Aktives Projekt",
                "Central Agent Data Hub Demo",
                "Empfohlener nächster Schritt",
                "4 geprüfte Einträge",
                "1 Prüfeintrag",
                "Prüfungseingang öffnen",
                "Projektstand lesen",
                "Geprüftes Projektgedächtnis finden",
                "Vorschläge prüfen",
                "Agent verbinden",
                "Eigenes Projekt nutzen",
            ),
            "/projects/new": (
                "Use ADH with your own project",
                "Choose an existing folder on this Mac",
                "Project name",
                "Short project ID",
                "Local project folder",
                "Register project",
                "What this step does",
                "ADH registers the project in the local Hub database.",
                "No repository files are written and the folder is not scanned for secrets.",
                "No agent starts automatically.",
                "After this, open the agent handoff",
            ),
            "/projects/new?lang=de": (
                "<html lang=\"de\">",
                "ADH mit deinem eigenen Projekt nutzen",
                "Wähle einen bestehenden Ordner auf diesem Mac",
                "Projektname",
                "Kurze Projekt-ID",
                "Lokaler Projektordner",
                "Projekt registrieren",
                "Was dieser Schritt macht",
                "ADH registriert das Projekt in der lokalen Hub-Datenbank.",
                "Es werden keine Repo-Dateien geschrieben",
                "Kein Agent startet automatisch.",
                "Danach öffnest du die Agentenübergabe",
            ),
            "/projects/central-agent-data-hub-demo": (
                "Hub View",
                "Skip to main content",
                "id=\"main-content\" tabindex=\"-1\"",
                "local review surface",
                "App navigation",
                "Project workspace",
                "Project workspace sidebar",
                "Project areas",
                "Latest status and watch points.",
                "Browse reviewed facts and decisions.",
                "1 suggestion waits.",
                "Prepare visible context handoff.",
                "Work state",
                "Agent handoff",
                "Project memory",
                "Project memory types",
                "Rules for work",
                "Known facts",
                "Watch points",
                "Still unclear",
                "Search and inspect the reviewed context",
                "Agent handoff and review",
                "Human review",
                "What needs a human decision?",
                "These suggestions are not reviewed memory yet.",
                "Preview only. Accept or reject in the Review Inbox",
                "Memory details",
                "Start with latest status, then check risks and questions",
                "Memory detail sections",
                "Newest report and project timestamp.",
                "Open risks and reviewed questions.",
                "Decisions, facts, and reports.",
                "Trust and review-health signals.",
                "How memory items point to each other.",
                "Use these entries as the verified base",
                "Read the newest report first",
                "Check whether an active risk or open question",
                "Fix or consciously accept the visible signals",
                "Review suggested changes",
                "Find reviewed memory",
                "Search and inspect the reviewed context this project can hand to a chatbot or local agent.",
                "Quality snapshot",
                "Quality score",
                "These are review signals",
                "Facts without source",
                "Open questions",
                "#connect-agent",
                "#memory-explorer",
                "Connect an agent",
                "Prepare agent handoff",
                "The next screen shows what ADH would give the agent",
                "Task for the agent",
                "/projects/central-agent-data-hub-demo/agent-context",
                "Search this page",
                "Matches appear below while the page sections are filtered.",
                "Press Enter or open the first match",
                "Open first match",
                "Showing visible reviewed memory on this page.",
                "No visible memory matches this search.",
                "enterkeyhint=\"done\"",
                "data-memory-filter",
                "memory-filter-actions",
                "data-memory-first",
                "data-memory-clear",
                "role=\"status\" aria-live=\"polite\"",
                "data-memory-hits",
                "Search matches",
                "memory-filter-hit",
                "data-memory-type=\"decision\"",
                "data-memory-type=\"fact\"",
                "data-memory-type=\"risk\"",
                "data-memory-type=\"report\"",
                "data-memory-type=\"latest status\"",
                "data-memory-type=\"relation\"",
                "Reviewed memory",
                "Project sections",
                "On this project",
                "data-project-section-nav",
                "data-section-target",
                "#reviewed-memory",
                "#risks-and-questions",
                "#latest-status",
                "#quality",
                "#relations",
                "Current work state",
                "Read this first. It shows the latest report",
                "Step 1",
                "Reports:",
                "Open latest status",
                "Step 2",
                "Needs attention",
                "Risks:",
                "Questions:",
                "Open risks and questions",
                "Step 3",
                "Review queue",
                "Review item: 1",
                "Open Review Inbox",
                "Step 4",
                "Quality signals",
                "Quality score:",
                "Open quality signals",
                "Latest status",
                "Review Inbox",
                "suggested memory changes",
                "Open detail",
                "/projects/central-agent-data-hub-demo/memory/fact/00000000-0000-4000-8000-000000000201",
            ),
            "/projects/central-agent-data-hub-demo/memory": (
                "Reviewed memory library",
                "Browse the reviewed facts, decisions, risks, questions, and reports",
                "Filter reviewed memory by type",
                "All entries",
                "Facts",
                "Decisions",
                "Risks",
                "Open questions",
                "Reports",
                "Find an entry",
                "Search is active. Only matching sections and entries are shown below.",
                "Show all entries",
                "Continue from this memory",
                "Find one useful entry",
                "Prepare agent handoff",
                "Review suggestions",
                "Back to work state",
                "/projects/central-agent-data-hub-demo/agent-context",
                "/inbox",
                "#current-state-title",
                "Showing",
                "reviewed entries",
                "data-memory-search-note",
                "data-memory-section",
                "data-memory-section-count",
                "data-search-template",
                "Reviewed memory is context with a source and a review status before agents use it.",
                "Open detail",
                "/projects/central-agent-data-hub-demo/memory/fact/00000000-0000-4000-8000-000000000201",
            ),
            (
                "/projects/central-agent-data-hub-demo/memory/fact/"
                "00000000-0000-4000-8000-000000000201"
            ): (
                "Back to memory library",
                "Show only Facts",
                "Continue in this app",
                "/projects/central-agent-data-hub-demo/memory",
                "/projects/central-agent-data-hub-demo/memory?type=fact",
                "/inbox",
                "/projects/central-agent-data-hub-demo/agent-context",
                "Facts",
                "Reviewed memory is context with a source and a review status before agents use it.",
                "This page only reads the selected project memory item",
                "Memory item at a glance",
                "What this is",
                "Why it can be trusted",
                "How to use it",
                "Memory detail quick actions",
                "Check status and source before relying on it.",
                "Open source, status, confidence, and update fields.",
                "Prepare a visible context handoff with this reviewed memory.",
                "How to use this memory item",
                "Use as reviewed context",
                "This is reviewed project memory. Agents may use it as context",
                "Trust check",
                "Status: verified",
                "Source: docs/demo/reviewed-context.md.",
                "Use outside Hub View",
                "Copy this item",
                "Copy this exact reviewed item",
                "data-copy-target=\"memory-item-copy-text\"",
                "Agent Data Hub reviewed memory item for Central Agent Data Hub Demo",
                "Use this as context only; copying it does not change the Hub database.",
                "Continue from here",
                "Back to project section",
                "Prepare agent handoff",
                "Source",
                "docs/demo/reviewed-context.md",
                "Related memory",
                "Points to this item",
                "Document: Concept: Reviewed Context",
                "supports",
                "Status",
                "verified",
            ),
            "/inbox": (
                "Review Inbox",
                "Suggested memory changes stay unconfirmed",
                "Review Inbox quick actions",
                "Review next suggestion",
                "Filter waiting items",
                "Open review history",
                "Review queue",
                "Current review decision",
                "Open the next suggestion",
                "Jump to first suggestion",
                "Accept only when the sentence is correct, useful, sourced, and safe for future agents.",
                "Accept becomes reviewed memory. Reject archives the suggestion without promoting it.",
                "id=\"first-review-item\"",
                "Review decision map",
                "Suggested memory changes need a human decision.",
                "Find an item",
                "Search or open the queue below.",
                "Audit trail",
                "Recent human decisions stay visible.",
                "Items to decide",
                "What ADH would remember",
                "Remember as a verified fact",
                "Source to check",
                "Source: reports/demo/review-flow.md",
                "If this is wrong",
                "Future work may rely on a false assumption.",
                "Should this become reviewed memory?",
                "Decision impact",
                "If accepted",
                "Becomes reviewed memory",
                "ADH stores it as reviewed context and records who accepted it.",
                "If rejected",
                "Stays out of reviewed memory",
                "How to review",
                "Would you want an agent to rely on this later?",
                "Is the origin concrete enough to trust?",
                "Accept stores it as reviewed memory. Reject archives it.",
                "Open one card, check the sentence and source",
                "Review actions",
                "Human decision needed",
                "demo-reviewer",
                "Back to project overview",
            ),
            "/inbox/activity": (
                "Review history",
                "This read-only view shows recent human decisions",
                "No review history yet.",
                "Back to Review Inbox",
            ),
            (
                "/projects/central-agent-data-hub-demo/agent-context"
                f"?task={quote('Review the public demo with ADH context')}"
            ): (
                "ADH context loaded",
                "Continue in this app",
                "/projects/central-agent-data-hub-demo/memory",
                "/inbox",
                "Review the public demo with ADH context",
                "Source of truth: local Agent Data Hub database",
                "How this should influence the agent",
                "Known gaps",
                "Connect your agent",
                "Copy text into chat",
                "it never runs an agent by itself",
                "Which agent do you use?",
                "Connection status",
                "ADH cannot prove that an unconnected agent read the context",
                "Recommended next step",
                "Demo project: no local write.",
                "The public demo can show the target and the context pack",
                "Choose an agent path",
                "View all checks",
                "Test the connection",
                "Visible proof",
                "These checkmarks stay in this browser page only.",
                "Manual checks completed: 0.",
                "Still open",
                "Looks ready",
                "The setup command was run once.",
                "A new Claude Code task shows an ADH receipt",
                "The startup rule was stored",
                "The next agent run shows an ADH receipt",
                "The context pack was copied.",
                "The context pack is visible in the chat before the task.",
                "data-connection-checklist",
                "data-connection-check",
                "Which agent do you use?",
                "Connect once where possible",
                "Connect once",
                "Check the handoff",
                "#agent-chatbot",
                "#agent-codex",
                "#agent-claude",
                "#agent-custom",
                "#agent-mcp",
                "#agent-terminal",
                "Claude Code",
                "Codex",
                "Hermes or custom agent",
                "Other MCP-compatible agent",
                "Connection verification",
                "ADH can check Codex here",
                "must be checked in their own app",
                "Demo preview only",
                "Manual check needed",
                "Persistent rule needed",
                "Per-task copy/paste",
                "Manual every task",
                "One local click",
                "One copied command",
                "Persistent instruction",
                "Copy MCP config",
                "Temporary fallback",
                "One-time setup",
                "Copy Claude setup",
                "Install Codex setup",
                "Copy fallback command",
                "Copy startup rule",
                "Copy MCP config",
                "Jump to chatbot text",
                "Use this when ADH knows the local project folder",
                "Check: Codex shows an ADH Context Loaded receipt at task start",
                "Check: the context pack is visible in the chat before the task",
                "Check: the agent shows an ADH receipt or matching counts",
                "Check: the terminal prints one visible ADH-backed run",
                "Show Claude manual setup pieces",
                "is instructed to request ADH context",
                "Add ADH as a local MCP server once",
                "AGENTS.md",
                "Demo preview",
                "ADH knows this checkout path",
                "Project folder:",
                "Target file:",
                "Planned action:",
                "Preview AGENTS.md block",
                "scripts/install_repo_agent_memory.sh",
                "--repo",
                "--dry-run",
                "Manual fallback",
                "For local agents: start a new task",
                "claude mcp add agent-data-hub",
                "agent_hub.cli mcp-serve",
                "it is not automation",
                "ADH cannot prove that an unconnected agent read the context",
                "data-copy-target=\"claude-code-setup-command\"",
                "data-copy-target=\"codex-setup-command\"",
                "data-copy-target=\"custom-startup-instruction\"",
                "data-copy-target=\"install-mcp-command\"",
                "data-copy-target=\"startup-instruction\"",
                "Copy chatbot text",
                "agent-hub prepare --project central-agent-data-hub-demo",
                "scripts/agent_start.sh --project central-agent-data-hub-demo",
                "# Agent Context Pack",
            ),
            "/projects/central-agent-data-hub-demo?lang=de": (
                "<html lang=\"de\">",
                "Zum Hauptinhalt springen",
                "lokale Prüfoberfläche",
                "App-Navigation",
                "Arbeitsstand",
                "Agentenübergabe",
                "Projektbereiche",
                "In diesem Projekt",
                "data-project-section-nav",
                "data-section-target",
                "Projektgedächtnis",
                "Arten von Projektgedächtnis",
                "Vorgaben für Arbeit",
                "Bekannte Fakten",
                "Im Blick behalten",
                "Noch unklar",
                "Durchsuche und prüfe den bestätigten Kontext",
                "Agentenübergabe und Prüfung",
                "Detailansicht",
                "Beginne mit dem letzten Stand, prüfe dann Risiken und Fragen",
                "Detailbereiche im Projektgedächtnis",
                "Neuester Bericht und Projektzeitpunkt.",
                "Offene Risiken und geprüfte Fragen.",
                "Entscheidungen, Fakten und Berichte.",
                "Vertrauens- und Prüfsignale.",
                "Wie Gedächtnis-Einträge zusammenhängen.",
                "Nutze diese Einträge als geprüfte Grundlage",
                "Lies zuerst den neuesten Bericht",
                "Prüfe, ob ein aktives Risiko",
                "Behebe oder akzeptiere die sichtbaren Signale bewusst",
                "Aktueller Arbeitsstand",
                "Lies das zuerst. Hier siehst du letzten Bericht",
                "Schritt 1",
                "Berichte:",
                "Letzten Stand öffnen",
                "Schritt 2",
                "Braucht Aufmerksamkeit",
                "Risiken:",
                "Fragen:",
                "Risiken und Fragen öffnen",
                "Schritt 3",
                "Prüf-Warteschlange",
                "Prüfeintrag: 1",
                "Prüfungseingang öffnen",
                "Schritt 4",
                "Qualitätssignale",
                "Qualitätswert:",
                "Qualitätssignale öffnen",
                "Das sind Prüfsignale",
                "Geprüftes Projektgedächtnis finden",
                "Diese Seite durchsuchen",
                "Suchtreffer",
                "role=\"status\" aria-live=\"polite\"",
                "Drücke Enter oder öffne den ersten Treffer",
                "Ersten Treffer öffnen",
                "Alle Einträge zeigen",
                "Agentenübergabe vorbereiten",
                "Dieses Projekt mit ADH-Kontext prüfen",
                "Neutrales Demo-Projekt",
                "Central Agent Data Hub Demo",
                "Detail öffnen",
                "/projects/central-agent-data-hub-demo/memory/fact/00000000-0000-4000-8000-000000000201?lang=de",
                "/inbox?lang=de",
                "/projects/central-agent-data-hub-demo/agent-context",
                "name=\"lang\" value=\"de\"",
            ),
            (
                "/projects/central-agent-data-hub-demo/agent-context"
                f"?lang=de&task={quote('Dieses Projekt mit ADH-Kontext prüfen')}"
            ): (
                "<html lang=\"de\">",
                "ADH-Kontext geladen",
                "Agent verbinden",
                "Beginne mit der Karte für dein Werkzeug",
                "Welchen Agenten nutzt du?",
                "Text in den Chat kopieren",
                "Verbindungsstatus",
                "Empfohlener nächster Schritt",
                "Demo-Projekt: kein lokales Schreiben.",
                "Die öffentliche Demo zeigt Ziel und Kontextpaket",
                "Agentenweg wählen",
                "Alle Prüfungen ansehen",
                "Verbindung testen",
                "Sichtbarer Nachweis",
                "Diese Haken bleiben nur in dieser Browserseite.",
                "Manuelle Prüfungen erledigt: 0.",
                "Noch offen",
                "Sieht bereit aus",
                "Der Einrichtungsbefehl wurde einmal ausgeführt.",
                "Eine neue Claude-Code-Aufgabe zeigt einen ADH-Beleg",
                "Die Startregel wurde in der eigenen Agenten-Konfiguration gespeichert.",
                "Der nächste Agentenlauf zeigt einen ADH-Beleg",
                "Das Kontextpaket wurde kopiert.",
                "Das Kontextpaket steht vor der Aufgabe sichtbar im Chat.",
                "Welchen Agenten nutzt du?",
                "Verbindung prüfen",
                "Geprüfte Entscheidungen werden zu Arbeitsgrenzen",
                "Geprüfte Fakten dürfen als Projektannahmen genutzt werden.",
                "Aktive Risiken und offene Fragen bleiben sichtbar",
                "Entwürfe bleiben als unbestätigt markiert",
                "ADH kann Codex hier prüfen.",
                "ADH kann nicht beweisen, dass ein unverbundener Agent den Kontext gelesen hat.",
            ),
            (
                "/projects/central-agent-data-hub-demo/memory/fact/"
                "00000000-0000-4000-8000-000000000201?lang=de"
            ): (
                "<html lang=\"de\">",
                "Zurück zur Gedächtnisbibliothek",
                "Nur Fakten zeigen",
                "Weiter in der App",
                "Geprüftes Gedächtnis",
                "Prüfungseingang",
                "Agentenübergabe",
                "Fakten",
                "Reviewed memory is context with a source and a review status before agents use it.",
                "Diese Seite liest nur den ausgewählten Eintrag",
                "Eintrag auf einen Blick",
                "Was ist das?",
                "Warum vertrauenswürdig?",
                "Wie nutzen?",
                "Schnellzugriff im Gedächtnisdetail",
                "Prüfe Status und Quelle, bevor du dich darauf stützt.",
                "Weiterarbeiten",
                "Öffne Quelle, Status, Vertrauen und Aktualisierung.",
                "Bereite eine sichtbare Kontextübergabe mit diesem geprüften Eintrag vor.",
                "Quelle",
                "docs/demo/reviewed-context.md",
                "Zusammenhänge",
                "Zeigt auf diesen Eintrag",
                "Dokument: Concept: Reviewed Context",
                "stützt",
                "Status",
                "geprüft",
            ),
            "/inbox?lang=de": (
                "<html lang=\"de\">",
                "Prüfungseingang",
                "Weiter in der App",
                "Projekte",
                "Prüfverlauf",
                "Vorgeschlagene Änderungen am Projektgedächtnis bleiben unbestätigt",
                "Schnellzugriff im Prüfungseingang",
                "Nächsten Vorschlag prüfen",
                "Wartende Einträge filtern",
                "Prüfverlauf öffnen",
                "Prüf-Warteschlange",
                "Karte der Prüfentscheidung",
                "Vorgeschlagene Änderungen brauchen eine menschliche Entscheidung.",
                "Eintrag finden",
                "Suche oder öffne die Warteschlange unten.",
                "Prüfspur",
                "Letzte menschliche Entscheidungen bleiben sichtbar.",
                "Einträge zur Entscheidung",
                "Was ADH merken würde",
                "Als gesicherten Fakt merken",
                "Quelle prüfen",
                "Quelle: reports/demo/review-flow.md",
                "Falls das falsch ist",
                "Spätere Arbeit könnte von einer falschen Annahme ausgehen.",
                "Soll das zu geprüftem Projektgedächtnis werden?",
                "Folge der Entscheidung",
                "Wenn gemerkt",
                "Wird geprüftes Projektgedächtnis",
                "Wenn verworfen",
                "Bleibt draußen",
                "Prüfe jeweils eine vorgeschlagene Änderung",
                "Nichts hier wird zu geprüftem Projektgedächtnis",
                "So prüfst du",
                "Soll ein Agent sich später darauf verlassen?",
                "Ist die Herkunft konkret genug",
                "Merken übernimmt es ins geprüfte Projektgedächtnis",
                "Öffne eine Karte, prüfe Satz und Quelle",
                "Prüfaktionen",
                "demo-reviewer",
                "Zurück zur Projektübersicht",
            ),
            "/inbox/activity?lang=de": (
                "<html lang=\"de\">",
                "Prüfverlauf",
                "Diese reine Leseansicht zeigt letzte menschliche Entscheidungen",
                "Noch kein Prüfverlauf.",
                "Zurück zum Prüfungseingang",
            ),
            (
                "/projects/central-agent-data-hub-demo/agent-context"
                f"?task={quote('Demo mit ADH-Kontext prüfen')}&lang=de"
            ): (
                "<html lang=\"de\">",
                "ADH-Kontext geladen",
                "Aufgabe",
                "Wie das den Agenten beeinflussen soll",
                "Bekannte Lücken",
                "Agent verbinden",
                "Beginne mit der Karte für dein Werkzeug",
                "Welchen Agenten nutzt du?",
                "Verbindung prüfen",
                "Text in den Chat kopieren",
                "Nur Demo-Vorschau",
                "Prüfen: Codex zeigt beim Start einen ADH-Kontext-Beleg.",
                "Prüfen: Das Kontextpaket steht vor der Aufgabe sichtbar im Chat.",
                "Terminal-Übergang starten",
                "ADH kann nicht beweisen",
                "# Agent Context Pack",
            ),
        }
        for path, expected_texts in checks.items():
            with urlopen(f"{base_url}{path}", timeout=1) as response:
                body = response.read().decode("utf-8", errors="replace")
            missing = [text for text in expected_texts if text not in body]
            if missing:
                print(
                    "Error: Hub View response missing expected text at "
                    f"{path}: {', '.join(missing)}",
                    file=sys.stderr,
                )
                sys.exit(1)
        sys.exit(0)
    except URLError as exc:
        last_error = exc
        time.sleep(0.1)

print(f"Error: Hub View did not answer at {base_url}/.", file=sys.stderr)
if last_error is not None:
    print(f"Last error: {last_error}", file=sys.stderr)
if log_path.exists():
    log = log_path.read_text(encoding="utf-8", errors="replace").strip()
    if log:
        print(log, file=sys.stderr)
print(
    "If the port is in use, retry with HUB_VIEW_SMOKE_PORT=<free-port>.",
    file=sys.stderr,
)
sys.exit(1)
PY
then
  exit 1
fi

echo "Public demo smoke: ok"
