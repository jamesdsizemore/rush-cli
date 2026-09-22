Status: needs-triage

## Summary

The Phase 69 Codex review (`docs/reports/69-dashboard-tui-codex-implementation-review.md`) §12 names specific regression test functions per finding. A coverage sweep (Phase 69 codex-review-remediation goal, T041/T042) found the production fixes for M03, M13, M15, M16, M17, M19, M20 are all genuinely implemented and correct, but no test anywhere exercises the named scenarios for these 7 findings — roughly 22 individual test cases across 5 files.

This is missing test coverage, not a functional defect: every one of these 7 findings' underlying fixes was independently checked present in current source (file:line citations below).
verified-by: T042 (goal-scout subagent, this session) read each cited file:line directly and grepped tests/*.py for scenario keywords per finding; see docs/goals/phase-69-codex-review-remediation/state.yaml task T042's receipt for full method and evidence.
Capped out of the active remediation goal on 2026-09-20 per explicit user direction to stop expanding test-writing scope indefinitely.

## Findings and evidence (production code checked present, T042)

- **M03** (2 missing tests): `test_persisted_inventory_survives_restart_and_file_changes`, `test_legacy_attempt_without_inventory_reports_missing_provenance_not_current_files`. No inventory-persistence-across-restart test found in `tests/test_dashboard_map.py`/`tests/test_project_run_lifecycle.py`.
- **M13** (3 missing tests): `test_no_synthetic_evidence_key_reaches_git_show_commit_path`, `test_clean_matching_commit_links_correctly_through_gitguard_diffcover_undercover`, `test_changed_repository_state_evidence_prevents_a_false_git_match`. Source split (`consumed_path_digests`/`repository_state_evidence`) read directly at `src/rush/workflows/project_run.py:325,333`; nearest adjacent test (`tests/test_dashboard_git_artifacts.py::test_git_scan_link_requires_matching_source_revision_not_just_path`, line 528) tests general revision matching, not this finding's specific synthetic-key exclusion.
- **M15** (3 missing tests): SlopTool/staged-bytes scenario. Read directly at `src/rush/workflows/project_run.py:781-813` (`_execute_candidate`'s `active_staging()`/`stage_path`/`record_consumption`/`remap_paths`).
- **M16** (3 missing tests): `consumed_paths` per-engine-target tracking. Read directly at `src/rush/runtime/subprocesses.py:1020-1058`, call sites at `tools/lint.py:89,104`, `format.py:86,99`, `typecheck.py:62`.
- **M17** (4 missing tests): GitGuard-through-execute_scan / unregistered-engine / absent-binary / denied-permission four-way status split. Read directly at `src/rush/workflows/project_run.py:696-737`.
- **M19** (4 missing tests): diff-cover scoped-tempdir cleanup + stale-report/conflicting-arg rejection. Read directly at `src/rush/engines/diff_cover.py:35-145`.
- **M20** (3 missing tests): stylelint/trivy decoded-path remapping vs literal-text preservation. Read directly at `src/rush/engines/stylelint.py:44-65`, `src/rush/engines/trivy.py:43-62`.

## Suggested fix

Write the ~22 named regression tests per each finding's Fix/Regression prose in the review doc's §3-6, split across: `tests/test_dashboard_map.py` (M03), `tests/test_dashboard_git_artifacts.py` (M13), `tests/test_full_project_scan.py`/`tests/test_engine_provisioning.py` (M15, M16, M17), `tests/test_diff_cover_reference.py` (M19), `tests/test_stylelint_reference.py`/`tests/test_trivy_reference.py` (M20). Production code changes are not expected to be needed for any of the 7 — each fix's source location is cited above and was read directly this session.

## Scope note

Not one of the review doc's 51 named findings' functional-fix requirements — those are all closed: the full suite was run directly this session (T037/T038/T040/T044/T045 receipts, `docs/goals/phase-69-codex-review-remediation/state.yaml`) and every cited fix was read directly in current source. This is a test-coverage-completeness gap the remediation's own audit process discovered by checking literal §12 test names against the actual test suite, going deeper than the original 51-finding scope required. Tracked here rather than chased indefinitely.
