# Agentic Work Workflow

This workflow is the working contract for Codex/Hermes project work that uses
the Central Agent Data Hub.

For the shortest copyable version, use `docs/agent-run-card.md`.

The Hub separates three things:

- **Gedächtnis**: what the project has durably reviewed.
- **Arbeitskontext**: what applies to this specific run.
- **Arbeitsregeln**: how the agent should work in the repo.

This distinction keeps the Hub small. PostgreSQL stores reviewed memory. The
start helpers assemble the current working context. `AGENTS.md`, repo documents,
and skills keep the working rules close to the code.

## Before Work

Run the start helper before changing or deciding anything meaningful:

```bash
scripts/agent_start.sh --project <project-slug> --query "<current work focus>"
```

If no focused query is known yet:

```bash
scripts/agent_start.sh --project <project-slug>
```

For higher-risk or longer work, include the project review:

```bash
scripts/agent_start.sh --project <project-slug> --query "<current work focus>" --review
```

The start helper prints an **ADH Context Loaded** receipt before the detailed
memory sections. The receipt shows the project, task, reviewed-memory counts,
and how reviewed facts, decisions, risks, open questions, and drafts should
shape the agent run. It then prints the working contract: keep the project
boundary explicit, do not transfer assumptions between projects, do not store
sensitive data, and treat uncertainty as an open question.

For single-project work, the start helper also creates a local working-tree run
lock. This protects against two write-capable agents using the same checkout at
the same time. The finish helper releases the lock. For parallel work, create a
separate git worktree instead of sharing one working tree.

Use `scripts/agent_lock_status.sh --repo /path/to/project` or
`scripts/agent_lock_status.sh --all` when a start is blocked and you need to see
which checkout is locked.

If `--all` shows `orphaned: yes`, the recorded repo path no longer exists.
Clean only those orphaned locks explicitly:

```bash
scripts/agent_lock_status.sh --all --clean-orphaned
```

If the next step is parallel write-capable work, prepare a separate checkout:

```bash
scripts/agent_worktree.sh \
  --repo /path/to/project \
  --branch codex/focused-task \
  --project <project-slug> \
  --start \
  --query "<current focus>" \
  --review
```

For single-project starts, it also prints a short "Start Decision". This
confirms whether scoped work is ready, whether a concrete focus is missing, and
whether review context should be loaded before risky changes.

For a single-project start, the helper now prefers the compiled memory:

```bash
agent-hub compile --project <project-slug>
```

Compiled memory is the token-efficient entrypoint for agents. It turns reviewed
Hub memory into a short working brief: current state, decisions, risks, open
questions, important relations, useful reports, and suggested next steps. Use
`agent-hub context` only when a specific focus query needs extra retrieval.

For a concrete task, use `prepare` to turn reviewed memory into a task-specific
read-only context pack:

```bash
agent-hub prepare --project <project-slug> --task "<current task>"
```

The Markdown output starts with the same **ADH Context Loaded** receipt, so a
human can see what context is being handed to a chatbot or agent before work
starts.

`agent-hub prepare --format json` is a versioned, read-only, point-in-time
context-pack snapshot for external tools. It is not a live ADH connection and
does not sync or write back. Drafts in the pack are pending-review signals, not
reviewed memory. Consumers should check `context_pack_version` before assuming
they understand the JSON format.

`prepare` includes the task goal, reviewed project state, relevant decisions,
constraints, risks, open questions, allowed actions, actions that require human
approval, suggested checks, and a Context Trail with included source counts and
item IDs, status, task scores, and inclusion reasons. It does not write memory
or promote Signal Inbox content. `--task` ranks facts, decisions, and reports
with deterministic PostgreSQL full-text search, then fills with recent reviewed
context. Active risks and open questions remain on a safety floor and are not
filtered out by task text.

The JSON field name `verified_project_state` is retained as a version-1
contract key. It means reviewed project-state facts from ADH, not a guarantee
that the outside world has been independently verified.

`prepare` also reports Known Gaps. This makes the context pack more honest: the
agent sees stale included items, old unanswered questions, empty memory types,
task areas with no reviewed match, and draft counts waiting for review. The
stale threshold is visible in the output and defaults to 42 days:

```bash
agent-hub prepare --project <project-slug> --task "<current task>" --stale-after-days 42
```

Stale is only a label in the output. It does not demote a reviewed item, change
status, trigger re-review, or write anything to PostgreSQL.

Useful compile variants:

```bash
agent-hub compile --project <project-slug> --since 24h
agent-hub compile --project <project-slug> --with-receipt-status --max-chars 4000
```

The lower-level project context helper remains available:

```bash
scripts/project_context.sh --project <project-slug>
```

To include the latest working activity in the same pre-work read:

```bash
scripts/project_context.sh --project <project-slug> --daily
```

For a full active-project orientation:

```bash
scripts/project_context.sh --all-projects
```

Domain shortcuts may exist for common working sets:

```bash
scripts/project_context.sh --all-websites
```

The helper runs the operational preflight first. It requires the durable local
database to be running, a fresh verified local backup to exist, `agent-hub
check` to have no errors, and the relevant project brief to be readable. A
configured remote backup target is checked and reported, but remote parity is
strict only when `AGENT_HUB_REQUIRE_REMOTE_BACKUP=1` or
`scripts/db_backup_health.sh --require-remote` is used.

For single-project starts, `scripts/agent_start.sh` permits a narrower
read-only fallback: if the current agent runtime cannot inspect Docker or the
local container, but `DATABASE_URL` is reachable and `agent-hub check` passes,
the start may still load context. Finish, writeback, export, and backup paths
stay on the stricter preflight because they can create durable artifacts.

If preflight reports that the central Hub is offline, do not guess at the
failure. Run the local doctor first:

```bash
agent-hub doctor
```

When the doctor reports a known stale Postgres lock-file problem, use the
guarded recovery script:

```bash
scripts/db_recover.sh --apply
```

The recovery path snapshots the Docker volume before changes, recreates only
the container, and never removes volumes or writes Hub memory.

For focused work, use a context pack after the brief:

```bash
agent-hub context --project <project-slug> --query "<current work focus>"
```

See `docs/operator/codex-memory-policy.md` for the reusable Codex/Hermes policy and
`docs/repo-agent-memory-template.md` for per-repository agent instructions.

Projects may also define a repo-local project skill manifest. This manifest is
a small map of working rules: required context files, recommended skill packs,
quality gates, and non-goals. It points agents toward the right execution help
without copying long technical rules into Hub memory.

See `docs/project-skill-manifest.md`.

## During Work

Keep project boundaries explicit. Do not let facts, decisions, risks, or open
questions drift from one project into another.

Do not store secrets, FTP credentials, raw invoice data, private customer data,
or deployment passwords in the Hub.

For automation, keep the levels explicit: automatic checks and projections are
safe by default, triage output is only suggested, Hub writeback must be reviewed,
and operational actions need explicit human approval. See
`automation-boundaries.md`.

Before adding a new workflow layer, ask whether it makes daily agent work
simpler, more reliable, or easier to review. If it only adds another place to
repeat rules, keep it out of the Hub.

## Signal Inbox And Triage

Not every interesting input should be written into reviewed memory.

Use a Signal Inbox outside PostgreSQL for:

- X or Twitter research
- Gmail observations
- Hermes or Codex notes
- screenshots, links, and outside findings

The Signal Inbox is intentionally upstream from the Hub:

- it is unreviewed
- it may be useful later
- it is not durable project truth yet

Triage sits between the Signal Inbox and the Hub. The normal outcomes are:

- ignore
- keep in wiki
- open question
- fact candidate
- decision candidate
- risk candidate
- skill candidate
- project note
- needs human review

Do not auto-promote Signal Inbox content into PostgreSQL. Review first, then
write back only the durable result.

To create a minimal local root:

```bash
scripts/init_signal_inbox.sh --path /path/to/wiki/inbox/signals
```

To intentionally scaffold a first source file:

```bash
scripts/init_signal_inbox.sh --path /path/to/wiki/inbox/signals --scaffold-source x-research
```

See `docs/signal-inbox.md`.

## Agent Run Loop

The preferred unit of work is one reviewed run: one project, one focus, one
handoff. Agent starts and finishes are intentionally not hidden write paths.
Use the existing audit trail to inspect recent actions:

```bash
agent-hub actions --project <project-slug> --since 7d
```

If stronger run tracking becomes necessary, design it as a small coordination
layer. Do not turn it into a chat transcript store. See
`docs/agent-run-loop.md`.

## Memory Quality Rules

Write fewer memories, but make them useful:

- Every memory must be attached to the correct project.
- Every memory must be reviewed, non-sensitive, and useful for future work.
- Facts need `--source` and an appropriate `--confidence`.
- Decisions should include `--rationale`.
- Risks should include impact or mitigation when known.
- Open questions should be real clarification needs, not a task list.
- Reports are for compressed daily summaries, handoffs, audits, or review notes.

Useful report and retrieval commands:

```bash
agent-hub daily --project <project-slug> --since 24h
agent-hub daily --project <project-slug> --since 24h --write-report
agent-hub handoff --project <project-slug> --since 7d
agent-hub review --project <project-slug>
agent-hub search --project <project-slug> --query "<topic>"
agent-hub compile --project <project-slug>
agent-hub quality --project <project-slug>
```

## Human Wiki Projection

`agent-hub export` writes the human-readable Markdown projection. It keeps
Human Notes stable, creates `Compiled/Agent Data Hub.md` as a central start
page, creates compact project overview files under `Compiled/`, and turns
curated Hub relations into Obsidian Wikilinks in `Linked Memory` sections.

Obsidian is for reading, review, graph navigation, and human notes. PostgreSQL
remains the binding data source; structured changes flow back only through the
controlled import or writeback paths.

## After Work

Run the finish helper to produce a final daily summary and handoff:

```bash
scripts/agent_finish.sh --project <project-slug>
```

The finish helper also prints recent audited agent actions for the same project
and time window. This makes the end of a run checkable without turning
`agent_start.sh` or `agent_finish.sh` into hidden write paths.

It also prints a short "Next Best Step" block. Treat it as guidance, not
automation: store no memory when nothing durable changed, dry-run 1-3 reviewed
writebacks when useful memory emerged, and export/backup after important writes.

For stronger closure, include review, export, and backup:

```bash
scripts/agent_finish.sh --project <project-slug> --review --export --backup
```

The finish helper prints a memory triage before any manual writeback. It should
help the agent decide whether the outcome is a fact, decision, risk, open
question, report, or just temporary working noise that should not be stored.

If useful information does not fit any existing Hub category, do not force it
into a fact, decision, risk, or report. Record a small structure question
instead:

```bash
scripts/project_schema_friction.sh \
  --project <project-slug> \
  --observed "The agent found a recurring project rule that is not memory." \
  --why "It is not a fact or decision; it may belong in AGENTS.md or a skill manifest." \
  --suggestion "review as project-skill-manifest candidate" \
  --dry-run
```

This stores, after review, an `open_question` marked with `schema_friction`
metadata. It does not create a new database category and it does not let agents
revise the Hub schema automatically.

When another channel claims that it wrote curated memory and exported it, verify
the claim with a receipt:

```bash
scripts/memory_receipt.sh --project <project-slug> --type report --since 24h
```

For direct CLI use:

```bash
agent-hub receipt --project <project-slug> --type report --since 24h
```

The receipt checks recent Hub rows and the matching Obsidian Markdown files. It
is meant as a lightweight audit trail between channels and agents.

Write back only reviewed, non-sensitive memory:

```bash
scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "Reviewed project memory goes here." \
  --source "/path/to/non-sensitive/source-or-note" \
  --confidence 0.9
```

For decisions:

```bash
scripts/project_remember.sh \
  --project <project-slug> \
  --type decision \
  --text "Use the approved implementation path." \
  --rationale "This keeps the current production state stable."
```

For risks:

```bash
scripts/project_remember.sh \
  --project <project-slug> \
  --type risk \
  --text "The next migration step could affect production state." \
  --severity high \
  --mitigation "Use staging, review, backup, and explicit approval first."
```

Use dry-run when unsure:

```bash
scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "dry-run review note" \
  --dry-run
```

`project_remember.sh` never creates projects. If a project is missing, add it
through reviewed seed or migration changes.

For an existing open question that is now resolved, use the narrow update path:

```bash
scripts/project_answer_question.sh \
  --project <project-slug> \
  --question-id <open-question-uuid> \
  --answer "Reviewed answer or closure note." \
  --source "/path/to/non-sensitive/review-note" \
  --dry-run
```

Then rerun without `--dry-run` to mark the row as `answered` or `closed`.

When the new memory clearly supports, mitigates, answers, or references an
existing object, the wrapper can write the memory and relation together:

```bash
scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "review note" \
  --relate-to decision:<decision-id> \
  --relation supports
```

The relation is created only after the memory write succeeds. In `--dry-run`
mode the wrapper shows the planned relation without writing anything.

## Relating Memory

Use relations when a reviewed memory should become part of the project graph:

```bash
agent-hub relate \
  --project <project-slug> \
  --source-type fact \
  --source-id <fact-id> \
  --relation supports \
  --target-type decision \
  --target-id <decision-id>
```

Relations are explicit CLI actions, not automatic guesses. Prefer them for
useful review links: facts supporting decisions, decisions mitigating risks,
reports referencing facts, or decisions answering open questions.

## Domain Profile: Websites

Website project sets can be loaded when projects are tagged with
`metadata.project_type=website`:

```bash
scripts/project_context.sh --all-websites
```

Website boundaries should live in reviewed project memory, not in this public
workflow document. Keep each website in its own Hub project and do not inherit
positioning, hosting state, or deployment assumptions across projects without a
separate reviewed decision.

For protected hosting, deployment, FTP, or production access, use the separate
handoff rule in `docs/operator/sensitive-access-handoffs.md`.
