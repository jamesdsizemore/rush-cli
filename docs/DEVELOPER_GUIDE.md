# Developer guide

This guide is for contributors. User help begins at [Documentation home](README.md).

## Local verification loop

```bash
uv sync --all-extras --frozen
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
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
- [Add a safety-gated operation](developer/tool-development.md#safety-review)

For the completed Phases 01–30 implementations, read:
- [Master PM Build Plan](developer/master-pm-build-plan.md): Complete specifications for Phases 21–30, incorporating the 7 Defensive Controls and 3 Architectural Recommendations.
- [Phase 21–30 Implementation Plans](developer/): Individual phase-by-phase implementation plans and ledgers.
- [Phase 09–19 coding-agent handoff](developer/phase-09-19-coding-agent-handoff.md), [Phase 07–08 coding-agent handoff](developer/phase-07-08-coding-agent-handoff.md), [Master Innovation & Remediation Plan](developer/innovation-remediation-plan.md), and [Vibecoder Toolkit Plan](developer/vibecoder-toolkit-plan.md).

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
* Memory & Invariants reside in `src/rush/memory/` (`preference_store.py`, `checkpoint_journal.py`, `merkle_invalidator.py`, `invariant_graph.py`, `failure_ledger.py`, `mistake_miner.py`).
* Release vectors reside in `src/rush/tools/ship/` (`cleaner.py`, `env_linter.py`, `docs_linter.py`, `migration_linter.py`, `semver_linter.py`, `package_linter.py`, `cockpit.py`).
* Grounding verification resides in `src/rush/codegraph/grounding_verifier.py` and `src/rush/tools/hallu_guard.py`.
