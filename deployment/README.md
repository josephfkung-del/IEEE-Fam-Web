# Submission reliability release

This release builds on the exact production files from deployment dpl_6UqE8eVpq44uU1TMr41hfVafGHFZ, which differs from the repository root application. Do not deploy the repository root to reproduce this release.

The release manifest identifies the preserved Vercel content-addressed source files. Map the prior production main.py to baseline_entry.py, then add this directory’s main.py, submission_reliability.py, submission_form.js, qa_reliability.py and requirements.txt at the deployment root. No credentials are stored in these patch files. The preserved private source retains the production configuration.

The build runs qa_reliability.py against an isolated copy of the patched legacy AST. Database and credential settings are replaced before any code executes. Tests cover validation, concurrent retries, daily cap contention, approval/feed/scoring and notification failure. Run node qa_client.cjs for repeated clicks and network/server error recovery.

Production writes use transaction-scoped advisory locks on PostgreSQL and BEGIN IMMEDIATE on SQLite. Existing schema and rows are preserved. No schema migration is required.
