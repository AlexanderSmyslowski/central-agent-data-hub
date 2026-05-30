# Active Agent Projects

This is the lightweight project map for Codex/Hermes work. It answers one
question before a new agent run starts: which project context, repository, and
start contract should be used?

The Central Agent Data Hub remains the shared memory layer. Each project keeps
its own repository instructions and project-specific working files.

## Current Projects

| Project | Hub slug | Type | Local path | Start contract |
| --- | --- | --- | --- | --- |
| Catering Agents Platform | `catering-agents-platform` | product | `/Users/alexandersmyslowski/Projects/catering-agents-platform` | `/Users/alexandersmyslowski/Projects/catering-agents-platform/AGENTS.md` |
| Agent Data Hub | `central-agent-data-hub` | ops | `/Users/alexandersmyslowski/Projects/central-agent-data-hub` | `/Users/alexandersmyslowski/Projects/central-agent-data-hub/AGENTS.md` |
| Zeiterfassung Tool | `zeiterfassung-tool` | product | `/Users/alexandersmyslowski/Projects/zeiterfassung-tool` | `/Users/alexandersmyslowski/Projects/zeiterfassung-tool/CODEX-START-PROMPT.md` |
| CommCats | `commcats-de` | website | `/Users/alexandersmyslowski/Documents/commcats.de` | `/Users/alexandersmyslowski/Documents/commcats.de/CODEX-START-PROMPT.md` |
| THE ONE | `the-one-catering` | website | `/Users/alexandersmyslowski/Documents/the-one-catering` | `/Users/alexandersmyslowski/Documents/the-one-catering/CODEX-START-PROMPT.md` |
| L'Amour | `lamour` | planned website | not assigned yet | Hub brief only |

## Standard Start

For substantial work, start inside the correct repository and run:

```bash
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/agent_start.sh \
  --project <hub-slug> \
  --query "<current focus>" \
  --review
```

After substantial work, finish with:

```bash
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/agent_finish.sh \
  --project <hub-slug> \
  --review
```

Only store reviewed, non-sensitive memory through:

```bash
/Users/alexandersmyslowski/Projects/central-agent-data-hub/scripts/project_remember.sh
```

## Project Boundaries

- Use the repository path and Hub slug from the table; do not guess.
- Do not copy assumptions from one project into another project.
- Treat cross-project comparisons as explicit analysis, not inherited facts.
- Do not store passwords, tokens, FTP credentials, private customer data, raw
  invoice data, deployment secrets, or unreviewed claims.

## Notes

- CommCats and THE ONE are separate website contexts. CommCats is already a
  live static Alfahosting site. THE ONE remains live on Framer while static
  migration work happens in its separate repository.
- The Catering Agents Platform is not a website side project. It is the larger
  product/platform project for agentic catering operations. Keep it in its own
  repo and Hub context.
- The Zeiterfassung Tool is a separate product project for single-tenant time
  tracking. Its current focus is pilot hardening and operational readiness, not
  platform expansion or multi-tenancy.
- L'Amour has a Hub project but no active local repo path yet. Register one
  before substantial implementation work starts.
