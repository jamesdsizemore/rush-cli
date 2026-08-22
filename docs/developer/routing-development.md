# Routing and language support

`detect_project_languages` checks marker groups in stable catalog order. File collectors sort paths and skip hidden/generated trees. Tool-specific maps select engines, and `aggregate_results` applies stable status, provenance, metric, artifact, and finding rules.

For review coordination, aggregation is deliberately serial and records compact
child tool/engine/status evidence plus partial status when a child skipped or
errored. It uses the ADR-0002 shared fingerprint helper before review dedupe.
`build_finding_baseline()` is a deterministic, in-memory fingerprint collector:
it does not create, overwrite, or persist a file. An explicit caller may pass
that collection back to review aggregation to receive `existing`/`new`
freshness; absence remains `unknown`.

`ReviewTool` accepts `changed_files` only as an explicit, target-contained list;
it performs no Git-diff discovery. Direct heuristic findings without existing
engine/Graft evidence receive a compact local source-location evidence packet
for repair consumers. Do not overwrite a supplied evidence object.

To add a language:

1. Add a marker tuple in deterministic priority order.
2. Add applicable extensions/markers to EngineSpec.
3. Add tool route(s) that invoke only when the project is eligible.
4. Write fixture routing tests for single-language, mixed, absent marker, missing engine, and stable ordering.
5. Stub `run_engine` in broad routing tests so the host's Go/Cargo/npm/etc. cannot leak into evidence.
6. Add a bounded real-engine contract only where CI intentionally provisions it.
7. Update checking-code, compatibility, engine, and tool references.

Never treat a `Path.glob()` generator itself as truthy; use `any()` over matches. Keep aggregation independent from filesystem iteration order.

## Content Routing Architecture (Phase 41)
`ContentRouter` (`src/rush/token_economy/router.py`) handles automated detection of payload types and calculates exact BPE token budgets via `tiktoken`.
