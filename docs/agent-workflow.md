# Agentic Work Workflow

This workflow is the working contract for Codex/Hermes project work that uses
the Central Agent Data Hub.

The Hub is not a website-only memory. It is the operational project memory for
agentic work across domains: implementation, operations, research, business
decisions, open questions, risks, reports, and handoffs.

## Before Work

Run the project context helper before changing or deciding anything meaningful:

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

## During Work

Keep project boundaries explicit. Do not let facts, decisions, risks, or open
questions drift from one project into another.

Do not store secrets, FTP credentials, raw invoice data, private customer data,
or deployment passwords in the Hub.

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
```

## After Work

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

- `commcats-de`: live static Alfahosting site; work from the local static source and upload only after approval.
- `the-one-catering`: live Framer site; keep it stable while SEO/AI work and protected static migration preparation happen.
- `lamour`: planned future web presence; do not inherit positioning from CommCats or THE ONE without a separate decision.
