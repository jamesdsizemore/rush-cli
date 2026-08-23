# Specification: Runtime Type Guard Synthesizer

## 1. Overview
`TypeSynthesizer` (`src/rush/tools/strictify.py`) inspects untyped function parameters and generates runtime type assertions and `TypeGuard` predicates to prevent dynamic payload type crashes.

## 2. CLI & FastMCP Reference
* `rush strictify --file <PATH>`
* `rush_strictify(file)`
