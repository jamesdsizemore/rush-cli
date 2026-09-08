# Workflow: Database Schema Drift & Code Simplification

Current limitations: schema identity and strictify inference require P64-15, and nested complexity counting requires P64-18. The commands below expose current analysis/proposal routes; a clean result does not establish corrected schema comparison, and proposed guards/refactors require validation. See [Phase 64](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md).

## 1. Pre-Deployment Database Drift Audit
```bash
rush db-drift
```

## 2. Refactoring Spaghetti Functions
```bash
rush simplify --file src/engine.py --max-complexity 10
rush strictify --file src/engine.py
```
