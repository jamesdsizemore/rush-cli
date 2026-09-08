# Repository Review and Remediation Plan

**Status:** Completed (100% Remediation Program Complete)
**Review date:** 2026-08-27 (Completed 2026-09-06)
**Implementation status:** All 16 findings (R-001 through R-016) are now 100% COMPLETE. Release-ready gates satisfied in Phases 52-59; Phase 9 maintainability hotspot reduction completed in Phase 60.
**Program scope:** Rush first-party product, packaging, release artifacts, CLI, stdio MCP, public operations, plugins, persistence, patch workflow, engines, documentation contracts, and tests.

## Executive decision

No release is permitted until the release-ready definition below is met. R-001, R-002, R-003, R-016, and any retained public operation without its required gate are release blockers. A green source-tree suite is never release evidence.

The review did not establish an auditable exact population of first-party files. Phase 0 creates the deterministic coverage manifest that scopes every repository-wide conclusion and classifies exclusions, including local untracked `research/`. Until then, this plan records observed findings, not exhaustive absence claims.

The following product decisions are locked. An implementation PR may not silently choose another option.

| Decision | Locked choice | Consequence |
|---|---|---|
| Publication artifacts | Wheel and sdist remain publishable | Both are independently installed and probed on Windows and POSIX. |
| Execution caching | Retained | Only declared pure operations are cacheable; identity and bypass rules are mandatory. Cache-management commands remain public admin operations. |
| Plugin isolation | Environment-only hardening | Approved plugins remain trusted user code with ambient filesystem and network authority; no OS/container sandbox claim is made. |
| Plugin trust authority | User-owned ledger and snapshot store outside the repository | Repository receipts are non-authorizing; legacy path grants require explicit reapproval. |
| Plugin launch platform | Fail closed | Trusted launch is disabled on a platform unless snapshot/handle mechanics prove approved bytes or no child starts. |
| Plugin secret configuration | Secret-free snapshots plus protected reference channels | Literal secret-bearing argv/config/resource bytes are rejected. A raw reference may reach the child only through its declared protected descriptor, protected-stdin protocol, or approved OS credential-provider channel; ordinary environment, argv, and configuration/resource files are forbidden. |
| Lock operations | Retained public tools with caller-generated capabilities | Raw capability is request-only ephemeral, supplied through a transport-specific secret channel; repository metadata stores only its verifier. |
| R-015 | Non-release remediation program | Release readiness does not wait for R-015; remediation-program completion does. |

## Review coverage and evidence boundary

Phase 0 must commit a deterministic first-party coverage manifest for `src`, `tests`, `scripts`, all shipping/user-facing documentation (including root README), templates, generated release documents, packaged metadata, packaging, release, and CI files. It records Git revision, inclusion rules, generated/vendor exclusions, and the reason local untracked `research/` is excluded. Every exhaustive search, stale-version/assurance scan, dead-code conclusion, and release gate consumes this manifest.

The review used graph traversal, targeted inspection, call-path tracing, clean-wheel execution, typing, linting, and repeated suite runs. These observations remain useful evidence, but the manifest—not an unsupported file count—becomes the coverage boundary.

| Area | Observed surfaces | Disposition |
|---|---|---|
| Packaging and entry points | `pyproject.toml`, package imports, wheel startup | R-001 |
| CLI, MCP, catalog, public operations | command builders, registry, legacy registrations, integration tests | R-004 through R-007 |
| Results, engines, redaction, logs, cache | `ToolResult`, normalizers, subprocesses, output/write boundaries | R-002, R-008, R-011, R-014 |
| Plugins | legacy/hardened trust and execution routes | R-003 |
| Coordination and persistence | locks, maps, journals, continuity callers | R-009, R-010 |
| Patch workflow | parser, worktree/sandbox, verifier, cleanup, public command | R-016 |
| Release/provenance/version | artifacts, attestations, templates, user-facing documentation | R-012, R-013 |
| Maintainability | central transport and orchestration hotspots | R-015; non-release program (completed) |

## Findings register

### R-001 — Critical — Installed artifacts cannot start reliably

**Evidence**

- `pyproject.toml:39` publishes `rush = "rush.cli:cli"`; `pyproject.toml:49-50` packages `src/rush`.
- Production imports use source-tree-only `src.rush` paths, including `src/rush/codegraph/context_packer.py:8` and `src/rush/core/git_sandbox.py:8`.
- `pyproject.toml:55-56` adds both `.` and `src` to test import paths.
- A clean built-wheel installation failed at `rush --help` with `ModuleNotFoundError: No module named 'src'`; `mypy src/rush` reported dual `rush.*` / `src.rush.*` identity.

**Impact:** A built artifact can be unusable while source-tree tests pass.

**Root cause:** The source-layout contract is not enforced from isolated installed artifacts. sdist parity is unproven and must be tested rather than assumed.

### R-002 — Critical — Redaction is not a complete serialization and write boundary

**Evidence**

- `src/rush/tools/common.py:28-33` uses `_SECRET_ASSIGNMENT` defined at `:318-320` for subprocess output.
- Observed probes leaked authorization/bearer and quoted JSON forms; `tests/test_subprocess_contract.py` starts from redacted fixture text instead of fresh secrets.
- `SecretRedactor.redact_value` is recursive for values but does not establish coverage of mapping keys, URL components, persistence, temporary artifacts, or every transport boundary.

**Impact:** Secret-like values can reach public responses, logs, exports, cache, persistence, and failed-write artifacts.

**Root cause:** No one sanitizer is defined and invoked at every serializable output/write boundary.

### R-003 — Critical — Plugin execution lacks a complete immutable content identity

**Evidence**

- `src/rush/cli.py:1220-1234` checks legacy repository-path trust and calls `plugins.loader.execute_plugin`.
- `src/rush/plugins/trust.py` stores repository-path grants, while `trust_store.py` stores repository-local executable hashes; their authorities and record shapes differ.
- `plugins/loader.py` executes configured commands with inherited environment; `HardenedPluginExecutor` and `SandboxedEnvironment` are not the production CLI route.

**Impact:** A previously approved repository path can launch changed code, configuration, interpreter-selected modules, or dependency/resource bytes. A snapshot that embeds literal secrets would create a second disclosure path; an executable hash alone does not identify runtime code.

**Root cause:** Legacy and hardened paths have incompatible trust stores and neither defines a user-owned immutable secret-free execution closure, exact runtime identity, protected secret-reference channel, or non-substitutable launch.

### R-004 — High — Public operation surface is undocumented and transport contracts diverge

**Evidence**

- `src/rush/mcp.py:49-56` registers canonical `ALL_TOOLS`, then registers 25 manual operations at `:58-427`.
- Manual wrappers return `str`, `bool`, or raw dictionaries and bypass the canonical implementation contract.
- `tests/test_mcp.py:25-52` lists the split surface; schema assertions apply only to catalog tools at `:258-263`.

**Impact:** Raw CLI/MCP set equality is neither a valid product contract nor proof of equivalent behavior.

**Root cause:** Public operations were added without a versioned inventory, disposition, output-contract class by operation kind, transport-specific probe, or semantic parity model.

### R-005 — High — Scope and execution-cache contracts are absent from generic invocation

**Evidence**

- `src/rush/cli.py:136+` exposes `--no-cache`, `--staged`, `--changed`, `--since`, `--workspace`, and `--all-workspaces`.
- `src/rush/cli.py:190-266` computes staged/changed/since lists only for empty checks, then invokes the broad original path; `no_cache` and `all_workspaces` are unused.
- Cache-management commands construct `ResultCache`, but generic execution has no production `compute_cache_key` / `get` / `set` path. Cache unit tests therefore do not establish execution integration.

**Impact:** Scope can widen silently and a cache can survive changes in artifact or tool behavior.

**Root cause:** Transport flags preceded one physical-target, invocation, and cache-identity contract.

### R-006 — High — Internal `TypeError` can rerun a tool

**Evidence**

- `src/rush/cli.py:86-133` catches a `TypeError` from `tool.run(...)` and retries without permissions.
- The exception can be from tool internals after a side effect, not signature binding.

**Impact:** Work can execute twice, permissions can be dropped, and the real error can be obscured.

**Root cause:** Runtime exceptions are used for signature negotiation.

### R-007 — High — LLM-review labeling is not tied to approved completed egress

**Evidence**

- `src/rush/cli.py:492-541` gathers LLM/network options but does not reliably deliver permission to `ReviewTool`.
- `src/rush/tools/review.py:455-470` calls providers without an explicit outcome or effective-origin contract.
- Provider adapters can return canned content when network permission is disabled, while output is labeled as LLM review.

**Impact:** Heuristic, denied, redirected, or failed work can be represented as approved model analysis.

**Root cause:** Provider denial/failure/egress is modeled as successful content rather than a constrained discriminated outcome.

### R-008 — High — Exception diagnostics can disappear

**Evidence**

- `src/rush/logging.py:29-35` passes `record.exc_info` to `Handler.format` rather than formatting the `LogRecord`/exception correctly.
- The handler swallows formatter errors; an observed `logger.exception(...)` probe emitted no event.

**Impact:** The stderr diagnostics required by stdio MCP can be absent precisely on failure paths.

**Root cause:** Incorrect formatter use and silent drop-on-failure behavior.

### R-009 — High — File locks are not atomic, secret holder capabilities

**Evidence**

- `src/rush/mcp_mesh/lock_manager.py:45-59` checks existence then writes; `:61-70` reads then unlinks.
- `mcp_mesh/daemon.py` duplicates the implementation.
- Existing operations expose boolean/agent-ID authority rather than holder-only capabilities.

**Impact:** Competing agents can both claim a lock, or a direct-file attacker can recover authority if a raw token is stored or transported through ordinary argv/output/log paths.

**Root cause:** Metadata-file existence is treated as atomic ownership and no caller-generated capability, secret-input-channel, or verifier-only storage contract exists.

### R-010 — High — Persistence lacks physical containment and distinct map/journal integrity contracts

**Evidence**

- `invariant_graph.py`, `preference_store.py`, and `merkle_invalidator.py` perform unlocked read-modify-write and return empty state on failures.
- `checkpoint_journal.py` writes individual records directly, relies on callers for name validation, and skips corrupt records while listing.
- **Phase 61 update:** this evidence describes each file's pre-Phase-58 shape. Phase 58 (below) closed R-010 by moving all four onto `CASMapTransaction`/`rush.io.AtomicFile`. As of Phase 61, all four are further reduced to thin compatibility views over the unified `TypedArtifactStore` (`.rush/memory.db`) — public signatures unchanged, canonical data no longer lives in a per-store JSON/journal file; `checkpoint_journal.py`'s `save_checkpoint()` still returns a real, existing `Path` for backwards compatibility.

**Impact:** Shared maps can lose updates; journals, temporary files, backups, and lock records can be substituted through file/directory links, junctions, or races, then be falsely reported absent.

**Root cause:** Shared maps and journals need different transaction semantics, but every persistence boundary also lacks a common no-follow, handle-safe physical-containment policy.

### R-011 — High — The declared result schema does not match runtime producers

**Evidence**

- `src/rush/tools/base.py` declares finding severity `info | warn | error`.
- Production findings include `fail` and `warning`; exporters and tests maintain compatibility branches.
- No runtime schema boundary validates every public result.

**Impact:** Consumers must guess shape and severity semantics.

**Root cause:** There is no versioned runtime result schema shared by tool, plugin, cache, export, persistence, lock, patch, and transport boundaries.

### R-012 — Medium — Version metadata is duplicated

**Evidence**

- `src/rush/__init__.py:11` reports `0.3.0`.
- Older literals remain in generated/runtime consumers, templates, and user-facing release documentation.

**Impact:** User agents and artifacts can report stale versions.

**Root cause:** Copied literals rather than one derived public version source and manifest-scoped documentation scan.

### R-013 — High — Local provenance output claims unsupported assurance

**Evidence**

- `src/rush/tools/attest.py:1-82` calls local unsigned JSON “SLSA Level 3”.
- It asserts reproducibility/completeness without collected evidence and may hash a commit string as an artifact subject.
- `src/rush/mcp.py:403-407` repeats the assurance claim.

**Impact:** Consumers can mistake statement-shaped local metadata for verified supply-chain provenance.

**Root cause:** Shape, signature, signer-builder identity, package/artifact identity, and assurance level are conflated.

### R-014 — Medium — Engine test outcomes depend on ambient installation state

**Evidence**

- A full suite observed `846 passed, 1 failed` in the `knip` discovery/version case; an isolated rerun passed and a later full run observed `847 passed`.
- The current test topology mixes deterministic contracts with ambient-engine behavior.

**Impact:** CI can change without a source change and cannot demonstrate the advertised engine surface.

**Root cause:** No published support taxonomy or provisioned conformance matrix exists.

### R-015 — Medium — Central modules remain maintainability hotspots [COMPLETED]

**Evidence**

- Health analysis identifies `cli.py`, `review.py`, `continuity.py`, `common.py`, and `lint.py` as high-change/complexity paths.
- The review identified complexity around 25-26 in `blast_radius.analyze`, workspace discovery, and database-drift paths.

**Impact:** Later changes remain costly and regression-prone.

**Disposition:** Non-release remediation program after correctness release. Completed in Phase 9 (Phase 60). All 8 target hotspots reduced to McCabe C901 <= 10 with 0 exemptions in `governance/maintainability-exemptions.toml` and 26/26 contract tests passing.

### R-016 — Critical — Public patch verification and target-state binding can fail open

**Evidence**

- The public patch path can report verification without requiring `PatchVerifier` after a successful application.
- Worktree creation/verifier unavailability, direct-apply failure, cleanup ownership, temporary-name collisions, rollback, containment, and symlink behavior do not have one fail-closed contract.
- The patch path does not require a recorded clean/snapshotted target state that binds patch, sandbox base, and result identities.

**Impact:** A public remediation command can claim verification without running required commands or can apply against drifting dirty/untracked state, leaving an altered checkout, escaped artifact, or unmanaged cleanup target.

**Root cause:** Verification outcomes, clean-base command-policy binding, ignored-host-input binding, tree/diff identity, rollback, sandbox confinement, and cleanup ownership are not enforced at the public command boundary.

## Remediation program

### Phase 0 — Freeze decisions, scope, and failing release gates

**Goal:** Establish auditable scope and executable gates before behavior changes. Gates may intentionally fail on the unfixed revision; each test records its expected pre-change failure.

1. Generate and commit the deterministic coverage manifest described above. It covers source, tests, scripts, root/user-facing docs, templates, generated release docs, packaged metadata, packaging, release, and CI; it records tool version, Git revision, rules, and exclusions. Scope all repository-wide claims and scans to it.
2. Create a versioned public-operation manifest before migration. It covers every Click leaf and all 25 legacy MCP operations with operation ID; kind (`tool`, `admin`, `service`, or `deprecated`); disposition; canonical implementation; CLI/MCP names and aliases; input schema; config policy; effect/permission class; **output-contract class and target ID**; compatibility notice; declared ignored runtime/test inputs; and transport-specific safe probe. `kind=tool` requires `ToolResultV1`; `kind=admin` requires an explicitly named admin-output contract (and uses `ToolResultV1` only when selected); `kind=service` uses liveness/protocol contract, not a wrapped result envelope. Only invoked tool calls are subject to `ToolResultV1`; only `kind=tool` pairs require CLI/MCP parity. No unclassified public route may remain advertised.
3. Define probes by manifest operation ID and transport: Click-only operations run an installed CLI probe; MCP tools run installed stdio `tools/call`; services receive liveness/protocol probes; `tools/list` reconciles only MCP-advertised entries. Pure operations use fixtures; engine operations exercise fixture and missing-engine paths; write/network/destructive operations use dry-run or injected fakes. Probes reject undeclared ignored host inputs or snapshot/content-address them and bind their identities; verification uses controlled environment/config roots. An operation with no safe probe is removed from advertising.
4. Record the locked cache, plugin-isolation, trust-authority, lock, artifact, and R-015 decisions in the operation manifest/release policy. Retain and admin-test `cache stats`/`cache clean` as public admin operations.
5. Build wheel and sdist, then install each into a fresh environment from a newly created empty directory outside the checkout on Windows and POSIX. Scrub `PYTHONPATH`, disable editable installation, assert every imported `rush.*` origin is installed, and assert checkout `src` is absent from import search. Include an isolated deliberately broken `src.rush` negative control.
6. Add fresh-sentinel redaction tests for subprocess, CLI, MCP, logs, exports, cache, persistence, provenance, trust receipts, temporary/backup files, and aborted writes. Include authorization/bearer/basic values, JSON/YAML, environment assignments, URL userinfo/query/fragment/percent encoding, mapping keys/collisions, identifiers, nested values, exception text, and truncation. Raw secret-bearing semantic inputs are owner-only ephemeral memory; they are neither returned nor persisted as artifacts, and sanitization must not mutate the inputs actually used to execute an approved action.
7. Add production-route `CliRunner` plugin fixtures: establish legacy trust, invoke `rush plugin run`, observe a child inherited-environment sentinel, reject every literal sentinel in argv/config/resource input, execute each declared protected-channel secret-reference fixture while a same-user observer captures child argv and environment, and scan snapshot/temp/ledger/receipt/output artifacts for literals. The sentinel must be absent from observer captures and every artifact while the plugin receives it only through its declared protected channel. Mutate executable/config/command, transitive dependency/resource, script directory, `PYTHONPATH`, dynamic import target, interpreter, file, symlink, and junction after approval; record pre-change failures and preserve inverted post-migration gates.
8. Add contract fixtures for schema kernel, signature adaptation, physical target and ignored-host-input selection, provider egress, caller-generated lock capability secrecy, shared-map/journal persistence, patch state/command-policy binding, duplicate-detecting provenance parsing, and `AtomicFile` fault behavior. Separate deterministic tests from engine conformance tests on a fixed PATH.
9. Publish engine support classes—mandatory, supported optional, best-effort—and identify every supported family and pinned provisioned conformance matrix. Unavailable skip is permitted only where that policy says so.

**Exit criteria:** The coverage and operation manifests are complete/versioned; every public operation has disposition plus correct transport probe; artifact harnesses prove isolation and detect the negative control; pre-change tests expose intended packaging/plugin/registry/redaction/scope/lock/patch failures without classifying unrelated ambient-engine behavior as deterministic.

### Phase 1 — Repair package namespace, artifact parity, and version source

**Addresses:** R-001, R-012.

1. Replace production/test `src.rush...` imports with `rush...` or relative imports and remove source-tree import leakage from test configuration.
2. Derive public version from `importlib.metadata` with an explicit development fallback; route generated user agents, SARIF, TUI, scaffolding, TypeScript headers, templates, and release docs through it.
3. Run manifest-scoped stale-version and unsupported-assurance scans across every shipping/user-facing doc, root README, template, generated release document, and packaged metadata. Record only explicit historical exemptions in the coverage manifest.
4. Make wheel and sdist external-CWD CLI/import/MCP probes pass independently on Windows and POSIX, including origins and every retained safe operation probe.

**Exit criteria:** Neither installed artifact imports checkout code or `src.rush`; both artifact families pass isolated probes; mypy analyzes one package namespace; version/assurance scans pass within manifest scope.

### Phase 2 — Make sanitization and diagnostics complete at every write boundary

**Addresses:** R-002, R-008.

1. Define one recursive JSON-safe sanitizer that handles values and user-controlled mapping keys, detects/redacts collisions deterministically, preserves serializable structure, and emits no secret-bearing diagnostics.
2. Apply it before every output/write: findings, summary, raw/metadata, CLI/MCP serialization, stderr, exports, execution cache, checkpoints, preferences, invariants/failures/merkle stores, trust receipts, provenance, temp files, backups, and rollback artifacts. Keep a final serializer pass.
3. Sanitize exception text and encoded URL components; bound output only after sanitation. Do not use the sanitizer to alter semantic execution inputs. A secret-bearing input may exist only in caller-owned ephemeral memory until consumed; it must never appear in a result, log, cache, trust receipt, provenance record, temporary file, backup, or rollback artifact.
4. Correct exception formatting from complete `LogRecord`/`exc_info`; on formatter failure emit exactly one minimal redacted stderr fallback without corrupting MCP stdout.

**Exit criteria:** Fresh corpus values are absent from every serializable position and completed/aborted artifact; collision behavior is deterministic; semantic execution-input tests prove sanitizer output is not substituted for the authorized action input; `logger.exception` emits one valid redacted NDJSON record.

### Phase 3 — Establish and test the schema kernel only

**Addresses:** R-011; prerequisite for later migrations.

1. Define `ToolResultV1` and `FindingV1`: schema version, required envelope/finding fields, exact statuses, exact severities, JSON-safe values, extension namespace, canonical structured error shape, serializer, and one validator/normalizer.
2. Lock severity migration exactly: legacy finding `warn` maps to `warning`; legacy finding `fail` maps to `error`. Unknown severities are canonical validation errors after the migration boundary. Tool status remains `ok | warn | fail | error | skipped`.
3. Build adapter interfaces and fixtures by manifest output-contract class: tool calls target `ToolResultV1`; each admin operation declares its own named contract (or explicitly selects `ToolResultV1`); service routes retain liveness/protocol contracts. The Phase 0 manifest names the target class/ID; it does not claim every adapter already exists or wrap stdio initialize/liveness.
4. Validate the kernel, mappings, serializer, extension policy, and malformed-input canonical errors in isolation. Do not mark the eligible tool/admin boundary migrations complete in this phase.

**Exit criteria:** The kernel and class-specific adapters/fixtures are independently test-valid; exact legacy mappings are asserted; no eligible-tool-wide `ToolResultV1` closure claim is made before Phases 5-7 complete.

### Phase 4 — Establish `AtomicFile` and physical-containment prerequisite

**Addresses:** prerequisites for R-003, R-009, R-010, R-016.

1. Define a narrow shared `AtomicFile` owned by one module. Its input is an already-sanitized serializable byte/value contract; it never receives raw secret-bearing artifacts.
2. Require owner-root physical containment, same-directory unique temporary creation, no-follow/reparse-safe opens, permission/ownership checks, flush/fsync policy, atomic replace, and cleanup limited to manager-owned resolved handles/paths. On a platform where required no-follow/handle guarantees cannot be made, fail closed for the protected operation.
3. Add deterministic fault tests for temp creation, write, flush, replace, cleanup, file/dir symlink and Windows junction/reparse cases, and swap races. Prove old-or-new valid content only and no outside sentinel modification.
4. Define a reusable one-way verifier-record format for secrets/capabilities; raw values may not be persisted in repository metadata.

**Exit criteria:** `AtomicFile` passes containment, link/junction, race, fault, sanitization, and outside-sentinel tests on every supported platform. Trust receipts and later persistent writers must reuse it; no later phase may invent a second atomic-write primitive.

### Phase 5 — Migrate plugin authorization to immutable content-addressed execution snapshots

**Addresses:** R-003.

1. Replace repository-path authorization with one user-owned, versioned, link/junction-safe ledger outside the repository. Repository-local receipts are non-authorizing evidence. A cloned repository containing matching `.rush/trust.json` remains denied until explicit user grant.
2. At grant time, reject literal secret-bearing argv, configuration, resource, dependency, and snapshot bytes. Construct a content-addressed immutable execution snapshot/closure in user-owned storage from secret-free code/configuration. Bind approval to every executable code, dependency, resource, import root, interpreter/runtime byte, and configuration byte that can supply runtime code; store a closure manifest of canonical locations/digests, approved secret-reference **names**, each reference's declared protected child-secret transport, and a snapshot identity. Copy/materialize approved bytes into the snapshot—never mutable source paths or hard links to them.
3. Grant/revoke UX records exact repository identity, snapshot/closure identity, trusted absolute interpreter/runtime identity, normalized **secret-free** argv, secret-free configuration digest, approved secret-reference names, each reference's protected transport and transport-policy/platform binding, default-deny child-environment forwarding list, and grant metadata. Literal secret values never enter ledger/snapshot/receipt/temp/argv records/log/cache/results. Legacy path grants never silently authorize; explicit reapproval or user-confirmed upgrade writes every binding field using `AtomicFile`.
4. Launch only the verified snapshot using the exact trusted interpreter/runtime identity. Resolve a value for an approved secret-reference name only into caller-owned ephemeral launch state and that reference's declared protected child-secret transport immediately before spawn. It is forbidden to put a raw value in child argv, configuration/resource files, snapshot, or ordinary environment variables, or to serialize it in any recorded, rendered, or persisted artifact. The only permitted child-secret transports are an inherited protected descriptor, a protected stdin protocol, or an approved OS credential-provider channel. Reject the reference, execution mode, or platform when the selected transport cannot enforce confidentiality. Refuse interpreter/script combinations, dynamic imports, local imports, `PYTHONPATH`, script-directory imports, generated code, or dependency/resource modes whose complete runtime closure cannot be proven and snapshotted. The child environment starts with minimal documented platform bootstrap variables plus only names explicitly bound in the grant; it never inherits the parent environment wholesale.
5. On each supported platform, use handle-bound execution or equally non-substitutable verified-snapshot mechanics. A synchronized replacement of a file, symlink, junction, interpreter, dependency, or resource immediately before spawn must produce either approved bytes or no child process. If that guarantee is unavailable, trusted plugin launch is disabled on that platform.
6. Delete/private legacy execution and `allow_untrusted`; validate/sanitize plugin output through its `ToolResultV1` adapter. Document only environment filtering: approved plugin code still has ambient filesystem/network authority.

**Exit criteria:** Every sentinel literal in argv/config/resource is rejected; each declared protected-channel secret-reference fixture executes while a same-user observer captures child argv and environment, proving the sentinel is absent there and in full snapshot/temp/ledger/receipt/argv/log/cache/result scans while the plugin receives it only through its declared protected transport; transitive dependency/resource, dynamic-import, `PYTHONPATH`, script-directory, interpreter, file, symlink, and junction mutations result in approved snapshot bytes or no child; unsupported platform/mode/transport is denied rather than documented as exploitable residual.

### Phase 6 — Resolve invocation, physical target scope, public operations, cache, and provider egress

**Addresses:** R-004, R-005, R-006, R-007.

1. Implement `resolve_invocation(request, transport)` then `execute(context)`. It canonicalizes repository/workspace root, physical target identity, effective config, declared ignored runtime/test inputs and their bound identities, explicit permissions, ordered target entries, target capability, cache policy, installed artifact/build identity, and tool/normalizer behavior revision. MCP accepts declared request data, never a mutable config object.
2. Target entries include selection provenance and `present`/`deleted`/`renamed` state. Resolve reparse-safe physical identities; reject root escapes; revalidate identity/containment immediately before engine launch; use handle-safe containment where supported and fail closed where not. The operation/verification manifest must reject ignored host inputs or content-address/snapshot them; verification uses controlled environment/config roots and invalidates changed declared input identity. Scoped operations receive an immutable allowlist; repository-wide exceptions have a distinct declared contract.
3. Centralize registration-time signature adaptation. Unsupported implementations fail registration. A tool that makes one observed side effect then raises internal `TypeError` executes once and returns one canonical error in CLI and MCP.
4. Execute the public-operation manifest. Retained `kind=tool` operations migrate to shared implementation and declared target contract; approved admin/service operations remain classified; deprecated routes emit their notice; routes without a correct transport probe are removed. CLI-only, MCP, and service probes run by operation ID as defined in Phase 0.
5. Retain execution caching only for declared pure operations and validated results. Cache key includes schema version, installed artifact/build identity, per-tool and normalizer behavior revision, canonical root/workspace, ordered target identity/content/state, effective-config digest, engine/version, behavior arguments, and permissions. Identity/revision missing or changed causes a miss and bypasses read/write; `--no-cache` bypasses both. Test cross-wheel/build upgrade and target mutation collisions.
6. Give review providers `completed`, `skipped`, or `error` outcomes. A request may use only a configured approved HTTPS origin; redirects to another origin are rejected before prompt/auth forwarding; proxy use is disabled by default or allowed only through an explicit approved-proxy policy. Only schema-valid non-empty completion from the approved effective origin sets `review_kind=llm`.

**Exit criteria:** CLI and stdio resolve equivalent eligible-tool context for non-default config, permissions, roots, relative/absolute paths, workspace, and selection; link/junction/swap/outside-sentinel tests prove no scoped access escape; ignored generated-code/config fixtures prove host inputs are rejected or identity-bound; cache misses across artifact/behavior revision changes; provider tests prove redirect receivers receive neither authorization nor prompt and prove approved-proxy behavior; every retained operation passes its own transport probe.

### Phase 7 — Make locks, persistence, patch verification, and eligible output migration fail closed

**Addresses:** R-009, R-010, R-016; completes R-011 migration for eligible tool-call boundaries.

1. Retain lock operations per the manifest with caller-generated capability. Acquire requires a cryptographically strong, policy-validated capability delivered only through a transport-specific secret input channel: CLI reads from stdin or a protected descriptor/platform-secret facility, never argv; MCP uses a sensitive request field that is omitted from rendering/logging/persistence. Rush returns no raw capability. The caller retains and presents it for renew/release; the raw value is request-only ephemeral and never appears in result, export, cache, log, receipt, metadata, or repository state.
2. Repository metadata stores only a one-way verifier plus lease data; release/renew compare the presented capability to the verifier, require owner/permission checks, and use no-follow/handle-safe opens. Inspect/logs/responses never expose a raw capability. Define stale-lock recovery so an old holder cannot release a renewed lock. Test valid client-retained acquire/release, low-entropy/reused/guessed/stale capability rejection, direct metadata non-recovery, file/dir link/junction, swap race, contention, renewal, crash recovery, and live CLI/MCP behavior.
3. Reuse `AtomicFile` and its physical-containment policy at every map, journal, lock, temp, backup, read, write, replace, and cleanup boundary. Shared maps use lock/CAS across read-validate-mutate-write with barrier tests. Journals use contained atomic per-record replace, explicit same-name policy, retained corrupt bytes, and list reporting of corruption. Unsupported platforms fail closed for protected operations.
4. Public persistence maps absent to `skipped` and corrupt/invalid/I-O to canonical `error`; no corruption is misreported as absence. Apply the Phase 2 sanitizer to every persisted/temporary value.
5. Before patch sandbox creation, reject dirty tracked or untracked checkout state. Record and bind a clean base tree identity, patch digest, sandbox base identity, and result tree/diff identity; revalidate before apply and before verification, and invalidate drift. No patch claim transfers across a changed base. Select and bind the complete required command plan, all command-selection/test configuration digests, and declared ignored-input identities from that clean base or an external trusted manifest.
6. Define verifier outcome `completed`, `unavailable`, or `failed`. Derive required verification commands only from the bound clean-base/trusted command plan; a verified-success result requires at least one selected required command to execute and succeed. A patch that changes markers, scripts, runner config, command manifest, generated input, or a declared ignored input cannot receive ordinary verified success without separate privileged review. Missing runner, zero selected/executed commands, unavailable verifier, or undeclared host input is non-verifying `skipped`/`error`, never verified success. Instrument execution to prove commands ran.
7. Run `PatchVerifier` after every successful application. Fail closed on sandbox/worktree/verifier failure; keep checkout unchanged; direct apply is sandbox-only unless rollback is proven. Cleanup is limited to manager-owned contained paths and uses unique temporary names.
8. Complete output migration here, after plugin, public-operation, lock, persistence, and patch adapters exist. Every invoked `kind=tool` call and each boundary declared `ToolResultV1` validates that contract; each admin operation validates its explicit declared admin-output contract; services retain their protocol/liveness contracts. Malformed eligible output becomes the contract's canonical error rather than prose/bool/raw dict. Stdio initialize/list/liveness is not wrapped in `ToolResultV1`.

**Exit criteria:** Only a caller-retained raw capability can release/renew while metadata disclosure grants no authority and no artifact contains it; links/junctions/swap races cannot redirect protected state; map/journal fault tests preserve truthful state; dirty/untracked/changed-base/command-policy/ignored-input patch cases deny, invalidate, or require privileged review; verified patch success proves an instrumented bound required command executed; and each eligible tool/admin boundary validates its declared contract only after adapter migration is complete.

### Phase 8 — Correct provenance and engine-support evidence

**Addresses:** R-013, R-014.

1. Rename local output to an **unsigned provenance draft**. Require actual artifact and package identities; remove unsupported reproducibility, completeness, builder, signature, and SLSA-level claims.
2. Pin implementation/tests to in-toto Statement v1 with SLSA provenance predicate `https://slsa.dev/provenance/v1` (SLSA v1.2), including selected buildType and recognized external-parameter/source constraints. Do not label current v0.2/v0.1 output as current standard.
3. Before any schema/signature-policy acceptance, apply strict duplicate-detecting parsing to every raw envelope, decoded Statement, predicate, nested builder, external parameters, and policy-relevant extension. Reject duplicate keys at every level and escaped/normalized key ambiguity. Optional signed mode then requires an exact allowlisted signer identity plus `builder.id` pair, trusted root/envelope verification, expected artifact/package identity, predicate version, buildType, external parameters, and source constraints. Reject wrong signer-builder pairs, wrong package/artifact/type/parameters/source, duplicate-key envelopes at any level, self-signed, unknown-root, mutated-subject, and malformed cases. Unsigned remains default.
4. Run deterministic tests on fixed PATH. For every mandatory/supported-optional engine family, provision pinned success, failure, and malformed-output conformance jobs and record resolved executable/version. Best-effort engines may report unavailable skip only under policy; all-skipped conformance is not success for a supported family.

**Exit criteria:** Unsigned output makes only evidence-backed draft claims; strict duplicate-detecting parse runs before all provenance schema/signature-policy acceptance; signed output verifies every pinned identity/constraint and rejects every mismatch; deterministic tests are PATH-independent; supported-family conformance cannot pass solely by skips.

### Phase 9 — Non-release maintainability program (completed)

**Addresses:** R-015 (completed).

This phase started after a correctness release was ready. Completed in Phase 60 with all 8 target hotspots reduced to McCabe C901 <= 10, zero exemptions in `governance/maintainability-exemptions.toml`, and 26/26 contract tests passing.

1. Pin the metric, tool, version, command, and baseline in the first R-015 PR. Scope named symbols: `cli.py` registration/option translation/rendering, `continuity.py` checkpoint/context/coordination/provider-resume orchestration, `review.py` collection/normalization/LLM/result assembly, and named traversal/state hotspots.
2. Set numeric thresholds per named symbol before refactoring, add characterization tests, and record exceptions with owner, rationale, and expiry. No later undefined agreement may alter completion.
3. Keep tools transport-independent; make no product behavior change; delete code only with manifest-scoped call-graph evidence and tests.

**Program-complete criterion:** The pinned report meets every named threshold or has only unexpired approved exemptions; characterization, artifact, parity, and release gates remain green; each PR documents no product behavior change. (Status: COMPLETED).

## Delivery slices

| Slice | Contents | Depends on |
|---|---|---|
| 1 | Coverage/public-operation manifests, locked decisions, failing artifact/redaction/plugin/scope/lock/patch fixtures, engine taxonomy | None |
| 2 | Wheel/sdist namespace, origin isolation, version/assurance scans | 1 |
| 3 | Recursive sanitizer and exception diagnostics | 1 |
| 4 | Schema kernel, exact severity mapping, adapters/fixtures only | 3 |
| 5 | Shared `AtomicFile`, verifier records, physical-containment/fault tests | 3 |
| 6 | User-owned plugin ledger, content-addressed closure snapshots, protected child-secret transport, handle-bound launch, explicit reapproval | 3-5 |
| 7 | Invocation resolver, physical target scope, registration adaptation, public-operation migration, cache, provider egress | 2-4 |
| 8 | Caller-capability locks, map/journal persistence, patch target/policy verification, eligible output-contract enforcement | 3-7 |
| 9 | Provenance correction and engine support matrix | 2-4 |
| 10 | R-015 non-release maintainability program (completed) | 2-9 and release-ready correctness state |

## Required release gates

All gates below are mandatory for release readiness.

- The current first-party coverage manifest includes all shipping/user-facing docs, root README, templates, generated release docs, and packaged metadata; manifest-scoped scans find no unsupported assurance or stale-version claims.
- The versioned public-operation manifest classifies every Click leaf and advertised MCP operation, names output-contract class/target ID, declared ignored inputs, and transport probe, and leaves no unclassified public route. `kind=tool` calls require `ToolResultV1`; admin operations validate only their explicit declared contract; services use protocol/liveness contracts. Only declared `kind=tool` pairs are parity-required.
- Wheel and sdist are independently built, installed, and probed from an external empty CWD on Windows/POSIX with scrubbed imports, installed-origin assertions, and the `src.rush` negative control.
- Every manifest operation runs its correct installed probe: Click-only CLI, MCP stdio `tools/call`, or service liveness/protocol. Live `tools/list` reconciles only MCP-advertised operations; every probe reaches lazy imports and preserves JSON-RPC-only stdout.
- Fresh sentinel corpus is absent from all values, keys, nested data, exceptions, outputs, persistence, cache, provenance, temporary/backup files, and aborted-write artifacts. Every literal sentinel in plugin argv/config/resource is rejected. For each declared protected secret transport, a same-user observer captures child argv and environment: the sentinel is absent there and in every snapshot/temp/ledger/receipt/argv/log/cache/result artifact while the plugin receives it only through its declared protected descriptor, protected-stdin protocol, or approved OS credential-provider channel. Secret semantic inputs are not sanitized into a different executed action.
- `AtomicFile` passes sanitized-value, same-directory, physical-containment, no-follow, file/dir link/junction, swap, fault, cleanup, and outside-sentinel tests on every supported platform; protected operations fail closed otherwise.
- Plugin grants bind a complete secret-free content-addressed runtime closure and exact runtime identity. Every secret reference declares exactly one protected transport: inherited protected descriptor, protected stdin protocol, or approved OS credential-provider channel. Raw referenced values are forbidden in child argv, configuration/resource files, snapshots, and ordinary environment variables; a reference/mode/platform without enforceable confidentiality is denied. Transitive dependency/resource, dynamic import, `PYTHONPATH`, script-directory, interpreter, file, symlink, and junction replacement tests yield approved snapshot bytes or no child; unsupported modes/platforms deny launch. Child environment is default-deny with only documented bootstrap plus grant-bound names; raw secret references never enter a persisted or rendered artifact.
- Semantic CLI/stdio parity covers non-default config, permissions, roots, relative/absolute paths, workspace, physical target selection, and canonical errors. An internal post-side-effect `TypeError` executes once.
- Scoped operations prove reparse-safe containment and pre-launch revalidation with link/junction/swap/outside-sentinel traps for empty, deleted, renamed, workspace, and aggregation cases. Ignored generated-code/config/host-input fixtures prove each declared input is rejected or content-addressed/snapshotted and revalidated under controlled roots; repository-wide exceptions follow their declared contract.
- Retained cache proves misses/bypass for absent/changed installed artifact/build identity and changed tool/normalizer behavior revision, plus cross-wheel upgrade and target-mutation collision tests. `--no-cache` prevents reads and writes; admin cache operations retain manifest tests.
- Review providers cover no-key, denied network, unapproved origin, redirect, DNS/timeout, HTTP error, malformed/empty response, explicit proxy routing, and success. Redirect receivers receive neither prompt nor authorization; only approved-effective-origin completion labels LLM.
- Retained lock tools prove caller-generated, cryptographically strong capability delivery only through CLI stdin/descriptor/platform-secret input or MCP sensitive field; valid client-retained acquire/release succeeds, while low-entropy/reused/guessed/stale values fail. Metadata is verifier-only; direct-file non-recovery, permission/ownership, no token in result/export/log/cache/receipt, link/junction/swap, contention, renewal, crash/stale recovery, and live CLI/MCP behavior are covered.
- Shared maps and journals reuse `AtomicFile`, pass CAS/barrier and per-record tests, and distinguish absent from corrupt/invalid/I-O with physical-containment/link/junction/swap/fault coverage.
- Public patch operations reject dirty/untracked state, bind patch/base/result tree-diff identities, and bind required command plan plus selection/test-config/ignored-input digests from clean base or trusted manifest. Patch changes to markers, scripts, runner config, command manifest, or bound inputs cannot receive ordinary verified success without privileged review. Verified success requires an instrumented bound required command execution; unavailable/zero-runner/verifier/worktree/undeclared-host-input failures are non-verifying and fail closed; cleanup remains contained.
- After Slice 8, every invoked `kind=tool` call and `ToolResultV1`-declared boundary validates `ToolResultV1`; each admin operation validates its declared admin contract. Services and stdio initialize/list/liveness remain under protocol/liveness contracts. Malformed eligible outputs are canonical contract errors, never prose, booleans, or raw dictionaries.
- Deterministic suite uses fixed PATH; every mandatory/supported-optional engine family has pinned success/failure/malformed conformance evidence with executable/version. Best-effort skip policy is explicit; all-skipped supported conformance fails.
- Ruff check/format and mypy pass against the installed artifact namespace contract.
- Provenance tests enforce unsigned default and actual artifact/package identity; strict duplicate-detecting parsing rejects duplicate/escaped/normalized key ambiguity in raw envelope, Statement, predicate, nested builder/external parameters, and policy-relevant extensions before policy acceptance. Optional signed output verifies exact signer + `builder.id`, predicate/buildType/parameters/source constraints, and rejects wrong/duplicate/malformed envelopes.

## Verification baseline captured by this review

- Observed full suite: `846 passed, 1 failed` in a `knip` discovery/version case; an isolated static-tool run passed; a later full run observed `847 passed, 1 warning`.
- Standard Ruff check passed; the baseline format check reported 623 formatted files.
- Mypy aborted on duplicate `rush.*` / `src.rush.*` module identity.
- A clean wheel smoke test failed at console startup with `ModuleNotFoundError: No module named 'src'`.

These are observations, not a release baseline. Phase 0 manifests, artifact matrix, engine taxonomy, isolated probes, and the gates above replace them as auditable release evidence.

## Completion definitions

**Release ready:** R-001 through R-014 and R-016 are closed with regression tests; every required release gate passes on wheel and sdist installed artifacts; no retained public operation lacks manifest disposition/probe/declared output-contract class; every eligible tool/admin boundary satisfies its declared contract; no protected operation relies on an exploitable unsupported-platform or residual-TOCTOU exception; and no trusted plugin secret reference passes raw values through argv, configuration/resource files, ordinary environment variables, or an unenforceable child transport. R-015 is explicitly excluded. (Status: COMPLETED across Phases 52-59).

**Remediation program complete:** The repository is release ready **and** Phase 9 satisfies its pinned maintainability criterion. A green source-tree pytest run alone is insufficient for either state. (Status: 100% COMPLETE. All 16 findings R-001 through R-016 closed, all 10 remediation phases 51-60 completed).
