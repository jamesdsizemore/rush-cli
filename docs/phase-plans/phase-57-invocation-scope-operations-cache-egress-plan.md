# Phase 57 Implementation Plan: Invocation Context, Physical Scope, Public Operations, Cache Policy, and Provider Egress

## 1. Purpose and Status

- **Operation:** Comprehensive implementation plan for Phase 57 remediation.
- **Planning Status:** Implementation-ready; fully verified against repo codebase and active development.
- **Implementation Status:** Authorized for strict TDD execution.
- **Authority:** Governing Roadmap findings R-004, R-005, R-006, and R-007 (`governance/remediation-contracts.toml`).
- **Predecessors:** Accepted Phase 51 operation manifest, Phase 52 artifact identity, Phase 53 sanitizer (`rush.safety.redactor`), Phase 54 result schema kernel (`rush.contracts.results.ToolResultV1`), Phase 55 physical containment primitives (`rush.io.PhysicalRoot`, `rush.io.AtomicFile`), and Phase 56 user-owned plugin trust.
- **Successor:** Phase 58 (Lock Persistence, Patch Remediation, and Failure State Recovery).
- **Security Boundary:** All operations (CLI and MCP) must construct immutable, equivalent invocation contexts; target scopes must be strictly contained under `rush.io.PhysicalRoot`; operations must execute exactly once without runtime `TypeError` retry; cache keys must cryptographically bind all behavior identities; provider outcomes must be truthful (LLM label requires schema-valid non-empty completion from an approved HTTPS origin).
- **Protected Boundaries:** Roadmap requirements, dependency lockfile, plugin execution primitives, and release versioning.
- **Zero-Downscope Invariant:** This plan is the immutable contract. Stubs returning "unknown", permissive test assertions (`assert status in (...)`), or skipping cache identity fields are strictly prohibited. Every covered failure mode must fail closed.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, release, hooks, history rewrite, live provider network calls, or live credentials without explicit user instructions.

---

## 2. Authority, Predecessor Artifacts, and Concrete Evidence

Authority order: User instructions → `AGENTS.md` → Roadmap (`governance/remediation-contracts.toml`) → Phases 51-56 contracts → Current CLI/MCP/cache/provider source and test suites.

### 2.1 Concrete Codebase Audit & Semantic Drift Identification

An exhaustive audit of the existing codebase against findings R-004, R-005, R-006, and R-007 identified seven critical vulnerabilities and architectural drifts:

1. **Drift 1: CLI vs. MCP Transport Divergence (Context Asymmetry & Mutation)**:
   - *Existing Code:* `src/rush/cli.py` and `src/rush/mcp.py` construct disparate parameter dictionaries, load mutable configuration objects in-flight, and query `PermissionManager` dynamically during execution. MCP tool handlers receive or mutate state inconsistently compared to CLI equivalents.
   - *Vulnerability:* Inconsistent permission gating, diverging option defaults, and potential configuration poisoning between CLI and MCP invocations.
   - *Remediation (R-004, R-007):* Introduce an authoritative, immutable `InvocationContext` in `src/rush/invocation/models.py`. Both CLI and MCP resolve to this unified context before dispatching any operation via `resolve_invocation(request, transport)`. MCP requests copy declared request values and never receive mutable config objects.

2. **Drift 2: Target Path Widening & Traversal Traps**:
   - *Existing Code:* Target file arguments passed via CLI flags or MCP inputs are parsed with basic `Path.resolve()` without verifying physical containment against the workspace root. Symlinks, Windows directory junctions (`0x400`), or `..` parent traversals can escape the intended workspace.
   - *Vulnerability:* Arbitrary filesystem read/write widening beyond project boundaries.
   - *Remediation (R-005):* Introduce `src/rush/invocation/targets.py` utilizing `rush.io.PhysicalRoot`. Target selections are classified into immutable states (`present`, `deleted`, `renamed`) with explicit provenance and capabilities. Symlinks, junctions, and directory swaps fail closed with `ContainmentError`, preventing scope widening.

3. **Drift 3: Runtime `TypeError` Exception Retries (Double Execution & Side-Effect Poisoning)**:
   - *Existing Code:* In certain tool wrappers and command dispatchers, callers attempt multi-signature dispatch by catching `TypeError` at invocation time and retrying with fewer arguments.
   - *Vulnerability:* If an underlying tool or engine raises an internal `TypeError` *after* executing a side effect (e.g. disk write, state update, or network call), the wrapper catches it, assumes an incompatible signature, and invokes the tool a second time.
   - *Remediation (R-004, R-006):* Introduce `src/rush/invocation/executor.py`. Signature inspection and adapter binding must occur strictly *once* at registration time. At runtime, operations execute exactly once. Internal `TypeError` exceptions are caught and propagated as genuine errors without retry.

4. **Drift 4: Public Operations Routing & Deprecation Discrepancies**:
   - *Existing Code:* Some public routes in `src/rush/cli.py` and `src/rush/mcp.py` diverge from the canonical implementations declared in `governance/public-operations.toml`. Unprobed or legacy route names remain advertised.
   - *Vulnerability:* Transport contract drift where CLI and MCP call different underlying functions or return differing schema structures.
   - *Remediation (R-004, R-007):* Reconcile all 146 operations in `governance/public-operations.toml`. Ensure every retained route delegates directly to its canonical implementation and adapter (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`). Only paired tool operations require dual-transport parity; admin and service operations retain their declared contracts (`ClickExitCode`, `ServiceProtocol`).

5. **Drift 5: Ad-Hoc Admin Cache vs. Generic Cryptographic Invocation Cache**:
   - *Existing Code:* `src/rush/cache.py` implements a simple SQLite cache keyed only by `file_path + tool_name + engine_version + config_hash + cli_flags`. It has no knowledge of operation purity, target states, ignored host inputs, artifact build identity, or permissions. Missing fields fall back to `"default"`.
   - *Vulnerability:* Cache collisions between distinct configurations; caching non-pure or side-effecting operations; inability to bypass cache cleanly via `--no-cache`.
   - *Remediation (R-005, R-006):* Introduce `src/rush/invocation/cache_policy.py`. Define `CacheDecision` (`eligible` or `bypass` with reason). Cache keys must bind the complete immutable context (operation ID, ordered arguments, config digest, permissions, environment, artifact build identity, tool/normalizer revisions, physical target content/states). If any identity is missing, cache returns `bypass` with no key (zero fallback salts). `--no-cache` performs zero cache reads and zero cache writes. Cache `get` and `set` sanitize and validate `ToolResultV1`.

6. **Drift 6: Misleading LLM Provider Labeling & Egress Failures**:
   - *Existing Code:* In `src/rush/tools/review.py` and `src/rush/providers/`, `_maybe_call_llm` returns `review_kind="llm"` whenever an LLM response object is non-None, even if an HTTP error occurred, an unexpected redirect was followed, or the content string was empty.
   - *Vulnerability:* Semantic drift where heuristic or failed reviews are mislabeled as AI-generated, masking network or authentication failures.
   - *Remediation (R-006, R-007):* Explicit provider outcome states (`completed`, `skipped`, `error`). The `review_kind="llm"` label is permitted *only* after a schema-valid, non-empty completion is received from an approved effective HTTPS origin without unauthorized redirects. Cross-origin redirects refuse to forward credentials or prompts fail-closed.

7. **Drift 7: Dual-Transport Capability Parity**:
   - *Existing Code:* CLI commands often support options that MCP tools do not expose, and vice-versa.
   - *Vulnerability:* Automation agents calling Rush via MCP experience capability deficits compared to human developers using the CLI.
   - *Remediation (R-007):* Enforce dual-transport parity for all 10 canonical core quality tools across CLI and MCP. Both transports must accept identical normalized inputs, enforce identical validation, and emit identical `ToolResultV1` output shapes.

---

## 3. Goals, Non-Goals, Operational Exclusions, and Security Boundaries

### 3.1 Primary Goals
1. Implement `InvocationContext` and `resolve_invocation()` guaranteeing identical execution context across CLI and MCP.
2. Implement `PhysicalTarget` allowlists contained under `rush.io.PhysicalRoot` with immutable states (`present|deleted|renamed`).
3. Guarantee single execution per request; eliminate runtime `TypeError` exception retries.
4. Reconcile 100% of public operations in `governance/public-operations.toml` with canonical implementations.
5. Implement complete cryptographic cache key derivation (`decide_cache`) binding all behavior identities; ensure `--no-cache` does zero I/O; enforce `ToolResultV1` sanitation and validation on cache get/set.
6. Enforce truthful LLM provider outcome labeling; reject cross-origin redirects; ensure `llm` label requires approved HTTPS origin completion.
7. Enforce dual-transport parity across CLI and MCP for all core tools.

### 3.2 Non-Goals and Operational Exclusions
1. **No Live Network or External Calls:** All provider tests must use local mock transports and spies; no live API keys or network traffic.
2. **No Dependency Additions:** 100% pure Python 3.12 standard library.
3. **No Migration of Phase 58 Internals:** Lock persistence, state transactions, and auto-patching internals belong to Phase 58.

---

## 4. Admission Gate and Predecessor Verification

The following criteria must be verified prior to initiating Phase 57 development:
1. `governance/remediation-phase-56.toml` is present with status `completed` (all 16 Phase 56 contract tests passed).
2. Clean test baseline of 1,079 passed tests.
3. Phase 51 public operations manifest (`governance/public-operations.toml`) is present with 146 operations mapped.
4. Phase 52 package identity and version authority validated.
5. Phase 53 sanitization diagnostics (`rush.safety.redactor.sanitize_value`) operational.
6. Phase 54 operation adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) and `ToolResultV1` operational.
7. Phase 55 physical containment primitives (`rush.io.PhysicalRoot`, `rush.io.AtomicFile`) operational.
8. Execution of P57.0.1 records platform baseline and maps all request-to-execution call paths.

---

## 5. Requirement-Ownership Ledger (R-004 through R-007)

| Requirement ID | Finding Summary | Workstreams | Specific Contract Outcomes |
|---|---|---|---|
| **R-004** | Public operation surface is undocumented and transport contracts diverge | P57.1, P57.4 | `InvocationContext` unifies CLI/MCP; all 146 operations mapped to canonical implementations; unprobed routes eliminated. |
| **R-005** | Scope and execution-cache contracts are absent from generic invocation | P57.2, P57.5 | Physical target containment (`PhysicalRoot`); cryptographic cache key binding all identities; `--no-cache` zero I/O. |
| **R-006** | Output egress and error states diverge from documented semantics | P57.3, P57.5, P57.6 | Single execution boundary (zero `TypeError` retry); cache get/set `ToolResultV1` sanitization; truthful provider outcomes. |
| **R-007** | Transport parity and capability coverage are unenforced | P57.1, P57.4, P57.6 | Dual-transport parity for all core tools; approved HTTPS effective origin verification for LLM labeling. |

---

## 6. Shared Architecture, State Invariants, and Data Structures

### 6.1 Data Structures & Contracts (`src/rush/invocation/models.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

TransportType = Literal["cli", "mcp"]
OperationKind = Literal["tool", "admin", "service"]
TargetState = Literal["present", "deleted", "renamed"]
CachePolicy = Literal["eligible", "bypass"]
ProviderOutcome = Literal["completed", "skipped", "error"]

@dataclass(frozen=True)
class PhysicalTarget:
    """Represents an immutable contained target within a physical workspace."""
    relative_path: Path
    state: TargetState
    capability: str = "read"
    provenance: str = "explicit"  # "explicit", "glob", "git-staged", "git-changed"
    content_hash: str = ""  # SHA-256 hex or empty if deleted

@dataclass(frozen=True)
class InvocationContext:
    """Unified, immutable context resolved prior to any operation execution."""
    workspace_root: Path
    transport: TransportType
    operation_id: str
    operation_kind: OperationKind
    targets: tuple[PhysicalTarget, ...]
    effective_config_digest: str
    permissions: tuple[str, ...]  # Immutable snapshot of allowed capabilities
    ordered_args: tuple[str, ...]
    declared_ignored_inputs: tuple[str, ...]
    cache_policy: CachePolicy
    artifact_build_identity: str
    tool_revision: str
    normalizer_revision: str
    environment_digest: str
    request_id: str = ""

@dataclass(frozen=True)
class CacheDecision:
    """Deterministic decision regarding cache eligibility and derived key."""
    decision: CachePolicy
    reason: str
    cache_key: str | None = None
    key_payload: dict[str, Any] = field(default_factory=dict)
```

### 6.2 Exception Hierarchy

- `InvocationError(Exception)`: Base class for invocation errors.
  - `TransportDivergenceError(InvocationError)`: Raised when transport contracts or arguments diverge.
  - `ScopeWideningError(InvocationError)`: Raised when a target path attempts to escape containment or widen scope.
  - `UndeclaredInputError(InvocationError)`: Raised when an undeclared host input is encountered.
  - `SignatureAdaptationError(InvocationError)`: Raised when a callable signature cannot be adapted at registration time.
  - `ProviderEgressError(InvocationError)`: Raised on cross-origin redirects or invalid provider egress.

### 6.3 State Invariants
1. **Transport Equivalence Invariant:** Given identical logical inputs, CLI and MCP must produce equal `InvocationContext` objects with identical effective config digests and permission sets.
2. **Scope Containment Invariant:** Target paths must never resolve outside `workspace_root`. Symlinks, junctions, and directory swaps fail closed with `ScopeWideningError`.
3. **Single Execution Invariant:** Operations execute exactly once. No runtime `TypeError` retries are permitted.
4. **Cache Purity Invariant:** Only operations declared pure (`pure = true` in manifest) are eligible for cache. Any missing identity yields `bypass` and zero key. `--no-cache` performs zero cache reads and zero cache writes.
5. **Provider Origin Invariant:** The `review_kind = "llm"` label is assigned if and only if a non-empty, schema-valid response was received from an approved effective HTTPS origin without unauthorized redirects.

---

## 7. Contract Test Inventory (T-57.01 to T-57.25)

| Test ID | Test File | Test Function | Target Contract & Non-Permissive Assertion |
|---|---|---|---|
| **T-57.01** | `tests/test_phase57_invocation_context.py` | `test_cli_and_mcp_resolve_equivalent_context` | Asserts CLI and MCP requests with identical inputs produce equal `InvocationContext` objects. |
| **T-57.02** | `tests/test_phase57_invocation_context.py` | `test_mcp_request_never_receives_mutable_config` | Asserts MCP requests receive a frozen copy of declared values; mutating config has 0 effect on context. |
| **T-57.03** | `tests/test_phase57_invocation_context.py` | `test_dual_transport_parity_across_transports` | **R-007 Governance Test:** Asserts dual-transport parity across CLI and MCP for all core quality tools. |
| **T-57.04** | `tests/test_phase57_physical_scope.py` | `test_target_states_and_selection_provenance_are_immutable` | Asserts targets maintain immutable states (`present`, `deleted`, `renamed`) and provenance cannot be mutated. |
| **T-57.05** | `tests/test_phase57_physical_scope.py` | `test_link_junction_and_swap_cannot_widen_scope` | Injects directory junction and symlink traps; asserts resolver fails closed with `ScopeWideningError`. |
| **T-57.06** | `tests/test_phase57_physical_scope.py` | `test_undeclared_host_input_refuses` | Injects undeclared external host input; asserts resolver raises `UndeclaredInputError` fail-closed. |
| **T-57.07** | `tests/test_phase57_public_operations.py` | `test_internal_typeerror_after_side_effect_executes_once` | Injects callable raising internal `TypeError` after writing sentinel; asserts side-effect count is strictly 1 (no retry). |
| **T-57.08** | `tests/test_phase57_public_operations.py` | `test_unsupported_signature_fails_registration` | Registers callable with unresolvable/unsupported signature; asserts registration fails immediately with `SignatureAdaptationError`. |
| **T-57.09** | `tests/test_phase57_public_operations.py` | `test_cli_mcp_signature_error_is_equivalent` | Compares signature mismatch errors across CLI and MCP; asserts both transports return identical error structure. |
| **T-57.10** | `tests/test_phase57_public_operations.py` | `test_transport_contracts_reconcile_with_operation_manifest` | **R-004 Governance Test:** Reconciles all 146 operations in `public-operations.toml` against registered adapters. |
| **T-57.11** | `tests/test_phase57_public_operations.py` | `test_every_retained_operation_reaches_manifest_implementation` | Dispatches probes to every retained operation ID; asserts invocation reaches declared canonical implementation. |
| **T-57.12** | `tests/test_phase57_public_operations.py` | `test_only_tool_pairs_require_semantic_parity` | Asserts tool operations require strict parity; admin/service operations maintain distinct declared contract shapes. |
| **T-57.13** | `tests/test_phase57_public_operations.py` | `test_unprobed_route_is_not_advertised` | Verifies no unprobed, deprecated, or orphaned routes appear in CLI `--help` or MCP tool listings. |
| **T-57.14** | `tests/test_phase57_public_operations.py` | `test_output_egress_and_error_codes` | **R-006 Governance Test:** Verifies exit codes and output formatting conform to Phase 54 operation adapters. |
| **T-57.15** | `tests/test_phase57_cache_policy.py` | `test_cache_identity_and_bypass_contracts` | **R-005 Governance Test:** Asserts complete cryptographic key derivation and proper bypass handling. |
| **T-57.16** | `tests/test_phase57_cache_policy.py` | `test_cache_key_binds_every_context_and_target_identity` | Mutates each context/target field individually; asserts derived cache key changes on every mutation. |
| **T-57.17** | `tests/test_phase57_cache_policy.py` | `test_missing_identity_returns_bypass_without_key` | Omits a required identity field; asserts `decide_cache()` returns `decision="bypass"` and `cache_key=None` (zero fallback salt). |
| **T-57.18** | `tests/test_phase57_cache_policy.py` | `test_artifact_behavior_config_permission_target_mutation_misses` | Simulates cache lookup after mutating build ID or permissions; asserts cache miss. |
| **T-57.19** | `tests/test_phase57_cache_policy.py` | `test_no_cache_performs_no_read_or_write` | Invokes executor with `cache_policy="bypass"`; asserts spy verifies 0 calls to cache read and 0 calls to cache write. |
| **T-57.20** | `tests/test_phase57_cache_policy.py` | `test_cache_set_requires_sanitized_valid_tool_result` | Attempts to cache invalid or unsanitized result; asserts cache set fails closed or cleanses payload. |
| **T-57.21** | `tests/test_phase57_cache_policy.py` | `test_cache_get_resanitizes_and_revalidates` | Injects tampered/secret data in cache DB; asserts cache get re-sanitizes and re-validates `ToolResultV1` before return. |
| **T-57.22** | `tests/test_phase57_cache_policy.py` | `test_only_manifest_pure_operation_uses_cache` | Executes non-pure operation; asserts executor bypasses cache completely. |
| **T-57.23** | `tests/test_phase57_provider_egress.py` | `test_denied_redirected_failed_or_empty_work_is_not_llm` | Injects empty response, HTTP error, or permission denial; asserts `review_kind` is NOT `"llm"`. |
| **T-57.24** | `tests/test_phase57_provider_egress.py` | `test_cross_origin_redirect_receives_no_authorization_or_prompt` | Simulates 302 redirect to unauthorized origin; asserts transport refuses redirect and sends 0 auth headers. |
| **T-57.25** | `tests/test_phase57_provider_egress.py` | `test_approved_effective_origin_completion_is_llm` | Simulates valid non-empty response from approved HTTPS origin; asserts `review_kind == "llm"`. |

---

## 8. File, Dependency, and Documentation Governance

### 8.1 File Write Inventory

#### New Files
1. `src/rush/invocation/__init__.py`: Public exports for invocation subsystem.
2. `src/rush/invocation/models.py`: `InvocationContext`, `PhysicalTarget`, `CacheDecision`.
3. `src/rush/invocation/resolver.py`: `resolve_invocation(request, transport)`.
4. `src/rush/invocation/targets.py`: `PhysicalTarget` allowlist builder and containment validator.
5. `src/rush/invocation/executor.py`: Single execution boundary, registration-time signature adaptation, cache gating.
6. `src/rush/invocation/cache_policy.py`: Deterministic cryptographic cache key policy (`decide_cache`).
7. `tests/test_phase57_invocation_context.py`: Contract tests T-57.01, T-57.02, T-57.03.
8. `tests/test_phase57_physical_scope.py`: Contract tests T-57.04, T-57.05, T-57.06.
9. `tests/test_phase57_public_operations.py`: Contract tests T-57.07 through T-57.14.
10. `tests/test_phase57_cache_policy.py`: Contract tests T-57.15 through T-57.22.
11. `tests/test_phase57_provider_egress.py`: Contract tests T-57.23, T-57.24, T-57.25.
12. `governance/remediation-phase-57.toml`: Phase 57 completion manifest.
13. `docs/developer/phase-57-implementation-evidence.md`: Evidence and execution logs.

#### Modified Files
1. `src/rush/cli.py`: Route commands through `resolve_invocation` and `InvocationExecutor`.
2. `src/rush/mcp.py`: Route MCP tool registrations through `resolve_invocation` and `InvocationExecutor`.
3. `src/rush/catalog.py`: Adapt signatures once at registration; eliminate runtime retry.
4. `src/rush/cache.py`: Integrate with `decide_cache`; enforce `ToolResultV1` sanitation on get/set.
5. `src/rush/config.py`: Provide immutable configuration snapshots for context resolution.
6. `src/rush/permissions.py`: Provide immutable permission sets for context resolution.
7. `src/rush/tools/__init__.py`: Register operation callables with fixed signatures.
8. `src/rush/tools/base.py`: Cross-reference `InvocationContext`.
9. `src/rush/tools/common.py`: Align execution helpers with single execution boundary.
10. `src/rush/tools/review.py`: Gate `review_kind="llm"` strictly on approved effective origin completion.
11. `src/rush/providers/__init__.py`: Export updated provider outcome models.
12. `src/rush/providers/base.py`: Define `ProviderOutcome`, effective origin checks, redirect refusal.
13. `src/rush/providers/openai.py`: Enforce approved HTTPS origin and redirect protection.
14. `src/rush/providers/anthropic.py`: Enforce approved HTTPS origin and redirect protection.
15. `src/rush/providers/registry.py`: Validate provider configurations.
16. `src/rush/contracts/operations.py`: Reconcile public operation manifest with invocation executor.
17. `governance/public-operations.toml`: Annotate pure operations for cache eligibility; verify transport parity.
18. `governance/remediation-contracts.toml`: Mark R-004, R-005, R-006, R-007 completed.
19. `tests/test_cli.py`: Update CLI tests to reflect unified context execution.
20. `tests/test_mcp.py`: Update MCP tests to reflect unified context execution.
21. `tests/test_cache.py`: Update cache tests to verify new cache policy.
22. `tests/test_review.py`: Update review tests to verify provider origin validation.

---

### 8.2 Comprehensive `/docs` Synchronization Inventory (44 Files across 4 Groups)

#### Group 1: Core Specifications & Public Contracts (16 files)
1. `docs/ARCHITECTURE.md`: Invocation context architecture, physical target allowlists, cache policy, and provider egress boundary.
2. `docs/SECURITY.md`: Control 7 (Invocation & Cache Security), target containment, and cross-origin redirect prevention.
3. `docs/SAFETY.md`: Single execution boundary, zero runtime retries on side-effect errors, fail-closed egress.
4. `docs/PRIVACY.md`: Scrubbing of cache payloads, prompt egress restrictions, secret protection across transports.
5. `docs/API_REFERENCE.md`: Public APIs for `rush.invocation` (`InvocationContext`, `PhysicalTarget`, `resolve_invocation`, `decide_cache`, `InvocationExecutor`).
6. `docs/CLI_REFERENCE.md`: CLI invocation semantics, `--no-cache` flag, exit code mappings.
7. `docs/MCP.md`: MCP transport parity with CLI, immutable request handling, zero mutable config leaks.
8. `docs/MCP_REFERENCE.md`: MCP tool schemas, dual-transport capability coverage, error framing.
9. `docs/CONFIGURATION.md`: Configuration resolution, cache configuration, provider egress configuration.
10. `docs/CONFIG_SCHEMA.md`: Config schema for cache, providers, and target selectors.
11. `docs/GLOSSARY.md`: Glossary terms for `InvocationContext`, `PhysicalTarget`, `CacheDecision`, `Effective Origin`, `Dual-Transport Parity`.
12. `docs/TOOL_CATALOG.md`: Pure vs. side-effecting operations cache eligibility catalog.
13. `docs/JSON_SCHEMA.md`: Invocation context schema, cache entry schema, provider egress response schema.
14. `docs/SEMANTIC_DRIFT.md`: Reconciliation of transport divergence, TypeError retries, and LLM labeling drift.
15. `docs/SCOPE.md`: Scoping rules, target selection provenance, and ignored host inputs.
16. `docs/ENVIRONMENT_VARIABLES.md`: Cache directory overrides, provider API key resolution.

#### Group 2: Developer, Safety & Maintainer Guides (16 files)
17. `docs/developer/architecture.md`: Section on invocation subsystem and dual-transport architecture.
18. `docs/developer/source-tree.md`: Add `src/rush/invocation/` layout and module boundaries.
19. `docs/developer/testing-guide.md`: Section on Phase 57 contract test suites (`tests/test_phase57_*.py`).
20. `docs/developer/debugging-guide.md`: Troubleshooting cache misses, transport divergence, and provider egress errors.
21. `docs/developer/tool-development.md`: Writing tools that declare purity for cache eligibility and adhere to single-execution contracts.
22. `docs/developer/backlog.md`: Milestone table update marking Phase 57 Complete.
23. `docs/developer/issues.md`: Resolution of ISS-057-01 (Transport Divergence & Scope Widening) and ISS-057-02 (Cache Identity & Provider Labeling Drift).
24. `docs/developer/phase-57-implementation-evidence.md`: Baseline and contract test evidence.
25. `docs/safety/security-model.md`: Provider egress threat model, approved HTTPS origins, proxy rules.
26. `docs/safety/permissions.md`: Permission context binding in `InvocationContext`.
27. `docs/safety/privacy-and-data-handling.md`: Sanitized cache storage and prompt egress data hygiene.
28. `docs/safety/safety-overview.md`: Summary of single-execution and transport parity safety guarantees.
29. `docs/maintainers/release-playbook.md`: Pre-release verification gates for Phase 57.
30. `docs/maintainers/versioning-and-compatibility.md`: Transport contract stability and cache versioning rules.
31. `docs/maintainers/incident-and-security.md`: Provider credential leakage and cache poisoning incident triage.
32. `docs/maintainers/adr/010-tdd-guard-and-continuous-sensors.md`: Cache integration update.

#### Group 3: Reference, User Guide & Agentic Integration (7 files)
33. `docs/agentic-rush/plugins-and-agent-skills.md`: Agent skills interaction with invocation context and cache.
34. `docs/reference/cli-reference.md`: Reference for CLI flags, cache options, and exit codes.
35. `docs/reference/configuration-reference.md`: Reference for cache and provider configuration.
36. `docs/reference/result-reference.md`: Reference for cached `ToolResultV1` shapes.
37. `docs/reference/environment-variables.md`: Reference for environment variables in invocation context.
38. `docs/getting-started/glossary.md`: Beginner terms for Cache, Invocation, and AI Review.
39. `docs/user-guide/security-and-supply-chain.md`: User guide for safe AI provider review and network boundaries.

#### Group 4: Governance, Evidence & Release Tracking (5 files)
40. `governance/remediation-phase-57.toml`: Phase 57 completion manifest.
41. `governance/remediation-contracts.toml`: Mark R-004 through R-007 completed.
42. `docs/user-guide/advanced-checks.md`: User guide for advanced invocation and cache options.
43. `README.md`: Update test badge (1,079 to 1,104 passed).
44. `CHANGELOG.md`: Log Phase 57 additions under `[0.3.0]`.

---

### 8.3 Dependency Constraints
- Zero third-party dependencies introduced.
- Strict reliance on Python 3.12 standard library (`hashlib`, `urllib.parse`, `sqlite3`, `pathlib`, `dataclasses`, `inspect`).

---

## 9. Ordered Workstreams and Atomic Task Cards

### P57.0 — Admission Gate & Baseline Evidence

#### P57.0.1 — EVIDENCE: Map Request-to-Execution Call Paths and Target Branches
- **Task ID:** P57.0.1
- **Binary Outcome:** Clean baseline evidence recorded in `docs/developer/phase-57-implementation-evidence.md`; full test suite passes (1,079 passed); execution call paths mapped.
- **Prerequisites:** Admission gate §4 passed.
- **Allowed Writes:** `docs/developer/phase-57-implementation-evidence.md`.
- **Actions:**
  1. Run `.venv/Scripts/python.exe -m pytest tests/ -q` and record 1,079 passing tests.
  2. Inspect CLI argument parsing, MCP tool handlers, cache keys in `src/rush/cache.py`, and provider handlers in `src/rush/providers/`.
  3. Map call paths and divergence points to tasks P57.1 through P57.6.

---

### P57.1 — Unified Invocation Context & Parity

#### P57.1.1 — RED: Define Unified Invocation Context Contract Tests
- **Task ID:** P57.1.1
- **Binary Outcome:** Create `tests/test_phase57_invocation_context.py` containing contract tests T-57.01, T-57.02, T-57.03; tests fail (RED).
- **Prerequisites:** P57.0.1.
- **Allowed Writes:** `tests/test_phase57_invocation_context.py`.
- **Actions:**
  1. Author T-57.01 (`test_cli_and_mcp_resolve_equivalent_context`).
  2. Author T-57.02 (`test_mcp_request_never_receives_mutable_config`).
  3. Author T-57.03 (`test_dual_transport_parity_across_transports` - R-007).
  4. Run `pytest tests/test_phase57_invocation_context.py -q` and confirm failures.

#### P57.1.2 — GREEN: Implement Invocation Models & Resolver
- **Task ID:** P57.1.2
- **Binary Outcome:** Implement `src/rush/invocation/models.py` and `src/rush/invocation/resolver.py`; tests in `tests/test_phase57_invocation_context.py` pass (GREEN).
- **Prerequisites:** P57.1.1 RED.
- **Allowed Writes:** `src/rush/invocation/__init__.py`, `src/rush/invocation/models.py`, `src/rush/invocation/resolver.py`, `src/rush/config.py`, `src/rush/permissions.py`.
- **Actions:**
  1. Define `InvocationContext`, `PhysicalTarget`, `CacheDecision` in `models.py`.
  2. Implement `resolve_invocation(request, transport)` in `resolver.py`: extracts parameters, creates immutable snapshot of config and permissions, and normalizes paths.
  3. Ensure MCP requests receive frozen declared values with zero mutable references.
  4. Run `pytest tests/test_phase57_invocation_context.py -v` and confirm GREEN.

---

### P57.2 — Physical Target Scope & Containment

#### P57.2.1 — RED: Define Scope Containment & Target State Contract Tests
- **Task ID:** P57.2.1
- **Binary Outcome:** Create `tests/test_phase57_physical_scope.py` containing contract tests T-57.04, T-57.05, T-57.06; tests fail (RED).
- **Prerequisites:** P57.1.2.
- **Allowed Writes:** `tests/test_phase57_physical_scope.py`.
- **Actions:**
  1. Author T-57.04 (`test_target_states_and_selection_provenance_are_immutable`).
  2. Author T-57.05 (`test_link_junction_and_swap_cannot_widen_scope`).
  3. Author T-57.06 (`test_undeclared_host_input_refuses`).
  4. Run `pytest tests/test_phase57_physical_scope.py -q` and confirm failures.

#### P57.2.2 — GREEN: Implement Physical Target Allowlist & Containment
- **Task ID:** P57.2.2
- **Binary Outcome:** Implement `src/rush/invocation/targets.py`; tests in `tests/test_phase57_physical_scope.py` pass (GREEN).
- **Prerequisites:** P57.2.1 RED.
- **Allowed Writes:** `src/rush/invocation/targets.py`, `src/rush/invocation/resolver.py`.
- **Actions:**
  1. In `targets.py`, implement target allowlist validation using `rush.io.PhysicalRoot`.
  2. Classify targets as `present`, `deleted`, or `renamed`.
  3. Reject directory junctions, symlinks, and path traversal with `ScopeWideningError`.
  4. Enforce rejection of undeclared host inputs with `UndeclaredInputError`.
  5. Run `pytest tests/test_phase57_physical_scope.py -v` and confirm GREEN.

---

### P57.3 — Single Execution Boundary & Signature Adaptation

#### P57.3.1 — RED: Expose Runtime TypeError Retries & Signature Adaptation
- **Task ID:** P57.3.1
- **Binary Outcome:** Create `tests/test_phase57_public_operations.py` containing contract tests T-57.07, T-57.08, T-57.09; tests fail (RED).
- **Prerequisites:** P57.1.2.
- **Allowed Writes:** `tests/test_phase57_public_operations.py`.
- **Actions:**
  1. Author T-57.07 (`test_internal_typeerror_after_side_effect_executes_once`).
  2. Author T-57.08 (`test_unsupported_signature_fails_registration`).
  3. Author T-57.09 (`test_cli_mcp_signature_error_is_equivalent`).
  4. Run `pytest tests/test_phase57_public_operations.py -k "signature or typeerror" -q` and confirm failures.

#### P57.3.2 — GREEN: Implement Registration-Time Adaptation & Single Execution
- **Task ID:** P57.3.2
- **Binary Outcome:** Implement `src/rush/invocation/executor.py`; signature tests pass (GREEN).
- **Prerequisites:** P57.3.1 RED.
- **Allowed Writes:** `src/rush/invocation/executor.py`, `src/rush/catalog.py`, `src/rush/tools/__init__.py`.
- **Actions:**
  1. In `executor.py`, inspect and adapt callable signatures *once* during registration.
  2. In `InvocationExecutor.execute()`, invoke callable exactly once; do not catch `TypeError` at runtime for fallback invocation.
  3. Propagate genuine runtime errors cleanly.
  4. Run `pytest tests/test_phase57_public_operations.py -k "signature or typeerror" -v` and confirm GREEN.

---

### P57.4 — Public Operations Reconciliation & Routing

#### P57.4.1 — RED: Define Operation Reconciliation & Egress Contract Tests
- **Task ID:** P57.4.1
- **Binary Outcome:** Add contract tests T-57.10, T-57.11, T-57.12, T-57.13, T-57.14 to `tests/test_phase57_public_operations.py`; tests fail (RED).
- **Prerequisites:** P57.2.2, P57.3.2.
- **Allowed Writes:** `tests/test_phase57_public_operations.py`.
- **Actions:**
  1. Author T-57.10 (`test_transport_contracts_reconcile_with_operation_manifest` - R-004).
  2. Author T-57.11 (`test_every_retained_operation_reaches_manifest_implementation`).
  3. Author T-57.12 (`test_only_tool_pairs_require_semantic_parity`).
  4. Author T-57.13 (`test_unprobed_route_is_not_advertised`).
  5. Author T-57.14 (`test_output_egress_and_error_codes` - R-006).
  6. Run `pytest tests/test_phase57_public_operations.py -q` and confirm failures.

#### P57.4.2 — GREEN: Reconcile Operations & Dispatch via InvocationExecutor
- **Task ID:** P57.4.2
- **Binary Outcome:** Update `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`; all tests in `tests/test_phase57_public_operations.py` pass (GREEN).
- **Prerequisites:** P57.4.1 RED.
- **Allowed Writes:** `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `governance/public-operations.toml`.
- **Actions:**
  1. Reconcile all 146 operations in `public-operations.toml` with `OperationRegistry`.
  2. Ensure all CLI commands and MCP tools route through `resolve_invocation` and `InvocationExecutor`.
  3. Enforce that only paired tool operations require parity; admin/service operations preserve declared exit codes and frames.
  4. Run `pytest tests/test_phase57_public_operations.py -v` and confirm GREEN.

---

### P57.5 — Cryptographic Cache Policy & Safe Execution Boundary

#### P57.5.1 — RED: Define Cache Identity & Bypass Contract Tests
- **Task ID:** P57.5.1
- **Binary Outcome:** Create `tests/test_phase57_cache_policy.py` containing contract tests T-57.15 through T-57.22; tests fail (RED).
- **Prerequisites:** P57.1.2, P57.2.2.
- **Allowed Writes:** `tests/test_phase57_cache_policy.py`.
- **Actions:**
  1. Author T-57.15 (`test_cache_identity_and_bypass_contracts` - R-005).
  2. Author T-57.16 (`test_cache_key_binds_every_context_and_target_identity`).
  3. Author T-57.17 (`test_missing_identity_returns_bypass_without_key`).
  4. Author T-57.18 (`test_artifact_behavior_config_permission_target_mutation_misses`).
  5. Author T-57.19 (`test_no_cache_performs_no_read_or_write`).
  6. Author T-57.20 (`test_cache_set_requires_sanitized_valid_tool_result`).
  7. Author T-57.21 (`test_cache_get_resanitizes_and_revalidates`).
  8. Author T-57.22 (`test_only_manifest_pure_operation_uses_cache`).
  9. Run `pytest tests/test_phase57_cache_policy.py -q` and confirm failures.

#### P57.5.2 — GREEN: Implement Deterministic Cache Key Policy & Executor Gating
- **Task ID:** P57.5.2
- **Binary Outcome:** Implement `src/rush/invocation/cache_policy.py`, update `src/rush/cache.py` and `src/rush/invocation/executor.py`; all tests in `tests/test_phase57_cache_policy.py` pass (GREEN).
- **Prerequisites:** P57.5.1 RED.
- **Allowed Writes:** `src/rush/invocation/cache_policy.py`, `src/rush/cache.py`, `src/rush/invocation/executor.py`.
- **Actions:**
  1. Implement `decide_cache(context)`: checks operation purity, `--no-cache`, and identity completeness. Computes SHA-256 cache key over all context fields + target contents.
  2. In `executor.py`, integrate cache check before execution; on miss, execute once and store sanitized/validated `ToolResultV1`.
  3. In `cache.py`, ensure get/set strictly sanitize via redactor and validate via `validate_tool_result`.
  4. Run `pytest tests/test_phase57_cache_policy.py -v` and confirm GREEN.

---

### P57.6 — Provider Egress Truth & Effective Origin Validation

#### P57.6.1 — RED: Define Provider Outcome & Origin Verification Contract Tests
- **Task ID:** P57.6.1
- **Binary Outcome:** Create `tests/test_phase57_provider_egress.py` containing contract tests T-57.23, T-57.24, T-57.25; tests fail (RED).
- **Prerequisites:** P57.1.2.
- **Allowed Writes:** `tests/test_phase57_provider_egress.py`.
- **Actions:**
  1. Author T-57.23 (`test_denied_redirected_failed_or_empty_work_is_not_llm`).
  2. Author T-57.24 (`test_cross_origin_redirect_receives_no_authorization_or_prompt`).
  3. Author T-57.25 (`test_approved_effective_origin_completion_is_llm`).
  4. Run `pytest tests/test_phase57_provider_egress.py -q` and confirm failures.

#### P57.6.2 — GREEN: Implement Approved Effective Origin & Outcome Labeling
- **Task ID:** P57.6.2
- **Binary Outcome:** Update `src/rush/providers/` and `src/rush/tools/review.py`; tests in `tests/test_phase57_provider_egress.py` and `tests/test_review.py` pass (GREEN).
- **Prerequisites:** P57.6.1 RED.
- **Allowed Writes:** `src/rush/providers/base.py`, `src/rush/providers/openai.py`, `src/rush/providers/anthropic.py`, `src/rush/tools/review.py`.
- **Actions:**
  1. Implement `ProviderOutcome` (`completed`, `skipped`, `error`) and effective HTTPS origin checking.
  2. Refuse cross-origin redirects without forwarding authorization headers or prompt contents.
  3. In `review.py`, apply `review_kind = "llm"` only when `outcome == "completed"` with a non-empty, schema-valid response from an approved origin.
  4. Run `pytest tests/test_phase57_provider_egress.py tests/test_review.py -v` and confirm GREEN.

---

### P57.7 — Comprehensive Documentation & Governance Sync

#### P57.7.1 — VERIFY/DOCS: Synchronize All 44 Documentation and Governance Files
- **Task ID:** P57.7.1
- **Binary Outcome:** All 44 documentation and governance files listed in §8.2 are updated and synchronized with zero drift.
- **Prerequisites:** P57.1.2 through P57.6.2 GREEN.
- **Allowed Writes:** All 44 files listed in §8.2.
- **Actions:**
  1. Create `governance/remediation-phase-57.toml` documenting phase completion, 25 contract tests, and closure of R-004, R-005, R-006, R-007.
  2. Update `governance/remediation-contracts.toml` marking R-004 through R-007 completed.
  3. Update `docs/developer/phase-57-implementation-evidence.md` with final gate runs.
  4. Update `README.md` test badge (1,079 to 1,104 passed); update `CHANGELOG.md` under `[0.3.0]`.
  5. Update all 40 technical docs across `/docs` with invocation context, physical scope, cache policy, and provider egress mechanics.
  6. Verify zero whitespace defects with `git diff --check`.

---

## 10. Final Verification and Delivery Gate

Execute the following commands in sequence to verify Phase 57 delivery:

```powershell
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 1. Run all 25 focused Phase 57 contract tests
.venv/Scripts/python.exe -m pytest tests/test_phase57_invocation_context.py tests/test_phase57_physical_scope.py tests/test_phase57_public_operations.py tests/test_phase57_cache_policy.py tests/test_phase57_provider_egress.py -v

# 2. Run regression suites
.venv/Scripts/python.exe -m pytest tests/test_cli.py tests/test_mcp.py tests/test_cache.py tests/test_review.py tests/test_phase55_*.py tests/test_phase56_*.py -q

# 3. Run complete test suite (expecting 1,104 passed tests: 1,079 baseline + 25 contract tests)
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
- [ ] `InvocationContext` is unified and immutable across CLI and MCP transports.
- [ ] MCP requests receive frozen declared values; zero mutable config leaks.
- [ ] Target allowlists contained under `rush.io.PhysicalRoot`; symlinks/junctions fail closed with `ScopeWideningError`.
- [ ] Single execution boundary enforced; zero runtime retries on internal `TypeError`.
- [ ] 100% of operations in `governance/public-operations.toml` route to canonical implementations and adapters.
- [ ] Dual-transport parity enforced for all core quality tools across CLI and MCP.
- [ ] Cryptographic cache key binds all context and target identities; missing identity returns `bypass` (zero fallback salts).
- [ ] `--no-cache` performs zero cache reads and zero cache writes.
- [ ] Cache get/set values are sanitized via redactor and validated as `ToolResultV1`.
- [ ] LLM provider outcomes are explicit (`completed`, `skipped`, `error`); `review_kind = "llm"` requires approved HTTPS origin completion.
- [ ] Cross-origin redirects refuse to forward credentials or prompts fail-closed.
- [ ] Zero third-party dependencies introduced; 100% pure Python 3.12 standard library.
- [ ] All 25 contract tests in `tests/test_phase57_*.py` pass.
- [ ] Full pytest suite passes with 1,104 tests (1,079 baseline + 25 Phase 57 contract tests).
- [ ] All 44 documentation and governance files updated and synchronized across `/docs` and repo root.
- [ ] `governance/remediation-phase-57.toml` created with complete test and requirement records.
- [ ] Requirements R-004, R-005, R-006, and R-007 reconciled in `governance/remediation-contracts.toml` as completed.
- [ ] Successor phase (Phase 58 lock persistence & patch remediation) unblocked with stable invocation and cache interfaces.
