# Routing and language support

`detect_project_languages` checks marker groups in stable catalog order. File collectors sort paths and skip hidden/generated trees. Tool-specific maps select engines, and `aggregate_results` applies stable status, provenance, metric, artifact, and finding rules.

To add a language:

1. Add a marker tuple in deterministic priority order.
2. Add applicable extensions/markers to EngineSpec.
3. Add tool route(s) that invoke only when the project is eligible.
4. Write fixture routing tests for single-language, mixed, absent marker, missing engine, and stable ordering.
5. Stub `run_engine` in broad routing tests so the host's Go/Cargo/npm/etc. cannot leak into evidence.
6. Add a bounded real-engine contract only where CI intentionally provisions it.
7. Update checking-code, compatibility, engine, and tool references.

Never treat a `Path.glob()` generator itself as truthy; use `any()` over matches. Keep aggregation independent from filesystem iteration order.
