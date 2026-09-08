Current status: historical decision; Distiller utilities do not establish universal subprocess integration, a global `--raw` flag, or the latency and 85–95% savings below. [CLI reference](../CLI_REFERENCE.md) and [token economy and context](../agentic-rush/token-economy-and-context.md) describe current routes and restoration limits; [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) preserves measured token-effect requirements.

# ADR-0040: Command-Output Distillation and Test Log Pruning

## Status
Accepted (v0.3.0 / Phase 41)

## Context
Test runners (pytest, vitest, cargo test) and linters (ruff, eslint) produce thousands of lines of passing test noise and redundant trace headers that flood agent context windows with useless tokens.

## Decision
1. Implement native **Command Output Distillers** in `src/rush/token_economy/distillers/` using deterministic pattern extractors for `pytest`, `cargo`, `ruff`, `vitest`, `mypy`, and `npm`.
2. Embed distillation directly into `src/rush/tools/common.py:run_subprocess()`, stripping passing lines and isolating failing assertion blocks, stack trace frames, and exit codes.
3. Preserve full un-distilled raw output access via `--raw` flag and fallback safety triggers on unclassified errors.

## Consequences
- **Positive**: Achieves 85–95% token reduction on test/lint execution logs in $<5\text{ ms}$ processing time.
- **Negative**: Regex heuristic maintenance as third-party CLI tool output formats evolve.
- **Safety**: Preserves non-zero exit codes, exact failure line numbers, and file paths.
