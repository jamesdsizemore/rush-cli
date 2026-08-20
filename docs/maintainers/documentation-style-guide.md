# Documentation style guide

## Audiences

User docs lead with goals and plain language: “Rush checks your project with tools you already use.” Explain engine and MCP immediately. Do not lead with registry, adapter, routing, schema, or subprocess.

Developer docs may use exact module and contract terminology. Maintainer docs are operational and evidence-driven.

## Page contract

State what it is, why/when it matters, prerequisites, numbered action, expected result, explanation, safety boundary, and next link where relevant. Examples must be copyable and capability-accurate. Tables support prose; they do not replace it.

## Diagrams and links

Use Mermaid only when it clarifies a flow or trust boundary. Use descriptive node labels and relative links. Every local link must validate.

## Change matrix

- New tool: README if user-visible, CLI reference, tool catalog, result examples, safety/maturity, tutorials if central, MCP reference, developer tool guide, changelog.
- New engine: engine directory, compatibility, install/recovery, tool pages, engine developer evidence, changelog.
- New config field: configuration reference/cookbook/example, migration, developer config guide, changelog.
- New permission/data boundary: safety, privacy/security, CLI/MCP reference, ADR, tests, changelog.

Never describe a stub, parsed no-op setting, or internal-only option as usable. Generated help and executable tests win over stale prose.
