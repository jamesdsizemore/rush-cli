# Specification: TOON v4.1 (Token-Oriented Object Notation) Wire Format

## 1. Overview
TOON (Token-Oriented Object Notation) v4.1 is an ultra-compact tabular serialization wire format engineered specifically for LLM tool call responses and FastMCP transports. It replaces redundant JSON key-value overhead with markdown pipe-delimited tables, achieving 40% to 65% token savings on array-of-objects payloads.

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
* CLI Flag: `--format toon` on supported subcommands.
