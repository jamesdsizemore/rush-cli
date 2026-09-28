## 6. P69-09 — Codex adversarial review remediation (2026-09-18)

Source: `docs/reports/69-dashboard-tui-codex-implementation-review.md`, reviewing frozen implementation `ea88324eae379c96b4fb2553d7247ea340b3cc16` (commits `b7966af`, `ea88324`) against this plan's own §3 (its five original superseding clauses plus the sixth P69-08.2 added) and Phase 66's §3. Verdict: **NOT COMPLETE / NO-SHIP**. This section records 51 of 51 findings (35 P1, 16 P2) from that review — S01-S16 (16 of 16, security/execution/recovery), M01-M21 (21 of 21, map/provenance/memory/telemetry/artifacts), U01-U11 (11 of 11, browser/terminal), D01-D03 (3 of 3, documentation/evidence) — zero deferred, zero descoped.

Every citation below was independently re-checked against real current source at the same frozen HEAD while drafting this section, not taken on the review's word alone (verified-by: `git log -1` confirming HEAD is still `ea88324` and `git status` showing a clean tree before drafting began; each S/M/U/D finding's own **Evidence** line below was then individually re-read against the live file at the cited path, with any drift called out inline per finding, e.g. U01's corrected `terminal_input.py` line numbers below). This matches the discipline §3's own text already requires ("don't trust this document's citations without re-reading the cited code first," §5).

Files: this section threads corrections through the files P69-01 through P69-08's own §4 lists already name, since each finding below is a correction to work already done inside those packets, plus the additional files each finding's own **Evidence**/**GREEN** entry names explicitly. No new packet directory or second implementation surface is created.

### Packet ownership (51 of 51 findings mapped below; none is un-owned)

| Findings | Extends packet(s) | Why |
|---|---|---|
| S01-S05, S11-S13, S15 | P69-01 | HTTP/session security hardening, ownership fencing, admission control — same files P69-01.2 already edits |
| S04-S10, S14, S16 | P69-02 | Action/mutation contract enforcement, CAS, attachment/cancellation — S04 also supplies P69-01's reservation contract, so it is jointly owned with P69-01 per the dependency note below |
| S01-S03 | P69-06 (in addition to P69-01) | The TUI-specific consumers of P69-01's ownership/lock primitives (`tui.py`'s scan dispatch) live in P69-06's file list |
| M01-M06, M13, M15-M21 | P69-03 | Live map population, staging, provenance, historical cursors |
| M07-M14 | P69-07 | Memory ownership scope, telemetry attribution/filtering, artifact/Git browse paging |
| U05, U10 | P69-07 (in addition to P69-03/P69-04) | Artifact-download and memory-ownership-form fixes are client-side counterparts to M12/M08, which P69-07 owns server-side |
| U01-U04, U09 | P69-06 | TUI startup/interaction contract, key/pane/theme/layout, terminal-capture harness |
| U05-U07, U11 | P69-04 | Browser application wiring: visible forms, artifact download control, shell-readiness regression |
| U08 | P69-05 | Motion/responsive/recovery acceptance |
| U06 | P69-02 (in addition to P69-04) | Handoff preview/send contract is primarily a server-side (S06/S16) fix that P69-04's visible form then consumes |
| D01-D03 | P69-08 | Plan and evidence reconciliation |

### Repair sequence (binding order — a later step's fix must not be started before its dependency closes)

1. **Execution safety first:** S01-S05, S07-S10, S15-S16, U02-U03, then the auth/redaction/header/schema-validation gaps S11-S14. These establish the ownership, recovery, and CAS primitives every later finding's own regression test assumes already hold.
2. **Immutable provenance/history and ownership second:** M01-M09, M12-M13, M15-M21 (all four scan producers and all user transports), then telemetry/paging M10-M11/M14.
3. **User routes third:** U01, U04-U08, U10-U11, including browser content downloads, visible handoff, independent shell timing, and runtime motion/recovery/accessibility proof — each of these has a hard dependency on a specific earlier-step finding named in its own **GREEN** section below (e.g. U05 on M12, U06 on S06, U10 on M08).
4. **U09's test-harness repair fourth,** then the full required packet VERIFY commands plus one complete frozen-byte full-suite regression.
5. **Documentation and sign-off last:** D01-D03, plus establishing row 18's timing-threshold approval receipt (D03's explicit sub-task), then a new independent adversarial review against the corrective frozen hash before this phase is reconsidered complete (§5).

**Cross-finding dependencies named explicitly (a coding agent executing one of these findings out of this order will hit a missing primitive, not a subtle bug):** S04 supplies persisted effect/reservation inputs S05 and S16 both require. S02 (dead-owner fencing) is independently repairable and does not require S09's attempt-schema work. S03 supplies the native Windows owner primitive other findings assume exists. S09 supplies exact scan-attachment identity that S10 (durable cancellation) and U02 (dashboard-owned operation polling) both consume. S08, M01, and M02 must agree on one shared publication/genesis-identity contract without nesting project/run locks — implement them together, not as three independent patches to the same lock ordering. M01 is a prerequisite for M07 (memory-mutation refresh). M02, M03, M13, and M15-M21 share one provenance/evidence-identity contract — implement the shared contract once, then apply it at each of those call sites. M12 is a hard prerequisite for U05 (paged download has no route to call without it). M08 supplies the authenticated session-owner exposure U10's browser control needs; M09 extends the same ownership contract to every maintenance caller. S04-S07 and S16 must all land before U06 (visible handoff) can close — U06's own **GREEN** section states this explicitly. Provisioning keeps its own durable job identity; S07/S16 must not force it into scan-admission attachment machinery. Every shared correction below gets exactly one implementation reused by every affected caller — no finding re-implements a fix another finding already owns.

