# Phase 69 plan document remediation plan

Yes — this document is the plan to fix the phase-69 plan file I broke. It does not itself touch that file. Nothing gets applied until this is reviewed and approved.

## Problem

`docs/phase-plans/phase-69-dashboard-tui-contract-remediation-plan.md` has grown from 207.7K (HEAD, round-8 committed) to ~348K in the current working tree. Root cause: every adversarial-review round (3 through 9) appended a new "Round-N correction" clause onto the *same* paragraph instead of rewriting it, so each of the five packet "GREEN" steps is one run-on paragraph containing round-3-text + round-4-correction-to-round-3 + round-5-correction-to-round-4 + ... concatenated forever, plus 15-50+ inline test names scattered through the prose. This is not readable or usable as a development plan.

A separate, smaller problem: mid-session, one bad `Edit` call on `P69-01.2` replaced only the paragraph's opening sentence and left the rest of the original text attached to it unchanged, producing a 3-line block (label / blank / one still-huge merged line) instead of the clean rewrite.

## Current state, by hunk

Comparison method: `git show HEAD:docs/phase-plans/phase-69-dashboard-tui-contract-remediation-plan.md` piped into a Python script that diffs the committed bytes against the working-tree file line-by-line. `verified-by: python3 one-off script run this session, output pasted below the table.`

| Location | HEAD size | Working-tree size | Status |
|---|---|---|---|
| P69-01 Files: line | 468B | 1,187B | Fork's finding #1 file-list additions |
| **P69-01.2 GREEN** | 30,964B (1 line) | 22B + 0B + 59,951B (3 lines) | **Broken by my bad edit — see below** |
| P69-01.4 VERIFY | 2,319B | 4,947B | Fork's finding #1 test additions |
| P69-02 "Handoff preview..." paragraph | 8,234B | 10,605B | Fork's work |
| P69-02.2 GREEN | 13,092B | 68,690B | Fork's findings #2+#3 closures, still bloated (not cleaned) |
| P69-02.4 VERIFY | 1,870B | 9,676B | Fork's work |
| P69-03.2 GREEN | 33,669B | 61,516B | Fork's finding #1 cross-reference, still bloated |
| P69-03.4 VERIFY | 2,782B | 5,752B | Fork's work |
| P69-06 Files: line | 439B | 628B | Fork's finding #1 shared-file note |
| P69-06.2 GREEN | 21,646B | 23,484B | Untouched this session, bloated from rounds 3-8 |
| P69-06.4 VERIFY | 2,935B | 3,562B | Fork's work |
| P69-07.2 GREEN | 14,188B | 17,812B | Untouched this session, bloated from rounds 3-8 |
| P69-07.4 VERIFY | 2,508B | 4,071B | Fork's work |

**P69-01.2 breakage, checked by direct string search against the live file** (`verified-by: python3 re.finditer over the actual current line content, three markers checked: the new label text, the "Admission control" phrase from mid-paragraph, and the paragraph's original closing test name — each found exactly once, at the expected position, output pasted in this session's transcript`): the current 59,951-byte line contains the label `**a. HTTP hardening.**` once at position 3, `Admission control must happen before thread creation` once at position 678, and ends with the paragraph's real original closing test name at the correct final position. No duplication, no truncation found by that check.

**Nothing has been discarded and nothing will be.** Every technical decision in the current bloated text is preserved verbatim in the rewritten versions below — only the narration ("round-3 said X, round-8 corrected it to Y") is stripped in favor of stating the final, current design directly.

## What's already drafted (scratchpad, not applied to the real file)

Three of the five bloated `GREEN` sections have full clean rewrites already written, each restructured into lettered subsections (current design only, no round-by-round narration) with one consolidated test list at the end instead of tests scattered through the prose:

| Section | Original size | Clean rewrite size | Scratch path |
|---|---|---|---|
| P69-01.2 GREEN | 30,964B | 28,818B | `.../scratchpad/p69-01-2-green-clean.md` |
| P69-02.2 GREEN | 68,690B | 36,160B | `.../scratchpad/p69-02-2-green-clean.md` |
| P69-03.2 GREEN | 61,516B | 32,373B | `.../scratchpad/p69-03-2-green-clean.md` |

Sizes above `verified-by: os.path.getsize() on the actual scratch files this session, not estimated` — an earlier draft of this table guessed P69-03.2's size at "~38,000B" without checking; the real value is 32,373B.

**Self-review finding, already fixed** (`verified-by: python3 re.findall(r'test_[a-zA-Z0-9_]+', ...) set-diff run this session against all three completed drafts before writing this table the first time — it had never actually been run before that`): found and fixed two real drops. P69-01.2's clean draft was missing the `tests/test_project_run_lifecycle.py:95` supporting citation (a file-path reference, not a test-function regex false-positive — re-added). P69-02.2's clean draft was missing one full test name, `test_a_conflicting_requests_attachment_write_that_races_the_winners_terminalization_checks_the_admission_row_not_merely_the_durable_operation_records_existence_and_falls_through_to_fresh_admission_if_the_row_is_already_gone` (re-added). Re-ran the same script after fixing both: P69-02.2 now reports zero missing; P69-01.2 reports two remaining "missing" names, `test_owner_with_expired_lease_but_live_pid_is_not_marked_interrupted` and `test_owner_with_valid_pid_but_expired_lease_is_still_reconciled` — read directly against the original text, both are round-6 tests the original plan itself explicitly marks as replaced ("two of round-6's own named tests below assert opposite outcomes for the identical... scenario... Replace PID+lease entirely... replacing the three round-6 tests above (including the self-contradictory pair) entirely") — correctly absent, not a gap. P69-03.2 reported zero missing on the first run, no fix needed.

Not yet drafted: P69-06.2 GREEN (23,484B) and P69-07.2 GREEN (17,812B).

## Remediation steps

1. **Fix the broken P69-01.2 section first.** Replace the current 3-line block (original text intact, just mislabeled) with the already-drafted clean rewrite, in one atomic full-block replacement done via a Python script (read exact line range by index, splice in the replacement, write back) rather than an `Edit`-tool partial-string match — a partial match on a huge single-line paragraph is what caused the original mistake. Immediately after, check the section boundaries directly: the replaced block starts with `2. **P69-01.2 GREEN:**`, the surrounding sections (P69-01.1, P69-01.3) are byte-identical to before, and the file's total line-count change matches what the replacement should produce.

2. **Apply the two other completed clean rewrites** (P69-02.2, P69-03.2) to the real file the same way — one section at a time, full-block replacement, checked immediately after each individual application before moving to the next. Never batch multiple section replacements into one action.

3. **Draft the two remaining clean rewrites** (P69-06.2, P69-07.2), same method already used for the first three: read the real current bloated content in full, restructure into lettered subsections preserving every technical decision, consolidate scattered test names into one list at the end. Before calling either draft finished, run: `python3 -c "import re; a=set(re.findall(r'test_[a-zA-Z0-9_]+', open('<original-scratch-copy>').read())); b=set(re.findall(r'test_[a-zA-Z0-9_]+', open('<clean-draft>').read())); print('missing:', a-b)"` — a non-empty `missing` set means a test name was dropped and must be added back before the draft counts as done.

4. **Apply those two** to the real file, same one-at-a-time, check-after-each discipline as step 2.

5. **Assess the remaining bloat contributors** (the `Files:` lines and `VERIFY` sections that also grew this session, per the table above) before touching them — report what's actually there and whether it needs the same lettered-subsection treatment, since this wasn't scoped yet.

6. **Whole-document check.** After every section is cleaned: `wc -c`/line count on the final file; the same `test_`-name-diff script from step 3, run once against `git show HEAD:...` (the full original) vs. the final cleaned file, unioned across all five sections at once, confirming an empty `missing` set; confirm the document still reads as one coherent, sequential TDD plan (RED → GREEN → CONNECT → VERIFY per packet, packet order P69-01 → 08 intact) by reading it start to end.

7. **Commit** the cleaned plan as its own commit, separate from any further finding-closure work, with a message describing this as a structural cleanup (round-by-round narration collapsed to current-state spec), not a content change.

8. **Only then resume `/goal`'s original work** — closing findings #4 through #9 — using a no-append-only editing discipline going forward: fixes get written into the already-clean lettered subsections directly (editing the relevant existing letter, or adding a new one), never appended as a fresh "Round-N correction" paragraph on top of prior text.

## Explicit non-goals

- No content is deleted. Every technical decision, file citation, and test requirement in the current bloated text is preserved in the rewrites.
- No git revert/reset/checkout of any kind. The broken section is fixed by writing correct content over it, not by discarding session work.
- No further `/goal` progress on findings #4-9 until this document itself is clean and committed.


## Completion status (2026-09-16, this session)

All eight remediation steps executed and verified:

1. **P69-01.2 GREEN fixed** — the broken 3-line block replaced with the verified clean rewrite, spliced by exact line-range Python script (not a partial `Edit` match), boundaries checked immediately after.
2. **P69-02.2 and P69-03.2 applied** the same way, one at a time, each checked before the next.
3. **P69-06.2 and P69-07.2 drafted** (they weren't done as of this doc's last update) and verified against the pre-cleanup scratch copies for zero dropped test names before touching the real file.
4. **Applied** to the real file, same one-at-a-time discipline.
5. **Assessed the remaining bloat contributors.** The `Files:` lines turned out fine as-is — their `(round-N addition — reason)` annotations are single per-file citations, not narration pileup, and were left untouched. The RED/VERIFY/narrative sections were a real second wave of the same disease: `P69-01.4 VERIFY`, `P69-02.1 RED`, `P69-02.4 VERIFY`, `P69-03.4 VERIFY`, `P69-04.2 GREEN`, three isolated one-line citations in P69-05, `P69-06.4 VERIFY`, the P69-07 "Ownership contract" paragraph, `P69-07.4 VERIFY`, and the P69-08/§5 completion section all had genuine round-N pileup and were cleaned the same way as the five originally-scoped GREEN sections.
6. **Whole-document check.** Final file: 243,914 bytes / 582 lines (from 350,070 bytes at session start). `test_*`-name diff against `git show HEAD:...`, unioned across the whole document: only the two already-documented superseded PID+lease tests are absent from the current text; every other test name, file citation, and technical decision survived. Read start to end — RED → GREEN → CONNECT → VERIFY per packet, packet order P69-01 → 08, intact (37 packet/step markers, in order).
7. **Committed** as `7e35151`, scoped to only this one file (the working tree had unrelated untracked/modified files from other work that were correctly left untouched).
8. **Phase 68 alignment**, per this session's broader `/goal` (not the original findings-#4-9 resumption this doc anticipated — that goal was superseded by a new one asking for full implementation-readiness plus a Codex adversarial review): cross-checked every explicit Phase-68-depends-on-Phase-69 reference. Found and fixed one real gap — P69-03 had no durable per-run publication record, which Phase 68's P68-04 explicitly names as a requirement it depends on (`phase-68...md:46,98,109,162,164-168`) — added as P69-03.2 GREEN subsection v, with matching RED and VERIFY coverage. Also made P69-04.2 explicitly wire the existing `restoreProjectId` option Phase 68's browser-handoff step depends on, rather than leaving that dependency implicit.

Next: this session's `/goal` requires a scoped Codex adversarial review of the cleaned plan (architecture fit, breakage risk, sequencing, scope soundness, test depth — not a citation/count check, which this session's own verification already covers) and closing whatever it finds.


## Round 10 Codex adversarial review (2026-09-16, same session)

Sent the cleaned plan to Codex (`codex exec --sandbox read-only`, high reasoning effort) with a review prompt explicitly scoped to architecture fit, breakage risk, sequencing validity, scope soundness, test depth, and Phase 68 alignment — directed past citation/count checking, which this session's own mechanical verification already covered.

**Result: NOT_READY, 12 findings (7 HIGH, 5 MEDIUM).** Independently verified every finding against real current source before fixing any of them (never took the review's word for it) — all 12 confirmed real:

1. **R10-01** — the new per-run publication record's "durable" wording was ambiguous; `ProjectRegistry` is explicitly documented as in-memory, per-server-instance, non-restart-surviving (`state.py:60-68`). Fixed: clarified the record lives in the same in-memory lock/lifecycle, no new persistence invented.
2. **R10-02** — a run that loses the generation-race could stay `published=false` forever, with no outcome Phase 68's poll could ever resolve to. Fixed: added an explicit `superseded` outcome, and updated Phase 68's own polling step to handle it.
3. **R10-03** — the publication record was keyed by bare `run_id`, but `load_run_manifest` always resolves the *latest* attempt — a resumed run could report a stale attempt's publication status. Fixed: keyed by `(run_id, attempt_id)` per the plan's own already-established historical-identity rule.
4. **R10-04** — the `restoreProjectId` requirement (added earlier this session) had no RED or VERIFY coverage. Fixed: added both.
5. **R10-05** — `get_operation_status()` was defined as a Python primitive with no browser-facing HTTP route; `do_GET`'s real routing has no such endpoint. Fixed: added `GET /api/projects/{id}/operations/{operation_id}` with RED/VERIFY coverage.
6. **R10-06** — CHECK_SUITE's own `resolve_invocation()` call (a separate construction site from `execute_scan`'s chain) never threads `owner_instance_id`/`run_id`, so Detach's subprocess-termination guarantee silently does nothing for CHECK_SUITE. Fixed: threaded ownership through `run_workflow_suite()` itself.
7. **R10-07** — a stray cross-reference sentence claimed P69-01.2 "depends on" a durable admission table P69-02 implements — backwards; P69-01.2 owns and defines that table itself (its own subsection f). Fixed: corrected the sentence.
8. **R10-08** — the cleanest, most concerning finding: my own cleanup preserved a test name (`test_resume_pre_execution_guard_is_a_separate_cheap_check_not_the_consumption_aggregate`) and a VERIFY mention, but dropped the actual GREEN design paragraph defining what that pre-execution guard field *is* — a real content-preservation defect the test-name-diff script couldn't catch, since it only diffs test names, not design prose. Verified against `project_run.py:886,1121,1494` (all three genuinely need a value before any scan executes) and the original round-8 scratch text. Fixed: restored the full design paragraph.
9. **R10-09** — staging only the bounded scan inventory (which excludes `node_modules`/`.venv`/etc. per the repo's own ignore convention) breaks any engine needing live dependency/config resolution (ESLint, TSC) when pointed at the staged copy. Fixed: defined a read-only-symlink exception for dependency-bearing engines' own resolution directories.
10. **R10-10** — the CLI (`rush memory maintain`) and an existing regression test (`tests/test_phase62_maintenance.py:64`) both call `run_maintenance_cycle()` directly with no `owner_scope`, and neither is in P69-07's own VERIFY scope — a required-parameter change would break both, discovered only later at P69-08's full-suite run. Fixed: added explicit CLI flags with a real (non-wildcard) default, migrated the existing test, added it to P69-07.4 VERIFY.
11. **R10-11** — the suggested generation-counter file path (`.../attempts/.generation`) sits *inside* the `attempts/` directory, which `tests/test_project_run_lifecycle.py:416,430` asserts contains exactly N entries for N real attempts. Fixed: moved the counter to a sibling path, added `test_project_run_lifecycle.py` to P69-02.4 VERIFY per the correction's own instruction.
12. **R10-12** — cleanup dropped the actual TTL duration (24 hours), keeping only when the clock starts. Verified against the original round-1 scratch text. Fixed: restored the explicit duration.

Every fix independently re-verified against real source after applying it (subsection-letter cross-references checked against the document's own actual lettering, not assumed). Whole-document test-name diff against the pre-round-10 commit (`7e35151`) confirms zero unintended drops — the only "missing" name is a deliberate rename (`test_unpublished_run_id_reports_not_published` → `test_unpublished_run_id_reports_not_yet`, part of the R10-01/02/03 fix). Packet/step sequence (RED→GREEN→CONNECT→VERIFY, P69-01→08) confirmed intact, 37 markers, same as before.

This round found real defects the same way rounds 3-9 (prior sessions) did — including inside this session's own cleanup work (R10-08), not just inside earlier rounds' fixes. Consistent with this plan's own established pattern: each review round finds something the previous one missed. Given the `/goal`'s explicit scope was one Codex review with all findings addressed (not an open-ended iterate-to-zero loop), and this round's findings are now fixed and independently verified, this document treats the remediation as complete pending final commit.
