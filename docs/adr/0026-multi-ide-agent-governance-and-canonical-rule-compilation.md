# ADR-0026: Multi-IDE Agent Governance and Canonical Rule Compilation

## Status
Accepted (v0.2.0)

## Context
As multi-agent AI ecosystems interact with enterprise codebases, disparate IDE assistants (Cursor, Windsurf, Copilot, Cline, Antigravity) enforce fragmented and drifting rule files (`.cursorrules`, `.windsurfrules`, `.clinerules`, `.github/copilot-instructions.md`, `.gemini/antigravity/rules.md`). Without a single canonical source of truth, security boundaries and coding invariants drift out of parity.

## Decision
1. Establish `AGENTS.md` at the repository root as the sole canonical source of governance, coding standards, and safety invariants.
2. Introduce `rush governance sync` and `rush_governance_sync` FastMCP tool to compile `AGENTS.md` into all target IDE rule files with SHA-256 integrity headers.
3. Introduce `rush governance verify` to validate rule parity in CI/CD without writing to disk.
4. Provide `McpConfigGenerator` to provision `.cursor/mcp.json` and `.vscode/mcp.json` automatically.
5. Enforce acyclic subagent invocation trees (`SubagentHierarchyValidator`) with max depth <= 3.

## Consequences
- **Positive**: Uniform governance across all AI tools, automated rule compilation, zero rule drift.
- **Negative**: Developers must edit `AGENTS.md` rather than IDE-specific rule files directly.
- **Safety**: Blocks recursive subagent invocation loops and path traversal in scaffolding.
