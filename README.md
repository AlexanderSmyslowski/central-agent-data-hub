# Central Agent Data Hub

Central Agent Data Hub ist ein neues v0-Projekt für eine zentrale, agentenlesbare Daten- und Wissensbasis rund um Projekte, Agenten, Dokumente, Fakten, Entscheidungen, offene Fragen, Risiken, Berichte und Audit-/Sync-Ereignisse.

## v0-Scope

Phase 1 legt nur die Basisstruktur an:

- PostgreSQL-v0-Migration unter `migrations/001_init.sql`
- Kernentitäten: Projekte, Agenten, Dokumente, Fakten, Entscheidungen, offene Fragen, Risiken und Reports
- polymorphes Relation-Modell
- Audit-/Event-Tabellen für Agentenaktionen, Events und Synchronisationen
- kurze Schema-Notizen unter `docs/schema-notes.md`

Nicht Teil von v0:

- Anwendungscode
- API
- UI
- Seed-Daten
- Trigram-/Volltextsuche
- produktive Sync-Worker

## Migration testen

Mit lokal laufendem PostgreSQL kann die Migration gegen eine leere Testdatenbank geprüft werden:

```bash
createdb central_agent_data_hub_test
psql -v ON_ERROR_STOP=1 -d central_agent_data_hub_test -f migrations/001_init.sql
```

Optional danach wieder löschen:

```bash
dropdb central_agent_data_hub_test
```
