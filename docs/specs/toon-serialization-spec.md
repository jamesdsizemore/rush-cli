# Specification: TOON v4.1 (Token-Oriented Object Notation) Wire Format

## 1. Overview
Rush's TOON utility represents tabular local data as pipe-delimited text. It does not replace MCP's JSON-RPC transport or the canonical tool response contract. Token savings depend on the actual payload and tokenizer; the prior 40–65% figure is not a measured guarantee for arbitrary input.

## 2. Wire Structure
```markdown
|col1|col2|col3|
|---|---|---|
|val1|val2|val3|
|val4|val5|val6|
```

## 3. Delimiter Escaping Rules
* Pipe characters within string values must be escaped as `\|`.
* Newlines within string cells are replaced by a space.
* Empty cells default to empty strings.

## 4. API Reference
* `rush.token_economy.toon.encode_toon(data: list[dict[str, Any]]) -> str`
* `rush.token_economy.toon.decode_toon(toon_str: str) -> list[dict[str, Any]]`
* There is no universal `--format toon` CLI option. Use the Python utility explicitly and inspect each command's actual `--help` before selecting an output format.
