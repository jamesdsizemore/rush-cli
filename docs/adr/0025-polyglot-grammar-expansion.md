# ADR-0025: Polyglot Grammar Expansion via tree-sitter-language-pack

## Status
Accepted

## Context
Coding agents operate in polyglot repositories containing Python, TypeScript, JavaScript, Rust, Go, Java, C#, Ruby, Kotlin, Swift, and Elixir. Managing individual grammar packages in `pyproject.toml` causes dependency sprawl and platform wheel mismatches.

## Decision
1. Pin `tree-sitter-language-pack==0.4.0` alongside native `tree-sitter==0.24.0`.
2. Provide unified on-demand parser resolution across 370+ pre-compiled Tree-Sitter language grammars.
3. Power `rush_graft_slice`, `rush schema-sync`, and `rush git-resolve` across polyglot codebases.

## Consequences
- Instantaneous, offline multi-language AST parsing across all tier-1 operating systems.
- Unified AST query API for all programming languages without requiring local C compilers.
