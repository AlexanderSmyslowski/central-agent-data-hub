# Central Agent Data Hub Roadmap

This roadmap keeps v0 focused on safe, reproducible project memory for Codex and Hermes.

## v0 Priorities

1. Automated tests
   - Keep fast unit tests for CLI helpers and non-database error paths.
   - Keep optional PostgreSQL smoke checks runnable against a disposable `DATABASE_URL`.
   - Do not require Docker Desktop for normal development.

2. Status and check improvements
   - Keep `agent-hub status` fast and human-readable.
   - Extend `agent-hub check` only with checks that produce clear actions.
   - Treat broken relations and unreachable databases as errors.

3. Safe import allowlist
   - Define allowed projects, source paths, and note types before implementing import.
   - Reject secrets, private customer data, raw invoice data, and deployment credentials.
   - Keep `agent-hub import` as a placeholder until the allowlist is tested.

4. Obsidian projection hardening
   - Keep Human Notes stable across repeated exports.
   - Add tests for template rendering and frontmatter once template shape changes again.

## Website Memory Boundaries

- `commcats-de` is a static live Alfahosting site.
- `the-one-catering` remains live on Framer while SEO/AI work and protected static migration prep happen.
- These two projects must not be treated as the same operational state.

## Later, Not v0

- Free two-way sync.
- Background sync workers.
- Vector search.
- Production auth, tenancy, or permissions.
