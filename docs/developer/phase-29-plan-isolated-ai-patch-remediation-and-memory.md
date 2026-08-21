# Phase 29 Implementation Plan: Isolated AI Patch Remediation & Context Memory

> **Phase:** 29 of 40  
> **Milestone:** Closed-Loop AI Agent Remediation & Multi-Turn Session Memory  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0018: Closed-Loop AI Agent Patch Remediation and Session Memory](../adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md), [ADR-0020: Cryptographic HMAC Context Boundary Framing](../adr/0020-cryptographic-hmac-context-boundary-framing.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Autonomous coding agents (Claude Code, Antigravity, DeepSeek) waste multiple turns attempting to guess how to fix scanner errors. Phase 29 provides single-turn issue resolution by enriching `ToolFinding` with unified diff patches, providing dedicated FastMCP tools (`rush_get_patch`, `rush_apply_fix`, `rush_session_context`), and maintaining a sanitized multi-turn session memory ledger (`.rush/session_memory.json`).

To prevent workspace corruption and prompt injection, patch application strictly enforces path confinement (blocking writes to `.git/`, `.rush/cache.db`, `.env`), and session memory is framed in HMAC-signed XML boundary tags.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Single-Turn Patch Delivery)**: By including verified, syntax-valid diff patches directly inside tool findings (`rush_get_patch`), agents can apply fixes in 1 turn without generating their own speculative code.
- **`graft` (Hunk Slicing)**: Patches are scoped to modified AST nodes rather than rewriting entire files.
- **`context-mode` (Bounded XML Framing)**: Session memory queries (`rush_session_context`) return compact XML records capped at 1,024 characters per summary.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/session_memory.py` (New: Sanitized session memory manager with XML boundary framing)
- `src/rush/patch_generator.py` (New: Deterministic diff patch generator for autofixable findings)
- `src/rush/tools/base.py` (Modified: Add `patch` and `suggested_fix` fields to `ToolFinding`)
- `src/rush/mcp_server.py` (Modified: Register FastMCP tools `rush_get_patch`, `rush_apply_fix`, `rush_session_context`)
- `src/rush/cli.py` (Modified: Add CLI flags for session memory inspection)
- `src/rush/catalog.py` (Modified: Register remediation capabilities)

### Test & Fixture Files
- `tests/test_session_memory.py` (New: Session persistence, sanitization, and rotation tests)
- `tests/test_patch_generator.py` (New: Unified diff generation tests)
- `tests/test_mcp_patch_tools.py` (New: FastMCP tool invocations and traversal blocking tests)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_mcp_patch_tools.py
def test_apply_fix_path_traversal_blocked(tmp_path):
    malicious_patch = "--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n-root\n+hacked\n"
    res = apply_unified_patch(malicious_patch, repo_root=tmp_path)
    assert res.success is False
    assert "outside repository boundary" in res.error

def test_apply_fix_git_dir_protection(tmp_path):
    git_patch = "--- a/.git/config\n+++ b/.git/config\n@@ -1 +1 @@\n-old\n+new\n"
    res = apply_unified_patch(git_patch, repo_root=tmp_path)
    assert res.success is False
    assert "Protected system path" in res.error
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/session_memory.py`, `src/rush/patch_generator.py`, and register FastMCP endpoints.

### 4.3 REFACTOR Phase
Ensure patch application rolls back automatically if post-patch syntax validation fails.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:55:00Z", "phase": 29, "tool": "rush_apply_fix", "event": "patch_applied", "target_file": "src/utils.py", "lines_modified": 4}
{"timestamp": "2026-08-21T07:55:01Z", "phase": 29, "tool": "rush_apply_fix", "event": "security_violation", "target": ".git/config", "reason": "protected_path"}
{"timestamp": "2026-08-21T07:55:02Z", "phase": 29, "tool": "rush_session_memory", "event": "turn_recorded", "tool": "lint", "findings": 2}
```

---

## 6. Step-by-Step Task Specifications

### Task 29.1: Sanitized Session Memory (`src/rush/session_memory.py`)
```python
from __future__ import annotations
import json
import xml.sax.saxutils as saxutils
from dataclasses import dataclass
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
        """Record sanitized turn metrics in session ledger."""
        ...
        
    def format_for_mcp(self) -> str:
        """Format session history inside XML boundary tags."""
        ...
```

### Task 29.2: FastMCP Remediation Tools (`src/rush/mcp_server.py`)
Register `rush_get_patch`, `rush_apply_fix`, and `rush_session_context`.

### Task 29.3: CLI & FastMCP Registrations
Expose session inspection commands in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Protected Paths**: Never allow writing to `.git/`, `.rush/cache.db`, `.env`.
2. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
