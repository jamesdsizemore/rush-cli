Implement Q03 full scope in rush-cli when implementation authorized.
Read AGENTS.md, docs/templates/task-block-template.md, README.md,
00-shared-foundation.md and exact audit/report first.

# Feature: Honest format checks contained preview/apply and isolated verification

Return honest formatter coverage, digest-bound contained preview/apply and source-bound isolated test verification through shared CLI/MCP tools.

Authorization: plan remediation only; production patches/tests below proposed,
unimplemented/unexecuted here. No commit/push/release.
Source revision: 66c6c799eaa5b6017776d659e9e0de2b4a8878a5.
Audit source c78e445ba1e575ca373e35840142cd627b055d6a only.
Binding audit docs/reports/cli-mcp-command-audit-2026-09-26.md, SHA256
8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.
Binding report docs/reports/command-tdd-2026-10-01-plan-remediation.md:
Q03, applicable X/M and C01–C29 (binding C overrides).
Scope Q01–Q10 only; next batch needs user approval.
Provenance GPT6.1 Sol/high, owned plan only.

## Required behavior

1. Default check=True direct/CLI/MCP; false error/error.code unsupported_operation,
   zero formatter/source writes. Handwritten cli.py::format paired --check/
   --no-check, never catalog builder format.
2. Ruff/Prettier explicit selected_targets, one operand/check, project cwd and
   shared staging. Q02 owner applies Ruff format branch after R1; Q03 consumes.
3. Child engines/scope/assessed_paths, no local aggregate override; partial
   warn (D5 proposal) names skipped engine, never all formatted. Prettier3
   stderr [warn] files and legacy stdout yield findings; rc1 no readable listing error,
   rc>=2 error. No targets/all unavailable skipped.
4. check|preview|apply mode default check. Artifact-write required preview/
   apply. Shared Q03-STDIO preserves exact captured bytes through owned runners. Canonical .rush/format-previews records/id SHA256 bind source/output/
   path/config/version. Nonempty selected_files and preview_id for apply;
   all containment/duplicates/source/output/config/version preflight before
   first write. Atomic per-file mode preservation. Second-write OSError:
   first actual changed path/hash, partial_write=true, no rollback claim.
5. verify_preview_id only check mode, unique nonempty selected test nodes.
   Build/slow denied whole call skipped before ordinary check, execution.cause
   permission_denied, preview_verification denied, zero sandbox/test launches.
   Isolated preview sandbox, Python AST without trivia, F5 selected pytest.
   AST change/fail/error => rejected; skipped/empty => inconclusive;
   current source drift stale_preview; runtime missing skipped reason
   isolation_unavailable. eligible only same AST/current digests/nonempty
   all-passing counts, zero skipped/error, factual preview-bound receipts.
## Phase70 reconciliation and shared contracts

Implementation base: phase/70-agent-adoption-and-usability at
66c6c799eaa5b6017776d659e9e0de2b4a8878a5. c78e445 is audit grounding only.
Phase70 T1–T29/G0–G8 acceptance is required before implementation; clean Git
or commit identity is not acceptance. Copy binding audit/plans byte-identically
or commit only under separate explicit authorization before packets start.

Foundation owner alone applies shared-file patch rows. F1 strict models use
wrapper public_sig, accept project/result_view/limit/max_bytes/no_cache/
allow_cache_write, publish flat properties/additionalProperties=false,
required=[path], no operation/schema_version. Strict MCP rejection:
isError=false, status=error, raw.error.code=INVALID_REQUEST, zero dispatch.
Public generated models use StrictBool allow_*; __call__ takes bool allow_* and builds ExecutionPermissions once;
run receives permissions:ExecutionPermissions|None. Executor already binds
allow_* from context.permissions; no permission rewrite or config coercion.

metadata.engines records child engines; metadata.scope v1 records coverage.
Lint/format metadata.assessed_paths={engine:[paths]}, skipped child => [].
No new tool-owned metadata.children/metadata.partial/metadata.aggregation in
lint/format. Review existing aggregation retained; workflow children and
error_result terminal_reason/partial retained. aggregate_status governs:
report D5 proposal ok+skipped=warn, CLI exit 1; no local skipped override.
CLI exits ok/skipped=0, warn/fail=1, error=2. Invalid argument carrier:
metadata.error={code:invalid_argument,message:summary}. Pre-dispatch MCP uses
raw.error.code=INVALID_REQUEST instead.

W18 = audit Command 45/79 rush_mem_profile isolation contract 13810–13889;
Foundation F4 implements provider under README D1. IsolatedRun has returncode,
stdout,stderr,process_launches,receipt. Signature:
run_isolated_argv(root,scratch,*,runtime_path,image_ref,entrypoint,argv,
timeout_s,workdir_rel=".",environment=None,max_process_launches=None,
scratch_on_pythonpath=False).
LaunchBudgetExhausted.process_launches counts launches before next refused.
runtime_path absolute-only, never CLI abspath or _CWD_RELATIVE_ARGS.
F4 check_isolation_inputs(root,*,runtime_path,image_ref) launches nothing;
runtime errors raise IsolationUnavailable first, malformed image ValueError
second. D10 runtime proposal supplied docker/podman final name, symlink target
name irrelevant, resolved regular executable owned root/current user, no
group/world write, supplied directory and realpath outside root, POSIX.
Provider read-only source/private writable scratch, no network, capability/
privilege/resource/time/output bounds, owned cleanup and factual receipts.
No host fallback. Missing runtime block skipped/reason isolation_unavailable
under unapproved D6 proposal, no fake successful isolation.

F5 run_selected_tests_isolated(root,scratch,*,nodes,runtime_path,image_ref,
python_entrypoint,timeout_s,max_process_launches=None,extra_pytest_args=(),
scratch_on_pythonpath=False) returns SelectedTestRun(outcome,counts,argv,
process_launches,isolated). pytest argv -m pytest -q --tb=line; outcomes
passed/failed/no_tests/error; counts passed/failed/skipped/error from final
summary, missing summary error. Nodes unique/nonempty/contained/no options/
NUL. F6 tests/transport_parity.py provides real CLI/stdio and real-file errlog;
never duplicate helper across command test files.

oci_isolation marker: unset RUSH_TEST_OCI_RUNTIME deselects, never skips.
Runtime set: every live test asserts own present/digest-pinned image. F4 CI
provisions Python/Rush/compiler images, exports all four variables, runs
pytest tests -m oci_isolation -q. Image owner README D11 unresolved. R/E
checks exclude provider-created modules until F4; X1 requires live OCI CI PASS.
ToolSpec.discovery single source in catalog, CLI help and MCP path schema;
mcp_description remains 20–199 chars with Phase70 phrases.

Shared requested baseline remains full scope: scanner provisioning, connected
specialist local models, selectable voice/live speech, 3D companion. Never
count these as command innovation.

## Decisions for James

Applicable README D1–D12 choices remain unapproved; report defaults in code
are conditional proposals, not decisions. D3 permissions, D5 aggregate warn,
D8 mypy src/rush remains an explicit proposal. Q03 also consumes
D1, D2, D4, D6, D10 and D11; D4 timeout=300 versus 180. References are to
X-D1/X-D2/X-D3/X-D4/X-D5/X-D6/X-D8/X-D10/X-D11 in the shared decision
register; change dependent code/tests/docs uniformly after an approved choice.
DECISION-Q03-B remains the report's explicit-selection proposal deviation:
apply requires selected_files instead of the audit's implicit-all default.
Verification-key rename and nonempty verification_tests are recorded contract
deviations below, not additional invented approval gates. Configuration closure
and source identity are concrete safety implementation obligations.

## Deliverables

Command owner literal paths: src/rush/tools/format.py;
src/rush/engines/prettier.py; src/rush/runtime/filesystem.py;
new tests/test_format.py; tests/test_format_parity.py;
tests/test_prettier_honest.py; tests/test_format_oci.py.
Q03-R1-CLI, Q03-E1-CLI and Q03-X1-CLI Foundation rows exact handwritten cli.py::format
decorators/forwarding. Q03-MCP-containment row selected_files validation;
runtime_path NEVER anchored. Runtime target plumbing is a Foundation-owned revised Q02 prerequisite; Q03-STDIO owns the additional shared runner/gate row.
Foundation Q03-SCOPE fixes staged runtime identity comparison. Ruff Q03-M2 below goes Q02 owner after R1; Q03 never writes Ruff.
All exact docs below Foundation F8 rows Q03-DOC-reference, Q03-DOC-guides, Q03-DOC-results, Q03-DOC-receipts, including references,
CHANGELOG/receipt. Q03 no ADR; immutable bodies/index untouched.

## Constraints

Planning-only current authorization. No production/test/shared-doc writes,
commit/push/release/version/hook/install. Source and tests below proposed,
unimplemented/unexecuted here. Preserve unrelated user edits. Reuse adapters,
PhysicalRoot.open_contained (returns Path), atomic_write_bytes, grants/routing.
No invented API/model executable source/local isolation fallback/simulated PASS.
R/E/X each needs own evidence; repair PASS never closes extensions/expansion.

## Ordered tasks

1. Foundation F1/F2/F3/F6 first; corrected Q02 selected-targets before Q03. Foundation Q03-STDIO before E1 preview and Q03-SCOPE before staged R/E checks; F4/F5 are X1-only dependencies.
2. Named R/E RED bodies against Phase70, exact failure, minimum GREEN,
   same acceptance and affected regressions. Preserve memory/staging/contracts.
3. X1 after F4/F5/live-image prerequisites; Q02 Ruff-only has no OCI dependency.
4. Exact user docs and F8 receipt/contracts same packet, serialized Foundation.
5. Freeze final bytes; checks below; R/E/X reconciled separately.

## Concrete implementation packets

Every packet is proposed source/test/doc specification, not an applied patch.
Draft line numbers below record superseded draft placement only. Code with
shared targets is exact Foundation patch-row content, applied by Foundation
owner; no second writer. Review report's earlier local-override/status/ownership
text is superseded by canonical code here, not retained as an alternative.

### Q03-01: CLI owner is `cli.py::format`, not the catalog builder

replace plan :224-226 with:
```text
Foundation owns shared selected_targets plumbing consumed from revised Q02 (Q03-07).
Foundation row Q03-R1-CLI owns the handwritten Click command src/rush/cli.py::format (C cli.py:386-421; P cli.py:607-647).
The catalog builder skips "format" (C cli.py:1628-1639; P cli.py:2177-2191), so src/rush/catalog.py and
src/rush/cli_support/catalog_commands.py are NOT edited for format options. The CLI patch is below
(stage A), plus the X1 additions. Existing `--check` invocations in docs and CI stay valid.
```
and replace :318-319 with:
```text
Replace the existing `--check` is_flag in src/rush/cli.py::format with paired `--check/--no-check`
(default True); `--no-check` is accepted by Click and returns error/unsupported_operation from the tool.
```
Foundation rows Q03-R1-CLI (paired check flag/forwarding) and Q03-E1-CLI (mode/preview/selected-file flags/forwarding), exact stage-A patch to `src/rush/cli.py` (against Phase70; proposed, unexecuted):
```diff
--- a/src/rush/cli.py
+++ b/src/rush/cli.py
@@ -609,3 +609,21 @@
 @click.option(
-    "--check", "check_only", is_flag=True, help="Only check; don't modify files."
+    "--check/--no-check",
+    "check",
+    default=True,
+    show_default=True,
+    help="Check only (default). --no-check is rejected; write with --mode apply.",
+)
+@click.option(
+    "--mode",
+    type=click.Choice(["check", "preview", "apply"]),
+    default="check",
+    show_default=True,
+    help="check reports; preview stores a digest-bound preview; apply writes selected files.",
+)
+@click.option("--preview-id", "preview_id", default=None, help="Preview to apply.")
+@click.option(
+    "--selected-file",
+    "selected_files",
+    multiple=True,
+    help="File (relative to the target root) to apply; repeatable.",
 )
@@ -616,3 +634,6 @@
     path: Path,
-    check_only: bool,
+    check: bool,
+    mode: str,
+    preview_id: str | None,
+    selected_files: tuple[str, ...],
     allow_network: bool,
@@ -644,3 +665,8 @@
         permissions=perms,
-        extra_kwargs={"check": check_only} if check_only else None,
+        extra_kwargs={
+            "check": check,
+            "mode": mode,
+            "preview_id": preview_id,
+            "selected_files": list(selected_files) or None,
+        },
         view=ViewOptions(result_view, limit, max_bytes),
```
Foundation Q03-X1-CLI addition (applies after the stage-A patch; proposed, unexecuted):
```diff
--- a/src/rush/cli.py
+++ b/src/rush/cli.py
@@ -628,4 +628,29 @@
     help="File (relative to the target root) to apply; repeatable.",
 )
+@click.option(
+    "--verify-preview-id",
+    "verify_preview_id",
+    default=None,
+    help="Verify this preview in an isolated checkout (needs --allow-build --allow-slow).",
+)
+@click.option(
+    "--verification-test",
+    "verification_tests",
+    multiple=True,
+    help="Test id to run for verification; repeatable.",
+)
+@click.option(
+    "--runtime-path",
+    "runtime_path",
+    type=click.Path(path_type=Path),
+    default=None,
+    help="Absolute path of the approved OCI runtime.",
+)
+@click.option(
+    "--image-ref",
+    "image_ref",
+    default=None,
+    help="Digest-pinned image reference (name@sha256:<64 hex>).",
+)
 @permission_options
 @click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
@@ -637,4 +662,8 @@
     preview_id: str | None,
     selected_files: tuple[str, ...],
+    verify_preview_id: str | None,
+    verification_tests: tuple[str, ...],
+    runtime_path: Path | None,
+    image_ref: str | None,
     allow_network: bool,
     allow_download: bool,
@@ -669,4 +698,8 @@
             "preview_id": preview_id,
             "selected_files": list(selected_files) or None,
+            "verify_preview_id": verify_preview_id,
+            "verification_tests": list(verification_tests) or None,
+            "runtime_path": runtime_path,
+            "image_ref": image_ref,
         },
         view=ViewOptions(result_view, limit, max_bytes),
```
Do not add the X1 hunk before `FormatTool` accepts those kwargs (Q03-04, X1 diff).

Verification requirement: original report Q03-01 at line 3431; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-02: Phase 70 T16 already owns format aggregation; ok+skipped is `warn` there

Use routing.aggregate_status per X-D5: report proposal ok+skipped warn, CLI exit 1, option b changes routing globally; FormatTool no override. Emit engines/scope/assessed_paths. Clean Ruff/missing Prettier=>warn, partial coverage, {ruff:[absolute logical a.py],prettier:[]}, summary names missing engine.

Verification requirement: original report Q03-02 at line 3556; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-03: `atomic_write_bytes` resets the mode of a rewritten file to 0600

insert into plan "Required behavior" after :207:
```text
Mode preservation (required): apply records each selected file's stat.S_IMODE during preflight and writes
through atomic_write_bytes(root, relative, data, mode=original_mode). format.py imports
`atomic_write_bytes` from `.common`. Tests: tests/test_format.py::test_apply_preserves_file_mode and
::test_atomic_write_bytes_mode_default_unchanged_and_mode_applied. Existing callers pass no mode and keep 0600.
```
Patch to `src/rush/runtime/filesystem.py` (against Phase70; proposed, unexecuted):
```diff
-def atomic_write_bytes(root: Path, relative: str | Path, data: bytes) -> Path:
-    """Write bytes atomically to a contained target path, replacing any existing file."""
+def atomic_write_bytes(
+    root: Path, relative: str | Path, data: bytes, *, mode: int | None = None
+) -> Path:
+    """Write bytes atomically to a contained target path, replacing any existing file.
+
+    `mode` (permission bits, e.g. 0o755) is applied to the replacement before it
+    swaps in; omitted, the new file keeps the temp file's private 0o600."""
@@
             raise ValueError("Symlinks forbidden during atomic replacement")

+        if mode is not None:
+            os.chmod(temp_path, mode)
         os.replace(temp_path, target)
         return target
```
The two tests are in Q03-12.

Verification requirement: original report Q03-03 at line 3599; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-04: No production patch anywhere; audit source artifacts dropped

add a plan section "## Proposed production patch" with the following, labeled "proposed; implementation unexecuted in this remediation".

Proposed src/rush/tools/format.py complete R/E/X source with binding C contracts:

```python
"""Format tool -- engine dispatch per file extension.

Architecture §4.3 + §10. ruff format (Python) and prettier (JS/TS + JSON/MD/YAML/CSS/HTML).

`mode="check"` (default) never mutates files: both engines always run in check mode.
`mode="preview"` stores digest-bound formatted bytes under `.rush/format-previews/`.
`mode="apply"` rewrites only explicitly selected files whose bytes still match that
preview. Verification of a preview runs selected tests inside the W18 OCI provider.
"""

from __future__ import annotations

import ast
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..permissions import (
    ExecutionPermissions,
    build_execution_metadata,
    check_permissions,
)
from .base import ToolFn, ToolName, ToolResult, ToolStatus
from .common import (
    atomic_write_bytes,
    elapsed_ms,
    error_result,
    now_ms,
    resolve_binary,
    run_engine,
    run_subprocess,
    skipped_result,
)
from .routing import (
    aggregate_scope,
    aggregate_status,
    child_scope,
    collect_files,
    concat_engine_entries,
    no_target_scope,
)

_PREVIEW_DIR = ".rush/format-previews"
_PREVIEW_ID = re.compile("[0-9a-f]{64}")
_PYTHON_SUFFIXES = (".py", ".pyi")
_CONFIG_FILES = (
    "pyproject.toml",
    "ruff.toml",
    ".ruff.toml",
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.yaml",
    ".prettierrc.yml",
    ".prettierrc.toml",
    ".prettierrc.js",
    ".prettierrc.cjs",
    ".prettierrc.mjs",
    "prettier.config.js",
    "prettier.config.cjs",
    "prettier.config.mjs",
    "package.json",
    ".editorconfig",
)


def _invalid(message: str, code: str = "invalid_argument") -> ToolResult:
    result = error_result("format", None, message)
    result.setdefault("metadata", {})["error"] = {
        "code": code,
        "message": result["summary"],
    }
    return result


def _apply_error(code: str, message: str) -> ToolResult:
    result = _invalid(message, code)
    result["metadata"].update(mode="apply", changed_paths=[], partial_write=False)
    return result


def _grant_denied(
    required: ExecutionPermissions, granted: ExecutionPermissions
) -> ToolResult | None:
    ok, missing = check_permissions(required, granted)
    if ok:
        return None
    flags = [
        name if name.startswith("--") else "--allow-" + name.replace("_", "-")
        for name in missing
    ]
    message = "requires permission: " + ", ".join(flags)
    result = skipped_result(
        "format",
        None,
        message,
        metadata={
            "execution": build_execution_metadata(
                "executed",
                requested=required,
                granted=granted,
                producer="format",
                extra={"disposition": "not_run", "cause": "permission_denied"},
            )
        },
    )
    result["summary"] = message
    return result


def _root(path: Path) -> Path:
    return (path if path.is_dir() else path.parent).resolve()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _formatter_versions() -> dict[str, str | None]:
    from ..engines import ENGINES

    return {name: ENGINES[name].version() for name in ("ruff", "prettier")}


def _format_input_file(root: Path, relative: str) -> Path:
    from ..engines.staging import StagingInputError, active_staging

    staging = active_staging()
    if staging is None:
        return PhysicalRoot(root).open_contained(relative)
    mapped = Path(staging.substitute_arg(str(root / relative)))
    staged_root = Path(staging.staged_root)
    if not mapped.is_relative_to(staged_root):
        raise StagingInputError("required format input was not staged")
    selected = PhysicalRoot(staged_root).open_contained(mapped.relative_to(staged_root))
    staging.record_consumption(selected)
    return selected


def _format_cwd(root: Path) -> Path:
    from ..engines.staging import active_staging

    staging = active_staging()
    if staging is None:
        return root
    mapped = Path(staging.substitute_arg(str(root)))
    if not mapped.is_relative_to(staging.staged_root):
        raise ValueError("required format cwd was not staged")
    return mapped


def _config_digests(
    root: Path, selected_paths: list[str] | None = None, *, use_staging: bool = True
) -> dict[str, str]:
    import tomllib

    from ..engines.staging import active_staging

    directories = {root}
    for relative in selected_paths or []:
        parent = (root / relative).parent
        directories.update(
            p for p in (parent, *parent.parents) if p == root or p.is_relative_to(root)
        )
    staging = active_staging() if use_staging else None
    pending = []
    for directory in sorted(directories):
        for name in _CONFIG_FILES:
            path = directory / name
            relative = path.relative_to(root).as_posix()
            staged = (
                Path(staging.staged_root) / relative if staging is not None else path
            )
            if path.is_file() or staged.is_file():
                pending.append((relative, frozenset()))
    record = {}
    visited = set()
    while pending:
        relative, ancestors = pending.pop()
        if relative in ancestors:
            raise ValueError("Ruff configuration extend cycle")
        if relative in visited:
            continue
        visited.add(relative)
        data = (
            _format_input_file(root, relative)
            if use_staging
            else PhysicalRoot(root).open_contained(relative)
        ).read_bytes()
        record[relative] = _sha(data)
        if relative.endswith((".js", ".cjs", ".mjs")) and re.search(
            rb"\b(?:import|require)\b", data
        ):
            raise ValueError("executable formatter configuration closure is unverified")
        if Path(relative).name in ("ruff.toml", ".ruff.toml", "pyproject.toml"):
            parsed = tomllib.loads(data.decode("utf-8"))
            if Path(relative).name == "pyproject.toml":
                tool = parsed.get("tool", {})
                if not isinstance(tool, dict):
                    raise ValueError("TOML tool must be a table")
                parsed = tool.get("ruff", {})
                if not isinstance(parsed, dict):
                    raise ValueError("TOML tool.ruff must be a table")
            extended = parsed.get("extend")
            if extended is not None:
                if not isinstance(extended, str):
                    raise ValueError("Ruff extend must be a string")
                target = Path(os.path.abspath(root / Path(relative).parent / extended))
                child = target.relative_to(root).as_posix()
                if use_staging:
                    _format_input_file(root, child)
                else:
                    PhysicalRoot(root).open_contained(child)
                pending.append((child, ancestors | {relative}))
    return record


def _preview_cancelled(
    granted: ExecutionPermissions,
    summary: str,
    *,
    requested: ExecutionPermissions | None = None,
) -> ToolResult:
    from ..runtime.subprocesses import _CANCEL_CHECK

    scope = _CANCEL_CHECK.get()
    if scope is not None:
        scope.hit = True
    cause = scope.cause if scope is not None else "cancelled"
    return skipped_result(
        "format",
        None,
        summary,
        metadata={
            "execution": build_execution_metadata(
                "executed",
                requested=requested or ExecutionPermissions(artifact_write=True),
                granted=granted,
                producer="format",
                extra={"disposition": "cancelled", "cause": cause},
            )
        },
    )


def _build_preview(path: Path, permissions: ExecutionPermissions) -> ToolResult:
    from ..engines import ENGINES
    from ..engines.staging import StagingInputError
    from ..runtime.subprocesses import SubprocessCancelled

    denied = _grant_denied(ExecutionPermissions(artifact_write=True), permissions)
    if denied is not None:
        return denied
    start = now_ms()
    base = (path if path.is_dir() else path.parent).absolute()
    root = base.resolve()
    sources = collect_files(
        path,
        {
            extension
            for name in ("ruff", "prettier")
            for extension in ENGINES[name].file_extensions
        },
    )
    if not sources:
        return skipped_result(
            "format",
            None,
            f"no Python/JS/TS files found under {path}",
            metadata={"scope": no_target_scope("no_supported_targets")},
        )
    records = []
    selected = [source.absolute().relative_to(base).as_posix() for source in sources]
    try:
        configurations = _config_digests(root, selected)
        versions = _formatter_versions()
        with TemporaryDirectory(
            prefix=".rush-format-input-", dir=root.parent
        ) as private:
            scratch = Path(private)
            scratch.chmod(0o700)
            for index, relative in enumerate(selected):
                before = _format_input_file(root, relative).read_bytes()
                python = relative.endswith(_PYTHON_SUFFIXES)
                binary = resolve_binary("ruff" if python else "prettier")
                if binary is None:
                    return skipped_result(
                        "format",
                        None,
                        f"{'ruff' if python else 'prettier'} not on PATH",
                        metadata={
                            "scope": child_scope(
                                "unavailable", reason="engine_unavailable"
                            )
                        },
                    )
                argv = (
                    [binary, "format", "--stdin-filename", relative, "-"]
                    if python
                    else [binary, "--stdin-filepath", relative]
                )
                input_path = scratch / f"{index}.input"
                input_path.write_bytes(before)
                input_path.chmod(0o600)
                output_path = scratch / f"{index}.output"
                proc = run_subprocess(
                    argv,
                    cwd=_format_cwd(root),
                    timeout=120,
                    stdin_path=input_path,
                    stdout_path=output_path,
                )
                if proc.returncode != 0:
                    return _invalid(
                        f"formatter preview failed: {relative}", "formatter_failed"
                    )
                formatted = output_path.read_bytes()
                if input_path.read_bytes() != before:
                    return _invalid(
                        "formatter input changed during preview", "formatter_failed"
                    )
                records.append(
                    {
                        "relative_path": relative,
                        "source_sha256": _sha(before),
                        "formatted_sha256": _sha(formatted),
                        "formatted_bytes": base64.b64encode(formatted).decode("ascii"),
                    }
                )
        if (
            configurations != _config_digests(root, selected)
            or versions != _formatter_versions()
        ):
            return _invalid(
                "formatter configuration/version changed during preview",
                "stale_preview",
            )
        if any(
            _sha(_format_input_file(root, r["relative_path"]).read_bytes())
            != r["source_sha256"]
            for r in records
        ):
            return _invalid("source changed during preview", "stale_preview")
    except SubprocessCancelled:
        return _preview_cancelled(
            permissions, "format preview cancelled; no artifact published"
        )
    except subprocess.TimeoutExpired:
        return _invalid(
            "formatter preview timed out; no artifact published", "formatter_failed"
        )
    except (
        ContainmentError,
        StagingInputError,
        OSError,
        UnicodeError,
        ValueError,
    ) as exc:
        return _invalid(f"preview source/configuration rejected: {exc}")
    payload = json.dumps(
        {
            "version": 1,
            "files": records,
            "formatters": versions,
            "config_sha256": configurations,
            "selected_paths": sorted(selected),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    preview_id = _sha(payload)
    try:
        atomic_write_bytes(root, f"{_PREVIEW_DIR}/{preview_id}.json", payload)
    except (ContainmentError, OSError, ValueError) as exc:
        return _invalid(f"preview publication failed: {exc}", "formatter_failed")
    return ToolResult(
        tool="format",
        engine="preview",
        engine_version=None,
        status="ok",
        duration_ms=elapsed_ms(start),
        summary=f"previewed {len(records)} file(s)",
        findings=[],
        raw=None,
        metadata={
            "mode": "preview",
            "preview_id": preview_id,
            "selected_paths": selected,
            "records": [
                {
                    k: r[k]
                    for k in ("relative_path", "source_sha256", "formatted_sha256")
                }
                for r in records
            ],
        },
    )


def _validate_preview(
    root: Path, preview_id: str, *, use_staging: bool = False
) -> tuple[dict[str, dict[str, Any]] | None, ToolResult | None]:
    """Load one preview artifact and fail closed: (records by path, None) or
    (None, error). Never writes."""
    from ..engines.staging import StagingInputError

    physical = PhysicalRoot(root)
    try:
        raw = physical.open_contained(f"{_PREVIEW_DIR}/{preview_id}.json").read_bytes()
    except (ContainmentError, OSError):
        return (
            None,
            _apply_error("invalid_preview", "preview artifact missing or unreadable"),
        )
    if _sha(raw) != preview_id:
        return (
            None,
            _apply_error("invalid_preview", "preview artifact digest mismatch"),
        )
    try:
        data = json.loads(raw)
        files = data["files"]
        by_path = {r["relative_path"]: r for r in files}
        if len(by_path) != len(files):
            return (None, _apply_error("invalid_preview", "duplicate preview records"))
        for r in files:
            formatted = base64.b64decode(r["formatted_bytes"], validate=True)
            if _sha(formatted) != r["formatted_sha256"]:
                return (
                    None,
                    _apply_error("invalid_preview", "formatted digest mismatch"),
                )
            physical.open_contained(r["relative_path"])
        recorded = (data["formatters"], data["config_sha256"])
    except (ValueError, KeyError, TypeError, binascii.Error, ContainmentError):
        return (None, _apply_error("invalid_preview", "preview artifact malformed"))
    try:
        current = (
            _formatter_versions(),
            _config_digests(root, list(by_path), use_staging=use_staging),
        )
    except (ContainmentError, StagingInputError, OSError, UnicodeError, ValueError):
        return (
            None,
            _apply_error("stale_preview", "formatter configuration cannot be verified"),
        )
    if recorded != current:
        return (
            None,
            _apply_error(
                "stale_preview",
                "formatter version or configuration changed since preview",
            ),
        )
    return (by_path, None)


def _apply_preview(
    path: Path,
    preview_id: str | None,
    selected_files: list[str] | None,
    allow_artifact_write: bool,
) -> ToolResult:
    start = now_ms()
    if not isinstance(preview_id, str) or not _PREVIEW_ID.fullmatch(preview_id):
        return _apply_error(
            "invalid_argument", "preview_id must be 64 lowercase hex characters"
        )
    if (
        not isinstance(selected_files, list)
        or not selected_files
        or not all(isinstance(s, str) and s for s in selected_files)
        or len(set(selected_files)) != len(selected_files)
    ):
        return _apply_error(
            "invalid_argument",
            "selected_files must be a nonempty list of distinct paths",
        )
    root = _root(path)
    physical = PhysicalRoot(root)
    try:
        for entry in selected_files:
            physical.open_contained(entry)
    except ContainmentError as exc:
        return _apply_error("invalid_argument", f"selected file rejected: {exc.code}")
    denied = _grant_denied(
        ExecutionPermissions(artifact_write=True),
        ExecutionPermissions(artifact_write=allow_artifact_write),
    )
    if denied is not None:
        return denied
    by_path, error = _validate_preview(root, preview_id)
    if by_path is None:
        return error or _apply_error("invalid_preview", "preview unavailable")
    unknown = [s for s in selected_files if s not in by_path]
    if unknown:
        return _apply_error("invalid_argument", f"not in preview: {unknown[0]}")
    prepared: list[tuple[str, bytes, int]] = []
    for relative in selected_files:
        record = by_path[relative]
        target = physical.open_contained(relative)
        try:
            current = target.read_bytes()
            mode_bits = stat.S_IMODE(os.stat(target).st_mode)
        except OSError:
            return _apply_error(
                "stale_preview", f"selected source unreadable: {relative}"
            )
        if _sha(current) != record["source_sha256"]:
            return _apply_error(
                "stale_preview", f"stale preview; no files changed: {relative}"
            )
        prepared.append(
            (relative, base64.b64decode(record["formatted_bytes"]), mode_bits)
        )
    changed: list[str] = []
    written: list[dict[str, str]] = []
    try:
        for relative, data, mode_bits in prepared:
            atomic_write_bytes(root, relative, data, mode=mode_bits)
            changed.append(relative)
            written.append({"relative_path": relative, "formatted_sha256": _sha(data)})
    except (OSError, ValueError) as exc:
        message = (
            f"apply interrupted after {len(changed)} file(s): {type(exc).__name__}"
        )
        return ToolResult(
            tool="format",
            engine="preview-apply",
            engine_version=None,
            status="error",
            duration_ms=elapsed_ms(start),
            summary=message,
            findings=[],
            raw=None,
            metadata={
                "mode": "apply",
                "preview_id": preview_id,
                "changed_paths": changed,
                "written": written,
                "partial_write": bool(changed),
                "error": {"code": "partial_write", "message": message},
            },
        )
    return ToolResult(
        tool="format",
        engine="preview-apply",
        engine_version=None,
        status="ok",
        duration_ms=elapsed_ms(start),
        summary=f"applied {len(changed)} formatted file(s)",
        findings=[],
        raw=None,
        metadata={
            "mode": "apply",
            "preview_id": preview_id,
            "changed_paths": changed,
            "written": written,
            "partial_write": False,
        },
    )


def _verification_preflight(path, preview_id, nodes, runtime_path, image_ref, granted):
    from ..runtime.isolated_process import IsolationUnavailable, check_isolation_inputs

    if not isinstance(preview_id, str) or not _PREVIEW_ID.fullmatch(preview_id):
        return _invalid("verify_preview_id must be 64 lowercase hex characters")
    if (
        not nodes
        or not isinstance(nodes, list)
        or any(
            not isinstance(node, str)
            or not node
            or node.startswith("-")
            or "\x00" in node
            for node in nodes
        )
        or len(set(nodes)) != len(nodes)
    ):
        return _invalid(
            "verification_tests must be nonempty distinct contained test ids"
        )
    root = _root(path)
    try:
        for node in nodes:
            if not PhysicalRoot(root).open_contained(node.split("::", 1)[0]).is_file():
                return _invalid("verification test must name an existing file")
    except ContainmentError as exc:
        return _invalid(f"verification test rejected: {exc.code}")
    denied = _grant_denied(ExecutionPermissions(build=True, slow=True), granted)
    if denied is not None:
        denied.setdefault("metadata", {})["preview_verification"] = {
            "preview_id": preview_id,
            "status": "denied",
            "reason": "build_or_slow_denied",
            "eligible": False,
            "ast_equal": False,
            "tests": [],
        }
        return denied
    if runtime_path is not None and image_ref is not None:
        try:
            check_isolation_inputs(root, runtime_path=runtime_path, image_ref=image_ref)
        except IsolationUnavailable:
            # F3 missing-runtime preserves ordinary check; _verify_preview
            # emits the actual unavailable operation after ordinary check.
            return None
        except ValueError as exc:
            return _invalid(str(exc))
    return None


def _verify_preview(
    result,
    path,
    verify_preview_id,
    verification_tests,
    runtime_path,
    image_ref,
    permissions,
):
    from ..engines.staging import StagingInputError
    from ..patch.contracts import DirtyWorkspaceError
    from ..patch.sandbox import PatchSandboxManager
    from ..runtime.isolated_process import (
        IsolatedCleanupError,
        IsolationUnavailable,
        check_isolation_inputs,
    )
    from ..runtime.isolated_tests import run_selected_tests_isolated
    from ..runtime.subprocesses import SubprocessCancelled

    root = _root(path)
    v = {
        "preview_id": verify_preview_id,
        "ast_equal": False,
        "tests": [],
        "eligible": False,
        "status": "rejected",
    }
    result["metadata"] = {**(result.get("metadata") or {}), "preview_verification": v}
    if runtime_path is None or image_ref is None:
        v.update(status="skipped", reason="isolation_unavailable")
        return result
    try:
        check_isolation_inputs(root, runtime_path=runtime_path, image_ref=image_ref)
    except IsolationUnavailable as exc:
        v.update(status="skipped", reason="isolation_unavailable", summary=str(exc))
        return result
    except ValueError as exc:
        return _invalid(str(exc))
    by_path, error = _validate_preview(root, verify_preview_id, use_staging=True)
    if by_path is None:
        code = ((error or {}).get("metadata") or {}).get("error", {}).get("code")
        v["status"] = "stale_preview" if code == "stale_preview" else "rejected"
        return result
    test_paths = {node.split("::", 1)[0] for node in verification_tests}
    try:
        captured = {
            relative: _format_input_file(root, relative).read_bytes()
            for relative in set(by_path)
            | test_paths
            | set(_config_digests(root, list(by_path)))
        }
        if any(
            _sha(captured[p]) != record["source_sha256"]
            for p, record in by_path.items()
        ):
            v["status"] = "stale_preview"
            return result
    except (ContainmentError, StagingInputError, OSError, ValueError) as exc:
        return _invalid(f"verification input rejected: {exc}")
    manifest = {relative: _sha(data) for relative, data in captured.items()}
    v["captured_inputs"] = manifest
    manager = PatchSandboxManager(root)
    try:
        sandbox = manager.create_sandbox()
    except DirtyWorkspaceError:
        v["status"] = "dirty_workspace"
        return result
    try:
        for relative, data in captured.items():
            atomic_write_bytes(sandbox, relative, data)
        same_ast = True
        for relative, record in by_path.items():
            formatted = base64.b64decode(record["formatted_bytes"], validate=True)
            if relative.endswith(_PYTHON_SUFFIXES):
                try:
                    same_ast &= ast.dump(ast.parse(captured[relative])) == ast.dump(
                        ast.parse(formatted)
                    )
                except SyntaxError:
                    same_ast = False
            atomic_write_bytes(sandbox, relative, formatted)
        v["ast_equal"] = same_ast
        executed = {
            relative: _sha(PhysicalRoot(sandbox).open_contained(relative).read_bytes())
            for relative in captured
        }
        v["executed_inputs"] = executed
        receipts = v["tests"]
        with TemporaryDirectory(prefix=".rush-format-verify-", dir=root.parent) as out:
            Path(out).chmod(0o700)
            for node in verification_tests:
                try:
                    run = run_selected_tests_isolated(
                        sandbox,
                        Path(out),
                        nodes=[node],
                        runtime_path=runtime_path,
                        image_ref=image_ref,
                        python_entrypoint="/usr/local/bin/python",
                        timeout_s=300,
                    )
                except (
                    subprocess.TimeoutExpired,
                    SubprocessCancelled,
                    IsolatedCleanupError,
                ) as exc:
                    # F4 attaches factual receipt and accepted host starts;
                    # no fabricated pytest counts or container-success claim.
                    terminal = {
                        "reason": "cancelled"
                        if isinstance(exc, SubprocessCancelled)
                        else "cleanup_unconfirmed"
                        if isinstance(exc, IsolatedCleanupError)
                        else "timeout",
                        "exception": type(exc).__name__,
                    }
                    if hasattr(exc, "receipt"):
                        terminal["isolation_receipt"] = exc.receipt
                    if hasattr(exc, "process_launches"):
                        terminal["process_launches"] = exc.process_launches
                    v["terminal_run"] = terminal
                    if isinstance(exc, SubprocessCancelled):
                        cancelled = _preview_cancelled(
                            permissions,
                            "format verification cancelled",
                            requested=ExecutionPermissions(build=True, slow=True),
                        )
                        result["metadata"]["execution"] = cancelled["metadata"][
                            "execution"
                        ]
                        v.update(status="skipped", reason="cancelled")
                    else:
                        v.update(status="rejected", reason=terminal["reason"])
                    return result
                receipts.append(
                    {
                        "outcome": run.outcome,
                        "counts": run.counts,
                        "argv": run.argv,
                        "process_launches": run.process_launches,
                        "isolation_receipt": run.isolated.receipt,
                        "captured_inputs": manifest,
                        "executed_inputs": dict(executed),
                    }
                )
                if any(
                    _sha(PhysicalRoot(sandbox).open_contained(p).read_bytes()) != digest
                    for p, digest in executed.items()
                ):
                    v.update(status="rejected", reason="verification_inputs_changed")
                    return result
        _, identity_error = _validate_preview(root, verify_preview_id, use_staging=True)
        if identity_error is not None or any(
            _sha(_format_input_file(root, p).read_bytes()) != digest
            for p, digest in manifest.items()
        ):
            v["status"] = "stale_preview"
        elif not same_ast or any(r["outcome"] in ("failed", "error") for r in receipts):
            v["status"] = "rejected"
        elif receipts and all(
            r["outcome"] == "passed"
            and r["counts"]["passed"] > 0
            and sum(r["counts"][k] for k in ("failed", "skipped", "error")) == 0
            and r["isolation_receipt"].get("cleanup_confirmed") is True
            for r in receipts
        ):
            v.update(status="eligible", eligible=True)
        else:
            v["status"] = "inconclusive"
    except IsolationUnavailable as exc:
        v.update(status="skipped", reason="isolation_unavailable", summary=str(exc))
    except (ValueError, ContainmentError, StagingInputError, OSError) as exc:
        return _invalid(f"verification input rejected: {exc}")
    finally:
        manager.cleanup_sandbox(sandbox)
    return result


def _consumed_selected(child: ToolResult, files: list[Path]) -> list[Path]:
    from ..engines.staging import active_staging

    if child["status"] in ("error", "skipped"):
        return []
    staging = active_staging()
    consumed: set[Path] = set()
    for entry in (child.get("metadata") or {}).get("engines", []):
        scope = entry.get("scope") or {}
        listed = scope.get("consumed_files")
        if isinstance(listed, list):
            identities = {
                os.path.abspath(item) for item in listed if isinstance(item, str)
            }
            for file in files:
                alternatives = {str(file.absolute())}
                if staging is not None:
                    alternatives.add(
                        os.path.abspath(staging.substitute_arg(str(file.absolute())))
                    )
                if identities.intersection(alternatives):
                    consumed.add(file)
        elif (
            scope.get("consumption_source") == "explicit_arguments"
            and scope.get("coverage") == "complete"
            and scope.get("consumed_file_count") == len(files)
        ):
            # Runtime _entry_scope validated these requested file identities
            # against actual recorded main argv; status alone never proves scope.
            consumed.update(files)
    return [file for file in files if file in consumed]


def _attach_scope(child: ToolResult, files: list[Path]) -> list[Path]:
    consumed = _consumed_selected(child, files)
    metadata = child.setdefault("metadata", {})
    execution = metadata.get("execution") or {}
    cause = execution.get("cause")
    if child["status"] == "error":
        coverage, reason = "unavailable", "engine_error"
    elif child["status"] == "skipped":
        coverage, reason = (
            ("none", cause)
            if cause in ("permission_denied", "cancelled")
            or execution.get("disposition") == "cancelled"
            else ("unavailable", "engine_unavailable")
        )
    elif len(consumed) == len(files):
        coverage, reason = "complete", None
    else:
        coverage, reason = "partial", "requested_files_not_consumed"
    metadata["scope"] = child_scope(
        coverage,
        reason=reason,
        requested_targets=[str(file.absolute()) for file in files],
        matched_file_count=len(files),
        consumed_file_count=len(consumed),
    )
    return consumed


class FormatTool(ToolFn):
    name: ToolName = "format"

    @property
    def mcp_description(self) -> str:
        return "Format Python/JS/TS at <path>. Returns {status, findings[], summary}. Engines: ruff format, prettier. Default check; preview/apply require allow_artifact_write."

    def __call__(
        self,
        path: Path,
        check: bool = True,
        *,
        mode: Literal["check", "preview", "apply"] = "check",
        preview_id: str | None = None,
        selected_files: list[str] | None = None,
        verify_preview_id: str | None = None,
        verification_tests: list[str] | None = None,
        runtime_path: Path | None = None,
        image_ref: str | None = None,
        allow_artifact_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
    ) -> ToolResult:
        return self.run(
            path,
            check=check,
            mode=mode,
            preview_id=preview_id,
            selected_files=selected_files,
            verify_preview_id=verify_preview_id,
            verification_tests=verification_tests,
            runtime_path=runtime_path,
            image_ref=image_ref,
            permissions=ExecutionPermissions(
                artifact_write=allow_artifact_write, build=allow_build, slow=allow_slow
            ),
        )

    def run(
        self,
        path: Path,
        *,
        check: bool = True,
        config=None,
        mode: Literal["check", "preview", "apply"] = "check",
        preview_id: str | None = None,
        selected_files: list[str] | None = None,
        verify_preview_id: str | None = None,
        verification_tests: list[str] | None = None,
        runtime_path: Path | None = None,
        image_ref: str | None = None,
        permissions: ExecutionPermissions | None = None,
    ) -> ToolResult:
        granted = permissions or ExecutionPermissions()
        if not check:
            return _invalid(
                "check=False is unsupported; use mode='apply' with a reviewed preview",
                "unsupported_operation",
            )
        if mode not in ("check", "preview", "apply"):
            return _invalid("mode must be one of check, preview, apply")
        verifying = verify_preview_id is not None
        misplaced = [
            name
            for name, given, allowed in (
                ("preview_id", preview_id is not None, mode == "apply"),
                ("selected_files", selected_files is not None, mode == "apply"),
                ("verify_preview_id", verifying, mode == "check"),
                ("verification_tests", verification_tests is not None, verifying),
                ("runtime_path", runtime_path is not None, verifying),
                ("image_ref", image_ref is not None, verifying),
            )
            if given and (not allowed)
        ]
        if misplaced:
            return _invalid(f"{', '.join(misplaced)} not valid for mode={mode}")
        if mode == "preview":
            return _build_preview(path, granted)
        if mode == "apply":
            return _apply_preview(
                path, preview_id, selected_files, granted.artifact_write
            )
        if verifying:
            preflight = _verification_preflight(
                path,
                verify_preview_id,
                verification_tests,
                runtime_path,
                image_ref,
                granted,
            )
            if preflight is not None:
                return preflight
        result = self._check(path)
        if verify_preview_id is not None:
            result = _verify_preview(
                result,
                path,
                verify_preview_id,
                verification_tests,
                runtime_path,
                image_ref,
                granted,
            )
        return result

    def _check(self, path: Path) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        targets = collect_files(
            path,
            {
                extension
                for engine in ENGINES.values()
                for extension in engine.file_extensions
            },
        )
        if not targets:
            return ToolResult(
                tool="format",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"format: no Python/JS/TS files found under {path}",
                findings=[],
                raw=None,
                metadata={
                    "scope": no_target_scope(
                        "no_supported_targets",
                        matched_file_count=0,
                        consumed_file_count=0,
                    ),
                    "engines": [],
                    "assessed_paths": {},
                },
            )
        base = (path if path.is_dir() else path.parent).absolute()
        batches: tuple[tuple[str, list[str]], ...] = (
            ("ruff", ["format", "--check"]),
            ("prettier", []),
        )
        children: list[ToolResult] = []
        ledger: list[dict[str, Any]] = []
        engines_used: list[str] = []
        for name, args in batches:
            files = [
                t.absolute()
                for t in targets
                if t.suffix.lstrip(".") in ENGINES[name].file_extensions
            ]
            if not files:
                continue
            child = run_engine(
                ENGINES[name],
                path,
                args,
                tool_name="format",
                consumed_paths=[str(p.absolute()) for p in files],
                selected_targets=files,
                cwd=base,
                scope_probe=False,
            )
            assessed = _attach_scope(child, files)
            children.append(child)
            engines_used.append(name)
            child_status = str(child.get("status", "ok"))
            ledger.append(
                {
                    "engine": name,
                    "engine_version": child.get("engine_version"),
                    "status": child_status,
                    "summary": child.get("summary"),
                    "assessed_paths": [str(p.absolute()) for p in assessed],
                }
            )
        if not engines_used:
            return ToolResult(
                tool="format",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="format: no supported formatter targets",
                findings=[],
                raw=None,
                metadata={
                    "scope": no_target_scope("no_supported_targets"),
                    "engines": [],
                    "assessed_paths": {},
                },
            )
        findings_all: list = [
            finding for child in children for finding in child.get("findings", [])
        ]
        last_status: ToolStatus = aggregate_status(
            str(child.get("status", "ok")) for child in children
        )
        n = len(findings_all)
        if n == 0:
            status: ToolStatus = last_status
            summary = (
                f"format [{'+'.join(engines_used)}]: all formatted"
                if status == "ok"
                else f"format [{'+'.join(engines_used)}]: engine {status}"
            )
        else:
            status = aggregate_status([last_status, "warn"])
            summary = (
                f"format [{'+'.join(engines_used)}]: engine error"
                if status == "error"
                else f"format [{'+'.join(engines_used)}]: {n} file(s) need reformatting"
            )
        scope = aggregate_scope(children)
        if scope["coverage"] == "unavailable":
            scope["reason"] = (
                "engine_error"
                if any(
                    c["metadata"]["scope"]["reason"] == "engine_error" for c in children
                )
                else "engine_unavailable"
            )
        partial = scope["coverage"] == "partial"
        if partial and status == "ok":
            status = "warn"
            excluded = [
                p
                for c in children
                for p in c["metadata"]["scope"]["requested_targets"]
                if p not in ledger[children.index(c)]["assessed_paths"]
            ]
            summary = (
                "format: partial assessment; requested_files_not_consumed: "
                + ", ".join(excluded)
            )
        if (
            partial
            and n == 0
            and status == "warn"
            and any(c["status"] == "skipped" for c in ledger)
        ):
            skipped = "+".join(c["engine"] for c in ledger if c["status"] == "skipped")
            summary = f"format [{'+'.join(engines_used)}]: partial assessment; {skipped} skipped"
        return ToolResult(
            tool="format",
            engine="+".join(engines_used),
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings_all,
            raw=None,
            metadata={
                "engines": concat_engine_entries(children),
                "scope": scope,
                "assessed_paths": {c["engine"]: c["assessed_paths"] for c in ledger},
            },
        )
```

**Part 3 — `src/rush/engines/prettier.py`, selected-target operands (proposed, unexecuted):**
```diff
--- a/src/rush/engines/prettier.py
+++ b/src/rush/engines/prettier.py
@@ -55,11 +55,17 @@
         owner_instance_id: str | None = None,
         run_id: str | None = None,
+        selected_targets: list[Path] | None = None,
     ) -> EngineResult:
         binary_path = resolve_binary(self.binary) or self.binary
+        targets = (
+            [str(path)]
+            if selected_targets is None
+            else [str(p) for p in selected_targets]
+        )
         argv = [
             binary_path,
             "--check",
             "--log-level=warn",  # suppress info noise
-            str(path),
+            *targets,
             *args,
         ]
```

**Part 4 — `src/rush/engines/ruff.py`, revised Q02 reference-only prerequisite, format branch consumes the selected vector (proposed, unexecuted; see Missed M2):**
```diff
--- a/src/rush/engines/ruff.py
+++ b/src/rush/engines/ruff.py
@@ -41,4 +41,5 @@
         owner_instance_id: str | None = None,
         run_id: str | None = None,
+        selected_targets: list[Path] | None = None,
     ) -> EngineResult:
         """Run `ruff check --output-format=json <path> <args>`.
@@ -55,5 +56,9 @@
                 "--output-format=json",
                 "--no-cache",
-                *args[2:],
+                *(
+                    args[2:]
+                    if selected_targets is None
+                    else [str(p) for p in selected_targets]
+                ),
             ]
         else:
```
Part 5 is the CLI patch (Q03-01). Part 6 is the Foundation-owned runtime plumbing consumed by Q03-07. Q03 owns format.py, prettier.py and filesystem.py; Ruff's format branch is the revised Q02 prerequisite. CLI/MCP/runtime/shared docs belong solely to the concrete Foundation rows listed in Deliverables. All source and checks remain proposed and unexecuted.

Verification requirement: original report Q03-04 at line 3637; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-05: W18 `isolated_process` is undefined in the plan, nonexistent, and not planned in this batch

W18 audit Command45/79 rush_mem_profile13810–13889; Foundation F4. Q03 no provider write; IsolatedRun factual receipts; X1 F5 selected tests, pinned RUSH_TEST_RUSH_IMAGE/runtime and OCI CI.

Verification requirement: original report Q03-05 at line 4516; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-06: `assessed_paths` is read from `metadata.execution.consumed_paths`, which nothing emits

Paths derive preserved runtime consumption facts, never status alone or nonexistent execution.consumed_paths. Q03-04's _consumed_selected intersects actual consumed_files with logical/staged selected identities, or accepts only runtime-validated complete explicit_arguments/count evidence. _attach_scope produces complete/partial/unavailable/none with exact requested/matched/consumed counts; errors are unavailable/engine_error, missing engines unavailable/engine_unavailable. Assessed paths are absolute logical consumed files. metadata.scope=aggregate_scope(children); metadata.assessed_paths={c["engine"]:c["assessed_paths"] for c in ledger}. Test {ruff:["a.py"],prettier:[]} and coverage partial.

Verification requirement: original report Q03-06 at line 4547; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-07: `selected_targets` is only a proposed Q02 contract, and a staged scan would aim Prettier and Ruff at live-tree files

replace plan :181-182 with:
```text
Shared target contract (Foundation-owned, consumed from revised Q02; Q03 adds PrettierEngine and consumes the Ruff format
branch, Q03-04 Parts 3-4): run_engine(..., selected_targets: list[Path] | None = None) forwards to
Engine.run(..., selected_targets=...) only when not None. Operand rule: targets = [str(path)] if
selected_targets is None else [str(p) for p in selected_targets]; Ruff's format branch uses
args[2:] when None (legacy: no root operand) else the vector. Staging: after _staged_invocation,
run_engine maps selected_targets through staging.substitute_arg exactly as extra_args; the 4-tuple
return of _staged_invocation is not changed. Q03 starts only after Foundation's revised Q02 selected_targets row lands.
Ruff format uses scope_probe=False: existing show_files builds `ruff check` and cannot
receive ['format', '--check']. Its preserved runtime explicit_arguments entry validates
selected identities against actual main argv. Prettier uses the same explicit argv
consumption evidence. No copied lint probe or status-only complete scope.
```
Reference-only Foundation runtime patch row consumed from revised Q02 (proposed, unexecuted; Foundation is sole shared writer):
```diff
--- a/src/rush/runtime/subprocesses.py
+++ b/src/rush/runtime/subprocesses.py
@@ -1271,4 +1271,5 @@
     project_root: Path | None = None,
     scope_probe: bool = False,
+    selected_targets: list[Path] | None = None,
 ) -> ToolResult:
     """Run an engine and always return a canonical result.
@@ -1309,4 +1310,5 @@
                 run_id=run_id,
                 consumed_paths=consumed_paths,
+                selected_targets=selected_targets,
             )
             if scope_probe and any(s["kind"] == "main" for s in spawns):
@@ -1580,4 +1582,5 @@
     run_id: str | None = None,
     consumed_paths: list[str] | None = None,
+    selected_targets: list[Path] | None = None,
 ) -> ToolResult:
     """Run an engine and always return a canonical result.
@@ -1676,4 +1679,11 @@
         )

+    if staging is not None and selected_targets is not None:
+        selected_targets = [
+            Path(staging.substitute_arg(str(p))) for p in selected_targets
+        ]
+    selected_kw: dict[str, Any] = (
+        {} if selected_targets is None else {"selected_targets": selected_targets}
+    )
     start = _now()
     try:
@@ -1683,4 +1693,5 @@
                 extra_args,
                 cwd=run_cwd,
+                **selected_kw,
                 **_engine_run_ownership(engine, owner_instance_id, run_id),
             )
```
Add this proposed, unexecuted test to `tests/test_format.py`; run after Foundation's selected_targets row lands:
```python
def test_staged_scan_maps_selected_targets(tmp_path, monkeypatch):
    from rush.engines.staging import stage_inventory, staging_scope

    root = (tmp_path / "project").resolve()
    root.mkdir()
    (root / "b.ts").write_text("const x = 1;\n")
    staged_root = tmp_path / "staged"
    staging = stage_inventory(root, staged_root, ["b.ts"])
    calls = []
    monkeypatch.setattr(prettier_module, "resolve_binary", lambda _b: "prettier-bin")
    monkeypatch.setattr(
        prettier_module,
        "run_subprocess",
        lambda argv, **kw: calls.append(argv) or CompletedProcess(argv, 0, "", ""),
    )
    monkeypatch.setattr(common, "engine_on_path", lambda _b: True)
    with staging_scope(staging):
        common.run_engine(
            PrettierEngine(),
            root,
            [],
            tool_name="format",
            consumed_paths=[str(root / "b.ts")],
            selected_targets=[root / "b.ts"],
        )
    assert calls[0][-1] == str(staged_root / "b.ts")
    assert str(root / "b.ts") not in calls[0]
```

Verification requirement: original report Q03-07 at line 4570; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-SCOPE: Staged requests use physical identities in the preserved runtime ledger

Foundation owns `src/rush/runtime/subprocesses.py::_entry_scope` and this one
defined helper. Current spans1410–1487 compare logical source inode identities
against actual staged main argv inodes, producing false partial coverage.
The repair changes only requested identity comparison; actual spawns, argv,
consumption_source, consumed counts, probe listings and requested counts stay
factual. Format calls remain scope_probe=False, because Ruff.show_files builds
lint argv and cannot accept a format command.

Proposed replacement (unimplemented/unexecuted):
```python
def _requested_scope_identity(value: str) -> tuple[int, int] | None:
    from ..engines.staging import active_staging
    from ..io.physical_paths import ContainmentError, PhysicalRoot

    staging = active_staging()
    if staging is None:
        return _identity(value)
    logical = Path(value)
    if not logical.is_absolute():
        logical = staging.original_root / logical
    try:
        relative = logical.relative_to(staging.original_root)
    except ValueError:
        return _identity(value)  # Existing explicitly external input behavior.
    if ".." in relative.parts or relative.as_posix() in staging.rejected_paths:
        return None
    try:
        physical = PhysicalRoot(staging.staged_root).open_contained(relative)
    except (ContainmentError, OSError):
        return None
    return _identity(str(physical))


def _entry_scope(main, consumed_paths, listed, reason):
    requested = len(consumed_paths) if consumed_paths is not None else None
    if listed is not None:
        return _probe_scope(listed, requested)
    base = {
        "requested_file_count": requested,
        "consumption_source": "explicit_arguments",
    }
    if not main:
        return {**base, "consumed_file_count": 0, "coverage": "none", "reason": reason}
    files, directory = _argv_targets(main)
    if directory:
        return {
            **base,
            "consumed_file_count": None,
            "coverage": "unavailable",
            "reason": "engine_discovers_directory_contents",
        }
    identities = [_requested_scope_identity(path) for path in consumed_paths or ()]
    wanted = {identity for identity in identities if identity is not None}
    if not files:
        coverage = "none"
    elif consumed_paths is None:
        coverage = "unavailable"
    else:
        coverage = (
            "complete"
            if all(identity is not None for identity in identities) and wanted <= files
            else "partial"
        )
    return {
        **base,
        "consumed_file_count": len(files),
        "coverage": coverage,
        "reason": "requested_files_unknown" if coverage == "unavailable" else None,
    }
```
Missing/rejected staged identities remain unassessed; they cannot disappear from
the all-identities condition to manufacture complete coverage. Existing
_staged_invocation/selected_targets rejects unsafe arguments before dispatch.
Actual explicit source/config staging and its four-tuple remain unchanged.

Add these bodies to the Q03-12 unit module (existing imports apply):
```python
def test_staged_scope_uses_physical_inputs_but_reports_logical_paths(
    tmp_path, monkeypatch
):
    import sys

    from rush.engines import ENGINES
    from rush.engines.staging import stage_inventory, staging_scope

    root = (tmp_path / "project").resolve()
    root.mkdir()
    source = root / "b.ts"
    source.write_bytes(b"const x = 1;\n")
    staging = stage_inventory(root, tmp_path / "stage", ["b.ts"])
    source.write_bytes(b"const x = 9;\n")
    calls = []

    class IdentityEngine(PrettierEngine):
        binary = sys.executable

        def version(self, **kwargs):
            return "controlled"

        def run(self, path, args, cwd=None, **kwargs):
            selected = kwargs["selected_targets"]
            calls.append(selected)
            proc = common.run_subprocess(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys; from pathlib import Path; "
                        "assert Path(sys.argv[1]).read_bytes() == b'const x = 1;\\n'"
                    ),
                    str(selected[0]),
                ],
                cwd=cwd,
                **{
                    key: kwargs[key]
                    for key in ("owner_instance_id", "run_id")
                    if key in kwargs
                },
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "findings": [],
                "summary": "controlled",
                "duration_ms": 0,
            }

    monkeypatch.setitem(ENGINES, "prettier", IdentityEngine())
    with staging_scope(staging):
        result = FormatTool().run(root)
    assert calls == [[staging.staged_root / "b.ts"]]
    assert result["status"] == "ok"
    assert result["metadata"]["scope"]["coverage"] == "complete"
    assert result["metadata"]["assessed_paths"] == {"prettier": [str(source)]}
    legacy = result["metadata"]["engines"][0]["scope"]
    assert legacy == {
        "requested_file_count": 1,
        "consumption_source": "explicit_arguments",
        "consumed_file_count": 1,
        "coverage": "complete",
        "reason": None,
    }
    assert source.read_bytes() == b"const x = 9;\n"


def test_rejected_or_missing_staged_identity_cannot_be_complete(tmp_path):
    from rush.engines.staging import stage_inventory, staging_scope
    from rush.runtime import subprocesses as runtime

    root = (tmp_path / "project").resolve()
    root.mkdir()
    source = root / "b.ts"
    source.write_text("const x = 1;\n")
    staging = stage_inventory(root, tmp_path / "stage", ["b.ts"])
    staged = staging.staged_root / "b.ts"
    actual = [{"argv": ["prettier", str(staged)], "cwd": str(staging.staged_root)}]
    with staging_scope(staging):
        staging.rejected_paths["b.ts"] = "copy or hash error"
        assert (
            runtime._entry_scope(actual, [str(source)], None, None)["coverage"]
            == "partial"
        )
        staging.rejected_paths.clear()
        staged.unlink()
        assert (
            runtime._entry_scope(actual, [str(source)], None, None)["coverage"]
            == "none"
        )
```
The first test launches an actual bounded child and reads staged bytes while live
bytes differ; the second exercises actual identity reconciliation with rejected
and missing input states. These are proposed, not executed here.
Proposed command: run tests/test_format.py (stage-A exclusions in final Checks),
and tests/test_subprocess_contract.py. Both are literal existing/planned owned
modules; the two exact staged identity bodies above live in tests/test_format.py.


### Q03-STDIO: Snapshot byte input and private exact output through the existing owned runner

Foundation owns this proposed row in `src/rush/runtime/subprocesses.py`.
Current source spans: gates 94–130, launchers 583–731, run_subprocess 857–919,
blocking 976–1010 and cancellable 1013–1101. Graft callers cover 165 source files;
every existing call keeps stdin_path=None/stdout_path=None and existing output
redaction/bounds. No public CLI/MCP option, alternate runner or shell mode.

Formatter stdin-filename/path determines source/config identity. A temporary
file operand changes that discovery path. Returned diagnostic stdout is bounded
and redacted; it cannot carry source bytes. Optional private descriptors solve
both constraints while preserving the existing owned bootstrap gate.

Proposed exact edits (unimplemented/unexecuted):
1. Add `import stat`, `ExitStack` to existing contextlib imports and `BinaryIO` to typing.
   Add keyword-only `stdin_path: Path | None = None`,
   `stdout_path: Path | None = None` to run_subprocess.
   Add optional `stdin_file: BinaryIO | None = None`,
   `stdout_file: BinaryIO | None = None` to both private runner signatures;
   additionally add `stdin_path: Path | None = None` to cancellable runner
   and both launchers. Existing positional/keyword arguments remain unchanged.
2. After existing _record_spawn, replace only runner dispatch with:
```python
    output_path = None if stdout_path is None else Path(stdout_path)
    stdin_path = None if stdin_path is None else Path(stdin_path).resolve(strict=True)
    output_created = False
    succeeded = False
    try:
        with ExitStack() as stack:
            io_kwargs = {}
            if stdin_path is not None:
                fd = os.open(stdin_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                input_file = stack.enter_context(os.fdopen(fd, "rb"))
                if not stat.S_ISREG(os.fstat(input_file.fileno()).st_mode):
                    raise ValueError("stdin_path must be a regular file")
                io_kwargs["stdin_file"] = input_file
            if stdout_path is not None:
                fd = os.open(
                    stdout_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                output_created = True
                io_kwargs["stdout_file"] = stack.enter_context(os.fdopen(fd, "wb"))
            if cancel_check is None and owner_instance_id is None:
                result = _run_subprocess_blocking(
                    exec_argv, argv, cwd=cwd, timeout=timeout, env=env, **io_kwargs
                )
            else:
                result = _run_subprocess_cancellable(
                    exec_argv,
                    argv,
                    cwd=cwd,
                    timeout=timeout,
                    env=env,
                    cancel_check=cancel_check,
                    poll_interval=poll_interval,
                    owner_instance_id=owner_instance_id,
                    run_id=run_id,
                    **io_kwargs,
                    **({"stdin_path": stdin_path} if stdin_path is not None else {}),
                )
            succeeded = result.returncode == 0
            return result
    finally:
        if output_created and not succeeded:
            assert output_path is not None
            output_path.unlink(missing_ok=True)
```
An exclusive output open never deletes a preexisting caller file. Descriptor
closure precedes failure cleanup. Cancellation, timeout, spawn error and nonzero
status remove only this call's partial output; a successful output remains mode 0600.
The ordinary returned stdout remains diagnostic text, empty for private capture.

3. Blocking runner before subprocess.run sets:
```python
    capture = (
        {"capture_output": True}
        if stdout_file is None
        else {"stdout": stdout_file, "stderr": subprocess.PIPE}
    )
```
Replace only `stdin=subprocess.DEVNULL` with
`stdin=subprocess.DEVNULL if stdin_file is None else stdin_file`;
replace `capture_output=True` with `**capture`. Also replace blocking return's `stdout=_bounded_redacted_output(result.stdout)` with
`stdout=_bounded_redacted_output(result.stdout or "")` for a descriptor-backed capture.
Keep text encoding, stderr redaction/bounds, timeout, shell=False and FileNotFoundError mapping unchanged.

4. Cancellable runner after _popen_kwargs_for_cancellable sets:
```python
    if stdin_file is not None:
        popen_kwargs["stdin"] = stdin_file
    if stdout_file is not None:
        popen_kwargs["stdout"] = stdout_file
```
Its owned _launch_gated_process call additionally forwards
`stdin_path=stdin_path` only when non-None. Existing communicate loop, owned
record/gate, process-group termination, timeout/cancel exceptions and stderr
redaction remain intact. A file-backed stdout returns None from communicate;
existing `stdout or ""` handles it. Do not route raw bytes into returned stdout.

5. Preserve original _GATE_SCRIPT for None. Add:
```python
_GATE_STDIN_SCRIPT = 'read -r _ && _rush_input=$1 && shift && exec "$@" <"$_rush_input"'
```
POSIX launcher selects command before Popen:
```python
    gate_argv = (
        [_GATE_SHELL, "-c", _GATE_SCRIPT, "sh", *exec_argv]
        if stdin_path is None
        else [
            _GATE_SHELL,
            "-c",
            _GATE_STDIN_SCRIPT,
            "sh",
            str(stdin_path),
            *exec_argv,
        ]
    )
```
Replace the existing first Popen argument with gate_argv; retain its stdin
release pipe, durable record before release, and _finish_gate_cleanup.
Forward stdin_path from POSIX dispatch to Windows launcher only when supplied.

6. Windows launcher inserts the private input path between handle and engine
argv only when supplied:
```python
    (
        [
            sys.executable,
            *gate_entry,
            str(handle_value),
            *(
                ["__rush_stdin_file__", str(stdin_path)]
                if stdin_path is not None
                else []
            ),
            *exec_argv,
        ],
    )
```
Replace _WINDOWS_GATE_SCRIPT with this equivalent bounded gate; update
windows_gate after its existing release-token check with the same payload logic:
```python
_WINDOWS_GATE_SCRIPT = (
    "import sys, os, msvcrt, subprocess\n"
    "handle = int(sys.argv[1])\n"
    "fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)\n"
    "data = os.read(fd, 1)\n"
    "os.close(fd)\n"
    "if not data:\n"
    "    sys.exit(1)\n"
    "argv = sys.argv[2:]\n"
    "if argv[:1] == ['__rush_stdin_file__']:\n"
    "    with open(argv[1], 'rb') as source:\n"
    "        sys.exit(subprocess.Popen(argv[2:], stdin=source).wait())\n"
    "sys.exit(subprocess.Popen(argv, stdin=subprocess.DEVNULL).wait())\n"
)
```
```python
    command = argv[1:]
    if command[:1] == ["__rush_stdin_file__"]:
        with open(command[1], "rb") as source:
            return subprocess.Popen(command[2:], stdin=source).wait()
    return subprocess.Popen(command, stdin=subprocess.DEVNULL).wait()
```
Keep Windows handle_list, Job Object assignment, owned record, gate release
ordering, frozen-executable entry and cleanup exactly as source. Gate token never
enters formatter stdin. Private input remains independent of release transport.

Foundation adds these proposed bodies to `tests/test_subprocess_contract.py`:
```python
import subprocess

import pytest


@pytest.mark.parametrize("owned", [False, True])
def test_format_private_stdio_preserves_bytes_and_diagnostics(tmp_path, owned):
    import os
    import stat
    import sys

    from rush.runtime.subprocesses import run_subprocess

    source = tmp_path / "input"
    source.write_bytes(b"\x00\xff" + b"x" * 20000 + b"secret")
    output = tmp_path / "output"
    kwargs = {"owner_instance_id": "format-fixture", "run_id": "stdio"} if owned else {}
    result = run_subprocess(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); "
                "sys.stderr.write('ordinary diagnostic\\n')"
            ),
        ],
        stdin_path=source,
        stdout_path=output,
        **kwargs,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == "ordinary diagnostic\n"
    assert output.read_bytes() == source.read_bytes()
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.parametrize("owned", [False, True])
def test_format_private_stdio_failure_discards_output(tmp_path, owned):
    import sys

    from rush.runtime.subprocesses import run_subprocess

    source = tmp_path / "input"
    source.write_bytes(b"input")
    output = tmp_path / "output"
    kwargs = (
        {"owner_instance_id": "format-fixture", "run_id": "failure"} if owned else {}
    )
    result = run_subprocess(
        [sys.executable, "-c", "import sys; print('partial'); sys.exit(2)"],
        stdin_path=source,
        stdout_path=output,
        **kwargs,
    )
    assert result.returncode == 2
    assert not output.exists()


@pytest.mark.parametrize("terminal", ["timeout", "cancelled"])
def test_format_private_stdio_terminal_cleanup(tmp_path, terminal):
    import os
    import sys

    from rush.runtime import subprocesses as runtime

    source = tmp_path / "input"
    source.write_bytes(b"input")
    output = tmp_path / "output"
    observed = {}

    def observe_partial():
        if output.exists() and output.stat().st_size > 0:
            observed["pid"] = int(output.read_text().strip())
            if os.name == "nt":
                observed.setdefault(
                    "birth", runtime._windows_process_creation_time(observed["pid"])
                )
                assert observed["birth"] is not None
            assert runtime.read_owned_process_records("format-fixture")
            return terminal == "cancelled"
        return False

    error = (
        subprocess.TimeoutExpired
        if terminal == "timeout"
        else runtime.SubprocessCancelled
    )
    with (
        runtime.cancel_scope(observe_partial, cause="format_fixture_cancelled"),
        pytest.raises(error),
    ):
        runtime.run_subprocess(
            [
                sys.executable,
                "-c",
                "import os,sys,time; print(os.getpid(),flush=True); time.sleep(30)",
            ],
            stdin_path=source,
            stdout_path=output,
            timeout=3,
            owner_instance_id="format-fixture",
            run_id="terminal",
        )
    assert observed["pid"] > 0
    if os.name == "nt":
        assert (
            runtime._windows_process_creation_time(observed["pid"]) != observed["birth"]
        )
    else:
        assert runtime._wait_group_gone(observed["pid"], 1, 0.05) is True
    assert not output.exists()
    assert runtime.read_owned_process_records("format-fixture") == []


@pytest.mark.parametrize("owned", [False, True])
def test_format_stdio_none_keeps_devnull(tmp_path, owned):
    import sys

    from rush.runtime.subprocesses import run_subprocess

    kwargs = (
        {"owner_instance_id": "format-fixture", "run_id": "devnull"} if owned else {}
    )
    result = run_subprocess(
        [sys.executable, "-c", "import sys; print(repr(sys.stdin.buffer.read()))"],
        **kwargs,
    )
    assert result.returncode == 0
    assert result.stdout == "b''\n"


@pytest.mark.parametrize("owned", [False, True])
def test_format_private_stdout_retains_raw_bytes_but_stderr_is_bounded_redacted(
    tmp_path, monkeypatch, owned
):
    import sys

    from rush.runtime.subprocesses import run_subprocess
    from rush.tools import common

    monkeypatch.setattr(common, "MAX_SUBPROCESS_OUTPUT_CHARS", 64)
    source, output = tmp_path / "input", tmp_path / "output"
    source.write_bytes(b"password=hunter2 " + b"x" * 200)
    kwargs = (
        {"owner_instance_id": "format-fixture", "run_id": "redaction"} if owned else {}
    )
    proc = run_subprocess(
        [
            sys.executable,
            "-c",
            "import sys; d=sys.stdin.buffer.read(); sys.stdout.buffer.write(d); sys.stderr.buffer.write(d)",
        ],
        stdin_path=source,
        stdout_path=output,
        **kwargs,
    )
    assert proc.returncode == 0
    assert output.read_bytes() == source.read_bytes()
    assert proc.stdout == ""
    assert proc.stderr == ("password=[REDACTED] " + "x" * 200)[:64] + "[TRUNCATED]"
    assert "hunter2" not in proc.stderr
```
Use existing subprocess-contract module imports/fixtures; subprocess and pytest
already exist there. Existing bounds/redaction assertions remain required,
including raw-output overflow and secret-redaction cases; private output bytes
are never passed through that diagnostic transformation.

Proposed check after shared row implementation:
```bash
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_subprocess_contract.py tests/test_phase70_t17.py tests/test_project_run_lifecycle.py tests/test_phase60_characterization.py -q
```
Exact expectations above plus existing termination/owned-gate/default redaction
regressions. POSIX and Windows gate variants require their native platform tests;
no POSIX-only static check proves Windows behavior.


### Q03-08: Preview artifact location, format and ID derivation unspecified

Artifact path and serialization are literal in Q03-04: .rush/format-previews/<sha256(payload)>.json, sorted-key compact UTF-8 JSON, version=1, files records with relative_path/source_sha256/formatted_sha256/formatted_bytes, formatters, config_sha256 and selected_paths. Paths remain POSIX root-relative; assessed paths are separately absolute logical paths. _config_digests covers each selected file's ancestor configuration files inside root plus recursive contained Ruff extends; cycles, escapes, wrong TOML table shapes, unreadable required staged config and unverified executable import closure fail closed before publication. Formatter configuration/version and captured source identities are checked again after preview execution.

Apply validates digest/schema/output digest/config/version and every selected live source before first write. Verification validates actual staged inputs when active, captures immutable source/test/config bytes, and binds executed sandbox hashes plus actual F5/F4 receipts. Live source/config drift must not be hidden behind a staged alias during apply. Concrete tests: test_preview_extend_configuration_identity_and_wrong_toml_shape, test_formatter_version_or_config_change_is_stale_preview, test_preview_staged_bytes_and_apply_live_drift, test_forged_formatted_digest_is_invalid_preview and test_apply_rejects_changed_preview.

Verification requirement: original report Q03-08 at line 4667; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-09: `metadata.reason` conflicts with the Phase 70 conventions, and grant denial drifts from the audit

replace plan :177-178 and :199-202 with:
```text
Explicit check=False => canonical error, metadata.error.code="unsupported_operation", zero engine
calls/writes. invalid mode/ID/selection/argument combination => status=error,
metadata.error.code="invalid_argument", zero writes. Missing artifact-write grant => status=skipped via
skipped_result("format", None, "requires permission: --allow-artifact-write", metadata={"execution":
build_execution_metadata("executed", requested=ExecutionPermissions(artifact_write=True),
granted=ExecutionPermissions(artifact_write=<flag>), producer="format",
extra={"disposition":"not_run","cause":"permission_denied"})}), zero persistent writes.
Drift from audit:1861/1893 (error) is deliberate: repo convention skips ungranted work
(run_engine docstring, P subprocesses.py:1274 area). Preview success => status=ok, metadata.mode=preview,
returned preview_id/hashes.
```
Replace RED :22 with `assert result["metadata"]["error"]["code"] == "unsupported_operation"`, :73 with `assert applied["metadata"]["error"]["code"] == "stale_preview"`, and parity :314 with
`assert cli["metadata"]["error"]["code"] == mcp["metadata"]["error"]["code"] == "unsupported_operation"`. The implementation is `_grant_denied` in Q03-04.

Verification requirement: original report Q03-09 at line 4689; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-10: Preview/apply metadata contract drifts from the audit

replace plan :90-91 with:
```text
preview ok: engine="preview", metadata={"mode":"preview","preview_id":ID,"selected_paths":[...],
  "records":[{"relative_path","source_sha256","formatted_sha256"}]}
preview formatter missing: status skipped, metadata.scope = child_scope("unavailable", reason="engine_unavailable"), no artifact
preview formatter nonzero exit or timeout: status error, metadata.error.code="formatter_failed", no artifact
preview with a symlinked/escaping source: status error, metadata.error.code="invalid_argument", no artifact
apply ok: engine="preview-apply", metadata={"mode":"apply","preview_id":ID,"changed_paths":[...],
  "written":[{"relative_path","formatted_sha256"}],"partial_write":false}
apply interrupted: error, metadata.error.code="partial_write", changed_paths = written prefix,
  written = receipts for that prefix, partial_write=bool(changed_paths) (no rollback claim)
stale/preflight errors: changed_paths=[], partial_write=false
DECISION-Q03-B (report-derived unapproved proposal, not an approved shipped choice): apply requires a nonempty,
duplicate-free selected_files. Audit alternative (audit:1890): apply every record when selected_files is
omitted.
```
Alternative for DECISION-Q03-B (exact edits to `_apply_preview`; unexecuted):
```diff
-    if (
-        not selected_files
-        or not all(isinstance(s, str) and s for s in selected_files)
-        or len(set(selected_files)) != len(selected_files)
-    ):
+    if selected_files is not None and (
+        not selected_files
+        or not all(isinstance(s, str) and s for s in selected_files)
+        or len(set(selected_files)) != len(selected_files)
+    ):
@@
-        for entry in selected_files:
+        for entry in selected_files or []:
@@
     if by_path is None:
         return error or _apply_error("invalid_preview", "preview unavailable")
+    selected_files = selected_files or list(by_path)
```

Verification requirement: original report Q03-10 at line 4717; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-11: Verification contract drift (key rename, statuses, grants, sandbox)

The Q03-04 source defines the full X1 route, proposed and unexecuted. metadata.preview_verification carries preview_id, ast_equal, tests, eligible and status; actual missing OCI uses status=skipped/reason=isolation_unavailable, while dirty workspace, stale preview, rejection and inconclusive collection remain operation states. Top-level status/findings/scope remain ordinary check for optional unavailable runtime, current-source drift or failed verification; whole-call grant denial is skipped/executed/not_run/permission_denied before ordinary check.

IDs and unique nonempty contained test files are validated before effects. Build+slow preflight precedes ordinary engines, sandbox writes and provider calls. Explicit runtime/image trust is checked through F4 check_isolation_inputs; malformed image returns invalid_argument, unavailable runtime has no host fallback. Preview/config/version/source identity loads precede sandbox creation; required active-stage bytes never fall back to live bytes. Sandbox receives captured source/test/config bytes, then formatted source; AST comparisons use captured Python originals. Actual F5 invocation produces parsed pytest counts, exact argv, .isolated receipt and factual accepted launches. Every receipt binds captured_inputs and executed_inputs. Input/config/version drift after execution invalidates eligibility.

eligible requires unchanged inputs, equal AST, each outcome=passed, positive passed count, zero failed/skipped/error counts and cleanup_confirmed=True. Failed/error/AST changes reject; actual zero collection or skipped counts are inconclusive. F4 timeout/cancel/cleanup errors preserve attached factual receipt/counts in terminal_run; no invented test counts, target starts or cleanup success. Ambient cancellation cause/hit is retained; manager cleanup always runs. Tests are the seven named X1 controllers plus test_format_real_oci_source_bound_verification_and_cleanup; R/E excludes these controllers until F4/F5 exists.

Verification requirement: original report Q03-11 at line 4762; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-12: Named RED/regression bodies

Proposed tests/test_format.py R/E/X controlled-provider source:

```python
"""Q03 rush format: honest check mode, contained preview/apply, isolated verification."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from rush.engines import prettier as prettier_module
from rush.engines import ruff as ruff_module
from rush.engines.prettier import PrettierEngine
from rush.engines.ruff import RuffEngine
from rush.permissions import ExecutionPermissions
from rush.tools import common
from rush.tools import format as format_module
from rush.tools.format import FormatTool


def _child(engine, status="ok", findings=None, files=(), **metadata):
    metadata["engines"] = [
        {
            "engine": engine.name,
            "engine_version": "fixture",
            "status": status,
            "summary": engine.name,
            "subprocess_count": 1 if status != "skipped" else 0,
            "scope": {
                "requested_file_count": len(files),
                "consumption_source": "explicit_arguments",
                "consumed_file_count": len(files)
                if status not in ("error", "skipped")
                else 0,
                "coverage": "complete"
                if status not in ("error", "skipped")
                else "none",
                "reason": None
                if status not in ("error", "skipped")
                else "engine_not_installed"
                if status == "skipped"
                else "engine_error",
            },
        }
    ]
    return {
        "tool": "format",
        "engine": engine.name,
        "engine_version": "fixture",
        "status": status,
        "duration_ms": 0,
        "summary": engine.name,
        "findings": findings or [],
        "raw": None,
        "metadata": metadata,
    }


def _preview(root: Path):
    result = FormatTool().run(
        root, mode="preview", permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "ok", result
    return result["metadata"]["preview_id"]


def _forge(root: Path, preview_id: str, mutate) -> str:
    """Rewrite one preview artifact consistently (new digest, new id)."""
    folder = root / ".rush" / "format-previews"
    data = json.loads((folder / f"{preview_id}.json").read_bytes())
    mutate(data)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    new_id = hashlib.sha256(payload).hexdigest()
    (folder / f"{new_id}.json").write_bytes(payload)
    return new_id


def _git_commit_all(root: Path) -> None:
    for argv in (
        ["git", "init", "-q"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=f@example.test",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(argv, cwd=root, check=True)


def test_explicit_false_is_error_without_execution(tmp_path):
    source = tmp_path / "a.py"
    source.write_bytes(b"x=1\n")
    with patch("rush.tools.format.run_engine") as execute:
        result = FormatTool().run(source, check=False)
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "unsupported_operation"
    execute.assert_not_called()
    assert source.read_bytes() == b"x=1\n"


def test_default_check_is_true_direct():
    assert inspect.signature(FormatTool.run).parameters["check"].default is True
    assert inspect.signature(FormatTool.__call__).parameters["check"].default is True


def test_check_is_read_only_and_partial(tmp_path):
    a, b = (tmp_path / "a.py", tmp_path / "b.ts")
    a.write_bytes(b"x = 1\n")
    b.write_bytes(b"const x = 1;\n")
    original = {p: p.read_bytes() for p in (a, b)}

    def child(engine, path, args, **kw):
        assert kw["selected_targets"] == ([a] if engine.name == "ruff" else [b])
        return _child(
            engine,
            "ok" if engine.name == "ruff" else "skipped",
            files=kw["selected_targets"],
        )

    with patch("rush.tools.format.run_engine", side_effect=child):
        result = FormatTool().run(tmp_path)
    assert result["status"] == "warn"
    aggregation = {
        "partial": result["metadata"]["scope"]["coverage"] == "partial",
        "children": result["metadata"]["engines"],
    }
    assert [(c["engine"], c["status"]) for c in aggregation["children"]] == [
        ("ruff", "ok"),
        ("prettier", "skipped"),
    ]
    assert result["metadata"]["assessed_paths"] == {"ruff": [str(a)], "prettier": []}
    assert result["metadata"]["scope"]["coverage"] == "partial"
    assert aggregation["children"][0]["scope"]["consumed_file_count"] == 1
    assert aggregation["children"][1]["scope"]["reason"] == "engine_not_installed"
    assert "all formatted" not in result["summary"]
    assert {p: p.read_bytes() for p in (a, b)} == original


def test_no_target_is_skipped_no_spawn(tmp_path):
    with patch("rush.tools.format.run_engine") as execute:
        result = FormatTool().run(tmp_path)
    assert result["status"] == "skipped"
    execute.assert_not_called()


def test_engine_without_files_is_not_invoked(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    seen = []

    def child(engine, path, args, **kw):
        seen.append((engine.name, kw["selected_targets"]))
        return _child(engine, files=kw["selected_targets"])

    with patch("rush.tools.format.run_engine", side_effect=child):
        result = FormatTool().run(tmp_path)
    assert seen == [("ruff", [tmp_path / "a.py"])]
    assert result["status"] == "ok"
    assert result["metadata"]["scope"]["coverage"] == "complete"


def test_targets_without_ruff_or_prettier_files_keep_legacy_skip(tmp_path):
    from rush.engines import ENGINES

    owned = {*ENGINES["ruff"].file_extensions, *ENGINES["prettier"].file_extensions}
    extension = next(e for e in ENGINES["squoosh"].file_extensions if e not in owned)
    (tmp_path / f"image.{extension}").write_bytes(b"x")
    with patch("rush.tools.format.run_engine") as execute:
        result = FormatTool().run(tmp_path)
    assert result["status"] == "skipped"
    assert result["metadata"]["scope"]["coverage"] == "none"
    assert result["metadata"]["scope"]["reason"] == "no_supported_targets"
    execute.assert_not_called()


def test_both_engines_absent_skipped(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    (tmp_path / "b.ts").write_bytes(b"const x = 1;\n")
    with patch(
        "rush.tools.format.run_engine",
        side_effect=lambda engine, *a, **k: _child(
            engine, "skipped", files=k["selected_targets"]
        ),
    ):
        result = FormatTool().run(tmp_path)
    aggregation = {"children": result["metadata"]["engines"]}
    assert result["status"] == "skipped"
    assert result["metadata"]["scope"]["coverage"] == "unavailable"
    assert result["metadata"]["scope"]["reason"] == "engine_unavailable"
    assert result["metadata"]["assessed_paths"] == {"ruff": [], "prettier": []}
    assert [c["status"] for c in aggregation["children"]] == ["skipped", "skipped"]
    assert "all formatted" not in result["summary"]


@pytest.mark.parametrize("failing", ["ruff", "prettier"])
def test_engine_error_wins_over_other_child(tmp_path, failing):
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    (tmp_path / "b.ts").write_bytes(b"const x = 1;\n")
    children = {}

    def child(engine, path, args, **kwargs):
        value = _child(
            engine,
            "error" if engine.name == failing else "ok",
            files=kwargs["selected_targets"],
        )
        children[engine.name] = value
        return value

    with patch("rush.tools.format.run_engine", side_effect=child):
        result = FormatTool().run(tmp_path)
    assert result["status"] == "error"
    assert result["metadata"]["scope"]["coverage"] == "partial"
    failed_scope = children[failing]["metadata"]["scope"]
    assert failed_scope["coverage"] == "unavailable"
    assert failed_scope["reason"] == "engine_error"
    assert failed_scope["matched_file_count"] == 1
    assert failed_scope["consumed_file_count"] == 0
    assert result["metadata"]["assessed_paths"][failing] == []


def test_warning_retained_beside_skipped(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x=1\n")
    (tmp_path / "b.ts").write_bytes(b"const x = 1;\n")
    finding = {"path": str(tmp_path / "a.py"), "rule": "formatting", "severity": "warn"}
    with patch(
        "rush.tools.format.run_engine",
        side_effect=lambda engine, *a, **k: _child(
            engine,
            "warn" if engine.name == "ruff" else "skipped",
            findings=[finding] if engine.name == "ruff" else None,
            files=k["selected_targets"],
        ),
    ):
        result = FormatTool().run(tmp_path)
    assert result["status"] == "warn"
    assert result["findings"] == [finding]
    assert result["metadata"]["scope"]["coverage"] == "partial"


def _engine_status(engine, module, argv, returncode, stdout="", stderr="", exc=None):

    def fake(cmd, **_kw):
        if exc is not None:
            raise exc
        return CompletedProcess(cmd, returncode, stdout, stderr)

    with (
        patch.object(module, "run_subprocess", fake),
        patch.object(common, "engine_on_path", lambda _b: True),
    ):
        return common.run_engine(engine, Path("."), argv, tool_name="format")


def test_ruff_exit_2_malformed_output_and_prettier_exit_2_timeout_are_errors():
    assert (
        _engine_status(
            RuffEngine(), ruff_module, ["format", "--check", "a.py"], 2, stderr="boom"
        )["status"]
        == "error"
    )
    assert (
        _engine_status(
            RuffEngine(), ruff_module, ["format", "--check", "a.py"], 1, stdout="{"
        )["status"]
        == "error"
    )
    assert (
        _engine_status(
            PrettierEngine(), prettier_module, ["b.ts"], 2, stderr="Syntax error"
        )["status"]
        == "error"
    )
    timed_out = _engine_status(
        PrettierEngine(),
        prettier_module,
        ["b.ts"],
        0,
        exc=subprocess.TimeoutExpired("prettier", 120),
    )
    assert timed_out["status"] == "error"
    assert timed_out["metadata"]["terminal_reason"] == "timeout"


def _prettier_argv(monkeypatch, tmp_path, args, **kwargs):
    monkeypatch.setattr(prettier_module, "resolve_binary", lambda _b: "prettier-bin")
    calls = []

    def fake(argv, **kw):
        calls.append((argv, kw))
        return CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(prettier_module, "run_subprocess", fake)
    PrettierEngine().run(tmp_path, args, cwd=tmp_path, **kwargs)
    return calls[0]


def test_selected_prettier_paths_once(monkeypatch, tmp_path):
    source = tmp_path / "b.ts"
    source.write_text("const x = 1;\n")
    argv, kw = _prettier_argv(monkeypatch, tmp_path, [], selected_targets=[source])
    assert argv.count("--check") == 1
    assert argv.count(str(source)) == 1
    assert str(tmp_path) not in argv
    assert kw["cwd"] == tmp_path


def test_prettier_none_keeps_root_and_caller_operands(monkeypatch, tmp_path):
    extra = tmp_path / "main.ts"
    argv, _ = _prettier_argv(monkeypatch, tmp_path, [str(extra)])
    assert argv == [
        "prettier-bin",
        "--check",
        "--log-level=warn",
        str(tmp_path),
        str(extra),
    ]


def test_prettier_empty_vector_has_no_operand(monkeypatch, tmp_path):
    argv, _ = _prettier_argv(monkeypatch, tmp_path, [], selected_targets=[])
    assert argv == ["prettier-bin", "--check", "--log-level=warn"]


def test_ruff_format_branch_uses_selected_targets(monkeypatch, tmp_path):
    source = tmp_path / "a.py"
    source.write_text("x = 1\n")
    calls = []
    monkeypatch.setattr(ruff_module, "resolve_binary", lambda _b: "ruff-bin")
    monkeypatch.setattr(
        ruff_module,
        "run_subprocess",
        lambda argv, **kw: calls.append(argv) or CompletedProcess(argv, 0, "[]", ""),
    )
    RuffEngine().run(
        tmp_path, ["format", "--check"], cwd=tmp_path, selected_targets=[source]
    )
    assert calls == [
        [
            "ruff-bin",
            "format",
            "--check",
            "--output-format=json",
            "--no-cache",
            str(source),
        ]
    ]


def test_real_check_assesses_only_selected_files(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x=1\n")
    (tmp_path / "b.py").write_bytes(b"y = 2\n")
    result = FormatTool().run(tmp_path / "a.py")
    assert result["status"] == "warn"
    assert [Path(f["path"]).name for f in result["findings"]] == ["a.py"]
    assert result["metadata"]["assessed_paths"]["ruff"] == [str(tmp_path / "a.py")]
    assert (tmp_path / "a.py").read_bytes() == b"x=1\n"


def test_preview_requires_grant_and_writes_nothing(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x=1\n")
    result = FormatTool().run(tmp_path, mode="preview")
    assert result["status"] == "skipped"
    assert result["metadata"]["execution"]["cause"] == "permission_denied"
    assert not (tmp_path / ".rush").exists()


def test_apply_rejects_changed_preview(tmp_path):
    a, b = (tmp_path / "a.py", tmp_path / "b.py")
    a.write_bytes(b"x=1\n")
    b.write_bytes(b"y=2\n")
    preview_id = _preview(tmp_path)
    b.write_bytes(b"y=99\n")
    original = {p: p.read_bytes() for p in (a, b)}
    applied = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py", "b.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert applied["status"] == "error"
    assert applied["metadata"]["error"]["code"] == "stale_preview"
    assert applied["metadata"]["changed_paths"] == []
    assert applied["metadata"]["partial_write"] is False
    assert {p: p.read_bytes() for p in (a, b)} == original


def test_apply_preview_scope(tmp_path):
    a, b = (tmp_path / "a.py", tmp_path / "b.py")
    a.write_bytes(b"x=1\n")
    b.write_bytes(b"y=2\n")
    preview_id = _preview(tmp_path)
    applied = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert applied["status"] == "ok"
    assert applied["metadata"]["changed_paths"] == ["a.py"]
    assert applied["metadata"]["partial_write"] is False
    assert applied["metadata"]["written"] == [
        {
            "relative_path": "a.py",
            "formatted_sha256": hashlib.sha256(b"x = 1\n").hexdigest(),
        }
    ]
    assert a.read_bytes() == b"x = 1\n"
    assert b.read_bytes() == b"y=2\n"


@pytest.mark.needs_prettier
def test_apply_preview_scope_cross_engine(tmp_path):
    a, b = (tmp_path / "a.py", tmp_path / "b.ts")
    a.write_bytes(b"x=1\n")
    b.write_bytes(b"const  y=2\n")
    preview_id = _preview(tmp_path)
    applied = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert applied["metadata"]["changed_paths"] == ["a.py"]
    assert a.read_bytes() == b"x = 1\n"
    assert b.read_bytes() == b"const  y=2\n"
    b.write_bytes(b"const  y=99\n")
    stale = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py", "b.ts"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert stale["metadata"]["error"]["code"] == "stale_preview"
    assert b.read_bytes() == b"const  y=99\n"


def test_apply_without_grant_is_skipped_and_writes_nothing(tmp_path):
    a = tmp_path / "a.py"
    a.write_bytes(b"x=1\n")
    preview_id = _preview(tmp_path)
    result = FormatTool().run(
        tmp_path, mode="apply", preview_id=preview_id, selected_files=["a.py"]
    )
    assert result["status"] == "skipped"
    assert result["metadata"]["execution"]["cause"] == "permission_denied"
    assert a.read_bytes() == b"x=1\n"


def test_apply_partial_io_failure_receipt(tmp_path, monkeypatch):
    a, b = (tmp_path / "a.py", tmp_path / "b.py")
    a.write_bytes(b"x=1\n")
    b.write_bytes(b"y=2\n")
    preview_id = _preview(tmp_path)
    real = format_module.atomic_write_bytes
    calls = []

    def flaky(root, relative, data, **kw):
        calls.append(str(relative))
        if len(calls) == 2:
            raise OSError("fixture")
        return real(root, relative, data, **kw)

    monkeypatch.setattr(format_module, "atomic_write_bytes", flaky)
    applied = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py", "b.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert applied["status"] == "error"
    assert applied["metadata"]["error"]["code"] == "partial_write"
    assert applied["metadata"]["changed_paths"] == ["a.py"]
    assert applied["metadata"]["partial_write"] is True
    assert applied["metadata"]["written"] == [
        {
            "relative_path": "a.py",
            "formatted_sha256": hashlib.sha256(b"x = 1\n").hexdigest(),
        }
    ]
    assert a.read_bytes() == b"x = 1\n"
    assert b.read_bytes() == b"y=2\n"


def test_apply_preserves_file_mode(tmp_path):
    a = tmp_path / "a.py"
    a.write_bytes(b"x=1\n")
    os.chmod(a, 493)
    preview_id = _preview(tmp_path)
    FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert stat.S_IMODE(os.stat(a).st_mode) == 493
    assert a.read_bytes() == b"x = 1\n"


def test_atomic_write_bytes_mode_default_unchanged_and_mode_applied(tmp_path):
    from rush.tools.common import atomic_write_bytes

    target = tmp_path / "f.bin"
    target.write_bytes(b"old")
    os.chmod(target, 420)
    atomic_write_bytes(tmp_path, "f.bin", b"new")
    assert stat.S_IMODE(os.stat(target).st_mode) == 384
    atomic_write_bytes(tmp_path, "f.bin", b"newer", mode=416)
    assert stat.S_IMODE(os.stat(target).st_mode) == 416
    assert target.read_bytes() == b"newer"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "write"},
        {"mode": "apply", "preview_id": "zz", "selected_files": ["a.py"]},
        {"mode": "apply", "preview_id": "A" * 64, "selected_files": ["a.py"]},
        {"mode": "apply", "preview_id": "0" * 64},
        {"mode": "apply", "preview_id": "0" * 64, "selected_files": []},
        {"mode": "apply", "preview_id": "0" * 64, "selected_files": ["a.py", "a.py"]},
        {"mode": "check", "preview_id": "0" * 64},
        {"mode": "preview", "selected_files": ["a.py"]},
    ],
)
def test_invalid_arguments_error_and_write_nothing(tmp_path, kwargs):
    (tmp_path / "a.py").write_bytes(b"x=1\n")
    result = FormatTool().run(
        tmp_path, permissions=ExecutionPermissions(artifact_write=True), **kwargs
    )
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "invalid_argument"
    assert (tmp_path / "a.py").read_bytes() == b"x=1\n"
    assert not (tmp_path / ".rush").exists()


def test_symlink_and_escape_selections_are_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"z=3\n")
    (root / "a.py").write_bytes(b"x=1\n")
    preview_id = _preview(root)
    (root / "link.py").symlink_to(outside)
    for selected in ("link.py", "../outside.py", str(outside)):
        result = FormatTool().run(
            root,
            mode="apply",
            preview_id=preview_id,
            selected_files=[selected],
            permissions=ExecutionPermissions(artifact_write=True),
        )
        assert result["status"] == "error"
        assert result["metadata"]["error"]["code"] == "invalid_argument"
    assert outside.read_bytes() == b"z=3\n"
    assert (root / "a.py").read_bytes() == b"x=1\n"


def test_preview_rejects_symlinked_source_and_writes_no_artifact(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"z=3\n")
    (root / "link.py").symlink_to(outside)
    result = FormatTool().run(
        root, mode="preview", permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "invalid_argument"
    assert not (root / ".rush").exists()


def test_tampered_or_missing_preview_is_invalid_and_writes_nothing(tmp_path):
    a = tmp_path / "a.py"
    a.write_bytes(b"x=1\n")
    preview_id = _preview(tmp_path)
    artifact = tmp_path / ".rush" / "format-previews" / f"{preview_id}.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")
    for pid in (preview_id, "1" * 64):
        result = FormatTool().run(
            tmp_path,
            mode="apply",
            preview_id=pid,
            selected_files=["a.py"],
            permissions=ExecutionPermissions(artifact_write=True),
        )
        assert result["status"] == "error"
        assert result["metadata"]["error"]["code"] == "invalid_preview"
    assert a.read_bytes() == b"x=1\n"


def test_forged_formatted_digest_is_invalid_preview(tmp_path):
    a = tmp_path / "a.py"
    a.write_bytes(b"x=1\n")
    preview_id = _preview(tmp_path)

    def mutate(data):
        data["files"][0]["formatted_bytes"] = base64.b64encode(b"import os\n").decode()

    forged = _forge(tmp_path, preview_id, mutate)
    result = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=forged,
        selected_files=["a.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert result["metadata"]["error"]["code"] == "invalid_preview"
    assert a.read_bytes() == b"x=1\n"


def test_formatter_version_or_config_change_is_stale_preview(tmp_path):
    a = tmp_path / "a.py"
    a.write_bytes(b"x=1\n")
    preview_id = _preview(tmp_path)
    (tmp_path / "ruff.toml").write_text("line-length = 100\n")
    result = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert result["metadata"]["error"]["code"] == "stale_preview"
    assert a.read_bytes() == b"x=1\n"


def test_preview_missing_formatter_is_skipped_without_artifact(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"x=1\n")
    monkeypatch.setattr(format_module, "resolve_binary", lambda _b: None)
    result = FormatTool().run(
        tmp_path, mode="preview", permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "skipped"
    assert result["metadata"]["scope"]["reason"] == "engine_unavailable"
    assert not (tmp_path / ".rush").exists()


def test_preview_formatter_failure_is_error_without_artifact(tmp_path):
    (tmp_path / "a.py").write_bytes(b"def broken(:\n    pass\n")
    result = FormatTool().run(
        tmp_path, mode="preview", permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "formatter_failed"
    assert not (tmp_path / ".rush").exists()


def _isolated_fake(spawns, status="ok", suites=True):
    """Controlled F4 double, real F5 parsing and actual pytest execution.
    This host oracle proves orchestration/count parsing, never OCI isolation.
    """
    from rush.runtime.isolated_process import IsolatedRun

    from rush.runtime import isolated_tests as it

    def isolated(sandbox, scratch, **kwargs):
        spawns.append(kwargs["nodes"])
        assert kwargs["nodes"] == ["tests/test_a.py::test_a"]

        def provider(root, out, **invocation):
            env = {**os.environ, "RUSH_FORMAT_CASE": status}
            if not suites:
                env["PYTEST_ADDOPTS"] = "-k no_selected_case"
            command = [sys.executable, *invocation["argv"]]
            proc = subprocess.run(
                command,
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            receipt = {
                "fixture_kind": "controlled_host_oracle",
                "cleanup_confirmed": True,
                "argv": command,
                "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
            }
            return IsolatedRun(proc.returncode, proc.stdout, proc.stderr, 1, receipt)

        with patch.object(it, "run_isolated_argv", provider):
            return it.run_selected_tests_isolated(sandbox, scratch, **kwargs)

    return isolated


@pytest.fixture(autouse=True)
def _controlled_verification_preflight(monkeypatch, request):
    x1_names = {
        "test_preview_ast_and_test_gate",
        "test_verification_rejects_failed_selected_test",
        "test_verification_with_skipped_or_empty_tests_is_inconclusive",
        "test_verification_rejects_changed_ast",
        "test_verification_isolation_unavailable_and_dirty_workspace",
        "test_verification_requires_build_and_slow_grants_and_selected_tests",
        "test_verification_denial_precedes_ordinary_effects",
    }
    if request.node.name.split("[", 1)[0] not in x1_names:
        return
    # Unit orchestration fixture only. Runtime trust remains independently
    # covered by F4 preflight tests and test_format_oci.py real acceptance.
    from rush.runtime import isolated_process as ip

    monkeypatch.setattr(ip, "check_isolation_inputs", lambda *_a, **_kw: None)


def _verify_options(preview_id):
    return {
        "verify_preview_id": preview_id,
        "verification_tests": ["tests/test_a.py::test_a"],
        "runtime_path": Path("/usr/local/bin/approved-oci"),
        "image_ref": "rush@sha256:" + "a" * 64,
        "permissions": ExecutionPermissions(build=True, slow=True),
    }


def _verify_project(tmp_path):
    source = tmp_path / "a.py"
    source.write_text("x=1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "import os, pytest\ndef test_a():\n    mode = os.environ.get('RUSH_FORMAT_CASE', 'ok')\n    if mode == 'skipped': pytest.skip('controlled oracle')\n    assert mode != 'fail'\n"
    )
    _git_commit_all(tmp_path)
    return (source, _preview(tmp_path))


def test_preview_ast_and_test_gate(tmp_path, monkeypatch):
    source, preview_id = _verify_project(tmp_path)
    spawns = []
    monkeypatch.setattr(
        "rush.runtime.isolated_tests.run_selected_tests_isolated",
        _isolated_fake(spawns),
    )
    options = _verify_options(preview_id)
    accepted = FormatTool().run(source, **options)["metadata"]["preview_verification"]
    assert accepted["eligible"] is True and accepted["ast_equal"] is True
    assert accepted["status"] == "eligible"
    assert source.read_text() == "x=1\n"
    source.write_text("x=2\n")
    stale = FormatTool().run(source, **options)["metadata"]["preview_verification"]
    assert stale["status"] == "stale_preview" and stale["eligible"] is False
    assert len(spawns) == 1


def test_verification_rejects_failed_selected_test(tmp_path, monkeypatch):
    source, preview_id = _verify_project(tmp_path)
    spawns = []
    monkeypatch.setattr(
        "rush.runtime.isolated_tests.run_selected_tests_isolated",
        _isolated_fake(spawns, status="fail"),
    )
    verdict = FormatTool().run(source, **_verify_options(preview_id))["metadata"][
        "preview_verification"
    ]
    assert verdict["status"] == "rejected" and verdict["eligible"] is False


def test_verification_with_skipped_or_empty_tests_is_inconclusive(
    tmp_path, monkeypatch
):
    source, preview_id = _verify_project(tmp_path)
    for status, suites in (("skipped", True), ("ok", False)):
        monkeypatch.setattr(
            "rush.runtime.isolated_tests.run_selected_tests_isolated",
            _isolated_fake([], status=status, suites=suites),
        )
        verdict = FormatTool().run(source, **_verify_options(preview_id))["metadata"][
            "preview_verification"
        ]
        assert verdict["status"] == "inconclusive" and verdict["eligible"] is False


def test_verification_rejects_changed_ast(tmp_path, monkeypatch):
    source, preview_id = _verify_project(tmp_path)

    def mutate(data):
        record = data["files"][0]
        changed = b"x = 2\n"
        record["formatted_bytes"] = base64.b64encode(changed).decode()
        record["formatted_sha256"] = hashlib.sha256(changed).hexdigest()

    forged = _forge(tmp_path, preview_id, mutate)
    spawns = []
    monkeypatch.setattr(
        "rush.runtime.isolated_tests.run_selected_tests_isolated",
        _isolated_fake(spawns),
    )
    verdict = FormatTool().run(source, **_verify_options(forged))["metadata"][
        "preview_verification"
    ]
    assert verdict["ast_equal"] is False
    assert verdict["status"] == "rejected" and verdict["eligible"] is False


def test_verification_isolation_unavailable_and_dirty_workspace(tmp_path, monkeypatch):
    from rush.runtime.isolated_process import IsolationUnavailable

    source, preview_id = _verify_project(tmp_path)

    def unavailable(*_a, **_k):
        raise IsolationUnavailable("fixture")

    monkeypatch.setattr(
        "rush.runtime.isolated_tests.run_selected_tests_isolated", unavailable
    )
    verdict = FormatTool().run(source, **_verify_options(preview_id))["metadata"][
        "preview_verification"
    ]
    assert (
        verdict["status"] == "skipped"
        and verdict["reason"] == "isolation_unavailable"
        and verdict["eligible"] is False
    )
    (tmp_path / "junk.txt").write_text("untracked\n")
    spawns = []
    monkeypatch.setattr(
        "rush.runtime.isolated_tests.run_selected_tests_isolated",
        _isolated_fake(spawns),
    )
    dirty = FormatTool().run(source, **_verify_options(preview_id))["metadata"][
        "preview_verification"
    ]
    assert dirty["status"] == "dirty_workspace" and spawns == []


def test_verification_requires_build_and_slow_grants_and_selected_tests(
    tmp_path, monkeypatch
):
    source, preview_id = _verify_project(tmp_path)
    spawns = []
    monkeypatch.setattr(
        "rush.runtime.isolated_tests.run_selected_tests_isolated",
        _isolated_fake(spawns),
    )
    for grant in (
        {"permissions": ExecutionPermissions(slow=True)},
        {"permissions": ExecutionPermissions(build=True)},
    ):
        denied = FormatTool().run(source, **{**_verify_options(preview_id), **grant})
        assert denied["status"] == "skipped"
        assert denied["metadata"]["execution"]["cause"] == "permission_denied"
    no_tests = FormatTool().run(
        source, **{**_verify_options(preview_id), "verification_tests": []}
    )
    assert no_tests["status"] == "error"
    assert no_tests["metadata"]["error"]["code"] == "invalid_argument"
    escaped = FormatTool().run(
        source, **{**_verify_options(preview_id), "verification_tests": ["../x.py::t"]}
    )
    assert escaped["status"] == "error"
    assert escaped["metadata"]["error"]["code"] == "invalid_argument"
    assert spawns == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "preview", "verify_preview_id": "0" * 64},
        {"verification_tests": ["tests/test_a.py::t"]},
    ],
)
def test_misplaced_verification_arguments_error(tmp_path, kwargs):
    (tmp_path / "a.py").write_bytes(b"x=1\n")
    result = FormatTool().run(
        tmp_path, permissions=ExecutionPermissions(artifact_write=True), **kwargs
    )
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "invalid_argument"
    assert not (tmp_path / ".rush").exists()


def test_relative_nested_directory_uses_absolute_operand_and_cwd(tmp_path, monkeypatch):
    root = tmp_path / "src"
    nested = root / "nested"
    nested.mkdir(parents=True)
    source = nested / "a.py"
    source.write_bytes(b"x=1\n")
    monkeypatch.chdir(tmp_path)
    calls = []
    real = ruff_module.run_subprocess

    def capture(argv, **kwargs):
        calls.append((argv, kwargs.get("cwd")))
        return real(argv, **kwargs)

    monkeypatch.setattr(ruff_module, "run_subprocess", capture)
    result = FormatTool().run(Path("src"))
    main = [(argv, cwd) for argv, cwd in calls if len(argv) > 1 and argv[1] == "format"]
    assert len(main) == 1
    argv, cwd = main[0]
    assert argv[-1] == str(source.absolute())
    assert Path(argv[-1]).is_absolute()
    assert cwd == root.absolute()
    assert str(root / "src") not in argv[-1]
    assert result["status"] == "warn"
    assert result["metadata"]["assessed_paths"]["ruff"] == [str(source.absolute())]
    assert source.read_bytes() == b"x=1\n"


@pytest.mark.parametrize("returncode", [0, 2])
def test_actual_consumption_and_engine_error_scope(tmp_path, monkeypatch, returncode):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("y = 2\n")
    captured = []

    def child(engine, path, args, **kwargs):
        value = _child(
            engine,
            "ok" if returncode == 0 else "error",
            files=kwargs["selected_targets"],
        )
        value["metadata"]["engines"][0]["scope"] = {
            "requested_file_count": 2,
            "consumed_file_count": 1,
            "consumption_source": "engine_show_files",
            "consumed_files": [str(a)],
            "configuration_files": [],
            "coverage": "complete",
            "reason": None,
        }
        captured.append(value)
        return value

    monkeypatch.setattr(format_module, "run_engine", child)
    result = FormatTool().run(tmp_path)
    assert result["status"] == ("warn" if returncode == 0 else "error")
    assert result["metadata"]["assessed_paths"]["ruff"] == (
        [str(a)] if returncode == 0 else []
    )
    assert result["metadata"]["scope"]["coverage"] == (
        "partial" if returncode == 0 else "unavailable"
    )
    assert captured[0]["metadata"]["scope"]["reason"] == (
        "requested_files_not_consumed" if returncode == 0 else "engine_error"
    )
    assert result["metadata"]["engines"][0]["scope"]["consumed_files"] == [str(a)]
    if returncode == 0:
        assert "requested_files_not_consumed" in result["summary"]
        assert str(b) in result["summary"]
    else:
        assert result["metadata"]["scope"]["reason"] == "engine_error"


def test_preview_staged_bytes_and_apply_live_drift(tmp_path):
    from rush.engines.staging import stage_inventory, staging_scope

    root = tmp_path / "project"
    root.mkdir()
    source = root / "a.py"
    source.write_bytes(b"x=1\n")
    stage = stage_inventory(root, tmp_path / "stage", ["a.py"])
    source.write_bytes(b"x=9\n")
    with staging_scope(stage):
        preview_id = _preview(root)
        artifact = json.loads(
            (root / ".rush" / "format-previews" / f"{preview_id}.json").read_bytes()
        )
        assert (
            artifact["files"][0]["source_sha256"]
            == hashlib.sha256(b"x=1\n").hexdigest()
        )
        assert base64.b64decode(artifact["files"][0]["formatted_bytes"]) == b"x = 1\n"
        applied = FormatTool().run(
            root,
            mode="apply",
            preview_id=preview_id,
            selected_files=["a.py"],
            permissions=ExecutionPermissions(artifact_write=True),
        )
    assert applied["metadata"]["error"]["code"] == "stale_preview"
    assert applied["metadata"]["changed_paths"] == []
    assert source.read_bytes() == b"x=9\n"


def test_preview_extend_configuration_identity_and_wrong_toml_shape(tmp_path):
    source = tmp_path / "a.py"
    source.write_bytes(b"x=1\n")
    (tmp_path / "ruff.toml").write_text('extend = "base.toml"\n')
    (tmp_path / "base.toml").write_text("line-length = 88\n")
    preview_id = _preview(tmp_path)
    (tmp_path / "base.toml").write_text("line-length = 100\n")
    result = FormatTool().run(
        tmp_path,
        mode="apply",
        preview_id=preview_id,
        selected_files=["a.py"],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert result["metadata"]["error"]["code"] == "stale_preview"
    assert result["metadata"]["changed_paths"] == []
    for wrong in ('tool = "x"\n', '[tool]\nruff = "x"\n'):
        (tmp_path / "pyproject.toml").write_text(wrong)
        denied = FormatTool().run(
            tmp_path,
            mode="preview",
            permissions=ExecutionPermissions(artifact_write=True),
        )
        assert denied["status"] == "error"
        assert denied["metadata"]["error"]["code"] == "invalid_argument"


def test_verification_denial_precedes_ordinary_effects(tmp_path, monkeypatch):
    source, preview_id = _verify_project(tmp_path)
    calls = []
    monkeypatch.setattr(
        format_module, "run_engine", lambda *_a, **_kw: calls.append("ordinary")
    )
    monkeypatch.setattr(
        "rush.runtime.isolated_tests.run_selected_tests_isolated",
        lambda *_a, **_kw: calls.append("oracle"),
    )
    result = FormatTool().run(
        source, **{**_verify_options(preview_id), "permissions": ExecutionPermissions()}
    )
    assert result["status"] == "skipped"
    assert result["metadata"]["execution"]["disposition"] == "not_run"
    assert (
        result["metadata"]["preview_verification"]["reason"] == "build_or_slow_denied"
    )
    assert calls == []
    assert source.read_bytes() == b"x=1\n"
```

R/E selection before F4/F5: tests/test_format.py excludes only the seven exact X1 controller names listed in _controlled_verification_preflight. Their F4 imports are lazy; no fake module or live skip masks missing prerequisites. Q03-16 and final checks use that exact -k exclusion before X1; after F4/F5, run the whole module and live OCI acceptance.

### Q03-13: "Foundation F5 selected-test helper" is undefined, and the in-container command is wrong

F5 run_selected_tests_isolated nodes=verification_tests, python_entrypoint="/usr/local/bin/python",timeout_s=300 (D4 proposal). Audit deviation: no rush.__main__, no --test-path/--test-environment, omitted --allow-build; F5 directly invokes selected pytest and parses counts. No Q04 forwarding invention.

Verification requirement: original report Q03-13 at line 5616; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.


Proposed complete `tests/test_format_oci.py` (F4/F5 and approved local Python image required; no live skip):
```python
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from rush.permissions import ExecutionPermissions
from rush.runtime.subprocesses import run_subprocess
from rush.tools.format import FormatTool


@pytest.mark.oci_isolation
def test_format_real_oci_source_bound_verification_and_cleanup(tmp_path, monkeypatch):
    runtime = Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image = os.environ["RUSH_TEST_PYTHON_IMAGE"]
    assert runtime.is_absolute()
    assert re.fullmatch(r"[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}", image)
    inspect = run_subprocess([str(runtime), "image", "inspect", image])
    assert inspect.returncode == 0, inspect.stderr
    root = tmp_path / "project"
    root.mkdir()
    source = root / "a.py"
    source.write_bytes(b"x=1\n")
    tests = root / "tests"
    tests.mkdir()
    node = tests / "test_a.py"
    node.write_text(
        "import ast\nfrom pathlib import Path\n"
        "def test_a():\n"
        "    source = Path('/work/a.py').read_text()\n"
        "    assert source == 'x = 1\\n'\n"
        "    assert ast.literal_eval(ast.parse(source).body[0].value) == 1\n"
    )
    for argv in (
        ["git", "init", "-q"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=f@example.test",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(argv, cwd=root, check=True)
    preview = FormatTool().run(
        root,
        mode="preview",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert preview["status"] == "ok", preview
    result = FormatTool().run(
        source,
        verify_preview_id=preview["metadata"]["preview_id"],
        verification_tests=["tests/test_a.py::test_a"],
        runtime_path=runtime,
        image_ref=image,
        permissions=ExecutionPermissions(build=True, slow=True),
    )
    v = result["metadata"]["preview_verification"]
    assert (
        v["status"] == "eligible" and v["eligible"] is True and v["ast_equal"] is True
    )
    oracle = v["tests"][0]
    assert oracle["counts"] == {"passed": 1, "failed": 0, "skipped": 0, "error": 0}
    assert oracle["argv"] == [
        "-m",
        "pytest",
        "-q",
        "--tb=line",
        "tests/test_a.py::test_a",
    ]
    assert v["captured_inputs"]["a.py"] == hashlib.sha256(b"x=1\n").hexdigest()
    assert v["executed_inputs"]["a.py"] == hashlib.sha256(b"x = 1\n").hexdigest()
    assert (
        v["captured_inputs"]["tests/test_a.py"]
        == v["executed_inputs"]["tests/test_a.py"]
        == hashlib.sha256(node.read_bytes()).hexdigest()
    )
    receipt = oracle["isolation_receipt"]
    assert receipt["runtime_path"] == str(runtime)
    assert receipt["runtime_sha256"] == hashlib.sha256(runtime.read_bytes()).hexdigest()
    assert receipt["image_ref"] == image
    assert receipt["image_digest"] == image.split("@", 1)[1]
    assert receipt["network"] == "none"
    assert receipt["cleanup_confirmed"] is True
    assert receipt["process_launches"] == oracle["process_launches"] > 0
    gone = run_subprocess(
        [str(runtime), "container", "inspect", receipt["container_name"]]
    )
    assert gone.returncode != 0
    assert source.read_bytes() == b"x=1\n"
    assert not (root / "forbidden").exists()
```
The controlled host oracle in Q03-12 proves actual pytest count parsing only.
This separate real OCI route proves provider identity, executed bytes, read-only
source mounts, receipt propagation and confirmed container cleanup. Supplied
runtime plus missing/unpinned image fails; unset runtime deselects via Foundation.

### Q03-14: Parity RED fails with JSONDecodeError; the reviewer's exit-code guard is itself wrong

replace plan :286-287 and the helper's tail. Put the bodies in a new `tests/test_format_parity.py` (the file keeps the module-level MCP imports out of the unit-test module; add it to Completion). Full file (proposed, unexecuted; consumes Foundation F6):
```python
import os
import re
from pathlib import Path

import pytest
from transport_parity import run_cli, run_mcp

CLI_EXIT = {"ok": 0, "skipped": 0, "warn": 1, "fail": 1, "error": 2}


def assert_real_transport_parity(command, arguments, cli_options, expected):
    code, cli_result = run_cli(command, arguments["path"], cli_options)
    mcp_result = run_mcp("rush_" + command, arguments)
    assert code == CLI_EXIT[expected]
    for result in (cli_result, mcp_result):
        assert result["tool"] == command
        assert result["status"] == expected
    for key in ("findings", "engine", "scope", "assessed_paths"):
        if key in ("scope", "assessed_paths"):
            assert cli_result.get("metadata", {}).get(key) == mcp_result.get(
                "metadata", {}
            ).get(key)
        else:
            assert cli_result.get(key) == mcp_result.get(key)
    return cli_result, mcp_result


def test_format_cli_mcp_explicit_false_parity(tmp_path):
    source = tmp_path / "a.py"
    source.write_bytes(b"x=1\n")
    cli, mcp = assert_real_transport_parity(
        "format", {"path": str(source), "check": False}, ["--no-check"], "error"
    )
    assert (
        cli["metadata"]["error"]["code"]
        == mcp["metadata"]["error"]["code"]
        == "unsupported_operation"
    )
    assert source.read_bytes() == b"x=1\n"


def test_format_cli_mcp_default_is_check_only_parity(tmp_path):
    source = tmp_path / "a.py"
    source.write_bytes(b"x=1\n")
    cli, _ = assert_real_transport_parity("format", {"path": str(source)}, [], "warn")
    assert [f["path"] for f in cli["findings"]] == [str(source)]
    assert source.read_bytes() == b"x=1\n"


def test_format_mcp_selected_file_escape_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "x.py").write_bytes(b"z=3\n")
    (root / "a.py").write_bytes(b"x=1\n")
    cli, mcp = assert_real_transport_parity(
        "format",
        {
            "path": str(root),
            "mode": "apply",
            "preview_id": "0" * 64,
            "selected_files": ["../x.py"],
            "allow_artifact_write": True,
        },
        [
            "--mode",
            "apply",
            "--preview-id",
            "0" * 64,
            "--selected-file",
            "../x.py",
            "--allow-artifact-write",
        ],
        "error",
    )
    assert (
        cli["metadata"]["error"]["code"]
        == mcp["metadata"]["error"]["code"]
        == "invalid_argument"
    )
    assert (tmp_path / "x.py").read_bytes() == b"z=3\n"


@pytest.mark.oci_isolation
def test_format_mcp_relative_runtime_is_unanchored_without_provider_launch(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "a.py"
    source.write_bytes(b"x=1\n")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text(
        "def test_a():\n"
        "    raise AssertionError('relative runtime must never launch selected tests')\n"
    )
    probe = tmp_path / "docker"
    launched = tmp_path / "provider-launched"
    probe.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path({str(launched)!r}).write_text('provider/probe invoked')\n"
        "raise SystemExit(1)\n"
    )
    probe.chmod(0o755)
    image = os.environ["RUSH_TEST_PYTHON_IMAGE"]
    assert re.fullmatch(r"[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}", image)
    code, preview = run_cli(
        "format",
        source,
        ["--mode", "preview", "--allow-artifact-write"],
    )
    assert code == 0 and preview["status"] == "ok"
    baseline = run_mcp("rush_format", {"path": str(source)})
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    relative_runtime = os.path.relpath(probe, root)
    assert not Path(relative_runtime).is_absolute()
    result = run_mcp(
        "rush_format",
        {
            "path": str(source),
            "verify_preview_id": preview["metadata"]["preview_id"],
            "verification_tests": ["tests/test_a.py::test_a"],
            "runtime_path": relative_runtime,
            "image_ref": image,
            "allow_build": True,
            "allow_slow": True,
        },
    )
    assert result["status"] == baseline["status"] == "warn"
    assert result["findings"] == baseline["findings"]
    for key in ("scope", "assessed_paths"):
        assert result["metadata"][key] == baseline["metadata"][key]
    verdict = result["metadata"]["preview_verification"]
    assert verdict["status"] == "skipped"
    assert verdict["reason"] == "isolation_unavailable"
    assert verdict["summary"] == "Runtime must be an absolute docker or podman path"
    assert verdict["eligible"] is False and verdict["tests"] == []
    assert not launched.exists()
    assert {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    } == before
```
Add under plan :316: `Expected RED at C and P: AssertionError: Usage: python -m rush.cli format [OPTIONS] PATH ... Error: No such option '--no-check'.`

Verification requirement: original report Q03-14 at line 5637; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-15: MCP transport: `selected_files` is not contained and `isolation_runtime` is not anchored at 66c6c79

Foundation Q03-MCP-containment retains selected_files validation below. runtime_path is deliberately absent from _CWD_RELATIVE_ARGS: a relative value must reach F4 unchanged and be rejected before any OCI probe/provider launch. Proposed source behavior and transport regression remain unexecuted.

and state in Required behavior: `_apply_preview` validates every `selected_files` entry with `PhysicalRoot(root).open_contained(entry)` (catching `ContainmentError`) before the preview is loaded or any write.

Verification requirement: original report Q03-15 at line 5770; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-16: Checks list a nonexistent test file and omit affected suites, mypy and the docs gate

Create `tests/test_format.py`, `tests/test_format_parity.py` and
`tests/test_prettier_honest.py` (absent at C and P) with the concrete bodies here.
The literal commands in **Checks to run before reporting** below are the sole
authoritative replacement for original plan :335–337: Stage A R/E union with
seven X1 exclusions and no `oci_isolation` cases; post-F4/F5 full modules and
marked live suite; then full-suite acceptance. That section also retains Ruff
lint/format, mypy, same-packet documentation and Git diff gates. Do not run X1
controller/provider cases before both F4 and F5 prerequisites are accepted.

Verification requirement: original report Q03-16 at line 5799; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-17: Template nonconformance, approval gates, `Status`, ordering

Template Feature/Required behavior/Deliverables/Constraints/Checks/Completion. No Status line or independent approval gate. Applicable README decisions only; literal file map above. Foundation shared rows; runtime/filesystem Q03, Ruff M2 Q02. New format_parity/prettier_honest/format_oci modules explicit.

Verification requirement: original report Q03-17 at line 5819; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-18: CLI flag names and before/after worked examples dropped

add a subsection "Worked examples" to the plan:
```text
Check (R3), CLI: rush format src --json   MCP: {"tool":"rush_format","arguments":{"path":"src"}}
 Before (C): fixture a.py formatted + b.ts, Prettier absent -> {"status":"ok","summary":"format [ruff]: all formatted"}
   (at P: "warn", engine summary only)
 After:  {"status":"warn","summary":"format [ruff+prettier]: partial assessment; prettier skipped",
   "metadata":{"scope":{"version":1,"kind":"aggregate","coverage":"partial"},
   "assessed_paths":{"ruff":["/project/src/a.py"],"prettier":[]},
   "engines":[{"engine":"ruff","status":"ok"},{"engine":"prettier","status":"skipped"}]}}   (X-D5 conditional proposal; preserved engines entries also include actual subprocess/scope evidence)
 check=False / --no-check -> status error, metadata.error.code "unsupported_operation", zero engine calls.
Preview then apply (E1):
 rush format src --mode preview --allow-artifact-write --json
   -> {"status":"ok","metadata":{"mode":"preview","preview_id":"<64 hex>","selected_paths":["a.py"],"records":[...]}}
 rush format src --mode apply --preview-id <64 hex> --selected-file a.py --allow-artifact-write --json
   MCP: {"tool":"rush_format","arguments":{"path":"src","mode":"apply","preview_id":"<64 hex>",
         "selected_files":["a.py"],"allow_artifact_write":true}}
   Before: a.py = b"x=1\n".  After: {"status":"ok","metadata":{"mode":"apply","changed_paths":["a.py"],
   "partial_write":false}} and a.py = b"x = 1\n" (mode bits preserved). A selected file edited after the
   preview -> error/stale_preview, no file changed.
Verification (X1): rush format a.py --verify-preview-id <64 hex> --verification-test tests/test_a.py::test_a
   --runtime-path "$RUSH_TEST_OCI_RUNTIME" --image-ref "$RUSH_TEST_RUSH_IMAGE" --allow-build --allow-slow --json
   -> metadata.preview_verification = {"preview_id":"<id>","ast_equal":true,"tests":[...],"eligible":true,"status":"eligible"};
   source drift leaves ordinary top-level check status/findings/scope intact and sets metadata.preview_verification.status="stale_preview", eligible=false, zero test spawns. Source is never written.
Why not existing behaviour: `rush fix` rewrites whole targets with `ruff format` and has no preview, digest
binding or per-file selection (src/rush/tools/fix.py:511-519); PatchApplyTool requires a clean Git tree and verifies
whole patches (audit:1764).
```

Verification requirement: original report Q03-18 at line 5860; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-19: Reference docs not scheduled, and the docs gate (receipts and contracts) is ignored

Foundation Q03-DOC-reference owns exact CLI/MCP reference and historical leading Current status replacements below. Q03-DOC-receipts owns the defined regeneration body.

replace plan :232-234 with a Docs deliverable list. Stage A edits (anchor to replacement, exact; all validated against the docs gate):
  - `docs/reference/cli-reference.md`:
    - ``` `format` also exposes `--check`. ``` becomes ``` `format` exposes `--check/--no-check` (default `--check`; `--no-check` is rejected), `--mode check|preview|apply`, `--preview-id`, and repeatable `--selected-file`. ```
    - `uv run rush format PATH [--check] [--json]` becomes `uv run rush format PATH [--check] [--mode check|preview|apply] [--preview-id ID] [--selected-file REL]... [--json]`
    - ``` The exception is `format` without `--check`, which can invoke formatter write modes; use version control and inspect the diff. ``` becomes ``` `format` never writes in `--mode check` (the default). `--mode preview` writes only `.rush/format-previews/<id>.json`, and `--mode apply` rewrites only the `--selected-file` files whose bytes still match that preview; both need `--allow-artifact-write`. Use version control and inspect the diff before applying. ```
  - `docs/reference/mcp-tool-reference.md`: ``` - `rush_format`: `path`, check-mode options. ``` becomes ``` - `rush_format`: required `path`; `check=true` (`false` returns `unsupported_operation`); `mode` (`check` default, `preview`, `apply`); `preview_id`; `selected_files`; `allow_artifact_write` (required for `preview` and `apply`). ```
  - Historical docs `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md` (and `docs/TOOL_CATALOG.md`, Q03-20): insert as superseded draft lines, before `# ...`:
```text
Current status: historical reference. `rush format` check, preview and apply semantics are defined in [CLI reference](reference/cli-reference.md) and [MCP tool reference](reference/mcp-tool-reference.md); this page's `rush format` defaults, engine list and write wording are superseded.
```
  - X1 additions (applied in the X1 task): in `cli-reference.md` append to the sentence above ``` With `--allow-build --allow-slow`, `--verify-preview-id`, repeatable `--verification-test`, `--runtime-path` and `--image-ref` verify a preview in an isolated checkout and report `metadata.preview_verification`; verification never applies the preview. ``` and extend the usage line with `[--verify-preview-id ID --verification-test TEST... --runtime-path PATH --image-ref REF]`; in `mcp-tool-reference.md` append ``` ; `verify_preview_id`, `verification_tests`, `runtime_path`, `image_ref`, `allow_build` and `allow_slow` (isolated preview verification) ```.
  - Foundation row Q03-DOC-receipts refreshes all registered document digests and actual CLI/MCP contracts after this packet's behavior tests pass. This consumes the revised Q01-M1 byte-identical 14-file prerequisite transfer and inventory registrations; it does not recreate those files or claim prior acceptance. Q03 creates no ADR and has no new-doc allowlist. Missing inventory entry fails before writing:
```python
import importlib.util
import json
from pathlib import Path

root = Path.cwd()
spec = importlib.util.spec_from_file_location(
    "sync_docs", root / "scripts/sync_docs.py"
)
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)
report = root / sd.REPORT_PATH
text = report.read_text(encoding="utf-8")
match = sd.BLOCK_RE.search(text)
if match is None:
    raise ValueError("Documentation receipt block is missing")
receipt = json.loads(match.group("payload"))
have = {entry["path"] for entry in receipt["documents"]}
missing = {entry["path"] for entry in sd.build_document_inventory(root)} - have
if missing:
    raise ValueError(
        f"Unregistered Foundation prerequisite or document: {sorted(missing)}"
    )
receipt["contracts"] = sd.collect_runtime_contracts(root)
for entry in receipt["documents"]:
    if entry["path"] != sd.REPORT_PATH:
        entry["sha256"] = sd.document_digest(root / entry["path"])
payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
report.write_text(
    text[: match.start("payload")] + payload + text[match.end("payload") :],
    encoding="utf-8",
)
```
Proposed execution: run this body with `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -` from the implementation checkout, then `python scripts/sync_docs.py --check` through the same uv environment. No extra script artifact is required. Historical document bodies remain unchanged below their leading Current status paragraph; sync_docs.document_digest keeps its established historical-body rules.

Verification requirement: original report Q03-19 at line 5893; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-20: User guide, FAQ, TOOL_CATALOG and compatibility docs carry false format claims

Foundation Q03-DOC-guides owns exact guide/FAQ/compatibility and historical catalog leading paragraph replacements below.

stage A edits, exact:
  - `docs/user-guide/checking-code.md`: replace
```text
# Automatically format all files in place:
uv run rush format .
```
with
```text
# Preview, then apply selected files (needs --allow-artifact-write):
uv run rush format . --mode preview --allow-artifact-write --json
uv run rush format . --mode apply --preview-id <id> --selected-file src/a.py --allow-artifact-write --json
```
and replace ``` Rush coordinates `Ruff format`, `Prettier`, and `Biome` to ensure your entire team shares identical formatting styles. ``` with ``` Rush coordinates `Ruff format` (Python) and `Prettier` (JS/TS/JSON/Markdown/YAML/CSS/HTML) in check mode; a missing engine beside an assessed engine yields partial `metadata.scope` and warn. `metadata.assessed_paths` maps engines to actual consumed absolute logical paths; missing engines have an empty list. ```
  - `docs/user-guide/faq.md`: replace ``` `format` supports a check-only flag and has a non-check path that can invoke formatters; inspect and version-control your work before using any mutating formatter mode. ``` with ``` `format` is check-only by default and writes only through `--mode apply` with a reviewed preview and `--allow-artifact-write`; inspect and version-control your work before applying. ```
  - `docs/reference/compatibility.md`: `` `format` (Prettier, Biome) `` becomes `` `format` (Prettier) ``.
  - `docs/TOOL_CATALOG.md`: add only the leading `Current status:` paragraph from Q03-19. The body (engine list at :23, "in-place writes" at :103) stays, superseded by that paragraph.
  - Refresh receipts with the Q03-19 script.

Verification requirement: original report Q03-20 at line 5943; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-21: Safety/permissions, result-reference, understanding-results, engine docs and CHANGELOG missing (ADR part refuted)

Foundation Q03-DOC-results owns exact permission/result/engine/CHANGELOG replacements below. Q03 creates no ADR.

exact edits (validated by the docs gate):
  - `docs/safety/permissions.md`: `Permit mutating or generating report/baseline artifacts` becomes `Permit mutating or generating report/baseline artifacts, `format --mode preview` artifacts under `.rush/format-previews/`, and `format --mode apply` rewrites of selected, digest-verified files`.
  - `docs/user-guide/understanding-results.md`: `Current `rush error-catalog` CLI has no `--export-docs` option.` becomes the same text followed by ` `rush format --mode preview|apply` is skipped without the grant.`
  - `docs/reference/engine-directory.md`: `JS/TS/JSON/YAML/Markdown and `package.json`; verify project configuration.` becomes `JS/TS/JSON/YAML/Markdown/CSS/HTML and `package.json`; verify project configuration.`
  - `docs/reference/result-reference.md`: insert after the `metadata.scope` paragraph ending `... unions each child's coverage and requested targets.` a new paragraph:
```text
`rush format` check results preserve runtime `metadata.engines`; canonical `metadata.scope` reports actual complete/partial/unavailable/none coverage. `metadata.assessed_paths` is `{engine: [absolute logical consumed paths]}`; skipped/error children have an empty list. Clean partial checks return warn and name unassessed inputs; all missing supported engines are unavailable/engine_unavailable. `mode=preview` returns `metadata.mode`, `preview_id`, `selected_paths` and `records` (`relative_path`, `source_sha256`, `formatted_sha256`); `mode=apply` returns `metadata.mode`, `preview_id`, `changed_paths`, `written` and `partial_write`. Failures carry `metadata.error={code,message}` with message equal to summary and code: `unsupported_operation`, `invalid_argument`, `invalid_preview`, `stale_preview`, `formatter_failed` or `partial_write`; a missing `--allow-artifact-write` grant is `skipped` with `metadata.execution.cause: "permission_denied"`.
```
  X1 adds ``; `verify_preview_id` adds `metadata.preview_verification` (`{preview_id, ast_equal, tests, eligible, status}`, status `eligible`, `rejected`, `inconclusive`, `stale_preview`, `skipped` with reason `isolation_unavailable`, or `dirty_workspace`)`` before ``. Failures carry``.
  - `CHANGELOG.md` (outside the docs gate): under `## [0.3.0]` add above `### Phase 70: ...`:
```text
### Command TDD Q03: `rush format` honest check mode, preview and apply
- **Check-only default enforced:** `check` defaults to `true`; `check=false` / `--no-check` returns `unsupported_operation` without running an engine.
- **Per-engine ledger:** `metadata.assessed_paths` records each Ruff and Prettier child; a clean partial assessment uses routed warn under D5 proposal, never "all formatted"; Prettier receives each selected file once with a single `--check`; unformatted files reported on Prettier 3's stderr are now findings.
- **Preview and apply:** `--mode preview|apply` stores a digest-bound preview under `.rush/format-previews/` and rewrites only selected files whose bytes still match it (file mode preserved), both gated by `--allow-artifact-write`; a failed later write reports `partial_write` with the exact `changed_paths`.
```
  Refresh receipts with the Q03-19 script.

Verification requirement: original report Q03-21 at line 5973; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-22: Expected RED failure reasons undocumented

under plan :4 add:
```text
Expected RED after Foundation shared contracts, before Q03 source, proposed and unexecuted here; no claimed count:
 test_explicit_false_is_error_without_execution (AssertionError 'skipped' == 'error'), test_default_check_is_true_direct
 (assert False is True), test_check_is_read_only_and_partial / test_engine_without_files_is_not_invoked /
 test_both_engines_absent_skipped / test_engine_error_wins_over_other_child / test_warning_retained_beside_skipped /
 test_real_check_assesses_only_selected_files (TypeError unexpected keyword argument 'selected_targets', or missing canonical scope/assessed_paths),
 test_selected_prettier_paths_once / test_prettier_empty_vector_has_no_operand / test_ruff_format_branch_uses_selected_targets
 (TypeError unexpected keyword argument 'selected_targets'), every preview/apply/invalid-argument test
 (TypeError unexpected keyword argument 'mode', or AttributeError/AssertionError for atomic_write_bytes mode).
 Existing regression guards retain their named bodies: test_no_target_is_skipped_no_spawn, test_targets_without_ruff_or_prettier_files_keep_legacy_skip,
 test_ruff_exit_2_malformed_output_and_prettier_exit_2_timeout_are_errors, test_prettier_none_keeps_root_and_caller_operands.
```

Verification requirement: original report Q03-22 at line 6003; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-23: Internal drift: tasks say `b.ts`, bodies use `b.py`

keep the Python-only bodies (`test_apply_rejects_changed_preview`, `test_apply_preview_scope`, a.py + b.py) and add `test_apply_preview_scope_cross_engine`, marked `@pytest.mark.needs_prettier`, exactly as in Q03-12 (a.py + b.ts, preview, apply a.py only, then a stale b.ts). Adjust Task 4 text to say the Python-only tests run everywhere and the cross-engine test needs Prettier on PATH.

Verification requirement: original report Q03-23 at line 6023; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-24: Governance `effect_class` for `tool.format`

Retain existing src/rush/governance/manifest.py entry `tool.format` with `effect_class='idempotent-write'`: preview/apply are explicit artifact-write operations; check stays read-only. No manifest mutation is required. Executable regression: tests/test_phase57_public_operations.py plus check/preview/apply grant and zero-write tests in Q03-12; exact denied state is skipped/executed/not_run/permission_denied.

Verification requirement: original report Q03-24 at line 6031; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-25: Vague warning about Ruff format JSON flags

Ruff format's existing argv includes `--output-format=json` and `--no-cache`. Preserve those flags and the format JSON contract; selected_targets replaces only operands in Q03-04 Part 4, None retains args[2:]. No lint JSON findings decoder is substituted. `test_ruff_format_branch_uses_selected_targets` asserts the exact command, and `test_ruff_exit_2_malformed_output_and_prettier_exit_2_timeout_are_errors` exercises malformed format output/config error.

Verification requirement: original report Q03-25 at line 6039; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-26: Line citations drift at 66c6c79; no current-development baseline

All current source citations refer to Phase70 66c6c799: FormatTool24–151, Prettier49–131, Ruff30–202, runtime1258–1759, gate/runner spans in Q03-STDIO. Audit c78e445 citations remain historical evidence only. Proposed current RED assertions are Q03-22; Claude historical overlay results do not prove current source behavior or plan readiness.

Verification requirement: original report Q03-26 at line 6052; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-27: X1 body passes `str` for a `Path` parameter; mode/verify combination unspecified

in the plan body use `runtime_path=Path(runtime)` (add `from pathlib import Path`), and add to Required behavior:
```text
verify_preview_id is valid only with mode="check"; any other mode => error invalid_argument. A verify call
runs the normal check engines first and attaches metadata.preview_verification to that result, except that an
invalid verify argument returns error/invalid_argument and a missing build/slow grant returns
skipped/permission_denied instead of the check result.
```

Verification requirement: original report Q03-27 at line 6060; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-28: Binding audit file is untracked and absent from the phase-70 worktree

Before implementation, consume revised Q01-M1 exact byte-identical prerequisite transfer for the binding audit/report, template/guide and ten accepted plans. Hash mismatch or missing source/destination fails before any implementation or receipt write. This remediation leaves all protected corpus files unchanged; no automatic commit or alternate-copy artifact is authorized.

Verification requirement: original report Q03-28 at line 6074; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-M1: blocker: `rush format` reports "all formatted" for unformatted TS files with real Prettier 3

add to Deliverables and patch `src/rush/engines/prettier.py` (against Phase70; proposed, unexecuted, together with the selected-targets patch in Q03-04 Part 3; the hunks do not overlap):
```diff
--- a/src/rush/engines/prettier.py
+++ b/src/rush/engines/prettier.py
@@ -22,4 +22,5 @@
 from __future__ import annotations

+import os
 from pathlib import Path

@@ -73,8 +74,16 @@
         # prettier --check writes filenames (one per line) to stdout for files
         # that would be reformatted.
+        # Prettier 3 lists unformatted files on stderr as `[warn] <path>`, relative to
+        # the child's real cwd, and leaves stdout empty; older versions list on stdout.
+        anchor = os.path.realpath(cwd if cwd is not None else Path.cwd())
         would_reformat = [
             ln.strip()
             for ln in proc.stdout.splitlines()
             if ln.strip() and not ln.startswith("[warn]")
+        ] or [
+            os.path.normpath(os.path.join(anchor, ln[len("[warn] ") :].strip()))
+            for ln in proc.stderr.splitlines()
+            if ln.startswith("[warn] ")
+            and not ln.startswith("[warn] Code style issues")
         ]

@@ -111,4 +120,7 @@
             status: ToolStatus = "error"
             summary = f"prettier error (exit {exit_code})"
+        elif exit_code == 1 and not findings:
+            status = "error"
+            summary = "prettier: nonzero exit without readable findings"
         elif findings:
             status = "warn"
```
New `tests/test_prettier_honest.py` (proposed, unexecuted; real Prettier case is marker-selected, never live-skipped):
```python
"""Prettier 3 reports unformatted files on stderr; an unlisted exit 1 is never clean."""

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from rush.engines import prettier as prettier_module
from rush.engines.prettier import PrettierEngine
from rush.tools import common


def _run(monkeypatch, tmp_path, returncode, stdout="", stderr=""):
    monkeypatch.setattr(prettier_module, "resolve_binary", lambda _b: "prettier-bin")
    monkeypatch.setattr(
        prettier_module,
        "run_subprocess",
        lambda argv, **kw: CompletedProcess(argv, returncode, stdout, stderr),
    )
    monkeypatch.setattr(common, "engine_on_path", lambda _b: True)
    return common.run_engine(
        PrettierEngine(), tmp_path, [], cwd=tmp_path, tool_name="format"
    )


def test_prettier3_stderr_warn_lines_are_findings(monkeypatch, tmp_path):
    stderr = "[warn] sub/b.ts\n[warn] Code style issues found in the above file. Run Prettier with --write to fix.\n"
    result = _run(monkeypatch, tmp_path, 1, stderr=stderr)
    assert result["status"] == "warn"
    assert [f["path"] for f in result["findings"]] == [
        str(tmp_path.resolve() / "sub" / "b.ts")
    ]


def test_prettier_nonzero_without_any_listing_is_error(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 1)
    assert result["status"] == "error"


def test_prettier_stdout_listing_still_wins(monkeypatch, tmp_path):
    result = _run(
        monkeypatch, tmp_path, 1, stdout="main.ts\n", stderr="[warn] other.ts\n"
    )
    assert [f["path"] for f in result["findings"]] == ["main.ts"]


@pytest.mark.needs_prettier
def test_real_prettier_unformatted_file_is_a_finding_even_via_symlinked_cwd(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "b.ts").write_text("const  y=2\n")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    raw = PrettierEngine().run(real, [], cwd=link)
    assert raw["exit_code"] == 1
    assert [Path(f["path"]) for f in raw["findings"]] == [real.resolve() / "b.ts"]
```

Verification requirement: original report Q03-M1 at line 6086; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-M2: major: Ruff's `format` branch ignores `path` and `selected_targets`, so an operandless `ruff format --check` assesses the process cwd

Consume Q03-04 Part 4 from the corrected Q02 owner; Q03 never applies that `ruff.py` diff (the format branch consumes `selected_targets`; `None` keeps the legacy `args[2:]`). Exact None/vector behavior is preserved; tests: `test_ruff_format_branch_uses_selected_targets` and `test_real_check_assesses_only_selected_files` (Q03-12). Revised Q02 already defines that prerequisite. No second plan edit.

Verification requirement: original report Q03-M2 at line 6195; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q03-M3: major: the CI docs gate (`scripts/sync_docs.py --check`) is not part of the plan

covered by Q03-16 (check command), Q03-17 (Completion paths) and Q03-19 (edits and refresh script).

### Q03-M4: major: the plan's code blocks are not lint- and format-clean

Changed Python fences are frozen and AST/lint/format checked separately during this Markdown remediation. These static checks prove snippet syntax/style only. Proposed production behavior and named tests remain unexecuted; final handoff records exact fence outcomes.

### Q03-M5: F5 selected pytest argv and factual count producer

Q03-04 invokes the revised Foundation F5 function with nodes=[node],
python_entrypoint="/usr/local/bin/python", timeout_s=300. Its exact argv is
["-m","pytest","-q","--tb=line",node]; no rush.__main__, --test-path,
--test-environment or --allow-build is passed inside the container. Caller
build/slow grants are checked before ordinary work. Typed SelectedTestRun
outcome/counts come from actual pytest summary parsing; missing summary is error.
Q03-12's controlled provider runs real pytest and invokes real F5 parsing;
test_format_real_oci_source_bound_verification_and_cleanup separately proves
actual isolated invocation, source/test digests and cleanup. Empty selected
test lists are invalid_argument; selected nodes collecting zero tests yield
inconclusive, never eligible. This is the stated audit-argv deviation, not an
additional approval gate.

### Q03-M6: Preserve legacy fixtures, staging tuple and unsupported-only skip

Existing fake children may omit engine/summary; batch identity provides the
name, while a missing factual runtime consumption ledger cannot prove complete
scope. Q03-12 controlled children explicitly record their selected-vector
ledger; real adapter tests independently verify those operands. Foundation
_staged_invocation still returns its original four-tuple; selected_targets is
mapped separately through active staging. test_staged_scan_maps_selected_targets
asserts staged physical argv, and test_preview_staged_bytes_and_apply_live_drift
asserts snapshot preview versus live apply invalidation. Unsupported-only
inventory remains skipped/none/no_supported_targets with no formatter spawn,
covered by test_targets_without_ruff_or_prettier_files_keep_legacy_skip. No
new enum, tuple field, legacy-engine assumption or unrelated test deletion.

## Checks to run before reporting

These are **proposed implementation acceptance commands**, not commands executed
during this Markdown remediation. Run from the accepted Phase70 implementation
checkout after the corresponding source/test files and shared rows exist.
Clear inherited `PYTHONPATH`; Python version must report 3.12. New Q03 modules
are created by these packets, not present at the frozen source revision.

R/E requires accepted F1/F2/F3/F6, revised Q02 selected-target/staging/Ruff-format
packets, Q03-STDIO/Q03-SCOPE and same-packet F8 documentation registration. F4/F5 and live
OCI are X1 prerequisites, not R/E requirements. Run the exact X13+C20 union
below; additional modules cover affected adapter, ownership, staging,
filesystem, catalog and Phase60 boundaries.

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_format.py tests/test_format_parity.py tests/test_prettier_honest.py tests/test_engines.py tests/test_tools.py tests/test_subprocess_contract.py tests/test_phase70_t16.py tests/test_phase70_result_trust.py tests/test_transport_parity.py tests/test_cli_registry.py tests/test_mcp.py tests/test_prettier_reference.py tests/test_ruff_reference.py tests/test_tool_common.py tests/test_workflows.py tests/test_phase57_public_operations.py tests/test_phase70_t9.py tests/test_phase70_t17.py tests/test_sync_docs.py tests/test_language_routing.py tests/test_dashboard_map.py tests/test_full_project_scan.py tests/test_project_run_lifecycle.py tests/test_phase60_characterization.py tests/test_phase60_refactor.py tests/test_phase60_complexity_thresholds.py tests/test_catalog.py -k 'not (test_preview_ast_and_test_gate or test_verification_rejects_failed_selected_test or test_verification_with_skipped_or_empty_tests_is_inconclusive or test_verification_rejects_changed_ast or test_verification_isolation_unavailable_and_dirty_workspace or test_verification_requires_build_and_slow_grants_and_selected_tests or test_verification_denial_precedes_ordinary_effects)' -m 'not oci_isolation' -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy git diff --check
```

Stage A deselects exactly these seven X1 controller cases because F4/F5 do not
exist yet. Their lazy imports preserve collection of every R/E case. This is
prerequisite sequencing, not acceptance removal. Stage A also deselects all
`oci_isolation`-marked cases even if a runtime environment variable is set;
the new relative-runtime stdio regression needs accepted F4/F5. All seven run in the complete
`tests/test_format.py` module after F4/F5 integration below.

After F4/F5 and Q03 X1 source/tests are created and accepted, add:

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_isolated_process.py tests/test_isolated_tests.py tests/test_format_oci.py tests/test_format.py tests/test_format_parity.py tests/test_mcp.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests -m oci_isolation -q
```

The `oci-isolation` CI job supplies verified runtime and digest-pinned Python,
Rush and compiler images and passes the marked suite. Runtime unset means
deselection, never a live skip. Runtime present with absent/unpinned image means
failure. Controlled F5/runner fixtures prove their exercised branches only;
they cannot close X1 isolation or captured/executed-byte acceptance.

Run full suite after accepted prerequisites and same-packet integration:

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/ -q
```

C19 pass criterion: zero new failures and zero SKIPPED. Only these five
historical 66c6c79 node failures may be recorded as identical before/after
failures, with the same assertion/error evidence; keep their modules collected.
A historical list is not current baseline acceptance or permission to ignore
any additional failure:

```text
tests/test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[core]
tests/test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[full]
tests/test_no_skips.py::test_no_collected_test_carries_a_live_skip_marker
tests/test_phase70_t12.py::test_t12_pyrefly_argv_no_directory_arg_when_explicit_files
tests/test_phase70_t12.py::test_t12_typecheck_config_routes_python_family
```

Each packet's exact named checks also remains required. Source/test interface
absence is classified separately from behavioral RED. Existing regressions
already satisfied by Phase70 retain their exact acceptance; do not count them
as newly implemented fixes.

## Failure and recovery

Invalid schema, artifact identity, containment, stale destination, formatter
identity or misplaced arguments rejects the operation before its first unsafe
effect. Verify grant refusal is whole-call per C11 and occurs before ordinary
formatting, sandbox/test/provider calls or source/artifact writes. Runtime/image
absence retains its explicit operation block and never falls back to host tests.

Preview consumes captured source/config bytes, including staged snapshots where
applicable; apply checks actual live destination bytes before its first write.
Owned formatter stdin/stdout remains private; runner diagnostics remain bounded
and redacted. Timeout, cancellation, launch/nonzero failure and uncertain cleanup
discard partial preview output and report factual terminal evidence. Never
manufacture successful subprocess counts, pytest counts or isolation receipts.

Apply preflights every selected record before writes. Each replacement is atomic,
preserves mode and reports actual written paths/hashes. A later I/O error reports
partial writes without claiming rollback. Clean only invocation-owned scratch.
Drift invalidates prior preview/verification evidence. Historical documentation
bodies stay unchanged; F8 refreshes current text, leading status paragraphs and
contract/coverage receipts in the same implementation packet.

## Completion

Implementation completes only when every R repair, E preview/apply extension
and X verification acceptance is independently satisfied; current source/API
and requirement ledger agree; exact direct/CLI/initialized-stdio outcomes agree;
relevant real engine/subprocess/OCI behavior gates pass; and documentation
registration/checks pass. R PASS does not close E or X acceptance.

Q03 command-owner writes are limited to these literal paths:

```text
src/rush/tools/format.py
src/rush/engines/prettier.py
src/rush/runtime/filesystem.py
tests/test_format.py
tests/test_format_parity.py
tests/test_prettier_honest.py
tests/test_format_oci.py
```

Shared changes remain explicit Foundation-owned rows in this plan:
Q03-R1-CLI, Q03-E1-CLI, Q03-X1-CLI for `src/rush/cli.py::format`;
Q03-MCP-containment for `src/rush/mcp_support/tool_registry.py`;
Q03-STDIO/Q03-SCOPE for `src/rush/runtime/subprocesses.py` and the existing
`tests/test_subprocess_contract.py` regressions; F1/F2/F6/F10/F11 rows for
strict schemas, routing, transport helper and discovery; and literal Q03-DOC
rows in Q03-19–21 for the exact documentation/contract inventory.
Foundation owner alone applies shared files. Q02 owner applies Ruff format
selection after Q02 R1; Q03 never writes `src/rush/engines/ruff.py`.
A cross-plan link cannot replace concrete packet content or prerequisite acceptance.

Current authorization is **only Markdown remediation of this Plan03 file**.
No production/test/config/shared-doc changes, implementation, other-plan edits,
commit, push or release is authorized. Development readiness and implementation
acceptance remain separate claims.

## Handoff

Return this one corrected plan with frozen whole-file SHA256, semantic review
verdict, source/binding identities, coverage, exact static checks and their limits,
preservation evidence and precise external decision/evidence blockers.
Future behavioral commands remain proposed and unexecuted during this task.
Stop for James's review; another plan needs explicit authorization.

## Remediation acceptance ledger

Every applicable finding is reconciled below. The proposed bodies and tests in
the named packet carry the concrete correction; this ledger does not substitute
for them. Report final C clauses override conflicting earlier snippets.
Repair, E extension, X proposal and shared user-requested baseline remain distinct.
Current source establishes behavior; it does not authorize removing required scope.

| Finding | Category | Binding requirement | Grounded evidence | Corrected packet | Concrete check and expected state | Disposition/evidence limit |
| --- | --- | --- | --- | --- | --- | --- |
| Q03-01 | repair/regression | Handwritten cli.py::format owns paired check/mode/preview/apply/X1 options; StageA beforeX1. | Phase70 cli.py::format and MCP wrapper; revised00 F1/F6 and final C14. | ### Q03-01; surgical source/test/doc specification. | test_format_cli_mcp_explicit_false_parity; test_default_check_is_true_direct | Proposed correction/regression; future behavior unexecuted. |
| Q03-02 | repair/regression | routing.aggregate_status only; D5 default ok+skipped warn; no tool-local skipped override; preserve child evidence. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-02; surgical source/test/doc specification. | test_check_is_read_only_and_partial; test_both_engines_absent_skipped; test_warning_retained_beside_skipped | Proposed correction/regression; future behavior unexecuted. |
| Q03-03 | repair/regression | atomic_write_bytes optional explicit mode preserves applied file permissions; common re-export avoids cycle; other callers unchanged. | Phase70 runtime/filesystem.py:49–78; tools/common.py re-export. | ### Q03-03; surgical source/test/doc specification. | test_apply_preserves_file_mode; test_atomic_write_bytes_mode_default_unchanged_and_mode_applied | Proposed correction/regression; future behavior unexecuted. |
| Q03-04 | repair/regression | Complete proposed format/Prettier/atomic/CLI/runtime interfaces/helpers; audit fields retained; no undefined bodies. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-04; surgical source/test/doc specification. | Q03-12 complete test module; preview/apply and verification fixtures | Proposed correction/regression; future behavior unexecuted. |
| Q03-05 | repair/regression | F4 owns W18 provider; absent live; exact prerequisite interface/entry/exit gates; no extraPlan45. | Revised00 F3/F4/F5; SelectedTestRun.isolated; Phase70 runner ownership/cancellation. | ### Q03-05; surgical source/test/doc specification. | Foundation F4 provider/cleanup and Q03 live OCI tests after prerequisites | Proposed correction/regression; future behavior unexecuted. |
| Q03-06 | repair/regression | F2 canonical child/aggregate scopes separate from nested runtime engine scope; actual consumed evidence and assessed paths. Staged argv must reconcile with logical selection before complete coverage can be claimed. | Phase70 _identity:1410–1415, _argv_targets:1418–1429, _entry_scope:1449–1487 compare file identities; original and staged inodes differ. | Q03-06/07 and the Foundation runtime row; surgical source/test/doc specification. | test_actual_consumption_and_engine_error_scope; test_staged_scan_maps_selected_targets; exact complete selection and truthful missing/engine_error cases. | Proposed correction/regression; future behavior unexecuted. |
| Q03-07 | repair/regression | Q02 runtime selected vector staging/ownership/cwd/config; _staged_invocation fourtuple unchanged; Prettier explicitvector. | Revised02 selected/staging/Ruff format packets; Phase70 runtime staging four-tuple. | ### Q03-07; surgical source/test/doc specification. | test_staged_scan_maps_selected_targets; test_selected_prettier_paths_once; test_ruff_format_branch_uses_selected_targets | Proposed correction/regression; future behavior unexecuted. |
| Q03-08 | E1 preview/apply extension | Canonical .rush/format-previews/{64hex}.json identity/source/output/path/config/version binding; invalid vs stale. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-08; surgical source/test/doc specification. | test_tampered_or_missing_preview_is_invalid_and_writes_nothing; test_forged_formatted_digest_is_invalid_preview | Proposed correction/regression; future behavior unexecuted. |
| Q03-09 | repair/regression | F3 artifact-write refusal canonical execution permissions, error carrier metadata.error; no bare reason. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-09; surgical source/test/doc specification. | test_preview_requires_grant_and_writes_nothing; test_apply_without_grant_is_skipped_and_writes_nothing | Proposed correction/regression; future behavior unexecuted. |
| Q03-10 | E1 preview/apply extension | Audit preview/apply fields preserved and declared deviations nonemptyselection; engine/partialwrite receipts. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-10; surgical source/test/doc specification. | test_apply_preview_scope; test_apply_partial_io_failure_receipt | Proposed correction/regression; future behavior unexecuted. |
| Q03-11 | X1 verification proposal | Verification declared schema deviation; isolated snapshot/scratch, AST check, F5 realselected tests; dirtytree/cleanup specified. | Revised00 F3/F4/F5; SelectedTestRun.isolated; Phase70 runner ownership/cancellation. | ### Q03-11; surgical source/test/doc specification. | test_preview_ast_and_test_gate; test_verification_rejects_failed_selected_test; test_verification_with_skipped_or_empty_tests_is_inconclusive | Proposed correction/regression; future behavior unexecuted. |
| Q03-12 | repair/regression | Complete tests/imports/helpers every named scenario concrete fixture expected branch; preserve prior bodies. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-12; surgical source/test/doc specification. | Every concrete body in Q03-12; exact current-callable versus future-interface classification Q03-22 | Proposed correction/regression; future behavior unexecuted. |
| Q03-13 | X1 verification proposal | F5 selectedtest helper exclusively; no -m rush/TestTool unsupported forwarding; exact entrypoint argv/timeouts. | Revised00 F3/F4/F5; SelectedTestRun.isolated; Phase70 runner ownership/cancellation. | ### Q03-13; surgical source/test/doc specification. | test_preview_ast_and_test_gate; F5 tests/test_isolated_tests.py | Proposed correction/regression; future behavior unexecuted. |
| Q03-14 | repair/regression | F6 sole CLI/initializedstdio helper realerrlog; CLIerror2valid; assert stdout before decode. | Phase70 cli.py::format and MCP wrapper; revised00 F1/F6 and final C14. | ### Q03-14; surgical source/test/doc specification. | test_format_cli_mcp_explicit_false_parity; test_format_cli_mcp_default_is_check_only_parity; tests/test_transport_parity.py | Proposed correction/regression; future behavior unexecuted. |
| Q03-15 | repair/regression | selected_files contained before artifact read/write; runtime absolute input unchanged no anchoring. | Phase70 cli.py::format and MCP wrapper; revised00 F1/F6 and final C14. | ### Q03-15; surgical source/test/doc specification. | test_format_mcp_selected_file_escape_rejected; F1 strict model cases | Proposed correction/regression; future behavior unexecuted. |
| Q03-16 | repair/regression | Union X13+C20 exactmodules; newvsabsent and OCIphase gating; mypy src/rush/docs/diff. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-16; surgical source/test/doc specification. | Literal stage-A/X1 command union below; mypy, docs, full-suite and diff gates | Proposed correction/regression; future behavior unexecuted. |
| Q03-17 | repair/regression | Localtemplate order Deliverables beforeConstraints; literalCompletion/Handoff; decisions separate no Status. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-17; surgical source/test/doc specification. | Feature/Required behavior/Deliverables/Constraints/Checks/Completion/Handoff; literal owned paths below | Proposed correction/regression; future behavior unexecuted. |
| Q03-18 | R/E/X public-route examples | Exact CLI/API names and worked before/after outputs match adapters/metadata D2. | Phase70 cli.py::format and MCP wrapper; revised00 F1/F6 and final C14. | ### Q03-18; surgical source/test/doc specification. | Worked CLI/MCP examples Q03-18; real transport cases | Proposed correction/regression; future behavior unexecuted. |
| Q03-19 | repair/regression | Exact F8 rows refs currentvsimmutable leadingstatus; receipt+runtimecontractsync samepacket. | Phase70 sync_docs.py BLOCK_RE/document inventory/contracts; revised01 receipt route; C22/C23. | ### Q03-19; surgical source/test/doc specification. | tests/test_sync_docs.py plus scripts/sync_docs.py --check after same-packet registration | Proposed correction/regression; future behavior unexecuted. |
| Q03-20 | repair/regression | Correct checkingcode/FAQ/compatibility/currentengine docs, historicalcatalog/ENGINESleadingonly. | Phase70 sync_docs.py BLOCK_RE/document inventory/contracts; revised01 receipt route; C22/C23. | ### Q03-20; surgical source/test/doc specification. | Literal historical/current doc replacements and Q03-19 receipt regeneration | Proposed correction/regression; future behavior unexecuted. |
| Q03-21 | repair/regression | F8 permissions/results/understanding/engine extensions/CHANGELOG exact; no Q03ADR. | Phase70 sync_docs.py BLOCK_RE/document inventory/contracts; revised01 receipt route; C22/C23. | ### Q03-21; surgical source/test/doc specification. | Exact F8 permission/result/engine/CHANGELOG rows; no Q03 ADR or historical-body rewrite | Proposed correction/regression; future behavior unexecuted. |
| Q03-22 | repair/regression | RED reason table matches final exact tests; classify currentbehavior/interfaces/regressions. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-22; surgical source/test/doc specification. | Per-test failure classification Q03-22; interface TypeError not behavioral proof | Proposed correction/regression; future behavior unexecuted. |
| Q03-23 | repair/regression | RetainPython fixtures plus separate realPrettier crossengine preview case, needs_prettier deselect. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-23; surgical source/test/doc specification. | test_apply_preview_scope; test_apply_preview_scope_cross_engine with real Prettier | Proposed correction/regression; future behavior unexecuted. |
| Q03-24 | repair/regression | Governance tool.format idempotent-write already correct; preserve declaration. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-24; surgical source/test/doc specification. | tests/test_phase57_public_operations.py; retain tool.format idempotent-write | Proposed correction/regression; future behavior unexecuted. |
| Q03-25 | repair/regression | VerifiedRuffformat flags no lintJSON assumption; Q02owner. | Revised02 selected/staging/Ruff format packets; Phase70 runtime staging four-tuple. | ### Q03-25; surgical source/test/doc specification. | test_ruff_format_branch_uses_selected_targets; test_real_check_assesses_only_selected_files | Proposed correction/regression; future behavior unexecuted. |
| Q03-26 | repair/regression | LivePhase70HEAD/source locator claims corrections distinguished auditc78e445. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-26; surgical source/test/doc specification. | Phase70 source/contract/design-brief identities and prerequisite gate | Proposed correction/regression; future behavior unexecuted. |
| Q03-27 | R/E/X input-contract repair | mode=check only verify; runtime Path adaptation; rejected irrelevantargs concrete. | Revised00 F3/F4/F5; SelectedTestRun.isolated; Phase70 runner ownership/cancellation. | ### Q03-27; surgical source/test/doc specification. | test_misplaced_verification_arguments_error; test_verification_requires_build_and_slow_grants_and_selected_tests | Proposed correction/regression; future behavior unexecuted. |
| Q03-28 | repair/regression | Binding untracked audit/plans transfer exacthash; revised01 full14file registration gate. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-28; surgical source/test/doc specification. | Q01-M1 exact 14-file transfer/registration gate; audit/report SHA256 listed here | Proposed correction/regression; future behavior unexecuted. |
| Q03-M1 | repair/regression | Prettier3 stderrfilenamefinding=>warn; exit1 NO usable stdout/stderr filenames=>error per reportM1; rc>=2 error; preserveactualpaths. | Phase70 PrettierEngine:31–131; Claude report6086–6101 and M1 patch. | ### Q03-M1; surgical source/test/doc specification. | test_prettier3_stderr_warn_lines_are_findings; test_prettier_nonzero_without_any_listing_is_error; real Prettier case | Proposed correction/regression; future behavior unexecuted. |
| Q03-M2 | repair/regression | Q02owns Ruff formatselectedtargets afterR1; Q03consumes no Ruffwrite. | Revised02 selected/staging/Ruff format packets; Phase70 runtime staging four-tuple. | ### Q03-M2; surgical source/test/doc specification. | test_ruff_format_branch_uses_selected_targets; test_real_check_assesses_only_selected_files; Q02 prerequisite | Proposed correction/regression; future behavior unexecuted. |
| Q03-M3 | repair/regression | Docs CI syncgate required samepacket; untrackedplans missingreceipts understood. | Phase70 sync_docs.py BLOCK_RE/document inventory/contracts; revised01 receipt route; C22/C23. | ### Q03-M3; surgical source/test/doc specification. | tests/test_sync_docs.py and literal docs gate after transfer/registration | Proposed correction/regression; future behavior unexecuted. |
| Q03-M4 | repair/regression | Embedded changedsource syntax/lint/format verified only affected snippets; no behaviorclaim. | Phase70 FormatTool:24–151; corresponding Claude Q03 finding and final overrides. | ### Q03-M4; surgical source/test/doc specification. | Changed/unchecked source-fragment AST/Ruff checks; future whole-tree lint/format | Proposed correction/regression; future behavior unexecuted. |
| Q03-M5 | repair/regression | F5 supersedes invalid auditincontainer -m rush/missingallow-build route. | Revised00 F3/F4/F5; SelectedTestRun.isolated; Phase70 runner ownership/cancellation. | ### Q03-M5; surgical source/test/doc specification. | F5 selected pytest argv/counts and test_preview_ast_and_test_gate | Proposed correction/regression; future behavior unexecuted. |
| Q03-M6 | repair/regression | Legacyfakechild .get loopenginename; staged4tuple; unsupportedenginefilelegacy skip. | Revised02 selected/staging/Ruff format packets; Phase70 runtime staging four-tuple. | ### Q03-M6; surgical source/test/doc specification. | test_targets_without_ruff_or_prettier_files_keep_legacy_skip; tests/test_tools.py; staged four-tuple regressions | Proposed correction/regression; future behavior unexecuted. |
| X-01 | shared contract | Phase70 66c6c799 baseline + T9/T16/T17 reconciliation; audit c78e445 historical | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-02/26 | Current source/briefs + current RED/regression routes | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-02 | shared contract | engines/scope/assessed_paths canonical; status shared only; no aggregation/partialnew | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-02/06 | F2 child actual counts + aggregate actualcoverage | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-03 | shared contract | F4 owns isolation provider, Q18 F7 reference-only | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-05/11 | Complete accepted Foundation API/prerequisiteorderedroute | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-04 | shared contract | Single F4 API, D2 names, Q03 D4timeout300, pythonentrypoint exact | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-11/13 | SelectedTestRun.isolated/receipts and processlaunchactual | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-05 | shared contract | Foundation serialized shared writer; Q03 filesystem/format/Prettier owner; Q02Ruffowner | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Deliverables/Ordered tasks | Literal maps/Completion route no overlappingownership | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-06 | shared contract | HandwrittenCLI formatoptionforwarding + grantsingledecorator existingconfig/result flags | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-01/15 | RealClicktypedforwarding + help eachonce | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-07 | shared contract | publicallowStrictBool buildsExecutionPermissionsonce; run permissions | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-04/09 | public/direct parity + no nonexistentinstanceAPI | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-08 | shared contract | Grantrefusal/skipped/denied/errorcarrier/emptyscope canonical | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-09/11 | Exact missingflagsummary executionrequested/granted effectcountzero | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-09 | shared contract | F5 solely owns selectedisolatedtest execution; counts/outcome exact | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-13/M5 | Complete nodesvalidate containedunique realpytestresult | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-10 | shared contract | Defined Foundation/W18/R/E/X/D abbreviations literal ownership | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Shared contracts | No undefined shorthand/API | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-11 | shared contract | Template exactsectionorder/noStatus/decisionsection/literalCompletion | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-17 | Requiredbehavior/Deliverables/Constraints/Checks/Completion/Handoff | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-12 | shared contract | New testmodules absentPhase70; pytest core notdevclaim | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-12/16 | Every new modulebody/helper/fixture andorderedcreation | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-13 | shared contract | Exactunionregressions plusmypy/docs/diff/fullsuite | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-16 | Future commands Python3.12 PYTHONPATHcleared | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-14 | shared contract | F6transport_parity solehelper initializedstdio errlog trueexitmapping | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-14 | CLIJSONparsedonlyafterstdout; MCP ToolResult envelope | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-15 | shared contract | FoundationF8 single shared docs owner exactpatchrows samepacket | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-19/20/21 | CLI/MCP/current/historicaldocs contractreceipt consistent | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-16 | shared contract | F9config/F10discovery/F11forwarding integration preserved | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-01/15/19 | TOOL_SPECS.discovery single, description20–199, schemaflat | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-17 | shared contract | Untracked bindinginputs exacthashtransfer+registration; Phase70acceptancenotGit | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Q03-28 | Revised01 14prerequisitefiles/docsreceipt gate | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| X-18 | shared contract | No irrelevant copied Q01/Q02/nextbatchscope; preserve requestedsharedbaseline | Binding X clause plus applicable final C; revised00–02 and current Phase70. | Scope/Decisions | Baseline scanner/localmodels/voice/3D notinnovation | Q03 consumer reconciliation; Q18-only portion of X03 remains reference-only. |
| C-01 | binding override | F2 engines/scope/assessed_paths, preserveactualnestedruntimeledger; no toolaggregation/partial | Final report C-01 overrides superseded earlier proposals. | Q03-02/06 | Fakebarechild +actualenginepartial/allmissing/unsupported | Applied to Q03 packet; conditional proposals not approvals. |
| C-02 | binding override | D5 route status no localoverride; defaultmixedwarn CLI1 | Final report C-02 overrides superseded earlier proposals. | Q03-02 | Cleanpartial summaries listmissingengine | Applied to Q03 packet; conditional proposals not approvals. |
| C-03 | binding override | F4 IsolatedRun/LaunchBudgetExhausted factuallaunches/receipt | Final report C-03 overrides superseded earlier proposals. | Q03-05/11 | Providerresult/exceptioncleanup no inventedPASS | Applied to Q03 packet; conditional proposals not approvals. |
| C-04 | excluded command clause | excluded: Q10-only timeout30; Q03 D4 timeout300 conditional | Final report C-04 overrides superseded earlier proposals. | Exclusion reconciliation | No Q03 change authorized by this command-specific clause. | excluded: Q10-only timeout30; Q03 D4 timeout300 conditional |
| C-05 | binding override | F5 pytestselectedtests replacesaudit -m rush with unsupported --test-path | Final report C-05 overrides superseded earlier proposals. | Q03-13/M5 | run_selected_tests_isolated exactnodes/counts/.isolated | Applied to Q03 packet; conditional proposals not approvals. |
| C-06 | binding override | D2 runtime_path/image_ref uniformoptionnames proposal | Final report C-06 overrides superseded earlier proposals. | Q03-01/15/18 | CLI/help/MCP/directsamefields | Applied to Q03 packet; conditional proposals not approvals. |
| C-07 | binding override | Runtimeabsoluteonly noMCP_CWD_RELATIVE_ARGS orCLIabspath | Final report C-07 overrides superseded earlier proposals. | Q03-15 | Relative runtime remainsunavailable unchanged | Applied to Q03 packet; conditional proposals not approvals. |
| C-08 | binding override | F4no-launchpreflight runtimeallowlist/pathpermissions thenimagegrammar; no extrahelperAPI | Final report C-08 overrides superseded earlier proposals. | Q03-05/11 | Relative/untrusted unavailable; image malformedinvalidargument | Applied to Q03 packet; conditional proposals not approvals. |
| C-09 | binding override | IsolationUnavailable skippedisolation_unavailable; ValueError error invalid_argument | Final report C-09 overrides superseded earlier proposals. | Q03-11/27 | Exact dualfixture +zero targeteffects | Applied to Q03 packet; conditional proposals not approvals. |
| C-10 | binding override | __call__StrictBool buildExecutionPermissionsonce; run andverify permissions | Final report C-10 overrides superseded earlier proposals. | Q03-04/09/11 | Directtestspermissions noallow_* runkwargs | Applied to Q03 packet; conditional proposals not approvals. |
| C-11 | binding override | Q03verify whole-callgrantdenial beforeordinarycheck/providers; optionalpolicies don'tcopyQ02 | Final report C-11 overrides superseded earlier proposals. | Q03-09/11 | skipped denied build_or_slow_denied executioncausepermission_denied zeroeffects | Applied to Q03 packet; conditional proposals not approvals. |
| C-12 | binding override | MissingOCIoperation blockstatusskipped/reasonisolation_unavailable preservebase | Final report C-12 overrides superseded earlier proposals. | Q03-11 | Noisolation_unavailableasstatus orhostfallback | Applied to Q03 packet; conditional proposals not approvals. |
| C-13 | binding override | metadata.error.code/message=summary, notbaremetadata.reason | Final report C-13 overrides superseded earlier proposals. | Q03-04/09/27 | Invalidpublicinput exactcarrier allbranches | Applied to Q03 packet; conditional proposals not approvals. |
| C-14 | binding override | F1public_sig strictflatmodels preservetransportoptions; MCPnonmemory INVALID_REQUEST isErrorFalse | Final report C-14 overrides superseded earlier proposals. | Q03-01/15 | Unknowns/nonBool grants rejectedpredispatch; typedoptionsaccepted | Applied to Q03 packet; conditional proposals not approvals. |
| C-15 | binding override | ToolSpec.discovery sharedsingle source path.description CLIhelp, shortmcp_descriptionPhase70phrases | Final report C-15 overrides superseded earlier proposals. | Q03-01/19 | tools/list pathdiscovery/help boundeddescription | Applied to Q03 packet; conditional proposals not approvals. |
| C-16 | binding override | Q03format/Prettier/filesystem +newformatmodules; RuffQ02 sharedsubprocessFoundation | Final report C-16 overrides superseded earlier proposals. | Deliverables/Completion | Exactliteralownership/orderedintegration | Applied to Q03 packet; conditional proposals not approvals. |
| C-17 | binding override | oci_isolation deselectedwhenruntimeunset; configuredimageunavailable/unpinnedfails; liveCIallimages | Final report C-17 overrides superseded earlier proposals. | Q03-11/16 | RealOCIonly afterF4/F5installed; noBLOCKED fakePASS | Applied to Q03 packet; conditional proposals not approvals. |
| C-18 | binding override | mypy src/rush D8 currentCI | Final report C-18 overrides superseded earlier proposals. | Q03-16 | Futureexactmypycommand | Applied to Q03 packet; conditional proposals not approvals. |
| C-19 | binding override | Only exactfiveknownnodefailuresidenticalbeforeafter; zeroSKIPPED; no expandedwaiver | Final report C-19 overrides superseded earlier proposals. | Checks | Keep fullmodules; failureidentities recorded | Applied to Q03 packet; conditional proposals not approvals. |
| C-20 | binding override | Checks union X13 +C20+perpacketmodules; conditionalprovider/liveOCI modules | Final report C-20 overrides superseded earlier proposals. | Q03-16 | LiteralR/Echecklist +X1+fullsuite | Applied to Q03 packet; conditional proposals not approvals. |
| C-21 | excluded command clause | excluded: Q08-only historical CI citation | Final report C-21 overrides superseded earlier proposals. | Exclusion reconciliation | No Q03 change authorized by this command-specific clause. | excluded: Q08-only historical CI citation |
| C-22 | binding override | Q03noADR; Foundation0050; revised01/02 0051/52; immutableADRindexleadingCurrentstatusonly | Final report C-22 overrides superseded earlier proposals. | Q03-19/21 | No newQ03ADR orhistoricalbodychanges | Applied to Q03 packet; conditional proposals not approvals. |
| C-23 | binding override | All shareddocupdatesF8exactrows/samepacket; immutableADR0007leadingstatusonly | Final report C-23 overrides superseded earlier proposals. | Q03-19/21 | Actualsync_docs.BLOCK_RE/documentinventory/contractsreceipt regeneration | Applied to Q03 packet; conditional proposals not approvals. |
| C-24 | binding override | NoStatus; decisions Jamessection; no approvalforcedderivedclaim | Final report C-24 overrides superseded earlier proposals. | Q03-17 | Externalchoiceslistedwithaffectedpackets | Applied to Q03 packet; conditional proposals not approvals. |
| C-25 | excluded command clause | excluded: Q07-only boilerplate deletion | Final report C-25 overrides superseded earlier proposals. | Exclusion reconciliation | No Q03 change authorized by this command-specific clause. | excluded: Q07-only boilerplate deletion |
| C-26 | excluded command clause | excluded: Q08-only ownership correction | Final report C-26 overrides superseded earlier proposals. | Exclusion reconciliation | No Q03 change authorized by this command-specific clause. | excluded: Q08-only ownership correction |
| C-27 | binding override | F2eachactualchildscope/aggregate complete/unavailable/none; runtimeengine.scopelegacystays | Final report C-27 overrides superseded earlier proposals. | Q03-06 | Actualconsumption/assessedpaths counts +engine_error reason | Applied to Q03 packet; conditional proposals not approvals. |
| C-28 | excluded command clause | excluded: Q06-only isolation decision | Final report C-28 overrides superseded earlier proposals. | Exclusion reconciliation | No Q03 change authorized by this command-specific clause. | excluded: Q06-only isolation decision |
| C-29 | binding override | F1tencommandunknownrejection includesformat, remainingtools globaldecision referenceonly | Final report C-29 overrides superseded earlier proposals. | Q03-15 | test_command_tools_reject_unknown_arguments +transportoptions/granttype | Applied to Q03 packet; conditional proposals not approvals. |
| X-M1 | shared missed issue | Canonical child/aggregate scope; security-only overwrite repair belongs Q05. | Binding shared missed issue; current Phase70/revised02. | Q03-06 | Exact child scope/runtime ledger cases. | Applicable F2 consumer; Q05 portion reference-only. |
| X-M2 | shared missed issue | Same-packet docs, mypy and diff CI gates. | Binding shared missed issue; current Phase70/revised02. | Q03-16/19 | Literal commands below and receipt regeneration. | Applicable. |
| X-M3 | shared missed issue | Q03 selected-test entrypoint/argv fully specified by F5. | Binding shared missed issue; current Phase70/revised02. | Q03-13/M5 | F5 pytest argv, outcomes and counts. | Applicable Q03 portion; Q06 isolation choice excluded. |
| X-M4 | shared missed issue | Q07 plugin transport with scratch_on_pythonpath. | Binding shared missed issue; current Phase70/revised02. | Shared F4/F5 reference | Q03 supplies no plugin; retain actual helper signature. | Q07-only correction excluded; no Q03 plugin proposal. |
| X-M5 | shared missed issue | D5 warn changes CLI exit from0 to1. | Binding shared missed issue; current Phase70/revised02. | Q03-02/14/18 | Partial warn JSON and CLI exit1. | Applicable; D5 remains user-owned. |
| X-M6 | shared missed issue | Q06 typecheck_config str versusPath. | Binding shared missed issue; current Phase70/revised02. | Exclusion reconciliation | No Q03 typecheck option. | Excluded Q06-only. |
| X-M7 | shared missed issue | Phase70 engine changes and Q02 Ruff dependency. | Binding shared missed issue; current Phase70/revised02. | Q03-07/25/M2 | Current adapters plus revised02 acceptance. | Ruff prerequisite applicable; unrelated engines reference-only. |

### Necessary source-grounded dependency

Q03-STDIO is an additional Foundation-owned correction, discovered while
grounding preview against the actual Phase70 runner. Its exact gate/descriptor
edits and five named subprocess regression bodies preserve captured bytes,
owned termination, private output cleanup and default DEVNULL behavior. Existing
diagnostic redaction/bounds remain required. This dependency supplements the
88 frozen finding/override dispositions; it does not replace any of them.

Q03-SCOPE is the Foundation-owned staged identity reconciliation needed by
Q03-06/07. It preserves logical requested counts, validates actual physical
argv consumption and refuses complete coverage when mapping or consumption is
missing. Its proposed body/tests supplement the same frozen coverage.

### Cross-plan alignment and frozen baseline

Delivery root: `/Users/jamesdsizemore/Developer/rush-cli`, HEAD
`c78e445ba1e575ca373e35840142cd627b055d6a`; existing user-owned AGENTS.md
diff and untracked documents/scratch are preserved.
Implementation root: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`,
branch `phase/70-agent-adoption-and-usability`, HEAD
`66c6c799eaa5b6017776d659e9e0de2b4a8878a5`, clean at capture.
Git identity does not establish Phase70 acceptance.

Original Plan03 SHA256:
`4e2bb14b67e05c15cdb251efb34bc1f1cdec22fcc2d9a15c890b59507dd61a9a`
(118598 bytes, 1855 lines). Revised protected inputs:

```text
00-shared-foundation.md 12917ade4f88f4d508f2829f55033cb2498638398df7a41be49e519ad2e46275
01-rush-review.md 773fe54dc1f6d37151ac60f0ea0d2e44c23c99e9f9587c1ffcb21f91d0259caa
02-rush-lint.md 4bb540e3559c3c81ecf5ea105468a4fbffcb9976667c9c61717b3edd2a3a068b
Claude report 362dae4489fbe8f6322217e30ae69ed3ad8a888732a37029641a0040cd8ef633
Command audit 8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f
```

Plan00 supplies actual F1–F6/F8–F11 contracts, including F5 `.isolated`,
cleanup/receipt semantics and shared ownership. Plan01 supplies its exact
14-file prerequisite transfer/registration route and verified documentation
regeneration APIs. Plan02 supplies selected vectors, config/cwd/staging,
Ruff format branch, canonical versus nested runtime scope and actual assessed
paths. Q03-STDIO is a backward-compatible Foundation row required by captured
preview I/O; existing callers retain default stdin/stdout behavior.

Shared requested baseline remains scanner provisioning, connected specialist
local models, selectable voice/live speech and 3D companion. These are user
requirements, not invented command innovations. Q03 adds no unrelated baseline
implementation or next-plan work.

### Remediation boundary receipt

Author: GPT6.1 Sol High, concrete prefix packets. Coordinator: scope, frozen
coverage, integration and tail. Independent reviewer: GPT6 Luna High, read-only
critical binding review and final frozen semantic review. No leaf delegation.

Full coverage froze before drafting: 34 Q03 findings/missed issues, 18 shared X
findings, all 29 final C dispositions (24 applicable; five command-specific
exclusions), and seven shared missed-issue dispositions. Exclusions are explicit
above; row counts prove inventory only. Final whole-file hash and semantic verdict
accompany frozen review/handoff; neither proves implementation behavior.

Observed static checks cover all 18 proposed Python fences: AST parsing and Ruff
lint/format pass. Nine standalone modules use full checks. Six existing runtime
body frames exclude only their existing-frame F821/F841 context; Q03-SCOPE's
module frame excludes F821 for verified existing runtime globals. Two test
augmentations are checked with the complete proposed unit-module context.
An affected literal-parenthesis repair invalidated only its fence's prior result;
unchanged fences were not rerun. These checks establish syntax/style only.

Relative direct-call operands and cwd are absolute; the concrete
`test_relative_nested_directory_uses_absolute_operand_and_cwd` regression invokes
the actual Ruff adapter and checks argv, cwd, assessed paths and unchanged bytes.
Only its two affected source/unit fences were rechecked after this correction;
AST and Ruff lint/format pass. An absent historical staged-input test-module
operand was removed; both staged identity tests live in the owned format module.

Coordinator compared captured original bytes with corrected test inventory:
all 46 original named test bodies remain represented among 60 current names.
Name retention proves
inventory; final semantic review separately checks substantive preservation.
Protected tracked/untracked file-byte fingerprints match baseline across 1633
main-checkout files and 1615 Phase70 files, excluding only this Plan03 target.
Both Git HEAD/status states and every other plan's hash match baseline, including
the protected revised Plans00/01/02. Fingerprints:

```text
main protected: 05bf2de2b9b71767b77d9916d846761d37b9d76c973d90cd90f18c2003cbd816
Phase70 protected: b437d5e0308a9b5c2a5cd750488a2429f2b0ac052eab63a2aaaec15f4fbff224
```

Independent review identified three stale canonical-scope assertions and one
MCP runtime-path anchoring conflict. Their corrections preserve valid child
evidence and physical containment. The added initialized-stdio regression uses
an observable executable launch marker and exact F4 relative-path rejection,
with ordinary check/source bytes preserved. Only affected fences 14/16 were
rechecked: AST, Ruff lint and Ruff format pass. Remaining fences retain their
accepted results. Q03-16's stale duplicate commands now point to the authoritative
staged checks; the stdio selector fixture raises if unexpectedly executed.
Only affected fence 16 was rechecked after these two final corrections: AST,
Ruff lint and Ruff format pass. Final semantic review covers this byte snapshot.

Final handoff must confirm these unchanged subjects and the reviewed target hash.
No future source/test/CLI/MCP/OCI behavioral check was executed during remediation.

Development readiness requires recorded applicable D1/D2/D3/D4/D5/D6/D8/D10/D11
choices and Phase70 T1–T29/G0–G8 acceptance evidence. Q03's explicitly flagged
audit deviations remain proposals as specified in its packet; routine source/
helper design is resolved here rather than delegated to James.
F1/F2/F3/F6, Q02 selection/staging/Ruff format and Q03-STDIO/Q03-SCOPE have an ordered
implementation route; F4/F5 and verified images/OCI CI are X1 entry/acceptance
requirements. Fully specified future dependencies are ordered work, not absent
packet authoring. Implementation acceptance during this task: none.
