# Agentic Rush: The AI Agent Copilot & Quality Control Engine

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
