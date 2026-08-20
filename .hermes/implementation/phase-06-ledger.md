# Phase 06 implementation ledger — review intelligence and governance

Authorization: user-approved on 2026-08-19.
Scope: complete only fixture-backed, non-browser review orchestration and evidence
lifecycle behavior. No URL launch, browser process, DOM/visual/a11y/performance/DAST
integration, engine installation, network access, or default baseline writes.
Protected: Phase 07–08 plans and `research/` remain untracked and unstaged.

## Baseline

- Phase 06 began on `main` after `b8e3b66 feat: add contained CodeQL SARIF importer`.
- RTK, Graft, and context-mode located existing read-only capabilities/planning,
  shared aggregation, review wiring, CLI/MCP paths, and fixture tests.
- Existing capabilities and planner are retained as non-executing surfaces; browser
  runtime tools remain blocked and excluded from the non-browser planner.

## Error register

| Timestamp | Attempt | Error | Recovery |
|---|---|---|---|
| 2026-08-19 | Documentation ADR file search | The filesystem search used an unsupported native Windows path and found no files; it did not modify the repository. | Use the repository-relative RTK/context-mode discovery paths for ADR and documentation inspection. |
| 2026-08-19 | Graft lifecycle search | The local Graft CLI accepts one query and one path; the command supplied two source paths and returned an argument error. | Query the repository root once per lifecycle symbol, then rely on bounded RTK reads for exact implementation details. |
| 2026-08-19 | ADR-0002 aggregation RED test | A review child finding without an engine-provided fingerprint raised `KeyError`, so coordinator output did not yet honor the normalized-finding identity contract. | Reuse the common redaction-safe SHA-256 identity helper in review aggregation and retain provenance/dedupe behavior. |
| 2026-08-19 | Focused routing format gate | Ruff accepted imports and syntax but required one deterministic multiline assertion wrap in the new lifecycle contract. | Apply Ruff's exact test-only formatting diff, then rerun the focused routing gate. |
| 2026-08-19 | ReviewTool ADR-0002 RED test | Direct heuristic review findings lacked fingerprint fields, so the user-facing review path diverged from normalized engine and aggregate evidence. | Stamp each direct review finding with the shared deterministic helper before deriving review status. |
| 2026-08-19 | Capability installed-state RED test | The new fixture could not patch `shutil.which` because capability detection had no PATH inspection yet; the test made the absent read-only installed-state seam explicit. | Add catalog-backed `shutil.which` detection only, then validate configured, installed, applicable, blocked, and missing states without spawning or probing engines. |
| 2026-08-19 | Lifecycle/coordinator RED test | Routing-test collection failed because no baseline builder or explicit-baseline aggregation parameter existed. | Add a pure, in-memory fingerprint baseline builder; label review evidence as `existing`, `new`, or `unknown`; record serial child status evidence and partial outcomes without writing any baseline. |
| 2026-08-19 | Lifecycle focused format gate | The lifecycle tests and static lint passed, but Ruff required only deterministic wrapping of the explicit-baseline metadata expression, baseline builder, and test name. | Apply Ruff's supplied formatting-only diff and rerun the focused lifecycle gate. |
| 2026-08-19 | Capability CLI malformed-config RED test | `rush capabilities` let `RushConfigError` escape and Click returned exit 1 rather than a user-facing usage error. | Handle local configuration errors in both capability inventory and planning commands, matching the shared tool runner's exit-2 behavior. |
| 2026-08-19 | Phase 06 documentation bundle patch | The change log anchor was ambiguous, so the multi-file patch was rejected before any file changed. | Re-read each affected documentation section, preserve independently modified wording, and apply context-specific documentation patches. |
| 2026-08-19 | Planner prerequisites RED test | A deterministic CodeQL plan step did not expose its report dependency, leaving automation unable to explain prerequisite evidence. | Add catalog-derived, read-only prerequisites to every plan step; importer steps name their accepted local report evidence and engine-backed steps name known local engines. |
| 2026-08-19 | Explicit review-scope RED tests | `ReviewTool.run()` accepted no changed-file input, so review necessarily scanned the full target and had no target-containment contract for supplied scope. | Add an opt-in changed-file list to the shared review implementation, CLI, and MCP callable; only supplied files constrain scope and out-of-target paths return structured errors. |
| 2026-08-19 | Explicit-scope GREEN test fixture | The selected test source did not trigger the current heuristic set, so the assertion expected `warn` from a clean result. | Put a deterministic TODO-density signal only in the selected file, then retain the assertion that the unselected file produces no evidence. |
| 2026-08-19 | Explicit-scope format gate | Focused review tests and lint passed, but Ruff requested line wrapping only. | Apply the formatter's exact no-semantic-change layout, then rerun the slice gate. |
| 2026-08-19 | Explicit-scope CLI RED test | Click rejected `--changed-file`, so the new review scope could not be supplied through the public CLI. | Add a repeatable CLI option and forward only nonempty values through the shared `ReviewTool` path; retain the same JSON-safe parameter on MCP. |
| 2026-08-19 | Explicit-scope CLI GREEN gate | The scoped review correctly produced advisory evidence, and the CLI maps its `warn` result to process exit 1; the fixture incorrectly expected exit 0. | Inspect the shared status-to-exit implementation, make the test assert the actual contract, and reconcile the conflicting public exit-code documentation. |
| 2026-08-19 | Empty explicit-scope RED test | The no-target early return discarded supplied scope metadata, making an explicit non-Python scope indistinguishable from a whole-target no-file review. | Carry the same scope descriptor through the no-target structured result. |
| 2026-08-19 | Post-scope focused format gate | The 39-test focused suite and Ruff lint passed; Ruff format requested only wrapping in the new CLI integration fixture. | Apply the formatter's no-semantic-change layout and rerun the focused gate before broader verification. |
| 2026-08-19 | Review repair-evidence RED test | Direct heuristic findings had path/line data but no canonical source-location evidence object for a repair consumer. | Add a redaction-safe local source-location evidence packet to direct findings only when no engine/Graft evidence already exists. |
| 2026-08-19 | Broad Markdown validation command | Full regression, Ruff, and CLI smoke checks passed, but the final inline Python link checker received literal `\n` escapes and stopped with `SyntaxError` before validating links. | Run the same local-link check through the code execution helper with real Python statements; do not treat the failed shell quoting as a documentation failure. |
| 2026-08-19 | Repository link-check scope | The corrected checker scanned `.venv` vendor documentation and reported two third-party relative links. | Restrict validation to repository documentation/Markdown while excluding generated virtual-environment files; then inspect only first-party broken links. |

## Verification and review evidence

- Fixture RED→GREEN contracts covered direct and aggregate fingerprints,
  in-memory baseline freshness, partial child evidence, read-only PATH/config
  inventory, deterministic prerequisites, malformed config, CLI/MCP scope
  forwarding, target escape rejection, empty explicit scope, and repair evidence.
- Focused Phase 06 suite: `39 passed in 3.25s`; focused Ruff lint passed and
  `10 files already formatted`.
- Full repository gate: `208 passed, 7 skipped in 6.31s`; the seven skips are
  documented optional static-engine absences (mypy, tsc, vulture, knip, radon,
  jscpd, sloppylint), not test failures.
- Full Ruff gates passed: `All checks passed!`; `127 files already formatted`.
- CLI smoke checks passed for `review --help`, `capabilities --json`,
  `plan --profile nonbrowser --json`, and explicit-scope JSON review. The last
  deliberately returned exit 1 because advisory `warn` maps to exit 1.
- First-party Markdown local-link validation passed for `278` files after
  excluding `.venv`, `.git`, and protected local research material.
- Graft graph rebuild/check and final caller searches for `changed_files` and
  `build_finding_baseline` passed. Context-mode indexed final review/capability
  seams and retrieved Phase 06 architecture/ADR evidence. RTK bounded status,
  search, and diff review was used throughout.
- Independent final review passes examined (1) implementation/test contracts
  for status preservation, containment, deterministic identity, and no implicit
  execution/write path, and (2) CLI/MCP/user/developer/ADR/governance documents
  for truthful parity. No unresolved defect was found.
- Staged Phase 06 review contains only the 28 listed Phase 06 implementation,
  tests, ledger/plan, and documentation files. `git diff --cached --check`
  passed; protected Phase 07/08 plans and `research/` remain unstaged.

## Commit readiness

Phase 06 is ready for its scoped commit. It adds no browser/runtime execution,
network access, engine installation/version probe, Git-diff inference, or
baseline persistence.
