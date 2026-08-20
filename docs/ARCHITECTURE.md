# Rush architecture

Rush is a Python 3.12 package with two transports and one implementation layer. Click CLI commands and FastMCP tools invoke the same objects from `src/rush/tools/`; external programs are isolated behind adapters in `src/rush/engines/`.

```mermaid
flowchart TB
  Catalog[src/rush/catalog.py] --> CLI[Click command generation]
  Catalog --> MCP[FastMCP registration]
  CLI --> Tools[ALL_TOOLS / ToolFn.run]
  MCP --> Tools
  Config[rush.toml discovery] --> Tools
  Tools --> Routing[language/applicability + aggregation]
  Routing --> Adapters[engine adapters]
  Adapters --> Proc[bounded subprocess; stdin DEVNULL]
  Proc --> Normalize[canonical ToolResult]
  Normalize --> CLI
  Normalize --> MCP
```

## Core contracts

- `TOOL_SPECS` and `ENGINE_SPECS` are declarative metadata; `ALL_TOOLS` and `ENGINES` are executable registries. Tests enforce parity.
- `ToolFn.run(path, *, config, ...)` is the internal execution surface. `ToolFn.__call__` is MCP-facing and must expose only JSON-schema-safe parameters.
- ToolResult required keys are `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, and `raw`; optional extensions include metrics, artifacts, metadata, and review fields.
- A missing optional executable returns `skipped`; it must not raise or install anything.
- Multi-engine aggregation is deterministic: worst status wins (`error > fail > warn > ok > skipped`), durations sum, findings sort by location/rule/message, and provenance is retained. The review aggregation path is explicitly serial, retains compact child tool/engine/status evidence, labels skipped/error children as partial metadata, deduplicates on normalized fingerprints, and never turns an error or skip into a clean result. Direct review only narrows scope when its caller explicitly supplies target-contained paths; it never shells out to infer a Git diff.

## Configuration flow

```mermaid
flowchart LR
  Target --> Walk[walk upward]
  Walk --> Config{rush.toml?}
  Walk --> Git{.git boundary?}
  Config -- nearest --> Parse[typed dataclasses + tool-name validation]
  Parse --> Defaults[built-in defaults]
  Defaults --> Overrides[explicit CLI/tool args win]
  Git -- reached --> Stop[do not read parent checkout config]
```

## Engine flow

```mermaid
sequenceDiagram
  participant T as Tool
  participant R as Router
  participant E as Engine adapter
  participant P as External process
  T->>R: target + options
  R->>E: applicable files / project
  E->>P: deterministic argv, timeout, stdin detached
  P-->>E: captured exit/stdout/stderr
  E-->>T: normalized ToolResult
  T-->>T: aggregate, sort, redact
```

## Safety architecture

Stdio MCP stdout is reserved for JSON-RPC. Logs are stderr NDJSON. Engine processes cannot consume protocol input. Security-sensitive promoted adapters own config/environment constraints. Artifact writers validate target containment and overwrite intent. Browser/network/slow/fuzz/baseline/publication work is denied or skipped without explicit implemented permission.

See the focused developer chapters linked from [Developer guide](DEVELOPER_GUIDE.md) and the [ADRs](maintainers/adr/README.md).
