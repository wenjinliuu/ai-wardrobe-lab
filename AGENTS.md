# Working on AI Wardrobe Lab

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
