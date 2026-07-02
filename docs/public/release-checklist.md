# Release Checklist

Use this short checklist before tagging a public release.

1. Update `pyproject.toml` so `[project].version` matches the tag without the
   leading `v`.
2. Update or add the matching release notes under `docs/public/`.
3. Run the local verification checks from the release notes.
4. Run `scripts/release_candidate_check.sh`, or manually confirm the same
   release-candidate evidence from
   [`v0.7-definition.md`](v0.7-definition.md): public demo startup and smoke,
   external developer smoke, trust-loop smoke, offline-agent smoke, upgrade
   drill, `agent-hub status`, and `agent-hub check`.
5. Push `main` and wait for CI to pass, including the separate behavioral
   smoke jobs. A green unit-test job alone is not enough.
6. Tag the checked commit and create the GitHub release from the release notes.

Do not move an already published tag. If a release needs a correction after it
is public, publish the next patch version instead.
