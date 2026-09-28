# Test suite runtime reduction — corrective action plan

## Problem

`pytest tests/ -q -p no:randomly` (~2750 tests) takes 45-60 minutes per run. Every worker task and audit in the current Phase 69 Codex remediation goal has had to run this full suite at least once, most twice, some three times. That is the actual bottleneck.

## Root cause (already diagnosed this session)

`tests/test_dashboard_memory_tokens.py::test_browse_and_query_traverse_more_than_10240_rows_with_exact_totals_and_unique_ids` alone accounts for the majority of the runtime under full-suite-scale thread contention.
verified-by: live macOS `sample <pid> 1` stack traces plus `lsof -p <pid>` taken during this session's own debugging of a stalled full-suite run, showing the main thread pinned in `pysqlite_cursor_fetchall_impl` iterating this test's 10,245-row result set, with no `os.fork()`/child-process frames present (isolated via the T027-T031 task chain, this same session).
Root cause: `_build_memory_section` (`src/rush/dashboard/server.py`) refetches the *entire* matching row set from SQLite on every paginated page request instead of using server-side `LIMIT`/`OFFSET`. For 10,245 rows at page size 100, that is ~103 full table refetches per traversal — quadratic, not linear. Already tracked at `.scratch/dashboard-memory-pagination-perf/issues/01-quadratic-refetch-per-page.md`, including the exact fix (SQL-side `LIMIT`/`OFFSET` + `COUNT(*)`, moving trust/source/freshness filters into the `WHERE` clause).

Before this bug's effects compounded across the current session's remediation work, the same suite ran in 15-25 minutes (documented baseline from ~15 runs earlier in this session).

## Actions

1. **Fix the quadratic-refetch bug** (`.scratch/dashboard-memory-pagination-perf/issues/01-quadratic-refetch-per-page.md`). This is the single highest-leverage fix: it should bring the dominant slow test from tens-of-minutes down to low seconds, and the full suite back toward its 15-25 minute baseline.
2. **Add a fast/slow pytest marker split.** Requires real per-test duration data first, not a guessed threshold — run `pytest tests/ --durations=0 -q` once (piggyback this flag onto the next scheduled full run) and mark the tests with the largest actual own-runtime as `@pytest.mark.slow`, starting with `test_browse_and_query_traverse_more_than_10240_rows_with_exact_totals_and_unique_ids`. Register the marker in `pyproject.toml`/`pytest.ini` and default local/dev runs to `-m "not slow"` via `[tool.pytest.ini_options] addopts`, reserving the unfiltered run for CI/pre-merge. Does not delete or weaken any test — only changes which ones run by default during iteration.
3. **Enable `pytest-xdist` parallelization** (`-n auto`) for the full/CI run. Checked this session: every dashboard test server in this repo binds via `port=0`/`bound_port=0` (`tests/test_ai_eval.py:207`, `test_dashboard.py:63`, `test_executed_modes.py:1019,1075,1519`, `test_dashboard_http_contract.py:162`, `test_memory_public_contract.py:611`, `src/rush/dashboard/server.py:184`) — OS-assigned ephemeral ports, so no port-collision risk under parallel workers was found; grep covered every `ThreadingHTTPServer(`/`HTTPServer((` construction in `tests/*.py` and `src/rush/dashboard/server.py`.

Item 4 (auditing the full 2750-test suite for genuinely redundant/duplicate coverage) is not included here: it requires a real per-test audit to do safely and is not needed once items 1-3 land — the actual complaint (waiting on the full suite before every task) is resolved by making the fast subset the default, not by reducing total test count.

## Execution order

Item 1 first (it's already fully diagnosed, no design work needed) → item 2 (mechanical, low risk) → item 3 (mechanical, low risk). All three are independent of the currently in-flight Phase 69 remediation goal's own file scope and can run as their own task once the goal's current active task (T046) is clear of test_dashboard_memory_tokens.py conflicts.
