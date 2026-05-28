# Safe Import Allowlist

`agent-hub import` imports curated Obsidian Markdown notes into Postgres. It is intentionally allowlist-based and is not a free two-way sync.

By default, import writes to Postgres. Use `--dry-run` to validate and preview without writes:

```bash
agent-hub import --path /path/to/notes --allowlist import_allowlist.yml --dry-run
agent-hub import --path /path/to/notes --allowlist import_allowlist.yml
```

Duplicate handling defaults to `skip` and can be changed explicitly:

```bash
agent-hub import --path /path/to/notes --on-duplicate skip
agent-hub import --path /path/to/notes --on-duplicate error
agent-hub import --path /path/to/notes --on-duplicate update
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

Every curated note should also include a stable `import_key`. If omitted, `agent-hub` derives a path-based import key from project, type, and the relative file path. `db_id` may be used to target one existing row directly.

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

## Identity, Dedupe, and Sync

Successful imports store source path, import key, content hash, data hash, and last import timestamp in `metadata.agent_hub_import`. This enables safe duplicate detection without a new migration.

`agent-hub sync --plan` classifies each allowlisted note as:

- `create`
- `update`
- `skip`
- `conflict`
- `reject`

`agent-hub sync --apply` writes only when the plan has no `conflict` or `reject` entries. Each create/update writes `agent_actions`, and each apply attempt writes a `sync_events` summary. `sync --watch` is reserved for later and intentionally returns an error today.

## Ownership Rules

Postgres owns IDs, audit rows, relations, timestamps, and export metadata. Obsidian may edit only the allowlisted curated memory fields. Human Notes remain separate and are never merged automatically into structured fields.
