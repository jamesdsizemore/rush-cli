# Source tree responsibilities

| Path | Responsibility |
|---|---|
| `src/rush/catalog.py` | declarative tool/engine metadata, maturity, parser-fixture ownership |
| `src/rush/cli.py` | Click options, catalog command generation, output/exit mapping |
| `src/rush/mcp.py` | stdio server construction and registration |
| `src/rush/config.py` | discovery and typed TOML parse |
| `src/rush/theme.py` | Rich CLI rendering |
| `src/rush/logging.py` | NDJSON stderr logging/redaction |
| `src/rush/tools/base.py` | ToolFn, ToolResult, Finding contracts |
| `src/rush/tools/common.py` | subprocess, normalization, error/skip helpers, exit mapping |
| `src/rush/tools/routing.py` | language detection and deterministic aggregation |
| `src/rush/tools/*.py` | one intent-focused tool implementation each |
| `src/rush/engines/base.py` | adapter contract |
| `src/rush/engines/*.py` | executable argv and parser normalization |
| `tests/test_*reference.py` | promoted adapter invocation/parser contracts |
| `tests/fixtures/engine_reports/` | bounded native reports, including malformed cases |
| `tests/test_cli_registry.py`, `test_mcp.py` | transport and parity evidence |
| `.github/workflows/ci.yml` | locked quality/package and representative-engine jobs |
| `docs/getting-started`, `user-guide`, `tutorials`, `reference` | user documentation |
| `docs/developer`, `maintainers` | implementation and operations documentation |

## Token Economy & Memory Source Layout (Phases 41–43)

```
src/rush/
├── token_economy/          # Context intelligence and compression
│   ├── router.py           # ContentRouter and ContentType classification
│   ├── ast_skeletonizer.py # Polyglot AST outline compressor
│   ├── ccr_store.py        # SQLite LRU chunk cache (.rush/cache/ccr.db)
│   ├── distillers/         # Output distillers (pytest, cargo, ruff, vitest)
│   └── toon/               # TOON v4.1 table encoder and decoder
├── memory/                 # Persistent memory and history tracking
│   ├── preference_store.py # Developer preferences (.rush/preferences.json)
│   ├── checkpoint_journal.py # Session snapshots (.rush/sessions/)
│   ├── merkle_invalidator.py # AST node hash tracking (.rush/cache/merkle.json)
│   ├── invariant_graph.py  # Architectural decision graph (.rush/memory/invariants.json)
│   ├── failure_ledger.py   # Negative knowledge failure ledger (.rush/memory/failures.db)
│   └── mistake_miner.py    # Bi-temporal Git revert miner
└── tools/
    ├── ship/               # Pre-flight ship vectors and 7-vector cockpit
    │   ├── cleaner.py      # Scratch directory cleaner
    │   ├── env_linter.py   # AST environment variable parity linter
    │   ├── docs_linter.py  # Markdown link parity auditor
    │   ├── migration_linter.py # SQL table-lock migration hazard detector
    │   ├── semver_linter.py # Public API breaking change contract differ
    │   ├── package_linter.py # Sensitive key / secret leak auditor
    │   └── cockpit.py      # Unified 7-vector parallel Ship Cockpit
    └── hallu_guard.py      # Real-time AST grounding and phantom package guard
```

## Context Packing & Blast Radius Modules
```
src/rush/
├── codegraph/
│   └── context_packer.py  # PageRank context packing
├── token_economy/
│   ├── stale_sweeper.py   # Multi-turn history sweeper
│   ├── cache_aligner.py   # Prompt cache boundary aligner
│   ├── telemetry.py       # SQLite token ledger (.rush/telemetry/tokens.db)
│   ├── output_shaper.py   # Terse persona output filter
│   └── tui_gain.py        # Rich terminal gain dashboard
└── tools/
    ├── blast_radius.py    # Downstream reachability analyzer
    └── arch_guard.py       # Architectural layer boundary guard
```



## Test Healing & API Diff Modules
```
src/rush/
├── core/
│   └── git_sandbox.py     # Ephemeral worktree sandbox manager
└── tools/
    ├── test_heal.py       # Autonomous flaky test healer
    └── api_diff.py        # Public API signature differ
```



## DB Drift & Simplification Modules
```
src/rush/tools/
├── db_drift.py    # ORM-to-migration schema drift auditor
├── simplify.py    # Cognitive complexity refactoring decomposer
└── strictify.py   # Runtime type guard synthesizer
```



## Traceability & Mesh Modules
```
src/rush/
├── mcp_mesh/
│   ├── __init__.py
│   ├── daemon.py          # Lock daemon
│   └── lock_manager.py    # Local file-based mutex client
└── tools/
    ├── trace.py           # Spec-to-code traceability scanner
    ├── flight_recorder.py # Session recorder & replayer
    ├── swarm_merge.py     # 3-way AST merge solver
    └── simulate_ci.py     # Local GHA workflow emulator
```



## SLSA Attestation & Security Modules
```
src/rush/tools/
├── attest.py         # SLSA Level 3 provenance generator
├── license_matrix.py # Copyleft license scanner
├── iam_audit.py      # Cloud IAM policy synthesizer
├── dead_asset.py     # Unreferenced asset pruner
└── pr_synthesize.py  # Semantic PR card synthesizer
```

## Benchmark Harness & Verification Modules (Phases B1–B6)
```
scripts/
└── benchmarks/
    ├── contracts.py     # Dataclass models & schema validation
    ├── fixtures.py      # Path-contained JSON fixture loader
    ├── run.py           # CLI runner & real-time terminal reporter
    ├── reporting.py     # Atomic temporary-file-and-replace writer
    ├── providers.py     # Provider route descriptor execution & scrubbing
    ├── protocol.py      # Multi-dialect envelope parser & quarantine
    ├── privacy.py       # Secret redaction & bounded parser limits
    ├── context.py       # ContextPacker & CCRStore retrieval probes
    ├── coordination.py  # MeshLockManager & CheckpointJournal probes
    └── local.py         # Hardware profiling & Ollama exclusion
tests/
└── fixtures/
    └── benchmarks/      # 40 declared scenario & candidate JSON fixtures
```

