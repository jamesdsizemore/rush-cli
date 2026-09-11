# Known issues

Current baseline: [application review F01–F43](reports/phase-64-66-application-review.md). Documentation corrections do not implement repairs.

- **Data loss and disclosure:** `rush fix` P64-01 dry runs preserve Git state and apply requires artifact-write; `ship clean` P64-02 previews registered Rush-owned artifacts and requires explicit apply plus artifact-write. Patch cleanup remains pending P64-04; checkpoint/governance symlinks can escape containment; sandbox fallback/cleanup is unsafe. Custom token-outline MCP output can expose secrets. Use disposable copies for affected runtime investigation. Status: planned — [P64-03–P64-05](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md).
- **False execution/results:** AI eval can launch without required grants; lint/format can falsely report success; mutation/fuzz/load/contract live modes probe versions instead of running workloads. Test healing lacks perturbation and verified repair. Use native engine evidence or valid imported reports. Status: planned — [P64-06–P64-12](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md).
- **Incorrect analysis:** provenance survival/correlation, failed-target profiling, table drift, strictify constraints, SPDX expressions, encoded SVG sanitization, hidden-parent scans, coverage validation, multiline exception extraction, nested-scope complexity and staged-byte checks have reproduced defects. Status: planned — [P64-13–P64-19](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md).
- **Installation/workflow:** `setup` only recommends engines; capabilities can overstate readiness; suites lose child evidence and can retry `TypeError`. Installer scripts require uv and a checkout. Verified beginner installation, full scan and agent handoff remain planned in [Phase 65](phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md).
- **Interfaces/gates:** `ui`/`context gain` print once. Web API/authentication mismatch and shared server state remain open; persistent interfaces are planned in [Phase 66](phase-plans/phase-66-interactive-tui-and-local-web-plan.md). CI/packaging failures remain planned work in [P64-20](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md).

1. `review --llm` can call a configured provider and send findings; default review remains local heuristics.
2. `release` CLI exposes only `check` for version parity. Catalog/MCP release behavior is separate; signed-envelope CLI verification is `attest --verify PATH`. Package publishing/uploading is unavailable.
3. `review.fail_on`, project path lists, and generic tool `check` configuration are parsed but not universally enforced across all tools.
4. Human terminal renderer uses ASCII/Rich formatting; automated tools should rely on `--json` for machine-readable invariants.
5. `error-catalog` and `iam-audit` write markdown catalogs or policy JSON artifacts only when explicitly authorized via `--allow-artifact-write` (or `permissions.artifact_write=True`). In absence of authorization, they return status `skipped` with zero filesystem mutation.

6. `dead-asset` is strictly read-only by default; pruning requires explicit `--prune` and `--allow-artifact-write` with SHA-256 validation.
7. `pr-synthesize` artifact export requires `--allow-artifact-write` and operates completely offline with local Git diff extraction.

8. `attest` produces honest unsigned local provenance drafts (`assurance: unsigned_draft`) and binds built distribution artifacts in `dist/`; it intentionally does not claim SLSA Level 3 without external cryptographic signing.
9. `mem-profile` and `cold-start` run static AST analyses by default (workload-dependent overhead); dynamic profiling requires explicit `--allow-slow`.
10. `offline-review` requires a local ONNX model file and `onnxruntime` or external local runner on PATH; returns `status='skipped'` if uninstalled.
11. `benchmark check` compares against recorded baselines; updating or recording baselines requires `--allow-cache-write`.
12. [RESOLVED - Phase 52] Installed wheel/sdist packages outside the source checkout previously failed on startup due to internal `src.rush` imports (Finding R-001). This was completely resolved in Phase 52 by eliminating all `src.rush` imports across production and tests, isolating pytest collection, and verifying wheel/sdist installation probes in scrubbed external virtualenvs.
13. [RESOLVED - Phase 60] Central transport and orchestration modules (`cli.py`, `mcp.py`, `continuity.py`, `review.py`, `common.py`, `lint.py`, `blast_radius.py`, `workspace.py`, `db_drift.py`) previously contained high-complexity maintainability hotspots with cyclomatic complexity exceeding 20 (Finding R-015). This was completely resolved in Phase 60 by decomposing logic into dedicated modular packages (`rush.cli_support`, `rush.mcp_support`, `rush.continuity`, `rush.review`, `rush.runtime`, `blast_radius_graph.py`, `workspace_graph.py`, `db_drift_rules.py`). All 8 target symbols now satisfy McCabe C901 <= 10 with strictly zero exemptions, while preserving 100% backwards compatibility via identity re-exports.

Numbered Phase 52/60 resolution statements retain their historical scope; they do not close newer application-review findings.
