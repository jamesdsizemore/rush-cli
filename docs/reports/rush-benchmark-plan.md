# Rush benchmark harness implementation plan

Status: executable development plan for a benchmark harness. It creates benchmark code and deterministic tests under `scripts/benchmarks/` and `tests/`; it does not alter product behavior in `src/rush/`, register a CLI/MCP tool, add dependencies, or modify `rush.toml`.

## 1. Outcome and non-negotiable completion criteria

The deliverable is a runnable, reproducible benchmark harness—not a list of benchmark ideas.

| Outcome | Concrete completion criterion |
|---|---|
| Runnable harness | `.venv/Scripts/python.exe -m scripts.benchmarks.run --scenario <id> --output <dir>` loads one fixture, executes only its declared probe, and writes one schema-valid result JSON. |
| Deterministic CI proof | `.venv/Scripts/python.exe -m pytest tests/test_benchmark_*.py -q` passes without network, credentials, model downloads, external CLIs, or a daemon. |
| Provider/OAuth/CLI proof | Each named provider has a fixture-mode result. A live result is possible only when the user explicitly selects one pre-authenticated route; no credential value reaches source, fixture, result, or log. |
| 9Router and OmniRouter | Independent route descriptors, evidence records, and tests exist; a shared generic-router descriptor fails validation. |
| Token reduction | The harness invokes `rush.codegraph.context_packer.ContextPacker` and records raw/control/packed token counts at 2k, 8k, and 16k. A pass requires >=50% median input-token reduction and zero loss of declared required facts. |
| Consumer hardware | Final phase writes a measured `hardware-profile.json`, source register, and local result for each available profile; unavailable profiles are `deferred`, never fabricated. |
| Handoff | `final-handoff.md` links every decision record to fixture IDs, test command, result JSON, exact unblocked P-task, and rejected fallback. |

Permitted result statuses are `pass`, `fail`, `inconclusive`, `deferred`, and `skipped`. `monitor` is invalid.

## 2. Exact harness layout and contracts

Create these files before adding a phase-specific probe.

```text
scripts/
  __init__.py
  benchmarks/
    __init__.py
    contracts.py          # dataclasses/enums and JSON validation
    fixtures.py           # fixture/result loading and path validation
    run.py                # argparse entry point and scenario dispatcher
    reporting.py          # atomic JSON/Markdown output writers
    providers.py          # descriptor-only provider/CLI probe
    protocol.py           # JSONL/Markdown/MCP/ACP/A2A envelope parser
    privacy.py            # synthetic-secret scan and bounded parser probe
    context.py            # raw/control/ContextPacker and CCRStore probes
    coordination.py       # journal/lock/flight-recorder probes
    local.py              # hardware capture and local-runtime probe
tests/
  fixtures/
    benchmarks/
      scenarios.json
      provider_routes.json
      routers.json
      protocol_cases.json
      privacy_cases.json
      context_cases.json
      coordination_cases.json
      local_candidates.json
  test_benchmark_contracts.py
  test_benchmark_runner.py
  test_benchmark_providers.py
  test_benchmark_privacy.py
  test_benchmark_context.py
  test_benchmark_coordination.py
  test_benchmark_local.py
research/benchmark/       # generated, untracked results only; never model weights
```

`scripts/benchmarks/contracts.py` defines only stdlib `dataclass` and `Enum` types: `Outcome`, `Scenario`, `SourceEvidence`, `RouteDescriptor`, `HardwareProfile`, `MetricSet`, `ProbeResult`, and `DecisionRecord`. `ProbeResult.to_dict()` is the only result serialization boundary; fixture deserialization is limited to the typed loaders below. Required JSON keys are `schema_version`, `scenario_id`, `probe`, `outcome`, `started_at`, `duration_ms`, `metrics`, `evidence`, `redactions`, `fallback`, and `reproduction`. Unknown keys or a missing required key fail fixture validation.

`scripts/benchmarks/fixtures.py` resolves fixtures only beneath `tests/fixtures/benchmarks/`; `scripts/benchmarks/reporting.py` resolves output only beneath an explicit `research/benchmark/B*/` directory and writes via temporary file plus replace. No fixture loader may read environment variables, a keychain, or a home-directory profile.
### 2A. Copyable core implementation specification

The coding agent must implement these public APIs exactly; phase tasks may add private helpers but may not change these signatures.

```python
# scripts/benchmarks/contracts.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1

class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    DEFERRED = "deferred"
    SKIPPED = "skipped"

class FixtureError(ValueError):
    pass

@dataclass(frozen=True)
class SourceEvidence:
    url: str
    retrieved_at: str
    revision: str = ""
    license_or_terms: str = ""

@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    probe: str
    category: str
    input: dict[str, Any]
    required_facts: tuple[str, ...]
    expected_outcome: Outcome

@dataclass(frozen=True)
class ProbeResult:
    scenario_id: str
    probe: str
    outcome: Outcome
    started_at: str
    duration_ms: int
    metrics: dict[str, int | float | str]
    evidence: tuple[SourceEvidence, ...] = ()
    redactions: tuple[str, ...] = ()
    fallback: str = ""
    reproduction: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        data["evidence"] = [asdict(item) for item in self.evidence]
        return data

REQUIRED_RESULT_KEYS = frozenset(ProbeResult.__dataclass_fields__)

def require_exact_keys(payload: dict[str, Any], keys: frozenset[str]) -> None:
    missing, unknown = keys - payload.keys(), payload.keys() - keys
    if missing or unknown:
        raise FixtureError(f"missing={sorted(missing)} unknown={sorted(unknown)}")
```

```python
# scripts/benchmarks/fixtures.py
import json
from pathlib import Path
from .contracts import FixtureError, Outcome, Scenario, require_exact_keys

FIXTURE_ROOT = Path("tests/fixtures/benchmarks").resolve()

def fixture_path(name: str) -> Path:
    path = (FIXTURE_ROOT / name).resolve()
    if FIXTURE_ROOT not in path.parents or path.suffix != ".json":
        raise FixtureError(f"fixture path denied: {name}")
    return path

def load_scenarios() -> dict[str, Scenario]:
    raw = json.loads(fixture_path("scenarios.json").read_text(encoding="utf-8"))
    scenarios: dict[str, Scenario] = {}
    for item in raw["scenarios"]:
        require_exact_keys(item, frozenset({
            "scenario_id", "probe", "category", "input",
            "required_facts", "expected_outcome",
        }))
        scenario = Scenario(
            scenario_id=item["scenario_id"], probe=item["probe"],
            category=item["category"], input=item["input"],
            required_facts=tuple(item["required_facts"]),
            expected_outcome=Outcome(item["expected_outcome"]),
        )
        if scenario.scenario_id in scenarios:
            raise FixtureError(f"duplicate scenario: {scenario.scenario_id}")
        scenarios[scenario.scenario_id] = scenario
    return scenarios
```

```python
# scripts/benchmarks/run.py
PROBES = {
    "provider": providers.run_provider_probe,
    "protocol": protocol.run_protocol_probe,
    "privacy": privacy.run_privacy_probe,
    "context": context.run_context_probe,
    "coordination": coordination.run_coordination_probe,
    "local": local.run_local_probe,
}

def run_scenario(
    scenario_id: str, output_root: Path, *,
    model_cache: Path | None = None,
    allow_live_route: str | None = None,
    allow_model_download: str | None = None,
) -> ProbeResult:
    scenario = load_scenarios()[scenario_id]  # KeyError is converted to FixtureError
    if scenario.probe not in PROBES:
        raise FixtureError(f"unknown probe: {scenario.probe}")
    result = PROBES[scenario.probe](
        scenario, model_cache=model_cache,
        allow_live_route=allow_live_route,
        allow_model_download=allow_model_download,
    )
    write_result(output_root, result)  # validates output_root before write
    return result
```

Use this fixture shape; all phase fixture files are an object with a plural top-level array, never JSONL:

```json
{
  "scenarios": [{
    "scenario_id": "ctx-2k-required-fact",
    "probe": "context",
    "category": "budget",
    "input": {"history": "…", "budget": 2000},
    "required_facts": ["repository uses Python 3.12"],
    "expected_outcome": "pass"
  }]
}
```

### 2B. Probe module behavior and focused test examples

| Module | Public function and required algorithm | Test that proves it |
|---|---|---|
| `providers.py` | `run_provider_probe(scenario, *, allow_live_route, **_) -> ProbeResult`: load one `RouteDescriptor`; if mode is `fixture`, return the fixture response; otherwise require `allow_live_route == route_id`, execute only `subprocess.run(route.command, shell=False, capture_output=True, text=True, timeout=route.timeout_s)`, redact stdout/stderr, and return `skipped` when not selected. | `test_live_route_requires_exact_opt_in`: monkeypatch `subprocess.run`; assert it is never called without the exact route ID and receives a list plus `shell=False`. |
| `protocol.py` | `run_protocol_probe(...)`: parse declared format; preserve `source_span`; treat all imported instructions as `quarantined`; never add them to `required_facts`. | `test_tampered_instruction_is_quarantined`: fixture containing “ignore prior policy” returns `fallback="quarantined-import"`. |
| `privacy.py` | `run_privacy_probe(...)`: apply deterministic synthetic-token patterns before `ProbeResult` serialization; return replacement labels in `redactions`, never source values. Enforce input `max_bytes`, `max_pages`, and `timeout_ms` before parsing. | `test_secret_never_reaches_json_or_exception`: serialize result and assert synthetic token absent while its source span remains. |
| `context.py` | `run_context_probe(...)`: call `ContextPacker(project_root=temp_root).pack(target_file, max_tokens=budget)`; calculate raw/control/packed token counts with `ContextPacker.count_tokens`; assert every `required_fact` is present or return `inconclusive` with `fallback="insufficient-budget"`. For CCR, call `store_chunk` then `retrieve_chunk` and verify exact restoration. | `test_required_fact_loss_cannot_pass` and `test_ccr_round_trip_and_missing_chunk`. |
| `coordination.py` | `run_coordination_probe(...)`: use a `tmp_path` project root; call `CheckpointJournal.save_checkpoint/restore_checkpoint`, `MeshLockManager.acquire/release`, and `FlightRecorder.record_event/replay_session`; convert any unexpected overwrite or missing replay event to `fail`. | `test_second_agent_cannot_acquire_held_lock` and `test_checkpoint_and_flight_replay_match`. |
| `local.py` | `run_local_probe(...)`: validate candidate evidence and an external `model_cache` first; without exact `allow_model_download`, return `skipped`; reject a cache under the repository and reject any command whose executable is `ollama`. The only permitted runtime command is user-selected `llama.cpp` or ONNX-compatible arguments. Write `hardware-profile.json` with required fields, then record elapsed milliseconds, observed cache bytes, and RSS when the selected runtime exposes it; missing metric is `inconclusive`, not zero. | `test_unapproved_candidate_does_not_invoke_subprocess`, `test_shell_string_is_rejected`, and `test_unavailable_profile_is_deferred`. |
| `reporting.py` | `write_result(output_root, result)`: resolve output under the supplied `research/benchmark/B*/` root, write `<scenario_id>.tmp`, replace `<scenario_id>.json`, and validate serialized keys before replace. `write_handoff(decisions, path)` rejects a decision lacking result path, fallback, P-task, or reproduction. | `test_writer_rejects_path_escape_and_incomplete_handoff`. |

The coding agent must begin each phase by adding the listed focused tests with these exact names. It must not substitute mocks for the existing Rush classes in B4/B5; mocks are allowed only for subprocesses and external routes.

## 3. External-route and local-runtime boundaries

A provider descriptor contains `provider_id`, `route_id`, `mode` (`fixture`, `api`, `oauth_cli`, or `cli`), `command` (argument array, never a shell string), `official_docs_url`, `terms_url`, `privacy_url`, `credential_boundary`, and `redaction_patterns`.

- Fixture mode is mandatory and is the only CI mode.
- `api`, `oauth_cli`, and `cli` mode require `--allow-live-route <route-id>` plus a user-selected, already-authenticated route. The harness may execute only the descriptor command; it cannot open a browser, create an account, inspect/export credentials, mutate a provider profile, retry through another provider, or persist provider output.
- `scripts/benchmarks/local.py` may download only a source-register-approved candidate into the explicit `--model-cache` path when invoked with `--allow-model-download <candidate-id>`. The cache must resolve outside the repository; its default is `%LOCALAPPDATA%/Rush/benchmark-model-cache` on Windows. It records URL, expected/observed hash, license, byte count, runtime version, and retention choice. Ollama is forbidden: do not invoke `ollama`, use its daemon or localhost endpoint, read its model directories, or start/stop/configure it. The permitted local-runtime descriptor is an explicit user-selected `llama.cpp` or ONNX-compatible command array.

## 4. TDD execution rule

For each task: add the failing test and minimal fixture first; run the named focused test and retain the red assertion; implement only the named file responsibilities; run the focused test green; run that phase’s regression command; then write the phase decision record and update its exact documents. Do not write a broad implementation before the red test exists.

## 5. Implementation phases

### B1 — harness foundation and control corpus

Entry: clean worktree. Outcome: a deterministic runner can execute fixture probes and serialize validated results. No product task is unblocked.

| Task | Files to create or change | Red → green acceptance | RTK / Graft / context-mode | Documents updated |
|---|---|---|---|---|
| B1-T01 | Create `scripts/__init__.py`, `scripts/benchmarks/__init__.py`, `contracts.py`, `fixtures.py`; create `tests/fixtures/benchmarks/scenarios.json` and `tests/test_benchmark_contracts.py`. | Red: missing `scenario_id`, unknown key, path escape, or invalid outcome is accepted. Green: each is rejected; 40 declared scenarios validate: 8 handoff, 6 drift, 6 recovery, 8 privacy, 8 budget, 4 concurrency. | `rtk find -name "test_phase4*.py"`; `rtk read --line-numbers tests/test_phase43_ccr_grounding.py`; `graft map .`; `context-mode index tests scripts --project . --ext .py,.json` | none |
| B1-T02 | Create `run.py`, `reporting.py`, `tests/test_benchmark_runner.py`. `run.py` accepts `--scenario`, `--output`, `--model-cache`, `--allow-live-route`, and `--allow-model-download`; reject all other live inputs. `--model-cache` is required for a live local run and must resolve outside the repository. | Red: dispatcher accepts unknown scenario/probe or writes outside output root. Green: it dispatches fixture probe, writes one atomic `ProbeResult`, and error results remain schema-valid. | `rtk read --line-numbers scripts/update_phase_docs.py`; `rtk pytest tests/test_benchmark_runner.py`; `graft check .`; `context-mode search "ToolResult result serialization" --project . --type code --limit 12` | none |
| B1-T03 | Add raw-history, naive-summary, and declared-control scenarios to `scenarios.json`; extend `tests/test_benchmark_runner.py`. | Red: missing token/latency/recovery/repetition metric passes. Green: all control results require those metrics and identical repeated fixture output. | `rtk grep "ContextPacker" src tests`; `rtk pytest tests/test_benchmark_runner.py`; `graft grep "ContextPacker" .`; `context-mode search "baseline continuation" --project . --type prose --limit 12` | none |
| B1-T04 | Create `research/benchmark/B1/decision-B-D01-B-D02.json` only from runner output. | Red: decision writer accepts result without fixture ID, red/green command, or fallback. Green: it rejects incomplete decisions and emits links to result JSON. | `rtk pytest tests/test_benchmark_contracts.py`; `rtk diff`; `graft check .`; `context-mode search "B-D01 B-D02" --project . --type prose --limit 12` | this plan; `docs/TESTING.md`; `docs/DEVELOPER_GUIDE.md`; `docs/developer/backlog.md`; `docs/developer/issues.md` |

### B2 — provider APIs, OAuth/CLI routes, 9Router, OmniRouter, and protocol

Entry: B1 green. Outcome: descriptor-driven, fixture-first route evaluation exists before the other benchmark phases. B-D07/B-D08/B-D09/B-D10 remain individually gated.

| Task | Files to create or change | Red → green acceptance | RTK / Graft / context-mode | Documents updated |
|---|---|---|---|---|
| B2-T01 | Create `providers.py`, `tests/fixtures/benchmarks/provider_routes.json`, `tests/test_benchmark_providers.py`. Add descriptors for Codex/OpenAI, Claude Code/Anthropic, Antigravity, Z.AI, DeepSeek, Mistral, and OpenRouter. | Red: descriptor lacking route mode, docs/terms/privacy evidence, command array, or credential boundary validates. Green: it fails; fixture mode produces redacted result; live mode rejects absent `--allow-live-route`. | `rtk read --line-numbers src/rush/providers/base.py`; `rtk pytest tests/test_benchmark_providers.py`; `graft callers LLMProvider .`; `context-mode search "provider capability OAuth CLI" --project . --type code --limit 20` | none |
| B2-T02 | Add 9Router and OmniRouter entries to `tests/fixtures/benchmarks/routers.json`; extend `providers.py` and provider tests. | Red: both router IDs share evidence URL, route ID, or generic vendor name. Green: independent evidence and result files are required; no generic router descriptor is accepted. | `rtk read --line-numbers tests/fixtures/benchmarks/routers.json`; `rtk pytest tests/test_benchmark_providers.py`; `graft grep "provider" .`; `context-mode search "9Router OmniRouter" --project . --type prose --limit 20` | none |
| B2-T03 | Create `protocol.py`, `tests/fixtures/benchmarks/protocol_cases.json`, and protocol tests in `tests/test_benchmark_providers.py`. | Red: JSONL/Markdown/MCP/ACP/A2A tampered input becomes trusted history. Green: parser returns a quarantined, source-spanned result with an explicit fallback. | `rtk grep "mcp" src tests`; `rtk pytest tests/test_benchmark_providers.py`; `graft grep "register" .`; `context-mode search "handoff protocol tombstone" --project . --type code --limit 20` | none |
| B2-T04 | Write B-D07/B-D08/B-D09/B-D10 results from the B2 runner output. | Red: decision can name two routes in one unblocking field. Green: each decision contains one route/router, its fixture IDs, source evidence, fallback, and exact P-task. | `rtk pytest tests/test_benchmark_providers.py`; `rtk diff`; `graft check .`; `context-mode search "B-D07 B-D08 B-D09 B-D10" --project . --type prose --limit 12` | this plan; `docs/TESTING.md`; `docs/DEPENDENCY_POLICY.md`; `docs/developer/backlog.md`; `docs/developer/issues.md` |

### B3 — privacy, parser, and dependency safety

Entry: B1 green. Outcome: B-D03 makes unsafe benchmark artifacts impossible before context, coordination, and local probes.

| Task | Files to create or change | Red → green acceptance | RTK / Graft / context-mode | Documents updated |
|---|---|---|---|---|
| B3-T01 | Create `privacy.py`, `tests/fixtures/benchmarks/privacy_cases.json`, `tests/test_benchmark_privacy.py`. | Red: a synthetic secret/PII token appears in serialized result, exception text, or markdown report. Green: it is redacted while source span and detector ID remain. | `rtk grep "redact\|secret" src tests`; `rtk pytest tests/test_benchmark_privacy.py`; `graft grep "redact" .`; `context-mode search "redaction privacy" --project . --type code --limit 12` | none |
| B3-T02 | Add `CandidateBinary` validation to `contracts.py` and candidate records to `privacy_cases.json`; extend privacy tests. | Red: discovered Gitleaks/detect-secrets candidate without version/license/result bounds is usable. Green: it becomes `deferred`; no installer, hook, or binary download path exists. | `rtk read --line-numbers src/rush/engines/gitleaks.py`; `rtk pytest tests/test_benchmark_privacy.py`; `graft grep "gitleaks" .`; `context-mode search "secret engine" --project . --type prose --limit 12` | none |
| B3-T03 | Add bounded malformed parser cases and parser probe in `privacy.py`. | Red: bytes/page/time limit or source offset is absent. Green: parser returns bounded failure with offsets and no egress. | `rtk find -name "*redactor*.py"`; `rtk pytest tests/test_benchmark_privacy.py`; `graft map .`; `context-mode search "parser source offsets" --project . --type code --limit 12` | none |
| B3-T04 | Write B-D03. | Red: decision omits a negative case or fallback. Green: output links every privacy fixture and test command. | `rtk pytest tests/test_benchmark_privacy.py`; `rtk diff`; `graft check .`; `context-mode search "B-D03" --project . --type prose --limit 12` | this plan; `docs/TESTING.md`; `docs/DEPENDENCY_POLICY.md`; `docs/developer/backlog.md`; `docs/developer/issues.md` |

### B4 — context reduction and retrieval

Entry: B1 and B3 green. Outcome: B-D04/B-D05 are measured against existing `ContextPacker` and `CCRStore`, not invented replacements.

| Task | Files to create or change | Red → green acceptance | RTK / Graft / context-mode | Documents updated |
|---|---|---|---|---|
| B4-T01 | Create `context.py`, `tests/fixtures/benchmarks/context_cases.json`, `tests/test_benchmark_context.py`. Call `ContextPacker.pack()` directly for every 2k/8k/16k case. | Red: required fact disappears without `insufficient-budget`; token result omits raw/control/packed counts. Green: all fields present; 0 critical loss and >=50% median reduction required for `pass`. | `rtk read --line-numbers src/rush/codegraph/context_packer.py`; `rtk pytest tests/test_benchmark_context.py`; `graft callers ContextPacker .`; `context-mode search "context budget omission" --project . --type code --limit 20` | none |
| B4-T02 | Add a retrieval adapter in `context.py` that tests existing `CCRStore` as control and declares Uteke/Hindsight as optional sidecars only. | Red: result lacks required-evidence recall, stale false-recall, delete/rebuild, or explanation metric. Green: incomplete sidecar is `deferred`; control stays exact IDs+FTS5. | `rtk read --line-numbers src/rush/token_economy/ccr_store.py`; `rtk pytest tests/test_benchmark_context.py`; `graft callers CCRStore .`; `context-mode search "retrieval stale evidence" --project . --type code --limit 20` | none |
| B4-T03 | Write B-D04/B-D05. | Red: decision unblocks an unspecified local/semantic task. Green: it names exactly one P-task and one fallback. | `rtk pytest tests/test_benchmark_context.py`; `rtk diff`; `graft check .`; `context-mode search "B-D04 B-D05" --project . --type prose --limit 12` | this plan; `docs/TESTING.md`; `docs/developer/backlog.md`; `docs/developer/issues.md` |

### B5 — coordination and portable handoff proof

Entry: B2, B3, and B4 green. Outcome: B-D11 is generated from existing checkpoint, mesh-lock, and flight-recorder behavior.

| Task | Files to create or change | Red → green acceptance | RTK / Graft / context-mode | Documents updated |
|---|---|---|---|---|
| B5-T01 | Create `coordination.py`, `tests/fixtures/benchmarks/coordination_cases.json`, `tests/test_benchmark_coordination.py`. Invoke `CheckpointJournal`, `MeshLockManager`, and `FlightRecorder` only through their public constructors/methods. | Red: lease collision, stale repository, conflicting claim, interrupted write, or deletion propagation silently overwrites state. Green: result contains owner, conflict ID, recovery action, and evidence span. | `rtk read --line-numbers src/rush/memory/checkpoint_journal.py`; `rtk pytest tests/test_benchmark_coordination.py`; `graft callers MeshLockManager .`; `context-mode search "lease conflict replay" --project . --type code --limit 20` | none |
| B5-T02 | Add cross-gate regression in `tests/test_benchmark_coordination.py`; use fixture-only provider and local probes. | Red: malicious import, denied egress, lost runtime, or repeat run lacks fallback. Green: no secret/authority breach and every result is reproducible. | `rtk pytest tests/test_benchmark_coordination.py`; `rtk diff`; `graft check .`; `context-mode search "privacy reproducibility fallback" --project . --type prose --limit 12` | none |
| B5-T03 | Write B-D11 from `ProbeResult` records. | Red: final decision lacks test command, result path, fallback, or exact P-task. Green: writer rejects incomplete record. | `rtk pytest tests/test_benchmark_coordination.py`; `rtk git status --short`; `graft check .`; `context-mode search "unblocked development task" --project . --type prose --limit 12` | this plan; `docs/TESTING.md`; `docs/developer/backlog.md`; `docs/developer/issues.md` |

### B6 — consumer-hardware local models and final handoff

Entry: B1–B5 green. Outcome: B-D06 is evidence from an implemented local probe; `final-handoff.md` is generated last.

| Task | Files to create or change | Red → green acceptance | RTK / Graft / context-mode | Documents updated |
|---|---|---|---|---|
| B6-T01 | Create `local.py`, `tests/fixtures/benchmarks/local_candidates.json`, `tests/test_benchmark_local.py`. `local.py` captures OS, CPU, RAM, GPU/VRAM or unified memory, free disk, runtime version, and profile ID into `hardware-profile.json`. | Red: candidate has no official model card, HF revision, upstream runtime release, license, quantization, disk size, or target profile. Green: it is rejected before download; accepted candidates are Granite 278M/BGE-small/Qwen3 embedding-reranker/Nomic/mxbai/BGE-M3 and Qwen3-4B/Phi-4-mini/SmolLM3; C2 permits Qwen3-8B/Granite8B/Qwen2.5-Coder-7B; C3 is comparator only. | `rtk read --line-numbers tests/test_phase43_ccr_grounding.py`; `rtk pytest tests/test_benchmark_local.py`; `graft map .`; `context-mode search "consumer hardware local model runtime" --project . --type prose --limit 20` | none |
| B6-T02 | Implement `--model-cache` and `--allow-model-download` in `local.py`; extend local tests with fake `llama.cpp`/ONNX runtime executable and fake external model cache. Add an explicit test that `ollama`, its endpoint, and any repository-local cache are rejected. | Red: unapproved download, repository-local cache, `ollama` executable/endpoint, shell-string command, missing hash/license/disk/RSS/latency, or daemon control succeeds. Green: only approved external-cache `llama.cpp`/ONNX argument-array command executes; unavailable C0/C1/C2/Apple profile is `deferred`; C3 cannot produce default acceptance. | `rtk grep "subprocess" src tests`; `rtk pytest tests/test_benchmark_local.py`; `graft grep "subprocess" .`; `context-mode search "local model runtime hardware" --project . --type prose --limit 20` | none |
| B6-T03 | Generate `research/benchmark/B6/decision-B-D06.json` and `final-handoff.md` through `reporting.py`; add final writer assertions to local tests. | Red: handoff omits a completed gate, result path, rejected fallback, exact P-task, or reproduction command. Green: one complete deterministic handoff is written from decision JSONs. | `rtk pytest tests/test_benchmark_local.py`; `rtk diff`; `graft check .`; `context-mode search "B-D06 final handoff" --project . --type prose --limit 12` | this plan; `docs/TESTING.md`; `docs/DEVELOPER_GUIDE.md`; `docs/DEPENDENCY_POLICY.md`; `docs/developer/backlog.md`; `docs/developer/issues.md` |

## 6. Final verification and development handoff

Run these exact repository checks after B6-T03:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_benchmark_contracts.py tests/test_benchmark_runner.py tests/test_benchmark_providers.py tests/test_benchmark_privacy.py tests/test_benchmark_context.py tests/test_benchmark_coordination.py tests/test_benchmark_local.py -q
.venv/Scripts/ruff.exe check scripts/benchmarks tests/test_benchmark_*.py
.venv/Scripts/ruff.exe format --check scripts/benchmarks tests/test_benchmark_*.py
```

A gate unblocks only: BG-AUTH/BG-PRIV → P2-T01; BG-CTX → P3-T01/T02; BG-RET/BG-LOCAL → named optional P3 task; BG-COORD → named P4 portability task; BG-PROV → one P5-T01 provider; BG-9R/BG-OMNI → that router’s P5-T02 route; BG-PROTO → named P2/P4/P5 protocol task. Every other result remains evidence only.