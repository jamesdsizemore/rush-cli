# Specification: Cognitive Complexity Decomposer

## 1. Overview
`ComplexityDecomposer` (`src/rush/tools/simplify.py`) calculates cyclomatic and cognitive complexity for all functions in a module, isolating nested logic blocks and suggesting modular sub-function extractions.

## 2. CLI & FastMCP Reference
* `rush simplify --file <PATH> [--max-complexity <INT>]`
* `rush_simplify(file, max_complexity=10)`
