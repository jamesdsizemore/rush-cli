# Versioning and compatibility

Rush follows SemVer intent: breaking CLI, ToolResult, config, MCP schema/name, or engine-behavior changes require an appropriate major boundary once stable; additive commands/fields normally require minor versions; compatible fixes require patches.

Compatibility surfaces:

- Python requirement and package entry point;
- CLI command names/options/exit mapping;
- ToolResult/Finding fields and status semantics;
- `rush.toml` discovery and accepted fields;
- MCP tool names, descriptions, input/output schemas, and stdio behavior;
- engine invocation/parser contracts and maturity labels.

Engine versions are external. Pin reference versions in evidence docs/fixtures and fail clearly when reports are incompatible. Every breaking change updates changelog, migration guide, reference docs, package tests, and clean-install evidence.
