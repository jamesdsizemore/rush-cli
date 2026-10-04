# Phase 71 adversarial plan review

Verdict: **READY as an implementation specification.** No unresolved plan findings or design decisions. Implementation has not started and remains gated on Phase 70 T1–T25/G0–G7 completion. Browser, installed/native and behavioral acceptance are required implementation work, not claimed by this review.

Subject: `docs/phase-plans/phase-71-prototype-dashboard-integration-plan.md`

Current SHA-256: `f8c7b66fa9dbacf07aa1c32db2982c6f7fb73fdd7da1738b6da20357c43cc323`.

Original integration-review SHA-256: `888aa356d407e252b95a8c1d09490344c4e272edd16430c2f9e40d1da31af8b0`. Current revision adds only the typography amendment reviewed below.

## Authority and evidence

Controlling request: integrate the full current `research/dashboard-prototype/` as Rush's app dashboard; preserve every surface; align with Phase 70/repository; TDD; implementation-ready tasks, resolved decisions, named documentation work; adversarially review every task before handoff. Global and repository AGENTS.md plus `orchestrate` skill were read. Coordinator alone edited plan; scouts/reviewers stayed read-only.

Live source review covered prototype README, reference ledger, HTML, JS, CSS and assets; canonical dashboard routes/auth/state/map/actions; shared scan, memory, telemetry, project, provisioning and agent implementations; package/release configuration; Phase 70 and task template; named documentation and coverage helpers. Prototype requirements were retained independently of sample implementation maturity. No external product substitution or new mockup was used.

| Assignment | Model / effort | Scope |
|---|---|---|
| prototype_inventory | GPT-6 Sol / low | All eight sections, controls, assets, responsive/motion states and sample boundaries. |
| runtime_integration | GPT-6 Sol / low | Canonical server, shared producers, tests, sessions/events/actions, package seams. |
| phase70_alignment | GPT-6 Sol / low | Phase 70 dependencies, local template, docs targets; focused P14/global correction check. |
| review_ui | GPT-6 Astra / high | P01–P04/P11–P13; R01/R02/R09; graph, assets, lifecycle, motion, packaging and browser feasibility. |
| review_workflows | GPT-6 Astra / high | P05–P10; R03–R08; actual APIs/producers, permissions, persistence, identity and recovery. |
| Coordinator | Current session model | Sole writer; integrated findings, P14/global final review, R10, finite ownership, provenance and structural checks. |

An attempted additional reviewer hit agent-thread limit; no review is claimed from that attempt. Existing reviewers and coordinator completed all assigned coverage.

## Frozen passes and finding closure

Draft A `d852294af91fb98c94da678d25ddc008955d907020cd2936e190878b4ca169ef`: NOT READY. Draft B `6a8a276a87873cc53500f8fba8ff428eb8953ab487f3dfac522ed533dd062508`: original findings largely closed; strict replay reader and pure scan/resolution contracts still blocked readiness. Both superseded after edits. Original integration-review hash above received READY from both high-reasoning reviewers; coordinator reviewed its global/P14 content read-only. Those reviewers did not review the subsequent typography amendment.

| Packet | Adversarial coverage and final disposition |
|---|---|
| P01 | Complete shell/CSS/fonts/SVG/licenses, resource allowlist/MIME/CSP; tracked asset baseline removes ignored-research dependency from installed tests. Closed. |
| P02 | All project pages, persistent preferences, request disposal, auth/reconnect. Independent event cursor requires read-only watermark-before-snapshot resync; retention/race tests specified. Closed. |
| P03 | Canonical directory producer/containment, pathless records, grouped paging and explicit one/two-hop cursor identity; no fixture graph substitution. Closed. |
| P04 | Complete scene/control/motion coverage; historical replay uses owned strict same-byte reader, explicit missing/corrupt/empty states and durable attempt identity. Closed. |
| P05 | Phase 70 status/readiness/scope/memory receipts mapped by producer; current attempt distinct from published results. Closed. |
| P06 | Complete attempt history, reviewed attempt on resume/rescan, operation-ID cancellation; pure scan preview, full reviewed plan validation and grant-gated staging. Closed. |
| P07 | Owner/version checks, inverse archive, batch deletion payload, fresh promotion candidate preserving original record/trust. Closed. |
| P08 | Actual token events without handoffs, read-only telemetry opening, missing/old/corrupt DB states, unavailable provenance/billing; Git paging/revision identity. Closed. |
| P09 | Standard findings/manifest/handoff producers, complete canonical serialization and immutable paging, raw-byte distinction, secret exclusion; handoff preview read-only classification and canonical handoff_id. Closed. |
| P10 | Bounded explicit-root discovery, full reviewed provision plan, exact resolution-only request/digest/grant path; project/session/data-root-bound agent preview/apply/status and separate consent. Closed. |
| P11 | All viewport/keyboard/focus/contrast/motion states; reduced mode forbids spatial animation while permitting ≤80ms opacity. Closed. |
| P12 | Wheel, sdist and actual frozen executable/archive; explicit release resource inclusion, offline assets and native launch/service acceptance. Closed. |
| P13 | Existing Playwright MCP filename runtime verified callable; concrete scenario selectors, real backend fixtures, download save/read/hash and measurement requirements; full regression and frozen review. Closed. |
| P14 | Phase 70 G0–G7 gate, all named docs exist, exact receipt procedure and executable link/check command; historical ADR bodies preserved via allowed Current status prefixes. Closed. |

R01–R10 all map to packets and acceptance. Review included user outcome, dependencies, runtime contracts, sequence, assets, write ownership, failure/recovery, security, adversarial cases and readiness semantics. Neither sample browser checks nor static tests count as production acceptance.

## Original integration-plan verification

- Original integration-review hash verified by both high-reasoning reviewers and coordinator.
- Structural assertions passed: P01–P14 exactly once; every packet contains Required behavior, Deliverables, Constraints, RED→GREEN/Checks and Completion; R01–R10 present; obsolete undefined Python browser-driver placeholder absent.
- Every literal §8.2 documentation target exists. No TODO/TBD or trailing whitespace in final plan. `rtk git diff --check` passed; direct whitespace check also covered untracked plan.
- AGENTS.md, Phase 70 plan and prototype app/panels/scene SHA-256 values match captured input baseline. Git status retained pre-existing user changes; no application implementation changes or commit were made.
- Original planning work created only Phase 71 plan and this review receipt. Application tests, native/browser runs, asset generation and implementation documentation updates were not executed; their exact ownership and acceptance remain in plan.

## Typography amendment — 2026-09-24

User authorized the proposed refinement with “Please tighten.” Coordinator reviewed frozen current plan hash above and prototype CSS hash `d2d916cdae85c09429c128e8a96310ae407000b6d6a3e52115e95155fec64309` read-only. Scoped verdict: READY; no unresolved amendment findings.

- Exactly two prototype CSS changes: `.scene-card-count` inherits existing Plex Sans body rule; `.timeline-event time` selects Plex Sans. Both use `font-variant-numeric: tabular-nums`. Barlow Condensed logo/headings and Plex Mono technical content remain unchanged; no new assets or dependencies.
- P01 specifies the refinement; P11 specifies computed-font, numeral, viewport and project-switch acceptance. Prototype README records the same refinement. Removing the two added plan paragraphs reconstructs the exact original integration-review hash; removing the README note reconstructs its original hash. Full integration requirements remain intact.
- Cache-disabled live prototype browser checks passed at 1440×960 and 390×844: all five category counts and both timeline timestamps compute to Plex Sans plus tabular numerals; brand/headings retain Barlow Condensed, keyboard technical text retains Plex Mono; no horizontal page overflow. No screenshots generated.
- This verifies prototype typography only. Live production integration, project-switch acceptance and all Phase 71 implementation gates remain required work; no production implementation or commit occurred.

Planning completion is distinct from Phase 70 prerequisite completion, Phase 71 implementation, release approval and user visual ratification. No unresolved design choice is delegated to implementation.
