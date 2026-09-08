# Specification: Terse Persona Mode

## 1. Overview
`OutputShaper` (`src/rush/token_economy/output_shaper.py`) applies local terse-output shaping. Configure the persona through the command below; there is no universal `--style terse` CLI flag. Measure token counts for the actual input/output rather than assuming a 40–60% reduction.

## 2. CLI & MCP Control
* `rush context persona --set terse`
* `rush context persona --set default`
