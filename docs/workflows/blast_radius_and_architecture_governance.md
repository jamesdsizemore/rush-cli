# Workflow: Blast Radius & Architectural Governance

## 1. Running Pre-Commit Blast Radius Analysis
Before refactoring shared components or core interfaces:
```bash
rush blast-radius --path src/rush/cli.py
```

## 2. Validating Clean Architecture Boundaries
```bash
rush arch-guard
```
