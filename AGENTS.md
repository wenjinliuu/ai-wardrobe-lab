# Working on AI Wardrobe Lab

## Frozen project — 2026-10-02 (Asia/Shanghai)

The project owner explicitly froze this project. Read `docs/project-freeze-2026-10-02.md` before any work. Preserve existing code, records and assets. Documentation and read-only inspection are permitted; do not add features, expand provider integrations, run billable experiments, trigger deployments or migrate/delete data unless the owner explicitly reopens that scope. Freeze documentation does not authorize shutting down services, revoking credentials or archiving the repository read-only. Existing CI/deployment configuration remains unchanged.

## Existing implementation safeguards

- This is a private API evaluation console, not a production wardrobe app.
- Default to mock mode. Never run billable provider calls as part of automated tests.
- Keep credentials in server environment variables, never browser storage or repository files.
- Freeze model, template and input hashes per job; do not mutate completed experiment history.
- Never automatically repeat an ambiguous generation POST. Resume task queries or file saving only.
- Deploy one Uvicorn process until distributed task leases are implemented.
- Add provider capability limits and contract tests before exposing a new model profile.
- Distinguish mock/contract-tested/live-tested status; do not call a provider live-tested without evidence.
- Verify with `python -m pytest tests -q`, `node --check web/app.js`, and `bash -n scripts/deploy.sh`.
- Use FFmpeg and Playwright for video and browser tests. Do not commit test photos, real selfies, Key files or .env.
- Maintain docs/handoff.md when changing deployment requirements or live-test boundaries.
