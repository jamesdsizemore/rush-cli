# Security Policy & Vulnerability Reporting

Rush prioritizes code security, execution isolation, and responsible disclosure.

---

## 1. Security Architecture Highlights

1. **Subprocess Isolation**: External engines are launched using `stdin=subprocess.DEVNULL`, `shell=False`, and a 120s timeout, preventing arbitrary shell expansion and MCP pipe corruption.
2. **Automated Secret Redaction**: High-entropy strings, API keys, tokens, and credentials identified by secret scanners or stderr logs are masked as `[REDACTED]`.
3. **Execution Permissions**: Destructive, network-accessing, or resource-heavy operations require explicit `--allow-*` permissions.
4. **Offline Safety**: All security adapters default to local, offline analysis.

---

## 2. Reporting a Vulnerability

If you discover a security vulnerability in Rush CLI:
1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately via GitHub Security Advisories or by emailing maintainers.
3. Include a detailed description, steps to reproduce, and a proof of concept.
4. Never include real production secrets, API keys, or private code in vulnerability reports.

See [Security Model](safety/security-model.md), [Incident & Security Runbook](maintainers/incident-and-security.md), and [Permissions](safety/permissions.md).
