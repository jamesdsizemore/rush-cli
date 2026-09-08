# Phase 61/62 review remediation

Status: implementation, TDD and independent review complete on `codex/phase-61-62-review-fixes`; user authorized committing the reviewed changes. Final evidence: [verification.md](verification.md). Seven pre-existing repository test failures remain outside this remediation.

## Goal

Correct all eleven findings from the review of `fc2d642efc4fbf40a25abd3d98a212f7d3a6181a`, with a failing regression test before each fix and independent review of the integrated result.

## Scope and non-goals

Work only in `codex/phase-61-62-review-fixes`, based on the reviewed feature branch, at `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes`. Preserve the original checkout and feature worktree. No main edits, release changes, pushes, hooks, new provider integrations, or live paid model calls. Commit authorized by the user's follow-up after verification. Existing Phase 61/62 plans remain specifications; this file records remediation, not replacement scope.

## Findings and acceptance

| ID | Finding | Required regression |
|---|---|---|
| 1 | Maintenance uses cwd instead of requested root | With cwd A and target B, only B changes; grounding and lock path use B. |
| 2 | Maintenance ignores write permission | Denied CLI/MCP maintenance performs no mutation; allowed invocation works. |
| 3 | Cached packs lack freshness baseline | Body edits, full-file edits, and deleted targets cannot return obsolete packs. |
| 4 | Approved promotion remains at entry tier | Recalled approved row is STATED with matching checksum and promotion timestamp. |
| 5 | Default session path creates nested database | Session writer and migration use the same repository database; custom file paths remain isolated. |
| 6 | List exposes undefended content | Listing cannot return cross-session or Trojan Source content without recall defenses. |
| 7 | SDK/ACP dispatch reports success without delivery | Real adapter path receives payload and acknowledges it; missing/failed acknowledgement is not success. |
| 8 | Migrated preference deletion resurrects values | Delete survives get/list, overrides, and migration reruns. |
| 9 | Non-expiring rows starve expiry | Small batches still reach overdue expirable rows behind STATED rows. |
| 10 | MCP session output ignores history bound | Output contains only the latest configured number of turns in chronological order. |
| 11 | Migrated checkpoints disappear from listing | List/restore and prior-provider handoff lookup retain migrated checkpoints without duplicates. |

## Ownership and dependencies

- Core worker: `memory/store.py`, `tools/memory.py`, `memory/maintenance.py`, `memory/expiry.py`, `token_economy/memory_cache_gate.py`, `cli.py`, focused core regression tests. Owns findings 1–4, 6, 9. Shared store changes stay in this lane.
- Compatibility worker: `session_memory.py`, `memory/preference_store.py`, `memory/checkpoint_journal.py`, necessary compatibility helpers in `memory/migration.py`, focused compatibility tests. Owns findings 5, 8, 10, 11; requests shared-store APIs from core worker when needed.
- Transport worker: `memory/transport.py`, focused transport tests. Owns finding 7. Confirms actual optional SDK APIs before implementing; no guessed provider commands.
- Coordinator: task evidence, directly affected docs and public-operation metadata, integrated verification, independent review coordination, final corrections.

## Sequence

1. Freeze baseline, inspect contracts/callers, and record full-suite baseline.
2. Each implementation lane writes and runs failing behavior tests, then applies minimum fixes and verifies its assigned paths.
3. Integrate compatible APIs and update directly affected documentation/operation metadata.
4. Freeze changed-file hashes; run focused regressions, full suite, lint, and formatting checks using project Python 3.12.
5. Independent read-only reviewer checks all eleven findings, tests, shared callers, permission boundaries, and remaining regressions against frozen hashes. Fix actionable review findings, rerun affected checks, and re-review changed hashes before handoff.

## Verification

Use `/Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python` with `VIRTUAL_ENV` unset and `PYTHONPATH` pointing to this worktree's `src`. Prefix shell commands with `rtk`. Run `python -m pytest tests/ -q`; use installed Ruff for `check` and `format --check`. Record exact RED/GREEN commands and results in each lane receipt, then record integrated evidence in `verification.md` here. Compare unrelated failures against baseline rather than changing unrelated behavior.

## Risks and stop conditions

- Optional native/ACP packages may be absent locally. Verify against installed packages or official APIs; test payload/acknowledgement and process lifecycle locally without real credentials. Missing endpoint configuration must be explicit, never false success.
- Concurrent edits must remain inside ownership boundaries. Pause conflicting work and reconcile before changing shared files.
- Preserve migrated source files and original user changes. Do not weaken tests or plan requirements to obtain a pass.
- At an execution ceiling, perform a read-only recenter, retain completed evidence, and continue only unresolved work in this request. No downstream tasks.

## Reconciliation

Completion requires all eleven regressions fixed, integrated checks assessed against baseline, and independent review resolved. No completion claim follows from test counts alone. Record any exact external limitation separately from verified behavior.
