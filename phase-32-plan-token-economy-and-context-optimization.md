# Phase 32 Implementation Plan: Token Economy, Context Window Optimization & Historical Hygiene

> **Phase:** 32 of 40  
> **Milestone:** Token Optimization, Secret Scrubbing & Repo Diet  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.4.0  
> **ADR References:** [ADR-0022: Offline BPE Token Accounting via `tiktoken`](docs/adr/0022-offline-bpe-token-accounting.md), [ADR-0024: Hardened Subprocess Git Invocations](docs/adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `tiktoken==0.9.0`, `mcp==1.28.1`  
> **Embedded Static Datasets:** `src/rush/data/model_pricing.json` (24 KB)

---

## 1. Objective & Scope

Autonomous coding agents and vibe-coders incur massive token bloat and financial costs when feeding entire repository file trees into frontier models (Claude 3.7 Sonnet, OpenAI o3, DeepSeek-R1). Furthermore, sensitive credentials committed in historical Git commits create recurring security risks during codebase indexing.

Phase 32 delivers:
1. **Offline BPE Token Accounting & Financial Cost Estimator (`rush token-cost`)**: Exact token calculations across cl100k and o200k encodings, forecasting inference costs for prompt and completion tiers.
2. **Context Window Optimizer & Bloat Purger (`rush context-diet`)**: Identifies token-heavy artifacts, build residue, minified bundles, lockfile dumps, and inline base64 blobs, generating `.rushignore` and context-pruning rules.
3. **Deep Git History Secret Purger (`rush git-leak-history`)**: Scans historical Git commit trees and blobs for leaked credentials and outputs git-filter-repo / BFG remediation scripts.
4. **Token-Aware Codebase Prompt Packer (`rush context-pack`)**: Generates structured, `.gitignore`-compliant Markdown prompt packages with exact token limits for prompt engineering.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Token Accounting)**: `rush token-cost` uses `tiktoken` BPE encodings directly in-process without making API round-trips. It enforces maximum context limits (e.g. 128k, 200k) and warns when prompts approach context limits.
- **`graft` (Code Pruning)**: `rush context-diet` recommends replacing full source files with semantic AST signatures (`rush_graft_slice`) in prompts, saving 60% to 90% of token overhead.
- **`context-mode` (Compact JSON & Diff Representation)**: Packing operations output concise, token-metered Markdown blocks with line-number markers.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/tools/token_cost.py` (New: Token counting & cost estimator using `tiktoken` and `model_pricing.json`)
- `src/rush/tools/context_diet.py` (New: Context bloat detector and `.rushignore` generator)
- `src/rush/git/leak_history.py` (New: Deep Git commit log and blob entropy scanner)
- `src/rush/tools/context_pack.py` (New: Codebase prompt packager with token budgets)
- `src/rush/data/model_pricing.json` (New: Pre-compiled offline model pricing matrix)
- `src/rush/cli.py` (Modified: Register `rush token-cost`, `rush context-diet`, `rush git-leak-history`, `rush context-pack`)
- `src/rush/mcp_server.py` (Modified: Register FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Catalog specifications)

### Test & Fixture Files
- `tests/test_token_cost.py` (New: BPE token accuracy, cost calculation, pricing model fallbacks)
- `tests/test_context_diet.py` (New: Context bloat scoring, lockfile detection, `.rushignore` creation)
- `tests/test_leak_history.py` (New: Commit tree scanning, historical blob extraction, filter script generation)
- `tests/test_context_pack.py` (New: Prompt bundling, token limit capping, `.gitignore` compliance)
- `tests/fixtures/pricing/model_pricing.json` (New: Fixture dataset)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_token_cost.py
def test_token_cost_cl100k_calculation():
    sample_text = "def calculate_velocity(distance: float, time: float) -> float:\n    return distance / time"
    cost_info = estimate_tokens_and_cost(sample_text, model="claude-3-7-sonnet")
    assert cost_info.token_count > 0
    assert cost_info.estimated_usd_prompt > 0.0
    assert cost_info.model == "claude-3-7-sonnet"

# tests/test_context_diet.py
def test_context_diet_flags_large_json_dumps(tmp_path):
    huge_json = tmp_path / "huge_payload.json"
    huge_json.write_text("{\"data\": " + str(list(range(50000))) + "}")
    findings = analyze_context_bloat(tmp_path)
    assert any(f.path.endswith("huge_payload.json") for f in findings)
    assert any(f.waste_category == "large_data_dump" for f in findings)

# tests/test_leak_history.py
def test_detect_leaked_secret_in_old_commit(tmp_path):
    repo = init_git_repo(tmp_path)
    # Commit secret
    secret_file = tmp_path / "secret.env"
    secret_file.write_text('API_KEY="sk-ant-api03-abcdef1234567890abcdef1234567890"')
    commit_file(repo, "Add secret")
    # Delete secret in next commit
    secret_file.unlink()
    commit_file(repo, "Remove secret")
    
    leaks = scan_git_history_for_leaks(tmp_path)
    assert len(leaks) >= 1
    assert leaks[0].commit_hash != ""
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/tools/token_cost.py`, `src/rush/tools/context_diet.py`, `src/rush/git/leak_history.py`, and `src/rush/tools/context_pack.py`.

### 4.3 REFACTOR Phase
Optimize token scanning loops using memory-mapped buffers for large repository files and verify offline determinism.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:20:00Z", "phase": 32, "tool": "rush_token_cost", "event": "tokens_calculated", "tokens": 14250, "cost_usd": 0.04275, "model": "claude-3-7-sonnet"}
{"timestamp": "2026-08-21T07:20:01Z", "phase": 32, "tool": "rush_context_diet", "event": "bloat_detected", "file": "package-lock.json", "tokens": 68000, "recommendation": "add_to_rushignore"}
{"timestamp": "2026-08-21T07:20:02Z", "phase": 32, "tool": "rush_git_leak_history", "event": "historical_leak_found", "commit": "a1b2c3d", "file": "config.json"}
```

---

## 6. Step-by-Step Task Specifications

### Task 32.1: BPE Token & Cost Estimator (`src/rush/tools/token_cost.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import tiktoken
from rush.tools.base import ToolResult

@dataclass(frozen=True)
class CostEstimate:
    token_count: int
    estimated_usd_prompt: float
    estimated_usd_completion: float
    model: str
    context_limit: int
    context_utilization_pct: float

def estimate_tokens_and_cost(text: str, model: str = "claude-3-7-sonnet") -> CostEstimate:
    """Calculate exact BPE tokens and USD cost from offline pricing matrix."""
    ...
```

### Task 32.2: Context Window Optimizer & `.rushignore` (`src/rush/tools/context_diet.py`)
Analyze repository files, score token waste density, and generate `.rushignore` / `.agentignore`.

### Task 32.3: Historical Git Leak Scanner (`src/rush/git/leak_history.py`)
Traverse `git rev-list --all` and scan historical tree blobs for high-entropy secrets and sensitive environment keys.

### Task 32.4: Codebase Prompt Packer (`src/rush/tools/context_pack.py`)
Pack multi-file repository slices into token-bounded Markdown prompt templates.

### Task 32.5: CLI & FastMCP Registrations
Register `rush token-cost`, `rush context-diet`, `rush git-leak-history`, `rush context-pack` in CLI and MCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Strict Offline Invariant**: Zero outbound HTTP calls for pricing models; pricing is loaded strictly from `src/rush/data/model_pricing.json`.
2. **Git History Safety**: Historical scan must never rewrite repository history without explicit `--apply` flag.
3. **Doc Parity**: Synchronize and verify all `/docs` files.
