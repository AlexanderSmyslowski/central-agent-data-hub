# Installation Boundary

Agent Data Hub currently uses the git checkout as the installation unit.

This is intentional for now. The daily workflow uses both the Python CLI and
repo-local shell scripts:

- `agent-hub` for database-backed read, review, export, and diagnostic commands
- `scripts/*.sh` for local Docker/Postgres startup, public demo setup,
  agent-start/finish wrappers, backup, restore, and smoke checks

## Supported Preview Path

Use the checkout directly. In this preview, clone is installation:

```bash
git clone https://github.com/AlexanderSmyslowski/central-agent-data-hub.git
cd central-agent-data-hub
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
scripts/db_start_public_demo.sh
scripts/db_doctor.sh --public-demo
scripts/smoke_public_demo.sh
```

The editable install makes the `agent-hub` CLI import this checkout. It does
not turn ADH into a standalone package that can run all operational scripts
from `site-packages`; `agent-hub` alone is not the full product surface.

## Platform Statement

The public preview is tested on:

- GitHub Actions `ubuntu-latest`
- local macOS development with Docker Desktop

The scripts require Bash, Python 3.11+, Docker, and Docker Compose.

Native Windows is not a supported v0.2 target. Windows users should treat WSL2
plus Docker as the realistic path and verify it locally.

## Upgrade Model

For this preview, upgrade the checkout with Git:

```bash
git pull
.venv/bin/python -m pip install -e .
agent-hub migrate --status
```

Apply migrations only after checking the target database and taking a backup
when it is an operator database.

The CI upgrade drill proves the untracked baseline path:

```bash
scripts/upgrade_drill.sh
```

That drill runs only against the isolated public demo database. It is not a
general-purpose restore tool and does not target the operator database.

## Non-Editable Installs

A regular `pip install` can expose importable Python modules, but checkout-bound
commands such as `agent-hub setup` and `agent-hub doctor` need the repository
scripts. Outside a checkout, they fail with an explicit message instead of
pretending that ADH is a fully packaged standalone application.
