# Advanced Checks & Monorepos

As software repositories grow into multi-package monorepos with hundreds of thousands of lines of code, managing performance, scoping checks, and tracking defect risk becomes critical.

Rush includes advanced architectural capabilities designed specifically for large-scale codebases.

---

## 1. Multi-Package Monorepo Scoping (`rush workspace`)

If your repository contains multiple packages (e.g. `apps/web`, `apps/api`, `packages/shared-ui`), running checks across the entire repository every time you change one file is slow and wasteful.

Rush automatically discovers workspace topologies across **pnpm, npm, yarn, Cargo, and Turborepo**:

```bash
# List all discovered workspace packages in topological order
rush workspace list

# Find only the packages affected by your recent Git changes
rush workspace affected

# Run checks on a specific package
rush check . -w packages/shared-ui
```

---

## 2. Flag-Salted Result Caching (`rush cache`)

Rush includes an embedded, high-performance SQLite result cache (`.rush/cache.db`). When a file hasn't changed and the tool configuration remains identical, Rush returns the cached result in **0 milliseconds**.

```bash
# Inspect the local result cache
rush cache inspect

# Clear cached results before a fresh run
rush cache clear
```

The cache uses cryptographic SHA-256 content hashing combined with command-line flags to guarantee you never receive stale or incorrect results.

---

## 3. Git Hotspots & Defect Risk Matrix (`rush hotspots`)

Where are bugs most likely to hide in your repository?

Research across software engineering shows that defects concentrate where **high commit churn** (files that are constantly being edited) intersects with **high cyclomatic complexity** (files with deeply nested `if/else` logic).

```bash
rush hotspots analyze
```

### What Rush Computes:
- **Commit Churn**: How many times a file has been modified over the past 90 days.
- **McCabe Cyclomatic Complexity**: How many decision paths exist in the code.
- **Composite Defect Risk Score**: Pinpoints the top 5 highest-risk files in your repository so you know exactly where to write extra unit tests or schedule refactoring.

---

## 4. Web Asset & Bundle Budgeting (`rush bundle`)

If you build frontend web applications, shipping massive JavaScript bundles to users slows down page load times and harms SEO rankings.

```bash
rush bundle analyze dist/
```

- Calculates raw, Gzip, and Brotli chunk transfer sizes.
- Identifies barrel file imports (`import { a } from './components'`) that prevent effective tree-shaking.
- Detects duplicate CSS rules and uncompressed images.

---

## Next Steps

- Explore the complete [Bundle Diagrams](../BUNDLE_DIAGRAMS.md).
- Discover solutions to common questions in [Troubleshooting Guide](troubleshooting.md).

## Advanced Ship Vectors (Phases 41–43)
* `rush ship migration`: Checks SQL files for table locks (`ALTER TABLE ... ADD COLUMN NOT NULL`).
* `rush ship semver`: Compares AST public interfaces between versions.
* `rush ship pack`: Scans repository trees for secret keys, credentials, and `.env` leaks.

## Blast Radius & Architecture Checks
* `rush blast-radius`: Downstream reachability.
* `rush arch-guard`: Layer boundary verification.



## Flaky Test Healing & API Diff
* `rush test-heal`: Diagnose intermittent test failures.
* `rush api-diff`: Ensure public signature parity.



## DB Drift & Code Simplification
* `rush db-drift`: Schema migration drift detection.
* `rush simplify`: Function complexity decomposition.
* `rush strictify`: Runtime type guard generation.



## Traceability & CI Simulation
* `rush trace`: Spec-to-code traceability.
* `rush simulate-ci`: Local GitHub Actions emulation.

