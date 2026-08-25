# Rush Benchmark Final Handoff & Decision Record

This document records all deterministic gate evaluation decisions and unblocked engineering tasks.

| Gate / Decision | Status | Unblocked Task | Fixtures | Result JSON | Fallback |
|---|:---:|---|---|---|---|
| `B-D01` (Harness Foundation & Typed Contracts) | `inconclusive` | `P2-T01` | scenarios.json | [`B1/decision-B-D01-B-D02.json`](B1/decision-B-D01-B-D02.json) | fixture-only-mode |
| `B-D02` (Control Corpus & Baseline Telemetry) | `pass` | `P3-T01` | scenarios.json | [`B1/decision-B-D01-B-D02.json`](B1/decision-B-D01-B-D02.json) | naive-summary-baseline |
| `B-D03` (Privacy Redaction & Parser Bounds) | `pass` | `P2-T02` | privacy_cases.json | [`B3/decision-B-D03.json`](B3/decision-B-D03.json) | strict-pattern-scrubbing |
| `B-D04` (ContextPacker Token Reduction) | `pass` | `P3-T01` | context_cases.json | [`B4/decision-B-D04-B-D05.json`](B4/decision-B-D04-B-D05.json) | full-file-fallback |
| `B-D05` (CCR Chunk Cache & Exact Byte Restoration) | `pass` | `P3-T02` | context_cases.json | [`B4/decision-B-D04-B-D05.json`](B4/decision-B-D04-B-D05.json) | uncompressed-raw-text |
| `B-D06` (Local Model Hardware Profiling & Runtime Bounds) | `pass` | `P4-T01` | local_candidates.json | [`B6/decision-B-D06.json`](B6/decision-B-D06.json) | lexical-symbol-search |
| `B-D07` (Provider Route Security & Redaction) | `pass` | `P5-T01` | provider_routes.json | [`B2/decision-B-D07-B-D10.json`](B2/decision-B-D07-B-D10.json) | fixture-replay |
| `B-D08` (9Router Route Independence) | `pass` | `P5-T02` | routers.json | [`B2/decision-B-D07-B-D10.json`](B2/decision-B-D07-B-D10.json) | direct-provider-route |
| `B-D09` (OmniRouter Multi-Agent Mesh Independence) | `pass` | `P5-T02` | routers.json | [`B2/decision-B-D07-B-D10.json`](B2/decision-B-D07-B-D10.json) | direct-provider-route |
| `B-D10` (Protocol Quarantine of Tampered Envelopes) | `pass` | `P5-T03` | protocol_cases.json | [`B2/decision-B-D07-B-D10.json`](B2/decision-B-D07-B-D10.json) | quarantined-import |
| `B-D11` (Multi-Agent Lock Mesh & Checkpoint Replay) | `pass` | `P4-T02` | coordination_cases.json | [`B5/decision-B-D11.json`](B5/decision-B-D11.json) | optimistic-single-agent-lock |

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

### `B-D09`: OmniRouter Multi-Agent Mesh Independence
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
