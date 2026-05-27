# Central Agent Data Hub

Central Agent Data Hub ist ein v0-Projekt fuer eine zentrale, agentenlesbare Daten- und Wissensbasis rund um Projekte, Agenten, Dokumente, Fakten, Entscheidungen, offene Fragen, Risiken, Berichte und Audit-/Sync-Ereignisse.

PostgreSQL ist die operative Wahrheit: Hier liegen die normalisierten Daten, Relationen und Audit-Spuren. Obsidian ist eine menschenlesbare Projektion daraus: Markdown-Dateien werden aus der Datenbank exportiert und koennen fuer Lesen, Review und manuelle Notizen genutzt werden.

## Aktueller v0-Status

- PostgreSQL-Schema ist vorhanden: `migrations/001_init.sql`
- Demo-Seed ist vorhanden: `seed/demo.sql`
- Obsidian-Jinja2-Templates sind vorhanden: `templates/`
- Minimaler Obsidian-Exporter ist vorhanden: `agent_hub/export_obsidian.py`
- CLI-Kommando ist vorhanden: `agent-hub export`
- CLI-Platzhalter sind vorhanden, aber noch nicht implementiert: `init`, `import`, `check`, `status`

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
python -m pip install -e .
```

Exportziel setzen und Export ausfuehren:

```bash
export DATABASE_URL="postgresql://postgres@localhost:55432/agent_hub_test"
export OBSIDIAN_EXPORT_DIR="/tmp/agent-hub-obsidian"

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

## Projektstruktur

- `migrations/`: PostgreSQL-Migrationen
- `seed/`: reproduzierbare Demo-Daten
- `templates/`: Jinja2-Templates fuer Obsidian-Markdown
- `agent_hub/`: Python-Code fuer Datenbankzugriff, Markdown-Rendering, Exporter und CLI

## Was v0 Bewusst Noch Nicht Macht

- kein freier Zwei-Wege-Sync
- kein Obsidian-Rueckimport
- kein produktives Rechte-/Mandantenmodell
- keine Vektor-Suche
- keine automatische Hintergrundsynchronisation

## Naechste Sinnvolle Schritte

- `agent-hub status`
- `agent-hub check`
- Import-Allowlist
- Tests automatisieren
