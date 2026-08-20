# Phase 01 — core code, security, dependency, workflow, and source-policy scanners

> **Depends on:** Phase 00 accepted. **Excludes:** IaC/artifacts/reliability/browser work.

**Objective:** Replace the highest-value false catalog claims with real local adapters while retaining Ruff/ESLint/Prettier/mypy/pytest/Vitest/Vulture/Knip/Radon/jscpd/Gitleaks/pip-audit/npm-audit/actionlint/commitlint behavior.

**Phase-00 handoff required before the first edit:** ADRs 0001–0006 and 0010 are accepted; the five-status mapping (`ok|warn|fail|error|skipped`), execution metadata, catalog maturity enum, resolver-only binary policy, fixture helper, and `Engine.version()` subprocess contract are merged. This phase must not add a second status vocabulary, a binary override, or a `rush.review` package.

## Mandatory compact development protocol

For every adapter slice: start/end `rtk git status --short`; use **Graft** (`ask`, `grep`, `callers`) to find the tool, engine, registry, config, CLI/MCP and tests; use **context-mode** to index/query that exact bounded seam plus ADRs 0001–0010; use **RTK** for exact reads/grep/diff/focused project-venv tests. RED fixture → RED proof → smallest code → GREEN → docs → self review → independent spec review → independent code/security review → targeted fix/re-review → scoped stage/commit. Build/check Graft after registration imports change.

## Exact external-engine baselines and selection gates

| Slice | Exact baseline and release source | Status at Phase 01 entry / required engine contract |
|---|---|---|
| Multi-language SAST | Semgrep `1.173.0`; [official release](https://github.com/semgrep/semgrep/releases/tag/v1.173.0) | `feasibility_gated` until official JSON/exit/local-rule/no-network and license evidence is recorded. It gets a new focused `sast` tool only after registry/CLI/MCP RED tests; do not overload dependency-oriented `security`. Local contained rules/config only; no registry download, metrics, version check, remote target, or local build. |
| Secrets | Gitleaks `8.30.1`; [official release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1) | Phase 00 reference adapter. Retain its current focused command; redact values and do not scan history unless a later explicit config/ADR authorizes it. detect-secrets and TruffleHog stay unnamed feasibility candidates, not supported dependencies. |
| Dependency security | Rush-pinned `pip-audit==2.10.1`; `npm audit` has no Phase 01 live baseline until Phase 00 records one exact Node/npm compatibility pair | Existing behavior is truth-audited only. An unrecorded Node/npm host tool remains `feasibility_gated`, not implicitly live. OSV Scanner/SBOM/provenance stay Phase 03; no new dependency scanner or network/cache policy here. |
| CI workflow | zizmor `1.29.0`; [official release](https://github.com/woodruffw/zizmor/releases/tag/v1.29.0) | `feasibility_gated` until local JSON/SARIF, exit, version, license, and no-token/no-network evidence is recorded. If accepted, it extends the existing `actions` command beside actionlint; it does not create a transport-specific path. Its child environment forces `ZIZMOR_OFFLINE=1` and removes `GH_TOKEN`, `GITHUB_TOKEN`, and `ZIZMOR_GITHUB_TOKEN`. |
| Source policy | Rush built-ins only; codespell remains Phase 02 | Deterministic configured architecture/TODO/scaffold/error-handling/readiness findings with stable IDs/exclusions. Do not claim authorship, model use, or AI detection. |

These are **external compatibility pins, not Rush package dependencies**. No scanner SDK, package manager, rule pack, or engine is added to `pyproject.toml`/`uv.lock`. Before any baseline is labelled live, record the exact version probe, command/output format, exit mapping, license, source, and network/cache/build/write behavior in `docs/ENGINE_COMPATIBILITY.md` and the untracked research record.

## Owned seams

- Preserve `src/rush/tools/security.py` as dependency vulnerability orchestration; do not put Semgrep there. Semgrep, if accepted, owns new `src/rush/tools/sast.py` and `src/rush/engines/semgrep.py`; zizmor, if accepted, extends the existing `tools/actions.py` through `engines/zizmor.py`.
- Modify `src/rush/tools/review.py`, `secrets.py`, `actions.py`, `quality.py`, `routing.py`, and `common.py` only when the Phase 00 contract and RED test require it. Do not touch `content.py` in this phase; content scanners are Phase 02.
- Create engine modules only after research proof; export through `engines/__init__.py`. Update `catalog.py`, `config.py`, `tools/__init__.py`, `cli.py`, and `mcp.py` atomically for each accepted real command.
- Tests: `test_tools.py`, `test_static_tools.py`, `test_supply_chain_tools.py`, `test_catalog.py`, `test_config.py`, `test_cli_registry.py`, `test_mcp.py`, plus adapter-specific fixture tests. `test_content_infra_tools.py` is intentionally Phase 02-owned.
- Docs: engines/compatibility/catalog/config/CLI/MCP/user guide/troubleshooting/contributing; local evidence in `research/engine-records/` remains unstaged.

## Task plan

1. **Truth audit:** create a table mapping each current Phase 01 tool to the Phase-00 maturity enum, exact engine baseline, command/output, and test owner. RED test blocks a `live_adapter` catalog flag without a registered parser fixture suite; preserve `guarded_placeholder` or `feasibility_gated` when evidence is incomplete.
2. **Review coordinator preservation:** write failing aggregation tests proving focused tools retain tool/engine/status/finding provenance and deterministic order. Implement only coordinator/routing changes needed; do not duplicate adapter logic.
3. **Semgrep feasibility and adapter:** first record Semgrep `1.173.0` official binary/version/license/JSON/exit/config/network behavior. Add fake JSON clean/findings/malformed/nonzero/missing/version fixtures. RED-test the new `sast` ToolSpec/registry/CLI/MCP parity before creating code. Its only candidate invocation is an argument vector equivalent to `semgrep scan --json --metrics off --disable-version-check --config <contained-local-rule> <contained-target>`; it must reject remote/registry config values and never pass `--allow-local-builds`, `--autofix`, `--remote`, or `semgrep ci`. Normalize rule/location/severity/remediation and map a valid findings exit to existing `warn`/`fail` policy, never a new `findings` status. If any gate fails, retain `feasibility_gated` and ship no adapter.
4. **Workflow/security expansion:** similarly gate zizmor `1.29.0` with local workflow JSON/SARIF fixtures before it can extend `actions`. Its child environment must force `ZIZMOR_OFFLINE=1` and remove `GH_TOKEN`, `GITHUB_TOKEN`, and `ZIZMOR_GITHUB_TOKEN`; fake-executable tests prove those values cannot reach the engine. Fix existing secret/dependency status/redaction issues found in review; never expand history, token lookup, or network scope silently.
5. **Deterministic source-policy rules:** add configuration-backed architectural/TODO/scaffold/error-handling/readiness findings with stable rule IDs and exclusions. Test false-positive boundaries and explain each remediation.
6. **Parity and review:** for each accepted adapter run fake-binary integration, CLI/MCP schema/invocation parity, docs snapshot checks, full review aggregation, both independent reviews, targeted fixes, then a scoped commit.

## Required failure semantics

Missing binary/config/local rules/inapplicable files → `skipped`; malformed JSON or unrecognized version → `error`; valid scanner findings map to existing `warn`/`fail` under the documented policy, never `error`; timeout/cancellation remain `error` with Phase-00 `metadata.terminal_reason`/`metadata.partial`; secrets/redacted env values never leave the adapter.

## Acceptance, docs, CI, non-goals

**Accept when:** every claimed live scanner meets Phase 00 real-integration gate; review output retains prior results; core catalog/CLI/MCP/docs agree; fixture/optional-engine lane and full quality gates pass.

**Docs:** add install/version matrix, local-rule examples, missing-engine/config/timeout troubleshooting, source-policy rationale and false-positive opt-outs.

**CI:** deterministic fake-executable fixtures required; only declared pinned representative engines may run in optional lane.

**Non-goals:** OSV/SBOM/provenance, IaC, mutation/API/load, language suites, browser/Playwright/axe/Lighthouse/DAST. Roll back only this phase’s adapter commits and restore truthful maturity state.