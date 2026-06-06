# Schema Notes

This note describes the durable PostgreSQL model used by Agent Data Hub.

The schema is intentionally compact. It is meant to support reviewed project
memory and auditability without turning the Hub into a transcript store.

## Core Tables

- `projects`: project anchors with slug, status, description, and metadata
- `agents`: known agents or profiles, optionally tied to a project
- `documents`: imported or projected Markdown-like documents
- `facts`: reviewed statements with source and confidence
- `decisions`: chosen directions with rationale and consequences
- `open_questions`: unresolved or answered clarification needs
- `risks`: active or resolved risks with severity, impact, and mitigation
- `reports`: daily summaries, handoffs, audits, or review notes
- `relations`: typed links between core objects
- `agent_actions`: audit trail for agent writes and updates
- `sync_events`: import/export/sync trail
- `schema_migrations`: migration tracking with checksum and status

## Migration Model

Migrations are applied in file order from `migrations/`.

- `001_init.sql`: baseline schema
- `002_schema_migrations.sql`: migration tracking table
- `003_relation_agent_actions.sql`: allows relations to reference agent actions

`agent-hub migrate --status` shows open, failed, or changed migrations.
`agent-hub migrate --apply` applies the pending set.

If an older database already has the base schema, the migration runner can mark
the baseline as applied and add tracking without rebuilding the database.

## Project Taxonomy

Project type is stored in `projects.metadata.project_type` rather than in a
dedicated column. That keeps the schema stable while allowing the project set
to evolve.

Documented values currently include:

- `website`
- `ops`
- `research`
- `product`
- `business`
- `personal`
- `learning`

`agent-hub projects --type <project_type>` filters active projects by that
metadata value.

## Relation Model

`relations` is intentionally polymorphic.

Allowed object types are:

- `project`
- `agent`
- `document`
- `fact`
- `decision`
- `open_question`
- `risk`
- `report`
- `agent_action`

The unique tuple
`source_type, source_id, relation_type, target_type, target_id`
prevents duplicate links while keeping the graph flexible.

Supported relation labels currently include:

- `supports`
- `contradicts`
- `supersedes`
- `mitigates`
- `answers`
- `raises`
- `references`
- `derived_from`
- `blocks`
- `depends_on`

`agent-hub relate` validates object types, relation labels, object existence,
and project compatibility before writing a relation.

## Audit Model

Auditability is handled through a small number of tables:

- `agent_actions` records write-oriented agent actions with input, output, and status
- `sync_events` records import/export/sync runs
- `schema_migrations` records migration state and checksum history

This keeps the system reviewable without storing raw chat transcripts.

## Projection Model

Markdown and Obsidian projection are layered on top of the database rather than
treated as the source of truth.

`documents` and `relations` support that projection by storing:

- paths
- frontmatter as JSON
- current content
- content hashes for sync checks
- graph-style links between structured objects

The projection layer is deliberately secondary. PostgreSQL remains the reviewed
operational source of truth.
