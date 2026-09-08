# Maintainer Documentation Style & Synchronization Guide

This style guide applies recursively to every file under `docs/`, including hidden subfolders, assets and retained historical records. Coverage comes from the current filesystem and Git inventory, not a fixed historical file count.

---

## 1. Core Documentation Rules

1. **Audience-Driven Writing**:
   - **User Guides (`docs/user-guide/`)**: Focus on user workflows, commands, outcomes, and clear explanations.
   - **Reference Docs (`docs/reference/`)**: Provide exhaustive technical specifications, exact parameter types, and CLI flag matrices.
   - **Developer Guides (`docs/developer/`)**: Cover architecture, layer boundaries, and internal contracts.
   - **Maintainer Runbooks (`docs/maintainers/`)**: Detail operational runbooks, triage steps, and governance policies.
2. **Capability Truth & Honest Maturity**:
   - Never document a feature as functional if it is a development stub or placeholder.
   - Document experimental features and permission flags explicitly.
3. **Deterministic Verification**:
   - Every relative markdown link in every documentation file must resolve to a valid file on disk.
   - Run `uv run --python 3.12 --extra dev python scripts/sync_docs.py --check` and `uv run --python 3.12 --extra dev python -m pytest tests/test_sync_docs.py tests/test_docs_parity_and_sync.py`. The checker verifies recorded hashes, links and registration contracts; review prose against actual behavior before recording evidence. Passing structural checks alone does not prove semantic parity.

---

## 2. Required Reference Surfaces and Recursive Review

Whenever a tool, engine, or permission boundary changes, inspect these reference surfaces and update affected current claims. Also inspect all affected guides and nested documents; this list does not limit scope:
1. `docs/TOOL_CATALOG.md`
2. `docs/ENGINE_COMPATIBILITY.md`
3. `docs/CLI_REFERENCE.md`
4. `docs/reference/cli-reference.md`
5. `docs/ENGINES.md`
6. `docs/reference/engine-directory.md`
7. `docs/MCP_REFERENCE.md`
8. `docs/reference/mcp-tool-reference.md`
9. `docs/user-guide/advanced-checks.md`
10. `docs/safety/permissions.md`
11. `docs/DEVELOPER_GUIDE.md`
12. `CHANGELOG.md`
13. The corresponding phase implementation evidence under `docs/phase-plans/`.

Apply the ordered ownership rules in [Phase 64 P64-00](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-00--account-for-every-document-in-every-subfolder). Preserve historical bodies and dates; add current-status cross-references when superseded. Keep unimplemented accepted requirements explicitly planned. Record per-file evidence and asset hashes in `docs/reports/phase-64-66-documentation-coverage.md` after completing the review.

See [Master Build Plan](../developer/master-innovation-remediation-build-plan.md).
