# ADR 0005: Optional engine version compatibility

## Context
External engines are not Rush dependencies and change independently.

## Decision
Each supported adapter has one exact tested engine baseline, version probe, public compatibility record, and local research evidence. Unknown or unverified candidates remain feasibility-gated.

## Rejected alternatives
Unbounded versions, implicit host-version support, and bundled scanner SDKs were rejected.

## Consequences
`Engine.version()` uses the shared process policy. Public compatibility guidance owns version/install/output behavior; local research remains untracked.

## Compatibility and operations
Missing or unparsable versions do not crash Rush. Tests: `tests/test_phase00_subprocess.py`, `tests/test_engines.py`.
