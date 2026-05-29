-- Central Agent Data Hub migration tracking.
-- Adds a durable record of applied schema migrations.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
  migration_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('applied', 'failed')),
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_schema_migrations_status
ON schema_migrations(status);

CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
ON schema_migrations(applied_at);

COMMIT;
