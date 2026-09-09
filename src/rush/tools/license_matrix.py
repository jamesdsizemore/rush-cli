"""Dependency license risk and open-source copyleft compliance auditor."""

from __future__ import annotations

import importlib.metadata
import json
import tomllib
from pathlib import Path
from typing import Any

from license_expression import (
    AND,
    OR,
    ExpressionError,
    LicenseSymbol,
    LicenseWithExceptionSymbol,
    Licensing,
    get_spdx_licensing,
)

from .base import Finding, ToolFn, ToolResult, ToolStatus
from .common import elapsed_ms, finding_fingerprint, now_ms
from .schemas import LicenseMatrixMetrics

# Canonical allowed permissive licenses
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
    "Zlib",
)

PERMISSIVE_LICENSES: set[str] = {lic.upper() for lic in DEFAULT_ALLOWED_LICENSES}

WEAK_COPYLEFT_LICENSES: set[str] = {
    "LGPL-2.0-ONLY",
    "LGPL-2.0-OR-LATER",
    "LGPL-2.1-ONLY",
    "LGPL-2.1-OR-LATER",
    "LGPL-3.0-ONLY",
    "LGPL-3.0-OR-LATER",
    "MPL-1.1",
    "MPL-2.0",
    "CDDL-1.0",
    "CDDL-1.1",
    "EPL-1.0",
    "EPL-2.0",
}

STRONG_COPYLEFT_LICENSES: set[str] = {
    "GPL-2.0-ONLY",
    "GPL-2.0-OR-LATER",
    "GPL-3.0-ONLY",
    "GPL-3.0-OR-LATER",
    "AGPL-3.0-ONLY",
    "AGPL-3.0-OR-LATER",
    "SSPL-1.0",
    "EUPL-1.1",
    "EUPL-1.2",
    "OSL-3.0",
}
KNOWN_EXCEPTIONS = frozenset(
    symbol.key.upper()
    for symbol in get_spdx_licensing().known_symbols.values()
    if symbol.is_exception
)
_CATEGORY_RANK = {
    "permissive": 0,
    "manual-review": 1,
    "weak-copyleft": 2,
    "strong-copyleft": 3,
    "proprietary": 4,
}
_CATEGORY_RISK = {
    "permissive": "LOW",
    "manual-review": "MEDIUM",
    "weak-copyleft": "MEDIUM",
    "strong-copyleft": "HIGH",
    "proprietary": "HIGH",
}


def _classify_symbol(symbol_name: str) -> str:
    """Classify a single normalized SPDX license symbol into a risk tier."""
    sym_upper = symbol_name.upper()
    if sym_upper in PERMISSIVE_LICENSES:
        return "permissive"
    if sym_upper in WEAK_COPYLEFT_LICENSES:
        return "weak-copyleft"
    if sym_upper in STRONG_COPYLEFT_LICENSES:
        return "strong-copyleft"
    if sym_upper in {"PROPRIETARY", "COMMERCIAL"}:
        return "proprietary"
    return "unclassified"


def _evaluate_license_node(node: Any, allowed_set: set[str]) -> tuple[str, bool]:
    if isinstance(node, LicenseWithExceptionSymbol):
        if node.exception_symbol.key.upper() not in KNOWN_EXCEPTIONS:
            return "manual-review", True
        # No exception waiver policy exists; retain the base obligation.
        return _evaluate_license_node(node.license_symbol, allowed_set)
    if isinstance(node, (AND, OR)):
        children = [_evaluate_license_node(arg, allowed_set) for arg in node.args]
        if not children or any(unknown for _, unknown in children):
            return "manual-review", True
        select = max if isinstance(node, AND) else min
        return select(
            (category for category, _ in children), key=_CATEGORY_RANK.__getitem__
        ), False
    if isinstance(node, LicenseSymbol):
        category = _classify_symbol(node.key)
        if category == "unclassified":
            return "manual-review", True
        if category == "permissive" and node.key.upper() not in allowed_set:
            return "manual-review", False
        return category, False
    return "manual-review", True


def evaluate_spdx_expression(
    expr_str: str,
    licensing: Licensing,
    allowed_set: set[str],
) -> tuple[str, str, list[str]]:
    """Evaluates an SPDX license expression using boolean AST resolution.

    Returns:
        (category, risk_level, list_of_symbols)
    """
    clean_expr = expr_str.strip()
    if not clean_expr:
        return "unspecified", "MEDIUM", []

    try:
        parsed = licensing.parse(clean_expr)
    except ExpressionError:
        return "manual-review", "MEDIUM", [clean_expr]

    if parsed is None:
        return "unspecified", "MEDIUM", []

    symbol_names = [symbol.key for symbol in licensing.license_symbols(parsed)]
    category, _ = _evaluate_license_node(parsed, allowed_set)
    return category, _CATEGORY_RISK[category], symbol_names


def _lookup_python_pkg_license(pkg_name: str) -> str:
    """Lookup license of an installed Python package via importlib.metadata."""
    try:
        meta = importlib.metadata.metadata(pkg_name)
        lic = meta.get("License")
        if (
            lic
            and lic.strip()
            and lic.strip().lower() not in ("unspecified", "none", "")
        ):
            return lic.strip()
        # Inspect trove classifiers
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
                    return "GPL-3.0-only"
                return part
    except Exception:  # noqa: BLE001, S110
        pass
    return "unspecified"


def _extract_pyproject_deps(pyproject_path: Path) -> set[str]:
    """Parse dependencies from pyproject.toml using stdlib tomllib."""
    deps: set[str] = set()
    try:
        data = tomllib.loads(
            pyproject_path.read_text(encoding="utf-8", errors="ignore")
        )
        project_table = data.get("project", {})

        # Standard dependencies
        for dep in project_table.get("dependencies", []):
            pkg = (
                dep.split(";")[0]
                .split(">")[0]
                .split("<")[0]
                .split("=")[0]
                .split("~")[0]
                .split("[")[0]
                .strip()
            )
            if pkg:
                deps.add(pkg.lower())

        # Optional dependencies
        opt_deps = project_table.get("optional-dependencies", {})
        if isinstance(opt_deps, dict):
            for opt_list in opt_deps.values():
                if isinstance(opt_list, list):
                    for dep in opt_list:
                        pkg = (
                            dep.split(";")[0]
                            .split(">")[0]
                            .split("<")[0]
                            .split("=")[0]
                            .split("~")[0]
                            .split("[")[0]
                            .strip()
                        )
                        if pkg:
                            deps.add(pkg.lower())

        # Poetry dependencies
        tool_poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        if isinstance(tool_poetry, dict):
            for k in tool_poetry:
                if k.lower() != "python":
                    deps.add(k.lower())
    except Exception:  # noqa: BLE001, S110
        pass
    return deps


def _extract_package_json_deps(pkg_json_path: Path) -> set[str]:
    """Parse dependencies from package.json using stdlib json."""
    deps: set[str] = set()
    try:
        data = json.loads(pkg_json_path.read_text(encoding="utf-8", errors="ignore"))
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            if isinstance(data.get(section), dict):
                deps.update(k.lower() for k in data[section])
    except Exception:  # noqa: BLE001, S110
        pass
    return deps


def _extract_cargo_toml_deps(cargo_path: Path) -> set[str]:
    """Parse dependencies from Cargo.toml using stdlib tomllib."""
    deps: set[str] = set()
    try:
        data = tomllib.loads(cargo_path.read_text(encoding="utf-8", errors="ignore"))
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            table = data.get(section, {})
            if isinstance(table, dict):
                deps.update(k.lower() for k in table)
    except Exception:  # noqa: BLE001, S110
        pass
    return deps


class LicenseMatrixTool(ToolFn):
    """Audits dependencies for license compliance and copyleft risks using SPDX parsing."""

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

        licensing = Licensing()
        allowed_set = {lic.upper() for lic in allowed_licenses}

        discovered_pkgs: dict[str, str] = {}  # pkg -> manifest relative path

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

        explicit_overrides = dict(package_licenses or {})
        for p in explicit_overrides:
            if p not in discovered_pkgs:
                discovered_pkgs[p] = "explicit"

        packages_report: list[dict[str, Any]] = []
        findings: list[Finding] = []

        for pkg, manifest_rel in sorted(discovered_pkgs.items()):
            if pkg in explicit_overrides:
                raw_lic = explicit_overrides[pkg]
            else:
                raw_lic = _lookup_python_pkg_license(pkg)

            category, risk_level, symbols = evaluate_spdx_expression(
                raw_lic, licensing, allowed_set
            )

            is_copyleft = category in ("strong-copyleft", "weak-copyleft")

            if category in {"strong-copyleft", "proprietary"}:
                rule = (
                    "license-copyleft-risk"
                    if is_copyleft
                    else "license-proprietary-risk"
                )
                msg = f"Dependency '{pkg}' uses {category} license '{raw_lic}'."
                findings.append(
                    Finding(
                        path=manifest_rel if manifest_rel != "explicit" else str(path),
                        line=1,
                        column=1,
                        rule=rule,
                        rule_id=rule,
                        severity="error",
                        message=msg,
                        fingerprint=finding_fingerprint(
                            manifest_rel, 1, 1, rule, "error", msg
                        ),
                    )
                )
            elif category in ("weak-copyleft", "manual-review", "unspecified"):
                msg = f"Dependency '{pkg}' requires manual review for license '{raw_lic}' (tier: {category})."
                findings.append(
                    Finding(
                        path=manifest_rel if manifest_rel != "explicit" else str(path),
                        line=1,
                        column=1,
                        rule="license-manual-review",
                        rule_id="license-manual-review",
                        severity="warn",
                        message=msg,
                        fingerprint=finding_fingerprint(
                            manifest_rel, 1, 1, "license-manual-review", "warn", msg
                        ),
                    )
                )

            packages_report.append(
                {
                    "package": pkg,
                    "license": raw_lic,
                    "category": category,
                    "risk": risk_level,
                    "is_copyleft": is_copyleft,
                    "symbols": symbols,
                    "manifest": manifest_rel,
                }
            )

        total_pkgs = len(packages_report)
        copyleft_count = sum(1 for p in packages_report if p["is_copyleft"])
        incompatible_count = sum(
            1
            for p in packages_report
            if p["is_copyleft"] or p["category"] == "proprietary"
        )
        unresolved_count = sum(
            1
            for p in packages_report
            if p["category"] in ("unspecified", "manual-review")
        )
        compliant_count = sum(
            1 for p in packages_report if p["category"] == "permissive"
        )

        compliance_score = (
            round(compliant_count / total_pkgs, 4) if total_pkgs > 0 else 1.0
        )

        status: ToolStatus = "ok"
        if incompatible_count > 0:
            status = "fail"
        elif unresolved_count > 0:
            status = "warn"

        metrics_obj = LicenseMatrixMetrics(
            compliance_score=compliance_score,
            packages_audited=total_pkgs,
            incompatible_count=incompatible_count,
            unresolved_count=unresolved_count,
        )

        metrics = {
            "compliance_score": metrics_obj.compliance_score,
            "packages_audited": metrics_obj.packages_audited,
            "incompatible_count": metrics_obj.incompatible_count,
            "unresolved_count": metrics_obj.unresolved_count,
            "total_packages": total_pkgs,
            "copyleft_violations_count": copyleft_count,
        }

        exec_meta = build_execution_metadata(
            "executed",
            requested=None,
            granted=permissions,
            producer="rush-license-matrix",
        )

        return ToolResult(
            tool=self.name,
            engine="license-expression",
            engine_version="30.4.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=(
                f"License Matrix audited {total_pkgs} packages "
                f"({copyleft_count} copyleft violations, {unresolved_count} unresolved, "
                f"compliance_score: {compliance_score})"
            ),
            findings=findings,
            metrics=dict(metrics),
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
            "total_packages": metrics.get("packages_audited", 0),
            "copyleft_violations_count": metrics.get("incompatible_count", 0),
            "packages": raw.get("packages", []),
        }


__all__ = ["DEFAULT_ALLOWED_LICENSES", "LicenseMatrixScanner", "LicenseMatrixTool"]
