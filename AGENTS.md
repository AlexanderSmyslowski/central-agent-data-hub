<!-- CENTRAL-AGENT-DATA-HUB:START -->

## Central Agent Data Hub

Project slug: `central-agent-data-hub`

Run Card:
`docs/agent-run-card.md`

Use the Run Card rhythm for substantial work: start with Hub context, work inside
one project boundary, finish with review, and write back only reviewed,
non-sensitive memory.

Use one start command before substantial project work. Keep its printed run_id
and pass that caller-owned ID to finish. Explicitly unlocked runs use --no-lock
at both ends:

```bash
scripts/agent_start.sh --project central-agent-data-hub --query "<current focus>"
scripts/agent_start.sh --project central-agent-data-hub --query "<current focus>" --review
scripts/agent_finish.sh --project central-agent-data-hub --review --run-id <id-from-start>
```

For reviewed, non-sensitive memory candidates, dry-run first:

```bash
scripts/project_remember.sh \
  --project central-agent-data-hub \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "non-sensitive source" \
  --dry-run
```

Then write only curated memory:

```bash
scripts/project_remember.sh \
  --project central-agent-data-hub \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "non-sensitive source"
```

Never store passwords, API keys, tokens, FTP credentials, private customer data,
raw invoice data, deployment secrets, unreviewed claims, or assumptions copied
from another project.

<!-- CENTRAL-AGENT-DATA-HUB:END -->
