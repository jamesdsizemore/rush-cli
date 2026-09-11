# Stale "rescan is a disclosed gap" comment remains in scan_handoff.py's module docstring

Status: needs-triage

## Observed evidence

T027 implemented and wired `rush_scan.rescan` for real. T029 (board `phases-64-63-65-66`) corrected the same stale claim in `src/rush/mcp.py` (2 spots) and `src/rush/cli.py:3076-3078`, but flagged a fourth instance at `src/rush/tools/scan_handoff.py:23`'s module docstring that it could not touch because that file was outside T029's `allowed_files`.

## Intervention assessment

Purely a stale-comment accuracy issue -- no functional impact, rescan itself works and is tested. One-line fix whenever a task next touches `scan_handoff.py`.

## Scope

Outside every currently-defined task's allowed_files on the `phases-64-63-65-66` board. Fix opportunistically the next time a task legitimately edits `src/rush/tools/scan_handoff.py`, or dispatch a trivial one-line fix task if none arises before this board's final audit.
