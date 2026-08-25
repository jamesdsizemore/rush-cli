# Agentic Rush: The AI Agent Copilot & Quality Control Engine

> **P3/P4 recovery:** When context cannot fit its budget, Rush stores a redacted omission under a stable local CCR handle so another agent can recover it deliberately. Coordination recovery also exposes up to three redacted mined mistake records as historical evidence only; neither recovery form executes a prior instruction, patch, or retry.

> **Phase 5 provider boundary:** `rush session resume` supports user-owned `claude_code`, `codex_cli`, `antigravity_cli`, and the fixed-loopback `omniroute_api` route, with explicit `--allow-network`. It projects only current goal, open work, and freshness; historical instructions, transcripts, failed patches, credentials, and provider output are excluded. Z.AI is deferred without invocation. 9Router remains tracked pending its explicit API-key and user-selected-model route contract.

> **Phase 1 continuity:** `rush session` and MCP `rush_continuity` share one local checkpoint contract. Save is denied unless the caller explicitly grants cache-write permission; list and restore are read-only and return canonical `ToolResult` data.

> **Phase 2 handoff:** save may carry a redacted current goal, open-work frontier, dependency hashes, and a failure receipt. Historic instructions are recorded only as quarantined `historical_evidence`, never as current authority.

> **Phase 4 coordination:** continuity reports held or stale ownership, merge-preview conflicts, and replay/failure receipts as non-executable evidence. It never releases a lock, merges source, or retries a failed patch.

Welcome to **Agentic Rush**. 

Whether you are building with **Cursor, Claude Code, Cline, Windsurf, Roo Code, GitHub Copilot Workspace**, or custom autonomous agent frameworks, you've likely encountered the reality of AI coding assistants: they are incredibly fast, but without guardrails, they can introduce subtle bugs, hallucinatory code ("AI slop"), destructive commands, out-of-sync types, and bloated token context costs.

**Agentic Rush is the safety harness, intelligence engine, and quality accelerator for autonomous AI coding agents and the humans who steer them.**

---

## Why Agentic Rush?

When AI agents write code, they operate fundamentally differently than human developers:
1. **Speed vs. Precision**: Agents can write 500 lines of code in 5 seconds, but may skip edge cases, leave empty stubs, or forget to write tests.
2. **Context Window Limits**: Passing an entire repository into an LLM costs money and causes "needle-in-a-haystack" amnesia.
3. **Safety & Execution Risks**: An unsupervised agent might run destructive commands (`rm -rf`, `git reset --hard`, accidental git history rewrites) or leak API keys.
4. **Multi-Model Disagreements**: Different LLMs catch different bugs and hallucinate different false positives.

Agentic Rush provides a complete, local, zero-network-dependency suite of tools designed specifically to solve these challenges.

---

## Visual Overview: The Agentic Workflow Loop

```mermaid
sequenceDiagram
    autonumber
    participant Human as Developer
    participant Agent as AI Coding Agent (Cursor/Claude/Cline)
    participant Rush as Rush Agentic Engine
    participant Repo as Codebase Repository

    Human->>Agent: Prompt: "Refactor auth and add rate limiting"
    Agent->>Rush: rush codegraph slice "AuthService"
    Rush-->>Agent: Returns 40-line verbatim symbol slice (saving 95% tokens)
    Agent->>Rush: rush safety check-cmd "git clean -fdx"
    Rush-->>Agent: [ALLOWED] Command validated against safety policy
    Agent->>Rush: Propose diff patch
    Rush->>Rush: Apply in isolated git worktree sandbox
    Rush->>Rush: Run syntax checks, linters & tests
    alt Regression or Lint Error
        Rush-->>Agent: Patch failed verification; returned detailed error trace
        Agent->>Agent: Self-corrects patch based on Rush feedback
    else Verification 100% Green
        Rush->>Repo: Atomically promote verified patch
        Rush->>Rush: Record turn in session memory ledger
        Rush-->>Human: Feature complete with verified tests and 0 lint errors
    end
```

---

## The 10 Pillars of Agentic Rush

Explore the dedicated in-depth guides for every agentic subsystem:

| Subsystem | What it Does | How it Helps You & Your Agents | Guide |
|---|---|---|---|
| **AI Safety & Sandboxing** | Destructive command interception & filesystem containment | Prevents agents from executing catastrophic shell commands or modifying files outside repo bounds. | [Read Guide](agentic-rush/ai-safety-and-sandboxing.md) |
| **Patch Remediation & Memory** | Closed-loop patch testing & multi-turn memory | Tests agent diffs in isolated worktree sandboxes with automatic rollbacks and persistent turn memory. | [Read Guide](agentic-rush/patch-remediation-and-memory.md) |
| **Token Economy & Context** | BPE token budgeting & AST outline compression | Shrinks code prompts by 70–90%, dramatically reducing LLM costs and eliminating context window amnesia. | [Read Guide](agentic-rush/token-economy-and-context.md) |
| **CodeGraph & Symbol Slicing** | Code Property Graph & verbatim symbol extraction | Lets agents query exact function implementations and call paths in sub-milliseconds without reading full files. | [Read Guide](agentic-rush/codegraph-and-semantic-slicing.md) |
| **Codebase Hygiene & AST Merges** | Dead code scanning & 3-way AST merge solver | Cleans up unreferenced code and automatically resolves merge conflicts when multiple agents edit in parallel. | [Read Guide](agentic-rush/codebase-hygiene-and-ast-merging.md) |
| **Governance & Multi-IDE Rules** | Canonical `AGENTS.md` compilation | Compiles one single rules file into `.cursorrules`, `.clinerules`, and Windsurf rules so all agents follow team standards. | [Read Guide](agentic-rush/governance-and-multi-ide-rules.md) |
| **Pre-Commit Intelligence** | Sub-second staged AST linting & Trojan Source detection | Catches invisible Unicode exploits, merge conflict markers, and syntax errors before commits hit git history. | [Read Guide](agentic-rush/pre-commit-intelligence.md) |
| **Multi-Model Consensus & Score** | Cross-model agreement voting & 6-pillar scorecard | Reconciles reviews from Claude, GPT-4o, and Gemini while computing a deterministic 0–100% repo health grade. | [Read Guide](agentic-rush/multi-model-consensus-and-scoring.md) |
| **Plugins & Agent Skills** | Trust-gated tools & exportable agent skill definitions | Extends agent capabilities with custom scripts secured by cryptographic SHA-256 trust verification. | [Read Guide](agentic-rush/plugins-and-agent-skills.md) |
| **AI Anti-Slop & TDD Guard** | Hallucination detection & test contract verification | Flags repetitive AI comments, empty stubs, and ensures every new feature has an accompanying test contract. | [Read Guide](user-guide/working-with-ai-agents.md) |

---

## Quick Start for AI Agents

Give your AI agent superpowers in two minutes:

1. **Initialize Rush in your repository**:
   ```bash
   rush init .
   rush governance sync
   ```
2. **Launch the FastMCP server for your IDE**:
   Add Rush to your Cursor / Claude Code / Cline MCP configuration:
   ```json
   {
     "mcpServers": {
       "rush": {
         "command": "rush",
         "args": ["mcp", "serve"]
       }
     }
   }
   ```
3. **Prompt your agent**:
   > *"Before writing code, use `rush_codegraph_slice` to inspect the target function. After editing, verify your changes with `rush_check` and `rush_tdd`."*

## Context Diet & Grounding Protocols for Agents (Phases 41–43)
1. **Token Diet**: Use `rush_token_outline` to read AST signatures before loading full files.
2. **Reversible Caching**: Large outputs are returned as `<!-- ccr:chunk:HASH -->`. Query `rush_context_retrieve(chunk_hash)` only when verbatim logs are needed.
3. **Hallucination Defense**: Run `rush_hallu_guard` to verify generated code contains zero phantom packages.
4. **Pre-Mortem Invariants**: Call `rush_context_mistakes_check` before starting work to avoid repeating reverted patterns.
5. **Ship Cockpit**: Call `rush_ship_gate` before submitting pull requests or ending turns.

## Agent Protocols for Context Packing & Blast Radius (Phases 44–46)
1. **Context Packing**: Call `rush_context_pack(path, symbol, budget)` to retrieve focused AST context without blowing your token budget.
2. **Savings Telemetry**: Call `rush_context_gain_stats()` to inspect session token savings and cost efficiency.
3. **Blast Radius Analysis**: Call `rush_blast_radius(path)` before refactoring to know which downstream routes and tests are impacted.
4. **Architecture Governance**: Call `rush_arch_guard()` to verify you have not introduced unauthorized cross-layer imports.


## Agent Protocols for Test Healing & API Contracts (Phase 47)
1. **Flaky Test Repair**: Call `rush_test_heal(target)` when encountering intermittent test failures.
2. **API Guard**: Call `rush_api_diff(base='main')` to verify that your refactor maintains backward compatibility.



## Agent Protocols for DB Drift & Code Simplification (Phase 48)
1. **Database Safety**: Call `rush_db_drift()` after modifying ORM data models to ensure migrations exist.
2. **Code Simplification**: Call `rush_simplify(file)` before refactoring to target high-complexity hotspots.
3. **Type Strictness**: Call `rush_strictify(file)` to add defensive runtime checks to untyped inputs.



## Agent Protocols for Swarms & Traceability (Phase 49)
1. **File Locks**: Acquire `rush_mesh_acquire_lock(path, agent_id)` before writing files in parallel swarms.
2. **Conflict Resolution**: Call `rush_swarm_merge(base, ours, theirs)` to reconcile concurrent edits.
3. **Traceability**: Call `rush_trace()` to verify you have covered all required spec tags.



## Agent Protocols for Security & Release (Phase 50)
1. **Provenance**: Call `rush_attest_generate()` to produce SLSA build provenance.
2. **Compliance**: Call `rush_license_matrix()` to ensure no viral licenses are added.
3. **IAM Safety**: Call `rush_iam_audit()` to synthesize minimal cloud permissions.
4. **PR Cards**: Call `rush_pr_synthesize()` to generate release notes.

