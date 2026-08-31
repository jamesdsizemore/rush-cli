# Cloud IAM Audit Tool (`rush iam-audit`)

## Overview
`rush iam-audit` statically parses Python AST calls to AWS SDKs (`boto3`, `botocore`) and synthesizes a minimal, least-privilege AWS IAM JSON policy. Any unmapped or unrecognized SDK method calls are reported as structured warnings to ensure security auditing coverage.

## Usage

### CLI
```bash
rush iam-audit [PATH] [--output <policy.json>] [--allow-artifact-write] [--json]
```

### MCP
- **Tool Name:** `rush_iam_audit`
- **Parameters:**
  - `path` (str): Target codebase path to scan.
  - `output_policy_file` (str, optional): Contained path to write synthesized IAM policy JSON.
  - `allow_artifact_write` (bool): Required when exporting policy JSON to `output_policy_file`.

## Supported Services
- **S3:** `GetObject`, `PutObject`, `DeleteObject`, `ListBucket`, `CreateBucket`, `DeleteBucket`, `ListAllMyBuckets`.
- **DynamoDB:** `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`, `Scan`, `BatchGetItem`, `BatchWriteItem`, `CreateTable`, `DescribeTable`.
- **SQS:** `SendMessage`, `ReceiveMessage`, `DeleteMessage`, `GetQueueUrl`, `CreateQueue`.
- **SNS:** `Publish`, `CreateTopic`, `Subscribe`.
- **Lambda:** `InvokeFunction`, `CreateFunction`, `GetFunction`.
- **Secrets Manager:** `GetSecretValue`, `PutSecretValue`, `CreateSecret`, `DescribeSecret`.
- **SSM:** `GetParameter`, `GetParameters`, `PutParameter`, `GetParameterHistory`.
- **STS / KMS:** `GetCallerIdentity`, `AssumeRole`, `Encrypt`, `Decrypt`, `GenerateDataKey`, `DescribeKey`.

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
