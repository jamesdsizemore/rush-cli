# Rush Memory, Context & Agent Substrate: Practical Execution Plan
**Document ID:** `innovations-memory-features-plan-agy`  
**Target Platform:** Rush CLI & FastMCP Server (`rush-cli`)  
**Python Version:** Python 3.12 managed via `uv`  
**Architecture Contract:** Local-first, stdio-only MCP server and CLI developer tool  
**Status:** Actionable Implementation Plan (Plain-English Features, Solid Technical Backend, Deep Research Grounding)  

---

# 1. Baseline & Repository Facts

### Verified Current Codebase Facts
* **Python 3.12 & Packaging:** Uses `hatchling`, `uv`, standard library `tomllib`, zero Pydantic dependencies.
* **Core Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`, `tiktoken==0.14.0`, `tree-sitter==0.26.0`, `sqlglot==30.17.0`, `ruamel.yaml==0.19.1`.
* **Transport & Output:** Stdio-only FastMCP (`rush mcp serve`). All logs go to stderr via `src/rush/logging.py`. Every tool returns the canonical `ToolResult` shape with `status`, `summary`, and `findings`.
* **Current Baseline Files:**
  * `src/rush/session_memory.py`: Multi-turn session turn recorder.
  * `src/rush/memory/checkpoint_journal.py`: Session snapshot saver in `.rush/sessions/`.
  * `src/rush/memory/invariant_graph.py`: Key-value rules store in `.rush/memory/invariants.json`.
  * `src/rush/memory/failure_ledger.py`: SQLite ledger in `.rush/memory/failures.db` tracking failed patches.
  * `src/rush/memory/merkle_invalidator.py`: Content hash cache in `.rush/cache/merkle.json`.
  * `src/rush/token_economy/ast_skeletonizer.py`: AST function body folding.
  * `src/rush/token_economy/cache_aligner.py`: Output prefix formatter for prompt caching.
  * `src/rush/mcp_mesh/lock_manager.py`: File-based mutex lock daemon in `.rush/mesh_locks.json`.

---

# 2. Deep Research: Analysis of 22+ GitHub Toolkits & Agent Repositories

Cross-referencing the project dataset (`docs/developer/headrushtoolsurls.txt` and `docs/research/claw-github-top3-deep-review.md`) reveals 6 functional categories of external tools that directly shape Rush's architecture:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL REPOSITORY RESEARCH MAPPING                          │
├─────────────────────┬─────────────────────────────────┬────────────────────────────────┤
│ Category            │ Repositories Researched         │ Concrete Takeaway for Rush     │
├─────────────────────┼─────────────────────────────────┼────────────────────────────────┤
│ 1. Memory Hubs      │ buildingjoshbetter/TrueMemory,  │ Calibrated user trait claims & │
│                     │ MemTensor/memmy-agent,          │ 4-layer memory hub without     │
│                     │ akitaonrails/ai-memory          │ cloud dependencies (local db)  │
├─────────────────────┼─────────────────────────────────┼────────────────────────────────┤
│ 2. Codebase Intel   │ Cranot/roam-code,               │ SQLite code-graph indexing to  │
│                     │ repowise-dev/repowise,          │ eliminate the blind "explore"  │
│                     │ theanshsonkar/carto             │ phase for coding agents        │
├─────────────────────┼─────────────────────────────────┼────────────────────────────────┤
│ 3. Safety & Guards  │ asamassekou10/ship-safe,        │ Pre-write safety shield and    │
│                     │ jlekerli-source/ShipGuard,      │ execution boundaries in FastMCP│
│                     │ slowcoder360/vibesafe           │ middleware interceptors        │
├─────────────────────┼─────────────────────────────────┼────────────────────────────────┤
│ 4. Anti-Slop & AST  │ scanaislop/aislop,              │ 50+ deterministic AST checks   │
│    Linting          │ rsionnach/sloppylint,           │ catching hallucinated imports  │
│                     │ tach-org/tach                   │ and layer boundary breaks      │
├─────────────────────┼─────────────────────────────────┼────────────────────────────────┤
│ 5. Outcome & TDD    │ Nimrobo/superdense,             │ Tracking outcome reward loops  │
│    Verification     │ nizos/tdd-guard,                │ and enforcing test-first       │
│                     │ grodowski/undercover            │ verification before promotion  │
├─────────────────────┼─────────────────────────────────┼────────────────────────────────┤
│ 6. Intent & Handoff │ TanStack/intent,                │ Versioned library skills &     │
│                     │ bitloops/bitloops,              │ structured session pods for    │
│                     │ danielgwilson/shiplog           │ seamless cross-model handoff   │
└─────────────────────┴─────────────────────────────────┴────────────────────────────────┘
```

### Detailed Breakdown of Key Projects Researched:

1. **[`buildingjoshbetter/TrueMemory`](https://github.com/buildingjoshbetter/TrueMemory):**
   * *Mechanism:* Local SQLite memory focused on "memory as calibration," recording user traits, decision styles, and rules rather than messy conversational transcripts.
   * *Rush Integration:* Directly informs Rush's `EpistemicLedger` (`USER_INTENT` and `OBSERVED_CONVENTION` record classes).

2. **[`MemTensor/memmy-agent`](https://github.com/MemTensor/memmy-agent):**
   * *Mechanism:* 4-layer memory hub (Trace, Policy, World Model, Skills) sharing persistent context across Claude Code, Cursor, and Codex.
   * *Rush Integration:* Informs Rush's `UniversalSessionBridge`, ensuring that switching tools does not lose accumulated repo knowledge.

3. **[`Cranot/roam-code`](https://github.com/Cranot/roam-code):**
   * *Mechanism:* Deterministic SQLite code graph MCP server that eliminates the token-wasting "explore phase" for coding agents.
   * *Rush Integration:* Powers Rush's `ContextSlimmer` (`src/rush/context/entropy_budgeter.py`), providing exact line ranges and symbol calls without full-file reading.

4. **[`Nimrobo/superdense`](https://github.com/Nimrobo/superdense):**
   * *Mechanism:* Local outcome-loop and reward layer that stores sessions, artifacts, and outcome snapshots so agents "remember what worked."
   * *Rush Integration:* Informs Rush's `EpistemicCompactor` and `FailureLedger` (remembering verified fixes vs failed patches).

5. **[`TanStack/intent`](https://github.com/TanStack/intent):**
   * *Mechanism:* Generates, validates, and ships versioned "Agent Skills" alongside packages to prevent agents from hallucinating outdated APIs.
   * *Rush Integration:* Informs Rush's `GroundingShield` to validate imported package signatures against the active environment.

6. **[`bitloops/bitloops`](https://github.com/bitloops/bitloops):**
   * *Mechanism:* Captures the "why" behind changes (architectural constraints and trade-offs).
   * *Rush Integration:* Stored in `.rush/memory/epistemic.db` as persistent rationale attached to code symbols.

7. **[`nizos/tdd-guard`](https://github.com/nizos/tdd-guard) & [`grodowski/undercover`](https://github.com/grodowski/undercover):**
   * *Mechanism:* Automated TDD enforcement hooks and diff-based code coverage guards that block unverified edits.
   * *Rush Integration:* Powers Rush's post-tool execution gate in `FastMCPSupervisor` to require test proofs before marking tasks complete.

8. **[`scanaislop/aislop`](https://github.com/scanaislop/aislop) & [`rsionnach/sloppylint`](https://github.com/rsionnach/sloppylint):**
   * *Mechanism:* Deterministic AST linter detecting swallowed errors, fake standard library imports, and dead boilerplate scaffolding.
   * *Rush Integration:* Pinned in Rush's `src/rush/engines/sloppylint.py` and pre-write `GroundingShield`.

---

# 3. The 8 Core Practical Features

---

## Feature 1: Smart Memory & Fact Checker
* **Module:** `src/rush/memory/epistemic_ledger.py`
* **Inspired By:** `TrueMemory`, `MemTensor/memmy-agent`, `bitloops`.
* **User Problem:** The agent forgets what was already built or breaks an earlier feature 10 turns later.
* **Agent Problem:** Assumptions are treated as permanent truths even after the underlying code is modified.
* **What It Does:**
  * Stores 4 simple memory types: **Proven Facts** (backed by passing tests), **User Rules** (explicit user instructions), **Project Conventions** (style and patterns), and **Agent Guesses** (untested ideas).
  * Automatically tags facts to specific functions/classes using code hashes.
  * If a function changes, any memory dependent on it is instantly marked **Stale**, telling the agent to re-check it before continuing.
* **User Commands:** `rush memory inspect` (view facts), `rush memory assert` (save a rule), `rush memory invalidate` (force re-check).
* **Agent Tools:** `rush_memory_query(symbol="...")`, `resource://rush/memory/{symbol}`.
* **Token Savings:** Saves up to 80% of tokens by injecting only verified facts for the current file instead of dumping entire chat histories.

---

## Feature 2: Pre-Write Safety Shield
* **Module:** `src/rush/mcp/supervisor.py` and `src/rush/mcp/grounding_shield.py`
* **Inspired By:** `ship-safe`, `ShipGuard`, `vibesafe`, `aislop`.
* **User Problem:** The agent tries to import fake libraries that don't exist, writes files outside the repo, or leaks API keys.
* **Agent Problem:** Standard MCP servers blindly execute whatever the agent sends, wasting time and tokens recovering from obvious mistakes.
* **What It Does:**
  * Runs before any tool write: checks that imported packages actually exist in `.venv`, checks file locks, and verifies paths stay inside the repo.
  * Runs after tool execution: scrubs all secrets (`[REDACTED]`) and adds next-step reminders (e.g. "You edited the DB schema, now update the API model").
* **User Config:** Configured in `rush.toml` under `[mcp.supervisor]`.
* **Token Savings:** Zero-token local offload—catches hallucinations in-process before wasting 5+ conversational turns trying to debug missing packages.

---

## Feature 3: Context Slimmer & Prompt Cache Locker
* **Module:** `src/rush/context/entropy_budgeter.py`
* **Inspired By:** `Cranot/roam-code`, `repowise`, `theanshsonkar/carto`.
* **User Problem:** Token bills get huge, and models slow down significantly as conversations grow.
* **Agent Problem:** Context gets clogged with boilerplate getters/setters, drowning out the actual problem area.
* **What It Does:**
  * **Code Slimming:** Shows full code only for the exact function being edited and its direct callers; collapses boilerplate helpers to single-line signatures.
  * **Cache Pinning:** Keeps tool definitions, project structure, and rules in an unchanging, byte-identical header so modern LLMs (Claude, OpenAI, DeepSeek, Gemini) hit their prompt cache 98%+ of the time.
* **User Commands:** `rush context pack <path> --budget 500`.
* **Agent Tools:** `rush_context_pack(path, budget=500)`.
* **Token Savings:** Cuts context size by 75–90% and gives developers a 90% discount on cached input tokens.

---

## Feature 4: History Cleaner (Turn Compactor)
* **Module:** `src/rush/memory/epistemic_compactor.py`
* **Inspired By:** `Nimrobo/superdense`, `danielgwilson/shiplog`.
* **User Problem:** Long 25-turn debugging sessions get sluggish, expensive, and lose track of the original goal.
* **Agent Problem:** Multi-turn chat history accumulates thousands of tokens of dead exploratory reading and failed attempts.
* **What It Does:**
  * Periodically cleans up past turns in the background.
  * Replaces 20 turns of back-and-forth chatter with a clean 10-line summary: what was built, which tests passed, what failed and shouldn't be tried again, and what remains to be done.
* **User Commands:** `rush memory compact`.
* **Token Savings:** Drops a 30,000-token chat history back down to ~400 tokens without losing a single proven fact.

---

## Feature 5: Loop Breaker (Anti-Thrashing)
* **Module:** `src/rush/memory/thrash_breaker.py`
* **Inspired By:** `getdebug-ai/cli`, `patchrail`.
* **User Problem:** The agent gets stuck in a loop toggling back and forth between two failing fixes.
* **Agent Problem:** Lack of cycle detection causes agents to repeat already-failed patches.
* **What It Does:**
  * Tracks the structural diff of every edit attempt in the session.
  * If the agent tries the same failed fix twice or oscillates between Fix A and Fix B, it trips the circuit breaker and stops the agent.
  * Returns a clear directive: *"You are repeating a failed fix. You must take an entirely different approach."*
* **Token Savings:** Saves $2–$5 and 10+ wasted turns per stuck debugging loop.

---

## Feature 6: Live Test Tracer
* **Module:** `src/rush/runtime/runtime_tracer.py`
* **Inspired By:** `grodowski/undercover`, `nizos/tdd-guard`.
* **User Problem:** The agent writes code that looks right syntactically but fails at runtime because of unwritten assumptions (like expecting a field to never be empty).
* **Agent Problem:** Static code analysis cannot see real runtime values or execution flow.
* **What It Does:**
  * Hooks into local `pytest` runs using standard Python tracing (`sys.settrace`).
  * Shows the agent which lines actually executed and what data types flowed through.
  * Automatically saves discovered rules (e.g. `user_id is never None`) to the memory ledger.
* **User Commands:** `rush runtime inspect <symbol>`.
* **Agent Tools:** `rush_runtime_inspect(symbol="...")`.
* **Token Savings:** Eliminates trial-and-error guessing by providing ground-truth runtime behavior up front.

---

## Feature 7: Safe Playground (Speculative Sandbox)
* **Module:** `src/rush/core/git_sandbox.py`
* **Inspired By:** `agents-shipgate`, `ShipGuard`.
* **User Problem:** Fear of letting an agent perform a big multi-file refactor that messes up uncommitted work.
* **Agent Problem:** Agents cannot safely test multi-step changes without risking repository breakage.
* **What It Does:**
  * Creates an instant, isolated Git worktree sandbox (`.rush/sandboxes/<id>`) in under 200ms.
  * Lets the agent refactor and run tests in complete isolation.
  * If all tests pass, it cleanly applies the changes to the main working tree. If anything fails, it discards the sandbox with zero mess left behind.
* **User Commands:** `rush sandbox run "<command>"`.
* **Token Savings:** Eliminates wasted panic-recovery turns where agents try and fail to manually undo broken edits.

---

## Feature 8: Universal Session Handoff
* **Module:** `src/rush/memory/session_bridge.py` and `src/rush/memory/dialects/`
* **Inspired By:** `MemTensor/memmy-agent`, `TanStack/intent`, `akitaonrails/ai-memory`.
* **Core Principle:** **"It is not about the model; it is about the context, history, handoff, and instructions."**
* **User Problem:** Losing all progress when switching from Claude Code in the terminal to Cursor in the IDE, delegating a hard bug to DeepSeek, or picking up work on Monday morning.
* **Agent Problem:** Every new agent session starts from zero and has to re-explore the whole repo.
* **What It Does:**
  * Saves the active task into a single readable file (`.rush/sessions/<id>.yaml`): original goal, modified files, passing tests, dead ends to avoid, and pending tasks.
  * When a new agent resumes, Rush automatically formats the briefing for that model:
    * **Claude:** Formatted with clear XML tags.
    * **OpenAI (GPT/o-series):** Formatted with strict JSON schema instructions.
    * **DeepSeek:** Formatted with step-by-step logic verification checklists.
    * **Generic/CLI:** Formatted as clean Markdown.
  * If files were changed outside the session, Rush automatically flags what needs re-checking.
* **User Commands:** `rush session save <name>`, `rush session resume <name>`, `rush session handoff --to [claude|cursor|cline|codex]`.
* **Agent Tools:** `rush_session_resume(session_id="active")`, `prompt://rush_handoff_briefing`.
* **Token Savings:** Saves 5,000–15,000 tokens of redundant re-exploration on every resumed session.

---

# 4. File & Repository Map

### Files to Modify
* `src/rush/mcp.py`: Mount supervisor middleware and register new session tools.
* `src/rush/catalog.py`: Register tool definitions and engine specs.
* `src/rush/cli.py`: Expose CLI commands (`rush memory`, `rush session`, `rush sandbox`).
* `src/rush/config.py`: Add `[memory]` and `[mcp.supervisor]` configuration sections.
* `src/rush/memory/invariant_graph.py`: Connect legacy rules to the new Epistemic Ledger.
* `src/rush/memory/checkpoint_journal.py`: Upgrade snapshots to the Universal Session Bridge.
* `src/rush/token_economy/cache_aligner.py`: Align output headers for prompt caching.

### Files to Read (Unchanged)
* `src/rush/tools/base.py`: Canonical `ToolResult` and `ToolFn` classes.
* `src/rush/tools/common.py`: Subprocess runner with secret redaction.
* `src/rush/logging.py`: Stderr logging.
* `src/rush/permissions.py`: Permission checks.

### New Files to Create
* `src/rush/memory/epistemic_ledger.py`: Smart memory and fact store.
* `src/rush/memory/epistemic_compactor.py`: Multi-turn chat cleaner.
* `src/rush/memory/thrash_breaker.py`: Anti-loop circuit breaker.
* `src/rush/memory/session_bridge.py`: Universal session handoff engine.
* `src/rush/memory/dialects/__init__.py`: Dialect transpiler package.
* `src/rush/memory/dialects/anthropic.py`: Claude XML formatter.
* `src/rush/memory/dialects/openai.py`: OpenAI JSON formatter.
* `src/rush/memory/dialects/deepseek.py`: DeepSeek reasoning formatter.
* `src/rush/memory/dialects/markdown.py`: Universal Markdown formatter.
* `src/rush/mcp/supervisor.py`: FastMCP middleware interceptor.
* `src/rush/mcp/grounding_shield.py`: Import and path safety validator.
* `src/rush/context/entropy_budgeter.py`: Code context slimmer.
* `src/rush/runtime/runtime_tracer.py`: Local test execution tracer.
* `src/rush/core/git_sandbox.py`: Git worktree safe playground.
* `src/rush/mcp_mesh/symbol_lock_mesh.py`: Symbol-level mutex locks.
* `src/rush/mcp_mesh/swarm_arbiter.py`: Multi-agent clean merge resolver.

---

# 5. Phased Implementation Plan

```
┌────────────────────────────────────────────────────────────────────────┐
│                        6-PHASE ROADMAP OVERVIEW                        │
├──────────┬──────────────────────────────────────┬──────────────────────┤
│ Phase    │ Focus Area                           │ User-Visible Value   │
├──────────┼──────────────────────────────────────┼──────────────────────┤
│ Phase 51 │ Pre-Write Safety Shield              │ No fake imports      │
│ Phase 52 │ Context Slimmer & Cache Locker       │ 75-90% token savings │
│ Phase 53 │ Smart Memory & History Cleaner       │ No amnesia or loops  │
│ Phase 54 │ Live Test Tracer                     │ Real runtime facts   │
│ Phase 55 │ Safe Playground & Universal Handoff  │ Model switching      │
│ Phase 56 │ Multi-Agent Locks & Clean Merging    │ Parallel swarms      │
└──────────┴──────────────────────────────────────┴──────────────────────┘
```

### Phase 51: Pre-Write Safety Shield
* **Objective:** Catch fake imports, out-of-bounds file writes, and secret leaks before tools execute.
* **Delivers:** `src/rush/mcp/supervisor.py`, `src/rush/mcp/grounding_shield.py`, `tests/test_mcp_supervisor.py`.
* **Success Criteria:** Passing tests for import verification, path safety, and secret scrubbing.

### Phase 52: Context Slimmer & Cache Locker
* **Objective:** Cut token consumption and guarantee prompt cache hits.
* **Delivers:** `src/rush/context/entropy_budgeter.py`, updated `cache_aligner.py`, `tests/test_entropy_budgeter.py`.
* **Success Criteria:** >75% reduction in code tokens with 100% valid syntax; deterministic cache headers.

### Phase 53: Smart Memory & History Cleaner
* **Objective:** Maintain verified facts across turns and clean up bloated chat history.
* **Delivers:** `src/rush/memory/epistemic_ledger.py`, `src/rush/memory/epistemic_compactor.py`, `src/rush/memory/thrash_breaker.py`.
* **Success Criteria:** Automatic fact invalidation when code changes; 30k token history compacted to <500 tokens; loop breaker trips on Turn 3.

### Phase 54: Live Test Tracer
* **Objective:** Bridge static code analysis to real test execution flow.
* **Delivers:** `src/rush/runtime/runtime_tracer.py`, `tests/test_runtime_tracer.py`.
* **Success Criteria:** Execution branch counting with <30% test run overhead.

### Phase 55: Safe Playground & Universal Session Handoff
* **Objective:** Isolated speculative refactors and seamless model switching (Claude $\leftrightarrow$ Cursor $\leftrightarrow$ DeepSeek).
* **Delivers:** `src/rush/core/git_sandbox.py`, `src/rush/memory/session_bridge.py`, `src/rush/memory/dialects/`.
* **Success Criteria:** Worktree spawns in <200ms and cleans up on error; session restores with 100% fidelity across all model formats.

### Phase 56: Multi-Agent Locks & Clean Merging
* **Objective:** Enable 3+ agents to edit code in parallel without conflicts.
* **Delivers:** `src/rush/mcp_mesh/symbol_lock_mesh.py`, `src/rush/mcp_mesh/swarm_arbiter.py`.
* **Success Criteria:** Concurrent function additions merge with zero git conflict markers.

---

# 6. First Recommended Pull Request (PR-1)

**Title:** `feat(mcp): implement FastMCP safety supervisor and pre-write import shield`

**Files Changed:**
* `src/rush/mcp/supervisor.py` (New)
* `src/rush/mcp/grounding_shield.py` (New)
* `src/rush/mcp.py` (Register middleware in `build_server()`)
* `src/rush/config.py` (Add `[mcp.supervisor]`)
* `rush.toml` (Add default config)
* `tests/test_mcp_supervisor.py` (New test suite)

**Smallest Acceptance Test:**
```python
def test_supervisor_blocks_fake_package():
    shield = GroundingShield()
    bad_code = "import completely_fake_package_xyz\n\ndef run(): pass"
    result = shield.verify_code_imports(bad_code)
    assert result.is_valid is False
    assert "completely_fake_package_xyz" in result.missing_packages
```

---

# 7. Open Decisions
1. **Memory Storage:** Use SQLite database in `.rush/memory/` for fast queries, with `rush memory export` to human-readable YAML for git tracking.
2. **Test Tracer:** Use standard Python `sys.settrace` to keep Rush dependency-free.
3. **Lock Lease:** Default to 30-second TTL with automatic renewal while the client process is running.
