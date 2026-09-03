# Specification: Least-Privilege Cloud IAM Policy Synthesizer

## 1. Overview
`IamAuditTool` (`src/rush/tools/iam_audit.py`) statically inspects source code for cloud SDK calls across AWS (`boto3`), GCP (`google.cloud`), and Azure (`azure.storage`), synthesizing minimal least-privilege JSON IAM policies. It also analyzes Terraform (`.tf`) files to detect dangerous wildcard permissions.

## 2. Multi-Cloud SDK Static Inspection
1. **AWS SDK (`boto3`, `botocore`)**:
   - Inspects client and resource method calls (e.g. `s3.get_object`, `dynamodb.put_item`, `sqs.send_message`).
   - Maps methods to IAM action strings (`s3:GetObject`, `dynamodb:PutItem`, etc.).
2. **GCP SDK (`google.cloud`)**:
   - Inspects Storage and BigQuery client calls (e.g. `storage.Client().get_bucket`, `bigquery.Client().query`).
   - Maps calls to GCP IAM permissions (`storage.objects.get`, `bigquery.jobs.create`).
3. **Azure SDK (`azure.storage.blob`)**:
   - Inspects `BlobServiceClient`, container, and blob client calls.
   - Maps calls to Azure RBAC actions (`Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read`).

## 3. Terraform Wildcard IAM Detection
- Scans all `.tf` files in the target directory for statements containing wildcard permissions:
  - `Action = "*"`
  - `Action = ["*"]`
  - `actions = ["*"]`
- Flags violations as `error` severity findings with rule `iam-wildcard-action`, failing the audit gate.

## 4. Least-Privilege Policy Generation
- Synthesizes a standardized, minimal AWS IAM policy document containing only the observed actions:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "RushSynthesizedLeastPrivilege",
        "Effect": "Allow",
        "Action": [ ... ],
        "Resource": "*"
      }
    ]
  }
  ```

## 5. Security & Confinement
- Analysis is 100% offline static AST parsing with zero network calls or credentials required.
- Exporting policy JSON to disk via `--output-policy-file` / `--export-path` requires explicit `--allow-artifact-write` permission and path traversal validation.

## 6. CLI & FastMCP Contracts
- **CLI**:
  ```bash
  rush iam-audit [PATH] [--output <policy.json>] [--allow-artifact-write] [--json]
  ```
- **FastMCP Tool**:
  ```python
  rush_iam_audit(path=".", output_policy_file=None, allow_artifact_write=False)
  ```
