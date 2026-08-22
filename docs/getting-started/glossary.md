# Glossary

**Coding assistant** — A development tool that can inspect or change code. Some assistants can launch Rush through MCP.

**Engine** — An optional helper program Rush knows how to run, such as Ruff, ESLint, pytest, or pip-audit. Rush does not install engines.

**Finding** — One reported issue with a path, rule, severity, message, and optional location.

**Heuristic review** — A deterministic rule-based inspection. It is not human review and not an AI model judgment.

**MCP (Model Context Protocol)** — A standard that lets a compatible coding assistant launch a local tool and call named operations. Rush supports local stdio MCP only.

**Optional check** — A check that can be skipped when its engine, project files, evidence, or explicit permission is absent.

**Result status** — `ok`, `warn`, `fail`, `error`, or `skipped`. These describe the command result, not the developer.

**Rush catalog** — Developer term for the source metadata that defines Rush's known commands and engines. Users normally only need `rush --help`.

**SBOM (software bill of materials)** — A machine-readable inventory of software components, usually used for supply-chain review.

**Semantic drift** — A test-risk pattern where a self-healing UI locator binds to a different element and hides a broken user workflow. Rush's related command is experimental and guarded.

**stdio** — Standard input/output pipes used for local process communication. Rush's MCP mode reserves stdout for protocol messages.

**ToolResult** — Rush's consistent result object. See [Result reference](../reference/result-reference.md).

### Context Intelligence Terms
* **TOON**: Ultra-compact pipe-table wire format.
* **CCR**: Context Compression & Restoration chunk storage.
* **HalluGuard**: Static AST import grounding verifier.
* **Ship Gate**: 7-vector pre-flight release readiness cockpit.

### Phases 44–46 Terms
* **Blast Radius**: Downstream impact analyzer.
* **ArchGuard**: Architectural boundary layer linter.
* **Context Packer**: Token-budgeted context assembler.
* **Gain HUD**: Real-time token savings terminal dashboard.


### Phase 47 Terms
* **Test Healer**: Autonomous flaky test repair tool.
* **API Differ**: Public signature breaking change detector.

