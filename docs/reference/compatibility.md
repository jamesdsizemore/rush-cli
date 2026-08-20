# Compatibility

## Rush runtime

- Python: 3.12 or newer, as declared by the package.
- Platforms: Windows, macOS, and Linux are intended; CI currently verifies Linux, while contributor guidance covers Windows project-environment isolation.
- Package workflow: uv is recommended; wheel and source distributions are build targets.
- MCP: local stdio through the pinned Python MCP SDK; no HTTP/SSE transport.

## Project ecosystems

Strongest implemented paths are Python and JavaScript/TypeScript. Marker detection also recognizes Go, Rust, Ruby, JVM, Swift, PHP, .NET, Elixir, Dart, Scala, and Nix for best-effort routing. Content, infrastructure, supply-chain, and workflow checks have individual maturity levels.

## Engine versions

Rush discovers executables rather than bundling all engines. Parser fixtures pin reference behavior for promoted adapters, but the environment chooses actual versions. Unsupported output changes should return `error` rather than fabricated findings.

For exact per-engine applicability and install hints, see [Engine directory](engine-directory.md). For compatibility promises and changes, see [Maintainer versioning](../maintainers/versioning-and-compatibility.md).
