# Seed Data

This directory contains two different kinds of local seed data.

## Public Demo

`demo.sql` is the neutral public demo dataset. It is the only seed file used by:

```bash
scripts/db_start_public_demo.sh
scripts/first_run_demo.sh
```

It should stay anonymous, small, and safe for outside developers.

## Maintainer Local Ops

`business_sites.sql` and `agentic_projects.sql` are maintainer-local operator
seeds. They describe the maintainer's own local workset and may contain local
paths, project slugs, and non-secret operational context.

They are not part of the public first-run path and are loaded only by:

```bash
scripts/db_start.sh
```

Do not add secrets, credentials, private customer data, raw invoices, or raw
deployment logs to any seed file.
