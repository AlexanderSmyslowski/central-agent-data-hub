# Release Checklist

Use this short checklist before tagging a public release.

1. Update `pyproject.toml` so `[project].version` matches the tag without the
   leading `v`.
2. Update or add the matching release notes under `docs/public/`.
3. Run the local verification checks from the release notes.
4. Push `main` and wait for CI to pass.
5. Tag the checked commit and create the GitHub release from the release notes.

Do not move an already published tag. If a release needs a correction after it
is public, publish the next patch version instead.
