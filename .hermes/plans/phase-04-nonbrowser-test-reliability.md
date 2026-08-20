# Phase 04 — non-browser test quality and reliability

> **Depends on:** Phases 00–03. **Hard exclusion:** no Playwright/browser/E2E/visual/Lighthouse/DOM/DAST implementation.

**Objective:** Complete truthful contained report importers for non-browser test
and reliability evidence. Live execution remains feasibility-gated until a
separate versioned engine, permission, bounded-command, and fake-process contract
is approved.

## Development protocol

Per task: RTK Git start/end; **Graft** discovers `GuardedQualityTool`, coverage/mutation/contract/fuzz/load/flaky/snapshot/pbt modules, common/engine/config/registry callers and `test_test_quality_tools.py`; **context-mode** queries guarded status, permission, report, timeout and result contracts; **RTK** reads exact seams, diffs and runs project-venv tests. RED→GREEN→docs→self/spec/security review→targeted remediation→re-review; Graft build/check for new registrations.

## Owned interfaces and candidates

| Tool family | Required behavior | Candidate gate |
|---|---|---|
| Coverage | Import coverage.py JSON, LCOV, and Cobertura XML; never runs tests. | A separate declared-command coverage adapter with `allow_slow`, bounded args/cwd/timeout, and fake-process fixtures. |
| Mutation | Import a contained JSON summary; never runs a mutation engine. | mutmut/Stryker versioned structured output, sandbox behavior, and explicit slow-run contract. |
| Contract/API | Import a contained Pact summary; never contacts a provider or broker. | Schemathesis/Pact local-command, target containment, and network-permission evidence. |
| Property/fuzz | Import seeded property/fuzz JSON; never executes a test or fuzzer. | Versioned local seed/time/corpus command contract with no implicit build/download. |
| Load | Import a local summary; never sends traffic. | k6/Locust target allowlist, users/duration limits, and network-permission evidence. |
| Flaky/snapshot | Import JUnit duplicate-case/comparison evidence; never changes a baseline. | Stable report-version evidence and an explicit baseline-write contract, if ever implemented. |

## Task plan

1. Verify importer maturity and the Phase 00 distinction: importers do not launch
   engines, while still-unsupported browser tools remain guarded and skipped.
2. Implement contained readers per supported report format with clean/findings,
   malformed, missing, and path-escape contracts. Readers retain local evidence
   provenance and do not emit report bodies or secret values.
3. Deliver coverage first, then mutation, contract, property, fuzz, load, flaky,
   and snapshot importers through the shared CLI/MCP registry.
4. Keep all live candidates out of the implemented surface. A later proposal must
   add its named opt-in, target/resource limits, cancellation behavior, no-download
   policy, fake executable fixtures, and fresh approval before promotion.
5. Make importer versus execution boundaries explicit in catalog, CLI/MCP help,
   capability planning, compatibility records, user documentation, troubleshooting,
   and the Phase 04 ledger.
6. Review command injection, resource exhaustion, target scope, report parsing,
   path containment, and accidental host-engine execution; remediate verified
   findings and rerun the full gates.

## Required tests/acceptance

Fixtures cover clean/findings, malformed, missing, and path-escape inputs for
each importer; coverage additionally proves coverage.py JSON, LCOV, and Cobertura
XML, and flaky proves duplicate JUnit evidence. The generic CLI and stdio MCP
share the same `ALL_TOOLS` registrations. Since this phase implements no external
engine execution, nonzero/timeout/cancelled/fake-binary tests belong to a future
live-adapter proposal rather than being simulated as importer behavior. CI runs
the deterministic importer matrix only.

**Exit:** no claimed live quality tool is a `GuardedQualityTool`; remaining unsupported tools are honestly guarded/importer/feasibility-gated. **Non-goals:** browser E2E, visual screenshot, accessibility, web performance, browser DAST. Rollback restores truthful skip/import behavior.