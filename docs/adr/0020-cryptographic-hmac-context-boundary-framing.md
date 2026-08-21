# ADR-0020: Cryptographic HMAC Context Boundary Framing

## Status
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
