# Specification: Least-Privilege Cloud IAM Policy Synthesizer

## 1. Overview
`IamAuditTool` (`src/rush/tools/iam_audit.py`) statically inspects source code for cloud SDK calls across AWS (`boto3`), GCP (`google.cloud`), and Azure (`azure.storage`) and proposes action policies. It also analyzes Terraform (`.tf`) files for wildcard permissions. An action list using `Resource: "*"` is not a complete least-privilege policy; deployment-specific resource restrictions and unobserved calls require review. [Phase 64 P64-17](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) repairs the hidden-parent traversal gap so skipped coverage cannot be presented as a clean audit.

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
- Exporting policy JSON uses CLI `--output` or MCP `output_policy_file` and requires explicit `allow_artifact_write` permission plus path traversal validation. CLI `--output-policy-file` and `--export-path` are not registered.

## 6. CLI & FastMCP Contracts
- **CLI**:
  ```bash
  rush iam-audit . --output policy.json --allow-artifact-write --json
  ```
- **FastMCP Tool**:
  ```python
  rush_iam_audit(path=".", output_policy_file="", allow_artifact_write=False)
  ```
