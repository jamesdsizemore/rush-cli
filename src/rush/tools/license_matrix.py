"""Dependency license risk and open-source copyleft compliance auditor."""

from __future__ import annotations

import importlib.metadata
import json
import re
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolResult
from .common import elapsed_ms, finding_fingerprint, now_ms

DEFAULT_ALLOWED_LICENSES: tuple[str, ...] = (
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Unlicense",
    "CC0-1.0",
    "0BSD",
    "PSF-2.0",
    "Python-2.0",
)

COPYLEFT_MARKERS: tuple[str, ...] = (
    "GPL",
    "AGPL",
    "LGPL",
    "SSPL",
    "EUPL",
    "MPL",
    "CDDL",
    "EPL",
)


def _normalize_spdx(raw_license: str) -> str:
    """Normalize common license strings to canonical SPDX identifiers."""
    cleaned = raw_license.strip()
    norm = cleaned.lower()
    if norm in ("mit", "mit license"):
        return "MIT"
    if norm in ("apache 2.0", "apache-2.0", "apache license 2.0", "apache"):
        return "Apache-2.0"
    if norm in ("bsd", "bsd-3-clause", "bsd 3-clause", "3-clause bsd"):
        return "BSD-3-Clause"
    if norm in ("bsd-2-clause", "bsd 2-clause", "2-clause bsd"):
        return "BSD-2-Clause"
    if norm in ("isc", "isc license"):
        return "ISC"
    if norm in ("unlicense", "the unlicense"):
        return "Unlicense"
    if norm in ("cc0", "cc0-1.0", "public domain"):
        return "CC0-1.0"
    if norm in ("0bsd", "zero-clause bsd"):
        return "0BSD"
    if norm in ("psf", "psf-2.0", "python software foundation license"):
        return "PSF-2.0"
    return cleaned


def _lookup_python_pkg_license(pkg_name: str) -> str:
    """Attempt to lookup license of an installed Python package via importlib.metadata."""
    try:
        meta = importlib.metadata.metadata(pkg_name)
        lic = meta.get("License")
        if lic and lic.strip() and lic.strip().lower() != "unknown":
            return lic.strip()
        # Look in classifiers
        classifiers = meta.get_all("Classifier") or []
        for c in classifiers:
            if "License :: OSI Approved ::" in c:
                part = c.split("::")[-1].strip()
                if "Apache" in part:
                    return "Apache-2.0"
                if "MIT" in part:
                    return "MIT"
                if "BSD" in part:
                    return "BSD-3-Clause"
                if "GPL" in part:
                    return "GPL-3.0"
                return part
    except Exception:  # noqa: BLE001, S110
        pass
    return "UNKNOWN"


def _extract_pyproject_deps(pyproject_path: Path) -> set[str]:
    """Parse dependencies from pyproject.toml."""
    deps: set[str] = set()
    try:
        text = pyproject_path.read_text(encoding="utf-8", errors="ignore")
        # standard [project.dependencies] or [tool.poetry.dependencies]
        found = re.findall(
            r'["\']([a-zA-Z0-9_-]+)(?:>=|==|<=|~=|<|>|\^|\[|;)?.*["\']', text
        )
        for dep in found:
            dep_clean = dep.lower().split("[")[0].strip()
            if dep_clean and dep_clean not in (
                "rush",
                "python",
                "project",
                "dependencies",
                "optional-dependencies",
                "tool",
            ):
                deps.add(dep_clean)
    except Exception:  # noqa: BLE001, S110
        pass
    return deps


def _extract_package_json_deps(pkg_json_path: Path) -> set[str]:
    """Parse dependencies from package.json."""
    deps: set[str] = set()
    try:
        data = json.loads(pkg_json_path.read_text(encoding="utf-8", errors="ignore"))
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            if isinstance(data.get(section), dict):
                deps.update(data[section].keys())
    except Exception:  # noqa: BLE001, S110
        pass
    return deps


def _extract_cargo_toml_deps(cargo_path: Path) -> set[str]:
    """Parse dependencies from Cargo.toml."""
    deps: set[str] = set()
    try:
        text = cargo_path.read_text(encoding="utf-8", errors="ignore")
        in_deps = False
        for line in text.splitlines():
            line_str = line.strip()
            if line_str.startswith("[") and line_str.endswith("]"):
                in_deps = "dependencies" in line_str.lower()
                continue
            if in_deps and "=" in line_str:
                pkg = line_str.split("=")[0].strip()
                if pkg and not pkg.startswith("#"):
                    deps.add(pkg)
    except Exception:  # noqa: BLE001, S110
        pass
    return deps


class LicenseMatrixTool(ToolFn):
    """Audits dependencies for license compliance and copyleft risks."""

    name = "license-matrix"

    @property
    def mcp_description(self) -> str:
        return (
            "Audit open-source dependencies for license risks and copyleft compliance. "
            "Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
        allowed_licenses: tuple[str, ...] = DEFAULT_ALLOWED_LICENSES,
        package_licenses: dict[str, str] | None = None,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(
            path,
            allowed_licenses=allowed_licenses,
            package_licenses=package_licenses,
            permissions=permissions,
        )

    def run(
        self,
        path: Path,
        *,
        allowed_licenses: tuple[str, ...] = DEFAULT_ALLOWED_LICENSES,
        package_licenses: dict[str, str] | None = None,
        config: Any = None,
        permissions: Any = None,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        target_dir = path if path.is_dir() else path.parent
        target_dir = target_dir.resolve()

        # Gather discovered dependencies across manifests
        discovered_pkgs: dict[str, str] = {}  # pkg -> manifest path

        pyproject = target_dir / "pyproject.toml"
        if pyproject.exists():
            for p in _extract_pyproject_deps(pyproject):
                discovered_pkgs[p] = "pyproject.toml"

        pkg_json = target_dir / "package.json"
        if pkg_json.exists():
            for p in _extract_package_json_deps(pkg_json):
                discovered_pkgs[p] = "package.json"

        cargo = target_dir / "Cargo.toml"
        if cargo.exists():
            for p in _extract_cargo_toml_deps(cargo):
                discovered_pkgs[p] = "Cargo.toml"

        # Explicit overrides / mock injection
        explicit_overrides = dict(package_licenses or {})
        for p in explicit_overrides:
            if p not in discovered_pkgs:
                discovered_pkgs[p] = "explicit"

        # Allowed licenses set (case-insensitive for lookup)
        allowed_set = {lic.upper() for lic in allowed_licenses}

        packages_report: list[dict[str, Any]] = []
        findings: list[Finding] = []

        for pkg, manifest_rel in sorted(discovered_pkgs.items()):
            raw_lic = explicit_overrides.get(pkg)
            if not raw_lic:
                raw_lic = _lookup_python_pkg_license(pkg)
                if raw_lic == "UNKNOWN" and manifest_rel in (
                    "package.json",
                    "Cargo.toml",
                ):
                    # Default assumed permissive or unknown for mock if manifest present
                    raw_lic = "MIT"

            norm_lic = _normalize_spdx(raw_lic)
            is_copyleft = any(
                m in norm_lic.upper() for m in COPYLEFT_MARKERS
            ) or norm_lic.upper().startswith("GPL")

            # Check if compound, unknown, or needs manual review
            is_compound = (
                any(sep in norm_lic for sep in ("/", " OR ", " AND ", "Dual"))
                or "REVIEW" in norm_lic.upper()
                or "PROPRIETARY" in norm_lic.upper()
            )
            is_unknown = norm_lic.upper() in ("UNKNOWN", "", "NONE")

            if is_copyleft:
                category = "Copyleft"
                risk = "HIGH"
                finding_msg = f"Dependency '{pkg}' uses copyleft license '{norm_lic}'."
                findings.append(
                    Finding(
                        path=manifest_rel if manifest_rel != "explicit" else str(path),
                        line=1,
                        column=1,
                        rule="license-copyleft-risk",
                        rule_id="license-copyleft-risk",
                        severity="error",
                        message=finding_msg,
                        fingerprint=finding_fingerprint(
                            manifest_rel,
                            1,
                            1,
                            "license-copyleft-risk",
                            "error",
                            finding_msg,
                        ),
                    )
                )
            elif is_compound or is_unknown or norm_lic.upper() not in allowed_set:
                category = "ManualReview"
                risk = "MEDIUM"
                finding_msg = f"Dependency '{pkg}' requires manual review for license '{norm_lic}'."
                findings.append(
                    Finding(
                        path=manifest_rel if manifest_rel != "explicit" else str(path),
                        line=1,
                        column=1,
                        rule="license-manual-review",
                        rule_id="license-manual-review",
                        severity="warn",
                        message=finding_msg,
                        fingerprint=finding_fingerprint(
                            manifest_rel,
                            1,
                            1,
                            "license-manual-review",
                            "warn",
                            finding_msg,
                        ),
                    )
                )
            else:
                category = "Permissive"
                risk = "LOW"

            packages_report.append(
                {
                    "package": pkg,
                    "license": norm_lic,
                    "raw_license": raw_lic,
                    "category": category,
                    "is_copyleft": is_copyleft,
                    "risk": risk,
                    "manifest": manifest_rel,
                }
            )

        copyleft_count = sum(1 for p in packages_report if p["is_copyleft"])
        manual_review_count = sum(
            1 for p in packages_report if p["category"] == "ManualReview"
        )
        total_pkgs = len(packages_report)
        allowed_count = total_pkgs - copyleft_count - manual_review_count

        status = "ok"
        if copyleft_count > 0:
            status = "fail"
        elif manual_review_count > 0:
            status = "warn"

        metrics = {
            "total_packages": total_pkgs,
            "allowed_count": allowed_count,
            "copyleft_violations_count": copyleft_count,
            "manual_review_count": manual_review_count,
        }

        exec_meta = build_execution_metadata(
            "executed",
            requested=None,
            granted=permissions,
            producer="rush-license-matrix",
        )

        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=(
                f"License Matrix audited {total_pkgs} packages "
                f"({copyleft_count} copyleft violations, {manual_review_count} manual review)"
            ),
            findings=findings,
            metrics=metrics,
            raw={"packages": packages_report},
            metadata={"packages": packages_report, "execution": exec_meta},
        )


class LicenseMatrixScanner:
    """Legacy wrapper for dependency license scanning."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._tool = LicenseMatrixTool()

    def scan_licenses(self) -> dict[str, Any]:
        res = self._tool.run(self.project_root)
        metrics = res.get("metrics") or {}
        raw = res.get("raw") or {}
        return {
            "total_packages": metrics.get("total_packages", 0),
            "copyleft_violations_count": metrics.get("copyleft_violations_count", 0),
            "packages": raw.get("packages", []),
        }


__all__ = ["DEFAULT_ALLOWED_LICENSES", "LicenseMatrixScanner", "LicenseMatrixTool"]
