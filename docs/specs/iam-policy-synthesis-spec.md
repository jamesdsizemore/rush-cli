# Specification: Least-Privilege Cloud IAM Policy Synthesizer

## 1. Overview
`IamPolicySynthesizer` (`src/rush/tools/iam_audit.py`) inspects source code for AWS `boto3` / GCP SDK calls and generates minimal JSON IAM policies adhering to least-privilege principles.

## 2. CLI & FastMCP Reference
* `rush iam-audit`
* `rush_iam_audit()`
