# Q10 — markdown

Implement `markdown` corrections and retained expansions from binding audit.

## Feature and goal

Remediate complete Q10 scope. Planning only; production changes and tests below proposed, unimplemented and unexecuted. Grounding: main `c78e445ba1e575ca373e35840142cd627b055d6a`; clean Phase70 `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70` at `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`. Read `AGENTS.md`, `docs/templates/task-block-template.md`, `README.md`, `00-shared-foundation.md` in this plan directory first. Foundation is defined dependency/owner. Audit `docs/reports/cli-mcp-command-audit-2026-09-26.md` SHA256 `8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f`; remediation `docs/reports/command-tdd-2026-10-01-plan-remediation.md` SHA256 `362dae4489fbe8f6322217e30ae69ed3ad8a888732a37029641a0040cd8ef633`. Binding C-01–C-29 overrides contradictory older fixes. Earlier report probe outcomes do not verify corrected proposed code.

## Required behavior

Preserve scanner provisioning, connected specialist local models, selectable voice/live speech and 3D companion as user baseline. Command expansions remain separate. F1 strict flat schema rejects unknown keys/string grants with MCP isError=false, ToolResult error, raw error.code=INVALID_REQUEST; valid-field rejection uses metadata.error.code=invalid_argument; escape uses path_escape. F2 canonical engines/scope, no duplicate child arrays or partial booleans. F3 whole-operation denial: skipped, execution cause permission_denied, operation block denied/build_or_slow_denied, zero spawns/writes. Verify-only row denial preserves base assessment. Runtime absolute, never cwd-anchored; F4 validates platform/runtime before image. F4/F5/F6 exact foundation contracts retained. Shared aggregate choice remains README decision, no local override.

## Deliverables and file map

Create new file tests/test_markdown.py (absent both revisions). Source/fixture/test patches below proposed only. Shared CLI/MCP/catalog/reference/permissions/CHANGELOG/coverage rows are Foundation-owned serialized Q10-DOC rows in same packet. Existing Phase70 discovery/permission/provenance/zero-skip gates retained.

## Dependencies and ordered tasks

1. Finish foundation interfaces and ratify open choices; no report default is approval.
2. Record interface-absent RED separately; assert exported interface/metadata before new-option invocation. Require behavior assertion RED once interface exists.
3. Apply local source/fixtures/tests; preserve existing protocols and unrelated code.
4. Run narrow gates and same-packet docs; future final full-suite acceptance only after implementation.

## Constraints

This remediation writes plans only; no production/tests/source/config writes, downloads, hooks, commits/pushes/releases. pytest runtime dependency (`pyproject.toml:27`). Terms: producer-qualified metric has engine, unit, actual value and source digest; TP/FP/TN/FN are observed labeled counts; isolation means actual foundation OCI boundary. Any edit invalidates frozen review.

## Proposed source changes

```python
"""Check Markdown files with externally discovered markdownlint-cli."""

from __future__ import annotations

import difflib
import hashlib
import importlib
import json
import os
import re
import shlex
import stat
import tempfile
from pathlib import Path
from typing import Any

import click
from pydantic import StrictBool, StrictInt

from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..permissions import ExecutionPermissions, build_execution_metadata, check_permissions
from .base import Finding, ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, run_engine
from .routing import collect_files

_SHELL_FENCES = frozenset({"sh", "bash", "shell", "console", "zsh"})
_EXECUTABLE_COMMANDS = frozenset({"lint", "markdown", "test"})
_RUNTIME_NAMES = frozenset({"docker", "podman"})
_OPERATOR_CHARS = frozenset("();<>|&")
_IMAGE_REF = re.compile(r"[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}")
_SKIPPED = {"status": "skipped", "reason": "isolation_unavailable"}


def _extract_rush_examples(text: str) -> list[tuple[int, str, str]]:
    """Return (line number, line prefix, command) for each Rush example inside a
    fenced sh/bash/shell/console/zsh block; the command starts at `rush`."""
    examples: list[tuple[int, str, str]] = []
    marker, shell = "", False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not marker:
            for char in "`~":
                if stripped.startswith(char * 3):
                    count = len(stripped) - len(stripped.lstrip(char))
                    marker = char * count
                    info = stripped[count:].split()
                    shell = bool(info) and info[0].lower() in _SHELL_FENCES
                    break
            continue
        if stripped.startswith(marker) and not stripped.strip(marker[0]):
            marker, shell = "", False
            continue
        if not shell:
            continue
        prefix = line[: len(line) - len(line.lstrip())]
        body = stripped
        if body.startswith("$ "):
            prefix, body = prefix + "$ ", body[2:].lstrip()
        if body.startswith("uv run rush "):
            prefix, body = prefix + "uv run ", body[len("uv run ") :]
        if body.startswith("rush "):
            examples.append((number, prefix, body))
    return examples


def _example_argv(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    argv = list(lexer)
    for token in argv:
        if set(token) <= _OPERATOR_CHARS:
            raise ValueError(f"shell operator {token!r}")
        if "$" in token or "`" in token:
            raise ValueError(f"shell substitution in {token!r}")
    return argv


def _validate_example_argv(argv: list[str]) -> None:
    from rush.cli import cli  # lazy: rush/cli.py imports rush.tools

    if not argv or argv[0] != "rush":
        raise ValueError("example does not start with rush")
    context = click.Context(cli)
    command: click.Command = cli
    rest = argv[1:]
    while isinstance(command, click.Group):
        if not rest:
            raise ValueError("missing subcommand")
        if rest[0].startswith("-"):
            break
        child = command.get_command(context, rest[0])
        if child is None:
            raise ValueError(f"unknown command {rest[0]!r}")
        command, rest = child, rest[1:]
        context = click.Context(command, parent=context)
    options = {
        opt
        for param in command.get_params(context)
        if isinstance(param, click.Option)
        for opt in (*param.opts, *param.secondary_opts)
    }
    for token in rest:
        if token == "--":
            break
        if token.startswith("-") and token != "-" and not token.lstrip("-").isdigit():
            name = token.split("=", 1)[0]
            if not name.startswith("--") and len(name) > 2:
                name = name[:2]
            if name not in options:
                raise ValueError(f"unknown option {name!r}")


def _executable_shape(argv: list[str]) -> bool:
    return (
        len(argv) == 4
        and argv[0] == "rush"
        and argv[1] in _EXECUTABLE_COMMANDS
        and argv[3] == "--json"
    )


def _invalid_arguments(
    verify_examples: object,
    repair_example: object,
    candidate_argv: object,
    example_expected: object,
    runtime_path: object,
    image_ref: object,
) -> str | None:
    if not isinstance(verify_examples, bool):
        return "verify_examples must be a boolean"
    if repair_example is not None and (
        isinstance(repair_example, bool)
        or not isinstance(repair_example, int)
        or repair_example < 1
    ):
        return "repair_example must be an integer line number of at least 1"
    if candidate_argv is not None and (
        not isinstance(candidate_argv, list)
        or not all(isinstance(token, str) for token in candidate_argv)
    ):
        return "candidate_argv must be a list of strings"
    if example_expected is not None and (
        not isinstance(example_expected, dict)
        or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in example_expected.items()
        )
    ):
        return "example_expected must be an object with string values"
    if runtime_path is not None and not isinstance(runtime_path, (str, Path)):
        return "runtime_path must be a path"
    if image_ref is not None and not isinstance(image_ref, str):
        return "image_ref must be a string"
    return None


def _contained_fixture(root: Path, example_fixture: Path | str) -> Path:
    fixture = Path(example_fixture)
    if fixture.is_absolute():
        fixture = Path(os.path.realpath(fixture)).relative_to(root)
    contained = PhysicalRoot(root).open_contained(fixture, purpose="read")
    if not contained.is_dir():
        raise ValueError("example fixture must be a directory inside the Markdown root")
    return contained


def _execute_candidate(
    root: Path,
    fixture: Path,
    argv: list[str],
    expected: dict[str, str],
    runtime_path: Path | str | None,
    image_ref: str | None,
) -> dict[str, Any]:
    """Run one data-only Rush command in the OCI provider and compare the
    declared keys of its ToolResult; raises ValueError/ContainmentError before
    any spawn for an invalid candidate."""
    if not _executable_shape(argv):
        raise ValueError("candidate must be rush lint|markdown|test PATH --json")
    _validate_example_argv(argv)
    target = PhysicalRoot(fixture).open_contained(argv[2], purpose="read")
    if not target.exists():
        raise ValueError("example target missing in fixture")
    try:
        provider = importlib.import_module("rush.runtime.isolated_process")
    except ImportError:
        return dict(_SKIPPED)
    try:
        provider.check_isolation_inputs(root, runtime_path=runtime_path, image_ref=image_ref)
        with tempfile.TemporaryDirectory(prefix="rush-example-") as directory:
            process = provider.run_isolated_argv(
                root,
                Path(directory),
                runtime_path=Path(runtime_path),
                image_ref=image_ref,
                entrypoint="/usr/local/bin/rush",
                argv=argv[1:],
                timeout_s=30,
                workdir_rel=fixture.relative_to(root).as_posix(),
            )
    except provider.IsolationUnavailable:
        return dict(_SKIPPED)
    if process.returncode not in (0, 1):
        return {"status": "candidate_failed", "returncode": process.returncode}
    try:
        observed = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"status": "malformed_output", "returncode": process.returncode}
    matches = isinstance(observed, dict) and all(
        observed.get(key) == value for key, value in expected.items()
    )
    return {
        "status": "verified_candidate" if matches else "output_mismatch",
        "returncode": process.returncode,
        "actual_result": observed,
    }


class MarkdownTool(ToolFn):
    name = "markdown"

    @property
    def mcp_description(self) -> str:
        return "Check Markdown at <path> without rewriting files; missing markdownlint-cli returns status='skipped'."

    def __call__(
        self,
        path: Path,
        *,
        verify_examples: StrictBool = False,
        example_fixture: Path | None = None,
        repair_example: StrictInt | None = None,
        candidate_argv: list[str] | None = None,
        example_expected: dict[str, str] | None = None,
        runtime_path: Path | None = None,
        image_ref: str | None = None,
        allow_build: StrictBool = False,
        allow_slow: StrictBool = False,
    ) -> ToolResult:
        if type(allow_build) is not bool or type(allow_slow) is not bool:
            result=error_result(self.name,None,'permission flags must be bool')
            result['metadata']={'error':{'code':'invalid_argument','message':result['summary']}}
            return result
        return self.run(
            path,
            verify_examples=verify_examples,
            example_fixture=example_fixture,
            repair_example=repair_example,
            candidate_argv=candidate_argv,
            example_expected=example_expected,
            runtime_path=runtime_path,
            image_ref=image_ref,
            permissions=ExecutionPermissions(build=allow_build, slow=allow_slow),
        )

    def run(
        self,
        path: Path,
        *,
        config=None,
        verify_examples: bool = False,
        example_fixture: Path | str | None = None,
        repair_example: int | None = None,
        candidate_argv: list[str] | None = None,
        example_expected: dict[str, str] | None = None,
        runtime_path: Path | str | None = None,
        image_ref: str | None = None,
        permissions: ExecutionPermissions | None = None,
    ) -> ToolResult:
        from ..engines import ENGINES
        from ..engines.markdownlint import DEFAULT_CONFIG, DEFAULT_IGNORE

        start = now_ms()

        def reject(message: str, reason: str = "invalid_argument") -> ToolResult:
            result = error_result(self.name, None, message, duration_ms=elapsed_ms(start),
                                  terminal_reason=reason if reason == "malformed_output" else None)
            result.setdefault("metadata", {})["error"] = {"code": reason, "message": message}
            return result

        invalid = _invalid_arguments(
            verify_examples,
            repair_example,
            candidate_argv,
            example_expected,
            runtime_path,
            image_ref,
        )
        if invalid:
            return reject(invalid)
        verify = verify_examples or repair_example is not None
        root = (path if path.is_dir() else path.parent).resolve()
        fixture: Path | None = None
        if verify:
            if example_fixture is None:
                return reject("contained example_fixture required")
            try:
                fixture = _contained_fixture(root, example_fixture)
            except (ValueError, ContainmentError) as exc:
                return reject(f"example_fixture must be a contained directory: {exc}")
        grants_ok, missing = check_permissions(
            ExecutionPermissions(build=True, slow=True), permissions
        )
        if repair_example is not None and not grants_ok:
            return ToolResult(tool=self.name, engine=None, engine_version=None, status="skipped",
                duration_ms=elapsed_ms(start), summary="markdown repair requires --allow-build and --allow-slow",
                findings=[], metadata={"execution": build_execution_metadata("executed", requested=ExecutionPermissions(build=True, slow=True), granted=permissions, extra={"disposition":"not_run", "cause":"permission_denied"}), "example_repair":{"status":"denied", "reason":"build_or_slow_denied"}})

        files = collect_files(path, {"md", "mdx"})
        if repair_example is not None:
            if candidate_argv is None or example_expected is None or not {'tool','status'} <= example_expected.keys():
                return reject('candidate_argv and expected tool/status required')
            if len(files) != 1 or repair_example not in {line for line,_,_ in _extract_rush_examples(files[0].read_text(encoding='utf-8'))}:
                return reject('selected line must be Rush shell example in one document')
            try:
                if not _executable_shape(candidate_argv):
                    raise ValueError('unsupported_example_shape')
                _validate_example_argv(candidate_argv)
                assert fixture is not None
                target = PhysicalRoot(fixture).open_contained(candidate_argv[2], purpose='read')
                if not target.exists():
                    raise ValueError('example target missing in fixture')
                provider = importlib.import_module('rush.runtime.isolated_process')
                provider.check_isolation_inputs(root, runtime_path=runtime_path, image_ref=image_ref)
            except ImportError:
                return ToolResult(tool=self.name,engine=None,engine_version=None,status='skipped',duration_ms=elapsed_ms(start),summary='markdown repair requires available isolation provider',findings=[],metadata={'example_repair':dict(_SKIPPED)})
            except (ValueError,ContainmentError,click.ClickException) as exc:
                return reject(str(exc),'path_escape' if isinstance(exc,ContainmentError) else 'invalid_argument')
            except provider.IsolationUnavailable:
                return ToolResult(tool=self.name,engine=None,engine_version=None,status='skipped',duration_ms=elapsed_ms(start),summary='markdown repair requires available isolation provider',findings=[],metadata={'example_repair':dict(_SKIPPED)})
        selected = [str(file.resolve()) for file in files]
        if not files:
            result = ToolResult(
                tool=self.name,
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"markdown: no supported source files found under {path}",
                findings=[],
                raw=None,
            )
            reason = "no_supported_targets"
        else:
            result = run_engine(
                ENGINES["markdownlint-cli"],
                path,
                selected,
                tool_name=self.name,
                consumed_paths=selected,
            )
            reason = None
        assessed = selected if result["status"] in ("ok", "warn", "fail") else []
        config_digest = hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest()
        ignore_digest = hashlib.sha256(DEFAULT_IGNORE.read_bytes()).hexdigest()
        metadata: dict[str, Any] = result.get("metadata") or {}
        result["metadata"] = metadata
        metadata.update(
            selected_paths=selected,
            assessed_paths=assessed,
            configuration={
                "config_path": str(DEFAULT_CONFIG),
                "config_digest": config_digest,
                "ignore_path": str(DEFAULT_IGNORE),
                "ignore_digest": ignore_digest,
            },
            examples=[],
            scope={
                "version": 1,
                "kind": "file",
                "logical_root": str(root),
                "requested_targets": [str(path)],
                "requested_file_count": len(selected),
                "matched_file_count": len(selected),
                "consumed_file_count": len(assessed),
                "consumed_files": assessed,
                "configuration_files": [str(DEFAULT_CONFIG), str(DEFAULT_IGNORE)],
                "coverage": "complete" if assessed else "none" if not files else "unavailable",
                "reason": reason
                or (None if assessed else f"engine_{result['status']}"),
            },
        )
        for entry in metadata.get("engines", []):
            if entry.get("engine") == "markdownlint-cli":
                entry["config"] = {
                    "path": str(DEFAULT_CONFIG),
                    "sha256": config_digest,
                    "reason": None,
                }
        if not files:
            metadata["skip_reason"] = "no_targets"
        elif verify:
            assert fixture is not None
            rows: list[dict[str, Any]] = []
            prefixes: dict[tuple[str, int], str] = {}
            for file in files:
                text = file.read_text(encoding="utf-8", errors="replace")
                for number, prefix, command in _extract_rush_examples(text):
                    row: dict[str, Any] = {
                        "document": str(file.resolve()),
                        "line": number,
                        "command": command,
                        "signature_status": "valid",
                        "execution_status": "not_run",
                    }
                    try:
                        _validate_example_argv(_example_argv(command))
                    except ValueError as exc:
                        row["signature_status"] = "invalid"
                        row["signature_error"] = str(exc)
                        result["findings"] = [
                            *result["findings"],
                            Finding(
                                path=str(file.resolve()),
                                line=number,
                                column=1,
                                rule="rush-example-signature",
                                rule_id="rush-example-signature",
                                severity="warn",
                                message=f"Rush example signature invalid: {exc}",
                            ),
                        ]
                        if result["status"] == "ok":
                            result["status"] = "warn"
                    prefixes[(row["document"], number)] = prefix
                    rows.append(row)
            metadata["examples"] = rows
            if repair_example is not None:
                if candidate_argv is None or example_expected is None or not {'tool','status'} <= example_expected.keys():
                    return reject('candidate_argv and expected tool/status required')
                if len(files)!=1 or (str(files[0].resolve()),repair_example) not in prefixes:
                    return reject('selected line must be Rush shell example in one document')
                try:
                    if not _executable_shape(candidate_argv):
                        raise ValueError('unsupported_example_shape')
                    _validate_example_argv(candidate_argv)
                    target=PhysicalRoot(fixture).open_contained(candidate_argv[2],purpose='read')
                    if not target.exists():
                        raise ValueError('example target missing in fixture')
                    provider=importlib.import_module('rush.runtime.isolated_process')
                    provider.check_isolation_inputs(root,runtime_path=runtime_path,image_ref=image_ref)
                except ImportError:
                    metadata['example_repair']=dict(_SKIPPED)
                    return result
                except (ValueError,ContainmentError,click.ClickException) as exc:
                    return reject(str(exc), 'path_escape' if isinstance(exc,ContainmentError) else 'invalid_argument')
                except provider.IsolationUnavailable:
                    metadata['example_repair']=dict(_SKIPPED)
                    return result
            for row in rows:
                if row["signature_status"] != "valid":
                    continue
                argv = _example_argv(row["command"])
                if not _executable_shape(argv):
                    row["execution_status"] = "unsupported_example_shape"
                elif not grants_ok:
                    row["execution_status"] = "denied"
                    row["execution_reason"] = "build_or_slow_denied"
                else:
                    try:
                        trial = _execute_candidate(
                            root,
                            fixture,
                            argv,
                            {"tool": argv[1]},
                            runtime_path,
                            image_ref,
                        )
                    except (ValueError, ContainmentError):
                        row["execution_status"] = "invalid_example_target"
                        continue
                    row["execution_status"] = trial["status"]
                    if "reason" in trial:
                        row["execution_reason"] = trial["reason"]
                    actual = trial.get("actual_result")
                    if isinstance(actual, dict):
                        row["observed_status"] = actual.get("status")
            if repair_example is not None:
                if (
                    candidate_argv is None
                    or example_expected is None
                    or not {"tool", "status"} <= example_expected.keys()
                ):
                    return reject("candidate_argv and expected tool/status required")
                if len(files) != 1:
                    return reject("repair requires one Markdown document")
                document = files[0]
                key = (str(document.resolve()), repair_example)
                if key not in prefixes:
                    return reject(
                        "selected line is not a Rush example inside a shell fence"
                    )
                original = document.read_bytes()
                try:
                    verified = _execute_candidate(
                        root,
                        fixture,
                        candidate_argv,
                        example_expected,
                        runtime_path,
                        image_ref,
                    )
                except (ValueError, ContainmentError, click.ClickException) as exc:
                    return reject(f"invalid example candidate: {exc}")
                if verified["status"] == "malformed_output":
                    return reject("candidate stdout was not JSON", "malformed_output")
                if verified["status"] == "verified_candidate":
                    digest = hashlib.sha256(original).hexdigest()
                    if hashlib.sha256(document.read_bytes()).hexdigest() != digest:
                        verified = {"status": "stale_source", "source_digest": digest}
                    else:
                        lines = original.decode("utf-8", errors="replace").splitlines(
                            keepends=True
                        )
                        line = lines[repair_example - 1]
                        ending = line[len(line.rstrip("\r\n")) :]
                        updated = lines.copy()
                        updated[repair_example - 1] = (
                            prefixes[key] + shlex.join(candidate_argv) + ending
                        )
                        verified["source_digest"] = digest
                        verified["patch"] = "".join(
                            difflib.unified_diff(
                                lines,
                                updated,
                                fromfile=str(document),
                                tofile=str(document),
                            )
                        )
                metadata["example_repair"] = verified
                if verified["status"] == "skipped":
                    result["status"] = "skipped"
                    result["summary"] = "markdown repair requires available isolation provider"
        result["duration_ms"] = elapsed_ms(start)
        return result
```

#### Block C: `src/rush/cli_support/catalog_commands.py` (66c6c79; three edits, each anchor occurs exactly once)

Verified with `ruff format --check`, `ruff check` and `mypy`: all clean. The `markdown --help` output lists each new option once. It also lists `--allow-build` and `--allow-slow` once each (the existing flags), and `rush lint --help` gains none of the new options.

1. Anchor `import os\nimport re\nfrom dataclasses import dataclass\n`: replace with `import json\nimport os\nimport re\nfrom dataclasses import dataclass\n`. The `json` import is required and is absent at 66c6c79.
2. Anchor `# Per-tool CLI options, mapped explicitly (R11.6): generating flags from every`: insert this before it.

```python
def _markdown_expected(
    _ctx: click.Context, _param: click.Parameter, value: str | None
) -> dict[str, str] | None:
    """Parse --example-expected into the ToolResult keys a repair must match."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"must be a JSON object: {exc}") from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in parsed.items()
    ):
        raise click.BadParameter("must be a JSON object with string values")
    return parsed


```

3. Anchor `    ),\n}\n\n\ndef build_catalog_path_command(`: insert the following after the typecheck entry's `    ),`, before the closing `}`.

```python
_TOOL_CLI_OPTIONS_UPDATE = {
    "markdown": (
        click.Option(
            ["--verify-examples", "verify_examples"],
            is_flag=True,
            default=None,
            help=(
                "Signature-check fenced Rush shell examples. Executing them also "
                "needs --example-fixture, --allow-build, --allow-slow, "
                "--runtime-path and --image-ref."
            ),
        ),
        click.Option(
            ["--example-fixture", "example_fixture"],
            type=click.Path(file_okay=False, path_type=Path),
            default=None,
            callback=lambda _ctx, _param, value: (
                None if value is None else Path(os.path.abspath(value))
            ),
            help=(
                "Directory inside the Markdown root that examples run against; "
                "relative paths resolve against the current directory."
            ),
        ),
        click.Option(
            ["--repair-example", "repair_example"],
            type=click.IntRange(min=1),
            default=None,
            help="One-based line of the Rush example to repair (one Markdown file).",
        ),
        click.Option(
            ["--candidate-argv", "candidate_argv"],
            multiple=True,
            default=(),
            callback=lambda _ctx, _param, value: list(value) or None,
            help="One argv token of the candidate command; repeat in order.",
        ),
        click.Option(
            ["--example-expected", "example_expected"],
            default=None,
            callback=_markdown_expected,
            help='JSON object of ToolResult keys, e.g. {"tool":"lint","status":"ok"}.',
        ),
        click.Option(
            ["--runtime-path", "runtime_path"],
            type=click.Path(dir_okay=False, path_type=Path),
            default=None,
            # Runtime is strict absolute provider input; never cwd-anchored.
            help="Absolute path of an approved docker or podman executable.",
        ),
        click.Option(
            ["--image-ref", "image_ref"],
            default=None,
            help="Locally present Rush image pinned as name@sha256:<64 hex>.",
        ),
    ),
}
```

#### Block R: `src/rush/mcp_support/tool_registry.py` (66c6c79, one edit)

This one-line map entry makes MCP anchor `example_fixture` and `runtime_path` the same way the CLI callbacks do. Anchor:

```
    # T12 S12.7/finding 7: containment and family checks follow in the tool.
    "typecheck": ("typecheck_config",),
}
```

Replace with the same text plus `    "markdown": ("example_fixture",),` before the closing `}`. `ruff` and `mypy` pass on the edited file.

#### Block T: `tests/test_markdown.py` (new file; `ruff check` and `ruff format --check` clean)

The file below passed 13/13 at 66c6c79 with Blocks I, C and R applied. At baseline it gives 12 failed and 1 passed.

Two edits are applied after the verified run, so the file below is not byte-identical to the executed copy:
- `check=False,` was added to the `subprocess.run` call in `test_markdown_options_cli_mcp_parity`, after `timeout=180,`. The only ruff finding on the executed file was PLW1510 on that call, and a probe file with `check=False` passes `ruff check` and `ruff format --check`.
- The live OCI test is appended at the end and has not been executed.

```python
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import rush.tools.markdown as module
from rush.engines.markdownlint import DEFAULT_CONFIG, DEFAULT_IGNORE, MarkdownlintEngine
from rush.permissions import ExecutionPermissions
from rush.tools.markdown import MarkdownTool

GRANTS = ExecutionPermissions(build=True, slow=True)
IMAGE = "rush@sha256:" + "a" * 64


def _engine(status):
    def fake(engine, path, args, **kwargs):
        return {
            "tool": "markdown",
            "engine": "markdownlint-cli",
            "engine_version": "0.49.1",
            "status": status,
            "duration_ms": 0,
            "summary": "captured",
            "findings": [],
        }

    return fake


def _no_spawn(*args, **kwargs):
    raise AssertionError("spawn")


def _repair_tree(tmp_path):
    docs = tmp_path / "docs"
    (docs / "fixture" / "src").mkdir(parents=True)
    (docs / "fixture" / "src" / "clean.py").write_text("value: int = 1\n")
    guide = docs / "guide.md"
    guide.write_text("~~~sh\nrush lint src --output json\n~~~\n")
    runtime = tmp_path / "bin" / "docker"
    runtime.parent.mkdir()
    runtime.write_text("")
    runtime.chmod(0o755)
    return docs, guide, runtime


def _provider(monkeypatch, returncode, stdout, mutate=None):
    calls = []

    class IsolationUnavailable(RuntimeError):
        pass

    def run_isolated_argv(root, scratch, **kwargs):
        calls.append(kwargs)
        if mutate is not None:
            mutate.write_text(mutate.read_text() + "\n")
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    fake = types.ModuleType("rush.runtime.isolated_process")
    fake.IsolationUnavailable = IsolationUnavailable
    fake.run_isolated_argv = run_isolated_argv
    from rush.runtime.isolated_process import check_isolation_inputs
    fake.check_isolation_inputs = check_isolation_inputs
    monkeypatch.setitem(sys.modules, "rush.runtime.isolated_process", fake)
    return calls


def test_malformed_or_nonzero_report(tmp_path, monkeypatch):
    engine = MarkdownlintEngine()
    monkeypatch.setattr(engine, "version", lambda: "fixture")
    for stdout, exit_code in [("{", 0), ("", 2)]:
        raw = {"stdout": stdout, "stderr": "", "exit_code": exit_code}
        assert engine.normalize(raw, tmp_path, "markdown")["status"] == "error"
    raw = {"stdout": "[]", "stderr": "", "exit_code": 0}
    assert engine.normalize(raw, tmp_path, "markdown")["status"] == "ok"


def test_selected_paths_and_config(tmp_path, monkeypatch):
    guide = tmp_path / "guide.md"
    guide.write_text("~~~sh\nrush lint src --json\n~~~\n")
    (tmp_path / "notes.txt").write_text("not Markdown\n")
    calls = []

    def lint(engine, path, args, **kwargs):
        calls.append(args)
        return {
            "tool": "markdown",
            "engine": "markdownlint-cli",
            "engine_version": None,
            "status": "skipped",
            "duration_ms": 0,
            "summary": "controlled engine absence",
            "findings": [],
        }

    monkeypatch.setattr(module, "run_engine", lint)
    monkeypatch.setattr(subprocess, "Popen", _no_spawn)
    result = MarkdownTool().run(tmp_path)
    assert calls == [[str(guide.resolve())]]
    assert result["metadata"]["selected_paths"] == [str(guide.resolve())]
    assert result["metadata"]["assessed_paths"] == []
    assert result["metadata"]["configuration"] == {
        "config_path": str(DEFAULT_CONFIG),
        "config_digest": hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
        "ignore_path": str(DEFAULT_IGNORE),
        "ignore_digest": hashlib.sha256(DEFAULT_IGNORE.read_bytes()).hexdigest(),
    }
    assert result["metadata"]["examples"] == []


def test_selected_paths_assessed_only_when_engine_ran(tmp_path, monkeypatch):
    guide = tmp_path / "guide.md"
    guide.write_text("# Guide\n")
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    result = MarkdownTool().run(tmp_path)
    assert result["metadata"]["assessed_paths"] == [str(guide.resolve())]
    assert result["metadata"]["scope"]["coverage"] == "complete"
    assert result["metadata"]["scope"]["consumed_file_count"] == 1


def test_no_targets_reports_none_scope(tmp_path):
    (tmp_path / "notes.txt").write_text("x\n")
    result = MarkdownTool().run(tmp_path)
    assert result["status"] == "skipped"
    assert result["metadata"]["scope"]["coverage"] == "none"
    assert result["metadata"]["scope"]["reason"] == "no_supported_targets"
    assert result["metadata"]["selected_paths"] == []
    assert result["metadata"]["assessed_paths"] == []


def test_verify_examples_opt_in(tmp_path, monkeypatch):
    guide = tmp_path / "guide.md"
    (tmp_path / "fx").mkdir()
    guide.write_text(
        "```bash\nuv run rush markdown . --json\nrush lint src | tee out\n"
        "$ rush memory expand --input x.json\nrush nosuch src\n```\n"
    )
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    monkeypatch.setattr(subprocess, "Popen", _no_spawn)
    assert MarkdownTool().run(guide)["metadata"]["examples"] == []
    fx = tmp_path / "fx"
    rows = MarkdownTool().run(guide, verify_examples=True, example_fixture=fx)[
        "metadata"
    ]["examples"]
    assert [
        (r["line"], r["signature_status"], r["execution_status"]) for r in rows
    ] == [
        (2, "valid", "build_or_slow_denied"),
        (3, "invalid", "not_run"),
        (4, "valid", "unsupported_example_shape"),
        (5, "invalid", "not_run"),
    ]
    granted = MarkdownTool().run(
        guide, verify_examples=True, example_fixture=fx, permissions=GRANTS
    )
    assert (
        granted["metadata"]["examples"][0]["execution_status"]
        == "isolation_unavailable"
    )


def test_example_signature_mismatch(tmp_path, monkeypatch):
    guide = tmp_path / "guide.md"
    guide.write_text("~~~sh\nrush lint src --nonexistent\n~~~\n")
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    monkeypatch.setattr(subprocess, "Popen", _no_spawn)
    result = MarkdownTool().run(guide, verify_examples=True, example_fixture=fixture)
    row = result["metadata"]["examples"][0]
    assert (row["line"], row["signature_status"], row["execution_status"]) == (
        2,
        "invalid",
        "not_run",
    )
    assert [(f["line"], f["rule"]) for f in result["findings"]] == [
        (2, "rush-example-signature")
    ]


def test_example_inputs_reject_before_spawn(tmp_path, monkeypatch):
    guide = tmp_path / "guide.md"
    guide.write_text("~~~sh\nrush lint src --json\n~~~\n")
    fx = tmp_path / "fx"
    fx.mkdir()
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    run = MarkdownTool().run
    assert run(guide, verify_examples="false", example_fixture=fx)["status"] == "error"
    assert run(guide, verify_examples=True)["status"] == "error"
    assert (
        run(guide, verify_examples=True, example_fixture=tmp_path.parent)["status"]
        == "error"
    )
    assert (
        run(guide, verify_examples=True, example_fixture=fx, repair_example=0)["status"]
        == "error"
    )
    assert (
        run(guide, verify_examples=True, example_fixture=fx, repair_example=True)[
            "status"
        ]
        == "error"
    )


def test_repair_controller_verified_mismatch_failed_malformed_stale(
    tmp_path, monkeypatch
):
    docs, guide, runtime = _repair_tree(tmp_path)
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    before = guide.read_bytes()
    ok = {"tool": "lint", "status": "ok"}
    kwargs = {
        "verify_examples": True,
        "repair_example": 2,
        "example_fixture": docs / "fixture",
        "candidate_argv": ["rush", "lint", "src", "--json"],
        "runtime_path": runtime,
        "image_ref": IMAGE,
        "permissions": GRANTS,
    }

    def repair(expected):
        return MarkdownTool().run(guide, example_expected=expected, **kwargs)

    calls = _provider(monkeypatch, 0, json.dumps(ok))
    verified = repair(ok)["metadata"]["example_repair"]
    assert verified["status"] == "verified_candidate"
    assert verified["returncode"] == 0 and verified["actual_result"]["tool"] == "lint"
    assert verified["source_digest"] == hashlib.sha256(before).hexdigest()
    assert "-rush lint src --output json\n+rush lint src --json\n" in verified["patch"]
    assert calls[0]["argv"] == ["lint", "src", "--json"]
    assert calls[0]["workdir_rel"] == "fixture"
    assert (
        calls[0]["entrypoint"] == "/usr/local/bin/rush" and calls[0]["timeout_s"] == 30
    )
    assert guide.read_bytes() == before
    mismatch = repair({"tool": "lint", "status": "fail"})
    assert mismatch["metadata"]["example_repair"]["status"] == "output_mismatch"
    _provider(monkeypatch, 2, "")
    assert repair(ok)["metadata"]["example_repair"]["status"] == "candidate_failed"
    _provider(monkeypatch, 0, "{")
    malformed = repair(ok)
    assert (malformed["status"], malformed["metadata"]["terminal_reason"]) == (
        "error",
        "malformed_output",
    )
    _provider(monkeypatch, 0, json.dumps(ok), mutate=guide)
    stale = repair(ok)["metadata"]["example_repair"]
    assert stale["status"] == "stale_source" and "patch" not in stale
    assert guide.read_bytes() != before


def test_repair_rejects_before_spawn(tmp_path, monkeypatch):
    docs, guide, runtime = _repair_tree(tmp_path)
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    calls = _provider(monkeypatch, 0, "{}")
    base = {
        "verify_examples": True,
        "repair_example": 2,
        "example_fixture": docs / "fixture",
        "example_expected": {"tool": "lint", "status": "ok"},
        "runtime_path": runtime,
        "image_ref": IMAGE,
    }
    good = ["rush", "lint", "src", "--json"]

    def run(candidate, **override):
        return MarkdownTool().run(
            guide, candidate_argv=candidate, permissions=GRANTS, **{**base, **override}
        )

    denied = MarkdownTool().run(guide, candidate_argv=good, **base)
    assert (denied["status"], denied["metadata"]["terminal_reason"]) == (
        "error",
        "permission_denied",
    )
    for candidate in (
        ["sh", "-c", "rm -rf ."],
        ["rush", "lint", "../../etc", "--json"],
        ["rush", "doctor", "--json"],
    ):
        assert run(candidate)["status"] == "error"
    assert run(good, example_fixture=tmp_path / "bin")["status"] == "error"
    rogue = docs / "docker"
    rogue.write_text("")
    rogue.chmod(0o755)
    inside = run(good, runtime_path=rogue)
    assert inside["metadata"]["example_repair"] == {
        "status": "skipped",
        "reason": "isolation_unavailable",
    }
    (docs / "fixture" / "link").symlink_to(tmp_path / "bin")
    assert run(["rush", "lint", "link", "--json"])["status"] == "error"
    writable = tmp_path / "bin2" / "podman"
    writable.parent.mkdir()
    writable.write_text("")
    writable.chmod(0o777)
    assert (
        run(good, runtime_path=writable)["metadata"]["example_repair"]["reason"]
        == "isolation_unavailable"
    )
    assert calls == []


def test_stale_example_repair_runs_only_rush_command(tmp_path, monkeypatch):
    docs, guide, runtime = _repair_tree(tmp_path)
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    kwargs = {
        "verify_examples": True,
        "repair_example": 2,
        "example_fixture": docs / "fixture",
        "example_expected": {"tool": "lint", "status": "ok"},
        "runtime_path": runtime,
        "image_ref": IMAGE,
        "permissions": GRANTS,
    }
    calls = _provider(
        monkeypatch, 0, json.dumps({"tool": "lint", "status": "ok"}), mutate=guide
    )
    stale = MarkdownTool().run(
        guide, candidate_argv=["rush", "lint", "src", "--json"], **kwargs
    )
    assert stale["metadata"]["example_repair"]["status"] == "stale_source"
    assert "patch" not in stale["metadata"]["example_repair"]
    assert (
        MarkdownTool().run(guide, candidate_argv=["sh", "-c", "rm -rf ."], **kwargs)[
            "status"
        ]
        == "error"
    )
    assert [call["argv"] for call in calls] == [["lint", "src", "--json"]]


def test_repair_preserves_example_prefix(tmp_path, monkeypatch):
    docs, guide, runtime = _repair_tree(tmp_path)
    guide.write_text("```bash\n  $ uv run rush lint src --output json\n```\n")
    monkeypatch.setattr(module, "run_engine", _engine("ok"))
    _provider(monkeypatch, 1, json.dumps({"tool": "lint", "status": "fail"}))
    result = MarkdownTool().run(
        guide,
        verify_examples=True,
        repair_example=2,
        example_fixture=docs / "fixture",
        candidate_argv=["rush", "lint", "src", "--json"],
        example_expected={"tool": "lint", "status": "fail"},
        runtime_path=Path(runtime_path),
        image_ref=IMAGE,
        permissions=GRANTS,
    )
    repair = result["metadata"]["example_repair"]
    assert repair["status"] == "verified_candidate" and repair["returncode"] == 1
    assert (
        "-  $ uv run rush lint src --output json\n+  $ uv run rush lint src --json\n"
        in repair["patch"]
    )


def _mcp_call(tmp_path, env, arguments):
    from transport_parity import run_mcp
    values=dict(arguments)
    values['path']=str(tmp_path / values['path']) if not Path(values['path']).is_absolute() else values['path']
    if 'example_fixture' in values:
        values['example_fixture']=str(tmp_path / values['example_fixture'])
    result=run_mcp('rush_markdown',values)
    return types.SimpleNamespace(isError=False, content=[types.SimpleNamespace(text=json.dumps(result))])


def _example_tree(tmp_path):
    guide = (
        "# Guide\n\n~~~bash\nrush lint src --nonexistent\nrush lint src --json\n~~~\n"
    )
    (tmp_path / "guide.md").write_text(guide)
    (tmp_path / "fixture" / "src").mkdir(parents=True)


def _rows(result):
    return [
        (e["line"], e["signature_status"], e["execution_status"])
        for e in result["metadata"]["examples"]
    ]


def _signature_findings(result):
    return [
        (f["line"], f["rule"])
        for f in result["findings"]
        if f["rule"] == "rush-example-signature"
    ]


def test_markdown_options_cli_mcp_parity(tmp_path):
    from transport_parity import run_cli, run_mcp
    _example_tree(tmp_path)
    code,left=run_cli('markdown',tmp_path/'guide.md',cli_options=('--verify-examples','--example-fixture',str(tmp_path/'fixture')))
    right=run_mcp('rush_markdown',{'path':str(tmp_path/'guide.md'),'verify_examples':True,'example_fixture':str(tmp_path/'fixture')})
    assert code==1
    assert _rows(left)==_rows(right)==[(4,'invalid','not_run'),(5,'valid','denied')]
    assert _signature_findings(left)==_signature_findings(right)==[(4,'rush-example-signature')]
    assert left['metadata']['scope']['consumed_file_count']==right['metadata']['scope']['consumed_file_count']==1
    assert left['metadata']['configuration']==right['metadata']['configuration']
    assert left['metadata']['examples'][1]['execution_reason']=='build_or_slow_denied'


def test_markdown_mcp_rejects_string_grants_before_spawn(tmp_path):
    import os

    project = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(project / "src")}
    _example_tree(tmp_path)
    response = _mcp_call(
        tmp_path,
        env,
        {
            "path": "guide.md",
            "verify_examples": True,
            "example_fixture": "fixture",
            "allow_build": "false",
            "allow_slow": "false",
        },
    )
    assert response.isError is False
    assert "allow_build" in response.content[0].text
    assert json.loads(response.content[0].text)["raw"]["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.oci_isolation
def test_verified_example_repair_uses_real_cli_result(tmp_path):
    # Live OCI test. PROPOSED, UNEXECUTED: no docker/podman or Rush image exists on this host.
    import os

    runtime = os.environ.get("RUSH_TEST_OCI_RUNTIME")
    image = os.environ.get("RUSH_TEST_RUSH_IMAGE")
    assert runtime and image, "OCI variables must be supplied for selected live gate"
    docs, guide, _ = _repair_tree(tmp_path)
    before = {p: p.read_bytes() for p in (guide, docs / "fixture" / "src" / "clean.py")}
    args = {
        "verify_examples": True,
        "repair_example": 2,
        "example_fixture": docs / "fixture",
        "candidate_argv": ["rush", "lint", "src", "--json"],
        "runtime_path": Path(runtime),
        "image_ref": image,
        "permissions": GRANTS,
    }
    ok = {"tool": "lint", "status": "ok"}
    repair = MarkdownTool().run(guide, example_expected=ok, **args)["metadata"][
        "example_repair"
    ]
    assert repair["status"] == "verified_candidate" and repair["returncode"] == 0
    actual = repair["actual_result"]
    assert (actual["tool"], actual["status"]) == ("lint", "ok")
    assert repair["source_digest"] == hashlib.sha256(before[guide]).hexdigest()
    assert "+rush lint src --json" in repair["patch"]
    assert {p: p.read_bytes() for p in before} == before
    fail = {"tool": "lint", "status": "fail"}
    mismatch = MarkdownTool().run(guide, example_expected=fail, **args)
    assert mismatch["metadata"]["example_repair"]["status"] == "output_mismatch"
    args["candidate_argv"] = ["sh", "-c", "rm -rf ."]
    assert MarkdownTool().run(guide, example_expected=ok, **args)["status"] == "error"
    assert {p: p.read_bytes() for p in before} == before
```

## Remediation reconciliation

Individual report Fix verification indexed by exact ID/line; safe replacements read frozen corrected plan, future behavior checks remain pending. No self-matching grep command copied into plan.

| ID | Substantive correction | Live evidence / exact check | Outcome / gap |
|---|---|---|---|
| Q10-01 | Correct `tests/test_markdown.py` is called "existing" but exists at neither revision; replacement in proposed packet/binding amendments below | report:13848, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-02 | Correct the mandatory check command collects a missing file; replacement in proposed packet/binding amendments below | report:13865, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-03 | Correct the RED test codifies "skipped engine = assessed" and drops `selected_paths`; replacement in proposed packet/binding amendments below | report:13880, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-04 | Correct E1 metadata conflicts with the phase-70 T16 scope and engine-evidence contract; replacement in proposed packet/binding amendments below | report:13891, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-05 | Correct CLI option forwarding is unowned and misdesigned for phase-70, and two flags are listed as new; replacement in proposed packet/binding amendments below | report:13918, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-06 | Correct a string `"false"` grants build and slow (CORRECTED); replacement in proposed packet/binding amendments below | report:13936, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-07 | Correct agent-controlled `runtime_path` gives unisolated host execution; replacement in proposed packet/binding amendments below | report:13969, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-08 | Correct the W18 interface is restated wrongly; replacement in proposed packet/binding amendments below | report:13986, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-09 | Correct the audit's executable-shape restriction is dropped (descope); replacement in proposed packet/binding amendments below | report:14005, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-10 | Correct status vocabulary drifts from the audit; replacement in proposed packet/binding amendments below | report:14020, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-11 | Correct test names and fixtures drift across tasks, bodies and audit commands; replacement in proposed packet/binding amendments below | report:14058, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-12 | Correct task 4, no-target and option-transport cases have no runnable bodies; replacement in proposed packet/binding amendments below | report:14099, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-13 | Correct the RED evidence rule is contradictory and partly unobtainable; replacement in proposed packet/binding amendments below | report:14106, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-14 | Correct no GREEN production code, helper names diverge, `run` signature undefined; replacement in proposed packet/binding amendments below | report:14121, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-15 | Correct example extraction misses the repo's own examples; replacement in proposed packet/binding amendments below | report:14136, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-16 | Correct Rush image provenance and "compatible current source identity" are undefined; replacement in proposed packet/binding amendments below | report:14164, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-17 | Correct text pasted from other plans; replacement in proposed packet/binding amendments below | report:14190, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-18 | Correct the parity body passes zero new options and compares nonexistent keys; replacement in proposed packet/binding amendments below | report:14198, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-19 | Correct containment root and relative-path resolution undefined (CORRECTED); replacement in proposed packet/binding amendments below | report:14206, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-20 | Correct docs work is a malformed token and 14 doc pages are unscheduled; replacement in proposed packet/binding amendments below | report:14225, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-21 | Correct the connected-specialist candidate provenance is dropped (descope); replacement in proposed packet/binding amendments below | report:14266, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-22 | Correct task-template non-conformance; replacement in proposed packet/binding amendments below | report:14279, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-23 | Correct checks omit mypy, the full suite and the existing adapter tests; replacement in proposed packet/binding amendments below | report:14301, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-24 | Correct undefined shorthand and abbreviated paths; replacement in proposed packet/binding amendments below | report:14312, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-25 | Correct the binding audit is not present at the cited revisions; replacement in proposed packet/binding amendments below | report:14320, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q10-26 | Correct the lazy import of `rush.cli` is required but unstated; replacement in proposed packet/binding amendments below | report:14327, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |

## Checks to run before reporting

Frozen-document checks now; future narrow behavior gates below. Full suite future final implementation only.

## Completion

All numbered/M/X/C scope reconciled; behavior acceptance pending implementation and decisions. No report probe pass adopted.

## Binding amendments, decisions and same-packet docs

Q10-P1 preserves MarkdownlintEngine parser/config flags, canonical engine version/raw/findings/scope. No-target scope none/no_supported_targets, assessed_paths empty when skipped/error; explicit selected files counted once, config/ignore separate. Foundation _entry_scope owns correction excluding --config/--ignore-path values from consumed-source count; controller scope above must merge canonical engine scope and avoid replacing its unavailable reason with none.

Q10-X1 `_execute_candidate` uses Foundation F4 IsolatedRun, no local runtime validator. Runtime is absolute outside root/target/dir validated by provider; callback and MCP cwd list exclude runtime_path. F4 check_isolation_inputs performs no launch; platform/runtime precedence before malformed image; supplied runtime path not silently rooted. Shared image entrypoint verified fixed, not model input. Provider missing => skipped/isolation_unavailable; malformed candidate/image => error metadata.error.code invalid_argument; containment => path_escape. F3 denied repair returns whole-call skipped + execution cause; verify row denied preserves Markdownlint result, execution_status denied + execution_reason build_or_slow_denied.

DECISION REQUIRED Q10-D1: accept candidate process exit0 only (audit) or accept0/1 when ToolResult matches declared expected tool/status (complete proposed code variant). Alternative exact line `if process.returncode != 0:` replaces `if process.returncode not in (0,1):`. Q10-D2: preserve prompt/uv prefix (proposal) or replace whole line (audit); alternative exact line `updated[repair_example-1]=shlex.join(candidate_argv)+ending`. Q10-D3 runtime acceptance and Q10-D4 image ownership/recipe map README D10/D11; alternatives preserve full real isolation/current-source provenance. No choice approved.

Image provenance required before example acceptance: `image inspect` labels org.opencontainers.image.revision equals applied Rush snapshot, verified entrypoint /usr/local/bin/rush and Python, installed Rush same source revision, pinned ruff 0.16.3 and pytest match pyproject.locked versions. Foundation owns exact image build recipe/version assertion script after D11 ratification; do not claim arbitrary digest implies source identity. Recipe builds only explicitly before runtime gate; runtime never pulls. Fixture root inside resolved Markdown directory (path if directory else parent); relative CLI/MCP fixture inputs anchor invocation cwd then physical containment checks. Candidate writes only proposed unified patch, digest-bound stale-source check, source unchanged. Connected specialist may supply candidate argv/expected output only with provenance model_id/artifact_id/candidate_digest/provider_receipt; never silently accept unconnected inference as specialist provenance.

Q10-M1–M5: source counts vs config args Foundation; command names/readme choices retained; dirty AGENTS precedence inspected, user binding controls this remediation; decisions no defaults; actual audit test names all declared in complete test module. X01–X18/C01–C29 applicable template/base/schema/grants/runtime/doc/parity/no-skip fixes retained. tests/test_markdown.py includes 15 functions (report added prefix/string-grant/live cases); required audit aliases test_selected_paths_and_config, test_verify_examples_opt_in, test_example_signature_mismatch, test_stale_example_repair_runs_only_rush_command remain distinct. Live test marked oci_isolation; absent runtime deselects, never skip. Supplied runtime/image absent or bad fails real OCI gate. Test provider uses actual no-launch preflight; controller fake cannot prove OCI.

Foundation serialized Q10-DOC rows: docs/reference/cli-reference.md, docs/reference/mcp-tool-reference.md, docs/reference/result-reference.md, docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/JSON_SCHEMA.md, docs/TOOL_CATALOG.md, docs/reference/engine-directory.md, docs/ENGINES.md, docs/ENGINE_COMPATIBILITY.md, docs/CLI_COOKBOOK.md, docs/user-guide/checking-project-files.md, docs/user-guide/checking-code.md, docs/user-guide/understanding-results.md, docs/permissions.md, docs/adr/0057-documentation-example-verification-in-oci.md new, docs/adr/README.md, CHANGELOG.md, docs/reports/phase-64-66-documentation-coverage.md. Remove false link-integrity/Lychee/Vale/Alex/No-Jargon claims; describe actual markdownlint plus opt-in shell signature/permission-isolated execution and specialist candidate provenance. Historical ADR body remains unchanged; leading current-status only FoundationF8. No invented docs/tools/markdown.md.

Future Command A NOT RUN (prerequisites applied Q10/F1/F2/F6 new tests):

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_markdown.py tests/test_content_infra_tools.py tests/test_transport_parity.py tests/test_cli_registry.py tests/test_mcp.py tests/test_markdownlint_reference.py tests/test_markdown_unfluff_reference.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk git diff --check
```

Future Command B NOT RUN (only after F4/F5 + image/runtime decisions implemented):

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_isolated_process.py tests/test_isolated_tests.py tests/test_markdown.py -m oci_isolation -q
```

Expected structural/local controller gate: all selected local tests pass, live OCI deselected by existing marker when absent. No fixed prior 12pass/1BLOCKED count adopted. Real OCI selection must execute and pass, zero skipped; source/fixture bytes hash unchanged after candidate.
