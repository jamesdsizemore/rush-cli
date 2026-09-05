# Phase 56 Implementation Plan: User-Owned Content-Addressed Plugin Trust

## 1. Purpose and Status

- **Operation:** Comprehensive implementation plan for Phase 56 remediation.
- **Planning Status:** Implementation-ready; fully verified against repo codebase and active development.
- **Implementation Status:** Authorized for strict TDD execution.
- **Authority:** Governing Roadmap finding R-003, ADR-012, and Control 6 (Plugin & Repository Trust Gating).
- **Predecessors:** Accepted Phase 53 sanitization diagnostics (`rush.safety.redactor`), Phase 54 result schema kernel (`rush.contracts.results.ToolResultV1`), and Phase 55 physical containment primitives (`rush.io.PhysicalRoot`, `rush.io.AtomicFile`, `rush.io.VerifierRecord`).
- **Successors:** Phase 57 (Invocation Scope & Cache Egress) and Phase 58 (Lock Persistence & State Verification).
- **Security Boundary:** External plugins execute untrusted user-supplied or third-party code. Rush provides immutable content authorization, complete closure verification, and protected secret transport; plugins execute in isolated subprocesses with strictly scrubbed environments. Plugins do NOT provide OS-level containerization or virtualization.
- **Protected Boundaries:** Roadmap requirements, dependency manifests, public non-plugin CLI/MCP operations, and release versioning.
- **Zero-Downscope Invariant:** This plan is the immutable contract. Stubs returning "unknown", permissive test assertions (`assert status in (...)`), or skipping transitive closure verification are strictly prohibited. Every covered failure mode must fail closed.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, release, hooks, history rewrite, live secret, or live network without explicit user instructions.

---

## 2. Authority, Predecessor Artifacts, and Concrete Evidence

Authority order: User instructions → `AGENTS.md` → Roadmap (`governance/remediation-contracts.toml`) → Phase 53-55 contracts → Current plugin source, CLI, MCP, and test suites.

### 2.1 Concrete Codebase Audit & Semantic Drift Identification

An exhaustive audit of the existing codebase against the requirements of R-003 identified seven critical vulnerabilities and architectural drifts:

1. **Drift 1: Authority Storage Location (Repository vs. User Ledger)**:
   - *Existing Code:* `src/rush/plugins/trust_store.py:26` stores trust records at `repo_root / ".rush" / "trust.json"`. Furthermore, `src/rush/plugins/trust.py:16` stores repository directory paths in `~/.rush/trusted_repositories.json`.
   - *Vulnerability:* A cloned repository can include a malicious pre-baked `.rush/trust.json` that grants execution trust to untrusted payloads. Directory-level grants allow any file subsequently placed into a trusted folder to run.
   - *Remediation:* Repository `.rush/trust.json` is strictly demoted to non-authorizing evidence. The sole authorizing store is moved to a user-owned ledger outside the repository (`~/.rush/plugin_trust_ledger.json`), written atomically via `rush.io.AtomicFile` within `rush.io.PhysicalRoot`. Cloned receipts are denied fail-closed.

2. **Drift 2: Content Hashing Scope (Single Executable vs. Transitive Closure)**:
   - *Existing Code:* `src/rush/plugins/trust_store.py:28-33` computes a SHA-256 hash solely of the single entrypoint file (`_compute_sha256(executable_path)`).
   - *Vulnerability:* A plugin script importing local helper modules, loading external configuration files, or relying on custom data assets can be mutated in-place while the entrypoint hash remains unchanged.
   - *Remediation:* Define and compute an immutable `PluginClosureManifest` that digests: (a) entrypoint executable bytes, (b) every imported script, resource, and asset in the plugin root, (c) plugin configuration table (`command`, `timeout_seconds`, `patterns`), (d) allowed environment variable names, (e) declared secret reference names/transports, (f) runtime/interpreter executable identity, and (g) platform binding.

3. **Drift 3: Execution Source & TOCTOU Mutation (In-Place vs. Materialized Snapshot)**:
   - *Existing Code:* `src/rush/plugins/executor.py:57` and `src/rush/plugins/loader.py:86` execute scripts directly from the mutable repository workspace directory (`cwd=self.repo_root`).
   - *Vulnerability:* Time-Of-Check to Time-Of-Use (TOCTOU) race: an attacker or concurrent process can tamper with source files between authorization verification and subprocess spawn.
   - *Remediation:* Upon trust grant, materialize an immutable content-addressed snapshot of pure copied bytes into `~/.rush/snapshots/<closure_digest>/` under `PhysicalRoot`. Reject all symlinks, directory junctions, and hardlinks. Subprocesses execute strictly from this immutable snapshot directory.

4. **Drift 4: Secret Transport & Exposure (Environment / Argv vs. Protected Channels)**:
   - *Existing Code:* `src/rush/plugins/sandboxed_env.py` strips known API keys from `os.environ`, but offers no mechanism for plugins to receive required credentials securely. Passing credentials via CLI flags or ambient environment exposes them to local process listings (`ps`, `/proc`, Process Hacker).
   - *Vulnerability:* Secret leakage across process table inspection and system logs.
   - *Remediation:* Enforce that literal secrets are strictly forbidden in manifests, configs, CLI flags, environments, ledgers, snapshots, and results. Secrets are declared as references (`secret:<NAME>`) and delivered strictly over protected channels (anonymous descriptor pipe, protected stdin JSON handshake protocol, or OS credential provider). Unsupported platforms or channels fail closed with zero child processes.

5. **Drift 5: Public Route Bypasses**:
   - *Existing Code:* `src/rush/plugins/loader.py:79-100` exposes `execute_plugin()`, which bypasses `HardenedPluginExecutor` and accepts `is_trusted: bool`. In `src/rush/cli.py:1283`, `plugin run` calls `execute_plugin()` directly. In `src/rush/plugins/executor.py:27`, `HardenedPluginExecutor.execute()` includes an `allow_untrusted: bool = False` parameter.
   - *Vulnerability:* Unhardened and unverified execution pathways remain accessible to callers.
   - *Remediation:* Deprecate and remove `execute_plugin()` from public loader surfaces. Remove `allow_untrusted` from `HardenedPluginExecutor`. Route `rush plugin run` exclusively through `HardenedPluginExecutor`.

6. **Drift 6: Output Schema & Error Handling (Legacy Dicts vs. ToolResultV1)**:
   - *Existing Code:* `src/rush/plugins/validator.py` and `executor.py` emit legacy dataclass `ToolResult` and untyped dictionaries from `rush.tools.base`.
   - *Vulnerability:* Non-compliance with canonical Phase 54 schema kernel (`ToolResultV1`, `FindingV1`).
   - *Remediation:* Adapt all plugin outputs to `ToolResultV1` using `AdminOperationAdapter(operation_id="cli.plugin_run", target_contract_id="ClickExitCode")` and validate findings using canonical severities (`info`, `warning`, `error`).

7. **Drift 7: Launch Verification Race Elimination**:
   - *Existing Code:* Subprocess invocation uses standard `run_subprocess` without atomic pre-flight identity check.
   - *Vulnerability:* Race conditions swapping interpreters or binaries before exec.
   - *Remediation:* Handle-bound pre-flight verification: immediately before `subprocess.Popen`, re-verify the closure digest, snapshot integrity, and interpreter identity. If any byte or attribute mismatches, deny execution fail-closed with zero child process creation.

---

## 3. Goals, Non-Goals, Operational Exclusions, and Security Boundaries

### 3.1 Primary Goals
1. Establish a single authoritative user-owned trust ledger outside the repository (`~/.rush/plugin_trust_ledger.json`).
2. Demote repository `.rush/trust.json` to read-only non-authorizing evidence; deny cloned receipts fail-closed.
3. Compute cryptographic `closure_digest` spanning code, dependencies, configuration, environment names, runtime, and platform.
4. Materialize immutable byte-copied snapshots in `~/.rush/snapshots/<closure_digest>/` defeating symlink/junction/hardlink tampering.
5. Provide protected secret delivery (descriptor pipe, stdin handshake, OS provider) with zero secret exposure in `argv` or `env`.
6. Bind process execution to verified snapshot bytes with handle-level pre-spawn reverification; guarantee approved bytes or zero child process.
7. Unify all public CLI/MCP plugin execution through `HardenedPluginExecutor` with `ToolResultV1` output compliance.

### 3.2 Non-Goals and Operational Exclusions
1. **No OS/Container Sandboxing:** Rush does not configure kernel namespaces, cgroups, Docker containers, or seccomp filters. Plugins run as user processes.
2. **No Dependency Fetching:** Rush does not download or install packages (`pip`, `npm`). All required dependencies must exist within the plugin root or runtime.
3. **No Network Proxying:** Network egress filtering is out of scope; security relies on content authorization and secret confinement.
4. **No Third-Party Dependencies:** 100% pure Python 3.12 standard library (`hashlib`, `hmac`, `secrets`, `pathlib`, `subprocess`, `os`, `stat`, `json`, `dataclasses`).

---

## 4. Admission Gate and Predecessor Verification

The following criteria must be verified prior to initiating Phase 56 development:
1. `governance/remediation-phase-55.toml` is present and valid with all 11 contract tests recorded as passed.
2. `src/rush/io/` primitives are available and operational:
   - `rush.io.PhysicalRoot` correctly blocks symlinks, traversal, and Windows reparse points.
   - `rush.io.AtomicFile` provides fail-closed same-directory atomic replacement.
   - `rush.io.VerifierRecord` provides PBKDF2-HMAC-SHA256 salted capability verification.
3. `src/rush/contracts/results.py` exports `ToolResultV1`, `FindingV1`, and `validate_tool_result`.
4. `src/rush/contracts/operations.py` provides `OperationRegistry` and `AdminOperationAdapter`.
5. Full repository test suite passes cleanly (1,063 passed tests).
6. Execution of P56.0.1 freezes baseline platform capabilities and maps all execution call paths.

---

## 5. Requirement-Ownership Ledger (R-003)

| Requirement ID | Finding Summary | Workstreams | Specific Contract Outcomes |
|---|---|---|---|
| **R-003.1** | Repository-bound trust store allows malicious cloned receipt attacks | P56.1.1, P56.1.2 | User ledger outside repository (`~/.rush/plugin_trust_ledger.json`); cloned receipt denied; grant/revoke/reapproval verified. |
| **R-003.2** | Single executable hash ignores imported modules, configs, and runtime | P56.2.1, P56.2.2 | `PluginClosureManifest` digests all files, configs, env names, runtime, and platform; transitive mutations trigger digest change. |
| **R-003.3** | In-place execution permits TOCTOU workspace mutation after grant | P56.2.1, P56.2.2 | Immutable content-addressed snapshot (`~/.rush/snapshots/<closure_digest>/`); copied physical bytes only; symlinks/hardlinks rejected. |
| **R-003.4** | Secret exposure in process `argv` and ambient environment | P56.3.1, P56.3.2 | Literal secrets rejected from manifests/configs/env; protected channels (pipe/stdin/provider) deliver credentials; child process invisible to `ps`. |
| **R-003.5** | Pre-spawn replacement races and substitute execution | P56.4.1, P56.4.2 | Immediate pre-spawn reverification; launch bound to snapshot directory; approved bytes or zero child process spawned. |
| **R-003.6** | Legacy execution bypass (`execute_plugin`, `allow_untrusted`) and legacy result dicts | P56.5.1, P56.5.2 | Eliminate public bypasses; route `rush plugin run` through `HardenedPluginExecutor`; adapt output to `ToolResultV1`. |
| **R-003.7** | Outdated documentation and governance tracking | P56.6.1 | All 42 identified docs and governance files updated and synchronized across `/docs` and repo root. |

---

## 6. Shared Architecture, State Invariants, and Data Structures

### 6.1 Data Structures & Contracts

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

@dataclass(frozen=True)
class PluginClosureManifest:
    """Cryptographic closure manifest for an external quality plugin."""
    schema_version: str = "1.0.0"
    plugin_name: str
    entrypoint: str  # Relative path within plugin root
    file_manifest: dict[str, str]  # {relative_path: sha256_hex}
    config_digest: str  # SHA-256 hex of canonicalized JSON config
    allowed_env_names: tuple[str, ...]
    declared_secret_refs: tuple[str, ...]
    runtime_identity: str  # e.g., "python3.12:sha256_of_interpreter"
    platform_identity: str  # e.g., "win32-x86_64" or "linux-x86_64"
    closure_digest: str  # SHA-256 hex of canonicalized manifest bytes

@dataclass(frozen=True)
class TrustedPluginRecord:
    """Ledger record for an authorized plugin closure."""
    name: str
    closure_digest: str
    snapshot_path: str
    granted_at: str  # ISO-8601 UTC
    granted_by: str  # "local_user"
    verifier_record: dict[str, Any]  # VerifierRecord serialized dictionary

@dataclass(frozen=True)
class SecretDeliveryContext:
    """Encapsulates protected channel parameters for subprocess launch."""
    channel_type: Literal["descriptor", "stdin", "provider"]
    env_overrides: dict[str, str]  # Scrubbed environment variables
    stdin_payload: bytes | None = None
    pass_fds: tuple[int, ...] = ()
```

### 6.2 Exception Hierarchy

- `PluginTrustError(Exception)`: Base class for all plugin trust and authorization exceptions.
  - `UntrustedPluginError(PluginTrustError)`: Raised when a plugin closure has not been explicitly granted trust in the user ledger.
  - `ClosureTamperedError(PluginTrustError)`: Raised when workspace or snapshot files do not match the expected cryptographic digest.
  - `SecretChannelError(PluginTrustError)`: Raised when declared secrets cannot be delivered over a supported protected channel.
  - `PluginExecutionError(PluginTrustError)`: Raised when subprocess launch fails pre-flight reverification or exits abnormally.

### 6.3 State Invariants
1. **User Ledger Invariant:** The user ledger (`~/.rush/plugin_trust_ledger.json`) is the sole authority. Cloned `.rush/trust.json` or in-repo receipts are never treated as authority.
2. **Snapshot Immutability Invariant:** Snapshots contain only pure byte copies of files under `rush.io.PhysicalRoot`. No symlinks, Windows directory junctions (`0x400`), or hardlinks are permitted.
3. **Secret Invisibility Invariant:** Literal secrets never appear in `argv`, `sys.argv`, `os.environ`, configs, snapshots, manifests, logs, or results.
4. **Pre-Spawn Verification Invariant:** Immediately before subprocess spawn, Rush re-verifies that snapshot files match the ledger's `closure_digest` and interpreter matches `runtime_identity`. If verification fails, zero child processes are spawned.
5. **Fail-Closed Output Invariant:** If a plugin outputs invalid JSON, unexpected keys, or times out, `HardenedPluginExecutor` returns a sanitized `ToolResultV1` with `status="error"` or `status="skipped"` and exit code reflecting failure.

---

## 7. Contract Test Inventory (T-56.01 to T-56.16)

Every requirement is guarded by an explicit, non-permissive contract test:

| Test ID | Test File | Test Function | Target Contract & Non-Permissive Assertion |
|---|---|---|---|
| **T-56.01** | `tests/test_phase56_plugin_trust.py` | `test_plugin_execution_fails_closed_without_content_digest` | **R-003 Governance Test:** Asserts execution of an unhashed or unregistered plugin fails closed with `UntrustedPluginError`; child count == 0. |
| **T-56.02** | `tests/test_phase56_plugin_trust.py` | `test_repository_receipt_never_authorizes` | Injects a pre-existing `.rush/trust.json` in repo; asserts `is_trusted()` returns `False` until user explicitly runs grant; child count == 0. |
| **T-56.03** | `tests/test_phase56_plugin_trust.py` | `test_cloned_repository_receipt_is_denied` | Simulates a cloned repo with foreign receipt; asserts authorization fails closed with code `RECEIPT_NOT_AUTHORIZING`. |
| **T-56.04** | `tests/test_phase56_plugin_trust.py` | `test_legacy_grant_requires_explicit_reapproval` | Migrates older Phase 28 path grant; asserts plugin cannot run without explicit reapproval with complete closure digest. |
| **T-56.05** | `tests/test_phase56_plugin_trust.py` | `test_revoke_invalidates_launch` | Grants trust, validates `is_trusted() == True`; revokes trust; asserts immediate subsequent launch fails closed with `UntrustedPluginError`. |
| **T-56.06** | `tests/test_phase56_plugin_closure.py` | `test_closure_digest_covers_every_code_and_behavior_input` | Mutates: (a) helper script, (b) asset file, (c) config table, (d) env names, (e) runtime; asserts `build_plugin_closure()` produces unique, differing digests. |
| **T-56.07** | `tests/test_phase56_plugin_closure.py` | `test_snapshot_contains_copied_bytes_not_links` | Materializes snapshot; inspects inodes/links; asserts symlinks and junctions are rejected with `ContainmentError` and files are independent physical copies. |
| **T-56.08** | `tests/test_phase56_plugin_closure.py` | `test_post_approval_mutation_uses_snapshot_or_denies` | Mutates source repo file after grant; executes plugin; asserts executed child observes unmodified snapshot bytes or fails closed if tampered. |
| **T-56.09** | `tests/test_phase56_plugin_secret_channels.py` | `test_literal_secret_is_rejected_from_argv_config_resource_and_environment` | Attempts to configure plugin with literal secret in command or env; asserts manifest validator rejects with `ValidationErrorV1`. |
| **T-56.10** | `tests/test_phase56_plugin_secret_channels.py` | `test_declared_protected_channel_is_not_visible_in_child_argv_or_environment` | Executes plugin requiring secret; inspects child `sys.argv` and `os.environ`; asserts secret is absent and delivered only via pipe/stdin descriptor. |
| **T-56.11** | `tests/test_phase56_plugin_secret_channels.py` | `test_unsupported_channel_denies_before_spawn` | Requests unsupported channel or simulates unsupported OS pipe; asserts execution denies with `SecretChannelError` before spawning child process. |
| **T-56.12** | `tests/test_phase56_plugin_launch_identity.py` | `test_snapshot_runtime_dependency_and_link_replacement_yields_approved_bytes_or_no_child` | Simulates TOCTOU race swapping binary immediately before spawn; asserts reverification detects hash mismatch and aborts spawn. |
| **T-56.13** | `tests/test_phase56_plugin_launch_identity.py` | `test_failed_verification_creates_no_child` | Injects corrupt file in snapshot; invokes executor; asserts `ClosureTamperedError` raised and child process counter strictly equals 0. |
| **T-56.14** | `tests/test_phase56_plugin_public_routes.py` | `test_plugin_run_cannot_reach_legacy_loader_execute_path` | Uses AST inspection and runtime spy asserting `rush plugin run` invokes `HardenedPluginExecutor.execute()` and never `loader.execute_plugin()`. |
| **T-56.15** | `tests/test_phase56_plugin_public_routes.py` | `test_allow_untrusted_is_not_public` | Inspects CLI arguments and MCP schema; asserts `--allow-untrusted` flag is completely absent from public CLI and MCP interfaces. |
| **T-56.16** | `tests/test_phase56_plugin_public_routes.py` | `test_plugin_output_uses_admin_result_adapter_and_sanitizer` | Executes plugin emitting findings; asserts output conforms to `ToolResultV1` with findings validated by Phase 54 operation adapter. |

---

## 8. File, Dependency, and Documentation Governance

### 8.1 File Write Inventory

#### New Files
1. `src/rush/plugins/closure.py`: Transitive closure discovery, cryptographic manifest building, and closure verification.
2. `src/rush/plugins/snapshot_store.py`: Content-addressed physical snapshot materialization and integrity validation under `PhysicalRoot`.
3. `src/rush/plugins/secret_channels.py`: Protected secret delivery negotiation (descriptor pipe, stdin handshake, OS provider).
4. `tests/test_phase56_plugin_trust.py`: Contract tests T-56.01 through T-56.05.
5. `tests/test_phase56_plugin_closure.py`: Contract tests T-56.06 through T-56.08.
6. `tests/test_phase56_plugin_secret_channels.py`: Contract tests T-56.09 through T-56.11.
7. `tests/test_phase56_plugin_launch_identity.py`: Contract tests T-56.12 and T-56.13.
8. `tests/test_phase56_plugin_public_routes.py`: Contract tests T-56.14 through T-56.16.
9. `governance/remediation-phase-56.toml`: Phase 56 completion manifest.
10. `docs/developer/phase-56-implementation-evidence.md`: Baseline, admission, and test verification logs.

#### Modified Files
1. `src/rush/plugins/__init__.py`: Export updated plugin symbols (`PluginClosureManifest`, `PluginSnapshotStore`, `HardenedPluginExecutor`, `PluginTrustStore`).
2. `src/rush/plugins/trust_store.py`: Refactor to use user-owned ledger outside repository via `rush.io.AtomicFile` and `rush.io.PhysicalRoot`.
3. `src/rush/plugins/trust.py`: Update trust helper functions to use user ledger.
4. `src/rush/plugins/executor.py`: Execute strictly from verified snapshot under `PhysicalRoot`; integrate protected secret channels; emit `ToolResultV1`.
5. `src/rush/plugins/loader.py`: Remove `execute_plugin` bypass; delegate execution exclusively to `HardenedPluginExecutor`.
6. `src/rush/plugins/manifest_schema.py`: Validate plugin manifest parameters, secret references, and pattern filters.
7. `src/rush/plugins/sandboxed_env.py`: Refactor environment sanitization and protected channel setup.
8. `src/rush/plugins/validator.py`: Validate plugin JSON output against `ToolResultV1` schema.
9. `src/rush/cli.py`: Update `rush trust` (grant, revoke, list) and `rush plugin run` to call `HardenedPluginExecutor`.
10. `src/rush/contracts/operations.py`: Verify `cli.plugin_run` adapter compliance.
11. `governance/remediation-contracts.toml`: Mark R-003 completed and reconcile predecessors.
12. `tests/test_plugin_trust.py`: Align existing tests to new user ledger semantics.
13. `tests/test_plugins.py`: Update plugin execution tests to verify hardened executor and `ToolResultV1`.

---

### 8.2 Comprehensive `/docs` Synchronization Inventory (42 Files across 4 Groups)

Every document and subfolder across `/docs` that intersects with plugins, trust, permissions, security, CLI, MCP, or execution has been identified:

#### Group 1: Core Specifications & Public Contracts (14 files)
1. `docs/ARCHITECTURE.md`: Document `src/rush/plugins/` content-addressed trust architecture, closure manifests, immutable snapshots, and protected secret channels.
2. `docs/SECURITY.md`: Update Control 6 (Plugin & Repository Trust Gating) with closure digest, user-owned ledger, non-authorizing repo receipts, and secret invisibility.
3. `docs/SAFETY.md`: Document fail-closed plugin execution, zero-child spawn on verification failure, and protected secret channel guarantees.
4. `docs/PRIVACY.md`: Document secret sanitization and protection in plugin argv/environment/logs.
5. `docs/API_REFERENCE.md`: Document public APIs in `rush.plugins` (`PluginClosureManifest`, `PluginSnapshotStore`, `HardenedPluginExecutor`, `PluginTrustStore`).
6. `docs/CLI_REFERENCE.md`: Document `rush trust` (user ledger, grant, revoke) and `rush plugin run` commands.
7. `docs/MCP.md`: Document plugin execution boundaries and administrative trust operations under MCP.
8. `docs/MCP_REFERENCE.md`: Document MCP plugin tool status and admin trust routes.
9. `docs/CONFIGURATION.md`: Document plugin declaration format in `rush.toml`, patterns, and declared secret references.
10. `docs/CONFIG_SCHEMA.md`: Document schema for `[plugins.<name>]` table including timeout, command, patterns, and secret channels.
11. `docs/GLOSSARY.md`: Add terms for `Plugin Closure`, `Content-Addressed Snapshot`, `User Trust Ledger`, `Protected Secret Channel`.
12. `docs/TOOL_CATALOG.md`: Document plugin executor catalog entry and custom quality engine integration.
13. `docs/JSON_SCHEMA.md`: Document schema for plugin manifest, closure manifest, and plugin output `ToolResultV1`.
14. `docs/SEMANTIC_DRIFT.md`: Document resolution of repository receipt drift, path-only trust drift, and bypass elimination.

#### Group 2: Developer, Safety & Maintainer Guides (16 files)
15. `docs/developer/architecture.md`: Detail Phase 56 architectural design for closure discovery, snapshot materialization, and process binding.
16. `docs/developer/source-tree.md`: Add `src/rush/plugins/closure.py`, `snapshot_store.py`, `secret_channels.py` to source tree.
17. `docs/developer/testing-guide.md`: Add Section for Phase 56 contract test suites (`tests/test_phase56_*.py`).
18. `docs/developer/debugging-guide.md`: Add troubleshooting guide for plugin trust denials, closure mismatches, and secret channel negotiation failures.
19. `docs/developer/tool-development.md`: Update guide for developing custom quality plugins targeting Phase 56 execution model.
20. `docs/developer/backlog.md`: Mark Phase 56 as Complete in milestone table.
21. `docs/developer/issues.md`: Record resolution of ISS-056-01 (Repository Trust Store RCE Vulnerability) and ISS-056-02 (Plugin Closure TOCTOU & Secret Leakage).
22. `docs/developer/phase-56-implementation-evidence.md`: Record admission gate, baseline, and test execution evidence.
23. `docs/safety/security-model.md`: Detail plugin execution threat model, zero-trust boundary, and non-sandboxed disclaimer.
24. `docs/safety/permissions.md`: Detail filesystem and network ambient permissions of plugins and user trust authorization model.
25. `docs/safety/privacy-and-data-handling.md`: Detail secret handling in plugins and exclusion from child process environment.
26. `docs/safety/safety-overview.md`: Summary of plugin safety guarantees and fail-closed denial.
27. `docs/maintainers/release-playbook.md`: Add Phase 56 pre-release verification gates.
28. `docs/maintainers/versioning-and-compatibility.md`: Document compatibility rules for plugin manifests, closures, and trust stores.
29. `docs/maintainers/incident-and-security.md`: Document incident response triage for malicious plugin execution or trust tampering.
30. `docs/maintainers/adr/012-extensible-plugin-architecture.md`: Update ADR-012 with content-addressed closure and user ledger decisions.

#### Group 3: Reference, User Guide & Agentic Integration (7 files)
31. `docs/agentic-rush/plugins-and-agent-skills.md`: Update agent skill generation and plugin execution instructions for autonomous agents.
32. `docs/reference/cli-reference.md`: Update CLI commands reference for `plugin` and `trust`.
33. `docs/reference/configuration-reference.md`: Reference guide for `rush.toml` `[plugins]` configuration.
34. `docs/reference/result-reference.md`: Reference guide for plugin `ToolResultV1` output shapes.
35. `docs/reference/environment-variables.md`: Document environment variable filtering and allowed env names in plugins.
36. `docs/getting-started/glossary.md`: Add beginner glossary definitions for plugins and trust stores.
37. `docs/user-guide/security-and-supply-chain.md`: User guide for securely executing third-party plugins and managing trust.

#### Group 4: Governance, Evidence & Release Tracking (5 files)
38. `governance/remediation-phase-56.toml`: Phase 56 completion manifest with test counts and closed requirements.
39. `governance/remediation-contracts.toml`: Mark R-003 as completed and update predecessors.
40. `docs/user-guide/advanced-checks.md`: User guide for running custom plugins via CLI.
41. `README.md`: Update test badge from 1,063 to 1,079 passed.
42. `CHANGELOG.md`: Log Phase 56 content-addressed plugin trust additions under `[0.3.0]`.

---

### 8.3 Dependency Constraints
- Zero third-party dependencies introduced.
- Strict reliance on Python 3.12 standard library.

---

## 9. Ordered Workstreams and Atomic Task Cards

### P56.0 — Admission Gate & Baseline Evidence

#### P56.0.1 — EVIDENCE: Record Baseline and Map Authority Call Paths
- **Task ID:** P56.0.1
- **Binary Outcome:** Clean baseline evidence recorded in `docs/developer/phase-56-implementation-evidence.md`; full test suite passes (1,063 passed); platform capabilities recorded.
- **Prerequisites:** Admission gate §4 passed.
- **Allowed Writes:** `docs/developer/phase-56-implementation-evidence.md`.
- **Actions:**
  1. Run `.venv/Scripts/python.exe -m pytest tests/ -q` and record 1,063 passing tests.
  2. Inspect current call paths from `rush plugin run`, `rush trust`, and `loader.execute_plugin`.
  3. Record platform capabilities for anonymous pipes, descriptors, and Windows junction detection.

---

### P56.1 — User-Owned Trust Ledger & Reapproval Lifecycle

#### P56.1.1 — RED: Define User-Owned Ledger & Reapproval Contract Tests
- **Task ID:** P56.1.1
- **Binary Outcome:** Create `tests/test_phase56_plugin_trust.py` containing contract tests T-56.01 to T-56.05; tests fail (RED) against current codebase.
- **Prerequisites:** P56.0.1.
- **Allowed Writes:** `tests/test_phase56_plugin_trust.py`.
- **Actions:**
  1. Author T-56.01 (`test_plugin_execution_fails_closed_without_content_digest`).
  2. Author T-56.02 (`test_repository_receipt_never_authorizes`).
  3. Author T-56.03 (`test_cloned_repository_receipt_is_denied`).
  4. Author T-56.04 (`test_legacy_grant_requires_explicit_reapproval`).
  5. Author T-56.05 (`test_revoke_invalidates_launch`).
  6. Run `pytest tests/test_phase56_plugin_trust.py -q` and confirm failures.

#### P56.1.2 — GREEN: Implement User-Owned Trust Ledger using AtomicFile & PhysicalRoot
- **Task ID:** P56.1.2
- **Binary Outcome:** Implement user-owned trust ledger in `src/rush/plugins/trust_store.py` and `trust.py`; all 5 tests in `tests/test_phase56_plugin_trust.py` pass (GREEN).
- **Prerequisites:** P56.1.1 RED.
- **Allowed Writes:** `src/rush/plugins/trust_store.py`, `src/rush/plugins/trust.py`, `src/rush/plugins/__init__.py`.
- **Actions:**
  1. Refactor `PluginTrustStore` to manage `~/.rush/plugin_trust_ledger.json` (or user config path) via `rush.io.PhysicalRoot` and `rush.io.AtomicFile`.
  2. Implement `TrustedPluginRecord` storing `closure_digest`, `snapshot_path`, `granted_at`, and `VerifierRecord`.
  3. Treat in-repo `.rush/trust.json` strictly as non-authorizing evidence; deny authorization if only repository receipt exists.
  4. Require explicit reapproval for any legacy path grant or closure change.
  5. Run `pytest tests/test_phase56_plugin_trust.py -v` and confirm GREEN.

---

### P56.2 — Content-Addressed Closure Discovery & Materialized Snapshots

#### P56.2.1 — RED: Define Transitive Closure & Byte Snapshot Contract Tests
- **Task ID:** P56.2.1
- **Binary Outcome:** Create `tests/test_phase56_plugin_closure.py` containing contract tests T-56.06 to T-56.08; tests fail (RED).
- **Prerequisites:** P56.1.2.
- **Allowed Writes:** `tests/test_phase56_plugin_closure.py`.
- **Actions:**
  1. Author T-56.06 (`test_closure_digest_covers_every_code_and_behavior_input`).
  2. Author T-56.07 (`test_snapshot_contains_copied_bytes_not_links`).
  3. Author T-56.08 (`test_post_approval_mutation_uses_snapshot_or_denies`).
  4. Run `pytest tests/test_phase56_plugin_closure.py -q` and confirm failures.

#### P56.2.2 — GREEN: Implement Plugin Closure Discovery & Snapshot Store
- **Task ID:** P56.2.2
- **Binary Outcome:** Implement `src/rush/plugins/closure.py` and `src/rush/plugins/snapshot_store.py`; tests in `tests/test_phase56_plugin_closure.py` pass (GREEN).
- **Prerequisites:** P56.2.1 RED.
- **Allowed Writes:** `src/rush/plugins/closure.py`, `src/rush/plugins/snapshot_store.py`, `src/rush/plugins/manifest_schema.py`, `src/rush/plugins/__init__.py`.
- **Actions:**
  1. In `src/rush/plugins/closure.py`, implement `PluginClosureManifest` and `build_plugin_closure()`. Walk all files under plugin root via `PhysicalRoot`, compute SHA-256 for each file, digest config table, allowed env names, declared secrets, runtime identity, and platform identity.
  2. In `src/rush/plugins/snapshot_store.py`, implement `PluginSnapshotStore.materialize_snapshot()`: copy physical bytes into `~/.rush/snapshots/<closure_digest>/` under `PhysicalRoot`. Strictly reject symlinks, hardlinks, and directory junctions.
  3. Implement `PluginSnapshotStore.verify_snapshot()` ensuring byte-for-byte fidelity.
  4. Run `pytest tests/test_phase56_plugin_closure.py -v` and confirm GREEN.

---

### P56.3 — Protected Secret Channels & Ephemeral Resolution

#### P56.3.1 — RED: Define Protected Secret Channel Contract Tests
- **Task ID:** P56.3.1
- **Binary Outcome:** Create `tests/test_phase56_plugin_secret_channels.py` containing contract tests T-56.09 to T-56.11; tests fail (RED).
- **Prerequisites:** P56.0.1.
- **Allowed Writes:** `tests/test_phase56_plugin_secret_channels.py`.
- **Actions:**
  1. Author T-56.09 (`test_literal_secret_is_rejected_from_argv_config_resource_and_environment`).
  2. Author T-56.10 (`test_declared_protected_channel_is_not_visible_in_child_argv_or_environment`).
  3. Author T-56.11 (`test_unsupported_channel_denies_before_spawn`).
  4. Run `pytest tests/test_phase56_plugin_secret_channels.py -q` and confirm failures.

#### P56.3.2 — GREEN: Implement Protected Secret Delivery & Channel Negotiation
- **Task ID:** P56.3.2
- **Binary Outcome:** Implement `src/rush/plugins/secret_channels.py`; update `sandboxed_env.py`; tests in `tests/test_phase56_plugin_secret_channels.py` pass (GREEN).
- **Prerequisites:** P56.3.1 RED.
- **Allowed Writes:** `src/rush/plugins/secret_channels.py`, `src/rush/plugins/sandboxed_env.py`, `src/rush/plugins/__init__.py`.
- **Actions:**
  1. Implement `SecretDeliveryContext`, `PipeSecretChannel`, and `StdinSecretChannel`.
  2. Ensure secret values are never formatted into CLI arguments or standard environment dictionaries.
  3. Implement channel negotiation: on POSIX/Windows, set up anonymous pipe descriptor or stdin handshake protocol.
  4. If channel or platform is unsupported, fail closed with `SecretChannelError` before spawning any child process.
  5. Run `pytest tests/test_phase56_plugin_secret_channels.py -v` and confirm GREEN.

---

### P56.4 — Non-Substitutable Launch Identity & Race Elimination

#### P56.4.1 — RED: Define Pre-Spawn Reverification & Race Contract Tests
- **Task ID:** P56.4.1
- **Binary Outcome:** Create `tests/test_phase56_plugin_launch_identity.py` containing contract tests T-56.12 and T-56.13; tests fail (RED).
- **Prerequisites:** P56.1.2, P56.2.2, P56.3.2.
- **Allowed Writes:** `tests/test_phase56_plugin_launch_identity.py`.
- **Actions:**
  1. Author T-56.12 (`test_snapshot_runtime_dependency_and_link_replacement_yields_approved_bytes_or_no_child`).
  2. Author T-56.13 (`test_failed_verification_creates_no_child`).
  3. Run `pytest tests/test_phase56_plugin_launch_identity.py -q` and confirm failures.

#### P56.4.2 — GREEN: Implement Pre-Spawn Verification & Snapshot Execution in HardenedPluginExecutor
- **Task ID:** P56.4.2
- **Binary Outcome:** Update `src/rush/plugins/executor.py`; all tests in `tests/test_phase56_plugin_launch_identity.py` pass (GREEN).
- **Prerequisites:** P56.4.1 RED.
- **Allowed Writes:** `src/rush/plugins/executor.py`, `src/rush/plugins/__init__.py`.
- **Actions:**
  1. In `HardenedPluginExecutor.execute()`, verify user trust ledger record against closure manifest.
  2. Open snapshot directory under `PhysicalRoot`; verify all files in snapshot match expected digests immediately before spawn.
  3. Spawn child process using working directory set to snapshot directory (or repository directory for target files while scripts execute from snapshot).
  4. On any mismatch, raise `ClosureTamperedError` or `UntrustedPluginError` and ensure zero child process is spawned.
  5. Run `pytest tests/test_phase56_plugin_launch_identity.py -v` and confirm GREEN.

---

### P56.5 — Public Route Unification & ToolResultV1 Output Adaptation

#### P56.5.1 — RED: Define Public Route & Output Adaptation Contract Tests
- **Task ID:** P56.5.1
- **Binary Outcome:** Create `tests/test_phase56_plugin_public_routes.py` containing contract tests T-56.14 to T-56.16; tests fail (RED).
- **Prerequisites:** P56.4.2.
- **Allowed Writes:** `tests/test_phase56_plugin_public_routes.py`.
- **Actions:**
  1. Author T-56.14 (`test_plugin_run_cannot_reach_legacy_loader_execute_path`).
  2. Author T-56.15 (`test_allow_untrusted_is_not_public`).
  3. Author T-56.16 (`test_plugin_output_uses_admin_result_adapter_and_sanitizer`).
  4. Run `pytest tests/test_phase56_plugin_public_routes.py -q` and confirm failures.

#### P56.5.2 — GREEN: Unify CLI/MCP Routes & Conform to ToolResultV1
- **Task ID:** P56.5.2
- **Binary Outcome:** Update `src/rush/cli.py`, `loader.py`, `validator.py`, and `executor.py`; tests in `tests/test_phase56_plugin_public_routes.py`, `test_plugins.py`, and `test_plugin_trust.py` pass (GREEN).
- **Prerequisites:** P56.5.1 RED.
- **Allowed Writes:** `src/rush/cli.py`, `src/rush/plugins/loader.py`, `src/rush/plugins/validator.py`, `src/rush/plugins/executor.py`, `src/rush/contracts/operations.py`, `tests/test_plugins.py`, `tests/test_plugin_trust.py`.
- **Actions:**
  1. In `src/rush/cli.py:plugin_run`, replace `loader.execute_plugin` with `HardenedPluginExecutor.execute()`.
  2. In `src/rush/plugins/loader.py`, deprecate or remove `execute_plugin()`.
  3. In `src/rush/plugins/validator.py` and `executor.py`, adapt stdout to `ToolResultV1` using `validate_tool_result()`.
  4. Update `tests/test_plugins.py` and `tests/test_plugin_trust.py` to align with new hardened semantics.
  5. Run `pytest tests/test_phase56_plugin_public_routes.py tests/test_plugins.py tests/test_plugin_trust.py -v` and confirm GREEN.

---

### P56.6 — Comprehensive Documentation & Governance Sync

#### P56.6.1 — VERIFY/DOCS: Synchronize All 42 Documentation and Governance Files
- **Task ID:** P56.6.1
- **Binary Outcome:** All 42 documentation and governance files listed in §8.2 are updated and synchronized with zero drift.
- **Prerequisites:** P56.1.2 through P56.5.2 GREEN.
- **Allowed Writes:** All 42 files listed in §8.2.
- **Actions:**
  1. Create `governance/remediation-phase-56.toml` documenting phase completion, 16 contract tests, and closure of R-003.
  2. Update `governance/remediation-contracts.toml` marking R-003 complete.
  3. Update `docs/developer/phase-56-implementation-evidence.md` with final gate runs.
  4. Update `README.md` test badge to 1,079 passed; update `CHANGELOG.md` under `[0.3.0]`.
  5. Update all 38 technical docs across `/docs` with content-addressed plugin trust, user ledger, and snapshot mechanics.
  6. Verify zero whitespace defects with `git diff --check`.

---

## 10. Final Verification and Delivery Gate

Execute the following commands in sequence to verify Phase 56 delivery:

```powershell
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 1. Run all 16 focused Phase 56 contract tests
.venv/Scripts/python.exe -m pytest tests/test_phase56_plugin_trust.py tests/test_phase56_plugin_closure.py tests/test_phase56_plugin_secret_channels.py tests/test_phase56_plugin_launch_identity.py tests/test_phase56_plugin_public_routes.py -v

# 2. Run plugin regression suites
.venv/Scripts/python.exe -m pytest tests/test_plugins.py tests/test_plugin_trust.py tests/test_phase54_*.py tests/test_phase55_*.py -q

# 3. Run complete test suite (expecting 1,079 passed tests: 1,063 baseline + 16 contract tests)
.venv/Scripts/python.exe -m pytest tests/ -q

# 4. Run Ruff lint check across entire codebase
.venv/Scripts/ruff.exe check src tests scripts

# 5. Run Ruff format check across entire codebase
.venv/Scripts/ruff.exe format --check src tests scripts

# 6. Verify Git diff whitespace and status hygiene
git diff --check
git diff --name-only
git status --short --branch
```

---

## 11. Exit Checklist and Successor Evidence

- [ ] Ordinary RED evidence precedes every GREEN task; zero skip, xfail, or permissive assertions.
- [ ] Sole authorizing store is user-owned ledger outside the repository (`~/.rush/plugin_trust_ledger.json`) managed via `rush.io.AtomicFile` and `rush.io.PhysicalRoot`.
- [ ] Repository receipts (`.rush/trust.json`) are strictly non-authorizing evidence; cloned foreign receipts deny fail-closed.
- [ ] `PluginClosureManifest` digests complete transitive closure (entrypoint, code files, configs, allowed env names, declared secrets, runtime, platform).
- [ ] Snapshots materialized in `~/.rush/snapshots/<closure_digest>/` under `PhysicalRoot` contain only pure byte copies; symlinks, directory junctions, and hardlinks are rejected.
- [ ] Literal secrets are strictly prohibited from manifests, configs, CLI flags, environments, ledgers, snapshots, logs, and results.
- [ ] Protected channels (descriptor pipe, stdin handshake, OS provider) deliver secrets invisibly to process listings (`ps`, `/proc`).
- [ ] Unsupported channels or platforms deny execution fail-closed before any child process is spawned.
- [ ] Immediate pre-spawn reverification guarantees approved bytes or zero child process created.
- [ ] Legacy bypasses (`execute_plugin`, `allow_untrusted`) are eliminated from public surfaces.
- [ ] `rush plugin run` routes exclusively through `HardenedPluginExecutor` and returns canonical `ToolResultV1` output.
- [ ] Zero third-party dependencies introduced; 100% pure Python 3.12 standard library.
- [ ] All 16 contract tests in `tests/test_phase56_*.py` pass.
- [ ] Full pytest suite passes with 1,079 tests (1,063 baseline + 16 Phase 56 contract tests).
- [ ] All 42 documentation and governance files updated and synchronized across `/docs` and repo root.
- [ ] `governance/remediation-phase-56.toml` created with complete test and requirement records.
- [ ] Requirement R-003 reconciled in `governance/remediation-contracts.toml` as completed.
- [ ] Successor phases (Phase 57 operations scope, Phase 58 mesh lock persistence) unblocked with stable plugin interfaces.
