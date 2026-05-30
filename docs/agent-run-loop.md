# Agent Run Loop

Agent Data Hub should support better self-management without becoming a raw
thread log. The unit of improvement is a reviewed work run: one project, one
focus, one handoff, and only the useful residue saved as memory.

## Current Mechanism

Use the existing workflow:

```bash
scripts/agent_start.sh --project <project-slug> --query "<focus>" --review
scripts/agent_finish.sh --project <project-slug> --review --export --backup
```

To inspect recent audited agent writes and system actions:

```bash
agent-hub actions --project <project-slug> --since 7d
```

This reads the existing `agent_actions` table. It does not create a new session
table and it does not make `agent_start.sh` write to the database.

## Design Rules

- Do not store raw chat logs.
- Do not make start/finish wrappers write by default.
- Keep work runs project-bound.
- Record durable outcomes through reports, facts, decisions, risks, questions,
  relations, and receipts.
- Add schema only when the existing audit trail is too weak for daily use.

## Future Option

If daily work shows that the existing audit trail is not enough, add a small
`work_sessions` table later. It should track only:

- project id
- focus
- start time
- finish time
- status
- optional branch or worktree path
- links to resulting reports, memories, and receipts

That table should not contain chat transcripts, secrets, or implementation
noise. Its purpose would be coordination and review, not memory hoarding.
