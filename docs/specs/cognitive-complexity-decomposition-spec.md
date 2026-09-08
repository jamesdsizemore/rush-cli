# Specification: Cognitive Complexity Decomposer

Current limitation: nested definitions inflate their enclosing function's complexity (F23). [P64-18](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-18--real-source-structure-in-catalogscomplexity-f2223) corrects definition-local counting. Existing suggestions do not constitute an applied or verified refactor.

## 1. Overview
`ComplexityDecomposer` (`src/rush/tools/simplify.py`) calculates cyclomatic and cognitive complexity for all functions in a module, isolating nested logic blocks and suggesting modular sub-function extractions.

## 2. CLI & FastMCP Reference
* `rush simplify --file <PATH> [--max-complexity <INT>]`
* `rush_simplify(file, max_complexity=10)`
