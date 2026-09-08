Current status: historical decision; The accepted boundary-framing requirement remains, but current XML framing is not evidence that all MCP output is cryptographically signed or that prompt injection is neutralized. The old session-memory database is superseded by [ADR-0049](0049-typed-artifact-memory-schema-and-trust-tiers.md); [security model](../safety/security-model.md) describes current trust limits, and [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) governs remaining memory capabilities.

# ADR-0020: Cryptographic HMAC Context Boundary Framing

## Status
Superseded by [ADR-0049](0049-typed-artifact-memory-schema-and-trust-tiers.md) for its
`.rush/session_memory.db` storage detail; the HMAC boundary-framing decision remains in
force.
Accepted

## Context
Indirect prompt injections embedded in repository comments, untrusted dependencies, or test fixtures can hijack autonomous agent reasoning loops during diagnostic scans.

## Decision
1. Wrap all MCP tool outputs and diagnostic strings in cryptographically signed XML boundary tags (`<rush_agent_sandbox hmac="...">`).
2. Generate SHA-256 HMAC signatures using session keys stored in `.rush/session_memory.db`.
3. Provide verification utilities allowing coding agents and harnesses to validate that diagnostic payloads have not been tampered with or injected.

## Consequences
- Zero-overhead boundary authentication neutralizing prompt injection attempts.
- Clean separation between machine diagnostic data and agent execution instructions.
