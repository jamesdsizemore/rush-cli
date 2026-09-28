# Quadratic full-row refetch on every dashboard memory page request

Status: ready-for-agent

## Summary

`_build_memory_section` in `src/rush/dashboard/server.py:3313-3376` refetches the ENTIRE matching row set from SQLite on every single paginated page request for the dashboard's memory browse/query section — there is no server-side `LIMIT`/`OFFSET`. Pagination is done by fetching all matching rows and Python-slicing by cursor offset.

Both branches are affected:
- Browse branch: loops `scope_artifacts()` (`src/rush/memory/store.py:854-897`, already uses `cur.fetchmany(scan_limit)` internally, batched at 512 rows via `_MEMORY_BROWSE_BATCH`) — but the OUTER loop still re-runs from the start on every page request.
- Query branch: `search()` (`src/rush/memory/store.py:2157-2183`) uses `cur.fetchall()` with no limit at all, refetching every matching row on every page.

For a project with N matching rows and page size P, one full traversal (N/P pages) costs O(N²/P) row-fetches instead of O(N). Confirmed empirically: a test seeding 10,245 rows with page=100 (~103 pages) does ~1,054,000+ row-level fetches per traversal, each one paying a CPython GIL release/reacquire inside `sqlite3_step`. Combined with normal background-thread activity from a long-lived dashboard process, this is real, measurable added latency on every page click for any project with more than a few thousand memory rows — not just a test artifact.

## How this was found

Discovered incidentally on 2026-09-19 while diagnosing a GoalBuddy full-suite test hang for `docs/goals/phase-69-codex-review-remediation/` (Phase 69 Codex review remediation). Confirmed via:
- Live `sample`/`lsof` process inspection during the slow test, showing the main thread pinned in `pysqlite_cursor_fetchall_impl`.
- Direct reads of `src/rush/dashboard/server.py:3313-3376`, `src/rush/memory/store.py:854-897` and `:2157-2183`, and `tests/test_dashboard_memory_tokens.py:685-740` (the test that surfaces it, seeding 10,245 rows and traversing via `_traverse()`, ~103 pages of 100).
- Isolated timing: the test alone takes ~25.6s single-threaded with no contention — the pagination inefficiency itself is real regardless of thread count, contention just makes it dramatically worse in a long-running process.

This is explicitly **out of scope** for Phase 69's own 51-finding remediation goal (`docs/goals/phase-69-codex-review-remediation/goal.md`) — it is not one of the 51 findings in `docs/reports/69-dashboard-tui-codex-implementation-review.md`. Phase 69's own T031 Judge checkpoint decided this is too large/risky a correctness-sensitive redesign to shoehorn into that goal's remaining tasks, and filed it here instead.

## Suggested fix

Move pagination to SQL: add real `LIMIT`/`OFFSET` (and a `COUNT(*)` for total-row reporting) to the query and browse code paths in `src/rush/memory/store.py`, so `_build_memory_section` requests only the one page of rows it actually needs per call instead of refetching everything and slicing in Python.

**Caution:** M14 (a prior Phase 69 finding) already found and fixed one truncated-total bug in this exact code path (an artificial batch cap silently truncating results at 10,240 rows). The current trust/source/freshness filters run in Python *after* the full fetch — moving pagination into SQL means those filters need to move into the `WHERE` clause too, or be applied before the `LIMIT`, or total/page-count correctness will regress the same way M14 did. Any fix here needs its own regression tests covering exact totals and page boundaries under filtering, not just raw row counts.

## Evidence

- `src/rush/dashboard/server.py:3313-3376` — `_build_memory_section`, both browse and query branches, no `LIMIT`/`OFFSET`.
- `src/rush/memory/store.py:854-897` — `scope_artifacts()`, `cur.fetchmany(scan_limit)` internally batched but outer loop restarts each call.
- `src/rush/memory/store.py:2157-2183` — `search()`, `cur.fetchall()` with zero limit.
- `tests/test_dashboard_memory_tokens.py:685-740` — `test_browse_and_query_traverse_more_than_10240_rows_with_exact_totals_and_unique_ids`, the test that surfaces this at scale.
- `docs/goals/phase-69-codex-review-remediation/state.yaml` — T031 receipt, decision and rationale.
