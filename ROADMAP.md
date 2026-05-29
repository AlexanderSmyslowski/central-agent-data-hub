# Central Agent Data Hub Roadmap

This roadmap keeps v0 focused on safe, reproducible project memory for Codex and Hermes.

## v0 Priorities

1. Operational readiness
   - Require a read-only agent preflight before regular Hub writeback.
   - Keep the durable local DB, latest verified backup, and project briefs healthy.
   - Treat missing local backup state as an operational blocker for writeback.

2. Agentic work workflow
   - Use `scripts/project_context.sh` before project work.
   - Use `scripts/project_remember.sh` for reviewed, non-sensitive writeback.
   - Keep each project context explicit; websites are only the first domain profile.

3. Schema evolution and project taxonomy
   - Track applied migrations in `schema_migrations`.
   - Use `agent-hub migrate --status` and `agent-hub migrate --apply` before schema-dependent work.
   - Keep `projects.metadata.project_type` as the lightweight taxonomy until a dedicated column is justified.
   - Block regular agent writeback when migrations are pending, failed, or checksum-changed.

4. Relations workflow and project graph
   - Use `agent-hub relate` for curated links between facts, decisions, risks, questions, reports, and audit actions.
   - Use `agent-hub relations` and `agent-hub brief --with-relations` for reviewable project graph context.
   - Keep relation types controlled in CLI/checks before hardening them into database constraints.

5. Automated tests
   - Keep fast unit tests for CLI helpers and non-database error paths.
   - Keep `scripts/smoke_postgres.sh` runnable against a disposable `DATABASE_URL`.
   - Do not require Docker Desktop for normal development.

6. Durable local database operations
   - Use Docker Compose for the local operational Postgres database.
   - Keep backups as local and optional remote dump files, not a live server sync.
   - Verify backups regularly before agents depend on writeback.

7. Status and check improvements
   - Keep `agent-hub status` fast and human-readable.
   - Extend `agent-hub check` only with checks that produce clear actions.
   - Treat broken relations and unreachable databases as errors.

8. Safe import allowlist
   - Keep `agent-hub import` limited to allowlisted projects, paths, types, and fields.
   - Reject secrets, private customer data, raw invoice data, and deployment credentials.
   - Keep import identity based on `import_key`, optional `db_id`, and metadata hashes.

9. Sync plan/apply
   - Keep `agent-hub sync --plan` as the default review path.
   - Keep field-level diffs visible for updates and conflicts.
   - Use `agent-hub sync --apply` only when the plan has no conflicts or rejected notes.
   - Keep `sync --watch` disabled until recovery and conflict handling are boring.

10. Obsidian projection hardening
   - Keep Human Notes stable across repeated exports.
   - Add tests for template rendering and frontmatter once template shape changes again.

## Domain Profile: Websites

- `commcats-de` is a static live Alfahosting site.
- `the-one-catering` remains live on Framer while SEO/AI work and protected static migration prep happen.
- These two projects must not be treated as the same operational state.

## Later, Not v0

- Free two-way sync.
- Background sync workers or watch mode.
- Vector search.
- Production auth, tenancy, or permissions.
