# Incident & Security Handling Protocol

This runbook defines the operational protocol for handling security vulnerabilities, credential leaks, and safety boundaries in Rush CLI.

---

## 1. Security Sensitivity Classifications

The following events are treated as high-priority security incidents:
- **Credential Disclosure / Leakage**: Raw secrets, tokens, or private keys appearing unredacted in findings or logs.
- **Subprocess Escape / Injection**: Arbitrary shell execution or path traversal outside project boundaries.
- **MCP Protocol Pollution**: Engine stdout polluting FastMCP stdio transport frames.
- **Unauthorized Side Effects**: Any engine performing remote downloads, network writes, or git mutations without explicit `--allow-*` flags.

---

## 2. 7-Step Security Response Workflow

1. **Private Triage**: Move issue to a private advisory; do not ask for public reproduction data.
2. **Containment**: If vulnerability is reproducible, isolate the affected engine adapter.
3. **Synthetic Reproduction**: Create sanitized unit tests that reproduce the vulnerability without real credentials.
4. **Fix & Redaction Verification**: Implement fix using strict subprocess isolation and regex redaction.
5. **Regression Testing**: Run `pytest tests/ -q` and verify all security reference test suites.
6. **Security Advisory & CVE**: Publish GitHub Security Advisory with remediation steps.
7. **Release Patch**: Bump patch version and publish updated wheel.

See [Security Policy](../SECURITY.md) and [Permissions](../safety/permissions.md).
