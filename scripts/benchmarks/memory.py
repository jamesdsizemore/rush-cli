"""Measured deterministic probes against Rush's existing MemoryTool."""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import tiktoken

from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryOperation, MemoryTool

from .contracts import FixtureError, Outcome, ProbeResult, Scenario
from .fixtures import load_memory_cases


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _scenario_hash(scenario: Scenario) -> str:
    contract = asdict(scenario)
    contract["expected_outcome"] = scenario.expected_outcome.value
    payload = json.dumps(
        contract,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(payload)


def _case_description(scenario: Scenario) -> str:
    cases = load_memory_cases(str(scenario.input.get("fixture", "memory_cases.json")))
    case_id = scenario.input.get("case_id", scenario.scenario_id)
    for case in cases:
        if case.get("scenario_id") == case_id:
            return str(case.get("input", {}).get("label", ""))
    raise FixtureError(f"unknown memory benchmark case: {case_id}")


def _content(index: int) -> str:
    prefix = f"memory benchmark artifact A{index:03d} matching retrieval evidence "
    return (prefix + ("x" * 512))[:512]


def run_memory_probe(
    scenario: Scenario, *, output_root: Path | None = None, **_: Any
) -> ProbeResult:
    """Measure actual legacy MemoryTool writes and defended recall."""
    started_at = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()
    if any(token in scenario.scenario_id for token in ("/", "\\", "..")):
        raise FixtureError(f"scenario path denied: {scenario.scenario_id}")
    description = _case_description(scenario)
    workspace_parent = (output_root or Path.cwd()).resolve()
    workspace_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="memory-", dir=workspace_parent
    ) as workspace:
        root = Path(workspace)
        permissions = ExecutionPermissions(cache_write=True)
        tool = MemoryTool()
        source_records = [
            {"id": "D1", "text": "DENIED_SECRET benchmark artifact"},
            *[{"id": f"A{index}", "text": _content(index)} for index in range(1, 101)],
        ]
        source_path = root / "memory-source.json"
        source_path.write_text(
            json.dumps(source_records, ensure_ascii=True, separators=(",", ":")),
            encoding="ascii",
        )
        source_hash = _sha256(source_path.read_bytes())

        denied = tool.run(
            root,
            operation="write",
            subject="domain_knowledge",
            content={"id": "D1", "text": "DENIED_SECRET benchmark artifact"},
            source="denied",
            permissions=permissions,
        )
        if denied["status"] != "ok":
            raise FixtureError(f"memory fixture write failed: {denied['summary']}")
        for record in source_records[1:]:
            written = tool.run(
                root,
                operation="write",
                subject="domain_knowledge",
                content=record,
                source="allowed",
                permissions=permissions,
            )
            if written["status"] != "ok":
                raise FixtureError(f"memory fixture write failed: {written['summary']}")

        recalled = tool.run(
            root,
            operation="ask",
            subject="domain_knowledge",
            query="benchmark",
            session_allowlist=["allowed"],
        )
        if recalled["status"] != "ok":
            raise FixtureError(f"memory recall failed: {recalled['summary']}")
        artifacts = recalled["raw"]
        if not isinstance(artifacts, list):
            raise FixtureError("memory recall returned malformed artifacts")
        serialized = json.dumps(recalled, ensure_ascii=False, separators=(",", ":"))
        token_count = len(tiktoken.get_encoding("cl100k_base").encode(serialized))
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        visible_ids = {
            item.get("content", {}).get("id")
            for item in artifacts
            if isinstance(item, dict)
        }
        visible_sources = {
            item.get("source") for item in artifacts if isinstance(item, dict)
        }
        denied_visible = "D1" in visible_ids or "denied" in visible_sources
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="memory",
            outcome=Outcome.FAIL if denied_visible else Outcome.PASS,
            started_at=started_at,
            duration_ms=elapsed_ms,
            metrics={
                "case_description": description,
                "artifact_count": len(artifacts),
                "serialized_bytes": len(serialized.encode("utf-8")),
                "token_count": token_count,
                "token_method": "tiktoken:cl100k_base",
                "elapsed_ms": elapsed_ms,
                "payload_truncated": False,
                "denied_id_visible": "D1" in visible_ids,
                "denied_source_visible": "denied" in visible_sources,
                "evidence_mode": str(
                    scenario.input.get("evidence_mode", "legacy-baseline")
                ),
                "operation_mode": str(
                    scenario.input.get("operation_mode", "current-ask")
                ),
                "source_hash": source_hash,
                "scenario_hash": _scenario_hash(scenario),
            },
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )


# --- MC13.3/MC13.4: real agent episodes over existing MC02/MC06/MC08/MC09/MC10/MC11
# infrastructure ------------------------------------------------------------------

_ENCODING = "cl100k_base"


@dataclass(frozen=True)
class EpisodeObservation:
    """What the agent under evaluation is allowed to see: the task text and,
    at each step, the actual raw `MemoryTool.run()` results of its own prior
    calls in this episode. Never includes a gold answer, an expected next
    action, or a graded patch."""

    task: str
    step_index: int
    history: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class EpisodeAction:
    """One decision returned by the agent under evaluation. `operation`
    is any `rush.tools.memory.MemoryTool` operation, or the sentinel
    `"submit"` to end the episode. `kwargs` are passed through verbatim to
    `MemoryTool.run()` (subject/query/session_allowlist/content/source/
    request, per that operation's own contract) -- `run_memory_episode`
    never reshapes them."""

    operation: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    final: Any = None


DecideFn = Callable[[EpisodeObservation], EpisodeAction]


@dataclass(frozen=True)
class EpisodeEvent:
    """One real observed tool call: `raw` is the exact, unmodified
    `MemoryTool.run()` return value."""

    step_index: int
    operation: str
    kwargs: dict[str, Any]
    raw: dict[str, Any]
    token_count: int


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: str
    task: str
    outcome: Outcome
    events: tuple[EpisodeEvent, ...]
    total_tokens: int
    budget_exhausted: bool
    timed_out: bool
    final: Any
    verifier_receipt: dict[str, Any] | None
    receiver_readback: bool | None
    started_at: str
    duration_ms: int
    reproduction: str


def _data(tool_result: dict[str, Any]) -> dict[str, Any]:
    """Unwraps an enveloped `MemoryTool.run()` result (`handoff`/`receive`/
    `expand`/`recipe`/`plan_checks`/`last_success_diagnose` all wrap their
    real content under `raw["data"]`, distinct from `write`/`verify_attempt`,
    which return their content directly under `raw`)."""
    return tool_result["raw"]["data"]


def _verifier_receipt(events: tuple[EpisodeEvent, ...]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.operation == "verify_attempt":
            return event.raw.get("raw")
    return None


def _receiver_readback(events: tuple[EpisodeEvent, ...]) -> bool | None:
    """`True` only when a `receive` call actually carried a verified `ack`
    (`MemoryTool.run` returns `status="ok"` only after
    `acknowledge_readback()` accepted every entry's exact content digest) --
    a bare delivered-page call with no `ack` never counts as a read-back."""
    receive_events = [e for e in events if e.operation == "receive"]
    if not receive_events:
        return None
    return any(
        isinstance(e.kwargs.get("request"), dict)
        and e.kwargs["request"].get("ack")
        and e.raw.get("status") == "ok"
        for e in receive_events
    )


def _score_episode(
    events: tuple[EpisodeEvent, ...],
    *,
    verifier_receipt: dict[str, Any] | None,
    receiver_readback: bool | None,
    budget_exhausted: bool,
    timed_out: bool,
) -> Outcome:
    """Scores actual observed behavior, never the agent's own claimed
    `final` value. Timeout and budget exhaustion are real failures, not
    exclusions -- callers still receive a full `EpisodeResult` for their
    denominator."""
    if timed_out or budget_exhausted:
        return Outcome.FAIL
    if verifier_receipt is not None:
        return (
            Outcome.PASS
            if verifier_receipt.get("outcome") == "completed"
            else Outcome.FAIL
        )
    if receiver_readback is not None:
        return Outcome.PASS if receiver_readback else Outcome.FAIL
    if not events:
        return Outcome.INCONCLUSIVE
    return (
        Outcome.PASS
        if all(e.raw.get("status") in ("ok", "warn") for e in events)
        else Outcome.FAIL
    )


def run_memory_episode(
    episode_id: str,
    task: str,
    decide_fn: DecideFn,
    *,
    root: Path,
    permissions: ExecutionPermissions,
    max_steps: int = 12,
    max_total_tokens: int = 16000,
    timeout_seconds: float | None = None,
) -> EpisodeResult:
    """Runs one real agent episode against `root`'s live `MemoryTool`.
    `decide_fn` chooses each step from the actual observed history only;
    every tool call it requests is genuinely executed (no fabricated
    events). Every expansion/recall/etc. step's real serialized-result token
    cost counts toward `max_total_tokens` -- there is no free/uncounted
    operation."""
    tool = MemoryTool()
    encoder = tiktoken.get_encoding(_ENCODING)
    events: list[EpisodeEvent] = []
    total_tokens = 0
    budget_exhausted = False
    timed_out = False
    final: Any = None
    started_at = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()
    for step_index in range(max_steps):
        if timeout_seconds is not None and (time.perf_counter() - t0) > timeout_seconds:
            timed_out = True
            break
        observation = EpisodeObservation(
            task=task, step_index=step_index, history=tuple(e.raw for e in events)
        )
        action = decide_fn(observation)
        if action.operation == "submit":
            final = action.final
            break
        operation = cast(MemoryOperation, action.operation)
        raw: dict[str, Any] = dict(
            tool.run(
                root, operation=operation, permissions=permissions, **action.kwargs
            )
        )
        serialized = json.dumps(
            raw, ensure_ascii=False, separators=(",", ":"), default=str
        )
        token_count = len(encoder.encode(serialized))
        total_tokens += token_count
        events.append(
            EpisodeEvent(
                step_index=step_index,
                operation=action.operation,
                kwargs=action.kwargs,
                raw=raw,
                token_count=token_count,
            )
        )
        if total_tokens > max_total_tokens:
            budget_exhausted = True
            break
    verifier_receipt = _verifier_receipt(tuple(events))
    receiver_readback = _receiver_readback(tuple(events))
    outcome = _score_episode(
        tuple(events),
        verifier_receipt=verifier_receipt,
        receiver_readback=receiver_readback,
        budget_exhausted=budget_exhausted,
        timed_out=timed_out,
    )
    return EpisodeResult(
        episode_id=episode_id,
        task=task,
        outcome=outcome,
        events=tuple(events),
        total_tokens=total_tokens,
        budget_exhausted=budget_exhausted,
        timed_out=timed_out,
        final=final,
        verifier_receipt=verifier_receipt,
        receiver_readback=receiver_readback,
        started_at=started_at,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        reproduction=f"python -m scripts.benchmarks.run --suite memory --episode {episode_id}",
    )


# --- Five named episode builders (MC13.3) ----------------------------------------

_UPLOAD_BUGGY = (
    "def upload(size_bytes: int, elapsed_seconds: float) -> bool:\n"
    "    if elapsed_seconds > 30:\n"
    "        return True\n"
    "    if size_bytes > 1_000_000:\n"
    "        return True\n"
    "    return True\n"
)
_CHECK_UPLOAD = (
    "import upload\n\n"
    'assert upload.upload(0, 999) is False, "expected timeout rejected"\n'
    'assert upload.upload(2_000_000, 0) is False, "expected oversized upload rejected"\n'
    'print("OK")\n'
)
_PATCH_TIMEOUT_ONLY = (
    "--- a/upload.py\n+++ b/upload.py\n@@ -1,6 +1,6 @@\n"
    " def upload(size_bytes: int, elapsed_seconds: float) -> bool:\n"
    "     if elapsed_seconds > 30:\n-        return True\n+        return False\n"
    "     if size_bytes > 1_000_000:\n         return True\n     return True\n"
)
_PATCH_TIMEOUT_AND_SIZE_LIMIT = (
    "--- a/upload.py\n+++ b/upload.py\n@@ -1,6 +1,6 @@\n"
    " def upload(size_bytes: int, elapsed_seconds: float) -> bool:\n"
    "     if elapsed_seconds > 30:\n-        return True\n+        return False\n"
    "     if size_bytes > 1_000_000:\n-        return True\n+        return False\n"
    "     return True\n"
)


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _init_upload_repair_repo(root: Path) -> tuple[str, str]:
    """Real git repo fixture for the "Upload repair" episode (mirrors MC05's
    `verify_attempt` sandbox fixture, `tests/test_memory_verify_attempt.py`):
    a buggy `upload()` with two independent bugs and a real check script that
    only exits 0 once both are fixed."""
    _run_git(["init", "-b", "main"], root)
    _run_git(["config", "user.name", "RushBenchmark"], root)
    _run_git(["config", "user.email", "benchmark@example.com"], root)
    (root / ".gitignore").write_text(".rush/\n", encoding="utf-8")
    (root / "upload.py").write_text(_UPLOAD_BUGGY, encoding="utf-8")
    (root / "check_upload.py").write_text(_CHECK_UPLOAD, encoding="utf-8")
    _run_git(["add", "."], root)
    _run_git(["commit", "-m", "initial upload module with two known bugs"], root)
    head = _run_git(["rev-parse", "HEAD"], root)
    tree = _run_git(["rev-parse", "HEAD^{tree}"], root)
    return head, tree


def build_upload_repair_episode(root: Path) -> tuple[str, DecideFn]:
    """Episode 1: a real two-attempt sandbox repair (`verify_attempt`). The
    agent's second attempt is chosen from the first attempt's actually
    observed `outcome="failed"`, never from a gold patch."""
    base_commit, base_tree = _init_upload_repair_repo(root)

    def decide(observation: EpisodeObservation) -> EpisodeAction:
        required_command = [{"command": [sys.executable, "check_upload.py"]}]
        if observation.step_index == 0:
            return EpisodeAction(
                operation="verify_attempt",
                kwargs={
                    "request": {
                        "attempt_id": "episode-attempt-1",
                        "behavior_ids": ["upload-timeout-fixed"],
                        "contract": {
                            "base_commit": base_commit,
                            "base_tree_digest": base_tree,
                            "patch_content_digest": "episode-patch-1",
                            "required_commands": required_command,
                            "config_digest": "episode-cfg-1",
                            "review_class": "standard",
                        },
                        "patch": _PATCH_TIMEOUT_ONLY,
                    }
                },
            )
        last_outcome = observation.history[-1].get("raw", {}).get("outcome")
        if observation.step_index == 1 and last_outcome == "failed":
            return EpisodeAction(
                operation="verify_attempt",
                kwargs={
                    "request": {
                        "attempt_id": "episode-attempt-2",
                        "behavior_ids": [
                            "upload-timeout-fixed",
                            "upload-size-limit-fixed",
                        ],
                        "contract": {
                            "base_commit": base_commit,
                            "base_tree_digest": base_tree,
                            "patch_content_digest": "episode-patch-2",
                            "required_commands": required_command,
                            "config_digest": "episode-cfg-2",
                            "review_class": "standard",
                        },
                        "patch": _PATCH_TIMEOUT_AND_SIZE_LIMIT,
                    }
                },
            )
        return EpisodeAction(operation="submit", final=last_outcome)

    return (
        "Fix upload() so it correctly rejects timed-out and oversized uploads.",
        decide,
    )


def build_guest_handoff_episode(root: Path) -> tuple[str, DecideFn]:
    """Episode 2: a real in-process handoff cycle -- write, prepare, receive,
    expand for the exact bytes, then ack with the receiver's own computed
    digest (never a value the agent invents)."""

    def decide(observation: EpisodeObservation) -> EpisodeAction:
        step = observation.step_index
        if step == 0:
            return EpisodeAction(
                operation="write",
                kwargs={
                    "subject": "domain_knowledge",
                    "content": {
                        "text": "guest checkout regression: promo code applies twice"
                    },
                    "source": "guest-session",
                },
            )
        if step == 1:
            written = observation.history[0]["raw"]
            return EpisodeAction(
                operation="handoff",
                kwargs={
                    "request": {
                        "action": "prepare",
                        "receiver_audience": "handoff-receiver",
                        "goal": "diagnose duplicate promo application",
                        "selected_refs": [
                            {
                                "id": written["id"],
                                "version": written["artifact_version"],
                            }
                        ],
                    }
                },
            )
        if step == 2:
            prepared = _data(observation.history[1])
            return EpisodeAction(
                operation="receive",
                kwargs={
                    "request": {
                        "session_id": prepared["handoff_id"],
                        "capability": prepared["capability"],
                    }
                },
            )
        if step == 3:
            received = _data(observation.history[2])
            change = received["changes"][0]
            return EpisodeAction(
                operation="expand",
                kwargs={
                    "session_allowlist": ["guest-session"],
                    "request": {"id": change["id"], "version": change["version"]},
                },
            )
        if step == 4:
            prepared = _data(observation.history[1])
            received = _data(observation.history[2])
            change = received["changes"][0]
            expanded = _data(observation.history[3])
            content_bytes = base64.b64decode(expanded["content_base64"])
            digest = hashlib.sha256(content_bytes).hexdigest()
            return EpisodeAction(
                operation="receive",
                kwargs={
                    "request": {
                        "session_id": prepared["handoff_id"],
                        "capability": prepared["capability"],
                        "ack": [
                            {
                                "id": change["id"],
                                "version": change["version"],
                                "digest": digest,
                            }
                        ],
                    }
                },
            )
        return EpisodeAction(operation="submit", final="handoff complete")

    return "Hand off the guest-checkout regression note to a receiver.", decide


_CSV_HELPER_ORIGINAL = (
    "import csv\n"
    "import io\n\n\n"
    'def export_rows(rows, caller="system"):\n'
    '    if caller != "system":\n'
    '        raise PermissionError(f"unauthorized caller: {caller}")\n'
    '    buf = io.StringIO(newline="")\n'
    "    writer = csv.writer(buf)\n"
    "    for row in rows:\n"
    "        writer.writerow(row)\n"
    "    return buf.getvalue()\n"
)
_CSV_HELPER_API_CHANGED = (
    "import csv\n"
    "import io\n\n\n"
    'def export_rows(rows, caller="system", strict=True):\n'
    '    if strict and caller != "system":\n'
    '        raise PermissionError(f"unauthorized caller: {caller}")\n'
    '    buf = io.StringIO(newline="")\n'
    "    writer = csv.writer(buf)\n"
    "    for row in rows:\n"
    "        writer.writerow(row)\n"
    "    return buf.getvalue()\n"
)


def build_csv_adaptation_episode(root: Path) -> tuple[str, DecideFn]:
    """Episode 3: records a CSV-export recipe against the real helper on
    disk, then an out-of-band API change (an independent fact, not a gold
    hint) makes the recorded recipe stale; the agent's own `resolve` call
    (real source re-read) is what detects the drift."""
    (root / "csv_helper.py").write_text(_CSV_HELPER_ORIGINAL, encoding="utf-8")

    def decide(observation: EpisodeObservation) -> EpisodeAction:
        step = observation.step_index
        if step == 0:
            return EpisodeAction(
                operation="recipe",
                kwargs={
                    "request": {
                        "action": "record",
                        "recipe_id": "csv-export-recipe",
                        "purpose": "export rows as CSV",
                        "helper_ref": {
                            "path": "csv_helper.py",
                            "symbol": "export_rows",
                        },
                    }
                },
            )
        if step == 1:
            return EpisodeAction(
                operation="recipe",
                kwargs={
                    "request": {"action": "resolve", "recipe_id": "csv-export-recipe"}
                },
            )
        if step == 2:
            # An out-of-band API change to the real helper file (an
            # environment fact, mirroring MC08's own "changed API rejects
            # recipe" scenario) -- never a gold hint about the outcome.
            (root / "csv_helper.py").write_text(
                _CSV_HELPER_API_CHANGED, encoding="utf-8"
            )
            return EpisodeAction(
                operation="recipe",
                kwargs={
                    "request": {"action": "resolve", "recipe_id": "csv-export-recipe"}
                },
            )
        last_resolution = _data(observation.history[-1])
        return EpisodeAction(operation="submit", final=last_resolution.get("usable"))

    return "Adapt the CSV export recipe after the helper API changes.", decide


def build_payload_check_order_episode(root: Path) -> tuple[str, DecideFn]:
    """Episode 4: ranks required checks by real (currently absent) evidence
    for a changed payload validator -- a fresh namespace has no recorded
    coverage, so this exercises the honest default-order path, not a
    fabricated ranking."""

    def decide(observation: EpisodeObservation) -> EpisodeAction:
        if observation.step_index == 0:
            return EpisodeAction(
                operation="plan_checks",
                kwargs={
                    "request": {
                        "changed_targets": [{"id": "payload-validator"}],
                        "required_checks": [
                            {"id": "schema-check"},
                            {"id": "regression-check"},
                        ],
                        "environment": {"available_engines": []},
                    }
                },
            )
        planned = _data(observation.history[0])
        return EpisodeAction(operation="submit", final=planned.get("checks"))

    return "Order required checks for the changed payload validator.", decide


def build_diagnosis_handoff_episode(root: Path) -> tuple[str, DecideFn]:
    """Episode 5: a real last-success diagnosis (no recorded pointer yet, so
    an honest `cause_state="candidate"` default) followed by handing the
    diagnosis note off through the same real receive/expand/ack cycle as
    episode 2."""

    def decide(observation: EpisodeObservation) -> EpisodeAction:
        step = observation.step_index
        if step == 0:
            return EpisodeAction(
                operation="last_success_diagnose",
                kwargs={
                    "request": {
                        "behavior_id": "deploy-pipeline",
                        "conditions": {"code_ref": "abc123"},
                    }
                },
            )
        if step == 1:
            diagnosis = _data(observation.history[0])
            return EpisodeAction(
                operation="write",
                kwargs={
                    "subject": "domain_knowledge",
                    "content": {
                        "text": "deploy-pipeline diagnosis",
                        "cause_state": diagnosis.get("cause_state"),
                    },
                    "source": "diagnosis-session",
                },
            )
        if step == 2:
            written = observation.history[1]["raw"]
            return EpisodeAction(
                operation="handoff",
                kwargs={
                    "request": {
                        "action": "prepare",
                        "receiver_audience": "handoff-receiver",
                        "goal": "hand off deploy-pipeline diagnosis",
                        "selected_refs": [
                            {
                                "id": written["id"],
                                "version": written["artifact_version"],
                            }
                        ],
                    }
                },
            )
        if step == 3:
            prepared = _data(observation.history[2])
            return EpisodeAction(
                operation="receive",
                kwargs={
                    "request": {
                        "session_id": prepared["handoff_id"],
                        "capability": prepared["capability"],
                    }
                },
            )
        if step == 4:
            received = _data(observation.history[3])
            change = received["changes"][0]
            return EpisodeAction(
                operation="expand",
                kwargs={
                    "session_allowlist": ["diagnosis-session"],
                    "request": {"id": change["id"], "version": change["version"]},
                },
            )
        if step == 5:
            prepared = _data(observation.history[2])
            received = _data(observation.history[3])
            change = received["changes"][0]
            expanded = _data(observation.history[4])
            content_bytes = base64.b64decode(expanded["content_base64"])
            digest = hashlib.sha256(content_bytes).hexdigest()
            return EpisodeAction(
                operation="receive",
                kwargs={
                    "request": {
                        "session_id": prepared["handoff_id"],
                        "capability": prepared["capability"],
                        "ack": [
                            {
                                "id": change["id"],
                                "version": change["version"],
                                "digest": digest,
                            }
                        ],
                    }
                },
            )
        return EpisodeAction(operation="submit", final="diagnosis handed off")

    return "Diagnose the deploy-pipeline regression and hand it off.", decide


EPISODE_BUILDERS: dict[str, Callable[[Path], tuple[str, DecideFn]]] = {
    "upload-repair": build_upload_repair_episode,
    "guest-handoff": build_guest_handoff_episode,
    "csv-adaptation": build_csv_adaptation_episode,
    "payload-check-order": build_payload_check_order_episode,
    "diagnosis-handoff": build_diagnosis_handoff_episode,
}


def run_named_episode(
    episode_id: str, root: Path, *, permissions: ExecutionPermissions | None = None
) -> EpisodeResult:
    """Builds and runs one of the five MC13.3 named episodes against a fresh
    `root`. `permissions` defaults to the full write/build grant every
    episode's real operations (`verify_attempt`, `write`, `handoff`,
    `recipe record`) require."""
    builder = EPISODE_BUILDERS.get(episode_id)
    if builder is None:
        raise FixtureError(f"unknown memory episode: {episode_id}")
    task, decide_fn = builder(root)
    return run_memory_episode(
        episode_id,
        task,
        decide_fn,
        root=root,
        permissions=permissions
        or ExecutionPermissions(cache_write=True, artifact_write=True, build=True),
    )
