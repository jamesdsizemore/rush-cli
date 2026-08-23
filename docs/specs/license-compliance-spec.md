# Specification: Open-Source License Compliance & Copyleft Auditor

## 1. Overview
`LicenseMatrixScanner` (`src/rush/tools/license_matrix.py`) scans dependencies and source code headers to categorize licenses (Permissive, Weak Copyleft, Strong Copyleft) and prevent accidental GPL/AGPL copyleft contamination.

## 2. CLI & FastMCP Reference
* `rush license-matrix`
* `rush_license_matrix()`
