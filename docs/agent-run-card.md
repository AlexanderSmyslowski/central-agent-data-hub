# Agent Run Card

Use this card when starting substantial work with Agent Data Hub.

## 1. Start

```bash
scripts/agent_start.sh --project <project-slug> --query "<current focus>" --review
```

Read the compiled memory, focused context, review, working contract, and Start
Decision before changing anything meaningful.

For single-project work this also creates a local working-tree run lock. If the
lock blocks, another agent is already using this checkout. Finish that run or
create a separate git worktree for parallel work.

To inspect locks without changing them:

```bash
scripts/agent_lock_status.sh --repo /path/to/project
scripts/agent_lock_status.sh --all
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
- Use one write-capable agent per working tree.
- Do not transfer assumptions from another project.
- Do not store secrets, credentials, private customer data, or raw invoice data.
- Treat uncertainty as an open question, not as a fact.
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

Store at most 1-3 reviewed, non-sensitive memories per run.

## 5. Close Strongly When Memory Was Written

```bash
scripts/agent_finish.sh --project <project-slug> --review --export --backup
scripts/memory_receipt.sh --project <project-slug> --since 24h
```

Use receipts when another channel or agent claims that memory was written and
exported.
