"""Full-project scan planning and execution (Phase 65 P65-04, F34-35).

Builds the scan candidate set from the shared tool/engine inventory
(`rush.catalog.TOOL_SPECS`/`ENGINE_SPECS`, `rush.tools.ALL_TOOLS`), assigns
every candidate exactly one plan §3.2 disposition (`applicable`,
`not_applicable`, `requires_input`, `unsupported`, `excluded_by_user`),
executes every `applicable` candidate exactly once through the same
zero-retry `InvocationExecutor` boundary `rush.workflows.suites` uses, and
aggregates every scheduled child through the canonical `aggregate_results`
(plan §3.3: "Shared `aggregate_results` behavior retains findings/versions/
reasons; no `TypeError` retry"). Persists one immutable terminal run manifest
under `<project_root>/.rush/runs/<run_id>/attempts/<attempt_id>/manifest.json`
with the existing `atomic_write_bytes` primitive (plan §6.1), guarded by a
real file lock mirroring `rush.workflows.projects._registry_lock`.

`plan_scan` also stages the plan itself under
`<project_root>/.rush/scan_plans/<plan_id>.json` -- the frozen `rush_scan.run`
request carries only `project`/`plan_id`/`install` (plan §6.1), so a plan must
be durably retrievable by ID before `execute_scan` can run it; `load_scan_plan`
is the read side of that staging.

CLI/MCP wiring for `rush scan`/`rush_scan` is out of this task's allowed
files -- P65-04 owns `plan_scan`/`execute_scan` and `ScanTool`'s own
`plan`/`run`/`status` envelope only; `cli.py`/`mcp.py` registration follows
the same split P65-03 used for `ProjectTool` (T204/T097/T015; see that
class's docstring).

P65-08 (F35, this packet, T216) adds per-run ordered progress events,
cooperative cancellation, and restart recovery: `execute_scan` now accepts
an optional `run_id` and persists an `attempt.json` header plus one
`candidates/<id>.json` evidence file per finished candidate *before* the
final aggregate/manifest write, so a real process death after a child
result but before the aggregate still leaves retained, resumable evidence.
`cancel_scan_run` writes a cross-process/cross-thread cooperative
`cancel_requested.json` marker under the run's own directory; `execute_scan`
checks it at every candidate boundary, and any candidate whose tool exposes
a duck-typed `run_cancellable(root, *, cancel_check)` (see
`rush.runtime.subprocesses.run_subprocess`'s optional `cancel_check`
contract) can also be interrupted mid-subprocess, terminating only its own
owned child process group/tree -- never a foreign process, never orphaned.
`resume_scan_run` starts a new attempt under the *same* `run_id`, retaining
every previously `executed` candidate's evidence unexecuted, denies a stale
resume (`ScanResumeStaleError`) if the project's source changed since the
original attempt started (reusing `_source_signature`, the same staleness
primitive `dispatch_handoff` already uses), and always mints a fresh
`attempt_id` on a valid retry. `ScanTool` (`src/rush/tools/scan.py`) is
outside this packet's allowed files and cannot register `cancel`/`resume`
as its own operations; `cli.py`'s `scan cancel`/`scan resume` subcommands
and `mcp.py`'s `rush_scan` `cancel`/`resume` operations call
`cancel_scan_run`/`resume_scan_run` directly, mirroring the `rescan`-direct-
call precedent the CLI already uses for `rescan_project_run`.

P65-06 (F35, this packet) adds `build_handoff`/`dispatch_handoff`/
`status_handoff`/`acknowledge_handoff`/`complete_handoff` (plan §6.1
`rush_scan_handoff` prepare/dispatch/status/acknowledge/complete) and
`compare_runs`/`rescan_project_run` (plan §6.1 `rush_scan.rescan`, §6.4
resolved/persisting/new/unverified). Handoff delivery/acknowledgment reuse
Phase63's real transport receiver (`rush.memory.handoff.prepare_handoff`/
`receive_handoff`) rather than a second, fabricated transport layer --
`dispatch_handoff` only reaches `delivered` on an actual `receive_handoff`
read-back, never a fictional send API. `rescan_project_run`'s corresponding
`rush_scan.rescan` MCP operation lives on `ScanTool` (`src/rush/tools/
scan.py`), outside this packet's allowed files -- see `ScanHandoffTool`'s
own docstring for the exact disclosed gap.

Engine coverage: every `ALL_TOOLS` entry plus every `ENGINE_SPECS` row with no
owning `TOOL_SPECS.engine_names` ("engine-only catalog entries", plan §6.4) is
a real coverage candidate. Rush has no scan adapter for those engine-only
entries yet (no owning `TOOL_SPECS` row exists to invoke and normalize their
output), so each one that isn't `capability="workflow"` gets disposition
`applicable` and execution outcome `unavailable`/`ENGINE_ROUTE_MISSING` --
never silently dropped, never counted as executed (plan §6.4: "missing
executable route is unavailable/ENGINE_ROUTE_MISSING, not excluded").
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import tiktoken

from rush.catalog import ENGINE_SPECS, TOOL_SPECS
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.memory.handoff import HandoffError, prepare_handoff, receive_handoff
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.runtime.filesystem import atomic_write_bytes
from rush.tools import ALL_TOOLS
from rush.tools.base import Finding, ToolResult
from rush.tools.common import error_result, finding_fingerprint, skipped_result
from rush.tools.quality import GuardedQualityTool
from rush.tools.routing import aggregate_results
from rush.workflows.projects import ProjectError, resolve_project

Disposition = Literal[
    "applicable", "not_applicable", "requires_input", "unsupported", "excluded_by_user"
]
ExecutionOutcome = Literal[
    "executed", "unavailable", "permission_blocked", "failed", "cancelled"
]
RunState = Literal[
    "planned",
    "provisioning",
    "running",
    "completed",
    "incomplete",
    "failed",
    "cancelled",
]

_NON_SCAN_REASON = "non_scan_workflow_operation"
_REPORT_INPUT_REASON = "requires_report_input"
_DYNAMIC_TARGET_REASON = "requires_dynamic_target_and_grants"
_STATIC_REASON = "comprehensive_static_analysis"
_EXPLICIT_TARGET_REASON = "explicit_target_provided"
_ENGINE_ROUTE_MISSING = "ENGINE_ROUTE_MISSING"

_RUN_LOCK_RELATIVE = ".rush/runs/.scan.lock"
_MANIFEST_RELATIVE = ".rush/runs/{run_id}/attempts/{attempt_id}/manifest.json"
_ATTEMPT_HEADER_RELATIVE = ".rush/runs/{run_id}/attempts/{attempt_id}/attempt.json"
_EVENTS_RELATIVE = ".rush/runs/{run_id}/attempts/{attempt_id}/events.json"
_CANDIDATE_EVIDENCE_RELATIVE = (
    ".rush/runs/{run_id}/attempts/{attempt_id}/candidates/{digest}.json"
)
_CANCEL_REQUEST_RELATIVE = ".rush/runs/{run_id}/cancel_requested.json"
_PLAN_RELATIVE = ".rush/scan_plans/{plan_id}.json"

_LOCK_STALE_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.02


class ScanError(ProjectError):
    """Base error for scan planning/execution. Defaults to INVALID_REQUEST."""


class ScanInvalidRequestError(ScanError):
    code = "INVALID_REQUEST"


class ScanPlanStaleError(ScanError):
    code = "PLAN_STALE"


class ScanBusyError(ScanError):
    code = "BUSY"
    retryable: ClassVar[bool] = True


class ScanResumeStaleError(ScanError):
    """A resume was refused because the project's source changed since the
    run's original attempt started (plan §6.4: "stale resume denied")."""

    code = "RESUME_STALE"


def _canonical_json(value: Any) -> bytes:
    """Canonical JSON: sorted keys, compact separators, UTF-8 (plan §6.1)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@contextmanager
def _run_lock(root: Path, *, timeout: float = 5.0) -> Iterator[None]:
    """Real mutual exclusion over one project's run directory.

    Mirrors `rush.workflows.projects._registry_lock`'s O_EXCL pattern so scan
    runs reuse the same atomic-lock discipline as the project registry
    (plan §6.1: "Mutations ... compare under existing lock; lock timeout 5
    seconds returns BUSY").
    """
    lock_dir = root / ".rush" / "runs"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / ".scan.lock"
    start = time.monotonic()
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > _LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() - start >= timeout:
                raise ScanBusyError(
                    f"timed out after {timeout}s waiting for the scan run lock"
                ) from None
            time.sleep(_LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        os.close(fd)
        with suppress(OSError):
            lock_path.unlink()


@dataclass(frozen=True)
class ScanCandidate:
    """One catalog entry with its reasoned plan §3.2 disposition."""

    candidate_id: str
    kind: Literal["tool", "engine"]
    category: str
    disposition: Disposition
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind,
            "category": self.category,
            "disposition": self.disposition,
            "reason": self.reason,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> ScanCandidate:
        return ScanCandidate(
            candidate_id=str(payload["candidate_id"]),
            kind=payload["kind"],
            category=str(payload["category"]),
            disposition=payload["disposition"],
            reason=str(payload["reason"]),
        )


@dataclass(frozen=True)
class ScanPlan:
    """Frozen, hashable full-scan plan (plan §6.1 `rush_scan.plan`)."""

    plan_id: str
    project_id: str
    root: str
    candidates: tuple[ScanCandidate, ...]
    exclude: tuple[str, ...]
    targets: dict[str, dict[str, Any]]
    severity: str
    concurrency: int
    timeout_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "root": self.root,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "exclude": list(self.exclude),
            "targets": self.targets,
            "severity": self.severity,
            "concurrency": self.concurrency,
            "timeout_seconds": self.timeout_seconds,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> ScanPlan:
        return ScanPlan(
            plan_id=str(payload["plan_id"]),
            project_id=str(payload["project_id"]),
            root=str(payload["root"]),
            candidates=tuple(
                ScanCandidate.from_dict(item) for item in payload["candidates"]
            ),
            exclude=tuple(payload.get("exclude") or ()),
            targets=dict(payload.get("targets") or {}),
            severity=str(payload.get("severity", "warn")),
            concurrency=int(payload.get("concurrency", 2)),
            timeout_seconds=int(payload.get("timeout_seconds", 300)),
        )


@dataclass(frozen=True)
class CandidateResult:
    """One scheduled candidate's real, retained execution outcome."""

    candidate: ScanCandidate
    outcome: ExecutionOutcome
    result: ToolResult

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.candidate.to_dict(),
            "outcome": self.outcome,
            "child": dict(self.result),
        }


@dataclass(frozen=True)
class ScanRun:
    """One terminal scan run, with its immutable manifest already persisted."""

    run_id: str
    attempt_id: str
    plan_id: str
    project_id: str
    root: str
    run_state: RunState
    candidate_results: tuple[CandidateResult, ...]
    aggregate: ToolResult
    manifest_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "root": self.root,
            "run_state": self.run_state,
            "candidates": [item.to_dict() for item in self.candidate_results],
            "aggregate": dict(self.aggregate),
            "manifest_path": self.manifest_path,
        }


def _owned_engine_names() -> set[str]:
    owned: set[str] = set()
    for spec in TOOL_SPECS.values():
        owned.update(spec.engine_names)
    return owned


def _classify_tool(name: str, tools_by_name: dict[str, Any]) -> tuple[Disposition, str]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        # A tool registered outside the shared catalog inventory: still a
        # real, visible candidate -- never silently dropped -- classified as
        # a comprehensive static check by default.
        return "applicable", _STATIC_REASON
    if spec.category == "workflow":
        return "not_applicable", _NON_SCAN_REASON
    if spec.maturity == "importer":
        return "requires_input", _REPORT_INPUT_REASON
    if spec.maturity == "browser_runtime":
        return "requires_input", _DYNAMIC_TARGET_REASON
    tool = tools_by_name.get(name)
    required_option = getattr(tool, "required_option", None)
    if isinstance(tool, GuardedQualityTool) and required_option:
        return "requires_input", f"requires_{required_option}"
    return "applicable", _STATIC_REASON


def _classify_engine(name: str) -> tuple[Disposition, str]:
    spec = ENGINE_SPECS[name]
    if spec.capability == "workflow":
        return "not_applicable", _NON_SCAN_REASON
    return "applicable", _STATIC_REASON


def _candidate_category(name: str) -> str:
    spec = TOOL_SPECS.get(name)
    return spec.category if spec is not None else "unknown"


def _build_candidates(tools: list[Any]) -> list[ScanCandidate]:
    """Build candidate set from every canonical tool plus every engine row
    (plan §6.4). Deterministic, sorted order -- never depends on iteration
    order of `ALL_TOOLS`/`ENGINE_SPECS`."""
    tools_by_name = {tool.name: tool for tool in tools}
    candidates: list[ScanCandidate] = []

    for name in sorted(tools_by_name):
        disposition, reason = _classify_tool(name, tools_by_name)
        candidates.append(
            ScanCandidate(name, "tool", _candidate_category(name), disposition, reason)
        )

    owned = _owned_engine_names()
    for name in sorted(ENGINE_SPECS):
        if name in owned:
            continue
        disposition, reason = _classify_engine(name)
        candidates.append(
            ScanCandidate(
                name, "engine", ENGINE_SPECS[name].capability, disposition, reason
            )
        )
    return candidates


def plan_scan(
    project: str | Path,
    *,
    exclude: tuple[str, ...] = (),
    targets: dict[str, dict[str, Any]] | None = None,
    severity: str = "warn",
    concurrency: int = 2,
    timeout_seconds: int = 300,
    data_root: Path | None = None,
) -> ScanPlan:
    """Plan a full scan: every catalog candidate gets exactly one reasoned
    disposition (plan §3.2/§6.4) before any execution. Stages the plan under
    `<root>/.rush/scan_plans/<plan_id>.json` so `execute_scan` can later run
    it by `plan_id` alone (plan §6.1 `rush_scan.run(project,plan_id,install)`
    -- no other scan parameters travel with the run request)."""
    if (
        not isinstance(concurrency, int)
        or isinstance(concurrency, bool)
        or not (1 <= concurrency <= 8)
    ):
        raise ScanInvalidRequestError("concurrency must be an integer in 1..8")
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not (1 <= timeout_seconds <= 3600)
    ):
        raise ScanInvalidRequestError("timeout_seconds must be an integer in 1..3600")
    if severity not in ("info", "warn", "error"):
        raise ScanInvalidRequestError("severity must be info, warn, or error")

    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    targets = dict(targets or {})
    exclude = tuple(exclude or ())

    candidates = _build_candidates(list(ALL_TOOLS))
    known_ids = {candidate.candidate_id for candidate in candidates}

    unknown_targets = sorted(set(targets) - known_ids)
    if unknown_targets:
        raise ScanInvalidRequestError(
            f"unknown tool id(s) in targets: {unknown_targets}"
        )
    for tool_id, payload in targets.items():
        if not isinstance(payload, dict):
            raise ScanInvalidRequestError(f"targets[{tool_id!r}] must be an object")

    unknown_exclude = sorted(set(exclude) - known_ids)
    if unknown_exclude:
        raise ScanInvalidRequestError(
            f"unknown tool id(s) in exclude: {unknown_exclude}"
        )

    resolved: list[ScanCandidate] = []
    for candidate in candidates:
        if candidate.candidate_id in exclude:
            resolved.append(
                ScanCandidate(
                    candidate.candidate_id,
                    candidate.kind,
                    candidate.category,
                    "excluded_by_user",
                    "excluded_by_user",
                )
            )
        elif (
            candidate.candidate_id in targets
            and candidate.disposition == "requires_input"
        ):
            resolved.append(
                ScanCandidate(
                    candidate.candidate_id,
                    candidate.kind,
                    candidate.category,
                    "applicable",
                    _EXPLICIT_TARGET_REASON,
                )
            )
        else:
            resolved.append(candidate)

    plan_payload = {
        "project_id": record["project_id"],
        "root": str(root),
        "candidates": [candidate.to_dict() for candidate in resolved],
        "exclude": list(exclude),
        "targets": targets,
        "severity": severity,
        "concurrency": concurrency,
        "timeout_seconds": timeout_seconds,
    }
    plan_id = sha256(_canonical_json(plan_payload)).hexdigest()

    plan = ScanPlan(
        plan_id=plan_id,
        project_id=record["project_id"],
        root=str(root),
        candidates=tuple(resolved),
        exclude=exclude,
        targets=targets,
        severity=severity,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
    )

    staged = (
        json.dumps(plan.to_dict(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    atomic_write_bytes(root, _PLAN_RELATIVE.format(plan_id=plan_id), staged)

    return plan


def load_scan_plan(root: Path, plan_id: str) -> ScanPlan | None:
    """Load a previously staged plan by ID, or `None` if never planned."""
    path = root / ".rush" / "scan_plans" / f"{plan_id}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return ScanPlan.from_dict(payload)


def load_run_manifest(root: Path, run_id: str) -> dict[str, Any] | None:
    """Load the terminal manifest for `run_id`, or `None` if it never ran."""
    attempts_dir = root / ".rush" / "runs" / run_id / "attempts"
    if not attempts_dir.is_dir():
        return None
    attempts = sorted(p for p in attempts_dir.iterdir() if p.is_dir())
    if not attempts:
        return None
    manifest_path = attempts[-1] / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _finding_id(tool: str, engine: str | None, finding: Finding) -> str:
    """SHA256 of canonical `{tool,engine,rule,path,line,column,
    evidence_fingerprint}` (plan §3.3/§6.4)."""
    evidence = finding.get("fingerprint") or finding_fingerprint(
        str(finding.get("path", "")),
        finding.get("line", 0) or 0,
        finding.get("column", 0) or 0,
        str(finding.get("rule_id") or finding.get("rule") or ""),
        str(finding.get("severity", "")),
        str(finding.get("message", "")),
    )
    payload = {
        "tool": tool,
        "engine": engine,
        "rule": str(finding.get("rule") or finding.get("rule_id") or ""),
        "path": str(finding.get("path", "")),
        "line": int(finding.get("line", 0) or 0),
        "column": int(finding.get("column", 0) or 0),
        "evidence_fingerprint": evidence,
    }
    return sha256(_canonical_json(payload)).hexdigest()


def _execute_candidate(
    candidate: ScanCandidate,
    *,
    root: Path,
    permissions: ExecutionPermissions,
    targets: dict[str, dict[str, Any]],
    config: Any,
    tools_by_name: dict[str, Any],
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[ExecutionOutcome, ToolResult]:
    """Run exactly one applicable candidate exactly once. Never retries on
    exception (plan §3.3/§6.4: "no exception retry"); a raised exception
    becomes that candidate's own real `failed` child, never a dropped one.

    P65-08: a tool that exposes a duck-typed
    `run_cancellable(root, *, cancel_check)` is invoked through that method
    instead of the generic `InvocationExecutor` path, letting it interrupt
    its own owned subprocess mid-flight (via
    `rush.runtime.subprocesses.run_subprocess`'s optional `cancel_check`
    contract) rather than only at this function's own boundary. No catalog
    tool implements this today -- every existing `ALL_TOOLS` candidate keeps
    its exact prior behavior, unaffected."""
    if candidate.kind == "engine":
        # No `TOOL_SPECS` owner exists to invoke and normalize this engine's
        # output yet -- an honest, deterministic coverage gap, not a silent
        # exclusion (plan §6.4).
        return "unavailable", skipped_result(
            candidate.candidate_id, candidate.candidate_id, _ENGINE_ROUTE_MISSING
        )

    tool = tools_by_name[candidate.candidate_id]
    run_cancellable = getattr(tool, "run_cancellable", None)
    if cancel_check is not None and callable(run_cancellable):
        try:
            result = run_cancellable(root, cancel_check=cancel_check)
        except Exception as exc:  # noqa: BLE001 -- one real child result, zero retry
            return "failed", error_result(candidate.candidate_id, None, str(exc))
        if (result.get("metadata") or {}).get("cancelled"):
            return "cancelled", result
        status = result.get("status")
        if status == "error":
            return "failed", result
        if status == "skipped":
            summary = str(result.get("summary", ""))
            if "requires permission" in summary or "requires_" in summary:
                return "permission_blocked", result
            return "unavailable", result
        return "executed", result

    request: dict[str, Any] = {
        "operation_id": candidate.candidate_id,
        "path": str(root),
        **targets.get(candidate.candidate_id, {}),
    }
    try:
        executor = InvocationExecutor()
        executor.register(candidate.candidate_id, tool.__call__)
        context = resolve_invocation(
            request,
            transport="cli",
            workspace_root=root,
            config=config,
            permissions=permissions,
        )
        result = executor.execute(context)
    except Exception as exc:  # noqa: BLE001 -- one real child result, zero retry
        return "failed", error_result(candidate.candidate_id, None, str(exc))

    status = result.get("status")
    if status == "error":
        return "failed", result
    if status == "skipped":
        summary = str(result.get("summary", ""))
        if "requires permission" in summary or "requires_" in summary:
            return "permission_blocked", result
        return "unavailable", result
    return "executed", result


def _build_manifest(
    *,
    run_id: str,
    attempt_id: str,
    plan: ScanPlan,
    run_state: RunState,
    scheduled: list[CandidateResult],
    aggregate: ToolResult,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": plan.plan_id,
        "project_id": plan.project_id,
        "root": plan.root,
        "run_state": run_state,
        "severity": plan.severity,
        "concurrency": plan.concurrency,
        "timeout_seconds": plan.timeout_seconds,
        "created_at": datetime.now(UTC).isoformat(),
        "candidates": [candidate.to_dict() for candidate in plan.candidates],
        "scheduled": [item.to_dict() for item in scheduled],
        "aggregate": dict(aggregate),
        "totals": {
            "candidate_count": len(plan.candidates),
            "scheduled_count": len(scheduled),
            "executed_count": sum(
                1 for item in scheduled if item.outcome == "executed"
            ),
            "finding_count": len(aggregate.get("findings") or []),
        },
    }


def execute_scan(
    plan: ScanPlan,
    *,
    run_id: str | None = None,
    permissions: ExecutionPermissions | None = None,
    config: Any = None,
    data_root: Path | None = None,
) -> ScanRun:
    """Execute every `applicable` candidate exactly once, aggregate every
    scheduled child through the canonical `aggregate_results`, and persist
    one immutable terminal run manifest (plan §3.3/§6.4).

    `complete`/`completed` requires every scheduled candidate to reach
    `executed`; any `unavailable`/`permission_blocked`/`failed` outcome
    among the scheduled set leaves the run `incomplete` -- never reported
    `clean` from an installed-only subset (plan §5: "Do not mark ... a full
    scan clean from installed-only selection").

    P65-08: `run_id` is optional and, when given, lets a caller (e.g. a test
    or a long-lived MCP server handling a concurrent `cancel` call) know the
    run's identity before this call returns -- `cancel_scan_run` targets it
    by that same ID. `data_root` is accepted for signature symmetry with the
    rest of this module's `project`-taking entry points; `plan.root` is
    already the resolved filesystem root."""
    resolved_permissions = permissions or ExecutionPermissions()
    root = Path(plan.root)
    resolved_run_id = run_id or str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    return _execute_attempt(
        plan,
        root=root,
        run_id=resolved_run_id,
        attempt_id=attempt_id,
        permissions=resolved_permissions,
        config=config,
        already_completed={},
    )


def _execute_attempt(
    plan: ScanPlan,
    *,
    root: Path,
    run_id: str,
    attempt_id: str,
    permissions: ExecutionPermissions,
    config: Any,
    already_completed: dict[str, CandidateResult],
) -> ScanRun:
    """Shared attempt pipeline for both a fresh `execute_scan` and a
    `resume_scan_run` retry: persist the attempt header first (so a crash
    before the aggregate still leaves a recoverable `plan_id`/source
    signature), run whatever candidates aren't already retained, then
    finalize one immutable terminal manifest."""
    with _run_lock(root):
        _write_attempt_header(root, run_id, attempt_id, plan)
        _append_event(
            root, run_id, attempt_id, event="attempt_started", candidate_id=None
        )
        scheduled, cancelled = _run_candidates(
            plan,
            root=root,
            run_id=run_id,
            attempt_id=attempt_id,
            permissions=permissions,
            config=config,
            already_completed=already_completed,
        )
        return _finalize_attempt(
            root=root,
            run_id=run_id,
            attempt_id=attempt_id,
            plan=plan,
            scheduled=scheduled,
            cancelled=cancelled,
        )


def _run_candidates(
    plan: ScanPlan,
    *,
    root: Path,
    run_id: str,
    attempt_id: str,
    permissions: ExecutionPermissions,
    config: Any,
    already_completed: dict[str, CandidateResult],
) -> tuple[list[CandidateResult], bool]:
    """Run every scheduled candidate not already in `already_completed`
    (retained evidence from a prior attempt), persisting each finished
    candidate's own evidence file and an ordered progress event as it
    completes. Checks the run's cooperative cancel-request marker at every
    candidate boundary; a candidate itself finishing with outcome
    `cancelled` (its own owned subprocess interrupted mid-flight) also stops
    scheduling further candidates. Returns `(results_in_schedule_order,
    was_cancelled)`."""
    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    scheduled_candidates = sorted(
        (c for c in plan.candidates if c.disposition == "applicable"),
        key=lambda c: c.candidate_id,
    )

    def cancel_check() -> bool:
        return _cancel_requested(root, run_id)

    results: list[CandidateResult] = []
    cancelled = False
    for candidate in scheduled_candidates:
        if candidate.candidate_id in already_completed:
            results.append(already_completed[candidate.candidate_id])
            continue
        if cancel_check():
            cancelled = True
            break
        _append_event(
            root,
            run_id,
            attempt_id,
            event="candidate_started",
            candidate_id=candidate.candidate_id,
        )
        outcome, result = _execute_candidate(
            candidate,
            root=root,
            permissions=permissions,
            targets=plan.targets,
            config=config,
            tools_by_name=tools_by_name,
            cancel_check=cancel_check,
        )
        for finding in result.get("findings") or []:
            cast(dict[str, Any], finding)["finding_id"] = _finding_id(
                str(result.get("tool", candidate.candidate_id)),
                result.get("engine"),
                finding,
            )
        candidate_result = CandidateResult(
            candidate=candidate, outcome=outcome, result=result
        )
        results.append(candidate_result)
        _persist_candidate_evidence(root, run_id, attempt_id, candidate_result)
        _append_event(
            root,
            run_id,
            attempt_id,
            event="candidate_completed",
            candidate_id=candidate.candidate_id,
            outcome=outcome,
        )
        if outcome == "cancelled":
            cancelled = True
            break
    return results, cancelled


def _finalize_attempt(
    *,
    root: Path,
    run_id: str,
    attempt_id: str,
    plan: ScanPlan,
    scheduled: list[CandidateResult],
    cancelled: bool,
) -> ScanRun:
    children = [item.result for item in scheduled]
    aggregate = aggregate_results("scan", children)

    run_state: RunState
    if cancelled:
        run_state = "cancelled"
        metadata = dict(aggregate.get("metadata") or {})
        metadata["cancelled"] = True
        aggregate["metadata"] = metadata
    elif not scheduled:
        run_state = "completed"
        metadata = dict(aggregate.get("metadata") or {})
        metadata["coverage"] = {"empty": True}
        aggregate["metadata"] = metadata
    elif any(item.outcome != "executed" for item in scheduled):
        run_state = "incomplete"
    else:
        run_state = "completed"

    manifest = _build_manifest(
        run_id=run_id,
        attempt_id=attempt_id,
        plan=plan,
        run_state=run_state,
        scheduled=scheduled,
        aggregate=aggregate,
    )
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    manifest_path = atomic_write_bytes(
        root,
        _MANIFEST_RELATIVE.format(run_id=run_id, attempt_id=attempt_id),
        manifest_bytes,
    )
    _append_event(root, run_id, attempt_id, event=f"run_{run_state}", candidate_id=None)

    return ScanRun(
        run_id=run_id,
        attempt_id=attempt_id,
        plan_id=plan.plan_id,
        project_id=plan.project_id,
        root=str(root),
        run_state=run_state,
        candidate_results=tuple(scheduled),
        aggregate=aggregate,
        manifest_path=str(manifest_path),
    )


def _write_attempt_header(
    root: Path, run_id: str, attempt_id: str, plan: ScanPlan
) -> None:
    header = {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": plan.plan_id,
        "project_id": plan.project_id,
        "started_at": datetime.now(UTC).isoformat(),
        "source_signature": _source_signature(root),
    }
    body = json.dumps(header, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_bytes(
        root,
        _ATTEMPT_HEADER_RELATIVE.format(run_id=run_id, attempt_id=attempt_id),
        body,
    )


def _load_attempt_header(attempt_dir: Path) -> dict[str, Any] | None:
    path = attempt_dir / "attempt.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _candidate_evidence_relative(
    run_id: str, attempt_id: str, candidate_id: str
) -> str:
    digest = sha256(candidate_id.encode("utf-8")).hexdigest()[:24]
    return _CANDIDATE_EVIDENCE_RELATIVE.format(
        run_id=run_id, attempt_id=attempt_id, digest=digest
    )


def _persist_candidate_evidence(
    root: Path, run_id: str, attempt_id: str, candidate_result: CandidateResult
) -> None:
    """Immediately retained evidence for one finished candidate -- survives a
    real process death that happens after this candidate's own result but
    before the run's final aggregate/manifest write."""
    body = (
        json.dumps(candidate_result.to_dict(), indent=2, sort_keys=True).encode("utf-8")
        + b"\n"
    )
    atomic_write_bytes(
        root,
        _candidate_evidence_relative(
            run_id, attempt_id, candidate_result.candidate.candidate_id
        ),
        body,
    )


def _load_completed_candidates(attempt_dir: Path) -> dict[str, CandidateResult]:
    """Only genuinely `executed` candidates are retained across a resume --
    a `failed`/`unavailable`/`permission_blocked`/`cancelled` candidate is
    re-attempted, never permanently stuck at its prior non-terminal-for-
    coverage outcome."""
    candidates_dir = attempt_dir / "candidates"
    if not candidates_dir.is_dir():
        return {}
    retained: dict[str, CandidateResult] = {}
    for path in sorted(candidates_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("outcome") != "executed":
            continue
        candidate = ScanCandidate.from_dict(payload)
        retained[candidate.candidate_id] = CandidateResult(
            candidate=candidate,
            outcome="executed",
            result=cast("ToolResult", dict(payload.get("child") or {})),
        )
    return retained


def _events_relative(run_id: str, attempt_id: str) -> str:
    return _EVENTS_RELATIVE.format(run_id=run_id, attempt_id=attempt_id)


def _load_events(root: Path, run_id: str, attempt_id: str) -> list[dict[str, Any]]:
    path = root / ".rush" / "runs" / run_id / "attempts" / attempt_id / "events.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    events = payload.get("events") if isinstance(payload, dict) else None
    return list(events) if isinstance(events, list) else []


def _append_event(
    root: Path,
    run_id: str,
    attempt_id: str,
    *,
    event: str,
    candidate_id: str | None,
    outcome: str | None = None,
) -> None:
    """Per-run ordered progress events (plan §6.4, Phase 66 polling/
    streaming): a full-file atomic rewrite per event, reusing the same
    `atomic_write_bytes` primitive as every other durable write in this
    module -- never a partial/torn events file."""
    events = _load_events(root, run_id, attempt_id)
    entry = {
        "sequence": len(events) + 1,
        "event": event,
        "candidate_id": candidate_id,
        "outcome": outcome,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    events.append(entry)
    body = (
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "events": events,
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    atomic_write_bytes(root, _events_relative(run_id, attempt_id), body)


def _latest_attempt_dir(root: Path, run_id: str) -> Path | None:
    attempts_dir = root / ".rush" / "runs" / run_id / "attempts"
    if not attempts_dir.is_dir():
        return None
    attempt_dirs = sorted(p for p in attempts_dir.iterdir() if p.is_dir())
    return attempt_dirs[-1] if attempt_dirs else None


def load_scan_events(
    root: Path, run_id: str, attempt_id: str | None = None
) -> dict[str, Any]:
    """Public accessor (plan §6.4, Phase 66 polling/streaming): the ordered
    progress event sequence plus the current terminal state for `run_id`'s
    latest (or explicitly given) attempt."""
    if attempt_id is None:
        latest = _latest_attempt_dir(root, run_id)
        if latest is None:
            raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
        attempt_id = latest.name
    manifest = load_run_manifest(root, run_id)
    return {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "events": _load_events(root, run_id, attempt_id),
        "run_state": (manifest or {}).get("run_state"),
    }


def _cancel_request_path(root: Path, run_id: str) -> Path:
    return root / ".rush" / "runs" / run_id / "cancel_requested.json"


def _cancel_requested(root: Path, run_id: str) -> bool:
    return _cancel_request_path(root, run_id).is_file()


def _clear_cancel_request(root: Path, run_id: str) -> None:
    with suppress(OSError):
        _cancel_request_path(root, run_id).unlink()


def cancel_scan_run(
    project: str | Path, run_id: str, *, data_root: Path | None = None
) -> dict[str, Any]:
    """`rush_scan.cancel(project,run_id)` (plan §6.1/§6.4, P65-08). Writes a
    cross-process/cross-thread cooperative cancel-request marker under the
    run's own directory; the run's `execute_scan`/`resume_scan_run` loop
    checks it at every candidate boundary and, for a candidate whose tool
    supports mid-subprocess cancellation, during that candidate's own
    execution too. Idempotent: cancelling an already-cancel-requested (or
    already-terminal) run just re-writes the same marker."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    if not (root / ".rush" / "runs" / run_id).is_dir():
        raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
    payload = {"run_id": run_id, "requested_at": datetime.now(UTC).isoformat()}
    atomic_write_bytes(
        root,
        _CANCEL_REQUEST_RELATIVE.format(run_id=run_id),
        _canonical_json(payload) + b"\n",
    )
    return payload


def resume_scan_run(
    project: str | Path,
    run_id: str,
    *,
    permissions: ExecutionPermissions | None = None,
    config: Any = None,
    data_root: Path | None = None,
) -> ScanRun:
    """`rush_scan.resume(project,run_id)` (plan §6.1/§6.4, P65-08). Starts a
    new attempt under the *same* `run_id`, retaining every previously
    `executed` candidate's evidence and re-attempting everything else
    (never-started, `cancelled`, `failed`, `unavailable`, or
    `permission_blocked`). Denies a stale resume (`ScanResumeStaleError`) if
    the project's source changed since the run's most recent attempt
    started -- the same `_source_signature` staleness check
    `dispatch_handoff` already applies to a handoff's own project source.
    Always mints a fresh `attempt_id` on a valid retry; clears any pending
    cancel request so the new attempt starts clean."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    latest_attempt = _latest_attempt_dir(root, run_id)
    if latest_attempt is None:
        raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
    header = _load_attempt_header(latest_attempt)
    if header is None:
        raise ScanInvalidRequestError(
            f"run {run_id} has no recoverable attempt state to resume"
        )

    plan_id = header.get("plan_id")
    plan = load_scan_plan(root, str(plan_id)) if plan_id else None
    if plan is None:
        raise ScanPlanStaleError(f"run {run_id}'s plan {plan_id!r} is no longer staged")

    current_signature = _source_signature(root)
    if current_signature != header.get("source_signature"):
        raise ScanResumeStaleError(
            "project source changed since this run's last attempt started; "
            "resume refuses to apply"
        )

    already_completed = _load_completed_candidates(latest_attempt)
    _clear_cancel_request(root, run_id)

    resolved_permissions = permissions or ExecutionPermissions()
    new_attempt_id = str(uuid.uuid4())
    return _execute_attempt(
        plan,
        root=root,
        run_id=run_id,
        attempt_id=new_attempt_id,
        permissions=resolved_permissions,
        config=config,
        already_completed=already_completed,
    )


HandoffState = Literal[
    "prepared", "delivered", "acknowledged", "agent_reported_complete"
]
RescanVerdict = Literal["resolved", "persisting", "new", "unverified"]

_HANDOFF_RELATIVE = ".rush/handoffs/{handoff_id}.json"
_HANDOFF_ENCODING = "cl100k_base"
_HANDOFF_EXCERPT_CHARS = 200
_SEVERITY_RANK: dict[str, int] = {"error": 0, "warn": 1, "info": 2}


class ScanHandoffSourceChangedError(ScanError):
    """Refuses to apply a handoff whose project source changed since prepare
    (plan §6.1/§6.4: "stale source identity refuses apply", `SOURCE_CHANGED`)."""

    code = "SOURCE_CHANGED"


class ScanHandoffInvalidStateError(ScanError):
    """Raised when a handoff operation is called out of its required lifecycle
    order (e.g. `acknowledge` before `dispatch` ever delivered it)."""

    code = "INVALID_STATE"


class ScanHandoffAuthError(ScanError):
    """Raised for a wrong/expired `session_capability` or `delivery_nonce`."""

    code = "E_PERMISSION"


def _source_signature(root: Path) -> str:
    """Deterministic fingerprint of every tracked file's path/size/mtime under
    `root` (excluding Rush's own `.rush`/`.git` state) -- detects a project
    mutated between a scan run and a later handoff dispatch or rescan (plan
    §6.1/§6.4: "stale source identity refuses apply", `SOURCE_CHANGED`)."""
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in (".rush", ".git"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(f"{rel.as_posix()}:{stat.st_size}:{stat.st_mtime_ns}")
    return sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _measure_packet(items: list[dict[str, Any]]) -> tuple[int, int]:
    text = json.dumps({"findings": items}, sort_keys=True, separators=(",", ":"))
    encoding = tiktoken.get_encoding(_HANDOFF_ENCODING)
    return len(text.encode("utf-8")), len(encoding.encode(text))


def _severity_rank(finding: dict[str, Any]) -> int:
    return _SEVERITY_RANK.get(str(finding.get("severity", "warn")), 1)


def _finding_reference(finding: dict[str, Any]) -> dict[str, Any]:
    message = str(finding.get("message", ""))
    return {
        "finding_id": finding.get("finding_id"),
        "reference_only": True,
        "path": finding.get("path"),
        "line": finding.get("line"),
        "rule": finding.get("rule") or finding.get("rule_id"),
        "severity": finding.get("severity"),
        "provenance": finding.get("provenance"),
        "excerpt": message[:_HANDOFF_EXCERPT_CHARS],
        "excerpt_truncated": len(message) > _HANDOFF_EXCERPT_CHARS,
    }


def _build_packet(
    findings: list[dict[str, Any]], *, max_tokens: int, max_bytes: int
) -> dict[str, Any]:
    """Budget-fitting compact packet (plan §6.4): severity-descending then
    canonical-finding-ID order; the full record while it still fits; a
    bounded-excerpt reference (never a mid-character UTF-8 truncation --
    Python string slicing always lands on a whole code point) once the full
    record does not; and a bare `remainder_ids` pointer -- never a silently
    dropped selection -- once even a reference stops fitting. Counts the
    entire serialized payload, never only finding messages."""
    ordered = sorted(
        findings, key=lambda f: (_severity_rank(f), str(f.get("finding_id", "")))
    )

    floor_bytes, floor_tokens = _measure_packet([])
    if floor_bytes > max_bytes or floor_tokens > max_tokens:
        raise ScanInvalidRequestError(
            "max_tokens/max_bytes too small to fit even an empty packet"
        )

    items: list[dict[str, Any]] = []
    remainder_ids: list[str] = []
    for finding in ordered:
        trial_bytes, trial_tokens = _measure_packet([*items, finding])
        if trial_bytes <= max_bytes and trial_tokens <= max_tokens:
            items.append(finding)
            continue
        reference = _finding_reference(finding)
        trial_bytes, trial_tokens = _measure_packet([*items, reference])
        if trial_bytes <= max_bytes and trial_tokens <= max_tokens:
            items.append(reference)
        else:
            remainder_ids.append(str(finding.get("finding_id")))

    packet_bytes, packet_tokens = _measure_packet(items)
    return {
        "items": items,
        "remainder_ids": remainder_ids,
        "tokens": packet_tokens,
        "bytes": packet_bytes,
        "encoding": _HANDOFF_ENCODING,
        "max_tokens": max_tokens,
        "max_bytes": max_bytes,
    }


@dataclass(frozen=True)
class ScanHandoff:
    """One bounded agent handoff (plan §6.1 `rush_scan_handoff`). `packet` is
    the budget-fitting compact view the agent actually receives; the exact
    selected records (`finding_ids`) are preserved unmodified as one typed
    artifact (`artifact_id`/`artifact_version`) so a truncated excerpt never
    loses the original evidence."""

    handoff_id: str
    run_id: str
    project_id: str
    root: str
    agent_id: str
    state: HandoffState
    finding_ids: tuple[str, ...]
    packet: dict[str, Any]
    artifact_id: str
    artifact_version: int
    source_signature: str
    memory_session_id: str
    session_capability: str
    delivery_nonce: str
    granted_actions: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    agent_reported_complete_artifact_ids: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "root": self.root,
            "agent_id": self.agent_id,
            "state": self.state,
            "finding_ids": list(self.finding_ids),
            "packet": self.packet,
            "artifact_id": self.artifact_id,
            "artifact_version": self.artifact_version,
            "source_signature": self.source_signature,
            "memory_session_id": self.memory_session_id,
            "session_capability": self.session_capability,
            "delivery_nonce": self.delivery_nonce,
            "granted_actions": list(self.granted_actions),
            "acceptance_checks": list(self.acceptance_checks),
            "agent_reported_complete_artifact_ids": list(
                self.agent_reported_complete_artifact_ids
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> ScanHandoff:
        return ScanHandoff(
            handoff_id=str(payload["handoff_id"]),
            run_id=str(payload["run_id"]),
            project_id=str(payload["project_id"]),
            root=str(payload["root"]),
            agent_id=str(payload["agent_id"]),
            state=payload["state"],
            finding_ids=tuple(payload.get("finding_ids") or ()),
            packet=dict(payload.get("packet") or {}),
            artifact_id=str(payload["artifact_id"]),
            artifact_version=int(payload["artifact_version"]),
            source_signature=str(payload["source_signature"]),
            memory_session_id=str(payload["memory_session_id"]),
            session_capability=str(payload["session_capability"]),
            delivery_nonce=str(payload["delivery_nonce"]),
            granted_actions=tuple(payload.get("granted_actions") or ()),
            acceptance_checks=tuple(payload.get("acceptance_checks") or ()),
            agent_reported_complete_artifact_ids=tuple(
                payload.get("agent_reported_complete_artifact_ids") or ()
            ),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
        )


def _handoff_path(root: Path, handoff_id: str) -> Path:
    return root / ".rush" / "handoffs" / f"{handoff_id}.json"


def _load_handoff(root: Path, handoff_id: str) -> ScanHandoff | None:
    path = _handoff_path(root, handoff_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return ScanHandoff.from_dict(payload)


def _persist_handoff(root: Path, handoff: ScanHandoff) -> None:
    body = (
        json.dumps(handoff.to_dict(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    atomic_write_bytes(
        root, _HANDOFF_RELATIVE.format(handoff_id=handoff.handoff_id), body
    )


def build_handoff(
    project: str | Path,
    run_id: str,
    agent_id: str,
    *,
    finding_ids: tuple[str, ...] = (),
    max_tokens: int = 2048,
    max_bytes: int = 8192,
    acceptance_checks: tuple[str, ...] = (),
    granted_actions: tuple[str, ...] = (),
    data_root: Path | None = None,
) -> ScanHandoff:
    """`rush_scan_handoff.prepare` (plan §6.1, F35). Empty `finding_ids`
    selects every finding on `run_id`'s aggregate. Preserves the exact
    selected finding records (never deduplicated by rule/location -- two
    engines flagging the same real issue keep two distinct provenance
    records) as one typed artifact before building the agent-facing compact
    packet, then opens a real Phase63 handoff transport session
    (`rush.memory.handoff.prepare_handoff`) over that one artifact. Writes an
    immutable packet and `delivery_nonce`, state `prepared` -- never
    `delivered` until `dispatch_handoff` gets an actual transport
    acceptance."""
    if not agent_id:
        raise ScanInvalidRequestError("build_handoff requires agent_id")
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    manifest = load_run_manifest(root, run_id)
    if manifest is None:
        raise ScanInvalidRequestError(f"unknown run_id: {run_id}")

    all_findings = [
        dict(f) for f in (manifest.get("aggregate") or {}).get("findings") or []
    ]
    by_id = {str(f.get("finding_id")): f for f in all_findings if f.get("finding_id")}

    if finding_ids:
        unknown = sorted(set(finding_ids) - set(by_id))
        if unknown:
            raise ScanInvalidRequestError(f"unknown finding_id(s): {unknown}")
        selected = [by_id[fid] for fid in finding_ids]
    else:
        selected = all_findings
    if not selected:
        raise ScanInvalidRequestError("no findings available to hand off")

    packet = _build_packet(selected, max_tokens=max_tokens, max_bytes=max_bytes)

    handoff_id = str(uuid.uuid4())
    store = TypedArtifactStore(root)
    artifact = store.write(
        MemoryArtifact(
            id=f"scan-handoff-{handoff_id}",
            family="handoff",
            subject="active_context",
            trust_tier="DERIVED",
            content={"run_id": run_id, "agent_id": agent_id, "findings": selected},
            source=str(root),
            created_at=time.time(),
            symbol_ref=f"scan_handoff:{handoff_id}",
        )
    )

    try:
        session, session_capability, _delta = prepare_handoff(
            store,
            root=root,
            audience=agent_id,
            granted_ids=[artifact.id],
            session_allowlist=[str(root)],
            constraints={
                "run_id": run_id,
                "acceptance_checks": list(acceptance_checks),
                "granted_actions": list(granted_actions),
            },
        )
    except HandoffError as exc:
        raise ScanHandoffAuthError(str(exc)) from exc

    now = datetime.now(UTC).isoformat()
    handoff = ScanHandoff(
        handoff_id=handoff_id,
        run_id=run_id,
        project_id=record["project_id"],
        root=str(root),
        agent_id=agent_id,
        state="prepared",
        finding_ids=tuple(str(f.get("finding_id")) for f in selected),
        packet=packet,
        artifact_id=artifact.id,
        artifact_version=artifact.artifact_version,
        source_signature=_source_signature(root),
        memory_session_id=session.session_id,
        session_capability=session_capability,
        delivery_nonce=secrets.token_urlsafe(32),
        granted_actions=tuple(granted_actions),
        acceptance_checks=tuple(acceptance_checks),
        created_at=now,
        updated_at=now,
    )
    _persist_handoff(root, handoff)
    return handoff


def dispatch_handoff(
    project: str | Path,
    handoff_id: str,
    session_capability: str,
    *,
    data_root: Path | None = None,
) -> ScanHandoff:
    """`rush_scan_handoff.dispatch`. Refuses to apply a handoff whose project
    source changed since `prepare` (`SOURCE_CHANGED`), then reaches
    `delivered` only on an actual Phase63 transport acceptance
    (`rush.memory.handoff.receive_handoff`'s real read-back) -- never a
    fictional external send API."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    handoff = _load_handoff(root, handoff_id)
    if handoff is None:
        raise ScanInvalidRequestError(f"unknown handoff_id: {handoff_id}")
    if handoff.state != "prepared":
        raise ScanHandoffInvalidStateError(
            f"dispatch requires state 'prepared', got {handoff.state!r}"
        )
    if _source_signature(root) != handoff.source_signature:
        raise ScanHandoffSourceChangedError(
            "project source changed since this handoff was prepared; refuses to apply"
        )
    if not hmac.compare_digest(session_capability, handoff.session_capability):
        raise ScanHandoffAuthError("invalid session_capability")

    store = TypedArtifactStore(root)
    try:
        receive_handoff(
            store, session_id=handoff.memory_session_id, capability=session_capability
        )
    except HandoffError as exc:
        raise ScanHandoffAuthError(str(exc)) from exc

    updated = replace(
        handoff, state="delivered", updated_at=datetime.now(UTC).isoformat()
    )
    _persist_handoff(root, updated)
    return updated


def status_handoff(
    project: str | Path, handoff_id: str, *, data_root: Path | None = None
) -> dict[str, Any]:
    """`rush_scan_handoff.status`. Never reveals `session_capability`/
    `delivery_nonce` -- status is a plain read, not a re-authentication."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    handoff = _load_handoff(root, handoff_id)
    if handoff is None:
        raise ScanInvalidRequestError(f"unknown handoff_id: {handoff_id}")
    payload = handoff.to_dict()
    for secret_field in ("session_capability", "delivery_nonce", "memory_session_id"):
        payload.pop(secret_field, None)
    return payload


def acknowledge_handoff(
    project: str | Path,
    handoff_id: str,
    delivery_nonce: str,
    *,
    data_root: Path | None = None,
) -> ScanHandoff:
    """`rush_scan_handoff.acknowledge`. Validates nonce/session/project and
    marks `acknowledged` -- never auto-transitions on its own, so a handoff
    that was delivered but never acknowledged stays exactly `delivered`."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    handoff = _load_handoff(root, handoff_id)
    if handoff is None:
        raise ScanInvalidRequestError(f"unknown handoff_id: {handoff_id}")
    if handoff.project_id != record["project_id"]:
        raise ScanHandoffAuthError("handoff does not belong to this project")
    if handoff.state != "delivered":
        raise ScanHandoffInvalidStateError(
            f"acknowledge requires state 'delivered', got {handoff.state!r}"
        )
    if not hmac.compare_digest(delivery_nonce, handoff.delivery_nonce):
        raise ScanHandoffAuthError("invalid delivery_nonce")

    updated = replace(
        handoff, state="acknowledged", updated_at=datetime.now(UTC).isoformat()
    )
    _persist_handoff(root, updated)
    return updated


def complete_handoff(
    project: str | Path,
    handoff_id: str,
    delivery_nonce: str,
    *,
    artifact_ids: tuple[str, ...] = (),
    data_root: Path | None = None,
) -> ScanHandoff:
    """`rush_scan_handoff.complete`. Records the agent's own completion claim
    as `agent_reported_complete` -- never a verified fix. Only a later
    `compare_runs`/`rescan_project_run` against real rescan evidence can mark
    a finding `resolved` (plan: "Never auto-promote agent claims to verified
    fixes")."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    handoff = _load_handoff(root, handoff_id)
    if handoff is None:
        raise ScanInvalidRequestError(f"unknown handoff_id: {handoff_id}")
    if handoff.state != "acknowledged":
        raise ScanHandoffInvalidStateError(
            f"complete requires state 'acknowledged', got {handoff.state!r}"
        )
    if not hmac.compare_digest(delivery_nonce, handoff.delivery_nonce):
        raise ScanHandoffAuthError("invalid delivery_nonce")

    updated = replace(
        handoff,
        state="agent_reported_complete",
        agent_reported_complete_artifact_ids=tuple(artifact_ids),
        updated_at=datetime.now(UTC).isoformat(),
    )
    _persist_handoff(root, updated)
    return updated


def _finding_tool(finding: dict[str, Any]) -> str | None:
    provenance = finding.get("provenance")
    if not isinstance(provenance, str) or "/" not in provenance:
        return None
    return provenance.split("/", 1)[0]


def compare_runs(
    project: str | Path,
    baseline_run_id: str,
    current_run_id: str,
    *,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Rescan comparison (plan §6.1/§6.4, F35): marks every baseline finding
    `resolved`, `persisting`, or `unverified`, and every current-only finding
    `new`. Resolves a prior finding only when the same tool/engine (its
    finding's own `provenance`, plan §3.3) actually reached `executed`
    coverage in the current run and no longer reports it; a missing,
    permission-blocked, or failed engine can never make a finding `resolved`
    -- it stays `unverified` (plan: "a missing engine cannot make a finding
    resolved")."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    baseline = load_run_manifest(root, baseline_run_id)
    current = load_run_manifest(root, current_run_id)
    if baseline is None:
        raise ScanInvalidRequestError(f"unknown run_id: {baseline_run_id}")
    if current is None:
        raise ScanInvalidRequestError(f"unknown run_id: {current_run_id}")

    baseline_findings = {
        str(f["finding_id"]): f
        for f in (baseline.get("aggregate") or {}).get("findings") or []
        if f.get("finding_id")
    }
    current_findings = {
        str(f["finding_id"]): f
        for f in (current.get("aggregate") or {}).get("findings") or []
        if f.get("finding_id")
    }
    current_outcomes = {
        str(item["candidate_id"]): item["outcome"]
        for item in current.get("scheduled") or []
    }

    verdicts: dict[str, RescanVerdict] = {}
    for finding_id, finding in baseline_findings.items():
        tool = _finding_tool(finding)
        if tool is None or current_outcomes.get(tool) != "executed":
            verdicts[finding_id] = "unverified"
        elif finding_id in current_findings:
            verdicts[finding_id] = "persisting"
        else:
            verdicts[finding_id] = "resolved"
    for finding_id in current_findings:
        if finding_id not in baseline_findings:
            verdicts[finding_id] = "new"

    by_verdict: dict[str, list[str]] = {
        "resolved": [],
        "persisting": [],
        "new": [],
        "unverified": [],
    }
    for finding_id, verdict in verdicts.items():
        by_verdict[verdict].append(finding_id)
    for ids in by_verdict.values():
        ids.sort()

    comparison: dict[str, Any] = {
        "baseline_run_id": baseline_run_id,
        "current_run_id": current_run_id,
        "verdicts": verdicts,
    }
    comparison.update(by_verdict)
    return comparison


def rescan_project_run(
    project: str | Path,
    run_id: str,
    *,
    permissions: ExecutionPermissions | None = None,
    config: Any = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """`rush_scan.rescan(project,run_id)` (plan §6.1): re-executes `run_id`'s
    own staged plan against the project's *current* source and compares the
    fresh run against `run_id` via `compare_runs`. New source is expected
    here (unlike `dispatch_handoff`/stale resume, which forbid it) -- a
    rescan's entire purpose is re-evaluating changed source."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    baseline = load_run_manifest(root, run_id)
    if baseline is None:
        raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
    plan_id = baseline.get("plan_id")
    plan = load_scan_plan(root, str(plan_id)) if plan_id else None
    if plan is None:
        raise ScanPlanStaleError(f"run {run_id}'s plan {plan_id!r} is no longer staged")

    run = execute_scan(
        plan, permissions=permissions, config=config, data_root=data_root
    )
    comparison = compare_runs(project, run_id, run.run_id, data_root=data_root)
    return {"run": run.to_dict(), "comparison": comparison}


__all__ = [
    "CandidateResult",
    "RescanVerdict",
    "ScanBusyError",
    "ScanCandidate",
    "ScanError",
    "ScanHandoff",
    "ScanHandoffAuthError",
    "ScanHandoffInvalidStateError",
    "ScanHandoffSourceChangedError",
    "ScanInvalidRequestError",
    "ScanPlan",
    "ScanPlanStaleError",
    "ScanResumeStaleError",
    "ScanRun",
    "acknowledge_handoff",
    "build_handoff",
    "cancel_scan_run",
    "compare_runs",
    "complete_handoff",
    "dispatch_handoff",
    "execute_scan",
    "load_run_manifest",
    "load_scan_events",
    "load_scan_plan",
    "plan_scan",
    "rescan_project_run",
    "resume_scan_run",
    "status_handoff",
]
