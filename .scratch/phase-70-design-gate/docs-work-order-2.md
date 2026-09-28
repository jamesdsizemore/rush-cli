# Phase 70 docs work order 2: T4, T19, aislop fix

This lists every `docs/` change the implementers reported for the tasks merged after work order 1 (phase HEAD 65f2219). The docs agent applies each item against the CURRENT code, and reads the code an item describes before writing it.

## Rules
- Every command, flag, path, field and code you cite must exist in the current source. Check each one with `rush <cmd> --help` or by reading the source.
- `docs/reports/phase-64-66-documentation-coverage.md` changes only through the `scripts/sync_docs.py` helpers (`build_document_inventory` / `read_coverage_receipt` / `collect_runtime_contracts`), and it stays compact JSON. Update only the touched entries and the changed contracts. After this work order, `python scripts/sync_docs.py --check` must show no new failure lines compared with the 65f2219 baseline. Record both line counts.
- Owner decision: Cursor is removed from Phase 70. The hosts are Claude Code and Codex CLI only. Add no Cursor instructions.
- Do not edit `docs/phase-plans/*-plan.md`.

## T4 — MCP profiles and profile migration
Source: `src/rush/mcp.py`, `src/rush/cli.py` (`mcp serve`, `agent connect`), `src/rush/integrations/agents.py`, `src/rush/tools/agent_connection.py`.
- `mcp serve --profile core|full`:
  - core registers exactly the seven agent tools (read the exact set in `mcp.py`);
  - full registers every tool;
  - the instructions list only the registered tools;
  - a call to a tool outside the profile returns "Unknown tool".
- Registrations:
  - new host registrations use `--profile core`;
  - existing registration args are kept, with command repair.
- `agent connect --profile core|full` and `--yes`:
  - it shows a preview, then a y/N prompt;
  - the migration is reversible, and a native write re-checks the reviewed digest;
  - a migration that writes nothing (preview only, conflict, or restored after a failure) is `skipped`, exit 0;
  - a failed restore is `error`.
- MCP `rush_agent_connection` gains strict `profile` and `confirm_profile_migration` fields.
- Files:
  - `docs/CLI_REFERENCE.md`
  - `docs/reference/cli-reference.md`
  - `docs/MCP.md`
  - `docs/MCP_REFERENCE.md`
  - `docs/reference/mcp-tool-reference.md`
  - `docs/integrations/mcp-client-setup.md`
  - `docs/INTEGRATIONS.md`
  - `docs/user-guide/working-with-ai-agents.md`
- Coverage receipt: the changed `mcp serve`, `agent connect` and `rush_agent_connection` contracts.

## T19 — memory use receipts
Source: `src/rush/memory/*`, `src/rush/tools/{review,memory,continuity,routing,scan_handoff}.py` and `src/rush/workflows/project_run.py`. `tests/test_phase70_t19.py` shows the exact shapes.
- In `docs/reference/result-reference.md`, add a "Memory receipts" section covering `metadata.memory`:
  - each entry has id, revision, operation, source and `used`, and is recorded once per (id, revision, operation);
  - the member is omitted when a tool touches no memory;
  - on resume, `metadata.cache.original_memory` holds the retained children's receipts and `metadata.memory` holds this attempt's;
  - the checkpoint-journal fallback reports a `restore` receipt.
- Take every field name from the tests and the source.
- Add a coverage receipt entry for that doc.

## aislop fix (slop tool)
Source: `src/rush/engines/aislop.py` and `src/rush/tools/slop.py`.
- Update the user and reference docs that describe `rush slop` or the slop step (not the historical plans in `docs/developer/`):
  - aislop scans the target directory; a file target becomes its parent plus `--include`;
  - findings are reported as `aislop/<engine>/<rule>`, from every aislop engine;
  - the result is `error` only when aislop produces no JSON report.
- Find the user-facing mentions with grep. Leave the historical phase plans untouched.
