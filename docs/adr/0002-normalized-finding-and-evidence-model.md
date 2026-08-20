# ADR 0002: Normalized finding and evidence model

## Context
Different local engines emit incompatible report formats.

## Decision
Keep the five public statuses and extend `Finding` additively with optional rule identity, remediation, evidence, provenance, freshness, and deterministic fingerprint fields. Redact secret-like assigned values before a finding is returned.

## Rejected alternatives
Replacing `ToolResult`, engine-native result contracts, and unredacted raw evidence were rejected.

## Consequences
`src/rush/tools/base.py` and `src/rush/tools/common.py` normalize compatible fields and stable order. `ReviewTool` and review aggregation use the same fingerprint identity; aggregation retains provenance while deduplicating. Direct heuristic findings get a redaction-safe local source-location evidence packet only when no richer evidence was supplied. A caller may compare an explicit in-memory fingerprint baseline to obtain `existing`/`new` freshness; no baseline storage is implicit. Tests: `tests/test_phase00_contract.py`, `tests/test_tools.py`, and `tests/test_routing.py`.

## Compatibility and operations
Existing consumers can ignore optional fields. Timeout/cancellation remain `error` with additive metadata, never new status values.
