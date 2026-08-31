# Offline ONNX Review Tool (`rush offline-review`)

## Overview
`rush offline-review` runs local machine learning quality and security review using user-supplied ONNX models. In accordance with D50-04, this tool guarantees zero network access, bundles no model weights, has no auto-download capability, and returns `status='skipped'` when `onnxruntime` or the model file is absent.

## Usage

### CLI
```bash
rush offline-review [PATH] [--model-path <path>] [--expected-sha256 <digest>] [--json]
```

### MCP
- **Tool Name:** `rush_offline_review`
- **Parameters:**
  - `path` (str): Target codebase path to evaluate.
  - `model_path` (str, optional): Path to user-supplied ONNX model file (default: `.rush/models/review.onnx`).
  - `expected_sha256` (str, optional): SHA-256 digest to verify model file integrity.
  - `defect_threshold` (float, optional): Anomaly/defect confidence threshold (default: 0.5).

## Behavior & Guarantees
- **Zero Network Calls**: Never dials external services or endpoints.
- **Graceful Skipping**: If `onnxruntime` is not installed or model file is absent, returns canonical structured `status='skipped'` without failing the gate suite.
- **Digest Verification**: If `expected_sha256` is configured, verifies model checksum before loading into `onnxruntime.InferenceSession`.

## Output Schema
Emits canonical `ToolResult`:
```json
{
  "tool": "offline-review",
  "engine": "offline-review",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 35,
  "summary": "offline-review: Evaluated 20 file(s) with local ONNX model, 0 finding(s)",
  "findings": [],
  "metrics": {
    "files_evaluated": 20,
    "model_findings_count": 0,
    "model_path": ".rush/models/review.onnx"
  }
}
```

## Security & Permissions
- Strictly offline, local-only evaluation.
- No network, download, or write permissions required.
