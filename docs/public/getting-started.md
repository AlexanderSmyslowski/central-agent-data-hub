# Public Getting Started

This path is the recommended public preview path for the repository. It uses
the neutral demo dataset, not the maintainer's own daily project seeds.

## 1. Prepare Environment

Use Python 3.11+, Docker, and Docker Compose.

Create a local `.env` from `.env.example`, or export the required variables:

```bash
export DATABASE_URL="postgresql://postgres@localhost:55432/agent_hub"
export OBSIDIAN_EXPORT_DIR=".local/obsidian-export"
```

## 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

## 3. Apply Migrations

```bash
.venv/bin/python -m agent_hub.cli migrate --apply
```

## 4. Load Demo Data

```bash
docker compose exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U postgres -d agent_hub \
  < seed/demo.sql
```

## 5. Verify the System

```bash
.venv/bin/python -m agent_hub.cli status
.venv/bin/python -m agent_hub.cli check
.venv/bin/python -m agent_hub.cli compile --project central-agent-data-hub-demo
```

## 6. Open Human Views

Export the Markdown projection:

```bash
.venv/bin/python -m agent_hub.cli export
```

Start Hub View:

```bash
scripts/hub_view.sh
```

Hub View is a local read-only review surface. PostgreSQL remains the reviewed
source of truth.

## Important Note About Seeds

`seed/demo.sql` is the public sample dataset.

`seed/business_sites.sql` and `seed/agentic_projects.sql` reflect the
maintainer's own operator workflow and local projects. They are useful as real
working examples, but not the recommended public preview path.
