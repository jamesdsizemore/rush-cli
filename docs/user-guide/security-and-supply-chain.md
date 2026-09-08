# Security & Supply Chain Protection

## Provider-continuation boundary

Provider continuation is an explicit local process invocation with no shell, no package installation, no profile mutation, and no retained provider output. Permission is per invocation. `9router_cli` uses a fixed local Codex bridge, child-process-only `RUSH_9ROUTER_API_KEY`, and no model argument; unsupported router routes are skipped rather than guessed or redirected.

Security shouldn't be an afterthought that only happens once a year during an external audit. In high-velocity development, security checks need to happen continuously as code is written.

Rush provides defense-in-depth across code privacy, secret detection, dependency vulnerabilities, and open-source license compliance.

Session handoff uses the same posture: explicit cache-write permission, local redacted receipts, and no provider credential persistence. A failure reference exposes a fingerprint and redacted error or a tombstone, never a patch body.

---

## 1. Catching Leaked Secrets & API Keys (`rush secrets`)

Accidentally committing an AWS secret access key, Stripe token, or database password to a public repository can lead to immediate compromise.

```bash
uv run rush secrets .
```

### What Rush Checks:
- High-entropy API tokens (OpenAI, GitHub, AWS, Stripe, Anthropic).
- Hardcoded passwords and private certificates (`.pem`, `.key`).
- Unredacted credentials in staged git changes.

### Automatic Output Redaction:
Whenever Rush encounters a secret in any log, finding, or terminal output, it automatically redacts the sensitive value as `[REDACTED]` to prevent secondary exposure in log collectors or AI prompt transcripts.

---

## 2. Auditing Vulnerable Dependencies (`rush security`)

Most modern applications rely on hundreds of third-party open-source packages. When a known vulnerability (CVE) is discovered in a package you use, you need to know immediately.

```bash
uv run rush security .
```

### What Rush Invokes:
- **Python**: Coordinates `pip-audit` to check packages against the PyPA advisory database.
- **Node.js**: Coordinates `npm audit` to check `package-lock.json`.
- **Containers**: Coordinates `Trivy` and `Grype` to scan base container images.
- **Static Security (SAST)**: Coordinates `Semgrep` and `Bearer` to find SQL injection, Cross-Site Scripting (XSS), and unauthenticated API endpoints.

---

## 3. Generating Software Bills of Materials & License Checks (`rush sbom`)

When shipping software to enterprise customers or open-source communities, you often need to prove which libraries you use and ensure you aren't accidentally violating restrictive copyleft licenses (like AGPL in proprietary commercial software).

```bash
# Generate a CycloneDX SBOM
uv run rush sbom . --output bom.json --allow-artifact-write
```

Rush coordinates `cdxgen` and `ScanCode` to audit dependencies, scan license terms, and generate standard CycloneDX and SPDX documents.

---

## 4. Evaluating AI & LLM Safety (`rush ai-eval`)

If your project builds with LLM prompts, agent workflows, or RAG systems, you need to test against prompt injection and jailbreaks:

```bash
uv run rush ai-eval .
```

Rush coordinates `Promptfoo`, `Garak`, and `DeepEval` to test that your AI system follows safety policies and refuses malicious prompts.

---

## Next Steps

- Learn about monorepos and advanced checks in [Advanced Checks & Monorepos](advanced-checks.md).
- Discover solutions to common issues in [Troubleshooting Guide](troubleshooting.md).

## 5. Polyglot Error Cataloging (`rush error-catalog`)
Extracts and documents exception pathways across Python, TypeScript, and Rust without leaking sensitive runtime details:
```bash
uv run rush error-catalog src/ --json
```

## 6. Copyleft Dependency Risk Matrix (`rush license-matrix`)
Audits dependencies across `pyproject.toml`, `package.json`, and `Cargo.toml` against an allowlist of permissive SPDX licenses:
```bash
uv run rush license-matrix . --json
```

## 7. Cloud IAM Policy Synthesis & Terraform Wildcards (`rush iam-audit`)
Statically extracts multi-cloud SDK operations and verifies that Terraform configurations do not contain dangerous wildcard actions (`*`):
```bash
uv run rush iam-audit . --output policy.json --allow-artifact-write --json
```

## Phantom Package Defense (Phase 43)
`rush hallu-guard` validates all import statements in your project against Python's standard library and installed distribution metadata, blocking supply-chain risks from unvetted AI hallucinations.

## 8. AI Code Provenance & Attribution (`rush provenance-ai`)
Audit Git commit history for AI generation trailers and track code survival:
```bash
uv run rush provenance-ai .
```

## 9. Honest Build Provenance Drafts (`rush attest`)
Generate an in-toto Statement v1 binding real distribution artifact digests from `dist/`:
```bash
uv run rush attest . --artifact-path dist/package.whl --out artifacts/provenance.json --allow-artifact-write --json
```

### Running Custom Plugins Securely (Phase 56)
When using community plugins or scripts from git repositories, Rush requires explicit trust authorization before execution. Run `rush trust plugin <name>` to approve the plugin closure.

## Secure AI Review and Network Boundaries (Phase 57)

Rush protects your code and credentials during AI reviews:
- Only approved HTTPS origins receive requests.
- Redirects to untrusted hosts are immediately blocked.

## Memory Trust Tiers (Phase 61)

Nothing an AI agent writes to Rush's memory is trusted by default: new records enter at `DERIVED`, `EXTERNAL_WRITE`, or `IMPORTED`, never `STATED`. Promotion to `STATED` requires passing an ALLOW/REDACT/BLOCK screen, a regex pre-filter against instruction-override/exfiltration patterns, a full-schema check, a grounding check against real files/symbols, and either your own explicit statement or corroboration from 2+ independent sources. Every recalled record is scanned for Trojan Source Unicode characters before it can re-enter an LLM context.
- Results are marked as AI-generated only when authentic model responses are received.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

Rush implements closed-loop resilience, fail-closed security, and physical containment across multi-agent concurrency, persistent memory, and AI-driven patch remediation (Findings R-009, R-010, R-011, R-016):

1. **Capability Locks & Verifier Custody (`rush.mcp_mesh`)**:
   - Callers retain high-entropy capability tokens (`LockCapabilityInput`) delivered exclusively via protected channels (`stdin`, `descriptor`, or sensitive MCP parameters); argv and environment leakage are rejected fail-closed.
   - `MeshLockManager` stores verifier-only records (`LockLeaseRecord`) generated via `rush.io.VerifierRecord` (PBKDF2-HMAC-SHA256, 100k rounds) with monotonic generation counters and `rush.io.PhysicalRoot` containment under `.rush/locks`.
   - Renewal and release verify caller capability in constant time (`hmac.compare_digest`); wrong, low-entropy, or stale tokens fail closed.

2. **CAS Map Transactions & Persistent Memory (`rush.memory`)**:
   - `CASMapTransaction` enforces optimistic concurrency with monotonic version numbers and atomic file replacement (`rush.io.AtomicFile`) using sanitized JSON payloads (`SanitizedJsonValue`).
   - Store states are truthfully separated into distinct typed exceptions: `StoreNotFoundError`, `StoreCorruptionError` (retaining raw bytes and SHA-256 digest), `StoreValidationError`, `StoreIOError`, and `CASConflictError` (exhausted retries fail closed).
   - `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` eliminate silent empty dict fallbacks.

3. **Atomic Checkpoint Journals & Unified Store Persistence (`rush.memory.checkpoint_journal`)**:
   - `checkpoint_journal.py` is a thin compatibility view over `TypedArtifactStore` (`rush.memory.store`, Phase 61): `save_checkpoint()`/`restore_checkpoint()` write/read each checkpoint as one `MemoryArtifact` row (`family="handoff"`, `subject="active_context"`); canonical data lives in `.rush/memory.db`, not a per-checkpoint JSON file.
   - `save_checkpoint()` still writes a physical `.json` artifact via `rush.io.AtomicFile` and returns its `Path` (`dest.exists()` holds), preserving the pre-Phase-61 contract for existing callers; explicit schema version `1.0.0` is unchanged.
   - Corrupted or unparseable checkpoint files are preserved on disk, cryptographically digested with SHA-256, and surfaced in `list_checkpoints()` with status `corrupt` — unchanged by the Phase 61 migration.

4. **Contained Patch Verification (`rush.patch`) — current safety repair pending**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Current failure cleanup can run broad `git reset --hard`, `git clean -fd`, and worktree cleanup. Do not use this as safe rollback evidence. Invocation-owned restoration is required by [Phase 64, P64-04](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-04--real-isolated-patch-application-f05-f2425-f43).

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### Supply Chain & Provenance (Phase 59)
Guide to generating truthful build provenance drafts and verifying signed packages with `rush attest --verify`.
