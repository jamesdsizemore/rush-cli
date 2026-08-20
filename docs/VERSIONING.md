# Versioning Policy & Compatibility Contracts

Rush follows [Semantic Versioning 2.0.0](https://semver.org/) (`MAJOR.MINOR.PATCH`) to communicate stability and compatibility boundaries across CLI, MCP, and configuration interfaces.

---

## 1. Stable Compatibility Surfaces

1. **CLI Commands & Flags**: Command names, options, and status exit codes.
2. **Model Context Protocol (MCP) Tools**: Tool names (`rush_<name>`), parameter schemas, and FastMCP annotations.
3. **Canonical ToolResult Shape**: The core dictionary keys (`tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, `raw`).
4. **Configuration Schema**: `rush.toml` syntax and table names.

---

## 2. Release & Version Cadence

- **Patch Releases (`0.2.x`)**: Bug fixes, engine adapter improvements, parser refinements, documentation updates. No breaking changes.
- **Minor Releases (`0.x.0`)**: New tools, new engine adapters, non-breaking schema additions, new permission flags.
- **Major Releases (`1.0.0+`)**: Breaking changes to CLI options, MCP parameter signatures, or core `ToolResult` dictionary keys.

See [Versioning and Compatibility Guide](maintainers/versioning-and-compatibility.md) and [Release Process](developer/release-process.md).
