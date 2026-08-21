# Phase 38 Implementation Plan: Agent Governance, Repository Onboarding & Skill Ecosystem

> **Phase:** 38 of 40  
> **Milestone:** Agent Governance, Repository Scaffolding & Skill Ecosystem  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.10.0  
> **ADR References:** [ADR-0020: Cryptographic HMAC Context Boundary Framing](../adr/0020-cryptographic-hmac-context-boundary-framing.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, Python 3.12 Standard Library (`pathlib`, `re`, `tomllib`, `json`)  
> **Embedded Static Datasets:** `src/rush/data/spdx_licenses.json` (120 KB)  
> **Adopted Standards:** Open Knowledge Format (OKF v0.2), HTML Comment Boundary Sync (`<!-- RUSH_START -->`)

---

## 1. Objective & Scope

Autonomous coding agents (Claude Code, Cursor, Antigravity) rely heavily on instructions defined in `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, and specialized skill directories (`.rush/skills/`, `.gemini/skills/`). However, ambiguous prompts lead to hallucinations, malformed YAML frontmatter breaks agent execution, and destructive repository scaffolders overwrite user custom configurations.

Phase 38 solves agent governance and seamless repository onboarding by delivering:
1. **System Prompt & Context Rule Auditor (`rush prompt-audit`)**: Lints instructions against 21 known anti-patterns (negative constraints, vague directives, circular logic).
2. **Agent Skill & Knowledge Validator (`rush skill-audit`)**: Validates agent skill schemas, parameters, and Markdown frontmatter against the Open Knowledge Format (OKF v0.2) specification.
3. **Non-Destructive Repository Scaffolder (`rush scaffold` / `rush onboard`)**: Dual-mode agentic scaffolder supporting **Greenfield Mode** (empty folder bootstrapping) and **Brownfield Mode** (strictly appending within `<!-- RUSH_START --> ... <!-- RUSH_END -->` comment blocks without overwriting user rules).
4. **SPDX License & Supply Chain Compliance Gate (`rush license-audit`)**: Offline validation of repository dependencies against the SPDX 3.23 matrix to block viral copyleft contamination (GPLv3 in commercial projects).

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Rule Linting Summaries)**: Summarizes prompt audit findings into actionable bullet points with line references rather than echoing the entire prompt file.
- **`graft` (Targeted Section Slicing)**: Parses Markdown AST headers to extract and validate individual prompt sections independently.
- **`context-mode` (Bounded Boundary Injection)**: Scaffolders operate exclusively on clearly delineated token-bounded HTML comment markers.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/tools/prompt_audit.py` (New: System prompt and rule hygiene linter)
- `src/rush/skills/auditor.py` (New: OKF v0.2 agent skill and tool definition validator)
- `src/rush/scaffolder.py` (New: Dual-mode non-destructive repository onboarding engine)
- `src/rush/tools/license_audit.py` (New: SPDX 3.23 license compatibility verifier)
- `src/rush/data/spdx_licenses.json` (New: Offline SPDX license matrix)
- `src/rush/cli.py` (Modified: Register `rush prompt-audit`, `rush skill-audit`, `rush scaffold`, `rush license-audit`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Catalog specifications)

### Test & Fixture Files
- `tests/test_prompt_audit.py` (New: Prompt ambiguity rules, negative constraint detection)
- `tests/test_skill_auditor.py` (New: OKF v0.2 schema validation, YAML frontmatter parsing)
- `tests/test_scaffolder.py` (New: Greenfield bootstrapping vs Brownfield non-destructive append tests)
- `tests/test_license_audit.py` (New: License classification: permissive, weak-copyleft, viral)
- `tests/fixtures/skills/sample_skill/SKILL.md` (New: Test skill fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_scaffolder.py
def test_brownfield_scaffold_preserves_user_rules(tmp_path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Custom Project\n\nAlways use tabs.")
    
    scaffold_repository(repo_root=tmp_path, target="claude")
    content = claude_md.read_text()
    
    assert "Always use tabs." in content
    assert "<!-- RUSH_START -->" in content
    assert "<!-- RUSH_END -->" in content
    assert content.startswith("# My Custom Project")

def test_greenfield_scaffold_bootstraps_empty_repo(tmp_path):
    empty_dir = tmp_path / "empty_project"
    empty_dir.mkdir()
    
    res = scaffold_repository(repo_root=empty_dir, target="all")
    assert (empty_dir / "README.md").exists()
    assert (empty_dir / ".gitignore").exists()
    assert (empty_dir / "rush.toml").exists()
    assert (empty_dir / "CLAUDE.md").exists()
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/tools/prompt_audit.py`, `src/rush/skills/auditor.py`, `src/rush/scaffolder.py`, and `src/rush/tools/license_audit.py`.

### 4.3 REFACTOR Phase
Ensure comment block boundary injection handles existing unclosed markers safely and prevents duplicate block generation.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:50:00Z", "phase": 38, "tool": "rush_scaffold", "event": "brownfield_appended", "file": "CLAUDE.md", "markers": "<!-- RUSH_START -->"}
{"timestamp": "2026-08-21T07:50:01Z", "phase": 38, "tool": "rush_prompt_audit", "event": "vague_instruction_flagged", "file": "AGENTS.md", "line": 14}
{"timestamp": "2026-08-21T07:50:02Z", "phase": 38, "tool": "rush_license_audit", "event": "copyleft_violation", "package": "gpl-lib", "license": "GPL-3.0-only"}
```

---

## 6. Step-by-Step Task Specifications

### Task 38.1: System Prompt Hygiene Scanner (`src/rush/tools/prompt_audit.py`)
```python
from __future__ import annotations
from pathlib import Path
from rush.tools.base import ToolResult, Finding

def audit_system_prompts(repo_root: Path) -> ToolResult:
    """Audit CLAUDE.md, AGENTS.md, .cursorrules against 21 prompt hygiene rules."""
    ...
```

### Task 38.2: Agent Skill Validator (OKF v0.2) (`src/rush/skills/auditor.py`)
Verify `SKILL.md` YAML frontmatter, input schema validation, tool descriptions, and permission scopes.

### Task 38.3: Dual-Mode Non-Destructive Scaffolder (`src/rush/scaffolder.py`)
Implement Greenfield folder bootstrapping and Brownfield bounded HTML comment appending (`<!-- RUSH_START --> ... <!-- RUSH_END -->`).

### Task 38.4: SPDX 3.23 License Compliance Gate (`src/rush/tools/license_audit.py`)
Match dependency manifests against `src/rush/data/spdx_licenses.json` and flag viral copyleft licenses in commercial projects.

### Task 38.5: CLI & FastMCP Registrations
Register all 4 tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Non-Destructive Invariant**: Existing user configuration outside `<!-- RUSH_START -->` must NEVER be modified or truncated.
2. **Offline SPDX Validation**: Zero network requests; all license metadata is evaluated offline.
3. **Doc Parity**: Synchronize and verify all `/docs` files.
