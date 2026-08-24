# MISSION: Architect 30+ Practical Breakthroughs for Rush (Memory, Context & MCP Agent Layers)

You are a Principal Systems Architect and Runtime Engineer specializing in developer experience (DX) and autonomous coding agents (Cursor, Claude Code, Cline, Windsurf, Copilot).

Your mission is to invent, specify, and engineer **30+ original, high-value innovations** for **Rush** (`rush-cli`), an open-source, local, zero-network quality engine and FastMCP server built in Python 3.12 with `uv`.

---

## 💡 CORE PHILOSOPHY: REAL VALUE FOR VIBECODERS & DEVELOPERS

Vibecoders and modern developers want to move fast, stay in the creative flow, and let AI agents build features without babysitting or cleaning up disasters.

Every proposed innovation must solve a **real, painful problem** developers experience when building with AI:
* **The Name & Description MUST be Plain-English and Intuitive**: Use clear, developer-friendly names (e.g., `LoopBreaker`, `GhostPackageShield`, `TokenSaver`, `SmartUndo`, `TeamConflictResolver`). No overly academic jargon in names or conceptual explanations.
* **The Backend MUST be Hardcore & Deterministic**: Under the hood, use rigorous AST parsing, graph algorithms, copy-on-write sandboxes, and pure stdio FastMCP protocols.
* **No Commodity Wrappers**: No wrapping basic linters, raw git commands, or simple regex in buzzwords. Solve actual structural failure modes.

---

## 🏛️ RUNTIME ARCHITECTURE & CONTRACTS

1. **Transport**: stdio-only FastMCP server (`rush mcp serve`). Standard output is strictly reserved for JSON-RPC messages; all internal logs and diagnostics route to stderr via `rush.logging`.
2. **Single Source of Truth**: MCP tools and CLI commands must execute identical underlying logic in `src/rush/` (zero duplication).
3. **Canonical Output Schema**: Every tool invocation returns the standard `ToolResult` dictionary:
   `{ "tool": str, "engine_version": str, "status": "ok"|"warn"|"fail"|"error"|"skipped", "duration_ms": float, "summary": str, "findings": list[dict] }`
4. **Local & Zero-Network**: 100% local execution; zero API keys, zero cloud telemetry, instant execution.
5. **Non-Destructive Defaults**: Never rewrite git history, corrupt working directories, or install git hooks without explicit flags. Isolated executions run in ephemeral worktree sandboxes.

---

## 🎯 6 INNOVATION VECTORS (30+ TOTAL INNOVATIONS REQUIRED)

Generate at least **5 distinct, high-impact innovations per vector**:

### Vector 1: Smart Memory & Assumption Tracking (Epistemic Context)
* *The Vibecoder Pain*: "The AI forgot what it did 5 turns ago and broke an earlier feature while fixing a new one."
* *The Solution*: Causal memory that tracks what the agent has proven vs. assumed, instantly catching when a new change breaks an old assumption.

### Vector 2: Token Saver & Lightning-Fast Context (KV-Cache & Context Packing)
* *The Vibecoder Pain*: "The AI dumps whole files into context, blowing my token limit and costing me a fortune in API bills."
* *The Solution*: Intelligent AST context packing that gives the AI only the exact code boundaries it needs, formatting outputs so prompt caching (Anthropic/OpenAI) hits 95%+.

### Vector 3: Loop Breaker & Safe Experimentation (Anti-Thrashing & Speculative Memory)
* *The Vibecoder Pain*: "The AI gets stuck in a loop trying the same failing fix over and over, or ruins my working directory."
* *The Solution*: Detection of circular edits that forces the agent to pivot to a fresh strategy, plus in-memory experimentation that tests ideas before writing to disk.

### Vector 4: Live Guardrails & Hallucination Defense (FastMCP Interceptors)
* *The Vibecoder Pain*: "The AI hallucinates npm/pip packages that don't exist, or writes code that doesn't match the project architecture."
* *The Solution*: Middleware that inspects proposed code *before* it hits disk, blocking fake imports and illegal cross-folder dependencies with instant fixes.

### Vector 5: One-Shot Super-Tools & Skill Pipelines (Composable Skill DAGs)
* *The Vibecoder Pain*: "The AI takes 6 slow back-and-forth turns to inspect, patch, lint, and test a single function."
* *The Solution*: Combined multi-step pipelines executed locally in one single round-trip, returning complete, verified results instantly.

### Vector 6: Multi-Agent Team Harmony & Auto-Merge (Swarm Meshes & Locking)
* *The Vibecoder Pain*: "When I run multiple agents in parallel, they overwrite each other's work and create nasty git merge conflicts."
* *The Solution*: Function-level locks and 3-way AST semantic merging that cleanly weaves parallel agent edits together without conflict markers.

---

## 🧪 10 REAL-WORLD VIBECODER & DEVELOPER STRESS SCENARIOS

Every proposed innovation must directly solve, mitigate, or protect against one or more of these 10 real-world headaches:

### Scenario 1: The "You Broke What You Built 10 Minutes Ago" Trap
* **The Situation**: A developer asks the AI to build a full authentication flow, then 10 prompts later asks it to add user profile avatars.
* **The Breakdown**: While adding avatars, the AI changes how user IDs are passed, silently breaking the login tokens it built earlier. The developer only finds out when testing the whole app.
* **The Required Fix**: The memory system tracks past working contracts and immediately alerts the agent: *"Wait, this avatar edit breaks the token payload format you locked in during Turn 2."*

### Scenario 2: The Multi-Agent Coffee Run (Parallel Swarm Conflict)
* **The Situation**: A vibecoder dispatches 3 background agents: Agent A adds Stripe billing, Agent B adds Dark Mode, and Agent C fixes API validation—all touching `App.tsx` or `router.py`.
* **The Breakdown**: All 3 finish, but git creates a mess of merge conflicts, broken brackets, and lost code, ruining the user's flow.
* **The Required Fix**: Symbol-level locking and 3-way AST auto-merging that intelligently slots in everyone's functions without touching shared lines or corrupting syntax.

### Scenario 3: The Infinite "Try-Again" Loop (Type / Logic Thrashing)
* **The Situation**: The AI encounters a tricky TypeScript or Python generic type error.
* **The Breakdown**: In Turn 1 it tries Solution A (fails). In Turn 2 it tries Solution B (fails). In Turn 3 it tries Solution A again. It burns $5 in API credits oscillating between the same two broken ideas.
* **The Required Fix**: The runtime computes state hashes across turns, detects the cycle on Turn 3, trips a circuit breaker, and forces the agent to take a completely different architectural approach.

### Scenario 4: The 100K-Token Bill Shock (Context Starvation)
* **The Situation**: A developer works in a growing 50-file repository on a tight context budget.
* **The Breakdown**: Every tool call dumps raw 400-line files with shifting header timestamps, busting prompt cache prefixes and blowing through the token limit in 5 turns.
* **The Required Fix**: Context streaming only sends essential function headers and callers, with static prefix alignment that ensures >95% prompt cache hit rates.

### Scenario 5: The "Phantom Package" Hallucination
* **The Situation**: A vibecoder asks for a fast video converter or cryptography routine.
* **The Breakdown**: The AI writes code importing a library that doesn't exist (`fast-video-utils-py`) or calls a deprecated method that fails at runtime.
* **The Required Fix**: Pre-write interceptor checks the local virtual environment, catches the fake import before it touches disk, and prompts the agent with installed native alternatives.

### Scenario 6: The Heisenbug / Flaky Test Distraction
* **The Situation**: A test suite has a timing-dependent async test that fails 1 out of 20 runs.
* **The Breakdown**: The AI changes a button color, runs tests, and the flaky test fails. The AI panics and spends 15 turns "fixing" the color change because it thinks it caused the failure.
* **The Required Fix**: Flaky test stresser runs jitter permutations, flags the test as pre-existing flakiness, and keeps the AI focused on the actual task.

### Scenario 7: The Panic Undo (Broken Worktree Recovery)
* **The Situation**: The AI attempts a major 4-step refactor of the database models.
* **The Breakdown**: Step 4 fails catastrophically. The AI tries to manually undo its edits, deletes half the developer's uncommitted work, and leaves the repo broken.
* **The Required Fix**: Speculative changes run in an isolated copy-on-write worktree sandbox; if verification fails, it rolls back cleanly with 0 risk to user files.

### Scenario 8: The "Spaghetti Architecture" Creep
* **The Situation**: A developer maintains a clean modular structure (API -> Services -> DB).
* **The Breakdown**: To fix a quick bug, the AI lazily imports the database connection directly into a frontend route component, creating ugly technical debt.
* **The Required Fix**: Architecture boundary guard detects the illegal cross-folder import and guides the AI to use the proper service layer instead.

### Scenario 9: The Swarm Duplicate Work & Wasted Tokens
* **The Situation**: 2 agents working on different endpoints both need to fetch external API data.
* **The Breakdown**: Both agents independently spend 6 turns researching and testing the same third-party rate limits.
* **The Required Fix**: Shared local knowledge federation publishes verified facts and benchmarks to a local pub/sub board so all agents share learnings instantly.

### Scenario 10: The "Works in Tests, Crashes in Prod" Database Drift
* **The Situation**: An agent changes a database model field type (e.g. `user_id` to UUID) and updates test mocks.
* **The Breakdown**: Unit tests pass green because they use mocks, but the developer deploys and the production database crashes because no migration was created.
* **The Required Fix**: Database drift auditor compares ORM models against migration scripts, spots the unmigrated change, and drafts the migration automatically.

---

## 📋 MANDATORY SPECIFICATION SCHEMA (PER INNOVATION)

For each of the 30+ innovations, output a structured block following this exact template:

```markdown
### [INNOVATION-###] <Clear, Intuitive Name>
* **Subsystem / Module**: `src/rush/<subsystem>/<module_name>.py`
* **Target Vector**: [Vector 1 | 2 | 3 | 4 | 5 | 6]
* **Target Stress Scenarios**: [Scenario 1–10]
* **Vibecoder / Developer Value**: 1–2 plain-English sentences explaining why this makes building apps faster, cheaper, or less frustrating.
* **The Agent Breakdown**: The exact multi-turn failure mode this prevents.
* **Hardcore Backend Mechanism**: The underlying Python 3.12 data structures, AST parsing, or graph mechanics that make it work deterministically.
* **Closed-Loop Agent Protocol**:
  1. *Perceive*: The environmental signal the agent receives.
  2. *Plan/Act*: How the agent uses the tool to execute.
  3. *Observe*: How the runtime verifies the outcome on disk.
  4. *Self-Correct*: How the agent automatically recovers if an issue occurs.
* **MCP / CLI Interface Contract**:
  - Tool/Resource/Prompt Name: `rush_<verb>_<noun>`
  - Inputs (with types):
  - Output Schema (canonical `ToolResult`):
* **Deterministic Verification Scenario**: Concrete pytest unit/integration test design with explicit assertions proving the capability works locally.
```

---

Produce all 30+ fully realized, production-grade innovations now.
