-- Central Agent Data Hub demo seed data
-- Re-runnable after migrations/001_init.sql.

BEGIN;

INSERT INTO projects (id, name, slug, description, status, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000001',
  'Central Agent Data Hub Demo',
  'central-agent-data-hub-demo',
  'Neutral demo project for showing how reviewed context is stored and read locally.',
  'active',
  '{"demo": true, "source": "seed/demo.sql"}'::jsonb
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO agents (id, project_id, name, slug, role, status, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000010',
  '00000000-0000-4000-8000-000000000001',
  'Demo Review Agent',
  'demo-review-agent',
  'Creates neutral sample memory for the public demo.',
  'active',
  '{"demo": true, "profile": "public-demo"}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  slug = EXCLUDED.slug,
  role = EXCLUDED.role,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO documents (id, project_id, title, slug, path, content, frontmatter, content_hash, status, metadata)
VALUES
(
  '00000000-0000-4000-8000-000000000101',
  '00000000-0000-4000-8000-000000000001',
  'Concept: Reviewed Context',
  'concept-reviewed-context',
  'docs/demo/reviewed-context.md',
  '# Reviewed Context\n\nAgent Data Hub keeps small pieces of project knowledge only after they have a source and a review status.',
  '{"type": "concept", "demo": true}'::jsonb,
  'demo-hash-concept-001',
  'active',
  '{"demo": true}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000102',
  '00000000-0000-4000-8000-000000000001',
  'Demo Note: Review Flow',
  'demo-note-review-flow',
  'reports/demo/review-flow.md',
  '# Review Flow\n\nUnreviewed notes stay separate until a person accepts or rejects them. Reviewed memory is then available to agents as context.',
  '{"type": "demo-note", "demo": true}'::jsonb,
  'demo-hash-report-001',
  'active',
  '{"demo": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  slug = EXCLUDED.slug,
  path = EXCLUDED.path,
  content = EXCLUDED.content,
  frontmatter = EXCLUDED.frontmatter,
  content_hash = EXCLUDED.content_hash,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO facts (id, project_id, statement, source, confidence, status, metadata)
VALUES
(
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000001',
  'Reviewed memory is context with a source and a review status before agents use it.',
  'docs/demo/reviewed-context.md',
  0.950,
  'verified',
  '{"demo": true, "confidence_label": "high"}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000202',
  '00000000-0000-4000-8000-000000000001',
  'A Signal Inbox can hold interesting but unreviewed notes until someone decides whether they matter.',
  'reports/demo/review-flow.md',
  0.650,
  'proposed',
  '{"demo": true, "confidence_label": "medium"}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  statement = EXCLUDED.statement,
  source = EXCLUDED.source,
  confidence = EXCLUDED.confidence,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO open_questions (id, project_id, question, answer, status, resolved_at, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000301',
  '00000000-0000-4000-8000-000000000001',
  'Should every useful note become reviewed memory?',
  'No. Only durable, sourceable context should be promoted. Temporary notes can stay in chat or in a Signal Inbox until reviewed.',
  'answered',
  CURRENT_TIMESTAMP,
  '{"demo": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  question = EXCLUDED.question,
  answer = EXCLUDED.answer,
  status = EXCLUDED.status,
  resolved_at = EXCLUDED.resolved_at,
  metadata = EXCLUDED.metadata;

INSERT INTO decisions (id, project_id, decision, rationale, consequences, status, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000401',
  '00000000-0000-4000-8000-000000000001',
  'Keep the public demo small and focused on reviewed context.',
  'A first-time user should see the memory model without maintainer-local projects or old test artifacts.',
  'The demo uses one neutral project with a few facts, decisions, questions, risks, and reports.',
  'accepted',
  '{"demo": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  decision = EXCLUDED.decision,
  rationale = EXCLUDED.rationale,
  consequences = EXCLUDED.consequences,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO risks (id, project_id, title, severity, impact, mitigation, status, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000501',
  '00000000-0000-4000-8000-000000000001',
  'Unreviewed notes treated as facts',
  'medium',
  'Agents may act on weak or stale assumptions if rough notes are promoted too early.',
  'Keep drafts and Signal Inbox items separate until a reviewer accepts them.',
  'open',
  '{"demo": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  severity = EXCLUDED.severity,
  impact = EXCLUDED.impact,
  mitigation = EXCLUDED.mitigation,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO reports (id, project_id, title, report_type, summary, body, status, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000601',
  '00000000-0000-4000-8000-000000000001',
  'Public Demo Context Report',
  'status',
  'The demo shows how a small set of reviewed project memory can become agent context.',
  'This report is neutral sample data. It exists only to make the local demo readable during a first run.',
  'published',
  '{"demo": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  report_type = EXCLUDED.report_type,
  summary = EXCLUDED.summary,
  body = EXCLUDED.body,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO relations (id, source_type, source_id, relation_type, target_type, target_id, metadata)
VALUES
(
  '00000000-0000-4000-8000-000000000701',
  'document', '00000000-0000-4000-8000-000000000101',
  'supports',
  'fact', '00000000-0000-4000-8000-000000000201',
  '{"demo": true, "label": "document supports fact"}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000702',
  'fact', '00000000-0000-4000-8000-000000000202',
  'raises',
  'open_question', '00000000-0000-4000-8000-000000000301',
  '{"demo": true, "label": "fact raises open_question"}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000703',
  'decision', '00000000-0000-4000-8000-000000000401',
  'answers',
  'open_question', '00000000-0000-4000-8000-000000000301',
  '{"demo": true, "label": "decision answers open_question"}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000704',
  'risk', '00000000-0000-4000-8000-000000000501',
  'blocks',
  'project', '00000000-0000-4000-8000-000000000001',
  '{"demo": true, "label": "risk blocks project"}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000705',
  'agent', '00000000-0000-4000-8000-000000000010',
  'references',
  'report', '00000000-0000-4000-8000-000000000601',
  '{"demo": true, "label": "agent references report"}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000706',
  'document', '00000000-0000-4000-8000-000000000102',
  'references',
  'decision', '00000000-0000-4000-8000-000000000401',
  '{"demo": true, "label": "demo note references decision"}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  source_type = EXCLUDED.source_type,
  source_id = EXCLUDED.source_id,
  relation_type = EXCLUDED.relation_type,
  target_type = EXCLUDED.target_type,
  target_id = EXCLUDED.target_id,
  metadata = EXCLUDED.metadata;

INSERT INTO agent_actions (id, agent_id, action, object_type, object_id, input, output, status, error, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000801',
  '00000000-0000-4000-8000-000000000010',
  'create_demo_report',
  'report',
  '00000000-0000-4000-8000-000000000601',
  '{"source_documents": ["docs/demo/reviewed-context.md"]}'::jsonb,
  '{"report_id": "00000000-0000-4000-8000-000000000601", "status": "published"}'::jsonb,
  'succeeded',
  NULL,
  '{"demo": true}'::jsonb
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
  metadata = EXCLUDED.metadata;

INSERT INTO event_log (id, agent_id, event_type, object_type, object_id, payload, status, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000901',
  '00000000-0000-4000-8000-000000000010',
  'public_demo_seed_loaded',
  'project',
  '00000000-0000-4000-8000-000000000001',
  '{"tables_seeded": ["projects", "agents", "documents", "facts", "open_questions", "decisions", "risks", "reports", "relations", "agent_actions", "event_log", "sync_events"]}'::jsonb,
  'recorded',
  '{"demo": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  agent_id = EXCLUDED.agent_id,
  event_type = EXCLUDED.event_type,
  object_type = EXCLUDED.object_type,
  object_id = EXCLUDED.object_id,
  payload = EXCLUDED.payload,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO sync_events (id, source, direction, status, payload, error, metadata)
VALUES (
  '00000000-0000-4000-8000-000000001001',
  'public-demo-export',
  'outbound',
  'succeeded',
  '{"vault": "Demo Vault", "exported_documents": 2, "target": "obsidian/central-agent-data-hub-demo"}'::jsonb,
  NULL,
  '{"demo": true, "simulated": true}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  source = EXCLUDED.source,
  direction = EXCLUDED.direction,
  status = EXCLUDED.status,
  payload = EXCLUDED.payload,
  error = EXCLUDED.error,
  metadata = EXCLUDED.metadata;

COMMIT;
