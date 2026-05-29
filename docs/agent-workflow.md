# Agent Website Workflow

This workflow is the working contract for Codex/Hermes website tasks that use the
Central Agent Data Hub.

## Before Work

Run the project context helper before changing a website project:

```bash
scripts/project_context.sh --project commcats-de
scripts/project_context.sh --project the-one-catering
scripts/project_context.sh --project lamour
```

For a cross-site orientation:

```bash
scripts/project_context.sh --all-websites
```

The helper runs the operational preflight first. It requires the durable local
database to be running, a verified local backup to exist, `agent-hub check` to
have no errors, and the relevant project brief to be readable.

## During Work

Keep project boundaries explicit:

- `commcats-de`: live static Alfahosting site; work from the local static source and upload only after approval.
- `the-one-catering`: live Framer site; keep it stable while SEO/AI work and protected static migration preparation happen.
- `lamour`: planned future web presence; do not inherit positioning from CommCats or THE ONE without a separate decision.

Do not store secrets, FTP credentials, raw invoice data, private customer data,
or deployment passwords in the Hub.

## After Work

Write back only reviewed, non-sensitive memory:

```bash
scripts/project_remember.sh \
  --project commcats-de \
  --type fact \
  --text "commcats.de has a reviewed static-source change ready for approval." \
  --source "/path/to/non-sensitive/source-or-note" \
  --confidence 0.9
```

For decisions:

```bash
scripts/project_remember.sh \
  --project the-one-catering \
  --type decision \
  --text "Keep THE ONE live on Framer until the static prototype is approved." \
  --rationale "The visible live site must remain stable during migration prep."
```

For risks:

```bash
scripts/project_remember.sh \
  --project the-one-catering \
  --type risk \
  --text "Static staging could be indexed if protection is incomplete." \
  --severity high \
  --mitigation "Use password protection, noindex, and no public links."
```

Use dry-run when unsure:

```bash
scripts/project_remember.sh \
  --project commcats-de \
  --type fact \
  --text "Reviewed memory candidate." \
  --dry-run
```

`project_remember.sh` never creates projects. If a project is missing, add it
through reviewed seed or migration changes.
