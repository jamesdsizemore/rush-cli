# Phase 00 — foundation and truthful integration contract

> **Depends on:** approved `master-build-plan-remediation.md` only.
> **Blocks:** every other phase. **Does not authorize browser/runtime work.**

**Objective:** Make Rush’s existing catalog, results, invocation path, configuration, and documentation truthfully distinguish live adapters, report importers, guarded placeholders, and feasibility-gated work. Prove the complete external-engine contract with one reference adapter before claiming further integration.

## Required inputs and frozen constraints

- Read `AGENTS.md`, the master plan §§1–5, and ADRs 0001–0010 before editing.
- Preserve `ToolResult` compatibility in `src/rush/tools/base.py`, one `ALL_TOOLS` registry, CLI/MCP shared implementations, `run_subprocess()` for all external commands, and local stdio MCP.
- Keep current direct pins (`mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`, `pip-audit==2.10.1`, `ruff==0.16.3`) and pin `[build-system].requires` to `hatchling==1.32.0` (official PyPI release verified 2026-08-18). `uv.lock` governs runtime/dev resolution; validate the separately resolved build backend with `uv build`. Never add scanner SDK dependencies.
- A “skipped” scanner must name the missing binary/config/permission or applicability condition; it must not report pass.

## Mandatory compact development loop

At the beginning and end of every task, run `rtk git status --short` and keep unrelated README/docs/research work out of the task scope.

1. **Graft:** `graft ask`/`graft grep` for `ToolResult`, `Engine`, `ALL_TOOLS`, catalog specs, CLI command builder, MCP builder, `resolve_binary`, `run_subprocess`, config validation, and their callers. Run `graft build/check` after registry/import changes.
2. **context-mode:** index only those source files plus `tests/test_catalog.py`, `tests/test_config.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_engines.py`, and this phase; query result/status, subprocess, config, and parity contracts before each interface decision.
3. **RTK:** use `rtk read` for the discovered blocks, `rtk rg` for exact status/config fields, `rtk git diff -- <owned paths>` for review, and project-native test commands for evidence.
4. For every implementation slice: RED test → observe RED → minimal implementation → GREEN → docs → self review → fresh spec reviewer → fresh code/security reviewer → targeted fix → both reviews again.

## Owned files and interfaces

| Area | Create/modify | Contract to freeze |
|---|---|---|
| Result/evidence model | Modify `src/rush/tools/base.py`; do **not** create a `rush.review` package in this phase | Preserve `ToolStatus` (`ok`, `warn`, `fail`, `error`, `skipped`); optional fields: `rule_id`, `location`, `remediation`, `evidence`, `provenance`, `fingerprint`, `freshness`; timeout/cancellation use deterministic optional execution metadata (`terminal_reason`, `partial`), serialization/order, and `[REDACTED]` policy. |
| Engine base/invocation | Modify `src/rush/engines/base.py`, `src/rush/tools/common.py`; tests in `tests/test_engines.py` | Preserve current resolver ordering (active venv Scripts/bin then PATH); no configured binary override. Migrate `Engine.version()` and every new external call through `run_subprocess()` with version-probe, args/cwd/DEVNULL/timeout/output-cap/cancellation/redaction and exit mapping tests. |
| Catalog maturity | Modify `src/rush/catalog.py`, `src/rush/tools/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/config.py` | Every tool carries a maturity class: `live_adapter`, `report_importer`, `guarded_placeholder`, or `feasibility_gated`; CLI/MCP schemas derive from same registry. |
| Capability/planning base | No module/package creation; Phase 06 exclusively owns capability/planner commands | Record only ADR/API prerequisites so Phase 06 can add read-only project-marker/config/report/PATH-version/permission detection without engine execution. |
| Dependency governance | Modify `pyproject.toml`, `uv.lock` only for runtime/dev changes, `.github/workflows/ci.yml`; create test/CI script only if needed | Pin `hatchling==1.32.0`; direct dependencies must be exact; frozen sync catches runtime/dev drift and `uv build` verifies the build backend separately. |
| ADR/docs | Create `docs/adr/0001-…0010-….md`, `docs/DEPENDENCY_POLICY.md`, `docs/ENGINE_COMPATIBILITY.md`; update `docs/ARCHITECTURE.md`, `docs/TOOL_CATALOG.md`, `docs/CONFIGURATION.md`, `docs/ENGINES.md`, `docs/CLI_REFERENCE.md`, `docs/MCP.md`, `CONTRIBUTING.md`, `docs/TROUBLESHOOTING.md` | State mature behavior, not aspirations; each tool’s class and skip/error semantics are visible. |

## Task-based development plan

### 00.1 — establish Git scope and contract evidence

1. Record branch/status/recent commits with RTK; copy no unrelated changes into the phase commit.
2. Use Graft to map result, engine, registry, config, CLI/MCP, and test call chains; store exact file:line references in this phase’s execution ledger.
3. Index the found set with context-mode; query “ToolResult engine error skipped config CLI MCP contract.”
4. Use RTK to read exact definitions and write a short decision table: existing field, compatibility need, proposed additive field, test owner.
5. **Acceptance:** a reviewer can reproduce the current architecture from the ledger without broad repository reads.

### 00.2 — write and approve the ADR set before behavior changes

1. Draft ADRs 0001–0010 named in master §3 with alternatives rejected and consequences.
2. Add a cross-reference table in `docs/ARCHITECTURE.md` mapping ADR → source seam → test suite → affected phase.
3. RED test/document check: add a documentation consistency test or review checklist that fails if catalog maturity vocabulary differs between catalog/docs.
4. Review ADRs for no accidental network, SDK, browser, or transport-scope expansion.
5. **Acceptance:** all downstream phase plans link to ADR IDs; browser-final ADR explicitly rejects early browser prerequisites.

### 00.3 — freeze normalized finding/evidence model

1. Add failing serialization/normalization tests covering legacy result compatibility, location with and without column, rule IDs, deterministic fingerprint, stable ordering, remediation/evidence/provenance, and `[REDACTED]` values.
2. Implement only additive `TypedDict`/helper changes needed for those tests; preserve existing consumers and JSON output shape.
3. Add clean, valid-warning, valid-failure, error, skipped, timeout, and cancelled samples as fixtures or factories; no external executable. Timeout/cancelled samples must remain `error` with `metadata.terminal_reason` and `metadata.partial`, not new statuses.
4. Update `docs/ARCHITECTURE.md`, `docs/CLI_REFERENCE.md`, and ADRs 0002/0004 with the exact status, exit-code, metadata, and legacy-JSON compatibility mapping.
5. **Acceptance:** `ToolResult` tests prove old result JSON remains valid and new evidence does not leak fixture secrets.

### 00.4 — harden shared local discovery and bounded subprocess contract

1. RED tests in `tests/test_engines.py`/new `tests/test_subprocess_contract.py` for existing resolver order (active venv Scripts/bin then PATH), rejection/absence of a configured executable override, missing binary, version probe failure, list-only invocation, fixed cwd, `stdin=DEVNULL`, stdout/stderr cap, redaction, timeout, cancellation, nonzero exit, and no `shell=True`.
2. Implement central helpers in `tools/common.py`; adapters and `Engine.version()` must not invoke `subprocess` directly.
3. Add a fake executable fixture that records argv/cwd/stdin behavior and returns controlled JSON/text/exit codes; do not use a real host scanner.
4. Use Graft callers to identify all direct process calls; migrate every external-engine call, including `Engine.version()` at `src/rush/engines/base.py`, with narrow regression tests.
5. Document timeout defaults, output truncation, safe diagnostics, and missing-engine messages in `docs/ENGINES.md`/troubleshooting.
6. **Acceptance:** a security reviewer confirms every new command is an argument vector and sensitive fixture data is redacted.

### 00.5 — catalog maturity and CLI/MCP parity

1. RED tests expand `test_catalog.py`, `test_config.py`, `test_cli_registry.py`, and `test_mcp.py`: exactly one catalog spec per registered tool; maturity classification is valid; config accepts only canonical maturity-compatible tables; CLI/MCP command metadata/options reflect same tool; MCP remains stdio-safe.
2. Add catalog fields and rendering/config validation only after the RED tests demonstrate the gap. Do not re-register tools or create transport forks.
3. For all 32 existing tools, classify actual current behavior; placeholders remain `guarded_placeholder`, report readers remain `report_importer`, and missing research remains `feasibility_gated`.
4. Update catalog, CLI reference, MCP guide, and engines matrix together; add a fixture test preventing a maturity label from contradicting the implementation class.
5. **Acceptance:** CLI and MCP inventory snapshots are equal modulo transport wording; no placeholder is advertised as live.

### 00.6 — dependency lock and compatibility governance

1. RED a direct-dependency policy check: direct runtime/dev/build requirements need exact `==` pins and lock consistency.
2. Pin `[build-system].requires` to the official verified release `hatchling==1.32.0`; verify it by `uv build`. Do not claim `uv.lock` resolves build-system requirements. Regenerate `uv.lock` only if a runtime/dev dependency changes, inspect every change with RTK, and reject unrelated upgrades.
3. Add `docs/DEPENDENCY_POLICY.md`: update cadence, license/security review, lock refresh command, rollback, and external-engine-versus-Rush-dependency distinction.
4. Seed `docs/ENGINE_COMPATIBILITY.md` with existing mature engines and version-output probing rules; each entry names one exact tested version, binary, format, official release source, install source, and safety constraints. Record the reference baseline as Gitleaks `8.30.1` from its official GitHub release.
5. Update CI to run frozen sync and dependency policy validation without installing optional engines.
6. **Acceptance:** clean frozen sync and policy test pass; package/build verification identifies exact build backend version.

### 00.7 — reference adapter proof

1. Use Gitleaks `8.30.1` (official GitHub release verified 2026-08-18) as the reference JSON-capable adapter; record its source/license/version/output/exit/network behavior in `research/engine-records/` and the public compatibility summary before code.
2. Add complete fake-binary fixtures for clean, findings, malformed output, missing engine, version failure, command failure, timeout, and redacted evidence.
3. Apply the shared contract end-to-end: discovery → version → invocation → parser → normalized result → catalog maturity → CLI/MCP → docs.
4. Run independent spec and code/security review; remediate verified findings only.
5. **Acceptance:** this adapter is a copyable, tested template for every later phase and no claim depends on it being installed on the developer machine.

## Test, CI, documentation, and review gates

- Focused: `tests/test_catalog.py`, `tests/test_config.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_engines.py`, new subprocess/result/policy tests.
- Full: project venv Ruff check/format and `pytest tests/ -q`; frozen `uv sync --all-extras --frozen`; package build and `pip-audit` when dependency files change.
- CI: deterministic fixture lane only; optional engine lane may test the one reference binary only if explicitly installed by CI and version recorded.
- Docs: all ADRs, dependency policy, engine compatibility matrix, user-facing maturity labels, config examples, contributor fixture protocol, skip/error troubleshooting.

## Exit criteria / explicit non-goals / rollback

**Exit:** ADRs merged; direct/build dependency policy locked; shared result/subprocess contract tested; one reference live adapter proves all real-integration gates; all existing catalog items truthfully classified; docs/CLI/MCP parity tests pass.

**Non-goals:** adding broad scanner coverage, changing the review UX, running engines by default, adding browser code, auto-installing anything, network listeners, or changing Git/release behavior.

**Rollback:** revert only the Phase 00 scoped commits; preserve old compatible result fields and canonical skipped behavior. If a new field destabilizes clients, remove the additive field and retain parser evidence/ADRs for the next revision.
