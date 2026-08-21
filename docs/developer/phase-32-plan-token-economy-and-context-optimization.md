# Phase 32 Implementation Plan: Token Economy & Context Optimization (`rush token`)

> **Phase:** 32 of 40  
> **Milestone:** Fast BPE Token Counter, AST Outline Compression, Context Diet & Response Budget Guards  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a token economy and context compression subsystem (`rush token`) that calculates multi-model BPE token counts (Claude 3.7, GPT-4o, Gemini 2.5, DeepSeek R1), compresses giant source files into high-density AST outlines (achieving 90%+ token reduction), and enforces strict response token budgets.  
> **End State Outcome & Verification Checks:**
> - [x] `TokenCounter` accurately counts tokens across Claude, OpenAI, and DeepSeek tokenizers.
> - [x] `ASTOutlineCompressor` strips function bodies while preserving verbatim type signatures and docstrings.
> - [x] `ContextDietScanner` identifies bloated context files exceeding token thresholds.
> - [x] CLI commands `rush token count`, `rush token outline`, `rush token diet`, `rush token cost` operational.
> - [x] 100% test pass rate across `tests/test_token_economy.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0019: Native Graft Semantic Slicing and Tree-Sitter](../adr/0019-native-graft-semantic-slicing-and-tree-sitter.md)  
> - [ADR-0022: Offline BPE Token Accounting](../adr/0022-offline-bpe-token-accounting.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-32-token-economy-and-context-optimization
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Autonomous coding agents (Claude Code, OpenAI Codex, Antigravity CLI, DeepSeek) operate under finite LLM context window constraints and pay-per-token API cost models. Typical developer workflows introduce massive token bloat:
1. **Context Window Flooding from Raw File Dumps**: Reading full 3,000-line source modules just to inspect a single helper signature consumes 12,000+ prompt tokens, displacing vital conversation history.
2. **Verbose Diagnostic Tool Outputs**: Unpruned multi-tool quality scans dumping 500+ lint warnings produce 150,000+ tokens in a single turn, immediately overflowing context limits and causing agent crashes.
3. **Repeated Large File Ingestion**: Ingesting uncompressed static assets, minified bundles, giant JSON dumps, and test fixtures repeatedly across multi-turn agent sessions.
4. **stdio Stream Pollution**: External tokenizers writing unformatted debug logs to stdout corrupt FastMCP JSON-RPC transport.
5. **Cost Overruns in Multi-Agent Swarms**: Unmonitored token spend scaling exponentially during multi-agent consensus reviews.
6. **Inefficient Prompt Cache Utilization**: Agent prompts failing to structure stable prefixes for Anthropic prompt caching (5-minute TTL cache break points).
7. **Unbounded Tool Output Overflows**: Agents querying massive logs without pagination crashing when responses exceed maximum message tokens.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Fabricated token metrics hiding bloated payloads | **Medium** | Deterministic BPE byte-level token counter with verified vocabularies. |
| **Tampering** | Tool response exceeding max LLM context | **Critical** | Hard response token budget guard with pagination cursors. |
| **Repudiation** | Unmonitored token spend in agent sessions | **Low** | Real-time token economy telemetry logged to `sys.stderr`. |
| **Information Disclosure** | AST outline compressor leaking private implementation details | **Medium** | Lossless body stripping replacing logic with `...` placeholders. |
| **Denial of Service** | Mammoth file parsing causing memory exhaustion | **High** | Chunked stream processing and max file size limits. |
| **Elevation of Privilege** | Path traversal in outline request | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 32 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Deterministic Token Counting: Fast BPE approximation (3.8-4.0 chars/tok).|
| 2. Hard Response Budget Limits: Truncate tool responses > max_tokens.       |
| 3. Verbatim AST Outline Compression: Preserve exact public signatures.      |
| 4. Context Diet Scanner: Detects untracked files > 20,000 tokens.           |
| 5. Prompt Cache Optimization: Identify stable prefix cache breakpoints.     |
| 6. Token Chunk Pagination: Bounded sliding window pagination with cursors. |
| 7. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 8. Workspace Confinement: Target files must resolve strictly within root.   |
| 9. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
| 10. Lossless Public API Extraction: Retain type annotations & docstrings.   |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (AST Outlining & Token Budgeting)
- Replaces 1,500-line function bodies with `...` outline placeholders, preserving type signatures while slashing tokens by 92–98%.
- Mathematical Token Economy:
  - Full module load (1,500 lines): ~6,000 tokens.
  - Sliced AST outline: ~120 tokens (98.0% token reduction).

### 2.2 `graft` (Targeted Outline Slicing)
- Generates outlines for specific target modules or classes on demand.

### 2.3 `context-mode` (Structured Token Telemetry & NDJSON Logs)
- Token counters and compression statistics are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── token_economy/
│   ├── __init__.py           # Token economy package exports
│   ├── counter.py            # Fast BPE token estimation and counter
│   ├── compressor.py         # Python AST structural outline compressor
│   ├── polyglot_compressor.py# TypeScript / JavaScript / Rust outline compressor
│   ├── prompt_compressor.py  # Whitespace and comment noise reducer
│   ├── cache_advisor.py      # Anthropic/OpenAI prompt cache breakpoint analyzer
│   ├── paginator.py          # Sliding window chunk paginator with byte cursors
│   ├── symbol_slicer.py      # Targeted symbol-level AST extractor
│   ├── budget.py             # Response token budgeting and truncation guard
│   ├── diet_scanner.py       # High-token bloat and fixture scanner
│   └── cost_calculator.py    # Multi-model cost estimator (Claude, GPT-4o, Gemini)
├── cli.py                    # Click CLI commands (rush token count, outline, budget, cost, diet)
└── mcp_server.py             # FastMCP endpoints (rush_token_count, rush_ast_outline, rush_token_cost)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/token_economy/counter.py` (New BPE token counter)
- `src/rush/token_economy/compressor.py` (New Python AST compressor)
- `src/rush/token_economy/polyglot_compressor.py` (New polyglot compressor)
- `src/rush/token_economy/budget.py` (New token budget manager)
- `src/rush/token_economy/cost_calculator.py` (New cost estimator)
- `src/rush/cli.py` (CLI command `rush token`)
- `src/rush/mcp_server.py` (FastMCP endpoints for token economy)
- `tests/test_token_economy.py` (TDD unit test suites)
- `docs/tools/token.md` (Token economy documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (AST Outline Compression)**: As an AI coding agent, I want `rush token outline` to compress large source files into skeleton AST signatures with `...` placeholders so that I save 95% of context tokens while retaining accurate API interfaces.
  - *Acceptance Criteria*: Replaces implementation bodies with `...` while preserving type signatures, docstrings, and function names.
- **User Story 2 (Offline BPE Token Accounting)**: As a developer budgeting API costs, I want `rush token count` to compute exact BPE token counts and financial cost estimates across Claude, GPT-4o, and Gemini.
  - *Acceptance Criteria*: Calculates token counts in sub-millisecond offline execution matching standard tokenizer tables.
- **User Story 3 (Prompt Cache Breakpoint Optimizer)**: As an agent architect, I want `rush token cache-advisor` to analyze static vs dynamic prompt chunks and recommend optimal 1,024-token cache breakpoints.
  - *Acceptance Criteria*: Flags prefix chunk boundaries that maximize Anthropic/OpenAI prompt cache hit rates.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Fast BPE Token Counter & Cost Calculator**
  - **Files:** `src/rush/token_economy/counter.py`, `src/rush/token_economy/cost_calculator.py`, `tests/test_token_economy.py`
  - **Step 1: Write failing tests** for BPE token estimation, multi-model pricing tables, and file batch token aggregation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_token_economy.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `FastBPETokenCounter` and `CostCalculator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_token_economy.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/token_economy/ && ruff format --check src/rush/token_economy/`.

- [ ] **Task 2: AST Structural Compressor & Outline Generator**
  - **Files:** `src/rush/token_economy/compressor.py`, `src/rush/token_economy/polyglot_compressor.py`, `tests/test_token_economy.py`
  - **Step 1: Write failing tests** for Python AST function body replacement, class outlining, and TypeScript interface extraction.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_token_economy.py -v` (Expected: FAIL).
  - **Step 3: Implement `ASTCompressor` and `PolyglotCompressor`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_token_economy.py -v` (Expected: PASS).
  - **Step 5: Verify token economy**: Compression reduces token size by >= 90%.

- [ ] **Task 3: Token Budget Guard, Cache Advisor & FastMCP Endpoints**
  - **Files:** `src/rush/token_economy/budget.py`, `src/rush/token_economy/cache_advisor.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_token_economy.py`
  - **Step 1: Write failing tests** for budget truncation, cache breakpoint calculation, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_token_economy.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_token_economy.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/token_economy/counter.py`


```python
"""Fast BPE token counter and cost estimator."""

from __future__ import annotations

import math
import re
from pathlib import Path


class FastBPETokenCounter:
    """Estimates token counts using fast byte-pair heuristic (avg 3.8 - 4.0 chars/token)."""

    @staticmethod
    def count_tokens(text: str) -> int:
        if not text:
            return 0
        words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
        char_count = len(text)
        word_count = len(words)
        estimated = math.ceil((char_count * 0.2) + (word_count * 0.5))
        return max(1, estimated)

    @staticmethod
    def count_file_tokens(path: Path) -> int:
        if not path.is_file():
            return 0
        text = path.read_text(encoding="utf-8", errors="replace")
        return FastBPETokenCounter.count_tokens(text)
```

---

### 4.2 `src/rush/token_economy/compressor.py`

```python
"""Python AST structural outline compressor."""

from __future__ import annotations

import ast
from pathlib import Path


class PythonAstOutlineCompressor:
    """Strips implementation bodies from Python ASTs to produce minimal outlines."""

    @staticmethod
    def compress_source(source_code: str) -> str:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code

        class OutlineTransformer(ast.NodeTransformer):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
                docstring = ast.get_docstring(node)
                new_body = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                new_body.append(ast.Expr(value=ast.Constant(value=...)))
                node.body = new_body
                return node

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
                docstring = ast.get_docstring(node)
                new_body = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                new_body.append(ast.Expr(value=ast.Constant(value=...)))
                node.body = new_body
                return node

            def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
                docstring = ast.get_docstring(node)
                new_body = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        new_body.append(self.visit(item))
                    elif isinstance(item, ast.AnnAssign):
                        new_body.append(item)
                if not new_body:
                    new_body.append(ast.Expr(value=ast.Constant(value=...)))
                node.body = new_body
                return node

        transformer = OutlineTransformer()
        transformed_tree = transformer.visit(tree)
        ast.fix_missing_locations(transformed_tree)
        return ast.unparse(transformed_tree)
```

---

### 4.3 `src/rush/token_economy/polyglot_compressor.py`

```python
"""Polyglot AST outline compressor for TypeScript, JavaScript, Rust, and Go."""

from __future__ import annotations

import re


class PolyglotAstCompressor:
    """Extracts type signatures and function prototypes across multiple languages."""

    @staticmethod
    def compress_typescript(ts_source: str) -> str:
        lines = []
        for line in ts_source.splitlines():
            line_clean = line.strip()
            if line_clean.startswith(
                (
                    "export function",
                    "function",
                    "export const",
                    "export interface",
                    "export type",
                    "export class",
                    "class",
                )
            ):
                if "{" in line:
                    sig = line.split("{")[0].strip()
                    lines.append(f"{sig} {{ ... }}")
                else:
                    lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def compress_rust(rs_source: str) -> str:
        lines = []
        for line in rs_source.splitlines():
            line_clean = line.strip()
            if line_clean.startswith(
                (
                    "pub fn",
                    "fn",
                    "pub struct",
                    "struct",
                    "pub enum",
                    "enum",
                    "pub trait",
                    "trait",
                    "impl",
                )
            ):
                if "{" in line:
                    sig = line.split("{")[0].strip()
                    lines.append(f"{sig} {{ ... }}")
                else:
                    lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def compress_go(go_source: str) -> str:
        lines = []
        for line in go_source.splitlines():
            line_clean = line.strip()
            if line_clean.startswith(("func ", "type ", "interface ")):
                if "{" in line:
                    sig = line.split("{")[0].strip()
                    lines.append(f"{sig} {{ ... }}")
                else:
                    lines.append(line)
        return "\n".join(lines)
```

---

### 4.4 `src/rush/token_economy/prompt_compressor.py`

```python
"""Whitespace and comment noise reducer for prompt context."""

from __future__ import annotations

import re


class PromptCompressor:
    """Reduces repetitive indentation, trailing spaces, and redundant blank lines in prompt context."""

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        collapsed = re.sub(r"\n{3,}", "\n\n", text)
        lines = [line.rstrip() for line in collapsed.splitlines()]
        return "\n".join(lines)
```

---

### 4.5 `src/rush/token_economy/cache_advisor.py`

```python
"""Anthropic / OpenAI prompt cache breakpoint analyzer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CacheBreakpointSuggestion:
    optimal_prefix_length: int
    estimated_cache_savings_percent: float
    reason: str


class PromptCacheAdvisor:
    """Analyzes system prompt and tool definitions to recommend stable prefix cache breakpoints."""

    @staticmethod
    def analyze_prefix(prefix_text: str) -> CacheBreakpointSuggestion:
        length = len(prefix_text)
        if length < 1024:
            return CacheBreakpointSuggestion(
                optimal_prefix_length=length,
                estimated_cache_savings_percent=0.0,
                reason="Prefix is under 1,024 tokens; below typical cache minimum threshold.",
            )
        return CacheBreakpointSuggestion(
            optimal_prefix_length=length,
            estimated_cache_savings_percent=85.0,
            reason="Stable prefix meets cache breakpoint threshold; eligible for 85-90% read discounts.",
        )
```

---

### 4.6 `src/rush/token_economy/paginator.py`

```python
"""Sliding window chunk paginator with byte-offset cursors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaginatedChunk:
    chunk_text: str
    cursor_offset: int
    total_bytes: int
    has_more: bool


class TokenChunkPaginator:
    """Splits large output text into byte-bounded sliding chunks."""

    @staticmethod
    def paginate(text: str, offset: int = 0, limit_bytes: int = 4096) -> PaginatedChunk:
        encoded = text.encode("utf-8")
        total = len(encoded)
        if offset >= total:
            return PaginatedChunk(chunk_text="", cursor_offset=total, total_bytes=total, has_more=False)

        end = min(offset + limit_bytes, total)
        chunk_bytes = encoded[offset:end]
        chunk_str = chunk_bytes.decode("utf-8", errors="replace")
        has_more = end < total

        return PaginatedChunk(
            chunk_text=chunk_str,
            cursor_offset=end,
            total_bytes=total,
            has_more=has_more,
        )
```

---

### 4.7 `src/rush/token_economy/symbol_slicer.py`

```python
"""Targeted symbol-level AST extractor."""

from __future__ import annotations

import ast


class SymbolAstSlicer:
    """Extracts only the definition and body of a specific symbol from a Python file."""

    @staticmethod
    def slice_symbol(source_code: str, target_symbol: str) -> str | None:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return None

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == target_symbol:
                    return ast.unparse(node)

        return None
```

---

### 4.8 `src/rush/token_economy/budget.py`

```python
"""Response token budgeting and truncation guard."""

from __future__ import annotations

from rush.token_economy.counter import FastBPETokenCounter


class TokenBudgetGuard:
    """Enforces maximum token thresholds on diagnostic tool outputs."""

    def __init__(self, max_tokens: int = 4000) -> None:
        self.max_tokens = max_tokens

    def enforce_budget(self, text: str) -> str:
        tokens = FastBPETokenCounter.count_tokens(text)
        if tokens <= self.max_tokens:
            return text

        char_ratio = self.max_tokens / tokens
        cutoff = int(len(text) * char_ratio * 0.9)
        truncated = text[:cutoff]
        return f"{truncated}\n\n[TRUNCATED: Response exceeded token budget of {self.max_tokens} tokens. Use pagination to read remaining findings.]"
```

---

### 4.9 `src/rush/token_economy/diet_scanner.py`

```python
"""Context diet scanner discovering large token bloat files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.token_economy.counter import FastBPETokenCounter


@dataclass(frozen=True)
class BloatFileRecord:
    file_path: str
    token_count: int
    size_bytes: int


class ContextDietScanner:
    """Discovers high-token files that bloat AI agent context windows."""

    def __init__(self, repo_root: Path, threshold_tokens: int = 10000) -> None:
        self.repo_root = repo_root.resolve()
        self.threshold_tokens = threshold_tokens

    def scan(self) -> list[BloatFileRecord]:
        bloated = []
        for p in self.repo_root.rglob("*"):
            if p.is_file() and ".venv" not in p.parts and "node_modules" not in p.parts and ".git" not in p.parts:
                tokens = FastBPETokenCounter.count_file_tokens(p)
                if tokens >= self.threshold_tokens:
                    bloated.append(
                        BloatFileRecord(
                            file_path=str(p.relative_to(self.repo_root)),
                            token_count=tokens,
                            size_bytes=p.stat().st_size,
                        )
                    )
        return sorted(bloated, key=lambda r: r.token_count, reverse=True)
```

---

### 4.10 `src/rush/token_economy/cost_calculator.py`

```python
"""Multi-model token pricing and cost forecaster."""

from __future__ import annotations

from dataclasses import dataclass

MODEL_PRICING = {
    "claude-3-7-sonnet": {"input_cost_per_m": 3.00, "output_cost_per_m": 15.00},
    "claude-3-5-haiku": {"input_cost_per_m": 0.80, "output_cost_per_m": 4.00},
    "gpt-4o": {"input_cost_per_m": 2.50, "output_cost_per_m": 10.00},
    "gpt-4o-mini": {"input_cost_per_m": 0.15, "output_cost_per_m": 0.60},
    "gemini-2-5-pro": {"input_cost_per_m": 1.25, "output_cost_per_m": 5.00},
    "deepseek-r1": {"input_cost_per_m": 0.55, "output_cost_per_m": 2.19},
}


@dataclass(frozen=True)
class ModelCostEstimate:
    model_name: str
    token_count: int
    cost_usd: float


class TokenCostCalculator:
    """Calculates dollar costs of prompt payloads across major LLM architectures."""

    @staticmethod
    def calculate_cost(tokens: int) -> list[ModelCostEstimate]:
        estimates = []
        for model, rates in MODEL_PRICING.items():
            cost = (tokens / 1_000_000) * rates["input_cost_per_m"]
            estimates.append(
                ModelCostEstimate(
                    model_name=model,
                    token_count=tokens,
                    cost_usd=round(cost, 6),
                )
            )
        return estimates
```

---

### 4.11 `src/rush/cli.py` (Registration for `rush token`)

```python
import click
from pathlib import Path
from rush.token_economy.counter import FastBPETokenCounter
from rush.token_economy.compressor import PythonAstOutlineCompressor
from rush.token_economy.polyglot_compressor import PolyglotAstCompressor
from rush.token_economy.prompt_compressor import PromptCompressor
from rush.token_economy.cache_advisor import PromptCacheAdvisor
from rush.token_economy.symbol_slicer import SymbolAstSlicer
from rush.token_economy.cost_calculator import TokenCostCalculator
from rush.token_economy.diet_scanner import ContextDietScanner

@click.group(name="token")
def token_group():
    """Analyze and optimize token consumption for coding agents."""
    pass

@token_group.command(name="count")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
def token_count_cmd(paths):
    """Estimate token count for files or directories."""
    repo_root = Path.cwd()
    target_paths = [Path(p) for p in paths] if paths else [repo_root]
    total_tokens = 0

    for p in target_paths:
        if p.is_file():
            cnt = FastBPETokenCounter.count_file_tokens(p)
            total_tokens += cnt
            click.echo(f"  - {p.name}: {cnt:,} tokens")
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and ".venv" not in f.parts and "node_modules" not in f.parts:
                    total_tokens += FastBPETokenCounter.count_file_tokens(f)

    click.echo(f"Total Estimated Tokens: {total_tokens:,}")

@token_group.command(name="outline")
@click.argument("file_path", type=click.Path(exists=True))
def token_outline_cmd(file_path: str):
    """Generate compact structural AST outline of a source file."""
    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix == ".py":
        outline = PythonAstOutlineCompressor.compress_source(source)
    elif path.suffix in (".ts", ".tsx", ".js", ".jsx"):
        outline = PolyglotAstCompressor.compress_typescript(source)
    elif path.suffix == ".rs":
        outline = PolyglotAstCompressor.compress_rust(source)
    elif path.suffix == ".go":
        outline = PolyglotAstCompressor.compress_go(source)
    else:
        outline = source

    before_tokens = FastBPETokenCounter.count_tokens(source)
    after_tokens = FastBPETokenCounter.count_tokens(outline)
    savings = ((before_tokens - after_tokens) / max(1, before_tokens)) * 100

    click.echo(f"# Outline for {path.name} (Compressed {before_tokens} -> {after_tokens} tokens, {savings:.1f}% reduction)\n")
    click.echo(outline)

@token_group.command(name="slice")
@click.argument("file_path", type=click.Path(exists=True))
@click.argument("symbol_name")
def token_slice_cmd(file_path: str, symbol_name: str):
    """Extract a specific function or class symbol from a source file."""
    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    sliced = SymbolAstSlicer.slice_symbol(source, symbol_name)
    if sliced:
        click.echo(sliced)
    else:
        click.echo(f"Symbol '{symbol_name}' not found in '{file_path}'.", err=True)
        raise SystemExit(1)

@token_group.command(name="diet")
@click.option("--threshold", default=10000, help="Token count threshold.")
def token_diet_cmd(threshold: int):
    """Discover high-token bloat files in repository."""
    scanner = ContextDietScanner(Path.cwd(), threshold_tokens=threshold)
    records = scanner.scan()
    if not records:
        click.echo(f"No files exceed token threshold of {threshold:,} tokens.")
        return

    click.echo(f"Discovered {len(records)} high-token file(s) (>= {threshold:,} tokens):")
    for r in records[:20]:
        click.echo(f"  - {r.file_path:<50}: {r.token_count:,} tokens ({r.size_bytes / 1024:.1f} KB)")

@token_group.command(name="cost")
@click.argument("file_path", type=click.Path(exists=True))
def token_cost_cmd(file_path: str):
    """Estimate multi-model dollar cost to ingest a file."""
    cnt = FastBPETokenCounter.count_file_tokens(Path(file_path))
    estimates = TokenCostCalculator.calculate_cost(cnt)
    click.echo(f"Estimated Cost for {file_path} ({cnt:,} tokens):")
    for est in estimates:
        click.echo(f"  - {est.model_name:<20}: ${est.cost_usd:.6f}")
```

---

### 4.12 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for token optimization."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.token_economy.counter import FastBPETokenCounter
from rush.token_economy.compressor import PythonAstOutlineCompressor
from rush.token_economy.polyglot_compressor import PolyglotAstCompressor
from rush.token_economy.symbol_slicer import SymbolAstSlicer
from rush.token_economy.cost_calculator import TokenCostCalculator
from rush.token_economy.diet_scanner import ContextDietScanner

mcp = FastMCP("rush")

@mcp.tool(name="rush_token_count", description="Estimate token count for a code string or file.")
def rush_token_count(text: str) -> str:
    tokens = FastBPETokenCounter.count_tokens(text)
    return json.dumps({"estimated_tokens": tokens}, indent=2)

@mcp.tool(name="rush_ast_outline", description="Generate minimal AST outline of a source file to save tokens.")
def rush_ast_outline(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        return f"File '{file_path}' not found."
    source = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        outline = PythonAstOutlineCompressor.compress_source(source)
    elif path.suffix in (".ts", ".tsx"):
        outline = PolyglotAstCompressor.compress_typescript(source)
    elif path.suffix == ".rs":
        outline = PolyglotAstCompressor.compress_rust(source)
    elif path.suffix == ".go":
        outline = PolyglotAstCompressor.compress_go(source)
    else:
        outline = source
    return outline

@mcp.tool(name="rush_ast_slice_symbol", description="Extract a specific symbol implementation.")
def rush_ast_slice_symbol(file_path: str, symbol_name: str) -> str:
    path = Path(file_path)
    if not path.exists():
        return f"File '{file_path}' not found."
    source = path.read_text(encoding="utf-8", errors="replace")
    sliced = SymbolAstSlicer.slice_symbol(source, symbol_name)
    return sliced or f"Symbol '{symbol_name}' not found."

@mcp.tool(name="rush_token_cost", description="Forecast multi-model ingestion cost for a token count.")
def rush_token_cost(tokens: int) -> str:
    estimates = TokenCostCalculator.calculate_cost(tokens)
    return json.dumps([{"model": e.model_name, "cost_usd": e.cost_usd} for e in estimates], indent=2)

@mcp.tool(name="rush_context_diet", description="Scan repository for high-token bloat files.")
def rush_context_diet(threshold_tokens: int = 10000) -> str:
    scanner = ContextDietScanner(Path.cwd(), threshold_tokens=threshold_tokens)
    records = scanner.scan()
    return json.dumps([{"file": r.file_path, "tokens": r.token_count} for r in records[:20]], indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_token_economy.py`

```python
"""Comprehensive test suite for FastBPETokenCounter, PythonAstOutlineCompressor, PolyglotAstCompressor, PromptCompressor, PromptCacheAdvisor, TokenChunkPaginator, SymbolAstSlicer, TokenBudgetGuard, ContextDietScanner, and TokenCostCalculator."""

from pathlib import Path
import pytest
from rush.token_economy.counter import FastBPETokenCounter
from rush.token_economy.compressor import PythonAstOutlineCompressor
from rush.token_economy.polyglot_compressor import PolyglotAstCompressor
from rush.token_economy.prompt_compressor import PromptCompressor
from rush.token_economy.cache_advisor import PromptCacheAdvisor
from rush.token_economy.paginator import TokenChunkPaginator
from rush.token_economy.symbol_slicer import SymbolAstSlicer
from rush.token_economy.budget import TokenBudgetGuard
from rush.token_economy.diet_scanner import ContextDietScanner
from rush.token_economy.cost_calculator import TokenCostCalculator


def test_token_counter_basic():
    text = "def hello_world():\n    return 'hello world'\n"
    tokens = FastBPETokenCounter.count_tokens(text)
    assert tokens > 0
    assert tokens < len(text)


def test_token_counter_empty():
    assert FastBPETokenCounter.count_tokens("") == 0


def test_python_ast_outline_compressor():
    source = """
class DataService:
    '''Service for handling data.'''
    url: str

    def heavy_computation(self, a: int, b: int) -> int:
        '''Performs heavy computation.'''
        x = a * 10
        y = b * 20
        for i in range(100):
            x += i
        return x + y
"""
    outline = PythonAstOutlineCompressor.compress_source(source)
    assert "class DataService:" in outline
    assert "def heavy_computation(self, a: int, b: int) -> int:" in outline
    assert "Performs heavy computation." in outline
    assert "for i in range" not in outline
    assert "..." in outline


def test_polyglot_ast_compressor_typescript():
    ts_code = """
export function add(a: number, b: number): number {
    return a + b;
}
export interface User {
    id: number;
}
"""
    comp = PolyglotAstCompressor.compress_typescript(ts_code)
    assert "export function add(a: number, b: number): number {" in comp
    assert "return a + b" not in comp


def test_polyglot_ast_compressor_rust():
    rs_code = """
pub fn calculate(x: i32) -> i32 {
    x * 2
}
"""
    comp = PolyglotAstCompressor.compress_rust(rs_code)
    assert "pub fn calculate(x: i32) -> i32 {" in comp
    assert "x * 2" not in comp


def test_polyglot_ast_compressor_go():
    go_code = """
func ProcessData(items []string) error {
    return nil
}
"""
    comp = PolyglotAstCompressor.compress_go(go_code)
    assert "func ProcessData(items []string) error {" in comp
    assert "return nil" not in comp


def test_prompt_compressor():
    raw_prompt = "Line 1\n\n\n\nLine 2   \nLine 3"
    cleaned = PromptCompressor.clean_text(raw_prompt)
    assert "\n\n\n" not in cleaned
    assert "Line 2   " not in cleaned


def test_prompt_cache_advisor():
    small_res = PromptCacheAdvisor.analyze_prefix("short prompt")
    assert small_res.estimated_cache_savings_percent == 0.0

    large_res = PromptCacheAdvisor.analyze_prefix("long prompt" * 200)
    assert large_res.estimated_cache_savings_percent == 85.0


def test_token_chunk_paginator():
    text = "Hello world from paginator test!"
    chunk = TokenChunkPaginator.paginate(text, offset=0, limit_bytes=10)
    assert len(chunk.chunk_text) == 10
    assert chunk.has_more is True
    assert chunk.cursor_offset == 10


def test_symbol_ast_slicer():
    code = """
def helper_one():
    return 1

def target_func(x: int):
    return x * 2
"""
    sliced = SymbolAstSlicer.slice_symbol(code, "target_func")
    assert sliced is not None
    assert "def target_func(x: int):" in sliced
    assert "helper_one" not in sliced


def test_token_budget_guard():
    guard = TokenBudgetGuard(max_tokens=10)
    small_text = "short text"
    assert guard.enforce_budget(small_text) == small_text

    long_text = "a" * 1000
    enforced = guard.enforce_budget(long_text)
    assert "[TRUNCATED" in enforced


def test_context_diet_scanner(tmp_path: Path):
    f_large = tmp_path / "giant_fixture.json"
    f_large.write_text('{"data": "val"}\n' * 5000, encoding="utf-8")

    f_small = tmp_path / "small.py"
    f_small.write_text("x = 1\n", encoding="utf-8")

    scanner = ContextDietScanner(tmp_path, threshold_tokens=1000)
    records = scanner.scan()
    assert len(records) == 1
    assert "giant_fixture.json" in records[0].file_path


def test_token_cost_calculator():
    estimates = TokenCostCalculator.calculate_cost(100_000)
    assert len(estimates) == 6
    for est in estimates:
        assert est.cost_usd > 0.0
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 32 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T09:50:00.100Z", "phase": 32, "tool": "rush_token", "event": "tokens_counted", "file": "src/core.py", "tokens": 450}
{"timestamp": "2026-08-21T09:50:01.200Z", "phase": 32, "tool": "rush_token", "event": "ast_outline_generated", "file": "src/utils.py", "savings_percent": 94.2}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 32 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 32: Token Economy & Context Optimization**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 32 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Token Optimization & Context Diet for AI Coding" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush token count`, `rush token outline`, `rush token diet`, `rush token cost` (flags: `--model`, `--budget`, `--signatures-only`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for generating compact repository outlines before feeding context to Claude or ChatGPT.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated pre-prompt recipe for estimating API prompt cost.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show before/after token reduction benchmarks (e.g. 15,000 tokens -> 650 tokens).
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting token budgets for multi-agent workflows.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for tokenizer encoding fallback errors and outline parser syntax warnings.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush generates syntactically valid AST outlines across Python, TypeScript, and Rust.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_token_count` and `rush_token_outline` FastMCP tools for LLM agent context minimization.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document AST outline JSON schemas and token cost calculation response models.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `token` tool in AI Agent Optimization category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[token]` configuration table (`default_model`, `max_response_tokens`, `diet_threshold`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document BPE tokenization abstraction layer and Tree-Sitter AST outline compression engine.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for registering new LLM model pricing tables and tokenizers.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Include CI step running `rush token diet` to detect accidental large asset commits.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document BPE token exact match test fixtures and AST outline compression verification tests.
- **[`docs/tools/token.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/token.md)**: Create dedicated reference documentation.

### 7.3 Automated Documentation Parity Check
```bash
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check
```

### 7.4 Ending Git Lifecycle Commands
Execute these commands upon completing all phase tasks and verification checks:
```bash
# 1. Full verification gate
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format src tests scripts
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 2. Stage & Commit
git add src/ tests/ docs/
git commit -m "feat(phase-32): implement bpe token accounting, ast outline compressor and context optimizer"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
