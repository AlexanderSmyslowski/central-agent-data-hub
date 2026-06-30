# First-Run Demo Session

This is the shortest useful way to evaluate Agent Data Hub as a public preview.
It should take about ten minutes on a machine with Python 3.11+, Docker, and
Docker Compose.

## 1. Start The Demo

```bash
git clone https://github.com/AlexanderSmyslowski/central-agent-data-hub.git
cd central-agent-data-hub
scripts/first_run_demo.sh
```

Expected result:

- Docker starts an isolated demo Postgres database.
- The demo uses `agent_hub_demo`, not the maintainer database.
- The script prints a local Hub View URL.
- The terminal ends with a working local preview, not a production service.

## 2. Open The Demo Project

Open the printed Hub View URL and choose the demo project.

Expected result:

- You see reviewed demo memory, not private maintainer projects.
- The project page shows latest status, risks and questions, reviewed memory,
  Review Inbox, and agent handoff options.
- Empty sections are normal; the demo is intentionally small.

## 3. Review One Draft

Open Review Inbox.

Expected result:

- One neutral suggested memory change is visible.
- The card says what would be remembered, where it came from, and what could go
  wrong if it is false.
- Accepting or rejecting the draft is an explicit review action by
  `demo-reviewer`. This is attribution, not authentication.

## 4. Prepare One Agent Handoff

Open **Connect an agent**, enter a small task such as:

```text
review the demo project state
```

Then prepare the handoff.

Expected result:

- Hub View shows reviewed context for that task.
- The handoff includes trail information and known gaps.
- Hub View does not run an agent. It gives a human or configured local agent a
  clearer starting point.

## 5. Check The Boundary

The first run should make these boundaries visible:

- Reviewed memory is different from raw chat history.
- Drafts do not become reviewed memory by age or background automation.
- PostgreSQL remains the source of truth.
- Hub View is a local review surface.
- Public demo data is separate from maintainer local data.

## 6. If The Hub Looks Offline

Run:

```bash
agent-hub doctor
# or, from this checkout:
.venv/bin/python -m agent_hub.cli doctor
```

For known local Docker/Postgres stale-lock failures, the guarded recovery path
is:

```bash
scripts/db_recover.sh --apply
```

Recovery creates a local volume snapshot before changes, recreates only the
container, and does not remove Docker volumes or alter Hub memory rows.

## What A Successful First Run Proves

A successful first run proves only this:

- Agent Data Hub can start locally.
- The public demo path is isolated.
- Reviewed memory can be inspected.
- A draft can be reviewed explicitly.
- A task-specific agent context handoff can be prepared.

It does not prove hosted deployment, multi-user auth, autonomous agent
execution, or production readiness.
