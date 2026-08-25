# Historical benchmark handoff index (non-canonical)

This historical index describes a prior fixture campaign. Its referenced `research/` result blobs are intentionally untracked and may be absent; it is not authority for product work or phase entry. Canonical, committed phase gates live in `docs/reports/continuity-gates/` and must be reconciled from reproducible evidence before use.

| Gate / Decision | Status | Unblocked Task | Fixtures | Result JSON | Fallback |
|---|:---:|---|---|---|---|
| `B-D01` (Harness Foundation & Typed Contracts) | `inconclusive` | none | scenarios.json | ignored/untracked evidence | fixture-only-mode |
| `B-D02` (Control Corpus & Baseline Telemetry) | `pass` | none | scenarios.json | ignored/untracked evidence | naive-summary-baseline |
| `B-D03` (Privacy Redaction & Parser Bounds) | `pass` | none; see `BG-PRIV` scope | privacy_cases.json | ignored/untracked evidence | strict-pattern-scrubbing |
| `B-D04` (ContextPacker Token Reduction) | `pass` | none | context_cases.json | ignored/untracked evidence | full-file-fallback |
| `B-D05` (CCR Chunk Cache & Exact Byte Restoration) | `pass` | none | context_cases.json | ignored/untracked evidence | uncompressed-raw-text |
| `B-D06` (Local Model Hardware Profiling & Runtime Bounds) | `pass` | none | local_candidates.json | ignored/untracked evidence | lexical-symbol-search |
| `B-D07` (Provider Route Security & Redaction) | `pass` | none | provider_routes.json | ignored/untracked evidence | fixture-replay |
| `B-D08` (9Router Route Independence) | `pass` | none | routers.json | ignored/untracked evidence | direct-provider-route |
| `B-D09` (OmniRoute Multi-Agent Mesh Independence) | `pass` | none | routers.json | ignored/untracked evidence | direct-provider-route |
| `B-D10` (Protocol Quarantine of Tampered Envelopes) | `pass` | none | protocol_cases.json | ignored/untracked evidence | quarantined-import |
| `B-D11` (Multi-Agent Lock Mesh & Checkpoint Replay) | `pass` | none | coordination_cases.json | ignored/untracked evidence | optimistic-single-agent-lock |

## Reproduction Commands

### `B-D01`: Harness Foundation & Typed Contracts
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_contracts.py tests/test_benchmark_runner.py -q
```

### `B-D02`: Control Corpus & Baseline Telemetry
```bash
.venv/Scripts/python.exe -m scripts.benchmarks.run --all --output research/benchmark/B1
```

### `B-D03`: Privacy Redaction & Parser Bounds
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_privacy.py -q
```

### `B-D04`: ContextPacker Token Reduction
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_context.py -q
```

### `B-D05`: CCR Chunk Cache & Exact Byte Restoration
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_context.py -q
```

### `B-D06`: Local Model Hardware Profiling & Runtime Bounds
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_local.py -q
```

### `B-D07`: Provider Route Security & Redaction
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q
```

### `B-D08`: 9Router Route Independence
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q
```

### `B-D09`: OmniRoute Multi-Agent Mesh Independence
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q
```

### `B-D10`: Protocol Quarantine of Tampered Envelopes
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q
```

### `B-D11`: Multi-Agent Lock Mesh & Checkpoint Replay
```bash
.venv/Scripts/python.exe -m pytest tests/test_benchmark_coordination.py -q
```
