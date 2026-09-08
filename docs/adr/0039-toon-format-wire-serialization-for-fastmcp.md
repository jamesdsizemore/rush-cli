Current status: planned; current contract: [Phase 63 memory capabilities and token benchmarks](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md); evidence: [current TOON specification](../specs/toon-serialization-spec.md). Historical percentages below are not Rush benchmark results. Current local serialization utilities do not replace MCP JSON-RPC framing, and no universal `--format toon` option is registered. Preserve lossless compact-result requirements while measuring actual token effects.

# ADR-0039: TOON Format Wire Serialization for FastMCP

## Status
Accepted (v0.3.0 / Phase 42)

## Context
JSON is the standard serialization format for MCP tool responses, but its repeated key strings, nested brackets, and indentation introduce 40–50% structural token overhead without providing semantic value to LLMs.

## Decision
1. Adopt **TOON (Token-Oriented Object Notation) v4.1** as a native wire serialization format for structured tool results in `src/rush/token_economy/toon/`.
2. Implement bidirectional `ToonEncoder` and `ToonDecoder` supporting Inline, Tabular, Keyed Tabular, and List forms.
3. Integrate TOON directly into `src/rush/tools/catalog.py:ToolResult.format()`, allowing agents and CLI consumers to request `--format toon`.

## Consequences
- **Positive**: Reduces JSON token footprint by 42.6% on average, increases model tabular reasoning accuracy (+0.8%), and cuts context bandwidth.
- **Negative**: Requires parser implementation for TOON format syntax.
- **Safety**: Lossless structural round-trip fidelity verified via automated tests.
