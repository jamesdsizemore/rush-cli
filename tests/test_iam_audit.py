"""Unit tests for IamAuditTool with multi-cloud AST analysis, Terraform HCL2 parsing, and strict metrics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rush.permissions import ExecutionPermissions
from rush.tools.iam_audit import IamAuditTool, IamPolicySynthesizer
from rush.tools.schemas import IamAuditMetrics


def test_iam_audit_metadata() -> None:
    tool = IamAuditTool()
    assert tool.name == "iam-audit"
    assert "iam" in tool.mcp_description.lower()
    assert len(tool.mcp_description) < 200


def test_iam_discovery_is_project_relative(tmp_path: Path) -> None:
    results = []
    for parent in ("ordinary", ".hidden"):
        project = tmp_path / parent / "project"
        project.mkdir(parents=True)
        (project / "app.py").write_text(
            'import boto3\ns3 = boto3.client("s3")\ns3.get_object()\n'
        )
        for child in (".hidden", "venv", "node_modules"):
            excluded = project / child
            excluded.mkdir()
            (excluded / "ignored.py").write_text("s3.delete_object()\n")
            (excluded / "ignored.tf").write_text('resource "aws_iam_policy" "bad" {}')
        results.append(IamAuditTool().run(project))
    for result in results:
        assert result["status"] == "ok"
        assert result["metrics"]["files_scanned"] == 1
        assert result["raw"]["actions"] == ["s3:GetObject"]
    assert results[0]["metrics"] == results[1]["metrics"]
    assert results[0]["findings"] == results[1]["findings"]


def test_iam_read_denial_is_error(tmp_path: Path) -> None:
    for suffix in ("py", "tf"):
        project = tmp_path / suffix
        project.mkdir()
        (project / f"app.{suffix}").write_text("x = 1\n")
        with patch.object(Path, "read_text", side_effect=PermissionError):
            result = IamAuditTool().run(project)
        assert result["status"] == "error"
        assert "read" in result["summary"].lower()


def test_iam_discovery_denial_is_error(tmp_path: Path) -> None:
    with patch("os.scandir", side_effect=PermissionError):
        result = IamAuditTool().run(tmp_path)
    assert result["status"] == "error"
    assert "read" in result["summary"].lower()


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

    policy = (res.get("metadata") or {}).get("policy")
    assert policy is not None
    assert policy["Version"] == "2012-10-17"
    statements = policy["Statement"]
    assert len(statements) == 1
    actions = set(statements[0]["Action"])
    assert "s3:GetObject" in actions
    assert "s3:PutObject" in actions
    assert "dynamodb:GetItem" in actions
    assert "dynamodb:PutItem" in actions

    # Strict schema validation
    metrics = res.get("metrics") or {}
    validated = IamAuditMetrics.model_validate(metrics)
    assert validated.risk_score == 0.0
    assert validated.wildcard_actions_count == 0


def test_iam_audit_parses_gcp_and_azure_calls(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    code_file = src_dir / "cloud_service.py"
    code_file.write_text(
        """
from google.cloud import storage, bigquery
from azure.storage.blob import BlobServiceClient

def run_cloud():
    gcp_storage = storage.Client()
    gcp_storage.download_as_bytes()

    bq = bigquery.Client()
    bq.query("SELECT 1")

    blob = BlobServiceClient(account_url="https://test.blob.core.windows.net")
    blob.download_blob("container", "blob")
""",
        encoding="utf-8",
    )

    tool = IamAuditTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "iam-audit"
    assert res["status"] == "ok"
    raw_actions = set(res["raw"]["actions"])
    assert "storage.objects.get" in raw_actions
    assert "bigquery.jobs.create" in raw_actions
    assert (
        "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"
        in raw_actions
    )


def test_iam_audit_valid_terraform_fixture() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    valid_tf_dir = repo_root / "tests" / "fixtures" / "phase50" / "iam"
    tool = IamAuditTool()
    res = tool.run(valid_tf_dir / "valid_policy.tf")

    assert res["tool"] == "iam-audit"
    assert res["status"] == "ok"
    assert res["findings"] == []
    metrics = res.get("metrics") or {}
    assert metrics["wildcard_actions_count"] == 0
    assert metrics["risk_score"] == 0.0


def test_iam_audit_overprivileged_terraform_fixture() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    fixture = (
        repo_root
        / "tests"
        / "fixtures"
        / "phase50"
        / "iam"
        / "overprivileged_policy.tf"
    )
    tool = IamAuditTool()
    res = tool.run(fixture)

    assert res["tool"] == "iam-audit"
    assert res["status"] == "fail"  # Fails due to privilege escalation findings
    findings = res["findings"]
    assert any(f["rule_id"] == "iam-wildcard-action" for f in findings)
    assert any(f["rule_id"] == "iam-privilege-escalation" for f in findings)

    metrics = res.get("metrics") or {}
    assert metrics["wildcard_actions_count"] >= 1
    assert metrics["privilege_escalation_paths"] >= 1
    assert metrics["risk_score"] >= 0.5


def test_iam_audit_zero_fallback_on_empty_code(tmp_path: Path) -> None:
    # Empty dir with no cloud calls
    empty_src = tmp_path / "empty.py"
    empty_src.write_text("x = 1\n", encoding="utf-8")

    tool = IamAuditTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "iam-audit"
    assert res["status"] == "ok"
    assert res["findings"] == []
    assert res["metrics"]["actions_count"] == 0
    # Proves zero fake fallback injection: policy must be None, not fake s3 actions!
    assert res["raw"]["policy"] is None


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

    # With artifact_write permission
    res_ok = tool.run(
        tmp_path,
        output_policy_file="policy.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res_ok["status"] == "ok"
    assert res_ok.get("artifacts") is not None
    assert (tmp_path / "policy.json").is_file()


def test_iam_policy_synthesizer_backward_compatibility(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "app.py").write_text(
        """
import boto3
s3 = boto3.client("s3")
s3.put_object(Bucket="b", Key="k")
""",
        encoding="utf-8",
    )

    synthesizer = IamPolicySynthesizer(project_root=tmp_path)
    policy = synthesizer.synthesize()
    assert policy.get("Version") == "2012-10-17"
    assert len(policy.get("Statement", [])) == 1
    assert "s3:PutObject" in policy["Statement"][0]["Action"]
