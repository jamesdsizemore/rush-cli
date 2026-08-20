# ADR-0015: Extensible Plugin Architecture and AI Agent Plugin Skills

## Status
Accepted

## Context
Organizations and development teams possess proprietary analyzers, internal security linters, and specialized quality checkers that cannot be hardcoded into the upstream Rush repository. Teams need a declarative, standard contract to add custom engines, and AI coding agents need automated capabilities to scaffold, test, and register custom plugins.

## Decision
1. Implement a declarative plugin configuration contract in `rush.toml` under `[plugins.<name>]` and a local `.rush/plugins/` directory.
2. Support executable script plugins (Python, Shell, Node, Rust, Go) that output structured `ToolResult` JSON.
3. Provide specialized AI agent skills (`rush-plugin-builder` and `rush-plugin-installer`) allowing coding agents to generate, validate, and install custom linters and analyzers autonomously.
4. Expose CLI commands: `rush plugin list`, `rush plugin install`, `rush plugin validate`, and `rush plugin create`.

## Consequences
- Infinite extensibility without core codebase modifications.
- Seamless developer and AI agent tooling creation.
- Strict schema enforcement for custom plugin outputs.
