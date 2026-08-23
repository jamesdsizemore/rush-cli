# Specification: Spec-to-Code Traceability Scanner

## 1. Overview
`TraceScanner` (`src/rush/tools/trace.py`) parses Markdown specs and tests for requirement tags (`[REQ-001]`, `FR-XX-YY`), mapping them to AST source implementations and test assertions to produce a complete compliance matrix.

## 2. CLI & FastMCP Reference
* `rush trace`
* `rush_trace()`
