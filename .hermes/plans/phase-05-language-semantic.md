# Phase 05 — language-native and semantic scanners

> **Depends on:** Phases 00–04. **Excludes:** all browser/runtime work and unbounded project builds.

**Objective:** Preserve stable marker routing without marketing it as integration, and add semantic evidence only where a machine-readable local-report contract is proven. This phase implements a contained CodeQL SARIF 2.1.0 importer; it does not promote a live CodeQL or language-toolchain adapter.

## Compact development and review protocol

Use RTK for Git/read/grep/diff/project-vnv tests; **Graft** for routing, engine registry, tool callers, project-marker tests and language adapter files; **context-mode** for marker/applicability/result/permission contracts. Each ecosystem is a separate RED→GREEN→docs→spec review→security/quality review→fix/re-review slice. No cross-ecosystem batch commit.

## Ecosystem plan

| Ecosystem | Candidate and guarded behavior | Exact prerequisite |
|---|---|---|
| Go | golangci-lint, gosec, govulncheck | `go.mod`, local binary, JSON/SARIF/text parser proof; no module download unless explicit build permission |
| Rust | cargo audit/deny/clippy | `Cargo.toml`, local cargo/tool, no fetch/update by default; lock/provenance state visible |
| JVM/.NET | SpotBugs/PMD/Checkstyle; dotnet analyzers | declared local command/project, `allow_project_build`, output parser; no restore/build default |
| Ruby/Rails/PHP | RuboCop/Brakeman/Psalm | marker + local config/binary; JSON output and no dependency install |
| Dart/Flutter/Swift/Elixir/Scala/Nix | feasibility-gated candidates | official CLI/output/license/platform proof before catalog live status |
| Deep semantic | CodeQL SARIF importer first; live DB/query only explicit local query and `allow_project_build` | no query-pack/database download/build without permission |

## Tasks

1. Audit the existing marker-routing tests for stable order, inapplicable skip, and no engine execution during detection. Preserve `routing.py` because its established route is feasibility evidence, not a live adapter.
2. RED→GREEN a contained CodeQL SARIF importer with native rule IDs and normalized location/severity. Require SARIF 2.1.0 and a CodeQL driver identity; test clean, error, warning, malformed, foreign-engine, non-object, missing, and target-escape reports.
3. Register `codeql` once in the catalog, shared CLI/MCP registry, capability report detection, and catalog-maturity truth tests. Its `importer` maturity must never imply executable CodeQL support.
4. Document the explicit report-file workflow, canonical result outcomes, target containment, and the no-build/no-database/no-query-pack/no-network boundary in user, reference, compatibility, MCP, README, and changelog surfaces.
5. Keep every live language ecosystem candidate feasibility-gated. No build-dependent invocation, SDK/toolchain install, project restore, cache write, database creation, or query-pack retrieval is implemented in this phase.
6. Review the importer and documentation for path/secret handling and all registration paths for CLI/MCP parity; remediate only verified findings.

**Acceptance:** `codeql PATH` and `rush_codeql` share the same contained importer; capabilities detect `codeql.sarif` without execution; all CodeQL failure paths are structured; catalog/tool counts remain truthful; user/developer/reference/MCP/compatibility docs state the import-only boundary; unsupported ecosystems remain feasibility-gated rather than invented. **CI:** deterministic local SARIF fixtures and registry/capability contracts; no installed-CodeQL smoke is required because CodeQL is never executed. **Non-goals:** browser/Playwright/axe/Lighthouse/visual/DAST, live CodeQL database/query execution, and automatic SDK/toolchain install. Rollback removes the importer registration while preserving marker routing.