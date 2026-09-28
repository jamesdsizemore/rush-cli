Status: needs-triage

## Summary

`rush dashboard --reconnect` prints a bootstrap token that is already invalid — `POST /api/session` with that exact token returns 401 `invalid or expired bootstrap token` every time, confirmed 3x via direct `curl`, independent of any browser tooling.

## Evidence

- Found during Phase 69 Codex review remediation (`docs/goals/phase-69-codex-review-remediation/`), task T036 (U05/U08 live-browser acceptance re-attempt).
- Worked around by using a fresh non-reconnect dashboard launch and driving one continuous browser session instead of reconnecting — never needed to actually fix the reconnect path for T036's own scope.
- Root cause not yet diagnosed (read-only discovery only, out of T036's allowed_files: `src/rush/dashboard/application.js`). Likely candidates for follow-up investigation, not yet verified: `src/rush/cli.py`'s `--reconnect` flag handling, `src/rush/dashboard/server.py`'s bootstrap-token issuance/consumption path.

## Suggested fix

Reproduce directly (`rush dashboard <project> --reconnect` against an already-running instance, then `curl -X POST http://<host>/api/session -d '{"token": "<printed token>"}'`), trace why the reconnect path's token is already consumed/expired at print time versus the fresh-launch path's token, and fix at the actual mismatch (likely a token being minted/consumed once already during the reconnect handshake before it's ever printed to the user).

## Scope note

Not one of the review doc's 51 named findings (S/M/U/D-series) and not required for Phase 69's `full_outcome_complete` — tracked here as a real out-of-scope production defect discovered incidentally during T036's live-browser testing.
