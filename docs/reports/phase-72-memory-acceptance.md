# Phase 72 memory acceptance

Status: frozen and live-checked on `c3c499b`. 7 of 15 lanes passed live acceptance against the PyInstaller artifact built from the freeze commit; the other 8 stay `open`, each with one blocker. Every receipt below was machine-recorded by a driver in `tests/test_phase72_memory_acceptance.py`. The sections `## 72-T07 walkthrough` and `## 72-T08 hybrid evaluation` were produced by their own tasks and are pinned byte for byte by `tests/test_phase72_memory_acceptance.py::test_t09_report_schema`.

## Source hash

The freeze commit carries the body `72-T09 freeze`. After it only documents change: `git diff c3c499b HEAD -- src tests scripts .github` prints nothing.

```text
freeze_commit: c3c499b4f4f29bcb677d223ff355e9d2501f8217
tree.src: 680476ed19ae73e61877cedd58731c21627edf6e
tree.tests: 81d23f76edf9e7033b3c9f49fb465be9d141b7c6
tree.scripts: c176153adc60cd5ce3f4d5e0082ca358a370e4be
tree..github: bfe68589b9f2ccb57ac507e779a2fe1c4984b1b4
phase70_ref: phase/70-agent-adoption-and-usability 23d5b45
phase70_parity: empty
```

## Installed artifact hash

Built from the freeze commit in a temporary directory with the `ci.yml` macOS recipe (`pyinstaller --onefile` from `rush_entry.py`, then `scripts.probe_installed_artifacts.build_release_archive` and `write_sha256sums`). The temporary directory was deleted after the build.

```text
installed_artifact_sha256: 6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9
archive: rush-darwin-arm64.tar.gz
archive_sha256: 1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752
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
    "frozen_commit": "c3c499b4f4f29bcb677d223ff355e9d2501f8217",
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
    "frozen_commit": "c3c499b4f4f29bcb677d223ff355e9d2501f8217",
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
    "frozen_commit": "c3c499b4f4f29bcb677d223ff355e9d2501f8217",
    "observed_sha256": "417648d136bc8f5b03865ca40ad71e9ef6eba0f37a759c9e31100229ba826816",
    "result_sha256": "417648d136bc8f5b03865ca40ad71e9ef6eba0f37a759c9e31100229ba826816"
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
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
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
        "transcript_sha256": "f0631ade5613c13485fc749c6502b555119c938bd674ee7557f6b5c2c5cb3b6c"
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
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
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
        "transcript_sha256": "7f3e7535bc5ab4b3fb88273c2dbfe2d367134fa755ab254d04401bb9fd67e082"
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
        "transcript_sha256": "34c2fc6d50048aa989909760f76e5cb9105f53f09175710da220076b68bb7cec"
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
        "transcript_sha256": "3b2db662724657a3efdf5cb4db719fba74a8d12d229ee3b7886335620975d89a"
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
        "transcript_sha256": "52852110ccbe4ac4eb69d2c1f271b29715029baaf0f199d306d18d1d5777815a"
      }
    ],
    "version": "0.3.0"
  },
  "installed-artifact-cli-mcp": {
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
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
        "transcript_sha256": "91a78c2fbb6eb5576506f9e30ac5e7c4886faf684c06de5c36266a7fbc4c4967"
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
        "transcript_sha256": "c65f749422b996e9c10f7bb2698dcb40475512f1f5b787a79299da4c49388192"
      },
      {
        "argv_redacted": "mcp list",
        "expected": "cross-project owner refused",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_OWNER"
        ],
        "step": "h",
        "transcript_sha256": "bbd536a375bfda182a032864eda105b9fbe8604ee5d73e7a2d67f4c2e94f57cc"
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
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
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
        "transcript_sha256": "91a78c2fbb6eb5576506f9e30ac5e7c4886faf684c06de5c36266a7fbc4c4967"
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
        "transcript_sha256": "c65f749422b996e9c10f7bb2698dcb40475512f1f5b787a79299da4c49388192"
      },
      {
        "argv_redacted": "mcp list",
        "expected": "cross-project owner refused",
        "independent_check": "persisted sqlite rows and file digests read back",
        "observed": [
          "E_OWNER"
        ],
        "step": "h",
        "transcript_sha256": "bbd536a375bfda182a032864eda105b9fbe8604ee5d73e7a2d67f4c2e94f57cc"
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
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
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
        "transcript_sha256": "b659c5d8e1ffb9880bebf9bf5243bd4e441ea28dff351f6c586001431fc00839"
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
        "transcript_sha256": "c46b6f5d03bbdab538bbb5d221da59b7c298ff9390148ca71d29845348ca1b44"
      },
      {
        "argv_redacted": "M",
        "expected": "Memory section opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "540123 characters",
        "step": "memory-section",
        "transcript_sha256": "1104e8ef41a56bfb1735458acd90e6b7e2e7775e892ede4b96018643b40273a8"
      },
      {
        "argv_redacted": "I",
        "expected": "import prompt opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526827 characters",
        "step": "import-open",
        "transcript_sha256": "f85dde7e9d630c872135caaaf5bfb817e2c02023293c33dd4bb6df1858a8eb77"
      },
      {
        "argv_redacted": "text(145) enter",
        "expected": "records show as pending",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526072 characters",
        "step": "import-preview",
        "transcript_sha256": "cf5a4d5a7d7dbd139684233be37e14ccc934269c8cad4e03a68c63c1a44b11f1"
      },
      {
        "argv_redacted": "escape",
        "expected": "review closes",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "import-leave",
        "transcript_sha256": "99e97595707e4f43a6c5c7ad325e8b61b0a265072c7871190d1d700c652ffe5b"
      }
    ],
    "version": "0.3.0"
  },
  "personal-overlay-two-projects": {
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
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
        "transcript_sha256": "c65f749422b996e9c10f7bb2698dcb40475512f1f5b787a79299da4c49388192"
      }
    ],
    "version": "0.3.0"
  },
  "pty-terminal": {
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
    "lane": "pty-terminal",
    "steps": [
      {
        "argv_redacted": "M",
        "expected": "Memory section opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512398 characters",
        "step": "memory-section",
        "transcript_sha256": "b5f0b2693ee868732a6fb7394ff97616932754a0985748974801d008ed1c4434"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "c18e99a4842d4a6a232ea977182723e4da9755910fc2c2d4b0eb60e9b237754c"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "subject-cycle",
        "transcript_sha256": "9d00697799dc851dd270007fcbd416b94995e7db0fffa3069f88517ca20b0fc5"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519990 characters",
        "step": "subject-cycle",
        "transcript_sha256": "dd524d72a823c5e3669053612ca446c81621b2baf2921db02214e3f6fcfd4e96"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519235 characters",
        "step": "subject-cycle",
        "transcript_sha256": "90f62de3c192b33f721a4bdbb090894753ca3b3bc1e1bf3a49ed8a194ee21410"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "subject-cycle",
        "transcript_sha256": "f5444d947fa5574a4b2225726f90786a853bec6c4bf10c76325beec9f69a7c39"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "subject-cycle",
        "transcript_sha256": "bf3aff4cfa9ecdac2609c333db3fe02437db0ee8d586cff4878188d3ca03654b"
      },
      {
        "argv_redacted": "S",
        "expected": "next subject lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "492264 characters",
        "step": "subject-cycle",
        "transcript_sha256": "b0f4b0034dcd8f8c796a8143f6032689168b726de2ec174a7733670008f6d77c"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "hostile-row",
        "transcript_sha256": "c18e99a4842d4a6a232ea977182723e4da9755910fc2c2d4b0eb60e9b237754c"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "505938 characters",
        "step": "hostile-row",
        "transcript_sha256": "00e8015acd78372931d43fcb31c548eb47f7022f294675d2cfd31cf58e0288fe"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "hostile-row",
        "transcript_sha256": "ffa102880f3671dcc493d5eb253ede63afec3ad3ec45671ff6dcce276c4bdfe5"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "hostile-row",
        "transcript_sha256": "6770c1c19560a53b09b07d175ca7cfb6424079dbfa7d86848450fb085a5660fd"
      },
      {
        "argv_redacted": "S",
        "expected": "failure rows list",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "519612 characters",
        "step": "hostile-row",
        "transcript_sha256": "8f2062af7268b398f0acf17fd06a4d980987294ec1d00860547b5704395bd511"
      },
      {
        "argv_redacted": "j",
        "expected": "hostile row selected",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "hostile-select",
        "transcript_sha256": "b93a7c45ce53891feb682a2a3c080169d813c57bf3d26a38c9ef83bab9cd2930"
      },
      {
        "argv_redacted": "S",
        "expected": "domain_knowledge lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "533286 characters",
        "step": "to-domain",
        "transcript_sha256": "7c7159812cfe79cca9d088abc236f20ca8578de5945c9bbae6e31a8631b7e98c"
      },
      {
        "argv_redacted": "S",
        "expected": "domain_knowledge lists",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "492264 characters",
        "step": "to-domain",
        "transcript_sha256": "0722ee1a9ff2fe336f251690ca925bb03c7aebea223691340fa11093b9bf5001"
      },
      {
        "argv_redacted": "/ text(6) enter",
        "expected": "query lists matches",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "search",
        "transcript_sha256": "0ee86247de531e05182753c1f0f7e15feb209dec25b2ed1a461cdd83f6b6b61b"
      },
      {
        "argv_redacted": "]",
        "expected": "next page differs",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "505938 characters",
        "step": "page-forward",
        "transcript_sha256": "60e1f24beea5507cd9d00887335b28e92acab3467d293028264cc54f5895b426"
      },
      {
        "argv_redacted": "[",
        "expected": "first page returns",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "492264 characters",
        "step": "page-back",
        "transcript_sha256": "48fc24a843e00e30e0d2c083dbd70f319c2ca4ebb136953e866326a6407cfaca"
      },
      {
        "argv_redacted": "x",
        "expected": "exact version expands",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "expand",
        "transcript_sha256": "fb07bd6e662ab0ee53540f26879e115fde96c0d23803149d3c67cd31b548e074"
      },
      {
        "argv_redacted": "v",
        "expected": "history opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "history",
        "transcript_sha256": "3def1c9fdd12ef0c9dd692905ba3e000d8a6d7a6fc5f73ce537331402cdba2a3"
      },
      {
        "argv_redacted": "E",
        "expected": "explain opens",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "512775 characters",
        "step": "explain",
        "transcript_sha256": "50821fa876e9ec6e69bc0bbb4d576a9eb336721a12c9b8c67c7a21e7195fd36c"
      },
      {
        "argv_redacted": "c escape",
        "expected": "cancel writes nothing",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526449 characters",
        "step": "correct-cancel",
        "transcript_sha256": "f1773ef008e2d14f3089df395bb754fd3049d2ea1e7b9a9531fffc7fe3168ef7"
      },
      {
        "argv_redacted": "c tab t e r m i n a l   c o r r e c t i o n tab n e e d l e   c o r r e c t e d   b y   t e r m i n a l enter",
        "expected": "version n+1 persisted",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "533664 characters",
        "step": "correct-apply",
        "transcript_sha256": "9259a64e1063771a9a0b98db5051f66413dbb1bd4bad1d1a8a37e0de98a0b978"
      },
      {
        "argv_redacted": "y",
        "expected": "version n+2 persisted",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "498724 characters",
        "step": "correct-apply",
        "transcript_sha256": "fa09af437a5efd3316af61fa754f9a57b4dc35ae9132f1654dab6a88d950c26b"
      },
      {
        "argv_redacted": "enter",
        "expected": "conflict keeps input",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "499101 characters",
        "step": "correct-conflict",
        "transcript_sha256": "9c734f898b6f3a3cedfec89d01d701bc2640af58a946fcd0a877a20a9b9cc11c"
      },
      {
        "argv_redacted": "S",
        "expected": "revoked state shown",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "526072 characters",
        "step": "revoked",
        "transcript_sha256": "a1c11503a255487c051e2bf3fd24435c1be11964dd73bed8bb60985af07437b3"
      },
      {
        "argv_redacted": "M",
        "expected": "expired state shown",
        "independent_check": "MemoryTool and sqlite readback in the driver",
        "observed": "533286 characters",
        "step": "expired",
        "transcript_sha256": "75fd46373da00b1a47ca70f90b8ddaf3d2b6a8eb58e629927372f84ba8ec1637"
      }
    ],
    "version": "0.3.0"
  },
  "two-agent-same-project": {
    "archive_sha256": "1bf04aa15d0d8bc7ef351e245ab8b61159fdad3ff946526f06d8892d49ce8752",
    "artifact_sha256": "6fc86d5669abb4841e448ec3a75e90511d96215e9e308eb6daeeb22e76d873c9",
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
        "transcript_sha256": "d7c89416363ef941ba19a42a6e2da8f83667f26863aa4bd12ab42426cc03f5f1"
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
        "transcript_sha256": "9f2e616ee1cb6d754edd53a7d5df615b0f33d2bd885193b5a3cbb9d355abc1ef"
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
| `installed-artifact-cli-mcp` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `9eab5cb65a88258b3f2d6ca94cd7c0c129c5ca981cf3632766217a5202405516` |
| `dashboard-memory-api` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `8aee958923068c1e3829f05f91ff073580855950f710198acc0ae3726dcc9044` |
| `pty-terminal` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_pty_walkthrough`, receipt sha256 `22b9e7a46118c4bb1a60b27f4b0bcfef573bc250867c10b2c751ac60e9711fdd` |
| `personal-overlay-two-projects` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes`, receipt sha256 `4f1a5905afebd0ab37f2820377bb5f0eb07e967d9b35e9c7051a3895f9d56aa3` |
| `two-agent-same-project` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent`, receipt sha256 `33ddc594fd2ac03712d51331357db0d72ba8ac2ff3e100c30e1cfe2664786920` |
| `e06-e25-rejection-reversal` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_two_agent`, receipt sha256 `123cb8e5e5386548a2bc3aa5832dad94df29b4ca5c42fcae8ab7283c1d4d6561` |
| `pas-import` | `passed` | `passed` | — | `tests/test_phase72_memory_acceptance.py::test_t09_live_pas_import`, receipt sha256 `5e76b8f02b53bdcd2d613674ccff40d22c383ebdf303f5a17a840b6e8a390f2d` |
| `portable-route-release` | `open` | `open` | Phase 73 73-T09 final release (75-T01 receipts, 75-T03/T04 budget and recovery) not landed | `docs/phase-plans/phase-73-agent-activation-and-continuity-plan.md` |
| `native-linux-ci` | `open` | `open` | The branch is not pushed, so the Linux CI lane has not run | `.github/workflows/ci.yml` |
| `native-windows-ci` | `open` | `open` | The branch is not pushed, so no `PASSED` line exists from `windows-latest` | `tests/test_phase72_memory_acceptance.py::test_t09_live_windows_console` |
| `native-macos` | `passed` | `open` | The branch is not pushed, so the macOS `artifact-probes` CI job has not run | `tests/test_phase72_memory_acceptance.py::test_t09_live_installed_routes` local run, receipt sha256 `d863d9247d5b8b8316226b6fcf043cd87fbb61b9abb977ea0fd3c6101dc4be9a` |
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
- source tree sha256: `ab61b2c575aaa96b551e67d595b08c26daa6e0a1deb91c13e164d68f048d7826`

| Step | Keys (hex) | Transcript sha256 | Observed |
|---|---|---|---|
| memory section | 1b4f5234 | `d462bfca7fef252d18677323559d310356405557310e81a17d9841b04ee68a03` | Memory section drew the owner's rows |
| subject skill_pattern | 53 | `1e9752695840b8c9ae404b8fc5257ec010b763b19a4546d192ca948513104fe9` | skill_pattern: listed alice-sk… |
| subject active_context | 53 | `432dbe19573bf5ae0039f2f801aa97ea200fc6b2186e8c169de6ea217a5628df` | active_context: listed alice-ac… |
| subject episodic | 53 | `5d507da0006c6d4bceb6244deb860097f72d72e7599992096003caaec70285f2` | episodic: listed alice-ep… |
| subject preference | 53 | `fb919ee1925017b909e65cd29343ef2f9f529b4de37590f582d6733d769e4c7f` | preference: listed alice-pr… |
| subject failure | 53 | `df151ce9a4c429732b6d6d06701f8b05a2b292d1bacb084747c2bb3cc6dfef15` | failure: listed alice-fa… |
| subject architectural_decision | 53 | `11fb724f58b7a7a1e306207fd553d216d4e960d04ea52384b8056119effab0e1` | architectural_decision: listed alice-ar… |
| subject domain_knowledge | 53 | `7c50cd5bd3a66a3f41dc7d5e4598a49da66ac09f7674bca69cd64b4771fa9bd7` | domain_knowledge: listed alice-dk-00 |
| search | 2f6e6565646c650d | `fc51e8aa4505f9869ebb81553cc395722dd2c73dae17b19e404b43828ea81408` | search needle: first hit alice-dk-00 |
| clear search | 2f0d | `9c91be73650ba017a1914d432e8436a027a528a6fd4a68f72d2003efca2d2ab5` | keys sent |
| next page | 5d | `1d963a82ecd6a605060ea9e8f90c56360a716afd2aa444b5f0ffa0da215cbd25` | page 2 starts at alice-dk-20 |
| previous page | 5b | `5994cd2bf37b98abe463ace912efa165cb8490e883fcc5176dc5f669ee811da0` | page 1 again at alice-dk-00 |
| expand | 78 | `c9dc3405a50e18032181bc3a79c7063ae429c913a571b679236e0cadeeaa940a` | exact version expanded: alice-dk-00 v1 |
| history | 76 | `f0846f3cd0d6c5b49434e1a6663e04cc1a7bea80df036d1132fd933c9fdb1eaa` | Memory history panel drew |
| explain | 45 | `05d31c4e112a97e19c13e89016dbd6d57415dd879a87869e55f1552d93fb6230` | Memory explain panel drew |
| collapse | 2d | `8a7e928491849af1172183e035dff7bc47d1b2660eb02be43c0d26eb279ef127` | keys sent |
| correction preview | 630970747920636f7272656374696f6e096e6565646c6520636f7272656374656420627920746865207074792077616c6b7468726f7567680d | `9ff93c52b264fcfc665fb0a69fa6853ab3bfd9d9ce3156d5cd469378885f2e17` | keys sent |
| correction apply | 79 | `1f58bbfdd30427a6635bd97a3615c83b4e80f71b887ee4024197676ab64b8ea8` | keys sent |
| correction cancel | 636e657665722073617665641b | `cff150444d7af7e08a7217d350d80e04764a37a53e234c854215686d490eca84` | keys sent |
| focus cycle | 0909090909 | `392273ff99a6cd42e29b9a333ef868e2facf47d5db1ee38d7760008bebbd6d57` | focus: inspect>edit>search>filter>list |
| historical view | 66090909747275650d | `717fd4c46996030cb8b5c0ff8a6e8e3281e59c38c499e32930627bbb0b22d347` | keys sent |
| hostile search | 2f686f7374696c656d61726b65720d | `feb98ed96ef7d5c7b6342cb9710133fb8c0725c25893944b62b30eeeb591015e` | keys sent |
| hostile row | 78 | `a12a846f5e83d01a4bd35e97e2fa64643bc289fa0f770a2f7d6683ac010cae6a` | hostile row rendered as escaped text |
| revoked grant | 53 | `58d75b8717af2808054678cb25c2d53dfd12aaf1c96006a5efa61aeba017f6cb` | revoked grant: state shown |
| quit | 71 | `a4a566aca9a5761241ad252aa9931fadbd180f4eb4625251a85870c800fcaf9a` | keys sent |

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
