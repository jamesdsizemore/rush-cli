# Phase 72 memory acceptance

Status: frozen and live-checked on `b25628e`. 7 of 15 lanes passed live acceptance against the PyInstaller artifact built from the freeze commit; the other 8 stay `open`, each with one blocker. Every receipt below was machine-recorded by a driver in `tests/test_phase72_memory_acceptance.py`. The sections `## 72-T07 walkthrough` and `## 72-T08 hybrid evaluation` were produced by their own tasks and are pinned byte for byte by `tests/test_phase72_memory_acceptance.py::test_t09_report_schema`.

## Source hash

The freeze commit carries the body `72-T09 freeze`. After it only documents change: `git diff b25628e HEAD -- src tests scripts .github` prints nothing.

```text
freeze_commit: b25628e98f9d1afb16d713e3f0f3549ec4f8b633
tree.src: 72d931518ebdd5822f1725d083788f75d4a33763
tree.tests: 7454f4b6b234f6868f27b6dcc44abbc9fd0d36b9
tree.scripts: c176153adc60cd5ce3f4d5e0082ca358a370e4be
tree..github: b2d6c8a12c1b37710ced105c03a7113a6b22cc94
phase70_ref: phase/70-agent-adoption-and-usability 23d5b45
phase70_parity: empty
```

## Installed artifact hash

Built from the freeze commit in a temporary directory with the `ci.yml` macOS recipe (`pyinstaller --onefile` from `rush_entry.py`, then `scripts.probe_installed_artifacts.build_release_archive` and `write_sha256sums`). The temporary directory was deleted after the build.

```text
installed_artifact_sha256: 2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779
archive: rush-darwin-arm64.tar.gz
archive_sha256: 3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600
```

## Commands

Each example a user document publishes carries a `t09-example` marker and equals one receipt below, executed on the freeze commit with a temporary HOME and project. A preview of `rush memory grant` needs `--expected-policy-revision` (73-T02 BOOTSTRAP-CONSENT A2.8), so the published grant example carries it.

```json
[
  {
    "example_id": "agents-grant-preview",
    "kind": "cli",
    "argv": [
      "rush",
      "memory",
      "grant",
      "--project",
      ".",
      "--source",
      "session_memory:record_turn",
      "--expected-policy-revision",
      "0",
      "--json"
    ],
    "frozen_commit": "b25628e98f9d1afb16d713e3f0f3549ec4f8b633",
    "exit_code": 0,
    "result_sha256": "afcb57015f06451140a1bfcc02552eac7a83ee866dfc0c7f3a1b3beb5d89580d"
  },
  {
    "example_id": "agents-bind-store-preview",
    "kind": "cli",
    "argv": [
      "rush",
      "memory",
      "bind-store",
      "--project",
      ".",
      "--json"
    ],
    "frozen_commit": "b25628e98f9d1afb16d713e3f0f3549ec4f8b633",
    "exit_code": 0,
    "result_sha256": "4b117b1d84db195b6b500153cfff824cd1ecdd5aabc4ca652819eeb82a02bb52"
  },
  {
    "example_id": "tui-memory-search",
    "kind": "tui",
    "keys": [
      "M",
      "/",
      "needle",
      "enter"
    ],
    "frozen_commit": "b25628e98f9d1afb16d713e3f0f3549ec4f8b633",
    "observed_sha256": "d72348d7449f831403e3d8060289adbdabf89b4a7deab406f66e829ad5c2824c",
    "result_sha256": "d72348d7449f831403e3d8060289adbdabf89b4a7deab406f66e829ad5c2824c"
  }
]
```

## Results

| Check | Test | State |
|---|---|---|
| Integrated route and scope (R1) | `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope` | passed in the full suite on the freeze tree |
| Report schema (R2, R7) | `tests/test_phase72_memory_acceptance.py::test_t09_report_schema` | passed |
| CLI reference lists the memory leaves (R3) | `tests/test_phase72_memory_acceptance.py::test_t09_cli_reference_lists_memory_leaves` | passed |
| Truth labels (R4) | `tests/test_phase72_memory_acceptance.py::test_t09_docs_truth_labels` | passed |
| Receipt matches delivery (R5a) | `tests/test_phase72_memory_acceptance.py::test_t09_receipt_matches_delivery` | passed |
| Route and mode matrix (R8) | `tests/test_phase72_memory_acceptance.py::test_t09_route_mode_matrix_complete` | passed |
| Windows-only tests selected by CI (R9) | `tests/test_phase72_memory_acceptance.py::test_t09_windows_only_tests_selected_by_ci` | passed |
| Documented examples match receipts (RB-5) | `tests/test_phase72_memory_acceptance.py::test_t09_documented_memory_examples_match_receipts` | passed |
| Operation documents (R10) | `tests/test_phase72_memory_acceptance.py::test_t09_memory_operation_docs_parity` | passed |
| Freeze source views (RB-1) | `tests/test_phase72_memory_acceptance.py::test_t09_freeze_source_views` | passed |

Full suite on freeze F6 `511414a` (`-m ''`, 8 shards, 3094 s wall): 13176 passed, 0 failed, 0 skipped. The ten matrices' 20499 cells ran inside R8, which collects them and requires every cell to pass. Two tests failed only under shard load and passed in the serial re-run, as they had in earlier runs: `tests/test_phase70_t28d_review1.py::test_r1_maintenance_never_creates_rows_or_enables_learning` (an in-flight apply outlived its deadline) and `tests/test_phase70_t5.py::test_stdio_core_and_full_profile_list_exact_tools_named_in_instructions` (`anyio.BrokenResourceError` from its stdio child). Both are fixed in `e309bf4` (drain deadline 30 s; `BrokenResourceError` tolerated only after both answers arrive). F7 `b25628e` differs from F6 by `e6ab3e3` (v2 maintain uses the request's project root), `e309bf4` and the regenerated 72-T07 section; the tests those commits touch pass (1100 attributed serially with no `.rush` writes, 91 for the two fixed flakes).

Lane receipts, as written by the drivers (`RUSH_T09_LIVE_ARCHIVE` and `RUSH_T09_LIVE_SUMS` naming the artifact above, `RUSH_T09_LIVE_AGENTS=1` for the two-agent driver):

```json
{
  "dashboard-memory-api": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "dashboard-memory-api",
    "steps": [
      {
        "argv_redacted": "dashboard list; dashboard list; dashboard expand",
        "expected": "write, read, correct, stale rejection and history on every transport",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "E_VERSION"
        ],
        "step": "a-f",
        "transcript_sha256": "d9274096a0bff2d28fd6cf4a2b33b1dabd00075808ddfd3d3780fbb9a040b696"
      },
      {
        "argv_redacted": "dashboard list",
        "expected": "revoked grant denied on the next use",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_PERMISSION"
        ],
        "step": "j",
        "transcript_sha256": "331722edebfa23dbd0fa7a93bbd44867a3de8eab1861cc2b4bd8d51428fefd59"
      }
    ],
    "version": "0.3.0"
  },
  "e06-e25-rejection-reversal": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "e06-e25-rejection-reversal",
    "steps": [
      {
        "argv_redacted": "codex exec --json",
        "expected": "strict JSON decision checked against persisted rows",
        "independent_check": "sqlite rows and MemoryTool readback",
        "observed": [
          "cited_refs",
          "decision"
        ],
        "step": "agent-b-2",
        "transcript_sha256": "6d4d12d06d6c674f9237fbcf13ee46c6c7d725a197d19261cabbaf6cef441938"
      },
      {
        "argv_redacted": "codex exec --json",
        "expected": "strict JSON decision checked against persisted rows",
        "independent_check": "sqlite rows and MemoryTool readback",
        "observed": [
          "cited_refs",
          "decision"
        ],
        "step": "agent-b-3",
        "transcript_sha256": "a15ef7123ea40706ca119f3593864a832b85b80154ef6d832b551b4c210a0bed"
      },
      {
        "argv_redacted": "codex exec --json",
        "expected": "strict JSON decision checked against persisted rows",
        "independent_check": "sqlite rows and MemoryTool readback",
        "observed": [
          "cited_refs",
          "decision"
        ],
        "step": "agent-b-4",
        "transcript_sha256": "7ce7e65a93a5077701dc6bdaa99a47a33e91c1755589b266f0871153e39154fb"
      },
      {
        "argv_redacted": "codex exec --json",
        "expected": "strict JSON decision checked against persisted rows",
        "independent_check": "sqlite rows and MemoryTool readback",
        "observed": [
          "cited_refs",
          "decision"
        ],
        "step": "agent-b-5",
        "transcript_sha256": "f48ea4c379f55b4c00c0494cc8190c608057fe602fc721eb06f29a58db7c90e3"
      }
    ],
    "version": "0.3.0"
  },
  "installed-artifact-cli-mcp": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "installed-artifact-cli-mcp",
    "steps": [
      {
        "argv_redacted": "mcp write; mcp list; dashboard list; mcp expand; mcp edit; mcp list; dashboard list; cli expand; mcp expand; dashboard expand; mcp edit; mcp history; cli history",
        "expected": "write, read, correct, stale rejection and history on every transport",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "E_VERSION",
          "E_VERSION",
          "E_VERSION",
          "E_VERSION",
          "OK",
          "OK"
        ],
        "step": "a-f",
        "transcript_sha256": "6bfe41410fb625c8048609d7bc6115314d044f33f1cf42066b60b65447d789d1"
      },
      {
        "argv_redacted": "mcp preference; mcp preference; mcp preference; cli preference; cli preference; cli preference; mcp preference; mcp preference; mcp preference; mcp list; mcp list",
        "expected": "personal key shared by two projects, private rows isolated",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK"
        ],
        "step": "g",
        "transcript_sha256": "81a7b44cae738784c1d68682de988e63da01fa92b84a671c3662d9bec9fec593"
      },
      {
        "argv_redacted": "mcp list",
        "expected": "cross-project owner refused",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_OWNER"
        ],
        "step": "h",
        "transcript_sha256": "e670592fa1f0acf5d72cc4a7cb683cdf3f3e9ef25cca4bb3967a0857a64c5ab6"
      },
      {
        "argv_redacted": "mcp list; dashboard list",
        "expected": "revoked grant denied on the next use",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_PERMISSION",
          "E_PERMISSION"
        ],
        "step": "j",
        "transcript_sha256": "8e7012ff96716688a045d68058a926d51bc11201954774e0a97475845212e603"
      }
    ],
    "version": "0.3.0"
  },
  "native-macos": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "native-macos",
    "steps": [
      {
        "argv_redacted": "mcp write; mcp list; dashboard list; mcp expand; mcp edit; mcp list; dashboard list; cli expand; mcp expand; dashboard expand; mcp edit; mcp history; cli history",
        "expected": "write, read, correct, stale rejection and history on every transport",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "E_VERSION",
          "E_VERSION",
          "E_VERSION",
          "E_VERSION",
          "OK",
          "OK"
        ],
        "step": "a-f",
        "transcript_sha256": "6bfe41410fb625c8048609d7bc6115314d044f33f1cf42066b60b65447d789d1"
      },
      {
        "argv_redacted": "mcp preference; mcp preference; mcp preference; cli preference; cli preference; cli preference; mcp preference; mcp preference; mcp preference; mcp list; mcp list",
        "expected": "personal key shared by two projects, private rows isolated",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK"
        ],
        "step": "g",
        "transcript_sha256": "81a7b44cae738784c1d68682de988e63da01fa92b84a671c3662d9bec9fec593"
      },
      {
        "argv_redacted": "mcp list",
        "expected": "cross-project owner refused",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_OWNER"
        ],
        "step": "h",
        "transcript_sha256": "e670592fa1f0acf5d72cc4a7cb683cdf3f3e9ef25cca4bb3967a0857a64c5ab6"
      },
      {
        "argv_redacted": "mcp list; dashboard list",
        "expected": "revoked grant denied on the next use",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_PERMISSION",
          "E_PERMISSION"
        ],
        "step": "j",
        "transcript_sha256": "8e7012ff96716688a045d68058a926d51bc11201954774e0a97475845212e603"
      }
    ],
    "version": "0.3.0"
  },
  "pas-import": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "pas-import",
    "steps": [
      {
        "argv_redacted": "cli capsule preview-import; cli capsule preview-import; cli capsule import",
        "expected": "PAS import: IMPORTED, imported_unverified, pending",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "OK"
        ],
        "step": "i",
        "transcript_sha256": "86e0484f047e6c10f6509dca899db5b59590f235db2ddfa8579293fc678cc9d3"
      },
      {
        "argv_redacted": "cli capsule preview-export; cli capsule export; cli capsule preview-import; cli capsule preview-import; cli capsule import",
        "expected": "Rush capsule round trip",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "OK",
          "OK",
          "OK"
        ],
        "step": "i2",
        "transcript_sha256": "afe74cfd8583bae1866a92095079eca34016398b9fe2fa8b2bf88a390015c299"
      },
      {
        "argv_redacted": "M",
        "expected": "Memory section opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "533286 characters",
        "step": "memory-section",
        "transcript_sha256": "d58c414926066d50c4756fa506f0636c381b68bfa61a63da11c6eecb5424bc72"
      },
      {
        "argv_redacted": "I",
        "expected": "import prompt opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526902 characters",
        "step": "import-open",
        "transcript_sha256": "ce4a87219e2ea16aac1f5c24c8be84fb54b0023b9099a45887114b5c027108b0"
      },
      {
        "argv_redacted": "text(145) enter",
        "expected": "records show as pending",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519237 characters",
        "step": "import-preview",
        "transcript_sha256": "09eccace5fb27c0352a86fa8a017afdabb785f63aab2f89088685dd85083396b"
      },
      {
        "argv_redacted": "escape",
        "expected": "review closes",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526449 characters",
        "step": "import-leave",
        "transcript_sha256": "5b64a679d2c223d7411f328d5ed59d85e77cbe6fcdac0c4148b87251779eb06a"
      }
    ],
    "version": "0.3.0"
  },
  "personal-overlay-two-projects": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "personal-overlay-two-projects",
    "steps": [
      {
        "argv_redacted": "mcp preference; mcp preference; mcp preference; cli preference; cli preference; cli preference; mcp preference; mcp preference; mcp preference; mcp list; mcp list",
        "expected": "personal key shared by two projects, private rows isolated",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK",
          "OK"
        ],
        "step": "g",
        "transcript_sha256": "81a7b44cae738784c1d68682de988e63da01fa92b84a671c3662d9bec9fec593"
      }
    ],
    "version": "0.3.0"
  },
  "pty-terminal": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "pty-terminal",
    "steps": [
      {
        "argv_redacted": "M",
        "expected": "Memory section opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "499101 characters",
        "step": "memory-section",
        "transcript_sha256": "4892440ddf2ca275a0a801db55f7e2d0c83289eab7051c8a02efdfd06b8f6d81"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "28f168d965d03e17e6f1392d193ae6226a7fb78642392775cf04de94d8d07448"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "89fa73a96089f562231d6508d6f372e390293141de23404c9ef4f40864087e33"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519686 characters",
        "step": "subject-cycle",
        "transcript_sha256": "c9716262196624b657bbe835f742c25e318f286ea13c2c075c07754a897c6f59"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519613 characters",
        "step": "subject-cycle",
        "transcript_sha256": "e782d8607d443f8b13336a9d8e1ecb5ec6bad36f8fa2a505b0bb948e06152a9a"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "095b7ed6c21c48518662749116f1dff5019942d65cc77058a7f9031160b32541"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "f4da21bfe1a1e0a92c65e8407117dc9c7c1cdbb253f990ae3d86084c48d642b0"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "485805 characters",
        "step": "subject-cycle",
        "transcript_sha256": "655f6169be891192e04328199991d4f104568ebb3b8403fbb9799f1933cf60ea"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519235 characters",
        "step": "hostile-row",
        "transcript_sha256": "16d02ddd8c8b1b79dbf0fa2a3aa48e41d228c449ac15ebe0a4672834c7d6992b"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "hostile-row",
        "transcript_sha256": "89fa73a96089f562231d6508d6f372e390293141de23404c9ef4f40864087e33"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519687 characters",
        "step": "hostile-row",
        "transcript_sha256": "f667a693cfdf38f93e568cddea2c8b3da63039087e81dbf93b97863bdcd81d18"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519613 characters",
        "step": "hostile-row",
        "transcript_sha256": "e782d8607d443f8b13336a9d8e1ecb5ec6bad36f8fa2a505b0bb948e06152a9a"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "hostile-row",
        "transcript_sha256": "095b7ed6c21c48518662749116f1dff5019942d65cc77058a7f9031160b32541"
      },
      {
        "argv_redacted": "j",
        "expected": "hostile row selected",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "527314 characters",
        "step": "hostile-select",
        "transcript_sha256": "b87103d325e622b52b7f4be005774d2ad0d958cc8984d6ccdb9b664e8c741b10"
      },
      {
        "argv_redacted": "S",
        "expected": "domain_knowledge lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "546095 characters",
        "step": "to-domain",
        "transcript_sha256": "589ff3bb14750061c31d9e5dee95942184195c44e982a63a5196e3084b379020"
      },
      {
        "argv_redacted": "S",
        "expected": "domain_knowledge lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "444405 characters",
        "step": "to-domain",
        "transcript_sha256": "a50769052f34360ab12fd89c45086e232d6e51f98f67c55a93db28afcda89da2"
      },
      {
        "argv_redacted": "/ text(6) enter",
        "expected": "query lists matches",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "300828 characters",
        "step": "search",
        "transcript_sha256": "4bb76e159a196ba6d1ca1c186f919031ba69b86b27af06e85f72765b4c687366"
      },
      {
        "argv_redacted": "]",
        "expected": "next page differs",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "492642 characters",
        "step": "page-forward",
        "transcript_sha256": "f6538f59bae4d1805bf5c198c0ebae62e61de2232eebaaa5cc4de3cf196c1328"
      },
      {
        "argv_redacted": "[",
        "expected": "first page returns",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "464539 characters",
        "step": "page-back",
        "transcript_sha256": "fb05a3e566b4ec6387f3d48282fe98ac4eb281c49e1181c385eb69e8722d430e"
      },
      {
        "argv_redacted": "x",
        "expected": "exact version expands",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519990 characters",
        "step": "expand",
        "transcript_sha256": "2c7f9c17b72556635132a6cb021f9ee3754958f010de32fb3e1da86b70e5aeeb"
      },
      {
        "argv_redacted": "v",
        "expected": "history opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "532909 characters",
        "step": "history",
        "transcript_sha256": "eee2dd7675f1be92bdc615d92e54a183213877879f42268a6c37158859235e04"
      },
      {
        "argv_redacted": "E",
        "expected": "explain opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "explain",
        "transcript_sha256": "f861b2478053c353903ba9d2d361f6d2b7e27c55cf9fd894f07c2687819ce222"
      },
      {
        "argv_redacted": "c escape",
        "expected": "cancel writes nothing",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519990 characters",
        "step": "correct-cancel",
        "transcript_sha256": "30580fca17a4ae5672e61aa4a07f08b16cd1539a78653c6d3a5374f8f59a7f6b"
      },
      {
        "argv_redacted": "c tab t e r m i n a l   c o r r e c t i o n tab n e e d l e   c o r r e c t e d   b y   t e r m i n a l enter",
        "expected": "preview shown, nothing persisted",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "553420 characters",
        "step": "correct-preview",
        "transcript_sha256": "0ddd84b9a36cf15258474da6ceb35f9f908ba52f455b6f9cad3c9a0ed7268113"
      },
      {
        "argv_redacted": "y",
        "expected": "version n+2 persisted",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "492264 characters",
        "step": "correct-apply",
        "transcript_sha256": "9adb50db0203b41455187c0ed92fb075c4e806752fbbee049f70dcd3f44ae4d8"
      },
      {
        "argv_redacted": "enter",
        "expected": "conflict keeps input",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "505561 characters",
        "step": "correct-conflict",
        "transcript_sha256": "ed9e82e425f8983ccc1cb4e9cbea00f84357f0a5c261f060c02ed025d4b4294c"
      },
      {
        "argv_redacted": "S",
        "expected": "revoked state shown",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526449 characters",
        "step": "revoked",
        "transcript_sha256": "ca2bf57c5284dca46cbc300f0ec82d56c350284d3c7eb05337af92f02ecb2977"
      },
      {
        "argv_redacted": "M",
        "expected": "expired state shown",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "547338 characters",
        "step": "expired",
        "transcript_sha256": "649cb6201585ebed5a270ca92258ba990cce76afa84201487f904b8e8dc52a43"
      }
    ],
    "version": "0.3.0"
  },
  "two-agent-same-project": {
    "archive_sha256": "3f282af910aa7dbd43ab86a7ea2b9fe1095cf640fbd800a890c3f24f03531600",
    "artifact_sha256": "2de374b62673f52661209ce6939ef2630079a807e8e5de20e0788f237631b779",
    "lane": "two-agent-same-project",
    "steps": [
      {
        "argv_redacted": "codex exec --json",
        "expected": "strict JSON decision checked against persisted rows",
        "independent_check": "sqlite rows and MemoryTool readback",
        "observed": [
          "cited_refs",
          "decision",
          "denied_without_content",
          "stale_v1"
        ],
        "step": "agent-b-0",
        "transcript_sha256": "b333bf3bc485c12034afe359578f7e31f1db087c7e6deaaf7307d455225890db"
      },
      {
        "argv_redacted": "codex exec --json",
        "expected": "strict JSON decision checked against persisted rows",
        "independent_check": "sqlite rows and MemoryTool readback",
        "observed": [
          "cited_refs",
          "decision",
          "denied_without_content",
          "stale_v1"
        ],
        "step": "agent-b-1",
        "transcript_sha256": "b00932c890ac0883a05ce84b3db46f16fb47866c0ecfa91cbd2486543ab198a8"
      }
    ],
    "version": "0.3.0"
  }
}
```

## Platform and client versions

```text
python: 3.12.12
rush: 0.3.0
os: macOS 26.6.2 arm64
claude: 2.1.296 (Claude Code)
codex: codex-cli 0.162.1
pyinstaller: 6.22.3 (temporary build environment from the freeze commit)
gh: gh version 2.95.0 (2026-06-17)
```

## Grants

Each driver writes its grants in a temporary data root that is deleted with the run; ids appear only as 8 characters followed by an ellipsis.

| Grant | Owner | Operations |
|---|---|---|
| Project grant | the project | `ask`, `list`, `expand`, `write`, `history` |
| Personal overlay grant | the user overlay | `list`, `overlay_read`, `write` |

## Lanes

| lane | implementation_gate | live_acceptance | blocker | evidence |
|---|---|---|---|---|
| `installed-artifact-cli-mcp` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `e8bc5ef445499d1924c00bd22c7a4c657ddbe75be4738b039b533fba160c0234` |
| `dashboard-memory-api` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `8e85709f3d7cc4d9395e45a5f7f3208bf53657f201d41afa50bad0362c43546e` |
| `pty-terminal` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_pty_walkthrough`, receipt sha256 `f9c24f9ad48509e819242c76a96095bb0dcd118d53d025523bd25dba30d5a10a` |
| `personal-overlay-two-projects` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `a1e2a41d83c2c6a124c2ced438e01f51111c1f2aa9a4b9c080ede6c292ce91ae` |
| `two-agent-same-project` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent`, receipt sha256 `47611a08f69722d1bae93323eede8a5dcc24d1d68b26bd86368ca47b0c778e92` |
| `e06-e25-rejection-reversal` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent`, receipt sha256 `626d113aac689483605e6d4655fc41a0886dd0e1d7f10385325e93f950103c69` |
| `pas-import` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_pas_import`, receipt sha256 `9e64de05c3dbb5f4f4a8db20bcc633579352e3cb81146daeb4997dc367b3ae86` |
| `portable-route-release` | `open` | `open` | Phase 73 73-T09 final release (75-T01 receipts, 75-T03/T04 budget and recovery) not landed | `docs/phase-plans/phase-73-agent-activation-and-continuity-plan.md` |
| `native-linux-ci` | `open` | `open` | The branch is not pushed, so the Linux CI lane has not run | `.github/workflows/ci.yml` |
| `native-windows-ci` | `open` | `open` | The branch is not pushed, so no `PASSED` line exists from `windows-latest` | `tests/test_phase72_memory_acceptance.py::test_t09_live_windows_console` |
| `native-macos` | `passed` | `open` | The branch is not pushed, so the macOS `artifact-probes` CI job has not run | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes` local run, receipt sha256 `e0ccb9e1daad1c1ca0c5d6480559e3b0b27b21bd1b87b2b7ccbace72530335bd` |
| `hybrid-evaluation` | `passed` | `open` | The Codex route is unavailable: its 32745-token route overhead exceeds the 16000-token case budget | `docs/reports/phase-72-memory-eval/hybrid-verdict.json` |
| `r5b-frame-receipts` | `open` | `open` | Phase 75 75-T01 frame columns not landed | `tests/test_phase75_usage.py::test_memory_event_frame_receipt_columns` |
| `phase70-t28d-g5-g8` | `open` | `open` | Phase 70 T28-D gates G5 to G8 are outside the Phase 72 checks | `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` |
| `phase71-p07` | `open` | `open` | Phase 71 P07 builds the dashboard memory panel and its live browser acceptance | `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` |

## Failures and blockers

- The branch is not pushed, so the Linux, Windows and macOS CI lanes have not run; the macOS lane's local driver passed (receipt above).
- The 72-T08 Codex route is `unavailable`: its router probe counts 32745 model tokens, including the user's `~/.codex/AGENTS.md` (4844 cl100k tokens), above the plan's 16000-token case budget. The global hybrid verdict is therefore `unavailable` and the hybrid default stays off.
- `portable-route-release`, `r5b-frame-receipts`, `phase70-t28d-g5-g8` and `phase71-p07` wait on Phase 73, Phase 75, Phase 70 and Phase 71 work outside this phase.
- Correction: the report on the previous freeze listed R8 as passed. It failed there: 324 matrix ids carried a `-producer-` suffix, which R8 rejects. On this freeze the ten matrices collect 20499 ids with no `-producer-` id and no uncovered (route, dimension, value) pair, and R8 runs every cell.
- G14 scope, from one `scripts/scope_gate.py` record per task commit: task commits changed 40 paths outside their packets' allowed paths. 7 are covered by gate amendments (72-T02 A13, 72-T04 A1 and A3, 72-T08 A1, 73-T09/CODEC A2b). 33 have no written approval in the packet, its gate amendments, `decisions.md` or the owner resolutions:
  - 72-T01 (11): `src/rush/memory/expiry.py`, `src/rush/memory/maintenance.py`, `tests/test_benchmark_memory.py`, `tests/test_memory_efficiency.py`, `tests/test_phase62_cache_gate.py`, `tests/test_phase72_portable_memory_policy.py`, `tests/test_phase49_trace_swarm_recorder.py`, `tests/test_phase58_checkpoint_journals.py`, `tests/test_phase61_migration.py`, and 2 GoalBuddy board files under `docs/goals/phase-72-memory-correctness/`.
  - 72-T02 (4): `scripts/benchmarks/memory.py`, `src/rush/mcp_support/request_models.py`, and 2 board files.
  - 73-T02/BOOTSTRAP-CONSENT (4): `scripts/benchmarks/coordination.py`, `local.py`, `providers.py`, `reporting.py` (typing only).
  - 73-T02/POLICY (12): 11 board files and `docs/reports/phase-64-66-documentation-coverage.md`.
  - 75-T02/EVALUATOR (2): `scripts/benchmarks/coordination.py`, `local.py` (typing only).
  - 72-T01 also changed the protected asserts of `test_t01_fix2_j1_noncanonical_backfill_survives_rewrite` and `test_t01_fix2_blob_content_never_rebound` (operands wrapped for typing), then restored their baseline assert AST; at the freeze they equal the baseline.

## Plan-vs-code check

- `rush memory grant` previews also require `--expected-policy-revision` (BOOTSTRAP-CONSENT A2.8); the working-with-AI-agents guide said a preview needed only `--project` and `--source` and now names the revision.
- A user-stated reversal of an explicit preference is a `preference correct` with `kind: "supersede"` on the rejection row (72-T05 §3.6.1). A second `record` of the same key and scope is a same-scope conflict that resolves `unresolved` (72-T05 R12); the two-agent driver uses the supersede form.
- `preference correct` with `kind: "correct"` writes the corrected version and promotes it to STATED, so the row moves from version n to n+2 (72-T05 §3.6.2 step 4); only `reject` is the n+1 case. The 72-T09 PTY driver on the previous freeze labelled its `correct` step `correct-apply`, "version n+1 persisted", although the step is a preview; it is now `correct-preview`, "preview shown, nothing persisted". The 72-T07 n+1 text (R14) is about a CLI `edit`, which is n+1.
- Plan L51/L55 (ordinary delivery needs a visible row that is usable as current) was broken on four surfaces, found by the R8 cells and fixed for this freeze: `memory_overview` listed and counted rejected, pending and task-bound rows; the dashboard legacy browse emitted them unqualified; the TUI memory table did not mark them; `_resolve_authorized_statement` accepted a rejected, pending or task-bound STATED row. `useful_memory_count` and the `rush status` memory count also counted them. `rush memory list` (v2 inspect, with a `rejected` badge) and the registry inventories show them by design.
- The v2 `maintain` route ran its maintenance cycle without the request's store root, so the cycle swept and locked the store of the process's working directory: it refused the request's rows as `not_visible` and created `.rush/memory.db` and the maintenance lock there. Found by a test-pollution watcher during integration (the matrix cells ran from the repository); fixed for this freeze, with `test_t06_v2_maintain_runs_on_the_request_project_not_the_cwd`.
- The TUI import form (`I`) takes a capsule path only (72-T07 §3.5), so a PAS session is imported through the CLI with `--format pas_v1` and a mapping, and the TUI review covers the Rush capsule of the same lane.
- `rush memory grant`, `rush memory revoke` and `rush memory bind-store` are CLI-only. No MCP operation writes a grant.

## 72-T07 walkthrough

Machine-generated by `tests/test_phase72_memory_ui.py::test_t07_pty_walkthrough`: keys written to a pty master, transcript bytes read back per step.

- installed entry sha256: `1423907cfd165c30c3b46cf3a3b08244627e36f56f84175e524e23427de32535`
- source tree sha256: `d37d4b9eb154de03166bf85daaf01f408c0eadfa3d7931930ab40b3059385a53`

| Step | Keys (hex) | Transcript sha256 | Observed |
|---|---|---|---|
| memory section | 1b4f5234 | `8a43dd2c19517c1293527f59f8f4988bb28cdf56c02c534d64e38fca815bd714` | Memory section drew the owner's rows |
| subject skill_pattern | 53 | `081cb0a8b50d31107221c6442a13b9482063b993fd7bdbd568f3c0567ed3eb82` | skill_pattern: listed alice-sk… |
| subject active_context | 53 | `3d2592a36dbbd93b9112a70dceab5afd1147471237970733c4062656efc2cd34` | active_context: listed alice-ac… |
| subject episodic | 53 | `637ba3bdfca296d10aeb614a5b003cb673c2935ff8422304d2941b088f4da436` | episodic: listed alice-ep… |
| subject preference | 53 | `20b010419068b4d3b462e4c110d0162754b4380dba48dc62d66c461b794a67c4` | preference: listed alice-pr… |
| subject failure | 53 | `e4c0b1158946947e047bcf0c533a7236d82b2bcf66ee6d20df69c52473a4a890` | failure: listed alice-fa… |
| subject architectural_decision | 53 | `87a4a9862ba9d21bda6033432948d763e60cea9d6f77bcff2470abea45799254` | architectural_decision: listed alice-ar… |
| subject domain_knowledge | 53 | `40528dce8758bf1277d46307d6f2bf18b23982fbf5482dc3019fd343a90b07de` | domain_knowledge: listed alice-dk-00 |
| search | 2f6e6565646c650d | `63e1ed97c4320edfec90a1e8d163e6cdbb7dd6bbc1e41cd6202003a9168c68d9` | search needle: first hit alice-dk-00 |
| clear search | 2f0d | `45e267dc84a9715d3c6648f6ba52404733b573e03913bd504b5e71096b27adbe` | search cleared: list reloaded |
| next page | 5d | `f64547150d0913ea808e37c288f0d75cf9e4c06eecb52fda9e687727d427491d` | page 2 starts at alice-dk-20 |
| previous page | 5b | `10701dba7d5ebb706b19a365174e04976d2640a537304929ed2c06779a51099e` | page 1 again at alice-dk-00 |
| expand | 78 | `6dacb6d60d27d8ea8972cef0cffbd24a626e1e86b3c7ef706516cb4c9e981186` | exact version expanded: alice-dk-00 v1 |
| history | 76 | `f0846f3cd0d6c5b49434e1a6663e04cc1a7bea80df036d1132fd933c9fdb1eaa` | Memory history panel drew |
| explain | 45 | `05d31c4e112a97e19c13e89016dbd6d57415dd879a87869e55f1552d93fb6230` | Memory explain panel drew |
| collapse | 2d | `64f6eb69c27655d24ef88eec90739015853cd159067a61a493d71fcb90edca65` | keys sent |
| correction preview | 630970747920636f7272656374696f6e096e6565646c6520636f7272656374656420627920746865207074792077616c6b7468726f7567680d | `e4ccc4c7b72b91461f906fa65c6d5f539f7549e29502780c44672d05a25d9db8` | keys sent |
| correction apply | 79 | `d5fe459ddb166e6b68fda8bffd8dc21b12c53f0a401127e9617fa7016d130d49` | keys sent |
| correction cancel | 636e657665722073617665641b | `2a22f30bf0209bdf16458438ed46ba92ebf7e1bcf595385f0ab32ae14d598b39` | keys sent |
| focus cycle | 0909090909 | `a187e502383fa3434acbc567684d37ea5b175c502fff56b787fcd4bf420045af` | focus: inspect>edit>search>filter>list |
| historical view | 66090909747275650d | `9b9c140b1c7c6179a951d51fc0bb511002fd680989d45c35e57ddde6157b2c24` | keys sent |
| hostile search | 2f686f7374696c656d61726b65720d | `ea15188c78015ea5f1ef57f025b079fb4926d4f49e602f8d34e95a0876b90f33` | keys sent |
| hostile row | 78 | `21182f32587b72f339747483753a83e8e931fa435382d3719009ff2532eccf28` | hostile row rendered as escaped text |
| revoked grant | 53 | `2b0be607c8ac2e4c9d276035449e584349487a40bf8c5d07d20e5b206815bfa9` | revoked grant: state shown |
| quit | 71 | `19619c2e4046b1dc3120c520bccef62a388c37462b4ca9980dac03fe1f1ed2b5` | keys sent |

## 72-T08 hybrid evaluation

Global verdict: `unavailable`. The Anthropic route measured `benefit`; the Codex route could not run, so the hybrid default is not switched on and `HYBRID_DEFAULT_VERDICT` stays `None`.

Six live commands, one per route and arm, each `env PYTHONPATH=src .venv/bin/python -m scripts.benchmarks.run --suite memory --decision-mode live --decision-route ROUTE --allow-live-route ROUTE --task-manifest tests/fixtures/phase75/task_manifest.json --variant ARM --seeds 1,2,3 --max-total-tokens 16000 --output docs/reports/phase-72-memory-eval/ARM/ROUTE`, with ROUTE in {`openai-codex-oauth-cli-live`, `anthropic-claude-code-live`} and ARM in {`current`, `hybrid`, `metadata`}. Raw reports: `docs/reports/phase-72-memory-eval/<arm>/<route>/memory-suite-report.json`; verdict: `docs/reports/phase-72-memory-eval/hybrid-verdict.json`.

```text
hybrid_verdict_sha256: 9a3b021b29d7f92c3ef87d5a1caa2d0a2caed21ef16b221a2ff9c2c62407f91a
phase72_cases_sha256: 235854622857c3a5a5149101cfd32113f554fa491825d1df2275722c562a32ff
embedding: nomic-embed-text 0a109f422b47 at http://127.0.0.1:11434
evaluator: normalized_contains v1
seeds: 1,2,3 (repetition labels)
max_total_tokens: 16000
source (anthropic arms): 95b56b5 plus the integration diff committed in 66cde17 (diff sha256 aa34fd66fabbec8f461d9f14c6c1204f3177fe2a70ae706a7da61c2049a403d1), run from a copy so later edits could not reach it
source (codex arms): 66cde17 plus the providers.py fix that records the instruction file the provider process loads
```

| route | arm | decisions | passed | literal recall@8 | paraphrase recall@8 | security inclusions | hybrid pages | fallback pages | provider tokens (p72 rows) | retrieval p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| `anthropic-claude-code-live` | `current` | 87 | 42 | 1.0 | 0.0 | 0 | 0 | 0 | 173980 | 55 |
| `anthropic-claude-code-live` | `hybrid` | 87 | 78 | 1.0 | 1.0 | 0 | 72 | 0 | 206120 | 992 |
| `anthropic-claude-code-live` | `metadata` | 87 | 30 | 0.667 | 0.0 | 0 | 0 | 0 | 177976 | 55 |
| `openai-codex-oauth-cli-live` | each arm | 0 | 0 | — | — | — | — | — | — | — |

- Anthropic route (Claude Code 2.1.296, route overhead 2192 tokens): provider verdict `benefit`, reason `paraphrase recall rose above chance`. Failures outside the 72 paired `p72-` rows are the same in every arm: 7 `budget_exhausted` and 2 `unknown_decision_field` on the earlier Phase 75 cases.
- Codex route (codex-cli 0.162.1): `unavailable`, reason `route_overhead_exceeds_budget`. Its router probe counted 32745 model tokens, which include the user's `~/.codex/AGENTS.md` (4844 cl100k tokens; no `codex exec` flag skips it and `CODEX_HOME` is never replaced), above the 16000-token case budget, so the D13a preflight ran no case. This is the open blocker of the `hybrid-evaluation` lane.
- Unknowns: the Codex route has no quality or cost evidence at this budget; the Anthropic result is one route, three seeds.
