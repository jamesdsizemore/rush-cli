# ADR 0001: External engine boundary

## Context
Rush invokes optional scanners but must remain a local, stdio-safe product.

## Decision
Resolve executables only from the active virtual-environment Scripts/bin and then `PATH`. No configured executable override, bundled scanner, auto-install, implicit download, or network runtime fetch is allowed.

## Rejected alternatives
Arbitrary executable paths and engine auto-installation were rejected because project configuration must not select uncontrolled binaries.

## Consequences
Missing engines return `skipped`; users install and select engines themselves. `src/rush/tools/common.py:resolve_binary` is the policy seam.

## Compatibility and operations
This preserves current resolver order and does not change CLI/MCP transport. Tests: `tests/test_phase00_subprocess.py`. A later exception requires an ADR amendment.
