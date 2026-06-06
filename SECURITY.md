# Security Policy

Agent Data Hub is a local reviewed context system. Even so, security issues
matter, especially where they could expose sensitive project data or break the
system's safety boundaries.

## Please Report Privately

Please do not open a public issue for:

- secret leakage risks
- unsafe import or export behavior
- ways to bypass project boundaries
- dangerous writeback paths
- backup or restore vulnerabilities

For now, report security issues privately to the maintainer through a direct
channel rather than a public GitHub issue.

## Scope

Security-relevant areas include:

- secret and private-data filtering
- import and sync behavior
- project-boundary enforcement
- backup and restore flows
- local review/export surfaces

## What Helps In A Report

- affected file or command
- exact reproduction steps
- expected behavior
- actual behavior
- potential impact

## Response Intent

The project is maintained as a small local-first system, so response times are
best-effort. Clear reports with reproducible steps are the fastest path to a
fix.
