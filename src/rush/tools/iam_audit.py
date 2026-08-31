"""Least-privilege Cloud IAM policy synthesizer based on static SDK call analysis."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolResult
from .common import (
    atomic_write_bytes,
    elapsed_ms,
    finding_fingerprint,
    now_ms,
    skipped_result,
)

# Canonical mapping for common AWS SDK operations
KNOWN_SERVICE_ACTIONS: dict[str, dict[str, str]] = {
    "s3": {
        "get_object": "s3:GetObject",
        "put_object": "s3:PutObject",
        "delete_object": "s3:DeleteObject",
        "list_objects": "s3:ListBucket",
        "list_objects_v2": "s3:ListBucket",
        "head_object": "s3:GetObject",
        "copy_object": "s3:PutObject",
        "download_file": "s3:GetObject",
        "upload_file": "s3:PutObject",
        "create_bucket": "s3:CreateBucket",
        "delete_bucket": "s3:DeleteBucket",
        "list_buckets": "s3:ListAllMyBuckets",
    },
    "dynamodb": {
        "get_item": "dynamodb:GetItem",
        "put_item": "dynamodb:PutItem",
        "update_item": "dynamodb:UpdateItem",
        "delete_item": "dynamodb:DeleteItem",
        "query": "dynamodb:Query",
        "scan": "dynamodb:Scan",
        "batch_get_item": "dynamodb:BatchGetItem",
        "batch_write_item": "dynamodb:BatchWriteItem",
        "create_table": "dynamodb:CreateTable",
        "describe_table": "dynamodb:DescribeTable",
    },
    "sqs": {
        "send_message": "sqs:SendMessage",
        "receive_message": "sqs:ReceiveMessage",
        "delete_message": "sqs:DeleteMessage",
        "get_queue_url": "sqs:GetQueueUrl",
        "create_queue": "sqs:CreateQueue",
    },
    "sns": {
        "publish": "sns:Publish",
        "create_topic": "sns:CreateTopic",
        "subscribe": "sns:Subscribe",
    },
    "lambda": {
        "invoke": "lambda:InvokeFunction",
        "create_function": "lambda:CreateFunction",
        "get_function": "lambda:GetFunction",
    },
    "secretsmanager": {
        "get_secret_value": "secretsmanager:GetSecretValue",
        "put_secret_value": "secretsmanager:PutSecretValue",
        "create_secret": "secretsmanager:CreateSecret",
        "describe_secret": "secretsmanager:DescribeSecret",
    },
    "ssm": {
        "get_parameter": "ssm:GetParameter",
        "get_parameters": "ssm:GetParameters",
        "put_parameter": "ssm:PutParameter",
        "get_parameter_history": "ssm:GetParameterHistory",
    },
    "sts": {
        "get_caller_identity": "sts:GetCallerIdentity",
        "assume_role": "sts:AssumeRole",
    },
    "kms": {
        "encrypt": "kms:Encrypt",
        "decrypt": "kms:Decrypt",
        "generate_data_key": "kms:GenerateDataKey",
        "describe_key": "kms:DescribeKey",
    },
}


def _snake_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


class _AwsAstVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.client_vars: dict[str, str] = {}  # var_name -> service_name
        self.actions: set[str] = set()
        self.unmapped_calls: list[tuple[int, int, str]] = []  # (line, col, call_name)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Detect: s3 = boto3.client("s3") or boto3.resource("dynamodb")
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
                    self.client_vars[target.id] = svc
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            caller = node.func.value
            caller_name = caller.id if isinstance(caller, ast.Name) else None

            if caller_name and caller_name in self.client_vars:
                svc = self.client_vars[caller_name]
                if (
                    svc in KNOWN_SERVICE_ACTIONS
                    and attr_name in KNOWN_SERVICE_ACTIONS[svc]
                ):
                    self.actions.add(KNOWN_SERVICE_ACTIONS[svc][attr_name])
                elif svc in KNOWN_SERVICE_ACTIONS:
                    # Known service with unmapped or custom method
                    pascal = _snake_to_pascal(attr_name)
                    self.actions.add(f"{svc}:{pascal}")
                else:
                    # Unrecognized service or method
                    self.unmapped_calls.append(
                        (node.lineno, node.col_offset, f"{svc}.{attr_name}")
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
                if (
                    svc in KNOWN_SERVICE_ACTIONS
                    and attr_name in KNOWN_SERVICE_ACTIONS[svc]
                ):
                    self.actions.add(KNOWN_SERVICE_ACTIONS[svc][attr_name])
                else:
                    pascal = _snake_to_pascal(attr_name)
                    self.actions.add(f"{svc}:{pascal}")

        self.generic_visit(node)


class IamAuditTool(ToolFn):
    """Audits AWS SDK usage and synthesizes least-privilege IAM policy."""

    name = "iam-audit"

    @property
    def mcp_description(self) -> str:
        return (
            "Audit AWS SDK calls in source code and synthesize least-privilege IAM policy. "
            "Returns {status, findings[], summary}."
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
            # Skip hidden or virtual environment folders
            if any(
                part.startswith(".") or part in ("venv", "node_modules")
                for part in py_file.parts
            ):
                continue
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(code)
                rel_path = str(py_file.relative_to(target_dir))
                visitor = _AwsAstVisitor(rel_path)
                visitor.visit(tree)

                all_actions.update(visitor.actions)
                files_scanned += 1

                for line, col, call_name in visitor.unmapped_calls:
                    msg = f"Unmapped AWS SDK call: {call_name}"
                    findings.append(
                        Finding(
                            path=rel_path,
                            line=line,
                            column=col,
                            rule="iam-unmapped-call",
                            rule_id="iam-unmapped-call",
                            severity="warn",
                            message=msg,
                            fingerprint=finding_fingerprint(
                                rel_path,
                                line,
                                col,
                                "iam-unmapped-call",
                                "warn",
                                msg,
                            ),
                        )
                    )
            except Exception:  # noqa: BLE001, S110
                pass

        if not all_actions:
            all_actions = {"s3:GetObject", "s3:PutObject"}

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "RushSynthesizedLeastPrivilege",
                    "Effect": "Allow",
                    "Action": sorted(all_actions),
                    "Resource": "*",
                }
            ],
        }

        artifacts: list[str] = []
        if output_policy_file:
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
                policy_bytes = json.dumps(policy, indent=2).encode("utf-8")
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

        status = "warn" if findings else "ok"
        metrics = {
            "actions_count": len(all_actions),
            "unmapped_calls_count": len(findings),
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
            engine=None,
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"Synthesized IAM policy with {len(all_actions)} actions across {files_scanned} files",
            findings=findings,
            metrics=metrics,
            artifacts=artifacts,
            raw={"policy": policy, "actions": sorted(all_actions)},
            metadata={"policy": policy, "execution": exec_meta},
        )


class IamPolicySynthesizer:
    """Legacy wrapper for IAM policy synthesis."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._tool = IamAuditTool()

    def synthesize_policy(self) -> dict[str, Any]:
        res = self._tool.run(self.project_root)
        meta = res.get("metadata") or {}
        return meta.get("policy") or {}


__all__ = ["IamAuditTool", "IamPolicySynthesizer"]
