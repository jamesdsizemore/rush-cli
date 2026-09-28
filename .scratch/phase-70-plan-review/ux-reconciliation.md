# Phase 70 UX scope reconciliation — 2026-09-24

Status: **FULL-TUI CONTRACT REVIEW PASS** on final hash in the full-TUI reconciliation below. This supersedes the earlier insufficient TUI coverage claim. Original 25 task packets remain preserved; T28 now contains six complete remediation packets. Implementation and native acceptance remain required.

## Controlling scope and review method

The user explicitly requires app user-friendliness/UX, fewer CLI commands to install/setup/connect a working LLM CLI, remediation of commands returning ok without useful output, and a useful TUI. All four are Phase 70 obligations. Full dashboard/prototype implementation remains the substantial separate Phase 71 plan. This review changes plans/review records only.

Applied [orchestrate skill](/Users/jamesdsizemore/.agents/skills/orchestrate/SKILL.md): three independent read-only GPT-6 Sol/low scouts with no inherited history and no delegation (onboarding_scope, empty_output_scope, tui_scope); parent integrates; GPT-6 Astra/high independent ux_final_review audits the frozen correction. Narrow scopes avoid repeating the previous technical review. No owner questions were necessary: explicit scope and prior approved permission/host defaults resolved choices.

Repository HEAD: `ddc064117e971b48e29100004052e876e456faf2`. Prior Phase 70 hash: `5017d33081e90b0abac08e9c0417b2d0cccd88f4a6a713e44bb51a4df7b82212`; exact before-image: [pre-ux-reconciliation.md](pre-ux-reconciliation.md). The prior verdict is now marked WITHDRAWN in [review.md](review.md); its technical findings remain intact as historical evidence.

## Findings and plan corrections

| Finding | Current evidence | Correction |
|---|---|---|
| Scope excluded TUI although user explicitly requested remediation; Phase 71 also excludes TUI | Prior Phase 70 §9; Phase 71 §1 | Goal/§9 corrected; R11/T28 owns complete terminal workflows and terminal acceptance |
| Empty-success output has shared renderer root cause beyond quality engines | `src/rush/theme.py:75-108`, `cli_support/rendering.py:45-76`, `tools/project.py:440-469`; populated in-memory project-list result renders only `project list: ok` | R10/T27 domain output, producer semantics, exhaustive public-route matrix, explicit no-work/denial/partial states |
| Install/setup/connect route has no command budget or proven CLI readiness | Bootstrap scripts hand off to install; `tools/install.py:300-327,344-385,467-481`; `cli.py:620-685` | R09/T26 shared guided flow, no second download, correct piped input, exact resume, native CLI tools/call proof |
| Passing TUI checks do not prove practical usefulness | Existing finding explorer, permission/cancel/memory handlers at `tui.py:1904-2067,2263-2535`; 46 headless tests pass | T28 status/setup/menu/check/details/memory/recovery, focus/resize/accessibility, native terminal checks |
| Preserving task count did not preserve user outcomes | Original ledger lacked explicit complete TUI and whole-catalog outcomes | R09–R12, T26–T29, E19–E22, G8 and T29 cross-interface acceptance |
| Separate dashboard plan had stale fixed prerequisite count | Phase 71 used 25 tasks/G0–G7 and said redesign excluded in Phase 70 | Only dependency row and start gate corrected to all current Phase 70 tasks/G0–G8; prototype scope unchanged |

T1–T25 packets are byte-identical to the before-image. Existing technical behavior, safety, host packages, memory work, result contracts and tests remain binding. D7 clarification preserves nonblocking default installation; an explicit --setup handoff enables the guided route. Added tasks extend implementation effort; the original estimate is preserved as subtotal and a separate increment is disclosed.

## Verification actually performed

- Three source audits used Graft before code inspection. Parent verified relevant current plan/template, separate Phase 71 gate, exact symbols and unchanged baseline.
- Scout reproduced hidden populated project-list output in memory through actual renderer with no state writes.
- Scout ran `tests/test_tui.py -q`: 46 passed. This is headless characterization, not terminal usability acceptance.
- Official terminal MCP contracts checked 2026-09-24: [Claude Code](https://code.claude.com/docs/en/mcp), [Cursor CLI](https://cursor.com/docs/cli/mcp), [Codex CLI](https://developers.openai.com/codex/mcp). These establish terminal registration/configuration options; no native host install/login/call was performed.
- Parent compared all original task packets: 25 unchanged, four added. New task fields and plan whitespace checked. `git diff --check` passed for tracked changes; explicit plan checks cover untracked plan bytes.

Static bootstrap flow shows a second downloader call; a real network installation was not executed. No claim that all existing CLI producers were behaviorally exhaustively tested during this plan review: T27 makes exhaustive semantic remediation an implementation gate. Real terminals, native host calls, platform installs, the complete suite and newly planned tests have not run. They remain explicit implementation acceptance, never represented as passing here.

## Scope preservation and changed artifacts

This corrective pass writes:
- `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`;
- two dependency statements in `docs/phase-plans/phase-71-prototype-dashboard-integration-plan.md`;
- withdrawal status in `.scratch/phase-70-plan-review/review.md`;
- exact prior-plan snapshot and this receipt under `.scratch/phase-70-plan-review/`.

Pre-existing AGENTS.md changes, stray untracked state, original review artifacts and Phase 71 content outside those dependency statements are preserved. No application code, tests, installation, hook configuration, real memory data, release version, AGENTS.md, durable memory, or commit changed during this corrective pass.

## Final independent review

GPT-6 Astra/high independently reviewed frozen Phase 70 `f192e84e5d0c80d03cabc8c6be4b4df1df7915926f5e8fd48716da7fbb45d570` and the two Phase 71 dependency amendments. Found two blockers: default bootstrap still permitted a host-selection prompt; saved provision plan did not bind host mutations. Both were corrected: default bootstrap only prints its handoff; T26 now defines a strict complete setup envelope binding host/session, exact resource changes/preconditions, separate grants, guidance/hooks and capability-probe approval while preserving T24's nested provisioning identity. Legacy provision payload cannot authorize added host actions. Evidence/requirement Markdown table joins were repaired.

Independent delta review returned **PASS** on Phase 70 `26d8ec7423fd4399801f8b51ce305af674fc85db6833486499dd7d80be987000`, with no remaining blocker in the reviewed changed contracts. Phase 71 dependency-amendment hash: `d6f2e9dbd6cca08aa0f45abf908c7f4cee688e4c427359a97c0c527b943b3339`. The old Phase 71 receipt describes its historical bytes; this review covers the two dependency amendments only, not a new complete Phase 71 re-review.

Parent final checks passed: 29 unique task packets; original 25 unchanged; required new packet fields present; E19–E22/R09–R12 tables contiguous; TUI exclusion removed; no plan trailing whitespace. Tracked source/tests/scripts have no diff. Exact previously captured source/bootstrap and both AGENTS.md hashes remain unchanged; existing AGENTS.md changes predate this pass.

This verdict establishes plan coverage and consistency, not exhaustive behavioral health of the current application. T27's full command matrix and G5/G6/G8 native execution remain mandatory implementation work. No unavailable host, platform or terminal is silently treated as passed, and no implementation evidence file was fabricated.

## Full-TUI correction after user challenge

The user challenged the claim that T28 constituted full remediation. Research confirmed the challenge. The earlier T28 covered selected first-use/check/memory/navigation flows but relied on “preserve existing capabilities” for several incomplete surfaces; it did not specify the complete terminal product.

Two new narrow read-only GPT-6 Sol/low lanes, tui_full_surface and tui_requirements, independently inventoried current source and original terminal requirements. No inherited conversation or delegation. Parent ran an in-memory render probe with three ToolResults: clean, missing-engine skipped and engine error, each with zero findings. At 80×24 all three render_app outputs were byte-identical, showed Findings (0), and omitted each distinctive summary. This proves one actual semantic display defect; it does not simulate native terminal acceptance.

Controlling requirement evidence: Phase 66 §3.1 (lines54–60) requires both surfaces to expose Overview/Scans/Memory/Tokens/Git/Artifacts/Setup-Agents and relationships; §3.8 (146–148) specifies terminal interaction/motion/non-TTY behavior; P66-03 and §5 require complete provision→scan→agent→rescan and all evidence access. Phase 69 P69-06 ownership/input/cancellation remains binding. Phase 71 excludes TUI and cannot absorb omissions.

Current source evidence: tui.py::render_app/_render_project_table hides no-finding result outcomes; _map_nodes contains only project/files/findings; _render_git_panel provides first-page history/category counts rather than navigable diffs/artifact detail; _memory_refresh requires query; token view uses side HUD. TelemetryStore constructor initializes/migrates database, so it cannot be reused unchanged for read-only render refresh.

T28 now specifies eight first-class sections and uniform loading/populated/empty/unavailable/denied/error/stale/disconnected states. Six serial packets own:
A workspace/navigation/truthful state;
B setup/agents/history/handoff/rescan;
C complete scan evidence and relationship Map;
D full scoped memory administration;
E actual-versus-estimated token provenance, navigable Git and every artifact;
F real terminal input/motion/performance, full section/action/state matrix and installed native acceptance.

Each packet includes concrete behavior, files, failing-first selector and completion criteria. Existing T28 requirements remain; original25 task packets are unchanged. Phase70 continues to own TUI; dashboard prototype remains Phase71. T28's initial effort estimate is explicitly superseded, not treated as sufficient for the expanded work.

This pass changes only the Phase70 plan and this review receipt. Source/tests/scripts have no tracked changes; both AGENTS.md hashes match before-images. No screenshot, code implementation, native installation, or fabricated acceptance evidence was produced.

Final independent Astra/high review found two bounded issues: conditional artifact export could exclude unsupported types, and wording confused a valid unavailable measurement with missing native acceptance. Corrections now require safe captured-artifact access/export through explicitly named shared readers, exact byte/identity preservation, permission/recovery controls, and the shared project_token_usage producer's read-only scoped filtering. Valid unavailable measurements must display truthfully; missing required native environment still blocks acceptance. ProjectTool file reference corrected.

Independent delta review: PASS on SHA-256 `e431c0d134c3883a8263ab0977b5dcb0b26ff9553be83e49f3a1faf0ee7c3589`, with no remaining blocker found in reviewed TUI contracts. Parent verified all25 original packets unchanged,29 parent tasks, six explicit TUI selectors, no conditional export exclusion, clean whitespace and git diff --check. Final verdict is specification coverage/consistency only; no implementation or native usability acceptance was performed. Earlier plan hashes and their TUI coverage claims are superseded by this section.
