# ADR-0048: Hybrid Dual-Engine Architecture (Graft Semantic Graph + CodeGraph AST Engine)

## Status
Accepted (v0.3.0 / Phase 41–50)

## Context
Rush requires both macroscopic repository-level architectural analysis (whole-project call graphs, cross-module links, dependency slicing) and microscopic syntax-level precision (AST Merkle tree hashing, PageRank symbol budget packing, real-time grounding verification, and target-aware skeletonization). Choosing only one creates unacceptable feature degradation: external graph tools lack sub-millisecond in-process AST slicing, while pure AST parsers lack multi-project architectural context.

## Decision
1. Formally adopt a **Hybrid Dual-Engine Architecture** where **Graft** and **CodeGraph** operate in symbiotic union without degrading either engine:
   - **Graft Subsystem (`src/rush/integrations/graft.py` / `LocalGraftContext`)**: Governed by [ADR-0019](file:///C:/Users/james/developer/rush-cli/docs/adr/0019-native-graft-semantic-slicing-and-tree-sitter.md). Interacts with `@nanonets/graft` / `.hermes/graft/` to generate macroscopic markdown-linked context graphs, whole-repo caller/callee traversal, and project-level semantic slices.
   - **CodeGraph AST Engine (`src/rush/codegraph/`)**: Governed by [ADR-0032](file:///C:/Users/james/developer/rush-cli/docs/adr/0032-code-property-graph-pruned-context-packing-and-token-budgeting.md) and [ADR-0038](file:///C:/Users/james/developer/rush-cli/docs/adr/0038-context-intelligence-engine-and-ccr-architecture.md). Operates in-process using Tree-sitter and SQLite WAL storage (`.rush/codegraph.db`) for Merkle hash cache invalidation, PageRank symbol budgeting (`rush context pack`), target-aware skeletonization (`AstSkeletonizer`), and real-time grounding verification (`GroundingVerifier`).
2. Downstream tools query Graft for macroscopic reachability and CodeGraph for microscopic AST node properties.

## Consequences
- **Positive**: Zero feature degradation; combines the proven architectural strength of Graft with the microscopic precision of in-process CodeGraph AST property trees.
- **Negative**: Requires maintaining integration interfaces for both `LocalGraftContext` and in-process `src/rush/codegraph/`.
- **Safety**: 100% local-first and offline execution; deterministic caching in `.hermes/graft/` and `.rush/codegraph.db`.
