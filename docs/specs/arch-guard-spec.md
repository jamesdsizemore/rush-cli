# Specification: Declarative Architecture Boundary Guard

## 1. Overview
`ArchGuard` (`src/rush/tools/arch_guard.py`) validates that internal module imports conform strictly to directional architectural layers (e.g., Domain -> Application -> Infrastructure -> Presentation), preventing reverse or circular cross-layer coupling.

## 2. CLI & MCP Reference
* `rush arch-guard`
* `rush_arch_guard()`
