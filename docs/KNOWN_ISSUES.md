# Known issues

1. `review --llm` returns deterministic stub information and does not call an external model provider.
2. `release` CLI exposes dry-run planning and signature/provenance verification; package publishing/uploading is intentionally unavailable by design.
3. `review.fail_on`, project path lists, and generic tool `check` configuration are parsed but not universally enforced across all tools.
4. Human terminal renderer uses ASCII/Rich formatting; automated tools should rely on `--json` for machine-readable invariants.

These reflect current design constraints and boundaries.
