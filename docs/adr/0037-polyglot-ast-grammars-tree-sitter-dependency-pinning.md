# ADR-0037: Polyglot AST Grammars and Tree-sitter Dependency Pinning

## Status
Accepted (v0.2.0 / Dependencies)

## Context
High-accuracy code property graphs, architectural boundary enforcement (`rush arch-guard`), and context packing across Python, JavaScript, TypeScript, and Rust require robust, high-performance polyglot AST parsing without spawning slow compiler subprocesses.

## Decision
1. Pin native Tree-sitter bindings (`tree-sitter==0.26.0`, `tree-sitter-python==0.25.0`) in the development environment for sub-millisecond AST grammar parsing.
2. Pin `tiktoken==0.14.0` for local deterministic BPE token counting and context packing budgets.
3. Pin `check-wheel-contents` for pre-flight RAM sandbox distribution archive inspection.
4. Pin `defusedxml` and `pillow` for secure SVG sanitization, layout shift (CLS) dimension auditing, and lossless image compression.

## Consequences
- **Positive**: Provides ultra-fast in-memory parsing across polyglot files with zero external tool dependencies.
- **Negative**: Adds compiled wheel dependencies to the developer virtual environment.
- **Safety**: Robust memory management and protection against XML entity injection (XXE).
