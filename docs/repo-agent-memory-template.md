# Agent Memory

Project slug: `<project-slug>`

Central Agent Data Hub:

```txt
/path/to/central-agent-data-hub
```

Run card:

```txt
/path/to/central-agent-data-hub/docs/agent-run-card.md
```

Use the Run Card rhythm for substantial work: start with Hub context, work inside
one project boundary, finish with review, and write back only reviewed,
non-sensitive memory.

If the work later requires protected hosting, deployment, FTP, or production
access, do not expect that access to live in the Hub, Git, or Obsidian. Ask
the Human Lead for a secure handoff outside those systems, and store back only
the reviewed, non-sensitive result.

## Before Work

Load operational readiness, project memory, daily activity, and focused context:

```bash
/path/to/central-agent-data-hub/scripts/agent_start.sh \
  --project <project-slug> \
  --query "<current work focus>" \
  --review
```

If there is no focused query yet:

```bash
/path/to/central-agent-data-hub/scripts/agent_start.sh \
  --project <project-slug>
```

## After Work

Produce a finish summary and handoff:

```bash
/path/to/central-agent-data-hub/scripts/agent_finish.sh \
  --project <project-slug> \
  --review
```

For a reviewed memory candidate, dry-run first:

```bash
/path/to/central-agent-data-hub/scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "non-sensitive source" \
  --dry-run
```

Then write only if reviewed and non-sensitive:

```bash
/path/to/central-agent-data-hub/scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "non-sensitive source"
```

## Optional Relations

When the new memory clearly supports, answers, mitigates, references, or
depends on an existing Hub object:

```bash
/path/to/central-agent-data-hub/scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "non-sensitive source" \
  --relate-to decision:<decision-id> \
  --relation supports
```

## Never Store

- passwords
- API keys or tokens
- FTP credentials
- private customer data
- raw invoice data
- deployment secrets
- unreviewed claims
- assumptions copied from another project

## Memory Quality

- Facts need `--source`.
- Decisions should include `--rationale`.
- Risks should include impact or mitigation.
- Open questions should be real unresolved questions.
- Reports should summarize meaningful work, handoffs, audits, or reviews.
