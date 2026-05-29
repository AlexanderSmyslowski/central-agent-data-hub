-- Central Agent Data Hub demo seed data
-- Re-runnable after migrations/001_init.sql.

BEGIN;

INSERT INTO projects (id, name, slug, description, status, metadata)
VALUES (
  '00000000-0000-4000-8000-000000000001',
  'Central Agent Data Hub Demo',
  'central-agent-data-hub-demo',
  'Demo project for validating the Central Agent Data Hub v0 schema.',
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
  'Architecture Agent',
  'architecture-agent',
  'Maintains schema decisions, reports, and knowledge-base projections.',
  'active',
  '{"demo": true, "profile": "architecture"}'::jsonb
)
ON CONFLICT (project_id, slug) DO UPDATE SET
  name = EXCLUDED.name,
  role = EXCLUDED.role,
  status = EXCLUDED.status,
  metadata = EXCLUDED.metadata;

INSERT INTO documents (id, project_id, title, slug, path, content, frontmatter, content_hash, status, metadata)
VALUES
(
  '00000000-0000-4000-8000-000000000101',
  '00000000-0000-4000-8000-000000000001',
  'Concept: Central Agent Data Hub',
  'concept-central-agent-data-hub',
  'docs/concepts/central-agent-data-hub.md',
  '# Central Agent Data Hub\n\nA shared schema for project knowledge, agent reports, decisions, risks, and sync events.',
  '{"type": "concept", "demo": true}'::jsonb,
  'demo-hash-concept-001',
  'active',
  '{"demo": true}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000102',
  '00000000-0000-4000-8000-000000000001',
  'Technical Report: v0 Schema Smoke',
  'technical-report-v0-schema-smoke',
  'reports/technical/v0-schema-smoke.md',
  '# v0 Schema Smoke\n\nMigration and demo seed validate core entities, relations, audit events, and sync events.',
  '{"type": "technical-report", "demo": true}'::jsonb,
  'demo-hash-report-001',
  'active',
  '{"demo": true}'::jsonb
)
ON CONFLICT (project_id, slug) DO UPDATE SET
  title = EXCLUDED.title,
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
  'The v0 schema stores documents, facts, decisions, open questions, risks, reports, and audit trails.',
  'docs/concepts/central-agent-data-hub.md',
  0.950,
  'verified',
  '{"demo": true, "confidence_label": "high"}'::jsonb
),
(
  '00000000-0000-4000-8000-000000000202',
  '00000000-0000-4000-8000-000000000001',
  'A later Obsidian export can map frontmatter and markdown paths without additional core tables.',
  'reports/technical/v0-schema-smoke.md',
  0.550,
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
  'Should Obsidian export remain file-based in v0 or get a dedicated sync worker immediately?',
  NULL,
  'open',
  NULL,
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
  'Keep v0 focused on schema, relations, audit, and sync events before adding application code.',
  'The first phase should validate the data model with deterministic migrations and seeds.',
  'No API, UI, worker, or search extension is introduced in v0.',
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
  'Knowledge graph drift',
  'medium',
  'Relations may become stale if documents, facts, and reports are updated independently.',
  'Use sync_events, content_hash checks, and agent_actions to audit later reconciliation runs.',
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
  'Demo Schema Validation Report',
  'status',
  'Demo data validates core project, document, fact, decision, risk, relation, audit, and sync flows.',
  'The Architecture Agent created this report as a deterministic seed artifact for local schema checks.',
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
  '{"demo": true, "label": "technical report references decision"}'::jsonb
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
  '{"source_documents": ["docs/concepts/central-agent-data-hub.md"]}'::jsonb,
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
  'demo_seed_loaded',
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
  'obsidian-demo-export',
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
