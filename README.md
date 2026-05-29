# Central Agent Data Hub

Central Agent Data Hub ist ein v0-Projekt fuer eine zentrale, agentenlesbare Daten- und Wissensbasis rund um Projekte, Agenten, Dokumente, Fakten, Entscheidungen, offene Fragen, Risiken, Berichte und Audit-/Sync-Ereignisse.

PostgreSQL ist die operative Wahrheit: Hier liegen die normalisierten Daten, Relationen und Audit-Spuren. Obsidian ist eine menschenlesbare Projektion daraus: Markdown-Dateien werden aus der Datenbank exportiert und koennen fuer Lesen, Review und manuelle Notizen genutzt werden.

## Aktueller v0-Status

- PostgreSQL-Schema, Migrationstracking und Relations-Erweiterung sind vorhanden: `migrations/001_init.sql`, `migrations/002_schema_migrations.sql`, `migrations/003_relation_agent_actions.sql`
- Demo-Seed ist vorhanden: `seed/demo.sql`
- Obsidian-Jinja2-Templates sind vorhanden: `templates/`
- Minimaler Obsidian-Exporter ist vorhanden: `agent_hub/export_obsidian.py`
- CLI-Kommandos sind vorhanden: `agent-hub migrate`, `agent-hub export`, `agent-hub status`, `agent-hub check`, `agent-hub projects`, `agent-hub brief`, `agent-hub daily`, `agent-hub handoff`, `agent-hub review`, `agent-hub search`, `agent-hub context`, `agent-hub remember`, `agent-hub relations`, `agent-hub relate`, `agent-hub import`, `agent-hub sync`
- CLI-Platzhalter sind vorhanden, aber noch nicht implementiert: `init`

## Voraussetzungen

- Python 3.11 oder neuer
- PostgreSQL 16 oder Docker/Docker Compose
- Umgebungsvariablen:
  - `DATABASE_URL`
  - `OBSIDIAN_EXPORT_DIR`
  - optional `AGENT_HUB_BACKUP_DIR`
  - optional `AGENT_HUB_BACKUP_MAX_AGE_HOURS`
  - optional `AGENT_HUB_BACKUP_REMOTE`

Beispielwerte fuer die dauerhafte lokale Hub-DB:

```bash
export DATABASE_URL="postgresql://postgres@localhost:55432/agent_hub"
export OBSIDIAN_EXPORT_DIR=".local/obsidian-export"
```

Eine Vorlage fuer lokale Konfiguration liegt in `.env.example`. Eine echte `.env` bleibt lokal und wird nicht committed.

## Durable Local Hub Database

Fuer den normalen Agentenbetrieb gibt es eine dauerhafte lokale PostgreSQL-DB per Docker Compose. Sie nutzt ein persistentes Docker-Volume, startet mit `restart: unless-stopped` wieder und bleibt erhalten, auch wenn der Container neu erstellt wird.

Feste lokale Namen:

- Container: `central-agent-data-hub-postgres`
- Volume: `central-agent-data-hub-pgdata`
- Datenbank: `agent_hub`
- Port: `55432`
- URL: `postgresql://postgres@localhost:55432/agent_hub`

Starten und initialisieren:

```bash
scripts/db_start.sh
```

Das Skript startet die Compose-DB, wartet auf den Healthcheck, fuehrt `agent-hub migrate --apply` aus und spielt den nicht-sensiblen Business-Sites-Seed ein. `seed/demo.sql` wird bewusst nur auf Wunsch geladen:
Zusaetzlich wird `seed/agentic_projects.sql` fuer nicht-sensitive agentische Projektkontexte wie `catering-agents-platform` eingespielt.

```bash
scripts/db_start.sh --demo
```

Status und Readiness pruefen:

```bash
scripts/db_status.sh
```

Das zeigt Container, Volume, Port, Healthcheck, Backup-Health, `agent-hub status` und einen kurzen `commcats-de`-Brief.

Backup erstellen:

```bash
scripts/db_backup.sh
```

Standardziel ist `.local/backups/`. Das Skript nutzt `pg_dump` im Postgres-Container, erzeugt einen Custom-Format-Dump und schreibt eine SHA256-Datei. Wenn `AGENT_HUB_BACKUP_REMOTE` gesetzt ist, kopiert es Dump und Checksumme zusaetzlich per `rsync` auf den Server:

```bash
export AGENT_HUB_BACKUP_REMOTE="user@example.com:/path/to/agent-hub-backups/"
scripts/db_backup.sh
```

Neuesten lokalen Backup-Stand anzeigen:

```bash
scripts/db_backup_latest.sh
```

Backup-Health pruefen:

```bash
scripts/db_backup_health.sh
```

Der Healthcheck prueft den neuesten lokalen Dump, SHA256, Backup-Alter, den macOS LaunchAgent-Status und, wenn `AGENT_HUB_BACKUP_REMOTE` gesetzt ist, ob der gleiche Dump auf dem Remote-Ziel liegt und dieselbe Pruefsumme hat. Standardmaessig gelten Backups nach 36 Stunden als stale; lokal kann das mit `AGENT_HUB_BACKUP_MAX_AGE_HOURS` geaendert werden.

Backup verifizieren:

```bash
scripts/db_verify_backup.sh
```

Das Skript restored den neuesten Dump in einen temporaeren Postgres-Container auf Port `55433`, fuehrt `agent-hub check` und einen Projektbrief aus und entfernt den Test-Container danach wieder.

Restore in die lokale Betriebs-DB:

```bash
scripts/db_restore.sh --confirm .local/backups/agent_hub-YYYYMMDD-HHMMSS.dump
```

Restore ist absichtlich explizit: Das Skript ersetzt den Inhalt der lokalen `agent_hub`-Datenbank und verlangt deshalb `--confirm`.

Rollen der Speicherorte:

- GitHub enthaelt Code, Schema, Seeds, Templates, Doku und Tests.
- Die lokale Postgres-DB ist die operative Wahrheit fuer Agenten-Gedaechtnis.
- Obsidian ist Projektion und kontrollierter Importkanal, nicht die alleinige Wahrheit.
- Server-Backups sind Wiederherstellungspunkte als Dump-Dateien, kein Live-DB-Sync.

## Operational Readiness Fuer Agenten

Vor Agenten-Writeback oder groesseren Projektarbeiten sollte der Hub in dieser Reihenfolge geprueft werden:

```bash
scripts/db_status.sh
scripts/db_backup.sh
scripts/db_verify_backup.sh
scripts/agent_preflight.sh
```

`scripts/agent_preflight.sh` ist read-only. Es prueft Docker/Compose, den laufenden Durable-DB-Container, offene oder fehlgeschlagene Migrationen, Backup-Health mit Remote-Paritaet, `agent-hub status`, `agent-hub check` und Baseline-Projekt-Briefs.

## Schema-Migrationen

Migrationen liegen in `migrations/` und werden in Dateireihenfolge angewendet. `migrations/001_init.sql` bleibt die unveraenderte Baseline; `migrations/002_schema_migrations.sql` fuehrt die Tabelle `schema_migrations` ein; `migrations/003_relation_agent_actions.sql` erlaubt Relations auf Agenten-Auditzeilen.

Status anzeigen:

```bash
agent-hub migrate --status
```

Offene Migrationen anwenden:

```bash
agent-hub migrate --apply
```

Bestehende Datenbanken werden beim ersten Lauf nachtraeglich migrationsfaehig gemacht: Wenn das Basisschema bereits existiert, wird `001_init.sql` als angewendet registriert und nur das Migrationstracking ergaenzt. Agenten-Writeback soll erst laufen, wenn keine Migration mehr offen oder fehlgeschlagen ist.

Exit-Codes:

- `0`: bereit fuer Agentenarbeit
- `1`: Daten- oder Konsistenzfehler
- `2`: Konfiguration oder Betriebsabhaengigkeit fehlt

Optional kann ein taegliches lokales Backup als macOS LaunchAgent eingerichtet werden:

```bash
scripts/install_backup_launch_agent.sh
```

Der LaunchAgent ruft `scripts/db_backup.sh` lokal auf. Remote-Kopie passiert nur, wenn `AGENT_HUB_BACKUP_REMOTE` lokal gesetzt ist. Server-Zugangsdaten gehoeren nicht ins Repo.

## Agent Workflow

Vor Projektarbeiten nutzen Agenten bevorzugt den Start-Wrapper:

```bash
scripts/agent_start.sh --project <project-slug>
scripts/agent_start.sh --project <project-slug> --query "<aktueller arbeitsfokus>"
```

Der Start-Wrapper fuehrt Preflight, Projektbrief, Daily Activity und optional ein fokussiertes Kontextpaket aus.

Die niedrigeren Bausteine bleiben verfuegbar:

```bash
scripts/project_context.sh --project <project-slug>
scripts/project_context.sh --project <project-slug> --daily
scripts/project_context.sh --all-projects
scripts/project_context.sh --project commcats-de
scripts/project_context.sh --project the-one-catering
scripts/project_context.sh --all-websites
```

Nach abgeschlossener Arbeit nutzen Agenten den Finish-Wrapper:

```bash
scripts/agent_finish.sh --project <project-slug>
```

Der Finish-Wrapper erzeugt Daily Summary und Handoff. Mit `--write-report` kann explizit ein Daily-Report in Postgres gespeichert werden.

Gepruefte, nicht-sensitive Erinnerungen werden danach kontrolliert geschrieben:

```bash
scripts/project_remember.sh \
  --project commcats-de \
  --type fact \
  --text "Reviewed project memory goes here." \
  --source "non-sensitive source or review note"
```

`scripts/project_remember.sh` ist ein Schutzlayer um `agent-hub remember`: Es fuehrt Preflight und Safety-Scan aus, blockiert Projekterzeugung, verlangt Quellen fuer Fakten, erlaubt `--dry-run` und kann nach erfolgreichem Writeback optional direkt eine kuratierte Relation anlegen. Details und Beispiele stehen in `docs/agent-workflow.md`.

Fuer Codex/Hermes-Policy und Repo-spezifische Startkarten:

- `docs/codex-memory-policy.md`
- `docs/repo-agent-memory-template.md`

## Disposable Demo Lokal Ausfuehren

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
- `agent-hub migrate --status`: zeigt angewendete, offene oder fehlgeschlagene Schema-Migrationen
- `agent-hub migrate --apply`: wendet offene Schema-Migrationen an
- `agent-hub status`: zeigt eine schnelle Diagnose fuer Datenbank, Exportordner, Tabellenzaehlungen und Schema-Version
- `agent-hub check`: prueft einfache Konsistenzregeln fuer Export, Review und Migrationen
- `agent-hub projects`: listet aktive Projekte fuer agentische Arbeit
- `agent-hub projects --type website`: filtert aktive Projekte nach `projects.metadata.project_type`
- `agent-hub brief --project <slug>`: gibt einen kompakten Projektbrief fuer Agenten aus
- `agent-hub brief --project <slug> --with-relations`: ergaenzt den Projektbrief um kuratierte Relations
- `agent-hub daily --project <slug>`: zeigt neue Fakten, Entscheidungen, Risiken, Fragen, Relations, Agent Actions und Sync Events seit einem Zeitraum
- `agent-hub daily --project <slug> --write-report`: speichert die Tagesverdichtung als `reports`-Zeile mit `report_type='daily'`
- `agent-hub handoff --project <slug>`: erzeugt eine Uebergabe mit Entscheidungen, Risiken, offenen Punkten, Kontext und naechsten Schritten
- `agent-hub review --project <slug>`: zeigt Entscheidungs-/Risiko-/Fragenuebersicht plus Relations-Graph
- `agent-hub search --project <slug> --query <text>`: sucht projektgebunden in kuratierten Memory-Typen
- `agent-hub context --project <slug> --query <text>`: baut ein kompaktes Kontextpaket aus Recent Activity, Suchtreffern und Relations
- `agent-hub remember --project <slug> --type <type> --text <text>`: speichert eine gepruefte Erinnerung
- `agent-hub relations --project <slug>`: listet den belegbaren Projektgraphen
- `agent-hub relate --project <slug> ...`: verknuepft zwei existierende Hub-Objekte kuratiert
- `agent-hub import --path <file-or-directory>`: importiert allowlisted Obsidian-Markdown nach Postgres
- `agent-hub sync --path <file-or-directory> --plan|--apply`: plant oder wendet allowlisted Obsidian-Sync an
- `agent-hub init`: noch nicht implementiert

## Codex-/Hermes-Gedaechtnis

Die `projects`-, `brief`-, `daily`-, `handoff`-, `review`-, `search`-, `context`- und `remember`-Kommandos bilden den kontrollierten Zugriffspfad fuer Codex und Hermes: erst lesen und verdichten, dann nur kuratiert schreiben.

Vor groesseren Arbeiten:

```bash
agent-hub projects
scripts/project_context.sh --project <project-slug>
scripts/project_context.sh --project <project-slug> --daily
agent-hub context --project <project-slug> --query "<aktueller arbeitsfokus>"
```

Website ist das erste Domain-Profil im Hub. Diese Website-Projekte haben unterschiedliche Bearbeitungsstaende:

- `commcats-de`: aktuelle Live-Seite ist bereits eine statische Alfahosting-Website. Agenten sollen lokal in der statischen Quelle arbeiten und nur nach ausdruecklicher Freigabe hochladen.
- `the-one-catering`: aktuelle Live-Seite bleibt vorerst Framer. Agenten sollen die Live-Seite stabil halten, optisch unsichtbare SEO-/AI-Schritte vorbereiten und eine geschuetzte statische Staging-Version bauen, bevor ueber Migration gesprochen wird.

Projekt-Taxonomie bleibt in v1 bewusst leichtgewichtig ueber `projects.metadata.project_type`. Dokumentierte Werte sind `website`, `ops`, `research`, `product`, `business`, `personal` und `learning`. Eine eigene Spalte kommt erst in Frage, wenn Projekttypen query-kritisch werden.

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

Wichtig: Erinnerungen sind fuer kuratierte, nicht-sensitive Projektarbeit gedacht. Passwoerter, rohe Rechnungsdaten, private Kundendaten und ungepruefte Behauptungen gehoeren nicht in den Hub.

Relations machen daraus einen belegbaren Projektgraphen. Sie bleiben explizite, kuratierte CLI-Aktionen und werden nicht automatisch geraten:

```bash
agent-hub relate \
  --project commcats-de \
  --source-type fact \
  --source-id <fact-id> \
  --relation supports \
  --target-type decision \
  --target-id <decision-id>

agent-hub relations --project commcats-de
agent-hub brief --project commcats-de --with-relations
```

Erlaubte Relationstypen sind `supports`, `contradicts`, `supersedes`, `mitigates`, `answers`, `raises`, `references`, `derived_from`, `blocks` und `depends_on`. Typische Muster: Fact supports Decision, Decision mitigates Risk, Report references Fact, Decision answers Open Question.

Der sichere Wrapper kann eine neue Erinnerung auch direkt mit einem bestehenden Objekt verbinden:

```bash
scripts/project_remember.sh \
  --project commcats-de \
  --type fact \
  --text "Reviewed project memory goes here." \
  --source "review note" \
  --relate-to decision:<decision-id> \
  --relation supports
```

Fuer Tagesarbeit und Uebergaben:

```bash
agent-hub daily --project commcats-de --since 24h
agent-hub daily --project commcats-de --since 24h --write-report
agent-hub handoff --project the-one-catering --since 7d
agent-hub review --project commcats-de
agent-hub search --project commcats-de --query Alfahosting
agent-hub context --project the-one-catering --query migration
```

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

Geprueft werden unter anderem `DATABASE_URL`, die Datenbankverbindung, `OBSIDIAN_EXPORT_DIR`, der Exportordner, die Datensatzanzahl der Kern-Tabellen und der aktuelle Migrationsstand.

## Konsistenz Pruefen

`agent-hub check` fuehrt einfache Konsistenzpruefungen fuer Export und Review aus:

```bash
agent-hub check
```

Bewertung:

- niedrige Confidence bei Fakten ist eine Warning
- offene Fragen sind eine Warning
- offene Migrationen sind eine Warning
- kaputte polymorphe Relationen sind ein Error
- unbekannte Relationstypen sind eine Warning
- fehlgeschlagene oder veraenderte Migrationen sind ein Error
- eine nicht erreichbare Datenbank ist ein Error

## Tests Ausfuehren

Die schnellen lokalen Tests benoetigen keine Datenbank:

```bash
python3 -m compileall agent_hub
python -m pytest
agent-hub --help
agent-hub brief --help
agent-hub remember --help
agent-hub daily --help
agent-hub context --help
```

PostgreSQL-Checks bleiben optional. Sie koennen gegen jede disposable Testdatenbank laufen, die ueber `DATABASE_URL` erreichbar ist. Docker ist dafuer praktisch, aber keine Pflicht fuer normale Entwicklung.

## Sicherer Obsidian-Import

`agent-hub import` schreibt Markdown-Notizen aus Obsidian nach Postgres, aber nur ueber eine explizite Allowlist. Standardmaessig wird geschrieben; `--dry-run` zeigt die geplanten Imports ohne Datenbank-Writes.

```bash
cp import_allowlist.example.yml import_allowlist.yml
# import_allowlist.yml an lokale Vault-/Importpfade anpassen

agent-hub import --path /path/to/allowlisted-notes --dry-run
agent-hub import --path /path/to/allowlisted-notes
```

Die Allowlist definiert erlaubte Projekt-Slugs, Quellpfade, Frontmatter-Typen und Felder. Import blockiert potentielle Secrets, private Kundendaten, rohe Rechnungsdaten, Deployment-Credentials, unbekannte Projekt-Slugs, nicht erlaubte Pfade und nicht erlaubte Typen.

Importierbare Notizen sollten ein stabiles `import_key` im Frontmatter haben. Ohne `import_key` wird ein pfadbasierter Key aus Projekt, Typ und relativem Importpfad abgeleitet. Der Import speichert Herkunft, Import-Key und Content-Hash in `metadata.agent_hub_import`.

Duplikate werden standardmaessig uebersprungen:

```bash
agent-hub import --path /path/to/allowlisted-notes --on-duplicate skip
agent-hub import --path /path/to/allowlisted-notes --on-duplicate error
agent-hub import --path /path/to/allowlisted-notes --on-duplicate update
```

`agent-hub sync` baut darauf auf und trennt Planung von Anwendung:

```bash
agent-hub sync --path /path/to/allowlisted-notes --plan
agent-hub sync --path /path/to/allowlisted-notes --apply
```

Der Plan klassifiziert Notizen als `create`, `update`, `skip`, `conflict` oder `reject`. Bei `update` und `conflict` zeigt er Feld-Diffs mit Datenbankwert, Markdown-Wert, letztem Importwert und Feld-Owner. `--apply` schreibt nur, wenn der Plan keine Konflikte oder Rejections enthaelt. `sync --watch` ist bewusst noch nicht implementiert; automatische Hintergrundsynchronisation kommt erst nach stabiler Plan-/Apply-Nutzung.

Die V1-Regeln sind in `docs/import-allowlist.md` dokumentiert.

## PostgreSQL Smoke-Test

Der reproduzierbare Smoke-Test laeuft gegen eine vorhandene Wegwerf-Datenbank:

```bash
export DATABASE_URL="postgresql://postgres@localhost:55432/agent_hub_test"
scripts/smoke_postgres.sh
```

Das Skript spielt Migration und Seeds ein, prueft `status`, `check`, `brief`, `import`, `sync --plan`, `sync --apply`, einen absichtlichen Konfliktfall, `export` und Human-Notes-Erhaltung. Docker ist dafuer optional; wichtig ist nur eine disposable PostgreSQL-Datenbank.

## Projektstruktur

- `migrations/`: PostgreSQL-Migrationen
- `seed/`: reproduzierbare Demo-Daten
- `templates/`: Jinja2-Templates fuer Obsidian-Markdown
- `agent_hub/`: Python-Code fuer Datenbankzugriff, Markdown-Rendering, Exporter und CLI
- `scripts/`: lokale Smoke- und Wartungsskripte
- `docker-compose.yml`: dauerhafte lokale PostgreSQL-Betriebsdatenbank
- `.env.example`: Vorlage fuer lokale, nicht committete Konfiguration
- `docs/agent-workflow.md`: Arbeitsvertrag fuer Agenten vor und nach Projektarbeiten
- `tests/`: schnelle lokale Unit-Tests
- `ROADMAP.md`: priorisierte v0-Folgearbeiten
- `import_allowlist.example.yml`: Beispiel-Allowlist fuer sicheren Import

## Was v0/V1 Bewusst Noch Nicht Macht

- kein freier Zwei-Wege-Sync
- kein freier Obsidian-Rueckimport ohne Allowlist; V1 importiert und synchronisiert nur kuratierte Memory-Typen
- kein produktives Rechte-/Mandantenmodell
- keine Vektor-Suche
- keine automatische Hintergrundsynchronisation; `sync --watch` ist reserviert, aber noch nicht aktiv

## Naechste Sinnvolle Schritte

- Konfliktauflösung nach Review fuer `agent-hub sync`
- bessere Reports auf Basis des Projektgraphs, z. B. Tagesreport, Uebergabereport und Entscheidungs-/Risikoueberblick
- defensiver Watch-/Cron-Modus nach stabiler Plan-/Apply-Nutzung
- Template-/Frontmatter-Tests erweitern
