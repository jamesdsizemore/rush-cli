# Specification: Zero-Server Public API Contract Differ

## 1. Overview
`ApiDiffer` (`src/rush/tools/api_diff.py`) parses AST function and class signatures across Git revisions to flag breaking API modifications, deleted symbols, or removed parameters before PR merges.

## 2. CLI & FastMCP Reference
* `rush api-diff [--base <REF>]`
* `rush_api_diff(base="main")`
