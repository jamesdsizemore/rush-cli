# Phase 00–02 implementation ledger

**Authorization:** user-approved on 2026-08-18.
**Scope:** implement `phase-00-foundation-and-truth.md`, then Phase 01, then Phase 02.
**Protected:** pre-existing uncommitted documentation drafts, all rejected research, and every later-phase plan remain out of scope and unstaged.

## Baseline

- Git: `main` equals upstream (`0 0`); pre-existing docs/plans/research are untracked or modified.
- Tests: `112 passed, 7 skipped` using `.venv/Scripts/python.exe -m pytest tests/ -q`.
- Quality: Ruff check and format check passed.
- Graft: source graph exists; Phase 00 seam discovery complete.
- context-mode: repository indexed as `rush-phase00-implementation`.

## Backlog and execution order

- [x] **00.1** Create ADR set and implementation-facing policy documentation.
- [x] **00.2** Add the Phase 00 test contract and verify each RED→GREEN slice.
- [x] **00.3** Add compatible normalized finding/evidence fields, deterministic ordering/fingerprints, and execution metadata.
- [x] **00.4** Centralize bounded subprocess/version probing and preserve resolver-only discovery.
- [x] **00.5** Add truthful catalog maturity, configuration invariants, CLI/MCP presentation, and 32-tool audit.
- [x] **00.6** Pin build backend and document dependency policy; validate isolated build.
- [x] **00.7** Validate Gitleaks reference adapter contract/fixtures and public documentation.
- [x] **01** Truth audit, coordinator preservation, and opt-in deterministic source-policy slice accepted; unsupported engines remain feasibility-gated.
- [x] **02** Inventory complete; accepted TFLint, Checkov, Hadolint, actionlint, and markdownlint adapters meet individual evidence gates; all remaining Phase 02 candidates have documented feasibility decisions.
- [x] **Final** Application docs, full quality gates, Graft/context-mode/RTK review, backlog update, and end Git inspection completed.

## Verified issues

| ID | Evidence | Required recovery |
|---|---|---|
| P00-001 | `Engine.version()` calls `subprocess.run()` directly. | Route it through the shared bounded subprocess helper and add timeout/malformed-output tests. |
| P00-002 | `ToolResult` has only generic `metadata`; `Finding` lacks normalized evidence identity fields. | Add compatible optional schema fields plus deterministic helper/test coverage. |
| P00-003 | `ToolSpec` has no maturity classification. | Add a truthful enum and classify all catalog entries without relabelling placeholders as live. |
| P00-004 | `[build-system].requires = ["hatchling"]` is unpinned. | Pin `hatchling==1.32.0`; validate `uv build`; do not claim it is in `uv.lock`. |
| P00-005 | Existing `slop` catalog text claims AI detection. | Replace with deterministic source/readiness policy language; never infer authorship or model use. |
| P01-001 | Engine-backed commands were labelled `real_adapter` without a deterministic parser-fixture registry. | Downgrade unsupported claims to `feasibility_gated`; register only fixture-proven adapters. |
| P02-001 | `iac` routed both TFLint and Checkov without a Phase 02 structured parser fixture suite. | Resolved: both routes now have independent local JSON fake-process suites and shared deterministic aggregation coverage. |
| P02-002 | Checkov `3.3.9` lacked exact local JSON/exit/no-download/network/cache/write/Windows evidence. | Resolved: pinned official source establishes `--directory`, Terraform-only JSON output, `--skip-download`, `--download-external-modules false`, exit `0`/`1`, and no-default-config behavior; Rush uses a credential-free allowlisted child environment and fixture coverage. |
| P02-003 | KICS `2.1.21` has only release/license and source-tree discovery evidence. | Keep it feasibility-gated: require a versioned write-free local JSON command, exit/config/cache/network/Windows evidence, a bounded Rush seam, and a fake-process reference suite before any route or catalog promotion. |
| P02-004 | Conftest `0.69.0` offers local JSON but defaults to `policy` and all capabilities; `--update` can fetch remote policies. | Keep it feasibility-gated until an explicit contained policy/data/capabilities config contract blocks network-capable Rego built-ins and has no-update fake-process/Windows evidence. |
| P02-005 | Spectral `6.16.3` accepts URL rulesets and custom resolvers; the inherited adapter used text output. | Resolved: the YAML route supplies a Rush-owned static no-extends ruleset, JSON output, explicit local paths, no resolver/output flags, and preflight blocks remote `$ref` values. Fixture ownership proves argv, findings, malformed/inconsistent output, and remote-reference containment. |
| P02-006 | Hadolint inherited text output and implicit project/home/environment configuration. | Resolved: pinned `2.15.1` JSON adapter supplies Rush-owned empty config and allowlisted environment; fixture suite proves argv, normalization, malformed output, and exit consistency. |
| P02-007 | SQLFluff `4.3.0` can discover project config/plugins and its dbt templater can require database access through profile/environment fallbacks. | Resolved: the SQL route uses `--ignore-local-config`, owned config, ANSI dialect, raw templater, JSON output, and one process; it never enables dbt, fix, output writes, or project config discovery. Fixture ownership proves argv, JSON findings, malformed output, and exit consistency. |
| P02-008 | djLint `1.44.2` has no documented JSON output and permits project custom Python rules. | Keep it feasibility-gated until a non-executable local profile/config contract and stable machine-output/exit fake-process suite exist. |
| P02-009 | kubeconform `0.8.0` defaults to `master` Kubernetes schemas and HTTP schema resolution/cache. | Defer to Phase 07: it needs a versioned local schema corpus, explicit `-schema-location`, multi-document containment, JSON fixtures, and Windows/CI evidence before YAML promotion. |
| P02-010 | actionlint inherited text parsing, implicitly discovered config, and could spawn shellcheck/pyflakes. | Resolved: pinned `1.7.12` JSON adapter supplies an empty config, disables child integrations, and has deterministic fixture ownership. |
| P02-011 | Markdown routed to unpinned `markdownlint-cli2` text parsing despite the Phase 02 `markdownlint-cli 0.49.1` baseline. | Resolved: pinned JSON adapter supplies owned JSON config/ignore files and does not enable fix, custom-rule, or output-file behavior. |
| P02-012 | ansible-lint `26.8.0` can create a project `.cache` and upstream warns linting untrusted content can execute code; Rush has no dedicated Ansible containment/config contract. | Keep feasibility-gated. Require a dedicated tool, read-only cache location/no-write proof, controlled `ANSIBLE_CONFIG`/vault environment, contained project-root semantics, and JSON/SARIF fake-process plus Windows evidence. |
| P02-013 | codespell `2.4.3` has no documented structured JSON report and automatically reads project `pyproject.toml` before `--config`; Phase 02 forbids a generic content catch-all. | Keep feasibility-gated until a focused command, project-config suppression contract, stable parser/exit fixtures, and catalog/docs ownership are approved. |
| P02-014 | Vale `3.17.1` defaults to global config/styles discovery, errors without configuration, and `vale sync` creates/removes style paths and downloads packages. | Keep feasibility-gated until a focused prose tool owns a versioned local config/style corpus, disables global/project lookup and sync/download, and proves JSON/exit behavior with Windows fixtures. |
| P02-015 | Lychee `0.24.2` is a link checker whose useful live checks require network access; Phase 02 expressly prohibits live checking without a dedicated permission ADR. | Keep feasibility-gated and do not create an inert link command. Future work needs explicit network permission, target/privacy/redirect/timeouts/rate-limit/cache rules, or separately labelled imported reports. |

## Error register

| Timestamp | Attempt | Error | Recovery |
|---|---|---|---|
| 2026-08-18 | Final plan validator through sandbox `read_file` | Sandbox could not resolve the repository path; no code defect. | Replaced with a repository-local invariant command; it passed. |
| 2026-08-18 | Untracked Markdown `git diff --no-index --check` wrapper | Checkout CRLF warning produced exit 3 despite no whitespace finding. | Used bounded whitespace/invariant validation instead; no retry of the same wrapper. |
| 2026-08-18 | `common.py` Phase 00 patch | Two ambiguous context hunks were rejected without modifying the file. | Re-read the complete module and atomically rewrote the bounded module; focused RED→GREEN test then passed. |
| 2026-08-18 | RTK/doc search | `rtk search` is not an RTK command; a native-path docs search also failed. | Used `rtk --help`, Graft, context-mode, and bounded reads; no source inference came from failures. |
| 2026-08-18 | Phase 02 context-mode query | A compound query caused shell parsing error near `do`; no repository action ran. | Retried a simplified bounded query; it confirmed Checkov has no approved independent evidence gate. |
| 2026-08-18 | Phase 00 test formatting | Ruff reported import grouping in `test_dependency_policy.py`; one fuzzy whitespace edit duplicated `ROOT`. | Re-read the exact block, removed the duplicate immediately, then verified Ruff check/format and policy tests passed. |
| 2026-08-18 | Phase 01 coordinator full gate | Global aggregate sorting changed TestTool's documented language-engine label from `go-test+cargo-test` to `cargo-test+go-test`. | Restricted canonical child sorting to review coordination; tool-specific routing retains its declared deterministic order. |
| 2026-08-18 | Phase 02 Checkov Graft query | A single-quoted query containing `Checkov's` caused shell quote termination; no repository action ran. | Used an apostrophe-free bounded query and direct source reads. |
| 2026-08-18 | Phase 02 documentation lookup | Native Windows paths were rejected by the repository search tool; no source inference came from the failure. | Re-ran bounded searches with repository-relative paths. |
| 2026-08-18 | Phase 02 Vale upstream lookup | The `v3.17.1` tag resolved directly to a commit, so an annotated-tag API request returned 404; a later jq regex was also malformed. | Used the direct ref, versioned raw sources, and bounded grep; no repository file or external executable was changed. |
| 2026-08-18 | Phase 02 test/document patch | An ambiguous generic `column` hunk was rejected without modifying files. | Re-read the precise test block and applied a context-specific patch. |

## Test evidence

### 2026-08-18 — Phase 00 acceptance gate

- Added `tests/test_subprocess_contract.py` for list-only argv, fixed cwd,
  `stdin=DEVNULL`, explicit `shell=False`, bounded output, and redaction.
- Added `tests/test_gitleaks_reference.py` fake-process coverage for local JSON
  argv, clean/findings, malformed output, missing binary, failed version probe,
  nonzero command failure, timeout, and redacted secret evidence.
- Corrected `Engine.version()` so a nonzero version probe returns `None`, and
  Gitleaks malformed/non-finding failures return canonical `error` metadata.
- Verification: focused reference gate `15 passed`; Phase 00 full gate `124
  passed, 7 skipped`; Ruff check/format, `git diff --check`, and Graft graph
  build/check passed. `uv sync --all-extras --frozen` and `uv build` passed in
  the preceding Phase 00 dependency gate.
- The local `research/` evidence record was updated but remains untracked and
  excluded from any future staging scope.

### 2026-08-18 — Phase 01 truth and coordinator gate

- Added `tests/test_phase01_truth_audit.py`: an engine-backed catalog entry can
  be `real_adapter` only when `PARSER_FIXTURE_SUITES` registers its deterministic
  parser/invocation suite.
- Kept command routing intact while downgrading unsupported engine-backed claims
  to `feasibility_gated`; `secrets` is the sole fixture-proven external adapter.
- Added coordinator coverage that proves stable aggregation independent of child
  order and copies child `tool/engine` provenance onto findings without mutating
  child results.
- Verification: `8 passed`; focused Ruff check/format, Graft build/check, and
  `git diff --check` passed.

### 2026-08-18 — Phase 01 acceptance / Phase 02 inventory

- Completed the opt-in `review` source-policy slice: configured
  `scaffold_markers` emit stable `scaffold-marker` warnings, and
  `source_policy_exclude` suppresses configured paths. Defaults are empty; no
  authorship, model-use, network, or browser claim is made.
- Added config and false-positive boundary tests, plus user-facing configuration
  documentation in `docs/ENGINE_COMPATIBILITY.md`.
- Direct local Phase 02 audit established that `tools/iac.py` is TFLint-only;
  the catalogued Checkov candidate is not routed and remains feasibility-gated.
- Phase 01 acceptance verification: `129 passed, 7 skipped`; full Ruff,
  `git diff --check`, and Graft build/check passed.

| Slice | RED evidence | GREEN evidence |
|---|---|---|
| Result/evidence metadata | `tests/test_phase00_contract.py`: 2 expected failures (`error_result` metadata and deterministic normalized findings). | `2 passed in 0.04s`; focused Ruff check and format check passed. |
| TFLint reference adapter | `tests/test_tflint_reference.py` failed because `TflintEngine` inherited positional-file text-lint behavior. | TFLint-specific safe JSON adapter and catalog truth tests passed; full gate: `138 passed, 7 skipped in 9.66s`. |
| Checkov reference adapter | `tests/test_checkov_reference.py` failed because `CheckovEngine` inherited text-lint output behavior and `IacTool` invoked only TFLint. | Controlled JSON Checkov adapter, missing/timeout/malformed/partial fixtures, and declared two-engine aggregation passed: `9 passed` in the promotion gate. |

## Next step

Keep KICS (`P02-003`), Conftest (`P02-004`), Spectral (`P02-005`), SQLFluff (`P02-007`), djLint (`P02-008`), and kubeconform (`P02-009`) feasibility-gated or deferred until each has its own official local-only contract, fake-process suite, catalog maturity update, and compatibility record. TFLint and Checkov are the supported Phase 02 `iac` adapters; Hadolint is the supported `containerfile` adapter; actionlint is the supported `actions` adapter. Phase 02 remains active.
