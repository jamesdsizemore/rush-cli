# Developer guide

## Continuity contribution rule

Keep session operation logic in `src/rush/tools/continuity.py`. CLI and MCP code may adapt arguments and render results, but must not instantiate `CheckpointJournal` or invent transport-specific strings.

This guide is for contributors. User help begins at [Documentation home](README.md).

## Local verification loop

```bash
uv sync --all-extras --frozen
unset VIRTUAL_ENV PYTHONPATH
uv run --python 3.12 --extra dev python -m pytest tests/ -q
uv run --python 3.12 --extra dev ruff check src tests
uv run --python 3.12 --extra dev ruff format --check src tests
git diff --check
```

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/ruff`. See [Contributor onboarding](developer/contributor-onboarding.md).

## System map

- `catalog.py`: canonical tool/engine metadata and maturity.
- `cli.py`: Click transport and result rendering only.
- `mcp.py`: stdio FastMCP registration only.
- `config.py`: bounded discovery, typed parse, catalog validation.
- `tools/`: implementation and routing; one shared path for CLI/MCP.
- `engines/`: binary discovery, argv, parsing, normalization.
- `logging.py`: stderr NDJSON and redaction.
- `tests/fixtures/engine_reports/`: engine-native parser contracts.

Read [Architecture](developer/architecture.md) and [Source tree](developer/source-tree.md).

## Canonical contracts

Tool and engine metadata must agree with executable registries and tests. Do not duplicate logic in transports. MCP-callable signatures cannot leak `config` and must remain JSON-schema-compatible. Missing binaries produce `skipped`. Subprocesses use captured output and detached stdin. ToolResult and Finding fields must stay stable and redacted.

## Extension recipes

- [Add a tool](developer/tool-development.md)
- [Add an engine](developer/engine-development.md)
- [Add a language route](developer/routing-development.md)
- [Add a config field](developer/configuration-development.md)
- [Change MCP](developer/mcp-development.md)
- [Add a safety-gated operation](developer/tool-development.md#1-tool-lifecycle--architecture)

For the completed Phases 01–30 implementations, read:
- [Master PM Build Plan](developer/master-pm-build-plan.md): Complete specifications for Phases 21–30, incorporating the 7 Defensive Controls and 3 Architectural Recommendations.
- [Phase 21–30 Implementation Plans](developer/): Individual phase-by-phase implementation plans and ledgers.
- [Phase 09–19 coding-agent handoff](developer/phase-09-19-coding-agent-handoff.md), [Phase 07–08 coding-agent handoff](developer/phase-07-08-coding-agent-handoff.md), [Master Innovation & Remediation Plan](developer/innovation-remediation-plan.md), and [Vibecoder Toolkit Plan](developer/vibecoder-toolkit-plan.md).
- [Benchmark Plan & Harness](reports/rush-benchmark-plan.md): Reproducible test and verification harness across Phases B1–B6.

## Testing and delivery

[Test guide](developer/testing-guide.md) defines unit, parser, routing, CLI, real stdio MCP, installed-engine, package, clean-clone, and CI layers. [CI and packaging](developer/ci-and-packaging.md) and [Release process](developer/release-process.md) keep tags and publication separate from validation.

## Contributor checklist

- [ ] Scope and safety boundary are explicit.
- [ ] RED test captured the missing contract.
- [ ] Tool/catalog/engine/CLI/MCP/config parity is preserved.
- [ ] Missing-engine, malformed report, timeout, and redaction paths are tested.
- [ ] User docs describe outcomes; developer docs describe internals.
- [ ] Ruff, format, tests, link validation, whitespace, and graph checks pass.
- [ ] No commit, tag, publish, or push without authorization.

## Developing Context Intelligence & Ship Tools (Phases 41–43)
* Token Economy modules reside in `src/rush/token_economy/` (`router.py`, `ast_skeletonizer.py`, `ccr_store.py`, `distillers/`, `toon/`).
* Memory & Invariants reside in `src/rush/memory/` (`store.py`, `trust.py`, `migration.py`, `transport.py` — Phase 61's unified `TypedArtifactStore`/`.rush/memory.db`, plus `preference_store.py`, `checkpoint_journal.py`, `merkle_invalidator.py`, `invariant_graph.py`, `failure_ledger.py`, all now thin compatibility views over it, and `mistake_miner.py`, still a pure git-log miner; Phase 62 adds `maintenance.py` (`run_maintenance_cycle()`), `expiry.py` (`ExpiryPolicy`/`sweep_expired()`), and `decision_schema.py` (`DecisionRecordFields`), plus `src/rush/token_economy/memory_cache_gate.py` (`check_memory_before_pack()`)). The query/write interface is `src/rush/tools/memory.py`'s `MemoryTool` (`rush memory ask|write|promote|list|recall|maintain`).
* Release vectors reside in `src/rush/tools/ship/` (`cleaner.py`, `env_linter.py`, `docs_linter.py`, `migration_linter.py`, `semver_linter.py`, `package_linter.py`, `cockpit.py`).
* Grounding verification resides in `src/rush/codegraph/grounding_verifier.py` and `src/rush/tools/hallu_guard.py`.
