# Phase 05 implementation ledger — language-native and semantic evidence

Authorization: user-approved on 2026-08-19.
<strong>Scope:</strong> preserve truthful marker routing and add only contained semantic evidence
whose behavior is fixture-backed. Browser/runtime work, live CodeQL database/query
execution, package restores, project builds, SDK installation, and toolchain
installation are excluded.
<strong>Protected:</strong> Phase 06–08 plans and `research/` remain untracked and unstaged.

## Baseline

- `117dc62` completed Phase 04 with a clean project suite (`193 passed, 7 skipped`).
- RTK identified the Phase 05 plan and existing marker contracts. Graft confirmed
  `detect_project_languages` is shared by lint, test, typecheck, capabilities,
  and their tests. context-mode indexed the plan, source, and routing tests.
- Existing marker routing is intentionally feasibility-gated: detecting Go, Rust,
  JVM/.NET, Ruby/PHP, Dart/Flutter, Swift, Elixir, Scala, and Nix never executes
  their runtime/toolchain.

## RED/GREEN evidence

- `tests/test_codeql_importer.py` initially failed collection with
  `ModuleNotFoundError: rush.tools.codeql`, proving no CodeQL importer existed.
- The next RED tests exposed incorrect warning precedence, acceptance of a
  foreign SARIF driver, failure to structure a non-object report, and acceptance
  of an empty run list. Each became a fixture-backed contained-import contract.
- The final focused importer/registry/capability/catalog/MCP slice passed:
  `21 passed in 1.73s`.

## Error register

| Timestamp | Attempt | Error | Recovery |
|---|---|---|---|
| 2026-08-19 | Focused Ruff format check after the first CodeQL importer slice | Ruff reported only deterministic line wrapping in the new importer and test; no semantic defect or file corruption occurred. | Apply Ruff's exact formatting, then rerun the focused importer test and check/format gates. |
| 2026-08-19 | Focused Ruff import-order check after registering CodeQL | Ruff identified the new `CodeqlTool` import's exact alphabetical position; registry behavior and tests were otherwise green. | Apply Ruff's supplied import-only diff, then rerun the affected check/format and registry tests. |
| 2026-08-19 | CodeQL SARIF validation patch | The patch tool found an ambiguous insertion anchor and made no change. | Re-read the complete new importer, then apply one context-specific validation patch rather than retrying the stale hunk. |
| 2026-08-19 | Focused Ruff format check after the non-object SARIF regression | Ruff requested only the exact wrapped test signature; all 17 focused behavioral contracts passed. | Apply the supplied one-function formatting diff and rerun the focused check/format gate. |
| 2026-08-19 | RTK documentation-anchor search | An unquoted backtick in the shell search pattern was interpreted as command substitution, so the compound inspection returned nonzero despite printing partial anchors. | Re-run the bounded RTK search with literal, backtick-free anchors before documentation edits; no repository file was changed by the failed command. |
| 2026-08-19 | Phase 00 catalog-maturity regression | The existing fixed catalog-count assertion correctly failed after adding the 33rd user-visible tool. | Update the truth test to assert the new count and CodeQL importer maturity before final suite verification. |
| 2026-08-19 | RTK multi-file diff attempt | This RTK installation forwarded the multi-path diff arguments to the platform `diff`, which accepts only two operands; the source and plan reads in the same compound command were valid. | Use `git diff -- PATH...` for the required multi-file scoped review, then return to RTK for status/stat and project test commands. |
| 2026-08-19 | Ledger metadata emphasis | A surplus Markdown asterisk made the authorization label malformed. | Restore the exact metadata line, re-read it, and re-stage the ledger before commit. |

## Final evidence

- `CodeqlTool` imports only an explicit, contained CodeQL SARIF 2.1.0 report;
  every run needs a CodeQL driver. Missing reports skip; malformed, foreign,
  non-object, empty-run, and path-escaping reports return structured errors.
  The tool never runs CodeQL, creates a database, builds/restores a project,
  installs an SDK, downloads query packs, or uses a network service.
- The shared `ALL_TOOLS` registry exposes the same `codeql` object through CLI
  and MCP. Catalog maturity is `importer`; capabilities recognize a local
  `codeql.sarif` marker without execution; the catalog truth test now records
  33 user-visible tools.
- User, README, catalog, CLI reference, MCP reference, compatibility record,
  changelog, Phase 05 plan, and this ledger describe the same import-only
  boundary. The user workflow is report-file `PATH`, never a claimed live
  CodeQL command.
- Final project verification after the last source/test edit: `200 passed,
  7 skipped in 5.74s`; the seven skips are unavailable optional static engines.
  Ruff check and format both passed (`127 files already formatted`).
- CLI smoke checks passed for `rush codeql --help`, `rush capabilities --help`,
  and `rush mcp --help`. Local Markdown-link validation checked 133 files.
- Graft rebuilt the final 668-node wiring graph and `graft check` passed.
  context-mode reindexed/retrieved the final CodeQL and Phase 05 contracts;
  RTK supplied scoped status, literal anchors, and bounded source/test reads.

Unsupported live ecosystem adapters remain feasibility-gated rather than
simulated. The final staged scope review and commit are the remaining Phase 05
boundary operations.
