-- Business-site memory seed data for Codex/Hermes shared context.
-- Re-runnable after migrations/001_init.sql.
-- Intentionally excludes passwords, raw invoice data, and private customer data.

BEGIN;

INSERT INTO projects (id, name, slug, description, status, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000001',
  'CommCats',
  'commcats-de',
  'Website, SEO, hosting, and positioning work for commcats.de.',
  'active',
  '{
    "domain": "commcats.de",
    "memory_scope": "website",
    "site_state": "live-static-alfahosting",
    "work_mode": "edit-local-static-source-then-upload-after-approval",
    "hosting_state": "already-migrated-away-from-framer-for-current-live-site"
  }'::jsonb
),
(
  '10000000-0000-4000-8000-000000000002',
  'THE ONE',
  'the-one-catering',
  'Website, SEO, AI visibility, and future migration work for the-one.catering.',
  'active',
  '{
    "domain": "the-one.catering",
    "memory_scope": "website",
    "site_state": "live-framer-site-with-static-migration-planned",
    "work_mode": "keep-live-framer-site-stable-build-protected-static-prototype",
    "hosting_state": "not-yet-migrated"
  }'::jsonb
),
(
  '10000000-0000-4000-8000-000000000003',
  'L''Amour',
  'lamour',
  'Planned future web presence; strategic work not yet started in depth.',
  'active',
  '{"memory_scope": "planned-website"}'::jsonb
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  status = EXCLUDED.status,
  metadata = projects.metadata || EXCLUDED.metadata;

INSERT INTO agents (id, project_id, name, slug, role, status, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000011',
  '10000000-0000-4000-8000-000000000001',
  'Codex',
  'codex',
  'Coding and implementation agent for website work.',
  'active',
  '{"interface": "codex", "seed": "business_sites.sql"}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000012',
  '10000000-0000-4000-8000-000000000002',
  'Codex',
  'codex',
  'Coding and implementation agent for website work.',
  'active',
  '{"interface": "codex", "seed": "business_sites.sql"}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000013',
  '10000000-0000-4000-8000-000000000003',
  'Codex',
  'codex',
  'Coding and implementation agent for future website work.',
  'active',
  '{"interface": "codex", "seed": "business_sites.sql"}'::jsonb
)
ON CONFLICT (project_id, slug) DO UPDATE SET
  name = EXCLUDED.name,
  role = EXCLUDED.role,
  status = EXCLUDED.status,
  metadata = agents.metadata || EXCLUDED.metadata;

INSERT INTO facts (id, project_id, statement, source, confidence, status, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000201',
  '10000000-0000-4000-8000-000000000001',
  'commcats.de is running as a static Alfahosting site with live HTTPS redirects and no Framer dependency for the current static deployment.',
  '/Users/alexandersmyslowski/Documents/commcats.de/DEPLOYMENT-LOG.md',
  0.950,
  'verified',
  '{"topic": "hosting", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000202',
  '10000000-0000-4000-8000-000000000001',
  'CommCats is currently positioned as "Agentur fuer Wissenschaftsevents".',
  '/Users/alexandersmyslowski/Documents/commcats.de/commcats-static-v1/index.html',
  0.950,
  'verified',
  '{"topic": "positioning", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000203',
  '10000000-0000-4000-8000-000000000002',
  'the-one.catering remains live on Framer while SEO metadata, JSON-LD, H1 cleanup, Search Console verification, and sitemap submission have been completed.',
  '/Users/alexandersmyslowski/Documents/commcats.de/THE-ONE-SEO-AUDIT.md',
  0.950,
  'verified',
  '{"topic": "seo", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000206',
  '10000000-0000-4000-8000-000000000001',
  'commcats.de and the-one.catering must not be treated as the same operational state: CommCats is already a live static Alfahosting site, while THE ONE remains a live Framer site with only migration preparation planned.',
  'conversation instruction 2026-05-28',
  0.950,
  'verified',
  '{"topic": "project-state", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000207',
  '10000000-0000-4000-8000-000000000002',
  'the-one.catering is not at the same implementation stage as commcats.de: THE ONE should keep the current Framer live site stable until a protected static prototype is complete, tested, and explicitly approved for migration.',
  'conversation instruction 2026-05-28',
  0.950,
  'verified',
  '{"topic": "project-state", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000204',
  '10000000-0000-4000-8000-000000000002',
  'A THE ONE SEO/AI and Alfahosting migration plan exists and recommends a static prototype before any live migration.',
  '/Users/alexandersmyslowski/Documents/commcats.de/THE-ONE-MIGRATION-SEO-PLAN.md',
  0.950,
  'verified',
  '{"topic": "migration", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000205',
  '10000000-0000-4000-8000-000000000003',
  'L''Amour is still in planning and should not inherit CommCats or THE ONE positioning without a separate brand decision.',
  'conversation summary 2026-05-28',
  0.750,
  'proposed',
  '{"topic": "planning", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  statement = EXCLUDED.statement,
  source = EXCLUDED.source,
  confidence = EXCLUDED.confidence,
  status = EXCLUDED.status,
  metadata = facts.metadata || EXCLUDED.metadata;

INSERT INTO decisions (id, project_id, decision, rationale, consequences, status, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000301',
  '10000000-0000-4000-8000-000000000001',
  'Keep commcats.de on the static Alfahosting path and continue improving the local static source before further live uploads.',
  'The static build gives lower cost, direct file control, and better control over robots, sitemap, llms.txt, redirects, and assets.',
  'Codex should work in the static source tree and upload only after explicit approval.',
  'accepted',
  '{"topic": "hosting", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000302',
  '10000000-0000-4000-8000-000000000002',
  'For THE ONE, start with optically invisible SEO and AI-readability improvements, then build a static Alfahosting prototype before migration.',
  'The visible Framer site is currently in use; a non-live prototype avoids business risk while preparing cost reduction.',
  'No DNS switch, Framer cancellation, or live migration before prototype review, redirect planning, HTTPS checks, and explicit approval.',
  'accepted',
  '{"topic": "migration", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000303',
  '10000000-0000-4000-8000-000000000002',
  'Use a protected Alfahosting staging subdomain for THE ONE once the first static prototype exists.',
  'The main domain currently points to Framer; a staging subdomain can point to Alfahosting without touching live traffic.',
  'Staging must be password-protected, noindex, and excluded from public live navigation.',
  'accepted',
  '{"topic": "staging", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  decision = EXCLUDED.decision,
  rationale = EXCLUDED.rationale,
  consequences = EXCLUDED.consequences,
  status = EXCLUDED.status,
  metadata = decisions.metadata || EXCLUDED.metadata;

INSERT INTO open_questions (id, project_id, question, answer, status, resolved_at, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000401',
  '10000000-0000-4000-8000-000000000002',
  'Which exact staging subdomain should be used for the future THE ONE static prototype?',
  NULL,
  'open',
  NULL,
  '{"topic": "staging", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000402',
  '10000000-0000-4000-8000-000000000002',
  'Which official THE ONE address should be used for schema.org, legal pages, and contact metadata?',
  NULL,
  'open',
  NULL,
  '{"topic": "legal", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  question = EXCLUDED.question,
  answer = EXCLUDED.answer,
  status = EXCLUDED.status,
  resolved_at = EXCLUDED.resolved_at,
  metadata = open_questions.metadata || EXCLUDED.metadata;

INSERT INTO risks (id, project_id, title, severity, impact, mitigation, status, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000501',
  '10000000-0000-4000-8000-000000000002',
  'THE ONE staging prototype could be indexed accidentally',
  'high',
  'Google or AI crawlers could surface unfinished staging pages if protection is incomplete.',
  'Use password protection, noindex headers or meta robots, blocking staging robots.txt, and no links from live pages.',
  'open',
  '{"topic": "staging", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000502',
  '10000000-0000-4000-8000-000000000002',
  'Framer-to-static migration could lose URLs or rankings if redirects are incomplete',
  'high',
  'Existing indexed Framer URLs may return 404 or lose relevance after migration.',
  'Capture the current Framer sitemap, map all important URLs to static equivalents, test 301 redirects, then submit the new sitemap.',
  'open',
  '{"topic": "seo", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000503',
  '10000000-0000-4000-8000-000000000001',
  'Shared memory must not store deployment secrets or private invoice details',
  'critical',
  'Sensitive credentials or private customer data could be exposed through Obsidian export, logs, or agent briefs.',
  'Store only non-sensitive facts, decisions, paths, and status reports; keep secrets out of Postgres and Obsidian memory.',
  'open',
  '{"topic": "privacy", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  severity = EXCLUDED.severity,
  impact = EXCLUDED.impact,
  mitigation = EXCLUDED.mitigation,
  status = EXCLUDED.status,
  metadata = risks.metadata || EXCLUDED.metadata;

INSERT INTO reports (id, project_id, title, report_type, summary, body, status, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000601',
  '10000000-0000-4000-8000-000000000001',
  'CommCats Website Memory Start',
  'handoff',
  'CommCats is live as a static Alfahosting site and should be improved through the local static source with explicit live-upload approval.',
  'Codex should read this project brief before future commcats.de work. Key constraints: no secret storage, no blind live uploads, use the static source tree, and document important decisions back into the hub.',
  'published',
  '{"topic": "handoff", "sensitive": false}'::jsonb
),
(
  '10000000-0000-4000-8000-000000000602',
  '10000000-0000-4000-8000-000000000002',
  'THE ONE Website Memory Start',
  'handoff',
  'THE ONE remains live on Framer while a static Alfahosting prototype and invisible SEO/AI improvements are prepared.',
  'Codex should read this project brief before future the-one.catering work. Key constraints: preserve the live Framer site until explicit migration approval, start with invisible SEO improvements, and use protected staging for the static prototype.',
  'published',
  '{"topic": "handoff", "sensitive": false}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  report_type = EXCLUDED.report_type,
  summary = EXCLUDED.summary,
  body = EXCLUDED.body,
  status = EXCLUDED.status,
  metadata = reports.metadata || EXCLUDED.metadata;

INSERT INTO agent_actions (id, agent_id, action, object_type, object_id, input, output, status, error, metadata)
VALUES
(
  '10000000-0000-4000-8000-000000000701',
  '10000000-0000-4000-8000-000000000011',
  'seed_business_site_memory',
  'project',
  '10000000-0000-4000-8000-000000000001',
  '{"seed": "business_sites.sql"}'::jsonb,
  '{"projects": ["commcats-de", "the-one-catering", "lamour"]}'::jsonb,
  'succeeded',
  NULL,
  '{"seed": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  agent_id = EXCLUDED.agent_id,
  action = EXCLUDED.action,
  object_type = EXCLUDED.object_type,
  object_id = EXCLUDED.object_id,
  input = EXCLUDED.input,
  output = EXCLUDED.output,
  status = EXCLUDED.status,
  error = EXCLUDED.error,
  metadata = agent_actions.metadata || EXCLUDED.metadata;

COMMIT;
