"""Phase 59 Engine Support Policy, Isolation Harness, and Conformance Enforcement.

Architecture & Remediation R-014.
Enforces governance/engine-support.toml taxonomy, deterministic capability discovery
without ambient PATH pollution, and non-permissive release gate verification.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Self

from rush.tools import common
from rush.tools.common import clear_binary_cache, resolve_binary

SupportClass = Literal["mandatory", "supported-optional", "best-effort"]


class EngineConformanceError(Exception):
    """Base exception for engine conformance and governance violations."""


class AllSkippedViolationError(EngineConformanceError):
    """Raised when an engine that cannot pass with all skipped results returns all skipped."""


class AmbientPathPollutionError(EngineConformanceError):
    """Raised when an engine resolves to an ambient unpinned host binary outside isolated PATH."""


class ReleaseGateFailureError(EngineConformanceError):
    """Raised when a mandatory release-gate engine fails verification or is absent."""


@dataclass(frozen=True)
class EngineTaxonomyRecord:
    """Taxonomy definition for an engine family from engine-support.toml."""

    family: str
    support_class: SupportClass
    executable: str
    version_command: str
    can_pass_all_skipped: bool
    permitted_skip_reason: str
    clean_fixture: str
    finding_fixture: str
    malformed_fixture: str | None = None


class FixedPathEnvironment:
    """Context manager isolating binary discovery from ambient host PATH pollution."""

    def __init__(self, fixed_path: Path | str | None = None) -> None:
        self.fixed_path = Path(fixed_path) if fixed_path is not None else None
        self._prev_path: str | None = None
        self._prev_venv_scripts = None

    def __enter__(self) -> Self:
        clear_binary_cache()
        self._prev_path = os.environ.get("PATH")
        if self.fixed_path is not None:
            os.environ["PATH"] = str(self.fixed_path)
        else:
            os.environ["PATH"] = ""

        # Suppress ambient venv script searching while in isolated context
        self._prev_venv_scripts = common._venv_scripts_dir
        common._venv_scripts_dir = lambda: None
        clear_binary_cache()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._prev_path is not None:
            os.environ["PATH"] = self._prev_path
        else:
            os.environ.pop("PATH", None)
        if self._prev_venv_scripts is not None:
            common._venv_scripts_dir = self._prev_venv_scripts
        clear_binary_cache()


class EngineSupportPolicy:
    """Engine support governance policy and execution validator."""

    def __init__(
        self, records: dict[str, EngineTaxonomyRecord], policy_version: str = ""
    ) -> None:
        self.records = records
        self.policy_version = policy_version

    @classmethod
    def load(cls, manifest_path: Path | None = None) -> EngineSupportPolicy:
        """Load engine taxonomy policy from engine-support.toml."""
        if manifest_path is None:
            candidates = [
                Path("governance/engine-support.toml"),
                Path(__file__).resolve().parent.parent.parent.parent
                / "governance"
                / "engine-support.toml",
            ]
            for candidate in candidates:
                if candidate.exists():
                    manifest_path = candidate
                    break
            if manifest_path is None:
                manifest_path = Path("governance/engine-support.toml")

        if not manifest_path.exists():
            raise EngineConformanceError(
                f"Engine support policy manifest not found: {manifest_path}"
            )

        with open(manifest_path, "rb") as f:
            data = tomllib.load(f)

        policy_version = data.get("manifest", {}).get("policy_version", "")
        records: dict[str, EngineTaxonomyRecord] = {}

        for entry in data.get("engines", []):
            family = entry["family"]
            fixture_matrix = entry.get("fixture_matrix", {})
            record = EngineTaxonomyRecord(
                family=family,
                support_class=entry["support_class"],
                executable=entry["executable"],
                version_command=entry["version_command"],
                can_pass_all_skipped=bool(entry["can_pass_all_skipped"]),
                permitted_skip_reason=entry.get("permitted_skip_reason", ""),
                clean_fixture=fixture_matrix.get("clean", ""),
                finding_fixture=fixture_matrix.get("finding", ""),
                malformed_fixture=fixture_matrix.get("malformed"),
            )
            records[family] = record

        return cls(records=records, policy_version=policy_version)

    def get_family(self, family_name: str) -> EngineTaxonomyRecord:
        """Retrieve taxonomy record for an engine family."""
        if family_name not in self.records:
            raise EngineConformanceError(f"Unknown engine family: {family_name}")
        return self.records[family_name]

    def validate_execution_result(
        self, family_name: str, results: list[dict[str, Any]]
    ) -> None:
        """Enforce all-skipped non-permissive contracts for supported families."""
        record = self.get_family(family_name)
        if not record.can_pass_all_skipped and (
            not results or all(item.get("status") == "skipped" for item in results)
        ):
            raise AllSkippedViolationError(
                f"Engine family '{family_name}' cannot pass with all-skipped results."
            )

    def verify_release_gate(self, engine_name: str = "mypy") -> bool:
        """Verify explicit release gate engine is provisioned and passes verification."""
        bin_path = resolve_binary(engine_name)
        if bin_path is None:
            raise ReleaseGateFailureError(
                f"Release gate engine '{engine_name}' is not installed or available on PATH"
            )

        # Run version command
        proc_ver = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc_ver.returncode != 0:
            raise ReleaseGateFailureError(
                f"Release gate engine '{engine_name}' version check failed: {proc_ver.stderr or proc_ver.stdout}"
            )

        # Run verification check on src/rush
        proc_check = subprocess.run(
            [bin_path, "src/rush"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc_check.returncode != 0:
            raise ReleaseGateFailureError(
                f"Release gate engine '{engine_name}' verification failed with exit code "
                f"{proc_check.returncode}: {proc_check.stderr or proc_check.stdout}"
            )

        return True

    def discover_engine(self, family_name: str) -> str | None:
        """Discover engine path deterministically respecting active environment."""
        record = self.get_family(family_name)
        if record.executable in ("python-built-in", "python-stdlib", "python-module"):
            return sys.executable
        return resolve_binary(record.executable)

    def discover_capabilities(self) -> dict[str, bool]:
        """Produce deterministic capability matrix for all 19 engine families."""
        return {
            family: self.discover_engine(family) is not None for family in self.records
        }

    def assert_no_ambient_pollution(
        self, family_name: str, allowed_root: Path | str
    ) -> str | None:
        """Assert resolved engine executable is located strictly within allowed_root."""
        resolved = self.discover_engine(family_name)
        if resolved is None:
            return None

        record = self.get_family(family_name)
        if record.executable in ("python-built-in", "python-stdlib", "python-module"):
            return resolved

        root = Path(allowed_root).resolve()
        resolved_path = Path(resolved).resolve()
        try:
            resolved_path.relative_to(root)
        except ValueError:
            raise AmbientPathPollutionError(
                f"Engine '{family_name}' resolved to ambient binary '{resolved}' outside "
                f"allowed isolated path '{root}'"
            )
        return resolved
