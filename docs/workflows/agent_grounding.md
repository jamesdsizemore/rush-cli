# Workflow: Real-Time AST Import Grounding Verification

## 1. Overview
The AST Grounding Verifier (`rush hallu-guard`) checks Python imports against local module and distribution evidence. A found package does not prove that it is safe, correctly attributed, or free of typosquatting; package presence also does not prove every imported symbol exists. Inspect findings alongside dependency and security scans.

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

```

FastMCP call: `rush_hallu_guard(path="src/new_feature.py")`. This is a tool invocation through the agent, not a shell command.
