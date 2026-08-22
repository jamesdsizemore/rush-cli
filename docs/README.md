# Rush documentation

Welcome. Choose the path that matches what you want to accomplish.

## I am new to Rush

1. [Install Rush](getting-started/installation.md).
2. Follow [First run](getting-started/first-run.md).
3. Read the [plain-English glossary](getting-started/glossary.md) whenever a term is unfamiliar.

## I want to use Rush on a project

The [User guide](user-guide/index.md) explains the everyday workflow, results, code and project-file checks, security, test confidence, advanced checks, coding-assistant use, troubleshooting, and FAQs.

- [Subsystem & Bundle Architecture Diagrams](BUNDLE_DIAGRAMS.md)
- [Agentic Rush Knowledge Base](AGENTIC_RUSH.md)
- [Vibecoding with Rush Guide](VIBECODING.md)

Guided lessons:

- [First 10 minutes](tutorials/first-10-minutes.md)
- [Python project](tutorials/python-project.md)
- [TypeScript project](tutorials/typescript-project.md)
- [Mixed-language project](tutorials/mixed-language-project.md)
- [Before a pull request](tutorials/before-a-pull-request.md)
- [CI integration](tutorials/ci-integration.md)
- [AI coding assistant](tutorials/ai-coding-assistant.md)
- [Team adoption](tutorials/team-adoption.md)

## Vibecoding with Rush

- [Vibecoding Master Portal](VIBECODING.md)
- [What is Vibecoding with Rush?](vibecoding/what-is-vibecoding-with-rush.md)
- [The Vibecoder Workflow](vibecoding/the-vibecoder-workflow.md)
- [Setting Up Your AI Agent](vibecoding/setting-up-your-agent.md)
- [Slop-Busting & Hallucination Defense](vibecoding/slop-busting-and-hallucination-defense.md)
- [Instant Fix & Auto-Remediation](vibecoding/instant-fix-and-auto-remediation.md)
- [Token Diet for Vibecoders](vibecoding/token-diet-for-vibecoders.md)
- [Shipping with Swagger](vibecoding/shipping-with-swagger.md)
- [Vibecoder Cheat Sheet & Golden Prompts](vibecoding/cheat-sheet.md)

## Agentic Rush (AI Copilot & Guardrails)

- [Agentic Rush Overview](AGENTIC_RUSH.md)
- [AI Safety & Worktree Sandboxing](agentic-rush/ai-safety-and-sandboxing.md)
- [Patch Remediation & Session Memory](agentic-rush/patch-remediation-and-memory.md)
- [Token Economy & Context Optimization](agentic-rush/token-economy-and-context.md)
- [CodeGraph & Semantic Slicing](agentic-rush/codegraph-and-semantic-slicing.md)
- [Codebase Hygiene & AST Merges](agentic-rush/codebase-hygiene-and-ast-merging.md)
- [Governance & Multi-IDE Rules](agentic-rush/governance-and-multi-ide-rules.md)
- [Pre-Commit Intelligence](agentic-rush/pre-commit-intelligence.md)
- [Multi-Model Consensus & Scorecards](agentic-rush/multi-model-consensus-and-scoring.md)
- [Plugins & Agent Skills](agentic-rush/plugins-and-agent-skills.md)

## I need an exact answer



- [CLI reference](reference/cli-reference.md)
- [Result and exit-code reference](reference/result-reference.md)
- [Configuration reference](reference/configuration-reference.md)
- [Configuration cookbook](reference/configuration-cookbook.md)
- [Engine directory](reference/engine-directory.md)
- [MCP tool reference](reference/mcp-tool-reference.md)
- [Environment variables](reference/environment-variables.md)
- [Compatibility](reference/compatibility.md)

## I want an integration

- [MCP overview](integrations/mcp-overview.md) and [client setup](integrations/mcp-client-setup.md)
- [CI overview](integrations/ci-overview.md) and [GitHub Actions](integrations/github-actions.md)
- [Scripts and automation](integrations/scripts-and-automation.md)

## I care about boundaries

- [Safety overview](safety/safety-overview.md)
- [Permissions](safety/permissions.md)
- [Privacy and data handling](safety/privacy-and-data-handling.md)
- [Security model](safety/security-model.md)

## I contribute or maintain Rush

Start with [Contributor onboarding](developer/contributor-onboarding.md), then use the [Developer guide](DEVELOPER_GUIDE.md), [architecture](developer/architecture.md), [testing guide](developer/testing-guide.md), [Phase 09–19 handoff](developer/phase-09-19-coding-agent-handoff.md), and [maintainer runbooks](maintainers/support-runbook.md). Agents continuing roadmap evolution should consult the handoff and build plan before modifying production code.

## Capability note

Rush's default review is deterministic and local. Optional Graft context is explicit. `review --llm` is not a working model integration; it is a development stub and does not call a provider.

## Context Intelligence, Token Diet & Ship Gates (v0.2.0 / Phases 41–43)

Rush provides zero-overhead, high-signal context optimization and pre-flight release gates for AI coding agents:

* **Command Distillers**: Real-time output compression for `pytest`, `cargo`, `ruff`, and `vitest` stripping noise while preserving exact failure blocks (50–90% token reduction).
* **Compact Wire Serialization (TOON v4.1)**: Pipe-delimited tabular format (`--format toon`) cutting tool response payload size by 40–65%.
* **AST Skeletonizer**: Target-aware symbol outline compressor (`rush token outline <path>`) preserving signatures, decorators, types, and docstrings while eliding method bodies with `...`.
* **Reversible Chunk Store (CCR)**: Lossless SQLite caching (`.rush/cache/ccr.db`) replacing large blobs with `<!-- ccr:chunk:HASH -->` and instant recovery (`rush context retrieve <HASH>`).
* **AST Grounding Verifier (`rush hallu-guard`)**: Real-time import validator ensuring zero phantom packages or hallucinated dependencies exist before code is executed.
* **Pre-Mortem Mistake Memory (`rush context mistakes`)**: Historical Git revert miner extracting past regressions into proactive guardrails.
* **Unified 7-Vector Ship Gate (`rush ship gate` / `rush ship`)**: Parallel release cockpit evaluating repository cleanliness, environment parity, docs integrity, migration hazards, SemVer diffs, package leak prevention, and test pass confidence.

## Context Packing, Telemetry HUD & Blast Radius (Phases 44–46)
* **Graph-Pruned Context Packing (`rush context pack`)**: Packs verbatim focus symbols and depth-1 caller/callee signatures under strict token limits (e.g. `--budget 4000`).
* **Prompt Cache Prefix Aligner (`rush context align-prompt`)**: Structures prompt prefixes ($\ge 1024$ tokens) and adds ephemeral cache-control headers for $\ge 85\%$ KV cache hit rates.
* **Multi-Turn Stale Read Sweeper**: Automatically collapses older turns' verbose file reads into 1-line signatures (`<!-- stale_read: collapsed N lines -->`).
* **Context Gain Terminal HUD (`rush context gain`)**: Interactive Rich TUI displaying gross vs. compressed tokens, compression ratios, and estimated dollar savings.
* **Terse Persona Output Shaper (`rush context persona --set terse`)**: Strips conversational preamble and fluff words, cutting agent output tokens by 40–60%.
* **Transitive Blast Radius Analyzer (`rush blast-radius --path <FILE>`)**: Calculates downstream reachability depth, affected API routes, and recommended test suites before making edits.
* **Declarative Architecture Layer Guard (`rush arch-guard`)**: Enforces clean architecture directional layer matrices (e.g. Domain -> Application -> Infrastructure).
