# Rush contributor guide

## Project contract

- Python **3.12** package managed with `uv`.
- Rush is a local CLI and **stdio-only** MCP server. stdout is JSON-RPC while
  `rush mcp serve` is running; diagnostics and logs belong on stderr.
- CLI commands and MCP registrations must call the same implementations in
  `src/rush/tools/`. Do not duplicate tool logic in the transport layer.
- Quality engines are discovered from the environment, not bundled as Rush
  dependencies. A missing engine returns a structured `skipped` result.

## Development

Hermes can expose another Python environment on PATH. From the repository root,
use uv's project environment and explicit Python 3.12 selection on macOS, Linux,
and Windows:

```text
uv run --python 3.12 --extra dev python --version
uv run --python 3.12 --extra dev python -m pytest tests/ -q
uv run --python 3.12 --extra dev ruff check src tests scripts
uv run --python 3.12 --extra dev ruff format --check src tests scripts
```

The version check must report Python 3.12. Clear inherited `PYTHONPATH` before
running tests so imports resolve to this checkout's `src/` tree.

## Karpathy coding guidelines

1. **Think before coding.** State material assumptions explicitly. Resolve
   ambiguity before implementation; never silently choose a different scope.
   Surface simpler approaches and relevant tradeoffs.
2. **Simplicity first.** Write the minimum code that solves the requested problem.
   No speculative features, single-use abstractions, unrequested configurability,
   or error handling for impossible scenarios.
3. **Surgical changes.** Every changed line must trace directly to the user's
   request. Match existing style. Do not improve adjacent code, comments, or
   formatting. Remove only imports, variables, and functions made unused by the
   current change; preserve unrelated pre-existing code.
4. **Verifiable outcomes.** Define concrete success criteria before editing.
   Reproduce bugs with failing tests, make the minimum fix, and verify the
   required behavior. For multi-step work, pair each bounded step with its check.
   Do not claim completion from unexecuted or insufficient verification.

## Scope and safety

- Keep results in the canonical ToolResult shape: tool, engine/version, status,
  duration, summary, findings.
- Never write secrets to logs or tool output; redact them as `[REDACTED]`.
- Workflow tools must never rewrite Git history, install hooks, create tags,
  publish releases, or upload packages without explicit user-controlled flags.
- Keep `research/` local and untracked.

## v0.2 configuration

Every `[tools.<name>]` table in `rush.toml` must match a canonical `TOOL_SPECS`
entry. Update the catalog, configuration guide, and example together when
adding a tool.
- Do not commit, publish, or alter release versions unless explicitly asked.

## Agent guidelines & anti-patterns

### Understanding genuine innovation
- **Do not mistake commodity tooling for innovation**: Re-labeling existing
  developer tasks (linters, E2E runners, git commits, database seeders, basic
  error handling) with buzzwords like "Autonomous" or "Agentic" is not
  innovation. If an existing Chrome extension, framework, or standard coding
  assistant already does it, it is not an innovation.
- **Do not substitute academic jargon for practical value**: Dumping compiler
  theory (SMT solvers, BDI models, Tarjan SCC algorithms) does not constitute
  product capability.
- **Zero recycling of rejected ideas**: Once an idea or direction is rejected,
  it is permanently blacklisted. Never re-word, re-skin, or re-package it.

### Understanding what "Agentic" means
- **Automation is not Agentic**: Simply running a script, linter, test suite, or
  calling an API on demand is deterministic automation, not agentic capability.
- **Agentic means closed-loop autonomy**: An agentic capability provides the AI
  agent itself with the substrate to perceive environment state, maintain grounded
  memory, plan under uncertainty, execute in isolation, observe feedback, and
  autonomously self-correct without human intervention.
- **Agent-side vs User-side**: Agentic features live on the *agent's* side of the
  system (enhancing how the AI reasons, navigates, remembers, and verifies), not
  as consumer UI widgets or product gimmicks for the end-user.

### Zero Simulated Completion & Zero Downscoping
- **Never downscope or degrade specifications**: The specification is the immutable contract. When an implementation falls short of a plan, the only acceptable action is completing the implementation. Never offer, propose, or execute downscoping to match degraded code.
- **Zero placeholder/deferred stubs in production paths**: Stubs returning `"unknown"`, `"deferred"`, or simulated metric dictionaries are prohibited. If an analytical engine cannot be implemented, do not fake its return shape.
- **Zero tautological or permissive test assertions**: Never write tests that assert placeholder values (e.g. `assert val == "unknown"`) or permissive membership (e.g. `assert status in ("ok", "warn", "skipped")`). Tests must assert exact domain computations against realistic fixtures.
- **Two-pass verification (Plan-vs-Code first)**: When reviewing or validating code, verify the plan's Requirement Ledger (§5) and File Writes (§8.1) against actual files and AST calls first. Green tests that validate stubs are a failure of review integrity.
- **Zero recycling of pre-remediation prototypes**: Never wrap legacy or pre-remediation stubs with new interfaces to simulate compliance. Build the required engine directly.

### Scope boundaries
- **Product interfaces**: Rush includes CLI, stdio MCP, an interactive TUI,
  and a local web interface. Interface work is in scope when requested; all
  interfaces must use shared Rush implementations and permission boundaries.
- **No unprompted Git hooks**: Never install, propose, or configure Git hooks.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.


<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->
