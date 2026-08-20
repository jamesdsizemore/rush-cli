# Phase 04 implementation ledger — non-browser test quality and reliability

**Authorization:** user-approved on 2026-08-19.
**Scope:** complete the Phase 04 report-importer contract without browser, E2E,
visual, Lighthouse, DOM, DAST, network, or live-engine implementation.
**Protected:** later phase plans and `research/` remain untracked and unstaged.

## Baseline and recovered implementation

- Existing implementation landed in `e6576d1` (`feat: add test quality tools`):
  `coverage`, `mutation`, `pbt`, `flaky`, `contract`, `snapshot`, `fuzz`, and
  `load` are contained importers registered through the common CLI/MCP registry.
- Phase plan and planning integration landed in `670762f`; this ledger records
  the final Phase 04 acceptance audit and user-facing documentation completion.
- Focused importer suite before documentation updates: `30 passed in 0.25s` with
  `.venv/Scripts/python.exe -m pytest` after clearing `VIRTUAL_ENV` and
  `PYTHONPATH`.
- Graft graph build/check passed. Its registry/CLI/MCP map confirms one
  `ALL_TOOLS` registry is consumed by both transports; no transport duplicates
  importer logic.
- context-mode indexed the Phase 04 plan, importer tools, fixtures, and docs;
  targeted retrieval confirmed the importer-only and permission boundaries.

## Acceptance audit

- [x] Every Phase 04 quality command is truthfully catalogued as `importer`.
- [x] Importers accept only contained local reports and return structured
  `skipped`/`error` states for absent, malformed, or path-escaping reports.
- [x] Coverage accepts coverage.py JSON, LCOV, and Cobertura XML; flaky accepts
  JUnit duplicate-case evidence; the remaining importers accept documented JSON
  summaries.
- [x] Importers never launch an engine, repeat tests, contact a target, build or
  download dependencies, or mutate/accept a baseline.
- [x] CLI and MCP use the same registered `ToolFn` instances. A report file is
  supplied as the ordinary `PATH` argument; directories without a report skip.
- [x] Browser, visual, and E2E execution remain excluded and guarded.
- [x] User-facing testing-confidence, advanced-check, CLI, compatibility, and
  catalog documentation label report importing rather than live execution.

## Error register

| Timestamp | Attempt | Error | Recovery |
|---|---|---|---|
| 2026-08-19 | `graft map` before a graph existed | Graft returned `no graph — run graft build first`; no repository file changed. | Built and checked `.hermes/graft`; subsequent registry/wiring queries used the synchronized graph. |
| 2026-08-19 | `.venv/Scripts/python.exe -m rush ...` CLI inspection | Python reported `No module named rush.__main__`; this package intentionally exposes a console entry point, not `python -m rush`. | Validate generated help through `.venv/Scripts/rush.exe`; retain the successful project-interpreter pytest evidence. |
| 2026-08-19 | `rtk diff` with a multi-file argument list | The RTK wrapper delegated to `diff`, which accepts two operands rather than a Git-style path list; no repository file changed. | Use `git diff -- <scoped paths>` for the bounded review and return to RTK for Git state, reads, search, and test gates. |
| 2026-08-19 | Inline Markdown-link checker passed literal `\\n` through `python -c` | The interpreter raised `SyntaxError`; no documentation content changed. | Supply the same read-only checker through Python stdin with a quoted Bash heredoc, preserving real newlines. |
| 2026-08-19 | RTK search pattern contained Markdown backticks in a double-quoted Bash command | Bash attempted command substitution for `PATH`; the literal search was incomplete and no repository file changed. | Search the remaining literals without backticks or single-quote the entire pattern. |

## Final evidence

- Generated entry-point help passed for `coverage`, `mutation`, and `mcp`; it
  advertises the importer maturity and ordinary `PATH` input without exposing an
  unsafe execution switch.
- Focused importer suite: `30 passed in 0.25s`.
- Full project suite: `193 passed, 7 skipped in 5.70s`; skips are optional
  uninstalled mypy, tsc, vulture, knip, radon, jscpd, and sloppylint engines.
- Ruff check and format check passed. The read-only Markdown validator checked
  133 tracked documentation files with no broken local links.
- Final Graft build/check passed; context-mode reindexed and retrieved the
  Phase 04 documentation and ledger contracts; RTK confirmed the scoped status,
  reads, search, and Git boundary.

The phase commit includes only this ledger, the Phase 04 plan, documentation
clarifications, and the changelog entry. `research/` and later-phase plans remain
unstaged.
