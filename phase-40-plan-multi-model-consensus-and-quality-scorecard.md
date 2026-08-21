# Phase 40 Implementation Plan: Multi-Model Consensus, Telemetry Dashboard & Quality Scorecard

> **Phase:** 40 of 40  
> **Milestone:** Multi-Model Consensus, Telemetry & Quality Scorecard  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v1.0.0  
> **ADR References:** [ADR-0022: Offline BPE Token Accounting via `tiktoken`](docs/adr/0022-offline-bpe-token-accounting.md), [ADR-0023: Async Local Model Bridge via `httpx`](docs/adr/0023-async-local-model-bridge.md)  
> **Pinned Dependencies:** `httpx==0.28.1`, `tiktoken==0.9.0`, `rich==13.9.4`, `mcp==1.28.1`  
> **Embedded Static Datasets:** `src/rush/data/redos_patterns.json` (18 KB), `src/rush/data/model_pricing.json` (24 KB)

---

## 1. Objective & Scope

As repositories reach enterprise scale and autonomous agents execute high-stakes refactorings, relying on a single AI model introduces systemic blindspots and confirmation bias. Furthermore, engineering leads need unified quality scorecards (0–100 health metrics) and chronological session telemetry replays to audit what autonomous coding agents accomplished across multi-turn sessions.

Phase 40 completes the Rush Operating System by delivering:
1. **Multi-Model Consensus & Peer Review Bridge (`rush consensus` / `rush_multi_model_review`)**: Dispatches asynchronous code review queries across multiple frontier models (Claude 3.7 Sonnet, OpenAI o3, DeepSeek-R1 via Ollama/vLLM) to identify consensus findings and resolve hallucinations.
2. **ReDoS Catastrophic Backtracking Detector (`rush regex-safe`)**: NFA/DFA state-complexity analyzer and regex vulnerability scanner that prevents catastrophic Regular Expression Denial of Service.
3. **Agent Session Telemetry & Replay Engine (`rush agent-replay` / `rush agent-transcript`)**: Ingests `.claude/projects/` and Antigravity conversation JSONL transcripts to generate chronological timeline views, token spend graphs, and tool invocation audits in the 127.0.0.1 Web Dashboard and Rich TUI.
4. **Unified Quality Scorecard Aggregator (`rush score`)**: Computes a single deterministic repository health score (0–100) across 6 dimensions: Security, Type Coverage, Test Health, Documentation Parity, Git Velocity, and Agent Governance.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Consensus Diff Reduction)**: Multi-model consensus prompts are stripped of boilerplate and send only AST slices (`rush_graft_slice`) to peer models. Responses are normalized and deduplicated before rendering.
- **`graft` (Targeted Vulnerability Extraction)**: ReDoS scanner extracts regex patterns from string literals and AST call arguments (`re.compile`, `RegExp`) without reading surrounding application logic.
- **`context-mode` (Compact Scorecard Serialization)**: Scorecards are serialized as compact, token-efficient JSON and rendered beautifully in the terminal using Python `rich`.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/tools/score.py` (New: Composite 6-pillar repository health score calculator)
- `src/rush/tools/regex_safe.py` (New: ReDoS regex vulnerability and catastrophic backtracking scanner)
- `src/rush/agent_telemetry.py` (New: Agent session JSONL transcript parser and timeline generator)
- `src/rush/tools/consensus.py` (New: Async multi-model peer review bridge using `httpx`)
- `src/rush/dashboard.py` (Modified: Embed session replay timeline and scorecard widgets)
- `src/rush/data/redos_patterns.json` (New: Known catastrophic regex vulnerability templates)
- `src/rush/cli.py` (Modified: Register `rush score`, `rush regex-safe`, `rush agent-replay`, `rush consensus`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Tool specs)

### Test & Fixture Files
- `tests/test_scorecard.py` (New: 6-pillar score weighting, penalty calculations, breakdown metrics)
- `tests/test_regex_safe.py` (New: ReDoS pattern detection: nested quantifiers, overlapping alternations)
- `tests/test_agent_telemetry.py` (New: Claude Code and Antigravity JSONL session parsing)
- `tests/test_consensus_bridge.py` (New: Mocked multi-model async dispatch and consensus voting)
- `tests/fixtures/telemetry/sample_session.jsonl` (New: Test session transcript fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_regex_safe.py
def test_regex_safe_detects_catastrophic_backtracking():
    vulnerable_regex = r"^(a+)+$"
    result = analyze_regex_safety(vulnerable_regex)
    assert result.is_safe is False
    assert result.complexity == "exponential"
    assert "nested_quantifiers" in result.vulnerability_types

# tests/test_scorecard.py
def test_quality_scorecard_calculation(tmp_path):
    # Setup clean project fixture
    score = calculate_repository_score(repo_root=tmp_path)
    assert 0 <= score.composite_score <= 100
    assert "security" in score.pillars
    assert "type_coverage" in score.pillars
    assert "git_velocity" in score.pillars
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/tools/score.py`, `src/rush/tools/regex_safe.py`, `src/rush/agent_telemetry.py`, and `src/rush/tools/consensus.py`.

### 4.3 REFACTOR Phase
Ensure multi-model HTTP calls have strict 10s timeouts, connection pooling via `httpx.AsyncClient`, and structured error fallbacks when local Ollama/vLLM daemons are offline.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T08:00:00Z", "phase": 40, "tool": "rush_score", "event": "scorecard_generated", "composite_score": 92.4, "rating": "A"}
{"timestamp": "2026-08-21T08:00:01Z", "phase": 40, "tool": "rush_regex_safe", "event": "redos_detected", "pattern": "^(a+)+$", "complexity": "exponential"}
{"timestamp": "2026-08-21T08:00:02Z", "phase": 40, "tool": "rush_consensus", "event": "models_polled", "models": ["claude-3-7-sonnet", "deepseek-r1"], "agreement_pct": 94.0}
```

---

## 6. Step-by-Step Task Specifications

### Task 40.1: ReDoS Catastrophic Backtracking Detector (`src/rush/tools/regex_safe.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from rush.tools.base import ToolResult, Finding

@dataclass(frozen=True)
class RegexVulnerability:
    pattern: str
    file_path: str
    line: int
    complexity: str  # "exponential" | "polynomial" | "safe"
    explanation: str

def audit_regex_safety(repo_root: Path) -> ToolResult:
    """Scan codebase for catastrophic backtracking regex patterns and ReDoS vulnerabilities."""
    ...
```

### Task 40.2: Unified Quality Scorecard Engine (`src/rush/tools/score.py`)
Aggregate results from security, typecheck, test, doc-parity, git-hotspots, and prompt-audit into a 0–100 composite scorecard.

### Task 40.3: Agent Telemetry & Replay Engine (`src/rush/agent_telemetry.py`)
Parse `.claude/projects/` and Antigravity transcripts into structured timeline events for the Web Dashboard.

### Task 40.4: Async Multi-Model Consensus Bridge (`src/rush/tools/consensus.py`)
Dispatch code review queries asynchronously via `httpx` and compute cross-model finding consensus.

### Task 40.5: CLI & FastMCP Registrations
Register all 4 tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Async Safety**: Consensus bridge must never block the FastMCP stdio transport.
2. **Deterministic Scoring**: Given the same codebase state, `rush score` must return identical scores.
3. **Doc Parity**: Synchronize and verify all `/docs` files.
