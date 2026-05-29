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
    "memory_scope": "product-platform",
    "project_type": "product",
    "work_mode": "repo-memory-plus-central-hub-start-finish",
    "domain_profile": "catering-operations"
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
