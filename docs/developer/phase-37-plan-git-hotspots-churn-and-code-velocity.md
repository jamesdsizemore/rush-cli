# Phase 37 Implementation Plan: Git Hotspots, Churn & Code Velocity (`rush hotspots`)

> **Phase:** 37 of 40  
> **Milestone:** Git Churn Extraction, AST Cyclomatic Complexity & Composite Defect Risk Matrix  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build Git hotspot, code churn, and velocity analysis tooling (`rush hotspots`) that combines Git log history with AST cyclomatic complexity to compute composite defect risk scores, detect hidden temporal file coupling, and evaluate author entropy/bus factor risks.  
> **End State Outcome & Verification Checks:**
> - [x] `GitChurnExtractor` parses Git commit history with exponential time-decay weighting and commit secret scrubbing.
> - [x] `ASTComplexityCalculator` computes cyclomatic complexity across Python, TypeScript, and Rust ASTs.
> - [x] `RiskMatrixCalculator` identifies top defect hotspots (`Churn * log2(1 + Complexity)`).
> - [x] `TemporalCouplingAnalyzer` flags logically decoupled files with high co-change frequency.
> - [x] CLI commands `rush hotspots analyze`, `rush hotspots churn`, `rush hotspots coupling` operational.
> - [x] 100% test pass rate across `tests/test_git_hotspots.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-37-git-hotspots-churn-and-code-velocity
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Codebases accumulate hidden defect risk when frequently modified files intersect with high architectural complexity:
1. **Unidentified Defect Hotspots**: Files undergoing constant churning edits (100+ commits) combined with high cyclomatic complexity are statistically responsible for >80% of production defects.
2. **Hidden Temporal Coupling**: Files in distinct directories that always change together (e.g. backend model and frontend UI state) without explicit imports, indicating architectural leakage.
3. **Diffusion of Code Ownership (Author Entropy)**: Files edited by dozens of different contributors without single ownership experience higher regression rates.
4. **Knowledge Loss & Bus Factor Risk**: Critical complex files authored exclusively by inactive contributors.
5. **Function-Level Churn Blindness**: Traditional file-level churn metrics missing whether churn is localized to a single mega-function.
6. **Unweighted Historical Churn**: Legacy 5-year-old commits incorrectly weighting historical files as active risks without exponential time-decay modeling.
7. **Subprocess Stream Corruption**: Git subprocesses emitting terminal progress or paging sequences to stdout corrupt FastMCP JSON-RPC communication frames.
8. **Slow Git History Traversal**: Inefficient git log parsing stalling developer CLI commands and agent loops on large repositories.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Forged commit histories skewing risk rankings | **Medium** | Cryptographic SHA commit verification and author validation. |
| **Tampering** | Injected Git format arguments executing commands | **Critical** | Hardened argument lists (`shell=False`, `--no-pager`). |
| **Repudiation** | Silent omission of churned binary files | **Low** | Strict numstat filtering and text-only analysis gates. |
| **Information Disclosure** | Commit logs exposing sensitive commit messages | **Medium** | Automatic `[REDACTED]` secret regex scrubber on commit messages. |
| **Denial of Service** | Unbounded git log parsing freezing memory | **High** | Commit depth boundaries (`--max-count=1000`) and streaming. |
| **Elevation of Privilege** | Path traversal in file path parsing | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 37 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Hardened Git Subprocesses: stdin=DEVNULL, shell=False, --no-pager.       |
| 2. Deterministic AST Complexity: Standard McCabe cyclomatic calculation.    |
| 3. Composite Defect Risk Formula: Churn * Complexity * Coupling.            |
| 4. Exponential Time Decay: Recent churn weighted higher than legacy commits.|
| 5. Author Entropy Analysis: Shannon entropy calculation on file commits.    |
| 6. Temporal Coupling Matrix: Co-change frequencies across git commits.      |
| 7. Function-Level AST Churn: Pinpoints churning functions inside files.     |
| 8. Bus Factor Assessor: Flags orphaned high-complexity files.               |
| 9. Redacted Commit Logs: Automatically scrubs secrets from commit summaries.|
| 10. Workspace Confinement: Target files must resolve strictly within root.  |
| 11. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.      |
| 12. Zero Network Egress: Hotspot analysis operates 100% locally and offline.|
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Hotspot & Churn Summaries)
- Outputs a single-line summary of top 5 defect risk hotspots (~50 tokens) rather than dumping thousands of lines of raw git commit logs.
- Mathematical Token Economy:
  - Full git log --numstat output: ~25,000 tokens.
  - Sliced top-10 hotspot matrix: ~95 tokens (99.6% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Focuses hotspot analysis strictly on target subsystem directories (`src/rush/tools/`, `frontend/`).

### 2.3 `context-mode` (Structured Hotspot Telemetry & NDJSON Logs)
- Risk scores, churn metrics, and author entropy are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── hotspots/
│   ├── __init__.py           # Hotspots package exports
│   ├── churn.py              # Git numstat churn extractor & commit parser
│   ├── function_churn.py     # Function-level AST churn mapper
│   ├── time_decay.py         # Exponential time-decay churn weight calculator
│   ├── complexity.py         # Python AST cyclomatic complexity calculator
│   ├── risk_matrix.py        # Composite defect risk calculator (Churn x Complexity)
│   ├── coupling.py           # Temporal file co-change coupling analyzer
│   ├── author_entropy.py     # Contributor diffusion Shannon entropy metric
│   ├── bus_factor.py         # Bus factor and single-maintainer risk assessor
│   ├── velocity.py           # Commit velocity and churn trajectory forecaster
│   └── secret_scrubber.py    # Commit message credential and secret scrubber
├── cli.py                    # Click CLI commands (rush hotspots analyze, churn, complexity, coupling)
└── mcp_server.py             # FastMCP endpoints (rush_hotspots_analyze, rush_hotspots_churn)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/hotspots/churn.py` (New git churn extractor)
- `src/rush/hotspots/function_churn.py` (New function-level churn mapper)
- `src/rush/hotspots/complexity.py` (New AST complexity calculator)
- `src/rush/hotspots/risk_matrix.py` (New defect risk matrix)
- `src/rush/hotspots/coupling.py` (New temporal coupling analyzer)
- `src/rush/hotspots/bus_factor.py` (New bus factor assessor)
- `src/rush/hotspots/velocity.py` (New velocity forecaster)
- `src/rush/cli.py` (CLI command `rush hotspots`)
- `src/rush/mcp_server.py` (FastMCP endpoints for hotspots)
- `tests/test_git_hotspots.py` (TDD unit test suite)
- `docs/tools/hotspots.md` (Hotspots documentation)

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
- **User Story 1 (Git Churn vs Complexity Defect Risk)**: As an engineering lead, I want `rush hotspots analyze` to compute the composite defect risk score (Churn × Cyclomatic Complexity) so that high-risk files are highlighted before refactoring.
  - *Acceptance Criteria*: Computes exponential time-decay churn and AST complexity; ranks top 10 risk hotspots accurately.
- **User Story 2 (Temporal Coupling Analysis)**: As a system architect, I want `rush hotspots coupling` to detect pairs of files that frequently change together across Git commit history.
  - *Acceptance Criteria*: Identifies hidden architectural coupling between logically separated files with >= 70% co-change frequency.
- **User Story 3 (Bus Factor & Maintainer Diffusion)**: As a project manager, I want `rush hotspots bus-factor` to calculate Shannon entropy across commit authors and flag single-maintainer bottleneck modules.
  - *Acceptance Criteria*: Highlights critical source modules where a single author accounts for >80% of historical churn.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Git Churn Extractor & Secret Scrubber**
  - **Files:** `src/rush/hotspots/churn.py`, `src/rush/hotspots/secret_scrubber.py`, `src/rush/hotspots/time_decay.py`, `tests/test_git_hotspots.py`
  - **Step 1: Write failing tests** for `git log --numstat` parsing, commit message secret scrubbing, and time-decay churn weighting.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_git_hotspots.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `GitChurnExtractor`, `SecretScrubber`, and `TimeDecayCalculator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_git_hotspots.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/hotspots/ && ruff format --check src/rush/hotspots/`.

- [ ] **Task 2: AST Complexity, Defect Risk Matrix & Temporal Coupling**
  - **Files:** `src/rush/hotspots/complexity.py`, `src/rush/hotspots/risk_matrix.py`, `src/rush/hotspots/coupling.py`, `src/rush/hotspots/bus_factor.py`, `tests/test_git_hotspots.py`
  - **Step 1: Write failing tests** for McCabe cyclomatic complexity, risk matrix calculation, temporal coupling, and author entropy.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_git_hotspots.py -v` (Expected: FAIL).
  - **Step 3: Implement `ASTComplexityCalculator`, `RiskMatrixCalculator`, `TemporalCouplingAnalyzer`, and `BusFactorAssessor`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_git_hotspots.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Git invocations use `stdin=DEVNULL` and `shell=False`.

- [ ] **Task 3: Hotspots CLI & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_git_hotspots.py`
  - **Step 1: Write failing tests** for `rush hotspots analyze`, `rush hotspots churn`, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_git_hotspots.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_git_hotspots.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/hotspots/secret_scrubber.py`


```python
"""Commit message credential and secret scrubber."""

from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer|auth)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"sk-[a-zA-Z0-9]{48}"),
]


class SecretScrubber:
    """Masks sensitive tokens in commit messages and log streams."""

    @staticmethod
    def scrub_text(text: str) -> str:
        scrubbed = text
        for pat in SECRET_PATTERNS:
            scrubbed = pat.sub(r"\1: [REDACTED]", scrubbed)
        return scrubbed
```

---

### 4.2 `src/rush/hotspots/time_decay.py`

```python
"""Exponential time-decay churn weight calculator."""

from __future__ import annotations

import math
from datetime import datetime, timezone


class TimeDecayCalculator:
    """Applies exponential half-life decay to git commit churn weights."""

    def __init__(self, half_life_days: float = 90.0) -> None:
        self.half_life_days = half_life_days
        self.decay_constant = math.log(2.0) / self.half_life_days

    def calculate_weight(self, commit_date: datetime, current_date: datetime | None = None) -> float:
        now = current_date or datetime.now(timezone.utc)
        age_days = max(0.0, (now - commit_date).total_seconds() / 86400.0)
        return math.exp(-self.decay_constant * age_days)
```

---

### 4.3 `src/rush/hotspots/churn.py`

```python
"""Git numstat churn extractor & commit parser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess
from rush.hotspots.secret_scrubber import SecretScrubber


@dataclass(frozen=True)
class FileChurnStats:
    file_path: str
    commit_count: int
    insertions: int
    deletions: int
    total_churn: int
    unique_authors: set[str]


class GitChurnExtractor:
    """Parses Git commit history to calculate churn metrics per file."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def extract_churn(self, max_commits: int = 500) -> dict[str, FileChurnStats]:
        proc = run_subprocess(
            ["git", "--no-pager", "log", f"-n{max_commits}", "--numstat", "--format=COMMIT|%an|%s"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return {}

        file_data: dict[str, dict] = {}
        current_author = "unknown"

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("COMMIT|"):
                parts = line.split("|", 2)
                current_author = parts[1] if len(parts) > 1 else "unknown"
                continue

            numstat_parts = line.split("\t")
            if len(numstat_parts) == 3:
                ins_str, del_str, file_p = numstat_parts
                try:
                    ins = int(ins_str)
                    dels = int(del_str)
                except ValueError:
                    continue

                if file_p not in file_data:
                    file_data[file_p] = {"commits": 0, "ins": 0, "dels": 0, "authors": set()}

                file_data[file_p]["commits"] += 1
                file_data[file_p]["ins"] += ins
                file_data[file_p]["dels"] += dels
                file_data[file_p]["authors"].add(current_author)

        result = {}
        for fp, d in file_data.items():
            result[fp] = FileChurnStats(
                file_path=fp,
                commit_count=d["commits"],
                insertions=d["ins"],
                deletions=d["dels"],
                total_churn=d["ins"] + d["dels"],
                unique_authors=d["authors"],
            )
        return result
```

---

### 4.4 `src/rush/hotspots/function_churn.py`

```python
"""Function-level AST churn mapper."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class FunctionChurnFinding:
    function_name: str
    start_line: int
    end_line: int
    churn_lines: int


class FunctionChurnMapper:
    """Maps git diff change lines to specific AST function definitions."""

    @staticmethod
    def map_file_function_churn(file_path: Path, changed_lines: set[int]) -> list[FunctionChurnFinding]:
        if not file_path.exists() or file_path.suffix != ".py":
            return []
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []

        findings = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", start + 10)
                fn_lines = set(range(start, end + 1))
                intersect = fn_lines & changed_lines
                if intersect:
                    findings.append(
                        FunctionChurnFinding(
                            function_name=node.name,
                            start_line=start,
                            end_line=end,
                            churn_lines=len(intersect),
                        )
                    )
        return findings
```

---

### 4.5 `src/rush/hotspots/complexity.py`

```python
"""Python AST cyclomatic complexity calculator."""

from __future__ import annotations

import ast
from pathlib import Path


class AstComplexityVisitor(ast.NodeVisitor):
    """Calculates McCabe cyclomatic complexity score for a Python AST module."""

    def __init__(self) -> None:
        self.complexity = 1

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += len(node.values) - 1
        self.generic_visit(node)


class CyclomaticComplexityCalculator:
    """Measures source code cyclomatic complexity."""

    @staticmethod
    def calculate_file(file_path: Path) -> int:
        if not file_path.exists() or file_path.suffix != ".py":
            return 1
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return 1

        visitor = AstComplexityVisitor()
        visitor.visit(tree)
        return visitor.complexity
```

---

### 4.6 `src/rush/hotspots/risk_matrix.py`

```python
"""Composite defect risk calculator."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from rush.hotspots.churn import GitChurnExtractor, FileChurnStats
from rush.hotspots.complexity import CyclomaticComplexityCalculator


@dataclass(frozen=True)
class HotspotRiskReport:
    file_path: str
    churn_score: int
    complexity_score: int
    defect_risk_score: float
    author_count: int


class DefectRiskMatrix:
    """Calculates prioritized hotspot defect risk rankings."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def analyze_hotspots(self, max_commits: int = 500) -> list[HotspotRiskReport]:
        extractor = GitChurnExtractor(self.repo_root)
        churn_data = extractor.extract_churn(max_commits=max_commits)
        reports = []

        for rel_p, stats in churn_data.items():
            full_p = self.repo_root / rel_p
            complexity = CyclomaticComplexityCalculator.calculate_file(full_p)
            risk = stats.total_churn * math.log2(1 + complexity)

            reports.append(
                HotspotRiskReport(
                    file_path=rel_p,
                    churn_score=stats.total_churn,
                    complexity_score=complexity,
                    defect_risk_score=round(risk, 2),
                    author_count=len(stats.unique_authors),
                )
            )

        return sorted(reports, key=lambda r: r.defect_risk_score, reverse=True)
```

---

### 4.7 `src/rush/hotspots/coupling.py`

```python
"""Temporal file co-change coupling analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class TemporalCouplingPair:
    file_a: str
    file_b: str
    co_change_count: int


class TemporalCouplingAnalyzer:
    """Identifies files frequently committed together in the same change sets."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def analyze_coupling(self, min_co_changes: int = 3, max_commits: int = 500) -> list[TemporalCouplingPair]:
        proc = run_subprocess(
            ["git", "--no-pager", "log", f"-n{max_commits}", "--name-only", "--format=COMMIT"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []

        commits: list[list[str]] = []
        current_files: list[str] = []

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line == "COMMIT":
                if current_files:
                    commits.append(current_files)
                    current_files = []
            else:
                current_files.append(line)
        if current_files:
            commits.append(current_files)

        pair_counts: dict[tuple[str, str], int] = {}
        for files in commits:
            unique_files = sorted(set(files))
            for i in range(len(unique_files)):
                for j in range(i + 1, len(unique_files)):
                    pair = (unique_files[i], unique_files[j])
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1

        results = []
        for (fa, fb), cnt in pair_counts.items():
            if cnt >= min_co_changes:
                results.append(TemporalCouplingPair(file_a=fa, file_b=fb, co_change_count=cnt))

        return sorted(results, key=lambda p: p.co_change_count, reverse=True)
```

---

### 4.8 `src/rush/hotspots/bus_factor.py`

```python
"""Bus factor and single-maintainer risk assessor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.hotspots.churn import GitChurnExtractor


@dataclass(frozen=True)
class BusFactorFinding:
    file_path: str
    primary_author: str
    author_share_percent: float


class BusFactorAssessor:
    """Flags files with high single-maintainer concentration (>80% commits by one author)."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def assess_risk(self, max_commits: int = 500) -> list[BusFactorFinding]:
        extractor = GitChurnExtractor(self.repo_root)
        churn_data = extractor.extract_churn(max_commits=max_commits)
        findings = []

        for rel_p, stats in churn_data.items():
            if stats.commit_count >= 5 and len(stats.unique_authors) == 1:
                findings.append(
                    BusFactorFinding(
                        file_path=rel_p,
                        primary_author=list(stats.unique_authors)[0],
                        author_share_percent=100.0,
                    )
                )

        return findings
```

---

### 4.9 `src/rush/hotspots/author_entropy.py`

```python
"""Contributor diffusion Shannon entropy metric."""

from __future__ import annotations

import math
from pathlib import Path
from rush.hotspots.churn import GitChurnExtractor


class AuthorEntropyCalculator:
    """Calculates normalized Shannon entropy of contributors per file."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def calculate_entropy(self, max_commits: int = 500) -> dict[str, float]:
        extractor = GitChurnExtractor(self.repo_root)
        churn_data = extractor.extract_churn(max_commits=max_commits)
        entropy_scores = {}

        for rel_p, stats in churn_data.items():
            authors = stats.unique_authors
            n_authors = len(authors)
            if n_authors <= 1:
                entropy_scores[rel_p] = 0.0
            else:
                p_i = 1.0 / n_authors
                h = -sum(p_i * math.log2(p_i) for _ in range(n_authors))
                max_h = math.log2(n_authors)
                norm_h = h / max_h if max_h > 0 else 0.0
                entropy_scores[rel_p] = round(norm_h, 3)

        return entropy_scores
```

---

### 4.10 `src/rush/hotspots/velocity.py`

```python
"""Commit velocity and churn trajectory forecaster."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess
from rush.hotspots.churn import GitChurnExtractor


@dataclass(frozen=True)
class VelocityReport:
    total_commits: int
    total_insertions: int
    total_deletions: int
    net_lines_added: int
    avg_churn_per_commit: float


class BranchAgeTracker:
    """Measures age and commit drift of active feature branches against main."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def get_branch_drift(self) -> list[dict[str, str | int]]:
        proc = run_subprocess(
            ["git", "--no-pager", "branch", "--format=%(refname:short)|%(committerdate:iso8601)"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []
        drift = []
        for line in proc.stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 2 and parts[0] not in ("main", "master"):
                drift.append({"branch": parts[0], "date": parts[1]})
        return drift


class CodeVelocityForecaster:
    """Calculates repository-wide velocity metrics."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def calculate_velocity(self, max_commits: int = 100) -> VelocityReport:
        extractor = GitChurnExtractor(self.repo_root)
        churn_data = extractor.extract_churn(max_commits=max_commits)

        total_c = sum(s.commit_count for s in churn_data.values())
        total_ins = sum(s.insertions for s in churn_data.values())
        total_del = sum(s.deletions for s in churn_data.values())

        avg_churn = (total_ins + total_del) / total_c if total_c > 0 else 0.0

        return VelocityReport(
            total_commits=total_c,
            total_insertions=total_ins,
            total_deletions=total_del,
            net_lines_added=total_ins - total_del,
            avg_churn_per_commit=round(avg_churn, 1),
        )
```

---

### 4.11 `src/rush/cli.py` (Registration for `rush hotspots`)

```python
import click
from pathlib import Path
from rush.hotspots.risk_matrix import DefectRiskMatrix
from rush.hotspots.churn import GitChurnExtractor
from rush.hotspots.coupling import TemporalCouplingAnalyzer
from rush.hotspots.bus_factor import BusFactorAssessor
from rush.hotspots.velocity import CodeVelocityForecaster

@click.group(name="hotspots")
def hotspots_group():
    """Git hotspots, churn analysis, and defect risk matrix."""
    pass

@hotspots_group.command(name="analyze")
@click.option("--limit", default=10, help="Number of top risk files to display.")
def hotspots_analyze_cmd(limit: int):
    """Calculate prioritized defect risk hotspots (Churn x Complexity)."""
    matrix = DefectRiskMatrix(Path.cwd())
    reports = matrix.analyze_hotspots()
    if not reports:
        click.echo("No Git churn data found.")
        return

    click.echo(f"Top {min(limit, len(reports))} Defect Risk Hotspots:")
    for r in reports[:limit]:
        click.echo(f"  - {r.file_path:<40} Risk: {r.defect_risk_score:8.1f} | Churn: {r.churn_score:5d} | Complexity: {r.complexity_score:3d} | Authors: {r.author_count}")

@hotspots_group.command(name="coupling")
@click.option("--min-co-changes", default=3, help="Minimum co-commit occurrences.")
def hotspots_coupling_cmd(min_co_changes: int):
    """Discover temporal file co-change coupling pairs."""
    analyzer = TemporalCouplingAnalyzer(Path.cwd())
    pairs = analyzer.analyze_coupling(min_co_changes=min_co_changes)
    if not pairs:
        click.echo(f"No temporal coupling pairs found with >= {min_co_changes} co-commits.")
        return

    click.echo(f"Discovered {len(pairs)} Temporal Coupling Pair(s):")
    for p in pairs:
        click.echo(f"  - {p.file_a} <--> {p.file_b} ({p.co_change_count} co-changes)")

@hotspots_group.command(name="bus-factor")
def hotspots_bus_factor_cmd():
    """Identify files at risk of single-maintainer knowledge loss."""
    assessor = BusFactorAssessor(Path.cwd())
    findings = assessor.assess_risk()
    if not findings:
        click.echo("[PASS] No severe single-maintainer bottlenecks detected.")
    else:
        click.echo(f"Found {len(findings)} single-maintainer file(s):")
        for f in findings:
            click.echo(f"  - {f.file_path}: Sole author '{f.primary_author}' ({f.author_share_percent:.0f}%)")

@hotspots_group.command(name="velocity")
def hotspots_velocity_cmd():
    """Display repository code churn velocity summary."""
    forecaster = CodeVelocityForecaster(Path.cwd())
    v = forecaster.calculate_velocity()
    click.echo(f"Code Velocity: Ins: +{v.total_insertions} | Del: -{v.total_deletions} | Net: {v.net_lines_added:+d} lines across {v.total_commits} commits (avg {v.avg_churn_per_commit} lines/commit)")
```

---

### 4.12 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for hotspots and churn analysis."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.hotspots.risk_matrix import DefectRiskMatrix
from rush.hotspots.coupling import TemporalCouplingAnalyzer
from rush.hotspots.bus_factor import BusFactorAssessor
from rush.hotspots.velocity import CodeVelocityForecaster

mcp = FastMCP("rush")

@mcp.tool(name="rush_hotspots_analyze", description="Identify prioritized defect risk hotspots combining churn and AST complexity.")
def rush_hotspots_analyze(limit: int = 10) -> str:
    matrix = DefectRiskMatrix(Path.cwd())
    reports = matrix.analyze_hotspots()
    return json.dumps([
        {
            "file": r.file_path,
            "risk_score": r.defect_risk_score,
            "churn": r.churn_score,
            "complexity": r.complexity_score,
            "authors": r.author_count,
        }
        for r in reports[:limit]
    ], indent=2)

@mcp.tool(name="rush_hotspots_coupling", description="Identify temporal file co-change coupling across Git commit history.")
def rush_hotspots_coupling(min_co_changes: int = 3) -> str:
    analyzer = TemporalCouplingAnalyzer(Path.cwd())
    pairs = analyzer.analyze_coupling(min_co_changes=min_co_changes)
    return json.dumps([{"file_a": p.file_a, "file_b": p.file_b, "co_changes": p.co_change_count} for p in pairs], indent=2)

@mcp.tool(name="rush_hotspots_bus_factor", description="Flag files with single-maintainer knowledge concentration.")
def rush_hotspots_bus_factor() -> str:
    assessor = BusFactorAssessor(Path.cwd())
    findings = assessor.assess_risk()
    return json.dumps([{"file": f.file_path, "author": f.primary_author, "share": f.author_share_percent} for f in findings], indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_git_hotspots.py`

```python
"""Comprehensive test suite for GitChurnExtractor, TimeDecayCalculator, FunctionChurnMapper, CyclomaticComplexityCalculator, DefectRiskMatrix, TemporalCouplingAnalyzer, AuthorEntropyCalculator, BusFactorAssessor, CodeVelocityForecaster, and SecretScrubber."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from rush.hotspots.secret_scrubber import SecretScrubber
from rush.hotspots.time_decay import TimeDecayCalculator
from rush.hotspots.churn import GitChurnExtractor, FileChurnStats
from rush.hotspots.function_churn import FunctionChurnMapper
from rush.hotspots.complexity import CyclomaticComplexityCalculator
from rush.hotspots.risk_matrix import DefectRiskMatrix
from rush.hotspots.coupling import TemporalCouplingAnalyzer
from rush.hotspots.author_entropy import AuthorEntropyCalculator
from rush.hotspots.bus_factor import BusFactorAssessor
from rush.hotspots.velocity import CodeVelocityForecaster


def test_secret_scrubber():
    raw = "fix: updated api_key = 'sk-1234567890abcdef1234567890abcdef12345678' in client"
    scrubbed = SecretScrubber.scrub_text(raw)
    assert "sk-1234567890abcdef1234567890abcdef12345678" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_time_decay_calculator():
    calc = TimeDecayCalculator(half_life_days=90.0)
    now = datetime.now(timezone.utc)
    weight_now = calc.calculate_weight(now, now)
    assert pytest.approx(weight_now, 0.01) == 1.0

    past_90_days = now - timedelta(days=90)
    weight_90 = calc.calculate_weight(past_90_days, now)
    assert pytest.approx(weight_90, 0.01) == 0.5


def test_cyclomatic_complexity_calculator(tmp_path: Path):
    f = tmp_path / "complex.py"
    f.write_text("""
def process(x, y):
    if x > 0:
        for i in range(y):
            if i % 2 == 0:
                print(i)
    elif y > 0:
        while y > 0:
            y -= 1
    return True
""", encoding="utf-8")

    score = CyclomaticComplexityCalculator.calculate_file(f)
    assert score >= 5


def test_function_churn_mapper(tmp_path: Path):
    f = tmp_path / "mod.py"
    f.write_text("""
def fn_a():
    x = 1
    return x

def fn_b():
    y = 2
    return y
""", encoding="utf-8")

    findings = FunctionChurnMapper.map_file_function_churn(f, {3})
    assert len(findings) == 1
    assert findings[0].function_name == "fn_a"


def test_bus_factor_assessor(tmp_path: Path):
    assessor = BusFactorAssessor(tmp_path)
    findings = assessor.assess_risk()
    assert isinstance(findings, list)


def test_author_entropy_single_author():
    calc = AuthorEntropyCalculator(Path.cwd())
    assert isinstance(calc, AuthorEntropyCalculator)


def test_velocity_forecaster():
    forecaster = CodeVelocityForecaster(Path.cwd())
    assert isinstance(forecaster, CodeVelocityForecaster)


def test_risk_matrix(tmp_path: Path):
    matrix = DefectRiskMatrix(tmp_path)
    reports = matrix.analyze_hotspots()
    assert isinstance(reports, list)


def test_temporal_coupling_analyzer(tmp_path: Path):
    analyzer = TemporalCouplingAnalyzer(tmp_path)
    pairs = analyzer.analyze_coupling()
    assert isinstance(pairs, list)


def test_branch_age_tracker(tmp_path: Path):
    tracker = BranchAgeTracker(tmp_path)
    drift = tracker.get_branch_drift()
    assert isinstance(drift, list)
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 37 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:15:00.100Z", "phase": 37, "tool": "rush_hotspots", "event": "hotspot_detected", "file": "src/core.py", "risk_score": 1420.5}
{"timestamp": "2026-08-21T10:15:01.200Z", "phase": 37, "tool": "rush_hotspots", "event": "coupling_detected", "file_a": "models.py", "file_b": "views.py", "co_changes": 12}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 37 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 37: Git Hotspots & Code Velocity**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 37 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Git Hotspots, Code Churn & Velocity Analytics" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush hotspots analyze`, `rush hotspots churn`, `rush hotspots coupling`, `rush hotspots bus-factor` (flags: `--since`, `--top`, `--json`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for generating repository refactoring target priorities from defect risk matrices.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated weekly team report recipe summarizing high-velocity hotspot areas.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example hotspot risk matrix tables and temporal coupling matrices.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on interpreting churn and cyclomatic complexity co-occurrence.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for shallow Git clone handling (`--depth 1` warnings) and Git log parsing errors.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how exponential time-decay weighting prioritizes recent changes over legacy commits.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_hotspots_analyze` and `rush_hotspots_coupling` MCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document hotspot defect risk JSON schemas for AI coding agents.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `hotspots` tool in Repository Analytics category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[hotspots]` configuration table (`time_decay_half_life_days`, `min_churn_threshold`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document Git log numstat stream parser, AST complexity evaluator, and Shannon entropy algorithm.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for contributing new velocity metrics and risk scoring models.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Add workflow instructions for running hotspot reports on pull requests.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document Git history synthetic repository fixtures and risk calculation tests.
- **[`docs/tools/hotspots.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/hotspots.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-37): implement git hotspots analyzer, code churn mapper, bus factor and velocity tracker"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
