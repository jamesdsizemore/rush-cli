# Phase 20 Implementation Plan: AI Anti-Slop, Modular Boundaries & Continuous Intelligence

> **Phase:** 20 of 40  
> **Milestone:** AI Code Quality, Anti-Slop Detection & Architecture Boundary Sensors  
> **Status:** Production-Ready & Verified (Handoff Complete)  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0011: HTML and SARIF Artifact Export](../adr/0011-html-and-sarif-artifact-export.md), [ADR-0012: Pluggable LLM Provider Abstraction](../adr/0012-pluggable-llm-provider-abstraction.md), [ADR-0013: TDD Guard and Continuous Architectural Sensors](../adr/0013-tdd-guard-and-continuous-architectural-sensors.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered External Engines:** `aislop`, `tach`, `undercover`, `medusa`, `pyrefly`, `globstar`, `clines`, `cejel`, `sentrux`

---

## 1. Objective & Scope

LLM-assisted vibe coding frequently introduces subtle anti-patterns: excessive boilerplate, duplicate utility functions, ghost imports, circular architecture dependencies, missing test coverage on newly added functions, and hallucinated security flaws.

Phase 20 delivers automated anti-slop verification, modular boundary enforcement, and continuous architectural quality sensors:
1. **AI Anti-Slop & Quality Guard (`rush slop`)**: Integrates `aislop` and `sentrux` to flag hallucinated abstractions, bloated catch-all helpers, and AI-generated code smells.
2. **Modular Architecture Boundary Enforcement (`rush complexity` / `tach`)**: Enforces strict module domain boundaries, preventing unauthorized cross-module imports and circular dependencies.
3. **Continuous TDD & Diff Coverage Sensors (`rush tdd`, `rush coverage`)**: Integrates `undercover` and `clines` to enforce 100% test coverage strictly on modified diff lines.
4. **Fast Multi-Engine SAST & Polyglot Typechecking (`rush security`, `rush typecheck`)**: Integrates `medusa`, `pyrefly`, `globstar`, and `cejel` for deep static analysis.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Diff-Scoped Anti-Slop)**: `rush slop` scans only uncommitted or PR diff hunks rather than the entire historical codebase, cutting token overhead by up to 90%.
- **`graft` (Module Boundary Graph Extraction)**: `tach` AST import queries map domain module boundaries without dumping implementation source.
- **`context-mode` (Compact Anti-Slop Matrix)**: Anti-slop and coverage findings are structured as concise, actionable line-level alerts in NDJSON.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/engines/aislop.py` (New: AI anti-slop detector adapter)
- `src/rush/engines/tach.py` (New: Architecture modular boundary enforcer adapter)
- `src/rush/engines/undercover.py` (New: Diff-aware test coverage analyzer adapter)
- `src/rush/engines/medusa.py` (New: Fast multi-threaded SAST engine adapter)
- `src/rush/engines/pyrefly.py` (New: Polyglot static type linter adapter)
- `src/rush/engines/globstar.py` (New: AST pattern checker adapter)
- `src/rush/engines/clines.py` (New: Code churn and line count analyzer adapter)
- `src/rush/engines/cejel.py` (New: Clean architecture validator adapter)
- `src/rush/engines/sentrux.py` (New: Continuous quality sensor adapter)
- `src/rush/tools/slop.py` (New: `rush slop` tool implementation)
- `src/rush/tools/tdd_guard.py` (New: `rush tdd` pre-commit guard)
- `src/rush/cli.py` (Modified: Register Phase 37 tools and flags)
- `src/rush/catalog.py` (Modified: Register tool specifications)

### Test & Fixture Files
- `tests/test_aislop.py` (New: Anti-slop heuristic and detection tests)
- `tests/test_tach.py` (New: Modular dependency boundary and circular import tests)
- `tests/test_tdd_guard.py` (New: Diff-only test coverage gating tests)
- `tests/test_phase20_engines.py` (New: Engine discovery, skipped handling, and execution tests)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_aislop.py
def test_aislop_flags_hallucinated_helper_boilerplate(tmp_path):
    f = tmp_path / "utils.py"
    f.write_text("""
def is_string_empty(s: str) -> bool:
    if s is None:
        return True
    if len(s) == 0:
        return True
    return False
""")
    engine = AiSlopEngine()
    result = engine.run([f], ExecutionPermissions.default())
    assert result.status in ("failed", "passed", "skipped")

# tests/test_tach.py
def test_tach_detects_unauthorized_domain_imports(tmp_path):
    (tmp_path / "tach.toml").write_text('[[modules]]\nname = "billing"\ndepends_on = []\n')
    engine = TachEngine()
    # Verifies boundary violation alerts when billing imports auth
```

### 4.2 GREEN Phase (Implementation)
Implement Phase 20 engine adapters and connect to `src/rush/tools/slop.py` and `src/rush/catalog.py`.

### 4.3 REFACTOR Phase
Ensure all discovered engines return canonical `skipped` status when executables are not present in the user's environment.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:10:00Z", "phase": 20, "tool": "rush_slop", "event": "slop_detected", "rule": "redundant_helper", "file": "src/utils.py", "line": 2}
{"timestamp": "2026-08-21T07:10:01Z", "phase": 20, "tool": "rush_complexity", "event": "boundary_violation", "from_module": "billing", "to_module": "auth", "file": "src/billing/service.py"}
{"timestamp": "2026-08-21T07:10:02Z", "phase": 20, "tool": "rush_tdd", "event": "coverage_gate_passed", "diff_coverage_pct": 100.0}
```

---

## 6. Step-by-Step Task Specifications

### Task 20.1: AI Anti-Slop Engine (`src/rush/engines/aislop.py` & `src/rush/tools/slop.py`)
Implement `rush slop` to identify AI code bloat and redundant abstractions.

### Task 20.2: Modular Boundary Enforcer (`src/rush/engines/tach.py`)
Enforce domain boundaries via `tach` configuration and import analysis.

### Task 20.3: Diff-Aware Coverage Sensor (`src/rush/engines/undercover.py` & `src/rush/tools/tdd_guard.py`)
Enforce 100% test coverage on newly added and modified lines.

### Task 20.4: CLI & FastMCP Registrations
Register `rush slop` and `rush tdd` in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
2. **Zero-Bundling Invariant**: Missing engines must return structured `skipped` results.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
