"""Unit tests for IamAuditTool (PR50.7)."""

from __future__ import annotations

import json
from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.iam_audit import IamAuditTool, IamPolicySynthesizer


def test_iam_audit_metadata() -> None:
    tool = IamAuditTool()
    assert tool.name == "iam-audit"
    assert "iam" in tool.mcp_description.lower()
    assert len(tool.mcp_description) < 200


def test_iam_audit_parses_boto3_s3_and_dynamodb_calls(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    code_file = src_dir / "service.py"
    code_file.write_text(
        """
import boto3

def handle_request():
    s3 = boto3.client("s3")
    data = s3.get_object(Bucket="my-bucket", Key="key.json")
    s3.put_object(Bucket="my-bucket", Key="out.json", Body=b"{}")

    ddb = boto3.client("dynamodb")
    ddb.get_item(TableName="my-table", Key={"id": {"S": "123"}})
    ddb.put_item(TableName="my-table", Item={"id": {"S": "123"}})
""",
        encoding="utf-8",
    )

    tool = IamAuditTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "iam-audit"
    assert res["status"] == "ok"
    assert res["findings"] == []

    policy = (res.get("metadata") or {}).get("policy") or (res.get("raw") or {}).get(
        "policy"
    )
    assert policy is not None
    assert policy["Version"] == "2012-10-17"
    statements = policy["Statement"]
    assert len(statements) >= 1
    actions = set(statements[0]["Action"])
    assert "s3:GetObject" in actions
    assert "s3:PutObject" in actions
    assert "dynamodb:GetItem" in actions
    assert "dynamodb:PutItem" in actions


def test_iam_audit_flags_unmapped_call(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    code_file = src_dir / "unmapped.py"
    code_file.write_text(
        """
import boto3

def do_unknown():
    client = boto3.client("custom_service_xyz")
    client.arbitrary_mystery_call()
""",
        encoding="utf-8",
    )

    tool = IamAuditTool()
    res = tool.run(tmp_path)

    assert res["status"] == "warn"
    assert any(f.get("rule_id") == "iam-unmapped-call" for f in res["findings"])


def test_iam_audit_export_policy_permissions(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "app.py").write_text(
        """
import boto3
s3 = boto3.client("s3")
s3.get_object(Bucket="b", Key="k")
""",
        encoding="utf-8",
    )

    tool = IamAuditTool()
    # Without artifact_write permission
    res_skipped = tool.run(
        tmp_path,
        output_policy_file="policy.json",
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert res_skipped["status"] == "skipped"
    assert (
        "artifact-write" in res_skipped["summary"]
        or "artifact_write" in res_skipped["summary"]
    )
    assert not (tmp_path / "policy.json").exists()

    # With artifact_write permission
    res_ok = tool.run(
        tmp_path,
        output_policy_file="policy.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res_ok["status"] == "ok"
    out_file = tmp_path / "policy.json"
    assert out_file.exists()
    assert str(out_file) in res_ok.get("artifacts", [])

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["Version"] == "2012-10-17"


def test_iam_audit_legacy_synthesizer_backward_compatibility(
    tmp_path: Path,
) -> None:
    synth = IamPolicySynthesizer(project_root=tmp_path)
    policy = synth.synthesize_policy()

    assert policy["Version"] == "2012-10-17"
    assert len(policy["Statement"]) > 0
    assert "s3:GetObject" in policy["Statement"][0]["Action"]
