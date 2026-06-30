# Public Getting Started

This is the recommended public preview path. It uses a neutral demo database,
not the maintainer's daily working data.

## Fast Path

Use Python 3.11+, Docker, and Docker Compose. Make sure Docker is running.

```bash
git clone https://github.com/AlexanderSmyslowski/central-agent-data-hub.git
cd central-agent-data-hub
scripts/first_run_demo.sh
```

The script creates `.venv` if needed, installs or reuses the local CLI, creates
`.env` from `.env.example` if missing, starts the isolated public demo
database, runs the public demo check, then starts Hub View and prints the local
URL to open. It does not overwrite an existing `.env`.

The demo includes one neutral suggested memory change in Review Inbox. The
one-command path uses `demo-reviewer` only for local demo attribution; this is
not authentication and is not written to `.env`.

## What To Check First

In the first ten minutes, check only this:

1. Open the printed Hub View URL.
2. Open the demo project.
3. Open Review Inbox and inspect the suggested memory change.
4. Accept or reject it; both actions are explicit review actions.
5. Open **Connect an agent** and prepare one agent handoff.
6. Notice the boundary: Hub View shows context; it does not run an agent.

For the same path with expected screen-by-screen observations, see
[`first-run-demo-session.md`](first-run-demo-session.md).

## If Something Fails

Run the local doctor before changing Docker state by hand:

```bash
agent-hub doctor
# or, from this checkout:
.venv/bin/python -m agent_hub.cli doctor
```

If the doctor reports a known stale Postgres lock-file problem, use:

```bash
scripts/db_recover.sh --apply
```

The recovery path creates a Docker-volume snapshot first, recreates only the
container, and never removes volumes or writes Hub memory.

For a non-blocking check without starting Hub View:

```bash
scripts/first_run_demo.sh --no-hub-view
```

## Optional Mobile Preview

To open the demo from a phone on the same trusted Wi-Fi:

```bash
scripts/first_run_demo.sh --mobile
```

The script prints a laptop URL and, when it can detect one, a phone URL such as
`http://192.168.x.x:8765`. Use this only on a trusted local network. Mobile
preview is read-oriented: Review Inbox and Codex setup writes stay disabled
when Hub View is not bound to loopback. Direct non-loopback Hub View starts
require `--allow-lan-read`.

## Manual Path

Use this only when you want to see each step separately:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
scripts/db_start_public_demo.sh
bash scripts/smoke_public_demo.sh
AGENT_HUB_PUBLIC_DEMO=1 AGENT_HUB_REVIEWERS=demo-reviewer HUB_VIEW_REVIEWER=demo-reviewer scripts/hub_view.sh
```

The `.env.example` file contains local defaults. Copying it to `.env` creates
your local configuration file. Existing `.env` files are local and should not be
committed.

For a later guided local operator setup, run:

```bash
agent-hub setup
```

The setup assistant is optional and is not required for the public demo.

## Startup Boundary

`scripts/db_start_public_demo.sh` is the public sample path. It forces a
separate demo database identity and ignores `DATABASE_URL` from `.env` for its
own process.

`scripts/db_start.sh` is the maintainer local ops path. It loads
maintainer-local working seeds and is not the recommended public preview path.
