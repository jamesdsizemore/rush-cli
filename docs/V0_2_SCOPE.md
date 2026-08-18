# Rush v0.2 Scope and Engine Policy

Rush v0.2 grows Rush from a Python/JS quality companion into a deterministic,
local-first quality router. It keeps the v0.1 CLI and stdio-only MCP protocol
compatible while adding a catalog of tool capabilities and language-aware
external engine adapters.

## Compatibility contract

- `rush mcp serve` remains **local stdio only**. No HTTP, SSE, ports, or
  background listener is introduced.
- MCP stdout carries JSON-RPC only. Logs remain structured NDJSON on stderr.
- CLI and MCP call the same `ToolFn` objects and return the canonical
  `ToolResult` shape.
- Existing commands (`review`, `lint`, `format`, `test`, `security`) remain
  available with their v0.1 arguments and check-only formatting semantics.
- Engine absence is not a crash: a capability returns a structured `skipped`
  result explaining which executable is unavailable.

## Catalog and result contract

The catalog is Rush's source of truth for user-visible tool names,
descriptions, categories, and candidate engines. The transport creates ordinary
`PATH --json` CLI commands from the catalog; tools with meaningful custom
options retain a dedicated command surface.

Every tool result includes these stable fields:

- `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, and
  `findings`;
- optional `metrics`, `artifacts`, and `metadata` fields for v0.2 capabilities;
- optional engine `raw` output for debugging only.

Status precedence is deterministic: `error > fail > warn > ok > skipped`.
When a capability uses more than one engine, its findings sort by source
location, metrics retain the first producer for a key, and artifact paths are
deduplicated in first-seen order.

## Dependency policy

Rush does **not** bundle operating-system or ecosystem CLIs as mandatory runtime
dependencies. An installed Python, Node, Go, Rust, Java, .NET, Docker, or
Terraform engine is discovered at execution time. Python-native engines may be
offered later as explicit optional extras; they are never silently installed by
a Rush command.

This preserves reproducibility and keeps `rush` usable in mixed-language
repositories. Documentation for each capability must state its executable,
expected installation path, supported files, and structured skipped behavior.

## Planned v0.2 capability groups

1. **Static analysis:** type checking, dead-code detection, complexity,
   duplication, conventional commits, and code-quality linting.
2. **Content and infrastructure:** Markdown, YAML, GitHub Actions, SQL,
   templates, Dockerfiles, and IaC.
3. **Supply chain:** secrets, SBOM, dependency policy, and vulnerability scans.
4. **Test quality:** coverage, mutation, property, end-to-end, snapshot,
   flaky-test, fuzz, load, and contract checks.
5. **Workflow and language routing:** CI health, release readiness,
   conventional commits, Go, Rust, Java, .NET, Ruby, PHP, C/C++, Dart/Flutter,
   Swift, Kotlin, Lua, and Elixir discovery.
6. **Context-aware analysis:** Graft-backed architecture/context reporting and
   an explicitly experimental semantic-drift command.

Potential LLM review, hosted OSV enrichment, and license-policy evaluation are
outside the default v0.2 engine set because they require credentials, network
access, or organization-specific policy. They remain explicit future opt-ins.

## Safety

Slow, networked, destructive, or environment-sensitive engines must be opt-in
through config and rejected by default with a structured `skipped` result.
Rush never reads credentials, never embeds keys, and never transmits repository
content unless a user explicitly enables an external engine.

## Language routing

Rush detects Python, JavaScript, Go, Rust, Ruby, JVM, Swift, PHP, .NET,
Elixir, Dart, Scala, and Nix project markers in stable order. A mixed project
is aggregated deterministically; it never selects an arbitrary first
ecosystem. Language CLI binaries are discovered at runtime and use check-only
commands. Missing binaries return `skipped`; Rush does not install them.
