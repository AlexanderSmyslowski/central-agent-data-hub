# Contributing

Thank you for taking a look at Agent Data Hub.

This project is intentionally small and opinionated. The best contributions are
the ones that make the system clearer, safer, or easier to review without
making it noisier.

## Before Opening A Change

- Read [README.md](README.md).
- Prefer the public demo path first:
  `scripts/db_start_public_demo.sh`
- Keep the distinction clear between:
  - reviewed memory
  - working context
  - working rules

## What Makes A Good Contribution

- Small, focused fixes
- Better public docs
- Safer operational checks
- Simpler setup
- Better tests around existing behavior
- Clearer human review surfaces

## What To Avoid

- Raw chat-memory features
- Secret handling inside the Hub
- Big speculative abstractions
- Large UI/product expansions without a real workflow need
- Schema changes that do not clearly improve daily use

## Development Checks

Run these before proposing a change:

```bash
git diff --check
bash -n scripts/*.sh
.venv/bin/python -m compileall agent_hub
.venv/bin/python -m pytest -q
```

For public-path changes, also run:

```bash
scripts/db_start_public_demo.sh
scripts/smoke_public_demo.sh
```

## Contribution Style

- Keep patches narrow.
- Preserve existing command behavior unless the change is deliberate and tested.
- Prefer plain language in user-facing docs.
- Do not add private data, secrets, or local access details to docs, seeds, or tests.

## Pull Request Notes

Please explain:

- what changed
- why it improves the project
- how you verified it
- whether it affects the public demo path, the maintainer ops path, or both
