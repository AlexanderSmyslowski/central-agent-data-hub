# Codex Memory Policy

This policy makes the Central Agent Data Hub the default project memory for
Codex/Hermes work.

## Core Rule

Before substantial project work:

```bash
/path/to/central-agent-data-hub/scripts/agent_start.sh --project <project-slug> --query "<current focus>"
```

After substantial project work:

```bash
/path/to/central-agent-data-hub/scripts/agent_finish.sh --project <project-slug>
```

Write back only reviewed, non-sensitive memory:

```bash
/path/to/central-agent-data-hub/scripts/project_remember.sh \
  --project <project-slug> \
  --type fact \
  --text "Reviewed memory goes here." \
  --source "non-sensitive source"
```

## Hard Boundaries

Never store these in the Hub:

- passwords
- API keys or tokens
- FTP credentials
- private customer data
- raw invoice data
- deployment secrets
- unreviewed claims
- cross-project assumptions

## Quality Gates

- Facts need a source and confidence.
- Decisions should include rationale.
- Risks should include impact or mitigation when known.
- Open questions should be real clarification needs, not task lists.
- Reports are for daily summaries, handoffs, audits, and review notes.
- Relations should be explicit and useful for future review.
- If useful information does not fit any category, record a schema-friction
  open question instead of inventing a new category or forcing it into the wrong
  one.

## Project Boundaries

Project context must stay explicit. A local website domain profile might look
like this:

- `demo-website`: live static website.
- `demo-catering`: live hosted website; only SEO/AI optimization and migration preparation.
- `future-website`: separate planned future web presence.

Do not transfer facts, decisions, risks, or assumptions between projects unless
a reviewed memory or relation explicitly says so.

## Practical Enforcement Layers

1. Put the project slug and start/finish commands into each important repo's
   `AGENTS.md` or equivalent local agent instruction file.
2. Start work with `scripts/agent_start.sh`.
3. Finish work with `scripts/agent_finish.sh`.
4. Use `scripts/project_remember.sh --dry-run` before uncertain writeback.
5. Prefer fewer, higher-quality memories over broad logging.

The goal is not automatic memory spam. The goal is a daily workflow where each
agent begins from the same reviewed context and leaves behind only useful,
traceable memory.
