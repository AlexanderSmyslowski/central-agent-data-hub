# Active Agent Projects

This is a template for an operator-local project map. It answers one question
before a new agent run starts: which project context, repository, and start
contract should be used?

The Central Agent Data Hub remains the shared memory layer. Each project keeps
its own repository instructions and project-specific working files.

Do not put a real private project map in this public repository. Keep it in a
local operator note, password manager note, private wiki, or machine-local file.

## Example Projects

| Project | Hub slug | Type | Local path | Start contract |
| --- | --- | --- | --- | --- |
| Demo Product | `demo-product` | product | `/path/to/demo-product` | `/path/to/demo-product/AGENTS.md` |
| Agent Data Hub | `central-agent-data-hub` | ops | `/path/to/central-agent-data-hub` | `/path/to/central-agent-data-hub/AGENTS.md` |
| Demo Website | `demo-website` | website | `/path/to/demo-website` | `/path/to/demo-website/AGENTS.md` |
| Future Website | `future-website` | planned website | not assigned yet | Hub brief only |

## Standard Start

For substantial work, start inside the correct repository and run:

```bash
/path/to/central-agent-data-hub/scripts/agent_start.sh \
  --project <hub-slug> \
  --query "<current focus>" \
  --review
```

After substantial work, finish with:

```bash
/path/to/central-agent-data-hub/scripts/agent_finish.sh \
  --project <hub-slug> \
  --review
```

Only store reviewed, non-sensitive memory through:

```bash
/path/to/central-agent-data-hub/scripts/project_remember.sh
```

## Project Boundaries

- Use the repository path and Hub slug from the table; do not guess.
- Do not copy assumptions from one project into another project.
- Treat cross-project comparisons as explicit analysis, not inherited facts.
- Do not store passwords, tokens, FTP credentials, private customer data, raw
  invoice data, deployment secrets, or unreviewed claims.

## Notes

- Separate website contexts should stay separate even when they share a domain
  category or similar workflow.
- Live-upload access is not Hub memory. If a new agent session needs protected
  hosting access, request a human secure handoff outside the Hub, Git, and
  Obsidian. The reusable rule lives in
  `docs/operator/sensitive-access-handoffs.md`.
- Product projects and website projects should not inherit positioning,
  deployment state, or risks from each other without a reviewed decision.
- Planned projects can exist in the Hub before a local repo path exists. Register
  a path before substantial implementation work starts.
