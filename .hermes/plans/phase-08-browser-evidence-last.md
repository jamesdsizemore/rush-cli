# Phase 08 — browser evidence, UI/UX, accessibility, visual, E2E, performance, DOM anti-slop, and DAST — LAST

> **Depends on:** Phases 00–07 accepted, including Phase 07's permissioned
> execution/evidence contract, **and a new explicit user approval.** This phase
> cannot begin early or change the accepted non-browser contracts.

**Objective:** Add bounded, local, opt-in runtime evidence to the completed non-browser review product: route/runtime failures, accessibility, responsive/keyboard UX, visual comparison, performance, deterministic DOM readiness policy, browser E2E, and safe local DAST.

## Start conditions and compact workflow

Before any source edit, RTK must prove all predecessor plan acceptance records and clean scoped Git boundary. **Graft** discovers only current runtime-placeholder seams (`tools/e2e.py`, `visual.py`, guarded quality base, review coordinator, config/catalog/CLI/MCP and test callers) and determines no earlier phase implementation duplicated browser logic. **context-mode** indexes Phase 08, ADRs 0001/0004/0007/0008/0009, those source/tests and queries target containment, artifact redaction, lifecycle, cancellation, a11y/visual result mapping. **RTK** reads exact blocks and validates every claimed dependency/output with pinned official evidence. Per slice: RED→GREEN→docs→self review→fresh spec review→fresh security/quality review→targeted fix/re-review; start/end Git and Graft check after wiring changes.

## Preconditions and dependency pins

- Playwright/axe/Lighthouse/pixelmatch/Pa11y/Accessibility Insights/Nuclei/ZAP candidates require a public compatibility entry with exact tested version or range, binary/dependency discovery, license, output/exit, browser/runtime/install behavior, platform support, timeout/artifact and network model. Each execution declares `executed`, `imported`, or `artifact` evidence under the Phase 07 result contract.
- Rush never runs `npx` installer, browser installer, `playwright install`, package manager, container, image pull, scan update, or target server. Missing dependency/runtime is `skipped` with safe install guidance.
- A target must be explicit (`--url` or declared local lifecycle command), contained by an allowlist, and local by default (`localhost`, loopback or configured private address). Non-local targets require explicit `allow_network` plus configuration. Browser/download/cache/build/slow/artifact-write effects use the shared Phase 07 per-invocation permission model; a user may choose them explicitly, but a discovered project config cannot silently grant them. Never send credentials; redact headers/query/body/cookies/artifacts.

## Owned seams

- Create only after feasibility: `src/rush/engines/playwright.py`, `axe.py`, `lighthouse.py`, `pixelmatch.py`, `nuclei.py`, `zap.py`; `src/rush/review/runtime.py`, `accessibility.py`, `responsive.py`, `visual.py`, `performance.py`, `dom_policy.py`, `artifacts.py`, `lifecycle.py`.
- Modify only as needed: `tools/e2e.py`, `visual.py`, `review.py`, `quality.py`, `common.py`, `base.py`, `catalog.py`, `config.py`, `cli.py`, `mcp.py`, `tools/__init__.py`.
- Add fixture-only tests: `test_browser_policy.py`, `test_runtime_review.py`, `test_accessibility_review.py`, `test_visual_review.py`, `test_performance_review.py`, `test_dast_policy.py`; reuse catalog/CLI/MCP parity suites.
- Docs: runtime prerequisites/permissions/local target examples, engine compatibility, artifact retention/redaction, a11y/visual interpretation, DAST safety, troubleshooting; update ADR 0008.

## Task-based delivery

1. **Policy/lifecycle before engine:** RED tests reject missing `allow_browser`, missing `allow_slow` where required, unapproved target, non-local target without network permission, absent browser/runtime, undeclared start command, unsafe env/credentials, artifact escape, and implicit baseline write. Implement contained target parser, process lifecycle with strict command/timeout/readiness/termination, and sanitized artifact manifest; no scanner yet.
2. **Playwright runtime evidence:** research/prove local binary/dependency resolution, trace/screenshot behavior and JSON/JUnit output. Fake fixtures cover clean, page error, console error, failed same-origin asset, navigation timeout, malformed report, missing runtime, cancellation. Normalize URL/title/route/error evidence without sensitive request data.
3. **Accessibility and UX:** add axe only after version/output injection/CLI safety is proven. Implement keyboard/focus/landmark/contrast/responsive route checks as deterministic evidence, not aesthetic score. Require explicit viewport/route/journey configs; inaccessible route findings include selector/impact/help URL when safe.
4. **Visual/performance/DOM policy:** screenshot comparison requires an explicit user-owned contained baseline. Default is compare-only; creation/update needs `--accept-baseline`. Pixel diff stores sanitized metrics/artifact paths. Lighthouse runs local target only with explicit slow/browser gates. DOM anti-slop uses configurable, explainable missing-state/placeholder/empty-action/design-token rules and never claims authorship/AI detection.
5. **Browser E2E:** run only a declared local suite/route journey under `allow_browser`, resource/time/trace limits. No auto-discovery that clicks destructive actions; interaction DSL defaults to read-only navigation/assertion and requires per-action opt-in.
6. **DAST:** Nuclei/ZAP require explicit `allow_network`, local default target, request/host allowlist, rate/request/concurrency bounds, passive/safe-template default, and the matching download/cache permission for template/database refresh. No authenticated scanning or exploit/destructive templates occurs unless separately approved. Parse executed output or imported reports with truthful mode metadata and safe severity/rule/location/evidence redaction.
7. **Integration/review:** register each proven tool once, ensure capabilities/planner labels browser prerequisite/blocked state, preserve non-browser review results, add CI fixture lane only (optional manual local runtime smoke). Conduct independent privacy/security review of target and artifacts plus spec review of browser-last compliance; remediate and rerun both.

## Failure semantics and acceptance

Missing engine/browser/target/config/permission → `skipped`; malformed output, lifecycle fault, unsupported engine version → `error`; timeout/cancelled gives partial marked evidence; no browser result may overwrite a non-browser result.

**Accept when:** browser work is still last; every live adapter meets the Phase 07 permission/evidence gate; default command cannot start/download/install/scan a remote target/update baseline; an explicitly consented command may perform only its documented effect; target/artifact/redaction tests pass; CLI/MCP/catalog/docs agree; full project/graph/context/diff/review gates pass.

**Non-goals:** hosted/local model features, automatic remediation, production deployment, auth scanning, generic web crawling, auto browser/package install. **Rollback:** revert only Phase 08 commits and retain prior complete non-browser review behavior.