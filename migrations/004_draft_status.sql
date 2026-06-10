-- Allow draft status for core memory types.
--
-- This migration only widens existing status CHECK constraints. It does not
-- change defaults, add columns, create tables, or update existing data.
--
-- open_questions also has a separate resolved_at CHECK for answered/closed
-- questions. That constraint intentionally remains unchanged; draft does not
-- collide with it because draft is neither answered nor closed.

BEGIN;

DO $$
DECLARE
  status_constraint text;
BEGIN
  SELECT c.conname
  INTO status_constraint
  FROM pg_constraint c
  WHERE c.conrelid = 'public.facts'::regclass
    AND c.contype = 'c'
    AND pg_get_constraintdef(c.oid) LIKE '%status = ANY%'
    AND pg_get_constraintdef(c.oid) NOT LIKE '%resolved_at%'
  ORDER BY c.conname
  LIMIT 1;

  IF status_constraint IS NOT NULL THEN
    EXECUTE format('ALTER TABLE public.facts DROP CONSTRAINT IF EXISTS %I', status_constraint);
  END IF;

  ALTER TABLE public.facts
    ADD CONSTRAINT facts_status_check
    CHECK (status IN ('draft', 'proposed', 'verified', 'disputed', 'deprecated', 'archived'));
END $$;

DO $$
DECLARE
  status_constraint text;
BEGIN
  SELECT c.conname
  INTO status_constraint
  FROM pg_constraint c
  WHERE c.conrelid = 'public.decisions'::regclass
    AND c.contype = 'c'
    AND pg_get_constraintdef(c.oid) LIKE '%status = ANY%'
    AND pg_get_constraintdef(c.oid) NOT LIKE '%resolved_at%'
  ORDER BY c.conname
  LIMIT 1;

  IF status_constraint IS NOT NULL THEN
    EXECUTE format('ALTER TABLE public.decisions DROP CONSTRAINT IF EXISTS %I', status_constraint);
  END IF;

  ALTER TABLE public.decisions
    ADD CONSTRAINT decisions_status_check
    CHECK (status IN ('draft', 'proposed', 'accepted', 'rejected', 'superseded', 'archived'));
END $$;

DO $$
DECLARE
  status_constraint text;
BEGIN
  SELECT c.conname
  INTO status_constraint
  FROM pg_constraint c
  WHERE c.conrelid = 'public.risks'::regclass
    AND c.contype = 'c'
    AND pg_get_constraintdef(c.oid) LIKE '%status = ANY%'
    AND pg_get_constraintdef(c.oid) NOT LIKE '%resolved_at%'
  ORDER BY c.conname
  LIMIT 1;

  IF status_constraint IS NOT NULL THEN
    EXECUTE format('ALTER TABLE public.risks DROP CONSTRAINT IF EXISTS %I', status_constraint);
  END IF;

  ALTER TABLE public.risks
    ADD CONSTRAINT risks_status_check
    CHECK (status IN ('draft', 'open', 'mitigating', 'accepted', 'resolved', 'archived'));
END $$;

DO $$
DECLARE
  status_constraint text;
BEGIN
  SELECT c.conname
  INTO status_constraint
  FROM pg_constraint c
  WHERE c.conrelid = 'public.open_questions'::regclass
    AND c.contype = 'c'
    AND pg_get_constraintdef(c.oid) LIKE '%status = ANY%'
    AND pg_get_constraintdef(c.oid) NOT LIKE '%resolved_at%'
  ORDER BY c.conname
  LIMIT 1;

  IF status_constraint IS NOT NULL THEN
    EXECUTE format(
      'ALTER TABLE public.open_questions DROP CONSTRAINT IF EXISTS %I',
      status_constraint
    );
  END IF;

  ALTER TABLE public.open_questions
    ADD CONSTRAINT open_questions_status_check
    CHECK (status IN ('draft', 'open', 'answered', 'deferred', 'closed', 'archived'));
END $$;

COMMIT;
