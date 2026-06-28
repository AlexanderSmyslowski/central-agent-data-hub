# Automation Boundaries

Agent Data Hub can support more independent agent work, but it should not blur
the line between unreviewed input and reviewed memory.

The useful question is not "can this be automated?" but "what kind of
automation is this?"

## Boundary Levels

### Automatic

These actions may run automatically because they inspect, verify, or project
already reviewed state:

- `agent-hub status`
- `agent-hub check`
- `agent-hub quality`
- `agent-hub receipt`
- `agent-hub export`
- `agent-hub export-okf`
- local backup health checks
- local database backup after reviewed memory changes
- read-only briefs, context packs, and compiled memory

Automatic actions must not create new reviewed claims. They may fail loudly,
write local projections, or produce audit evidence.

The MCP server belongs in this read-only layer. It exposes reviewed Hub context
over stdio for external agents, but it has no write tools, no HTTP transport,
and no import, remember, accept, reject, or sync capability. The server asks
Postgres for a read-only session; writes remain outside the MCP boundary.

Hub View's agent context screen mostly belongs in this read-only layer. It lets
a human click from a project to a visible task context pack, using the same
reviewed prepare path as the CLI. It may show how reviewed memory should shape
an agent run, but it must not create, promote, or modify Hub memory.

Hub View may show one-time local agent connection instructions, such as Claude
Code MCP setup, Codex `AGENTS.md` setup, Hermes/custom startup-rule text, or
generic MCP configuration. These instructions make the handoff visible; they do
not launch, control, or silently feed an unconfigured agent.

The one exception on this screen is a local Codex setup action. When Hub View
knows a project's local folder, it may preview and install the marked ADH block
into that repo's `AGENTS.md` file after an explicit human click. This writes a
repo-local working-rule file, not Hub memory, and it does not run Codex or prove
that Codex used the context.

The `ADH Context Loaded` receipt in `agent_start.sh`, `agent-hub prepare`, and
Hub View is also read-only. It confirms which reviewed context is being handed
to an agent or chatbot; it is not proof that an agent has already used that
context.

`agent-hub export-okf` also belongs in this read-only layer. It projects
reviewed Hub memory into an OKF-style Markdown/YAML bundle and does not import,
sync, promote drafts, or change Hub rows.

The only write candidates that may use the automatic route are reversible
evidence with strong provenance:

- receipts
- audit records
- same-source refreshes of an existing reviewed item

Automatic routing records a reason string. It must not silently turn an
ordinary new claim into reviewed memory.

### Suggested

These actions may produce recommendations, but not reviewed Hub writes:

- reading Signal Inbox entries
- grouping signals by likely project
- summarizing what a signal appears to say
- proposing a fact, decision, risk, open question, report, skill, or policy
  candidate
- identifying unclear project ownership
- flagging sensitive or unsafe material

Suggested actions should show the evidence, uncertainty, likely memory type,
and recommended next step. They should be treated as triage output, not as Hub
truth.

Ordinary unreviewed candidates may be stored as `draft`. A draft is visible to
`agent-hub prepare` and `agent-hub inbox`, but it is not reviewed memory.
Agent-facing read automation must use the shared status policy: briefs,
compiled memory, handoffs, context/search defaults, and MCP project briefs hide
drafts and inactive statuses. Search may include them only when the caller asks
with the explicit include flags. Human projection surfaces may show drafts as
review work, but they must label them as unreviewed.

### Reviewed

These actions may write to PostgreSQL only after review:

- storing a fact
- storing or updating a decision
- storing a risk
- creating or answering an open question
- storing a report
- writing a relation
- importing controlled Markdown into Hub memory

Reviewed writeback needs a project boundary, clear source, correct memory type,
non-sensitive content, and durable value for future work. Use `--dry-run` first
when there is any doubt.

Draft promotion is a reviewed action. It happens only through an explicit review
step such as:

```bash
agent-hub inbox --accept <draft-id> --reviewer alice
```

Rejecting a draft is also explicit and audited:

```bash
agent-hub inbox --reject <draft-id> --reviewer alice
```

There is no time-based auto-accept and no silent promotion from draft to
reviewed memory.

Relations may be created while either endpoint is still a draft, but the
command warns about that state. Agent-facing relation reads hide relations that
would expose draft or inactive endpoint summaries.

Hub View may expose the same reviewed action in its local Review Inbox. This is
not a general UI write boundary: the only allowed Hub View memory writes are
accepting one draft or rejecting one draft. Both actions reuse the
`agent-hub inbox` review path and write the same audit trail.

Hub View review actions are guarded deliberately:

- writes use `POST` only
- each form includes a server-generated CSRF token
- requests with an `Origin` header must come from loopback
- review buttons are disabled when Hub View is not bound to loopback
- there is no bulk accept and no silent promotion

Hub View's Codex setup action is guarded separately:

- writes use `POST` only
- each form includes a server-generated CSRF token
- requests with an `Origin` header must come from loopback
- setup buttons are disabled when Hub View is not bound to loopback
- the browser does not provide the repo path; Hub View uses the known project
  path from ADH metadata
- the public-demo checkout is preview/dry-run only and cannot install a
  demo-project block into the repository's `AGENTS.md`
- the target is the repo-local `AGENTS.md` file
- the block is shown before installation
- no shell command is executed from Hub View

The public mobile preview mode binds Hub View to the local network for reading
from a phone. That does not widen the write boundary: because the server is not
bound to loopback, Review Inbox actions and Codex setup actions remain disabled.

Agent Data Hub v0.1.x uses attribution instead of access control: everyone in
the trusted local workspace can see the review inbox, but every accept/reject
decision must carry a reviewer handle. This is not an authentication system.
Routing can name a responsible reviewer for a draft, but it does not enforce
permissions; the audit records the responsible reviewer and the reviewer who
actually accepted or rejected the draft.
A local `AGENT_HUB_REVIEWER` environment variable may provide the reviewer handle, but public templates leave it unset so review identity is chosen explicitly.

Allowlisted internal chat channels, such as Telegram, are consciously approved
review channels for draft cards. Telegram bot messages are not end-to-end
encrypted and pass through Telegram servers; only content that is non-sensitive
by Hub policy may appear in cards. Channel adapters live outside this repository
and must use `agent_hub.review_api`. This is attribution, not authentication.

## Demo And Ops Database Boundary

The public demo path and the maintainer local ops path are physically separate
database targets.

`scripts/db_start_public_demo.sh` forces a demo database identity for its own
process: separate database name, container, volume, and port. It also overrides
any `DATABASE_URL` loaded from `.env` and refuses to migrate or seed unless the
effective target database is the demo database.

`scripts/db_start.sh` is the maintainer local ops path. It intentionally uses
the configured local database from `.env` and is the place for the operator's
real working set.

This keeps public onboarding scripts from writing into the maintainer's
operational memory store.

### Human Review Required

Some candidates are not written as drafts until a human looks at them. The Hub
routes these to `ask` when a deterministic rule sees:

- money amounts
- secret or credential patterns
- customer-data hints
- deletion intent
- contradiction with existing reviewed memory for the same identity

Each `ask` decision carries a reason string and should be shown in plain
language: what would be remembered, the source, and the consequence if it is
wrong.

### Requires Explicit Human Approval

These actions are outside normal autonomous Hub work:

- deployment or production changes
- deleting data, backups, repositories, or live files
- publishing externally
- using credentials or protected hosting access
- handling customer-private data, raw invoices, secrets, tokens, or private logs
- changing the schema or automation policy in a way that expands write authority

For these, request explicit human approval and use secure handoff outside the
Hub, Git, and Obsidian for credentials or protected access. Store back only the
reviewed, non-sensitive outcome.

## Writeback Checklist

Before a memory write, an agent should be able to answer yes to all of these:

- Is it attached to the correct project?
- Is the source clear and non-sensitive?
- Has the claim or conclusion been reviewed?
- Is it useful beyond the current chat or command output?
- Is the memory type correct?
- Is it free of secrets, credentials, private customer data, raw invoices, raw
  logs, and deployment secrets?

If any answer is no, do not write reviewed memory. Keep it in the current work,
place a non-sensitive signal upstream, or create a reviewed open question.

## Signal Inbox Rule

Signal Inbox content is unreviewed by default. An agent may read it, summarize
it, and suggest what it might become. It must not auto-promote Signal Inbox
entries into PostgreSQL.

Before a Signal Inbox item is promoted, the reviewing agent should briefly tell
the human:

- what the signal is about
- which project it likely concerns
- what memory type it might become
- what uncertainty remains
- whether any sensitivity risk exists

Only the reviewed result may be written to Agent Data Hub.

## Practical Default

Keep automation boring:

- automate checks, projections, receipts, and backups
- automate summaries and triage suggestions
- keep reviewed writeback explicit
- keep operational actions behind human approval

This preserves the core promise: verified context for humans and agents.
