# Attestation Tool (`rush attest`)

## Overview
`rush attest` generates in-toto Statement v1 SLSA Provenance drafts binding real distribution artifacts in `dist/`. Per R-013, local runs produce explicit unsigned drafts (`assurance: unsigned_draft`) without fraudulent Level 3 claims.
`rush attest` generates in-toto Statement v1 build provenance draft statements complying with SLSA Provenance v1 specifications. It links build artifacts to source commits and repository metadata without requiring network calls or uncontained file system access.

## Usage

### CLI
```bash
rush attest [PATH] [--artifact-path <path>] [--out <output_path>] [--builder-id <uri>] [--allow-artifact-write] [--json]
```

### MCP
- **Tool Name:** `rush_attest` (and deprecated alias `rush_attest_generate`)
- **Parameters:**
  - `path` (str): Target directory or file to attest.
  - `artifact_path` (str, optional): Explicit target artifact path to attest.
  - `output_path` (str, optional): Contained path to export in-toto provenance JSON.
  - `builder_id` (str, optional): Builder URI identifier.
  - `allow_artifact_write` (bool): Required when exporting provenance to `output_path`.

## Output Schema
Emits canonical `ToolResult` with `raw` containing an in-toto Statement v1 payload:
```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "artifact.whl",
      "digest": {
        "sha256": "..."
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://rush-cli.org/build/draft/v1",
      "externalParameters": {
        "sourceUri": "https://github.com/rush-cli/rush",
        "commit": "...",
        "entryPoint": "rush attest"
      },
      "internalParameters": {
        "builderId": "https://rush-cli.org/builder/v1"
      }
    },
    "runDetails": {
      "builder": {
        "id": "https://rush-cli.org/builder/v1"
      },
      "metadata": {
        "invocationId": "rush-...",
        "startedOn": "...",
        "finishedOn": "...",
        "assurance": "unsigned_draft"
      }
    }
  }
}
```

## Security & Permissions
- Read-only execution by default.
- Exporting provenance statements via `--out` / `output_path` requires explicit `--allow-artifact-write` permission.
- Output paths are strictly confined to the workspace root; path traversal escapes (`..`) and symlink attacks are rejected.
