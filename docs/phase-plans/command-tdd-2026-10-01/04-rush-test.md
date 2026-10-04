# Q04 — Project-bound multi-suite tests and bounded interaction reproduction
Source revision: c78e445ba1e575ca373e35840142cd627b055d6a
Planning only; all implementation/tests proposed and unexecuted.
Batch: Q01–Q10 only; any next batch requires explicit user approval.
No implementation, commit or push authorized by this plan.
Subagent provenance: gpt-6.1-sol / high; responsibility: Q04 source grounding,
suite/environment truth, total process budget and standalone-plan fixes.
Implementation readiness: NOT READY until shared transport/coverage work,
real project engine-version fixtures and genuine W18 accounting/acceptance exist.
Read AGENTS.md, docs/templates/task-block-template.md and the exact audit Q04
identified below.

## Goal, scope and non-goals
Assess every selected applicable suite through verified project executables and
real assertion reports; optionally reproduce and minimize observed test-order
interaction. No installs, implicit npm fallback, test rewrites, W18 implementation,
unrelated healing, global-minimum or determinism claims.
Shared baseline preserves scanner provisioning, connected specialist local
models, selectable voice/live speech and the 3D companion. Shared integration
owns applicable runtime/permission contracts; these user-requested features
are baseline, not this command's novel expansion or an authorized omission.

## Evidence and requirement ledger
Source citations refer to frozen revision above; authoritative plan lives at
/Users/jamesdsizemore/Developer/rush-cli/docs/phase-plans/command-tdd-2026-10-01/04-rush-test.md.
Audit input:
/Users/jamesdsizemore/Developer/rush-cli/docs/reports/cli-mcp-command-audit-2026-09-26.md,
Q04:2044–2056,2073–2223,2427–2588; SHA256
8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.

| ID | Category and requirement | Source | Acceptance |
| --- | --- | --- | --- |
| R1 | Repair Python early return omitting JS | src/rush/tools/test.py:19–93 | Mixed fixture yields two assessed child rows |
| R2 | Repair zero/invalid assertion evidence | engines/pytest.py:44–191; engines/vitest.py:28–139 | Pytest exit5 skipped; invalid fresh Vitest JSON error |
| R3 | Repair interpreter/provenance mismatch | runtime/subprocesses.py:1090–1275 preflight | Same verified absolute executable for probe/dispatch |
| E1 | Ordinary suite/graph selection | TestTool.__call__/run | Explicit order; current complete graph; honest fallback |
| X1 | Expansion: order interaction minimizer | Audit Q04:2427–2588 | Total spawn budget; observed minimality only |

Preserve subprocess ownership regression tests/test_subprocess_contract.py:940–950.

## Required behavior and concrete interfaces
Add suite: Literal["python","javascript","all"]="all", test_paths: list[str]|None,
changed_files: list[str]|None, test_graph_path: Path|None,
test_environment: Literal["project","active"]="project",
minimize_order_failure: str|None, runtime_path: Path|None, image_ref: str|None,
max_subprocesses: int=6, boolean allow_build=False/allow_slow=False.
Every nullable input defaults None. Callable constructs ExecutionPermissions
from actual bool grants and passes it to run(..., permissions=...). run accepts
permissions: ExecutionPermissions|None=None, not executor permission-name sets.
CLI equivalent choices, repeated --test-path/--changed-file, contained graph,
target and integer budget; actual stdio MCP equivalent. Reject invalid enum,
bool/string budgets, escaped/duplicate/option-like selectors before spawning.

Build grant required before executable environment probes or tests; minimizer
also slow. Denial => skipped with missing grants and zero child processes.
all independently schedules Python marker suite and package.json JS suite.
Unavailable selected suite => skipped/unassessed; retain other child outcomes.

Project Python executable is .venv/bin/python or .venv/Scripts/python.exe;
verify sys.prefix equals project .venv and pytest exists. Engine.binary and
execution argv use that same absolute executable. JS uses verified project
toolchain and local node_modules Vitest. Unresolved => environment_unresolved,
no silent Rush/PATH/npm fallback. active explicitly reports actual identity,
never project-aligned dependencies. Preserve owner_instance_id/run_id through
tests, version and environment subprocesses.

Pytest exit5 => skipped, all count fields zero. Collection/internal/interruption
errors (exit2/3/4) => error; exit1 => fail; exit0 with real passed assertions =>
ok; all-skipped exit0 => skipped. Vitest writes a fresh invocation-owned JSON outputFile.
Validate nonnegative integer aggregates against assertionResults and execution
status. Missing/stale/malformed/inconsistent file => error. Successful exit
alone cannot fabricate counts. Each suite receipt includes suite/argv/runtime/
selected_tests/collected/passed/failed/skipped/status. Relevant omission sets
partial=true; aggregate status is error if any child errors, otherwise fail
if any child fails, otherwise warn when assessed and omitted suites mix, otherwise
skipped when none assessed, otherwise ok. Child rows use routing.child_scope; the
result uses routing.aggregate_scope. Zero selected applicable suites returns
skipped with metadata.scope.coverage="none" and the existing reason.

Explicit test_paths preserve order. Supplied graph schema version1/complete=true,
sources maps each relative source path to SHA256 of actual current bytes;
edges maps each source to a nonempty array of contained test node IDs, e.g.
{"src/a.py":["tests/test_a.py::test_a"]}. Validate paths and
current digests. Explicit test_paths and changed_files are mutually exclusive;
empty arrays error. Missing graph falls back with missing_graph_full_suite;
malformed JSON invalid_graph_full_suite; incomplete schema
incomplete_graph_full_suite; stale/unknown edge unknown_graph_edge_full_suite.
Complete graph selects nodes; unknown/incomplete/stale/malformed graph falls back
to full selected suites with selection_reason. Path escape errors. Do not
combine ambiguous explicit selectors and changed_files.

### Interaction contract
With target supplied, take exclusive minimization branch instead of ordinary
suite scheduling. Python ordered distinct contained node IDs, target last,
verified W18 runtime/image required. Budget min2/default6 counts EVERY child
spawn including validation, baseline, target-alone and candidates. Reserve
budget before launch; missing provider accounting blocks acceptance.

Baseline must fail specified target with pytest exit1. Other failures/collection
errors do not reproduce target. Target alone must pass. Otherwise report
baseline_not_reproduced or target_fails_alone without interaction certification.
Delete predecessors left-to-right, retain only target-reproducing deletion,
restart after successful deletion. Cached same-invocation sequence observations
must remain in receipt. one_deletion_minimal only when every deletion of final
sequence observed target pass. Exhaustion => budget_limited with best observed
sequence, no unearned certification. Non-test errors => error; source drift =>
stale_source. Record total spawns, every argv/outcome, source/runtime/image/
environment identities and exact ordered nodes. Originals unchanged.

## Deliverables, dependencies and ownership
Own src/rush/tools/test.py::TestTool.__call__/run; new local select_graph_tests,
_minimize_order_failure, _run_target_oracle; src/rush/engines/pytest.py::PytestEngine;
src/rush/engines/vitest.py::VitestEngine; new tests/test_test_tool.py.
Foundation exclusively owns catalog/generic CLI option forwarding, permission
adaptation and aggregation plus tests/test_cli_registry.py/tests/test_mcp.py.
Exact shared targets: src/rush/catalog.py::TOOL_SPECS,
src/rush/cli_support/catalog_commands.py::build_catalog_path_command,
src/rush/config.py::resolve_tool_options, src/rush/mcp_support/tool_registry.py,
src/rush/invocation/executor.py and src/rush/tools/routing.py::aggregate_results.
Declare the exact options/defaults above; reject string/integer bool coercion;
preserve ordered arrays and nullable paths. Serial shared integration must
implement the aggregate coverage/status rules above and actual CLI/stdio MCP
parity. No missing behavior is delegated to an external planning wrapper.
After executable routes, update docs/reference/cli-reference.md,
mcp-tool-reference.md/result-reference.md via integration owner.

W18 required local contract: pinned locally present pytest image with fixture
dependencies, read-only originals, exclusive writable scratch, network/home
write denial, time/resource/output/spawn bounds, ownership and cleanup receipts.
Required proposed interface: run_isolated_argv(root:Path,scratch:Path,*,
runtime_path:Path,image_ref:str,entrypoint:str,argv:list[str],timeout_s:int,
max_process_launches:int|None=None) returns returncode:int,stdout:str,stderr:str,
process_launches:int and validated isolation receipt. Provider reserves a
launch before each environment/backend/test subprocess; receipt counts all
launches. Calling beyond remaining budget is prohibited. This contract is
not implemented; W18 owner must supply it before X1 acceptance.
Oracle argv=["-m","pytest","-q","--tb=line",*ordered_nodes], timeout_s=180;
verify selected pinned image's absolute Python entrypoint before use.
Budget exhaustion has its own terminal outcome, never IsolationUnavailable.
Rehash every selected source before and after each attempt; source identity
drift invalidates cached observations and stops with stale_source.
Real tests/test_isolated_process.py acceptance; mocks prove controller only.

## Ordered RED/GREEN tasks
1. test_mixed_project_runs_both_suites: real project pytest/Vitest with one
   passing test each => two rows, collected=passed=1 each, exact executables.
2. test_zero_collection_is_incomplete, test_project_venv_used,
   test_environment_unresolved_never_falls_back: exit5/zero; correct prefix;
   missing environment no unintended runtime. Minimum scheduling/identity fix.
3. test_vitest_fresh_report_cases: real one-test pass => ok, collected/passed=1;
   one failure => fail, collected/failed=1, exact actual failure message;
   one skip => skipped, collected/skipped=1; absent => skipped/all counts0.
   Assert remaining count fields0; corrupt totals/missing/stale report => error.
4. test_suite_selection_and_unknown_graph_edge: JS selection, complete graph
   exact node, stale/unknown full-suite fallback, escaped node error.
   test_test_selection_cli_mcp_parity exercises transmitted inputs.
5. test_order_failure_minimizes_to_two_nodes: tests/test_a.py contains
   "import builtins\ndef test_a():\n    builtins.rush_order_flag=True\n";
   tests/test_b.py contains these concatenated Python string literals:
   "import builtins\ndef test_b():\n"
   "    assert not getattr(builtins,'rush_order_flag',False)\n".
   A,B fails B; B alone passes
   => exact retained nodes and observed
   deletion minimality. Irrelevant predecessor, low budget, unrelated failure,
   target-alone failure, timeout/source drift and EVERY spawn count tested.

## Runnable RED bodies — proposed, unimplemented and unexecuted

Append direct-engine cases to tests/test_test_tool.py. Move the defined public
transport helper/case into tests/test_mcp.py under integration ownership.
All helpers below are defined; they invoke the real changed TestTool and
process transports, not a fabricated ToolResult.

metadata.interaction_reproducer has status, ordered_nodes, minimality,
subprocess_count and process_receipts. Each process receipt records argv,
returncode and process_launches, including validation/control processes.
subprocess_count equals their sum and cannot exceed max_subprocesses.
Minimality values are one_deletion_minimal or budget_limited; non-reproduction,
target_fails_alone and errors must not publish one_deletion_minimal.

```python
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

from click.testing import CliRunner
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from rush.cli import cli
from rush.permissions import ExecutionPermissions
from rush.tools.test import TestTool

TEST_REPO = Path(__file__).resolve().parents[1]


def _python_test_project(root):
    (root / "pyproject.toml").write_text(
        "[project]\nname='q04-fixture'\nversion='0.1'\n", encoding="utf-8"
    )
    (root / "src").mkdir()
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    source = root / "src/value.py"
    source.write_text("def value():\n    return 'fixture'\n", encoding="utf-8")
    (root / "tests").mkdir()
    target = root / "tests/test_value.py"
    target.write_text(
        "from src.value import value\n"
        "def test_value():\n    assert value() == 'fixture'\n", encoding="utf-8"
    )
    return source, target


async def _test_stdio(root, arguments):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "rush.cli", "mcp", "serve"],
        cwd=str(TEST_REPO),
        env={**os.environ, "PYTHONPATH": str(TEST_REPO / "src")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            schemas = {t.name: t.inputSchema for t in (await session.list_tools()).tools}
            assert schemas["rush_test"]["properties"]["suite"]["default"] == "all"
            response = await session.call_tool("rush_test", {"path": str(root), **arguments})
            assert response.isError is not True
            return json.loads(response.content[0].text)


def test_unknown_graph_runs_real_full_suite_and_zero_collection(tmp_path):
    source, target = _python_test_project(tmp_path)
    graph = tmp_path / "test-graph.json"
    graph.write_text(json.dumps({
        "version": 1, "complete": True,
        "sources": {"src/value.py": hashlib.sha256(source.read_bytes()).hexdigest()},
        "edges": {},
    }), encoding="utf-8")
    options = {
        "suite": "python", "test_environment": "active",
        "changed_files": ["src/value.py"], "test_graph_path": graph,
        "permissions": ExecutionPermissions(build=True),
    }
    first = TestTool().run(tmp_path, **options)
    assert first["status"] == "ok"
    assert first["metadata"]["scope"]["coverage"] == "complete"
    assert first["metadata"]["selection_reason"] == "unknown_graph_edge_full_suite"
    assert len(first["metadata"]["suites"]) == 1
    row = first["metadata"]["suites"][0]
    assert row["suite"] == "python"
    assert row["status"] == "ok"
    assert {k: row[k] for k in ("collected", "passed", "failed", "skipped")} == {
        "collected": 1, "passed": 1, "failed": 0, "skipped": 0,
    }
    assert Path(row["environment"]).resolve() == Path(sys.executable).resolve()
    target.unlink()
    empty = TestTool().run(tmp_path, **options)
    assert empty["status"] == "skipped"
    assert empty["metadata"]["scope"]["coverage"] == "none"
    row = empty["metadata"]["suites"][0]
    assert row["status"] == "skipped"
    assert {k: row[k] for k in ("collected", "passed", "failed", "skipped")} == {
        "collected": 0, "passed": 0, "failed": 0, "skipped": 0,
    }


def test_project_environment_missing_never_uses_active_python(tmp_path):
    _python_test_project(tmp_path)
    result = TestTool().run(tmp_path, permissions=ExecutionPermissions(build=True))
    assert result["status"] == "skipped"
    assert result["metadata"]["scope"]["coverage"] == "none"
    row = result["metadata"]["suites"][0]
    assert row["status"] == "skipped"
    assert row["reason"] == "environment_unresolved"
    assert row["environment"] == "unresolved"


def test_test_selection_actual_cli_stdio(tmp_path):
    _python_test_project(tmp_path)
    invocation = CliRunner().invoke(cli, [
        "test", str(tmp_path), "--suite", "python",
        "--test-environment", "active", "--allow-build", "--json",
    ])
    assert invocation.exit_code == 0, invocation.output
    cli_result = json.loads(invocation.output)
    mcp_result = asyncio.run(_test_stdio(tmp_path, {
        "suite": "python", "test_environment": "active", "allow_build": True,
    }))
    for result in (cli_result, mcp_result):
        assert result["status"] == "ok"
        assert result["metadata"]["scope"]["coverage"] == "complete"
        row = result["metadata"]["suites"][0]
        assert {k: row[k] for k in ("suite", "collected", "passed", "failed", "skipped")} == {
            "suite": "python", "collected": 1, "passed": 1, "failed": 0, "skipped": 0,
        }
    denied = asyncio.run(_test_stdio(tmp_path, {"suite": "python"}))
    assert denied["status"] == "skipped"
    assert denied["metadata"]["subprocess_count"] == 0


def test_order_failure_real_oci_total_budget(tmp_path):
    required = ("RUSH_TEST_OCI_RUNTIME", "RUSH_TEST_RUSH_IMAGE")
    assert all(os.environ.get(k) for k in required), "Genuine W18 runtime/image prerequisite unmet"
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='q04-order-fixture'\nversion='0.1'\n", encoding="utf-8"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_noise.py").write_text(
        "def test_noise(tmp_path):\n"
        "    p=tmp_path/'noise'\n    p.write_text('isolated')\n"
        "    assert p.read_text() == 'isolated'\n", encoding="utf-8"
    )
    (tests / "test_a.py").write_text(
        "import builtins\ndef test_a():\n    builtins.rush_order_flag=True\n",
        encoding="utf-8",
    )
    (tests / "test_b.py").write_text(
        "import builtins\ndef test_b():\n"
        "    assert not getattr(builtins,'rush_order_flag',False)\n", encoding="utf-8"
    )
    nodes = ["tests/test_noise.py::test_noise", "tests/test_a.py::test_a",
             "tests/test_b.py::test_b"]
    original = {p.name: p.read_bytes() for p in tests.glob("*.py")}
    options = {
        "suite": "python", "test_paths": nodes,
        "minimize_order_failure": nodes[-1],
        "runtime_path": Path(os.environ["RUSH_TEST_OCI_RUNTIME"]),
        "image_ref": os.environ["RUSH_TEST_RUSH_IMAGE"],
        "permissions": ExecutionPermissions(build=True, slow=True),
    }
    result = TestTool().run(tmp_path, max_subprocesses=32, **options)
    receipt = result["metadata"]["interaction_reproducer"]
    assert receipt["status"] == "reproduced"
    assert receipt["ordered_nodes"] == nodes[1:]
    assert receipt["minimality"] == "one_deletion_minimal"
    assert 3 <= receipt["subprocess_count"] <= 32
    assert receipt["subprocess_count"] == sum(
        r["process_launches"] for r in receipt["process_receipts"]
    )
    limited = TestTool().run(tmp_path, max_subprocesses=2, **options)
    receipt = limited["metadata"]["interaction_reproducer"]
    assert receipt["status"] == "budget_limited"
    assert receipt["minimality"] == "budget_limited"
    assert receipt["subprocess_count"] <= 2
    assert {p.name: p.read_bytes() for p in tests.glob("*.py")} == original
```

Suite rows additionally carry reason for unassessed execution and exact
environment executable; unassessed counts are zero. Build-denied results
record metadata.subprocess_count=0. "active" in these tests deliberately
exercises the uv Python 3.12 environment and reports its actual executable;
it does not prove project-environment selection or replace that acceptance.

## Exact source patches (implementation base: phase/70 at 66c6c79)

### P1. src/rush/tools/test.py — replace the import block, `TestTool.__call__` and `TestTool.run`; keep `mcp_description` and `_find_project_root` unchanged

```python
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import StrictBool, StrictInt, StrictStr

from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..permissions import ExecutionPermissions, build_execution_metadata, check_permissions
from ..runtime.binaries import resolve_binary, resolve_project_binary, select_analysis_environment
from ..runtime.project_python import project_python
from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, error_result, now_ms, run_engine, run_subprocess, skipped_result
from .routing import aggregate_results, aggregate_scope, child_scope, detect_project_languages

_PYTHON_ENTRYPOINT = "/usr/local/bin/python"
_ZERO = ("collected", "passed", "failed", "skipped")


class TestTool(ToolFn):
    name: ToolName = "test"
    # mcp_description property: unchanged.

    def __call__(
        self,
        path: Path,
        *,
        suite: Literal["python", "javascript", "all"] = "all",
        test_paths: list[StrictStr] | None = None,
        changed_files: list[StrictStr] | None = None,
        test_graph_path: Path | None = None,
        test_environment: Literal["project", "active"] = "project",
        minimize_order_failure: StrictStr | None = None,
        runtime_path: Path | None = None,
        image_ref: StrictStr | None = None,
        max_subprocesses: StrictInt = 16,
        allow_build: StrictBool = False,
        allow_slow: StrictBool = False,
    ) -> ToolResult:
        return self.run(
            path, suite=suite, test_paths=test_paths, changed_files=changed_files,
            test_graph_path=test_graph_path, test_environment=test_environment,
            minimize_order_failure=minimize_order_failure, runtime_path=runtime_path,
            image_ref=image_ref, max_subprocesses=max_subprocesses,
            permissions=ExecutionPermissions(build=allow_build, slow=allow_slow),
        )

    def run(
        self, path: Path, *, config=None, permissions: ExecutionPermissions | None = None,
        suite: str = "all", test_environment: str = "project",
        test_paths: list[str] | None = None, changed_files: list[str] | None = None,
        test_graph_path: Path | None = None, minimize_order_failure: str | None = None,
        runtime_path: Path | None = None, image_ref: str | None = None,
        max_subprocesses: int = 16,
    ) -> ToolResult:
        """Assess every selected suite through verified project executables. Without
        a build grant (plus slow for the minimizer) no process starts."""
        from ..engines.pytest import PytestEngine
        from ..engines.vitest import VitestEngine

        permissions = permissions or ExecutionPermissions()
        start = now_ms()
        project_root = _find_project_root(path)
        if project_root is None:
            return ToolResult(
                tool="test", engine=None, engine_version=None, status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"test: no pyproject.toml or package.json found above {path}",
                findings=[], raw=None,
            )
        languages = detect_project_languages(project_root)
        if suite not in {"python", "javascript", "all"}:
            return error_result("test", None, "invalid suite")
        if test_environment not in {"project", "active"}:
            return error_result("test", None, "invalid test_environment")
        requested = [
            name for name, marker in (
                ("python", (project_root / "pyproject.toml").is_file()
                 or (project_root / "setup.py").is_file()),
                ("javascript", (project_root / "package.json").is_file()),
            ) if marker and suite in {"all", name}
        ]
        if not requested and suite == "all":
            if languages:
                return ToolResult(
                    tool="test", engine=None, engine_version=None, status="skipped",
                    duration_ms=elapsed_ms(start),
                    summary="test: detected " + ", ".join(languages)
                    + " project markers, but their adapters are feasibility-gated",
                    findings=[], raw=None,
                )
            return ToolResult(
                tool="test", engine=None, engine_version=None, status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"test: unrecognized project type at {project_root}",
                findings=[], raw=None,
            )
        required = ExecutionPermissions(build=True, slow=minimize_order_failure is not None)
        allowed, missing = check_permissions(required, permissions)
        if not allowed:
            return skipped_result(
                "test", None, "requires permission: " + ", ".join(missing),
                metadata={
                    "execution": build_execution_metadata(
                        "executed", requested=required, granted=permissions, producer="test",
                        extra={"disposition": "not_run", "cause": "permission_denied"},
                    ),
                    "suites": [], "scope": child_scope("none", reason="permission_denied"), "subprocess_count": 0,
                },
            )
        selection_reason = "explicit_test_paths" if test_paths else "full_suite"
        if changed_files is not None:
            if test_paths is not None or not changed_files:
                return error_result("test", None, "changed_files requires nonempty exclusive selection")
            try:
                test_paths, selection_reason = select_graph_tests(
                    project_root, changed_files, test_graph_path)
            except (OSError, ValueError, ContainmentError) as exc:
                return error_result("test", None, f"invalid changed-file selection: {exc}")
        if test_paths is not None and (
            not isinstance(test_paths, list) or not test_paths
            or len(set(test_paths)) != len(test_paths)
        ):
            return error_result("test", None, "test_paths must be a nonempty list of distinct selectors")
        selectors: dict[str, list[str]] = {"python": [], "javascript": []}
        for node in test_paths or []:
            if not isinstance(node, str) or not node or node.startswith("-"):
                return error_result("test", None, "invalid test selector")
            file = node.split("::", 1)[0]
            try:
                selected_file = PhysicalRoot(project_root).open_contained(file, purpose="read")
            except ContainmentError:
                return error_result("test", None, "selected test escapes project root")
            if not selected_file.is_file():
                return error_result("test", None, "selected test missing")
            language = (
                "python" if file.endswith(".py")
                else "javascript" if file.endswith((".test.js", ".test.jsx", ".test.ts", ".test.tsx"))
                and "::" not in node else None
            )
            if language not in requested:
                return error_result("test", None, "selector outside requested suite")
            selectors[language].append(node)
        if minimize_order_failure is not None:
            return _minimizer_result(
                project_root, test_paths, minimize_order_failure, selectors,
                runtime_path, image_ref, max_subprocesses, start)

        launches = 0
        outcomes: list[tuple[str, ToolResult]] = []
        rows: list[dict] = []
        for name in requested:
            reason: str | None = None
            executable = "unresolved"
            command: list[str] = []
            chosen = selectors[name] or [str(project_root)]
            if name == "python":
                if test_environment == "project":
                    env = select_analysis_environment(project_root, "project", permissions)
                    interpreter = Path(env.interpreter) if env.mode == "project" and env.interpreter else None
                    venv = Path(env.environment_root) if env.environment_root else project_root / ".venv"
                else:
                    active = project_python()
                    interpreter = Path(active) if active else None
                    venv = None
                if interpreter is not None and interpreter.is_file() and os.access(interpreter, os.X_OK):
                    prefix = run_subprocess([str(interpreter), "-c", "import sys;print(sys.prefix)"],
                                            cwd=project_root, timeout=10)
                    launches += 1
                    probe = None
                    if prefix.returncode == 0:
                        probe = run_subprocess([str(interpreter), "-m", "pytest", "--version"],
                                               cwd=project_root, timeout=10)
                        launches += 1
                    if (prefix.returncode or probe is None or probe.returncode
                            or (venv is not None
                                and Path(prefix.stdout.strip()).resolve() != venv.resolve())):
                        interpreter = None
                else:
                    interpreter = None
                if interpreter is None:
                    child = skipped_result("test", "pytest", "environment_unresolved")
                    reason = "environment_unresolved"
                else:
                    executable = str(interpreter)
                    command = [executable, "-m", "pytest", *chosen, "--tb=line", "-q"]
                    child = run_engine(
                        PytestEngine(interpreter=interpreter), project_root, selectors[name],
                        cwd=project_root, tool_name="test",
                        required_permissions=ExecutionPermissions(build=True),
                        permissions=permissions)
            else:
                if test_environment == "project":
                    binary = (resolve_project_binary("vitest", project_root)
                              or str(project_root / "node_modules/.bin/vitest"))
                else:
                    binary = resolve_binary("vitest")
                if not binary or not Path(binary).is_file() or not os.access(binary, os.X_OK):
                    child = skipped_result("test", "vitest", "environment_unresolved")
                    reason = "environment_unresolved"
                else:
                    executable = str(binary)
                    command = [executable, "run", "--reporter=json", "--no-color", *chosen]
                    engine = VitestEngine()
                    engine.binary = executable
                    child = run_engine(
                        engine, project_root, selectors[name], cwd=project_root,
                        tool_name="test", required_permissions=ExecutionPermissions(build=True),
                        permissions=permissions)
            outcomes.append((name, child))
            metrics = child.get("metrics") or {}
            if child["status"] == "skipped" and reason is None:
                reason = "no_tests_collected"
            rows.append({
                "suite": name, "status": child["status"], "reason": reason, "command": command,
                "environment": executable, "selected_tests": chosen,
                **{key: metrics.get(key, 0) for key in _ZERO},
            })
        for (_, child), row in zip(outcomes, rows):
            child_reason = row["reason"]
            if child_reason is None and child["status"] == "error":
                child_reason = "engine_error"
            coverage = "complete" if child["status"] in {"ok", "warn", "fail"} and row["collected"] > 0 else "none"
            child.setdefault("metadata", {})["scope"] = child_scope(
                coverage, reason=child_reason, requested_targets=row["selected_tests"],
                matched_file_count=row["collected"], consumed_file_count=row["passed"] + row["failed"] + row["skipped"],
            )
        result = aggregate_results("test", [child for _, child in outcomes])
        assessed = [p for (_, child), row in zip(outcomes, rows)
                    if child["status"] in {"ok", "warn", "fail"} and row["collected"] > 0
                    for p in row["selected_tests"]]
        spawns = sum(len(((c.get("metadata") or {}).get("engines") or [{}])[0].get("spawns", []))
                     for _, c in outcomes)
        result.setdefault("metadata", {}).update({
            "suites": rows, "assessed_paths": assessed, "selection_reason": selection_reason,
            "test_environment": test_environment, "subprocess_count": launches + spawns,
            "scope": aggregate_scope([child for _, child in outcomes]),
        })
        return result


def select_graph_tests(root: Path, changed_files: list[str],
                       graph_path: Path | str | None) -> tuple[list[str] | None, str]:
    root = Path(root).resolve()
    physical = PhysicalRoot(root)
    changed: dict[str, str] = {}
    for name in changed_files:
        source = physical.open_contained(name, purpose="read")
        if not source.is_file():
            raise ValueError("changed source absent")
        changed[source.relative_to(root).as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
    if graph_path is None:
        return None, "missing_graph_full_suite"
    graph_rel = Path(graph_path)
    if graph_rel.is_absolute():
        graph_rel = graph_rel.resolve().relative_to(root)  # ValueError when outside the root
    try:
        graph = json.loads(physical.open_contained(graph_rel, purpose="read").read_text())
    except (OSError, json.JSONDecodeError):
        return None, "invalid_graph_full_suite"
    if (not isinstance(graph, dict) or graph.get("version") != 1 or graph.get("complete") is not True
            or not isinstance(graph.get("sources"), dict) or not isinstance(graph.get("edges"), dict)):
        return None, "incomplete_graph_full_suite"
    tests: list[str] = []
    for source, digest in changed.items():
        nodes = graph["edges"].get(source)
        if graph["sources"].get(source) != digest or not isinstance(nodes, list) or not nodes:
            return None, "unknown_graph_edge_full_suite"
        for node in nodes:
            if not isinstance(node, str) or not node or node.startswith("-"):
                return None, "invalid_graph_edge_full_suite"
            if not physical.open_contained(node.split("::", 1)[0], purpose="read").is_file():
                return None, "missing_graph_test_full_suite"
            tests.append(node)
    return sorted(set(tests)), "complete_graph_selection"


def _minimizer_result(project_root, test_paths, target, selectors, runtime_path, image_ref,
                      max_subprocesses, start) -> ToolResult:
    from ..runtime.isolated_process import (
        IsolationUnavailable, LaunchBudgetExhausted, run_isolated_argv)

    nodes = test_paths or []
    if (not nodes or nodes[-1] != target or selectors["javascript"] or runtime_path is None
            or not image_ref or type(max_subprocesses) is not int or max_subprocesses < 2
            or any("::" not in n or not n.split("::", 1)[0].endswith(".py")
                   or not n.split("::", 1)[1] for n in nodes)):
        return error_result("test", None, "minimize_order_failure requires ordered distinct pytest node "
                            "test_paths ending in the target, runtime_path, image_ref, max_subprocesses >= 2")
    physical = PhysicalRoot(project_root)

    def sources() -> dict[str, str]:
        return {n.split("::", 1)[0]: hashlib.sha256(
            physical.open_contained(n.split("::", 1)[0], purpose="read").read_bytes()).hexdigest()
            for n in nodes}

    before = sources()
    identity = {"image_ref": image_ref, "sources": before,
                "runtime_sha256": hashlib.sha256(Path(runtime_path).read_bytes()).hexdigest()}
    receipts: list[dict] = []
    observations: list[dict] = []
    cache: dict[tuple[str, ...], bool] = {}
    state = {"launches": 0, "attempts": 0}

    class _Stop(Exception):
        def __init__(self, status: str, reason: str | None = None):
            self.status, self.reason = status, reason

    def observe(sequence: list[str]) -> bool:
        key = tuple(sequence)
        if key in cache:
            observations.append({"nodes": list(sequence), "target_failed": cache[key], "cached": True})
            return cache[key]
        if sources() != before:
            raise _Stop("stale_source")
        remaining = max_subprocesses - state["launches"]
        if remaining <= 0:
            raise _Stop("budget_limited")
        argv = ["-m", "pytest", "-q", "--tb=line", *sequence]
        with tempfile.TemporaryDirectory(prefix="rush-test-order-") as scratch:
            try:
                proc = run_isolated_argv(
                    project_root, Path(scratch), runtime_path=runtime_path, image_ref=image_ref,
                    entrypoint=_PYTHON_ENTRYPOINT, argv=argv, timeout_s=180,
                    max_process_launches=remaining)
            except LaunchBudgetExhausted as exc:
                state["launches"] += exc.process_launches
                receipts.append({"argv": argv, "returncode": None,
                                 "process_launches": exc.process_launches})
                raise _Stop("budget_limited")
        state["launches"] += proc.process_launches
        receipts.append({"argv": argv, "returncode": proc.returncode,
                         "process_launches": proc.process_launches})
        if sources() != before:
            raise _Stop("stale_source")
        if proc.returncode in (0, 2):
            failed = False
        elif proc.returncode == 1:
            failed = bool(re.search(r"(?m)^FAILED\s+" + re.escape(target) + r"(?:\s|$)", proc.stdout))
        else:
            raise _Stop("error", f"pytest_exit_{proc.returncode}")
        cache[key] = failed
        observations.append({"nodes": list(sequence), "target_failed": failed, "cached": False})
        return failed

    status, reason, current = "reproduced", None, list(nodes[:-1])
    try:
        state["attempts"] += 1
        if not observe(list(nodes)):
            raise _Stop("baseline_not_reproduced")
        if observe([target]):
            raise _Stop("target_fails_alone")
        while True:
            for index in range(len(current)):
                trial = current[:index] + current[index + 1:]
                state["attempts"] += 1
                if observe([*trial, target]):
                    current = trial
                    break
            else:
                break
    except _Stop as stop:
        status, reason = stop.status, stop.reason
    except IsolationUnavailable:
        status, reason = "skipped", "isolation_unavailable"
    except ValueError as exc:
        status, reason = "error", str(exc)
    if status == "reproduced":
        ordered = [*current, target]
    elif status == "budget_limited":
        ordered = min((o["nodes"] for o in observations if o["target_failed"] and len(o["nodes"]) > 1),
                      key=len, default=list(nodes))
    else:
        ordered = list(nodes)
    receipt = {
        "status": status, "ordered_nodes": ordered,
        "minimality": {"reproduced": "one_deletion_minimal", "budget_limited": "budget_limited"}.get(status),
        "subprocess_count": sum(r["process_launches"] for r in receipts),
        "attempts": state["attempts"], "process_receipts": receipts, "observations": observations,
        "environment_digest": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
    }
    if reason:
        receipt["reason"] = reason
    tool_status = {"reproduced": "fail", "budget_limited": "warn", "baseline_not_reproduced": "warn",
                   "target_fails_alone": "warn", "skipped": "skipped", "error": "error",
                   "stale_source": "error"}[status]
    return ToolResult(
        tool="test", engine=None, engine_version=None, status=tool_status,
        duration_ms=elapsed_ms(start), summary=f"test: interaction reproducer {status}",
        findings=[], raw=None,
        metadata={"interaction_reproducer": receipt, "suites": [],
                  "scope": child_scope("complete" if status == "reproduced" else "none",
                                       reason=None if status == "reproduced" else (reason or status),
                                       requested_targets=ordered, matched_file_count=len(ordered)),
                  "subprocess_count": receipt["subprocess_count"]},
    )
```

### P2. src/rush/engines/pytest.py — add `__init__`, `version`, and an interpreter branch in `run`; replace `normalize`
`PytestEngine()` with no argument must keep working: it is the registry instance (`engines/__init__.py:137`) and many tests construct it. Add inside `class PytestEngine(Engine)`, before `run`:

```python
    def __init__(self, interpreter: Path | None = None) -> None:
        self.interpreter = None if interpreter is None else Path(interpreter)
        if self.interpreter is not None:
            self.binary = str(self.interpreter)  # run_engine preflight checks the same executable

    def version(self, *, owner_instance_id: str | None = None, run_id: str | None = None) -> str | None:
        if self.interpreter is None:
            return super().version(owner_instance_id=owner_instance_id, run_id=run_id)
        probe = run_subprocess([str(self.interpreter), "-m", "pytest", "--version"], timeout=10,
                               **ownership_kwargs(owner_instance_id, run_id))
        text = (probe.stdout or probe.stderr).strip()
        return text.split()[-1] if probe.returncode == 0 and text else None
```

In `run`, replace the lines

```python
        python = project_python(cwd or path)
        if python is None:
            return EngineResult(
                stdout="",
                stderr="",
                parsed={"prerequisite": "python"},
                findings=[],
                summary=PYTHON_PREREQUISITE,
                duration_ms=0,
            )
        argv = [python, "-m", "pytest", str(path), "--tb=line", "-q", *args]
```

with

```python
        if self.interpreter is not None:
            argv = [str(self.interpreter), "-m", "pytest", *(args or [str(path)]), "--tb=line", "-q"]
        else:
            python = project_python(cwd or path)
            if python is None:
                return EngineResult(
                    stdout="",
                    stderr="",
                    parsed={"prerequisite": "python"},
                    findings=[],
                    summary=PYTHON_PREREQUISITE,
                    duration_ms=0,
                )
            argv = [python, "-m", "pytest", str(path), "--tb=line", "-q", *args]
```

Replace the body of `normalize` after its existing `prerequisite` early-return block with audit lines 2265–2300 verbatim (the audit `normalize`). Add `from ..tools.common import error_result` at the top of that body as the audit does, and keep `Path`, `re` and `ownership_kwargs` imports. Exit 5 becomes `skipped` with collected 0; exit 0 with passed assertions is `ok`; exit 1 with failures is `fail`; everything else is `error`.

### P3. src/rush/engines/vitest.py
Add `import tempfile`, `from collections import Counter` and `from collections.abc import Mapping` to the imports. Paste audit lines 2306–2343 (`parse_vitest_502`) byte-for-byte as a module-level function. Replace `run` and `normalize` with:

```python
    def run(self, path, args, cwd=None, *, owner_instance_id=None, run_id=None) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        with tempfile.TemporaryDirectory(prefix="rush-vitest-") as directory:
            report_file = Path(directory) / "report.json"
            if report_file.exists():  # a pre-existing report is stale; never launch against it
                return EngineResult(exit_code=None, stdout="", stderr="", parsed=None, findings=[],
                                    summary="vitest report stale", duration_ms=0)
            argv = [binary_path, "run", "--reporter=json", f"--outputFile={report_file}", "--no-color",
                    *(args if args else [str(path)])]
            proc = run_subprocess(argv, cwd=cwd, timeout=300,
                                  **ownership_kwargs(owner_instance_id, run_id))
            try:
                report = json.loads(report_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = None
        return EngineResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
                            parsed=report, findings=[], summary=f"vitest exit {proc.returncode}",
                            duration_ms=0)

    def normalize(self, raw, path, tool_name) -> ToolResult:
        from ..tools.common import error_result

        status, metrics, findings = parse_vitest_502(raw.get("parsed"), raw.get("exit_code"))
        if status == "error":
            return error_result(tool_name, self.name,
                                "Vitest JSON report absent, stale, malformed, or inconsistent",
                                terminal_reason="malformed_output")
        return ToolResult(
            tool=tool_name, engine=self.name, engine_version=self.version(), status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"vitest: {metrics['passed']} passed, {metrics['failed']} failed, "
                    f"{metrics['skipped']} skipped",
            findings=findings, raw=None, metrics=metrics)
```
`resolve_binary(self.binary)` keeps its one-argument call so the existing test stub keeps working. An absolute `binary` returns itself (`binaries.py:396`).

### P4. W18 provider extension (specified here, implemented by the W18 owner)
Keep the audit signature at audit 13824 and add one trailing keyword, `max_process_launches: int | None = None`. Return `IsolatedRun(returncode, stdout, stderr, process_launches, receipt)` (a frozen dataclass with those five fields). Define `class LaunchBudgetExhausted(RuntimeError)` with attribute `process_launches: int`, raised before the launch that would exceed `max_process_launches`. Existing W18/W19/W21 callers omit the keyword and read only `.returncode`, `.stdout` and `.stderr`. The controller reads `.process_launches` only. The audit provider spends 2 launches per successful invocation (`image inspect` at 13858 plus the container run at 13877).

1. R1: replace early returns with independent suite outcomes, retain canonical
   ToolResult, and implement exact coverage aggregation above. RED uses a
   preprovisioned project .venv plus local Vitest, one real test each; assert
   two rows and exact 1/1/0/0 metrics. GREEN only scheduling/shared aggregation.
   Regression: test_mixed_project_runs_both_suites and existing tests/test_tools.py.
2. R2/R3: bind engine.binary/preflight/run to verified executable; map zero
   collection honestly; preserve every owner/run path. Regression:
   test_unknown_graph_runs_real_full_suite_and_zero_collection,
   test_project_environment_missing_never_uses_active_python,
   test_project_venv_used and existing subprocess ownership regression.
3. Vitest: implement fresh owned report invocation and validated adapter counts.
   RED four actual installed-version reports; GREEN run/normalize only.
   Regression: test_vitest_fresh_report_cases including malformed/stale report.
   Refactor no generic stdout parser and no npm fallback.
4. E1/transport: implement local select_graph_tests and typed forwarding once.
   Regression: test_unknown_graph_runs_real_full_suite_and_zero_collection and
   test_test_selection_actual_cli_stdio; complete graph selects exact nodes;
   path escape/string bool errors launch nothing.
5. X1: implement exclusive branch, real isolated oracle, remaining-budget debit
   before every launch, deterministic ordered deletion loop and final evidence.
   Regression: test_order_failure_real_oci_total_budget plus target-alone failure,
   unrelated failure, timeout/source drift and real isolation denial tests.
   Refactor only repeated validated oracle invocation, no new runner/framework.

The real mixed-project/project-.venv/Vitest cases require provisioning of actual
compatible test environments before RED execution. Those fixtures must be
captured from installed tools, not synthesized report dictionaries. Missing
engine/version/isolation inputs remain NOT READY and cannot be replaced by the
active Python regression body or a mocked launcher.

## Checks, failure/recovery, stop and completion
Before parser acceptance capture installed project Vitest --version and four
real reporter fixtures; audit observed 5.0.2 only. Unsupported shape stops
acceptance, never network install or mock equivalence.
Freeze bytes before checks; keep original source and failure receipts, owned
scratch cleanup only. Missing W18/process accounting stops X1.

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_test_tool.py tests/test_tools.py tests/test_subprocess_contract.py tests/test_cli_registry.py tests/test_mcp.py tests/test_isolated_process.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts

Reconcile R1–R3/E1/X1 independently with actual versions, frozen hash, exact
test results, budget and declared-file diff. Current authorization covers exactly
ten standalone Q01–Q10 plans. Any next batch requires explicit user approval;
no implementation, commit or push authorized.
