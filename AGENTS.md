<!-- CENTRAL-AGENT-DATA-HUB:START -->

## Central Agent Data Hub

Project slug: `central-agent-data-hub`

Use the shared Hub before and after substantial project work:

```bash
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/agent_start.sh --project central-agent-data-hub --query "<current focus>"
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/agent_start.sh --project central-agent-data-hub --query "<current focus>" --review
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/agent_finish.sh --project central-agent-data-hub --review
```

For reviewed, non-sensitive memory candidates, dry-run first:

```bash
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/project_remember.sh \
  --project central-agent-data-hub \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "non-sensitive source" \
  --dry-run
```

Then write only curated memory:

```bash
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/project_remember.sh \
  --project central-agent-data-hub \
  --type fact \
  --text "Reviewed memory candidate." \
  --source "non-sensitive source"
```

Never store passwords, API keys, tokens, FTP credentials, private customer data,
raw invoice data, deployment secrets, unreviewed claims, or assumptions copied
from another project.

<!-- CENTRAL-AGENT-DATA-HUB:END -->
