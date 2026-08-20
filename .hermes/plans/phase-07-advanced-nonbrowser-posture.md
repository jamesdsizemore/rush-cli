# Phase 07 — permissioned execution and adapter back-integration

> **Depends on:** Phases 00–06. **Hard exclusion:** browser process, DOM,
> visual comparison, browser E2E, Lighthouse, axe, Playwright, and DAST remain
> Phase 08 work. Network use is **not** an exclusion: it is user-controlled.

**Goal:** Turn Rush's existing dormant adapters and selected missing scanners
into truthful executable tools. A missing adapter must not stay non-executing
merely because one mode may use the network, download data, write a cache, build
an artifact, or take time. Those effects require explicit per-invocation user
consent and result evidence.

**Architecture:** Keep one `ToolFn` implementation shared by CLI and stdio MCP,
the existing `ENGINES` registry, `run_subprocess()` for bounded child processes,
and canonical `ToolResult`. Add a typed execution-permission request that is
denied by default, passed explicitly from CLI/MCP, checked before process
invocation, and recorded in result metadata. Do not bundle every scanner into
Rush's Python dependencies: users install the external engine they choose, while
Rush provides a tested adapter, discovery, safe argv, parser, and install hint.

## Corrected terminology and result contract

Every integration declares exactly one or more of these modes in catalog,
CLI/MCP docs, compatibility, and `metadata.execution`:

| Mode | Behavior | Required evidence |
|---|---|---|
| `executed` | Rush runs an installed engine and normalizes stdout/JSON/SARIF. | Engine/version if known, argv-safe mode, required/granted permissions, duration, normalized findings. |
| `imported` | Rush reads a user-supplied local report and does not run its producer. | Producer/version/path/checksum/timestamp when available, freshness and provenance. |
| `artifact` | Rush deliberately writes a contained user-requested artifact. | Explicit output path, overwrite decision, checksum/path, producer/version. |

A scanner returning normalized findings is useful executable evidence even when
it creates no durable report file. Never describe executed output as imported
report evidence, or vice versa.

## Permission contract — implement before every promotion

### Owned seams

- Modify: `src/rush/config.py`, `src/rush/tools/base.py`,
  `src/rush/tools/common.py`, `src/rush/catalog.py`, `src/rush/cli.py`,
  `src/rush/mcp.py`, `src/rush/tools/__init__.py`,
  `src/rush/capabilities.py`.
- Create: `src/rush/permissions.py`, `tests/test_permissions.py`,
  `tests/test_execution_metadata.py`.
- Update: `tests/test_cli_registry.py`, `tests/test_mcp.py`,
  `tests/test_phase00_contract.py`, `docs/safety/permissions.md`,
  `docs/reference/cli-reference.md`, `docs/reference/mcp-tool-reference.md`,
  `docs/reference/result-reference.md`, `docs/ENGINE_COMPATIBILITY.md`,
  `CHANGELOG.md`.

### Public interface

1. Add immutable `ExecutionPermissions` with defaults all `False`:
   `network`, `download`, `cache_write`, `build`, `slow`, and `artifact_write`.
   Browser permissions remain Phase 08-owned.
2. Add explicit CLI options for each relevant command rather than a hidden
   global bypass: `--allow-network`, `--allow-download`,
   `--allow-cache-write`, `--allow-build`, `--allow-slow`, and
   `--allow-artifact-write`. An explicit output path and `--overwrite` remain
   separate from permission.
3. Add the same optional boolean inputs to each MCP callable that supports the
   corresponding mode. Existing calls retain default-denied compatibility.
4. A discovered project `rush.toml` may describe tool arguments and policy
   preferences but cannot silently grant an elevated permission to an MCP/CLI
   invocation. Per-invocation caller consent is authoritative.
5. `run_engine()` receives the validated permission request plus a declared
   engine-mode policy. It returns `skipped` before spawning when permission is
   absent, naming the exact missing flag. It records requested/granted effects
   under `metadata.execution`; it must not rewrite an engine error as success.
6. `run_subprocess()` remains list-only, `shell=False`, `stdin=DEVNULL`,
   bounded/redacted, timeout-bounded, and does not install anything. Engine
   modes that would alter a cache/build/artifact get only their documented,
   consented argv/environment.

### RED→GREEN acceptance

For each permission independently, write and observe failing tests for:

- default denial without child-process invocation;
- CLI flag and MCP input forwarding to the one shared tool;
- project config being unable to escalate a missing caller grant;
- granted execution producing auditable metadata;
- unknown/irrelevant permission rejection;
- timeout, cancellation, malformed output, and redaction retaining canonical
  `error`/partial behavior.

Commit the permission foundation before promoting an engine.

## Back-integration tranche A — promote existing engine modules

The repository already has registered engine classes and tool routing for the
following candidates. Their current feasibility labels do **not** mean the code
is absent; they mean their invocation/parser/fixture/documentation proof is
incomplete. Promote one focused tool family at a time, preserving the shared
CLI/MCP implementation.

| Order | Tool family / existing engines | Execution boundary and promotion work |
|---|---|---|
| A1 | `lint`: Ruff, ESLint | Explicit local target; structured machine output; project config behavior documented per engine. No network permission is required merely to run a preinstalled binary. |
| A2 | `format`: Ruff format, Prettier | Read-only `--check` default. Any formatting write requires an explicit existing write-mode contract and separate user confirmation; no silent rewrite. |
| A3 | `test`: pytest, Vitest | Execute only the user-selected project test runner. `--allow-slow` gates long-running modes; preserve child stdin isolation and return test failures as findings/results. |
| A4 | `typecheck`: mypy, `tsc` | Local source/project config execution with deterministic machine/text parser fixtures and documented build/config side effects. |
| A5 | `dead`: Vulture, Knip | Local analysis, stable source selection, text/JSON parser fixtures, and missing-engine semantics. |
| A6 | `complexity`: Radon, jscpd | Local metrics/findings with deterministic ordering and fixture coverage. |
| A7 | `slop`: sloppylint plus existing JS fallback | Keep explainable deterministic rules; never infer authorship. |
| A8 | `templates`: djLint and `commit-msg`: commitlint | Add the missing complete CLI inputs (`--message` for commit messages) and fixture-backed normalization. |
| A9 | `sbom`: cdxgen | Make the explicit contained output path and overwrite decision public; return an `artifact` result plus normalized summary. Artifact creation requires `--allow-artifact-write`, not a hidden write. |

For **every A tranche**:

1. Research and store a compact local compatibility record under untracked
   `research/engines/`: official release/source, license, platform support,
   exact argv, output/exit mapping, config discovery, network/cache/build/write
   modes, and Windows behavior.
2. Write a focused fixture test that fails before maturity promotion: clean,
   findings, missing binary, malformed output, nonzero failure, timeout, unsafe
   flag/config attempt, and CLI/MCP parity as applicable.
3. Use fake `run_subprocess()` tests for argv/cwd/env/timeout/`DEVNULL`; do not
   require the external binary or network in CI. Add an optional local smoke
   marker only when a user has installed the engine.
4. Promote catalog maturity only after its deterministic parser/invocation test
   is registered in `PARSER_FIXTURE_SUITES`; update capability reasons,
   planner prerequisites, tool catalog, compatibility table, docs, and
   changelog in the same slice.
5. Start/end each tranche with scoped Git inspection, and commit only its owned
   files after focused and full regression gates.

## Back-integration tranche B — execute advanced evidence, not only import it

Keep importers, but add explicit execution modes without changing their meaning.
Each mode has its own permission and safe input contract:

| Capability | Candidate execution route | Required consent / non-goals |
|---|---|---|
| Coverage | coverage.py/pytest-cov and c8 | `--allow-slow`; return execution output and optionally import LCOV/Cobertura/JUnit separately. |
| Property / contract | Hypothesis/fast-check and Pact local command/report | `--allow-slow`; no provider publication, broker contact, or implicit test generation. |
| Mutation | mutmut / Stryker | `--allow-slow` and `--allow-build` when the selected engine needs a build; no baseline write. |
| Fuzz | Hypothesis/Atheris or a declared local fuzz command | `--allow-slow`; `--allow-network` only for an explicit user-owned target mode; time/case limits required. |
| Load | k6 / Locust | explicit target plus `--allow-network` for any target traffic; local-only target default, rate/duration/concurrency limits, no destructive scenario auto-discovery. |
| Flaky / snapshot | pytest rerun/local snapshot verifier | `--allow-slow`; compare-only default; baseline acceptance requires explicit artifact/write consent. |
| CodeQL | existing SARIF import plus optional declared local database/query workflow | `--allow-build` and any required `--allow-download`/`--allow-network`; no automatic database, pack, or dependency action. |

Each engine execution mode must return `metadata.execution.mode="executed"`;
each import retains `"imported"`. CLI/MCP must make the chosen mode explicit—no
path-only ambiguity and no inferred Git history.

## Back-integration tranche C — network-capable and artifact/security scanners

Network capability is a permission boundary, not an automatic rejection. Add
one scanner at a time after its official compatibility evidence and fixture
matrix are complete.

| Order | Scanner | Default / permissioned behavior |
|---|---|---|
| C1 | Semgrep | Local user-owned rules/config and JSON/SARIF output first. Remote registry/config fetch requires `--allow-network`; download/cache modes require their matching grants. |
| C2 | Lychee | Local file/anchor validation may run without network. External link checking requires `--allow-network`, bounded concurrency/rate/timeout, and redacted URLs/query data. |
| C3 | Trivy | Local filesystem/config and user-supplied OCI archive modes. DB refresh, image pull, or remote repository modes require the exact download/network/cache permissions and are disabled otherwise. |
| C4 | Syft and Grype | Generate/consume local SBOM/artifact evidence. SBOM writes require explicit output plus artifact-write consent; advisory database refresh requires download/network/cache consent. |
| C5 | Cosign | Verify user-supplied local artifact/attestation/bundle by default. Rekor/remote identity lookup requires network consent; no signing, key generation, upload, or publication. |
| C6 | kubeconform/KubeLinter and policy posture | Local manifest validation first; remote schema/CRD retrieval requires explicit network/download/cache grants; never apply/install a chart or start a cluster. |

For each C scanner, add a dedicated tool rather than overloading an unrelated
command, except where the result domain is already canonical (`security` may
aggregate dependency/vulnerability findings with preserved source provenance).
Do not add a scanner solely to list it: it must execute under its granted mode,
parse machine output, return normalized findings, and publish an accurate
maturity label.

## Documentation, compatibility, and audit repair

Before Phase 07 closes:

- Correct contradictory maturity claims in `docs/ENGINE_COMPATIBILITY.md`
  (including the stale YAML/SQL feasibility table) against catalog and tests.
- Replace “no network” as a reason for exclusion with the actual execution
  mode, required consent, possible effect, default behavior, and result
  evidence.
- Update `README.md`, `docs/TOOL_CATALOG.md`, `docs/ENGINES.md`, both CLI
  references, MCP references, result/configuration/permissions/privacy guides,
  troubleshooting, architecture, ADRs, and `CHANGELOG.md` for every promoted
  tool.
- Add a generated or fixture-tested support matrix that distinguishes: installed
  engine, executable mode available, missing consent, imported-only support,
  and artifact mode. Do not call a successful process “a report” unless it
  actually emits a durable user-requested artifact.
- Maintain `.hermes/implementation/phase-07-ledger.md` with each RED failure,
  compatibility decision, recovery, excluded mode, verification command, and
  per-tranche commit.

## Phase 07 final acceptance

- Every named A/B/C adapter is either a real executable/importer/artifact
  implementation with its full fixture contract, or has a documented concrete
  blocker tied to license, absent machine output, or uncontainable behavior—not
  merely network access.
- A user can grant network/download/cache/build/slow/artifact effects explicitly
  through CLI and MCP; absent consent never spawns the corresponding process.
- Every executed, imported, and artifact path has distinct result metadata and
  truthful docs.
- CLI and MCP call the same tool implementation; no transport duplicates logic.
- No implicit installation, package-manager invocation, publishing, history
  rewrite, baseline acceptance, or artifact overwrite occurs.
- Full project tests, formatter/linter, fixture-only integration coverage,
  Graft wiring check, context-mode reindex/query, documentation link check,
  staged diff review, and scoped Phase 07 commit pass.

**Rollback:** revert the isolated tranche commit. Preserve permission/result
contracts so another engine can be added without changing existing behavior.

---

# Phase 08 dependency handoff — browser/runtime remains last

Phase 08 begins only after Phase 07 accepts the reusable permission and evidence
model. Browser work owns `allow_browser`, explicit target/lifecycle policy, and
runtime artifacts; it inherits—not reimplements—network/download/cache/build,
slow, artifact-write, redaction, provenance, result-mode, CLI/MCP, and audit
contracts from Phase 07. It then implements Playwright, axe, Lighthouse, visual
comparison, browser E2E, and safe DAST one bounded adapter at a time.
