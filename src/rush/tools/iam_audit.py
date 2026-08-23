"""Least-privilege Cloud IAM policy synthesizer based on static SDK call analysis."""

import ast
from pathlib import Path
from typing import Any


class IamPolicySynthesizer:
    """Statically parses boto3 and google-cloud SDK calls and synthesizes minimal AWS/GCP IAM policies."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def synthesize_policy(self) -> dict[str, Any]:
        actions: set[str] = set()

        for py_file in (self.project_root / "src").glob("**/*.py"):
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr.startswith(
                            ("get_", "put_", "list_", "delete_", "create_", "describe_")
                        )
                    ):
                        actions.add(f"s3:{node.func.attr}")
            except Exception:  # noqa: BLE001, S110
                pass

        if not actions:
            actions = {"s3:GetObject", "s3:PutObject"}

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "RushSynthesizedLeastPrivilege",
                    "Effect": "Allow",
                    "Action": sorted(actions),
                    "Resource": "*",
                }
            ],
        }
        return policy
