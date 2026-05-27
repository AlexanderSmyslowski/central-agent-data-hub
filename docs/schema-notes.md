# Schema Notes

## Tabellenübersicht

- `projects`: zentrale Projektanker mit Slug, Status und Metadaten.
- `agents`: bekannte Agenten oder Profile, optional projektbezogen.
- `documents`: Knowledge-Base- oder Obsidian-nahe Dokumente mit Pfad, Inhalt, Frontmatter und Content-Hash.
- `facts`: verdichtete Aussagen mit Quelle, Confidence und Prüfstatus.
- `decisions`: getroffene oder vorgeschlagene Entscheidungen mit Begründung und Folgen.
- `open_questions`: offene oder beantwortete Fragen mit optionaler Antwort und `resolved_at`.
- `risks`: Risiken mit Severity, Impact, Mitigation und Status.
- `reports`: kuratierte Lageberichte, Statusberichte oder Entscheidungsnotizen.
- `relations`: typisierte Verknüpfungen zwischen Kernobjekten.
- `agent_actions`: Auditspur für Agentenhandlungen.
- `event_log`: generische Ereignisspur.
- `sync_events`: Import-/Export-/Synchronisationsereignisse.

## Relation-Modell

`relations` ist bewusst polymorph gehalten. Erlaubte Objekttypen sind:

- `project`
- `agent`
- `document`
- `fact`
- `decision`
- `open_question`
- `risk`
- `report`

Die Kombination aus `source_type`, `source_id`, `relation_type`, `target_type`, `target_id` ist eindeutig. Dadurch können z. B. Dokumente Fakten belegen, Entscheidungen Risiken entschärfen oder Reports offene Fragen zusammenfassen, ohne für jede Beziehung eine eigene Join-Tabelle anzulegen.

## Audit-Modell

- `agent_actions` beschreibt konkrete Handlungen eines Agenten mit Input, Output, Status und Fehlertext.
- `event_log` beschreibt fachliche oder technische Ereignisse mit Payload und Status.
- `sync_events` beschreibt Synchronisationsläufe aus Quellen wie Obsidian, Git, Hermes-Reports oder späteren Importern.

Alle drei Tabellen haben `created_at`, `updated_at`, JSONB-Metadaten und Indizes für typische Auswertungen nach Agent, Objekt, Status und Zeit.

## Obsidian-/Knowledge-Base-Projektion

Die Tabelle `documents` ist der primäre Anker für eine spätere Obsidian- oder Markdown-Projektion:

- `path` bildet den relativen oder absoluten Dokumentpfad ab.
- `frontmatter` speichert YAML-/Markdown-Metadaten als JSONB.
- `content` speichert den aktuellen Markdown-Text.
- `content_hash` erlaubt Sync- und Änderungsprüfung.
- `relations` kann Links, Quellenbezüge, Ableitungen und Entscheidungszusammenhänge strukturiert ergänzen.

In v0 wird kein `pg_trgm` aktiviert. Suchfunktionen bleiben bewusst außerhalb dieser Basismigration, bis ein konkreter Suchpfad entschieden ist.
