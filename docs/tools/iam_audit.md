# Cloud IAM Audit Tool (`rush iam-audit`)

## Overview
`rush iam-audit` statically parses source code for cloud SDK calls across AWS (`boto3`), GCP (`google.cloud.storage`, `google.cloud.bigquery`), and Azure (`azure.storage.blob`), synthesizes minimal least-privilege IAM policies, and scans Terraform (`.tf`) files for dangerous wildcard permissions (`iam-wildcard-action`).

**Status: planned correction — implementation [Phase 64, P64-17](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-17--project-relative-discovery-and-valid-coverage-f2021).** Current discovery can exclude all files when the selected project is under a hidden parent directory. Zero analyzed files is unavailable evidence.

## Usage

### CLI
```bash
uv run rush iam-audit [PATH] [--output POLICY_JSON] [--allow-artifact-write] [--json]
```

### MCP
- **Tool Name:** `rush_iam_audit`
- **Parameters:**
  - `path` (str): Target codebase path to scan.
  - `output_policy_file` (str; default `""`): Contained path to write synthesized IAM policy JSON.
  - `allow_artifact_write` (bool): Required when exporting policy JSON to `output_policy_file`.

## Supported Clouds & Services
- **AWS:** S3, DynamoDB, SQS, SNS, Lambda, Secrets Manager, SSM, STS, KMS.
- **GCP:** Cloud Storage (`storage.objects.*`), BigQuery (`bigquery.jobs.*`, `bigquery.tables.*`).
- **Azure:** Azure Blob Storage (`Microsoft.Storage/...`).
- **Terraform / IaC:** Scans `.tf` files for wildcard `Action = "*"` or `actions = ["*"]` blocks. Emits `iam-wildcard-action` finding.


## Output Schema
Emits canonical `ToolResult` with synthesized IAM policy in `metadata.policy`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RushSynthesizedLeastPrivilege",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "*"
    }
  ]
}
```

## Security & Confinement
- Analysis is purely static AST inspection without executing scanned files or making external AWS API calls.
- Policy file exports require `--allow-artifact-write` and are confined to the workspace root.
