# ADR-0042: AST Grounding and Phantom Symbol Verification

## Status
Accepted (v0.3.0 / Phase 43)

## Context
LLMs hallucinate phantom standard library methods, uninstalled third-party packages, and nonexistent workspace exports, causing broken patches and runtime import crashes.

## Decision
1. Implement a deterministic **Grounding Verifier** in `src/rush/codegraph/grounding_verifier.py` and `src/rush/tools/hallu_guard.py`.
2. Cross-reference all AST import statements against installed virtualenv site-packages (`importlib.metadata`), standard library manifests, and project Code Property Graph symbols.
3. Intercept and block code patches introducing ungrounded imports or typosquatted package names with $<20\text{ ms}$ verification latency.

## Consequences
- **Positive**: 100% elimination of phantom imports and hallucinated third-party dependencies.
- **Negative**: Requires maintaining standard library symbol tables per target language.
- **Safety**: Purely local AST verification without external cloud lookups.
