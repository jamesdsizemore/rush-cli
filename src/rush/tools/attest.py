"""SLSA Provenance v1 / in-toto Statement v1 cryptographic attestation draft tool."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .base import ToolFn, ToolResult
from .common import (
    atomic_write_bytes,
    elapsed_ms,
    error_result,
    now_ms,
    run_subprocess,
    skipped_result,
)


class AttestationTool(ToolFn):
    """Generates in-toto Statement v1 / SLSA Provenance v1 draft attestations."""

    name = "attest"

    @property
    def mcp_description(self) -> str:
        return (
            "Generate in-toto Statement v1 SLSA provenance draft for build artifacts. "
            "Exporting requires explicit artifact_write permission."
        )

    def __call__(
        self,
        path: Path,
        *,
        artifact_path: str = "",
        output_path: str = "",
        builder_id: str = "https://rush-cli.org/builder/v1",
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
            artifact_path=artifact_path or None,
            output_path=output_path or None,
            builder_id=builder_id,
            permissions=permissions,
        )

    def run(
        self,
        path: Path,
        *,
        artifact_path: str | Path | None = None,
        output_path: str | Path | None = None,
        builder_id: str = "https://rush-cli.org/builder/v1",
        config: Any = None,
        permissions: Any = None,
    ) -> ToolResult:
        from ..permissions import (
            ExecutionPermissions,
            build_execution_metadata,
            check_permissions,
        )

        start = now_ms()
        target_dir = path if path.is_dir() else path.parent
        target_dir = target_dir.resolve()

        # Subject calculation
        subject_name = "source-tree"
        subject_digest = "unknown"

        if artifact_path:
            raw_art = Path(artifact_path)
            candidate = raw_art if raw_art.is_absolute() else (target_dir / raw_art)
            if candidate.is_file():
                subject_name = candidate.name
                subject_digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            else:
                subject_name = raw_art.name
                subject_digest = hashlib.sha256(
                    str(artifact_path).encode("utf-8")
                ).hexdigest()
        elif path.is_file():
            subject_name = path.name
            subject_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            dist_dir = target_dir / "dist"
            dist_files = (
                [
                    f
                    for f in dist_dir.iterdir()
                    if f.is_file()
                    and (
                        f.suffix in (".whl", ".zip", ".tar", ".gz")
                        or f.name.endswith(".tar.gz")
                    )
                ]
                if dist_dir.is_dir()
                else []
            )
            if dist_files:
                dist_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                target_art = dist_files[0]
                subject_name = target_art.name
                subject_digest = hashlib.sha256(target_art.read_bytes()).hexdigest()
            else:
                commit_res = run_subprocess(
                    ["git", "rev-parse", "HEAD"], cwd=target_dir
                )
                commit_out = (
                    commit_res.stdout.strip()
                    if commit_res.returncode == 0 and commit_res.stdout.strip()
                    else "unknown"
                )
                subject_name = path.name or "source-tree"
                subject_digest = hashlib.sha256(commit_out.encode("utf-8")).hexdigest()

        # Git commit and origin metadata
        commit_res = run_subprocess(["git", "rev-parse", "HEAD"], cwd=target_dir)
        commit_hash = (
            commit_res.stdout.strip()
            if commit_res.returncode == 0 and commit_res.stdout.strip()
            else "unknown"
        )

        origin_res = run_subprocess(
            ["git", "config", "--get", "remote.origin.url"], cwd=target_dir
        )
        repo_url = (
            origin_res.stdout.strip()
            if origin_res.returncode == 0 and origin_res.stdout.strip()
            else "https://github.com/rush-cli/rush"
        )

        time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        statement: dict[str, Any] = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "name": subject_name,
                    "digest": {
                        "sha256": subject_digest,
                    },
                }
            ],
            "predicateType": "https://slsa.dev/provenance/v1",
            "predicate": {
                "buildDefinition": {
                    "buildType": "https://rush-cli.org/build/draft/v1",
                    "externalParameters": {
                        "sourceUri": repo_url,
                        "commit": commit_hash,
                        "entryPoint": "rush attest",
                    },
                    "internalParameters": {
                        "builderId": builder_id,
                    },
                },
                "runDetails": {
                    "builder": {
                        "id": builder_id,
                    },
                    "metadata": {
                        "invocationId": f"rush-{now_ms()}",
                        "startedOn": time_str,
                        "finishedOn": time_str,
                        "assurance": "unsigned_draft",
                    },
                },
            },
        }

        artifacts: list[str] = []
        if output_path:
            required_perms = ExecutionPermissions(artifact_write=True)
            ok, missing = check_permissions(required_perms, permissions)
            if not ok:
                missing_str = ", ".join(missing)
                return skipped_result(
                    self.name,
                    None,
                    f"requires permission: {missing_str}",
                    duration_ms=elapsed_ms(start),
                    metadata={
                        "execution": build_execution_metadata(
                            "skipped",
                            requested=required_perms,
                            granted=permissions,
                            producer="rush-attest",
                        )
                    },
                )
            try:
                from rush.safety.redactor import sanitize_value

                clean_statement = sanitize_value(statement).value
                data_bytes = json.dumps(clean_statement, indent=2).encode("utf-8")
                written = atomic_write_bytes(target_dir, output_path, data_bytes)
                artifacts.append(str(written))
            except Exception as exc:  # noqa: BLE001
                return error_result(
                    self.name,
                    None,
                    f"failed to write attestation artifact: {exc}",
                    duration_ms=elapsed_ms(start),
                )

        exec_meta = build_execution_metadata(
            "executed",
            requested=None,
            granted=permissions,
            producer="rush-attest",
        )

        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status="ok",
            duration_ms=elapsed_ms(start),
            summary=f"Generated in-toto v1 SLSA Provenance v1 draft statement for {subject_name}",
            findings=[],
            raw=statement,
            artifacts=artifacts,
            metadata={"statement": statement, "execution": exec_meta},
        )


class SLSAAttestationGenerator:
    """Legacy wrapper for generating in-toto Statement v1 / SLSA Provenance v1 draft."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._tool = AttestationTool()

    def generate_attestation(self, artifact_path: Path | None = None) -> dict[str, Any]:
        res = self._tool.run(
            self.project_root,
            artifact_path=str(artifact_path) if artifact_path else None,
        )
        return res.get("raw") or {}


__all__ = ["AttestationTool", "SLSAAttestationGenerator"]
