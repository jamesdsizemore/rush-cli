# CR2 — MC00 Benchmark Review Remediation (independent re-review of fixtures.py)

**Decision:** clean
**Findings:** 0 blocking, 0 required, 0 suggestion

## Blocking findings
None

## Required findings
None

## Suggestions
None

## Independent verification results

1. **Constant + both call sites confirmed.** Read the whole current file. `_SCENARIO_CONTRACT_KEYS = frozenset({"scenario_id", "probe", "category", "input", "required_facts", "expected_outcome"})` exists directly above `load_scenarios`. Both `load_scenarios`'s loop (`require_exact_keys(item, _SCENARIO_CONTRACT_KEYS)`) and `load_memory_cases`'s loop (`require_exact_keys(case, _SCENARIO_CONTRACT_KEYS)`) reference the shared constant. No inline `frozenset({...})` literal for the 6-key contract remains anywhere in the file.

2. **Whole-file diff confirms only two hunks changed.** Ran `rtk git diff HEAD -- scripts/benchmarks/fixtures.py` myself. Diff is 10 insertions / 31 deletions across exactly two hunks: (a) the new constant + `load_scenarios`'s memory-merge line + the `require_exact_keys` call swap, and (b) the same call swap inside `load_memory_cases`. `load_provider_routes` and every other loader (`load_routers`, `load_protocol_cases`, `load_privacy_cases`, `load_context_cases`, `load_coordination_cases`, `load_local_candidates`, `fixture_path`) do not appear in the diff at all — byte-identical to HEAD. `load_provider_routes`'s own 10-key frozenset (`provider_id, route_id, mode, command, official_docs_url, terms_url, privacy_url, credential_boundary, redaction_patterns, timeout_s`) is untouched, matching the plan's explicit instruction not to touch it.

3. **Traced `load_memory_cases()` call.** `load_scenarios` now builds `items = [*raw.get("scenarios", []), *load_memory_cases()]`. Read `load_memory_cases`'s full body: same default fixture file (`memory_cases.json`), same `"cases"` key, returns `list[dict]` — identical items/order to the old inline `memory_raw.get("cases", [])` for well-formed fixture data. Every item in `items` (both scenarios.json entries and memory cases) still passes through `load_scenarios`'s own loop, which calls `require_exact_keys(item, _SCENARIO_CONTRACT_KEYS)` unconditionally before constructing each `Scenario` — nothing is skipped. Memory-case items are validated twice (once inside `load_memory_cases`, once again in `load_scenarios`'s loop) via the same shared constant; this is the plan's explicitly documented "redundant-but-harmless" design (Task B step 3), not an oversight.

   One genuine behavioral nuance, not a regression: `load_memory_cases()` raises `FixtureError` if `"cases"` is missing or not a list, whereas the old inline code silently defaulted to `[]` via `.get("cases", [])`. This stricter check already existed in `load_memory_cases` at HEAD (untouched by this diff — confirmed by the diff in item 2 showing no changes to that isinstance logic), and the real fixture file already satisfies it (confirmed by the passing 46-scenario / 6-memory-category count assertions in item 4). No behavior change in practice.

4. **Test file read in full.** `tests/test_benchmark_contracts.py::test_load_scenarios_validation` contains both `assert len(scenarios) == 46` and `assert categories.get("memory") == 6`, plus per-category counts for handoff/drift/recovery/privacy/budget/concurrency. Ran:
   - `source .venv/bin/activate && rtk pytest tests/test_benchmark_contracts.py tests/test_benchmark_memory.py -v` -> `Pytest: 18 passed`.
   - `rtk pytest -q` (full suite) -> `Pytest: 2283 passed, 0 failed, 5 skipped`.
   - `rtk ruff check scripts/benchmarks/fixtures.py` -> `[]` (clean).
   - `rtk mypy scripts/benchmarks/fixtures.py` -> `No issues found`.

5. (Merged into 4 above — same commands, all re-run live this session, not inherited from any prior report.)

6. **Scope check.** `rtk git status --porcelain` shows `scripts/benchmarks/fixtures.py`, `scripts/benchmarks/memory.py`, and `tests/test_benchmark_memory.py` modified. Read `docs/goals/mc00-benchmark-review-remediation/state.yaml`: `memory.py`/`test_benchmark_memory.py` are owned by T001/T002 (Task A/D, separate Worker tasks, status recorded independently), not this task (T011, which reviews only T010's `scripts/benchmarks/fixtures.py`-scoped diff, `allowed_files: ["scripts/benchmarks/fixtures.py"]`). Confirmed T010's own diff touches only `fixtures.py`.

7. **Edge cases / docstrings.** `require_exact_keys`'s validation is applied per-item identically regardless of merged-list origin — no ordering assumption changed (scenarios still precede memory cases in `items`, same as the old code's `[*raw.get(...), *memory_raw.get(...)]` order). `load_scenarios`'s docstring now reads "...merged with memory benchmark cases loaded via load_memory_cases()." — accurate, matches the new call. `load_memory_cases`'s own docstring ("Load deterministic memory benchmark descriptors under fixture containment.") is unchanged and still accurate since its behavior is unchanged (only the internal frozenset reference was swapped for the shared constant). No inaccurate docstrings found.

## Comparison against CR1

Agreement on every substantive item: constant placement and exact key set (item 1), whole-file byte-identity of all untouched loaders including `load_provider_routes` (item 2/3-4 in CR1), the memory-case merge and its double-validation being deliberate per the plan (item 3/5-6 in CR1), all four verification commands and their exact output (item 4/9 in CR1), and task-scope separation from T001/T002's memory.py work (item 6/8 in CR1). CR1 also flagged a wording-only misattribution in the board task text (the `len(scenarios) == 46` assertion lives in `test_load_scenarios_validation`, not `test_fixture_path_security` as the task text implied) — independently confirmed the same by reading the test file myself; it's a board-doc wording note, not a code or test defect, so it isn't listed as a finding here either.

No disagreements. No new issues found beyond what CR1 already surfaced.

## Notes

This run overwrites the prior T007 CR2 content that lived at this same file path (T007 reviewed `scripts/benchmarks/memory.py`/Task A, already complete and recorded in `state.yaml`'s T007 receipt) — expected, per this file's per-task scoping convention.

Derived independently before reading CR1: read the full current file, ran my own `git diff HEAD` rather than trusting a prior diff description, traced `load_memory_cases` and `load_scenarios` by hand, re-ran every verification command live, and cross-checked scope against `state.yaml` myself. FIXES-CR1.md was read only after completing steps 1-7 above.
