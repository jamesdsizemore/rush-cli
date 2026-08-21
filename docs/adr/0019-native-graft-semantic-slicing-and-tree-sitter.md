# ADR-0019: Native Graft Semantic Slicing and Tree-Sitter AST Engine

## Status
Accepted

## Context
Autonomous coding agents operating on multi-thousand line files waste up to 90% of their context window reading irrelevant file contents. External AST tools like standalone `ast-grep` require compiling and spawning platform-specific binaries and lack multi-file call-graph traversal.

## Decision
1. Standardize on **`graft`** powered by native embedded `tree-sitter==0.24.0` as Rush's unified AST engine.
2. Provide in-process semantic symbol slicing (`rush_graft_slice`), structural code rewrites (`rush_apply_ast_patch`), and 3-way AST merge conflict resolution.
3. Expose Tree-Sitter parsing across standard Python and TypeScript/JavaScript language bindings natively.

## Consequences
- Up to 90% reduction in agent context token consumption during code analysis and refactoring.
- Sub-millisecond in-process AST extraction with zero external binary dependencies.
- Deterministic syntax validation prior to committing patches to disk.
