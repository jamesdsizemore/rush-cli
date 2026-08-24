# Rush Memory, Context & Tool Implementation Plan
**Document ID:** `rush-unified-agent-intelligence-development-plan-agy`  
**Target:** Rush CLI & FastMCP Server (`rush-cli`)  
**Python Version:** Python 3.12 managed with `uv`  
**Contract:** Local-first, stdio-only MCP server and CLI tool  
**Status:** Implementation Plan (Phases 51–56)  

---

# 1. Decisions & Scope

### 1.1 Core Architecture
* **Role:** Rush provides local repository facts, test verification, session handoffs, and tool guardrails to coding agents and developers.
* **Storage:** Standard SQLite in `.rush/memory/` and YAML files in `.rush/sessions/`. No external servers or cloud dependencies.
* **Transport:** Stdio-only FastMCP server (`rush mcp serve`). Standard output is strictly JSON-RPC. Diagnostics and logs go to stderr via `src/rush/logging.py`.
* **Single Implementation:** CLI commands and MCP endpoints share the exact same underlying Python functions in `src/rush/` returning standard `ToolResult` dictionaries.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  SYSTEM ARCHITECTURE                                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ CODING AGENTS & TOOLS:                                                                 │
│ [Claude Code]            [Cursor]            [DeepSeek-R1]            [CLI / Other]    │
│        │                    │                     │                         │          │
│        └────────────────────┼─────────────────────┴─────────────────────────┘          │
│                             ▼ (FastMCP JSON-RPC over stdio / Click CLI)                │
│ ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ RUSH LOCAL ENGINE (src/rush/)                                                      │ │
│ │  ├─ Tool Supervisor: Catches fake imports, path escapes, and redacts secrets       │ │
│ │  ├─ Fact Memory: Stores test-proven facts; marks them stale when code changes      │ │
│ │  ├─ Context Slicer: Sends only active code; keeps static headers for prompt caches │ │
│ │  ├─ Session Bridge: Saves task state to YAML; formats it for any target model      │ │
│ │  ├─ Test Tracer: Traces lines executed during pytest runs                          │ │
│ │  ├─ Git Sandbox: Runs edits in detached git worktrees; applies only if tests pass  │ │
│ │  └─ File Locks & AST Merge: Prevents concurrent agent edit collisions              │ │
│ └────────────────────────────────────────────────────────────────────────────────────┘ │
│                             ▼                                                          │
│ LOCAL REPOSITORY (.rush/, .git/, .venv/, source files, test runners)                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Priorities & Outcomes
* **No Broken Assumptions:** If an agent changes a function, dependent facts are marked stale so the agent doesn't rely on outdated test results.
* **Safe Edits:** Multi-file refactors run in detached Git worktrees (`git worktree add --detach`) and only merge into the working tree if tests pass.
* **Lower Token Usage:** Only sends the code being edited and direct callers; formats headers to hit prompt cache discounts.
* **Model Portability:** Save a task in one tool (e.g. Claude Code) and resume in another (e.g. Cursor or DeepSeek) without re-explaining the task.
* **Multi-Agent Locks:** Symbol-level locks prevent parallel agents from creating git merge conflicts.

### 1.3 What is Built First vs Rejected
* **Build First:**
  1. Phase 51: Tool supervisor and import validator (`src/rush/mcp/supervisor.py`, `src/rush/mcp/grounding_shield.py`).
  2. Phase 52: Context slicer and prompt cache header aligner (`src/rush/context/entropy_budgeter.py`, `src/rush/token_economy/cache_aligner.py`).
  3. Phase 53: Fact memory ledger and turn cleaner (`src/rush/memory/epistemic_ledger.py`, `src/rush/memory/epistemic_compactor.py`).
* **Rejected:**
  * Docker-based sandboxes (too slow, requires heavy background daemons).
  * External vector/graph databases (breaks zero-dependency local design).
  * Random word-dropping compression (breaks code syntax).
  * UI widgets, visual canvases, and unprompted Git hooks (outside project scope).

---

# 2. Source Documents & Repository Baseline

### 2.1 Resolved Source Reference
`innovations-llm-memory-dev-plan` resolves to `innovations-llm-memory-dev-plan.md` (45 KB, 571 lines).

### 2.2 Verified Current Repository State
* Python 3.12, `hatchling`, `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`, `tiktoken==0.14.0`, `tree-sitter==0.26.0`, `sqlglot==30.17.0`, `ruamel.yaml==0.19.1`.
* `src/rush/tools/base.py`: Canonical `ToolResult` dictionary and `ToolFn` base class.
* `src/rush/mcp.py`: FastMCP stdio server setup.
* `src/rush/session_memory.py`: Multi-turn session turn recorder.
* `src/rush/memory/checkpoint_journal.py`: Session snapshot saver in `.rush/sessions/`.
* `src/rush/memory/invariant_graph.py`: Rule store in `.rush/memory/invariants.json`.
* `src/rush/memory/failure_ledger.py`: SQLite ledger in `.rush/memory/failures.db` tracking failed patches.
* `src/rush/token_economy/ast_skeletonizer.py`: Tree-sitter code folding.
* `src/rush/mcp_mesh/lock_manager.py`: File-based lock daemon in `.rush/mesh_locks.json`.

---

# 3. The 8 Core Features

---

## 3.1 Feature 1: Fact Memory & Staleness Checker
* **Module:** `src/rush/memory/epistemic_ledger.py`
* **User Problem:** Agents forget earlier decisions or break working features during long sessions.
* **Agent Problem:** Agents assume past test results are still valid after editing code.
* **Behavior:**
  * Stores 4 fact types: **Proven** (passed tests), **User Rules** (explicit user constraints), **Conventions** (repo patterns), and **Hypotheses** (unverified ideas).
  * Attaches code hashes to every recorded fact.
  * When a function is edited, all facts linked to that function are automatically marked **Stale**.
* **Commands & Tools:** `rush memory inspect`, `rush memory assert`, `rush_memory_query(symbol="...")`.
* **Token Impact:** Saves tokens by supplying only verified facts relevant to the active file instead of dumping entire chat histories.

---

## 3.2 Feature 2: Pre-Write Tool Supervisor
* **Module:** `src/rush/mcp/supervisor.py` and `src/rush/mcp/grounding_shield.py`
* **User Problem:** Agents try to import packages that are not installed, write outside the repo, or leak credentials.
* **Agent Problem:** Standard MCP servers execute invalid writes without checking preconditions.
* **Behavior:**
  * Before writing: checks that imported libraries exist in `.venv`, checks file locks, and verifies paths stay inside the repo.
  * After writing: redacts sensitive keys (`[REDACTED]`) and appends reminders for dependent files (e.g. updating types after a schema change).
* **Config:** `[mcp.supervisor]` in `rush.toml`.
* **Token Impact:** Catches mistakes locally in milliseconds instead of wasting multi-turn agent debugging cycles.

---

## 3.3 Feature 3: Context Slicer & Cache Locker
* **Module:** `src/rush/context/entropy_budgeter.py` and `src/rush/token_economy/cache_aligner.py`
* **User Problem:** Large context windows increase API costs and slow down model responses.
* **Agent Problem:** Full-file dumps fill context with irrelevant boilerplate.
* **Behavior:**
  * Shows full code only for the target function and its immediate callers; collapses other functions to single-line signatures.
  * Formats headers identically across turns so modern models (Claude, OpenAI, DeepSeek) hit their prompt cache 98%+ of the time.
* **Commands & Tools:** `rush context pack <path> --budget 500`, `rush_context_pack(...)`.
* **Token Impact:** Reduces code payload by 75–90% while keeping full interface signatures intact.

---

## 3.4 Feature 4: History Cleaner (Turn Compactor)
* **Module:** `src/rush/memory/epistemic_compactor.py`
* **User Problem:** Long sessions accumulate thousands of tokens of old chat chatter.
* **Agent Problem:** Large conversation histories cause attention dilution and forgetfulness.
* **Behavior:**
  * Scans previous turns in the session.
  * Compacts old turns into a structured summary: modified files, passing tests, failed approaches, and remaining tasks.
* **Commands:** `rush memory compact`.
* **Token Impact:** Compresses 30,000 tokens of chat history down to ~400 tokens of net verified state.

---

## 3.5 Feature 5: Loop Breaker (Anti-Thrashing)
* **Module:** `src/rush/memory/thrash_breaker.py`
* **User Problem:** Agents get stuck alternating between two failing fixes.
* **Agent Problem:** Agents lack cycle detection and repeat failed patches.
* **Behavior:**
  * Hashes code diffs across turns.
  * If the agent repeats a failed patch or oscillates between two fixes, it trips the breaker and requires a different approach.
* **Token Impact:** Prevents wasted turns and API spend on infinite repair loops.

---

## 3.6 Feature 6: Test Tracer
* **Module:** `src/rush/runtime/runtime_tracer.py` and `src/rush/memory/invariant_miner.py`
* **User Problem:** Code passes syntax checks but fails at runtime due to unstated assumptions.
* **Agent Problem:** Static analysis cannot see real runtime data values or execution paths.
* **Behavior:**
  * Uses Python's built-in `sys.settrace` during `pytest` runs.
  * Records executed lines, branch coverage, and observed argument types.
  * Stores discovered rules (e.g. `user_id is not None`) in the memory store.
* **Commands & Tools:** `rush runtime inspect <symbol>`, `rush_runtime_inspect(...)`.
* **Token Impact:** Gives the agent real runtime facts up front, eliminating trial-and-error debugging.

---

## 3.7 Feature 7: Git Sandbox
* **Module:** `src/rush/core/git_sandbox.py`
* **User Problem:** Large multi-file agent refactors can break uncommitted local code.
* **Agent Problem:** Agents cannot safely test complex changes without risking working tree corruption.
* **Behavior:**
  * Creates an isolated Git worktree in `.rush/sandboxes/<id>` in under 200ms.
  * Runs agent edits and test suites in isolation.
  * Applies the patch to the main repository only if all tests pass; deletes the sandbox cleanly on error.
* **Commands:** `rush sandbox run "<command>"`.
* **Token Impact:** Eliminates recovery turns spent manually reverting bad edits.

---

## 3.8 Feature 8: Universal Session Handoff
* **Module:** `src/rush/memory/session_bridge.py` and `src/rush/memory/dialects/`
* **Core Rule:** **"It is not about the model; it is about the context, history, handoff, and instructions."**
* **User Problem:** Losing all task progress when switching tools (e.g. Claude Code $\rightarrow$ Cursor $\rightarrow$ DeepSeek).
* **Agent Problem:** New agent sessions start from scratch and repeat full repository exploration.
* **Behavior:**
  * Saves active task state to `.rush/sessions/<id>.yaml` (intent, modified files, passing tests, failed approaches, remaining tasks).
  * Automatically formats the briefing for the target model:
    * **Claude:** Formatted with XML tags.
    * **OpenAI:** Formatted with structured JSON schemas.
    * **DeepSeek:** Formatted with step-by-step logic checklists.
    * **Generic/CLI:** Formatted as Markdown.
  * Checks for external file changes before resuming and flags modified files.
* **Commands & Tools:** `rush session save <name>`, `rush session resume <name>`, `rush_session_resume(...)`.
* **Token Impact:** Saves 5,000–15,000 tokens of redundant exploration per resumed session.

---

# 4. File-Level Changes

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         REPOSITORY FILE MAP                              │
├──────────────────────────────────────────────────────────────────────────┤
│ FILES TO MODIFY:                                                         │
│  - src/rush/mcp.py                  (Mount FastMCP supervisor middleware)│
│  - src/rush/catalog.py              (Register new tool specs)            │
│  - src/rush/cli.py                  (Add CLI commands)                   │
│  - src/rush/config.py               (Add [memory] & [mcp.supervisor])   │
│  - src/rush/memory/invariant_graph.py (Bridge rules to fact store)       │
│  - src/rush/memory/checkpoint_journal.py (Upgrade to Session Bridge)     │
│  - src/rush/token_economy/cache_aligner.py (Align headers for caching)   │
│                                                                          │
│ UNCHANGED FILES TO READ:                                                 │
│  - src/rush/tools/base.py           (Canonical ToolResult & ToolFn)      │
│  - src/rush/tools/common.py         (Subprocess runner with redaction)   │
│  - src/rush/logging.py              (Stderr logging)                     │
│                                                                          │
│ NEW FILES TO CREATE:                                                     │
│  - src/rush/mcp/supervisor.py          (FastMCP middleware supervisor)   │
│  - src/rush/mcp/grounding_shield.py    (Import & path safety validator)  │
│  - src/rush/context/entropy_budgeter.py(Context slicer)                  │
│  - src/rush/memory/epistemic_ledger.py (Fact memory store)               │
│  - src/rush/memory/epistemic_compactor.py(Chat history cleaner)          │
│  - src/rush/memory/thrash_breaker.py   (Anti-loop circuit breaker)       │
│  - src/rush/runtime/runtime_tracer.py  (Test execution tracer)           │
│  - src/rush/memory/invariant_miner.py  (Runtime rule miner)              │
│  - src/rush/core/git_sandbox.py        (Git worktree sandbox)            │
│  - src/rush/memory/session_bridge.py   (Session handoff engine)          │
│  - src/rush/memory/dialects/           (Model formatters: XML/JSON/CoT)  │
│  - src/rush/mcp_mesh/symbol_lock_mesh.py(Symbol lock manager)            │
│  - src/rush/mcp_mesh/swarm_arbiter.py  (AST merge resolver)              │
│                                                                          │
│ NEW TEST FILES:                                                          │
│  - tests/test_mcp_supervisor.py                                          │
│  - tests/test_entropy_budgeter.py                                        │
│  - tests/test_epistemic_ledger.py                                        │
│  - tests/test_epistemic_compactor.py                                     │
│  - tests/test_thrash_breaker.py                                          │
│  - tests/test_runtime_tracer.py                                          │
│  - tests/test_git_sandbox.py                                             │
│  - tests/test_session_bridge.py                                          │
│  - tests/test_swarm_arbiter.py                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

# 5. Phased Roadmap (Phases 51–56)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 PHASED ROADMAP                                         │
├──────────┬───────────────────────────────────────────┬─────────────────────────────────┤
│ Phase    │ Deliverables                              │ User Value                      │
├──────────┼───────────────────────────────────────────┼─────────────────────────────────┤
│ Phase 51 │ Tool Supervisor & Pre-Write Shield        │ Blocks fake imports; no leaks   │
├──────────┼───────────────────────────────────────────┼─────────────────────────────────┤
│ Phase 52 │ Context Slicer & Cache Locker             │ 75-90% token reduction; faster  │
├──────────┼───────────────────────────────────────────┼─────────────────────────────────┤
│ Phase 53 │ Fact Memory Ledger & History Cleaner      │ No amnesia; cleans bloated chat │
├──────────┼───────────────────────────────────────────┼─────────────────────────────────┤
│ Phase 54 │ Test Tracer & Rule Miner                  │ Real test execution facts       │
├──────────┼───────────────────────────────────────────┼─────────────────────────────────┤
│ Phase 55 │ Git Sandbox & Universal Session Handoff   │ Safe edits; model switching     │
├──────────┼───────────────────────────────────────────┼─────────────────────────────────┤
│ Phase 56 │ File Locks & AST Merge Arbiter            │ Parallel agents without clashes │
└──────────┴───────────────────────────────────────────┴─────────────────────────────────┘
```

### Phase 51: Tool Supervisor & Pre-Write Shield
* **Deliverables:** `src/rush/mcp/supervisor.py`, `src/rush/mcp/grounding_shield.py`, `tests/test_mcp_supervisor.py`.
* **Details:** Implements FastMCP middleware intercepting `on_call_tool`. Validates imports against `.venv` before disk writes and scrubs secrets from outputs.
* **Success Criteria:** 100% test pass rate on `pytest tests/test_mcp_supervisor.py`.

### Phase 52: Context Slicer & Cache Locker
* **Deliverables:** `src/rush/context/entropy_budgeter.py`, `src/rush/token_economy/cache_aligner.py`, `tests/test_entropy_budgeter.py`.
* **Details:** Folds non-essential function bodies to single-line signatures; keeps static prefix headers identical across calls.
* **Success Criteria:** $>75\%$ reduction in code tokens with 100% valid syntax; identical header bytes across 50 consecutive tool calls.

### Phase 53: Fact Memory Ledger & History Cleaner
* **Deliverables:** `src/rush/memory/epistemic_ledger.py`, `src/rush/memory/epistemic_compactor.py`, `src/rush/memory/thrash_breaker.py`, `tests/test_epistemic_ledger.py`.
* **Details:** SQLite table `epistemic_records` tracking code facts and hashes. Marks dependent facts stale when functions change. Compacts multi-turn history to a 400-token summary.
* **Success Criteria:** Upstream code edits automatically demote dependent facts to `STALE`; loop breaker catches repeated failed patches on Turn 3.

### Phase 54: Test Tracer & Rule Miner
* **Deliverables:** `src/rush/runtime/runtime_tracer.py`, `src/rush/memory/invariant_miner.py`, `tests/test_runtime_tracer.py`.
* **Details:** Hooks `sys.settrace` during pytest runs to record real line coverage and argument types.
* **Success Criteria:** $<30\%$ test run overhead; accurate line execution counts.

### Phase 55: Git Sandbox & Universal Session Handoff
* **Deliverables:** `src/rush/core/git_sandbox.py`, `src/rush/memory/session_bridge.py`, `src/rush/memory/dialects/`, `tests/test_git_sandbox.py`, `tests/test_session_bridge.py`.
* **Details:** Creates detached Git worktrees for isolated agent execution. Serializes task state to `.rush/sessions/<id>.yaml` and transpiles to Claude XML, OpenAI JSON, DeepSeek CoT, or Markdown.
* **Success Criteria:** Worktree spawns in $<200\text{ms}$; session state restores accurately across all 4 model formats.

### Phase 56: File Locks & AST Merge Arbiter
* **Deliverables:** `src/rush/mcp_mesh/symbol_lock_mesh.py`, `src/rush/mcp_mesh/swarm_arbiter.py`, `tests/test_swarm_arbiter.py`.
* **Details:** Symbol-level mutex locks with 30-second TTL; 3-way AST structural merge for non-overlapping code changes.
* **Success Criteria:** Multiple concurrent agent edits merge with zero git conflict markers.

---

# 6. First Pull Request (PR-1)

**Title:** `feat(mcp): implement FastMCP supervisor middleware and pre-write import grounding shield`

**Files:**
* `src/rush/mcp/supervisor.py` (New)
* `src/rush/mcp/grounding_shield.py` (New)
* `src/rush/mcp.py` (Register middleware in `build_server()`)
* `src/rush/config.py` (Add `[mcp.supervisor]`)
* `rush.toml` (Default config)
* `tests/test_mcp_supervisor.py` (Test suite)

**Acceptance Test:**
```python
def test_supervisor_blocks_fake_package():
    shield = GroundingShield()
    bad_code = "import non_existent_package_12345\n\ndef run(): pass"
    result = shield.verify_code_imports(bad_code)
    assert result.is_valid is False
    assert "non_existent_package_12345" in result.missing_packages
```

---

# 7. Open Decisions
1. **Memory Storage:** Use SQLite database in `.rush/memory/` for fast queries; export to YAML for optional git tracking.
2. **Test Tracer:** Use standard Python `sys.settrace` to keep Rush dependency-free.
3. **Lock TTL:** Default to 30-second timeout with automatic renewal while the client process is alive.
