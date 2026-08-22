# Workflow: Real-Time AST Import Grounding Verification

## 1. Overview
The AST Grounding Verifier (`rush hallu-guard`) protects AI coding sessions from dependency hallucinations and package typosquatting vulnerabilities by verifying that every imported symbol or package exists in the Python standard library or the active environment's installed distributions.

## 2. Verification Protocol
1. Parse code concrete syntax tree using Python `ast`.
2. Inspect `ast.Import` and `ast.ImportFrom` nodes.
3. Check top-level package against:
   * `sys.stdlib_module_names` (Python Standard Library)
   * `importlib.metadata.distributions()` (Installed venv packages)
   * Local project package namespace (`rush`)
4. Flag ungrounded phantom imports before execution or patch application.

## 3. CLI and FastMCP Usage
```bash
# Run codebase-wide grounding check
rush hallu-guard

# Run FastMCP grounding check on a single file
rush_hallu_guard(path="src/new_feature.py")
```
