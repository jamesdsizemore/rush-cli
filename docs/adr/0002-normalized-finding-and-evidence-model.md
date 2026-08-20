# ADR 0002: Normalized finding and evidence model

## Context
Different local engines emit incompatible report formats.

## Decision
Keep the five public statuses and extend `Finding` additively with optional rule identity, remediation, evidence, provenance, freshness, and deterministic fingerprint fields. Redact secret-like assigned values before a finding is returned.

## Rejected alternatives
Replacing `ToolResult`, engine-native result contracts, and unredacted raw evidence were rejected.

## Consequences
`src/rush/tools/base.py` and `src/rush/tools/common.py` normalize compatible fields and stable order. Tests: `tests/test_phase00_contract.py`.

## Compatibility and operations
Existing consumers can ignore optional fields. Timeout/cancellation remain `error` with additive metadata, never new status values.
