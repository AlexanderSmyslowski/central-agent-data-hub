# Public Getting Started

This path is the recommended public preview path for the repository. It uses
the neutral demo dataset, not the maintainer's own daily project seeds.

## 1. Run The Public Demo

Use Python 3.11+, Docker, and Docker Compose. Make sure Docker is running
before starting the local database.

From a fresh folder:

```bash
git clone https://github.com/AlexanderSmyslowski/central-agent-data-hub.git
cd central-agent-data-hub
scripts/first_run_demo.sh
```

The script creates `.venv` if needed, installs the local CLI, creates `.env`
from `.env.example` if missing, starts the isolated public demo database, runs
the public demo check, then starts Hub View and prints the local URL to open.
It does not overwrite an existing `.env`.

For a non-blocking check without starting Hub View:

```bash
scripts/first_run_demo.sh --no-hub-view
```

## 2. Manual Path For Troubleshooting

If you want to run the same path step by step, use:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
scripts/db_start_public_demo.sh
bash scripts/smoke_public_demo.sh
AGENT_HUB_PUBLIC_DEMO=1 scripts/hub_view.sh
```

The `.env.example` file contains local defaults. Copying it to `.env` creates
your local configuration file. Existing `.env` files are local and should not be
committed.

Pip may print upgrade notices. You can ignore those during the first demo run
as long as the install command finishes successfully.

For a later guided local operator setup, run:

```bash
agent-hub setup
```

The setup assistant is optional and is not required for the public demo.

If you prefer not to create `.env`, export the required variables manually:

```bash
export DATABASE_URL="postgresql://postgres:changeme@localhost:55432/agent_hub"
export OBSIDIAN_EXPORT_DIR=".local/obsidian-export"
```

## 3. Direct Public Demo Database Start

```bash
scripts/db_start_public_demo.sh
```

This script starts PostgreSQL, applies migrations, seeds only `seed/demo.sql`,
and prints a demo-focused readiness check.

It does not wipe an existing local operator database. For the quietest first
run, use it against a fresh local database or Docker volume.

If you need to run a second local copy alongside an existing Agent Data Hub
instance, set demo overrides in the shell before starting the script. Use a
database name containing `demo`, and set matching `AGENT_HUB_DB_NAME`,
`AGENT_HUB_DB_PORT`, `AGENT_HUB_DB_CONTAINER`, `AGENT_HUB_DB_VOLUME`, and
`AGENT_HUB_COMPOSE_PROJECT_NAME` values. The public demo path ignores
`DATABASE_URL` from `.env` for its own process.

## 4. Run The Demo Check

```bash
bash scripts/smoke_public_demo.sh
```

This checks the demo database, core read paths, Markdown export, and Hub View
startup. `Public demo smoke: ok` means the demo path is working.

## 5. Open Hub View

Start Hub View:

```bash
AGENT_HUB_PUBLIC_DEMO=1 scripts/hub_view.sh
```

Hub View is a local review surface. It reads reviewed memory and can accept or
reject draft candidates as explicit review actions. PostgreSQL remains the
reviewed source of truth.

To see how an agent would use ADH, open a project in Hub View and use
**Connect an agent**. Enter a task and click **Create context pack**. Hub View
will show the reviewed context being handed to the agent and provide a
copy-ready pack for chatbots. For local agents, Hub View shows the one-time MCP
or startup-rule setup. Hub View does not connect the agent by itself; the local
agent must be configured once before it can request ADH context when work
starts.

Optional: export the Markdown projection manually if you want to inspect the
generated files:

```bash
.venv/bin/python -m agent_hub.cli export
```

## Important Note About Startup Paths

`scripts/db_start_public_demo.sh` is the public sample path.

`scripts/db_start.sh` reflects the maintainer's own operator workflow and loads
maintainer-local working seeds. It is useful for real daily operations, but not
the recommended public preview path.
