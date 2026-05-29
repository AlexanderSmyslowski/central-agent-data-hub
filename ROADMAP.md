# Central Agent Data Hub Roadmap

This roadmap keeps v0 focused on safe, reproducible project memory for Codex and Hermes.

## v0 Priorities

1. Automated tests
   - Keep fast unit tests for CLI helpers and non-database error paths.
   - Keep `scripts/smoke_postgres.sh` runnable against a disposable `DATABASE_URL`.
   - Do not require Docker Desktop for normal development.

2. Durable local database operations
   - Use Docker Compose for the local operational Postgres database.
   - Keep backups as local and optional remote dump files, not a live server sync.
   - Verify backups regularly before agents depend on writeback.

3. Status and check improvements
   - Keep `agent-hub status` fast and human-readable.
   - Extend `agent-hub check` only with checks that produce clear actions.
   - Treat broken relations and unreachable databases as errors.

4. Safe import allowlist
   - Keep `agent-hub import` limited to allowlisted projects, paths, types, and fields.
   - Reject secrets, private customer data, raw invoice data, and deployment credentials.
   - Keep import identity based on `import_key`, optional `db_id`, and metadata hashes.

5. Sync plan/apply
   - Keep `agent-hub sync --plan` as the default review path.
   - Keep field-level diffs visible for updates and conflicts.
   - Use `agent-hub sync --apply` only when the plan has no conflicts or rejected notes.
   - Keep `sync --watch` disabled until recovery and conflict handling are boring.

6. Obsidian projection hardening
   - Keep Human Notes stable across repeated exports.
   - Add tests for template rendering and frontmatter once template shape changes again.

## Website Memory Boundaries

- `commcats-de` is a static live Alfahosting site.
- `the-one-catering` remains live on Framer while SEO/AI work and protected static migration prep happen.
- These two projects must not be treated as the same operational state.

## Later, Not v0

- Free two-way sync.
- Background sync workers or watch mode.
- Vector search.
- Production auth, tenancy, or permissions.
