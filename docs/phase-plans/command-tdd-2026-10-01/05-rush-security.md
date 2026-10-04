# Q05 — Complete dependency-input accounting and evidence-bound trials

## Goal, scope and non-goals
Enumerate every relevant contained dependency input, run only verified adapter
formats, preserve omissions and offline constraints; add advisory reachability
and separately isolated remediation trials. No blind uv.lock→pip-audit,
implicit network, scan-route dependency updates, installation, hooks/releases.
Scanner provisioning remains user baseline, distinct from candidate trials.
Connected specialist local models, selectable voice/live speech and 3D companion
remain shared user baseline, never relabeled proposed command expansion.

## Evidence and requirement ledger
| ID | Category and requirement | Current source | Acceptance |
| --- | --- | --- | --- |
| R1 | Repair first/fixed manifest selection | src/rush/tools/security.py:105–161,181–208 | Every input has explicit row, including standalone files |
| R2 | Repair unavailable/unsupported coverage | SecurityTool.run | Omission unassessed/partial, never clean |
| R3 | Repair offline accounting | pip_audit.py:49–66; npm_audit.py:53–69; osv.py:49–60 | Exact input mode and zero denied network calls |
| E1 | Ordinary advisory/graph evidence | SecurityTool.run | Stable identity and current lock/graph digests |
| X1 | Expansion: isolated lock trial | Audit Q05:2869–2887 | Identical complete coverage, target gone, no new advisory, tests pass |

_OSV_LOCKFILES names at security.py:26–32 are not proof that every installed
OSV version extracts every listed format. Existing adapter shape proves
requirements input, npm project cwd and OSV explicit -L offline only.

## Required behavior and proposed inputs
Keep existing seven permission flags default False. Proposed __call__/run add
affected_paths: list[Path]|None=None, dependency_graph_path: Path|None=None,
sbom_path: Path|None=None, sbom_sha256: str|None=None,
trial_candidate: Path|None=None, target_advisory: str|None=None,
dependency_tests: list[str]|None=None, runtime_path: Path|None=None,
image_ref: str|None=None. CLI --trial-candidate/--target-advisory/
--dependency-tests/--runtime-path/--image-ref forwards these exact
typed inputs. CLI --affected-paths/--dependency-graph-path/--sbom-path/
--sbom-sha256 forwards remaining fields; all need value-based parity tests.
Malformed/escaped inputs => status=error, metadata.reason=invalid_argument,
zero trial execution. A trial requires nonempty target_advisory/dependency_tests.

Deterministic selected-workspace enumeration includes requirements*.txt, uv.lock,
pyproject.toml, package-lock.json and declared OSV formats. Account each input
with path/format/engine/status/reason; deduplicate intentional shared input
assessment without omitting another file. Unsupported format => unassessed/
no_adapter; absent engine => unassessed/engine_not_installed; denial explicit.
No inputs => skipped/no_dependency_inputs. Otherwise-clean omitted input =>
skipped/partial; retain completed findings/error severity.
Medusa remains distinct project-scan child.

Before dispatch acceptance, real versioned fixtures must establish explicit
requirements input, package-lock cwd, poetry.lock/requirements/package-lock/
Cargo.lock/go.sum OSV handling. uv.lock/pyproject only assessed after verified
resolver/extractor identity; until then ledger includes unsupported row.
Offline missing advisory database => unassessed, not clean. Network permission
and offline extractor availability are different observations.

Advisory rows retain stable advisory ID/package/version/source. Supplied graph
binds source/lock SHA256, package identities and evidence IDs. Missing/stale
graph, path, version or advisory identity => unknown_reachability. Never infer
identity from message title. SBOM requires Q18 exact verified producer digest
and consumer contract, not presumed compatibility with lockfile adapters.

Trial requires contained diff, real OCI, build/slow grants, complete baseline
and candidate input assessment with identical scope/engine/config identities,
stable target advisory, and actual selected Q04 dependency tests.
Target disappears + no new advisory + tests all pass => verified_candidate.
Coverage changed/omitted/missing identity => inconclusive; target persists,
new advisory or failed tests => rejected. Missing OCI => isolation_unavailable.
Original locks unchanged; denied network cannot produce complete network scan.

## Deliverables, ownership and dependencies
Own src/rush/tools/security.py::SecurityTool.__call__/run/_find_project_root;
new local _enumerate_dependency_inputs, _bind_advisory_evidence,
_trial_lock_candidate; tests/test_security.py.
Adapter normalization changes only in src/rush/engines/pip_audit.py,
npm_audit.py/osv.py to preserve actual stable evidence.
Q18 overlaps security.py: one integration owner, sequential changes.
Q05 owns input-ledger attachment and any required
src/rush/tools/routing.py::aggregate_results coverage preservation plus security
options in src/rush/catalog.py and cli_support/catalog_commands.py and
value-based CLI/MCP parity tests. Serialize shared edits with Q01–Q10;
one active writer. Preserve canonical security ToolSpec/registry identity.
Extend existing metadata.scope.dependencies rows from T14; preserve path/kind/state/reason/exclusions and add relative_path, engine and engines. Do not add metadata.inputs, metadata.partial or a second enumerator. Aggregate scope via Foundation child_scope/aggregate_scope. Generic child
aggregation cannot erase those rows or completed findings. No wrapper supplies
missing input, transport or registry behavior.
After executable route, update docs/reference/cli-reference.md,
mcp-tool-reference.md/result-reference.md with input accounting/recovery.
Use shared F5 selected-test helper for dependency tests and F4 isolated runtime contract; actual OCI acceptance requires pinned image and real denial/cleanup tests.

## Ordered RED/GREEN tasks
1. test_all_manifests_accounted_for: uv.lock, requirements-dev.txt,
   package-lock.json; verified requirements adapter success, npm absent.
   Assert exactly three rows; uv row exactly
   {"path":"uv.lock","format":"uv.lock","engine":null,"status":"unassessed",
   "reason":"no_adapter"} until proved; requirements-dev.txt has
   engine=pip-audit/status=assessed; package-lock.json has engine=npm-audit/
   status=unassessed/reason=engine_not_installed. Aggregate warn with metadata.scope.coverage == "partial".
2. test_standalone_manifest_discovery: requirements-dev.txt alone reaches exact
   adapter. test_all_osv_manifests_accounted_for invokes both supported inputs,
   not only first. Implement deterministic discovery and supported dispatch.
3. test_missing_engine_is_partial, test_denied_engine_is_unassessed preserve
   completed findings. test_offline_does_not_fetch network sentinel => zero
   calls, unavailable offline database => unassessed.
4. test_advisory_evidence_invalidates_on_lock_change: ADV-1/current graph maps
   src/api.py; changed lock invalidates to unknown_reachability. Missing
   identities and escaped graph errors covered.
5. test_lock_candidate_requires_complete_rescan_and_tests: pkg1.0→1.1 owned
   sandbox, same complete manifests, ADV-1 gone, no new IDs, actual tests pass
   => verified_candidate; omission inconclusive; new/persisting/failure rejected.
   Assert original hashes, selected tests, owned cleanup and transport parity.
   Missing target identity => inconclusive; absent isolation =>
   isolation_unavailable and zero test/install spawns. All trial labels belong
   metadata.remediation_trial.status, never invented ToolStatus enum values.

## Actual CLI and stdio MCP parity body — proposed, unexecuted

Add body below to this command's test file. It starts real stdio server and
performs initialize/tools-call through installed MCP client (existing pattern
tests/test_mcp.py:206–476). No direct FastMCP invocation substitutes for transport.
Both child processes use same checkout and environment. Prerequisite: project
dev environment includes mcp; no importorskip permitted for required acceptance.

```python
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import rush
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

def assert_real_transport_parity(command, arguments, cli_options, expected):
    repo = Path(rush.__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}
    cli = subprocess.run([sys.executable, "-m", "rush.cli", command,
                          str(arguments["path"]), *cli_options, "--json"],
                         cwd=repo, env=env, capture_output=True, text=True,
                         timeout=30)
    # Tool status error may use nonzero CLI exit; JSON must still be canonical.
    cli_result = json.loads(cli.stdout)
    async def exercise():
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "rush.cli", "mcp", "serve"], cwd=str(repo), env=env)
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err:
            async with stdio_client(params, errlog=err) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool("rush_" + command, arguments)
                    assert response.isError is False
                    return json.loads(response.content[0].text)
    mcp_result = asyncio.run(asyncio.wait_for(exercise(), timeout=30))
    for result in (cli_result, mcp_result):
        assert result["tool"] == command
        assert result["status"] == expected
    assert cli_result["findings"] == mcp_result["findings"]
    assert cli_result.get("engine") == mcp_result.get("engine")
    return cli_result, mcp_result
```


```python
def test_security_cli_mcp_empty_input_parity(tmp_path):
    cli, mcp = assert_real_transport_parity("security",
        {"path":str(tmp_path)}, [], "skipped")
    assert cli["metadata"]["reason"] == mcp["metadata"]["reason"] == "no_dependency_inputs"
    assert cli["metadata"]["inputs"] == mcp["metadata"]["inputs"] == []
    assert list(tmp_path.iterdir()) == []
```

Freeze no-input metadata.reason=no_dependency_inputs and metadata.scope.dependencies=[];
it is proposed contract, not an existing proven field. Run RED bodies first;
minimum GREEN: deterministic discovery, proven adapter dispatch, honest input
ledger, then digest-bound graph/advisory enrichment and isolated trial.
Refactor common receipt accumulation only after GREEN. Named regressions:
test_standalone_manifest_discovery, test_all_manifests_accounted_for,
test_trial_missing_runtime_never_executes_project_code,
test_offline_does_not_fetch. Execute tests/test_security.py plus existing
tests/test_engines.py/tests/test_cli_registry.py/tests/test_mcp.py.
Full expansion acceptance additionally needs actual OCI candidate diff + original
baseline rescan + selected passing/failing dependency tests, stable advisory
snapshot and identical input coverage. Passing helper/controller tests leaves
format-version, real advisory and W18 acceptance open.

## Checks, failure/recovery, stops and reconciliation
Capture actual installed format/version fixtures before accepting extractor
claims. Missing Q18/Q04/W18 contract blocks affected packet, not completed
repair evidence. Freeze bytes; edits invalidate verdict. Preserve original
inputs and child receipts; clean only owned artifacts. No commit/push.

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_security.py tests/test_cli_registry.py tests/test_mcp.py tests/test_isolated_process.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts

Reconcile R1–R3/E1/X1 with actual input scope/version/identity evidence, frozen
hash, executed checks and declared-file diff. Unsupported evidence remains
explicitly unresolved; this draft does not certify security or implementation.
