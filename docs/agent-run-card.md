# Agent Run Card

Use this card when starting substantial work with Agent Data Hub.

Keep the three parts separate:

- **Gedächtnis**: what the Hub stores as reviewed project knowledge.
- **Arbeitskontext**: what the start step assembles for this run.
- **Arbeitsregeln**: how the repo says work should be done.

## 1. Start

```bash
scripts/agent_start.sh --project <project-slug> --query "<current focus>" --review
```

Read the compiled memory, focused context, review, working contract, and Start
Decision before changing anything meaningful. Together they form the
Arbeitskontext for this run.

For single-project work this first checks that the current working directory
belongs to the selected project. If the project and directory do not match, stop
and switch to the correct Codex project or repo.

For single-project work this also creates a local working-tree run lock. If the
lock blocks, another agent is already using this checkout. Finish that run or
create a separate git worktree for parallel work.

To inspect locks without changing them:

```bash
scripts/agent_lock_status.sh --repo /path/to/project
scripts/agent_lock_status.sh --all
```

If a lock is marked `orphaned: yes`, its recorded repo path no longer exists.
Clean only those orphaned locks explicitly:

```bash
scripts/agent_lock_status.sh --all --clean-orphaned
```

For parallel write-capable work, create a separate worktree first:

```bash
scripts/agent_worktree.sh \
  --repo /path/to/project \
  --branch codex/focused-task \
  --project <project-slug> \
  --start \
  --query "<current focus>" \
  --review
```

## 2. Work

- Stay inside the selected project context.
- Follow the Arbeitsregeln from `AGENTS.md`, repo documents, and relevant skills.
- Use one write-capable agent per working tree.
- Do not transfer assumptions from another project.
- Do not store secrets, credentials, private customer data, or raw invoice data.
- Treat uncertainty as an open question, not as a fact.
- Treat triage output as a suggestion until it is reviewed.
- Prefer one focused task and one clean outcome.

## 3. Finish

```bash
scripts/agent_finish.sh --project <project-slug> --review
```

Read the handoff, memory triage, Next Best Step, and recent agent actions.

## 4. Remember Only If Useful

If nothing durable changed, store no memory.

If useful memory emerged, dry-run first:

```bash
scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "<reviewed fact>" \
  --source "<source>" \
  --confidence 0.9 \
  --dry-run
```

If an existing open question is now resolved, dry-run the reviewed answer:

```bash
scripts/project_answer_question.sh \
  --project <project-slug> \
  --question-id <open-question-uuid> \
  --answer "Reviewed answer or closure note." \
  --source "<source>" \
  --dry-run
```

Store at most 1-3 reviewed, non-sensitive memories per run.

## 5. Close Strongly When Memory Was Written

```bash
scripts/agent_finish.sh --project <project-slug> --review --export --backup
scripts/memory_receipt.sh --project <project-slug> --since 24h
```

Use receipts when another channel or agent claims that memory was written and
exported. The `--backup` path creates a dump and verifies the latest timestamped
local backup before treating the finish as complete.
