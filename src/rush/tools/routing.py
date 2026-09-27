"""Deterministic helpers shared by multi-engine Rush tools."""

from __future__ import annotations

import os
from collections.abc import Collection, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any, cast

from rush.discovery.stack import PYTHON_MARKERS

from .base import Finding, ToolResult, ToolStatus
from .common import finding_fingerprint

#: Python checker configuration files: a finding in one is configuration.
PYTHON_CONFIG_NAMES = frozenset(
    {"mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg", "pyrefly.toml"}
)


def classify_finding_scopes(
    findings: Sequence[Finding],
    requested: Collection[str],
    configuration: Collection[str] = (),
) -> list[str]:
    """T12 S12.2: tag each finding `extensions.scope` as `requested` (its
    file is a requested target), `configuration` (no path, or a checker
    config file) or `dependency` (anything else the engine consumed). Every
    finding is kept; returns the sorted dependency files."""
    wanted = {os.path.realpath(p) for p in requested}
    configs = {os.path.realpath(p) for p in configuration}
    dependencies: set[str] = set()
    for finding in findings:
        path = finding.get("path")
        real = os.path.realpath(path) if path else None
        if real is None or real in configs or Path(real).name in PYTHON_CONFIG_NAMES:
            scope = "configuration"
        elif real in wanted:
            scope = "requested"
        else:
            scope = "dependency"
            dependencies.add(str(path))
        finding["extensions"] = {**(finding.get("extensions") or {}), "scope": scope}
    return sorted(dependencies)


def _merge_counts(values: list[Any]) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(values)


def merge_scopes(
    children: Sequence[tuple[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    """T12 A13: one tool scope from its engines' scopes -- lists unioned and
    sorted, booleans OR-ed, counts summed (unknown if any child's is), and
    groups concatenated with their engine."""
    if not children:
        return None
    scopes = [scope for _, scope in children]
    coverages = {scope.get("coverage") for scope in scopes}
    merged: dict[str, Any] = {
        "version": 1,
        "kind": "file",
        "logical_root": scopes[0].get("logical_root"),
        "coverage": coverages.pop() if len(coverages) == 1 else "partial",
        "reason": next((s["reason"] for s in scopes if s.get("reason")), None),
    }
    for key in (
        "requested_targets",
        "dependency_files",
        "ambient_files",
        "configuration_files",
        "unclassifiable_files",
    ):
        merged[key] = sorted(
            {item for scope in scopes for item in scope.get(key) or []}
        )
    for key in (
        "requested_file_count",
        "matched_file_count",
        "consumed_file_count",
        "engine_library_file_count",
    ):
        merged[key] = _merge_counts([scope.get(key) for scope in scopes])
    for key in ("unclassifiable", "explicit_override"):
        merged[key] = any(bool(scope.get(key)) for scope in scopes)
    merged["excluded_files"] = sorted(
        (item for scope in scopes for item in scope.get("excluded_files") or []),
        key=lambda item: (str(item.get("path")), str(item.get("reason"))),
    )
    merged["groups"] = [
        {**group, "engine": engine}
        for engine, scope in children
        for group in scope.get("groups") or []
    ]
    return merged


#: S16.3: error > fail > warn > skipped > ok.
_STATUS_RANK: dict[str, int] = {"ok": 0, "skipped": 1, "warn": 2, "fail": 3, "error": 4}
_SKIP_DIRS = frozenset(
    {".git", ".next", ".venv", "__pycache__", "build", "dist", "node_modules", "venv"}
)

_LANGUAGE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", PYTHON_MARKERS),
    ("javascript", ("package.json",)),
    ("go", ("go.mod",)),
    ("rust", ("Cargo.toml",)),
    ("ruby", ("Gemfile",)),
    ("jvm", ("pom.xml", "build.gradle", "build.gradle.kts")),
    ("swift", ("Package.swift",)),
    ("php", ("composer.json",)),
    ("dotnet", ("*.sln", "*.csproj")),
    ("elixir", ("mix.exs",)),
    ("dart", ("pubspec.yaml",)),
    ("scala", ("build.sbt",)),
    ("nix", ("flake.nix",)),
)


def detect_project_languages(path: Path) -> list[str]:
    """Return every detected ecosystem in stable catalog order."""
    root = path if path.is_dir() else path.parent
    if not root.is_dir():
        return []
    return [
        language
        for language, markers in _LANGUAGE_MARKERS
        if any(any(root.glob(marker)) for marker in markers)
    ]


def no_target_scope(reason: str, **counts: int) -> dict[str, Any]:
    """T9: the `metadata.scope` of a result that examined nothing, with the
    exact reason (e.g. `target_not_found`, `no_supported_targets`,
    `engine_unavailable`) and any known file counts."""
    return {
        "version": 1,
        "kind": "files",
        "coverage": "none",
        "reason": reason,
        **counts,
    }


def aggregate_status(statuses: Iterable[str]) -> ToolStatus:
    """S16.3: the worst status by error>fail>warn>skipped>ok. Work that is
    partly ok and partly skipped is `warn` (finding 9: every engine a tool
    runs is required); no status at all is `skipped`."""
    seen = {status for status in statuses if status in _STATUS_RANK}
    if not seen:
        return "skipped"
    worst = cast("ToolStatus", max(seen, key=_STATUS_RANK.__getitem__))
    if {"ok", "skipped"} <= seen and _STATUS_RANK[worst] < _STATUS_RANK["warn"]:
        return "warn"
    return worst


def combine_status(left: ToolStatus, right: ToolStatus) -> ToolStatus:
    """S16.3: `aggregate_status` of exactly two statuses."""
    return aggregate_status([left, right])


def _child_metadata(result: ToolResult) -> dict[str, Any]:
    metadata = result.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _with_environment(entry: Any, metadata: dict[str, Any]) -> Any:
    """A tool that records its analysis environment on the child after the
    dispatch (typecheck) has it carried into that child's engine entry."""
    environment = metadata.get("analysis_environment")
    if not isinstance(entry, dict) or not isinstance(environment, dict):
        return entry
    if (entry.get("analysis_environment") or {}).get("mode") != "not_applicable":
        return entry
    return {**entry, "analysis_environment": environment}


def concat_engine_entries(results: Sequence[ToolResult]) -> list[dict[str, Any]]:
    """S16.2: every child's `metadata.engines` entries, in child order."""
    return [
        _with_environment(entry, _child_metadata(result))
        for result in results
        for entry in _child_metadata(result).get("engines") or []
    ]


def _aggregate_coverage(coverages: list[str]) -> str:
    """§3 item 3: complete if all complete; none if all none; unavailable if
    nothing is complete/partial and any is unavailable; else partial."""
    kinds = set(coverages)
    if not kinds or kinds == {"none"}:
        return "none"
    if kinds == {"complete"}:
        return "complete"
    if not kinds & {"complete", "partial"} and "unavailable" in kinds:
        return "unavailable"
    return "partial"


def aggregate_scope(results: Sequence[ToolResult]) -> dict[str, Any]:
    """§3 item 3: the aggregate scope of a multi-child result. File counts
    stay on each child; a child that reports no scope counts as
    `unavailable`."""
    from rush.invocation.executor import current_invocation_root

    scopes = [_child_metadata(result).get("scope") or {} for result in results]
    root = current_invocation_root()
    return {
        "version": 1,
        "kind": "aggregate",
        "coverage": _aggregate_coverage(
            [str(scope.get("coverage") or "unavailable") for scope in scopes]
        ),
        "requested_targets": sorted(
            {str(t) for scope in scopes for t in scope.get("requested_targets") or []}
        ),
        "logical_root": str(root) if root is not None else None,
    }


def child_entry(result: ToolResult) -> dict[str, Any]:
    """§3 item 3: one suite/scan child as `{tool, status, summary, reason,
    engines, scope, execution}`."""
    metadata = _child_metadata(result)
    scope = metadata.get("scope") or {}
    execution = metadata.get("execution") or {}
    error = metadata.get("error") or {}
    return {
        "tool": result.get("tool"),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "reason": error.get("code") or execution.get("cause"),
        "engines": [
            entry.get("engine")
            for entry in metadata.get("engines") or []
            if entry.get("engine")
        ],
        "scope": {
            "coverage": scope.get("coverage") or "unavailable",
            "reason": scope.get("reason"),
        },
        "execution": {
            "disposition": execution.get("disposition") or "executed",
            "cause": execution.get("cause"),
        },
    }


def collect_files(
    path: Path, extensions: set[str], *, strict: bool = False
) -> list[Path]:
    """Collect supported files in deterministic order without generated trees."""
    normalized_extensions = {extension.lower().lstrip(".") for extension in extensions}
    if path.is_file():
        return (
            [path] if path.suffix.lower().lstrip(".") in normalized_extensions else []
        )
    if not path.is_dir():
        return []

    def raise_walk_error(error: OSError) -> None:
        raise error

    candidates: Iterator[Path] = path.rglob("*")
    if strict:
        strict_candidates: list[Path] = []
        for directory, subdirs, filenames in path.walk(on_error=raise_walk_error):
            subdirs[:] = [
                name
                for name in subdirs
                if name not in _SKIP_DIRS and not name.startswith(".")
            ]
            strict_candidates.extend(directory / name for name in filenames)
        candidates = iter(strict_candidates)

    files = [
        candidate
        for candidate in candidates
        if candidate.is_file()
        and candidate.suffix.lower().lstrip(".") in normalized_extensions
        and not any(
            part in _SKIP_DIRS or part.startswith(".")
            for part in candidate.relative_to(path).parts[:-1]
        )
    ]
    return sorted(files, key=lambda candidate: candidate.as_posix())


def aggregate_results(
    tool: str,
    results: Sequence[ToolResult],
    *,
    baseline_fingerprints: Collection[str] | None = None,
) -> ToolResult:
    """Combine engine results into one stable, JSON-safe canonical result.

    Findings sort by source location, status uses the documented severity rank,
    metrics keep the first producer for each key, and artifact paths retain
    first-seen order without duplicates.
    """
    if not results:
        return ToolResult(
            tool=tool,
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=0,
            summary=f"{tool}: no eligible engines",
            findings=[],
            raw=None,
            metadata={"engines": [], "scope": aggregate_scope(())},
        )

    status = aggregate_status(
        str(result.get("status", "skipped")) for result in results
    )
    duration_ms = 0
    engines: list[str] = []
    findings: list[Finding] = []
    metrics: dict[str, int | float | str | None] = {}
    artifacts: list[str] = []

    ordered_results = results
    if tool == "review":
        ordered_results = sorted(
            results,
            key=lambda item: (
                str(item.get("tool", "")),
                str(item.get("engine", "")),
                str(item.get("engine_version", "")),
            ),
        )

    for result in ordered_results:
        duration_ms += int(result.get("duration_ms", 0) or 0)
        engine = result.get("engine")
        if engine and engine not in engines:
            engines.append(engine)
        source = f"{result.get('tool', tool)}/{engine or 'no-engine'}"
        for finding in result.get("findings", []):
            normalized = Finding(**finding)
            normalized["provenance"] = normalized.get("provenance") or source
            if tool == "review":
                normalized["fingerprint"] = finding_fingerprint(
                    str(normalized.get("path", "")),
                    normalized.get("line", 0) or 0,
                    normalized.get("column", 0) or 0,
                    str(normalized.get("rule_id") or normalized.get("rule") or ""),
                    str(normalized.get("severity", "")),
                    str(normalized.get("message", "")),
                )
            findings.append(normalized)

        for key, value in (result.get("metrics") or {}).items():
            if key not in metrics and isinstance(value, (int, float, str)):
                metrics[key] = value
        for artifact in result.get("artifacts") or []:
            if artifact not in artifacts:
                artifacts.append(artifact)

    if tool == "review":
        findings = _deduplicate_review_findings(findings)
        baseline = set(baseline_fingerprints or ())
        for finding in findings:
            if baseline_fingerprints is None:
                finding["freshness"] = "unknown"
            elif finding["fingerprint"] in baseline:
                finding["freshness"] = "existing"
            else:
                finding["freshness"] = "new"
    findings.sort(key=_finding_sort_key)
    engine_label = "+".join(engines) if engines else None
    summary = f"{tool} [{engine_label or 'no engine'}]: {len(findings)} finding(s)"

    output = ToolResult(
        tool=tool,
        engine=engine_label,
        engine_version=None,
        status=status,
        duration_ms=duration_ms,
        summary=summary,
        findings=findings,
        raw=None,
    )
    if metrics:
        output["metrics"] = metrics
    if artifacts:
        output["artifacts"] = artifacts
    # S16.2/§3 item 3: every child's engine entries, in order, and the
    # aggregate scope over the children.
    metadata: dict[str, Any] = {
        "engines": concat_engine_entries(ordered_results),
        "scope": aggregate_scope(ordered_results),
    }
    if tool == "review":
        metadata |= {
            "aggregation": {
                "mode": "serial",
                "partial": any(
                    str(result.get("status", "skipped")) in {"error", "skipped"}
                    for result in ordered_results
                ),
                "children": [
                    {
                        "tool": str(result.get("tool", tool)),
                        "engine": result.get("engine"),
                        "status": str(result.get("status", "skipped")),
                    }
                    for result in ordered_results
                ],
            },
            "baseline": "provided"
            if baseline_fingerprints is not None
            else "not-provided",
        }
    output["metadata"] = metadata
    return output


def build_finding_baseline(findings: Sequence[Finding]) -> tuple[str, ...]:
    """Build a deterministic in-memory baseline without writing a file."""
    return tuple(
        sorted(
            {
                str(finding["fingerprint"])
                for finding in findings
                if "fingerprint" in finding
            }
        )
    )


def _deduplicate_review_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse identical review evidence while retaining every source."""
    by_fingerprint: dict[str, Finding] = {}
    for finding in findings:
        fingerprint = str(finding.get("fingerprint") or "")
        if not fingerprint:
            fingerprint = "\x1f".join(
                str(finding.get(field, ""))
                for field in ("path", "line", "column", "rule", "severity", "message")
            )
        existing = by_fingerprint.get(fingerprint)
        if existing is None:
            by_fingerprint[fingerprint] = finding
            continue
        provenance = [
            item
            for item in (
                str(existing.get("provenance") or "").split(";")
                + str(finding.get("provenance") or "").split(";")
            )
            if item
        ]
        existing["provenance"] = ";".join(dict.fromkeys(provenance))
    return list(by_fingerprint.values())


def _finding_sort_key(finding: Finding) -> tuple[str, int, int, str, str]:
    """Sort findings reproducibly even when an engine omits coordinates."""
    return (
        str(finding.get("path", "")),
        int(finding.get("line", 0) or 0),
        int(finding.get("column", 0) or 0),
        str(finding.get("rule", "")),
        str(finding.get("message", "")),
    )


__all__ = [
    "aggregate_results",
    "aggregate_scope",
    "aggregate_status",
    "build_finding_baseline",
    "child_entry",
    "collect_files",
    "combine_status",
    "concat_engine_entries",
    "detect_project_languages",
    "no_target_scope",
]
