# T001: Environment and full baseline at 07775f1

Worktree: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`. Branch: `phase/72-memory-correctness-and-user-control`. HEAD: `07775f1`. Run date: 2026-10-05. Product files were unchanged during every run.

## Environment

- **Venv (decision D4):** `.venv` was created in this worktree by the first plan command, `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c ...`. uv built `rush-cli` from this worktree and installed 79 packages. Size: 388M (`du -sh .venv`).
- **Python:** that same command printed `3.12.12 (main, Feb  4 2026, 01:57:59) [Clang 21.1.4 ]`, with executable `.../phase-72/.venv/bin/python`. `rush.__file__` is `.../phase-72/src/rush/__init__.py`.
- **Disk monitor:** a `run_in_background` loop runs `rtk proxy df -g /Users` every 60 s and exits with `DISK ALERT` below 8 GiB. Free space was 23 GiB at start and 21 GiB after the suite.

## Baseline results

| Check | Command | Exit | Result |
|---|---|---|---|
| Full suite | `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m '' -p no:cacheprovider` | 1 | **2 failed, 6491 passed, 0 skipped, 14 deselected**, 933.44 s (15:33) |
| ruff check | `rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts` | 0 | `All checks passed!` |
| ruff format | `rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts` | 0 | `938 files already formatted` |
| mypy | `rtk proxy uv run --python 3.12 --extra dev mypy src/rush` | 0 | `Success: no issues found in 474 source files` |
| sync_docs | `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check` | 1 | 6 errors, all `missing coverage receipt` for the new board docs (see below) |
| diff check | `rtk proxy git diff --check` | 0 | clean |

### Deviation from the plan's literal command

The full-suite command adds `-p no:cacheprovider`. The flag stops the run from writing `.pytest_cache`; it does not change which tests are selected or how they run.

### Failing tests at baseline (each reproduced alone)

Both tests fail again when run alone with `pytest <id> -q -m '' -p no:cacheprovider`. They are deterministic pre-existing failures on the Phase 70 tip, not interference from other runs.

1. `tests/test_phase70_t28f_review1.py::test_plus_minus_expand_and_collapse_detail_in_git_and_memory` fails at `tests/test_phase70_t28f_review1.py:409`: `assert expanded[0] is not None and expanded[1] == expanded[0]` gives `E assert (None is not None)`. This is the memory-mode `+` expansion in the TUI. It touches 72-T02 (expansion paging) and 72-T07 (TUI memory handlers), and those gates (T005, T011) must account for it.
2. `tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts`, inside `_artifacts_journey` (call at `:755`), fails on `assert "[/bad]" in text and "\x1b" not in text`. The rendered Artifacts view for search `'pwned'` shows a binary blob row and does not contain `[/bad]`. This is the Phase 70 artifacts TUI and is not a memory path.

### Deselected tests (not skipped)

`tests/conftest.py:86-127` (`pytest_collection_modifyitems`) deselects tests whose markers cannot run on this platform. It prints `windows_only: 13 deselected (not Windows)` and `atheris_only: 1 deselected (not Linux x86_64)`. The docstring says the Windows CI job and the ubuntu x86_64 engine-contracts job run them. The SKIPPED count is 0.

### sync_docs and the board docs

On base bytes, the only `sync_docs --check` errors come from the new, not-yet-committed board docs:

- `.goalbuddy-board/app.js`
- `.goalbuddy-board/goalbuddy-mark.png`
- `.goalbuddy-board/index.html`
- `.goalbuddy-board/styles.css`
- `goal.md`
- `notes/prep-board-review.md`

Every docs file needs a sha256 receipt in `docs/reports/phase-64-66-documentation-coverage.md` (`scripts/sync_docs.py:687-690`). Only `docs/goals/*/state.yaml` is exempt (`scripts/sync_docs.py:450-466`). CI runs this check (`tests/test_ci_contract.py:42`).

The board commit therefore also refreshes receipts for `docs/goals/phase-72-memory-correctness/` in the coverage report, as commit `87370cf` did for earlier boards. This goes beyond the T001 card's pathspec, which names only `docs/goals/phase-72-memory-correctness/`. It is recorded here as the reason. Every later board or report commit refreshes these receipts the same way.

## Baseline the oracle compares against

- **Full suite:** exactly the 2 failures above. Any other failure is a regression. 0 skipped.
- **ruff check, ruff format --check, mypy, git diff --check:** clean.
- **sync_docs --check:** clean once the board receipts are committed.
