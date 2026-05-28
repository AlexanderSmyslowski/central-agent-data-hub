# Safe Import Allowlist Direction

`agent-hub import` is intentionally not implemented yet. v0 may export to Obsidian and accept curated writes through `agent-hub remember`, but it must not freely ingest arbitrary vault files.

## Required Allowlist Before Import

An import implementation must require an explicit allowlist with:

- project slugs that may receive imported content
- source directories or files that may be read
- accepted frontmatter `type` values
- accepted target tables
- fields that may be imported for each type

## Initial Allowed Types

The first import version should be limited to the same reviewed memory types as `remember`:

- `fact`
- `decision`
- `open_question`
- `risk`
- `report`

Documents may be considered later, after content hash and path ownership rules are explicit.

## Rejection Rules

Import must reject or skip content that includes:

- passwords, API keys, tokens, FTP credentials, or private keys
- raw invoice data
- private customer data
- unknown project slugs
- paths outside the allowlisted import roots
- unsupported frontmatter types
- missing source/provenance for facts

## Default Behavior

Until the allowlist is implemented and tested, `agent-hub import` must remain a placeholder that performs no writes.
