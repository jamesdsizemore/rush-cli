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

---

## 3. Sanitization & Diagnostic Invariants (Phase 53)

Maintainers must verify that all newly added tools, exports, and logging calls comply with Phase 53 invariants:
- **Zero Unredacted Persistent Writes**: Any write to `.rush/` or exported files (SARIF, HTML, attestation statements, IAM policies) must pass through `sanitize_value` or `SecretRedactor.redact_text`.
- **Zero Raw Exceptions to Logs**: Exceptions logged to stderr must format tracebacks safely and redact secrets from messages and stack traces.
- **Fail-Safe Logging Fallback**: `NdjsonHandler` must never raise unhandled exceptions or drop log records silently.
- **Strict Stdout Purity**: Subprocesses, background threads, and logging handlers must never write directly to `sys.stdout`.

## 4. Physical Containment & Verifier Security Invariants (Phase 55)
- **Zero Path Traversal / Symlink Escapes**: Disk operations targeting repository workspaces must use `PhysicalRoot.open_contained()` (`src/rush/io/physical_paths.py`), which fail-closed blocks absolute paths, parent traversals (`..`), symlinks across all parent directories, and Windows reparse points.
- **Fail-Closed Atomic Replacement**: File writes must use `AtomicFile` (`src/rush/io/atomic_file.py`) with same-directory unique temporary files (`.rush_tmp_`), explicit `flush()` and `os.fsync()`, and owned-temp cleanup only. Target files must never be corrupted by partial writes.
- **Non-Recoverable Capability Storage**: Stored tokens, locks, or trust credentials must never persist raw secrets. All capability verification must use `VerifierRecord` (`src/rush/io/verifier_record.py`) storing only PBKDF2-HMAC-SHA256 salted hashes with constant-time verification.

### Plugin Trust Breach Triage (Phase 56)
If a malicious plugin closure is detected, run `rush trust plugin <name> --revoke` immediately. The user ledger will purge the capability record and delete the snapshot directory.

## Cache & Egress Incident Procedures (Phase 57)

If cache poisoning is suspected:
1. Purge cache with `rush cache clear` or remove the SQLite database.
2. Verify provider API keys and review egress logs for unauthorized redirect attempts.
