# ADR index and implementation cross-reference

| ADR | Source seam | Test owner | Affected phase |
|---|---|---|---|
| 0001 | `tools/common.py:resolve_binary` | `test_phase00_subprocess.py` | 00–08 |
| 0002 | `tools/base.py`, `tools/common.py` | `test_phase00_contract.py` | 00–08 |
| 0003 | catalog/config/CLI/MCP | `test_catalog.py`, `test_phase00_catalog_maturity.py` | 00–08 |
| 0004 | `tools/common.py:run_subprocess`, `engines/base.py` | `test_phase00_subprocess.py`, `test_engines.py` | 00–08 |
| 0005 | `engines/base.py:Engine.version` | `test_phase00_subprocess.py`, `test_engines.py` | 00–08 |
| 0006 | future importer seams | phase-owned importer tests | 03–07 |
| 0007 | guarded tools/config | phase-owned permission tests | 01–08 |
| 0008 | `semantic-drift` maturity | catalog/config tests | 08 |
| 0009 | adapter fixtures/CI | phase-owned fixture tests | 00–08 |
| 0010 | `.hermes/implementation/phase-00-02-ledger.md` | full quality gates | 00–02 |
| 0011 | `src/rush/html_export.py`, `src/rush/sarif.py` | `test_html_export.py`, `test_sarif.py` | 20 |
| 0012 | `src/rush/providers/` | `test_providers.py` | 20 |
| 0013 | `src/rush/tools/tdd_guard.py`, `src/rush/engines/` | `test_tdd_guard.py`, `test_*_reference.py` | 20 |

The pre-existing `docs/ARCHITECTURE.md` draft is deliberately not modified by this implementation program; this index provides its required mapping without mixing unrelated draft content into Phase 00 scope.
