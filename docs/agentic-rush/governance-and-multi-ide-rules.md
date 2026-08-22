# Agent Governance & Multi-IDE Rules

Modern engineering teams use a diverse mix of AI coding assistants: some developers use **Cursor**, others use **Claude Code**, **Cline**, **Windsurf**, or **GitHub Copilot**. Each tool reads rules from a different file format (`.cursorrules`, `.clinerules`, `.windsurfrules`, `AGENTS.md`, or Claude system prompts), creating severe rule drift and inconsistent agent behaviors.

Rush’s **Agent Governance Subsystem** (`rush governance`) establishes `AGENTS.md` as the single canonical source of truth and automatically compiles it across all IDE formats.

---

## 1. The Single Source of Truth: `AGENTS.md`

`AGENTS.md` is a human-readable, AI-optimized markdown document located at your repository root. It defines:
- The project contract (language runtime, package manager, build scripts).
- Testing and documentation synchronization requirements.
- Scope, security, and secret handling policies.
- Architectural boundaries and forbidden operations.

---

## 2. Compiling Rules Across All IDEs

The `rush governance sync` command reads `AGENTS.md` and compiles tailored rule files for every supported AI coding environment:

```bash
# Compile canonical AGENTS.md into all IDE rule formats
rush governance sync
```

### Generated Target Files:
- `.cursorrules` (Cursor IDE)
- `.clinerules` (Cline / Roo Code extension)
- `.windsurfrules` (Windsurf Cascade AI)
- `.github/copilot-instructions.md` (GitHub Copilot)
- `.gemini/settings.json` (Google Gemini / Antigravity)

---

## 3. Subagent Boundary Guard

When autonomous subagents are dispatched in parallel, `rush governance check` verifies that no subagent exceeds its authorized operational scope or violates team architecture policies.

```bash
# Check repository governance parity and agent permissions
rush governance check
```

---

## 4. Scaffolding New Repositories

To bootstrap a new project with production-ready agent governance in seconds:

```bash
# Scaffold canonical AGENTS.md and rush.toml templates
rush governance scaffold init
```

---

## Next Steps

- Explore sub-second pre-commit hooks in [Pre-Commit Intelligence & Hook Guard](pre-commit-intelligence.md).
- Learn how to grade repository health with [Multi-Model Consensus & Quality Scorecards](multi-model-consensus-and-scoring.md).
