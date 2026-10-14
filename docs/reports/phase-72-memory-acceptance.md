# Phase 72 memory acceptance

Status: frozen and live-checked on `8c9503c`. 7 of 15 lanes passed live acceptance against the PyInstaller artifact built from the freeze commit; the other 8 stay `open`, each with one blocker. Every receipt below was machine-recorded by a driver in `tests/test_phase72_memory_acceptance.py`. The sections `## 72-T07 walkthrough` and `## 72-T08 hybrid evaluation` were produced by their own tasks and are pinned byte for byte by `tests/test_phase72_memory_acceptance.py::test_t09_report_schema`.

## Source hash

The freeze commit carries the body `72-T09 freeze`. After it only documents change: `git diff 8c9503c HEAD -- src tests scripts .github` prints nothing.

```text
freeze_commit: 8c9503cc5b8e09880379d4cb423672a85f29daa4
tree.src: 75a72ec522c014121bcdba04de95f21e9b90a4e7
tree.tests: 2da87a4e3086f5f88ffaf054bf353c1ee9464af1
tree.scripts: c176153adc60cd5ce3f4d5e0082ca358a370e4be
tree..github: bfe68589b9f2ccb57ac507e779a2fe1c4984b1b4
phase70_ref: phase/70-agent-adoption-and-usability 23d5b45
phase70_parity: empty
```

## Installed artifact hash

Built from the freeze commit in a temporary directory with the `ci.yml` macOS recipe (`pyinstaller --onefile` from `rush_entry.py`, then `scripts.probe_installed_artifacts.build_release_archive` and `write_sha256sums`). The temporary directory was deleted after the build.

```text
installed_artifact_sha256: 7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f
archive: rush-darwin-arm64.tar.gz
archive_sha256: 02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8
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
    "frozen_commit": "8c9503cc5b8e09880379d4cb423672a85f29daa4",
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
    "frozen_commit": "8c9503cc5b8e09880379d4cb423672a85f29daa4",
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
    "frozen_commit": "8c9503cc5b8e09880379d4cb423672a85f29daa4",
    "observed_sha256": "c783db268683a381f560843fd78f830b3af0d0b83746a90981a85e495650bc00",
    "result_sha256": "c783db268683a381f560843fd78f830b3af0d0b83746a90981a85e495650bc00"
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

Lane receipts, as written by the drivers (`RUSH_T09_LIVE_ARCHIVE` and `RUSH_T09_LIVE_SUMS` naming the artifact above, `RUSH_T09_LIVE_AGENTS=1` for the two-agent driver):

```json
{
  "dashboard-memory-api": {
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
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
        "transcript_sha256": "8c79c3176c4fc4dff1facfd9291b6cc2969c1aa4b1762045fe2c933bbfd9c539"
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
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
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
        "transcript_sha256": "7167dc8fcbeb2055555f2881002abebad27c94c32991953f4bcc55eff7ea75c7"
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
        "transcript_sha256": "70d14e4fbf6bac43f4472e1b522c5ae1eb52fda78a7b486dd8de1b2c0324ebc4"
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
        "transcript_sha256": "784013d3a6b82544b2313efff8363423a36eb06d2476abdfebe9df44876efcd2"
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
        "transcript_sha256": "76ce359ee7b4ce2d2589e70389005e2e42c66e9ea5534887bf39317ed12b4ce8"
      }
    ],
    "version": "0.3.0"
  },
  "installed-artifact-cli-mcp": {
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
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
        "transcript_sha256": "f16dfbcbb86efcad2fe9d2293ab65c5b6446b165893fa4dd3d01e2739c1babcf"
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
        "transcript_sha256": "beb50b7d8882fadd036b9309ce1709b0d36b5170505d3e2ca6e7b7f401daaae3"
      },
      {
        "argv_redacted": "mcp list",
        "expected": "cross-project owner refused",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_OWNER"
        ],
        "step": "h",
        "transcript_sha256": "22c537aa8407ff562dfd84570f71c5b22e69fd679b65f353c34d7cabf250e130"
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
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
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
        "transcript_sha256": "f16dfbcbb86efcad2fe9d2293ab65c5b6446b165893fa4dd3d01e2739c1babcf"
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
        "transcript_sha256": "beb50b7d8882fadd036b9309ce1709b0d36b5170505d3e2ca6e7b7f401daaae3"
      },
      {
        "argv_redacted": "mcp list",
        "expected": "cross-project owner refused",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_OWNER"
        ],
        "step": "h",
        "transcript_sha256": "22c537aa8407ff562dfd84570f71c5b22e69fd679b65f353c34d7cabf250e130"
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
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
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
        "transcript_sha256": "9debfd172a5283e710ea85014619dbc0bbacf9fe51a8f3a5fd00cd12621d1b22"
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
        "transcript_sha256": "b7ac6fb1a156ff569c5c94de56fe0d9b8e44377b799ecfa7274787b7ffbca4a1"
      },
      {
        "argv_redacted": "M",
        "expected": "Memory section opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "506316 characters",
        "step": "memory-section",
        "transcript_sha256": "14bab65c699be6bf85429f1d07c77b5f0cd777c33e2e814b31d35cedabffe0eb"
      },
      {
        "argv_redacted": "I",
        "expected": "import prompt opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "533287 characters",
        "step": "import-open",
        "transcript_sha256": "bfb4cbc37a52ab362049e52574fe31cff4d1e397db1378c7ba89934d0a6cf4c1"
      },
      {
        "argv_redacted": "text(144) enter",
        "expected": "records show as pending",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519235 characters",
        "step": "import-preview",
        "transcript_sha256": "ae45a62e6677ee46f1130ab309302d297571c84ee341ef41b6d7d693561011c7"
      },
      {
        "argv_redacted": "escape",
        "expected": "review closes",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "533286 characters",
        "step": "import-leave",
        "transcript_sha256": "5d467cda57ca9d148f1d1ef102eb8ca00644864ad7508627776f4d90cdcc627b"
      }
    ],
    "version": "0.3.0"
  },
  "personal-overlay-two-projects": {
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
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
        "transcript_sha256": "beb50b7d8882fadd036b9309ce1709b0d36b5170505d3e2ca6e7b7f401daaae3"
      }
    ],
    "version": "0.3.0"
  },
  "pty-terminal": {
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
    "lane": "pty-terminal",
    "steps": [
      {
        "argv_redacted": "M",
        "expected": "Memory section opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "493760 characters",
        "step": "memory-section",
        "transcript_sha256": "f96f7e54302cfacd85c22250cb6dec477197887cf9d646c5d8cf8b0836d3d1fc"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "af1122222a777113854d102f52a4b6fde0acee940c0b9ee6507363ab68c57a75"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "bc9b5a4ace22ada901ee4741e00469f47d289010333d6ab4e42f4b0d137856fe"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519990 characters",
        "step": "subject-cycle",
        "transcript_sha256": "461ecf85a1844f9b586936b1bf3600c91611d0c2b36b763f18065a97e3993095"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526072 characters",
        "step": "subject-cycle",
        "transcript_sha256": "b73b2349d17a89162e08cfa04da6d93a404687bfa3ed4840bff42b2d85fc48d8"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519990 characters",
        "step": "subject-cycle",
        "transcript_sha256": "10f5e79dfadbf8c374f2b1b3d3a38bed24c36f4e1d5f055cf2ba5316818e1186"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526072 characters",
        "step": "subject-cycle",
        "transcript_sha256": "bacbd0149087156d239579c16ee67b7330c938700bf2a661965495705b31ff9d"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "492264 characters",
        "step": "subject-cycle",
        "transcript_sha256": "6b4b104e391a91fb5e6dc7cc5affb08a08697cd3dceea800e6515dbcaec9f50a"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "hostile-row",
        "transcript_sha256": "3ef5ac8d6813cfe14b2a616efcfa192cc33128feb6021ad40da76688db3a4fb3"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519990 characters",
        "step": "hostile-row",
        "transcript_sha256": "442046c09def62b398d19e2d31e792681c8f6959672c4ca7f150d86e6ac65601"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526450 characters",
        "step": "hostile-row",
        "transcript_sha256": "907fd269852e544d8d1ba77bf2d6aa1f9a3fdbcc0fabae68027d7af7d2209eeb"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526450 characters",
        "step": "hostile-row",
        "transcript_sha256": "78834b87cbbdfabf4e1b191d310e7a662dc19a50837b16e8aaa1ced10d094be7"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526450 characters",
        "step": "hostile-row",
        "transcript_sha256": "53dab3d64c3a4474212412611bc390fcbc5a53a1fc4c5449b32ac196fe41987a"
      },
      {
        "argv_redacted": "j",
        "expected": "hostile row selected",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "539746 characters",
        "step": "hostile-select",
        "transcript_sha256": "92410840b49e96b7912982b7de5a3e2926e0d5868f5d3e282130278c0f09ed52"
      },
      {
        "argv_redacted": "S",
        "expected": "domain_knowledge lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "540123 characters",
        "step": "to-domain",
        "transcript_sha256": "0104a1c16c005b2344deef5892bd9ff8aa50953920ab3a6acae02e10865f6243"
      },
      {
        "argv_redacted": "S",
        "expected": "domain_knowledge lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "499101 characters",
        "step": "to-domain",
        "transcript_sha256": "808e252959549922c45ba27d1836a61217e6523bb0904c6f4885b3cbb6b39c75"
      },
      {
        "argv_redacted": "/ text(6) enter",
        "expected": "query lists matches",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "search",
        "transcript_sha256": "84e21b99f761e589b3f7e2053a3e8ac9c04675b86caf94658df9d39212b5bd8a"
      },
      {
        "argv_redacted": "]",
        "expected": "next page differs",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "page-forward",
        "transcript_sha256": "61a702ede700450c7d333f30de12026a71af5629a5c3d86fb27d0f541df90dce"
      },
      {
        "argv_redacted": "[",
        "expected": "first page returns",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "499479 characters",
        "step": "page-back",
        "transcript_sha256": "3b9d01cb5205693421220a18960b25b8570eab041db170a69ba450787d56696f"
      },
      {
        "argv_redacted": "x",
        "expected": "exact version expands",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526072 characters",
        "step": "expand",
        "transcript_sha256": "797620e3f2ed1b1cf9552f08eb227f6116c34dcc51c7cfbb213601860277f1f0"
      },
      {
        "argv_redacted": "v",
        "expected": "history opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "513153 characters",
        "step": "history",
        "transcript_sha256": "8fe18fd7ae9e18c31341363a2d5e5eeeee68e941eb2d4711d7fe9d1bd3c9f913"
      },
      {
        "argv_redacted": "E",
        "expected": "explain opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519613 characters",
        "step": "explain",
        "transcript_sha256": "41125916a96ccc130c1c0b52b59843196a1802b164510fd512297a4b9faaf7c9"
      },
      {
        "argv_redacted": "c escape",
        "expected": "cancel writes nothing",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "546961 characters",
        "step": "correct-cancel",
        "transcript_sha256": "59a8801d83375ec34e0b886b98eeba77e36905716c60301737c3c0f31e053bf5"
      },
      {
        "argv_redacted": "c tab t e r m i n a l   c o r r e c t i o n tab n e e d l e   c o r r e c t e d   b y   t e r m i n a l enter",
        "expected": "version n+1 persisted",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "560257 characters",
        "step": "correct-apply",
        "transcript_sha256": "47d6f49b217e809850130fbc7b6a6ebc8f8a1157706a363500f8006504918c5e"
      },
      {
        "argv_redacted": "y",
        "expected": "version n+2 persisted",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "499101 characters",
        "step": "correct-apply",
        "transcript_sha256": "33d96e0a24c9dc19d5fd4236ed363836a7e3366b0510410d669dfda147dd9083"
      },
      {
        "argv_redacted": "enter",
        "expected": "conflict keeps input",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "505938 characters",
        "step": "correct-conflict",
        "transcript_sha256": "b8c04ac9475be186fcd5a97ccba8ab5384bb7909a611a273bfddbb1803c8d031"
      },
      {
        "argv_redacted": "S",
        "expected": "revoked state shown",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526449 characters",
        "step": "revoked",
        "transcript_sha256": "a280409db3e709aa2cee77a24a589e16a5fa69711f101d53248944891b907b45"
      },
      {
        "argv_redacted": "M",
        "expected": "expired state shown",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "546583 characters",
        "step": "expired",
        "transcript_sha256": "11393fe1a72f4bf6b636ef00cd8e6976d719daea266e1c6e6198b8bb260a4537"
      }
    ],
    "version": "0.3.0"
  },
  "two-agent-same-project": {
    "archive_sha256": "02214f7c62d333aa143fdcf8ed6b3ad85f07e5cb77bd7e9f0381a92c465bc1c8",
    "artifact_sha256": "7172ae181917007eb9e1b4fa1335fa08292dfa283464754d23ac7a4264997e9f",
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
        "transcript_sha256": "e7601bf2e4b6aa2fa8780a99d3c7b1a2246483b8cbd1ffb26950934de5ac1025"
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
        "transcript_sha256": "920e1d1b8a56524df46ded95e21e713f06f73d034c3ec1de57e0a2aab7d1a583"
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
| `installed-artifact-cli-mcp` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `52daf095eb1458772e1e403d98cb8d7e0d83ac0ebc92d02e52397de467725f91` |
| `dashboard-memory-api` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `614a25806a02e5fd9b1c4efa14514534f0886166bf4340ab371a018a9135e367` |
| `pty-terminal` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_pty_walkthrough`, receipt sha256 `4f28993169c01a6cf80e90a1a792c4c3b5f07529d4787c8c2d5da7cc8e11cae6` |
| `personal-overlay-two-projects` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `a6764372db9fbcd690262cf2d19b5105f88201315b6b29a33e298683ac6cdf53` |
| `two-agent-same-project` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent`, receipt sha256 `73f71e8d24e1e2f9a6c57daf994eb03ac3ef5260540c67f650432c242f492e66` |
| `e06-e25-rejection-reversal` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent`, receipt sha256 `33bba09202a4d2931feca47343ef9883272ca1bb1c889400f8700c5690889e12` |
| `pas-import` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_pas_import`, receipt sha256 `249e9f2473bd610a002e01c43592788ab47017b20a36e171a3d5aa55fc7ad865` |
| `portable-route-release` | `open` | `open` | Phase 73 73-T09 final release (75-T01 receipts, 75-T03/T04 budget and recovery) not landed | `docs/phase-plans/phase-73-agent-activation-and-continuity-plan.md` |
| `native-linux-ci` | `open` | `open` | The branch is not pushed, so the Linux CI lane has not run | `.github/workflows/ci.yml` |
| `native-windows-ci` | `open` | `open` | The branch is not pushed, so no `PASSED` line exists from `windows-latest` | `tests/test_phase72_memory_acceptance.py::test_t09_live_windows_console` |
| `native-macos` | `passed` | `open` | The branch is not pushed, so the macOS `artifact-probes` CI job has not run | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes` local run, receipt sha256 `edd50582c47a6e994a92878860f7c393e6c15cd9d67a70338c79f3b691f7d09e` |
| `hybrid-evaluation` | `passed` | `open` | The Codex route is unavailable: its 32745-token route overhead exceeds the 16000-token case budget | `docs/reports/phase-72-memory-eval/hybrid-verdict.json` |
| `r5b-frame-receipts` | `open` | `open` | Phase 75 75-T01 frame columns not landed | `tests/test_phase75_usage.py::test_memory_event_frame_receipt_columns` |
| `phase70-t28d-g5-g8` | `open` | `open` | Phase 70 T28-D gates G5 to G8 are outside the Phase 72 checks | `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` |
| `phase71-p07` | `open` | `open` | Phase 71 P07 builds the dashboard memory panel and its live browser acceptance | `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` |

## Failures and blockers

- The branch is not pushed, so the Linux, Windows and macOS CI lanes have not run; the macOS lane's local driver passed (receipt above).
- The 72-T08 Codex route is `unavailable`: its router probe counts 32745 model tokens, including the user's `~/.codex/AGENTS.md` (4844 cl100k tokens), above the plan's 16000-token case budget. The global hybrid verdict is therefore `unavailable` and the hybrid default stays off.
- `portable-route-release`, `r5b-frame-receipts`, `phase70-t28d-g5-g8` and `phase71-p07` wait on Phase 73, Phase 75, Phase 70 and Phase 71 work outside this phase.

## Plan-vs-code check

- `rush memory grant` previews also require `--expected-policy-revision` (BOOTSTRAP-CONSENT A2.8); the working-with-AI-agents guide said a preview needed only `--project` and `--source` and now names the revision.
- A user-stated reversal of an explicit preference is a `preference correct` with `kind: "supersede"` on the rejection row (72-T05 §3.6.1). A second `record` of the same key and scope is a same-scope conflict that resolves `unresolved` (72-T05 R12); the two-agent driver uses the supersede form.
- `preference correct` with `kind: "correct"` writes the corrected version and promotes it to STATED, so the row moves from version n to n+2 (72-T05 §3.6.2 step 4); only `reject` is the n+1 case. The 72-T07 and 72-T09 walkthrough texts say n+1.
- The TUI import form (`I`) takes a capsule path only (72-T07 §3.5), so a PAS session is imported through the CLI with `--format pas_v1` and a mapping, and the TUI review covers the Rush capsule of the same lane.
- `rush memory grant`, `rush memory revoke` and `rush memory bind-store` are CLI-only. No MCP operation writes a grant.

## 72-T07 walkthrough

Machine-generated by `tests/test_phase72_memory_ui.py::test_t07_pty_walkthrough`: keys written to a pty master, transcript bytes read back per step.

- installed entry sha256: `1423907cfd165c30c3b46cf3a3b08244627e36f56f84175e524e23427de32535`
- source tree sha256: `f08097d890745cb56b9027c19f5c4e7ad1c148462c9bcaae4be84efd8cd96e10`

| Step | Keys (hex) | Transcript sha256 | Observed |
|---|---|---|---|
| memory section | 1b4f5234 | `ce90612f623d89a9f444883b61c3ae81f76a39f609e781f14500a510ea5fc769` | Memory section drew the owner's rows |
| subject skill_pattern | 53 | `f49c0059a57d4a18da49f0f770f8f160729f03acebec636401af0a08420025a9` | skill_pattern: listed alice-sk… |
| subject active_context | 53 | `6fa025a9a23dfd3a97b0a00bca7a2a864819a5f9d9fba77704488387a23bd70b` | active_context: listed alice-ac… |
| subject episodic | 53 | `3979d0351b5c7f383430220373acd3459893b66deb45bbcd2999fc73ef901096` | episodic: listed alice-ep… |
| subject preference | 53 | `b25a191dff7d74f1386706769928ba85fbd931c59a62e5524fe09ef49ef58dd2` | preference: listed alice-pr… |
| subject failure | 53 | `9d27b187d508cdd7f0472024f62d2d9fb74814d38b1c86debbd6c916a2b358ff` | failure: listed alice-fa… |
| subject architectural_decision | 53 | `b41bafc0f460edcded56cf88a1be7f8e546f5c713ff168d69a423c2ae22b303f` | architectural_decision: listed alice-ar… |
| subject domain_knowledge | 53 | `bb66a031c3502189d71c391f3105d9c5cf1fe274d9012b083dfece5b7610e10b` | domain_knowledge: listed alice-dk-00 |
| search | 2f6e6565646c650d | `1043f6905335f8ac37291417c6774770f86badbe16f6ebaa2804fcd43c700189` | search needle: first hit alice-dk-00 |
| clear search | 2f0d | `aba0f719bc456553135d0d60ff42750d1bc7c46fe2b9c4972d91c173a0a85acd` | search cleared: list reloaded |
| next page | 5d | `fda098b5ee769f035da652ef7599912013c3f7c32ee396f05a706e5b3957ae51` | page 2 starts at alice-dk-20 |
| previous page | 5b | `d99017f6671db010612a082fd5e6a539c836c15f905d61a4cc55c72fa4896927` | page 1 again at alice-dk-00 |
| expand | 78 | `b695cb39a6a462dc9ab1310e2d7186aa80c713deb56bd37280d5fb725da1f3fc` | exact version expanded: alice-dk-00 v1 |
| history | 76 | `f0846f3cd0d6c5b49434e1a6663e04cc1a7bea80df036d1132fd933c9fdb1eaa` | Memory history panel drew |
| explain | 45 | `05d31c4e112a97e19c13e89016dbd6d57415dd879a87869e55f1552d93fb6230` | Memory explain panel drew |
| collapse | 2d | `56715391dca0b6b73e3f72bc095e7d830ebced4ebfeeef38d8e6052e73be897e` | keys sent |
| correction preview | 630970747920636f7272656374696f6e096e6565646c6520636f7272656374656420627920746865207074792077616c6b7468726f7567680d | `bac8acf06e08b4777f87028f353fa3d7bfe3ac09e10ffdaa049890b577a871e6` | keys sent |
| correction apply | 79 | `bc57c33d8a45cd5b08e7fb951a45114c3374fc1bc121694daf9b3c956ed76c6a` | keys sent |
| correction cancel | 636e657665722073617665641b | `0c2829059b9e5ae8e32ffaa04d8e3e7d8349aa6a6e3b27116f566764dcc33f27` | keys sent |
| focus cycle | 0909090909 | `e613cfa190e79afc0b679316e44dca826c015a3945b9e816e170036e40af4392` | focus: inspect>edit>search>filter>list |
| historical view | 66090909747275650d | `7dfe7583c67be4e91d1577c5742796a563c0bfcedef3c1883705b055d1ae1b60` | keys sent |
| hostile search | 2f686f7374696c656d61726b65720d | `5fc492979230861c1e7a78965612426fd864fe3599b8246373fc11eb90feda17` | keys sent |
| hostile row | 78 | `1ae2d0dfc5b6d2728efc505791374db19e4dc8fde7e47cac3067ce833f206a06` | hostile row rendered as escaped text |
| revoked grant | 53 | `ba59645c333fb7f439eedb22c2fdb33d351484b5a945fc7e28a3376e67ab1868` | revoked grant: state shown |
| quit | 71 | `ffc819dcf78e911ca5b2d5c6157c2834b03517e7fb6aea0e5728a0266909fd42` | keys sent |

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
