# Tool development

## Worked example: add `licenses`

1. **Define the contract in a failing test.** Specify purpose, safe default, result shape, and missing-engine behavior.
2. **Add catalog metadata.** Add one `ToolSpec` with category, human and MCP descriptions, engine names, experimental flag, and honest maturity. Update the exhaustive maturity map.
3. **Implement `LicenseTool`.** Put business logic in `run`; keep `__call__` schema-safe and free of `config`. Return canonical ToolResult for every path.
4. **Register once.** Add the object to `ALL_TOOLS`; generated CLI/MCP parity tests should prove exposure. Do not hand-copy transport logic.
5. **Wire configuration only if consumed.** Unknown tool tables already fail; add field behavior with a test rather than accepting a no-op.
6. **Add engine adapters and routing** only after their contracts are fixture-backed.
7. **Document user outcome, helper install, result meanings, and maturity.** Update tool catalog, CLI reference, engine directory, safety docs, and examples.

## Safety review

For browser, slow, network, fuzz, baseline, filesystem-write, Git, or publication behavior: define explicit invocation-scoped permission; default to skip/refuse; constrain target and output; add denial and success tests; expose the same capability accurately in CLI and MCP; and record an ADR. A permission mentioned only in summary text is not an implemented permission surface.

## Done gate

Catalog/registry parity, CLI help, MCP schema/call, config validation, deterministic output, missing engine, malformed/timeout, redaction, docs, full tests, Ruff, format, diff, links, and graph checks all pass.
