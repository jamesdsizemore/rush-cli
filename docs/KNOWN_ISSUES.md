# Known issues

1. `review --llm` returns deterministic stub information and does not call an external model provider.
2. `release` CLI exposes dry-run planning and signature/provenance verification; package publishing/uploading is intentionally unavailable by design.
3. `review.fail_on`, project path lists, and generic tool `check` configuration are parsed but not universally enforced across all tools.
4. Human terminal renderer uses ASCII/Rich formatting; automated tools should rely on `--json` for machine-readable invariants.
5. `error-catalog` and `iam-audit` write markdown catalogs or policy JSON artifacts only when explicitly authorized via `--allow-artifact-write` (or `permissions.artifact_write=True`). In absence of authorization, they return status `skipped` with zero filesystem mutation.

6. `dead-asset` is strictly read-only by default; pruning requires explicit `--prune` and `--allow-artifact-write` with SHA-256 validation.
7. `pr-synthesize` artifact export requires `--allow-artifact-write` and operates completely offline with local Git diff extraction.

8. `attest` produces honest unsigned local provenance drafts (`assurance: unsigned_draft`) and binds built distribution artifacts in `dist/`; it intentionally does not claim SLSA Level 3 without external cryptographic signing.
9. `mem-profile` and `cold-start` run static AST analyses by default (0s overhead); dynamic profiling requires explicit `--allow-slow`.
10. `offline-review` requires a local ONNX model file and `onnxruntime` or external local runner on PATH; returns `status='skipped'` if uninstalled.
11. `benchmark check` compares against recorded baselines; updating or recording baselines requires `--allow-cache-write`.
12. [RESOLVED - Phase 52] Installed wheel/sdist packages outside the source checkout previously failed on startup due to internal `src.rush` imports (Finding R-001). This was completely resolved in Phase 52 by eliminating all `src.rush` imports across production and tests, isolating pytest collection, and verifying wheel/sdist installation probes in scrubbed external virtualenvs.

These reflect current design constraints and boundaries.
