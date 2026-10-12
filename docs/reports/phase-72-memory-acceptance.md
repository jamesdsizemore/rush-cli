# Phase 72 memory acceptance

Status: provisional. This report records what Phase 72 has proven about memory correctness and user control and what is still open. No live lane has run. The 15 lanes below are `open`, each with one blocker, and no line states a result that was not observed. The sections `## 72-T07 walkthrough` and `## 72-T08 hybrid evaluation` are produced by their own tasks and pinned byte for byte by `tests/test_phase72_memory_acceptance.py::test_t09_report_schema`; the 72-T09 integration step places them after the sections below and never edits them.

## Source hash

No source freeze exists yet. The freeze commit F is cut after tasks 72-T02 to 72-T08, the portable capsule codec, the bootstrap consent task and the hybrid evaluator are integrated, and before any live lane runs. The live run replaces the lines below with the strict form and changes nothing else in this section.

```text
freeze_commit: not frozen
tree.src: not frozen
tree.tests: not frozen
tree.scripts: not frozen
tree..github: not frozen
phase70_ref: not observed
phase70_parity: not observed
```

## Installed artifact hash

No installed PyInstaller artifact has been built. The live run builds it from the freeze commit inside a temporary directory and records its digest here as `installed_artifact_sha256: <64 hex>`.

```text
installed_artifact_sha256: not built
```

## Commands

An example that a user document publishes carries a `t09-example` marker and must equal one machine-recorded receipt below, executed on the freeze commit. Name resolution and `--help` success are not execution. No example has been executed, so the receipt list is empty. Three marked examples wait for their receipts: `agents-grant-preview` and `agents-bind-store-preview` in `docs/user-guide/working-with-ai-agents.md`, and `tui-memory-search` in `docs/user-guide/interactive-tui.md`. `tests/test_phase72_memory_acceptance.py::test_t09_documented_memory_examples_match_receipts` fails until the live run executes each one on the freeze commit and records it here.

```json
[]
```

## Results

| Check | Test | State |
|---|---|---|
| Integrated route and scope (R1) | `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope` | not run against an integrated tree |
| Report schema (R2, R7) | `tests/test_phase72_memory_acceptance.py::test_t09_report_schema` | open: no freeze, and the 72-T07 and 72-T08 sections are not placed |
| CLI reference lists the memory leaves (R3) | `tests/test_phase72_memory_acceptance.py::test_t09_cli_reference_lists_memory_leaves` | documented; leaves from tasks not yet integrated cannot be enumerated |
| Truth labels (R4) | `tests/test_phase72_memory_acceptance.py::test_t09_docs_truth_labels` | claim table written in the architecture proposal; the other four documents are written by their owners |
| Receipt matches delivery (R5a) | `tests/test_phase72_memory_acceptance.py::test_t09_receipt_matches_delivery` | not run against an integrated tree |
| Route and mode matrix (R8) | `tests/test_phase72_memory_acceptance.py::test_t09_route_mode_matrix_complete` | not run: nine producer matrices are not integrated |
| Windows-only tests selected by CI (R9) | `tests/test_phase72_memory_acceptance.py::test_t09_windows_only_tests_selected_by_ci` | not run: producer selections are not integrated |
| Documented examples match receipts (RB-5) | `tests/test_phase72_memory_acceptance.py::test_t09_documented_memory_examples_match_receipts` | open: three marked examples have no receipt before the live run |
| Operation documents (R10) | `tests/test_phase72_memory_acceptance.py::test_t09_memory_operation_docs_parity` | the reference documents list 26 operations; the runtime enumeration is authoritative after integration |

## Platform and client versions

Observed on the pipeline host with a temporary home directory. The live run re-records them on the host that runs the lanes.

```text
python: 3.12.12
rush: 0.3.0
os: macOS 26.6.2 arm64
claude: 2.1.296 (Claude Code)
codex: codex-cli 0.162.1
pyinstaller: not installed in the project environment
gh: gh version 2.95.0 (2026-06-17)
```

## Grants

No grant has been written for acceptance. The live run writes each grant in a temporary data root and records its id as 8 characters followed by an ellipsis. The grants it needs are:

| Grant | Owner | Operations |
|---|---|---|
| Project grant | the project | `ask`, `list`, `expand`, `write`, `history` |
| Personal overlay grant | the user overlay | `list`, `overlay_read`, `write` |

## Lanes

| lane | implementation_gate | live_acceptance | blocker | evidence |
|---|---|---|---|---|
| `installed-artifact-cli-mcp` | `open` | `open` | No installed artifact has been built from a freeze commit | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes` |
| `dashboard-memory-api` | `open` | `open` | The dashboard memory routes are not run against an integrated tree | `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope` |
| `pty-terminal` | `open` | `open` | The terminal walkthrough has not run against an installed artifact | `tests/test_phase72_memory_acceptance.py::test_t09_live_pty_walkthrough` |
| `personal-overlay-two-projects` | `open` | `open` | The personal overlay across two projects has not run against an integrated tree | `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope` |
| `two-agent-same-project` | `open` | `open` | Agent A and agent B have not run on the same project | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent` |
| `e06-e25-rejection-reversal` | `open` | `open` | The held-out rejection and reversal cases have not run with two agents | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent` |
| `pas-import` | `open` | `open` | No PAS session has been imported through the installed artifact | `tests/test_phase72_memory_acceptance.py::test_t09_live_pas_import` |
| `portable-route-release` | `open` | `open` | Phase 73 73-T09 final release (75-T01 receipts, 75-T03/T04 budget and recovery) not landed | `docs/phase-plans/phase-73-agent-activation-and-continuity-plan.md` |
| `native-linux-ci` | `open` | `open` | The branch is not pushed, so the Linux CI lane has not run | `.github/workflows/ci.yml` |
| `native-windows-ci` | `open` | `open` | The branch is not pushed, so no `PASSED` line exists from `windows-latest` | `tests/test_phase72_memory_acceptance.py::test_t09_live_windows_console` |
| `native-macos` | `open` | `open` | The branch is not pushed, so the macOS CI lane has not run | `.github/workflows/ci.yml` |
| `hybrid-evaluation` | `open` | `open` | The 72-T08 hybrid verdict is not integrated | `docs/reports/phase-72-memory-eval/hybrid-verdict.json` |
| `r5b-frame-receipts` | `open` | `open` | Phase 75 75-T01 frame columns not landed | `tests/test_phase75_usage.py::test_memory_event_frame_receipt_columns` |
| `phase70-t28d-g5-g8` | `open` | `open` | Phase 70 T28-D gates G5 to G8 are outside the Phase 72 checks | `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` |
| `phase71-p07` | `open` | `open` | Phase 71 P07 builds the dashboard memory panel and its live browser acceptance | `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` |

## Failures and blockers

- No lane has run, so no lane has failed. Each open lane names its single blocker in the table above.
- The branch is not pushed. The Linux, Windows and macOS lanes need the branch on the remote, and the orchestrator pushes it only after the owner's go.
- PyInstaller is not installed in the project environment, so the installed artifact cannot be built until the live run supplies it inside a temporary directory.
- The three marked examples named under `## Commands` have no receipt until the freeze commit exists and the live run records them, so the examples test stays red until then.

## Plan-vs-code check

- The reference documents list 26 `rush_memory` operations and 35 `rush memory` leaves. The plan fixes the operation count at 22 existing, plus `preference`, `history`, `explain` and `capsule`. The runtime enumeration in `test_t09_memory_operation_docs_parity` and the Click walk in `test_t09_cli_reference_lists_memory_leaves` are authoritative once the producing tasks are integrated.
- `rush memory grant`, `rush memory revoke` and `rush memory bind-store` are CLI-only. No MCP operation writes a grant.
- The architecture proposal's primitives, lifecycle steps and tools are marked `proposed` because no code in `src/rush` implements them. Only the delta handoff and the redacted context recovery are marked `implemented`.
