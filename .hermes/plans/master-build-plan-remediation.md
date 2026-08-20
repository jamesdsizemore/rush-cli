# Rush expansive scanner remediation — master build plan

> **Planning artifact; implementation is blocked until explicit approval.** This is the single execution contract for the remediation program. It is derived from `.hermes/plans/2026-08-18_152220-expansive-unified-app-review-scanner-plan.md`, which remains the scanner-scope inventory, not the task plan.

**Goal:** Turn Rush’s broad catalog into a truthful, fixture-tested, local-only unified app/code-review product without removing current commands or moving any browser-dependent evidence ahead of the final phase.

**Architecture:** Keep the existing `ToolFn`/`ToolResult` public result shape and one `ALL_TOOLS` registry consumed by CLI and stdio MCP. Every external scanner becomes a narrowly scoped engine adapter with local `PATH` discovery, an explicit bounded invocation through `run_subprocess()`, a parser to normalized findings, canonical skip/error states, and fixture-backed tests. The review coordinator aggregates those unchanged focused tools; it does not duplicate scanner logic in CLI or MCP transports.

**Technology/dependency policy:** Python `>=3.12,<3.13`, `uv`, existing stdio-only `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`, development `pip-audit==2.10.1`, and `ruff==0.16.3`. `uv.lock` is authoritative for Rush runtime/development resolution and must stay synchronized. Phase 00 pins the currently verified PyPI build backend as `hatchling==1.32.0` in `[build-system].requires`; it is verified by an isolated `uv build`, not falsely expected to appear in `uv.lock`. Optional scanners are never Rush dependencies: each has an exact tested engine baseline, release source, install command, output contract, license, and known network/build/write behavior in the engine compatibility documentation.

---

## 1. Scope, hard invariants, and definition of “real”

### Retained product scope

Rush remains one local review product covering quality, format, types, dead code, duplication, complexity, security/SAST, secrets, dependency risk, SBOM/artifacts/licenses/provenance, CI/workflows/IaC/policy/containers/cloud configuration, tests/coverage/mutation/contracts/API/fuzz/load/reliability, documentation/content, language ecosystems, repository health, deterministic source anti-slop, and finally browser/UI/UX/accessibility/visual/runtime/DAST evidence.

No existing tool, scanner family, CLI command, MCP registration, or focused workflow is removed to simplify the program. A command that is catalog-only, route-only, report-only, or guarded-only must be labelled accurately until a real adapter replaces it.

### Non-negotiable safety and truth rules

1. **Local only.** External engines use the existing local resolver (active project virtual-environment Scripts/bin, then `PATH`) only. There is no arbitrary configured executable override. Rush never installs/downloads binaries, package managers, engines, rule packs, vulnerability databases, containers, browser runtimes, or browser bundles.
2. **Bounded execution.** All engine calls use `run_subprocess()` with an argument list, explicit working directory, timeout, `stdin=DEVNULL`, bounded captured output, and redaction before persistence or result emission.
3. **Canonical result.** Keep `ToolResult` in `src/rush/tools/base.py`; every result includes `tool`, `engine`/`version` when known, `status`, `duration`, `summary`, and normalized `findings`. Use deterministic `skipped` for missing engine, inapplicable repository, missing explicit permission, missing report, or unavailable prerequisite; do not report `passed` merely because nothing executed.
4. **One implementation path.** `src/rush/tools/__init__.py` remains the sole registry. `src/rush/cli.py` and `src/rush/mcp.py` invoke the same `ToolFn` implementation; no transport-specific logic.
5. **No hidden side effects.** No VCS rewrite/tag/publish/upload, baseline update, package install, external network listener, or destructive target action without a dedicated explicit flag. MCP stays local stdio JSON-RPC; diagnostics stay on stderr.
6. **Permissioned expensive/network-sensitive work.** Mutation, fuzzing, load, live contract/API, cluster posture, build-dependent semantic analysis, browser, DAST, and baseline mutation require explicit configuration and named opt-in flags. `semantic_drift` retains both `--allow-browser` and `--allow-slow`.
7. **Anti-slop is deterministic policy.** It finds configured, explainable source/DOM/readiness conditions; it never claims to identify an author, model, or AI use.
8. **Browser last.** No browser runtime, Playwright, axe browser flow, Lighthouse, screenshot/visual, responsive, DOM anti-slop, live DAST, or browser dependency is introduced before Phase 8 is accepted.

### “Real integration” gate

A scanner is real only after all of the following are merged and verified:

- local binary discovery and version probe;
- safe bounded invocation with documented input applicability, flags, timeout, working directory, and no implicit install/network/write behavior;
- documented output/exit contract and a parser to Rush normalized findings;
- stable finding identity, severity, rule/category, message, file/line/column/span when supplied, remediation/evidence/provenance metadata, and secret redaction;
- canonical absent-engine, malformed-output, command-failure, timeout/cancellation, invalid-config, and permission-denied behavior;
- `[tools.<name>]` schema validation plus catalog/CLI/MCP parity;
- clean/findings/malformed/error/missing-engine fixtures and focused unit/integration tests;
- source-backed docs/install/compatibility guidance and a bounded CI lane.

A catalog entry, accepted configuration, language route, or report importer alone is not a live integration.

---

## 2. Current seam inventory and planned ownership

| Concern | Current seam | Master rule |
|---|---|---|
| Canonical public result | `src/rush/tools/base.py:ToolResult`, `Finding`, statuses/severity | Extend only compatibly; add fields as optional, serialized deterministically, and cover backward compatibility. |
| Invocation/discovery | `src/rush/tools/common.py:resolve_binary`, `run_subprocess` | Improve centrally before new engines; no adapter owns a divergent subprocess wrapper. |
| Adapter contract | `src/rush/engines/base.py:Engine`, `EngineResult` | Every executable adapter subclasses/uses this contract and is registered through `src/rush/engines/__init__.py`. |
| Existing reference adapters | `gitleaks.py`, `pip_audit.py`, `checkov.py`, `actionlint.py`, `markdownlint.py` | Reuse their patterns only after contract tests capture correct behavior; do not copy ad-hoc parsing. |
| Tool registry and parity | `src/rush/tools/__init__.py:ALL_TOOLS`; `catalog.py`; `cli.py`; `mcp.py` | A tool has one spec/registration and one behavior across interfaces. |
| Configuration | `src/rush/config.py`; `rush.toml` docs/example | Every `[tools.<name>]` maps to `TOOL_SPECS`; unknown tables fail precisely. |
| Review orchestration | `src/rush/tools/review.py`, `common.py`, `routing.py` | Add coordinator/planner behavior here; retain focused tool implementations and deterministic ordering. |
| Placeholder quality tools | `src/rush/tools/quality.py:GuardedQualityTool`; coverage/mutation/e2e/fuzz/load/flaky/snapshot/contract modules | Replace only when an adapter/importer meets the real-integration gate; otherwise keep truthful `skipped`. |
| Tests | `test_catalog.py`, `test_cli_registry.py`, `test_mcp.py`, `test_engines.py`, `test_*_tools.py` | Add shared fixture helpers and preserve required skip tests while adding direct-adapter tests. |
| CI/package gates | `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock` | Split deterministic fixtures from optional installed-engine smoke lanes; no broad installs from Rush. |
| Documentation | `README.md`, `docs/ENGINES.md`, `docs/TOOL_CATALOG.md`, `docs/CONFIGURATION.md`, `docs/CLI_REFERENCE.md`, `docs/MCP.md`, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md` | Documentation ships with each phase; separate user quickstart, operator install guide, adapter compatibility contract, and contributor fixture protocol. |

---

## 3. Required ADR set

Create these ADRs under `docs/adr/` in Program 0. Each ADR must state context, decision, alternatives/rejections, consequences, security/operational impact, compatibility/migration rule, and links to code/tests/docs.

| ADR | Decision that must be frozen before dependent work |
|---|---|
| `0001-external-engine-boundary.md` | Existing local resolver only (active venv Scripts/bin, then PATH); no configured executable override, bundled/auto-installed engines, or implicit network/runtime download. |
| `0002-normalized-finding-and-evidence-model.md` | Stable finding identity, optional location/remediation/evidence/provenance fields, redaction, deterministic ordering/dedupe. |
| `0003-tool-catalog-cli-mcp-parity.md` | One registry/spec and shared implementation; capability/maturity classification is truthful. |
| `0004-subprocess-timeout-cancellation-and-redaction.md` | Argument construction, `DEVNULL`, timeout/cancellation, output cap, stderr/secret handling, exit mapping. |
| `0005-optional-engine-version-compatibility.md` | Version probe, tested version pins/compatibility matrix, deprecated-version warning, docs ownership. |
| `0006-report-import-vs-live-adapter.md` | Imported evidence and executed engines are distinct maturity classes in results/catalog/docs. |
| `0007-slow-network-and-destructive-permissions.md` | Opt-in flags/config, local-safe defaults, artifact containment, baseline mutation rules. |
| `0008-browser-evidence-final-program.md` | Browser/runtime/DAST remains Phase 8 only and cannot create Program 0–7 dependencies. |
| `0009-testing-fixtures-and-optional-ci.md` | Fixture-first adapter test matrix, no accidental host-engine execution, CI lane policy. |
| `0010-review-and-remediation-gates.md` | TDD, independent spec review, independent code-quality/security review, fix/review loop, scoped commit boundary. |

---

## 4. Dependency and version lock plan

### Rush package/build dependency tasks

1. Keep all current direct package constraints exact and retain `uv.lock` as the resolved source of truth.
2. In Phase 0, pin `[build-system].requires` to `hatchling==1.32.0`, verify the build backend with `uv build`, and record that build-system requirements are independently resolved from the project lock. Regenerate `uv.lock` only for actual runtime/development dependency changes and reject unrelated upgrades.
3. Add a deterministic dependency-policy test or CI check that rejects unpinned direct runtime/dev/build requirements, detects runtime/dev `pyproject.toml`/`uv.lock` drift, and separately verifies `uv build` succeeds with the exact build backend declaration.
4. Do not add scanner SDKs to Rush. If a parser needs an optional library, prefer stdlib parsing; otherwise pin it as an explicit Rush dependency with license/security review and an ADR amendment.

### External-engine compatibility pins

Every phase creates/updates `docs/ENGINE_COMPATIBILITY.md` and `research/engine-records/<engine>.md` (local, untracked) before code. The public document records: engine name/binary, **one exact tested version** (no unbounded range), official release source, license, install examples, supported platforms, source input markers, output mode, exit codes, default network/cache/build/write behavior, Rush flags/timeout, known incompatibilities, and last verification date. `research/` may contain raw official evidence but is never staged.

No phase may call an unverified candidate “supported.” At most it may be “feasibility-gated” with the missing proof spelled out.

---

## 5. Universal task protocol — mandatory in every phase plan

### Start gate (before the first source edit)

1. `rtk git status --short`, `rtk git status -sb`, and `rtk git log -3 --oneline`; record unrelated modified/untracked paths and exclude them.
2. **Graft discovery:** `graft map`/`graft ask`/`graft grep` to identify exact files, tool registration, config schema, engine callers, relevant tests, and affected docs. Rebuild/check graph when imports/call wiring are implicated.
3. **context-mode understanding:** index only the discovered source + tests + relevant plan/ADR/docs; query the result schema, safety contract, and call path. Record the query and returned seam in the phase evidence log.
4. **RTK exact inspection:** use `rtk read` and narrow `rtk rg` against only the paths found above. Read `AGENTS.md` and the phase plan’s prior-phase acceptance evidence.
5. Verify the exact engine contract from official documentation/release notes; record it in local research before choosing command/output behavior.

### Per vertical-slice task (2–5 minute actions)

1. Write one focused failing fixture/unit/contract test; run it with the project interpreter and record the expected RED failure.
2. Implement the smallest compatible change in the owned seam; no side refactor or unapproved dependency.
3. Run the focused test to GREEN, then a focused format/lint check.
4. Update the corresponding user/engine/config/architecture documentation in the same slice.
5. Re-run Graft callers/check when wiring changed; context-mode query the changed contract; use RTK diff/read to inspect only the changed lines.
6. Add the slice’s evidence and error/recovery entries to the phase plan’s implementation ledger.

### Mandatory code-review/remediation loop

After each coherent adapter/tool slice and before its commit:

1. **Author self-review:** `rtk git diff -- <owned paths>`; inspect argument safety, secret redaction, result status mapping, registry/config/docs parity, tests, and no hidden side effects.
2. **Independent spec-compliance review:** fresh reviewer checks the diff against the phase acceptance criteria and ADRs. Any missing requirement blocks the slice.
3. **Independent code-quality/security review:** fresh reviewer checks security, parsing, error paths, compatibility, test isolation, and maintainability. Fail closed if review evidence is malformed/unavailable.
4. **Targeted remediation:** a separate fix pass addresses verified findings only; rerun RED/GREEN and both reviews. Maximum two repair cycles, then record remaining blocker precisely for user decision.
5. **Pre-commit gate:** stage only owned paths; run cached diff inspection/security scan, test/lint/format/diff/graph gates; do not include `research/`, unrelated docs, rejected drafts, or generated artifacts.

### Finish gate (after phase acceptance)

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
.venv/Scripts/python.exe -m pytest tests/ -q
git diff --check
rtk git diff --stat
graft --dir .hermes/graft build . >/dev/null
graft --dir .hermes/graft check .
```

Then use RTK to inspect `git status --short`, the staged scoped stat, and `git diff --cached --check`; use Graft to confirm changed registrations/callers; use context-mode to reindex/query the updated seam and phase plan. Commit only after all phase criteria pass. Never push, merge, tag, publish, or stage `research/` without explicit user instruction.

---

## 6. Canonical dependency-ordered phase plan set

The master is written first; the individual plans below are derived from it and cannot change these boundaries without an ADR amendment and user approval.

| Phase plan | Depends on | Delivers | Explicit exclusions |
|---|---|---|---|
| `phase-00-foundation-and-truth.md` | none | result/evidence/maturity contract, ADRs, dependency lock policy, shared fixture/subprocess/capability plumbing, docs skeleton | no new browser/runtime engine; no misleading catalog claim |
| `phase-01-core-code-security-workflow.md` | 00 | core source/SAST/secrets/dependency/workflow/source-policy adapters and real review aggregation | no IaC, artifact, advanced reliability, or browser work |
| `phase-02-iac-policy-content.md` | 00–01 | IaC/config/policy/container/template/SQL/document quality adapters | no browser/runtime execution |
| `phase-03-supply-chain-artifacts-posture.md` | 00–02 | OSV/SBOM/vulnerability/license/provenance/repository posture/artifact evidence | no browser/runtime execution |
| `phase-04-nonbrowser-test-reliability.md` | 00–03 | coverage/mutation/contract/API/property/fuzz/load/flaky/snapshot report/live contracts behind permissions | no E2E browser, visual, Lighthouse, DOM, DAST |
| `phase-05-language-semantic.md` | 00–04 | language-native and feasibility-gated semantic adapters with project-marker routing | no browser/runtime execution |
| `phase-06-review-governance.md` | 00–05 | capability detection, planner, coordinator, finding lifecycle/freshness/dedupe/governance | no browser/runtime execution |
| `phase-07-advanced-nonbrowser-posture.md` | 00–06 | cluster/repository/artifact/workflow posture and imported evidence that is non-browser | no browser/runtime execution |
| `phase-08-browser-evidence-last.md` | 00–07 + explicit user approval | Playwright, a11y, UI/UX, visual, performance, DOM anti-slop, browser E2E, DAST | cannot start early; no browser install/download or unsafe target action |

A phase is not a timebox. It is a complete vertical contract: source, tests, engine evidence, docs, review/remediation evidence, CI lane, and scoped Git boundary.

---

## 7. Cross-phase data/API contracts

### Finding identity and evidence

Program 0 freezes a deterministic fingerprint from scanner/tool name, engine rule ID, normalized location, and stable message/category material. The model must preserve raw engine identifiers separately from Rush severity/category. Findings must carry optional `location`, `rule_id`, `severity`, `message`, `remediation`, `evidence`, `provenance`, `fingerprint`, and `freshness` fields without breaking existing consumers. Secrets never appear in message/evidence; use `[REDACTED]` while retaining a non-sensitive identity where feasible.

### Status mapping

Phase 00 preserves the existing public `ToolStatus` literal exactly: `ok`, `warn`, `fail`, `error`, and `skipped`. It does not introduce `passed`, `findings`, `cancelled`, or `timed_out` as result statuses.

- `ok`: engine completed with no policy-relevant normalized findings.
- `warn`/`fail`: engine completed and supplied valid normalized findings; the configured documented policy selects the severity threshold. A valid nonzero findings exit is never automatically an `error`.
- `skipped`: deterministic nonexecution; includes `reason`, prerequisite, and installation/configuration hint when safe.
- `error`: invocation/parser/internal failure; includes safe diagnostics and does not masquerade as a clean scan.
- timeout/cancellation are represented as `error` plus additive deterministic execution metadata (`terminal_reason` and `partial`); partial evidence is labelled partial, never successful.

### Config and capability state

Every tool config has explicit defaults, validation, scope/target containment, timeout/resource fields where appropriate, and an opt-in token for slow/network/build/destructive operation. `rush capabilities` reports configured/installed/applicable/blocked/missing separately. `rush plan` returns selected, skipped, blocked, and feasibility-gated scans in deterministic order.

### Documentation model

Each live adapter updates: user guide/CLI reference; tool catalog maturity table; engines install/compatibility document; configuration schema/example; architecture/ADR link; contributor fixture/release/CI instructions; troubleshooting skipped/error/timeout cases. Every report importer says it consumes pre-existing evidence and does not execute the engine.

---

## 8. Required test and CI topology

1. **Unit/parser fixtures:** valid clean/findings, malformed structured output, missing fields, parser version drift, location/severity normalization, secret redaction.
2. **Adapter invocation tests:** argument vector, cwd, timeout, `DEVNULL`, no shell, absent binary, version probe, nonzero exit, cancellation/timeout, forbidden permission/network/build/baseline write.
3. **Tool/config tests:** routing/applicability, `rush.toml` parsing, invalid schema, status mapping, dedupe/order/fingerprint.
4. **Parity tests:** every `TOOL_SPECS` entry is registered, CLI subcommand/options match tool metadata, MCP tool/schema invokes identical implementation, stdio stays clean.
5. **Integration fixtures:** fake executables/reports through actual adapter path; no dependency on host-installed engines. Optional real-engine smoke tests are marker-gated and never the sole proof.
6. **CI lanes:** deterministic fixtures on all supported CI platforms; representative PATH-engine lane only for a small, declared set; separate manual/dispatch-only slow lane; browser lane exists only in Phase 8 after approval.
7. **Release gate:** frozen lock, package build, pip-audit, test/lint/format, diff checks, catalog/CLI/MCP inventory, scoped review evidence, and documented expected optional-engine skips.

---

## 9. Program-level acceptance and rollback boundaries

- Phase 0 accepts only when the first adapter can prove the full contract end-to-end and the catalog distinguishes live/placeholder/importer/feasibility-gated maturity.
- Phases 1–7 accept only when all claimed adapters meet the real-integration gate, their docs match behavior, and review aggregation retains existing focused results.
- Phase 8 accepts only with explicit opt-in, local target containment, artifact sanitization, no browser/download/install, and no visual baseline mutation without `--accept-baseline`.
- On regression, revert only the scoped phase commit(s); preserve the canonical skipped fallback and documented engine compatibility evidence. Never erase another phase’s fixtures, catalog entries, or docs to achieve a green test.

## 10. Approval and handoff

**Planning deliverables:** this master plus the nine phase plans. They are executable specifications, not permission to alter production code.

**Implementation authorization required:** explicit approval of this plan package and the first phase. On approval, begin Phase 00 only, execute its Git start gate, and do not parallelize a dependent phase before predecessor acceptance is recorded.
