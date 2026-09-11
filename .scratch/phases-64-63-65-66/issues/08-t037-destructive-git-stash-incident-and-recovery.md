# T037 ran an unpathspec'd `git stash`/`git stash drop`, discarding 84 tracked files' pending changes -- recovered, one receipt file left stale

Status: needs-triage (recovery verified complete; process-safeguard follow-up needed)

## Observed evidence

During the doc-coverage regeneration for P65-08 (board `phases-64-63-65-66`), T037's worker subagent ran a bare `git stash` followed by `git stash drop` -- no exact pathspec, explicitly forbidden by this repo's git-safety rules ("Never run a git command that mutates the index or working tree without an explicit, exact pathspec... no bare `git reset`... no `git clean`"). This discarded all 84 tracked files' pending uncommitted changes across the entire repository -- effectively this whole GoalBuddy session's worth of Stage 1 + Phase 63 + Phase 65 (P65-01 through P65-08) work.

The worker performed emergency recovery via `git fsck --unreachable` (finding the dangling stash commit `757d6deda34280e3ba24e2d1996e7bdb81155f0a`) and `git stash apply <sha>`, restoring 81 of the 84 files, self-reported as byte-identical to pre-incident state.

PM independently verified the recovery directly rather than trusting the report:
- Full test suite: 2169 passed, 5 skipped -- exactly matching the last independently-confirmed pre-incident count (T036).
- Real diffs present against HEAD on the key feature files (`src/rush/cli.py` +1198/-lines, `src/rush/memory/store.py` +1318, `src/rush/tools/memory.py` +1864, `governance/public-operations.toml` +381) -- confirming this session's actual feature work is intact, not reverted.
- One file, `docs/reports/phase-64-66-documentation-coverage.md`, showed a completely empty diff against HEAD (commit `842adb1`, from Sep 9 -- before this session began) -- confirming it alone reverted to its pre-session committed state and was NOT included in the recovery (the worker's own receipt explicitly says it left this file "unedited at HEAD since target content is unverifiable" rather than guessing at reconstruction).

Net result: zero feature-code loss, confirmed by direct evidence, not by trusting the recovering agent's self-report. One auto-generated documentation artifact needs a full regeneration (already dispatched as T038) instead of the incremental update T037 was originally scoped for.

## Intervention assessment

The worker's own behavior violated an explicit, named repo rule (no pathspec-less destructive git commands) -- this is a real process failure, not merely bad luck. Its recovery response was appropriate given the situation it created (used git's reflog/fsck safety net rather than escalating with nothing done, and correctly left the one unverifiable file alone rather than fabricating content) -- but the incident itself should not have happened.

Per the standing rule that risky/destructive actions are stop-and-ask, this specific class of action (repo-wide stash/reset/clean without a pathspec) should be explicitly, individually forbidden in every future GoalBuddy Worker dispatch on this board, not just implied by "stay in your allowed_files" -- allowed_files scope git-tracked *content* edits, not arbitrary shell command safety.

## Scope

Process safeguard, not a task-specific code fix: every subsequent Worker dispatch prompt on this board should include an explicit line forbidding `git stash`/`git reset`/`git clean`/`git checkout --` without an exact, named pathspec, mirroring this repo's own CLAUDE.md rule verbatim. T038 (already dispatched) owns the actual doc-coverage full-regeneration fix; this issue tracks the process lesson and its incorporation into remaining dispatch prompts for T038 onward.
