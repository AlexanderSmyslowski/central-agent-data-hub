# Project Skill Manifest

The project skill manifest is an optional repo-local orientation file for agent
work. It tells Codex/Hermes which local documents, skill packs, quality gates,
and non-goals matter before work starts.

It is deliberately not a new Hub subsystem. The Hub remains the verified memory
and governance layer; `AGENTS.md` remains the repo-local working contract; skill
packs remain execution help; Obsidian remains review and projection.

## Why This Exists

Agents are more reliable when they know which project-specific instructions and
domain skills apply. The manifest gives them that map without copying long
technical rules into Postgres.

Use it when a project has more than one important local instruction file or when
domain-specific skills are easy to forget.

## Recommended Location

```text
.agent-data-hub/project-skill-manifest.yml
```

The path is intentionally repo-local. A future Hub project may reference it via
`projects.metadata.skill_manifest`, but the manifest itself should stay close to
the code and project documents it describes.

## What Belongs Here

- Short lists of required repo-local context files.
- Recommended or required skill packs by stable name.
- Quality gates to check before finish or handoff.
- Explicit non-goals and scope boundaries.
- A brief statement of what belongs in Hub memory and what does not.

## What Does Not Belong Here

- Long technical rule texts copied from framework docs.
- Raw chat history, private notes, credentials, or customer data.
- Secrets, API keys, tokens, FTP credentials, raw invoice data, or deployment
  details.
- Project facts that should be stored as verified Hub memory.
- Automatically generated dependency or tool output.

## Example

See:

```text
/Users/alexandersmyslowski/Projects/central-agent-data-hub/docs/examples/project-skill-manifest.yml
```

## Relationship To The Hub

The manifest is a thin reference layer:

- Hub memory answers: what is true, decided, risky, open, or linked?
- `AGENTS.md` answers: how should agents behave in this repo?
- Skill packs answer: how should a domain task be executed well?
- The manifest answers: which of those things should an agent load first?

If a manifest entry becomes a durable project fact or decision, write that
curated statement to the Hub through `scripts/project_remember.sh`. Do not copy
the whole manifest into Hub memory.

## Architecture Rule

Before expanding this mechanism, ask:

- Does it reduce daily agent confusion?
- Does it remove another manual step?
- Does it keep the Hub smaller than the work it coordinates?
- Would a strong engineer consider the boundary clean?

If the answer is no, keep it as documentation.
