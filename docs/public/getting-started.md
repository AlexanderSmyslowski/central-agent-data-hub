# Public Getting Started

This path is the recommended public preview path for the repository. It uses
the neutral demo dataset, not the maintainer's own daily project seeds.

## 1. Prepare Environment

Use Python 3.11+, Docker, and Docker Compose.

From a fresh checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

For the guided path, start here:

```bash
agent-hub setup
```

The assistant asks only a few questions, proposes defaults, can create a
Signal Inbox, shows a summary before writing, and stores a local setup file
without touching the database or silently registering projects.

If you prefer not to create `.env`, export the required variables manually:

```bash
export DATABASE_URL="postgresql://postgres@localhost:55432/agent_hub"
export OBSIDIAN_EXPORT_DIR=".local/obsidian-export"
```

## 2. Start The Public Demo Path

```bash
scripts/db_start_public_demo.sh
```

This script starts PostgreSQL, applies migrations, seeds only `seed/demo.sql`,
and prints a demo-focused readiness check.

It does not wipe an existing local operator database. For the quietest first
run, use it against a fresh local database or Docker volume.

## 3. Run The End-To-End Demo Smoke

```bash
bash scripts/smoke_public_demo.sh
```

## 4. Open Human Views

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

## Important Note About Startup Paths

`scripts/db_start_public_demo.sh` is the public sample path.

`scripts/db_start.sh` reflects the maintainer's own operator workflow and loads
maintainer-local working seeds. It is useful for real daily operations, but not
the recommended public preview path.
