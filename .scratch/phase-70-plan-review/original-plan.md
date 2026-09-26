# Phase 70: Agent adoption, result trust, and visible memory

Status: proposed, not started. Written 2026-09-22.

This phase answers three questions no previous phase asked:

1. **What makes an agent use Rush at all**, without the user naming it every time.
2. **How does the user see that memory did anything.**
3. **Why do results deserve trust**, when today several of them are wrong.

**Coverage of the evidence below:** ran 11 of the 104 CLI subcommands and 7 of the 53 MCP tools the
server advertises; read all 23 `rush memory` subcommand signatures; queried all 21 tables in
`.rush/memory.db`; read 5 of the 59 documents in `docs/phase-plans/`, plus
`src/rush/tools/install.py`, `src/rush/plugins/skills_generator.py` and `src/rush/cli.py:647-703`.
Everything asserted here was run or read on 2026-09-22 against the installed binary (`rush 0.3.0`)
and this repo; nothing is carried over from an earlier phase document. The unexamined remainder is
93 CLI subcommands, 46 MCP tools and 54 plan documents — unexamined, not asserted healthy.

---

## 1. The agentic surface was asked for, specified, and dropped

The user's own words, 2026-09-06: extend Rush with "hooks, skills, per-llm plugin, agents". And
2026-09-08, after a deep review: the features "are incredibly disjointed and are hard for a user to
access and use... If this means we need to expand functionality, expand the MCP tools, whatever is
needed - then let's plan to do that."

What is actually in the repo today:

| Asked for | What exists |
|---|---|
| Agent skills | `skills/` holds 2 SKILL.md files, both for developing Rush itself (`adversarial-plan-review`, `orchestrator`). Neither teaches an agent to use Rush. |
| Skill generator | `src/rush/plugins/skills_generator.py::generate_skill_markdown(plugin)` generates a SKILL.md **per user-defined rush.toml plugin**. It takes a `PluginSpec`, so it cannot describe Rush's own tools. |
| Per-LLM plugin | `rush plugin` means custom quality plugins declared in `rush.toml` (`list`, `run`). No Claude Code, Cursor or Codex plugin exists; `packaging/` holds homebrew, scoop and winget only. |
| Hooks | `rush hook` covers git pre-commit hooks. No agent-lifecycle hooks. |
| Agent connection | `rush install --agents all` writes MCP server registration. `install.py` has no reference to `CLAUDE.md`, `AGENTS.md`, `SKILL.md` or `skills/` (grep: no matches), so nothing tells a connected agent when to call Rush. |
| Rule sync | `rush governance sync` compiles this repo's `AGENTS.md` into `.cursorrules` and similar — contributor rules for working *on* Rush, not usage rules for working *with* Rush. |

Where it got dropped: `phase-61-cross-llm-memory-typed-artifact-schema-plan.md:109` lists "Per-tool
skill/hook bundles" first among "Remaining Phase 62+ candidates, not ranked (16 of 35)". The Phase
62 plan that followed mentions "skill" 5 times and contains no skill/hook bundle work, so the item
was deferred into a phase that never picked it up.
`docs/developer/phase-28-plan-trust-gated-plugin-system-and-agent-skills.md` marks
`AgentSkillGenerator` complete — true for the plugin-skill generator, and not the agent-facing
skill system asked for on 2026-09-06.

**This is the core of the phase.** An agent uses a tool when it knows the tool exists at the moment
of need, knows the tool is authoritative for that need, and found past results trustworthy. Rush
supplies none of the three.

---

## 2. Evidence

### 2.1 Nothing makes an agent reach for Rush

| # | Observed | How checked |
|---|---|---|
| E1 | Installing Rush into an agent registers an MCP server and writes no usage guidance anywhere. | grep of `src/rush/tools/install.py` for `CLAUDE.md`, `AGENTS.md`, `SKILL.md`, `skills/` |
| E2 | 53 MCP tools are exposed flat, with descriptions naming what each wraps rather than when to use it. | MCP server tool list |
| E3 | `rush --help` lists 104 subcommands, directly under the line "Five tools: review, lint, format, test, security." | `rush --help` |
| E4 | `rush_scan` and `rush_project` take one untyped `request` object with no documented fields; an empty call returns only `schema_version must be 1`. | MCP `rush_scan({})`, `rush_project({})` |
| E5 | `rush_memory` has undeclared required fields: `ask` returns `memory ask requires subject and query`, though the schema marks only `path` required. | MCP `rush_memory(path=..., operation="ask", query=...)` |

### 2.2 Results an agent cannot trust

| # | Observed | Ground truth |
|---|---|---|
| E6 | Relative paths resolve under `src/rush/tools/` from any working directory, then report `✓ lint: no Python/JS/TS files found`. Rush also created a stray `src/rush/tools/.rush/` (cache plus a 140K `memory.db`) there. | Same file by absolute path: `✓ lint: clean`. Reproduced from two working directories. |
| E7 | `rush_typecheck` on one file returned `fail`, 395 findings across the whole repo, ~93K characters — larger than many agents' per-result budget. Findings include `Cannot find implementation or library stub for module named "tiktoken"`. | `.venv/bin/mypy src/rush/tools/continuity.py` → `Success: no issues found in 1 source file`. `rush doctor` reports `Virtualenv: inactive`. |
| E8 | Every lint finding is emitted twice: `rush lint . --json` returns 16 findings, 8 unique by (path, line, rule). | `.venv/bin/ruff check .` → `Found 8 errors.` |
| E9 | `security` returns `skipped: unrecognized project type` on this repo. | `pyproject.toml` and `uv.lock` are both at the repo root. |
| E10 | `doctor` returns `status: ok` with `6/11 engines installed`, naming none of the 5 missing; `findings: []` even with `--json`. | `.rush/toolchains.json` lists 6 engines; `rush setup` recommends 7, including `bandit`, which is absent. |
| E11 | Results carry no scope: `engine_version`, `metrics`, `artifacts` and `raw` came back `null` on every tool called. | 7 MCP calls |

An agent that receives `clean` for a path never scanned, and `fail` for errors that do not exist,
learns to stop calling the tool. That is the adoption problem, upstream of any skill file.

### 2.3 Memory is invisible, and is mostly Rush talking to itself

| # | Observed | How checked |
|---|---|---|
| E12 | 685 artifacts in `.rush/memory.db`: 341 from `flight_recorder:record_event`, 341 from `checkpoint_journal:save_checkpoint` — Rush's own bookkeeping. 3 from any other source. | SQLite query grouped by `source` |
| E13 | All 685 are trust tier `EXTERNAL_WRITE`. | same query |
| E14 | `memory_relations`, `memory_embeddings`, `memory_behavior_success` and `memory_handoff_receipts` all have 0 rows. | `select count(*)` across all 21 tables |
| E15 | Every read path into memory demands a subject enum plus a query string, so a user cannot ask what Rush remembers without already knowing. verified-by: read all 23 `rush memory` subcommands from `rush memory --help`, then ran `rush memory list` → `Error: Missing argument '{active_context\|episodic\|...}'` and `rush memory recall` → same required `{subject} QUERY` signature. The other 21 subcommands act on a named artifact, id, or candidate. |
| E16 | No result from any tool names memory it read or wrote; no MCP result field carries it. | the 7 MCP calls |

### 2.4 Setup does not set up

| # | Observed | How checked |
|---|---|---|
| E17 | `rush setup` prints the detected stack and recommended engines, then exits 0. It installs nothing, writes no `rush.toml`, and leaves `.rush/project.json` at `"configured": false`. No file under `.rush/` changed. | ran `rush setup`; compared `.rush/` mtimes before and after |
| E18 | Installing engines needs `--install` plus `--allow-network --allow-download --allow-cache-write`; without them the plan is preview-only. | `setup_cmd`, `src/rush/cli.py:647-703` |

---

## 3. Principles

1. **An agent must be told when to reach for Rush**, in the surface its harness actually reads.
2. **A result states its own scope**: files scanned, engine, version, what was skipped and why.
3. **Never report ok for work not done.** `skipped` and `ok` never collapse.
4. **Memory is shown, not claimed** — in the agent's result and in a surface the user can open.
5. **Small surface by default**; everything else opt-in.
6. **Fix truth before surface**: the TUI and dashboard render these results.

---

## 4. Workstreams

Every task is test-first: the test fails against today's code before the fix lands.

### W1 — The agent adoption surface (the dropped work)

| Task | Change | Verify |
|---|---|---|
| T1 | Ship a Rush **agent skill**: a real SKILL.md stating when to call Rush (before committing, after generating code, when asked about quality, security or dead code), which tool answers which question, and what each guarantees. Separate from the plugin-skill generator, which stays as is. | Test asserts the skill exists, declares its triggers, and names only tools present in the MCP tool list. |
| T2 | Ship a **Claude Code plugin** packaging that skill, the MCP registration and the commands, installable in one command. Cursor and Codex equivalents carry the same content. | Test installs into a fixture agent home and asserts both the skill and the MCP server register. |
| T3 | `rush install --agents` writes a short usage block into each detected agent's instruction file (`CLAUDE.md`, `AGENTS.md`), showing the exact text and asking first. Idempotent; removed cleanly on disconnect. | Test asserts write, re-run idempotence and clean removal on a fixture file. |
| T4 | Cut the default MCP tool set to a core group; the rest move behind explicit opt-in. | Test asserts the default `tools/list` contains only the agreed core names. |
| T5 | Rewrite core tool descriptions to state trigger and guarantee, not the wrapped engine. | Test asserts each core description names a trigger and a scope guarantee. |
| T6 | Declare required fields in schemas: `rush_memory.ask` declares `subject` and `query`; `rush_scan` and `rush_project` replace the untyped `request` blob with named fields; errors name the missing field and its valid values. | Test asserts schema rejection and error content for each (E4, E5). |
| T7 | Agent-lifecycle hooks so Rush runs without being asked: a post-edit or pre-commit hook that runs `check` and returns findings to the agent. | Test asserts the hook fires in a fixture repo and its output reaches the agent channel. |

**Decision D1:** which tools form the core set in T4. My proposal is seven of the 53 — status,
check, lint, review, security, test, memory. Your call; I have not settled it.

**Decision D2:** T3 writes into your own instruction files. Ask at every install, ask once, or
require a flag? I recommend showing the exact text and asking at install.

**Decision D3:** T7 hooks can fire automatically or only on opt-in. I recommend opt-in first.

### W2 — Results an agent can trust

| Task | Change | Verify |
|---|---|---|
| T8 | Resolve relative paths against the process working directory, at one shared entry point. | Test runs a relative-path lint from three working directories and asserts the resolved target (E6). |
| T9 | Never report `✓ clean` for a path that does not exist or matched no files; return a distinct status naming the path. | Test asserts non-ok status and the path in the summary. |
| T10 | Write Rush state only under the resolved project root. Delete the stray `src/rush/tools/.rush/`. | Test scans a temp-tree file and asserts no `.rush/` appears beside it. |
| T11 | Run engines against the project's own environment, or state in the result that they ran isolated and that import errors are expected. | Test asserts zero `import-not-found` findings for a file whose imports resolve in the project venv (E7). |
| T12 | Scope `typecheck` to the requested path. | Test asserts single-file typecheck returns findings for that file only. |
| T13 | Deduplicate findings by (path, line, rule, message). | Test asserts `rush lint .` count equals `ruff check .` count (E8). |
| T14 | Detect Python projects from `pyproject.toml`, `uv.lock` and `requirements*.txt` in `security`. | Test asserts this repo is not `unrecognized project type` (E9). |
| T15 | `doctor` names every missing engine with its install command, and does not return `ok` while recommended engines are absent. | Test asserts all 5 missing engines appear by name in `--json` (E10). |
| T16 | Populate `scanned` (file count and roots), `engine`, `engine_version` and `skipped` reasons on every result; summaries state scope, e.g. `lint: 8 issues in 412 files (ruff 0.16.7)`. | Test asserts non-null fields across lint, review, typecheck and security; snapshot test on the summary (E11). |
| T17 | `check` runs every step and reports each, rather than stopping at the first failure. | Test asserts a project with a formatting failure still reports lint and test results. |

**Decision D4:** T11 — use the project's interpreter when found, or stay isolated and label the
results? I recommend using the project's interpreter and labelling the fallback.

**Decision D5:** T17 changes `check`'s exit behavior. I recommend run-all by default, with
`--fail-fast` to opt back in.

### W3 — Visible memory

| Task | Change | Verify |
|---|---|---|
| T18 | Tag `flight_recorder` and `checkpoint_journal` rows as internal and exclude them from memory surfaces and counts. | Test asserts a memory listing on this repo returns the 3 real artifacts, not 685 (E12). |
| T19 | Every result that used memory names what it read and wrote, with ids; the field is absent rather than null when nothing was used. | Test asserts `memory.used` is populated on a recall-backed call and absent otherwise (E16). |
| T20 | `rush memory` with no arguments shows recent memory for this project: what was written, by whom, when, trust tier. | Test asserts bare `rush memory` exits 0 and lists recent artifacts (E15). |
| T21 | A memory line in every scan summary: what Rush knew going in, what it learned. Silent when nothing was used. | Snapshot test both ways. |
| T22 | Investigate why `memory_relations`, `memory_embeddings` and `memory_behavior_success` are empty — never wired, or wired and unused. Deliverable is a written finding with file:line, before any code change. | Finding document. |

**Decision D6:** T18 — filter the 682 bookkeeping rows at read time, or migrate them out of
`memory_artifacts`? I recommend filtering first, so no existing data is destroyed.

### W4 — First five minutes

| Task | Change | Verify |
|---|---|---|
| T23 | Bare `rush` prints project status: root, configured or not, engines present and missing, last scan and results, agents connected, memory count. | Test asserts bare `rush` exits 0 and prints the status block (E3). |
| T24 | `rush setup` configures for real: writes `rush.toml`, flips `configured`, installs recommended engines after showing exactly what it will do and asking. Output states what changed and what did not. | Test asserts a fixture project is configured after setup, and that declining changes nothing (E17). |
| T25 | Group `rush --help` into an everyday list plus categories, and delete the "Five tools" line that contradicts the 104 commands beneath it. | Test asserts the top-level help lists only the agreed everyday commands. |

**Decision D7:** T24 makes `setup` mutate state by default, after asking. Today it is preview-only
and permission-gated by design, so this needs explicit confirmation.

---

## 5. Sequence

1. **W2 first.** Correct results are what the other three workstreams rest on, and what decides
   whether an agent keeps calling Rush after the first wrong answer.
2. **W3 T18 and T20 next** — they are what make memory visible at all.
3. **W1 after W2**, so the skill and tool descriptions promise guarantees that are already true.
4. **W4 last**, since bare `rush` status displays what W1–W3 produce.

W1 T3, W1 T7 and W4 T24 write outside Rush's own state — into instruction files, git hooks and
project config. None lands without a separate explicit go, beyond approving this plan.

## 6. Excluded from this phase, and needing their own

The dashboard and the TUI are excluded here. Both are broken, and each needs its own phase
document; listing them here is not tracking them:

- The installed dashboard serves a blank page. The server raises
  `FileNotFoundError: .../_MEI.../rush/dashboard/application.js` from
  `src/rush/dashboard/static_assets.py:193` — the release binary does not bundle the dashboard
  JavaScript. From source it renders, but opens on a project chooser, labels the project root with
  a raw UUID, and its "map" is a flat list of every top-level file including `.DS_Store`.
- `rush ui` opens on an empty findings table with no map. Arrow keys and Enter changed nothing on
  screen across a scripted 120x36 PTY run, and `q` did not exit from the help overlay.
- A working map prototype exists at `research/dashboard-prototype/`, on sample data. It is
  gitignored and was never the build target.
