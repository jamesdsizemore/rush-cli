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

Guided lessons:

- [First 10 minutes](tutorials/first-10-minutes.md)
- [Python project](tutorials/python-project.md)
- [TypeScript project](tutorials/typescript-project.md)
- [Mixed-language project](tutorials/mixed-language-project.md)
- [Before a pull request](tutorials/before-a-pull-request.md)
- [CI integration](tutorials/ci-integration.md)
- [AI coding assistant](tutorials/ai-coding-assistant.md)
- [Team adoption](tutorials/team-adoption.md)

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
