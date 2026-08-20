# Findings & Decisions — rush

## Requirements

Captured from the user's request:

- **Name:** rush — companion app to headcleaner (separate repo).
- **Form factor:** CLI + MCP server.
- **Agentic surface:** MCP only. No other agent/SDK plumbing.
- **Domain:** code review, linting, code formatting, testing, security.
- **Target consumers:** coding agents (Claude Code, Cursor, Windsurf, etc.) invoking rush as an MCP server from their own process.
- **Project location:** new folder `C:\Users\james\developer\rush-cli`, with a fresh `git init`.

Implied requirements:

- CLI subcommands for humans (so devs can run `rush lint ./src` the same way the MCP tool would).
- Structured I/O — MCP requires JSON-serializable inputs/outputs; the CLI should emit the same structured payloads (with a `--human` flag for pretty printing).
- Local-only, no network calls, no daemon.
- Single-binary-ish: `uv tool install rush-cli` (or `uvx rush`) should be the install story.
- Stdio MCP server must NEVER write to stdout except JSON-RPC frames — all logs go to stderr.

## Research Findings

### MCP transport choice (confirmed with user)

- **stdio**: `rush mcp serve` runs a local stdio MCP server. Zero infra, works in Claude Code / Cursor / Windsurf out-of-the-box via command+args. — **Selected.**
- HTTP/SSE: rejected — adds daemon/auth story; remote access not requested.
- Hybrid (stdio default + http/sse flags): rejected — more surface to build/test without a concrete remote-access need.

### MCP Python SDK

- Package: `mcp` (https://modelcontextprotocol.io), version **1.28.1** available on PyPI.
- Submodules we need:
  - `mcp.server.fastmcp.FastMCP` — high-level server API, JSON-schema I/O, stdio transport.
  - `mcp.server.stdio` — stdio plumbing (lower-level, but worth knowing).
- `FastMCP.__init__` takes a server name string; tools registered via `@mcp.tool()` decorator on async functions whose type-annotated args/return become the JSON schema.
- Logging: stdout is the MCP transport. Any `print()` or stdlib `logging.StreamHandler(sys.stdout)` corrupts the stream. The SDK's own logger goes to stderr by default; we'll route everything through `logging` → stderr.

### Headcleaner-cli parallels (for reuse, not import)

- Same stack: Python 3.12 + uv + pyproject.toml + click + rich + pytest.
- Same neon palette: cyan `#22D3EE` primary, pink `#EC4899` active/warning, purple `#A855F7` info. **No red, no yellow.**
- Same layout pattern: `src/rush/{cli,mcp,tools,engines,config,theme}.py`.
- Same trust stance philosophy: don't auto-claim review by a human; rush's `review` v0.1 returns `status: heuristic` (not `reviewed`). `review-needed` findings render in neon yellow so humans (and agents reading rendered output) can spot them.
- AGENTS.md will mirror headcleaner's structure so the two projects feel like siblings.
- **Palette divergence:** headcleaner = cyan + pink + purple. Rush = cyan + green + yellow. Both ban red. Both share cyan as primary. The two tools are visually related but distinct.

### Per-language engine matrix (v0.1, Python + JS/TS — **expanded after deep research, 109 tools surveyed**)

> Source: 14 parallel `gh search repos` queries across AI-slop, MCP, SAST, SCA,
> secret-scanning, IaC, linters, formatters, type checkers, dead code, complexity,
> tests, security, supply chain, commit/style, license, pre-commit, code review.
> **1,055 repos returned, 740 categorized as relevant, 109 curated as shippable.**
> Raw data: `research/raw_search_*.txt`, consolidated: `research/consolidated.json`,
> bucketed: `research/bucketed.json`, final picks: `research/curated.json`.

Selection rules per file extension: `.py`/`.pyi` → Python engines; `.js`/`.jsx`/`.mjs`/`.cjs`/`.ts`/`.tsx` → JS/TS engines; everything else falls back to heuristic-only review.

#### v0.1 (ship now — what was already planned)

| Tool | Python engine | JS/TS engine | Notes |
|------|---------------|--------------|-------|
| review | Heuristics (`--llm` flag → calls configured model) | Same heuristics + same `--llm` flag | Heuristics: file size, TODO density, missing docstrings, naming, cyclomatic smell. LLM call reads `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` from env when set. |
| lint | `ruff check --output-format=json` | `eslint --format=json` (auto-detect flat config vs legacy) | If engine CLI not on PATH, surface a clear install hint, don't fail silently. |
| format | `ruff format` | `prettier --write` | `prettier` also handles JSON/MD/YAML/CSS/HTML — bonus for free |
| test | `pytest` (parse summary; `--json-report` if plugin present) | `vitest run --reporter=json` preferred; fallback `npm test --silent -- --reporter=json` | Detect `package.json` test runner before choosing |
| security | `pip-audit --format=json` | `npm audit --json` | `npm audit` works for non-npm manifests that still resolve; warn otherwise |

#### v0.2 candidates (backlog — not in v0.1 plan, listed for Phase 6+ expansion)

| New tool | Engine(s) | Why it's a strong addition | Notes |
|---|---|---|---|
| `secrets` | `gitleaks` (Go, 28.7k★) + `trufflehog` (Go, 27.5k★ — verifies creds, not just detects) | Secret scanning is **security**'s missing twin. rush's `security` is currently SCA-only; secrets live in a separate conceptual bucket. | TruffleHog validates against the live API; gitleaks is the de-facto. Either works. v0.2 picks gitleaks for breadth. |
| `iac` | `tflint` (Go, 5.8k★) + `checkov` (Python, 8.9k★) | IaC misconfigs are a real attack vector. Auto-detect Terraform (`*.tf`) and Docker (`Dockerfile`) files and run the matching engine. | tflint for linting/checkov for security policy. |
| `containerfile` | `hadolint` (Haskell) | Best Dockerfile linter. | Single binary, JSON output. |
| `markdown` | `markdownlint-cli` (JS, 1.1k★) or `markdownlint-cli2` (faster) | The user-facing surface of most repos includes `.md`. We lint it for free when `prettier` is on PATH, but markdownlint is the canonical. | Detect via repo file extensions. |
| `actions` | `actionlint` (Go, 4.1k★) | GitHub Actions YAML is its own lint domain with shell injection risk. | Auto-detect `.github/workflows/*.yml`. |
| `yaml` / `json` | `spectral` (TS, 3.2k★) | JSON/YAML/OpenAPI linter. Catches schema drift in `rush.toml` itself. | Optional. |
| `sql` | `sqlfluff` (Python, 9.9k★) | SQL is everywhere. Multi-dialect lint+format with one tool. | Optional. |
| `jinja` / `templates` | `djlint` (Python, 945★) | HTML template linter. Optional but cheap. |  |
| `dead` | `vulture` (Python, 4.8k★) + `knip` (TS, 12k★) | Dead-code detection per language. Output as a `dead` tool that returns findings without changing files. |  |
| `unused-deps` | `depcheck` (JS, 4.9k★) + reuse `pip-audit --dry-run` deps | Distinct from `dead` — finds packages you don't import. |  |
| `coverage` | `coveragepy` (Python, 3.4k★) for Python + `vitest --coverage` for JS/TS | Coverage is half of `test`'s story. | Returns as a `coverage` metric in the `test` tool output. |
| `mutation` | `mutpy` (Python, 368★) for Python + `gremlins` (Go, 386★) for Go | Mutation testing finds tests that don't actually test anything. |  |
| `e2e` | `playwright` (TS, 94.6k★) | End-to-end browser testing — distinct from unit test. |  |
| `typecheck` | `mypy` (Python, 20.6k★) or `pyright` (15.6k★ — faster) for Python; `tsc --noEmit` for TS | Static type checking. |  |
| `complexity` | `radon` (Python) for cyclomatic complexity; `jscpd` (TS, 6k★) for copy-paste | `jscpd` is **especially compelling** — copy-paste detection across 223 formats. |  |
| `ai-slop` | `sloppylint` (Python, 86★) — heuristics (over-engineering, hallucination, dead code) for Python; heuristic-only for other langs in v0.2 | The user explicitly called this out. Heuristic slop detection complements the heuristic `review`. | Output as a separate `slop` tool so agents can filter. |
| `ai-review` (separate from `review`) | `sourcery` (1.9k★), `kodus-ai` (1.3k★), or `codeball` (324★) | Cloud-hoster or self-host LLM review. Distinct from rush's `--llm` flag because these are dedicated products. | v0.2 opt-in only; requires API key. |
| `sbom` | `cyclonedx/cdxgen` (JS, 1.2k★) | Generate CycloneDX SBOM from repo. Distinct from vuln scanning. |  |
| `osv` | `osv-scanner` (Go, 10.8k★) | OSV.dev-backed vuln scanning across ecosystems (broader than `pip-audit`/`npm audit`). | v0.2 candidate to replace pip-audit/npm-audit as the security default. |
| `commit-msg` | `commitlint` (TS, 18.7k★) | Conventional Commits enforcement. | Optional pre-commit hook integration. |
| `license` | `pip-licenses` or `conda-license` for Python; `license-checker` (JS, 1.7k★) for JS/TS | License compliance check on deps. | Optional. |

#### Per-language coverage (research-driven, not just Python+JS/TS)

| Language | Lint | Format | Test | Type-check | Dead code |
|---|---|---|---|---|---|
| Python | ruff | ruff/black | pytest, hypothesis (PBT) | mypy, pyright | vulture, dead |
| JavaScript / TypeScript | eslint, biome, oxlint | prettier, biome | vitest, jest, playwright, fast-check (PBT) | tsc | knip, depcheck |
| Go | golangci-lint | gofmt / goimports | go test, gremlins (mutation) | go vet / staticcheck | unused |
| Rust | clippy | rustfmt | cargo test, quickcheck (PBT), tarpaulin (cov) | rustc | cargo-udeps |
| Ruby | rubocop | rubocop | rspec, minitest | sorbet | unused |
| Java | checkstyle, spotbugs | google-java-format | junit, junit-quickcheck (PBT) | errorprone | unused |
| Kotlin | ktlint, detekt | ktlint / spotless | kotlin.test | kotlinc | unused |
| Swift | SwiftLint | SwiftLint | XCTest, swift-snapshot-testing | swiftc | peripheral |
| PHP | phpcs, phpstan | php-cs-fixer | phpunit | psalm, phpstan | unused |
| C# | dotnet format, roslyn analyzers | dotnet format, csharpier | xunit, Verify (snapshot) | roslyn | unused |
| Elixir | credo | mix format | exunit, stream_data (PBT) | dialyzer | unused |
| Dart / Flutter | dart analyze / very_good_analysis | dart format | flutter test | dart analyze | unused |
| Scala | scalafix | scalafmt | scalatest, scalacheck (PBT) | scalac | scapegoat |
| Nix | statix, deadnix | alejandra | none | nix-instantiate | deadnix |
| SQL | sqlfluff | sqlfluff | tSQLt, pgTAP | — | — |
| Templates (Jinja/Django) | djlint | djlint | — | — | — |
| Dockerfile | hadolint | — | container-structure-test | — | — |
| Terraform | tflint | terraform fmt | terratest | tflint | — |
| GitHub Actions | actionlint | — | — | — | — |
| YAML / JSON / OpenAPI | spectral | yamllint? | — | — | — |

**Routing rule:** rush detects language by extension, looks for the engine on PATH, and uses the highest-priority available tool. Engines missing from PATH surface as `{status: "skipped"}`.

#### Testing-category expansion

| New tool | Engine(s) | Why |
|---|---|---|
| `pbt` (property-based testing) | `hypothesis` (Python, 8.9k★), `fast-check` (JS, 5.1k★), `quickcheck` (Rust, 2.8k★), `stream_data` (Elixir) | Generates hundreds of cases from invariants; catches edge cases unit tests miss. Distinct from `test` (which runs whatever tests exist). |
| `visual` (visual regression) | `jest-image-snapshot` (JS, 3.9k★), `loki` (JS, 1.9k★), `reg-suit` (TS, 1.3k★) | Catches UI regressions. Auto-detected on `*.test.tsx` / `*.spec.tsx` files or via config flag. |
| `snapshot` | `insta` (Rust, 2.9k★), `Verify` (C#, 3.5k★), `swift-snapshot-testing` (Swift, 4.3k★), `inline-snapshot` (Python, 749★) | Different from visual — text/data snapshot diffing. |
| `flaky` (flaky-test detection) | `ctrf-io/github-test-reporter` (TS, 371★), `WithSecureOpenSource/flaky-tests-detection` (Python, 26★) | Tracks test outcomes across runs to flag inconsistent tests. |
| `fuzz` | `AFLplusplus` (C, 6.7k★), `oss-fuzz` (orchestrator, 12.6k★), `ffuf` (Go, 16.5k★ — web fuzzing) | Finds crashes/panics in code via randomized input. |
| `load` | `k6` (Go, 31.3k★), `locust` (Python, 28.1k★), `vegeta` (Go, 25.1k★), `gatling` (Scala, 6.9k★) | Performance / capacity testing. Distinct from `test`. |
| `contract` | `pact-python` / `pact-js` / `pact-go` | Consumer-driven contract testing for API integrations. |
| `semantic-drift` (NEW — user-requested) | `svitaliy/SemanticDriftDetector` (C# .NET, 0★ but well-documented challenge repo) | **Detects when an AI self-healing test framework re-binds locators and silently keeps a broken workflow passing.** Anchors test intent to visible semantics instead of fragile IDs. v0.3 candidate — niche but exactly rush's domain (test correctness, not just test execution). |

#### MCP-server precedents (validates rush's architecture)

| Repo | Stars | What it does | Takeaway for rush |
|---|---|---|---|
| `modelcontextprotocol/python-sdk` | 24,024 | Official Python SDK | This is what we use. |
| `modelcontextprotocol/servers` | 89,611 | Canonical MCP server catalog | Reference for tool schema patterns |
| `microsoft/mcp-for-beginners` | 16,999 | MCP curriculum | Best learning source for agents |
| `ast-grep/ast-grep-mcp` | 451 | Structural-search MCP server | **Direct proof that MCP servers wrapping a CLI tool work** — rush's exact pattern |
| `semgrep/mcp` | 683 | Official Semgrep MCP | **Direct competitor / partner** — confirms SAST-as-MCP is real |
| `microsoft/playwright-mcp` | 36,185 | Playwright MCP server | **Test execution via MCP is a major pattern** — rush's `test` tool may live alongside this |
| `executeautomation/mcp-playwright` | 5,632 | Alt Playwright MCP | Same pattern, second implementation |
| `ChromeDevTools/chrome-devtools-mcp` | 49,264 | Chrome DevTools Protocol as MCP server | Pattern: DevTools → MCP |
| `hangwin/mcp-chrome` | 12,307 | Chrome MCP server (extension-based) | Another browser-as-MCP precedent |
| `theserverlessdev/wsc` | 4 | Prose-linter + AI-slop MCP server | Tiny but exactly our domain — proves the niche exists |
| **`NanoNets/Graft`** | **3,096** | **Context-graph MCP server for Claude Code/Cursor/Codex/Gemini — exposes `graft_find_code`, `graft_trace_calls`, `graft_repo_map`, `graft_check_freshness`, `graft_file_api`, `graft_find_all` over MCP. Vendor-neutral LLM (OpenAI/Anthropic/OpenRouter/LiteLLM/local). 21 languages, tree-sitter structural pass is $0 and key-free.** | **This is rush's direct conceptual neighbor.** See dedicated section below. |

#### Graft — rush's conceptual neighbor (user-requested)

- Repo: https://github.com/NanoNets/Graft (TypeScript, 3,096★, MIT, NanoNets, July 2026)
- Tagline: *"Turbocharge Claude Code, Cursor, Codex, Gemini & every coding agent: faster, cheaper, with contextual understanding specific to your codebase."*
- What it does: builds a **context graph** of your repo as a folder of linked markdown files (one node per system/API/concept). Each node holds: summary, crux (the few lines that matter), sources, typed links, notes. Graph is deterministic-tree-sitter + optional-LLM. Tree-sitter pass is `$0, no key, no network`.
- CLI surface (relevant to rush): `graft build`, `graft ask`, `graft grep`, `graft map`, `graft callers`, `graft skeleton`, `graft check`, `graft viz`, `graft init`, `graft mcp`, `graft upgrade`.
- **MCP tools Graft exposes (the exact shape rush should learn from):**
  - `graft_find_code` (question) — ranked nodes with file:line
  - `graft_file_api` (file path) — every signature in that file, no bodies
  - `graft_trace_calls` (symbol) — who depends on it / blast radius
  - `graft_find_all` (regex) — every hit, grouped by enclosing symbol
  - `graft_repo_map` — first look at unfamiliar repo (clusters, hubs, hotspots)
  - `graft_check_freshness` — has the graph drifted from the code?
- Languages: 21 supported via tree-sitter (TS/JS/JSX/TSX/Python/Go/Java full-fidelity; Rust/C/C++/C#/Ruby/PHP/Kotlin/Scala/Swift/Elixir/Solidity/OCaml/Zig/Dart/Clojure broad). Compiler-grade edges via `--lsp` opt-in (rust-analyzer, clangd, gopls, pyright, typescript-language-server).
- **Benchmarks (real, from README):**
  - SWE-bench Verified (50 instances, Claude Sonnet 5): 54% → 66% correctness (+12 pts) with **25% fewer tool calls, 23% fewer tokens, 32% less wall-clock**
  - 162-run controlled sweep: -42% tokens, -46% tool calls, -60% latency, correctness equal-or-better
- **Why this matters for rush:**
  1. **Pattern validation.** Graft is rush's exact architectural template: CLI + MCP server for coding agents, vendor-neutral LLM, JSON output, deterministic base + LLM-augmented. rush is doing the same thing in the **code-quality** domain (review/lint/test/security) where graft does it in the **code-understanding** domain.
  2. **Integration opportunity.** rush's `review` tool could call graft's MCP to *ground* its heuristic review in actual symbol-level context (callers, dependencies, blast radius). rush's `lint` could read graft's code graph to scope lint runs to only-changed-symbols and their blast radius (saves tokens).
  3. **Competitive positioning.** They don't compete — they compose. Rush = "is this code good?", Graft = "what does this code do?". A coding agent using both gets full coverage.
  4. **Tool-schema precedent.** Graft's 6 MCP tools are the cleanest schema design rush has seen so far. rush's tools should follow the same pattern: terse tool name (`verb_noun`), single natural-language input, structured output with file:line citations.
- **How rush should relate to Graft (v0.2 plan):**
  - Add a `graft` integration module: detect `graft` on PATH / detect `graft/` folder, offer to use it as context provider
  - rush's `review` tool gets a `--use-graft` flag that augments heuristics with graft's symbol graph
  - rush's MCP server can optionally advertise "pairs well with `npx @nanonets/graft`" in its tool descriptions
  - **No code dependency on Graft.** rush stays standalone; integration is via MCP-to-MCP if both servers are loaded in the same agent session.

#### Cross-language engines worth knowing about (not in v0.1)

- **ast-grep** (Rust, 15.5k★) — structural search/replace across 10+ languages. Faster than semgrep for custom rules; **MCP-ready**. Should become rush's `search` tool in v0.2.
- **biomejs/biome** (Rust, 25.6k★) — unified lint+format for JS/TS in a single Rust binary. Alternative to eslint+prettier.
- **oxc-project/oxc** (Rust, 22.3k★) — high-perf JS/TS toolchain (parser, linter, formatter, minifier). Emerging.
- **semgrep/semgrep** (OCaml, 16.2k★) — multi-language SAST. Worth a rush `sast` tool.
- **aquasecurity/trivy** (Go, 37.4k★) — does vulns + misconfigs + secrets + SBOM in one binary. Could be a single `security` mega-engine for v0.2.

Engine discovery: each tool checks for its CLI on PATH and skips with a structured `{status: "skipped", reason: "..."}` if missing — agents can react without hard failures.

#### v0.1 tool count vs. v0.2 tool count

| Phase | Tools shipped | Rationale |
|---|---|---|
| v0.1 | 5 (review, lint, format, test, security) — Python + JS/TS only | Original plan: tight scope, prove MCP architecture works |
| v0.2 | **+27** (secrets, iac, containerfile, markdown, actions, yaml, sql, dead, coverage, mutation, e2e, typecheck, complexity, ai-slop, sbom, commit-msg, pbt, visual, snapshot, flaky, fuzz, load, contract, semantic-drift, **ci**, **release**) | High-value adjacent domains identified by research; covers more languages, more testing categories, and CI/CD |
| v0.3 | `ai-review` (cloud), `osv` (replace security engines), `license`, `semantic-drift` polish, renovate/dependabot integration | Lower priority / requires API keys / niche domain |

#### Language coverage vs. v0.1 scope

| Phase | Languages | Why |
|---|---|---|
| v0.1 | Python, JS/TS | Confirmed by user |
| v0.2 | + Go, Rust, Ruby, Java, Kotlin, Swift, PHP, C#, Elixir, Dart, Scala, Nix | Engines are CLI-first and on PATH for most devs; rush becomes language-agnostic via the engine matrix |
| v0.3 | + Haskell, C/C++, Lua | Lower priority; smaller ecosystems |

#### Semantic drift detection (user-requested, `svitaliy/SemanticDriftDetector`)

- Repo: https://github.com/svitaliy/SemanticDriftDetector (C# / .NET, Playwright, June 2026)
- Status: 0★ but it answers a real challenge by Christian DeLaphante
- What it does: demonstrates that **AI self-healing test locators can mask real bugs** by re-anchoring to a similar-looking element after a UI swap. The detector anchors to visible intent and asserts `intent → outcome` invariants across N loads.
- Why it matters for rush: rush's `test` tool currently executes tests. Adding a `semantic-drift` tool would audit tests for exactly this class of false-pass bug — a **test correctness** tool, not a test execution tool. Niche but exactly rush's lane.
- Implementation: would need a Playwright/Puppeteer backend in rush's MCP (or wrap `SemanticDriftDetector.csproj` if .NET is on PATH). Add to v0.2/v0.3 backlog.
- Related challenge: https://github.com/DeLaphante/FidelityTests/blob/main/AISemanticBug.html (the buggy page the detector targets)

### Output schema (single source of truth)

Every tool, whether called from CLI or MCP, returns the same dict:

```python
{
    "tool": "lint",               # one of: review, lint, format, test, security
    "engine": "ruff",             # engine name
    "engine_version": "0.6.9",    # captured at runtime
    "status": "ok",               # ok | warn | fail | error
    "duration_ms": 412,
    "summary": "12 issues, 2 auto-fixable",
    "findings": [                 # uniform shape across tools
        {
            "path": "src/foo.py",
            "line": 42,
            "column": 8,
            "rule": "E501",
            "severity": "warn",  # info | warn | error
            "message": "line too long",
            "fix": null          # or { "edits": [...] } when engine provides it
        }
    ],
    "raw": "<engine-native payload, optional>",
}
```

MCP tool return = JSON-serialized version. CLI default = `rich.table.Table`; `--json` flag = the same dict printed.

### Config file shape (`rush.toml`)

```toml
[project]
src = ["src"]                # paths to scan when invoked bare
test = ["tests"]
exclude = ["**/.venv/**", "**/node_modules/**"]

[tools.lint]
engine = "ruff"
args = ["--select", "E,F,W,I"]

[tools.format]
engine = "ruff"
check = false               # if true, exit non-zero when changes would be made

[tools.test]
engine = "pytest"
args = ["-q"]

[tools.review]
max_file_lines = 400
fail_on = ["todo-density-high"]

[tools.security]
engine = "pip-audit"
ignore = []
```

Discovery: walk up from cwd to git root, pick first `rush.toml`. CLI flags override file values.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| `mcp` Python SDK 1.28.x via PyPI | Official, stdio-first, FastMCP maps 1:1 to our tool function shape |
| One tool function per tool, called by both CLI and MCP | Single source of truth; CLI is just a wrapper that pretty-prints the same dict |
| JSON output is the canonical schema; CLI uses `--json` for raw | Agents always get JSON; humans opt into a pretty view |
| Logs go to stderr, NDJSON, gated by `RUSH_LOG_LEVEL` | MCP stdout is sacred; surface debug info without breaking transport |
| Config discovery: walk up to git root | Standard CLIs (eslint, prettier, ruff) all do this; matches user mental model |
| `review` v0.1 = heuristics; `--llm` flag calls configured model when API key present | User confirmed: heuristics now, LLM behind opt-in flag (deterministic default; agents can opt into real review) |
- **v0.1 ships Python + JS/TS engines (ruff/pytest/pip-audit + eslint/prettier/vitest/npm-audit)** | User confirmed: bigger v0.1 surface; engines auto-detected per file ext |
| Rush palette: **neon cyan `#22D3EE` (primary)** → **neon green `#22FF88` (secondary, active/info)** → **neon yellow `#FFE600` (tertiary, review-needed/warning/soft accent)** | User confirmed; in-use order from main to least. Yellow replaces the headcleaner "no yellow" rule — review-needed and warnings now render in neon yellow. Red stays banned. |
| Separate repo, no shared code with headcleaner-cli | Shared name only; both stay independently shippable. Shared palette/AGENTS.md patterns documented, not imported |
| v0.1 ships the **original 5 tools** (review/lint/format/test/security); v0.2 adds **16 more** identified by research (secrets/iac/containerfile/markdown/actions/yaml/sql/dead/coverage/mutation/e2e/typecheck/complexity/ai-slop/sbom/commit-msg) | Keeps v0.1 tight while preserving a clear expansion roadmap backed by 109 curated real-world tools |
| **MCP architecture is validated by 6 existing real-world MCP servers** (ast-grep-mcp, semgrep/mcp, microsoft/playwright-mcp, etc.) | Confirms rush's "MCP is the only agentic surface" decision isn't novel — it's the established pattern |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| `pydantic_core` import error in Hermes system venv | Not our problem — rush uses its own uv-managed `.venv`; will pin `mcp` resolution fresh on `uv sync` |
| Requested `context` CLI is absent and codegraph has no index | `rtk` is installed and used for compact repository status. Use Graft's local key-free wiring graph for project context; do not create a codegraph index unless the user asks. |

## v0.2 Implementation Session — 2026-08-17

- `rtk` is available at `C:\Users\james\.local\bin\rtk`; it was used for compact Git status.
- No `context`, `ctx`, `code-context`, or `context7` executable is available on PATH.
- The codegraph MCP service cannot inspect this repository because there is no `.codegraph/` index; indexing is explicitly the user's decision.
- `graft` is installed. A key-free, non-deep structural graph was built in `.hermes/graft/`:
  - 29 Python files, 201 nodes, 506 edges, and 29 cards.
  - Graft automatically added `.hermes/graft/` to `.gitignore` as a local cache.
  - `graft check` reports the wiring graph is fresh.
- Graft located the v0.2 core refactor seam: `src/rush/tools/common.py` for subprocess/result utilities; `src/rush/tools/lint.py` and `src/rush/tools/format.py` for duplicated file/routing aggregation; `src/rush/tools/__init__.py`, `src/rush/cli.py`, and `src/rush/mcp.py` for fixed tool registration; and `src/rush/engines/__init__.py` for the fixed engine registry.

## Resources

- MCP spec / docs: https://modelcontextprotocol.io
- `mcp` Python SDK: https://github.com/modelcontextprotocol/python-sdk
- ruff: https://docs.astral.sh/ruff/
- pip-audit: https://pypi.org/project/pip-audit/
- Sibling reference: `~/developer/headcleaner-cli/AGENTS.md` (layout, palette, trust stance — read for inspiration, do NOT import)

## Visual / Browser Findings

- [ ] (none yet — build-from-scratch task)

## Resources (post-research)

### Raw research artifacts (in `research/`)

- `consolidated.json` — 1,055 unique repos across all search queries
- `bucketed.json` — 740 categorized into 18 relevant domains
- `curated.json` — 109 picks across 19 categories (the v0.1 + v0.2 candidate list)

### Tool repositories (canonical)

**Lint / format / type-check (Python):**
- ruff: https://github.com/astral-sh/ruff (49,227★)
- mypy: https://github.com/python/mypy (20,595★)
- pyright: https://github.com/microsoft/pyright (15,588★)
- vulture: https://github.com/jendrikseipp/vulture (4,767★) — dead code
- basedpyright: https://github.com/DetachHead/basedpyright (3,531★)
- mutpy: https://github.com/mutpy/mutpy (368★) — mutation testing
- coveragepy: https://github.com/coveragepy/coveragepy (3,409★)

**Lint / format / dead-code (JS/TS):**
- prettier: https://github.com/prettier/prettier (52,203★)
- eslint: https://github.com/eslint/eslint (27,457★)
- biome: https://github.com/biomejs/biome (25,588★)
- oxc: https://github.com/oxc-project/oxc (22,340★)
- knip: https://github.com/webpro-nl/knip (11,965★) — unused files/deps/exports
- vitest: https://github.com/vitest-dev/vitest (16,961★)
- markdownlint-cli2: https://github.com/DavidAnson/markdownlint-cli2 (900★)
- depcheck: https://github.com/depcheck/depcheck (4,929★)
- commitlint: https://github.com/conventional-changelog/commitlint (18,694★)

**Multi-language static analysis:**
- semgrep: https://github.com/semgrep/semgrep (16,244★)
- ast-grep: https://github.com/ast-grep/ast-grep (15,547★) — **also MCP-wrapped**
- sqlfluff: https://github.com/sqlfluff/sqlfluff (9,855★)
- djlint: https://github.com/djlint/djLint (945★) — Django/Jinja

**Security / SCA / secrets / IaC:**
- trivy: https://github.com/aquasecurity/trivy (37,435★) — mega-tool (vulns/secrets/SBOM/IaC)
- gitleaks: https://github.com/gitleaks/gitleaks (28,760★)
- trufflehog: https://github.com/trufflesecurity/trufflehog (27,488★) — verifies creds live
- osv-scanner: https://github.com/google/osv-scanner (10,840★)
- checkov: https://github.com/bridgecrewio/checkov (8,945★)
- dependency-check: https://github.com/dependency-check/DependencyCheck (7,664★)
- tflint: https://github.com/terraform-linters/tflint (5,789★)
- terrascan: https://github.com/tenable/terrascan (5,213★)
- detect-secrets: https://github.com/Yelp/detect-secrets (4,621★)
- actionlint: https://github.com/rhysd/actionlint (4,139★) — GitHub Actions

**AI-slop / AI-review:**
- sloppylint: https://github.com/rsionnach/sloppylint (86★) — Python AI-slop detector
- flamehaven01/AI-SLOP-Detector: https://github.com/flamehaven01/AI-SLOP-Detector (78★)
- theserverlessdev/wsc: https://github.com/theserverlessdev/wsc (4★) — prose + slop + MCP
- sourcery: https://github.com/sourcery-ai/sourcery (1,855★) — AI review
- kodus-ai: https://github.com/kodustech/kodus-ai (1,309★) — AI review
- codeball: https://github.com/sturdy-dev/codeball-action (324★) — AI review
- brooks-lint: https://github.com/hyhmrright/brooks-lint (1,361★) — book-grounded review

**MCP servers (validates rush's architecture):**
- python-sdk: https://github.com/modelcontextprotocol/python-sdk (24,024★) — what rush uses
- servers catalog: https://github.com/modelcontextprotocol/servers (89,611★)
- mcp-for-beginners: https://github.com/microsoft/mcp-for-beginners (16,999★)
- ast-grep-mcp: https://github.com/ast-grep/ast-grep-mcp (451★)
- semgrep/mcp: https://github.com/semgrep/mcp (683★)
- playwright-mcp: https://github.com/microsoft/playwright-mcp (36,185★)
- mcp-playwright: https://github.com/executeautomation/mcp-playwright (5,632★)

**Pre-commit / hooks:**
- pre-commit: https://github.com/pre-commit/pre-commit (15,507★)
- prek: https://github.com/j178/prek (8,265★) — Rust reimplementation
- talisman: https://github.com/thoughtworks/talisman (2,095★)

## 2026-08-18 — Phase 02 verified IaC decision

- `iac` supports exactly two local Terraform adapters: TFLint `0.64.0`
  (MPL-2.0) and Checkov `3.3.9` (Apache-2.0), in declared TFLint-then-Checkov
  order. Both remain optional environment-discovered executables.
- Checkov's supported local command is `--directory DIR --framework terraform
  --output json --skip-download --download-external-modules false`. Rush uses
  a credential-free allowlisted child environment, does not request external
  checks, downloads, source rewriting, soft-fail, or a config file.
- Fake-process fixtures own argv, normalized output, malformed/partial reports,
  missing executable, timeout, and aggregation provenance. The full compatibility
  record and residual Phase 02 backlog live in `docs/ENGINE_COMPATIBILITY.md`
  and `.hermes/implementation/phase-00-02-ledger.md`.

## 2026-08-18 — Phase 02 kubeconform deferral

- kubeconform `0.8.0` has a documented JSON mode and invalid-resource exit
  behavior, but its documented default Kubernetes version is `master` and schema
  resolution is HTTP/cache-backed.
- Rush will not rely on that default or download schemas. A safe invocation
  requires a maintained local schema corpus and explicit schema locations;
  ownership belongs to the Phase 07 cluster-manifest/offline-evidence scope.
- The existing `yaml` command remains feasibility-gated. No engine, catalog,
  CLI, MCP, configuration, or fixture promotion is claimed in Phase 02.

## 2026-08-18 — Phase 02 actionlint decision

- `actions` supports actionlint `1.7.12` (MIT) as a local JSON adapter.
- Rush passes a package-owned empty `-config-file`, disables `shellcheck` and
  `pyflakes`, supplies no write/download/init command, and maps only `0` clean
  and `1` findings; malformed, inconsistent, timeout, and command errors are
  canonical structured errors.
- The deterministic fake-process suite owns invocation and parser behavior;
  CLI/MCP use the existing catalog-generated shared implementation.

## 2026-08-18 — Phase 02 markdownlint decision

- `markdown` supports markdownlint-cli `0.49.1` (MIT), replacing the prior
  unpinned markdownlint-cli2 text route.
- Rush passes owned empty JSON config and ignore files with `--json`; it omits
  fix, custom-rule, and output-file behavior and cannot discover project config.
- Deterministic JSON fixture ownership proves invocation, parser, malformed
  report, and exit consistency; shared catalog registration preserves CLI/MCP.

## 2026-08-18 — Phase 02 Spectral decision

- `yaml` supports Spectral `6.16.3` (Apache-2.0) through owned static rules and
  JSON output. Rush neither discovers project rules nor passes a custom resolver
  or output file.
- Remote `$ref` inputs are blocked before execution. The fake-process suite owns
  argv, normalization, malformed/inconsistent output, and that containment rule.

## 2026-08-18 — Phase 02 ansible-lint feasibility decision

- ansible-lint `26.8.0` has SARIF JSON output, but its documented project-root
  behavior creates a `.cache` and upstream warns untrusted content can execute
  code via Ansible configuration and vault sources.
- Rush has no contained Ansible config/environment or dedicated tool seam.
  It remains feasibility-gated; `YamlTool` remains Spectral-only.

## 2026-08-18 — Phase 02 codespell feasibility decision

- codespell `2.4.3` defaults to dry-run, but has no stable structured report and
  loads project `pyproject.toml` before an explicit config file.
- The plan forbids a generic content catch-all. It remains feasibility-gated;
  Rush does not invoke codespell or its mutating `--write-changes` option.

## 2026-08-18 — Phase 02 Vale feasibility decision

- Vale `3.17.1` can use structured output but requires configuration/styles;
  upstream source discovers global defaults and `vale sync` can mutate style
  paths and download packages.
- Rush has no versioned local corpus or focused prose route. It remains
  feasibility-gated; no config, style package, adapter, or scanner execution
  was added.

## 2026-08-18 — Phase 02 Lychee feasibility decision

- Lychee `0.24.2` is a live link checker. Phase 02 forbids such network activity
  without an explicit permission ADR and has no import-only report route.
- It remains feasibility-gated; Rush does not add an inert command or execute it.

## 2026-08-19 — Documentation source-of-truth audit

- Generated CLI inspection confirms 32 catalog commands plus the `mcp` group.
  Only `review` exposes `--llm`/`--use-graft`, and only `format` exposes
  `--check`; ordinary generated path commands expose `PATH` and `--json`.
- Catalog inspection confirms 27 engine metadata entries and mixed maturity:
  real adapters, feasibility-gated routes, guarded placeholders, catalog-only
  SBOM, and experimental browser runtime.
- ToolResult uses `engine_version` and `duration_ms`; older prose using
  `version`/`duration` was stale. `skipped` maps to exit 0, so mandatory CI
  checks must inspect JSON status.
- Configuration discovery is nearest-file, upward, Git-root-bounded, and
  non-merging. Verified setting consumers are narrower than the parser:
  review thresholds/Graft/scaffold policy and lint engine arguments are active;
  `fail_on`, generic `check`, and project lists are not universal enforcement.
- Advanced guarded tools state browser/slow/network/fuzz/baseline permissions
  internally, but generic CLI commands do not expose them. `commit-msg` lacks a
  CLI message input; SBOM lacks CLI output/overwrite controls; release lacks
  CLI publish/confirm controls. Documentation labels these gaps explicitly.
- `review --llm` detects provider-key presence but returns deterministic stub
  text and performs no hosted or local model call.
