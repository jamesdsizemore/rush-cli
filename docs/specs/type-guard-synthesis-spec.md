# Specification: Runtime Type Guard Synthesizer

Status: planned — safe constraint-derived synthesis is owned by [P64-15](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-15--ground-schema-drift-and-type-guards-f1617). Current heuristic guards can reject valid inputs (F17). Treat existing output as an unverified proposal; the required implementation must preserve valid list, tuple and generator behavior and refuse unsupported inference.

## 1. Overview
`TypeSynthesizer` (`src/rush/tools/strictify.py`) inspects untyped function parameters and generates runtime type assertions and `TypeGuard` predicates to prevent dynamic payload type crashes.

## 2. CLI & FastMCP Reference
* `rush strictify --file <PATH>`
* `rush_strictify(file)`
