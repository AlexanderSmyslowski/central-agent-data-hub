# Seed Data

This directory contains the neutral public demo seed data.

## Public Demo

`demo.sql` is the neutral public demo dataset. It is the only seed file used by:

```bash
scripts/db_start_public_demo.sh
scripts/first_run_demo.sh
```

It should stay anonymous, small, and safe for outside developers.

## Local Operator Data

Maintainer- or operator-specific seed files are not shipped in this public
repository. Keep private local workset seeds outside Git and pass them
explicitly when needed:

```bash
scripts/db_start.sh --seed-file /path/to/local-operator-seed.sql
```

Do not add secrets, credentials, private customer data, raw invoices, or raw
deployment logs to any seed file.
