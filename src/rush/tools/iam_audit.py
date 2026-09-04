"""Least-privilege Cloud IAM policy synthesizer and Terraform/HCL2 audit engine."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import hcl2

from .base import Finding, ToolFn, ToolResult
from .common import (
    atomic_write_bytes,
    elapsed_ms,
    finding_fingerprint,
    now_ms,
    skipped_result,
)
from .schemas import IamAuditMetrics

_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources" / "iam"


def _load_action_registry(filename: str) -> dict[str, dict[str, str]]:
    registry_file = _RESOURCES_DIR / filename
    if registry_file.is_file():
        try:
            return json.loads(registry_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001, S110
            pass
    return {}


AWS_ACTION_REGISTRY = _load_action_registry("aws_actions.json")
GCP_ACTION_REGISTRY = _load_action_registry("gcp_actions.json")
AZURE_ACTION_REGISTRY = _load_action_registry("azure_actions.json")

PRIVILEGE_ESCALATION_ACTIONS: set[str] = {
    "iam:PassRole",
    "iam:CreatePolicyVersion",
    "iam:SetDefaultPolicyVersion",
    "iam:AttachUserPolicy",
    "iam:AttachGroupPolicy",
    "iam:AttachRolePolicy",
    "iam:PutUserPolicy",
    "iam:PutGroupPolicy",
    "iam:PutRolePolicy",
    "iam:CreateAccessKey",
    "iam:CreateLoginProfile",
    "iam:UpdateLoginProfile",
}


def _snake_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


class _CloudAstVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.client_vars: dict[str, str] = {}  # var_name -> service_identifier
        self.actions: set[str] = set()
        self.unmapped_calls: list[tuple[int, int, str]] = []  # (line, col, call_name)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Detect AWS: s3 = boto3.client("s3") or boto3.resource("dynamodb")
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr in ("client", "resource")
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
        ):
            svc = str(node.value.args[0].value).lower()
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.client_vars[target.id] = f"aws:{svc}"
        # Detect GCP: storage_client = storage.Client()
        elif (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "Client"
            and isinstance(node.value.func.value, ast.Name)
        ):
            cloud_module = node.value.func.value.id.lower()
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.client_vars[target.id] = f"gcp:{cloud_module}"
        # Detect Azure: blob_service = BlobServiceClient(...)
        elif (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and "BlobService" in node.value.func.id
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.client_vars[target.id] = "azure:blob"

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            caller = node.func.value
            caller_name = caller.id if isinstance(caller, ast.Name) else None

            if caller_name and caller_name in self.client_vars:
                svc_id = self.client_vars[caller_name]
                prefix, svc = svc_id.split(":", 1)
                if prefix == "aws":
                    actions_for_svc = AWS_ACTION_REGISTRY.get(svc, {})
                    if attr_name in actions_for_svc:
                        self.actions.add(actions_for_svc[attr_name])
                    else:
                        pascal = _snake_to_pascal(attr_name)
                        self.actions.add(f"{svc}:{pascal}")
                elif prefix == "gcp":
                    actions_for_svc = GCP_ACTION_REGISTRY.get(svc, {})
                    if attr_name in actions_for_svc:
                        self.actions.add(actions_for_svc[attr_name])
                    else:
                        self.unmapped_calls.append(
                            (node.lineno, node.col_offset, f"{svc_id}.{attr_name}")
                        )
                elif prefix == "azure":
                    actions_for_svc = AZURE_ACTION_REGISTRY.get(svc, {})
                    if attr_name in actions_for_svc:
                        self.actions.add(actions_for_svc[attr_name])
                    else:
                        self.unmapped_calls.append(
                            (node.lineno, node.col_offset, f"{svc_id}.{attr_name}")
                        )
            elif attr_name.startswith(
                ("get_", "put_", "list_", "delete_", "create_", "describe_")
            ) and caller_name in (
                "s3",
                "s3_client",
                "dynamodb",
                "sqs",
                "sns",
                "kms",
                "sts",
                "ssm",
            ):
                svc = caller_name.split("_")[0]
                actions_for_svc = AWS_ACTION_REGISTRY.get(svc, {})
                if attr_name in actions_for_svc:
                    self.actions.add(actions_for_svc[attr_name])
                else:
                    pascal = _snake_to_pascal(attr_name)
                    self.actions.add(f"{svc}:{pascal}")

        self.generic_visit(node)


def _scan_terraform_ast(
    tf_file: Path,
    rel_path: str,
    findings: list[Finding],
) -> tuple[int, int, int]:
    """Parses Terraform HCL2 file and identifies wildcards, escalations, and statement counts.

    Returns:
        (total_statements, wildcard_count, escalation_count)
    """
    total_statements = 0
    wildcard_count = 0
    escalation_count = 0

    try:
        content = tf_file.read_text(encoding="utf-8", errors="ignore")
        parsed = hcl2.loads(content)
    except Exception:  # noqa: BLE001
        return 0, 0, 0

    # Walk resources
    resources = parsed.get("resource", [])
    for res_block in resources:
        if not isinstance(res_block, dict):
            continue
        for res_type, res_instances in res_block.items():
            clean_type = res_type.strip('"')
            if "iam" not in clean_type.lower() and "policy" not in clean_type.lower():
                continue
            if not isinstance(res_instances, dict):
                continue
            for inst_name, inst_body in res_instances.items():
                if not isinstance(inst_body, dict):
                    continue
                policy_raw = inst_body.get("policy")
                if isinstance(policy_raw, str):
                    # Check if jsonencode or string
                    match_actions = re.findall(
                        r'["\']?Action["\']?\s*[:=]\s*(?:\[(.*?)\]|["\'](.*?)["\'])',
                        policy_raw,
                        re.IGNORECASE,
                    )
                    for multi_act, single_act in match_actions:
                        total_statements += 1
                        act_str = single_act or multi_act
                        if "*" in act_str:
                            wildcard_count += 1
                            msg = f"Wildcard IAM action '{act_str.strip()}' in resource '{clean_type}.{inst_name.strip('"')}'"
                            findings.append(
                                Finding(
                                    path=rel_path,
                                    line=1,
                                    column=1,
                                    rule="iam-wildcard-action",
                                    rule_id="iam-wildcard-action",
                                    severity="warn",
                                    message=msg,
                                    fingerprint=finding_fingerprint(
                                        rel_path,
                                        1,
                                        1,
                                        "iam-wildcard-action",
                                        "warn",
                                        msg,
                                    ),
                                )
                            )
                        for esc in PRIVILEGE_ESCALATION_ACTIONS:
                            if esc in act_str:
                                escalation_count += 1
                                msg = f"Privilege escalation action '{esc}' granted in resource '{clean_type}.{inst_name.strip('"')}'"
                                findings.append(
                                    Finding(
                                        path=rel_path,
                                        line=1,
                                        column=1,
                                        rule="iam-privilege-escalation",
                                        rule_id="iam-privilege-escalation",
                                        severity="error",
                                        message=msg,
                                        fingerprint=finding_fingerprint(
                                            rel_path,
                                            1,
                                            1,
                                            "iam-privilege-escalation",
                                            "error",
                                            msg,
                                        ),
                                    )
                                )

    return total_statements, wildcard_count, escalation_count


class IamAuditTool(ToolFn):
    """Audits cloud SDK API calls and Terraform policies; synthesizes least-privilege IAM policies."""

    name = "iam-audit"

    @property
    def mcp_description(self) -> str:
        return (
            "Audit cloud SDK calls in code, inspect Terraform HCL2 policies for wildcards, and synthesize "
            "minimal least-privilege IAM policies. Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
        output_policy_file: str = "",
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
            output_policy_file=output_policy_file or None,
            permissions=permissions,
        )

    def run(
        self,
        path: Path,
        *,
        output_policy_file: str | Path | None = None,
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

        all_actions: set[str] = set()
        findings: list[Finding] = []
        files_scanned = 0

        # Scan python files
        py_files = (
            list(target_dir.glob("**/*.py")) if target_dir.is_dir() else [target_dir]
        )
        for py_file in py_files:
            if any(
                part.startswith(".") or part in ("venv", "node_modules")
                for part in py_file.parts
            ):
                continue
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(code)
                rel_path = str(py_file.relative_to(target_dir))
                visitor = _CloudAstVisitor(rel_path)
                visitor.visit(tree)
                all_actions.update(visitor.actions)
                for line, col, call_name in visitor.unmapped_calls:
                    msg = f"Unmapped cloud SDK method call: {call_name}"
                    findings.append(
                        Finding(
                            path=rel_path,
                            line=line,
                            column=col + 1,
                            rule="iam-unmapped-call",
                            rule_id="iam-unmapped-call",
                            severity="warn",
                            message=msg,
                            fingerprint=finding_fingerprint(
                                rel_path,
                                line,
                                col + 1,
                                "iam-unmapped-call",
                                "warn",
                                msg,
                            ),
                        )
                    )
                files_scanned += 1
            except Exception:  # noqa: BLE001, S110
                pass

        # Scan Terraform files using python-hcl2
        total_statements = 0
        wildcard_count = 0
        escalation_count = 0

        if path.is_file() and path.suffix == ".tf":
            tf_files = [path]
        elif target_dir.is_dir():
            tf_files = list(target_dir.glob("**/*.tf"))
        else:
            tf_files = []
        for tf_file in tf_files:
            if any(
                part.startswith(".") or part in ("venv", "node_modules", ".terraform")
                for part in tf_file.parts
            ):
                continue
            rel_tf = str(tf_file.relative_to(target_dir))
            stmts, wild, esc = _scan_terraform_ast(tf_file, rel_tf, findings)
            total_statements += stmts
            wildcard_count += wild
            escalation_count += esc
            files_scanned += 1

        # Synthesize real least-privilege policy (Zero fake fallbacks!)
        policy: dict[str, Any] | None = None
        if all_actions:
            # Partition actions by service to build clean least-privilege statements
            statements: list[dict[str, Any]] = []
            aws_actions = [
                a
                for a in sorted(all_actions)
                if ":" in a and not a.startswith(("gcp:", "azure:"))
            ]
            if aws_actions:
                statements.append(
                    {
                        "Sid": "RushSynthesizedLeastPrivilegeAWS",
                        "Effect": "Allow",
                        "Action": aws_actions,
                        "Resource": "*",
                    }
                )
            policy = {
                "Version": "2012-10-17",
                "Statement": statements,
            }

        artifacts: list[str] = []
        if output_policy_file and policy:
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
                            producer="rush-iam-audit",
                        )
                    },
                )
            try:
                from rush.safety.redactor import sanitize_value

                clean_policy = sanitize_value(policy).value
                policy_bytes = json.dumps(clean_policy, indent=2).encode("utf-8")
                written = atomic_write_bytes(
                    target_dir, output_policy_file, policy_bytes
                )
                artifacts.append(str(written))
            except Exception as exc:  # noqa: BLE001
                return skipped_result(
                    self.name,
                    None,
                    f"failed to write policy artifact: {exc}",
                    duration_ms=elapsed_ms(start),
                )

        # Risk score computation: 0.0 (safe) to 1.0 (critical risk)
        base_risk = 0.0
        if wildcard_count > 0:
            base_risk += min(0.5, wildcard_count * 0.25)
        if escalation_count > 0:
            base_risk += min(0.5, escalation_count * 0.25)
        risk_score = round(min(1.0, max(0.0, base_risk)), 2)

        has_errors = any(f.get("severity") == "error" for f in findings)
        status = "fail" if has_errors else ("warn" if findings else "ok")

        metrics_obj = IamAuditMetrics(
            risk_score=risk_score,
            total_statements=total_statements,
            wildcard_actions_count=wildcard_count,
            privilege_escalation_paths=escalation_count,
        )

        metrics = {
            "risk_score": metrics_obj.risk_score,
            "total_statements": metrics_obj.total_statements,
            "wildcard_actions_count": metrics_obj.wildcard_actions_count,
            "privilege_escalation_paths": metrics_obj.privilege_escalation_paths,
            "actions_count": len(all_actions),
            "files_scanned": files_scanned,
        }

        exec_meta = build_execution_metadata(
            "executed",
            requested=None,
            granted=permissions,
            producer="rush-iam-audit",
        )

        return ToolResult(
            tool=self.name,
            engine="python-hcl2",
            engine_version="8.1.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=(
                f"IAM audit scanned {files_scanned} files, discovered {len(all_actions)} actions "
                f"({wildcard_count} wildcards, {escalation_count} escalation paths, risk_score: {risk_score})"
            ),
            findings=findings,
            metrics=metrics,
            artifacts=artifacts if artifacts else None,
            raw={"actions": sorted(all_actions), "policy": policy},
            metadata={"policy": policy, "execution": exec_meta},
        )


class IamPolicySynthesizer:
    """Legacy wrapper for IAM policy synthesis."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._tool = IamAuditTool()

    def synthesize(self) -> dict[str, Any]:
        res = self._tool.run(self.project_root)
        meta = res.get("metadata") or {}
        return meta.get("policy") or {}

    def synthesize_policy(self) -> dict[str, Any]:
        return self.synthesize()


__all__ = ["AWS_ACTION_REGISTRY", "IamAuditTool", "IamPolicySynthesizer"]
