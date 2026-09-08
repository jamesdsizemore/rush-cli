# Verification evidence

Status: all eleven requested P1/P2 findings fixed with TDD; independent review clear. Evidence below was captured before the user-authorized commit on `codex/phase-61-62-review-fixes`. No main edits or pushes performed. Whole-repository baseline remains non-green for the seven pre-existing tests listed below.

## Frozen baseline

Base: `fc2d642efc4fbf40a25abd3d98a212f7d3a6181a`; branch `codex/phase-61-62-review-fixes`. Source/test writes paused until baseline finished.

Command (from remediation worktree):

```sh
rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH PYTHONPATH=/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest tests/ -q --disable-warnings
```

Result: **1269 passed, 7 failed, 7 skipped in 108.62 seconds**.

Pre-existing failures:

- `tests/test_checkov_reference.py::test_checkov_normalizes_failed_checks_and_clean_reports`
- `tests/test_phase50c_integration.py::test_cli_offline_review_json_output`
- `tests/test_phase52_installed_artifacts.py::test_wheel_and_sdist_pass_every_safe_probe`
- `tests/test_phase52_installed_artifacts.py::test_artifact_imports_never_resolve_to_checkout_or_src`
- `tests/test_phase52_installed_artifacts.py::test_artifact_version_matches_distribution_metadata`
- `tests/test_providers.py::test_continuity_provider_resume_uses_a_user_owned_claude_cli_profile`
- `tests/test_providers.py::test_continuity_cmd_provider_keeps_checkpoint_text_out_of_command_line`

Installed-artifact failures include missing built distributions and a Windows-style path expectation on macOS. Provider failures involve Windows command wrapping and WindowsPath construction under macOS monkeypatching. Optional quality-engine availability accounts for seven skips. These test failures predate this remediation; no unrelated fixes authorized.

## Public-operation metadata TDD

`tests/test_memory_operation_metadata.py::test_memory_maintenance_inventory_uses_mutating_memory_implementation` first failed: expected `stateful-mutation`, got `read-only` (1 failed in 1.18 seconds). The generator and saved manifest now classify maintenance using `rush.tools.memory:MemoryTool`. Post-fix command included this test and `tests/test_phase51_public_operations.py tests/test_phase57_public_operations.py`: **14 passed in 3.15 seconds**.

## Lint/format baseline

Against a source-identical archive of `fc2d642`, full `ruff check src tests scripts` reports **29 existing diagnostics**. `ruff format --check src tests scripts` reports **7 files needing formatting**, 780 already formatted. Final checks must introduce no additional diagnostics; changed files must remain formatted.

## Independent review, first pass

Compatibility reviewer verified frozen hashes and independently ran **44 passing tests**. Two additional lifecycle defects were reproduced: modifying/deleting a promoted preference retained an obsolete checksum; remigrating a reused checkpoint restored the older receipt. Worker corrected both with RED tests; subsequent **47-test** run passed. Follow-up review reproduced boolean/number equality losing preference type changes; coordinator reproduced **4 failing cases**, corrected canonical JSON comparison, and ran **35 passing related tests**. Independent reviewer then verified exact hashes and **7 targeted tests**, with no remaining compatibility findings.

Core/metadata independent verification: **61 passed**. Real SDK transport independent verification: **17 passed**. Review nevertheless reproduced three additional defects: hashless legacy cache reuse, source edits between packing and hash capture, and native SDK version-probe process leakage on timeout. Each received a failing regression and correction. Cache follow-up: **2 failed before**, **39 passed after**; independent focused verification **24 passed, 15 deselected**. Native startup leak received a failing PID-survival regression and a parent-owned SDK process tree boundary.

Initial transport startup tests expired before cold SDK imports reached their target stage in independent verification (**2 failed, 17 passed**). Corrected tests preserve production deadlines, allow bounded startup time, require peer-stage readiness, and assert timely return plus absent child PID. Final worker suite: **19 passed in 32.36 seconds**. Independent rerun of only the two changed startup cases: **2 passed, 17 deselected in 20.96 seconds**. The other seventeen cases had passed independently on identical production bytes. SDK dependencies are isolated because their MCP version shadows the project's FastMCP when combined with the main suite.

Final independent verdict: **no remaining actionable findings** across all eleven original issues and six additional review defects. Reviewer checked all thirty frozen file hashes and reviewed runtime, tests, docs, operation metadata, shared callers and cleanup boundaries.

## Implementation lane evidence

Detailed RED/GREEN commands, behavior coverage and lane hashes: [core.md](core.md), [compatibility.md](compatibility.md), [transport.md](transport.md). Original eleven requirements and ownership: [plan.md](plan.md).

## Final integrated verification

Run from the remediation worktree after independent review cleared the frozen subject:

```sh
rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH PYTHONPATH=/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest tests/ -q --disable-warnings --tb=short
```

Result: **1312 passed, 7 failed, 20 skipped in 112.82 seconds**. Failed test IDs exactly match the seven baseline IDs above; no newly failing test. Thirteen skips are optional SDK cases executed successfully in the separate nineteen-test SDK suite; seven skips are unavailable quality engines. This is a baseline comparison, not a claim that the entire repository test suite passes.

Full Ruff comparison against source-identical `fc2d642`: **29 baseline diagnostics, 26 final diagnostics, zero new diagnostics**. Three obsolete UTF-8 encode arguments removed in touched compatibility files account for the reduction. All **21 changed Python files** pass `ruff format --check`. `git diff --check` passes.

Graft index refreshed. Final [SHA-256 manifest](frozen-sha256.txt) covers all **30 changed runtime, test, documentation and governance files**. Post-verification comparison found **zero hash drift and zero unexpected changed files**. Branch remains `codex/phase-61-62-review-fixes`; HEAD remains `fc2d642efc4fbf40a25abd3d98a212f7d3a6181a`, proving no remediation commit was made. Original main checkout still has its pre-existing AGENTS.md modification and untracked files; remediation stayed in the separate worktree.

## Empirical limits

Native Claude SDK 0.2.152 and ACP SDK 0.12.1 were exercised through real serialization and stdio subprocesses against local protocol peers. No live model call was made; acknowledgement establishes delivery, not durable model memory. Windows process-tree cleanup is implemented but was not executed on this macOS host. These results establish the requested remediation, not completion of every Phase 61/62 plan requirement.
