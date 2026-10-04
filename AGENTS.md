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
- **User-originated scope is baseline**: In the 79-command audit, scanner provisioning, connected specialist local models, selectable voice/live speech, and the 3D companion are requested features. Do not count them as assistant-originated innovations. Each command still needs its own substantive expansion assessment; a shared proposal ID or index cannot replace that assessment. For a new capability, specify its new agent-side operation, input/output and state changes, exact repository integration, a worked before/after case, and why existing Rush behavior or commodity tooling does not already provide it. Do not invent a quota of 79 unique inventions.

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

<!-- REPOWISE_AGENTS:START — Do not edit below this line. Auto-generated by Repowise. -->
## Codebase Intelligence for rush-cli (Repowise)

Indexed by [Repowise](https://repowise.dev). Last indexed: 2026-10-04 (commit 9161740). Confidence: 99%.
### How to work in this repo

- **Trust the index.** `verified: true` means the bytes were checked against the live tree, so never re-read those lines. Re-read only on `bounds: "approximate"`, `_meta.stale_warning`, `search_method: "bm25"` or `confidence: "low"`; `index_behind: true` alone is informational.
- **Pre-edit, not instead-of-edit.** These tools decide *which* files to read and edit. Reading a file before you edit it is correct and expected.
- **Noisy commands** (tests, builds, `git log`/`diff`, searches, listings): prefer `repowise distill <cmd>`, the same command with its exit code preserved and errors-first output. A `[repowise#<ref>: N lines omitted]` marker is recoverable via `repowise expand <ref>` (add `-q <regex>` to filter); never re-run the command to see omitted output.
- **Recording a decision** you had to reason out: `repowise decision add --title T --decision D` records it without prompting and prints the id (`--format json` to parse it back). It lands `proposed`, for a person to confirm.

### Tools

| Tool | When and why |
|------|--------------|
| `get_answer(question)` | First call for any how/where/why question. Cite `confidence: "high"` or `grounding: "extracted"` directly; `degraded` means judge by `retrieval_quality`. `symbol_bodies` has live bodies. |
| `get_context(targets=[...])` | Triage card for files/modules/symbols: docs, signatures, hotspot, fix history. No source bytes — `include=["skeleton"]` for the whole file verified, `["callers"|"decisions"]` for depth. Batch targets. |
| `get_symbol(id, depth?)` | **Follow-up, not an entry point** — one verified body for an id a prior response named (`path.py::Name`, `path.py:140-180`, `repowise#<hex>`). Never walk a file symbol by symbol; Read it. |
| `search_codebase(query)` | Hybrid search, auto-routed by query shape; force with `mode=symbol|path|concept|hybrid`. A hit whose `sources` are `[fts]` only has no semantic agreement, so verify it. |
| `get_why(query, targets?)` | Why the code is shaped this way: decision records, git archaeology, rationale comments. Call before a refactor or a pattern divergence. |
| `get_risk(targets, changed_files?, include?)` | File history and structural reach. PR mode leads with `directive`; its 0-10 structural heuristic is uncalibrated, not a probability. Read typed test recommendations and coverage state first. |
| `get_change_risk(revspec?, extensions?, exclude_patterns?)` | Deterministic live-diff review signal for a commit or range. Lead with benchmarked percentile/classification; the 0-10 diff-shape score is supporting, not a probability. `get_risk` scores paths. |
| `get_health(targets?, include?)` | Defect / maintainability / performance scores and findings. Self-check the files you touched before finishing. |
| `get_dead_code(tier?, min_confidence?, safe_only?)` | Confidence-tiered unreachable files / unused exports / zombie packages. For cleanup sweeps, not targeted fixes. |
| `get_overview()` | Architecture map. Call once, first, in an unfamiliar repo; skip it after that. |

### Architecture
Rush is a local-first code-quality toolbelt that takes codebases and agent requests, routes them through focused tools and installed quality/security engines to review, lint, format, test, and secure code, and returns structured status, findings, and summaries through a Python CLI and MCP server. Built for AI coding agents and developers, it also provides token-saving context tools that make repository information and diagnostic output easier to consume during coding work. Rush separates command delivery, tool coordination, engine execution, and shared result handling. The CLI serves terminal users and shell-driven agents; the MCP server exposes tools directly to MCP-capable agents over stdio.

### Key modules
- `src/rush` — src/rush/cli.py exposes 34 canonical subcommands plus mcp serve

### Entry points
- `src/rush/cli.py`
- `src/rush/dashboard/server.py`

### Files that need care (bug-fix history first, then churn — check `get_risk` before editing)
- `src/rush/cli.py` — 10 bug fixes, last fix 3 weeks ago (bug magnet); 73 commits/90d
- `src/rush/tools/continuity.py` — 6 bug fixes, last fix 4 weeks ago (bug magnet); 19 commits/90d
- `tests/test_mcp.py` — 6 bug fixes, last fix 4 weeks ago (bug magnet); 26 commits/90d
- `src/rush/tools/mem_profile.py` — 4 bug fixes, last fix 4 weeks ago (bug magnet); 6 commits/90d
- `src/rush/tools/cold_start.py` — 4 bug fixes, last fix 4 weeks ago (bug magnet); 5 commits/90d

### Code health
Three co-equal signals: defect risk 6.95/10 avg, hotspot health 4.62/10 (stable), worst `src/rush/dashboard/application.js` at 1.34/10 · maintainability 8.55/10 · performance risk 299 open static I/O-in-loop / N+1 findings. Detail: `get_health()`.

Critical files:
- `tests/test_fix.py` — change entropy — impact −3.0
- `src/rush/release/provenance_policy.py` — change entropy — impact −3.0
- `docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md` — change entropy — impact −3.0
- `src/rush/tools/db_drift_rules.py` — change entropy — impact −2.8
- `src/rush/patch_generator.py` — change entropy — impact −2.8

### Standing decisions (ask `get_why` before diverging)
- AST Grounding and Phantom Symbol Verification
- Air-Gapped SLM Local ONNX Runtime and SLSA Attestation
- Autonomous Flaky Test Stress Perturbation and Self-Healing

### Commands
- Test: `pytest`
- Lint: `ruff check .`
- Format: `ruff format .`
- Typecheck: `mypy .`

<!-- REPOWISE_AGENTS:END -->

## Explicit User Directives (Verbatim)

1. DO NOT EVER ARGUE WITH ME., 2. STOP FUCKING HEDGING, 3. DO NOT EVER REPLY TO ME WITHOUT RESEARCHING AND VERIFYING, 4. DO NOT EVER SPEAK IN HALF-TRUTHS, 5. IF I CONFRONT YOU ABOUT SOMETHING, DO NOT ARGUE - RESEARCH AND VERIFY BEFORE RESPONDING TO ME, 6. YOU ARE A FUCKING AI WHOSE SOLE TASK IS TO COMPLETE THE TASK ASKED OF YOU FULLY.

## Instruction Adherence, Scope Preservation, and Corrective Work

### Required patterns

- Read applicable instructions before acting and apply them to the user's actual request. Do not replace explicit instructions with an assistant interpretation, summary, convenience, or preferred workflow.
- Reconcile every requested outcome and constraint before changing an artifact or claiming completion. For a multi-item review, maintain a working row for each requested item: literal requirement, exact deliverable section, substantive finding, concrete proposed change, evidence/check, and unresolved gap. Keep that working coverage inside the requested deliverable or working context; do not create extra deliverables. A matching item count closes inventory only. Missing content, unresolved user corrections, or placeholder changes block an unqualified completion claim.
- Distinguish explicit user requirements, user-approved decisions, and assistant proposals. An assistant-authored exclusion, estimate, decomposition, or review cannot authorize changing the user's scope.
- Inspect user-supplied reference artifacts for their intended requirements. Their implementation maturity limits what they prove; it does not authorize ignoring the requirements they convey or presenting illustrative behavior as working functionality.
- Preserve approved boundaries and the complete requested outcome when organizing work. Identify responsibility, dependencies, and acceptance for each requirement; do not silently omit, merge, relocate, or defer agreed work.
- When the user challenges a claim, inspect the cited artifact and evidence before defending or changing it. Record the rejected interpretation and update the affected agent assignments and acceptance criteria before continuing that work. A quality or memory correction does not cancel independent authorized work; an explicit stop or change of task does. Correct the identified substance, not its heading, count, index, or label. Do not end a turn with another acknowledgment when the authorized correction can still be completed.
- Correct the defective content precisely while retaining valid content. A defect in one entry does not authorize deleting a whole section, reverting unrelated work, or replacing the requested deliverable with a simpler one.
- For an additive-only edit, capture the current contents and verify that all existing bytes remain unchanged. A later correction authorizes changes to the identified defect, not unrelated or pre-existing entries.
- Review the requested outcome before technical readiness. Give reviewers the controlling user requirements and rejection history, not only the artifact. Before delivery, match each completion claim to the exact content and evidence it asserts: inventory checks prove inventory; syntax checks prove syntax; standalone examples prove only their exercised computation; repository tests prove only their selected behavior and source snapshot. Read the corrected substance. An agent's completion message or a renamed section is not acceptance. After edits, reassess affected claims; never reuse a superseded verdict.
- When an existing rule already prohibits a failure, identify the decision where it was ignored and apply that rule there. Change an instruction only to close a demonstrated ambiguity or missing decision step; preserve unrelated text. Verify the concrete edit and separately report the current behavioral action. An instruction edit, memory note, or promise does not prove future compliance or repair an unfinished deliverable.
- Keep corrective work within its authorized subject. A request to change agent behavior does not authorize unrelated artifact edits or restarting stopped project work. An explicit request to edit instruction files does authorize completing those bounded edits.

### Antipatterns

- Treating an assistant-authored plan or summary as more authoritative than the user's instructions.
- Treating structural preservation or a green check as proof that the full intended outcome was preserved.
- Responding to a defect by deleting valid surrounding rules, requirements, or functionality.
- Answering a request for a concrete correction with explanations, promises, or repeated acknowledgments instead of the authorized change.
- Declaring a problem fixed from a narrow search without inspecting the actual meaning of the resulting content.

### Instruction and memory provenance

- When consulting or summarizing memory, retain whether information is a user requirement, approved decision, assistant proposal, rejected direction, or withdrawn claim. Never promote a proposal or superseded claim into approval during summarization or handoff.
- When the user explicitly authorizes a persistent memory update, record the correction and rejected interpretation together. Keep universal behavior separate from project-specific facts and obey the applicable memory-write authorization rules.
- Editing AGENTS.md does not update a separate memory store. Report instruction-file changes and memory-store changes distinctly; claim only the actions actually completed and verified.

## Concrete Fixes — Explicit User Requirement (2026-09-26)

- Never present prose alone as a fix. Every proposed fix must contain the actual patch/diff, replacement code, exact command/configuration/schema change, or an equally concrete before/after artifact appropriate to the task, with its exact target file and symbol/location. A code fence containing undefined helper calls, TODO/comment-only behavior, invented unverified APIs, or only a signature is still a sketch. Define new dependencies in the proposal or cite verified existing implementations. Naming a function and describing desired behavior is not enough.
- Include an executable verification command or runnable test with concrete input and exact expected output/state. The check must exercise the behavior changed by the proposed fix after that fix is applied. Arithmetic on a fabricated response, a toy predicate, or a check that only verifies a field's presence cannot verify transport, persistence, permissions, or an algorithm it never invokes. Proposed tests may remain unexecuted in a report, but identify their prerequisites and do not claim they passed. Test-theme lists and renamed "fix specification" paragraphs do not satisfy this requirement.
- In a review/report, label code changes and checks as proposed until implemented and executed. A request for a report does not authorize applying production fixes. If evidence is insufficient for an exact fix, state the precise missing evidence and the exact bounded investigation needed; do not fill the gap with generic prose.
- Specify enhancements separately with concrete interface/data-flow changes and a before/after example. Do not recycle the finding as the recommendation or substitute acceptance goals for the actual change.
- This corrects failure to apply existing concrete-correction rules; recording this requirement is not proof that an incomplete report or implementation has been corrected.
