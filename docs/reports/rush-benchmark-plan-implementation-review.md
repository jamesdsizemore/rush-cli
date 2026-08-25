# Implementation Review: Rush Benchmark Harness Plan
**Document Reviewed:** [`docs/reports/rush-benchmark-plan.md`](file:///C:/Users/james/developer/rush-cli/docs/reports/rush-benchmark-plan.md)  
**Review Date:** August 24, 2026  
**Status:** Implementation Ready (with 3 minor import/signature reconciliations noted)  

---

## 1. Executive Evaluation

The benchmark harness implementation plan is **architecturally sound, strictly bounded, and ready for immediate phased execution**.

### Strengths
* **Zero Production Footprint:** The harness lives entirely in `scripts/benchmarks/` and `tests/`. It does not modify `src/rush/`, alter CLI/MCP production entry points, add runtime dependencies, or touch `rush.toml`.
* **Deterministic Offline CI:** All CI tests run in fixture mode with zero network calls, zero credential requirements, zero external daemon dependencies, and zero model weight downloads.
* **Strict Security Boundaries:** Subprocess calls require argument arrays (`shell=False`), explicit CLI flag opt-ins (`--allow-live-route`, `--allow-model-download`), output secret redaction, and strict path-containment checks.
* **TDD-First Structure:** Every task across phases B1–B6 specifies exact red-to-green failure modes, minimal fixture shapes, and regression commands.

---

## 2. Codebase Discrepancies & Resolutions

During audit against `src/rush/`, three minor module/method path discrepancies were identified and resolved:

| Plan Reference | Actual Codebase Reality | Implementation Resolution |
|---|---|---|
| `src/rush/telemetry/flight_recorder.py` | `src/rush/tools/flight_recorder.py` | Import `FlightRecorder` from `rush.tools.flight_recorder`. |
| `rush.mcp_mesh.lock_manager.LockManager` | `rush.mcp_mesh.lock_manager.MeshLockManager` | Use `MeshLockManager` with `acquire(file_path, agent_id, timeout_s)` and `release(file_path, agent_id)`. |
| `CCRStore.store_chunk` return format | Returns `<!-- ccr:chunk:<hash> -->` | Parse `<hash>` from the markdown chunk tag when calling `retrieve_chunk(<hash>)`. |

---

## 3. Section-by-Section Verification

### Section 1: Outcome & Completion Criteria
* **Permitted Statuses:** `pass`, `fail`, `inconclusive`, `deferred`, `skipped`. Explicitly rejects invalid status `monitor`.
* **CI Determinism:** All tests in `tests/test_benchmark_*.py` execute completely offline without hardware or API dependencies.
* **Token Reduction Gate:** Enforces $\ge 50\%$ median input-token reduction on 2k, 8k, and 16k context budgets with zero critical fact omission.

### Section 2 & 2A: Harness Layout & Typed Contracts
* **Schema Version:** `SCHEMA_VERSION = 1`.
* **Core Dataclasses:** `Outcome`, `SourceEvidence`, `Scenario`, `ProbeResult`.
* **Exact Serialization Boundary:** `ProbeResult.to_dict()` is the single source of serialization truth; `require_exact_keys()` enforces exact JSON keys without extra or missing attributes.
* **Path Containment:** `fixtures.py` restricts reads to `tests/fixtures/benchmarks/`; `reporting.py` restricts writes to `research/benchmark/B*/`.

### Section 2B: Probes & Verification Matrix
* `providers.py`: Fixture-first descriptor loader. Live execution gated by `--allow-live-route <id>`.
* `protocol.py`: Parses JSONL, Markdown, MCP, ACP, and A2A envelopes; marks all imported external instructions as `quarantined`.
* `privacy.py`: Scans synthetic tokens; returns replacement labels in `redactions` tuple; enforces max input bytes, max pages, and timeout before parsing.
* `context.py`: Directly calls `ContextPacker.pack()` and verifies fact presence; verifies `CCRStore` chunk caching and restoration.
* `coordination.py`: Exercises `CheckpointJournal`, `MeshLockManager`, and `FlightRecorder` to verify lease contention and deterministic replay.
* `local.py`: Captures hardware profiles (`hardware-profile.json`); strictly forbids `ollama` daemon or endpoints; allows only approved external `llama.cpp` or ONNX argument arrays.
* `reporting.py`: Atomic write via `<id>.tmp` $\rightarrow$ `<id>.json` replace.

### Section 3: External-Route & Local-Runtime Boundaries
* **Fixture Mode:** Default and only mode in automated CI.
* **Live Route Execution:** Requires user-authenticated route and `--allow-live-route`. No browser automation, no credential export.
* **Model Cache:** Must resolve outside repository (`%LOCALAPPDATA%/Rush/benchmark-model-cache` on Windows).
* **Ollama Ban:** Explicitly rejects any candidate where binary name is `ollama` or endpoint points to local Ollama daemon.

### Section 4 & 5: Phased Implementation Roadmap
* **Phase B1:** Harness Foundation (`contracts.py`, `fixtures.py`, `run.py`, `reporting.py`, `scenarios.json`, `test_benchmark_contracts.py`, `test_benchmark_runner.py`).
* **Phase B2:** Providers, Routers & Protocol (`providers.py`, `protocol.py`, `provider_routes.json`, `routers.json`, `protocol_cases.json`, `test_benchmark_providers.py`).
* **Phase B3:** Privacy & Dependency Safety (`privacy.py`, `privacy_cases.json`, `test_benchmark_privacy.py`).
* **Phase B4:** Context Reduction & Retrieval (`context.py`, `context_cases.json`, `test_benchmark_context.py`).
* **Phase B5:** Coordination & Multi-Agent Locks (`coordination.py`, `coordination_cases.json`, `test_benchmark_coordination.py`).
* **Phase B6:** Local Runtime & Final Handoff (`local.py`, `local_candidates.json`, `test_benchmark_local.py`, `final-handoff.md`).

---

## 4. Implementation Readiness & Execution Order

To execute the plan cleanly, implement tasks in strict sequential order:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     HARNESS EXECUTION PHASES                             │
├──────────┬─────────────────────────────┬─────────────────────────────────┤
│ Phase    │ Primary Target              │ Key Validation Gate             │
├──────────┼─────────────────────────────┼─────────────────────────────────┤
│ Phase B1 │ Core Contracts & Runner     │ test_benchmark_contracts.py     │
│          │                             │ test_benchmark_runner.py        │
├──────────┼─────────────────────────────┼─────────────────────────────────┤
│ Phase B2 │ Provider & Router Probes    │ test_benchmark_providers.py     │
├──────────┼─────────────────────────────┼─────────────────────────────────┤
│ Phase B3 │ Secret Redaction & Parsers  │ test_benchmark_privacy.py       │
├──────────┼─────────────────────────────┼─────────────────────────────────┤
│ Phase B4 │ ContextPacker & CCRStore    │ test_benchmark_context.py       │
├──────────┼─────────────────────────────┼─────────────────────────────────┤
│ Phase B5 │ Locks & Flight Recorder     │ test_benchmark_coordination.py  │
├──────────┼─────────────────────────────┼─────────────────────────────────┤
│ Phase B6 │ Hardware Profile & Handoff  │ test_benchmark_local.py         │
│          │                             │ final-handoff.md generation     │
└──────────┴─────────────────────────────┴─────────────────────────────────┘
```

### Recommendation
Proceed directly with **Phase B1 (Harness Foundation & Control Corpus)** following standard TDD (Red $\rightarrow$ Green) workflow.
