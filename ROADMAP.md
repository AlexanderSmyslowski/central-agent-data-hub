# Central Agent Data Hub Roadmap

This roadmap keeps v0 focused on safe, reproducible project memory for Codex and Hermes.

## v0.2 Milestone Boundary

v0.2 should mean a reliable local reviewed-context loop for outside developers:
clone, run the neutral demo, register a local project, connect an agent, prepare
task-specific context, review drafts explicitly, and verify operational health.

The v0.2 definition lives in `docs/public/v0.2-definition.md`. It keeps the
claim narrow: reviewed context for humans and agents. It does not require hosted
SaaS, production auth, background sync workers, embeddings, write-capable MCP
tools, or a non-checkout package installation path.

## v0.3 Milestone Boundary

v0.3 should mean the multi-agent trust loop is executable and tested: an agent
can create draft candidates from a signal, a reviewer can accept or reject them
through the CLI or the public Review API, audit metadata records the review, and
the next agent can see the accepted result through `prepare`, `handoff`, and the
read-only MCP prepare payload.

The v0.3 definition lives in `docs/public/v0.3-definition.md`. CI should keep
`scripts/smoke_trust_loop.sh` green as a separate proof of that path.

## v0.4 Milestone Boundary

v0.4 should mean the local daily agent loop is operationally reliable: when the
Hub is ready, start/finish wrappers load and close reviewed context; when the
Hub is offline, they stop clearly, write no reviewed memory, and point to the
doctor/start/retry path.

The v0.4 definition lives in `docs/public/v0.4-definition.md`. CI should keep
`scripts/smoke_agent_offline.sh` green as a separate proof of the offline
behavior.

## v0.5 Milestone Boundary

v0.5 should mean a first external developer can move from the public demo into
one real local project loop: register a repo, install repo-local agent
instructions, start with reviewed context, review one draft explicitly, and
finish with a handoff.

The v0.5 definition lives in `docs/public/v0.5-definition.md`. CI should keep
`scripts/smoke_external_developer.sh` green as a separate proof of that path.

## v0.6 Milestone Boundary

v0.6 should mean the first real-project bootstrap is available through the
installed CLI, not only through repo-local shell scripts. A developer who has
installed the checkout with `pip install -e .` can run
`agent-hub register-project`, get the same project registration and repo-local
agent instructions, and then continue with the existing start/review/finish
loop.

The v0.6 definition lives in `docs/public/v0.6-definition.md`. CI should keep
the external-developer smoke on the CLI bootstrap path.

## v0.7 Milestone Boundary

v0.7 should mean a small public release candidate is evidence-led: fresh clone,
public demo, first external project, trust loop, offline behavior, upgrade
drill, status, and check are visible as separate proofs before tagging.

The v0.7 definition lives in `docs/public/v0.7-definition.md`. CI should keep
the behavioral smokes separate so release readiness is not reduced to unit
tests alone.

## v0.8 Milestone Boundary

v0.8 should mean local runtime health is visible before agent work or release
checks depend on it: disk space, temp directories, Docker, Compose, ports,
containers, volumes, backups, migrations, status, and check produce clear
diagnosis and one safe next step.

The v0.8 definition lives in `docs/public/v0.8-definition.md`. It remains a
diagnostic milestone, not an automatic recovery or hosted monitoring system.

## v1.0 Milestone Boundary

v1.0 should mean boringly reliable reviewed context infrastructure for local
agent work: a fresh checkout can run the demo, a real project can be registered,
agents can start from reviewed context, drafts are explicitly reviewed, context
packs expose trail and gaps, finish can export and verify backups, and offline
states stop clearly before false success claims.

The v1.0 definition lives in `docs/public/v1.0-definition.md`. It remains a
local-first infrastructure milestone, not a hosted product, auth system, or
automation platform.

## v0 Priorities

1. Operational readiness
   - Require a read-only agent preflight before regular Hub writeback.
   - Keep the durable local DB, latest verified backup, and project briefs healthy.
   - Treat missing local backup state as an operational blocker for writeback.

2. Agentic work workflow
   - Prefer `scripts/agent_start.sh` before substantial project work.
   - Prefer compact `agent-hub compile` output as the first agent context for single-project work.
   - Prefer `scripts/agent_finish.sh` after substantial project work.
   - Use `scripts/agent_start.sh --review` for longer or riskier work.
   - Use `scripts/agent_finish.sh --review --export --backup` when a session should end with human-readable projection and verified backup.
   - Use `scripts/memory_receipt.sh` when another agent/channel claims that reviewed memory was written and exported.
   - Use `scripts/project_context.sh` before project work.
   - Use `scripts/project_remember.sh` for reviewed, non-sensitive writeback.
   - Keep each project context explicit; websites are only the first domain profile.
   - Use `scripts/install_repo_agent_memory.sh` to install or update repo-local Hub instructions in important project repos.
   - Use `scripts/onboard_known_repos.sh` for dry-run/apply onboarding of active projects with explicit `metadata.local_path`.
   - Use `scripts/register_project.sh` as the first step for new project repos before substantial agent work.
   - Prefer `agent-hub register-project` for public/CLI-first project bootstrap; keep `scripts/register_project.sh` as the repo-local compatibility path.
   - Keep project skill manifests as repo-local orientation maps, not Hub memory payloads.
   - Use `agent-hub actions` to inspect recent audited agent activity before adding any heavier work-session model.
   - Keep thread/worktree self-management as a reviewed workflow layer, not automatic memory capture.

3. Schema evolution and project taxonomy
   - Track applied migrations in `schema_migrations`.
   - Use `agent-hub migrate --status` and `agent-hub migrate --apply` before schema-dependent work.
   - Keep `projects.metadata.project_type` as the lightweight taxonomy until a dedicated column is justified.
   - Block regular agent writeback when migrations are pending, failed, or checksum-changed.

4. Relations workflow and project graph
   - Use `agent-hub relate` for curated links between facts, decisions, risks, questions, reports, and audit actions.
   - Use `agent-hub relations` and `agent-hub brief --with-relations` for reviewable project graph context.
   - Use Obsidian `Linked Memory` sections and `Compiled/` project pages as the human-readable graph projection.
   - Keep relation types controlled in CLI/checks before hardening them into database constraints.

5. Daily workflow, handoff, review, and retrieval
   - Use `agent-hub daily` before/after work to make new memory visible.
   - Use `agent-hub handoff` for session transfer between agents or days.
   - Use `agent-hub review` for decision/risk/question review from the project graph.
   - Use `agent-hub search` and `agent-hub context` before large changes instead of relying on raw recall.
   - Use `agent-hub compile --since --with-receipt-status --max-chars` for token-efficient starts.
   - Use `agent-hub quality` to spot thin, stale, or weak project memory.
   - Keep vector search and watch-mode automation out until simple retrieval is boringly useful.

6. Automated tests
   - Keep fast unit tests for CLI helpers and non-database error paths.
   - Keep `scripts/smoke_postgres.sh` runnable against a disposable `DATABASE_URL`.
   - Do not require Docker Desktop for normal development.

7. Durable local database operations
   - Use Docker Compose for the local operational Postgres database.
   - Keep backups as local and optional remote dump files, not a live server sync.
   - Verify backups regularly before agents depend on writeback.

8. Status and check improvements
   - Keep `agent-hub status` fast and human-readable.
   - Extend `agent-hub check` only with checks that produce clear actions.
   - Treat broken relations and unreachable databases as errors.

9. Safe import allowlist
   - Keep `agent-hub import` limited to allowlisted projects, paths, types, and fields.
   - Reject secrets, private customer data, raw invoice data, and deployment credentials.
   - Keep import identity based on `import_key`, optional `db_id`, and metadata hashes.

10. Sync plan/apply
   - Keep `agent-hub sync --plan` as the default review path.
   - Keep field-level diffs visible for updates and conflicts.
   - Use `agent-hub sync --apply` only when the plan has no conflicts or rejected notes.
   - Keep `sync --watch` disabled until recovery and conflict handling are boring.

11. Obsidian projection hardening
   - Keep Human Notes stable across repeated exports.
   - Keep `Compiled/Agent Data Hub.md` as the human-readable Hub start page.
   - Keep export filenames stable and build Wikilinks from the export index, never from guessed paths.
   - Add tests for template rendering and frontmatter once template shape changes again.

12. Public explanation pack
   - Keep anonymized public-facing docs under `docs/public/`.
   - Avoid real project names, private paths, customer data, and deployment details.
   - Use Agent Data Hub as the project name and "reviewed context for humans and agents" as the claim.

13. Product elegance
   - Prefer fewer, sharper workflow entrypoints over many equal-seeming commands.
   - Evolve Hub View as the local human-facing app for reviewed memory; keep
     the scoped app roadmap in `docs/hub-view-app-roadmap.md`.
   - Add features only when they reduce daily confusion, improve reviewability, or protect memory quality.
   - Keep long technical rule text in repos or skill packs, not in the Hub core.
   - Split new CLI logic into focused modules before `agent_hub/cli.py` grows further.

## Domain Profile: Websites

- `commcats-de` is a static live Alfahosting site.
- `the-one-catering` remains live on Framer while SEO/AI work and protected static migration prep happen.
- These two projects must not be treated as the same operational state.

## Later, Not v0

- Free two-way sync.
- Background sync workers or watch mode.
- Vector search.
- Production auth, tenancy, or permissions.
