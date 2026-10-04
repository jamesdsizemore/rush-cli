# Q19 — `rush coverage` / `rush_coverage`: measured coverage and verified gap trials

Planning artifact. Production changes and future checks below are proposed, not implemented or passed. First executable packet is C1. Gap trials are a separately identified capability proposal; planning it does not make it an already approved production feature. Author: `gpt-6-astra`, high reasoning, responsible for Q19 source reconciliation, invocation/security design and this complete document. Coordinator must review frozen document bytes before assigning a development-ready verdict.

## Baseline, authority and ownership

Source: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, branch `phase/70-agent-adoption-and-usability`, HEAD `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`, clean; relevant dirty hashes: none. Delivery: `/Users/jamesdsizemore/Developer/rush-cli`, branch `codex/codex-cli-mcp-commands-review`, HEAD `c78e445ba1e575ca373e35840142cd627b055d6a`. Delivery's user-modified `AGENTS.md` SHA-256 `70252e9068f419b79d88e87b228ce796ae5e61fc0572f06f5354acf209f40617` and unrelated untracked documents/scratch remain untouched. Future implementation worktree starts at verified source HEAD; none is created by this plan. Do not switch/reset either checkout.

Binding inputs, SHA-256:

| Input | Identity |
|---|---|
| Delivery `docs/reports/cli-mcp-command-audit-2026-09-26.md`, complete Q19 lines 6975–7369 | `8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f` |
| Source `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` | `9453032d9411a27b2b7ee2ede074d98d93969fbe85433adacdec1c7bcc89c5c7` |
| Delivery `docs/templates/task-block-template.md` | `10fdb5380f04097258e29327cf74fe474532cdc42747a38310d0befa2107ecc3` |
| Source `.scratch/phase-70-design-gate/T8.md` | `b15a2c5e9c0fd0cab275c1bd17de78e1975f341048e6df9c403982619f12bfe2` |
| Source `.scratch/phase-70-design-gate/W1-T1-T7-T23.md` | `5fa3c629ef17c3f7812af1f274df1b23c3c43a00181778950902ae98f81939b3` |
| Source `.scratch/phase-70-design-gate/W2-T9-T17.md` | `a402ea6ffd4de9c5ca74860d9672cdb834242573ee45b2feb4ca2c2c5da9a0f9` |
| Source `.scratch/phase-70-design-gate/W4-T23-T29.md` | `47de33a0888a63ee6999a1610577f0e3d0868701642a3a27eb36111d1c1d7204` |
| Source `src/rush/tools/coverage.py` | `5edd9082b3b7d4d46b9ae65a45237297306e8a5ca0c77b64a7134e0cc1829da3` |
| Source `src/rush/cli_support/catalog_commands.py` | `a090f5cc4851cc3e4846e65a766f48286b0230c355cf188c04a4c562544c94ff` |
| Source `src/rush/mcp_support/tool_registry.py` | `76b16ae7c4ecd01d3206d798d6f827de4bcf969a0e1f99a9af7857d8deeb10b2` |
| Source `tests/test_coverage_importer.py` | `5aa755bcca770026a9b70c40a3ca4417b9503860e406b14e3d9d13936f6d580e` |

Read both AGENTS files, batch prompt Sections 1–6, template and current Phase 70 T8/T9/T10/T11/T15/T16/T6/T27 packets with their fuller brief resolutions/test matrices before implementation. Historical Batch 1 failure report supplies lessons only: current-callable RED; complete dependency contracts; source/delivery separation; no receipt substituted for plan. Cursor integration was removed by owner correction; do not reintroduce it.

**Single shared owner:** Batch integration owner owns all future edits to `src/rush/catalog.py`, `src/rush/cli_support/catalog_commands.py`, `src/rush/mcp_support/tool_registry.py`, `docs/CONFIGURATION.md`, `examples/rush.toml`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_phase60_characterization.py`, and `tests/fixtures/phase70/cli-outcomes.json`. Serialize consuming command changes Q11 → Q12 → Q13 → Q14 → Q15 → Q16 → Q17 → Q18 → Q19 → Q20. Q15 P0 implements shared isolation before any consuming trial packet. Q19 command owner owns `src/rush/tools/coverage.py`, new `tests/test_coverage.py`, new `tests/test_coverage_transport.py`. No worker concurrently edits shared paths. Shared ownership does not delegate missing design: Q19 exact changes follow below.

## P0A — Raw MCP catalog validation before SDK coercion

**Required behavior.** Shared prerequisite, Batch integration owner, implemented once with Q11 before new options. Applies only registered rush_actions, rush_yaml, rush_sql, rush_templates, rush_containerfile, rush_iac, rush_secrets, rush_sbom, rush_coverage, rush_codeql. Preserve unregistered/unknown SDK errors, existing request-model tools, and restricted memory server. Parent's current Python3.12 SDK probe proved unknown fields discarded and string "true" coerced to True before make_tool_wrapper. Wrapper-only validation is insufficient. This fixes current contract; additional options are still future interfaces.

**Deliverables.** `src/rush/mcp_support/tool_registry.py` adds two finite helpers/constants below; `src/rush/mcp.py::RushFastMCP.call_tool/list_tools` consumes them before super call; `tests/test_mcp.py::test_catalog_raw_invalid_before_sdk`, `::test_catalog_raw_type_matrix`. No dependency or validation framework.

~~~python
# src/rush/mcp_support/tool_registry.py
import math

RAW_CATALOG_TOOLS = frozenset({
    "rush_actions", "rush_yaml", "rush_sql", "rush_templates",
    "rush_containerfile", "rush_iac", "rush_secrets", "rush_sbom",
    "rush_coverage", "rush_codeql",
})

def catalog_raw_invalid_fields(arguments, schema):
    if not isinstance(arguments, dict) or any(type(k) is not str for k in arguments):
        return ["$"]
    properties = schema.get("properties", {})
    definitions = schema.get("$defs", {})

    def matches(value, shape, depth=0):
        if depth > 16:
            return False
        reference = shape.get("$ref")
        if reference is not None:
            prefix = "#/$defs/"
            return (isinstance(reference, str) and reference.startswith(prefix)
                    and reference[len(prefix):] in definitions
                    and matches(value, definitions[reference[len(prefix):]], depth + 1))
        alternatives = shape.get("anyOf")
        if alternatives is not None:
            return any(matches(value, branch, depth + 1) for branch in alternatives)
        kind = shape.get("type")
        if kind == "null":
            return value is None
        if kind == "boolean":
            return type(value) is bool
        if kind == "integer":
            return type(value) is int
        if kind == "number":
            return type(value) is int or (type(value) is float and math.isfinite(value))
        if kind == "string":
            return type(value) is str
        if kind == "array":
            return type(value) is list and all(
                matches(item, shape.get("items", {}), depth + 1) for item in value)
        if kind == "object":
            return type(value) is dict and all(type(key) is str for key in value)
        if "enum" in shape:
            return any(type(value) is type(item) for item in shape["enum"])
        if not shape:
            return (value is None or type(value) in (str, bool, int)
                    or (type(value) is float and math.isfinite(value))
                    or (type(value) is list and all(matches(v, {}, depth + 1) for v in value))
                    or (type(value) is dict and all(
                        type(k) is str and matches(v, {}, depth + 1)
                        for k, v in value.items())))
        return False

    invalid = set(arguments) - set(properties)
    invalid.update(set(schema.get("required", [])) - set(arguments))
    invalid.update(key for key, value in arguments.items()
                   if key in properties and not matches(value, properties[key]))
    return sorted(invalid)
~~~

This guard validates raw JSON types, nullable branches, required/unknown fields and array element types. Semantic choice values, bounds, path containment and grants stay existing command/shared validators. It rejects JSON-stringified arrays for these ten catalog tools; legacy JSON-string container compatibility on request-model project/scan/memory is unchanged. No expansion to other tools.

Exact insertion at the start of existing `RushFastMCP.call_tool`, before its current REQUEST_MODEL_TOOLS condition:

~~~text
from .mcp_support.tool_registry import RAW_CATALOG_TOOLS, catalog_raw_invalid_fields
from .tools.common import error_result

registered = self._tool_manager.get_tool(name)
if name in RAW_CATALOG_TOOLS and registered is not None:
    invalid = catalog_raw_invalid_fields(arguments, registered.parameters)
    if invalid:
        envelope = error_result(
            name.removeprefix("rush_"), None, "Invalid request",
            terminal_reason="INVALID_REQUEST",
            metadata={"reason": "invalid_request", "invalid_fields": invalid})
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope, indent=2))],
            structuredContent=envelope, isError=False)
~~~

The insertion is a method-body fragment: indentation belongs inside async method. Imports json/CallToolResult/TextContent already exist in defining module. Existing method body follows untouched. In `list_tools` existing loop, add independent `if tool.name in RAW_CATALOG_TOOLS: tool.inputSchema={**tool.inputSchema,"additionalProperties":False}`, importing same constant. Do not change registered.parameters or low-level SDK manager internals.

Complete current regression body, appended to existing tests/test_mcp.py:

~~~python
def test_catalog_raw_invalid_before_sdk(tmp_path):
    import asyncio, json
    from rush.mcp import build_server
    from mcp.types import CallToolResult
    server = build_server(profile="full")
    raw = asyncio.run(server.call_tool("rush_actions", {
        "path": str(tmp_path / "missing"),
        "unexpected": 1, "allow_cache_write": "true"}))
    if isinstance(raw, CallToolResult):
        value = raw.structuredContent
        if value is None:
            value = json.loads(next(c.text for c in raw.content if c.type == "text"))
    elif isinstance(raw, tuple):
        value = raw[1]
    else:
        value = json.loads(next(c.text for c in raw if c.type == "text"))
    assert value["status"] == "error"
    assert value.get("metadata", {}).get("invalid_fields") == [
        "allow_cache_write", "unexpected"]
    assert value["metadata"]["reason"] == "invalid_request"
    assert list(tmp_path.iterdir()) == []


def test_catalog_raw_type_matrix():
    from rush.mcp_support.tool_registry import catalog_raw_invalid_fields
    schema = {"type": "object", "required": ["path"], "properties": {
        "path": {"type": "string"},
        "allow_build": {"type": "boolean", "default": False},
        "limit": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None},
        "names": {"type": "array", "items": {"type": "string"}, "default": []}}}
    assert catalog_raw_invalid_fields(
        {"path": ".", "allow_build": False, "limit": None, "names": ["a"]}, schema) == []
    assert catalog_raw_invalid_fields(
        {"path": ".", "allow_build": "false", "limit": True, "names": ["a", 2]}, schema
    ) == ["allow_build", "limit", "names"]
    assert catalog_raw_invalid_fields({"path": ".", "limit": 1.0}, schema) == ["limit"]
    assert catalog_raw_invalid_fields({"path": ".", "names": '["a"]'}, schema) == ["names"]
    assert catalog_raw_invalid_fields({"path": None}, schema) == ["path"]
    assert catalog_raw_invalid_fields({}, schema) == ["path"]
    assert catalog_raw_invalid_fields([], schema) == ["$"]
~~~

First test runs current real server path with missing target, so no engine needed; current RED reaches invalid_fields assertion, not new helper import. Second checks future helper only after implementation. To prove early rejection itself, after implementation wrap `_standard_context` with a raising spy while calling each invalid case; zero calls plus unchanged root/tree. Full stdio consumer test below exercises raw wire arguments, not only SDK metadata.

**Constraints.** Guard has no root/config/permissions/runtime/engine reads; registration lookup/schema inspection only. Unknown/unregistered tools remain SDK errors. Do not reject valid nulls or coerce strings to bool/int/list.

**Checks.** `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_mcp.py::test_catalog_raw_invalid_before_sdk tests/test_mcp.py::test_catalog_raw_type_matrix -q`; each command transport invalid-input case and existing request-model/restricted-server regression.

**Completion.** Actual raw MCP invalid fields produce canonical error with sorted names before effects; every advertised new/default field follows current published type; ordinary valid calls and unaffected profiles remain compatible.



Q19 consumes P0A unchanged. Batch integration owner additionally owns `src/rush/mcp.py::{RushFastMCP.call_tool,RushFastMCP.list_tools}` solely for this shared prerequisite. Order: Q11 P0A raw guard before Q19 C2 option/schema integration; command owner must not duplicate guard in `CoverageTool` or a late wrapper. Add this complete consumer body to `tests/test_coverage_transport.py`, using its defined `rpc` helper:

```python
def test_coverage_stdio_raw_invalid_has_zero_effects(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "rush.toml").write_text("")
    before = {p.relative_to(root).as_posix(): p.read_bytes()
              for p in root.rglob("*") if p.is_file()}
    result = asyncio.run(rpc(root, {
        "path": "missing", "unexpected": 1, "allow_cache_write": "true",
    }, tmp_path / "invalid-wire.log"))
    assert result["status"] == "error"
    assert result["metadata"]["reason"] == "invalid_request"
    assert result["metadata"]["invalid_fields"] == ["allow_cache_write", "unexpected"]
    assert {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()} == before
    assert not (root / ".rush").exists()
```

This actual initialized stdio request must fail at P0A before missing-target/config/engine processing. It does not substitute for granted engine/algorithm tests. Check: `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_mcp.py::test_catalog_raw_invalid_before_sdk tests/test_mcp.py::test_catalog_raw_type_matrix tests/test_coverage_transport.py::test_coverage_stdio_raw_invalid_has_zero_effects -q`.

## Goal, scope and requirement ledger

Fresh execution must measure actual exercised source. Exit zero alone is never coverage. Preserve report imports, canonical statuses and Phase 70 invocation identity. Distinguish fixes, ordinary extensions, user baselines and capability proposals.

| ID/category | Current evidence and disposition | Exact change / packet / acceptance |
|---|---|---|
| Q19-F1 repair | `CoverageTool.run`, `tools/coverage.py:129–206`: slow-only grant; implicit undercover preference; coverage/pytest launch returns no metrics. Current-callable reproduction below returns `ok`, `metrics=None`. | C1: build+slow+artifact-write before probes/writes; fresh owned run; coverage JSON export; measured counts; no export/zero tests errors. C1 RED must fail at status assertion. |
| Q19-P1 preservation | Import code `:72–127`, `_coverage_percent :209–244`: LCOV/Cobertura/JSON percentages, containment and imported metadata. `tests/test_coverage_importer.py` passed as part of 24 importer tests on source. | C1 keeps import metrics/label and statuses; report import never invokes engine, specialist or tests. Malformed, absent, escaping reports remain distinct. |
| Q19-F2 semantic repair | Undercover measures untested changed blocks, not whole-project line coverage; current preference masks chosen measurement. | C1 live line route uses coverage.py, with pytest-cov as compatible export fallback only after confirmed installed capability. Preserve `UndercoverEngine` and `tests/test_undercover_reference.py`; add explicit `measurement='diff'` route that returns its real result with `metadata.measurement='untested-diff-blocks'`, no invented line percentage. Trial/base options reject diff measurement. |
| Q19-E1 ordinary proposed extension | Audit changed-line proposal is absent from current signatures. Audit regex ignores quoted filenames and zero-count hunks. | C2 explicit Git commit base; NUL-delimited changed file paths; per-file hunk ranges and source/report digest guards. Exact missing changed-line set, never branch percent derived from lines. |
| Q19-E2 ordinary proposed extension | Current `__call__` has report+grants only. Audit mentions selected tests but callsite omits them. | C2 `test_paths` tuple, CLI repeatable `--test-path`, MCP string array; one canonical root-relative selection; selector outside root errors before spawn. |
| Q19-B1 requested baseline: provisioning | Engine discovery exists through `runtime/binaries.py::resolve_binary`, current coverage catalog has no engine IDs (`catalog.py:340–346`). Absence is not installer authorization. | C2 catalog names `coverage`/`undercover`; missing report lists exact executable/action and probe state. Existing consented setup/provisioning remains provider. Command never installs/downloads; unsupported provisioning is explicit. |
| Q19-B2 requested baseline: connected specialist | Audit's `OfflineReviewTool._invoke_local_model` and isolated runtime are proposals, not callable verified providers. | C3 supplies command-local pinned llama.cpp invocation and JSON response parser; exact model/image digests, prompt, grant and failures below. No fabricated specialist output. |
| Q19-B3 requested baseline: voice/live speech/3D | Neither command signature nor measured-result path is a voice/companion endpoint. | Result metadata remains serializable source-bound evidence available to those consumers; Q19 adds no unrelated UI or microphone operation. This is applicability assessment, not removal of product-wide baseline. |
| Q19-X1 distinct capability proposal | Gap trial is not current execution, and current coverage does not close exact missing branch through a generated assertion. Audit toy `gap_trial` proves only Boolean controller. | C3 fresh baseline → specialist candidate → isolated test → same source plus exact line/arc observed transition; repeat/assertion sensitivity control; candidate artifact only, no source application. Label proposal separately; full design below. |
| P70 T8/T9 preservation + direct-call repair | Defining resolver/executor already canonicalize CLI/MCP paths, preserve originals and reject missing targets; wrapper `tool_registry.py:318–388` anchors server cwd. Direct tool method still needs secondary report/test containment. | C1/C2 reuse `PhysicalRoot`; no `chdir`; directory live target required; missing=error, empty supported source=skipped; declared project wins; symlink/reparse and foreign-cwd tests. |
| P70 T10/T11 preservation | Existing `run_subprocess` carries ambient owner/run identity. `resolve_binary(..., project_root=root)` excludes untrusted project PATH. | C1 owner directory `.rush/runs/coverage-*`, grants before construction, identity before/after, no hidden cache; all children through existing runner; record actual interpreter/binary. Never call bare `coverage` after a trusted lookup. |
| P70 T15/T16/T27 preservation | Execution metadata/scope/compact delivery are shared contracts, not coverage parser responsibilities. | C2 truthful per-engine states; actual JSON file list for consumed source; original requested scope retained; human output includes counts/report path; exact exits and initialized stdio tests. Compact denial produces zero effects; no tool-local CCR. |
| P70 T6 preservation | Flat object MCP schema and typed explicit callable signature already published. | C2 explicit optional parameters, unchanged existing grants/project injection; inspect real `tools/list`; no top-level schema combinator or generic option introspection. |

No memory retrieval/storage or token-budget side effect added. Changed-line evidence is ordinary functionality. Specialist trials assess new agent-side execution/observation; model connectivity itself is requested baseline, not invention.

## Required behavior and concrete interface

Both `CoverageTool.__call__` and `.run` gain exactly these keyword fields; `.run` retains `config=None, permissions=None`, `__call__` retains seven `allow_*: bool=False` and constructs existing `ExecutionPermissions`:

```python
report_path: Path | None = None
measurement: str = "line"                 # exactly line|diff
test_paths: tuple[str, ...] = ()
base_ref: str | None = None
trial_gap_test: str | None = None
local_runtime_path: str | None = None
local_model_path: str | None = None
local_model_sha256: str | None = None
local_model_image_ref: str | None = None
coverage_image_ref: str | None = None
trial_timeout_seconds: int = 60           # strict integer, 1..600
```

Explicit flags: `--measurement [line|diff]`, repeatable `--test-path TEXT`, `--base-ref TEXT`, `--trial-gap-test TEXT`, `--local-runtime-path PATH`, `--local-model-path PATH`, `--local-model-sha256 TEXT`, `--local-model-image-ref TEXT`, `--coverage-image-ref TEXT`, `--trial-timeout-seconds INTEGER`. Add only Q19 entry to `_TOOL_CLI_OPTIONS`, not generic generation. Use `click.IntRange(1,600)`; semantic validation also runs in tool so direct/MCP calls cannot bypass it. Add matching `ToolOptionSpec` declarations using `str`, `tuple`, `int`, defaults above; runtime-only executable/image/model pins are explicit invocation fields, never accepted from project `rush.toml`. Ordinary config allows measurement/test_paths/base_ref only; explicit request overrides config.

`test_paths` and `local_model_path` are project-root-relative, documented as such; exclude both from MCP `_CWD_RELATIVE_ARGS` so wrapper does not anchor them to foreign server cwd. `report_path` keeps existing report interpretation; coverage's cwd-relative map contains only `report_path`, so CLI/MCP report operands resolve at invocation/server/declared-project anchor before containment. `local_runtime_path` must be absolute; never silently resolve relative runtime binaries. `project` remains wrapper-only. Flat MCP properties are the exact names above; test paths are an array of strings; no implicit grants from connection/profile/prior calls.

Import wins only when an explicit `report_path` exists or positional file has `.json/.xml/.lcov/.info`; conflicting execution fields yield canonical `error`, `metadata.reason='import_execution_conflict'`, zero effects. Preserve legacy valid file imports. A `.py` positional file now gives actionable `error` (`live_requires_directory`) rather than treating source text as malformed report. Explicit absent report remains `skipped`; missing analysis target is `TARGET_NOT_FOUND` through shared invocation. Empty directory with no regular Python source gives `skipped`, `reason='no_supported_targets'`, no run directory.

Line mode execution requires build+slow+artifact-write even if one is granted already. Denial uses `skipped`, `metadata.execution.disposition='not_run'`, `cause='permission_denied'`; exact missing grants from `check_permissions`. No version probe, directory, import execution, export, specialist or cache on denied branch. Diff mode requires same execution grants because Undercover can execute project test machinery; reuse existing adapter and annotate distinct measurement.

Fresh line runner prefers resolved `coverage` executable. Probe its version and required `coverage json --help`/`coverage run --help` capabilities after grants: require JSON export, branch, source and rcfile options. Missing option/nonzero probe returns `skipped`, reason `engine_incompatible`; do not invent version ranges. Historical audit exercised coverage.py7.16.1 helper only; it is a reference fixture version, not current integrated evidence. If coverage binary missing, resolve trusted `pytest`; probe `pytest --help` only after grants and require `--cov`, `--cov-report`, `--cov-branch`, `--cov-config` before fallback. Record actual plugin version from `pytest --version --version`, whose plugin list must identify pytest-cov; absent version is explicit unavailable metadata, not invented range. In fallback execute `pytest --cov --cov-branch --cov-config=<owned>/.coveragerc --cov-report=json:<owned>/coverage.json -o addopts=` with same JUnit/run directories and owned environment below. If neither capability exists: `skipped`, reason `engine_missing`, metrics null, actionable engine message. Both adapters validate actual report shape/counts after execution, so unsupported JSON is error rather than guessed compatibility. No implicit package install.

Run root is canonical target directory. Source scope is its contained `src/` directory when present, otherwise target directory excluding `tests/`, `.rush/`, `.git/`, `.venv/` and `__pycache__/`. User tests default to contained `tests/` if present, otherwise target directory; explicit test paths replace default and reject absolute/traversal/NUL/symlink/node selector escape. A `::node` suffix is allowed only after validating its file path; it is passed as one argv element. No shell. `coverage run --rcfile=<owned>/.coveragerc --branch -m pytest <tests...> -q -o addopts= -p no:cacheprovider --junitxml=<owned>/tests.xml` followed by `coverage json --rcfile=<owned>/.coveragerc -o <owned>/coverage.json`. Both phases receive the exact owned configuration and scrubbed environment below; ambient `.coveragerc`, `pyproject.toml`, `setup.cfg`, `tox.ini` and `COVERAGE_*` must not change measurement. Baseline host execution is permissioned project execution; it does not claim OCI isolation.

### C1 owned measurement configuration

Insert complete helper in `src/rush/tools/coverage.py`, called only after execution grants and owned run-directory creation. `owned` is existing exclusive invocation directory, never source root. Caller passes validated canonical `source_scope` (`root/src` when present, otherwise root); helper writes that source directory into effective config bytes used by both execution and reporting. Same returned environment goes to capability probes, run and JSON export; record SHA256 of the effective bytes as `metadata.measurement_config_digest`, record contained config artifact path separately. Configuration remains unchanged through export; verify its digest alongside source/report identity. It is an output artifact, not user project configuration.

Coverage's [relative-files contract](https://coverage.readthedocs.io/en/latest/config.html#run-relative-files) requires source in configuration for reporting to retain origin; CLI-only source is insufficient. Its [source-selection contract](https://coverage.readthedocs.io/en/latest/source.html) also enables reporting files never imported. Therefore both runner paths use one explicit configured source, and the genuine two-module fixture below must include the unexecuted module in total statements. Configuration path escaping follows documented `$$` literal-dollar syntax; reject comma/CR/LF/NUL or surrounding whitespace that INI source-list syntax cannot represent exactly, returning canonical error `unrepresentable_source_scope` before creating config or launching a runner.

```python
import hashlib
import os

def coverage_config_bytes(source_scope):
    source = source_scope.as_posix()
    if (not source_scope.is_absolute() or source != source.strip()
            or any(character in source for character in (",", "\r", "\n", "\x00"))):
        raise ValueError("unrepresentable_source_scope")
    source = source.replace("$", "$$")
    prefix = b"[run]\nbranch = True\nparallel = False\nrelative_files = True\nsource =\n    "
    return prefix + source.encode("utf-8") + b"\n" + (
        b"plugins =\nomit =\n    */tests/*\n    */.rush/*\n    */.git/*\n"
        b"    */.venv/*\n    */__pycache__/*\n"
        b"[report]\nignore_errors = False\n[json]\nshow_contexts = False\n"
    )

def owned_coverage_environment(owned, source_scope):
    effective_config = coverage_config_bytes(source_scope)
    rcfile = owned / ".coveragerc"
    with rcfile.open("xb") as stream:
        stream.write(effective_config)
    rcfile.chmod(0o600)
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("COVERAGE_") and key not in {
            "PYTHONPATH", "PYTEST_ADDOPTS", "PYTEST_PLUGINS",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD"}
    }
    environment.update(COVERAGE_FILE=str(owned / ".coverage"),
                       COVERAGE_RCFILE=str(rcfile),
                       PYTHONDONTWRITEBYTECODE="1")
    return rcfile, environment, hashlib.sha256(effective_config).hexdigest()
```

Fallback capability probe additionally requires `--cov-config`. Exact fallback argv extends existing pytest selection with `--cov --cov-branch --cov-config=<owned>/.coveragerc --cov-report=json:<owned>/coverage.json -o addopts= -p no:cacheprovider --junitxml=<owned>/tests.xml`; no fallback reloads project coverage config. Explicit `--cov-config` and `COVERAGE_RCFILE` agree. Coverage CLI uses explicit `--rcfile` on both `run` and `json`; source/project `addopts` cannot reintroduce coverage override because final `-o addopts=` clears it. Ordinary user conftest/test execution remains permissioned; this contract does not claim hostile test code is contained.

Use bare `--cov` immediately followed by `--cov-branch`, never a source-valued cov option: [pytest-cov documents that a value overrides configured source](https://pytest-cov.readthedocs.io/en/latest/config.html). Source remains in one effective config through JSON export. Append complete genuine-engine regression to `tests/test_coverage.py`. Both parametrized modes use actual installed executables/plugins; monkeypatch only forces selection of fallback and sets hostile environment. Missing prerequisite fails acceptance; no engine/process output fabricated. Explicit fixture sys.path insertion occurs before importing project code and makes external pytest entrypoint behavior independent of inherited PYTHONPATH or launcher cwd.

```python
import pytest

@pytest.mark.parametrize("mode", ["coverage", "pytest-cov"])
def test_owned_config_ignores_hostile_project_and_environment(tmp_path, monkeypatch, mode):
    import hashlib
    import rush.tools.coverage as module
    from rush.permissions import ExecutionPermissions
    from rush.runtime.binaries import resolve_binary

    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "src").mkdir(); (root / "tests").mkdir()
    (root / "src/a.py").write_text(
        "def classify(x):\n    if x:\n        return 'yes'\n    return 'no'\n")
    (root / "src/b.py").write_text("def unimported():\n    return 42\n")
    (root / "tests/test_a.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from src.a import classify\ndef test_yes():\n    assert classify(1) == 'yes'\n")
    escaped = tmp_path / "escaped.coverage"
    marker = tmp_path / "plugin-imported"
    (root / "poison_coverage.py").write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('bad')\n"
        "def coverage_init(reg, options):\n    raise RuntimeError('ambient plugin')\n")
    hostile = "[run]\ndata_file = " + str(escaped) + "\nomit = *\nplugins = poison_coverage\n"
    (root / ".coveragerc").write_text(hostile)
    (root / "setup.cfg").write_text(hostile.replace("[run]", "[coverage:run]"))
    (root / "tox.ini").write_text(hostile.replace("[run]", "[coverage:run]"))
    (root / "pyproject.toml").write_text(
        '[tool.coverage.run]\nomit = ["*"]\nplugins = ["poison_coverage"]\n'
        '[tool.pytest.ini_options]\naddopts = "--cov=poison_coverage"\n')
    external = tmp_path / "external.rc"; external.write_text(hostile)
    monkeypatch.setenv("COVERAGE_RCFILE", str(external))
    monkeypatch.setenv("COVERAGE_FILE", str(escaped))
    monkeypatch.setenv("COVERAGE_PROCESS_START", str(external))
    monkeypatch.setenv("PYTEST_ADDOPTS", "--cov=poison_coverage")
    before = {p.relative_to(root).as_posix(): p.read_bytes()
              for p in root.rglob("*") if p.is_file()}
    if mode == "coverage":
        assert resolve_binary("coverage", project_root=root), "installed coverage prerequisite"
    else:
        assert resolve_binary("pytest", project_root=root), "installed pytest prerequisite"
        original = module.resolve_binary
        def prefer_pytest(binary, *args, **kwargs):
            return None if binary == "coverage" else original(binary, *args, **kwargs)
        monkeypatch.setattr(module, "resolve_binary", prefer_pytest)
    result = module.CoverageTool().run(root,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True))
    assert result["status"] == "warn", result
    assert (result["metrics"]["covered_lines"], result["metrics"]["total_lines"],
            result["metrics"]["line_percent"]) == (3, 6, 50.0)
    assert result["metadata"]["missing_lines"] == {"src/a.py": [4], "src/b.py": [1, 2]}
    assert result["metadata"]["measurement_config_digest"] == hashlib.sha256(
        module.coverage_config_bytes(root / "src")).hexdigest()
    assert not escaped.exists() and not marker.exists()
    assert not (root / ".coverage").exists()
    for name, content in before.items():
        assert (root / name).read_bytes() == content
```

Before execution inventory regular source bytes and contained coverage/pytest configs; reject symlink configs and compare hashes afterward. Stale source/config makes `error` reason `source_digest_drift` or `config_digest_drift`, with completed steps retained. Hidden inherited coverage configuration must be neutralized using explicit owned `.coveragerc` containing the selected source/omit/branch settings; pytest uses contained project config and its hash. This prevents user/environment export settings from moving report artifacts.

`.rush/runs` is checked with `PhysicalRoot.open_contained(..., purpose='write')` before mkdir. Create private unique child, never reuse an old report. Report/JUnit regular files must be inside owned run and not symlinks, max 16 MiB each. Failed parse/export/timeout/crash produces `error`, preserves bounded phase diagnostics in result and valid recovery artifact paths, removes incomplete `.tmp` only in owned directory. A prior successful report is never consumed. Export completed report using replace within owned directory; never overwrite user reports. Retain owned finished evidence until explicit user cleanup.

Statuses: denied/missing/incompatible engine or no supported input=`skipped`; infrastructure/invalid measurements/no tests=`error`; pytest return 1 with valid report and executed tests=`fail`; return 0 with missing source lines=`warn`; return 0 with 100% measured lines=`ok`. A test suite with any skipped testcase and successful others is at least `warn`; all skipped means `error` reason `zero_executed_tests`. Valid zero source statements means `skipped`, reason `zero_measurable_lines`; never 100%. Test exit 2/3/4/5 is error even if stale-looking files exist. Scope counts derive from verified report file entries, never from arbitrary directory operands.

Canonical result keeps tool/engine/version/status/duration/summary/findings/raw. Metrics: `covered_lines:int`, `total_lines:int`, `line_percent:float`, `collected_tests:int`, `executed_tests:int`, `skipped_tests:int`; branch metrics use `covered_branches,total_branches,branch_percent` only when JSON includes valid branch counts. Metadata includes `evidence_source='executed-runner'`, `measurement='line'`, sorted `source_hashes`, `config_hashes`, `report_digest`, `test_exit`, `missing_lines`, `missing_branches`, `steps`, `execution`, `engines`, and exact scope. Artifacts contain fresh report/JUnit/owned configuration, not `.coverage` as substitute for parsed evidence. Imported evidence retains `imported-local-report` and existing percentages; no source freshness claim.

### Minimum GREEN measurement parser

Add this exact helper in `src/rush/tools/coverage.py`; runner described above calls it only on its own fresh JSON/JUnit after bounded reads. Imports are local here so fragment is executable. `_coverage_percent` remains import-format parser.

```python
def measured_counts(payload, junit_text):
    from xml.etree import ElementTree

    totals = payload["totals"]
    covered, total = totals["covered_lines"], totals["num_statements"]
    if type(covered) is not int or type(total) is not int or not 0 <= covered <= total:
        raise ValueError("invalid_line_counts")
    cases = list(ElementTree.fromstring(junit_text).iter("testcase"))
    skipped = sum(case.find("skipped") is not None for case in cases)
    if not cases or len(cases) == skipped:
        raise ValueError("zero_executed_tests")
    files = payload["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("missing_file_evidence")
    summed_covered = summed_total = 0
    for name, row in files.items():
        if not isinstance(name, str) or not isinstance(row, dict):
            raise ValueError("invalid_file_evidence")
        hit, miss = row["executed_lines"], row["missing_lines"]
        if not isinstance(hit, list) or not isinstance(miss, list):
            raise ValueError("invalid_line_evidence")
        if any(type(x) is not int or x < 1 for x in hit + miss):
            raise ValueError("invalid_line_evidence")
        if len(set(hit)) != len(hit) or len(set(miss)) != len(miss) or set(hit) & set(miss):
            raise ValueError("inconsistent_line_evidence")
        summed_covered += len(hit)
        summed_total += len(hit) + len(miss)
    if (summed_covered, summed_total) != (covered, total):
        raise ValueError("inconsistent_totals")
    return {
        "covered_lines": covered, "total_lines": total,
        "line_percent": 100.0 * covered / total if total else 0.0,
        "collected_tests": len(cases), "executed_tests": len(cases) - skipped,
        "skipped_tests": skipped,
    }
```

Report file names are validated separately through `PhysicalRoot(root).open_contained(name, purpose='read')`, with absolute engine paths translated only when physically within root; resolve once, normalize to POSIX relative names, reject duplicate aliases. Reject lines beyond file length. Branch arcs accept signed coverage.py endpoints (negative means function entry/exit); `trial_gap_test` line target is positive, arc target permits signed endpoints except zero. A negative arc endpoint is not an invalid source-line location.

## C0 — Register coverage in existing consented provisioning

### Required behavior

Requested baseline Q19-B1, not a capability proposal. Batch integration owner implements C0 before C1 runner acceptance and C2 catalog publication, after prior serialized command changes. SOURCE `catalog.py::EngineSpec` takes `(name,binary,install_hint,file_extensions,project_markers,capability)`; current `ENGINE_SPECS`, `ENGINE_PACKAGES` and `ENGINES` contain no `coverage`. Observed current call `resolve_engine_package('coverage')` raises `UnknownEngineError: Unknown or unsupported engine id: 'coverage'`. `runtime/binaries.py::resolve_binary` already accepts `engine_id='coverage'` and verifies a selected manifest before runtime-bin/PATH fallback; it requires no module registration or new engine adapter. Existing `setup/provision.py::{build_provision_plan,resolve_provision_identities,apply_provision_plan}` supplies the full preview, frozen identity, grant, install/probe and manifest flow. Reuse it.

### Deliverables

Single Batch integration owner additionally owns `src/rush/setup/engine_packages.py` and `tests/test_engine_provisioning.py`; catalog remains that same owner's file. Command owner retains C1 tool code. No new adapter/module/framework, no `ENGINES` addition, no tool registration or canonical tool-count change. Source has 56 `TOOL_SPECS` entries; MCP's separate 79-tool contract stays unchanged. Exact production patch fragments, inserted into existing literal maps (these are contextual fragments, not executable modules):

```diff
--- a/src/rush/catalog.py
+++ b/src/rush/catalog.py
@@ ENGINE_SPECS
+    "coverage": EngineSpec(
+        "coverage", "coverage", "pip install coverage",
+        ("py", "pyi"), ("pyproject.toml",), "metrics",
+    ),
--- a/src/rush/setup/engine_packages.py
+++ b/src/rush/setup/engine_packages.py
@@ _PYPI_ENGINES
+        "coverage",
@@ _ENGINE_BINARIES
+    "coverage": "coverage",
--- a/tests/test_engine_provisioning.py
+++ b/tests/test_engine_provisioning.py
@@
-def test_engine_packages_covers_exactly_all_121_engine_specs_keys() -> None:
+def test_engine_packages_covers_exactly_all_122_engine_specs_keys() -> None:
     assert set(ENGINE_PACKAGES.keys()) == set(ENGINE_SPECS.keys())
-    assert len(ENGINE_PACKAGES) == 121
+    assert len(ENGINE_PACKAGES) == 122
```

Existing `_build_engine_packages` derives package_id `coverage`, source `pypi`, manager `uv`, binary `coverage`, version_policy `latest_stable`, platform_policy `native_exact`, scan_class `standalone`, prerequisites `('uv','python')`, probe `('coverage','--version')`. Existing PyPI grant tuple is exactly `('network','download','cache_write')`. The version is resolved once under network consent and frozen into reviewed setup plan; C1 separately probes required measurement capabilities before execution. This does not guarantee pytest is installed inside coverage's interpreter: absent pytest/module capability gives actionable incompatible-engine result before tests, and existing pytest-cov fallback remains conditional on its actual installed capabilities. No implicit dependency install.

### Constraints

Preview remains offline and writes nothing. Existing setup save/apply routes retain plan ID and permission checks; coverage command never calls installer. Network/download/cache-write consent belongs setup, distinct from C1's build/slow/artifact-write execution grants. Installed-manifest hash verification must select the exact approved binary; replacing its bytes invalidates selection. Preserve unknown-engine rejection, other 121 package rows and all canonical tool IDs. Registry unit tests below use injected HTTP/installer/prober only; they prove wiring and denial, not real installation or coverage measurement. C1's genuine runtime tests remain mandatory.

### Checks

Add complete tests below to `tests/test_engine_provisioning.py`. First test is a current-API RED: existing `resolve_engine_package` raises before metadata assertion; it does not invoke a future API or install anything. Remaining tests run after exact three-map changes. All filesystem writes occur only in pytest temporary fixtures; no actual HTTP, package manager or engine launches occur.

```python
import hashlib
import json
import subprocess
from pathlib import Path

from rush.catalog import ENGINE_SPECS, TOOL_SPECS
from rush.permissions import ExecutionPermissions
from rush.runtime.binaries import resolve_binary, resolve_project_binary
from rush.setup.engine_packages import ENGINE_PACKAGES, resolve_engine_package
from rush.setup.provision import build_provision_plan, resolve_and_apply_provision_plan


def test_coverage_package_registered():
    package = resolve_engine_package("coverage")
    assert (package.engine_id, package.package_id, package.source, package.manager,
            package.binary, package.version_policy, package.platform_policy,
            package.scan_class, package.prerequisites, package.probe) == (
        "coverage", "coverage", "pypi", "uv", "coverage", "latest_stable",
        "native_exact", "standalone", ("uv", "python"), ("coverage", "--version"))
    spec = ENGINE_SPECS["coverage"]
    assert (spec.name, spec.binary, spec.install_hint, spec.file_extensions,
            spec.project_markers, spec.capability) == (
        "coverage", "coverage", "pip install coverage", ("py", "pyi"),
        ("pyproject.toml",), "metrics")
    assert len(TOOL_SPECS) == 56
    assert set(ENGINE_PACKAGES) == set(ENGINE_SPECS)


def test_coverage_provision_preview_denial_and_approved_binary(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='coverage-fixture'\n")
    data = tmp_path / "data"
    calls = []

    def snapshot():
        return {p.relative_to(tmp_path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in tmp_path.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("preview or denied setup attempted external effect")

    before = snapshot()
    plan = build_provision_plan(project, ["coverage"], os_name="linux", arch="x86_64",
        data_root=data, which=lambda name: f"/fixture/{name}", runner=forbidden)
    entry, = plan.entries
    assert (entry.engine_id, entry.identity_state, entry.required_grants, entry.probe) == (
        "coverage", "unresolved", ("network", "download", "cache_write"),
        ("coverage", "--version"))
    assert snapshot() == before and not data.exists() and not (project / ".rush").exists()
    denied = resolve_and_apply_provision_plan(plan, ExecutionPermissions(),
        project_id="coverage-fixture", data_root=data, current_platform=("linux", "x86_64"),
        http_get=forbidden, downloader=forbidden, runner=forbidden, prober=forbidden)
    assert denied.permission_blocked == {
        "coverage": ["--allow-network", "--allow-download", "--allow-cache-write"]}
    assert denied.applied == {} and denied.failed == {}
    assert snapshot() == before and not data.exists() and not (project / ".rush").exists()

    def http_get(url):
        assert url == "https://pypi.org/pypi/coverage/json"
        calls.append(("http", url))
        return json.dumps({"info": {"version": "7.6.1"}, "releases": {
            "7.6.1": [{"packagetype": "bdist_wheel", "url": "fixture:wheel",
                       "digests": {"sha256": "a" * 64}}]}}).encode()

    def runner(argv, env=None):
        assert argv == ["uv", "tool", "install", "--force", "coverage==7.6.1"]
        assert env is not None
        destination = Path(env["UV_TOOL_BIN_DIR"])
        assert destination.is_relative_to(data)
        assert Path(env["UV_TOOL_DIR"]) == destination / "tools"
        executable = destination / "coverage"
        executable.write_text("#!/bin/sh\nprintf 'Coverage.py, version 7.6.1\\n'\n")
        executable.chmod(0o755)
        calls.append(("install", argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    def prober(argv):
        assert len(argv) == 2 and argv[1] == "--version"
        assert Path(argv[0]).is_relative_to(data)
        calls.append(("probe", argv))
        return subprocess.CompletedProcess(argv, 0, "Coverage.py, version 7.6.1", "")

    granted = resolve_and_apply_provision_plan(plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="coverage-fixture", data_root=data, current_platform=("linux", "x86_64"),
        http_get=http_get, downloader=forbidden, runner=runner, prober=prober,
        which=lambda name: f"/fixture/{name}")
    assert set(granted.applied) == {"coverage"} and granted.failed == {}
    assert [kind for kind, _ in calls] == ["http", "install", "probe"]
    selected = resolve_project_binary("coverage", project)
    assert selected == calls[-1][1][0]
    assert resolve_binary("coverage", engine_id="coverage", project_root=project) == selected
    Path(selected).write_text("changed after approval")
    assert resolve_project_binary("coverage", project) is None
```

The injected version 7.6.1 is a deterministic provisioning identity, not a supported-version claim. Command owner must retain C1's explicit `resolve_binary('coverage',engine_id='coverage',project_root=root)` invocation before launching measurement. Resolver test above proves exact manifest binding; genuine C1 tests prove execution. Recovery uses existing setup semantics: failed probe or changed executable yields no ready manifest/selection; unknown IDs still reject before preview effects; no package install is triggered from coverage fallback.

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_engine_provisioning.py::test_coverage_package_registered tests/test_engine_provisioning.py::test_coverage_provision_preview_denial_and_approved_binary tests/test_engine_provisioning.py::test_engine_packages_covers_exactly_all_122_engine_specs_keys tests/test_engine_provisioning.py::test_unknown_engine_rejected_everywhere tests/test_engine_provisioning.py::test_apply_denied_grants_have_zero_effects -q
```

### Completion

Exit C0 only when new package metadata, offline preview, zero-effect denial, consented injected install/probe and exact manifest resolution assertions pass; then C1 genuine engine execution and C2 transport acceptance remain required. Stop on registry-count drift beyond this single addition and reconcile another serialized owner's registered engine before changing an exact count. Planning reproduced current UnknownEngineError, then executed these two proposed function bodies with only in-memory registry additions and temporary filesystem fixtures: metadata, preview, denial, injected consented install/probe, binding and changed-byte rejection passed. This verifies the proposed test wiring against current provisioning APIs; it is not production registry implementation or real installation. No production/test files changed and no external HTTP or package manager ran.

## C1 — Repair actual current execution

Implement `CoverageTool.run` measured execution in Rush using existing helpers. Read binding inputs above first.

### Required behavior

First RED reproduces current exit-only false success through current signature; then introduce complete runner/parser, grants and owned artifacts. Import preservation is initially GREEN and must remain GREEN.

### Deliverables

`src/rush/tools/coverage.py::{CoverageTool.run,measured_counts,run_measured_coverage}`; `tests/test_coverage.py` with first RED and real fixture below. Keep imports to `runtime.binaries.resolve_binary`, existing `tools.common.run_subprocess`, `permissions.check_permissions/build_execution_metadata`, `io.physical_paths.PhysicalRoot/ContainmentError`, canonical result helpers. No second process framework, no changes to shared subprocess ownership.

### RED — complete current-callable body

```python
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from rush.permissions import ExecutionPermissions
from rush.tools.coverage import CoverageTool


def test_missing_fresh_report_not_ok(tmp_path: Path):
    (tmp_path / "rush.toml").write_text("")
    (tmp_path / "a.py").write_text("x = 1\n")
    calls = []

    def child(argv, **kwargs):
        calls.append(argv)
        return CompletedProcess(argv, 0, "1 passed\n", "")

    with patch("rush.tools.coverage.engine_on_path", side_effect=lambda name: name == "coverage"), patch(
        "rush.tools.coverage.run_subprocess", side_effect=child
    ):
        result = CoverageTool().run(
            tmp_path,
            permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
        )
    assert calls, "fixture must reach current executed branch"
    assert result["status"] == "error", result
```

Observed 2026-10-01 on source: `status='ok'`, metrics absent/None, one argv `['coverage','run','-m','pytest',<root>]`. Thus exact last assertion fails, not a future-keyword `TypeError`. This launcher double proves controller defect only. After resolver change adapt its availability patch to verified resolved fixture binary and emit valid version/JUnit as needed so missing fresh JSON remains asserted cause; do not weaken assertion to a status membership check.

### GREEN and actual engine acceptance

Replace executed branch in one place with `run_measured_coverage(path, permissions=permissions, test_paths=test_paths)` and defined behavior above; move diff dispatch behind explicit measurement. `run_measured_coverage` owns validation→grant→resolve→identity snapshot→private directory→run→JUnit validate→export→parse→identity recheck→canonical result. Each error attaches completed step results; no exception or raw runner stdout escapes to MCP stdout. Fixture below runs genuine installed coverage.py/pytest; explicit prerequisite is coverage.py major 7 in Rush's trusted environment, no installing by test.

```python
def test_live_partial_coverage_counts(tmp_path: Path):
    from rush.runtime.binaries import resolve_binary

    assert resolve_binary("coverage", project_root=tmp_path), "prerequisite: installed coverage.py 7"
    (tmp_path / "rush.toml").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/a.py").write_text(
        "def classify(x):\n    if x:\n        return 'yes'\n    return 'no'\n"
    )
    (tmp_path / "tests/test_a.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from src.a import classify\ndef test_yes():\n    assert classify(1) == 'yes'\n"
    )
    result = CoverageTool().run(
        tmp_path, permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True)
    )
    assert result["status"] == "warn", result
    assert {k: result["metrics"][k] for k in ("covered_lines", "total_lines", "line_percent")} == {
        "covered_lines": 3, "total_lines": 4, "line_percent": 75.0
    }
    assert result["metadata"]["missing_lines"] == {"src/a.py": [4]}
    assert result["metadata"]["evidence_source"] == "executed-runner"
    assert result["metrics"]["executed_tests"] == 1
    assert not (tmp_path / ".coverage").exists()
```

### Constraints

Do not report reference fixture passed during planning. A launcher-written JSON fixture validates parsing/controller only. Genuine run above is separate mandatory acceptance. No engine install or download as test setup. No prerequisite satisfied by skipped test.

### Checks to run before reporting

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_coverage.py::test_missing_fresh_report_not_ok tests/test_coverage.py::test_live_partial_coverage_counts tests/test_coverage_importer.py tests/test_undercover_reference.py -q
```

### Completion

Measured 3/4/75.0 fixture passes real runner, missing export fails, imports preserved, grants denial writes/spawns nothing. Refactor only after RED→GREEN; retain command-local helpers and existing runtime.

## C2 — Shared routing, changed-line evidence and transports

### Required behavior

Publish interface above through explicit catalog options and signature. Changed-line evidence requires current executed line measurement, `base_ref` resolved by `git rev-parse --verify --end-of-options <ref>^{commit}`; reject option-leading refs/control characters and nonzero/truncated output. Run `git diff --name-only -z --no-renames <commit> -- .` then per contained filename `git diff --no-ext-diff --no-textconv --no-renames --unified=0 <commit> -- <name>`. NUL path records avoid quoted-name mistakes. Parse only hunk headers `@@ -old[,n] +new[,n] @@`; absent count=1, zero=0. Add untracked source files as all added lines only after explicit inventory with `git ls-files --others --exclude-standard -z -- .`; metadata states untracked inclusion. Deletions contribute zero new lines. Intersect changed added-line set with measured `missing_lines`; output sorted `uncovered_changed_lines=['src/a.py:4']`, `base_commit`, source/report digests. Invalid base, changed source/config/report between measurement and diff, non-UTF8 path, binary patch or incomplete Git output gives canonical error; never stale evidence.

### Deliverables

Command owner: `tools/coverage.py::{changed_uncovered_lines,attach_changed_line_evidence}`, `tests/test_coverage.py` C2 cases, `tests/test_coverage_transport.py`. Batch integration owner: exact coverage entry in `_TOOL_CLI_OPTIONS`; matching `ToolOptionSpec`, truthful catalog description/maturity after real acceptance, existing wrapper root-relative rules; `docs/CONFIGURATION.md` and `examples/rush.toml` ordinary options only; two coverage cases in CLI semantic fixture for imported and executed operation; existing schema tests retain 79 tool count. Runtime pins cannot be selected by repository configuration.

### RED/GREEN and regression

First feature-absence test is distinct from C1: current `CoverageTool.run(...,base_ref='HEAD')` raises TypeError because feature absent. After C2 implementation, create temporary Git repository (local only) with committed four-line fixture, append/change uncovered return line, execute real C1 runner, assert exact uncovered changed line `src/a.py:4`; edit bytes after result and call `attach_changed_line_evidence` directly, assert `ValueError('source_digest_drift:src/a.py')`. Function takes `(root:Path,result:ToolResult,base_ref:str)->ToolResult`, validates report digest then source/config hashes then Git and returns copied metadata; orchestration converts exceptions to canonical errors. No helper reads stale report without hash check.

Complete new-feature test in `tests/test_coverage.py`, using imports from C1. Requires installed coverage.py7 and local Git; no remote, hook or commit in Rush repository (only disposable fixture):

```python
def test_changed_line_source_digest_guard(tmp_path: Path):
    import subprocess
    from rush.tools.coverage import attach_changed_line_evidence

    (tmp_path / "rush.toml").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    source = tmp_path / "src/a.py"
    source.write_text("def classify(x):\n    if x:\n        return 'yes'\n    return 'old'\n")
    (tmp_path / "tests/test_a.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from src.a import classify\ndef test_yes():\n    assert classify(1) == 'yes'\n"
    )
    for argv in (["git", "init"], ["git", "add", "rush.toml", "src", "tests"],
                 ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "-c", "commit.gpgsign=false", "commit", "-m", "fixture"]):
        subprocess.run(argv, cwd=tmp_path, check=True, capture_output=True)
    source.write_text("def classify(x):\n    if x:\n        return 'yes'\n    return 'no'\n")
    result = CoverageTool().run(tmp_path, base_ref="HEAD",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True))
    assert result["status"] == "warn", result
    assert result["metadata"]["uncovered_changed_lines"] == ["src/a.py:4"]
    source.write_text(source.read_text().replace("'no'", "'changed'"))
    try:
        attach_changed_line_evidence(tmp_path, result, "HEAD")
    except ValueError as exc:
        assert str(exc) == "source_digest_drift:src/a.py"
    else:
        raise AssertionError("stale changed-line evidence accepted")
```

Transport module below is complete executable import/denial path. It uses actual CLI subprocess and initialized MCP stdio session, reaching real shared tool. It also checks actual serialized protocol via SDK; a non-JSON stdout line breaks the client, and stderr capture stays separate. Add live fixture case using C1 project and same `rpc` helper with execution grants; exact projection must be `('warn',3,4,75.0,'executed-runner')`, never timing/path equality. Current imports are preservation; execution fields become feature-absence RED until C2 lands.

```python
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def cli(root, args):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-m", "rush.cli", *args, "--json"],
        cwd=root, env=env, capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, json.loads(proc.stdout), proc.stderr


async def rpc(root, arguments, log):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "rush.cli", "mcp", "serve"],
        cwd=str(root), env=env,
    )
    with log.open("w+") as errors:
        async with stdio_client(params, errlog=errors) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listed = await session.list_tools()
                schema = next(t.inputSchema for t in listed.tools if t.name == "rush_coverage")
                assert schema["type"] == "object"
                assert schema["additionalProperties"] is False
                assert not {"oneOf", "anyOf", "allOf"} & schema.keys()
                reply = await session.call_tool("rush_coverage", arguments)
                assert not reply.isError
                return json.loads(next(c.text for c in reply.content if c.type == "text"))


def test_cli_stdio_import_and_denial(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "coverage.json").write_text(json.dumps({"totals": {"percent_covered": 75.0}}))
    (root / "a.py").write_text("x = 1\n")
    code, left, _ = cli(root, ["coverage", ".", "--report-path", "coverage.json"])
    right = asyncio.run(rpc(root, {"path": ".", "report_path": "coverage.json"}, tmp_path / "mcp.log"))
    def project(result):
        return result["status"], result["metrics"], result["metadata"]["evidence_source"]
    assert code == 1
    assert project(left) == project(right) == (
        "warn", {"line_percent": 75.0}, "imported-local-report"
    )
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    code, left, _ = cli(root, ["coverage", "."])
    right = asyncio.run(rpc(root, {"path": "."}, tmp_path / "denied.log"))
    assert (code, left["status"], right["status"]) == (0, "skipped", "skipped")
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before
    assert not (root / ".rush").exists()
```

Denial zero-spawn proof is additional controlled executable with append-only marker placed in trusted external PATH, and spies on version/runner in unit test; no marker after CLI/MCP denial. Real import transport above uses no engine mock. Environment prerequisite: project installed editable in tested uv environment, same `sys.executable` imports current checkout. Add nested project/report test with foreign server cwd and explicit registered `project`: report anchor follows documented secondary-operand rule, `test_paths` always project relative; exact target/source digest matches direct run. Do not let absolute `/var` alias spelling invalidate transparent ancestor semantics.

Complete granted/denied engine-fixture transport case in same `tests/test_coverage_transport.py`. `monkeypatch` changes test process environment only; subprocesses inherit it. Trusted test environment must have no runtime-bin `coverage` executable taking precedence over fixture PATH; assert marker/count so an unexpected real executable fails fixture rather than yielding false transport proof. Real-engine C1 acceptance remains separate.

```python
def test_cli_stdio_executed_counts_and_zero_effect_denial(tmp_path: Path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src/a.py").write_text("def f(x):\n    if x:\n        return 1\n    return 0\n")
    (root / "tests/test_a.py").write_text("def test_yes():\n    assert True\n")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    log = tmp_path / "engine.log"
    engine = binary_dir / "coverage"
    engine.write_text("#!" + sys.executable + "\n" + r'''
import json, os, pathlib, sys
a = sys.argv[1:]
with open(os.environ["RUSH_ENGINE_LOG"], "a") as log:
    log.write(json.dumps(a) + "\n")
if a == ["--version"]:
    print("Coverage.py, version 7.16.1 with C extension")
elif a == ["json", "--help"]:
    print("coverage json --rcfile=RCFILE -o OUTFILE")
elif a == ["run", "--help"]:
    print("coverage run --rcfile=RCFILE --branch --source=SOURCE")
elif a and a[0] == "run":
    junit = next(x.split("=", 1)[1] for x in a if x.startswith("--junitxml="))
    pathlib.Path(junit).write_text('<testsuites><testsuite><testcase name="test_yes"/></testsuite></testsuites>')
    pathlib.Path(os.environ["COVERAGE_FILE"]).write_bytes(b"fixture measurement")
elif a and a[0] == "json":
    pathlib.Path(a[a.index("-o") + 1]).write_text(json.dumps({
        "meta": {"version": "7.16.1", "branch_coverage": True},
        "totals": {"covered_lines": 3, "num_statements": 4, "percent_covered": 75.0},
        "files": {"src/a.py": {"executed_lines": [1,2,3], "missing_lines": [4],
                               "executed_branches": [[2,3]], "missing_branches": [[2,4]]}}
    }))
else:
    sys.exit(2)
''')
    engine.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("RUSH_ENGINE_LOG", str(log))
    code, denied, _ = cli(root, ["coverage", "."])
    denied_rpc = asyncio.run(rpc(root, {"path": "."}, tmp_path / "deny.log"))
    assert (code, denied["status"], denied_rpc["status"]) == (0, "skipped", "skipped")
    assert not log.exists()
    assert not (root / ".rush").exists()
    grants = ["--allow-build", "--allow-slow", "--allow-artifact-write"]
    code, left, _ = cli(root, ["coverage", ".", *grants])
    right = asyncio.run(rpc(root, {"path": ".", "allow_build": True,
        "allow_slow": True, "allow_artifact_write": True}, tmp_path / "allow.log"))
    def projection(result):
        m = result["metrics"]
        return result["status"], m["covered_lines"], m["total_lines"], m["line_percent"], result["metadata"]["missing_lines"]
    assert code == 1
    assert projection(left) == projection(right) == ("warn", 3, 4, 75.0, {"src/a.py": [4]})
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert sum(a[0] == "run" and "--help" not in a for a in calls) == 2
    assert sum(a[0] == "json" and "--help" not in a for a in calls) == 2
```

### Constraints

Keep shared full/compact delivery, T16 precedence `error>fail>warn>skipped>ok`, mixed assessed/skipped=`warn`; scope unavailable has reason until real file instrumentation available. Preserve original target strings separately from normalized paths. No broad invocation refactor. No new CLI/MCP registration or command count change.

### Checks to run before reporting

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_coverage.py tests/test_coverage_transport.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase60_characterization.py tests/test_phase70_result_trust.py -q
```

### Completion

CLI and initialized stdio execute same shared tool and produce exact counts/findings/status; schemas carry every new optional field; denied and compact-denied calls have zero children and filesystem changes; source drift prevents changed-line claims.

## C3 — Gap-trial proposal with complete prerequisites

### Required behavior

New agent-side operation accepts one missing `path:line` or `path:start->end`. Fresh baseline with branch collection must show that exact target uncovered. A connected local specialist proposes one assertion-bearing test; isolated execution must pass, hit target and fail when target outcome is deliberately contradicted. Return candidate and measured proof; never automatically modify source/tests. This extends agent perception→candidate→execution→feedback. Commodity percentage reporting alone does not provide this closure. It is a proposal assessed here, not claimed prior user approval.

User baseline connectivity is implemented by command-local `invoke_gap_specialist(root,prompt,runtime)->str`, not by inventing `OfflineReviewTool._invoke_local_model`. `runtime` is validated dict with exactly `runtime_path`, `model_path`, `model_sha256`, `model_image_ref`, `coverage_image_ref`, `timeout_seconds`. Model path is contained regular file, sha256 must match explicit 64 lowercase hex input. Images must match `name@sha256:<64 lowercase hex>`. Runtime absolute binary is approved user operand. A grant to test does not grant remote model egress: this route is local/offline only; network backend not silently substituted.

Model prompt schema: `{schema_version:1,target,source_sha256,source,existing_tests,request}`. Target source max65,536 UTF-8 bytes; existing selected tests total max65,536 bytes, no environment/secrets. Prompt says return one JSON object `{schema_version:1,test_source:string}` with exactly one top-level `test_*` function and no markdown. Copy contained approved model and only prompt/source fixtures into private model stage; no `.env`, `.git`, `.venv`, `.rush` copy except explicitly selected model bytes. Model file must be≤4GiB, hash-match explicit pin, and actual acceptance must fit profile; size alone does not prove runtime memory use. Store prompt at `/out/prompt.txt`, run pinned image entrypoint `/usr/local/bin/llama-cli` with `resource_profile='analysis'` and argv `['-m','/work/model.gguf','-f','/out/prompt.txt','--single-turn','--no-display-prompt','--color','off','--no-show-timings','--temp','0','--seed','0','-c','4096','-n','2048','-t','2','--cache-ram','0','--json-schema',schema_json]`. `schema_json` is `json.dumps({'type':'object','properties':{'schema_version':{'const':1},'test_source':{'type':'string'}},'required':['schema_version','test_source'],'additionalProperties':False})`. [Official llama.cpp CLI reference](https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md) documents model/file input, context/output/thread limits, single-turn and JSON schema controls. Pinned image preflight `--help` must expose each flag; unsupported flags produce inconclusive `model_runtime_incompatible`, no fallback to unbounded invocation. Oversized context/nonzero/truncation/non-JSON/schema mismatch gives trial inconclusive with exact reason; never silently trim source to make prompt fit. Capture stdout max256KiB. Validate strict integer version (not bool), no unknown keys, one top-level test and at least one nonconstant `ast.Assert` within it; max test source64KiB. AST parsing is syntax validation, never security sandbox or proof assertion executed.

## P0 — shared offline isolation prerequisite

Implement owned OCI subprocess execution in rush-cli in future implementation worktree. Read source AGENTS.md, Phase 70 T8/T10/T16 and this contract first.

# Feature: own and confine offline child execution

## Required behavior

New src/rush/runtime/isolated_process.py defines IsolationUnavailable(RuntimeError), IsolationCleanupError(RuntimeError) and:
~~~text
def run_isolated_argv(root: Path, scratch: Path, *, runtime_path: Path,
                      image_ref: str, entrypoint: str, argv: list[str],
                      timeout_s: float, workdir_rel: str = ".",
                      environment: dict[str, str] | None = None,
                      resource_profile: Literal["standard", "analysis"] = "standard"
                      ) -> subprocess.CompletedProcess[str]:
~~~
This is a fully specified proposed interface; absence initially proves missing interface only. Complete implementation algorithm:

1. Caller invokes existing check_permissions(required, granted) BEFORE scratch creation, runtime lookup or version probes. Caller creates fresh tempfile.TemporaryDirectory, chmod 0700, owns final deletion. Provider grants nothing. POSIX only; Windows unavailable. Runtime is explicitly approved absolute executable file; image matches name@sha256:64-lowercase-hex. Validate finite 0<timeout_s<=600; argv NUL-free string list; fixed absolute entrypoint selected by command, never model text. Reject source/scratch symlink/reparse components before resolve; source and scratch must not overlap in either direction; scratch owner is current UID, no group/other mode bits. Reject NUL/comma/CR/LF in mount paths. PhysicalRoot(root).open_contained(workdir_rel) must be directory. Only SOURCE_DATE_EPOCH/TZ/LC_ALL string environment overrides, no control characters.
2. Existing run_subprocess([runtime,"image","inspect",image_ref],timeout=10,env={"PATH":"/usr/bin:/bin"}) must yield exactly one matching locally present RepoDigest and approved native OS/architecture. Missing runtime/image/daemon => IsolationUnavailable before execution, no pulls/installs. Runtime capability tested with actual denial fixture below.
3. Generate uuid4 hex identity and name rush-<identity>. Exact argv: [runtime,"create","--name",name,"--label","io.rush.invocation="+identity,"--pull=never","--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges","--pids-limit=64","--memory=512m","--cpus=1","--user",f"{os.getuid()}:{os.getgid()}","--mount",f"type=bind,src={root},dst=/work,readonly","--mount",f"type=bind,src={scratch},dst=/out","--tmpfs","/tmp:rw,nosuid,nodev,size=64m","--workdir",contained_workdir,"--env","PATH=/usr/local/bin:/usr/bin:/bin","--env","HOME=/out","--env","PYTHONDONTWRITEBYTECODE=1","--env","RUSH_CHECK_RECEIPT=/out/checks.json",*sorted_allowed_env_pairs,"--entrypoint",entrypoint,image_ref,*argv]. No HOME/socket/credential mounts. Create stdout must be 64-hex container ID.
4. Start [runtime,"start","--attach",name] with remaining timeout, then inspect container. Matching ID/label, State.Running false, StartedAt nonzero and integer State.ExitCode required. Return CompletedProcess(create_argv,actual_exit,attached.stdout,attached.stderr). The create/start/inspect split distinguishes real target exit125/126/127 from launcher failures, correcting audit run/125 ambiguity.
5. Finally inspect label/ID, rm --force only owned name, inspect known absence on success/error/timeout/cancellation, including create timeout that may already have created container. Cleanup calls use cancel_check=lambda:False so ambient cancellation cannot prevent reaping; timeout10. Existing run_subprocess inherits ambient owner_instance_id/run_id and cancellation, preserving current durable client ownership. Label mismatch, unreachable daemon or remaining container => IsolationCleanupError, never success. Re-raise original timeout/SubprocessCancelled only after confirmed cleanup. Record owned container name in sanitized error metadata for explicit recovery. No host-power-loss cleanup guarantee.

Mapping: unavailable => skipped plus metadata.reason=isolation_unavailable; cleanup failure => error plus terminal_reason=isolation_cleanup_failed. Provider preserves actual target exit; consumer applies exact domain exit/report consistency (valid finding exit1 is not universally error); unexpected exits error. Timeout/cancel retain exact existing reasons. Combined scanner+unavailable trial retains scanner evidence but incomplete/warn unless fail/error already wins. PatchSandboxManager is Git staging, not isolation; NetworkEgressGuard is interpreter-local monkeypatch, not confinement.

## Deliverables

Batch integration owner owns new src/rush/runtime/isolated_process.py and new tests/test_isolated_process.py. Existing PhysicalRoot, run_subprocess, check_permissions and owned scopes reused without modification. P0 ordered before every consuming isolated expansion: Q11–Q16 and Q18–Q20; cross-reference does not replace this embedded contract.

Proposed tests in tests/test_isolated_process.py: test_missing_image_never_creates_container patches only provider run_subprocess with CompletedProcess(argv,1,"","No such image"); asserts sole call image inspect and IsolationUnavailable. test_closed_mounts_and_environment verifies exact create argv above. test_target_exit_125 supplies valid create/start/inspect lifecycle and asserts returned125. test_timeout_and_cancel_reap verifies cleanup despite ambient cancellation and unrelated container untouched.

Runnable genuine-runtime acceptance; only selected when explicit preinstalled approved runtime/image supplied. Missing environment is failure prerequisite, never successful isolation:
~~~python
def test_real_oci_denials(tmp_path):
    import json, os, subprocess, tempfile
    from pathlib import Path
    from rush.runtime.isolated_process import run_isolated_argv
    runtime = Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image = os.environ["RUSH_TEST_OCI_IMAGE"]
    root = tmp_path / "source"
    root.mkdir()
    (root / "keep").write_bytes(b"unchanged")
    home_secret = tmp_path / "host-only-secret"
    home_secret.write_bytes(b"host-canary")
    probe = (
        "import json,socket,pathlib; out={}\n"
        "try: pathlib.Path('/work/blocked').write_text('x'); out['source_write']=True\n"
        "except OSError: out['source_write']=False\n"
        "try: s=socket.create_connection(('1.1.1.1',80),timeout=1); s.close(); out['network']=True\n"
        "except OSError: out['network']=False\n"
        "try: pathlib.Path(" + repr(str(home_secret)) + ").read_bytes(); out['host_read']=True\n"
        "except OSError: out['host_read']=False\n"
        "pathlib.Path('/out/allowed').write_text('ok')\n"
        "print(json.dumps(out))\n"
    )
    with tempfile.TemporaryDirectory(prefix="rush-denial-") as folder:
        scratch = Path(folder)
        scratch.chmod(0o700)
        result = run_isolated_argv(root, scratch, runtime_path=runtime,
            image_ref=image, entrypoint="/usr/local/bin/python",
            argv=["-c", probe], timeout_s=15)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "source_write": False, "network": False, "host_read": False}
        assert (scratch / "allowed").read_text() == "ok"
        name = result.args[result.args.index("--name") + 1]
        check = subprocess.run([str(runtime), "container", "inspect", name],
            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=10)
        assert check.returncode != 0
    assert [p.name for p in root.iterdir()] == ["keep"]
    assert (root / "keep").read_bytes() == b"unchanged"
    assert home_secret.read_bytes() == b"host-canary"
~~~
Add actual infinite-sleep timeout and cancellation variants with same post-cleanup inspect. Image must contain fixed /usr/local/bin/python; approved command images additionally contain their named executables. Mocked launcher cannot satisfy this test.

## Constraints

No network/pull/install, unowned deletion, real credentials, source writes or simulated isolation receipts. Keep hard memory/CPU/PID/tmp limits and current UID/GID. Inspect local image/runtime capability; version banners alone prove no confinement.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_isolated_process.py -q

## Completion

Exact runtime denials, allowed /out write and cleanup pass with actual local runtime; only two P0 files changed. Missing approved image/runtime blocks runtime acceptance, not beginning scanner repairs.

### P0 fixed resource profiles

The function signature additionally accepts resource_profile: Literal["standard","analysis"]="standard"; import Literal from typing. Validate exact enum before any runtime call (other strings, None/bools invalid). Standard maps to --memory=512m --cpus=1 --pids-limit=64. Analysis maps to --memory=8g --cpus=2 --pids-limit=256. No arbitrary user limits. Replace the three literal standard flags in create argv with values from this fixed mapping; every other flag/environment/mount/cleanup invariant unchanged.

Q15/Q16/Q18 and Q11–Q14 use standard. Q20 CodeQL uses analysis with --ram=6144 --threads=2; Q19 local-model process uses analysis with GGUF≤4GiB/context4096/output2048. CodeQL primary evidence: https://docs.github.com/en/code-security/reference/code-scanning/codeql/hardware-resources-for-codeql — small repositories recommend8GB/2cores; 512MiB cannot satisfy promised real analysis. Host insufficient resources => unavailable before target, never reduce guarantees.

Proposed complete flag test in tests/test_isolated_process.py:
~~~python
def test_resource_profiles_reach_real_argv(tmp_path):
    import json, os, subprocess
    from pathlib import Path
    from unittest.mock import patch
    from rush.runtime import isolated_process as provider
    runtime=Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image=os.environ["RUSH_TEST_OCI_IMAGE"]
    root=tmp_path/"root"; root.mkdir()
    for profile,memory,cpu,pids in (("standard","512m","1","64"),
                                    ("analysis","8g","2","256")):
        scratch=tmp_path/profile; scratch.mkdir(mode=0o700)
        real=provider.run_subprocess
        calls=[]
        def observe(argv,**kwargs):
            calls.append(list(argv))
            return real(argv,**kwargs)
        with patch.object(provider,"run_subprocess",side_effect=observe):
            result=provider.run_isolated_argv(root,scratch,runtime_path=runtime,
                image_ref=image,entrypoint="/usr/local/bin/python",
                argv=["-c","print('ready')"],timeout_s=15,resource_profile=profile)
        assert result.returncode==0
        created=[a for a in calls if len(a)>1 and a[1]=="create"]
        assert len(created)==1
        assert "--memory="+memory in created[0]
        assert "--cpus="+cpu in created[0]
        assert "--pids-limit="+pids in created[0]
        assert "--network=none" in created[0] and "--read-only" in created[0]
    with patch.object(provider,"run_subprocess") as execute:
        try:
            provider.run_isolated_argv(root,tmp_path/"standard",runtime_path=runtime,
                image_ref=image,entrypoint="/usr/local/bin/python",argv=["-c","pass"],
                timeout_s=1,resource_profile="unlimited")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown resource profile accepted")
        execute.assert_not_called()
~~~

### P0 executable lifecycle acceptance bodies

Append these complete bodies to proposed tests/test_isolated_process.py. Interface absence is expected initial failure; no current isolation claim.

~~~python
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

def test_missing_image_never_creates_container(tmp_path):
    from rush.runtime.isolated_process import run_isolated_argv, IsolationUnavailable
    root=tmp_path/"root"; root.mkdir()
    scratch=tmp_path/"scratch"; scratch.mkdir(mode=0o700)
    runtime=tmp_path/"docker"; runtime.write_text("#!/bin/sh\nexit 0\n"); runtime.chmod(0o700)
    image="fixture@sha256:"+"0"*64
    calls=[]
    def missing(argv,**kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv,1,"","No such image")
    with patch("rush.runtime.isolated_process.run_subprocess",side_effect=missing):
        try:
            run_isolated_argv(root,scratch,runtime_path=runtime,image_ref=image,
                entrypoint="/usr/local/bin/python",argv=["-c","pass"],timeout_s=1)
        except IsolationUnavailable:
            pass
        else:
            raise AssertionError("missing image launched")
    assert calls==[[str(runtime),"image","inspect",image]]
    assert list(scratch.iterdir())==[]

def test_real_timeout_and_cancel_reap(tmp_path):
    from rush.runtime import isolated_process as provider
    from rush.runtime.subprocesses import cancel_scope, SubprocessCancelled
    runtime=Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image=os.environ["RUSH_TEST_OCI_IMAGE"]
    root=tmp_path/"root"; root.mkdir()
    (root/"keep").write_bytes(b"unchanged")
    for mode in ("timeout","cancel"):
        calls=[]
        real=provider.run_subprocess
        def observed(argv,**kwargs):
            calls.append(list(argv))
            return real(argv,**kwargs)
        with tempfile.TemporaryDirectory(prefix="rush-reap-") as folder:
            scratch=Path(folder); scratch.chmod(0o700)
            code="import pathlib,time; pathlib.Path('/out/started').write_text('yes'); time.sleep(60)"
            with patch.object(provider,"run_subprocess",side_effect=observed):
                try:
                    with cancel_scope((lambda:(scratch/"started").exists()) if mode=="cancel" else None):
                        provider.run_isolated_argv(root,scratch,runtime_path=runtime,
                            image_ref=image,entrypoint="/usr/local/bin/python",
                            argv=["-c",code],timeout_s=10)
                except subprocess.TimeoutExpired:
                    assert mode=="timeout"
                except SubprocessCancelled:
                    assert mode=="cancel"
                else:
                    raise AssertionError("sleeping child completed")
            assert (scratch/"started").read_text()=="yes"
            created=[a for a in calls if len(a)>1 and a[1]=="create"]
            assert len(created)==1
            name=created[0][created[0].index("--name")+1]
            assert [str(runtime),"rm","--force",name] in calls
            remaining=subprocess.run([str(runtime),"container","inspect",name],
                env={"PATH":"/usr/bin:/bin"},capture_output=True,text=True,timeout=10)
            assert remaining.returncode!=0
    assert (root/"keep").read_bytes()==b"unchanged"
    assert [p.name for p in root.iterdir()]==["keep"]
~~~

### Deliverables and exact trial algorithm

Only `src/rush/tools/coverage.py::{invoke_gap_specialist,parse_gap_test_response,run_gap_candidate_isolated,trial_gap_candidate}` and `tests/test_coverage.py` C3 tests; shared P0 files owned above; C2 owns flag/metadata integration. Reuse current result helpers and `run_subprocess`; no new generic model framework.

Candidate stage is a private copy of regular source/tests/config excluding secrets/cache/VCS/venv, symlinks rejected before copy; candidate written to `tests/test_rush_gap_candidate.py` only in stage, fail if that path already exists. Source scope and report coordinates normalize `/work/` to original root-relative names. Runtime image must already include Python 3.12, coverage.py 7, pytest and project dependencies; absence is inconclusive `test_environment_unavailable`, no pip/uv install.

Run pinned coverage image, fixed entrypoint `/usr/local/bin/python`, argv `['-c',GAP_DRIVER,'/work/tests/test_rush_gap_candidate.py::<name>', '/work/src']`; last argument is `/work` only when baseline selected whole-root source scope. Literal production constant follows. Driver records exact node through real pytest, exports branch JSON/JUnit/test exit under `/out`, and returns zero only after all exports complete. Parse real pytest return independently from driver return. Exactly one executed testcase, no skips/errors, target file must appear in `executed_lines` or `executed_branches`; target merely absent from `missing_*` is insufficient. Recheck all original source/config/model hashes after model and after execution. Test candidate twice in separate scratch; both pass and hit target.

```python
GAP_DRIVER = r'''
import json
import pathlib
import sys

import coverage
import pytest

sys.path.insert(0, "/work")
sys.path.insert(0, "/work/src")
node, source = sys.argv[1:]
cov = coverage.Coverage(
    data_file="/out/.coverage", branch=True, source=[source], config_file=False,
    omit=["*/tests/*", "*/.rush/*", "*/.venv/*"],
)
cov.start()
try:
    test_exit = int(pytest.main([
        node, "-q", "-o", "addopts=", "-p", "no:cacheprovider", "--junitxml=/out/tests.xml",
    ]))
finally:
    cov.stop()
cov.save()
cov.json_report(outfile="/out/coverage.json")
out = pathlib.Path("/out")
if not (out / "tests.xml").is_file():
    raise RuntimeError("candidate_junit_missing")
temporary = out / "test-exit.json.tmp"
temporary.write_text(json.dumps({"exit": test_exit}), encoding="utf-8")
temporary.replace(out / "test-exit.json")
'''
```

`run_gap_candidate_isolated` calls `run_isolated_argv(stage,output,runtime_path=Path(runtime['runtime_path']),image_ref=runtime['coverage_image_ref'],entrypoint='/usr/local/bin/python',argv=['-c',GAP_DRIVER,node,source],timeout_s=remaining_seconds,resource_profile='standard')`. `remaining_seconds` is monotonic total trial deadline minus now, validated positive and capped600; model and all three candidate/control runs share one deadline. Read reports only after provider cleanup succeeded. Partial export/nonzero driver exit produces inconclusive, never a passing candidate.

Assertion sensitivity: instrument candidate AST by replacing each `assert test, message` with `assert not (test), message` while preserving locations, execute altered candidate in another isolated stage. Require assertion failure recorded in JUnit and no collection/runtime error; an unexecuted assert, unconditional pass, `assert True`, or swallowed assertion cannot validate behavior. Reject literal-constant asserts during AST validation. This control proves assertion is evaluated and discriminates opposite condition; it does not prove domain oracle correctness. Return `oracle='specialist-proposed'`, retain candidate for human review; do not label it verified semantic correctness.

Statuses in `metadata.gap_trial`: `verified_candidate` only real exact transition plus two passes plus sensitivity failure; `rejected` on test failure/no hit/no assertion sensitivity; `inconclusive` on engine/isolation/model/identity infrastructure failure. Baseline top-level status remains at least `warn` for rejected/inconclusive trial; never erase baseline test failures. Record target, candidate SHA, model SHA/image digest, test node, before/after missing+executed coordinates, baseline/candidate report digests, each attempt phases/exits and oracle limitation. Artifact is candidate source under owned run, not installed test. Preserve baseline findings and counts unchanged; trial measurements are nested evidence.

Worked case: source `classify(x)` above, baseline `classify(1)` leaves line4 / arc2→4 missing. Specialist proposes `assert classify(0)=='no'`. Two isolated candidate runs hit line4/arc2→4 and pass; inverted assertion fails; result `gap_trial.status='verified_candidate'`, source tree unchanged. A test only importing module does not hit target and is rejected; a passing test on another line is rejected even if total percentage rises.

### RED, GREEN, regression and checks

Feature absence is expected until C3 exists. Add `test_gap_trial_requires_exact_branch_transition`: use real C1 fixture and deterministic model response at only `invoke_gap_specialist` boundary, but genuine OCI coverage execution for candidate and sensitivity. Assert exact target2→4 in candidate executed arcs, 2 pass attempts, 1 expected assertion-failure control, candidate hash and no original `tests/test_rush_gap_candidate.py`. Separate `test_gap_specialist_real_runtime` executes actual pinned llama-cli/model, asserts parseable one-test output and genuine target transition; model failure cannot be renamed engine success. Pins are supplied by test environment `RUSH_COVERAGE_TEST_RUNTIME`, `RUSH_COVERAGE_TEST_IMAGE`, `RUSH_COVERAGE_TEST_MODEL_IMAGE`, `RUSH_COVERAGE_TEST_MODEL`, `RUSH_COVERAGE_TEST_MODEL_SHA256`; assert variables exist, never `pytest.skip` in acceptance run. Model file copied to contained fixture `.rush/models/model.gguf` only after explicit test setup grant.

`test_gap_trial_rejects_no_target_hit` uses `assert classify(1)=='yes'`; exact state rejected. `test_gap_trial_rejects_unexecuted_assertion` places assert after unconditional return; exact rejected. `test_gap_trial_source_digest_drift` mutates source between baseline/model and requires inconclusive without candidate start. `test_gap_trial_runtime_denial` omits artifact grant and asserts zero model/OCI calls and zero `.rush` writes. `test_gap_trial_cleanup_failure` raises `IsolationCleanupError` and requires top-level error with reason `isolation_cleanup_failed`, retained cleanup evidence. Fully qualified check names below are proposed tests, not existing passes.

Complete C3 runtime test bodies, in `tests/test_coverage.py`; real fixture and provider must exist first. Initial missing keyword/helper failure is feature absence, not C1 bug reproduction. Imports from C1 apply; all further imports/helpers defined here:

```python
def gap_project(tmp_path):
    import os
    import shutil

    required = ("RUSH_COVERAGE_TEST_RUNTIME", "RUSH_COVERAGE_TEST_IMAGE",
        "RUSH_COVERAGE_TEST_MODEL_IMAGE", "RUSH_COVERAGE_TEST_MODEL", "RUSH_COVERAGE_TEST_MODEL_SHA256")
    for key in required:
        assert os.environ.get(key), "required acceptance asset: " + key
    root = tmp_path / "project"
    root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / ".rush/models").mkdir(parents=True)
    (root / "src/a.py").write_text("def classify(x):\n    if x:\n        return 'yes'\n    return 'no'\n")
    (root / "tests/test_a.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from src.a import classify\ndef test_yes():\n    assert classify(1) == 'yes'\n")
    shutil.copyfile(os.environ["RUSH_COVERAGE_TEST_MODEL"], root / ".rush/models/model.gguf")
    args = dict(trial_gap_test="src/a.py:2->4", local_runtime_path=os.environ[required[0]],
        coverage_image_ref=os.environ[required[1]], local_model_image_ref=os.environ[required[2]],
        local_model_path=".rush/models/model.gguf", local_model_sha256=os.environ[required[4]],
        trial_timeout_seconds=600,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True))
    return root, args


def assert_real_gap_transition(root, result):
    assert result["status"] == "warn", result
    trial = result["metadata"]["gap_trial"]
    assert trial["status"] == "verified_candidate", trial
    assert trial["target"] == "src/a.py:2->4"
    assert trial["before"]["missing_branches"] == [[2, 4]]
    assert [2, 4] in trial["after"]["executed_branches"]
    assert [p["kind"] for p in trial["attempts"]] == ["candidate", "candidate", "assertion_control"]
    assert [p["test_exit"] for p in trial["attempts"]] == [0, 0, 1]
    assert not (root / "tests/test_rush_gap_candidate.py").exists()


def test_gap_trial_requires_exact_branch_transition(tmp_path: Path):
    import json

    root, args = gap_project(tmp_path)
    original = (root / "src/a.py").read_bytes()
    candidate = json.dumps({"schema_version": 1,
        "test_source": "from src.a import classify\ndef test_zero():\n    assert classify(0) == 'no'\n"})
    with patch("rush.tools.coverage.invoke_gap_specialist", return_value=candidate):
        result = CoverageTool().run(root, **args)
    assert_real_gap_transition(root, result)
    assert (root / "src/a.py").read_bytes() == original


def test_gap_specialist_real_runtime(tmp_path: Path):
    root, args = gap_project(tmp_path)
    result = CoverageTool().run(root, **args)
    assert_real_gap_transition(root, result)
    assert result["metadata"]["gap_trial"]["model_sha256"] == args["local_model_sha256"]
```

The nested trial schema is fixed by these assertions: `before.missing_branches`, `after.executed_branches`, and `attempts` list with `kind` and `test_exit`; add matching line fields for line targets. Baseline counts are not overwritten. Actual local model generation may fail acceptance; do not substitute deterministic candidate for that separate test.

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_isolated_process.py tests/test_coverage.py::test_gap_trial_requires_exact_branch_transition tests/test_coverage.py::test_gap_specialist_real_runtime tests/test_coverage.py::test_gap_trial_rejects_no_target_hit tests/test_coverage.py::test_gap_trial_rejects_unexecuted_assertion tests/test_coverage.py::test_gap_trial_source_digest_drift tests/test_coverage.py::test_gap_trial_runtime_denial tests/test_coverage.py::test_gap_trial_cleanup_failure -q
```

### Completion

Both genuine isolated candidate execution and actual local model invocation must pass with pinned assets; synthetic adapters prove only controller tests. No model/isolation availability today is asserted. Proposal remains separately authorized from first repair packet; do not block C1 on model assets.

## Adversarial acceptance, recovery and stop conditions

`tests/test_coverage.py` must parameterize exact outcomes: missing binary→skipped; incompatible version→skipped; malformed/oversized/nonfinite/inconsistent JSON→error; crash/timeout/export exit nonzero/missing report→error; zero selected or all skipped tests→error; zero measurable lines→skipped; 1 pass+1 skip→warn with counts 2/1/1; failing assertion+valid measured data→fail; source/report/config drift→error; symlink report/config/run directory or escaping test path→error before child/write; imported valid report→no child; denied execution→no child/state. Undercover route preserves actual diff findings and emits no line counts. Capture pre/post tree hashes, not filenames alone, for zero effects.

Recovery: never re-use failed run directory, never delete other runs, never repair unrelated historical state. Preserve existing valid completed files and mark incomplete phases; remove own temp stage only, OCI cleanup verified. Partial output cannot count as measurement. Source/plan byte drift during implementation invalidates review; reconcile at current hash before continuing. If installed engine/model/OCI prerequisites absent, stop that acceptance lane with exact missing binary/image/model digest; no fake success, install or new harness. Two identical unchanged-byte verification runs maximum.

## Final checks and completion

### Literal shared documentation delta and check ownership

Batch integration owner additionally owns `docs/CONFIGURATION.md` (exact tracked case), `examples/rush.toml`, `docs/reference/cli-reference.md`, `docs/MCP_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`, `docs/reference/configuration-reference.md`, `docs/reference/result-reference.md`, `scripts/sync_docs.py` and `docs/reports/phase-64-66-documentation-coverage.md`. These are existing source files, not new documentation surfaces. This expands the short ownership list above; no command worker edits them concurrently. Retain all unrelated command rows and baseline counts.

Exact Q19 changes after executable routes pass: in CLI reference's existing coverage/evaluation dual-mode section, replace ambiguous executed-mode summary with `coverage PATH` import versus fresh line measurement, all C2 flags/defaults, three execution grants, status/exit and 3/4/75.0 example. Add dedicated `rush_coverage` row under MCP reference's canonical catalog with the exact typed C2 signature and actual initialized `tools/list` schema/defaults; mirrored detailed row belongs `docs/reference/mcp-tool-reference.md`. Add `[tools.coverage] measurement='line'` and optional test_paths/base_ref only to existing configuration sections/example; no grant, executable/model/image or import path settings in project config. Result reference receives imported-local-report, executed-runner and undercover-diff evidence distinctions, missing_lines/measurement_config_digest/changed-line fields and a genuine numeric receipt. C3 options and trial receipt are published only when separately authorized/implemented, not described as current C1 capability.

`scripts/sync_docs.py::main` is check-only and requires `--check`; it is not a document generator. Reconcile only affected coverage-document entries, source hashes, evidence and contract facts in existing `docs/reports/phase-64-66-documentation-coverage.md` receipt through the current schema. No new writer/harness, no unrelated regenerated text. Executable verification after serialized Q19 shared edits:

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_coverage.py::test_owned_config_ignores_hostile_project_and_environment tests/test_cli_registry.py tests/test_mcp.py -q
```

Expected doc check prints `Documentation coverage and runtime contracts match.` with exit0; test expectations are proposed until run against implementation. The check cannot replace semantic review of exact command examples or real coverage measurement.

Run from implementation worktree based on source baseline; source attribution must resolve to that worktree. These are future checks, not planning evidence:

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_coverage.py tests/test_coverage_transport.py tests/test_coverage_importer.py tests/test_undercover_reference.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase60_characterization.py tests/test_phase70_result_trust.py tests/test_subprocess_contract.py -q
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff format --check src tests scripts
```

Version must be Python 3.12. Planning observed only current-callable launcher reproduction and existing importer suite (combined coverage/CodeQL: 24 passed); future runner/trial tests remain unexecuted. Document readiness requires coordinator frozen-byte substantive review of every ledger row and exact file map. Production completion additionally requires actual count, initialized transport, denial, recovery and applicable genuine runtime gates. Future command-focused PR contains C1 repair first, C2 explicit integration next, separately identified C3 capability implementation after P0; no PR/commit/publication occurs during planning.
