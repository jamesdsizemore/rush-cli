# License Matrix Tool (`rush license-matrix`)

## Overview
`rush license-matrix` audits project dependencies across `pyproject.toml`, `package.json`, `Cargo.toml`, and installed package metadata for copyleft risks and open-source license compliance. It compares extracted licenses against an exact allowlist, flags copyleft licenses as high-risk errors, and flags unknown or compound licenses for manual review.

**Status: planned correction — implementation [Phase 64, P64-16](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-16--spdx-expressions-and-decoded-svg-safety-f18-f19).** Current grouped SPDX expression handling can understate copyleft risk. Do not use current classification as compliance evidence.

## Usage

### CLI
```bash
uv run rush license-matrix [PATH] [--json]
```

### MCP
- **Tool Name:** `rush_license_matrix`
- **Parameters:**
  - `path` (str): Target directory containing project manifests.
  - `package_licenses` (object or null; default null): Optional supplied package-license mapping.
  - `allowed_licenses` (array, optional): SPDX allowlist. Default is `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `Unlicense`, `CC0-1.0`, `0BSD`, `PSF-2.0`, `Python-2.0`, and `Zlib`.

Current CLI exposes neither `--allowed-licenses` nor `--export-path`; those are not valid CLI examples.

## Classification Policy
- **Permissive / Allowed:** Matches canonical allowlist (`MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `Unlicense`, `CC0-1.0`, `0BSD`, `PSF-2.0`, `Python-2.0`).
- **Copyleft Risk (`license-copyleft-risk`):** Flagged as `error` severity (`GPL`, `AGPL`, `LGPL`, `SSPL`, `EUPL`, `MPL`, `CDDL`, `EPL`). Results in `fail` tool status.
- **Manual Review (`license-manual-review`):** Flagged as `warn` severity for compound (`Dual`, `OR`, `AND`), custom/proprietary, missing, or unrecognized licenses. Results in `warn` tool status.

## Output Schema
Emits canonical `ToolResult` with findings and summary metrics:
```json
{
  "tool": "license-matrix",
  "status": "ok",
  "summary": "License Matrix audited 12 packages (0 copyleft violations, 0 manual review)",
  "findings": [],
  "metrics": {
    "total_packages": 12,
    "allowed_count": 12,
    "copyleft_violations_count": 0,
    "manual_review_count": 0
  }
}
```

## Security & Confinement
- Operates entirely locally on project manifests and metadata without outbound network queries.
