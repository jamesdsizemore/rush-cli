"""Deterministic helpers shared by multi-engine Rush tools."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .base import Finding, ToolResult

_STATUS_RANK = {"skipped": 0, "ok": 1, "warn": 2, "fail": 3, "error": 4}
_SKIP_DIRS = frozenset(
    {".git", ".next", ".venv", "__pycache__", "build", "dist", "node_modules", "venv"}
)

_LANGUAGE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("pyproject.toml", "setup.py")),
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


def combine_status(left: str, right: str) -> str:
    """Return the worst Rush status while preserving known status semantics."""
    return left if _STATUS_RANK.get(left, -1) >= _STATUS_RANK.get(right, -1) else right


def collect_files(path: Path, extensions: set[str]) -> list[Path]:
    """Collect supported files in deterministic order without generated trees."""
    normalized_extensions = {extension.lower().lstrip(".") for extension in extensions}
    if path.is_file():
        return (
            [path] if path.suffix.lower().lstrip(".") in normalized_extensions else []
        )
    if not path.is_dir():
        return []

    files = [
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file()
        and candidate.suffix.lower().lstrip(".") in normalized_extensions
        and not any(
            part in _SKIP_DIRS or part.startswith(".")
            for part in candidate.relative_to(path).parts[:-1]
        )
    ]
    return sorted(files, key=lambda candidate: candidate.as_posix())


def aggregate_results(tool: str, results: Sequence[ToolResult]) -> ToolResult:
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
        )

    status = "skipped"
    duration_ms = 0
    engines: list[str] = []
    findings: list[Finding] = []
    metrics: dict[str, int | float | str] = {}
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
        status = combine_status(status, str(result.get("status", "skipped")))
        duration_ms += int(result.get("duration_ms", 0) or 0)
        engine = result.get("engine")
        if engine and engine not in engines:
            engines.append(engine)
        source = f"{result.get('tool', tool)}/{engine or 'no-engine'}"
        for finding in result.get("findings", []):
            normalized = Finding(**finding)
            normalized["provenance"] = normalized.get("provenance") or source
            findings.append(normalized)

        for key, value in (result.get("metrics") or {}).items():
            if key not in metrics and isinstance(value, (int, float, str)):
                metrics[key] = value
        for artifact in result.get("artifacts") or []:
            if artifact not in artifacts:
                artifacts.append(artifact)

    if tool == "review":
        findings = _deduplicate_review_findings(findings)
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
    return output


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
    "collect_files",
    "combine_status",
    "detect_project_languages",
]
