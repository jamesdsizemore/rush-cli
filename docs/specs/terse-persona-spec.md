# Specification: Terse Persona Mode

## 1. Overview
`OutputShaper` (`src/rush/token_economy/output_shaper.py`) strips conversational preamble, greetings, and repetitive summary paragraphs when `--style terse` is configured, cutting output tokens by 40–60%.

## 2. CLI & MCP Control
* `rush context persona --set terse`
* `rush context persona --set default`
