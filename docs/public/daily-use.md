# Daily Local Use

The public demo is the first ten minutes. Daily use starts when Agent Data Hub
is connected to a real local project.

Keep the daily path small:

```text
register project -> connect agent -> start with reviewed context -> work
-> review useful residue -> finish with handoff
```

## 1. Register One Project

Register each real repository once:

```bash
scripts/register_project.sh \
  --repo /path/to/project \
  --slug <project-slug> \
  --name "Project Name"
```

This creates the project boundary that later agent runs must respect. Do not
reuse another project's memory for an unregistered repo.

## 2. Connect The Agent

Use one of these paths:

- Hub View: open the project and use **Connect an agent**.
- CLI: install the repo-local ADH block with
  `scripts/install_repo_agent_memory.sh`.
- MCP: configure the agent to launch `agent-hub mcp-serve` over stdio.
- Chatbot fallback: copy the visible context pack from Hub View or
  `agent-hub prepare`.

The connection step does not prove that an agent used the context. It only
makes the handoff visible and repeatable.

## 3. Start Work

Before meaningful work, load reviewed context:

```bash
scripts/agent_start.sh \
  --project <project-slug> \
  --query "<current focus>" \
  --review
```

For a task-specific pack, use:

```bash
agent-hub prepare --project <project-slug> --task "<current task>"
```

Agents should treat the Context Trail and Known Gaps as part of the work, not
as decorative output.

## 4. Keep Inputs Separate

During the run, keep the three zones distinct:

- Chat or working notes: temporary material for the current task.
- Signal Inbox: interesting unreviewed inputs that may matter later.
- Agent Data Hub: reviewed project memory only.

Unreviewed claims may become drafts or signals. They are not reviewed memory
until a human explicitly accepts them.

## 5. Review Drafts

Review suggested memory changes deliberately:

```bash
agent-hub inbox
agent-hub inbox --accept <draft-id> --reviewer alice
agent-hub inbox --reject <draft-id> --reviewer alice
```

Hub View exposes the same narrow review action locally. Accept and reject are
audited; there is no time-based auto-accept and no silent promotion.

## 6. Finish The Run

Close the loop with a summary and handoff:

```bash
scripts/agent_finish.sh --project <project-slug> --review
```

If durable memory was written and the session should end with projection and
backup, use:

```bash
scripts/agent_finish.sh --project <project-slug> --review --export --backup
scripts/memory_receipt.sh --project <project-slug> --since 24h
```

## 7. Diagnose Before Restarting Things

For the configured operator database:

```bash
agent-hub doctor
```

For the public demo database:

```bash
scripts/db_doctor.sh --public-demo
```

For the public demo path as a whole:

```bash
scripts/smoke_public_demo.sh
```

The smoke checks status, consistency, prepare context with Context Trail and
Known Gaps, deterministic OKF export, Markdown export, and Hub View rendering.

Doctor and recovery paths are local operator tools. They should explain what is
wrong before anything changes.

## Daily Success Criteria

A good daily ADH run has these properties:

- the project boundary is explicit
- the agent starts from reviewed context
- unreviewed inputs stay labelled
- useful residue is reviewed before it becomes memory
- the finish step leaves a readable handoff
- status, check, backup, and receipt commands can explain the system state

The goal is not to remember everything. The goal is to make tomorrow's agent
start from fewer, better, verified assumptions.
