-- Allow curated relations to point at agent action audit rows.

BEGIN;

ALTER TABLE relations
DROP CONSTRAINT IF EXISTS relations_source_type_check;

ALTER TABLE relations
ADD CONSTRAINT relations_source_type_check
CHECK (
  source_type IN (
    'project',
    'agent',
    'document',
    'fact',
    'decision',
    'open_question',
    'risk',
    'report',
    'agent_action'
  )
);

ALTER TABLE relations
DROP CONSTRAINT IF EXISTS relations_target_type_check;

ALTER TABLE relations
ADD CONSTRAINT relations_target_type_check
CHECK (
  target_type IN (
    'project',
    'agent',
    'document',
    'fact',
    'decision',
    'open_question',
    'risk',
    'report',
    'agent_action'
  )
);

COMMIT;
