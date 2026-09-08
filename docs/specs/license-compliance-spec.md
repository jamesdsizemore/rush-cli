# Specification: Open-Source License Compliance & Copyleft Auditor

## 1. Overview
`LicenseMatrixTool` (`src/rush/tools/license_matrix.py`) statically audits open-source dependency licenses across polyglot package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`) and installed distribution metadata. It compares normalized SPDX identifiers against an allowlist, flags copyleft contamination risks, and categorizes ambiguous or compound licenses for manual review.

## 2. Architecture & Manifest Parsing
1. **Python Dependencies**:
   - Parses dependencies from `[project.dependencies]` in `pyproject.toml`.
   - Inspects installed distribution metadata via `importlib.metadata`.
2. **Node.js Dependencies**:
   - Parses `dependencies` and `devDependencies` from `package.json`.
3. **Rust Dependencies**:
   - Parses `[dependencies]` from `Cargo.toml`.

## 3. SPDX Normalization & Risk Classification
Current limitation: the legacy classifier does not correctly evaluate all SPDX compound expressions. [Phase 64 P64-16](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) implements expression-aware evaluation; the categories below describe the existing policy vocabulary, not proof of complete SPDX coverage.

Extracted license expressions are normalized against standard SPDX 2.0 identifiers and categorized:
- **Permissive / Allowed (Pass)**:
  `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `Unlicense`, `CC0-1.0`, `0BSD`, `PSF-2.0`, `Python-2.0`.
- **Copyleft Risk (High Severity / `fail` status)**:
  `GPL-2.0`, `GPL-3.0`, `AGPL-3.0`, `LGPL-2.1`, `LGPL-3.0`, `MPL-2.0`, `SSPL-1.0`, `EUPL-1.2`, `CDDL-1.0`, `EPL-2.0`.
  Emits finding rule `license-copyleft-risk` with severity `error`.
- **Manual Review (Warning / `warn` status)**:
  Compound expressions (`Dual`, `OR`, `AND`), custom/proprietary text, or missing licenses.
  Emits finding rule `license-manual-review` with severity `warn`.

## 4. Execution Permissions & Export Safety
- **Offline By Default**: Operates completely locally without external HTTP network calls.
- **Export Contract**: No `--export-path` CLI flag or `export_path` MCP parameter is registered for this tool. `--json` returns the result to the caller. Any future file-export route must require explicit artifact-write permission and reject traversal outside its authorized root.

## 5. CLI & FastMCP Contracts
- **CLI**:
  ```bash
  rush license-matrix . --json
  ```
- **FastMCP Tool**:
  ```python
  rush_license_matrix(path=".")
  ```
  MCP additionally exposes `allowed_licenses` and `package_licenses`; use the live input schema for their defaults. CLI `--allowed-licenses` is not registered.
