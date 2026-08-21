# Phase 31 Implementation Plan: Agent Safety Foundation, Worktree Isolation & Ephemeral Sandboxing

> **Phase:** 31 of 40  
> **Milestone:** Multi-Agent Worktree Farm, Output Sanitization & Security Sandbox  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.3.0  
> **ADR References:** [ADR-0020: Cryptographic HMAC Context Boundary Framing](../adr/0020-cryptographic-hmac-context-boundary-framing.md), [ADR-0021: Ephemeral Git Worktree Sandboxing](../adr/0021-ephemeral-git-worktree-sandboxing.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `tree-sitter==0.24.0`, `tiktoken==0.9.0`

---

## 1. Objective & Scope

Establish the fundamental agent safety, context isolation, and workspace protection layer for autonomous coding agents (Claude Code, Antigravity, DeepSeek-R1) and human vibe-coders. 

When agents run speculative remediation or execute multi-turn diagnostic tasks, they risk polluting the active Git repository, exposing secret keys in tool outputs, or succumbing to indirect prompt injections in repository comments. Phase 31 solves this by delivering:
1. **Ephemeral Git Worktree Farm (`rush git-worktree`)**: Automated creation, branch isolation, and garbage collection of detached worktree workspaces under `.rush/worktrees/`.
2. **Cryptographic Sandbox Framing (`rush sandbox` / `rush_agent_sandbox`)**: Encapsulates tool outputs and findings within HMAC-SHA256 authenticated XML boundaries (`<rush_agent_sandbox hmac="...">`) to neutralize prompt injection vectors.
3. **High-Speed Secret Leak Guard (`rush leak-check`)**: Pre-output entropy scanner that redacts API keys, JWTs, and private keys into `[REDACTED]` before emission.
4. **Token-Aware Finding Paginator (`rush_paginate_findings`)**: Structural AST-aware pagination over FastMCP stdio transport preventing context window overflow.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

To maximize agent efficiency and prevent context-window exhaustion during development and runtime execution:
- **`rtk` (Rust Token Killer / Finding Slicing)**: When emitting findings from scanners, `rush_paginate_findings` limits individual responses to 50 findings or a strict 2,000-token budget. Large stack traces are truncated to relevant top frames.
- **`graft` (Semantic AST Extraction)**: Secret scanner and worktree diff inspectors use Tree-Sitter AST node queries to identify string literals and assignment expressions rather than analyzing entire files as raw text.
- **`context-mode` (Compact Diagnostic Representation)**: Diagnostic outputs and XML sandbox envelopes use compact JSON serialization and strip superfluous whitespace.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/git/worktree.py` (New: Worktree manager, isolation lifecycle, GC)
- `src/rush/agent_sandbox.py` (New: HMAC-SHA256 signature generator and XML envelope builder)
- `src/rush/tools/leak_check.py` (New: Secret leak regex and Shannon entropy scanner)
- `src/rush/agent_transport.py` (New: FastMCP token-aware pagination and result chunker)
- `src/rush/cli.py` (Modified: Register `rush git-worktree`, `rush sandbox`, `rush leak-check`)
- `src/rush/mcp_server.py` (Modified: Register `rush_agent_sandbox`, `rush_paginate_findings`, `rush_secret_check`)
- `src/rush/catalog.py` (Modified: Tool specifications for catalog parity)

### Test & Fixture Files
- `tests/test_agent_worktree.py` (New: Worktree creation, concurrency, isolation, teardown)
- `tests/test_agent_sandbox.py` (New: HMAC generation, tamper resistance, prompt injection resistance)
- `tests/test_leak_check.py` (New: Secret detection, Shannon entropy thresholds, redaction)
- `tests/test_agent_transport.py` (New: FastMCP pagination, token budgeting, chunk reassembly)
- `tests/fixtures/secrets/leaked_tokens.env` (New: Test fixture with synthetic credentials)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

Write unit and integration tests in `tests/` before implementation:

```python
# tests/test_agent_sandbox.py
def test_sandbox_envelope_hmac_validity():
    payload = "Tool diagnostic finding: clean"
    envelope = wrap_in_sandbox(payload, secret_key="rush-test-key")
    assert envelope.startswith('<rush_agent_sandbox hmac="')
    assert verify_sandbox_envelope(envelope, secret_key="rush-test-key") is True

def test_sandbox_envelope_tamper_detection():
    payload = "Tool diagnostic finding: clean"
    envelope = wrap_in_sandbox(payload, secret_key="rush-test-key")
    tampered = envelope.replace("clean", "malicious instruction")
    assert verify_sandbox_envelope(tampered, secret_key="rush-test-key") is False

# tests/test_agent_worktree.py
def test_create_and_destroy_worktree(tmp_path):
    repo = init_git_repo(tmp_path)
    manager = WorktreeManager(repo_root=tmp_path)
    wt_info = manager.create_worktree(task_id="agent-task-001")
    assert Path(wt_info["path"]).exists()
    assert manager.is_worktree_clean(wt_info["path"]) is True
    manager.cleanup_worktree("agent-task-001")
    assert not Path(wt_info["path"]).exists()

# tests/test_leak_check.py
def test_secret_scanner_redacts_keys():
    text = 'export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
    result = scan_and_redact_secrets(text)
    assert "wJalrXUtnFEMI" not in result.sanitized_text
    assert "[REDACTED]" in result.sanitized_text
    assert len(result.findings) == 1
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/git/worktree.py`, `src/rush/agent_sandbox.py`, `src/rush/tools/leak_check.py`, and `src/rush/agent_transport.py`. Ensure all 571+ existing tests continue to pass.

### 4.3 REFACTOR Phase
Verify subprocess commands use `stdin=DEVNULL`, `shell=False`, and that worktree teardown is guarded with `try...finally` context managers to prevent orphan directory leaks.

---

## 5. Structured Error Logging & Diagnostics Contract

All logging must be emitted exclusively to `sys.stderr` in structured NDJSON:

```json
{"timestamp": "2026-08-21T07:15:00Z", "phase": 31, "tool": "rush_git_worktree", "event": "worktree_created", "task_id": "agent-task-001", "path": ".rush/worktrees/agent-task-001"}
{"timestamp": "2026-08-21T07:15:01Z", "phase": 31, "tool": "rush_leak_check", "event": "secret_redacted", "rule_id": "aws_secret_key", "entropy": 4.82}
{"timestamp": "2026-08-21T07:15:02Z", "phase": 31, "tool": "rush_agent_sandbox", "event": "hmac_verified", "status": "valid"}
```

---

## 6. Step-by-Step Task Specifications

### Task 31.1: Ephemeral Worktree Manager (`src/rush/git/worktree.py`)
Implement the `WorktreeManager` class supporting atomic creation, health checking, and garbage collection:
```python
from __future__ import annotations
from pathlib import Path
from rush.utils import run_subprocess

class WorktreeManager:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.worktree_dir = self.repo_root / ".rush" / "worktrees"

    def create_worktree(self, task_id: str, base_ref: str = "HEAD") -> dict[str, str]:
        """Create a detached git worktree for isolated agent execution."""
        ...

    def cleanup_worktree(self, task_id: str, force: bool = False) -> bool:
        """Remove worktree and prune administrative metadata."""
        ...

    def list_active_worktrees(self) -> list[dict[str, str]]:
        """List active worktrees with creation timestamps and disk usage."""
        ...

    def prune_stale_worktrees(self, max_age_seconds: int = 3600) -> int:
        """Garbage collect abandoned worktree directories."""
        ...
```

### Task 31.2: Cryptographic Sandbox Envelope (`src/rush/agent_sandbox.py`)
Implement HMAC-SHA256 signed XML boundary wrappers:
```python
from __future__ import annotations
import hmac
import hashlib

def wrap_in_sandbox(content: str, secret_key: str) -> str:
    """Wrap content in HMAC-signed XML boundary."""
    signature = hmac.new(secret_key.encode("utf-8"), content.encode("utf-8"), hashlib.sha256).hexdigest()
    return f'<rush_agent_sandbox hmac="{signature}">\n{content}\n</rush_agent_sandbox>'

def verify_sandbox_envelope(envelope_text: str, secret_key: str) -> bool:
    """Verify HMAC integrity of sandboxed payload."""
    ...
```

### Task 31.3: Secret Scanner & Redaction (`src/rush/tools/leak_check.py`)
Implement regex and Shannon entropy calculation:
```python
from __future__ import annotations
from rush.tools.base import ToolResult, Finding

def calculate_shannon_entropy(data: str) -> float: ...

def scan_and_redact_secrets(text: str) -> tuple[str, list[Finding]]:
    """Detect and redact API keys, private keys, and high-entropy strings."""
    ...
```

### Task 31.4: Token-Aware FastMCP Pagination (`src/rush/agent_transport.py`)
Implement `rush_paginate_findings` to chunk large tool result payloads into bounded token frames.

### Task 31.5: CLI & FastMCP Registrations
Expose `rush git-worktree`, `rush sandbox`, and `rush leak-check` via `src/rush/cli.py` and register corresponding FastMCP endpoints in `src/rush/mcp_server.py`.

---

## 7. Semantic Drift Review & Verification Gate

1. **Subprocess Isolation**: All Git invocations must use `run_subprocess` with `stdin=DEVNULL`.
2. **Zero Hardcoded Secrets**: Ensure all test fixtures use explicit mock tokens (`EXAMPLEKEY`).
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and `python scripts/sync_docs.py --check`.
4. **Test Pass**: Ensure 100% test pass across all new and existing test files.
