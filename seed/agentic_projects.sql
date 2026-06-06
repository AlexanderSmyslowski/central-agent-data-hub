-- Agentic project memory seed data for Codex/Hermes shared context.
-- Re-runnable after migrations/001_init.sql.
-- Intentionally excludes passwords, raw invoice data, private customer data, and deployment secrets.

BEGIN;

INSERT INTO projects (id, name, slug, description, status, metadata)
VALUES
(
  '20000000-0000-4000-8000-000000000001',
  'Catering Agents Platform',
  'catering-agents-platform',
  'Agentic production, intake, offer, print export, and backoffice platform work for catering operations.',
  'active',
  '{
    "repo": "AlexanderSmyslowski/catering-agents-platform",
    "local_path": "/Users/alexandersmyslowski/Projects/catering-agents-platform",
    "codex_workspace_root": "/Users/alexandersmyslowski/Library/Mobile Documents/com~apple~CloudDocs/Dateien/THE ONE von Alexander/Codex",
    "memory_scope": "product-platform",
    "project_type": "product",
    "work_mode": "repo-memory-plus-central-hub-start-finish",
    "domain_profile": "catering-operations"
  }'::jsonb
),
(
  '20000000-0000-4000-8000-000000000002',
  'Central Agent Data Hub',
  'central-agent-data-hub',
  'Durable local Postgres-backed shared agentic work memory, export, import, backup, and operational governance.',
  'active',
  '{
    "repo": "AlexanderSmyslowski/central-agent-data-hub",
    "local_path": "/Users/alexandersmyslowski/Projects/central-agent-data-hub",
    "codex_workspace_root": "/Users/alexandersmyslowski/Documents/Agenten Gedächtnis Datenbank Progres SQL",
    "memory_scope": "agentic-operations",
    "project_type": "ops",
    "work_mode": "durable-local-db-plus-curated-agent-writeback",
    "domain_profile": "agent-memory-infrastructure"
  }'::jsonb
),
(
  '20000000-0000-4000-8000-000000000003',
  'Zeiterfassung Tool',
  'zeiterfassung-tool',
  'Single-tenant time tracking app for catering, event, hospitality, and shift-based operations.',
  'active',
  '{
    "repo": "AlexanderSmyslowski/zeiterfassung-tool",
    "local_path": "/Users/alexandersmyslowski/Projects/zeiterfassung-tool",
    "codex_workspace_root": "/Users/hans_clawbot/Documents",
    "memory_scope": "product-platform",
    "project_type": "product",
    "work_mode": "central-hub-start-finish",
    "domain_profile": "time-tracking"
  }'::jsonb
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  status = EXCLUDED.status,
  metadata = projects.metadata || EXCLUDED.metadata;

INSERT INTO agents (id, project_id, name, slug, role, status, metadata)
VALUES
(
  '20000000-0000-4000-8000-000000000011',
  '20000000-0000-4000-8000-000000000001',
  'Codex',
  'codex',
  'Coding and implementation agent for the catering agents platform.',
  'active',
  '{"interface": "codex", "seed": "agentic_projects.sql"}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000012',
  '20000000-0000-4000-8000-000000000002',
  'Codex',
  'codex',
  'Coding and operations agent for the Central Agent Data Hub.',
  'active',
  '{"interface": "codex", "seed": "agentic_projects.sql"}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000013',
  (SELECT id FROM projects WHERE slug = 'zeiterfassung-tool'),
  'Codex',
  'codex',
  'Coding and implementation agent for the Zeiterfassung Tool.',
  'active',
  '{"interface": "codex", "seed": "agentic_projects.sql"}'::jsonb
)
ON CONFLICT (project_id, slug) DO UPDATE SET
  name = EXCLUDED.name,
  role = EXCLUDED.role,
  status = EXCLUDED.status,
  metadata = agents.metadata || EXCLUDED.metadata;

INSERT INTO facts (id, project_id, statement, source, confidence, status, metadata)
VALUES
(
  '20000000-0000-4000-8000-000000000201',
  '20000000-0000-4000-8000-000000000001',
  'The catering agents platform repo is located at /Users/alexandersmyslowski/Projects/catering-agents-platform; /Users/alexandersmyslowski/Projects/catering-agenten is a symlink to that repo.',
  '/Users/alexandersmyslowski/Projects/catering-agents-platform/AGENTS.md',
  0.950,
  'verified',
  '{"topic": "repo-location", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000202',
  '20000000-0000-4000-8000-000000000001',
  'The repo-local memory remains memory.md, with AGENTS.md, HANDOFF_PROMPT.md, and START_HERE.md as required onboarding files for new agent sessions.',
  '/Users/alexandersmyslowski/Projects/catering-agents-platform/START_HERE.md',
  0.950,
  'verified',
  '{"topic": "repo-memory", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000203',
  '20000000-0000-4000-8000-000000000001',
  'The current governance anchors are ApprovalRequestRecord as leading approval truth, SpecGovernanceStateRecord as status trail, and SpecChangeSetRecord as change unit.',
  '/Users/alexandersmyslowski/Projects/catering-agents-platform/AGENTS.md',
  0.900,
  'verified',
  '{"topic": "governance", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000204',
  '20000000-0000-4000-8000-000000000002',
  'The Central Agent Data Hub is the shared agentic work memory for Codex/Hermes: agents should run preflight, load project context, work project-bound, and write back only curated non-sensitive memory.',
  '/Users/alexandersmyslowski/Projects/central-agent-data-hub/docs/agent-workflow.md',
  0.950,
  'verified',
  '{"topic": "agent-workflow", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000205',
  '20000000-0000-4000-8000-000000000002',
  'The durable Hub database runs locally in Docker/Postgres with a persistent named volume and is backed up using scripts/db_backup.sh and scripts/db_verify_backup.sh.',
  '/Users/alexandersmyslowski/Projects/central-agent-data-hub/README.md',
  0.950,
  'verified',
  '{"topic": "durable-db", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000206',
  (SELECT id FROM projects WHERE slug = 'zeiterfassung-tool'),
  'The Zeiterfassung Tool repo is located at /Users/alexandersmyslowski/Projects/zeiterfassung-tool and is backed by GitHub repo AlexanderSmyslowski/zeiterfassung-tool.',
  '/Users/alexandersmyslowski/Projects/zeiterfassung-tool/PROJECT_STATUS.md',
  0.950,
  'verified',
  '{"topic": "repo-location", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000207',
  (SELECT id FROM projects WHERE slug = 'zeiterfassung-tool'),
  'The Zeiterfassung Tool is currently in internal stabilization and pilot/operational readiness for a single-tenant time tracking app per instance.',
  '/Users/alexandersmyslowski/Projects/zeiterfassung-tool/PROJECT_STATUS.md',
  0.900,
  'verified',
  '{"topic": "project-state", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  statement = EXCLUDED.statement,
  source = EXCLUDED.source,
  confidence = EXCLUDED.confidence,
  status = EXCLUDED.status,
  metadata = facts.metadata || EXCLUDED.metadata,
  updated_at = now();

INSERT INTO decisions (id, project_id, decision, rationale, consequences, status, metadata)
VALUES
(
  '20000000-0000-4000-8000-000000000301',
  '20000000-0000-4000-8000-000000000001',
  'Use the Central Agent Data Hub as the start and finish layer for future catering agents platform work, while keeping memory.md as the detailed repo-local reference.',
  'The Hub gives Codex/Hermes a shared operational memory across channels, while the existing repo-local memory already contains detailed project history.',
  'Agents should begin with scripts/agent_start.sh --project catering-agents-platform and finish with scripts/agent_finish.sh --project catering-agents-platform before curated writeback.',
  'accepted',
  '{"topic": "agent-workflow", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000302',
  '20000000-0000-4000-8000-000000000001',
  'Do not introduce new persistence systems, Prisma, or expanded governance workflows in the catering agents platform without an explicit decision.',
  'The existing AGENTS.md marks these as out of scope and keeps the current phase focused on consolidation.',
  'Future agents must treat persistence or governance expansion as blocked until explicitly requested.',
  'accepted',
  '{"topic": "scope-control", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000303',
  '20000000-0000-4000-8000-000000000002',
  'Treat the Central Agent Data Hub as operational memory infrastructure, not as a raw chatlog or storage place for sensitive operational material.',
  'The Hub is useful only if memories stay project-bound, reviewed, traceable, and safe for shared agent use.',
  'Agents should prefer fewer high-quality facts, decisions, risks, open questions, and reports over broad transcript capture.',
  'accepted',
  '{"topic": "memory-quality", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000304',
  (SELECT id FROM projects WHERE slug = 'zeiterfassung-tool'),
  'Keep Zeiterfassung Tool work focused on pilot hardening and operational readiness unless the user explicitly approves platform, multi-tenancy, or white-label expansion.',
  'AGENTS.md and PROJECT_STATUS.md define the current phase as pilot hardening of the existing single-tenant product.',
  'Future agents must treat platform expansion, multi-tenancy, and broad architecture changes as out of scope unless explicitly requested.',
  'accepted',
  '{"topic": "scope-control", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  decision = EXCLUDED.decision,
  rationale = EXCLUDED.rationale,
  consequences = EXCLUDED.consequences,
  status = EXCLUDED.status,
  metadata = decisions.metadata || EXCLUDED.metadata,
  updated_at = now();

INSERT INTO risks (id, project_id, title, severity, impact, mitigation, status, metadata)
VALUES
(
  '20000000-0000-4000-8000-000000000501',
  '20000000-0000-4000-8000-000000000001',
  'Repo-local memory and Central Hub memory can diverge if agents update only one layer.',
  'medium',
  'Future agents may start from incomplete context or repeat outdated assumptions.',
  'Keep AGENTS.md pointing to agent_start/agent_finish, preserve memory.md as local detail memory, and write only curated cross-session facts back into the Hub.',
  'open',
  '{"topic": "memory-drift", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000502',
  '20000000-0000-4000-8000-000000000002',
  'Agent work can become less reliable if preflight, backups, or project context are skipped.',
  'medium',
  'Codex/Hermes may act on stale assumptions or lose important operational continuity.',
  'Use scripts/agent_preflight.sh, scripts/agent_start.sh, scripts/agent_finish.sh, daily backup, and verified restores as the normal operating path.',
  'open',
  '{"topic": "operational-readiness", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000503',
  (SELECT id FROM projects WHERE slug = 'zeiterfassung-tool'),
  'Zeiterfassung Tool agents can confuse future platform documents with the current pilot-ready single-tenant product scope.',
  'medium',
  'Agents may overbuild multi-tenancy, white-label, or platform features before the current pilot hardening path is intentionally changed.',
  'Start from AGENTS.md, PROJECT_STATUS.md, and Hub context; classify future-path documents separately from current implementation state.',
  'open',
  '{"topic": "scope-drift", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  severity = EXCLUDED.severity,
  impact = EXCLUDED.impact,
  mitigation = EXCLUDED.mitigation,
  status = EXCLUDED.status,
  metadata = risks.metadata || EXCLUDED.metadata,
  updated_at = now();

INSERT INTO reports (id, project_id, title, report_type, summary, body, status, metadata)
VALUES
(
  '20000000-0000-4000-8000-000000000601',
  '20000000-0000-4000-8000-000000000001',
  'Catering Agents Platform Hub Onboarding',
  'handoff',
  'The catering agents platform is now represented in the Central Agent Data Hub with a dedicated project slug and start/finish workflow.',
  'Project slug: catering-agents-platform. The existing repo-local memory stack remains memory.md, AGENTS.md, HANDOFF_PROMPT.md, START_HERE.md, and docs/agent-memory/. The Hub is the cross-channel start/finish and curated writeback layer. The first integration keeps existing scope controls: no new persistence system, no Prisma, no expanded governance workflow, and no sensitive operational data in Hub memory.',
  'published',
  '{"topic": "hub-onboarding", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000602',
  '20000000-0000-4000-8000-000000000002',
  'Central Agent Data Hub Ops Memory Start',
  'handoff',
  'The Hub itself now has a dedicated ops project context for infrastructure, backup, memory workflow, and operational governance.',
  'Project slug: central-agent-data-hub. This context is for the Hub infrastructure itself: durable local Postgres, migrations, backup/restore, CLI workflows, agent preflight, curated writeback, Obsidian export/import, and operational readiness. Keep website, catering platform, and other domain-specific memory in their own project contexts.',
  'published',
  '{"topic": "ops-project-onboarding", "sensitive": false}'::jsonb
),
(
  '20000000-0000-4000-8000-000000000603',
  (SELECT id FROM projects WHERE slug = 'zeiterfassung-tool'),
  'Zeiterfassung Tool Hub Onboarding',
  'handoff',
  'The Zeiterfassung Tool is now represented in the Central Agent Data Hub with a dedicated project slug and start/finish workflow.',
  'Project slug: zeiterfassung-tool. The current leading repository is /Users/alexandersmyslowski/Projects/zeiterfassung-tool. The current work focus is pilot hardening and operational readiness for a single-tenant time tracking app; platform, multi-tenancy, white-label expansion, external customer rollout, and unreviewed compliance claims remain out of scope unless explicitly approved.',
  'published',
  '{"topic": "hub-onboarding", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  report_type = EXCLUDED.report_type,
  summary = EXCLUDED.summary,
  body = EXCLUDED.body,
  status = EXCLUDED.status,
  metadata = reports.metadata || EXCLUDED.metadata,
  updated_at = now();

COMMIT;
