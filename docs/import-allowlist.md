# Safe Import Allowlist

`agent-hub import` imports curated Obsidian Markdown notes into Postgres. It is intentionally allowlist-based and is not a free two-way sync.

By default, import writes to Postgres. Use `--dry-run` to validate and preview without writes:

```bash
agent-hub import --path /path/to/notes --allowlist import_allowlist.yml --dry-run
agent-hub import --path /path/to/notes --allowlist import_allowlist.yml
```

## Allowlist Shape

Copy `import_allowlist.example.yml` to `import_allowlist.yml` and adjust it locally. The allowlist must define:

- project slugs that may receive imported content
- source directories or files that may be read
- accepted frontmatter `type` values
- fields that may be imported for each type

Relative roots are resolved relative to the allowlist file. Import paths are resolved and must stay inside one of the listed roots.

## Allowed Types

- `fact`
- `decision`
- `open_question`
- `risk`
- `report`

Documents are not imported in V1. They may be considered later, after content hash and path ownership rules are explicit.

## Frontmatter Requirements

Every imported note must start with YAML frontmatter and include:

- `type`
- `project` or `project_slug`
- required fields for its type

Required fields:

- `fact`: `statement`, `source`
- `decision`: `decision`
- `open_question`: `question`
- `risk`: `title`
- `report`: `title`; `body` may come from frontmatter or Markdown body

## Rejection Rules

Import rejects or skips content that includes:

- passwords, API keys, tokens, FTP credentials, or private keys
- raw invoice data
- private customer data
- unknown project slugs
- paths outside the allowlisted import roots
- unsupported frontmatter types
- missing source/provenance for facts

## Write Behavior

V1 intentionally does not update or deduplicate existing rows. Every successful import creates a new memory row and an `agent_actions` audit row with `action='import_obsidian_note'`.
