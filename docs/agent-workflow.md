# Agentic Work Workflow

This workflow is the working contract for Codex/Hermes project work that uses
the Central Agent Data Hub.

For the shortest copyable version, use `docs/agent-run-card.md`.

The Hub is not a website-only memory. It is the operational project memory for
agentic work across domains: implementation, operations, research, business
decisions, open questions, risks, reports, and handoffs.

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

The start helper prints the working contract after loading context: keep the
project boundary explicit, do not transfer assumptions between projects, do not
store sensitive data, and treat uncertainty as an open question.

For single-project work, the start helper also creates a local working-tree run
lock. This protects against two write-capable agents using the same checkout at
the same time. The finish helper releases the lock. For parallel work, create a
separate git worktree instead of sharing one working tree.

Use `scripts/agent_lock_status.sh --repo /path/to/project` or
`scripts/agent_lock_status.sh --all` when a start is blocked and you need to see
which checkout is locked.

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

Compiled memory is the token-efficient entrypoint for agents. It compresses the
current state, decisions, risks, open questions, important relations, useful
reports, and suggested next steps into one short working brief. Use
`agent-hub context` only when a specific focus query needs extra retrieval.

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
database to be running, a verified local backup to exist, `agent-hub check` to
have no errors, and the relevant project brief to be readable.

For focused work, use a context pack after the brief:

```bash
agent-hub context --project <project-slug> --query "<current work focus>"
```

See `docs/codex-memory-policy.md` for the reusable Codex/Hermes policy and
`docs/repo-agent-memory-template.md` for per-repository agent instructions.

Projects may also define a repo-local project skill manifest. This manifest is
a small map of required context files, recommended skill packs, quality gates,
and non-goals. It should point agents toward the right execution help without
copying long technical rules into Hub memory.

See `docs/project-skill-manifest.md`.

## During Work

Keep project boundaries explicit. Do not let facts, decisions, risks, or open
questions drift from one project into another.

Do not store secrets, FTP credentials, raw invoice data, private customer data,
or deployment passwords in the Hub.

Before adding a new workflow layer, ask whether it makes daily agent work
simpler, more reliable, or easier to review. If it only adds another place to
repeat rules, keep it out of the Hub.

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

The current website project set can be loaded with:

```bash
scripts/project_context.sh --all-websites
```

Website boundaries:

- `commcats-de`: live static Alfahosting site; work from the local static source and upload only after approval. If a live upload needs protected access, request a human secure handoff outside the Hub, Git, and Obsidian.
- `the-one-catering`: live Framer site; keep it stable while SEO/AI work and protected static migration preparation happen.
- `lamour`: planned future web presence; do not inherit positioning from CommCats or THE ONE without a separate decision.

For protected hosting, deployment, FTP, or production access, use the separate
handoff rule in `docs/sensitive-access-handoffs.md`.
