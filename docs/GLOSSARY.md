# Glossary of Terms

A comprehensive reference for terms, architectural concepts, and acronyms used across Rush CLI, MCP transports, and documentation.

---

**AI Evaluator** — Specialized tools (Promptfoo, Garak, DeepEval, Guardrails) that probe and grade LLM prompts, agent workflows, and safety policies.

**Canonical ToolResult** — The standard JSON dictionary returned by every Rush tool, containing `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, `raw`, and optional `metadata`.

**Deterministic Aggregation** — Multi-engine result combination with strict status precedence (`error > fail > warn > ok > skipped`), sum of durations, and coordinate-sorted findings.

**Engine Adapter** — An isolated Python class in `src/rush/engines/` that discovers an external executable, constructs bounded CLI arguments, executes the process safely, and normalizes output.

**Execution Permissions** — Granular, explicit opt-in flags (`--allow-network`, `--allow-download`, `--allow-cache-write`, `--allow-build`, `--allow-slow`, `--allow-artifact-write`, `--allow-browser`) required for resource-intensive or mutating operations.

**FastMCP** — The Model Context Protocol SDK used by Rush to register local stdio tools (`rush_<name>`) matching CLI commands.

**Finding Fingerprint** — A deterministic SHA-256 hash calculated from normalized finding attributes (path, line, rule, message) used for tracking and baseline comparisons.

**Graft** — A code knowledge graph tool that traces call graphs and symbol relationships. Rush can consume local Graft context during reviews via `--use-graft`.

**Heuristic Review** — Deterministic Python AST and structure analysis for code maintainability, function lengths, and scaffold markers without requiring an external AI provider.

**Model Context Protocol (MCP)** — An open protocol that enables AI coding assistants (Cursor, Claude Code, Windsurf) to securely query local tools over stdio.

**Maturity Level** — Status classification for catalog tools (`real_adapter`, `importer`, `browser_runtime`, `catalog_only`, `guarded_placeholder`).

**Redaction** — Automated masking of API keys, tokens, and credentials as `[REDACTED]` before findings or logs are emitted.

**Subprocess Isolation** — Executing external tools with `stdin=DEVNULL`, `shell=False`, and timeout limits to protect the MCP transport from pollution or hanging.

**Vibecoder Guardrails** — Specialized quality checks (such as `sloppylint`, `markdown-unfluff`, `git-guard`, `safe-env`, `diff-cover`) designed to catch AI slop, hallucinations, and untracked code artifacts before shipping.

See [Getting Started Glossary](getting-started/glossary.md) and [Result Reference](reference/result-reference.md).
