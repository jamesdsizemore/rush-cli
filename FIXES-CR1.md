# CR1 — MC00 Benchmark Review Remediation (T008 fixtures.py implementation)

**Decision:** approved
**Findings:** 0 blocking, 0 required, 0 suggestion

## Blocking findings
None

## Required findings
None

## Suggestions
None

## Checklist verdicts

1. **PASS** — Module-level `_SCENARIO_CONTRACT_KEYS = frozenset({"scenario_id", "probe", "category", "input", "required_facts", "expected_outcome"})` exists at `scripts/benchmarks/fixtures.py:34-36`, directly above `load_scenarios` (`fixtures.py:39`). Keys match the plan's Task B spec exactly.

2. **PASS** — Both call sites reference the shared constant, confirmed by reading both functions in full:
   - `load_scenarios`'s loop: `require_exact_keys(item, _SCENARIO_CONTRACT_KEYS)` (`fixtures.py:46`).
   - `load_memory_cases`'s loop: `require_exact_keys(case, _SCENARIO_CONTRACT_KEYS)` (`fixtures.py:139`).
   No inline `frozenset({...})` literal remains for the 6-key contract anywhere in the file.

3. **PASS** — `load_provider_routes` (`fixtures.py:61-105` in the new file) is byte-identical to `git show HEAD:scripts/benchmarks/fixtures.py`'s version of the same function. Confirmed via a structural diff of the whole file against HEAD (see item 4) — the function's body text matches HEAD verbatim, only its line offset shifted (+27 lines) due to the new constant/docstring inserted earlier in the file. Its 10-key frozenset (`provider_id, route_id, mode, command, official_docs_url, terms_url, privacy_url, credential_boundary, redaction_patterns, timeout_s`) is untouched, per the plan's explicit instruction not to touch it.

4. **PASS** — Diffed the entire file (`git show HEAD:...` vs. current working tree) rather than just the two named functions. Every other loader — `load_routers`, `load_protocol_cases`, `load_privacy_cases`, `load_context_cases`, `load_coordination_cases`, `load_local_candidates` — is byte-identical to HEAD; the whole-file diff shows only a uniform line-offset shift (new constant + expanded docstring add lines before `load_scenarios`, and the dedup removes the two inline frozenset literals) with zero content changes to any function body outside `load_scenarios` and `load_memory_cases`.

5. **PASS** — `load_scenarios`'s memory-case loading now reads `items = [*raw.get("scenarios", []), *load_memory_cases()]` (`fixtures.py:43`), replacing the old inline `memory_raw = json.loads(fixture_path("memory_cases.json").read_text(...)); items = [*raw.get("scenarios", []), *memory_raw.get("cases", [])]`. Read both old (`git show HEAD:scripts/benchmarks/fixtures.py`) and new `load_memory_cases` (`fixtures.py:130-140`, unchanged logic from HEAD other than the constant swap): it reads the same default file (`memory_cases.json`), parses the same `"cases"` key, and returns the same list — same items, same order, for well-formed fixture data. The only behavioral delta is `load_memory_cases()` additionally raises `FixtureError` if `cases` is missing/not-a-list or a case is malformed (checks that already existed in `load_memory_cases` before this diff, at HEAD) — stricter, not looser, and the real fixture file already satisfies these checks (confirmed by the 46/6-memory count assertions passing in item 10).

6. **PASS** — `load_scenarios`'s own loop still calls `require_exact_keys(item, _SCENARIO_CONTRACT_KEYS)` (`fixtures.py:46`) for every item in `items`, which now includes both the raw `scenarios.json` entries and the memory cases returned by `load_memory_cases()`. Nothing skips validation — memory-case items are validated twice (once inside `load_memory_cases`, once again in `load_scenarios`'s loop), both times via the same shared constant, matching the plan's stated "redundant-but-harmless" design.

7. **PASS** — `load_scenarios`'s docstring now reads "Loads and validates scenarios from tests/fixtures/benchmarks/scenarios.json, merged with memory benchmark cases loaded via load_memory_cases()." (`fixtures.py:40-41`), which accurately describes the new `load_memory_cases()` call at line 43. No other docstrings in the file changed.

8. **PASS (scoped)** — `git status --porcelain` at review time also shows `scripts/benchmarks/memory.py` and `tests/test_benchmark_memory.py` modified. Verified these are Task A/Task D changes tracked under different board tasks (T002/T004 per `state.yaml`), not part of T008's fixtures.py diff — confirmed via `git diff HEAD -- scripts/benchmarks/memory.py tests/test_benchmark_memory.py` showing the M03/M06/M09/M10 probe-behavior work (unrelated to the fixtures.py dedup) and via `state.yaml:274,294` naming T002/T004/T006 as owning memory.py's changes. Within T008's own diff, only `scripts/benchmarks/fixtures.py` was touched.

9. **PASS** — All commands re-run directly this session, not read from a prior report:
   - `rtk pytest tests/test_benchmark_contracts.py tests/test_benchmark_memory.py -v` → `Pytest: 18 passed`.
   - `rtk pytest -q` (full suite) → `Pytest: 2283 passed, 0 failed, 5 skipped` — matches exactly.
   - `rtk ruff check scripts/benchmarks/fixtures.py` → `[]` (clean).
   - `rtk mypy scripts/benchmarks/fixtures.py` → `No issues found` (clean).

10. **PASS, with one wording note** — Read `tests/test_benchmark_contracts.py` in full. `test_load_scenarios_validation` (line 81) contains both `assert len(scenarios) == 46` (line 83) and `assert categories.get("memory") == 6` (line 101) — both exist and both passed in the item-9 run. Note: the task's checklist text attributes `len(scenarios) == 46` to `test_fixture_path_security`; that assertion actually lives in `test_load_scenarios_validation` (`test_fixture_path_security`, lines 66-79, only tests `fixture_path()`'s traversal/extension guard). This is a misattribution in the board task's wording, not a defect in the code or tests — both cited assertions are real, present, and passing.

## Notes

This run OVERWRITES the prior T005 CR1 content that lived at this same file path — expected and correct. T005's CR1 (for `scripts/benchmarks/memory.py`) is already complete and its findings are permanently recorded in `state.yaml`'s T005/T006/T007 receipts. This file is scoped per-task by the board's own workflow, not a cumulative log.

Whole-file diff command used for items 3/4: compared `git show HEAD:scripts/benchmarks/fixtures.py` against the current working-tree file directly (not just a unified `git diff`), to see full function bodies side by side and confirm byte-identity of untouched functions beyond what unified-diff context lines show.

`load_memory_cases` itself is unchanged in behavior from HEAD except for the constant swap (`_SCENARIO_CONTRACT_KEYS` replacing its own inline literal) — it was already being called by other code (`scripts/benchmarks/memory.py` at HEAD, before T002's edits removed that import) before this diff; T008's only new addition is `load_scenarios` now also calling it instead of duplicating the memory_cases.json read inline.

All verification commands in the plan's Task B / Verification section were re-executed live this session (not inherited from an earlier task's report), per this repo's "verify by executing" rule.
