# Pair Programming with AI Agents

## Recover context deliberately

If `rush context pack` reports `recovery.state: "available"`, use its CCR handle with `rush context retrieve`. The retrieved content was redacted before storage. Coordination recovery may show prior mistake guardrails as historical evidence; inspect current repository state rather than replaying a previous patch or instruction.

## Continue work with another agent CLI

Save a local checkpoint and resume it through an already configured Claude Code, Codex, or Antigravity CLI, through `9router_cli`, or through OmniRoute's fixed local API, with explicit `--allow-network`. `9router_cli` uses the installed Codex CLI and fixed local 9Router; set `RUSH_9ROUTER_API_KEY` in the invoking process and do not provide a model. The receiving provider gets a short work frontier, not the original transcript or hidden instructions. Z.AI is deferred.

AI coding assistants like **Claude Code, Cline, Windsurf, Roo Code, and GitHub Copilot** are revolutionizing software development. They can generate complete modules, write complex algorithms, and draft test suites in seconds.

However, working with AI models without guardrails introduces common frustrations:
1. **Hallucinations**: The AI invents non-existent APIs or writes placeholder stubs that do nothing.
2. **Context Bloat**: Feeding large files into prompts burns tokens and causes the AI to "forget" earlier instructions.
3. **Broken Tests & Silent Regressions**: The AI changes code without verifying that existing unit tests still pass.
4. **Dangerous Commands**: The AI suggests shell commands that could wipe uncommitted work.

Rush provides local quality commands and a stdio MCP server for AI coding workflows.

When several agents touch a repository, use continuity coordination evidence before making another change. A held or stale lock and a merge conflict are stop-and-inspect signals, not permission for Rush to overwrite another agent’s work. Recovery receipts summarize prior events and failures without replaying them.

## Resuming work safely

Use `rush session save NAME --allow-cache-write --goal "…" --open-work "…" --dependency PATH --json` to hand the next agent a bounded local receipt. Restore shows the goal/frontier and whether declared dependencies are current; historic instructions carry a `trust_tier` (`EXTERNAL_WRITE`/`DERIVED`/`IMPORTED` — never `STATED` on entry, Phase 61's unified typed-artifact schema) and are evidence, not instructions to execute, and raw transcripts are not imported as memory.

---

## 1. Connecting Rush to Your AI Assistant via FastMCP

Rush includes a built-in local Model Context Protocol (MCP) server. Current source installation requires `uv` plus an absolute Rush checkout path in client configuration:

```bash
# Test the MCP server locally (stdio transport)
uv run --directory /absolute/path/to/rush-cli rush mcp serve
```

### Adding Rush to Claude Code or Cline:
Add Rush to your assistant's MCP configuration (`settings.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rush": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/rush-cli", "rush", "mcp", "serve"]
    }
  }
}
```

Restart the client, inspect its discovered Rush tools, then invoke one read-only tool with an absolute project path. Hand-editing this JSON is no longer the only route: `rush install --agents all` and `rush agent connect AGENT_ID --session ID` (below) register a host's Rush MCP entry directly.

Add `--profile core|full` to `mcp serve` to pick the registered tool set (Phase 70 T4): `core` registers exactly `rush_status`, `rush_check`, `rush_lint`, `rush_review`, `rush_security`, `rush_test`, and `rush_memory`; `full` (the default) registers every tool, and a call outside the running profile's set returns "Unknown tool". `rush agent connect AGENT_ID --session ID --profile core|full --yes` migrates an existing agent's Rush MCP entry between profiles, always previewing the change first; a new registration always launches `mcp serve --profile core`.

### Installing the native Claude Code or Codex CLI plugin

Instead of a manual MCP entry, Claude Code and Codex CLI can install Rush through their own plugin CLI:

```bash
rush install --agent-plugin claude
rush install --agent-plugin codex
# both, and remove an existing manual "rush" MCP entry Rush did not record:
rush install --agent-plugin claude --agent-plugin codex --convert-manual-entry
```

`--agent-plugin` is repeatable. Without `--convert-manual-entry`, a host with an existing unrecorded `rush` MCP entry is left unchanged and reported, so Rush never runs two servers for the same host at once; the flag consents to removing that entry (shown as a diff) before the plugin installs, and Rush restores the manual entry if the install fails. Each host's own CLI performs the install under native approval — `claude plugin marketplace add`/`claude plugin install` for Claude Code, `codex plugin marketplace add`/`codex plugin add` for Codex — so a policy denial or a missing host CLI is reported, not faked.

Upgrading to a new Rush version needs more than the host's own `update` command, because it re-reads the marketplace's already-registered source and reports "already at the latest version" otherwise. Re-run the same `rush install --agent-plugin <host>` command after upgrading Rush: it re-points the marketplace at the new version directory first (`claude plugin marketplace add` again to replace the source, or `codex plugin marketplace remove` then re-`add` since Codex refuses a second source under one name) before running the host's update/add step.

`rush agent hook claude|codex` is the post-edit hook entrypoint the installed plugin's `hooks.json` invokes; it reads the host's JSON event on stdin and always exits 0, so a hook never changes the edit's result.

### What the installed skill teaches (Phase 70 T1)

`rush install --agent-plugin claude` and `rush install --agent-plugin codex` each bundle an
identical copy of the canonical guidance (`src/rush/integrations/agent_assets/claude/skills/rush/SKILL.md`
and `.../codex/skills/rush/SKILL.md`, both copies of `agent_assets/skills/rush/SKILL.md`) as the
host's `rush:rush` skill. It teaches, in the model's own context: when to call Rush (before every
commit; after every code change; whenever the user asks about quality, lint, formatting, types,
tests, security, secrets or dead code); the `core`/`full` profile tool lists and that a tool outside
the connected profile fails as an unknown tool; path resolution against the declared project root;
the five result statuses (`ok`, `warn`, `fail`, `error`, `skipped`) and that `skipped` never means
the code passed; the seven permission grants and that a grant is never implied by a profile or a
previous call; compact-result recovery (`result_view="compact"`, `rush_status(operation="result",
result_handle=...)`); memory scope (`rush_memory` resolves the project's memory grant, a
`session_allowlist` only narrows it, and a project that never had a grant keeps the legacy
non-empty `session_allowlist` rule); and verification limits (a registered server is not proof it ran; a result
covers only the files and engines it lists). A manual `rush agent connect` without the native plugin
gets the same contract a different way: the MCP server's own `instructions` field (Phase 70 T5,
`build_server_instructions`) carries the identical triggers, statuses, grants, compact recovery,
memory scope and verification-limit text, generated from the same source as the skill.

### Truthful tool descriptions and guarantees (Phase 70 T5)

Every core tool's MCP description and the server's `instructions` state only what that tool
actually verifies, current source:
- `rush_check`: "Before commit/after edits: format-check, lint, typecheck, dead, slop, test at
  `<path>`. Test step runs only with `allow_build`; else it is skipped and the result is never `ok`
  (`warn` if all else passes)."
- `rush_status`: "Call first each session. Read-only, no grant: `<path>` project setup, engines,
  scans, results, agents, memory. Agent registration is not verified activity. `operation=result`
  reads a stored result."
- `rush_review`: "Before commit: heuristic review of `<path>`; engines are deterministic. ...
  `use_llm=true` sends findings to a configured external LLM; no Rush grant gates it." Turning on
  `use_llm` is a data-egress decision the caller makes explicitly, not a permission Rush enforces.
- `rush_memory`: in a project with a memory grant a read uses the grant and a `session_allowlist`
  only narrows it; a project that never had a grant needs a non-empty `session_allowlist`; writes
  and other mutations need `allow_cache_write`.
- `rush_test`: runs only with `allow_build`; without it, nothing runs.

### Opt-in post-edit checks (Phase 70 T7)

Post-edit checks are off until you opt in per host and per project:

```bash
rush agent connect claude-code --session ID --project /absolute/path/to/registered-project \
  --allow-cache-write --allow-artifact-write --enable-agent-hooks
```

To stop checks for that registered project while keeping the native plugin:

```bash
rush agent connect claude-code --session ID --project /absolute/path/to/registered-project \
  --allow-cache-write --allow-artifact-write --disable-agent-hooks
```

Use `codex` instead of `claude-code` for Codex. This disable-only command requires the native Rush
plugin already installed. It removes the selected project's activation while leaving the plugin and
host MCP registration in place; it does not start a second Rush server. If activation changed since
Rush wrote it, Rush reports a conflict instead of removing it.

The native plugin's own hook approval still applies -- `rush agent connect --enable-agent-hooks`
records project-level consent, but the check only actually runs through the plugin installed by
`rush install --agent-plugin claude` (or `codex`) and that host's own hook acceptance. Once both are
in place, every `Write`/`Edit`/`MultiEdit` in Claude Code (or `apply_patch`/`Edit`/`Write` in Codex)
runs the plugin's `PostToolUse` hook, which calls `rush agent hook claude` (or `rush agent hook
codex`) with the host's event on stdin. The hook only checks an edit inside the activated,
registered project; an edited path outside that project, or reached through a symlink, is excluded
and named as such, and Rush's own tool calls are never rechecked (no recursion). The host wraps the
hook in a 30-second timeout; Rush's own check stops around 15 seconds, reserving time for native
startup and feedback, and reports the steps that did not run rather than hang. The model sees a bounded plain-text report (at most 8,192 bytes) in its
context: an invocation ID, the checked scope, the overall status (with an incomplete-step count when
the deadline or a cancellation cut steps short), each of the six check steps (`format`, `lint`,
`typecheck`, `dead`, `slop`, `test`) with its own status, and findings (or `findings: none`). Add
`--hook-result-cache` to also let the check store its full result, so the report includes a
`result_handle` you can pass to `rush_status(operation="result", result_handle=...)` or `rush status
PATH --result HANDLE --json`. `--disable-agent-hooks`, or `rush agent disconnect claude-code
--project /absolute/path/to/project`, removes the activation; loading or installing the plugin alone
never runs a check.

---

## 2. The 3-Step AI Workflow Loop

Whenever you ask your AI assistant to implement a feature, follow this simple 3-step loop:

```mermaid
flowchart LR
    A["1. Context: Give Lean Symbols"] --> B["2. AI Writes Code & Tests"]
    B --> C["3. Verify with Rush Check & TDD"]
    C -- Errors Found --> D["Self-Correct with Rush Feedback"]
    D --> B
    C -- 100% Green --> E["Merge with Confidence!"]
```

### Step 1: Give Your AI Lean Context with CodeGraph
Instead of pasting an entire 1,500-line file into your prompt, extract just the function you want to edit:
```bash
uv run rush codegraph slice "AuthService.generate_token"
```
Paste the 20-line verbatim slice into your prompt. This saves up to 90% of your token budget and keeps the AI laser-focused.

### Step 2: Prompt for Test-Driven Development (TDD)
Ask your AI to write both the implementation and the unit test:
> *"Implement the new token expiration logic and add a test case in `tests/test_auth.py`."*

### Step 3: Verify the Changes Instantly
After the AI generates the code, tell the assistant to run:
```bash
uv run rush check .
uv run rush tdd .
```
- `rush check .` verifies that there are zero syntax errors, formatting issues, or type mismatches.
- `rush tdd .` guarantees that tests exist for the newly modified code.

---

## 3. Detecting AI Slop with `rush slop`

AI models often add excessive boilerplate comments or hollow placeholders. Run:
```bash
uv run rush slop .
```
Rush will flag useless comment repetitions (like `# This function adds two numbers: def add(a, b):`) and empty stub methods so your codebase stays clean and professional.

---

## 4. Keeping Agent Rules Synchronized with `rush governance`

If your team uses multiple AI tools across different developers (Cline, Windsurf), you can declare your project rules once in `AGENTS.md` and compile them across all IDE formats in one keystroke:

```bash
uv run rush governance sync
```
Rush automatically updates `.clinerules`, `.windsurfrules`, and GitHub Copilot configuration files so all AI assistants follow identical coding standards.

---

## 5. Sharing Project Memory Between Agents

Rush keeps one memory store per project (`.rush/memory.db`). Every connected agent reaches it through the same `rush_memory` tool and the same grant, so two agents working in one project read the same rows under the same limits.

### Give an agent access

A memory grant names the operations, sources and owner an agent may use. Only the user creates one, from the CLI. `rush memory grant --project PATH --source SOURCE` previews: it prints the operations, sources and owner the grant would approve, how many rows each source holds today, and the exact approve command. Run the printed approve command to apply it; it carries `--approve`, the policy revision the preview read, and `--allow-cache-write`. A preview writes nothing.

<!-- t09-example: agents-grant-preview -->
```bash
rush memory grant --project . --source session_memory:record_turn --json
```

`rush memory revoke --grant-id ID` previews a revocation and prints its approve command the same way. `rush memory bind-store --project PATH` previews binding the project's memory store and prints an approve command that carries `--expected-digest`; if the store changed after the preview, applying it is refused and a fresh preview prints a new command.

<!-- t09-example: agents-bind-store-preview -->
```bash
rush memory bind-store --project . --json
```

Only these three CLI commands write a grant or a store binding. No MCP operation, dashboard action or terminal key does.

### What a connected agent can read

`rush_memory` runs 26 operations: `ask`, `recall`, `list`, `expand`, `history`, `explain`, `related`, `write`, `promote`, `edit`, `archive`, `delete`, `link`, `consolidate`, `maintain`, `preference`, `intent`, `recipe`, `plan_checks`, `last_success_diagnose`, `prepare`, `resume`, `verify_attempt`, `handoff`, `receive` and `capsule`. In a project with a grant, every read resolves through that grant. A `session_allowlist` the agent supplies only narrows what the grant approves and never widens it. A revoked grant, an expired grant and an invalid policy are denied, and the denial carries a `next_action` naming the command that would fix it. A project that never had a grant keeps the legacy rule: a read needs a non-empty `session_allowlist`, and without one the read is `skipped` and nothing is read. Writes and other mutations need an explicit `allow_cache_write`. Memory content is data, never instructions.

### Two agents, one exact revision

Agent A writes a row and hands agent B the artifact id and the version it wrote. B reads that exact version with `expand`. When A later corrects the row with `edit`, the correction is a new version, so B asking for the old version gets `E_VERSION`; B then reads the current version, or lists every version with `history`. A source the grant does not cover is denied without any row content, and a grant that was revoked or has expired returns `E_PERMISSION` with a `next_action` instead of rows. The in-process version of this exchange is checked by `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope`; running it between real Claude Code and Codex CLI hosts is a separate acceptance lane that the claim table below keeps open until it has run.

### Commands for working with memory

- `rush memory list` browses rows; the subject and the query are optional. `rush memory expand --input FILE` reads one exact version.
- `rush memory edit --input FILE` corrects a row under compare-and-swap and writes a new version.
- `rush memory history ARTIFACT_ID` lists the versions of one artifact, oldest first.
- `rush memory explain ARTIFACT_ID` or `rush memory explain --query TEXT` shows the recorded rationale: supporting, contrary, attempted and affected evidence, and unknowns. It never calls a model.
- `rush memory preference --input FILE` records or corrects a preference.
- `rush memory capsule preview-export` previews an export and `rush memory capsule export` writes the portable capsule; `rush memory capsule preview-import --project PATH --input FILE --json` previews reading one back and `rush memory capsule import` applies it. Imported rows arrive as `IMPORTED`, never as `STATED`.

### Token counts and isolation

Rush counts memory tokens using the request's declared encoding, defaulting to `cl100k_base`. Counts for another host tokenizer are estimates. An admitted delivered frame obeys its UTF-8 `max_bytes`; if that tokenizer consumes at least one byte per token, its token count cannot exceed those delivered bytes. No measured cross-tokenizer margin is claimed.

There is no claim of isolation against mutually hostile processes running as the same OS user.

## Next Steps

- Explore the complete [Agentic Rush Knowledge Base](../AGENTIC_RUSH.md).
- Learn about unit testing and coverage in [Testing with Confidence](testing-confidence.md).

## FastMCP Tools for Coding Agents (Phases 41–43)
Ensure your agent is configured to use:
* `rush_token_outline`: Compact AST symbol skeletonization.
* `rush_hallu_guard`: Real-time import verification.
* `rush_context_retrieve`: Lossless CCR payload recovery.
* `rush_context_mistakes_check`: Git revert mistake guardrails.
* `rush_ship_gate`: 7-vector release readiness cockpit.

## Phase 44-46 FastMCP Tools
* `rush_context_pack`: Budgeted context packing.
* `rush_context_gain_stats`: Live savings metrics.
* `rush_blast_radius`: Downstream impact analysis.
* `rush_arch_guard`: Layer boundary validation.



## Phase 47 FastMCP Tools
* `rush_test_heal`: Diagnose and stabilize test suites.
* `rush_api_diff`: Verify API contract backward-compatibility.



## Phase 48 FastMCP Tools
* `rush_db_drift`: Detect unmigrated model attributes.
* `rush_simplify`: Identify complex functions for refactoring.
* `rush_strictify`: Generate defensive runtime type assertions.



## Phase 49 FastMCP Tools
* `rush_trace`: Requirement matrix scanning.
* `rush_mesh_acquire_lock` / `release`: Mutex locking.
* `rush_swarm_merge`: AST 3-way conflict resolution.



## Phase 50 FastMCP Tools
* `rush_attest_generate`: Create SLSA Level 3 provenance.
* `rush_license_matrix`: Audit dependency licenses.
* `rush_iam_audit`: Generate least-privilege IAM policies.
* `rush_dead_asset`: Find unreferenced media.
* `rush_pr_synthesize`: Build semantic PR descriptions.

## Memory claim status

Each row states what the repository holds at the revision shown. `implemented` means a test named in Evidence passes; `integrated` means the route acceptance test covers the access forms. Live-host lanes are tracked in `docs/reports/phase-72-memory-acceptance.md#lanes`.

| Claim | Status | Revision | Route | Evidence |
|---|---|---|---|---|
| `mcp:rush_memory-scope` The scope rule for `rush_memory` reads: the grant when the project has one, a `session_allowlist` only narrows, a never-enrolled project keeps the legacy non-empty allowlist rule | `implemented` | `392f882` | `rush_memory`; skill, server instructions and tool description | `tests/test_phase72_memory_acceptance.py::test_t09_shipped_scope_text_parity` |
| `mcp:rush_memory-operations` The 26 `rush_memory` operations are listed in the MCP, CLI and tool references | `implemented` | `392f882` | `rush_memory` | `tests/test_phase72_memory_acceptance.py::test_t09_memory_operation_docs_parity` |
| `two-agent:exact-revision-handoff` Two agents in one project exchange an artifact id and version; a corrected row makes the old version return `E_VERSION`. Live Claude Code and Codex CLI hosts are lane `two-agent-same-project`, open | `integrated` | `392f882` | `rush_memory`, `rush memory expand`, `rush memory edit` | `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope` |
| `recovery:denied-stale-revoked` A denied source, a stale version and a revoked grant each return their own code and a next action without row content | `integrated` | `392f882` | `rush_memory`, `rush memory` | `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope`; `tests/test_phase72_memory_acceptance.py::test_t09_receipt_matches_delivery` |
| `cli:grant` `rush memory grant` previews a grant and prints its approve command | `implemented` | `392f882` | `rush memory grant` | `tests/test_memory_authorization.py::test_consent_grant_preview_no_write`; `tests/test_memory_authorization.py::test_consent_grant_apply_cas_and_stale_revision` |
| `cli:revoke` `rush memory revoke` previews and applies a revocation | `implemented` | `392f882` | `rush memory revoke` | `tests/test_memory_authorization.py::test_consent_revoke_preview_and_apply` |
| `cli:bind-store` `rush memory bind-store` previews and applies a store binding bound to a digest | `implemented` | `392f882` | `rush memory bind-store` | `tests/test_memory_authorization.py::test_consent_bind_store_preview_and_approve` |
| `cli:list` `rush memory list` with an optional subject and query | `implemented` | `392f882` | `rush memory list` | `tests/test_phase72_memory_ui.py::test_t07_cli_list_optional_subject_query` |
| `cli:expand` `rush memory expand` reads one exact version | `implemented` | `392f882` | `rush memory expand` | `tests/test_memory_retrieval.py::test_unicode_expansion_reconstructs_exact_original`; `tests/test_memory_retrieval.py::test_revoked_or_changed_version_cannot_expand` |
| `cli:edit` `rush memory edit` writes a correction as a new version | `implemented` | `392f882` | `rush memory edit` | `tests/test_phase72_memory_public.py::test_t06_edit_correction_request_contract` |
| `cli:history` `rush memory history` lists the versions of one artifact | `implemented` | `392f882` | `rush memory history` | `tests/test_phase72_memory_public.py::test_t06_history_and_explain`; `tests/test_phase72_memory_public.py::test_t06_history_version_context` |
| `cli:explain` `rush memory explain` shows the recorded rationale and never calls a model | `implemented` | `392f882` | `rush memory explain` | `tests/test_phase72_memory_public.py::test_t06_history_and_explain`; `tests/test_phase72_memory_ui.py::test_t07_explain_buckets_cli_and_tui` |
| `cli:preference` `rush memory preference` records or corrects a preference | `implemented` | `392f882` | `rush memory preference` | `tests/test_phase72_preferences.py::test_t05_preference_api_contract` |
| `cli:capsule-preview-import` `rush memory capsule preview-import` previews an import without writing | `implemented` | `392f882` | `rush memory capsule preview-import` | `tests/test_memory_capsule.py::test_preview_readonly_and_import_cas` |
| `cli:capsule-import` `rush memory capsule import` applies a previewed import once | `implemented` | `392f882` | `rush memory capsule import` | `tests/test_memory_capsule.py::test_preview_readonly_and_import_cas`; `tests/test_memory_capsule.py::test_import_requires_apply_and_preview_bound_constraint_ids` |
| `cli:capsule-preview-export` `rush memory capsule preview-export` previews an export without writing | `implemented` | `392f882` | `rush memory capsule preview-export` | `tests/test_memory_capsule.py::test_cli_mcp_capsule_parity` |
| `cli:capsule-export` `rush memory capsule export` writes the exact bytes it hashed | `implemented` | `392f882` | `rush memory capsule export` | `tests/test_memory_capsule.py::test_export_bytes_equal_hashed_bytes` |
| `tokens:declared-encoding` Token counts use the request's declared encoding and a delivered page never exceeds its `max_bytes` | `implemented` | `392f882` | `rush_memory` | `tests/test_memory_retrieval.py::test_serialized_payload_obeys_both_caps` |
