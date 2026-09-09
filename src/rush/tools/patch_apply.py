"""Verify a unified diff in an owned Git worktree before optional promotion."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from rush.io.physical_paths import PhysicalRoot
from rush.permissions import ExecutionPermissions, check_permissions
from rush.safety.redactor import sanitize_value

from .base import ToolFn, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms, run_subprocess


def _git(root: Path, *args: str) -> str:
    result = run_subprocess(["git", "--no-optional-locks", *args], cwd=root)
    if result.returncode != 0:
        raise ValueError(f"Git command failed: {result.stderr or result.stdout}")
    return result.stdout


class PatchApplyTool(ToolFn):
    name = "patch-apply"

    @property
    def mcp_description(self) -> str:
        return (
            "Verify a contained unified diff in an isolated checkout. Defaults to dry-run; "
            "promotion requires artifact-write permission. Returns status, findings, summary."
        )

    def __call__(
        self,
        path: Path = Path("."),
        *,
        patch_file: Path,
        dry_run: bool = True,
        circuit_breaker: bool = True,
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        return self.run(
            path,
            patch_file=patch_file,
            dry_run=dry_run,
            circuit_breaker=circuit_breaker,
            permissions=ExecutionPermissions(artifact_write=allow_artifact_write),
        )

    def run(
        self,
        path: Path,
        config: Any = None,
        *,
        patch_file: Path,
        dry_run: bool = True,
        circuit_breaker: bool = True,
        permissions: ExecutionPermissions | None = None,
    ) -> ToolResult:
        started = now_ms()
        metadata: dict[str, Any] = {
            "dry_run": dry_run,
            "circuit_breaker": circuit_breaker,
            "verified": False,
            "promoted": False,
            "executed_commands": 0,
        }
        status: ToolStatus = "error"
        summary = "Patch application did not complete."
        manager = None
        sandbox = None
        try:
            allowed, missing = check_permissions(
                ExecutionPermissions(artifact_write=not dry_run), permissions
            )
            if not allowed:
                status = "skipped"
                summary = f"Patch promotion requires {', '.join(missing)}."
            else:
                from rush.patch.applier import PatchApplier
                from rush.patch.contracts import PatchContract, VerifierCommandPlan
                from rush.patch.promoter import PatchPromoter, sandbox_diff_digest
                from rush.patch.sandbox import PatchSandboxManager
                from rush.patch.verifier import PatchVerifier

                lexical_root = Path(path).absolute()
                physical = PhysicalRoot(path)
                root = physical.root_path
                patch_path = Path(patch_file)
                if patch_path.is_absolute():
                    patch_path = patch_path.relative_to(lexical_root)
                patch_path = physical.open_contained(patch_path, purpose="read")
                if not patch_path.is_file():
                    raise ValueError(
                        "patch_file must be an ordinary unified-diff file."
                    )
                patch_text = patch_path.read_text(encoding="utf-8")
                if (
                    Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve()
                    != root
                ):
                    raise ValueError(
                        "The invocation path must be the Git project root."
                    )
                base_commit = _git(root, "rev-parse", "HEAD").strip()
                base_tree = _git(root, "rev-parse", "HEAD^{tree}").strip()
                manager = PatchSandboxManager(root)
                sandbox = manager.create_sandbox()
                applied, message = PatchApplier.apply_patch_to_dir(sandbox, patch_text)
                if not applied:
                    summary = message
                else:
                    applied_diff = sandbox_diff_digest(sandbox, root)
                    if not applied_diff:
                        raise ValueError("Patch produced no tracked changes to verify.")
                    command = (sys.executable, "-m", "pytest", "-q", "--tb=short")
                    contract = PatchContract(
                        base_commit=base_commit,
                        base_tree_digest=base_tree,
                        patch_content_digest=hashlib.sha256(
                            patch_text.encode()
                        ).hexdigest(),
                        sandbox_path=sandbox,
                        required_commands=(VerifierCommandPlan(command=command),),
                        config_digest=hashlib.sha256(
                            json.dumps(command).encode()
                        ).hexdigest(),
                    )
                    verifier = PatchVerifier(sandbox, contract)
                    verified, message = verifier.verify_patch()
                    if verifier.last_result is not None:
                        metadata["executed_commands"] = len(
                            verifier.last_result.executed_commands
                        )
                    if not verified:
                        status = "fail"
                        summary = message
                    elif sandbox_diff_digest(sandbox, root) != applied_diff:
                        summary = (
                            "Verification modified tracked files; promotion refused."
                        )
                    else:
                        metadata["verified"] = True
                        if dry_run:
                            status = "ok"
                            summary = (
                                "Patch verified in isolated checkout; source unchanged."
                            )
                        else:
                            promoted, message = PatchPromoter(
                                root
                            ).promote_sandbox_diff(
                                sandbox, contract=contract, permissions=permissions
                            )
                            metadata["promoted"] = promoted
                            status = "ok" if promoted else "fail"
                            summary = message
        except Exception as exc:  # noqa: BLE001 - public tools return canonical errors
            summary = f"Patch application failed: {exc}"
            status = "error"
        finally:
            if manager is not None and sandbox is not None:
                try:
                    manager.cleanup_sandbox(sandbox)
                except Exception as exc:  # noqa: BLE001 - report owned-worktree cleanup failure
                    status = "error"
                    summary = f"{summary} Owned worktree cleanup failed: {exc}"
        return ToolResult(
            tool=self.name,
            engine="git",
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(started),
            summary=str(sanitize_value(summary).value),
            findings=[],
            metadata=metadata,
        )
