# Phase 64 implementation evidence

Current status: Phase 64 is in progress; this evidence records completed packet checks only. Current contract: [Phase 64 runtime correctness and safe execution](phase-64-runtime-correctness-and-safe-execution-plan.md). Review evidence: [whole-application review](../reports/phase-64-66-application-review.md).

## P64-00 — Documentation coverage

Source commits: `e1abab8` and `c9a7681`.

- GREEN: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_sync_docs.py -q` — 13 passed.
- GREEN: Ruff check and format-check on `scripts/sync_docs.py` and `tests/test_sync_docs.py` — passed.
- GREEN: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` — documentation coverage and runtime contracts match. FastMCP/Pydantic emitted `IncompleteFieldDefinitionWarning`; [tracked issue](../../.scratch/phases-64-63-65-66/issues/01-fastmcp-settings-forward-reference-warning.md) records it as nonblocking, with no runtime conclusion.

## P64-01 — Preserve checkout/index during fixes (F01)

Requirement mapping: F01 requires dry-run to preserve worktree, index, untracked files, and history; failure may restore only invocation-owned changes. Frozen source SHA-256: `src/rush/tools/fix.py` `dd61b75efab2bb5bd307c4bb3f02330e46627ff1b72f7c1fe9b90ff574f8950d`; frozen test SHA-256: `tests/test_fix.py` `cf1c09a0befe5320da926b4767ab40ec27c1a3985f762d688c266f057f9e6c39`.

- RED initial: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_fix.py::test_dry_run_preserves_index_and_unrelated_files tests/test_fix.py::test_failed_fix_preserves_untracked_files -q` — 3 failures. Dry run reset dirty fixture bytes, invalid syntax returned the wrong status, and Ruff exit 2 was reported successful without restoring bytes/mode.
- RED review expansion:
  - `... python -m pytest tests/test_fix.py::test_dry_run_preserves_index_and_unrelated_files tests/test_fix.py::test_fix_missing_ruff_is_skipped_without_launch tests/test_fix.py::test_fix_reports_restore_failure_and_continues_other_targets -q` — 3 failed, 2 passed.
  - `... python -m pytest tests/test_fix.py::test_fix_restores_owned_targets_when_ast_validation_is_cancelled -q` — 1 failed.
  - `... python -m pytest tests/test_fix.py::test_fix_preserves_ruff_excluded_python_files -q` — 1 failed.
  - `... python -m pytest tests/test_fix.py::test_fix_sanitizes_subprocess_exceptions tests/test_fix.py::test_fix_restores_target_deleted_by_engine -q` — 3 failed; sanitizer case is parametrized twice.
  - Final consolidated `... python -m pytest tests/test_fix.py::test_fix_refuses_dangling_symlink_during_rollback tests/test_fix.py::test_fix_refuses_parent_symlink_redirection_during_rollback tests/test_fix.py::test_fix_rejects_incomplete_snapshot_before_mutating_launch tests/test_fix.py::test_fix_restores_after_unexpected_validation_exception tests/test_fix.py::test_fix_git_status_failure_stops_before_ruff tests/test_fix.py::test_registered_mcp_fix_apply_denies_and_grants_artifact_write -q` — 8 failed in 4.12 seconds; first GREEN attempt had 2 failed, 6 passed in 3.74 seconds; final GREEN had 8 passed in 3.42 seconds. The MCP permission test is a RED here; an earlier permission test added after its guard is not presented as RED.
- GREEN focused: consolidated six-node RED command expanded to eight cases — 8 passed in 3.42 seconds. The full frozen command `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_fix.py -q` — 30 passed in 11.61 seconds on Python 3.12.12 with Ruff 0.16.3. Ruff check, format-check, and diff-check on `src/rush/tools/fix.py` and `tests/test_fix.py` passed.
- GREEN runtime/transport route: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_fix.py::test_fix_cli_and_direct_dry_run_preserve_same_dirty_fixture -q` — direct tool and in-process Click `cli` invoke `fix PATH --dry-run --force --json` against one fixture containing staged, unstaged, and untracked files; exact repository state remains unchanged. This is not an external installed-`rush` binary run.

Caller and permission review: shared `FixTool` covers direct, CLI, and registered MCP `rush_fix` routes. The MCP schema exposes `allow_artifact_write: bool = False`; absent grant denies apply and `True` applies. `FixTool.__call__` bridges that flag to execution permissions. `src/rush/tools/fix.py` uses native `ruff check --show-files --no-cache` selection, preserves Ruff excludes, runs read-only ordinary Ruff check for unfixable lint, snapshots selected regular targets before writes, and reports bounded/redacted subprocess or restoration failures. Direct/Click dry-run parity and excluded `.venv/vendor.py` apply behavior use real Ruff; exact argv, failure/config, invalid-AST, cancellation, missing-Ruff, deletion, and symlink cases include mocked boundaries where stated by their tests. No external shell-installed `rush` binary ran.

## Remaining Phase 64 work

Only P64-00 and P64-01 evidence is recorded here. Other Phase 64 packets remain planned until their own RED, GREEN, and acceptance evidence is added.
