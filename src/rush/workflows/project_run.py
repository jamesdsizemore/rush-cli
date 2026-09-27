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

import fcntl
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import tiktoken

from rush.catalog import ENGINE_SPECS, TOOL_SPECS
from rush.engines.staging import (
    PROVENANCE_FORMAT,
    active_staging,
    aggregate_content_identity,
    remap_paths,
    stage_inventory,
    staging_scope,
)
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.memory.handoff import (
    HandoffError,
    prepare_handoff,
    receive_handoff,
    recover_session_delta_without_capability,
)
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.runtime.filesystem import atomic_write_bytes
from rush.tools import ALL_TOOLS
from rush.tools.base import Finding, ToolResult
from rush.tools.common import (
    error_result,
    finding_fingerprint,
    run_engine,
    skipped_result,
)
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
_GENERATION_RELATIVE = ".rush/runs/{run_id}/.generation"
_EVENTS_RELATIVE = ".rush/runs/{run_id}/attempts/{attempt_id}/events.json"
_CANDIDATE_EVIDENCE_RELATIVE = (
    ".rush/runs/{run_id}/attempts/{attempt_id}/candidates/{digest}.json"
)
_CANCEL_REQUEST_RELATIVE = (
    ".rush/runs/{run_id}/attempts/{attempt_id}/cancel_requested.json"
)
_PLAN_RELATIVE = ".rush/scan_plans/{plan_id}.json"

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
    """Scan-exclusion lock over one project's run directory (P69-01
    subsection h): a real kernel-held `fcntl.flock`, not the prior
    `O_CREAT|O_EXCL`-plus-age-based-staleness scheme, which unlinked a lock
    file purely on elapsed time with no check of whether its holder was
    still alive -- letting a second process steal a still-live scan's lock.
    Held only for the duration of an actual scan (acquired here, released
    on exit from this context, including a crash: the kernel releases the
    lock the instant the holding process exits, no staleness window). The
    5s acquisition-attempt timeout (`ScanBusyError`) is unchanged, and is
    purely a waiting caller's own patience -- decoupled from any staleness
    concept, since there is none anymore.

    POSIX only (`fcntl.flock`) -- the real Windows-equivalent named-mutex
    primitive named in the plan is not implemented here.
    """
    lock_dir = root / ".rush" / "runs"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / ".scan.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    start = time.monotonic()
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() - start >= timeout:
                os.close(fd)
                raise ScanBusyError(
                    f"timed out after {timeout}s waiting for the scan run lock"
                ) from None
            time.sleep(_LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


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
    #: P69-03e: the per-file content digests of the staged bytes this
    #: candidate actually ran against -- every key here is a real
    #: project-relative path. Persisted with the candidate's evidence so a
    #: resume that *retains* this candidate carries its original digests
    #: forward verbatim instead of manufacturing a fresh consumption event for
    #: content nothing re-read.
    consumed_path_digests: dict[str, str] = field(default_factory=dict)
    #: M13: a repository-state engine's (GitGuard/DiffCover/Undercover) own
    #: synthetic `candidate_id:kind` -> digest evidence. Never a real path --
    #: kept in a separate field so it can never reach `git_link.path_digests`
    #: (`projects.py`'s Git lookup treats every `path_digests` key as a
    #: literal `git show commit:path` argument), while still folding into
    #: `_source_identity`'s aggregate content identity under its own domain
    #: tag.
    repository_state_evidence: dict[str, str] = field(default_factory=dict)
    #: M12: this candidate's own immutable copy of every declared artifact's
    #: bytes, captured immediately after `_execute_candidate` returns (see
    #: `_capture_artifact_snapshots`) -- before the next candidate, or a
    #: later attempt's candidate, can run and physically overwrite the same
    #: absolute staged/live path a declared artifact currently points at.
    #: Keyed by the exact declared path string in `ToolResult.artifacts`
    #: (never rewritten -- aggregate consumers still see the same
    #: canonical `list[str]` they always did). `_load_completed_candidates`
    #: reloads this verbatim on resume, so a retained candidate keeps
    #: pointing at its own original bytes forever.
    artifact_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.candidate.to_dict(),
            "outcome": self.outcome,
            "child": dict(self.result),
            "consumed_path_digests": dict(self.consumed_path_digests),
            "repository_state_evidence": dict(self.repository_state_evidence),
            "artifact_snapshots": {
                path: dict(entry) for path, entry in self.artifact_snapshots.items()
            },
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


def load_run_manifest(
    root: Path, run_id: str, *, attempt_id: str | None = None
) -> dict[str, Any] | None:
    """Load the terminal manifest for `run_id`'s given `attempt_id`, or its
    highest-generation (latest) attempt when `attempt_id` is omitted (plan
    §6.4/P69-02m, mirroring `load_scan_events()`'s existing `attempt_id`
    parameter). `None` if it never ran, or the requested attempt never
    reached a terminal manifest."""
    if attempt_id is not None:
        manifest_path = (
            root / ".rush" / "runs" / run_id / "attempts" / attempt_id / "manifest.json"
        )
    else:
        selected = _highest_generation_attempt_dir(root, run_id)
        if selected is None:
            return None
        manifest_path = selected / "manifest.json"
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


_ARTIFACT_SNAPSHOT_RELATIVE = (
    ".rush/runs/{run_id}/attempts/{attempt_id}/artifacts/{digest}/{index}.bin"
)


def _capture_artifact_snapshots(
    root: Path,
    run_id: str,
    attempt_id: str,
    candidate_id: str,
    result: ToolResult,
) -> dict[str, dict[str, Any]]:
    """M12 Fix item 1: copy each declared artifact's bytes into this
    attempt's own contained artifact directory immediately -- before the
    next candidate (or a later attempt's candidate) can run and physically
    overwrite the same absolute staged/live path a declared artifact
    currently points at. Reads whatever path `ToolResult.artifacts` already
    declares, verbatim; never rewrites that canonical `list[str]` (aggregate
    consumers still see exactly what they always did). Missing/unreadable
    declared paths are skipped, never a live-file fallback at read time --
    a candidate that declared an artifact this call could not snapshot
    simply has no entry for it below."""
    snapshots: dict[str, dict[str, Any]] = {}
    for index, declared in enumerate(result.get("artifacts") or []):
        if not isinstance(declared, str) or not declared:
            continue
        source = Path(declared)
        if not source.is_file():
            continue
        try:
            data = source.read_bytes()
        except OSError:
            continue
        digest = sha256(candidate_id.encode("utf-8")).hexdigest()[:24]
        relative = _ARTIFACT_SNAPSHOT_RELATIVE.format(
            run_id=run_id, attempt_id=attempt_id, digest=digest, index=index
        )
        atomic_write_bytes(root, relative, data)
        media_type = mimetypes.guess_type(declared)[0] or "application/octet-stream"
        snapshots[declared] = {
            "immutable_path": relative,
            "size": len(data),
            "sha256": sha256(data).hexdigest(),
            "media_type": media_type,
        }
    return snapshots


def _execute_candidate(
    candidate: ScanCandidate,
    *,
    root: Path,
    permissions: ExecutionPermissions,
    targets: dict[str, dict[str, Any]],
    config: Any,
    tools_by_name: dict[str, Any],
    cancel_check: Callable[[], bool] | None = None,
    owner_instance_id: str | None = None,
    run_id: str | None = None,
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
        # M17: route through the canonical `rush.engines.ENGINES`/
        # `rush.catalog.ENGINE_SPECS` pair -- a registered engine with no
        # `TOOL_SPECS` owner is still executed through the exact same shared
        # `run_engine` every owning tool uses, never a dummy owning tool or
        # an invented permission grant. `EngineSpec` carries no permission
        # field, so a route reaching here (already filtered to `applicable`
        # by `_classify_engine` at plan time) is read-only:
        # `required_permissions=ExecutionPermissions()` (all ungranted, all
        # unneeded) -- a genuinely privileged unowned engine stays
        # `requires_input`/`unsupported` at classification and never
        # schedules as `applicable` in the first place.
        from rush.engines import ENGINES

        engine = ENGINES.get(candidate.candidate_id)
        if engine is None:
            # A registered `ENGINE_SPECS` row with no matching `ENGINES`
            # entry: a genuine catalog/registry mismatch, not a route this
            # fix can resolve -- stays the same honest, deterministic gap.
            return "unavailable", skipped_result(
                candidate.candidate_id, candidate.candidate_id, _ENGINE_ROUTE_MISSING
            )
        result = run_engine(
            engine,
            root,
            [],
            tool_name=candidate.candidate_id,
            required_permissions=ExecutionPermissions(),
            permissions=permissions,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
        )
        status = result.get("status")
        if status == "error":
            return "failed", result
        if status == "skipped":
            summary = str(result.get("summary", ""))
            if "requires permission" in summary or "requires_" in summary:
                return "permission_blocked", result
            return "unavailable", result
        return "executed", result

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
    # P69-01.2j: structural ownership travels with the request, so the
    # invocation layer binds it onto `tool.__call__` by name and each
    # engine's own `run_subprocess()` call is fenced and reapable.
    if owner_instance_id is not None and run_id is not None:
        request["owner_instance_id"] = owner_instance_id
        request["run_id"] = run_id
    # M15: a direct in-process reader (slop, offline-review, dead-asset,
    # license-matrix, and other applicable direct readers) previously called
    # `resolve_invocation` against the live project root even while a scan
    # attempt had staged its bounded inventory -- only nested `run_engine`
    # invocations (runtime/subprocesses.py's `_staged_invocation`) redirected
    # to staging. Mirror that exact pattern here: redirect the request's own
    # path-bearing fields and `InvocationContext.workspace_root` to the
    # staged tree, record the read as consumed staged content, and remap any
    # staged paths the result carries back to logical paths before this
    # candidate's finding IDs/evidence are computed by the caller. A call
    # made outside a staged attempt (`active_staging()` is `None`) is
    # unaffected -- today's exact behavior byte for byte.
    # T8: capture the logical (pre-staging) path-bearing values verbatim,
    # before any staging substitution below rewrites them to the staged
    # tree -- diagnostics keep the original request even though execution
    # identity/cache identity below stays the staged/normalized value.
    # Finding 8: derive originals only from this candidate's own explicit
    # override (`targets[candidate.candidate_id]`), never from the merged
    # `request` dict -- `request["path"]` is always populated (falls back to
    # `str(root)`, the resolved registered root, when no override exists),
    # so reading it here would record that resolved root as a fabricated
    # "original request" whenever a caller supplied no real one.
    candidate_override = targets.get(candidate.candidate_id, {})
    original_targets: list[str] = []
    for key in ("path", "file", "filename"):
        value = candidate_override.get(key)
        if isinstance(value, str):
            original_targets.append(value)
    for key in ("files", "paths"):
        values = candidate_override.get(key)
        if isinstance(values, (list, tuple)):
            original_targets.extend(str(v) for v in values)

    staging = active_staging()
    staged_root = root
    if staging is not None:
        staged_root = staging.stage_path(root) or root
        for key in ("path", "file", "filename"):
            value = request.get(key)
            if isinstance(value, str):
                mapped = staging.stage_path(Path(value))
                if mapped is not None:
                    request[key] = str(mapped)
        for key in ("files", "paths"):
            values = request.get(key)
            if isinstance(values, (list, tuple)):
                request[key] = [str(staging.stage_path(Path(v)) or v) for v in values]
        staging.record_consumption(staged_root)
    try:
        executor = InvocationExecutor()
        executor.register(candidate.candidate_id, tool.__call__)
        context = resolve_invocation(
            request,
            transport="cli",
            workspace_root=staged_root,
            config=config,
            permissions=permissions,
            original_requested_targets=tuple(original_targets) or None,
        )
        result = executor.execute(context)
        if staging is not None:
            remap_paths(result, staging.staged_root, staging.original_root)
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
    source_identity: dict[str, Any] | None = None,
    digests: dict[str, str] | None = None,
    file_inventory: list[dict[str, str]] | None = None,
    staging_failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # P69-07.2b: the persisted Git-link provenance a later Git-section reader
    # uses to decide whether this attempt's output can be linked to a
    # specific commit -- reuses `source_identity["git"]` verbatim (the exact
    # `_git_link()` result already computed for `source_identity`) plus the
    # same per-path digest set, never a second, independently computed Git
    # read that could drift from `source_identity`'s own snapshot.
    git_link = dict((source_identity or {}).get("git") or {"repository": False})
    git_link["path_digests"] = dict(digests or {})
    return {
        "schema_version": 1,
        "run_id": run_id,
        # P69-03d/j: the format-tagged consumption identity, written only once
        # a scan has actually executed -- never the pre-execution signature the
        # attempt header carries, and never comparable to one.
        "source_identity": source_identity or {},
        "git_link": git_link,
        # M03: the exact bounded inventory captured at attempt start --
        # hydration (`dashboard/server.py::_hydrate_published_scan`) reads
        # this instead of rewalking whatever files happen to be present now.
        "file_inventory": file_inventory or [],
        # M21 bullet 3: every staging input/configuration failure, structured
        # -- never silently absent from the terminal manifest.
        "staging_failures": staging_failures or [],
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
    attempt_id: str | None = None,
    permissions: ExecutionPermissions | None = None,
    config: Any = None,
    data_root: Path | None = None,
    owner_instance_id: str | None = None,
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
    already the resolved filesystem root.

    P69-01.2j: `owner_instance_id` is the caller's own executor identity (the
    TUI's or the dashboard server's), threaded all the way down to each
    engine's `run_subprocess()` call so a crash of this process leaves a
    durable, reapable record of every subprocess it started.

    P69-02d: `attempt_id` mirrors `run_id`'s own preallocation pattern -- a
    dispatcher that must return this attempt's real id before its own
    background thread runs (e.g. a 202 response) mints it here instead of
    letting this call mint its own."""
    resolved_permissions = permissions or ExecutionPermissions()
    root = Path(plan.root)
    resolved_run_id = run_id or str(uuid.uuid4())
    resolved_attempt_id = attempt_id or str(uuid.uuid4())
    return _execute_attempt(
        plan,
        root=root,
        run_id=resolved_run_id,
        attempt_id=resolved_attempt_id,
        permissions=resolved_permissions,
        config=config,
        already_completed={},
        owner_instance_id=owner_instance_id,
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
    owner_instance_id: str | None = None,
) -> ScanRun:
    """`execute_scan`'s own lock-acquiring entry point (P69-02l): acquires
    `_run_lock` once and delegates the whole attempt pipeline to
    `_execute_attempt_locked`. `resume_scan_run`/`rescan_project_run` call
    `_execute_attempt_locked` directly instead -- `_run_lock` is a real file
    lock, not reentrant, so calling this wrapper from inside a lock either of
    them already holds would deadlock."""
    with _run_lock(root):
        return _execute_attempt_locked(
            plan,
            root=root,
            run_id=run_id,
            attempt_id=attempt_id,
            permissions=permissions,
            config=config,
            already_completed=already_completed,
            owner_instance_id=owner_instance_id,
        )


def _execute_attempt_locked(
    plan: ScanPlan,
    *,
    root: Path,
    run_id: str,
    attempt_id: str,
    permissions: ExecutionPermissions,
    config: Any,
    already_completed: dict[str, CandidateResult],
    owner_instance_id: str | None = None,
) -> ScanRun:
    """Shared attempt pipeline for a fresh `execute_scan`, a `resume_scan_run`
    retry, and a `rescan_project_run` (P69-02l/m): persist the attempt header
    first (so a crash before the aggregate still leaves a recoverable
    `plan_id`/source signature), run whatever candidates aren't already
    retained, then finalize one immutable terminal manifest. The caller must
    already hold `_run_lock(root)`."""
    _write_attempt_header(root, run_id, attempt_id, plan.plan_id, plan.project_id)
    _append_event(root, run_id, attempt_id, event="attempt_started", candidate_id=None)
    # P69-03e/f: stage the bounded inventory as genuinely independent copies
    # *before* any engine runs. `_run_lock` mutex-excludes concurrent scans but
    # never locks the project's source files -- only a private copy nothing
    # else can touch makes "these are the bytes that were scanned" true.
    # M03 bullet 2: one captured, sorted project-relative inventory at
    # attempt start -- the exact same bounded list staged below, reused for
    # the persisted manifest instead of a second, separate walk at finalize
    # time.
    inventory = _scan_inventory(root)
    with tempfile.TemporaryDirectory(prefix="rush-stage-") as staging_dir:
        staging = stage_inventory(root, Path(staging_dir), inventory)
        with staging_scope(staging):
            scheduled, cancelled = _run_candidates(
                plan,
                root=root,
                run_id=run_id,
                attempt_id=attempt_id,
                permissions=permissions,
                config=config,
                already_completed=already_completed,
                owner_instance_id=owner_instance_id,
            )
        return _finalize_attempt(
            root=root,
            run_id=run_id,
            attempt_id=attempt_id,
            plan=plan,
            scheduled=scheduled,
            cancelled=cancelled,
            staging_findings=staging.findings,
            file_inventory=inventory,
            staging_failures=staging.staging_failures,
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
    owner_instance_id: str | None = None,
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
        return _cancel_requested(root, run_id, attempt_id)

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
            owner_instance_id=owner_instance_id,
            run_id=run_id,
        )
        for finding in result.get("findings") or []:
            cast(dict[str, Any], finding)["finding_id"] = _finding_id(
                str(result.get("tool", candidate.candidate_id)),
                result.get("engine"),
                finding,
            )
        staging = active_staging()
        consumed_path_digests = (
            dict(staging.take_candidate_digests()) if staging is not None else {}
        )
        # P69-03h/M13: a repository-state-dependent engine (git-guard/
        # diff-cover/undercover) never enters staging, so it contributes
        # nothing above -- fold its own real-evidence digest
        # (subprocesses.py's `run_engine`) into its own separate field, never
        # `consumed_path_digests`: this synthetic `candidate_id:kind` key is
        # not a real path, and `git_link.path_digests` must contain only real
        # paths (M13).
        provenance = (result.get("metadata") or {}).get("repository_state_provenance")
        repository_state_evidence: dict[str, str] = {}
        if isinstance(provenance, dict) and provenance.get("digest"):
            key = (
                f"{candidate.candidate_id}:{provenance.get('kind', 'repository-state')}"
            )
            repository_state_evidence[key] = provenance["digest"]
        # M12: snapshot every declared artifact's bytes right here -- before
        # the next scheduled candidate gets a chance to run and physically
        # overwrite the same absolute staged/live path a declared artifact
        # currently points at.
        artifact_snapshots = _capture_artifact_snapshots(
            root, run_id, attempt_id, candidate.candidate_id, result
        )
        candidate_result = CandidateResult(
            candidate=candidate,
            outcome=outcome,
            result=result,
            consumed_path_digests=consumed_path_digests,
            repository_state_evidence=repository_state_evidence,
            artifact_snapshots=artifact_snapshots,
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
    staging_findings: list[dict[str, Any]] | None = None,
    file_inventory: list[str] | None = None,
    staging_failures: list[dict[str, Any]] | None = None,
) -> ScanRun:
    children = [item.result for item in scheduled]
    if staging_findings:
        # P69-03i: a symlink resolving outside the project root is reported,
        # never silently followed into the staged copy.
        children = [
            *children,
            cast(
                "ToolResult",
                {
                    "tool": "scan",
                    "engine": "staging",
                    "engine_version": None,
                    "status": "fail",
                    "duration_ms": 0,
                    "summary": (
                        f"staging rejected {len(staging_findings)} escaping symlink(s)"
                    ),
                    "findings": list(staging_findings),
                },
            ),
        ]
    aggregate = aggregate_results("scan", children)

    run_state: RunState
    if cancelled:
        run_state = "cancelled"
        metadata = dict(aggregate.get("metadata") or {})
        metadata["cancelled"] = True
        aggregate["metadata"] = metadata
    elif staging_failures:
        # M21 bullet 2: a required source that could not be safely staged
        # (broken/escaping symlink, copy/hash error, a disappeared inventory
        # path, a dependency/config symlink creation error) -- checked ahead
        # of `not scheduled` too, since a disappeared inventory file with
        # zero scheduled candidates must still report incomplete, never
        # "completed" from an empty schedule. This fix has no per-candidate
        # consumer-identification mechanism to isolate exactly which
        # scheduled candidate(s) depended on the failed source, so per the
        # fix's own explicit fallback ("if a support failure's affected
        # consumers cannot be identified safely, fail the attempt
        # conservatively") this attempt is never reported clean.
        run_state = "incomplete"
    elif not scheduled:
        run_state = "completed"
        metadata = dict(aggregate.get("metadata") or {})
        metadata["coverage"] = {"empty": True}
        aggregate["metadata"] = metadata
    elif any(item.outcome != "executed" for item in scheduled):
        run_state = "incomplete"
    else:
        run_state = "completed"

    # P69-03d/e/M13: the consumption aggregate over every scheduled
    # candidate's own per-file digests -- freshly read ones for candidates
    # this attempt executed, carried-forward ones for candidates a resume
    # retained. `path_digests` (real paths only) feeds `git_link.path_digests`
    # through `_build_manifest`; `repository_state_evidence` (synthetic
    # per-candidate identity) never does, but both still fold into
    # `_source_identity`'s aggregate content identity.
    path_digests: dict[str, str] = {}
    repository_state_evidence: dict[str, str] = {}
    for item in scheduled:
        path_digests.update(item.consumed_path_digests)
        repository_state_evidence.update(item.repository_state_evidence)
    manifest = _build_manifest(
        run_id=run_id,
        attempt_id=attempt_id,
        plan=plan,
        run_state=run_state,
        scheduled=scheduled,
        aggregate=aggregate,
        source_identity=_source_identity(
            path_digests, root, repository_state_evidence=repository_state_evidence
        ),
        digests=path_digests,
        file_inventory=[{"path": rel} for rel in (file_inventory or [])],
        staging_failures=staging_failures or [],
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


def _generation_path(root: Path, run_id: str) -> Path:
    """Sibling of `attempts/`, never inside it -- existing lifecycle tests
    assert `attempts/`'s own entry count exactly matches real attempt
    directories (P69-02k)."""
    return root / ".rush" / "runs" / run_id / ".generation"


def _fsync_dir(path: Path) -> None:
    """`atomic_write_bytes` fsyncs its temp file's content before
    `os.replace` but not the containing directory afterward -- fsync it here
    so the generation counter's rename itself survives a crash (P69-02k)."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _next_attempt_generation(root: Path, run_id: str) -> int:
    """Persisted, monotonic per-run generation counter (P69-02k): read the
    last-stamped value (or bootstrap from this run's existing attempt-
    directory count, never `0`, on this run's first post-fix write) and
    persist the incremented result *before* the caller stamps it into the
    new attempt's header -- a crash between the two can only ever leave an
    unused counter value, never two attempts sharing one. Must run inside
    the caller's already-held `_run_lock`."""
    path = _generation_path(root, run_id)
    if path.is_file():
        try:
            current = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            current = 0
    else:
        attempts_dir = root / ".rush" / "runs" / run_id / "attempts"
        current = (
            sum(1 for p in attempts_dir.iterdir() if p.is_dir())
            if attempts_dir.is_dir()
            else 0
        )
    generation = current + 1
    written = atomic_write_bytes(
        root,
        _GENERATION_RELATIVE.format(run_id=run_id),
        str(generation).encode("utf-8"),
    )
    _fsync_dir(written.parent)
    return generation


def _highest_generation_attempt_dir(root: Path, run_id: str) -> Path | None:
    """Shared 'latest attempt' selector (P69-02k), used by
    `_latest_attempt_dir()` and `load_run_manifest()`: any attempt carrying a
    persisted `attempt_generation` outranks any that doesn't (a legacy,
    pre-fix attempt), so a legacy attempt is never selected once even one
    post-fix attempt exists for this run. Among attempts that all lack
    `attempt_generation`, falls back to `started_at`, with `attempt_id` as a
    final deterministic tie-break -- enumeration-order-independent, though it
    does not recover true chronology between two equal-timestamp legacy
    attempts."""
    attempts_dir = root / ".rush" / "runs" / run_id / "attempts"
    if not attempts_dir.is_dir():
        return None
    attempt_dirs = [p for p in attempts_dir.iterdir() if p.is_dir()]
    if not attempt_dirs:
        return None

    def _sort_key(attempt_dir: Path) -> tuple[bool, Any, str]:
        header = _load_attempt_header(attempt_dir) or {}
        generation = header.get("attempt_generation")
        if isinstance(generation, int):
            return (True, generation, attempt_dir.name)
        return (False, str(header.get("started_at", "")), attempt_dir.name)

    return max(attempt_dirs, key=_sort_key)


def _write_attempt_header(
    root: Path, run_id: str, attempt_id: str, plan_id: str, project_id: str
) -> None:
    header = {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": plan_id,
        "project_id": project_id,
        "started_at": datetime.now(UTC).isoformat(),
        # P69-03d/j: the *pre-execution* guard only. `source_identity` (the
        # consumption aggregate) cannot exist here -- no engine has run yet --
        # and is written into the terminal manifest instead. The format tag
        # keeps an old, untagged path/size/mtime value from ever being compared
        # as though it were a content hash.
        "source_signature": _source_signature(root),
        "source_signature_format": PROVENANCE_FORMAT,
        # P69-02k: the real ordering key -- `started_at` above is kept only
        # as informational metadata, no longer load-bearing for selection.
        "attempt_generation": _next_attempt_generation(root, run_id),
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
            # P69-03e: carried forward verbatim -- this candidate is not
            # re-executed, so nothing re-reads its content and no fresh
            # consumption event is manufactured for it.
            consumed_path_digests=dict(payload.get("consumed_path_digests") or {}),
            repository_state_evidence=dict(
                payload.get("repository_state_evidence") or {}
            ),
            # M12: carried forward verbatim -- a retained candidate is not
            # re-executed, so its original captured bytes must stay exactly
            # what this attempt (or an earlier one) already snapshotted.
            artifact_snapshots={
                path: dict(entry)
                for path, entry in (payload.get("artifact_snapshots") or {}).items()
            },
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
    """Delegates to the shared, generation-based selector (P69-02k) -- kept
    as its own name since `load_scan_events()`/`resume_scan_run()` already
    call it by this name."""
    return _highest_generation_attempt_dir(root, run_id)


def latest_attempt_id(
    project: str | Path, run_id: str, *, data_root: Path | None = None
) -> str | None:
    """Public helper (P69-02j): `run_id`'s current latest attempt id, for a
    dispatcher to capture synchronously before handing work to a background
    thread. `None` means an unknown `run_id` -- the caller should reject the
    request synchronously rather than discovering this only after the
    background thread's own error handling swallows it."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    latest = _highest_generation_attempt_dir(root, run_id)
    return latest.name if latest is not None else None


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
    # P69-07.2c: terminal state must come from this exact attempt, not
    # whichever attempt is currently highest-generation -- an explicitly
    # requested (non-latest) `attempt_id` would otherwise silently read a
    # different attempt's `run_state`.
    manifest = load_run_manifest(root, run_id, attempt_id=attempt_id)
    return {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "events": _load_events(root, run_id, attempt_id),
        "run_state": (manifest or {}).get("run_state"),
    }


def _cancel_request_path(root: Path, run_id: str, attempt_id: str) -> Path:
    return (
        root
        / ".rush"
        / "runs"
        / run_id
        / "attempts"
        / attempt_id
        / "cancel_requested.json"
    )


def _cancel_requested(root: Path, run_id: str, attempt_id: str | None = None) -> bool:
    """S10: attempt-scoped. `attempt_id` omitted resolves to `run_id`'s
    current latest attempt (legacy 2-argument call compatibility) -- the
    internal candidate-loop `cancel_check()` closure always passes its own
    exact executing attempt explicitly."""
    resolved = attempt_id
    if resolved is None:
        latest = _highest_generation_attempt_dir(root, run_id)
        resolved = latest.name if latest is not None else None
    if resolved is None:
        return False
    return _cancel_request_path(root, run_id, resolved).is_file()


def _clear_cancel_request(root: Path, run_id: str, attempt_id: str) -> None:
    with suppress(OSError):
        _cancel_request_path(root, run_id, attempt_id).unlink()


def cancel_scan_run(
    project: str | Path,
    run_id: str,
    *,
    attempt_id: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """`rush_scan.cancel(project,run_id)` (plan §6.1/§6.4, P65-08). Writes a
    cross-process/cross-thread cooperative cancel-request marker under the
    run's own *currently executing attempt* directory (S10) -- an explicit
    `attempt_id` (the caller's own resolved executor identity) is preferred;
    omitted, this resolves the run's current latest attempt at call time,
    preserving the legacy `run_id`-only call contract. Scoping the marker to
    one attempt means an old cancellation intent for a prior attempt can
    never reach a later resume's fresh attempt. Idempotent: cancelling an
    already-cancel-requested (or already-terminal) run just re-writes the
    same marker."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    if not (root / ".rush" / "runs" / run_id).is_dir():
        raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
    resolved_attempt_id = attempt_id or latest_attempt_id(
        project, run_id, data_root=data_root
    )
    if not resolved_attempt_id:
        raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
    payload = {
        "run_id": run_id,
        "attempt_id": resolved_attempt_id,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    atomic_write_bytes(
        root,
        _CANCEL_REQUEST_RELATIVE.format(run_id=run_id, attempt_id=resolved_attempt_id),
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
    attempt_id: str | None = None,
    expected_attempt_id: str | None = None,
    owner_instance_id: str | None = None,
) -> ScanRun:
    """`rush_scan.resume(project,run_id)` (plan §6.1/§6.4, P65-08). Starts a
    new attempt under the *same* `run_id`, retaining every previously
    `executed` candidate's evidence and re-attempting everything else
    (never-started, `cancelled`, `failed`, `unavailable`, or
    `permission_blocked`). Denies a stale resume (`ScanResumeStaleError`) if
    the project's source changed since the run's most recent attempt
    started -- the same `_source_signature` staleness check
    `dispatch_handoff` already applies to a handoff's own project source.
    Clears any pending cancel request so the new attempt starts clean.

    P69-02l: validates and mutates under one held `_run_lock`, closing the
    race between a dispatcher capturing this run's latest attempt id
    (`latest_attempt_id()`, P69-02j) and this call actually executing.
    `expected_attempt_id`, when supplied, must still match the current
    latest attempt at the moment the lock is acquired; a mismatch (a
    concurrent resume already landed a newer attempt) raises a structured
    conflict *before* clearing any pending cancel request or minting a new
    attempt id. `attempt_id` mirrors `execute_scan`'s own preallocation
    pattern (P69-02d) -- `attempt_id or str(uuid.uuid4())` -- for a
    dispatcher that must return the real id before its own background
    thread runs."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    resolved_permissions = permissions or ExecutionPermissions()

    with _run_lock(root):
        latest_attempt = _highest_generation_attempt_dir(root, run_id)
        if latest_attempt is None:
            raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
        current_attempt_id = latest_attempt.name
        if (
            expected_attempt_id is not None
            and current_attempt_id != expected_attempt_id
        ):
            raise ScanBusyError(
                f"run {run_id}'s latest attempt changed since dispatch "
                f"(expected {expected_attempt_id}, now {current_attempt_id})"
            )
        header = _load_attempt_header(latest_attempt)
        if header is None:
            raise ScanInvalidRequestError(
                f"run {run_id} has no recoverable attempt state to resume"
            )

        plan_id = header.get("plan_id")
        plan = load_scan_plan(root, str(plan_id)) if plan_id else None
        if plan is None:
            raise ScanPlanStaleError(
                f"run {run_id}'s plan {plan_id!r} is no longer staged"
            )

        # P69-03d/j: the cheap pre-execution guard, never the consumption
        # aggregate -- and only ever compared against a value the same
        # algorithm produced.
        if not _signature_comparable(header.get("source_signature_format")):
            raise ScanResumeStaleError(
                "this run's attempt header carries an old-format source "
                "signature that cannot be compared against the current "
                "algorithm; start a fresh scan"
            )
        current_signature = _source_signature(root)
        if current_signature != header.get("source_signature"):
            raise ScanResumeStaleError(
                "project source changed since this run's last attempt started; "
                "resume refuses to apply"
            )

        already_completed = _load_completed_candidates(latest_attempt)
        _clear_cancel_request(root, run_id, latest_attempt.name)
        new_attempt_id = attempt_id or str(uuid.uuid4())
        return _execute_attempt_locked(
            plan,
            root=root,
            run_id=run_id,
            attempt_id=new_attempt_id,
            permissions=resolved_permissions,
            config=config,
            already_completed=already_completed,
            owner_instance_id=owner_instance_id,
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
    """The cheap, *pre-execution* guard -- deliberately not `source_identity`.

    Deterministic fingerprint of every tracked file's path/size/mtime/ctime
    under `root` (excluding Rush's own `.rush`/`.git` state). Its only job is
    "is it even worth starting" for the three call sites that must decide
    before any engine has run (`_write_attempt_header`, `resume_scan_run`,
    `dispatch_handoff`) -- a false negative there costs an unnecessary rescan,
    never a false provenance claim. Certifying *what was actually scanned* is
    `source_identity`'s job (P69-03d/e), computed only once a scan executes.

    P69-03d: `st_ctime_ns` is read from the same `path.stat()` call this
    function already made, closing the equal-length-content-replacement-at-a-
    preserved-mtime gap for free -- `ctime` changes on any content or metadata
    write and cannot be reset through `utime()` (mtime/atime only) without
    root.
    """
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
        entries.append(
            f"{rel.as_posix()}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"
        )
    return sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _scan_inventory(root: Path) -> list[str]:
    """The bounded file inventory staged for one attempt (P69-03b/e).

    Reuses the repo's single ignore convention (`rush.review.collection`'s
    `SKIP_DIRS` plus dotted directories) rather than inventing a second one --
    the excluded dependency/build directories are symlinked back to the live
    tree by `stage_inventory` so config/plugin/module resolution is unchanged.
    """
    from rush.review.collection import SKIP_DIRS

    if not root.is_dir():
        return []
    inventory: list[str] = []
    for directory, subdirs, filenames in root.walk():
        subdirs[:] = [
            name
            for name in subdirs
            if name not in SKIP_DIRS and not name.startswith(".")
        ]
        for name in filenames:
            inventory.append((directory / name).relative_to(root).as_posix())
    return sorted(inventory)


def _signature_comparable(stored_format: Any) -> bool:
    """P69-03j: a pre-execution signature is comparable only against one
    computed by the same algorithm. An untagged (format-1 path/size/mtime)
    record predates the `ctime` change and is unsupported/stale -- never
    silently compared as though the two numbers meant the same thing."""
    return stored_format == PROVENANCE_FORMAT


def _git_link(root: Path) -> dict[str, Any]:
    """P69-03d: the Git half of `source_identity` -- HEAD commit plus an
    explicit dirty/clean flag for the working tree at scan start. Absent
    (`{"repository": False}`) for a non-Git project, which still gets a real
    content-based identity from the per-file digests."""

    def _git(*args: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout if proc.returncode == 0 else None

    head = _git("rev-parse", "HEAD")
    if head is None:
        return {"repository": False}
    status = _git("status", "--porcelain")
    return {
        "repository": True,
        "head": head.strip(),
        "dirty": bool((status or "").strip()),
    }


def _source_identity(
    path_digests: dict[str, str],
    root: Path,
    *,
    repository_state_evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    """P69-03d/e/j/M13: the consumption identity of one completed attempt --
    a format-tagged record carrying the Git link and a deterministic
    aggregate over the per-file digests of the staged content engines
    actually ran against. Never the pre-execution signature, and never
    comparable to one.

    `path_digests` must contain only real project-relative paths --
    `git_link.path_digests` (`_build_manifest`) is built from this exact
    dict, and `projects.py`'s Git lookup treats every one of its keys as a
    literal `git show commit:path` argument. `repository_state_evidence` (a
    repository-state engine's own synthetic `candidate_id:kind` -> digest
    evidence, never a real path) is folded into `content` under a separate
    domain tag so changing either structure still changes the aggregate
    identity, without ever contributing a key to `path_digests`/`git_link`."""
    tagged = {f"path:{key}": value for key, value in path_digests.items()}
    tagged.update(
        {
            f"repo-state:{key}": value
            for key, value in (repository_state_evidence or {}).items()
        }
    )
    return {
        "provenance_format": PROVENANCE_FORMAT,
        "git": _git_link(root),
        "content": aggregate_content_identity(tagged),
        "file_count": len(path_digests),
    }


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
    source_signature_format: int
    memory_session_id: str
    session_capability: str
    delivery_nonce: str
    granted_actions: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    agent_reported_complete_artifact_ids: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    # S05: the dashboard's preallocated ledger operation_id for this
    # handoff's `handoff_send`, so a crash after 202 can recover/replay
    # against the same operation rather than reminting one. Empty for a
    # CLI/MCP-prepared handoff with no dashboard mutation ledger involved.
    operation_id: str = ""
    # S06: the exact attempt this handoff's packet/envelope was built from
    # (dashboard preview/send always pin one; a legacy CLI/MCP call that
    # omits it keeps loading the run's latest attempt, empty here).
    attempt_id: str = ""
    # S05: SHA-256 of the one-time raw capability, persisted in place of the
    # plaintext -- `dispatch_handoff` compares digests, never raw values, so
    # the descriptor on disk never carries a durable plaintext credential.
    session_capability_digest: str = ""
    # T038: the dashboard process's own owner identity at the moment this
    # handoff was prepared -- the only linkage from a dead
    # `owner_instance_id` (S02's `reconcile_admissions`) to a `prepared`
    # handoff it left behind. Empty for a CLI/MCP-prepared handoff (no
    # dashboard owner involved) and for any handoff persisted before this
    # field existed -- both cases degrade to "never matches a real owner",
    # never a crash (`from_dict`'s `payload.get(..., "")` below).
    owner_instance_id: str = ""

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
            "source_signature_format": self.source_signature_format,
            "memory_session_id": self.memory_session_id,
            # S05: `to_dict()` still carries the in-memory raw capability
            # (needed by CLI/MCP `prepare`'s one-time response, built from a
            # fresh, never-persisted object) -- `_persist_handoff` below is
            # what actually strips it before anything reaches disk.
            "session_capability": self.session_capability,
            "session_capability_digest": self.session_capability_digest,
            "delivery_nonce": self.delivery_nonce,
            "granted_actions": list(self.granted_actions),
            "acceptance_checks": list(self.acceptance_checks),
            "agent_reported_complete_artifact_ids": list(
                self.agent_reported_complete_artifact_ids
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "operation_id": self.operation_id,
            "attempt_id": self.attempt_id,
            "owner_instance_id": self.owner_instance_id,
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
            # P69-03j: an untagged persisted handoff predates the algorithm
            # change -- it stays format 1 and `dispatch_handoff` refuses to
            # compare it rather than reinterpreting it.
            source_signature_format=int(payload.get("source_signature_format", 1)),
            memory_session_id=str(payload["memory_session_id"]),
            # S05: the raw capability is never persisted -- a loaded handoff
            # carries no usable in-memory capability, only the stored digest.
            session_capability="",
            delivery_nonce=str(payload["delivery_nonce"]),
            granted_actions=tuple(payload.get("granted_actions") or ()),
            acceptance_checks=tuple(payload.get("acceptance_checks") or ()),
            agent_reported_complete_artifact_ids=tuple(
                payload.get("agent_reported_complete_artifact_ids") or ()
            ),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            operation_id=str(payload.get("operation_id", "")),
            attempt_id=str(payload.get("attempt_id", "")),
            session_capability_digest=str(payload.get("session_capability_digest", "")),
            # T038: absent on a handoff persisted before this field existed --
            # defaults to "", which never matches a real owner_instance_id.
            owner_instance_id=str(payload.get("owner_instance_id", "")),
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


def list_prepared_handoffs(root: Path, owner_instance_id: str) -> list[ScanHandoff]:
    """T038/S02: every handoff at `root/.rush/handoffs/*.json` still in state
    `'prepared'` whose own `owner_instance_id` matches the given dead owner
    -- the linkage `reconcile_admissions` needs to find a handoff a dead
    owner left mid `handoff_send` (prepared, never dispatched). Reuses
    `_load_handoff`'s exact loading/error handling for each file, so a
    handoff persisted before `owner_instance_id` existed (`""` on load)
    degrades to "never matches a real owner" here too, never a crash."""
    if not owner_instance_id:
        return []
    handoffs_dir = root / ".rush" / "handoffs"
    if not handoffs_dir.is_dir():
        return []
    matches = []
    for path in sorted(handoffs_dir.glob("*.json")):
        handoff = _load_handoff(root, path.stem)
        if handoff is None:
            continue
        if (
            handoff.state == "prepared"
            and handoff.owner_instance_id == owner_instance_id
        ):
            matches.append(handoff)
    return matches


def handoff_descriptor_exists_for_operation(root: Path, operation_id: str) -> bool:
    """T052/S05: whether any handoff descriptor -- in any state, `prepared`
    or further along -- has ever been persisted for `operation_id`. `False`
    means `build_handoff` reserved this operation's `artifact_create`/
    `session_create` effect receipts (either or both) but crashed before
    ever reaching `_persist_handoff` (its own final statement) -- the exact
    gap `list_prepared_handoffs` above cannot see, since it only globs
    already-persisted descriptor files."""
    if not operation_id:
        return False
    handoffs_dir = root / ".rush" / "handoffs"
    if not handoffs_dir.is_dir():
        return False
    for path in sorted(handoffs_dir.glob("*.json")):
        handoff = _load_handoff(root, path.stem)
        if handoff is not None and handoff.operation_id == operation_id:
            return True
    return False


def _persist_handoff(root: Path, handoff: ScanHandoff) -> None:
    # S05: the durable descriptor never carries the raw capability -- only
    # `to_dict()`'s in-memory, never-persisted return value does (for a
    # fresh object's one-time CLI/MCP `prepare` response).
    payload = handoff.to_dict()
    payload.pop("session_capability", None)
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
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
    persist: bool = True,
    attempt_id: str = "",
    operation_id: str = "",
    effect_ids: dict[str, str] | None = None,
    owner_instance_id: str = "",
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
    acceptance.

    P69-02.2n: `persist=False` (dashboard `handoff_preview`) builds the
    identical packet from identical selected findings but writes nothing --
    no `MemoryArtifact`, no transport session, no handoff descriptor -- so a
    genuinely read-only preview never durably mutates anything. The caller
    hashes the returned packet/identity for tamper/staleness detection and
    only a later `persist=True` call (`handoff_send`) actually writes."""
    if not agent_id:
        raise ScanInvalidRequestError("build_handoff requires agent_id")
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    manifest = load_run_manifest(root, run_id, attempt_id=attempt_id or None)
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

    if not persist:
        now = datetime.now(UTC).isoformat()
        return ScanHandoff(
            handoff_id=handoff_id,
            run_id=run_id,
            project_id=record["project_id"],
            root=str(root),
            agent_id=agent_id,
            state="prepared",
            finding_ids=tuple(str(f.get("finding_id")) for f in selected),
            packet=packet,
            artifact_id="",
            artifact_version=0,
            source_signature=_source_signature(root),
            source_signature_format=PROVENANCE_FORMAT,
            memory_session_id="",
            session_capability="",
            delivery_nonce="",
            granted_actions=tuple(granted_actions),
            acceptance_checks=tuple(acceptance_checks),
            created_at=now,
            updated_at=now,
            operation_id=operation_id,
            attempt_id=attempt_id,
            owner_instance_id=owner_instance_id,
        )

    # S04: a crashed handoff_send needs to distinguish "artifact written,
    # session not yet created" from "both created" -- reusing one coarse
    # `operation_id` for both receipts would let the second write's
    # `INSERT OR REPLACE` (`mutation_receipts.operation_id` is its primary
    # key) silently clobber the first one. Each reserved effect key gets its
    # own receipt id; an out-of-scope/direct caller with no reservation
    # falls back to the old shared-`operation_id` behavior.
    effect_ids = effect_ids or {}
    artifact_receipt_id = effect_ids.get("artifact_create") or operation_id or None
    session_receipt_id = effect_ids.get("session_create") or operation_id or None

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
        ),
        receipt_operation_id=artifact_receipt_id,
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
            receipt_operation_id=session_receipt_id,
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
        source_signature_format=PROVENANCE_FORMAT,
        memory_session_id=session.session_id,
        # S05: kept in-memory only, for an immediate same-call `dispatch_handoff`
        # (server.py/tui.py both build then dispatch in one call chain) --
        # never round-tripped through `to_dict()`/`from_dict()`.
        session_capability=session_capability,
        session_capability_digest=hashlib.sha256(
            session_capability.encode("utf-8")
        ).hexdigest(),
        delivery_nonce=secrets.token_urlsafe(32),
        granted_actions=tuple(granted_actions),
        acceptance_checks=tuple(acceptance_checks),
        created_at=now,
        updated_at=now,
        operation_id=operation_id,
        attempt_id=attempt_id,
        owner_instance_id=owner_instance_id,
    )
    _persist_handoff(root, handoff)
    return handoff


def _deliver_handoff(
    root: Path,
    handoff: ScanHandoff,
    delta: dict[str, Any],
    *,
    delivery_receipt_id: str,
    store: TypedArtifactStore,
) -> ScanHandoff:
    """S05 bullet 3: the one internal `prepared` -> `delivered` projection
    shared by `dispatch_handoff` (real capability, initial send) and
    `recover_prepared_handoff` (no capability, claimed dead-owner recovery)
    -- `delta` is already fetched/verified by the caller (`receive_handoff`
    for a real send, `recover_session_delta_without_capability` for a
    recovery); this function only owns the idempotent receipt and the
    state projection, identically either way.

    Already-`delivered` (or a later stage) is returned unchanged -- delivery
    recovery never re-runs delivery for a stage that already advanced past
    it, and never touches acknowledged/complete state at all.

    The receipt commit is `INSERT OR IGNORE` (never overwritten): an
    identical prior receipt for `delivery_receipt_id` means this exact
    delivery already happened, so its stored binding -- not a fresh one --
    is authoritative. A *different* stored binding for the same id is a
    genuine conflict (recovery-required), never silently accepted."""
    if handoff.state != "prepared":
        return handoff
    digest = hashlib.sha256(
        json.dumps(delta.get("changes", []), sort_keys=True).encode("utf-8")
    ).hexdigest()
    receipt_payload = {
        "handoff_id": handoff.handoff_id,
        "operation_id": handoff.operation_id,
        "run_id": handoff.run_id,
        "attempt_id": handoff.attempt_id,
        "memory_session_id": handoff.memory_session_id,
        "delivery_nonce": handoff.delivery_nonce,
        "delta_digest": digest,
    }
    stored = store.write_handoff_delivery_receipt(
        delivery_receipt_id,
        artifact_id=handoff.memory_session_id,
        payload=receipt_payload,
    )
    if stored is not None and stored != receipt_payload:
        raise ScanHandoffInvalidStateError(
            f"delivery receipt {delivery_receipt_id!r} already recorded with a "
            "conflicting binding; this handoff is recovery-required"
        )
    updated = replace(
        handoff, state="delivered", updated_at=datetime.now(UTC).isoformat()
    )
    _persist_handoff(root, updated)
    return updated


def dispatch_handoff(
    project: str | Path,
    handoff_id: str,
    session_capability: str,
    *,
    data_root: Path | None = None,
    delivery_receipt_id: str = "",
) -> ScanHandoff:
    """`rush_scan_handoff.dispatch`. Refuses to apply a handoff whose project
    source changed since `prepare` (`SOURCE_CHANGED`), then reaches
    `delivered` only on an actual Phase63 transport acceptance
    (`rush.memory.handoff.receive_handoff`'s real read-back) -- never a
    fictional external send API.

    S05 bullet 3: `delivery_receipt_id` (S04's reserved
    `effect_ids['delivery_transition']` for a dashboard-driven send) makes
    this call idempotent against `_deliver_handoff`'s shared receipt --
    empty for a legacy CLI/MCP caller with no dashboard reservation, which
    falls back to this handoff's own `operation_id`, then a
    handoff-id-derived key, so replay is still possible without one."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    handoff = _load_handoff(root, handoff_id)
    if handoff is None:
        raise ScanInvalidRequestError(f"unknown handoff_id: {handoff_id}")
    if handoff.state != "prepared":
        raise ScanHandoffInvalidStateError(
            f"dispatch requires state 'prepared', got {handoff.state!r}"
        )
    # P69-03j: never reinterpret an old-format (untagged path/size/mtime)
    # signature as though it were comparable to the current algorithm's value.
    if not _signature_comparable(handoff.source_signature_format):
        raise ScanHandoffSourceChangedError(
            "this handoff carries an old-format source signature that cannot be "
            "compared against the current algorithm; prepare the handoff again"
        )
    if _source_signature(root) != handoff.source_signature:
        raise ScanHandoffSourceChangedError(
            "project source changed since this handoff was prepared; refuses to apply"
        )
    presented_digest = hashlib.sha256(session_capability.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(presented_digest, handoff.session_capability_digest):
        raise ScanHandoffAuthError("invalid session_capability")

    store = TypedArtifactStore(root)
    try:
        delta = receive_handoff(
            store, session_id=handoff.memory_session_id, capability=session_capability
        )
    except HandoffError as exc:
        raise ScanHandoffAuthError(str(exc)) from exc

    receipt_id = (
        delivery_receipt_id
        or handoff.operation_id
        or f"legacy-delivery:{handoff.handoff_id}"
    )
    return _deliver_handoff(
        root, handoff, delta, delivery_receipt_id=receipt_id, store=store
    )


def _mark_handoff_unrecoverable(
    store: TypedArtifactStore, handoff: ScanHandoff
) -> None:
    """S05 bullet 4: once `recover_prepared_handoff` has confirmed -- past
    the initial prepared-state/operation-claim gate -- that this handoff can
    never complete through the normal `dispatch_handoff` path either (the
    same signature/source checks would fail there too, or the session row
    itself disagrees), give up cleanly: idempotently revoke its session and
    mark its artifact orphaned for safe later cleanup. Never called for a
    wrong-operation claim or an already-resolved (non-`prepared`) handoff,
    either of which may still belong to a live owner."""
    store.revoke_handoff_session(handoff.memory_session_id)
    store.mark_artifact_orphaned(handoff.artifact_id)


def recover_prepared_handoff(
    project: str | Path,
    handoff_id: str,
    *,
    claimed_operation_id: str,
    artifact_create_receipt_id: str,
    session_create_receipt_id: str,
    delivery_receipt_id: str,
    data_root: Path | None = None,
) -> ScanHandoff | None:
    """S05 bullet 2: internal dead-owner recovery for a handoff that
    crashed between `prepare` and `dispatch`. NOT an HTTP/CLI/MCP entry
    point -- callable only from inside a process that has already won
    `claim_dead_owner(...)` for the owner_instance_id that prepared this
    handoff (the caller's responsibility; this function does not itself
    claim anything).

    Verifies, in order, before recovering anything: this handoff's
    persisted state is exactly `"prepared"`; its `operation_id` matches
    `claimed_operation_id` (the dead owner's own reserved operation, never
    an unrelated/fabricated one); S04's `artifact_create`/`session_create`
    effect receipts both exist (proof `build_handoff` actually committed
    both writes, not a partial crash mid-write); the project's source
    hasn't changed since prepare (same check `dispatch_handoff` makes); and
    -- inside `recover_session_delta_without_capability` -- the store's live
    session row still matches this handoff's own project/audience/
    allowlist and is neither expired nor revoked. Returns `None`
    (recovery-required, never auto-resolved) the instant any check fails.

    S05 bullet 4: once past the initial prepared-state/operation-claim gate
    (where a wrong claim or an already-resolved handoff may still belong to
    a live owner and is left untouched), every later failure means this
    handoff could never complete through the normal `dispatch_handoff` path
    either -- so `_mark_handoff_unrecoverable` idempotently revokes its
    session and orphans its artifact before returning `None`."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    handoff = _load_handoff(root, handoff_id)
    if handoff is None or handoff.state != "prepared":
        return None
    if not claimed_operation_id or handoff.operation_id != claimed_operation_id:
        return None
    store = TypedArtifactStore(root)
    if store.get_receipt(artifact_create_receipt_id) is None:
        _mark_handoff_unrecoverable(store, handoff)
        return None
    if store.get_receipt(session_create_receipt_id) is None:
        _mark_handoff_unrecoverable(store, handoff)
        return None
    if not _signature_comparable(handoff.source_signature_format):
        _mark_handoff_unrecoverable(store, handoff)
        return None
    if _source_signature(root) != handoff.source_signature:
        _mark_handoff_unrecoverable(store, handoff)
        return None
    delta = recover_session_delta_without_capability(
        store,
        handoff.memory_session_id,
        expected_root=str(root),
        expected_audience=handoff.agent_id,
        expected_session_allowlist=[str(root)],
    )
    if delta is None:
        _mark_handoff_unrecoverable(store, handoff)
        return None
    return _deliver_handoff(
        root, handoff, delta, delivery_receipt_id=delivery_receipt_id, store=store
    )


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
    baseline_attempt_id: str | None = None,
    current_attempt_id: str | None = None,
) -> dict[str, Any]:
    """Rescan comparison (plan §6.1/§6.4, F35): marks every baseline finding
    `resolved`, `persisting`, or `unverified`, and every current-only finding
    `new`. Resolves a prior finding only when the same tool/engine (its
    finding's own `provenance`, plan §3.3) actually reached `executed`
    coverage in the current run and no longer reports it; a missing,
    permission-blocked, or failed engine can never make a finding `resolved`
    -- it stays `unverified` (plan: "a missing engine cannot make a finding
    resolved").

    P69-02m: `baseline_attempt_id`/`current_attempt_id`, when supplied, pin
    the comparison to those exact attempts instead of re-selecting "latest"
    on either side -- a rescan's own `_run_lock` has already released by the
    time this runs, and a different resume/rescan can otherwise land a newer
    attempt on either `run_id` in that gap."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    baseline = load_run_manifest(root, baseline_run_id, attempt_id=baseline_attempt_id)
    current = load_run_manifest(root, current_run_id, attempt_id=current_attempt_id)
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
    new_run_id: str | None = None,
    attempt_id: str | None = None,
    expected_attempt_id: str | None = None,
    owner_instance_id: str | None = None,
) -> dict[str, Any]:
    """`rush_scan.rescan(project,run_id)` (plan §6.1): re-executes `run_id`'s
    own staged plan against the project's *current* source and compares the
    fresh run against `run_id` via `compare_runs`. New source is expected
    here (unlike `dispatch_handoff`/stale resume, which forbid it) -- a
    rescan's entire purpose is re-evaluating changed source.

    P69-02m: validates the baseline and mutates under one held `_run_lock`,
    calling `_execute_attempt_locked` directly rather than `execute_scan` --
    `execute_scan` acquires `_run_lock` itself, and calling it from inside a
    lock this function already holds would be a nested, non-reentrant
    acquisition that blocks for the full timeout and raises `ScanBusyError`.
    `new_run_id`/`attempt_id` mirror `execute_scan`'s own preallocation
    pattern (P69-02d) for a dispatcher that must return these ids before its
    own background thread runs. `expected_attempt_id`, when supplied, is the
    baseline's latest attempt id a dispatcher captured synchronously before
    dispatch (`load_run_manifest(...)["attempt_id"]`, per P69-02j); a
    mismatch at execution time (a concurrent resume advanced the baseline in
    the gap) raises a structured conflict instead of silently comparing
    against a baseline the caller never actually reviewed."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    resolved_permissions = permissions or ExecutionPermissions()
    resolved_new_run_id = new_run_id or str(uuid.uuid4())

    with _run_lock(root):
        run_dir = root / ".rush" / "runs" / run_id
        if not run_dir.is_dir():
            raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
        baseline = load_run_manifest(root, run_id)
        if baseline is None:
            # A concurrent resume can publish a newer attempt's header
            # without yet finishing -- load_run_manifest() then finds no
            # terminal manifest for this run's current latest attempt. A
            # real, distinct condition from an unknown run_id (checked
            # above), never a TypeError from indexing into None.
            raise ScanBusyError(
                f"run {run_id} has no terminal attempt available for rescan "
                "right now (a concurrent operation may be in progress)"
            )
        current_baseline_attempt_id = baseline.get("attempt_id")
        if (
            expected_attempt_id is not None
            and current_baseline_attempt_id != expected_attempt_id
        ):
            raise ScanBusyError(
                f"run {run_id}'s baseline attempt changed since dispatch "
                f"(expected {expected_attempt_id}, now "
                f"{current_baseline_attempt_id})"
            )
        plan_id = baseline.get("plan_id")
        plan = load_scan_plan(root, str(plan_id)) if plan_id else None
        if plan is None:
            raise ScanPlanStaleError(
                f"run {run_id}'s plan {plan_id!r} is no longer staged"
            )
        resolved_attempt_id = attempt_id or str(uuid.uuid4())
        run = _execute_attempt_locked(
            plan,
            root=root,
            run_id=resolved_new_run_id,
            attempt_id=resolved_attempt_id,
            permissions=resolved_permissions,
            config=config,
            already_completed={},
            owner_instance_id=owner_instance_id,
        )

    comparison = compare_runs(
        project,
        run_id,
        run.run_id,
        data_root=data_root,
        baseline_attempt_id=expected_attempt_id or current_baseline_attempt_id,
        current_attempt_id=run.attempt_id,
    )
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
    "latest_attempt_id",
    "list_prepared_handoffs",
    "load_run_manifest",
    "load_scan_events",
    "load_scan_plan",
    "plan_scan",
    "recover_prepared_handoff",
    "rescan_project_run",
    "resume_scan_run",
    "status_handoff",
]
