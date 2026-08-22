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
| 0014 | `src/rush/cache.py`, `src/rush/tools/common.py` | `test_cache.py`, `test_git_scoping.py` | 21 |
| 0015 | `src/rush/plugins/`, `rush.toml` | `test_plugins.py`, `test_plugin_skills.py` | 28 |
| 0016 | `src/rush/tui.py`, `src/rush/dashboard.py` | `test_tui.py`, `test_dashboard.py` | 27 |
| 0017 | `src/rush/workflows/`, `src/rush/watcher.py` | `test_workflows.py`, `test_watcher.py` | 24, 25 |
| 0018 | `src/rush/tools/base.py`, `src/rush/session_memory.py` | `test_session_memory.py`, `test_agent_remediation.py` | 29 |
| 0019 | `src/rush/ast_patcher.py`, `src/rush/tools/graft_slice.py` | `test_ast_slicer.py`, `test_ast_patcher.py` | 35 |
| 0020 | `src/rush/agent_sandbox.py` | `test_agent_sandbox.py` | 31 |
| 0021 | `src/rush/git/worktree.py` | `test_agent_worktree.py` | 31 |
| 0022 | `src/rush/tools/token_cost.py` | `test_token_cost.py` | 32 |
| 0023 | `src/rush/tools/consensus.py` | `test_consensus_bridge.py` | 40 |
| 0024 | `src/rush/git/` (all tools) | `test_git_*.py` | 31–40 |
| 0025 | `src/rush/ast_patcher.py` | `test_ast_slicer.py` | 35 |
| 0026 | `src/rush/governance/` | `test_agent_governance.py` | 38 |
| 0027 | `src/rush/hook/` | `test_git_hook_guard.py` | 39 |
| 0028 | `src/rush/score/` | `test_quality_scorecard.py` | 40 |
| 0029 | `src/rush/vibecoder/` | `test_vibecoder_toolkit.py` | VibeCoder Toolkit |
| 0030 | `src/rush/memory/` | `test_agent_context_memory.py` | 41A, 41B |
| 0031 | `src/rush/ship/` | `test_ship_readiness_cockpit.py` | 41C |
| 0032 | `src/rush/tools/context_pack.py` | `test_context_pack.py` | 42 |
| 0033 | `src/rush/safety/hallucination.py` | `test_hallucination_guard.py` | 42 |
| 0034 | `src/rush/tools/test_heal.py` | `test_flaky_test_healer.py` | 44 |
| 0035 | `src/rush/mcp/mesh.py`, `src/rush/tools/swarm_merge.py` | `test_mcp_mesh.py`, `test_swarm_merge.py` | 46 |
| 0036 | `src/rush/providers/offline.py`, `src/rush/release/attest.py` | `test_offline_runtime.py`, `test_attestation.py` | 44, 46 |
| 0037 | Tree-sitter & `pyproject.toml` | `test_polyglot_grammars.py` | Dependencies |
| 0038 | `src/rush/token_economy/`, `src/rush/token_economy/ccr_store.py` | `test_ccr_store.py` | 41, 43 |
| 0039 | `src/rush/token_economy/toon/` | `test_toon_serialization.py` | 42 |
| 0040 | `src/rush/token_economy/distillers/`, `src/rush/tools/common.py` | `test_command_distillers.py` | 41 |
| 0041 | `src/rush/memory/mistake_miner.py` | `test_mistake_miner.py` | 43 |
| 0042 | `src/rush/codegraph/grounding_verifier.py`, `src/rush/tools/hallu_guard.py` | `test_grounding_verifier.py` | 43 |
| 0043 | `src/rush/token_economy/stale_sweeper.py` | `test_stale_sweeper.py` | 44 |
| 0044 | `src/rush/codegraph/`, `src/rush/memory/` | Clean-room tests | 41–50 |
| 0045 | `src/rush/token_economy/telemetry.py`, `src/rush/token_economy/tui_gain.py` | `test_telemetry.py`, `test_gain_tui.py` | 45 |
| 0046 | `src/rush/tools/ship/` | `test_ship_clean_env_docs.py`, `test_ship_gate_cockpit.py` | 41, 42 |
| 0047 | `src/rush/mcp_mesh/`, `src/rush/tools/swarm_merge.py` | `test_mcp_mesh.py`, `test_swarm_merge.py` | 49 |
| 0048 | `src/rush/integrations/graft.py`, `src/rush/codegraph/` | `test_graft_integration.py`, `test_ast_skeletonizer.py` | 41–50 |

The pre-existing `docs/ARCHITECTURE.md` draft is deliberately not modified by this implementation program; this index provides its required mapping without mixing unrelated draft content into Phase 00 scope.
