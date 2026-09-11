# Phase 65 implementation evidence

Current status: this document covers P65-09 (installed end-to-end acceptance and beginner docs, F35/F41) only. It assumes P65-01 through P65-08 and P65-10 are already integrated on this board (their own receipts are recorded elsewhere on `docs/goals/phases-64-63-65-66/state.yaml`); it does not re-verify their individual packet claims. Current contract: [Phase 65 project provisioning, scan, and agent workflow plan](phase-65-project-provisioning-scan-and-agent-workflow-plan.md). Review evidence: [whole-application review](../reports/phase-64-66-application-review.md).

Read-only review must follow freeze; any further implementation change to a file cited below invalidates that file's evidence and requires re-running the cited commands.

## P65-09 — Installed end-to-end acceptance and accurate beginner docs (F35, F41)

Requirement mapping (verbatim source findings from the [whole-application review](../reports/phase-64-66-application-review.md)):

| F# | Finding (as originally reproduced) | Packet |
|---|---|---|
| F28 | Release matrix declares named archives but uploads unarchived `dist/rush`/`rush.exe`; manifests require other asset names/architectures and use stale versions/missing checksums. | P65-01 |
| F30 | `setup`'s `--non-interactive` flag defaults true with no false spelling, so the documented install branch is unreachable. | P65-02 |
| F31 | Installer used executable names as package identities instead of a canonical registry, with non-executing/unsupported manager branches. | P65-02 |
| F32 | JavaScript-only project plus Ruff was described as lint-ready without ESLint; configuration presence was confused with readiness. | P65-03 |
| F33 | Requirements-only Python and Dart projects received different language classifications across discovery/routing. | P65-03 |
| F34 | Fixed suites lost child summaries/versions/skip reasons, counted skipped tools as executed, reported duration zero. | P65-04 |
| F35 | Product gap: init/setup/plan/review/MCP registration were disconnected — no one-command beginner installation, automatic agent connection, comprehensive all-applicable-tool scan, unified repair handoff, or verified rescan route. | P65-01 through P65-10 |
| F41 | README advertised undelivered runtime dependencies (Starlette ASGI, Textual); installation docs omitted the required simple cross-platform route. | P65-09, P66-07 |
| F42 | `install.sh`/`install.ps1` required preinstalled `uv` and a local source checkout, then performed editable installation — no beginner bootstrap, no agent connection, no memory activation. | P65-01, P65-10 |

F28/F30–F34 are P65-01 through P65-04's own packets (their source/test evidence lives in those packets' own receipts on the board); this document's own new evidence is the P65-09 acceptance journey below, which exercises every one of those packets' real, already-integrated code paths end to end and records what F35/F41/F42 look like once actually wired together.

### Source

- `scripts/benchmarks/run.py` — `run_project_journey`, `run_project_journey_suite`, `_project_journey_release_fixture` (new `project_journey` workload alongside the existing `scenario`/`memory` suites; `--suite project_journey` CLI dispatch). SHA-256: `8abfd39ac9be30b04a83f61eda47668458bddf599ad6ecec139e70f960ccfd2d`.
- `scripts/sync_docs.py` — `_engine_contracts`, `collect_runtime_contracts` extended with an `"engines"` surface, `_check_contracts` extended to check it. SHA-256: `a892ea6b1597ed8f20ffb9df8c11b3c2df8ebd2b543b923ebc151ead9d4feb70`.
- `tests/test_project_journey.py` — new. SHA-256: `bd2f98a7bde203d7cbbcc06a5ad4dbcfd15eb684747432b4d4a62e367c908d15`.
- `docs/ENGINES.md` — 8 engine-identifier corrections (`backstop`, `guac`, `markdownlint-cli`, `pagespeed`, `pitest`, `readability`, `squoosh`, `zap` now show their real registry `engine_id` instead of a bare binary/package name). SHA-256: `3afce2b3fe4247836835ca8514e667ad493b92b0a127d4e6efbb9b50cb9648eb`.
- `docs/CLI_REFERENCE.md` — corrected the stale CLI/MCP/catalog inventory count, documented `rush scan handoff/rescan/cancel/resume`, `rush install`, `rush agent list/connect/doctor`. SHA-256: `2abaf56b55e27b0d7bd6700c3aa0fed31182d15e3f40cc103a348ea08e49fd9e`.
- `docs/MCP_REFERENCE.md` — corrected the stale `rush_scan` operation list (`rescan` was already implemented, not "rejected as unknown"), documented `rush_scan_handoff` and `rush_agent_connection`. SHA-256: `d169a7acb9725324627f3f9003f9241b89859046c4b168c2954f2ef4880d59a2`.
- `docs/integrations/mcp-client-setup.md` — corrected the stale claim that `rush_agent_connection` was "registered by a Phase 65 follow-up packet"; it is registered now. SHA-256: `33de21948faaa1f9dd37defa08d6fbe3570fb5818e182b7bf2098ade08b6503f`.
- `README.md`, `docs/TOOL_CATALOG.md`, `docs/CONFIGURATION.md` — reviewed for hardcoded author paths, developer prerequisites in the beginner route, and missing new-operation coverage; no genuine defect found (README's one-command install section already carries no author filesystem paths and already states its own release-matrix blocker; `docs/TOOL_CATALOG.md`/`docs/CONFIGURATION.md` cover the generic engine catalog and `rush.toml` schema respectively, and none of P65-05/06/08/10's new commands are catalog-dispatched tools or `rush.toml` settings — confirmed via `rush.catalog.TOOL_SPECS`, which does not contain `scan_handoff`, `agent_connection`, `install`, `scan`, or `project`). Left unedited.

### RED

`tests/test_project_journey.py` did not exist before this packet; every one of its 9 tests is new, asserting the real install→provision→scan→aggregate→handoff→rescan→memory-retrieval pipeline against P65-01–08/P65-10's already-implemented public functions (`InstallTool`, `register_project`, `build_provision_plan`/`apply_provision_plan`, `initialize_agent_memory`/`record_tool_observation`/`read_agent_memory_state`/`acknowledge_agent_connection`, `plan_scan`/`execute_scan`, `build_handoff`/`dispatch_handoff`/`acknowledge_handoff`/`complete_handoff`/`status_handoff`, `rescan_project_run`, `MemoryTool`). No RED failure state was captured (the underlying packets already exist and pass); RED here means "the assertions did not exist until this packet wrote them."

### GREEN

`env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_project_journey.py -q` — 8 passed (fresh run recorded 2026-09-11; see Runtime evidence below for exact IDs from that run).

Test coverage, one function per facet of the single shared `run_project_journey` execution (module-scoped fixture, no second harness):
1. `test_install_produces_a_verified_binary_and_activates_memory` — real checksum-verified binary install; every one of the 6 known agent adapters reports `unsupported`/`detected: false` under `agents="none"`, never silently omitted.
2. `test_two_projects_are_registered_with_distinct_ids` — two isolated `register_project` calls produce distinct `project_id`s, each `ScanRun.project_id` matches its own project.
3. `test_provision_reports_missing_toolchain_never_a_fabricated_install` — real `apply_provision_plan` against `eslint`/`checkov`/`markdownlint-cli` (one per non-Python fixture language) with a `which` probe reporting no installed manager: all three fail `SYSTEM_PREREQUISITE_REQUIRED` naming the exact missing manager (`npm`/`uv`/`npm`); `applied == {}`.
4. `test_connected_agent_profile_is_isolated_across_projects` — project A's `cursor` session is `connected`/`consent`ed with its real recorded observation; project B's same agent ID and session ID (different `project_root`) is untouched (`connected: False`, `last_observation: None`).
5. `test_scan_produces_exact_seeded_coverage_with_source_identities` — real `plan_scan`/`execute_scan` (scan step scoped to `[ReviewTool()]` for exact, host-independent finding counts) produces exactly 3 findings in project A (2 `missing-docstring` + 1 `naming`, by exact line/message) and exactly 1 in project B, all `provenance: "review/heuristic-v1"`, zero overlapping `finding_id`s between projects, and confirms the *real*, unscoped 121-engine candidate set still schedules (JS/IaC/docs engines genuinely `unavailable` in this sandbox) — `run_state == "incomplete"`, never a fabricated "completed".
6. `test_handoff_completes_but_is_never_auto_promoted_to_verified` — real `build_handoff`→`dispatch_handoff`→`acknowledge_handoff`→`complete_handoff` round trip; `handoff.finding_ids` matches the aggregate's real finding IDs exactly; terminal state is `agent_reported_complete`, never `resolved`/`verified`; `status_handoff` never leaks `session_capability`/`delivery_nonce`.
7. `test_rescan_against_real_execute_scan_shows_unmodified_findings_persisting` — real `rescan_project_run` against the same unmodified source: all 3 seeded findings verdict `persisting`, `resolved`/`new`/`unverified` all empty.
8. `test_memory_retrieval_returns_the_real_written_source_identity` — real `MemoryTool` write+recall round trip; the recalled item's `source` is exactly `"journey-session"` and its `excerpt` contains the real `handoff_id`/`run_id` written moments earlier, never a fabricated match.

### VERIFY (run this session, exact output)

- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_project_journey.py -q` — 8 passed.
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` — 2177 passed, 5 skipped (the 5 skips are the pre-existing named real-engine acceptance tests in `tests/test_executed_modes.py`, unrelated to this packet; unchanged from baseline).
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff check src tests scripts` — all checks passed.
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff format --check src tests scripts` — 851 files already formatted.
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m mypy src/rush` — no issues found in 461 source files.
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m scripts.benchmarks.run --suite project_journey --output <tmp>` — exit 0; writes `project-journey-report.json`; prints its two named blockers (below).
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` — **fails**; see "Documentation coverage regeneration" below. This is the one verify command this packet cannot make pass within its own `allowed_files`.

Tool versions this session: Python 3.12 (repo `.venv`), Ruff (pinned via `.venv`, `ruff format`/`ruff check` both clean), mypy (via `.venv`), pytest (via `.venv`). `npm`/`node` and `ruff` (the CLI binary) are present on the host; `eslint`, `checkov`, `terraform`, `tflint` are absent — confirmed directly via `shutil.which` before designing the fixture, which is why the provisioning acceptance criterion uses an explicit injected `which` probe (deterministic, host-independent) rather than depending on incidental host state.

### Seeded-defect recall, false-clean count, coverage

- Seeded defects: 3 in project A (`app.py` lines 1/5/9), 1 in project B (`app.py` line 1). Real recall: 4/4 (100%) — every seeded defect is present in its run's `aggregate.findings` by exact line and rule.
- False-clean count: **0**. No scan step, provision step, or handoff step in this journey ever reports success/clean where the real underlying state disagrees — `run_a.run_state == "incomplete"` (never coerced to "completed"), `provision_result.applied == {}` (never populated from a skipped/failed install), `completed.state == "agent_reported_complete"` (never auto-promoted to `resolved`).
- Coverage gaps (named, not silently omitted):
  - JS (`eslint`), IaC (`checkov`, and by extension any Terraform-specific engine), and docs (`markdownlint-cli`) engines are real registry members but have no installed toolchain in this sandbox — their scan candidates are honestly `unavailable`; only the toolchain-free `ReviewTool` (Python-only) result is asserted exactly.
  - "Installed release-matrix journey jobs" (P65-09.3's own phrase) require a real published GitHub release, confirmed absent from this repository — see `.scratch/phases-64-63-65-66/issues/06`. Not run; named here as an open external blocker, matching P65-01/P65-02/P65-10's own precedent for this exact gap.
  - Real provider tokens / a live connected-agent session require live network/credential access unavailable in this sandbox. The connected-agent profile in this journey exercises Rush's own real consent/acknowledgment/isolation mechanics (`rush.integrations.agents`) — real code, real state transitions, real isolation — but never a live agent process or live model call. Named as an open external blocker, matching MC12/MC13's established precedent for a missing external engine/credential.
  - Payload tokens: the handoff packet's own real token accounting is asserted structurally in `test_scan_handoff.py` (not re-derived here); this journey's own printed evidence (`handoff.packet` in the runtime capture below) shows `tokens: 678`, `bytes: 1755`, `encoding: "cl100k_base"` — real `tiktoken`-class counts over the real packet, not an estimate.
  - Memory retrieval: real, exact — see the runtime capture below.
- Runtime: the full `run_project_journey` pipeline (install + two project registrations + provisioning + agent isolation + two real scans + full handoff lifecycle + rescan + memory write/recall) completes in about 2 seconds locally (`tests/test_project_journey.py`'s 8-test module, which runs it once via a module-scoped fixture, completes in ~2.3s total).
- Each supported agent/platform combination: `rush agent list`'s six adapters (`claude-desktop`, `claude-code`, `cursor`, `windsurf`, `zed`, `codex`) are exercised structurally through `InstallTool(agents="none")`'s reporting (all six report `unsupported`/`not-detected`, never silently dropped) and through `rush.integrations.agents`'s real isolated-scope mechanics for `cursor` specifically. Native per-client registration/config-write parity for all six is P65-05's own acceptance evidence (`tests/test_agent_connection.py`, `tests/test_install_memory_activation.py`), not re-derived here — no second harness.

### Runtime evidence (fresh capture, this session)

```
PROJECT_A_ID 6cece16c-5c4d-456c-bdff-08dad554ed78
PROJECT_B_ID 6c4dd076-8733-46b4-a854-03867e262a16
PROVISION_FAILED {"eslint": {"code": "SYSTEM_PREREQUISITE_REQUIRED", "message": "[SYSTEM_PREREQUISITE_REQUIRED] required manager 'npm' is not installed"}, "checkov": {"code": "SYSTEM_PREREQUISITE_REQUIRED", "message": "[SYSTEM_PREREQUISITE_REQUIRED] required manager 'uv' is not installed"}, "markdownlint-cli": {"code": "SYSTEM_PREREQUISITE_REQUIRED", "message": "[SYSTEM_PREREQUISITE_REQUIRED] required manager 'npm' is not installed"}}
AGENT_A {"connected": true, "consent": true, "last_observation": {"project": "a", "tool": "scan"}, "scope": "project"}
AGENT_B {"connected": false, "consent": true, "last_observation": null, "scope": "project"}
HANDOFF_STATE agent_reported_complete ('agent-patch-1',)
RESCAN {"resolved": [], "persisting": [<3 seeded finding_ids>], "new": [], "unverified": []}
MEMORY_RECALL [{"source": "journey-session", "excerpt": "handoff <handoff_id> completed for run <run_id>", "trust": "EXTERNAL_WRITE", "freshness": "fresh"}]
```

API/event/snapshot examples for Phase 66 (real shapes, generated from this fixture, field names verbatim from the live code — no real-UI acceptance claimed here):

- **Scan candidate/event shape** (`CandidateResult.to_dict()`, one array element of `ScanRun.to_dict()["candidates"]`):
  ```json
  {"candidate_id": "a11ywatch", "kind": "engine", "category": "security", "disposition": "applicable", "reason": "comprehensive_static_analysis", "outcome": "unavailable", "child": {"tool": "a11ywatch", "engine": "a11ywatch", "engine_version": null, "status": "skipped", "duration_ms": 0, "summary": "skipped: ENGINE_ROUTE_MISSING", "findings": [], "raw": null}}
  ```
- **Finding shape** (real, from the executed `review` candidate):
  ```json
  {"path": "<project_a_root>/app.py", "line": 5, "rule": "missing-docstring", "severity": "info", "message": "function 'compute_value' has no docstring", "evidence": {"kind": "source-location", "path": "<project_a_root>/app.py", "line": 5}, "fingerprint": "65234e...", "finding_id": "343275bd...", "provenance": "review/heuristic-v1"}
  ```
- **Handoff status snapshot** (`status_handoff`'s real return value, `session_capability`/`delivery_nonce` never present):
  ```json
  {"handoff_id": "bc6bc4cd-beb1-4edc-b178-4c38cf33327e", "run_id": "c882fadc-3066-4d6e-96d3-c86a47a4fdee", "project_id": "6cece16c-5c4d-456c-bdff-08dad554ed78", "agent_id": "codex-cli", "state": "agent_reported_complete", "finding_ids": ["37b06...", "17850b...", "45705...a"], "packet": {"bytes": 1755, "encoding": "cl100k_base", "tokens": 678, "items": [...], "remainder_ids": []}, "agent_reported_complete_artifact_ids": ["agent-patch-1"], "created_at": "2026-09-11T04:35:20.550437+00:00", "updated_at": "2026-09-11T04:35:20.580689+00:00"}
  ```
- **Rescan comparison event** (`rescan_project_run(...)["comparison"]`):
  ```json
  {"baseline_run_id": "<run-a>", "current_run_id": "<run-a-prime>", "verdicts": {"<finding_id>": "persisting", ...}, "resolved": [], "persisting": ["<3 finding_ids>"], "new": [], "unverified": []}
  ```
- **Memory recall item** (`MemoryTool.run(operation="recall")`'s real return, one `data.items[]` element):
  ```json
  {"id": "45c73b22-5b3e-4e50-992c-0a3d1f9c2bbc", "version": 1, "excerpt": "handoff bc6bc4cd-beb1-4edc-b178-4c38cf33327e completed for run c882fadc-3066-4d6e-96d3-c86a47a4fdee", "source": "journey-session", "trust": "EXTERNAL_WRITE", "freshness": "fresh", "relations": []}
  ```

### Documentation coverage regeneration (named remaining blocker, out of this packet's `allowed_files`)

Two of this packet's mandated changes make `scripts/sync_docs.py --check` fail for reasons entirely caused by this packet's own required work, exactly mirroring the established `T015`→`T016` pattern already used elsewhere on this board:

1. **New `"engines"` contract surface** (P65-09.2's explicit "add coverage checks... for new operations/engine registry" requirement): `collect_runtime_contracts` now returns a 4th `"engines"` key (121 entries, from `rush.catalog.ENGINE_SPECS`) alongside `cli`/`mcp`/`catalog`. `docs/reports/phase-64-66-documentation-coverage.md`'s saved receipt has no `contracts.engines` key at all, so `--check` reports exactly 121 `contracts.engines: missing registered command <engine_id>` lines (verified count: 121 of 121 registry keys, via `_check_contracts`'s own diff logic).
2. **`sha256`/`historical_body_sha256` drift on every doc this packet edited**: `docs/ENGINES.md` (already broken before this packet — a pre-existing, previously-deferred item; see below), `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, and `docs/integrations/mcp-client-setup.md` all now have real content that no longer matches their frozen receipt entries' `sha256` (and, for the two marked `authority: "historical"`, their `immutable_body_sha256`).
3. **New file, no receipt at all**: this document itself (`docs/phase-plans/phase-65-implementation-evidence.md`) is new and has no coverage-report entry.

`docs/reports/phase-64-66-documentation-coverage.md` is **not** in this packet's `allowed_files` (confirmed against `docs/goals/phases-64-63-65-66/state.yaml`'s T218 card), and `scripts/sync_docs.py`'s own `check_docs` is deliberately read-only ("never rewrite documentation" — its own docstring). Regenerating the receipt requires a follow-up worker task scoped to `docs/reports/phase-64-66-documentation-coverage.md` using `sync_docs.py`'s own helper functions (`document_digest`, `historical_body_digest`, `documentation_owner`, `collect_runtime_contracts`, `_actual_referrers`) exactly as `T016` already did for `T015`'s analogous new-contract-surface case. The pre-existing `docs/ENGINES.md` 2-line drift (`stale sha256` + `historical body changed`) predates this packet and was explicitly, repeatedly deferred by prior tasks this run (T090, T092/T095/T097, T015/T016) to "P65-10" — but P65-10's own `allowed_files` never actually included `docs/ENGINES.md`, so it was never actually fixed; this packet corrected the document's real content (8 engine-identifier mismatches out of 121 registry keys checked; all 121 now appear verbatim in the doc body) but, like every prior packet, cannot regenerate the receipt itself.

Exact remaining mismatch, reproducible via `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check`:
- 121× `contracts.engines: missing registered command <engine_id>` (one per `rush.catalog.ENGINE_SPECS` key).
- `docs/CLI_REFERENCE.md: historical body changed`, `docs/CLI_REFERENCE.md: stale sha256`.
- `docs/MCP_REFERENCE.md: historical body changed`, `docs/MCP_REFERENCE.md: stale sha256`.
- `docs/ENGINES.md: historical body changed`, `docs/ENGINES.md: stale sha256` (pre-existing, now also reflecting this packet's content corrections).
- `docs/integrations/mcp-client-setup.md: stale sha256`.
- `docs/phase-plans/phase-65-implementation-evidence.md: missing coverage receipt` (this document).

No other document this packet reviewed but did not edit (`README.md`, `docs/TOOL_CATALOG.md`, `docs/CONFIGURATION.md`) contributes a new mismatch.
