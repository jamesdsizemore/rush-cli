# Phase 70 docs work order: merged tasks

This file lists every `docs/` change the implementers reported for the tasks already merged into `phase/70-agent-adoption-and-usability`. The docs agent applies each item against the CURRENT code, and must read the code that each item describes before writing.

## Rules
- Every command, flag, path and code cited must exist in the current source.
- `docs/reports/phase-64-66-documentation-coverage.md` is changed only through the `scripts/sync_docs.py` helpers (`build_document_inventory` / `read_coverage_receipt`), and stays compact JSON. After this work order, `python scripts/sync_docs.py --check` must report no new failure lines compared with its pre-existing baseline debt.
- The plan's own text is not rewritten here, except the plan §8.1 and §3.3 corrections listed under T2.

## T2 — native plugin packages
- Plan §8.1: `agent_assets/.claude-plugin/marketplace.json` → `agent_assets/claude/.claude-plugin/marketplace.json`; `codex/plugin.json` → `codex/.codex-plugin/plugin.json`.
- Plan §3.3, Codex row: replace "Root plugin.json… Do not invent a plugin-install CLI" with `.codex-plugin/plugin.json`, `codex plugin marketplace add`, and `codex plugin add rush@rush-local`.
- `docs/user-guide/working-with-ai-agents.md`: add `rush install --agent-plugin claude|codex`, `--convert-manual-entry` (consent), `rush agent hook`, and the verified upgrade sequences now recorded in the W1 brief T2 §1.5.

## T3 — agent instruction blocks and disconnect
- `docs/CLI_REFERENCE.md`, the `rush agent list|connect|doctor` section: rename the heading to `list|connect|disconnect|doctor`, add `[--install-guidance]` to the connect synopsis, and add a disconnect bullet. Add `[--install-guidance]` to the `rush install` synopsis.
- `docs/integrations/mcp-client-setup.md` §3: after "Acknowledgment", add "Guidance consent" and "Disconnecting" bullets.

## T6 — MCP request schemas
- `docs/MCP_REFERENCE.md` and `docs/reference/mcp-tool-reference.md`: the new published schemas for `rush_project`, `rush_scan` and `rush_memory` (top-level object, StrictBool grants, `schema_version`, operation enums). A rejected call is a structured `E_INPUT` with zero effects. An empty `session_allowlist` on ask/recall/list is now `E_INPUT`.
- Coverage receipt: refresh the recorded contracts for `rush_project`, `rush_scan` and `rush_memory`.

## T8 — target identity
- Coverage receipt: the declared-root `project` / `project_id` MCP parameters on every path-taking tool.

## T9 — invalid input, empty scope, clean work
- `docs/CLI_REFERENCE.md` "Advanced Scoping" (lines ~210–216):
  - an unknown `--workspace` is `TARGET_NOT_FOUND` (`workspace_not_found`), exit 2;
  - `--all-workspaces` gives one child per workspace, or `skipped` / `no_workspaces`;
  - an empty `--staged` / `--changed` / `--since` selection is `skipped`, with reason `no_staged_files` / `no_changed_files` / `no_files_since_ref`, exit 0;
  - a non-empty selection analyzes only those files, which are paths inside the target.
- Same file, exit-code text (~line 235): a missing target is `TARGET_NOT_FOUND` and a malformed one is `TARGET_INVALID`, both exit 2, with no engine run.

## T10 — project state and recovery
- `docs/CLI_REFERENCE.md` `rush flight-recorder`: the new status text.
- `docs/user-guide/advanced-checks.md`: cache stats report `exists`, and a missing DB is not created.
- `docs/MCP_REFERENCE.md` and `docs/workflows/gain_tui_and_telemetry.md`: gain stats return `available` / `reason` / `path`, read-only.
- Recovery: document `scripts/phase70_t10_recovery.py` (inventory by default; `--execute` backs up, quarantines, writes `manifest.json` and prints the restore command).

## T11 — project environment
- Coverage receipt: typecheck `environment` (x3) and MCP `allow_build`.
- `docs/user-guide/checking-code.md`: `--environment project|isolated`, the `analysis_environment` metadata and its causes, and pyrefly (required, minimum 0.37.0, in the dev extra).

## T12 — typecheck scoping
- `docs/user-guide/checking-code.md` §4:
  - mypy and pyrefly; tsc needs `--allow-cache-write`;
  - `--typecheck-config PATH` (MCP `typecheck_config`) and `TYPECHECK_CONFIG_{NOT_FOUND,OUTSIDE_ROOT,INVALID,CONFLICT,REQUIRED}`;
  - mypy plugins and pyrefly interpreter-executing config keys need `--allow-build`;
  - the `extensions.scope` values;
  - the `TSC_*` codes (`TSC_REFERENCE_CYCLE`, `TSC_AMBIGUOUS_OWNER`, `TSC_CONFIG_DIAGNOSTICS`).
- `docs/tutorials/typescript-project.md` step 3: `rush typecheck .` → `rush typecheck . --allow-cache-write`.
- `docs/MCP_REFERENCE.md`: the `typecheck_config` and `allow_cache_write` parameters.

## T14 — dependency audit
- `docs/user-guide/security-and-supply-chain.md:42`: replace the pip-audit-only line. `uv.lock` / `requirements*` (root and nested, includes resolved against the including file) are audited offline by osv-scanner. pyproject-declared dependencies are audited by gated pip-audit project mode, which requires network, download, cache_write and build. Also document `metadata.scope.dependencies` states.

## T15 — engine readiness
- `rush doctor`: per-engine readiness (`installed` / `missing` / `unsupported`); the `engine-missing` / `engine-unsupported` / `binary-shadowing` / `engine-integrity` findings; the action is the saved-plan route (after T26).

## T16 — scope, engines, recoverable output
- Coverage receipt: 463 contract lines for `--result-view` / `--limit` / `--max-bytes` on every catalog command, the MCP view params, the retrieve params, and patch apply's `--allow-cache-write`.
- `docs/reference/result-reference.md`: add `metadata.engines`, the v1 `metadata.scope`, `metadata.delivery`, the `RESULT_*` codes, and `cache clean`'s report line.

## T18 / T20 — memory
- `docs/reference/cli-reference.md` §"Memory (Phase 61)" and `docs/CLI_REFERENCE.md` heading `rush memory ask|…|maintain`: add the bare `rush memory [--offset N --generation TOKEN] [--include-internal] [--json]` overview (the 20 newest useful rows, read-only, `migration_required` / `corrupt` states, internal bookkeeping hidden by default).
- Coverage receipt: `contracts.cli["rush memory"]` = `{"parameters":[{"default":false,"kind":"option","name":"as_json","required":false,"type":"bool"},{"default":null,"kind":"option","name":"generation","required":false,"type":"string"},{"default":false,"kind":"option","name":"include_internal","required":false,"type":"bool"},{"default":0,"kind":"option","name":"offset","required":false,"type":"integer range"}]}`.
- Dashboard: the `include_internal` query parameter.

## T24 — setup review and apply
- `docs/getting-started/installation.md:66`: replace "Current `rush setup` does not provide a verified installer…" with this. `rush setup PATH` previews config, registration, configure and engines, then asks. `--json` / `--non-interactive` preview only. Non-interactive apply is `--save-plan` then `--apply --yes --plan-file F --plan-id ID` with the `--allow-*` grants.
- `docs/reference/cli-reference.md:117`, the `setup` row: options `--interactive/--non-interactive`, `--apply`, `--yes`, `--plan-file`, `--plan-id`, `--save-plan`, `--allow-*`, `--json`, and `--install` (compatibility, no effect). Remove "prototype".

## T26 — guided route
- `docs/getting-started/installation.md`: the guided route from the bootstrap script to a working host, and the printed resume line.
- `docs/integrations/mcp-client-setup.md`: project-bound Claude (local scope) and Codex (global, consented rebind) registration; readiness states `installed` → `capability_verified`; `--verify-host`; `rush mcp serve --project/--session`.
- `docs/reference/cli-reference.md`: the new flags on setup, install and mcp serve.
- README install section.

## TS — test-suite speed
- `CHANGELOG.md`: the C2 lingering-close total deadline for rejected request bodies (dashboard).
- The developer testing doc (find where the suite is documented in `docs/`): the suite builds wheel, sdist and native archive per session (PyInstaller via `uv run --with`, `uv build`) and provisions mutation, load and contract engines locally. Scan tests use a hermetic engine PATH. The serial suite takes ~7 minutes.
