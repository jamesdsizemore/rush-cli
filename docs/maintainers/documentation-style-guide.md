# Maintainer Documentation Style & Synchronization Guide

This style guide enforces clarity, truthfulness, and zero documentation drift across all 128 documentation files in Rush CLI.

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
   - Run `python scripts/sync_docs.py --check` and `pytest tests/test_docs_parity_and_sync.py` to verify 100% parity.

---

## 2. 13-File Mandatory Update Checklist

Whenever a tool, engine, or permission boundary is added or modified, the maintainer must update all 13 documents:
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
13. `.hermes/implementation/phase-XX-ledger.md`

See [Master Build Plan](../developer/master-innovation-remediation-build-plan.md).
