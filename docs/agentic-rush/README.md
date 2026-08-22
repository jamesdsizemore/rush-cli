# Agentic Rush Documentation

Welcome to the **Agentic Rush** knowledge base. This section details the complete suite of AI-native tooling, autonomous safety layers, token economy optimization, and governance systems integrated into Rush.

---

## Guides in This Section

1. [AI Safety & Worktree Sandboxing](ai-safety-and-sandboxing.md)
   - How `rush safety` intercepts dangerous shell commands and confines agent file modifications within repository boundaries.
2. [Patch Remediation & Session Memory](patch-remediation-and-memory.md)
   - How `rush patch` tests diffs in isolated worktree environments with automated rollbacks, and how `rush memory` preserves multi-turn context.
3. [Token Economy & Context Optimization](token-economy-and-context.md)
   - How `rush token` performs offline BPE counting and AST outline compression, shrinking prompts by up to 90%.
4. [CodeGraph & Semantic Slicing](codegraph-and-semantic-slicing.md)
   - How `rush codegraph` extracts verbatim code slices, call paths, and AST symbols in sub-milliseconds.
5. [Codebase Hygiene & 3-Way AST Merges](codebase-hygiene-and-ast-merging.md)
   - How `rush hygiene` hunts down dead code and `rush conflict` reconciles parallel AI branch modifications.
6. [Agent Governance & Multi-IDE Rules](governance-and-multi-ide-rules.md)
   - How `rush governance` compiles canonical `AGENTS.md` instructions into `.cursorrules`, `.clinerules`, and Windsurf rules.
7. [Pre-Commit Intelligence & Hook Guard](pre-commit-intelligence.md)
   - How `rush hook` prevents Trojan Source Unicode vulnerabilities and blocks broken commit markers.
8. [Multi-Model Consensus & Quality Scorecards](multi-model-consensus-and-scoring.md)
   - How `rush consensus` reconciles findings across multiple AI models and `rush score` grades repository health.
9. [Plugins & Agent Skills](plugins-and-agent-skills.md)
   - How `rush plugins` and `rush skills` provide trust-gated execution of custom tools and automated skill generation for agents.

---

## Common Agent Workflows

- **Inner-Loop Quality Verification**: Run `rush check` and `rush tdd` after each agent code generation step.
- **Context Injection**: Use `rush codegraph slice <symbol>` or `rush token outline <file>` to provide concise, verbatim context to your model.
- **Pre-Merge Hardening**: Run `rush gate` and `rush score compute` before submitting pull requests.
