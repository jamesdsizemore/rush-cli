# Agentic Rush/Anti Hallucination

## Anti-Hallucination Guardrails (Phase 43)
* **Static Import Verification**: `rush hallu-guard` validates AST imports.
* **Mistake Miner**: `rush context mistakes` loads bi-temporal Git revert history.
* **Failure Ledger**: Stores failed-patch fingerprints for explicit inspection; it is not an interceptor for arbitrary agent commands.
* **Continuity receipt**: exposes a redacted failure receipt or a tombstone and labels historic instruction with a `trust_tier` (Phase 61's unified typed-artifact schema — never `STATED` on entry, replacing the earlier binary quarantine flag), preventing a resumed agent from inventing authority from old context.
