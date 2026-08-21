# Phase 07–08 coding-agent handoff

> **Status:** implementation handoff; production work has not started.  
> **Target:** a coding agent completing Rush after Phase 06.  
> **Read this first:** this page, `AGENTS.md`, then the two active phase plans.

Rush is at version **0.1.0**. It is a Python 3.12 developer tool: a local CLI and
**stdio-only** MCP server that presents one consistent app-review surface over
specialized external engines. Its target user is a developer or coding agent
that needs actionable evidence across code quality, security, dependency and
artifact posture, tests, repository/workflow configuration, and—last—browser
runtime quality.

It is not a wrapper that merely lists installed tools, and it is not a
report-import product. It must execute selected installed engines when the user
authorizes their declared effects, normalize their output into the canonical
result shape, and optionally import existing evidence or create a deliberately
requested artifact.

## 1. Non-negotiable correction: network is a permission, not a rejection

Do **not** reject an engine or dependency merely because a useful mode needs the
network. The corrected product rule is:

> Rush defaults to bounded, transparent, denied-by-default effects. A user may
> explicitly authorize network, download, cache write, build, slow execution,
> or artifact writing for a particular CLI/MCP invocation. The result records
> what was requested and granted.

This does **not** permit hidden effects. Rush still must not implicitly install
a package, run `npx`, invoke a package manager, pull a container/browser runtime,
rewrite source, accept a baseline, overwrite an artifact, publish, tag, upload,
or rewrite Git history. Those require separately implemented and explicit user
controls.

A discovered project `rush.toml` is not a sufficient grant for an elevated
operation: the invoking CLI/MCP caller must grant it. This protects agents from
untrusted project configuration while retaining the user's choice.

### Evidence vocabulary

Use these terms precisely in code, results, docs, and user messages:

| Mode | Meaning |
|---|---|
| `executed` | Rush ran an installed engine and normalized its stdout/JSON/SARIF into findings/results. It may return useful results without writing a report file. |
| `imported` | Rush read a supplied local report; it did not run the report producer. |
| `artifact` | Rush deliberately created a user-requested contained file, with explicit output and overwrite controls. |

All three return the canonical `ToolResult`; only their provenance/effect differs.
Never call executed scanner output an imported report, and never market an
importer as a live scanner.

## 2. Current state and completed delivery

### Completed phases

| Phase | Delivered outcome | Commit |
|---|---|---|
| 04 | Non-browser test-reliability evidence/import contracts, documentation, and ledger. | `117dc62 docs: complete phase 04 reliability evidence` |
| 05 | Contained CodeQL SARIF 2.1.0 importer; it imports supplied local evidence only. | `b8e3b66 feat: add contained CodeQL SARIF importer` |
| 06 | Finding fingerprinting, aggregation provenance/partial evidence, in-memory baseline freshness, capability planning, explicit review scope, governance docs. | `33ce115 feat: complete phase 06 review governance` |

Phase 06's broad pre-commit gate passed **208 passed, 7 skipped**. The optional
skips were unavailable external static engines, not successful integrations.
A post-commit affected CLI/MCP regression passed **24 tests**.

### Current worktree and protected material

- Branch: `main`.
- The active Phase 07 and Phase 08 plans are intentionally **untracked**:
  `.hermes/plans/phase-07-advanced-nonbrowser-posture.md` and
  `.hermes/plans/phase-08-browser-evidence-last.md`.
- `research/` is local, untracked evidence. Never stage it. It contains useful
  engine records and historical/rejected roadmaps; it is research input, not an
  implementation authority.
- Preserve unrelated user work. Start every phase by inspecting Git and record
  the exact protected paths before staging anything.
- No credentials, tokens, passwords, or connection strings are retained. Never
  read or print environment/credential files merely to discover an integration.

### Active planning authority and conflicts

Read in this order:

1. `AGENTS.md` — repository contract and exact Windows verification commands.
2. This handoff.
3. `.hermes/plans/phase-07-advanced-nonbrowser-posture.md` — current Phase 07
   implementation contract.
4. `.hermes/plans/phase-08-browser-evidence-last.md` — current browser-last
   Phase 08 contract.
5. `.hermes/plans/master-build-plan-remediation.md` — historical program-wide
   gates, data contracts, and test topology.
6. Current source, tests, generated CLI help, and current docs — the authority
   for present behavior.

The master plan contains older “local-only/no network” language. Do **not** use
that language to override the revised Phase 07/08 permission model. Retain its
truthfulness, containment, fixture, registry, and verification requirements;
replace a blanket network denial with explicit, audited consent.

## 3. Repository map and contracts

| Location | Purpose | Agent guidance |
|---|---|---|
| `src/rush/tools/base.py` | `ToolFn`, `ToolResult`, `Finding` public contracts. | Extend compatibly; required result keys stay stable. |
| `src/rush/tools/__init__.py` | `ALL_TOOLS`, the only executable tool registry. | Register a tool once; CLI and MCP must share it. |
| `src/rush/catalog.py` | `TOOL_SPECS`, `ENGINE_SPECS`, maturities, fixture parity metadata. | Catalog labels are product claims; update only with proof. |
| `src/rush/cli.py` | Click command generation and result rendering. | Transport only; do not reimplement tool logic. |
| `src/rush/mcp.py` | FastMCP stdio registration. | Keep stdout JSON-RPC-only; MCP schemas must mirror CLI capability. |
| `src/rush/config.py` | nearest-`rush.toml` discovery and typed config. | It stops at Git root; add permission policy without allowing config escalation. |
| `src/rush/tools/common.py` | local binary resolution, `run_subprocess()`, `run_engine()`, result/error helpers, redaction. | The single bounded subprocess path: argv list, `shell=False`, `stdin=DEVNULL`, timeout, bounded/redacted capture. |
| `src/rush/engines/` | engine adapters and `ENGINES` registry. | Existing dormant engines are implementation starting points, not proof of support. |
| `src/rush/tools/routing.py` | language routing, deterministic aggregation, fingerprints, provenance/freshness. | Preserve ordering, provenance, partial/error behavior; do not silently clean a partial review. |
| `src/rush/capabilities.py` | installed/configured/applicable/blocked planning view. | Capability detection is read-only; no execution/version probing. |
| `tests/fixtures/engine_reports/` | native parser fixture corpus. | Add clean/findings/malformed/error fixtures for every real adapter. |
| `tests/` | unit, adapter, routing, catalog, CLI, MCP, contract coverage. | Maintain CLI/MCP/catalog parity and fixture-first tests. |
| `docs/` | user, reference, contributor, safety, architecture, maintainer documentation. | Update the relevant audience pages in the same slice. |

Canonical result statuses are `ok`, `warn`, `fail`, `error`, and `skipped`.
`skipped` means deterministic non-execution; it is not a successful scan.
`error` means invocation/parsing/internal failure; never turn it into a clean
result. Findings have stable deterministic SHA-256 fingerprints where available
and secret-sensitive values must be redacted as `[REDACTED]`.

## 4. Present product surface: real, dormant, importer-only, and missing

The catalog has 33 visible tools. Inspect `docs/TOOL_CATALOG.md` and
`src/rush/catalog.py` before changing a maturity label.

### Real adapters today

- deterministic local `review` (optional explicit Graft context; LLM is a
  no-provider-call stub);
- `security`: pip-audit, npm audit, offline OSV-Scanner routing;
- `secrets`: Gitleaks;
- `markdown`: markdownlint-cli;
- `actions`: actionlint;
- `yaml`: Spectral with owned rules/remote-reference blocking;
- `sql`: SQLFluff with owned config;
- `containerfile`: Hadolint;
- `iac`: TFLint plus contained Checkov;
- `ci` and dry-run local `release` workflow inspection.

### Existing but feasibility-gated code to back-integrate in Phase 07

Ruff, ESLint, Ruff format, Prettier, pytest, Vitest, mypy, tsc, Vulture, Knip,
Radon, jscpd, sloppylint, djLint, commitlint, and cdxgen already have engine or
tool implementation seams. Their current label means that deterministic
invocation/parser/permission/CLI-MCP/doc proof is incomplete—not that their
usefulness is denied.

### Importers that need explicit execution modes as appropriate

Coverage, mutation, PBT, flaky, contract, snapshot, fuzz, load, and CodeQL
currently consume explicit local reports. They must retain that importer mode
and add independently truthful `executed` mode only when its engine contract is
implemented. In particular, current CodeQL **does not execute CodeQL**; it only
imports contained SARIF 2.1.0.

### New Phase 07 candidates

Semgrep, Lychee, Trivy, Syft, Grype, Cosign, kubeconform, and KubeLinter are the
named non-browser candidates. They are not “supported” until each has official
compatibility evidence, a bounded invocation, permission mapping, parser,
fixtures, CLI/MCP/catalog parity, and docs. Their network, download, cache,
image, remote-schema, Rekor, or artifact modes are permissioned—not automatic
disqualifiers.

### Phase 08 only

Playwright, axe, Lighthouse, pixel comparison, accessibility/keyboard/responsive
checks, browser E2E, DOM readiness/anti-slop, Nuclei, and ZAP remain browser
runtime work. Do not move browser dependencies into Phase 07.

## 5. Current backlog and known defects

Treat `docs/KNOWN_ISSUES.md` and `docs/LIMITATIONS.md` as user-visible backlog:

1. Guarded tools name consent flags, but generic generated CLI commands do not
   expose them.
2. `commit-msg` has no CLI message input.
3. `sbom` lacks public output-path/overwrite controls despite contained internal
   behavior.
4. Release publication controls are intentionally absent.
5. `review --llm` is a deterministic stub; no provider call exists.
6. Parsed `review.fail_on`, project path lists, and generic `check` are not
   universally enforced.
7. The human format renderer has a replacement glyph; JSON is unaffected.
8. External-engine behavior remains environment-dependent; Windows lacks a full
   CI matrix.
9. `skipped` exits zero, so automation must inspect JSON if a scan is mandatory.

There is a documentation defect to repair in Phase 07:
`docs/ENGINE_COMPATIBILITY.md` correctly marks YAML/SQL as real in the current
truth-audit table, but an older Phase 02 section still calls them
feasibility-gated. Catalog, tests, compatibility docs, and user references must
agree.

## 6. Phase 07: required delivery sequence

The detailed executable plan is
`.hermes/plans/phase-07-advanced-nonbrowser-posture.md`. Do not collapse it into
a bulk refactor. Use these commits/slices in order.

### 07.0 — foundation before engine promotion

Create `ExecutionPermissions` and carry it through config validation, shared
tool execution, CLI, MCP, capabilities, result metadata, and docs. Default all
permissions to false:

- network
- download
- cache write
- build
- slow execution
- artifact write

Add explicit CLI flags and matching MCP inputs. A missing grant must return a
structured `skipped` result **without spawning a child**. A granted operation
records requested/granted effects, execution mode, and any declared artifact in
metadata. Keep browser permission ownership in Phase 08.

Required focused tests include default denial, no child spawn, CLI/MCP forwarding,
non-escalation by project config, valid granted metadata, unknown/irrelevant
permission rejection, timeout/cancellation, malformed output, and redaction.

### 07.A — promote existing adapters by focused family

1. `lint`: Ruff, ESLint.
2. `format`: Ruff format, Prettier; check-only/read-only is default and write
   behavior must be separately explicit.
3. `test`: pytest, Vitest; long-running modes require `--allow-slow`.
4. `typecheck`: mypy, tsc.
5. `dead`: Vulture, Knip.
6. `complexity`: Radon, jscpd.
7. `slop`: sloppylint plus explainable deterministic fallback.
8. `templates`: djLint; `commit-msg`: commitlint with a real `--message` input.
9. `sbom`: cdxgen with explicit contained output and overwrite behavior.

Every slice follows RED → smallest implementation → GREEN → docs → self review
→ independent spec and security review → repair/re-review → scoped Git commit.
A registered engine class is insufficient proof; add clean/findings/malformed,
missing binary, nonzero error, timeout, unsafe/config rejection, and CLI/MCP
parity tests. Use fake subprocesses in CI; optional real-engine smoke tests are
marker-gated and not the sole evidence.

### 07.B — add executed modes to advanced evidence

Keep current report importers intact, then add explicit execution modes for:
coverage, property/contract tests, mutation, fuzz, load, flaky/snapshot
verification, and an optional declared CodeQL database/query workflow. Each
mode must declare whether it needs slow/build/network/download/artifact consent;
no tool may infer a target, write a baseline, publish a contract, or contact a
provider/broker without the matching explicit path and permission.

### 07.C — network-capable/security/artifact posture

Implement Semgrep, Lychee, Trivy, Syft/Grype, Cosign, and Kubernetes/policy
adapters one at a time. Examples of the required framing:

- Semgrep may run local owned rules without network; remote rules/config need
  network permission, and registry/cache behavior needs its matching grant.
- Lychee may validate local anchors; external links require bounded network
  consent and must redact sensitive query data.
- Trivy's local filesystem/archive modes differ from DB refresh, image pull,
  and remote repository modes; each effect must be gated independently.
- Syft/Grype may work over local artifacts; SBOM writing requires explicit output
  and artifact-write consent; advisory refresh needs download/network/cache.
- Cosign local-bundle verification differs from Rekor lookup; no signing, key
  generation, upload, or publication is in scope.
- kubeconform/KubeLinter may validate local manifests; remote schema/CRD lookup
  needs consent. Never apply resources, install a chart, or start a cluster.

For every engine, first record official version/license/platform/argv/output/exit
and effect evidence under `research/engine-records/` without staging it. Network
permission is not a reason to skip research or implementation.

### Phase 07 close criteria

Every named adapter is either a working executable/importer/artifact mode with
its complete fixture matrix or has a concrete, documented blocker such as an
uncontainable side effect, licensing problem, or lack of machine-readable output.
“Requires network” is not an acceptable blocker. Update the phase ledger,
compatibility/catalog/capability/docs, run all gates, stage only owned files, and
create the scoped Phase 07 commit.

## 7. Phase 08: browser evidence comes last

Read `.hermes/plans/phase-08-browser-evidence-last.md` in full. Start only after
Phase 07 acceptance and a new explicit user approval.

Phase 08 reuses Phase 07's network/download/cache/build/slow/artifact evidence
model. It owns browser-specific consent, explicit target containment, controlled
local lifecycle, sanitized runtime artifacts, and read-only default journeys.

Delivery order:

1. Browser target/lifecycle/artifact/redaction policy and tests before an engine.
2. Playwright runtime evidence.
3. axe accessibility plus keyboard/focus/landmark/contrast/responsive checks.
4. visual comparison, Lighthouse, and explainable DOM readiness policy.
5. bounded browser E2E journeys.
6. safe DAST through Nuclei/ZAP.
7. catalog/capability/CLI/MCP/documentation and privacy/security review.

A target is explicit (`--url` or declared lifecycle command), allowlisted, and
local by default. Non-local traffic requires explicit network consent. No
credential transmission, destructive discovery, auth scanning, exploit template,
or automatic browser/package install is permitted. Local targets can still be
useful; the user may authorize broader behavior explicitly and the result must
show that authorization.

## 8. Documentation and research reading map

Read/update these pages as their subject changes:

- Product behavior: `README.md`, `docs/README.md`.
- Contract and architecture: `docs/ARCHITECTURE.md`,
  `docs/developer/architecture.md`, `docs/adr/0002-normalized-finding-and-evidence-model.md`,
  `docs/maintainers/scanner-governance.md`.
- Tool truth: `docs/TOOL_CATALOG.md`, `docs/ENGINE_COMPATIBILITY.md`,
  `docs/reference/engine-directory.md`, `docs/reference/compatibility.md`.
- User interfaces: `docs/reference/cli-reference.md`,
  `docs/CLI_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`,
  `docs/MCP.md`, `docs/reference/result-reference.md`.
- Configuration/permissions: `docs/reference/configuration-reference.md`,
  `docs/reference/configuration-cookbook.md`, `docs/safety/permissions.md`,
  `docs/safety/security-model.md`, `docs/safety/privacy-and-data-handling.md`.
- Contributor workflow: `docs/DEVELOPER_GUIDE.md`,
  `docs/developer/tool-development.md`, `docs/developer/engine-development.md`,
  `docs/developer/routing-development.md`, `docs/developer/testing-guide.md`,
  `docs/developer/ci-and-packaging.md`.
- Backlog: `docs/KNOWN_ISSUES.md`, `docs/LIMITATIONS.md`, `CHANGELOG.md`.
- Local evidence: `research/engine-records/phase-00-02-baselines.md` and
  `research/engine-records/phase-02-iac-evidence-status.md`. Historical
  `research/rejected/` files are context only; do not revive rejected rules
  without comparing them to the active Phase 07/08 plans.

Documentation must distinguish user guidance from contributor internals. A
maturity table alone is not enough: for each promoted tool, document install,
detection, consented effects, expected result, skipped/error diagnosis,
platform constraints, and a safe example.

## 9. Required development protocol

### Before each phase and slice

1. Run `rtk git status --short`, `rtk git status -sb`, and `rtk git log -3
   --oneline`; preserve unrelated work.
2. Use **Graft** to locate the exact tool/catalog/config/engine/CLI/MCP/test/docs
   seam and run `graft --dir .hermes/graft check .` after wiring changes.
3. Use **context-mode** only on the discovered contract paths and query the
   permissions/result/adapter seam.
4. Use **RTK** for exact source/document reads and diffs. Do not use broad raw
   reads when RTK can provide a bounded read/search.
5. Research the engine's official contract before implementing its invocation.
6. Start with a focused failing test. Do not start from a catalog-label edit.

### Project commands on this Windows host

Use the project interpreter; do not rely on Hermes's ambient Python:

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
.venv/Scripts/rush.exe --help
```

`python -m rush` is invalid because this package has no `rush.__main__`.
Use `.venv/Scripts/rush.exe` or the installed `rush` entry point.

### Before every commit

- Run focused tests, then the full suite/ruff/format gates above.
- Validate Markdown links locally, including this handoff if it changes.
- Run `git diff --check`, RTK scoped diff/stat, Graft check, and a context-mode
  reindex/query for the changed seams.
- Stage only owned source/tests/docs/ledger files. Do not stage `research/`,
  unrelated plans, secrets, generated artifacts, or unrelated worktree changes.
- Perform a self review plus independent specification and security/quality
  reviews; fix verified findings and rerun the gates.
- Commit a completed phase only after its acceptance criteria pass. Do not push,
  merge, tag, or release unless the user explicitly asks.

## 10. First concrete action for the next agent

Begin **Phase 07.0**, not a scanner. Inspect Git; locate `ToolResult`,
`run_engine`, config parsing, generated Click commands, MCP registration,
capabilities, and current permission placeholders; then write a failing test for
default denial/no-process-spawn. Build the reusable permission/evidence contract
first. It is the prerequisite that makes the remaining integrations both useful
and user-controlled.
