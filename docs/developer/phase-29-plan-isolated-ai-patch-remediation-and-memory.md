# Phase 29 Implementation Plan: Isolated AI Patch Remediation & Context Memory

> **Phase:** 29 of 30  
> **Milestone:** Closed-Loop AI Agent Remediation & Multi-Turn Session Memory  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0018: Closed-Loop AI Agent Patch Remediation and Session Memory](../adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md)

---

## 1. Objective & Scope

Equip AI coding agents with single-turn issue resolution by enriching `ToolFinding` with unified diff patches, providing dedicated FastMCP tools (`rush_get_patch`, `rush_apply_fix`, `rush_session_context`), and maintaining a sanitized multi-turn session memory ledger (`.rush/session_memory.json`).

Incorporate **Control 7 (Patch Confinement & Context Framing)** to prevent patch traversal outside the workspace, protect sensitive repository paths (`.git/`, `.rush/cache.db`, `.env`), and frame session memory in strict XML boundary tags to prevent prompt injection and context hijacking.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/session_memory.py` (New: Sanitized session memory manager)
- `src/rush/patch_generator.py` (New: Deterministic diff generator)
- `src/rush/tools/base.py` (Modified: Add `patch` and `suggested_fix` fields to `ToolFinding`)
- `src/rush/mcp.py` (Modified: Register FastMCP tools `rush_get_patch`, `rush_apply_fix`, `rush_session_context`)
- `src/rush/logging.py` (Modified: `[rush-agent:LEVEL]` and `[rush-memory:LEVEL]`)

### Test & Fixture Files
- `tests/test_session_memory.py` (New: Session persistence, sanitization, and rotation tests)
- `tests/test_patch_generator.py` (New: AST/regex unified diff generation tests)
- `tests/test_mcp_patch_tools.py` (New: FastMCP tool invocations and traversal blocking tests)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_session_memory.py` and `tests/test_mcp_patch_tools.py`:
1. `test_apply_fix_path_traversal_blocked()`: Asserts patches targeting `../../sensitive_file` fail with a security error.
2. `test_apply_fix_git_dir_protection()`: Asserts patches attempting to modify `.git/config` or `.git/hooks` are rejected.
3. `test_session_memory_injection_sanitization()`: Asserts prompt injection payloads in findings are sanitized and escaped.
4. `test_mcp_memory_xml_framing()`: Asserts FastMCP returns records safely encapsulated in XML boundary tags.

### 3.2 GREEN Phase
Implement `session_memory.py`, `patch_generator.py`, and register FastMCP tools.

### 3.3 REFACTOR Phase
Ensure patch application is atomic and rolls back automatically if syntax validation fails.

---

## 4. Step-by-Step Implementation Tasks

### Task 29.1: Sanitized Session Memory (`src/rush/session_memory.py`)
```python
from __future__ import annotations
import json
import xml.sax.saxutils as saxutils
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class SessionRecord:
    timestamp: str
    tool_name: str
    finding_count: int
    fixes_applied: int
    summary: str

class SessionMemoryManager:
    def __init__(self, memory_file: Path) -> None:
        self.memory_file = memory_file
        
    def record_turn(self, tool_name: str, findings: int, fixes: int, summary: str) -> None:
        # Sanitize summary and store
        ...
        
    def format_for_mcp(self) -> str:
        # Format as strict XML frames
        records = self.load_records()
        out = ["<rush_session_memory>"]
        for r in records:
            clean_summary = saxutils.escape(r.summary[:1024])
            out.append(f'  <record tool="{r.tool_name}" findings="{r.finding_count}" fixes="{r.fixes_applied}">{clean_summary}</record>')
        out.append("</rush_session_memory>")
        return "\n".join(out)
```

### Task 29.2: FastMCP Remediation Tools (`src/rush/mcp.py`)
Register `rush_get_patch`, `rush_apply_fix`, and `rush_session_context`:
```python
@mcp.tool(name="rush_apply_fix", description="Safely apply a unified diff patch proposed by Rush.")
def rush_apply_fix(patch: str) -> str:
    # 1. Parse diff headers
    # 2. Assert targets are relative to repo_root and not in protected paths
    # 3. Apply patch atomically
    ...
```

### Task 29.3: Stderr Diagnostics & Logging
- `[rush-agent:INFO] FastMCP tool invoked: {tool_name}`
- `[rush-agent:SECURITY_VIOLATION] Refused patch targeting protected path: {target}`
- `[rush-memory:INFO] Recorded session turn for {tool_name}`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/MCP_INTEGRATION.md` & `docs/integrations/cursor-claude-setup.md` (Document new FastMCP remediation tools).
2. `docs/API_REFERENCE.md` & `docs/reference/api-reference.md` (Document `rush_apply_fix` and `rush_session_context`).
3. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run patch remediation and memory unit tests
.venv/Scripts/python.exe -m pytest tests/test_session_memory.py tests/test_mcp_patch_tools.py -v

# 2. Full test suite verification
.venv/Scripts/python.exe -m pytest tests/ -q

# 3. Documentation parity verification
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 4. Lint and format
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 5. Graft code graph check
graft --dir .hermes/graft build . && graft --dir .hermes/graft check .
```
