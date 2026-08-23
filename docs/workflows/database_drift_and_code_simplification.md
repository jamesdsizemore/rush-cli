# Workflow: Database Schema Drift & Code Simplification

## 1. Pre-Deployment Database Drift Audit
```bash
rush db-drift
```

## 2. Refactoring Spaghetti Functions
```bash
rush simplify --file src/engine.py --max-complexity 10
rush strictify --file src/engine.py
```
