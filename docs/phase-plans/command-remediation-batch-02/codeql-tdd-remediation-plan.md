# Q20 — `rush codeql` / `rush_codeql`: real analysis and query-witness reduction

Planning artifact. Production changes and future checks below are proposed, not implemented or passed. First implementation packet is Q1; witness reduction is separately assessed capability proposal, not prior approval inferred from audit wording. Actual author: `gpt-6-astra`, high reasoning, responsible for invocation/security/algorithm reconciliation and this document. Coordinator reviews frozen bytes before development-readiness verdict.

## Baseline, binding inputs and ownership

Source checkout `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, branch `phase/70-agent-adoption-and-usability`, clean HEAD `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`; relevant source dirty-file hashes: none. Delivery checkout `/Users/jamesdsizemore/Developer/rush-cli`, branch `codex/codex-cli-mcp-commands-review`, HEAD `c78e445ba1e575ca373e35840142cd627b055d6a`. Delivery user-modified `AGENTS.md` SHA-256 `70252e9068f419b79d88e87b228ce796ae5e61fc0572f06f5354acf209f40617` and unrelated untracked documents/scratch are preserved. Future implementation worktree starts at verified source HEAD; none created here. No checkout switch/reset.

| Binding input | SHA-256 |
|---|---|
| Delivery `docs/reports/cli-mcp-command-audit-2026-09-26.md`, complete Q20 lines 7370–7779 | `8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f` |
| Source `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` | `9453032d9411a27b2b7ee2ede074d98d93969fbe85433adacdec1c7bcc89c5c7` |
| Delivery `docs/templates/task-block-template.md` | `10fdb5380f04097258e29327cf74fe474532cdc42747a38310d0befa2107ecc3` |
| Source `.scratch/phase-70-design-gate/T8.md` | `b15a2c5e9c0fd0cab275c1bd17de78e1975f341048e6df9c403982619f12bfe2` |
| Source `.scratch/phase-70-design-gate/W1-T1-T7-T23.md` | `5fa3c629ef17c3f7812af1f274df1b23c3c43a00181778950902ae98f81939b3` |
| Source `.scratch/phase-70-design-gate/W2-T9-T17.md` | `a402ea6ffd4de9c5ca74860d9672cdb834242573ee45b2feb4ca2c2c5da9a0f9` |
| Source `.scratch/phase-70-design-gate/W4-T23-T29.md` | `47de33a0888a63ee6999a1610577f0e3d0868701642a3a27eb36111d1c1d7204` |
| Source `src/rush/tools/codeql.py` | `cd780e165d2cd414a62defde3a2b8f7e3cf97c83185a154cdc888f4abe620dc9` |
| Source `src/rush/catalog.py` | `88c3c340ede406c5251ff53e9b6291f7f5f0239d860d832fe904359c1dddc7b9` |
| Source `src/rush/cli_support/catalog_commands.py` | `a090f5cc4851cc3e4846e65a766f48286b0230c355cf188c04a4c562544c94ff` |
| Source `src/rush/mcp_support/tool_registry.py` | `76b16ae7c4ecd01d3206d798d6f827de4bcf969a0e1f99a9af7857d8deeb10b2` |
| Source `tests/test_codeql_importer.py` | `0c665af68f8e8358e28f2db4ccfae0ef6b794d78d241afaf5eb7af9c4dd19f27` |

Read applicable AGENTS, batch prompt Sections 1–6, task template, Phase 70 T8/T9/T10/T11/T15/T16/T6/T27 with fuller brief Resolutions/test matrices first. Batch 1 failure report supplies lessons only: full source reconciliation, meaningful current-callable RED, closed prerequisites, truthful readiness. Do not alter Batch 1. Owner removed Cursor integration; do not restore it.

Command owner owns future `src/rush/tools/codeql.py`, new `tests/test_codeql.py`, new `tests/test_codeql_transport.py`, new `tests/fixtures/codeql/witness.py`, new `tests/fixtures/codeql/pack/flow.ql`. **Batch integration owner alone** owns `src/rush/catalog.py`, `src/rush/cli_support/catalog_commands.py`, `src/rush/mcp_support/tool_registry.py`, `docs/CONFIGURATION.md`, `examples/rush.toml`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_phase60_characterization.py`, `tests/fixtures/phase70/cli-outcomes.json`. Serialize shared consuming edits Q11→Q20. Q15 P0 owns `src/rush/runtime/isolated_process.py` and `tests/test_isolated_process.py` before any witness-trial work. No simultaneous writers; codeql command owner preserves others' work. P0 design is repeated fully below; cross-plan ordering does not substitute for design.

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



Q20 consumes P0A unchanged. Batch integration owner additionally owns `src/rush/mcp.py::{RushFastMCP.call_tool,RushFastMCP.list_tools}` solely for this shared prerequisite. Order: Q11 P0A raw guard before Q20 Q2 option/schema integration; command owner must not duplicate guard in `CodeqlTool` or a late wrapper. Add this complete consumer body to `tests/test_codeql_transport.py`, using its defined `rpc` helper:

```python
def test_codeql_stdio_raw_invalid_has_zero_effects(tmp_path: Path):
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

This actual initialized stdio request must fail at P0A before missing-target/config/engine processing. It does not substitute for granted engine/algorithm tests. Check: `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_mcp.py::test_catalog_raw_invalid_before_sdk tests/test_mcp.py::test_catalog_raw_type_matrix tests/test_codeql_transport.py::test_codeql_stdio_raw_invalid_has_zero_effects -q`.

## Goal, scope and requirement ledger

Create a fresh CodeQL database, run a locally approved query pack, parse newly produced CodeQL SARIF and report actual evidence. A version probe must never count as analysis. Preserve real report importing and canonical severity. Separately design source-bound query witness reduction.

| Requirement/category | Current evidence / disposition | Exact planned behavior, test, acceptance |
|---|---|---|
| Q20-F1 false-completion repair | `tools/codeql.py:133–191` needs build only, runs sole `['codeql','version']`, labels successful exit analysis. Current-callable reproduction observed status ok. | Q1 replace with grant→version→database create→analyze→fresh parse; exact completed steps, no missing-phase success. `test_version_only_binary_cannot_pass`, `test_fresh_sarif_pipeline`. |
| Q20-P1 importer preservation | `CodeqlTool.run :71–131`, `_is_codeql_sarif :194–210`; tests reject nonobject/foreign/no-run/malformed/outside reports and preserve warning severity. Existing combined importer suite 24 passed on source. | Q1 imported file remains read-only and distinct `imported-local-report`; no code execution or new grants for import; severity error→fail, warn→warn, note→ok. |
| Q20-F3 malformed importer repair | `_is_codeql_sarif :205–207` calls `.get` on `run['tool']` without confirming object type. Current `tool:null` report raises observed `AttributeError: 'NoneType' object has no attribute 'get'`. | Q1 validates tool and driver objects before use; complete RED below expects canonical error and no engine call. This repairs malformed-report boundary without broad exception masking. |
| Q20-F2 catalog repair | `catalog.py:347–352` says never runs CodeQL, but current tool does spawn version. `:974` maturity importer. | Q2 descriptions state import or explicitly granted fresh analysis; engine_names=('codeql',); maturity `real_adapter` only after genuine acceptance, retain importer evidence; docs and help same contract. |
| Q20-E1 ordinary proposed extension / necessary fix continuation | Language/pack/build absent from current explicit signatures. Audit default language wording conflicts with helper requiring explicit language. | Q1/Q2 resolve once: auto detect unique supported language, ambiguous none→actionable error; explicit selection validated. Local pack mandatory, bound by tree digest; no pack download. Build commands explicit user input only. |
| Q20-E2 query-pack identity | Audit `query_pack_identity` proposed; no current corresponding API. Presence of qlpack.yml alone is not approval or transitive dependency identity. | Q1 contained explicit pack path plus full regular-file/dependency closure digest and lock; malformed, symlink, external dependency, remote pack name rejected. No dependency resolution network. |
| Q20-B1 requested provisioning baseline | Existing secure binary resolver/provisioning supports installed engines; CodeQL licensing/download must not be invented. | Q2 actionable missing/unsupported readiness, same resolver as execution. No automatic installer, release asset fetch, query download or license claim. Existing user-consented provisioning owns acquisition; preinstalled assets prerequisite. |
| Q20-B2 connected specialist baseline | No model needed for exact CodeQL query evaluation or deterministic reducer. | Preserve structured evidence for agent consumption. Do not add model scoring of vulnerabilities or claim model integration from SARIF. Baseline specialist connectivity remains separately owned product work; not an invention in Q20. |
| Q20-B3 voice/live speech/3D baseline | No corresponding command endpoint or audio/UI state in current CodeqlTool. | Exact SARIF/witness metadata remains machine-readable for those consumers; no unrequested UI/mic command. Applicability assessment does not delete product-wide requirements. |
| Q20-X1 distinct capability proposal | Audit minimizer/controller is unimplemented; fake preserves-flow callback proves no CodeQL or isolation. | Q3 bounded removal of unrelated Python function occurrences, genuine fresh query rerun after each trial, same source/sink/rule/pack, one-deletion claim only after exhaustive final single-removal sweep. |
| P70 T8/T9/T10 | Current shared invocation normalizes target and rejects missing/escaping input; tool itself resolves reports. | Reuse logical root, original request preserved; secondary pack/report paths anchored once; invalid target error; empty supported source skipped; denied grants create no DB/run directory; owned artifacts remain contained. |
| P70 T11/T15 | `runtime/binaries.py::resolve_binary :355–400` verified manifest→Rush runtime→safe PATH; existing subprocess owner/run context. | Exact resolved executable; record version/binary SHA; no bare executable re-resolution. No unsafe project PATH, hidden install or config-supplied executable. Replacing binary invalidates prior readiness. |
| P70 T16/T27/T6 | Wrapper `tool_registry.py:318–388` delivers full/compact and explicit signature, existing catalogue CLI forwards `**tool_options`. | Q2 exact flat schema, actual stdio+CLI tests, status parity excluding runtime IDs/timings, engines/scope and recoverable output; count evidence comes from real database/SARIF, never directory guesses. |

No memory or token-budget operation is added. Query witness is a new agent-side source-reduction operation; CodeQL execution, language flags and provisioning are fixes/baselines/ordinary extensions, not inventions. Planning fully specifies proposal but does not relabel it approved implementation.

## Required behavior and exact interface

Add explicit keywords to both `CodeqlTool.__call__` and `.run`; retain `.run(config=None,permissions=None)` and existing seven `allow_*:bool=False` on callable, constructing existing `ExecutionPermissions` and forwarding every value unchanged:

```python
report_path: Path | None = None
language: str | None = None
query_pack: Path | None = None
build_command: str | None = None
minimize_alert: int | None = None
isolation_runtime_path: str | None = None
codeql_image_ref: str | None = None
codeql_entrypoint: str | None = None
trial_timeout_seconds: int = 600
```

Flags: `--language`, `--query-pack`, `--build-command`, `--minimize-alert`, `--isolation-runtime-path`, `--codeql-image-ref`, `--codeql-entrypoint`, `--trial-timeout-seconds`. Strings default None; alert index strict nonnegative integer; timeout strict integer 1..600, bool rejected. Existing `--report-path` unchanged. `_TOOL_CLI_OPTIONS['codeql']` explicit options only; no generic catalog introspection. MCP schema has same field names and types plus existing `project`/view grants injected by wrapper; no new top-level combinator or tool.

`query_pack` and `report_path` are invocation-cwd-relative CLI and server-anchor/declared-root-relative MCP secondary paths; add exact `('report_path','query_pack')` to codeql `_CWD_RELATIVE_ARGS`, preserving prior entries. Tool receives normalized absolute path then verifies under logical project root through `PhysicalRoot`; no repeated cwd join. Runtime path must be explicit absolute approved binary, never project config. Language may be `python`, `javascript-typescript`, `java-kotlin`, `c-cpp`, `csharp`, `go`, `ruby`, `swift`, `rust`; selected language must also exist in actual installed CodeQL `resolve languages --format=json` output. Unknown or unsupported is error `unsupported_language`, no database. Auto detection groups regular source suffixes `.py`; `.js/.jsx/.ts/.tsx`; `.java/.kt`; `.c/.cc/.cpp/.h/.hpp`; `.cs`; `.go`; `.rb`; `.swift`; `.rs`, excluding `.git/.rush/.venv/node_modules/vendor`; zero groups→skipped `no_supported_targets`, >1→error `language_required` listing sorted candidates. Explicit language scopes analysis; no multi-language aggregate invented.

Explicit imported report or positional `.sarif/.json` file uses current importer. Reject any language/pack/build/minimize/runtime fields with import as `import_execution_conflict`, zero processes. Source file positional input is error `live_requires_directory`; directory required for live DB. Missing explicit report remains skipped. Empty SARIF CodeQL run with `results=[]` is valid imported clean evidence; no CodeQL runs is invalid. Preserve valid note/warning/error severities. Import never establishes source freshness.

Live mode requires build+slow+artifact-write before any probe, scratch or state. No network/download granted implicitly and no pack resolution downloads; host build command is explicitly permissioned code execution, not advertised as network-isolated. Missing query pack yields canonical `error`, reason `query_pack_required`, recovery command tells user `--query-pack <contained-local-pack>`. This is truthful no-work, not a version success. Missing executable→skipped `engine_missing`; malformed/unsupported version→skipped `engine_incompatible`; database or analyzer nonzero, timeout/crash/missing/truncated/invalid SARIF→error. Findings error→fail, warning→warn, notes-only or valid no-findings analysis→ok. Engine errors never become findings-only warn.

Resolve `codeql` using `resolve_binary('codeql',engine_id='codeql',project_root=root)`. Version subprocess uses absolute executable `version --format=json`, parses object key `version` as semantic version; require version ≥2.15.2 because this design uses `--common-caches`, introduced in that version according to [official version reference](https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/version). This is a specific required capability, not a broad untested support claim. Record full version and executable SHA-256 before/after. Map API names to extractor names: `javascript-typescript→javascript`, `java-kotlin→java`, `c-cpp→cpp`; other names unchanged. `resolve languages --format=json` must return exactly one location for chosen extractor; zero/multiple locations are unsupported/ambiguous, per [official resolver contract](https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/resolve-languages). Use extractor name for `--language`, retain public language in metadata. For languages requiring extraction/build (`java-kotlin,c-cpp,csharp,go,swift,rust`), require explicit `build_command`; interpreted Python/JS/Ruby reject build command as unused. Command must be nonempty ≤4096 chars, no NUL/newline; passed as single `--command=<text>` to CodeQL, never through Rush shell. It is user-authorized build code, not sanitized safe code. Project configuration may choose ordinary language only; `query_pack`, executable, build command and trial pins require explicit invocation. No hidden config grants.

Owned run `.rush/runs/codeql-<unique>/` created 0700 after physical containment/grants. Fresh database path nonexistent before create, output `results.sarif` nonexistent before analyze. Commands:

```text
<resolved-codeql> version --format=json
<resolved-codeql> resolve languages --format=json
<resolved-codeql> database create <owned>/database --language=<extractor> --source-root=<root> --common-caches=<owned>/codeql-cache [--command=<explicit build command>]
<resolved-codeql> database analyze <owned>/database <contained-pack> --additional-packs=<contained-pack>/vendor --common-caches=<owned>/codeql-cache --no-default-compilation-cache --compilation-cache=<owned>/compilation-cache --format=sarifv2.1.0 --sarif-add-snippets --output=<owned>/results.sarif
```

Every phase uses existing `tools.common.run_subprocess`, timeout 30 seconds for probes, 600 seconds each database/analyze; ambient owner/run identity preserved. After grants and secure binary resolution, create owned run/home before first probe and set child `HOME=<owned>/home`; no inherited user CodeQL config. Add `--common-caches=<owned>/codeql-cache` to create/analyze. For every analyze and fixture query compile, also pass `--no-default-compilation-cache --compilation-cache=<owned>/compilation-cache`; common-caches alone does not suppress caches next to query packs/toolchain. Fixture compile explicitly uses `--no-precompile` to avoid adjacent `.qlx` output. This matches official [query-compile cache flags](https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/query-compile) and [database-analyze cache flags](https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/database-analyze). No helper falls back to default cache locations. Probe HOME is already contained even before version compatibility checked. Existing environment preserved only where build needs it; remove `CODEQL_*` overrides capable of replacing config/search paths, inherited `PYTHONPATH` and externally selected library paths; explicit contained additional-packs wins. No `shell=True`, installs, network pack names, remote repository operations or automatic database re-use. Validate database directory created and metadata `codeql-database.yml` before analyze. Read fresh report bounded at 32 MiB, regular and not symlink. `_is_codeql_sarif` plus `parse_structured_iac_report(raw,root)` enforce CodeQL and finding containment. Use same severity computation as importer, correcting audit sketch's all-findings-warn downgrade.

Source identity hashes every regular selected-language file and relevant project/build config before/after; reject symlink/reparse descendants prior to reading. Query pack identity binds all files and transitive local dependencies. Use existing dependency `ruamel.yaml==0.19.1` (`pyproject.toml:34`): `from ruamel.yaml import YAML; parser=YAML(typ='safe'); parser.allow_duplicate_keys=False`; load `qlpack.yml`, require object `name`, `version`, dependencies object (absent means empty). Lock file `codeql-pack.lock.yml` is required only when dependencies nonempty; `lockVersion` must be integer1, `dependencies` maps each package to an object with exact version string. Resolve each entry to already installed content whose path lies in supplied pack closure directory; remote/missing/unlocked dependencies produce error `query_pack_dependencies_unavailable`. No shell `codeql pack download`. Define closure root as supplied pack directory; vendor dependency packs below `vendor/` and pass explicit `--additional-packs=<pack>/vendor` to analyze. A dependency name/version must match one unique vendored `qlpack.yml`; cycles rejected; all files hashed. Reject absolute/external `extractor`, `libraryPathDependencies` or symlink references. Runtime's trusted standard CodeQL library bundle is recorded by CLI version/binary + bundle digest (SHA-256 of sorted relative-file→SHA-256 JSON for trusted executable's containing bundle directory, excluding owned runtime output), and must match same identity in witness image. No path/hash alone implies trusted licensing or model correctness.

Change source, config, pack closure or binary during run→error reason `<kind>_digest_drift`, retain completed steps and valid artifacts but no fresh-analysis success. Each step metadata `{name,argv,exit,status,duration_ms}`; args redacted where necessary, never log secret build strings verbatim. Record build command digest; rendered argv uses `[REDACTED]` for its value. Top metadata `evidence_source='executed-analysis'`, language, `database_path`, relative query_pack, query_pack_digest, source_hashes, config_hashes, report_digest, execution and engines. Import remains `imported-local-report`. `metrics.findings` exact parser count; scope consumed-file count unavailable with reason unless actual database source inventory supplies it. SARIF files with findings are not a complete consumed-file inventory.

On failed phase retain valid owned diagnostics/report only, mark step error, delete only owned incomplete temp files. Do not overwrite old database/report, remove other runs or repair unrelated state. Creation/analyze resources cleaned by underlying ownership; incomplete DB remains explicitly incomplete for user recovery, never reused. Output stdout during MCP is JSON-RPC only; child diagnostics captured/redacted, logs stderr.

## Q1 — Replace version-only success with fresh analysis

Implement `CodeqlTool.run` live branch in Rush. Read binding instructions and Phase 70 source contract first.

### Required behavior

Begin current-callable RED below; then implement language/pack input and complete pipeline. Preserve existing importer. No passing result until valid fresh CodeQL report exists from successful database creation and analysis.

### Deliverables

`src/rush/tools/codeql.py::{CodeqlTool.__call__,CodeqlTool.run,run_codeql_analysis,query_pack_identity}`; `tests/test_codeql.py` current reproduction, pipeline and adversarial tests. Helpers reuse verified result/parser/permission/subprocess/physical-path implementations, not audit imaginary API.

### RED — observed current callable, not future keyword absence

```python
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from rush.permissions import ExecutionPermissions
from rush.tools.codeql import CodeqlTool


def test_version_only_binary_cannot_pass(tmp_path: Path):
    (tmp_path / "rush.toml").write_text("")
    (tmp_path / "app.py").write_text("print(1)\n")
    calls = []

    def version_only(argv, **kwargs):
        calls.append(argv)
        return CompletedProcess(argv, 0, "CodeQL command-line toolchain release 2.23.0.\n", "")

    with patch("rush.tools.codeql.engine_on_path", return_value=True), patch(
        "rush.tools.codeql.run_subprocess", side_effect=version_only
    ):
        result = CodeqlTool().run(
            tmp_path, permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True)
        )
    assert calls == [["codeql", "version"]], "current reproduction boundary changed"
    assert result["status"] == "error", result
```

Observed on clean source 2026-10-01: calls exactly `[['codeql','version']]`, status `ok`, metrics None. Last assertion fails; fixture invokes real current branch. Historical-path assertion is removed when branch replaced and replaced by production contract `no successful analysis without database/analyze`. New interface absence is separate: `.run(language=...,query_pack=...)` currently raises TypeError and proves only feature absence.

Additional current importer RED, observed without engine doubles: `tool:null` raises exact AttributeError above. Add to `tests/test_codeql.py`:

```python
def test_malformed_driver_returns_error_without_execution(tmp_path: Path):
    import json

    report = tmp_path / "bad.sarif"
    report.write_text(json.dumps({"version": "2.1.0", "runs": [{"tool": None}]}))
    with patch("rush.tools.codeql.run_subprocess") as child:
        result = CodeqlTool().run(tmp_path, report_path=report)
    assert result["status"] == "error"
    assert result["findings"] == []
    child.assert_not_called()
```

Exact replacement `_is_codeql_sarif`, preserving existing format/version semantics:

```python
def _is_codeql_sarif(report_text: str) -> bool:
    import json

    try:
        report = json.loads(report_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(report, dict):
        return False
    runs = report.get("runs")
    if report.get("version") != "2.1.0" or not isinstance(runs, list) or not runs:
        return False
    for run in runs:
        if not isinstance(run, dict):
            return False
        tool = run.get("tool")
        if not isinstance(tool, dict):
            return False
        driver = tool.get("driver")
        if not isinstance(driver, dict):
            return False
        name = driver.get("name")
        if not isinstance(name, str) or not name.lower().startswith("codeql"):
            return False
    return True
```

Parametrize tool as None/list/string and driver as None/list/string, exact error each; valid CodeQL runs retain existing import behavior. Do not catch all AttributeError to hide programmer bugs elsewhere.

### Minimum GREEN and complete pipeline test

Replace existing executed branch with `run_codeql_analysis(self,path,language=language,query_pack=query_pack,build_command=build_command,permissions=permissions)`, defined with precise flow above. No-input legacy live call becomes actionable missing-pack error, not analysis. Pipeline acceptance below supplies language/pack so it cannot pass merely by missing-parameter refusal. It injects only process execution and binary resolver; genuine SARIF parsing and containment run. Local pack fixture without dependencies is valid for controller test; Q1 owns genuine query fixtures, complete materializer and independent direct/CLI/MCP acceptance below. Q3 consumes those Q1 prerequisites; Q1 does not require witness reduction authorization.

```python
def test_fresh_sarif_pipeline(tmp_path: Path):
    import json

    root = tmp_path / "project"
    root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "app.py").write_text("value = input()\nprint(value)\n")
    pack = root / "packs/security"
    pack.mkdir(parents=True)
    (pack / "qlpack.yml").write_text("name: rush/test-pack\nversion: 0.0.1\n")
    (pack / "flow.ql").write_text("select 1\n")
    binary = tmp_path / "codeql"
    binary.write_text("fixture executable identity\n")
    calls = []
    sarif = {
        "version": "2.1.0", "runs": [{
            "tool": {"driver": {"name": "CodeQL"}},
            "results": [{"ruleId": "py/test-flow", "level": "error",
                "message": {"text": "Fixture flow."},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "app.py"}, "region": {"startLine": 2}
                }}]}],
        }],
    }

    def child(argv, **kwargs):
        calls.append(argv[1:3])
        if argv[1] == "version":
            return CompletedProcess(argv, 0, '{"version":"2.23.0"}', "")
        if argv[1:3] == ["resolve", "languages"]:
            return CompletedProcess(argv, 0, '{"python":["/fixture/python-extractor"]}', "")
        if argv[1:3] == ["database", "create"]:
            db = Path(argv[3])
            db.mkdir()
            (db / "codeql-database.yml").write_text("primaryLanguage: python\n")
        elif argv[1:3] == ["database", "analyze"]:
            assert "--no-default-compilation-cache" in argv
            cache = Path(next(arg.split("=", 1)[1] for arg in argv
                              if arg.startswith("--compilation-cache=")))
            assert cache.is_relative_to(root / ".rush")
            assert not cache.is_relative_to(pack)
            output = Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--output=")))
            output.write_text(json.dumps(sarif))
        else:
            raise AssertionError(argv)
        return CompletedProcess(argv, 0, "", "")

    with patch("rush.tools.codeql.resolve_binary", return_value=str(binary)), patch(
        "rush.tools.codeql.run_subprocess", side_effect=child
    ):
        result = CodeqlTool().run(
            root, language="python", query_pack=pack,
            permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
        )
    assert calls == [["version", "--format=json"], ["resolve", "languages"],
                     ["database", "create"], ["database", "analyze"]]
    assert result["status"] == "fail", result
    assert [(f["path"], f["line"], f["rule"], f["severity"]) for f in result["findings"]] == [
        (str(root / "app.py"), 2, "py/test-flow", "error")
    ]
    assert result["metadata"]["evidence_source"] == "executed-analysis"
    assert [s["name"] for s in result["metadata"]["steps"]] == [
        "version", "resolve_languages", "database_create", "database_analyze"
    ]
    assert Path(result["artifacts"][0]).is_file()
```

Define `resolve_binary` import at module scope, making this patch target literal and real after GREEN. `run_codeql_analysis` phase state machine is `validated → permitted → resolved → versioned → database_created → analyzed → parsed → identity_verified`; no transition can be inferred from output filename alone. Exceptions map canonical error with completed phase list. Missing engine stays skipped; child nonzero after start is error.

Query tree digest algorithm below is concrete core of `query_pack_identity`. Invoke after safe YAML/closure validation described above; inputs already no-follow validated. Re-run after analyzer and before each witness candidate. This code defines digest bytes, not trust policy replacement:

```python
def pack_tree_digest(pack):
    import hashlib
    import json
    import os
    from pathlib import Path

    from rush.io.physical_paths import PhysicalRoot
    from rush.workflows.projects import open_contained_file

    pack = Path(pack)
    physical = PhysicalRoot(pack)
    hashes = {}
    for file in sorted(pack.rglob("*")):
        relative = file.relative_to(pack).as_posix()
        checked = physical.open_contained(relative, purpose="read")
        if checked.is_file():
            with os.fdopen(open_contained_file(pack, relative), "rb") as stream:
                hashes[relative] = hashlib.sha256(stream.read()).hexdigest()
    encoded = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
```

### Q1 complete local query fixture materialization and genuine acceptance

Q1 command owner owns `tests/fixtures/codeql/witness.py` and `tests/fixtures/codeql/pack/flow.ql`, whose exact bytes appear under **Q1-owned genuine query fixture, reused by Q3** below. Generated `qlpack.yml`, `codeql-pack.lock.yml` and vendored dependencies exist only in test-owned temporary project; never commit an environment-specific library version or vendor distribution. Put following complete helper and direct test in existing proposed `tests/test_codeql.py`. Transport test imports `materialize_codeql_fixture, codeql_domain` from `test_codeql` under repository's current pytest prepend import mode. No new fixture framework/file is needed.

Only external library prerequisites: `RUSH_CODEQL_TEST_LIBRARY` is an approved existing local directory containing `codeql/python-all` and every dependency as regular, nonoverlapping package trees; `RUSH_CODEQL_TEST_LIBRARY_SHA256` is independently supplied SHA256 of the exact whole-directory file map using `tree_hash` below. Each package with dependencies must have its own `codeql-pack.lock.yml` with exact pins. Missing lock/package/hash, duplicate name, cycles, unsupported legacy `libraryPathDependencies`, symbolic/hard links or mutated bytes fail before compilation. The materializer never resolves/downloads a package, trusts a hash it computed without comparison, or chooses a version. It derives versions from pinned approved input, validates each transitive edge, creates an immediate-child vendor layout, and writes complete root lock. `--additional-packs=<pack>/vendor` searches those immediate package directories, matching [CodeQL's local pack search contract](https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/resolve-packs). No `RUSH_CODEQL_TEST_PACK` prebuilt-pack escape hatch remains.

```python
def materialize_codeql_fixture(root: Path):
    import hashlib
    import json
    import os
    import re
    import stat
    import subprocess
    from ruamel.yaml import YAML
    from rush.runtime.binaries import resolve_binary
    from rush.workflows.projects import open_contained_file

    def read(directory, relative):
        with os.fdopen(open_contained_file(directory, relative), "rb") as stream:
            return stream.read()

    def inventory(directory):
        result = {}
        for parent, dirs, names in os.walk(directory, followlinks=False):
            for name in dirs + names:
                path = Path(parent) / name
                mode = path.lstat().st_mode
                assert not path.is_symlink(), "fixture symlink: " + str(path)
                assert not getattr(path.lstat(), "st_file_attributes", 0) & 0x400
                assert stat.S_ISDIR(mode) or stat.S_ISREG(mode), "nonregular fixture"
            for name in sorted(names):
                relative = (Path(parent) / name).relative_to(directory).as_posix()
                result[relative] = hashlib.sha256(read(directory, relative)).hexdigest()
        return result

    def tree_hash(files):
        return hashlib.sha256(json.dumps(files, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()

    def yaml_object(data):
        parser = YAML(typ="safe"); parser.allow_duplicate_keys = False
        value = parser.load(data.decode("utf-8"))
        assert isinstance(value, dict), "fixture YAML object required"
        return value

    source = Path(os.environ["RUSH_CODEQL_TEST_LIBRARY"]).absolute()
    assert source.is_dir() and not source.is_symlink(), "approved library directory required"
    expected = os.environ["RUSH_CODEQL_TEST_LIBRARY_SHA256"]
    assert re.fullmatch(r"[0-9a-f]{64}", expected)
    files = inventory(source)
    assert tree_hash(files) == expected, "approved library SHA256 mismatch"
    packages = {}
    version_pattern = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"
    for relative in sorted(files):
        if Path(relative).name != "qlpack.yml":
            continue
        manifest = yaml_object(read(source, relative))
        name, version = manifest.get("name"), manifest.get("version")
        assert isinstance(name, str) and re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+", name)
        assert isinstance(version, str) and re.fullmatch(version_pattern, version)
        assert name not in packages, "ambiguous installed pack " + name
        assert not manifest.get("libraryPathDependencies"), "legacy external library paths"
        extractor = manifest.get("extractor")
        assert extractor is None or extractor == "python", "external/non-Python extractor"
        folder = Path(relative).parent
        dependencies = manifest.get("dependencies", {})
        assert isinstance(dependencies, dict)
        lock = {}
        if dependencies:
            locked = yaml_object(read(source, (folder / "codeql-pack.lock.yml").as_posix()))
            assert type(locked.get("lockVersion")) is int and locked["lockVersion"] == 1
            lock = locked.get("dependencies")
            assert isinstance(lock, dict)
            for dependency in dependencies:
                assert dependency in lock and isinstance(lock[dependency], dict)
                pin = lock[dependency].get("version")
                assert isinstance(pin, str) and re.fullmatch(version_pattern, pin)
        packages[name] = (version, folder, dependencies, lock)
    assert "codeql/python-all" in packages, "Python library prerequisite absent"
    visiting, closure = set(), {}
    def visit(name, required_version=None):
        assert name in packages, "missing local dependency " + name
        version, folder, dependencies, lock = packages[name]
        assert required_version is None or version == required_version, "locked version mismatch"
        assert name not in visiting, "dependency cycle"
        if name in closure:
            return
        visiting.add(name)
        for dependency in sorted(dependencies):
            visit(dependency, lock[dependency]["version"])
        visiting.remove(name)
        closure[name] = (version, folder)
    visit("codeql/python-all")
    roots = [folder for _, folder in closure.values()]
    assert all(a == b or not a.is_relative_to(b) for a in roots for b in roots), "nested pack roots"
    root.mkdir(parents=True, exist_ok=True)
    (root / "rush.toml").write_text("")
    fixture_dir = Path(__file__).parent / "fixtures/codeql"
    (root / "witness.py").write_bytes((fixture_dir / "witness.py").read_bytes())
    pack = root / "packs/security"; pack.mkdir(parents=True)
    vendor = pack / "vendor"; vendor.mkdir()
    for name, (_, folder) in sorted(closure.items()):
        destination = vendor / name.replace("/", "__"); destination.mkdir()
        prefix = folder.as_posix() + "/" if folder != Path(".") else ""
        for relative in sorted(files):
            if not relative.startswith(prefix):
                continue
            target = destination / relative[len(prefix):]
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = read(source, relative)
            assert hashlib.sha256(payload).hexdigest() == files[relative], "library changed while copying"
            target.write_bytes(payload)
    assert inventory(source) == files, "library changed during materialization"
    version = closure["codeql/python-all"][0]
    (pack / "qlpack.yml").write_text(
        "name: rush/witness-fixture\nversion: 0.0.1\ndependencies:\n"
        "  codeql/python-all: " + version + "\n"
        "defaultSuite:\n  - query: flow.ql\n")
    lock = {"lockVersion": 1, "dependencies": {
        name: {"version": version} for name, (version, _) in sorted(closure.items())}}
    writer = YAML()
    with (pack / "codeql-pack.lock.yml").open("w") as stream:
        writer.dump(lock, stream)
    (pack / "flow.ql").write_bytes((fixture_dir / "pack/flow.ql").read_bytes())
    pack_before = inventory(pack)
    binary = resolve_binary("codeql", engine_id="codeql", project_root=root)
    assert binary, "installed trusted CodeQL prerequisite"
    owned = root / ".rush/fixture-compile"; owned.mkdir(parents=True, mode=0o700)
    home = owned / "home"; home.mkdir(mode=0o700)
    (owned / "compilation-cache").mkdir(mode=0o700)
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith("CODEQL_") and k not in {"PYTHONPATH", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS"}}
    environment["HOME"] = str(home)
    compiled = subprocess.run([str(binary), "query", "compile",
        "--additional-packs=" + str(vendor), "--common-caches=" + str(owned / "cache"),
        "--no-default-compilation-cache", "--compilation-cache=" + str(owned / "compilation-cache"),
        "--no-precompile",
        "--ram=6144", "--threads=2", "--", str(pack / "flow.ql")],
        cwd=root, env=environment, capture_output=True, text=True, timeout=600)
    assert compiled.returncode == 0, (compiled.stdout, compiled.stderr)
    assert inventory(pack) == pack_before, "compiler changed approved pack inputs"
    return pack, tree_hash(pack_before), expected


def codeql_domain(result, root):
    rows = []
    for finding in result["findings"]:
        path = Path(finding["path"])
        relative = path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
        rows.append((finding["rule"], relative, finding["line"], finding["severity"]))
    return (result["status"], sorted(rows), result["metadata"]["evidence_source"],
            result["metadata"]["language"])


def test_real_q1_analysis_without_minimizer(tmp_path: Path):
    import hashlib
    root = tmp_path / "project"
    pack, digest, _ = materialize_codeql_fixture(root)
    original = (root / "witness.py").read_bytes()
    result = CodeqlTool().run(root, language="python", query_pack=pack,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True))
    assert codeql_domain(result, root) == (
        "fail", [("py/rush-witness-flow", "witness.py", 11, "error")],
        "executed-analysis", "python")
    assert "query_witness" not in result["metadata"]
    assert result["metadata"]["query_pack_digest"] == digest
    from rush.tools.codeql import pack_tree_digest
    assert pack_tree_digest(pack) == digest
    assert result["metadata"]["source_hashes"]["witness.py"] == hashlib.sha256(original).hexdigest()
    assert (root / "witness.py").read_bytes() == original
```

The compile call performs actual query compilation, not `--check-only`; installed version/library incompatibility fails its exact assertion. Generated `defaultSuite: [{query: flow.ql}]` selects only supplied fixture query, preventing directory recursion from selecting vendored queries; this uses CodeQL's [documented pack default suite](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/scan-from-the-command-line/publish-and-use-packs). Input file hash verification occurs before and after each no-follow copy. Asset digest is supplied independently, never filled automatically from discovered files. Q1 grants explicitly permit its contained compiler cache/run artifacts. CodeQL compiler's [documented compilation output/cache behavior](https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/query-compile) is separate from fresh database analysis proof.

### Constraints and checks to run before reporting

Version/controller doubles prove no query evaluation. Run actual preinstalled CodeQL with supplied local query fixture separately; missing prerequisites cannot become a passing skip. Keep existing importer return severity and `ToolResult` shape. No new process layer.

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_codeql.py::test_version_only_binary_cannot_pass tests/test_codeql.py::test_fresh_sarif_pipeline tests/test_codeql_importer.py -q
```

### Completion

False-success regression closed at current boundary; pipeline test reaches real parser and all phases; fresh real-engine acceptance below passes. Refactor only command-local control flow after GREEN; do not rewrite shared resolver/importer.

## Q2 — Explicit routes, containment and real transports

### Required behavior

Expose options above; preserve alias/declared-root semantics, flat schema, grants and compact delivery. `CodeqlTool.__call__` uses current grant conversion, not invented executor kwargs. Update only codeql `_TOOL_CLI_OPTIONS` and `_CWD_RELATIVE_ARGS`, catalog and docs. Same tool must serve CLI, initialized stdio MCP and direct invocation. Dynamic text rendered safely by existing Phase 70 renderer. Human summary must state imported vs executed, language, findings count and report path; machine evidence remains untruncated in default mode.

### Deliverables

Command owner `tests/test_codeql_transport.py`; Batch integration owner exact paths from ownership list. Add ordinary language `ToolOptionSpec`; user-approved pack/build/runtime pins remain explicit call fields and are not project config defaults. `examples/rush.toml` contains only `[tools.codeql] language='python'` with comment that explicit approved local pack and three execution grants still required. `docs/CONFIGURATION.md` documents same. Catalog description becomes “Import contained CodeQL SARIF or run a fresh local CodeQL database analysis with build, slow and artifact-write grants.” MCP description states same within 200 chars. Maturity becomes real_adapter only with real engine acceptance; no unsupported readiness claim from file count.

### Runnable preservation and grant transport test

```python
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def cli(root, arguments, *, timeout=60):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-m", "rush.cli", *arguments, "--json"],
        cwd=root, env=env, capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode, json.loads(proc.stdout), proc.stderr


async def rpc(root, arguments, log):
    from datetime import timedelta
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    params = StdioServerParameters(command=sys.executable,
        args=["-m", "rush.cli", "mcp", "serve"], cwd=str(root), env=env)
    with log.open("w+") as errors:
        async with stdio_client(params, errlog=errors) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                schema = next(t.inputSchema for t in tools.tools if t.name == "rush_codeql")
                assert schema["type"] == "object"
                assert schema["additionalProperties"] is False
                assert not {"oneOf", "anyOf", "allOf"} & schema.keys()
                response = await session.call_tool("rush_codeql", arguments,
                    read_timeout_seconds=timedelta(seconds=1800))
                assert not response.isError
                return json.loads(next(c.text for c in response.content if c.type == "text"))


def test_cli_stdio_codeql_import_and_denial(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "app.py").write_text("x = 1\n")
    report = {"version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": "CodeQL"}}, "results": [{
            "ruleId": "py/example", "level": "warning", "message": {"text": "Review value."},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": "app.py"}, "region": {"startLine": 1}
            }}],
        }],
    }]}
    (root / "results.sarif").write_text(json.dumps(report))
    code, left, _ = cli(root, ["codeql", ".", "--report-path", "results.sarif"])
    right = asyncio.run(rpc(root, {"path": ".", "report_path": "results.sarif"}, tmp_path / "mcp.log"))
    def projection(result):
        return result["status"], [(f["line"], f["rule"], f["severity"]) for f in result["findings"]], result["metadata"]["evidence_source"]
    assert code == 1
    assert projection(left) == projection(right) == (
        "warn", [(1, "py/example", "warn")], "imported-local-report"
    )
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    code, left, _ = cli(root, ["codeql", "."])
    right = asyncio.run(rpc(root, {"path": "."}, tmp_path / "denied.log"))
    assert (code, left["status"], right["status"]) == (0, "skipped", "skipped")
    assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    assert not (root / ".rush").exists()
```

Tests use installed editable project Python, inherited PYTHONPATH cleared. SDK's initialized protocol parser rejects stdout diagnostics; stderr separately captured. Q1 owns this complete genuine executed transport test in `tests/test_codeql_transport.py`; it calls no minimizer or OCI API. Materializer above independently validates source library SHA256, transitive pins and actual compilation before any tool run. Child runtime ceiling1800 seconds covers probes plus create/analyze; this is a proposed test timeout, not a planning wait.

```python
def test_real_q1_cli_stdio_analysis_without_minimizer(tmp_path: Path):
    import hashlib
    from test_codeql import materialize_codeql_fixture, codeql_domain
    from rush.permissions import ExecutionPermissions
    from rush.tools.codeql import CodeqlTool

    root = tmp_path / "project"
    pack, expected_pack_digest, _ = materialize_codeql_fixture(root)
    original = (root / "witness.py").read_bytes()
    direct = CodeqlTool().run(root, language="python", query_pack=pack,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True))
    code, local, stderr = cli(root, ["codeql", ".", "--language", "python",
        "--query-pack", "packs/security", "--allow-build", "--allow-slow",
        "--allow-artifact-write"], timeout=1800)
    remote = asyncio.run(rpc(root, {"path": ".", "language": "python",
        "query_pack": "packs/security", "allow_build": True, "allow_slow": True,
        "allow_artifact_write": True}, tmp_path / "real-codeql.stderr"))
    expected = ("fail", [("py/rush-witness-flow", "witness.py", 11, "error")],
                "executed-analysis", "python")
    assert code == 1
    assert codeql_domain(direct, root) == codeql_domain(local, root) == codeql_domain(remote, root) == expected
    for result in (direct, local, remote):
        assert "query_witness" not in result["metadata"]
        assert result["metadata"]["query_pack_digest"] == expected_pack_digest
        assert result["metadata"]["source_hashes"]["witness.py"] == hashlib.sha256(original).hexdigest()
        assert (root / Path(result["metadata"]["database_path"])).is_dir()
    assert (root / "witness.py").read_bytes() == original
    # cli parsed its complete stdout as one JSON document; initialized stdio
    # parsed every stdout frame. Scanner logs can occur only on captured stderr.
    assert "Traceback" not in stderr
    assert "Traceback" not in (tmp_path / "real-codeql.stderr").read_text()
    from rush.tools.codeql import pack_tree_digest
    assert pack_tree_digest(pack) == expected_pack_digest
```

Scanner/pack/resource prerequisites are hard failures in this explicitly selected acceptance test; no pytest skip. Independent runtime absence does not replace this body with a double. Fake pipeline transport below separately proves denial zero-spawn and exact orchestrated argv without claiming CodeQL semantics.

Complete granted and denied process-fixture acceptance in same `tests/test_codeql_transport.py`. Prerequisite: no runtime-bin CodeQL takes precedence over fixture PATH. The marker and exact phase assertions prevent accidental use of another executable. This tests public transports, parser and orchestration, not actual CodeQL query semantics:

```python
def test_cli_stdio_codeql_pipeline_and_denied_effects(tmp_path: Path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "app.py").write_text("value = input()\nprint(value)\n")
    pack = root / "packs/security"
    pack.mkdir(parents=True)
    (pack / "qlpack.yml").write_text("name: rush/test-pack\nversion: 0.0.1\n")
    (pack / "flow.ql").write_text("select 1\n")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    engine = binaries / "codeql"
    marker = tmp_path / "calls.jsonl"
    engine.write_text("#!" + sys.executable + "\n" + r'''
import json, os, pathlib, sys
a = sys.argv[1:]
with open(os.environ["RUSH_ENGINE_LOG"], "a") as log:
    log.write(json.dumps(a) + "\n")
if a == ["version", "--format=json"]:
    print('{"version":"2.23.0"}')
elif a == ["resolve", "languages", "--format=json"]:
    print('{"python":["/fixture/python-extractor"]}')
elif a[:2] == ["database", "create"]:
    db = pathlib.Path(a[2]); db.mkdir()
    (db / "codeql-database.yml").write_text("primaryLanguage: python\n")
elif a[:2] == ["database", "analyze"]:
    out = pathlib.Path(next(x.split("=", 1)[1] for x in a if x.startswith("--output=")))
    out.write_text(json.dumps({"version":"2.1.0","runs":[{
        "tool":{"driver":{"name":"CodeQL"}}, "results":[{
            "ruleId":"py/test-flow","level":"error","message":{"text":"Fixture flow."},
            "locations":[{"physicalLocation":{"artifactLocation":{"uri":"app.py"},
                "region":{"startLine":2}}}]}]}]}))
else:
    sys.exit(2)
''')
    engine.chmod(0o755)
    monkeypatch.setenv("PATH", str(binaries) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("RUSH_ENGINE_LOG", str(marker))
    opts = ["codeql", ".", "--language", "python", "--query-pack", "packs/security"]
    request = {"path": ".", "language": "python", "query_pack": "packs/security"}
    code, denied, _ = cli(root, opts)
    denied_rpc = asyncio.run(rpc(root, request, tmp_path / "denied.log"))
    assert (code, denied["status"], denied_rpc["status"]) == (0, "skipped", "skipped")
    assert not marker.exists()
    assert not (root / ".rush").exists()
    code, left, _ = cli(root, [*opts, "--allow-build", "--allow-slow", "--allow-artifact-write"])
    right = asyncio.run(rpc(root, {**request, "allow_build": True, "allow_slow": True,
        "allow_artifact_write": True}, tmp_path / "granted.log"))
    def project(result):
        return result["status"], [(f["path"], f["line"], f["rule"], f["severity"]) for f in result["findings"]], result["metadata"]["evidence_source"]
    assert code == 1
    assert project(left) == project(right) == (
        "fail", [(str(root / "app.py"), 2, "py/test-flow", "error")], "executed-analysis"
    )
    assert left["metadata"]["query_pack_digest"] == right["metadata"]["query_pack_digest"]
    calls = [json.loads(line) for line in marker.read_text().splitlines()]
    assert [a[:2] for a in calls] == [
        ["version", "--format=json"], ["resolve", "languages"], ["database", "create"], ["database", "analyze"],
        ["version", "--format=json"], ["resolve", "languages"], ["database", "create"], ["database", "analyze"],
    ]
    for arguments in calls:
        if arguments[:2] == ["database", "analyze"]:
            assert "--no-default-compilation-cache" in arguments
            cache = Path(next(a.split("=", 1)[1] for a in arguments
                              if a.startswith("--compilation-cache=")))
            assert cache.is_relative_to(root / ".rush")
            assert not cache.is_relative_to(pack)
```

Foreign server cwd test registers project with real project route, uses explicit project and relative `query_pack='packs/security'`, compares canonical approved pack/digest to CLI from root. Negative `../pack`, internal symlink, absolute external pack, same-name pack with altered bytes, remote `owner/pack@version` string all error with zero DB children. Missing declared project/root uses existing exact Phase 70 error, no fallback to server cwd. `report_path` import remains no writes. JSON results assert all new schema properties, exact defaults and strict int/grant types.

### Constraints

No general invocation or schema refactor. Preserve T16 compact grant before spawn/store, no-cache conflict, full-result retrieval/no engine rerun. Status aggregation `error>fail>warn>skipped>ok`, mixed assessed/skipped warn; no guessed consumed count. T27 JSON untruncated, human 50-findings cap and copyable full JSON route remain shared.

### Checks to run before reporting

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_codeql.py tests/test_codeql_transport.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase60_characterization.py tests/test_phase70_result_trust.py -q
```

### Completion

Actual CLI and initialized MCP hit shared implementation, import/execute/denied exact projections and effects match, foreign-cwd pack anchoring is correct, published schema and docs describe implemented pipeline.

## Q3 — Query-witness reduction proposal

### Required behavior

Accept `minimize_alert` as index into flattened CodeQL thread-flow sequence: runs/results/codeFlows/threadFlows in SARIF order, include only threads with at least two valid locations; return index and original run/result/flow/thread coordinates. Selected fresh baseline flow must reproduce in pinned isolated CodeQL before reduction. Python endpoints in same file are supported; other language/cross-file/nested class unsupported shapes return `metadata.query_witness.minimality='inconclusive'`, reason `syntax_adapter_unavailable`, preserving baseline result. This is explicit capability boundary from audit, not pretending unsupported analysis succeeded.

No LLM chooses reduction. New agent-side operation maintains source/pack identities, executes candidate edits in isolation, observes exact query result, retains only reductions reproducing same flow and returns bounded evidence. Ordinary linter/CLI invocation does not provide minimal source witness with query oracle. No security fix or global minimum claim.

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

### Concrete candidate and identity design

`codeql_trial_runtime(...)` validates explicit absolute runtime and entrypoint, pinned image, timeout1..600 before any test; baseline pipeline still requires Q1 grants/options. Actual image must contain CodeQL matching baseline CLI version and bundle digest, Python extractor and approved local dependency closure. Probe image CodeQL version and bundle before candidates, mismatch→inconclusive `engine_identity_mismatch`; no image download/build. Q20 calls P0 with fixed `resource_profile='analysis'` (8GiB RAM,2CPU,256PIDs); analyzer argv adds `--ram=6144 --threads=2`, keeping headroom below container cap. [GitHub's resource guidance](https://docs.github.com/en/code-security/reference/code-scanning/codeql/hardware-resources-for-codeql) recommends at least8GB/2cores for small projects and14GBSSD capacity. Acceptance host/image VM must supply those resources and free disk; runtime OOM/timeout remains inconclusive, never minimality proof. This fixed profile replaces infeasible illustrative512MiB cap for CodeQL without exposing arbitrary resource controls.

`codeql_flow_ids(root,sarif_path)` verifies fresh CodeQL SARIF, bounded regular report and physical source containment. Decode `file://` only for `/work/` or actual contained root; reject network authorities/URLs/traversal. Resolve artifact index references through each SARIF run's `artifacts` array; resolve `originalUriBaseIds` only when contained. Each endpoint identity is `(relative_path, original_startLine, original_startColumn, original_endLine, original_endColumn, sha256(exact source-region bytes))`. Missing required line/invalid column/out-of-range region→inconclusive `flow_location_incomplete`; do not guess first/last file line. Preserve exact selected ruleId; query pack digest/CLI bundle identity separately bound.

`function_occurrences(source,protected_ranges)` walks only top-level FunctionDef/AsyncFunctionDef; occurrence ID `<name>@<first-line>`, span includes decorators. Source/sink containing top-level functions protected; other functions candidates. Reject overlapping spans, wildcard dynamic source rewriting, syntax errors and module-level endpoints as `syntax_adapter_unavailable` rather than inventing a body. Preserve imports/top-level statements/classes. Rendering removed functions replaces every character except newline in each span with spaces; line count and original endpoint offsets remain stable, avoiding audit's shifting-line identity ambiguity and orphan decorators. Parse rendered Python AST before invocation. Whitespace-only eliminated functions are semantically absent; duplicate names remain distinct occurrence IDs.

`isolated_codeql_candidate(project,query_pack,runtime,*,deadline)` creates fresh private output dir, source stage is read-only; calls P0 database create with `/out/database --language=python --source-root=/work --common-caches=/out/codeql-cache`, then P0 analyze same database `/work/<pack-rel>` with same vendored closure, `--common-caches=/out/codeql-cache --no-default-compilation-cache --compilation-cache=/out/compilation-cache --ram=6144 --threads=2`, SARIF flags and fresh `/out/results.sarif`. Both calls explicitly pass `resource_profile='analysis'`, same output directory and default container HOME=/out. Each phase timeout `min(600,deadline-time.monotonic())`, reject exhausted deadline before spawn. No candidate database reuse. Validate phase exits, database metadata, report provenance and parse exact flows. Errors raise, never return false predicate. Record each candidate source hash, pack digest, phase exits and report SHA; save retained witness source/report under original owned baseline run only after containment and source-drift recheck. Recompute pack tree digest after each analyze and compare to pre-run digest; mismatch is infrastructure error, never a preserving predicate result.

`codeql_witness_trial` copies only regular contained source/config/query closure to private stage, excludes `.git/.rush/.venv/node_modules/.env/.env.*`; never follows symlinks. No source or test in original project modified. Baseline selected flow is first reproduced in isolated unchanged copy. Remaining function deletion sequence is source order, deterministic. Max20 evaluations includes baseline; `trial_timeout_seconds` is total trial wall-clock budget, not 20×600. Infrastructure error→inconclusive and no minimality label. Budget exhaustion→budget_limited with current reproducing candidate only; baseline not reproduced→baseline_not_reproduced, no reduced source claim. Final no-preserving single-deletion sweep yields one_deletion_minimal over enumerated unprotected function occurrences only. Nonmonotonic predicates restart sweep after every accepted deletion.

### Minimum GREEN reducer core and runnable behavioral unit

Add `minimize_units` to `src/rush/tools/codeql.py`; callback is actual Q3 candidate pipeline in production, deterministic callback only in its controller unit. Full control code:

```python
def minimize_units(units, preserves_flow, *, max_attempts=20):
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("invalid_budget")
    current = list(units)
    if len(set(current)) != len(current):
        raise ValueError("duplicate_occurrence_id")
    attempts = 1

    def result(state):
        return {"units": list(current), "minimality": state, "attempts": attempts}

    if not preserves_flow(current):
        return result("baseline_not_reproduced")
    while True:
        for index in range(len(current)):
            if attempts == max_attempts:
                return result("budget_limited")
            candidate = current[:index] + current[index + 1:]
            attempts += 1
            if preserves_flow(candidate):
                current = candidate
                break
        else:
            return result("one_deletion_minimal")


def test_minimizer_restarts_and_keeps_required_flow():
    calls = []

    def flow(units):
        calls.append(tuple(units))
        return "sql_concat@4" in units

    result = minimize_units(["helper@1", "sql_concat@4", "log@7"], flow)
    assert result == {"units": ["sql_concat@4"], "minimality": "one_deletion_minimal", "attempts": 5}
    assert calls == [
        ("helper@1", "sql_concat@4", "log@7"), ("sql_concat@4", "log@7"),
        ("log@7",), ("sql_concat@4",), (),
    ]
    assert minimize_units(["a@1", "b@2"], lambda _: True, max_attempts=2) == {
        "units": ["b@2"], "minimality": "budget_limited", "attempts": 2
    }
```

Test imports production `minimize_units` rather than redefining it in final test module. Exceptions from `preserves_flow` propagate to command wrapper's explicit inconclusive infrastructure state; they are never interpreted as “flow disappeared”. Test custom exception verifies this. This unit is one bounded algorithm test, not evidence of real CodeQL/OCI.

### Q1-owned genuine query fixture, reused by Q3

Exact fixtures belong Q1 command owner. Q3 reuses them without redefining or weakening Q1 acceptance. `tests/fixtures/codeql/witness.py`:

```python
def helper():
    return 7

def request():
    return input()

def sql_concat(value):
    return "select " + value

def execute(value):
    return eval(value)

def log():
    return 0

execute(sql_concat(request()))
```

Use real CodeQL Python data-flow query, not file-text-presence oracle. Q1's complete `materialize_codeql_fixture` above builds temporary root manifest, full lock and vendored closure from independently hash-pinned local libraries, validates exact transitive versions and compiles this query. The source `codeql/python-all` manifest legitimately declares `extractor: python` ([upstream manifest](https://github.com/github/codeql/blob/main/python/ql/lib/qlpack.yml)); that literal is allowed, path-valued/other extractor overrides are rejected. No prebuilt-pack environment assumption or runtime download remains. Fixture compilation is mandatory Q1 acceptance; witness reduction remains separately proposed Q3 behavior.

`tests/fixtures/codeql/pack/flow.ql` exact source:

```ql
/**
 * @name Rush witness fixture flow
 * @description Fixture input reaches eval through a concatenation helper.
 * @kind path-problem
 * @problem.severity error
 * @id py/rush-witness-flow
 */
import python
import semmle.python.dataflow.new.DataFlow
import semmle.python.dataflow.new.TaintTracking

module Config implements DataFlow::ConfigSig {
  predicate isSource(DataFlow::Node source) {
    exists(Call c | c.getFunc() instanceof Name and
      c.getFunc().(Name).getId() = "input" and source.asExpr() = c)
  }
  predicate isSink(DataFlow::Node sink) {
    exists(Call c | c.getFunc() instanceof Name and
      c.getFunc().(Name).getId() = "eval" and sink.asExpr() = c.getArg(0))
  }
}
module Flow = TaintTracking::Global<Config>;
import Flow::PathGraph
from Flow::PathNode source, Flow::PathNode sink
where Flow::flowPath(source, sink)
select sink.getNode(), source, sink, "Fixture input reaches eval."
```

Query API must compile under recorded local CodeQL version/library before runtime acceptance; compile failure is concrete prerequisite incompatibility, not permission to replace query with text search. Planning did not execute this QL or verify an installed CodeQL bundle. Runtime acceptance begins with Q1's exact `query compile` command including additional-packs, owned common/compilation caches, `--no-default-compilation-cache`, `--no-precompile`, RAM and thread limits through trusted resolved binary; exact same unchanged pack then used for baseline and all candidates.

Primary API grounding: CodeQL's [Python data-flow guide](https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-python/) documents `DataFlow::ConfigSig`, `TaintTracking::Global` and `PathGraph`; [database-analyze reference](https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/database-analyze) documents fresh SARIF output and additional local packs. These references ground proposed interfaces; they do not prove fixture compilation or execution on this machine.

Proposed complete Q3 runtime test body in `tests/test_codeql.py` (imports and materializer defined in Q1):

```python
def test_alert_minimizer_keeps_same_source_sink_flow(tmp_path: Path):
    import hashlib
    import os

    for key in ("RUSH_CODEQL_TEST_RUNTIME", "RUSH_CODEQL_TEST_IMAGE", "RUSH_CODEQL_TEST_ENTRYPOINT"):
        assert os.environ.get(key), "required local runtime fixture: " + key
    root = tmp_path / "project"
    pack, expected_pack_digest, _ = materialize_codeql_fixture(root)
    before = hashlib.sha256((root / "witness.py").read_bytes()).hexdigest()
    result = CodeqlTool().run(
        root, language="python", query_pack=pack, minimize_alert=0,
        isolation_runtime_path=os.environ["RUSH_CODEQL_TEST_RUNTIME"],
        codeql_image_ref=os.environ["RUSH_CODEQL_TEST_IMAGE"],
        codeql_entrypoint=os.environ["RUSH_CODEQL_TEST_ENTRYPOINT"], trial_timeout_seconds=600,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "fail", result
    witness = result["metadata"]["query_witness"]
    assert witness["minimality"] == "one_deletion_minimal", witness
    assert witness["rule"] == "py/rush-witness-flow"
    assert "def helper" not in witness["minimal_source"]
    assert "def log" not in witness["minimal_source"]
    assert all("def " + name in witness["minimal_source"] for name in ("request", "sql_concat", "execute"))
    assert witness["query_pack_digest"] == result["metadata"]["query_pack_digest"]
    assert witness["query_pack_digest"] == expected_pack_digest
    from rush.tools.codeql import pack_tree_digest
    assert pack_tree_digest(pack) == expected_pack_digest
    assert witness["attempts"] == len(witness["ledger"])
    assert all([p["name"] for p in item["phases"]] == ["database_create", "database_analyze"] for item in witness["ledger"])
    for item in witness["ledger"]:
        analyze_argv = item["phases"][1]["argv"]
        assert "--no-default-compilation-cache" in analyze_argv
        assert "--compilation-cache=/out/compilation-cache" in analyze_argv
    assert hashlib.sha256((root / "witness.py").read_bytes()).hexdigest() == before
    assert not (root / "database").exists()
```

This test runs genuine queries in genuine isolation; no monkeypatched oracle/launcher. Source and image bundle identities must match. Run baseline CLI/MCP actual execution with same fixture too. Missing binaries, image, dependencies or resource capacity remains failed prerequisite; no auto install, fake provider, skipped-success or altered fixture to force PASS.

### Deliverables, constraints, checks and completion

Q3 command files/helpers specified above; no additional framework or cross-command provider. Top-level result preserves baseline findings/severity and metadata; witness nested `{minimality,reason?,attempts,rule,source_sink,query_pack_digest,minimal_source,ledger}`. Budget-limited source returned only if last retained candidate actually reproduced. Inconclusive never carries one-deletion claim. Cleanup failure is top-level error `isolation_cleanup_failed`, not inconclusive success.

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_isolated_process.py tests/test_codeql.py::test_minimizer_restarts_and_keeps_required_flow tests/test_codeql.py::test_alert_minimizer_keeps_same_source_sink_flow -q
```

Complete only when real query preserves exact rule/endpoints/pack after removing helper/log, all retained removable-function deletions fail to preserve flow, baseline remains unchanged, containers reaped, unsupported/budget/infrastructure states honest. Proposal implementation is distinct from Q1 repair authorization.

## Adversarial matrix, recovery and stop conditions

`tests/test_codeql.py` exact cases: version-only executable fails database create→error with steps version0/resolve0/create2; malformed version→skipped incompatible; missing executable→skipped missing; no source→skipped; missing path→error; ambiguous auto-language→error with candidates; absent/remote/unlocked/escaping/symlink/changed pack→error; denied any required grant→skipped zero children/state; create0 but database absent→error; analyze0 but missing/foreign/nonobject/oversized/malformed SARIF→error; SARIF warning/error/note preserve warn/fail/ok; engine crash/timeout→error with completed phase ledger; changed binary/source/config→error; partial report not consumed; import clean runs[] invalid vs CodeQL results[] valid. No toy status arithmetic as evidence.

Q3 cases: duplicate occurrence IDs rejected; decorated function removal does not leave decorator; protected endpoints stable; repeated names distinguished; module/cross-file endpoint unsupported explicit; URI percent-encoding and artifact-index lookup preserve containment; query mismatch or library drift inconclusive; missing baseline flow baseline_not_reproduced; max2 budget limited after one evaluated reduction; error/timeout not false predicate; no network and no host writes in real OCI probe; cancel and cleanup failure state exact. A no-alert baseline with `minimize_alert=0` gives actionable `unknown_flow_alert`, not empty verified witness.

Recovery uses owned unique run directories and stage-only edits; preserve existing report/database/source. Keep completed evidence for failed run with incomplete flag; never reuse failed DB. Cleanup only owned containers and temporary directories; failure records container ID for manual recovery, never hides it. Source/plan drift invalidates readiness and affected checks. No source edits during planning; no commits, pushes, releases or PR publication authorized here.

## Final checks and completion

### Literal shared documentation delta and check ownership

Batch integration owner additionally owns `docs/CONFIGURATION.md` (exact tracked case), `examples/rush.toml`, `docs/reference/cli-reference.md`, `docs/MCP_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`, `docs/reference/configuration-reference.md`, `docs/reference/result-reference.md`, `scripts/sync_docs.py` and `docs/reports/phase-64-66-documentation-coverage.md`. All exist in source checkout. This completes the short ownership list above; one serialized writer Q11→Q20, preserving every unrelated command entry.

Exact Q20 delta: replace existing CLI `codeql PATH` row and execution paragraph with importer versus fresh database analysis, explicit language/local query pack/build command rules, required build+slow+artifact-write, local dependency requirements, no hidden download and error/recovery examples. Add exact callable arguments/defaults to `rush_codeql` catalog entry in `docs/MCP_REFERENCE.md` and detailed schema/example in `docs/reference/mcp-tool-reference.md`, sourced from actual initialized `tools/list`, preserving tool identity/count. Existing configuration docs/example receive only optional `[tools.codeql] language='python'`; no approved pack, executable/image/build command or grant from project config. Result reference receives imported-local-report versus executed-analysis, real findings/severity, source/config/query closure digests, per-step ledger and truthful consumed-scope limits. Include one successful no-finding real analysis, one fixture error-severity result, one missing-pack actionable error and one zero-effect denied example with exact CLI exit. Q3 witness fields/options remain marked separately proposed until authorized and implemented; no public claim from unexecuted minimizer.

`scripts/sync_docs.py::main` is an existing check-only entrypoint requiring `--check`. It does not generate references. Integration owner edits only changed command sections and corresponding existing receipt evidence/source hashes/contract facts in `docs/reports/phase-64-66-documentation-coverage.md`, using its current schema. No new documentation generator. Mandatory proposed Q1/Q2 verification, independent of Q3:

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_codeql.py::test_real_q1_analysis_without_minimizer tests/test_codeql_transport.py::test_real_q1_cli_stdio_analysis_without_minimizer tests/test_cli_registry.py tests/test_mcp.py -q
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check
```

Doc check expected exit0 and `Documentation coverage and runtime contracts match.`; genuine query tests hard-fail absent library hash/closure/compiler instead of silently skipping. These are future acceptance commands, not present planning-pass claims.

Future commands run from implementation worktree based on source baseline, Python3.12, inherited PYTHONPATH cleared:

```text
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_codeql.py tests/test_codeql_transport.py tests/test_codeql_importer.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase60_characterization.py tests/test_phase70_result_trust.py tests/test_subprocess_contract.py -q
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff format --check src tests scripts
```

Planning observed current-callable version-only false success and existing combined importer tests (24 passed). No new pipeline, QL compilation, live CodeQL/OCI witness, new public options or future checks were executed. Development readiness depends on frozen substantive coordinator review; real runtime asset absence is an explicit acceptance-environment prerequisite, never proof analysis works. Future command-focused PR order: Q1 actual pipeline; Q2 literal transport/docs integration; Q3 separately identified proposal after shared P0. No additional deliverable, worktree, commit or PR created by this plan.
