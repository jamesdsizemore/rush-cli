# Frequently Asked Questions (FAQ)

Comprehensive answers to common architectural, operational, and user questions about Rush CLI and its Model Context Protocol (MCP) server.

---

### What is Rush?
Rush is a local-first CLI and stdio-only MCP server that provides a unified, deterministic interface across 77 specialized quality engines, security scanners, linters, test runners, and AI safety evaluators.

### Does Rush replace tools like Ruff, ESLint, Semgrep, or pytest?
No. Rush does not replace native quality engines. Instead, it acts as a safe, normalized front door that discovers existing tools on your `PATH`, runs them with isolated subprocess safety, normalizes findings to a canonical schema, and serves them to developers and AI coding agents.

### Does Rush install missing tools automatically?
No. Rush follows a strict no-implicit-install policy. When an optional engine is absent from your environment, Rush returns a structured `status: "skipped"` with an install hint (e.g. `npm install -D eslint` or `pip install semgrep`).

### How does Rush protect AI coding agents from crashing?
Rush runs as a dedicated stdio MCP server (`rush mcp serve`). It strictly isolates child process execution using `stdin=subprocess.DEVNULL`, so external CLI tools can never consume or corrupt MCP JSON-RPC protocol frames. All diagnostics are emitted to `stderr`, leaving `stdout` pure for JSON-RPC.

### How are secrets handled?
All findings and logs passed through Rush are normalized and automatically redacted. Credentials, private keys, high-entropy tokens, and passwords discovered by engines like TruffleHog or Gitleaks are replaced with `[REDACTED]` in output.

### What are the permission flags?
Rush enforces explicit execution permissions for potentially slow, heavy, or mutating operations:
- `--allow-network`: Live network communication (e.g. k6 load tests, URL link checks).
- `--allow-download`: Fetching vulnerability databases or schemas.
- `--allow-cache-write`: Writing engine rule caches.
- `--allow-build`: Compiling code or CodeQL analysis databases.
- `--allow-slow`: Long-running test, mutation, or fuzz runs.
- `--allow-artifact-write`: Overwriting or mutating baseline artifacts and report files.
- `--allow-browser`: Launching browser engines (Playwright, Chromium/WebKit/Firefox).

### Does `rush review --llm` send code to external AI providers?
No. In the current release, `rush review --llm` is a development stub that returns deterministic placeholder information and makes zero outbound network or API calls. Default review uses fast, deterministic local heuristics.

For more questions, see the [User Guide FAQ](user-guide/faq.md) and [Troubleshooting Guide](user-guide/troubleshooting.md).

## Context Intelligence, Token Reduction & Ship Gates (Phases 41–43)

### How does Rush reduce token consumption on test failures?
Rush uses specialized command distillers (`src/rush/token_economy/distillers/`) for `pytest`, `cargo`, `ruff`, and `vitest`. When a test suite fails, Rush intercepts the raw stdout/stderr, extracts only the failure headers, assertion lines, and stack frames, and strips thousands of lines of noisy pass indicators, saving 50% to 90% of prompt tokens.

### What is TOON and how does it save tokens over JSON?
TOON (Token-Oriented Object Notation) v4.1 formats arrays of dictionaries into markdown pipe tables (`|col1|col2|`). Because JSON repeats dictionary keys on every single object, TOON eliminates repetitive key overhead, cutting payload token counts by 40% to 65%.

### How does CCR (Context Compression & Restoration) work?
When tool responses or logs exceed token thresholds, Rush stores the verbatim content in `.rush/cache/ccr.db` and replaces it with `<!-- ccr:chunk:<hash> -->`. If the AI agent or developer needs the full raw payload, it can retrieve it at any time using `rush context retrieve <hash>` or the FastMCP `rush_context_retrieve` tool.

### What does `rush hallu-guard` do?
`rush hallu-guard` parses Python Abstract Syntax Trees across your codebase or proposed patches and checks every `import` and `from ... import` against `sys.stdlib_module_names` and `importlib.metadata.distributions()`. If an AI agent attempts to import a package that is neither in Python's standard library nor installed in your environment, Rush flags it immediately before runtime.

### What checks are included in `rush ship gate`?
`rush ship gate` (or `rush ship`) evaluates 7 vectors in parallel:
1. **Clean**: Ensures no uncommitted scratch or temporary files exist.
2. **Env**: Confirms all `os.getenv` variables in code are declared in `.env.example`.
3. **Docs**: Checks that all relative markdown links in `docs/` point to existing files.
4. **Migration**: Analyzes SQL migration files for table-locking DDL hazards.
5. **SemVer**: Compares public API signatures to prevent accidental breaking changes.
6. **Pack**: Scans source trees to prevent leaking `.env` or private keys into release builds.
7. **Gate**: Aggregates all vectors into a 0–100% release confidence score.

## Context Packing, Telemetry & Blast Radius (Phases 44–46)

### How does `rush context pack` help with large refactors?
Instead of reading 10 separate files and exceeding context limits, `rush context pack --path <file> --symbol <symbol> --budget 4000` packages the exact target implementation verbatim and includes compressed AST skeletons of surrounding dependencies, fitting complex module hierarchies into a single compact prompt.

### What is the purpose of `rush context align-prompt`?
AI providers (Anthropic, OpenAI, Gemini) offer up to 85%+ discounts on prompt tokens if the static prefix is identical and meets minimum token boundaries (typically 1,024 tokens). `rush context align-prompt` ensures your prompt prefix meets this threshold and injects proper cache control tags.

### What does `rush blast-radius` calculate?
`rush blast-radius --path <file>` parses all imports across the codebase to find every file, API endpoint, and test file that depends on the changed file, assigning a risk score (LOW, MEDIUM, HIGH) and recommending specific tests to run.

### How does `rush arch-guard` enforce clean architecture?
`rush arch-guard` checks all module imports against layer definitions (e.g. Domain, Application, Infrastructure). If a Domain entity attempts to import from Infrastructure or Presentation, `rush arch-guard` blocks the violation with a non-zero exit code.


## Test Healing & API Contracts (Phase 47)
### How does `rush test-heal` work?
It executes multiple perturbation runs in a sandboxed git worktree, diagnosing non-deterministic timing issues and suggesting fixes.

### What does `rush api-diff` protect against?
It prevents breaking SDK/API changes by verifying that public function/class signatures have not removed arguments or symbols compared to the base branch.



## DB Drift & Code Simplification (Phase 48)
### What does `rush db-drift` catch?
It flags ORM fields added to models that have no corresponding `sa.Column` or SQL `ALTER TABLE` statement in migration files.

### How does `rush simplify` assist developers?
It identifies monolithic functions with cognitive complexity over threshold and outlines modular sub-function boundaries.

