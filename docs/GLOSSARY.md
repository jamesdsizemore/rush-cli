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

### Context Intelligence & Ship Gate Terms (Phases 41–43)

* **AST Skeletonization**: Replacing function/method implementation bodies with `...` or `/* ... */` while preserving signatures, type annotations, and docstrings for minimal token footprint.
* **BPE (Byte-Pair Encoding)**: Token counting algorithm (`tiktoken` cl100k/o200k) used for exact budget estimation.
* **CCR (Context Compression & Restoration)**: Lossless chunk caching protocol replacing large text blobs with `<!-- ccr:chunk:HASH -->` tags backed by local SQLite storage.
* **Command Distiller**: Regex/AST parser that extracts concise failure frames from verbose build and test outputs (e.g., `pytest`, `cargo`, `vitest`).
* **Grounding Verifier**: Static AST analyzer that confirms imported packages and symbols are physically present in the standard library or installed environment.
* **HalluGuard**: Real-time pre-execution defense preventing AI agents from hallucinating nonexistent packages or typosquatting dependencies.
* **Merkle Invalidator**: AST node hashing mechanism using SHA-256 to invalidate cached memories only when specific AST subtrees change.
* **Mistake Miner**: Bi-temporal Git revert analyzer extracting historical regression post-mortems into active guardrails.
* **Ship Cockpit**: Parallel 7-vector release readiness evaluator checking scratch hygiene, environment parity, docs links, SQL table locks, API compatibility, package safety, and test confidence.
* **TOON (Token-Oriented Object Notation)**: Compact pipe-delimited table serialization format cutting 40–65% of JSON token overhead in MCP tool responses.

### Context Packing, Telemetry & Blast Radius Terms (Phases 44–46)
* **ArchGuard**: Declarative architectural boundary validator enforcing directional dependency rules between software layers.
* **Blast Radius**: The downstream set of modules, API routes, and test suites affected by modifying a target source file.
* **Cache Aligner**: Pre-processor that pads invariant prompt prefixes above 1,024 tokens to maximize provider KV prompt cache hits.
* **Context Packer**: Algorithm that extracts verbatim focus symbols while compressing peripheral code to meet strict token budgets.
* **Stale Read Sweeper**: Optimizer that collapses older conversation turns' file contents into 1-line signatures.
* **Telemetry Ledger**: SQLite database (`.rush/telemetry/tokens.db`) tracking token savings and estimated dollar reductions.
* **Terse Persona**: Agent response shaper stripping conversational fluff and filler words for concise output.
