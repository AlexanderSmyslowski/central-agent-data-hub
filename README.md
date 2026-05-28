# Central Agent Data Hub

Central Agent Data Hub ist ein v0-Projekt fuer eine zentrale, agentenlesbare Daten- und Wissensbasis rund um Projekte, Agenten, Dokumente, Fakten, Entscheidungen, offene Fragen, Risiken, Berichte und Audit-/Sync-Ereignisse.

PostgreSQL ist die operative Wahrheit: Hier liegen die normalisierten Daten, Relationen und Audit-Spuren. Obsidian ist eine menschenlesbare Projektion daraus: Markdown-Dateien werden aus der Datenbank exportiert und koennen fuer Lesen, Review und manuelle Notizen genutzt werden.

## Aktueller v0-Status

- PostgreSQL-Schema ist vorhanden: `migrations/001_init.sql`
- Demo-Seed ist vorhanden: `seed/demo.sql`
- Obsidian-Jinja2-Templates sind vorhanden: `templates/`
- Minimaler Obsidian-Exporter ist vorhanden: `agent_hub/export_obsidian.py`
- CLI-Kommandos sind vorhanden: `agent-hub export`, `agent-hub status`, `agent-hub check`
- CLI-Platzhalter sind vorhanden, aber noch nicht implementiert: `init`, `import`

## Voraussetzungen

- Python 3.11 oder neuer
- PostgreSQL 16 oder Docker
- Umgebungsvariablen:
  - `DATABASE_URL`
  - `OBSIDIAN_EXPORT_DIR`

Beispielwerte fuer lokale Tests:

```bash
export DATABASE_URL="postgresql://postgres@localhost:55432/agent_hub_test"
export OBSIDIAN_EXPORT_DIR="/tmp/agent-hub-obsidian"
```

## Demo Lokal Ausfuehren

Eine frische PostgreSQL-16-Testdatenbank per Docker starten:

```bash
docker run --name central-agent-data-hub-demo \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB=agent_hub_test \
  -p 55432:5432 \
  -d postgres:16
```

Warten, bis PostgreSQL bereit ist:

```bash
docker exec central-agent-data-hub-demo \
  pg_isready -U postgres -d agent_hub_test
```

Migration und Demo-Seed einspielen:

```bash
docker exec -i central-agent-data-hub-demo \
  psql -v ON_ERROR_STOP=1 -U postgres -d agent_hub_test \
  < migrations/001_init.sql

docker exec -i central-agent-data-hub-demo \
  psql -v ON_ERROR_STOP=1 -U postgres -d agent_hub_test \
  < seed/demo.sql
```

Paket lokal installieren, zum Beispiel als editable install:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Exportziel setzen, Status pruefen, Konsistenz pruefen und Export ausfuehren:

```bash
export DATABASE_URL="postgresql://postgres@localhost:55432/agent_hub_test"
export OBSIDIAN_EXPORT_DIR="/tmp/agent-hub-obsidian"

agent-hub status
agent-hub check
agent-hub export
```

Demo-Container danach optional entfernen:

```bash
docker rm -f central-agent-data-hub-demo
```

## Erwartetes Ergebnis

Der Demo-Export erzeugt 10 Markdown-Dateien in sinnvollen Obsidian-Ordnern, unter anderem:

- `Projects/`
- `Documents/`
- `Reports/`
- `Decisions/`
- `Facts/`
- `Open Questions/`
- `Risks/`
- `Agent Actions/`

Jede Datei enthaelt YAML-Frontmatter, einen automatisch ueberschreibbaren Bereich und einen menschlich editierbaren Bereich:

```markdown
## Human Notes

<!-- HUMAN-NOTES:START -->

<!-- HUMAN-NOTES:END -->
```

Beim erneuten Export bleibt der Inhalt innerhalb des Human-Notes-Blocks erhalten.

## CLI Commands

- `agent-hub export`: exportiert Datenbankzeilen als Obsidian-Markdown-Dateien
- `agent-hub status`: zeigt eine schnelle Diagnose fuer Datenbank, Exportordner und Tabellenzaehlungen
- `agent-hub check`: prueft einfache Konsistenzregeln fuer Export und Review
- `agent-hub brief --project <slug>`: gibt einen kompakten Projektbrief fuer Agenten aus
- `agent-hub remember --project <slug> --type <type> --text <text>`: speichert eine gepruefte Erinnerung
- `agent-hub init`: noch nicht implementiert
- `agent-hub import`: noch nicht implementiert

## Codex-/Hermes-Gedaechtnis

Die neuen `brief`- und `remember`-Kommandos bilden den kleinen kontrollierten Zugriffspfad fuer Codex und Hermes.

Vor groesseren Arbeiten:

```bash
agent-hub brief --project commcats-de
agent-hub brief --project the-one-catering
```

Die Website-Projekte haben unterschiedliche Bearbeitungsstaende:

- `commcats-de`: aktuelle Live-Seite ist bereits eine statische Alfahosting-Website. Agenten sollen lokal in der statischen Quelle arbeiten und nur nach ausdruecklicher Freigabe hochladen.
- `the-one-catering`: aktuelle Live-Seite bleibt vorerst Framer. Agenten sollen die Live-Seite stabil halten, optisch unsichtbare SEO-/AI-Schritte vorbereiten und eine geschuetzte statische Staging-Version bauen, bevor ueber Migration gesprochen wird.

Nach relevanten, geprueften Entscheidungen:

```bash
agent-hub remember \
  --project the-one-catering \
  --type decision \
  --text "Build the static Alfahosting prototype before any live migration." \
  --rationale "The live Framer site remains in use and must not be disrupted."
```

Fuer neue Fakten mit Quelle:

```bash
agent-hub remember \
  --project commcats-de \
  --type fact \
  --text "commcats.de has a static Alfahosting deployment." \
  --source "/Users/alexandersmyslowski/Documents/commcats.de/DEPLOYMENT-LOG.md" \
  --confidence 0.95
```

Erlaubte Typen fuer `remember`:

- `fact`
- `decision`
- `open-question`
- `risk`
- `report`

Wichtig: `remember` ist fuer kuratierte, nicht-sensitive Arbeitsfakten gedacht. Passwoerter, rohe Rechnungsdaten, private Kundendaten und ungepruefte Behauptungen gehoeren nicht in den Hub.

Ein nicht-sensibler Start-Seed fuer die Website-Projekte liegt in:

```txt
seed/business_sites.sql
```

Einspielen nach der Basismigration:

```bash
docker exec -i central-agent-data-hub-demo \
  psql -v ON_ERROR_STOP=1 -U postgres -d agent_hub_test \
  < seed/business_sites.sql
```

## Status Pruefen

`agent-hub status` zeigt, ob die Grundkonfiguration arbeitsfaehig ist:

```bash
agent-hub status
```

Geprueft werden unter anderem `DATABASE_URL`, die Datenbankverbindung, `OBSIDIAN_EXPORT_DIR`, der Exportordner und die Datensatzanzahl der Kern-Tabellen.

## Konsistenz Pruefen

`agent-hub check` fuehrt einfache Konsistenzpruefungen fuer Export und Review aus:

```bash
agent-hub check
```

Bewertung:

- niedrige Confidence bei Fakten ist eine Warning
- offene Fragen sind eine Warning
- kaputte polymorphe Relationen sind ein Error
- eine nicht erreichbare Datenbank ist ein Error

## Tests Ausfuehren

Die schnellen lokalen Tests benoetigen keine Datenbank:

```bash
python3 -m compileall agent_hub
python -m pytest
agent-hub --help
agent-hub brief --help
agent-hub remember --help
```

PostgreSQL-Checks bleiben optional. Sie koennen gegen jede disposable Testdatenbank laufen, die ueber `DATABASE_URL` erreichbar ist. Docker ist dafuer praktisch, aber keine Pflicht fuer normale Entwicklung.

## Sichere Import-Richtung

`agent-hub import` ist absichtlich noch nicht implementiert. Ein spaeterer Obsidian-Rueckimport darf nur ueber eine explizite Allowlist laufen:

- erlaubte Projekt-Slugs
- erlaubte Quellpfade
- erlaubte Frontmatter-Typen
- erlaubte Zielfelder
- keine Secrets, privaten Kundendaten, rohen Rechnungsdaten oder Deployment-Credentials

Die Richtung ist in `docs/import-allowlist.md` dokumentiert.

## Projektstruktur

- `migrations/`: PostgreSQL-Migrationen
- `seed/`: reproduzierbare Demo-Daten
- `templates/`: Jinja2-Templates fuer Obsidian-Markdown
- `agent_hub/`: Python-Code fuer Datenbankzugriff, Markdown-Rendering, Exporter und CLI
- `tests/`: schnelle lokale Unit-Tests
- `ROADMAP.md`: priorisierte v0-Folgearbeiten

## Was v0 Bewusst Noch Nicht Macht

- kein freier Zwei-Wege-Sync
- kein Obsidian-Rueckimport
- kein produktives Rechte-/Mandantenmodell
- keine Vektor-Suche
- keine automatische Hintergrundsynchronisation

## Naechste Sinnvolle Schritte

- Import-Allowlist
- optionale PostgreSQL-Smoke-Tests scriptbar machen
- `agent-hub import` erst nach Allowlist-Tests implementieren
