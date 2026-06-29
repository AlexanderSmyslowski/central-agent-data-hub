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
hub_view_smoke_port="${HUB_VIEW_SMOKE_PORT:-9876}"
hub_view_log="$(mktemp)"
hub_view_pid=""

cleanup() {
  if [[ -n "$hub_view_pid" ]]; then
    kill "$hub_view_pid" >/dev/null 2>&1 || true
    wait "$hub_view_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$hub_view_log"
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
            "/": (
                "Hub View",
                "Skip to main content",
                "id=\"main-content\" tabindex=\"-1\"",
                "local review surface",
                "App navigation",
                "Current app status",
                "Area",
                "Project overview",
                "1 item",
                "Select a project",
                "Projects",
                "Review",
                "central-agent-data-hub-demo",
                "Project work center",
                "Start here when you want to see what each local project knows",
                "Latest status",
                "Attention",
                "risks/questions",
                "Review queue",
                "Reviewed memory",
                "Recommended next step",
                "Review pending suggestions before using this project with an agent.",
                "Open Review Inbox",
                "Next actions",
                "Open project",
                "Prepare agent",
                "Review suggestions",
                "Read latest status",
                "/projects/central-agent-data-hub-demo#risks-and-questions",
                "/projects/central-agent-data-hub-demo#project-memory",
                "/projects/central-agent-data-hub-demo/agent-context",
                "/projects/central-agent-data-hub-demo#latest-status",
                "/projects/central-agent-data-hub-demo",
            ),
            "/projects/central-agent-data-hub-demo": (
                "Hub View",
                "Skip to main content",
                "id=\"main-content\" tabindex=\"-1\"",
                "local review surface",
                "App navigation",
                "Current app status",
                "Project workspace",
                "Handoff ready",
                "Project workspace sidebar",
                "Project areas",
                "Latest status and watch points.",
                "Search reviewed facts and decisions.",
                "1 suggestion waits.",
                "Prepare visible context handoff.",
                "Project snapshot",
                "What needs attention now?",
                "Start with the newest status, check visible concerns",
                "Prepare agent context",
                "Work state",
                "Agent handoff",
                "Workspace areas",
                "Project memory",
                "Project memory types",
                "Rules for work",
                "Known facts",
                "Watch points",
                "Still unclear",
                "Search and inspect the reviewed context",
                "Agent handoff and review",
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
                "Use ADH with an agent",
                "Prepare reviewed context before a chatbot or local agent starts work.",
                "Review suggested changes",
                "Find reviewed memory",
                "Search facts, decisions, risks, questions, reports, and relations already on this page.",
                "Check memory quality",
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
                "Showing visible reviewed memory on this page.",
                "No visible memory matches this search.",
                "enterkeyhint=\"done\"",
                "data-memory-filter",
                "data-memory-clear",
                "data-memory-hits",
                "memory-filter-hit",
                "itemHaystack",
                "filter.blur()",
                "data-memory-type=\"decision\"",
                "data-memory-type=\"fact\"",
                "data-memory-type=\"risk\"",
                "data-memory-type=\"report\"",
                "data-memory-type=\"latest status\"",
                "data-memory-type=\"relation\"",
                "Reviewed memory",
                "#reviewed-memory",
                "#risks-and-questions",
                "#latest-status",
                "#quality",
                "#relations",
                "Project workspace",
                "Use these areas like a local app",
                "Recommended next",
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
                "Review items:",
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
            (
                "/projects/central-agent-data-hub-demo/memory/fact/"
                "00000000-0000-4000-8000-000000000201"
            ): (
                "Back to Central Agent Data Hub Demo",
                "Facts",
                "Reviewed memory is context with a source and a review status before agents use it.",
                "This page only reads the selected project memory item",
                "How to use this memory item",
                "Use as reviewed context",
                "This is reviewed project memory. Agents may use it as context",
                "Trust check",
                "Status: verified",
                "Source: docs/demo/reviewed-context.md.",
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
                "Source to check",
                "If this is wrong",
                "Should this become reviewed memory?",
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
                "Review the public demo with ADH context",
                "Source of truth: local Agent Data Hub database",
                "How this should influence the agent",
                "Known gaps",
                "Connect your agent",
                "Agent connection steps",
                "Choose agent",
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
                "Aktive Projekte",
                "Arbeitsbereiche",
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
                "Projekt-Arbeitsfläche",
                "Nutze diese Bereiche wie eine lokale App",
                "Empfohlen",
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
                "Prüfeinträge:",
                "Prüfungseingang öffnen",
                "Schritt 4",
                "Qualitätssignale",
                "Qualitätswert:",
                "Qualitätssignale öffnen",
                "Das sind Prüfsignale",
                "ADH mit Agent nutzen",
                "Geprüftes Projektgedächtnis finden",
                "Diese Seite durchsuchen",
                "Alles zeigen",
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
                "/projects/central-agent-data-hub-demo/memory/fact/"
                "00000000-0000-4000-8000-000000000201?lang=de"
            ): (
                "<html lang=\"de\">",
                "Zurück zu Central Agent Data Hub Demo",
                "Fakten",
                "Reviewed memory is context with a source and a review status before agents use it.",
                "Diese Seite liest nur den ausgewählten Eintrag",
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
                "Vorgeschlagene Änderungen am Projektgedächtnis bleiben unbestätigt",
                "Prüf-Warteschlange",
                "Karte der Prüfentscheidung",
                "Vorgeschlagene Änderungen brauchen eine menschliche Entscheidung.",
                "Eintrag finden",
                "Suche oder öffne die Warteschlange unten.",
                "Prüfspur",
                "Letzte menschliche Entscheidungen bleiben sichtbar.",
                "Einträge zur Entscheidung",
                "Was ADH merken würde",
                "Quelle prüfen",
                "Falls das falsch ist",
                "Soll das zu geprüftem Projektgedächtnis werden?",
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
