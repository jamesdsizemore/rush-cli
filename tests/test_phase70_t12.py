"""Phase 70 T12 -- scope typechecking without concealing dependency failures.

Binding design: .scratch/phase-70-design-gate/W2-T9-T17.md section "## T12",
including "S12.6 tsc algorithm (full)" (A0-A15b), the T12 items of
"## W2 adversarial review -- verified" (X2 and the 8 T12 amendments) and the
owner's finding-9 resolution (pyrefly is required and runs for real).
Plan packet: docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md
"#### T12 -- Scope typechecking without concealing dependency failures".

Every engine here is real: mypy 2.3.1 and pyrefly 1.3.1 (dev extra) and the
trusted tsc 7.0.2. Expected tsc results are the A15 rows, which came from
the probed prototype and equal the control `tsc -p <owner>` runs.

Every tsc fixture declares its root with an empty regular `rush.toml`
(OR-13), and every tsc case except the denial case grants cache-write.

Zero-spawn assertions use the finding-26 spy: `subprocess.Popen.__init__`
and `subprocess.run` are both patched, children are counted once at
`Popen.__init__`, and each such test has a granted positive control.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from rush.engines.base import EngineResult
from rush.engines.pyrefly import PyreflyEngine
from rush.engines.tsc import TscEngine
from rush.tools.typecheck import TypecheckTool

pytestmark = pytest.mark.needs_mypy

Spawn = tuple[list[str], str | None]


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _tsc_root(root: Path, files: dict[str, str]) -> Path:
    """OR-13: an empty regular `rush.toml` declares the fixture root."""
    root.mkdir(parents=True, exist_ok=True)
    _write_tree(root, {"rush.toml": "", **files})
    return root.resolve()


def _run_typecheck(path: Path, **kwargs: Any) -> Any:
    return TypecheckTool().run(path, **kwargs)


def _tsc(path: Path, **kwargs: Any) -> Any:
    return TypecheckTool().run(path, allow_cache_write=True, **kwargs)


def _spawn_spy(monkeypatch: pytest.MonkeyPatch) -> list[Spawn]:
    """Finding 26: count every child once, at `Popen.__init__` (which
    `subprocess.run` also goes through); record argv and cwd."""
    calls: list[Spawn] = []
    real_init = subprocess.Popen.__init__
    real_run = subprocess.run

    def init(self: Any, args: Any, *rest: Any, **kwargs: Any) -> None:
        argv = (
            [str(a) for a in args] if isinstance(args, (list, tuple)) else [str(args)]
        )
        cwd = kwargs.get("cwd")
        calls.append((argv, None if cwd is None else str(cwd)))
        real_init(self, args, *rest, **kwargs)

    def run(*args: Any, **kwargs: Any) -> Any:
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", init)
    monkeypatch.setattr(subprocess, "run", run)
    return calls


def _engine_calls(
    calls: list[Spawn], name: str, *, include_version: bool = False
) -> list[Spawn]:
    """`name`'s spawns; by default without the `--version` and `--help`
    capability probes (T11's pyrefly `check --help` gate)."""
    return [
        (argv, cwd)
        for argv, cwd in calls
        if Path(argv[0]).name == name
        and (include_version or not {"--version", "--help"} & set(argv))
    ]


def _tree_bytes(root: Path, *, skip: tuple[str, ...] = ()) -> dict[str, bytes | None]:
    snapshot: dict[str, bytes | None] = {}
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in skip):
            continue
        snapshot[rel] = item.read_bytes() if item.is_file() else None
    return snapshot


def _findings(result: Any, root: Path) -> list[tuple[Any, ...]]:
    """(relative path or None, line, column, rule, scope) per finding."""
    rows = []
    for finding in result["findings"]:
        path = finding.get("path")
        rel = None if path is None else os.path.relpath(path, root)
        rows.append(
            (
                rel,
                finding.get("line"),
                finding.get("column"),
                finding["rule"],
                finding["extensions"]["scope"],
            )
        )
    return sorted(rows, key=repr)


def _scope(result: Any) -> Any:
    return result["metadata"]["scope"]


def _error(result: Any) -> Any:
    return result["metadata"]["error"]


# ---------------------------------------------------------------------------
# Group 1 -- Python, real mypy and real pyrefly.
# ---------------------------------------------------------------------------


def test_t12_typecheck_requested_and_dependency_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief-named anchor test (S12.1, S12.2, S12.3, design steps 1-2).

    Requested `a.py` imports `dep.py`, which has an error; unrelated `c.py`
    has an error. Exact findings for both real Python engines: mypy reports
    a's own error (`requested`) and dep's (`dependency`), pyrefly reports
    a's; nothing from `c.py`. Every path is absolute, every cwd is the
    owning-config directory, and the owning config is passed explicitly.
    """
    root = tmp_path.resolve()
    _write_tree(
        root,
        {
            "pyproject.toml": "[tool.mypy]\n\n[tool.pyrefly]\n",
            "a.py": "from dep import f\nf()\ndef g() -> int:\n    return 'bad'\n",
            "dep.py": "def f() -> int:\n    return 'oops'\n",
            "c.py": "def unrelated() -> int:\n    return 'also-bad'\n",
        },
    )
    calls = _spawn_spy(monkeypatch)

    result = _run_typecheck(root / "a.py")

    rows = sorted(
        (
            f["provenance"],
            f["path"],
            f["line"],
            f["rule"],
            f["extensions"]["scope"],
        )
        for f in result["findings"]
    )
    assert rows == [
        ("typecheck/mypy", str(root / "a.py"), 4, "return-value", "requested"),
        ("typecheck/mypy", str(root / "dep.py"), 2, "return-value", "dependency"),
        (
            "typecheck/pyrefly",
            str(root / "a.py"),
            4,
            "pyrefly/bad-return",
            "requested",
        ),
    ]
    assert result["status"] == "fail"
    mypy_calls = _engine_calls(calls, "mypy")
    pyrefly_checks = [
        (argv, cwd) for argv, cwd in _engine_calls(calls, "pyrefly") if "check" in argv
    ]
    assert [cwd for _, cwd in mypy_calls] == [str(root)]
    assert [cwd for _, cwd in pyrefly_checks] == [str(root)]
    mypy_argv = mypy_calls[0][0]
    assert mypy_argv[-1] == str(root / "a.py")
    at = mypy_argv.index("--config-file")
    assert mypy_argv[at : at + 2] == ["--config-file", str(root / "pyproject.toml")]
    pyrefly_argv = pyrefly_checks[0][0]
    assert pyrefly_argv[-1] == str(root / "a.py")
    assert str(root) not in pyrefly_argv, "no directory argument next to explicit files"
    at = pyrefly_argv.index("--config")
    assert pyrefly_argv[at : at + 2] == ["--config", str(root / "pyproject.toml")]
    scope = _scope(result)
    assert scope["dependency_files"] == [str(root / "dep.py")]
    assert scope["requested_targets"] == [str(root / "a.py")]


def test_t12_mypy_no_stray_cache_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R12.1/S12.4: mypy runs with `--cache-dir=<os.devnull>`; neither the
    process cwd nor the project gains any durable state (no `.mypy_cache`,
    nothing from pyrefly either)."""
    _write_tree(tmp_path, {"proj/a.py": "def f() -> int:\n    return 1\n"})
    isolated_cwd = tmp_path / "elsewhere"
    isolated_cwd.mkdir()
    monkeypatch.chdir(isolated_cwd)
    before = _tree_bytes(tmp_path)
    calls = _spawn_spy(monkeypatch)

    result = _run_typecheck(tmp_path / "proj" / "a.py")

    assert result["status"] == "ok"
    assert _tree_bytes(tmp_path) == before
    assert not (isolated_cwd / ".mypy_cache").exists()
    assert not (tmp_path / "proj" / ".mypy_cache").exists()
    mypy_argv = _engine_calls(calls, "mypy")[0][0]
    assert f"--cache-dir={os.devnull}" in mypy_argv


@pytest.mark.parametrize(
    ("config_name", "config_text"),
    [
        (
            "pyproject.toml",
            "[tool.mypy]\nplugins = ['rush_test_nonexistent_plugin']\n",
        ),
        ("mypy.ini", "[mypy]\nplugins = rush_test_nonexistent_plugin\n"),
        ("setup.cfg", "[mypy]\nplugins = rush_test_nonexistent_plugin\n"),
    ],
)
def test_t12_mypy_plugin_requires_allow_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_name: str,
    config_text: str,
) -> None:
    """S12.5/R12.2: an owning mypy config declaring `plugins` needs
    `allow_build`; without it the mypy child is skipped with the exact
    build reason and mypy is never spawned (pyrefly still runs: it is a
    separate required child). Granted positive control: mypy spawns."""
    _write_tree(
        tmp_path,
        {config_name: config_text, "a.py": "def f() -> int:\n    return 1\n"},
    )
    calls = _spawn_spy(monkeypatch)

    denied = _run_typecheck(tmp_path / "a.py")

    assert _engine_calls(calls, "mypy", include_version=True) == []
    assert (
        "mypy: skipped: requires permission: --allow-build "
        "(project mypy plugins execute code)"
    ) in denied["summary"]
    assert _engine_calls(calls, "pyrefly"), "pyrefly child still runs"
    # Finding 9 (owner): every engine a tool runs is required, so a skipped
    # mypy next to an ok pyrefly never reads as clean. T16 pins the exact
    # precedence value (plan §3.2: mixed ok+skipped is promoted to warn).
    assert denied["status"] != "ok"

    calls.clear()
    _run_typecheck(tmp_path / "a.py", allow_build=True)
    assert _engine_calls(calls, "mypy"), "granted control must spawn mypy"


@pytest.mark.parametrize(
    ("config_name", "config_text"),
    [
        ("pyrefly.toml", 'python-interpreter-path = "/bin/sh"\n'),
        ("pyrefly.toml", 'python-interpreter-find-command = ["/bin/sh"]\n'),
        ("pyrefly.toml", 'fallback-python-interpreter-name = "python9"\n'),
        ("pyrefly.toml", 'conda-environment = "base"\n'),
        (
            "pyproject.toml",
            '[tool.pyrefly]\npython-interpreter-path = "/bin/sh"\n',
        ),
    ],
)
def test_t12_pyrefly_program_executing_config_requires_allow_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_name: str,
    config_text: str,
) -> None:
    """Finding 25: each pyrefly config key that makes pyrefly execute a
    program needs `allow_build`; without it the pyrefly child is skipped
    with the exact reason and pyrefly is never spawned (not even its
    version/help probes). The aggregate is not `ok` (finding 9; T16 pins
    the precedence value). Granted positive control: pyrefly spawns."""
    _write_tree(
        tmp_path,
        {config_name: config_text, "a.py": "def f() -> int:\n    return 1\n"},
    )
    calls = _spawn_spy(monkeypatch)

    denied = _run_typecheck(tmp_path / "a.py")

    assert _engine_calls(calls, "pyrefly", include_version=True) == []
    assert (
        "pyrefly: skipped: requires permission: --allow-build "
        "(project pyrefly interpreter config executes a program)"
    ) in denied["summary"]
    assert _engine_calls(calls, "mypy"), "mypy child still runs"
    assert denied["status"] != "ok"

    calls.clear()
    _run_typecheck(tmp_path / "a.py", allow_build=True)
    assert _engine_calls(calls, "pyrefly", include_version=True), (
        "granted control must spawn pyrefly"
    )


def test_t12_staged_bytes_reflect_staged_content(tmp_path: Path) -> None:
    """Keep-green guard: typecheck analyzes the staged copy, never bytes
    mutated on the live tree after staging closed over them."""
    from rush.engines.staging import stage_inventory, staging_scope

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def f() -> int:\n    return 1\n", encoding="utf-8")

    staged_root = tmp_path / "staged"
    staging = stage_inventory(root, staged_root, ["a.py"])
    with staging_scope(staging):
        (root / "a.py").write_text(
            "def f() -> int:\n    return 'bad'\n", encoding="utf-8"
        )
        result = _run_typecheck(root / "a.py")

    assert result["status"] == "ok", (
        "must reflect the staged (clean) bytes, not the live post-staging mutation"
    )


# ---------------------------------------------------------------------------
# Group 2 -- pyrefly, the real binary (finding 9: required, never faked).
# ---------------------------------------------------------------------------


def test_t12_pyrefly_cwd_is_directory_never_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """S12.1: with an explicit file and no cwd, real pyrefly runs with the
    file's directory as cwd (never the file: `NotADirectoryError` today),
    the file as its only target, and reports an absolute finding path."""
    root = tmp_path.resolve()
    _write_tree(root, {"pyrefly.toml": "", "a.py": 'x: int = "s"\n'})
    calls = _spawn_spy(monkeypatch)
    engine = PyreflyEngine()

    raw = engine.run(root / "a.py", [], cwd=None)
    result = engine.normalize(raw, root / "a.py", "typecheck")

    check = [
        (argv, cwd) for argv, cwd in _engine_calls(calls, "pyrefly") if "check" in argv
    ]
    assert [cwd for _, cwd in check] == [str(root)]
    assert check[0][0][-1] == str(root / "a.py")
    assert [(f["path"], f["line"], f["rule"]) for f in result["findings"]] == [
        (str(root / "a.py"), 1, "pyrefly/bad-assignment")
    ]


def test_t12_pyrefly_argv_no_directory_arg_when_explicit_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """S12.1: argv is `[...defaults, *absolute requested files]` only -- no
    directory argument after explicit targets, so the real pyrefly never
    reports the unrelated erroneous sibling."""
    from rush.tools.common import resolve_binary

    root = tmp_path.resolve()
    _write_tree(
        root,
        {
            "pyrefly.toml": "",
            "a.py": "x = 1\n",
            "c.py": 'y: int = "sibling"\n',
        },
    )
    calls = _spawn_spy(monkeypatch)
    engine = PyreflyEngine()

    raw = engine.run(root, [str(root / "a.py")], cwd=root)
    result = engine.normalize(raw, root, "typecheck")

    check = [argv for argv, _ in _engine_calls(calls, "pyrefly") if "check" in argv]
    assert check == [
        [
            str(resolve_binary("pyrefly")),
            "check",
            "--output-format=json",
            str(root / "a.py"),
        ]
    ]
    assert result["findings"] == []
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Group 3 -- tsc output parsing and classification (unit level, A10/A11).
# ---------------------------------------------------------------------------


def test_t12_tsc_absolute_finding_paths(tmp_path: Path) -> None:
    """S12.3: tsc prints cwd-relative paths (`src/a.ts(2,14)`); normalize
    joins them with the engine cwd."""
    engine = TscEngine()
    raw: EngineResult = {
        "exit_code": 2,
        "stdout": "src/a.ts(2,14): error TS2322: Type 'string' is not assignable to type 'number'.\n",
        "stderr": "",
    }
    result = engine.normalize(raw, tmp_path, "typecheck")
    assert [(f["path"], f["line"], f["column"]) for f in result["findings"]] == [
        (str(tmp_path / "src" / "a.ts"), 2, 14)
    ]


def test_t12_tsc_normalize_joins_recorded_cwd(tmp_path: Path) -> None:
    """Finding 10: the engine result records the cwd tsc actually ran in,
    and normalize joins relative paths with it, not with the run path."""
    owner = tmp_path / "owner"
    raw: EngineResult = {
        "exit_code": 2,
        "stdout": "src/a.ts(1,1): error TS2322: Type 'string' is not assignable to type 'number'.\n",
        "stderr": "",
        "cwd": str(owner),
    }
    result = TscEngine().normalize(raw, tmp_path / "elsewhere", "typecheck")
    assert result["findings"][0]["path"] == str(owner / "src" / "a.ts")


def test_t12_tsc_run_records_cwd_and_tsc_in_engine_result(tmp_path: Path) -> None:
    """Finding 10/A13: `TscEngine.run` returns `cwd` (the first group's
    owner directory) and `tsc` as engine-result fields."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "pkg/tsconfig.json": json.dumps({"include": ["src"]}),
            "pkg/src/a.ts": "export const x = 1;\n",
        },
    )

    raw = TscEngine().run(root / "pkg" / "src" / "a.ts", [])

    assert raw["cwd"] == str(root / "pkg")
    assert raw["tsc"]["groups"][0]["cwd"] == str(root / "pkg")
    assert raw.get("parsed") is None


def test_t12_tsc_dependency_scope_extensions(tmp_path: Path) -> None:
    """S12.2: a diagnostic in a non-requested source file is kept and
    classified `extensions.scope == "dependency"`."""
    engine = TscEngine()
    raw: EngineResult = {
        "exit_code": 2,
        "stdout": "src/dep.ts(1,1): error TS2322: Type 'string' is not assignable to type 'number'.\n",
        "stderr": "",
    }
    result = engine.normalize(raw, tmp_path, "typecheck")
    finding = result["findings"][0]
    assert finding["extensions"]["scope"] == "dependency"
    assert result["status"] == "fail"


def test_t12_tsc_missing_reference_is_configuration_scope(tmp_path: Path) -> None:
    """A11/OR-15: TS6305 (unbuilt reference) is `configuration`, and a
    configuration diagnostic makes the result `error`
    (TSC_CONFIG_DIAGNOSTICS), never clean."""
    engine = TscEngine()
    raw: EngineResult = {
        "exit_code": 1,
        "stdout": (
            "index.ts(1,19): error TS6305: Output file "
            "'/proj/pkgA/dist/index.d.ts' has not been built from source "
            "file '/proj/pkgA/index.ts'.\n"
        ),
        "stderr": "",
    }
    result = engine.normalize(raw, tmp_path, "typecheck")
    assert result["findings"][0]["extensions"]["scope"] == "configuration"
    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_CONFIG_DIAGNOSTICS"


def test_t12_tsc_unicode_path_absolute_and_intact(tmp_path: Path) -> None:
    """S12.3: Unicode path bytes survive normalization exactly."""
    engine = TscEngine()
    raw: EngineResult = {
        "exit_code": 2,
        "stdout": "café/a.ts(1,14): error TS2322: Type 'string' is not assignable to type 'number'.\n",
        "stderr": "",
    }
    result = engine.normalize(raw, tmp_path, "typecheck")
    assert result["findings"][0]["path"] == str(tmp_path / "café" / "a.ts")


def test_t12_tsc_parse_output_newline_paths_and_continuations(
    tmp_path: Path,
) -> None:
    """A10/E12: a newline inside a path splits the diagnostic head and the
    listFiles line; both are reassembled against the filesystem. Indented
    continuation lines join the open diagnostic; a GLOBAL line is
    path-less; anything else is unparsed."""
    weird = tmp_path / "a\nb"
    weird.mkdir()
    (weird / "c.ts").write_text("export const x = 1;\n", encoding="utf-8")
    text = (
        "a\nb/c.ts(1,14): error TS2322: Type 'string' is not assignable to type 'number'.\n"
        "  The file is in the program because:\n"
        "error TS5023: Unknown compiler option 'x'.\n"
        f"{tmp_path}/a\nb/c.ts\n"
        "garbage line\n"
    )

    from rush.engines.tsc import parse_tsc_output

    parsed = parse_tsc_output(text, tmp_path)

    assert [
        (
            d.get("path"),
            d.get("line"),
            d.get("column"),
            d["rule"],
            d["message"],
        )
        for d in parsed.diagnostics
    ] == [
        (
            str(weird / "c.ts"),
            1,
            14,
            "TS2322",
            (
                "Type 'string' is not assignable to type 'number'.\n"
                "  The file is in the program because:"
            ),
        ),
        (None, None, None, "TS5023", "Unknown compiler option 'x'."),
    ]
    assert parsed.consumed == [str(weird / "c.ts")]
    assert parsed.unparsed == ["garbage line"]
    assert parsed.listfiles_seen is True
    assert parsed.truncated is False


def test_t12_tsc_parse_output_truncation(tmp_path: Path) -> None:
    """A10/OR-16: a `[TRUNCATED]` tail drops the partial last line;
    before any consumed-file line it is TSC_OUTPUT_TRUNCATED."""
    text = "a.ts(1,1): error TS2304: Cannot find name 'x'.\nb.ts(1,[TRUNCATED]"
    from rush.engines.tsc import parse_tsc_output

    parsed = parse_tsc_output(text, tmp_path)
    assert parsed.truncated is True
    assert parsed.listfiles_seen is False
    assert [d["rule"] for d in parsed.diagnostics] == ["TS2304"]
    assert parsed.unparsed == []
    result = TscEngine().normalize(
        {"exit_code": 2, "stdout": text, "stderr": ""}, tmp_path, "typecheck"
    )
    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_OUTPUT_TRUNCATED"


# ---------------------------------------------------------------------------
# Group 4 -- owning configuration, scoped config and classification, run
# against real tsc 7.0.2 (A15 rows, X2 corrected).
# ---------------------------------------------------------------------------

_NO_UNUSED = "const unused = 1;\nexport {};\n"
_UNUSED_MSG = "'unused' is declared but its value is never read."
_CUSTOM_TYPES = "declare const CUSTOM_FLAG: boolean;\n"
_REACT_RUNTIME = (
    "export namespace JSX { interface IntrinsicElements { [name: string]: any } "
    "interface Element {} }\nexport function jsx(...a: any[]): any;\n"
    "export function jsxs(...a: any[]): any;\n"
)

# name -> (files, target, status, findings, dependency_files, ambient_files);
# None means the list is not part of that A15 row.
_ScopedCase = tuple[
    dict[str, str], str, str, list[tuple[Any, ...]], list[str] | None, list[str] | None
]
_SCOPED_CASES: dict[str, _ScopedCase] = {
    "inherited_option_via_extends": (
        {
            "base.tsconfig.json": json.dumps(
                {"compilerOptions": {"noUnusedLocals": True}}
            ),
            "tsconfig.json": json.dumps(
                {"extends": "./base.tsconfig.json", "include": ["a.ts"]}
            ),
            "a.ts": _NO_UNUSED,
        },
        "a.ts",
        "fail",
        [("a.ts", 1, 7, "TS6133", "requested")],
        [],
        None,
    ),
    "inherited_paths": (
        {
            "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {"paths": {"@lib/*": ["./libs/*"]}},
                    "include": ["a.ts", "libs/*.ts"],
                }
            ),
            "libs/thing.ts": "export const val = 1;\n",
            "a.ts": 'import { val } from "@lib/thing";\nexport const x = val;\n',
        },
        "a.ts",
        "ok",
        [],
        ["libs/thing.ts"],
        [],
    ),
    "inherited_types": (
        {
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"types": ["custom"]}, "include": ["a.ts"]}
            ),
            "node_modules/@types/custom/index.d.ts": _CUSTOM_TYPES,
            "a.ts": "export const f = () => CUSTOM_FLAG;\n",
        },
        "a.ts",
        "ok",
        [],
        ["node_modules/@types/custom/index.d.ts"],
        [],
    ),
    "explicit_type_roots": (
        {
            "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {"typeRoots": ["./types"], "types": ["foo"]},
                    "include": ["src"],
                }
            ),
            "types/foo/index.d.ts": "declare namespace Foo { interface Bar { x: number } }\n",
            "src/a.ts": "export const b: Foo.Bar = { x: 1 };\n",
        },
        "src/a.ts",
        "ok",
        [],
        ["types/foo/index.d.ts"],
        None,
    ),
    "default_type_roots": (
        {
            "node_modules/@types/custom/index.d.ts": _CUSTOM_TYPES,
            "packages/a/tsconfig.json": json.dumps(
                {"compilerOptions": {"types": ["custom"]}}
            ),
            "packages/a/a.ts": "export const f = () => CUSTOM_FLAG;\n",
        },
        "packages/a/a.ts",
        "ok",
        [],
        ["node_modules/@types/custom/index.d.ts"],
        None,
    ),
    "module_detection_auto": (
        {
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"moduleDetection": "auto"}}
            ),
            "globals.ts": "var MY_FLAG: boolean;\n",
            "consumer.ts": "export const f = () => MY_FLAG;\n",
        },
        "consumer.ts",
        "ok",
        [],
        ["globals.ts"],
        ["globals.ts"],
    ),
    "module_detection_force": (
        {
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"moduleDetection": "force"}}
            ),
            "globals.ts": "var MY_FLAG: boolean;\n",
            "consumer.ts": "export const f = () => MY_FLAG;\n",
        },
        "consumer.ts",
        "fail",
        [("consumer.ts", 1, 24, "TS2304", "requested")],
        [],
        [],
    ),
    "module_detection_legacy_import_meta": (
        {
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"moduleDetection": "legacy", "module": "esnext"}}
            ),
            "meta.ts": "const u = import.meta.url;\nvar META_G: number;\n",
            "c2.ts": "export const g = () => META_G;\n",
        },
        "c2.ts",
        "fail",
        [("c2.ts", 1, 24, "TS2304", "requested")],
        [],
        [],
    ),
    "package_type_module": (
        {
            "package.json": json.dumps({"type": "module"}),
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"module": "nodenext", "moduleDetection": "auto"}}
            ),
            "g.ts": "var PKG_G: number;\n",
            "c.ts": "export const g = () => PKG_G;\n",
        },
        "c.ts",
        "fail",
        [("c.ts", 1, 24, "TS2304", "requested")],
        [],
        [],
    ),
    "package_type_commonjs": (
        {
            "package.json": json.dumps({"type": "commonjs"}),
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"module": "nodenext", "moduleDetection": "auto"}}
            ),
            "g.ts": "var PKG_G: number;\n",
            "c.ts": "export const g = () => PKG_G;\n",
        },
        "c.ts",
        "ok",
        [],
        ["g.ts"],
        ["g.ts"],
    ),
    "tsx_automatic_jsx": (
        {
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"jsx": "react-jsx"}, "include": ["a.tsx"]}
            ),
            "node_modules/react/package.json": json.dumps(
                {"name": "react", "version": "18.0.0"}
            ),
            "node_modules/react/jsx-runtime.d.ts": _REACT_RUNTIME,
            "a.tsx": "export const A = () => <div/>;\n",
        },
        "a.tsx",
        "ok",
        [],
        ["node_modules/react/jsx-runtime.d.ts"],
        [],
    ),
    "solution_packages_ab_deepest_owner": (
        {
            "packages/a/tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "strict": True,
                        "composite": True,
                        "outDir": "dist",
                    },
                    "include": ["*.ts"],
                }
            ),
            "packages/a/index.ts": "export function f(y) { return y; }\n",
            "packages/b/tsconfig.json": json.dumps(
                {
                    "compilerOptions": {"composite": True, "outDir": "dist"},
                    "references": [{"path": "../a"}],
                    "include": ["*.ts"],
                }
            ),
            "packages/b/index.ts": 'import { f } from "../a";\nexport const g = f(1);\n',
            "tsconfig.json": json.dumps(
                {"references": [{"path": "packages/a"}, {"path": "packages/b"}]}
            ),
        },
        "packages/a/index.ts",
        "fail",
        [("packages/a/index.ts", 1, 19, "TS7006", "requested")],
        [],
        None,
    ),
    "solution_deepest_owner": (
        {
            "tsconfig.json": json.dumps(
                {
                    "files": [],
                    "references": [
                        {"path": "./tsconfig.all.json"},
                        {"path": "./src/lib/tsconfig.lib.json"},
                    ],
                }
            ),
            "tsconfig.all.json": json.dumps(
                {"compilerOptions": {"composite": True}, "include": ["src/**/*.ts"]}
            ),
            "src/lib/tsconfig.lib.json": json.dumps(
                {
                    "compilerOptions": {"composite": True, "noUnusedLocals": True},
                    "include": ["*.ts"],
                }
            ),
            "src/lib/x.ts": _NO_UNUSED,
        },
        "src/lib/x.ts",
        "fail",
        [("src/lib/x.ts", 1, 7, "TS6133", "requested")],
        [],
        None,
    ),
    "excluded_explicit_file_nearest_non_solution_config": (
        {
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"strict": True}, "exclude": ["generated/**"]}
            ),
            "generated/a.ts": "function f(y) { return y; }\n",
        },
        "generated/a.ts",
        "fail",
        [("generated/a.ts", 1, 12, "TS7006", "requested")],
        [],
        None,
    ),
    "composite_rootdir_buildinfo_containment": (
        {
            "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "composite": True,
                        "outDir": "dist",
                        "rootDir": ".",
                        "types": ["custom"],
                    },
                    "include": ["a.ts"],
                }
            ),
            "node_modules/@types/custom/index.d.ts": _CUSTOM_TYPES,
            "a.ts": "export const f = () => CUSTOM_FLAG;\n",
        },
        "a.ts",
        "ok",
        [],
        ["node_modules/@types/custom/index.d.ts"],
        None,
    ),
    "incremental_explicit_buildinfo": (
        {
            "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "incremental": True,
                        "tsBuildInfoFile": "./cache/x.tsbuildinfo",
                    }
                }
            ),
            "a.ts": "export const a = 1;\n",
        },
        "a.ts",
        "ok",
        [],
        [],
        None,
    ),
}


@pytest.mark.parametrize("case_name", sorted(_SCOPED_CASES))
def test_t12_tsc_scoped_config_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_name: str
) -> None:
    """A15: each fixture's result equals the control `tsc -p <owner>`
    under tsc 7.0.2 (`strict` defaults to true and `types` to `[]`).
    Every case also proves: exactly one analysis spawn, never `-b`,
    never `--listFilesOnly` as the analysis, the project tree outside
    `.rush/` byte-identical, and no `tsc-*` temp residue."""
    files, target, status, findings, dependency, ambient = _SCOPED_CASES[case_name]
    root = _tsc_root(tmp_path / "root", files)
    before = _tree_bytes(root)
    calls = _spawn_spy(monkeypatch)

    result = _tsc(root / target)

    assert result["status"] == status, result["summary"]
    assert _findings(result, root) == sorted(findings, key=repr)
    scope = _scope(result)
    if dependency is not None:
        assert scope["dependency_files"] == [str(root / d) for d in dependency]
    if ambient is not None:
        assert scope["ambient_files"] == [str(root / a) for a in ambient]
    tsc_calls = [argv for argv, _ in _engine_calls(calls, "tsc")]
    analyses = [argv for argv in tsc_calls if "--noEmit" in argv]
    assert len(analyses) == 1
    assert analyses[0][1] == "-p"
    assert analyses[0][3:] == ["--noEmit", "--listFiles", "--pretty", "false"]
    assert not any("-b" in argv or "--build" in argv for argv in tsc_calls)
    assert _tree_bytes(root, skip=(".rush",)) == before
    assert [p.name for p in (root / ".rush" / "tmp").iterdir()] == []
    if case_name == "composite_rootdir_buildinfo_containment":
        assert not (root / "dist").exists()
        assert not (root / "tsconfig.tsbuildinfo").exists()
    if case_name == "incremental_explicit_buildinfo":
        assert not (root / "cache").exists()
    if case_name == "excluded_explicit_file_nearest_non_solution_config":
        assert scope["explicit_override"] is True
    if case_name == "inherited_option_via_extends":
        assert result["findings"][0]["message"] == _UNUSED_MSG
    if case_name == "solution_deepest_owner":
        assert [g["config"] for g in scope["groups"]] == [
            str(root / "src" / "lib" / "tsconfig.lib.json")
        ]


def test_t12_tsc_reference_cycle_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """X2/A15: a reference cycle is TSC_REFERENCE_CYCLE (tsc itself does not
    report it outside build mode, E5); zero findings; no analysis spawn."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "packages/a/tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "composite": True,
                        "outDir": "dist",
                        "types": ["custom"],
                    },
                    "references": [{"path": "../b"}],
                    "include": ["*.ts"],
                }
            ),
            "node_modules/@types/custom/index.d.ts": _CUSTOM_TYPES,
            "packages/a/index.ts": "export const a = () => CUSTOM_FLAG;\n",
            "packages/b/tsconfig.json": json.dumps(
                {
                    "compilerOptions": {"composite": True, "outDir": "dist"},
                    "references": [{"path": "../a"}],
                    "include": ["*.ts"],
                }
            ),
            "packages/b/index.ts": "export const b = 1;\n",
        },
    )
    calls = _spawn_spy(monkeypatch)

    result = _tsc(root / "packages" / "a" / "index.ts")

    a_cfg = str(root / "packages" / "a" / "tsconfig.json")
    b_cfg = str(root / "packages" / "b" / "tsconfig.json")
    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_REFERENCE_CYCLE"
    assert _error(result)["message"] == (
        f"tsc: project references form a cycle: {a_cfg} -> {b_cfg} -> {a_cfg}"
    )
    assert _error(result)["cycle"] == [a_cfg, b_cfg, a_cfg]
    assert result["findings"] == []
    tsc_calls = [argv for argv, _ in _engine_calls(calls, "tsc")]
    assert tsc_calls
    assert all("--showConfig" in argv for argv in tsc_calls)


def test_t12_tsc_ambiguous_equal_depth_owners_is_error(tmp_path: Path) -> None:
    """X2/A15 (rebuilt as a solution): two equally deep referenced owners
    of the target is TSC_AMBIGUOUS_OWNER; zero findings."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "tsconfig.json": json.dumps(
                {
                    "files": [],
                    "references": [{"path": "packages/a"}, {"path": "packages/b"}],
                }
            ),
            "packages/a/tsconfig.json": json.dumps(
                {
                    "compilerOptions": {"composite": True},
                    "include": ["../../shared/*.ts"],
                }
            ),
            "packages/b/tsconfig.json": json.dumps(
                {
                    "compilerOptions": {"composite": True},
                    "include": ["../../shared/*.ts"],
                }
            ),
            "shared/x.ts": "export const x = 1;\n",
        },
    )

    result = _tsc(root / "shared" / "x.ts")

    a_cfg = str(root / "packages" / "a" / "tsconfig.json")
    b_cfg = str(root / "packages" / "b" / "tsconfig.json")
    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_AMBIGUOUS_OWNER"
    assert _error(result)["message"] == (
        f"tsc: {root / 'shared' / 'x.ts'} is owned by more than one equally deep "
        f"config: {a_cfg}, {b_cfg}; pass --typecheck-config to choose one"
    )
    assert _error(result)["configs"] == [a_cfg, b_cfg]
    assert result["findings"] == []


def test_t12_tsc_malformed_jsonc_config_is_visible_error(tmp_path: Path) -> None:
    """X2/A15/OR-15: malformed JSONC surfaces in the analysis run as a
    `configuration` finding that makes the result error
    (TSC_CONFIG_DIAGNOSTICS); the requested file's own finding is kept."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "tsconfig.json": '{ "compilerOptions": { "strict": true,',
            "node_modules/@types/custom/index.d.ts": _CUSTOM_TYPES,
            "a.ts": "export const f = () => CUSTOM_FLAG;\n",
        },
    )

    result = _tsc(root / "a.ts")

    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_CONFIG_DIAGNOSTICS"
    assert _error(result)["message"] == (
        "tsc: 1 configuration diagnostic(s); first: TS1005 at "
        f"{root / 'tsconfig.json'}:1:39"
    )
    assert _findings(result, root) == [
        ("a.ts", 1, 24, "TS2304", "requested"),
        ("tsconfig.json", 1, 39, "TS1005", "configuration"),
    ]
    messages = {f["rule"]: f["message"] for f in result["findings"]}
    assert messages == {
        "TS1005": "'}' expected.",
        "TS2304": "Cannot find name 'CUSTOM_FLAG'.",
    }


def test_t12_tsc_missing_reference_reported_in_scoped_config(tmp_path: Path) -> None:
    """A15/A11: a missing reference is TSC_CONFIG_DIAGNOSTICS; tsc reports
    TS6053 inside Rush's scoped config, which is attributed to the owner
    config with no line or column and `reported_in="rush_scoped_config"`."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "tsconfig.json": json.dumps(
                {"references": [{"path": "./missing"}], "include": ["a.ts"]}
            ),
            "a.ts": "export const a = 1;\n",
        },
    )

    result = _tsc(root / "a.ts")

    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_CONFIG_DIAGNOSTICS"
    [finding] = result["findings"]
    assert finding["rule"] == "TS6053"
    assert finding["path"] == str(root / "tsconfig.json")
    assert "line" not in finding
    assert "column" not in finding
    assert finding["extensions"]["scope"] == "configuration"
    assert finding["extensions"]["reported_in"] == "rush_scoped_config"


def test_t12_tsc_owner_outside_root_is_error(tmp_path: Path) -> None:
    """Amendment T12 #3: the only owner lies outside the project root."""
    base = tmp_path.resolve()
    _write_tree(
        base,
        {
            "proj/rush.toml": "",
            "proj/tsconfig.json": json.dumps(
                {"files": [], "references": [{"path": "../outside"}]}
            ),
            "outside/tsconfig.json": json.dumps(
                {
                    "compilerOptions": {"composite": True},
                    "include": ["../proj/src/*.ts"],
                }
            ),
            "proj/src/a.ts": "export const a = 1;\n",
        },
    )

    result = _tsc(base / "proj" / "src" / "a.ts")

    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_OWNER_OUTSIDE_ROOT"
    assert _error(result)["message"] == (
        f"tsc: owning config {base / 'outside' / 'tsconfig.json'} lies outside "
        f"the project root {base / 'proj'}"
    )
    assert result["findings"] == []


def test_t12_tsc_solution_only_no_owner_requires_config(tmp_path: Path) -> None:
    """Amendment T12 #2: only a solution config exists and no referenced
    project owns the target -> TYPECHECK_CONFIG_REQUIRED."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "tsconfig.json": json.dumps(
                {"files": [], "references": [{"path": "packages/a"}]}
            ),
            "packages/a/tsconfig.json": json.dumps({"include": ["src"]}),
            "packages/a/src/i.ts": "export const i = 1;\n",
            "tools/x.ts": "export const x = 1;\n",
        },
    )

    result = _tsc(root / "tools" / "x.ts")

    assert result["status"] == "error"
    assert _error(result)["code"] == "TYPECHECK_CONFIG_REQUIRED"
    assert _error(result)["message"] == (
        f"tsc: {root / 'tools' / 'x.ts'} is not owned by any project referenced "
        f"from the solution config {root / 'tsconfig.json'}; pass --typecheck-config"
    )


def test_t12_tsc_cwd_relative_paths_absolutized(tmp_path: Path) -> None:
    """Amendment T12 #5: the owner-directory cwd (`pkg/`) differs from the
    run path; tsc's cwd-relative `src/a.ts(...)` becomes the absolute path."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "pkg/tsconfig.json": json.dumps({"include": ["src"]}),
            "pkg/src/a.ts": "export const x: number = 'bad';\n",
        },
    )

    result = _tsc(root / "pkg" / "src" / "a.ts")

    assert result["status"] == "fail"
    assert _findings(result, root) == [("pkg/src/a.ts", 1, 14, "TS2322", "requested")]
    assert _scope(result)["groups"][0]["cwd"] == str(root / "pkg")


@pytest.mark.parametrize(
    "rel",
    ["café dir/a b .ts", "new\nline.ts"],
    ids=["unicode-whitespace", "newline"],
)
def test_t12_tsc_real_unusual_paths(tmp_path: Path, rel: str) -> None:
    """Packet: newline/Unicode/whitespace paths, through real tsc output."""
    root = _tsc_root(tmp_path / "root", {rel: "export const x: number = 'bad';\n"})

    result = _tsc(root / rel)

    assert result["status"] == "fail"
    assert [
        (f["path"], f["line"], f["column"], f["rule"]) for f in result["findings"]
    ] == [(str(root / rel), 1, 14, "TS2322")]
    assert _scope(result)["consumed_file_count"] == 1


# ---------------------------------------------------------------------------
# Group 5 -- global declarations / ambient scope (no-config mode, A7/A8).
# ---------------------------------------------------------------------------


def test_t12_tsc_ordinary_script_global_not_visible_without_import(
    tmp_path: Path,
) -> None:
    """An ordinary script's globals are shared ambient input: `globals.ts`
    is added as an ambient root and `consumer.ts` is clean."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "globals.ts": "var MY_FLAG: boolean;\n",
            "consumer.ts": "export const f = () => MY_FLAG;\n",
        },
    )

    result = _tsc(root / "consumer.ts")

    assert result["status"] == "ok"
    assert _scope(result)["ambient_files"] == [str(root / "globals.ts")]
    assert _scope(result)["dependency_files"] == [str(root / "globals.ts")]


def test_t12_tsc_declare_global_external_module_scope_metadata(tmp_path: Path) -> None:
    """`declare global` inside an imported external module is dependency
    input (both imported and an ambient root)."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "globals.ts": (
                "export {};\ndeclare global {\n"
                "  interface Window { myFlag: boolean; }\n}\n"
            ),
            "consumer.ts": (
                'import "./globals";\n'
                "declare const window: Window;\n"
                "export const f = () => window.myFlag;\n"
            ),
        },
    )

    result = _tsc(root / "consumer.ts")

    assert result["status"] == "ok"
    assert _scope(result)["dependency_files"] == [str(root / "globals.ts")]


# ---------------------------------------------------------------------------
# Group 6 -- directory scopes (A6).
# ---------------------------------------------------------------------------


def test_t12_tsc_no_unrelated_package_compilation(tmp_path: Path) -> None:
    """A15: two groups -- owner `packages/a/tsconfig.json` (index.ts) and
    no-config (`packages/b/index.ts`, depending on `packages/a/index.ts`);
    `internal.ts` is excluded by its config and never compiled."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "packages/a/tsconfig.json": json.dumps(
                {"include": ["index.ts"], "exclude": ["internal.ts"]}
            ),
            "packages/a/index.ts": "export const a = 1;\n",
            "packages/a/internal.ts": "const bad: number = 'oops';\n",
            "packages/b/index.ts": 'import { a } from "../a/index";\nexport const b = a;\n',
        },
    )

    result = _tsc(root / "packages")

    scope = _scope(result)
    assert result["status"] == "ok"
    assert [g["config"] for g in scope["groups"]] == [
        str(root / "packages" / "a" / "tsconfig.json"),
        None,
    ]
    assert scope["groups"][0]["requested_files"] == [str(root / "packages/a/index.ts")]
    assert scope["groups"][1]["requested_files"] == [str(root / "packages/b/index.ts")]
    assert scope["groups"][1]["dependency_files"] == [str(root / "packages/a/index.ts")]
    assert scope["excluded_files"] == [
        {"path": str(root / "packages/a/internal.ts"), "reason": "excluded_by_config"}
    ]
    assert not any("internal.ts" in (f.get("path") or "") for f in result["findings"])
    assert scope["coverage"] == "partial"


def test_t12_directory_scope_honors_include_exclude(tmp_path: Path) -> None:
    """A15: `scratch/bad.ts` is excluded by the config's `exclude` and its
    real error never appears; `src/a.ts` is analyzed clean."""
    root = _tsc_root(
        tmp_path / "root",
        {
            "tsconfig.json": json.dumps(
                {"compilerOptions": {"strict": True}, "exclude": ["scratch/**"]}
            ),
            "src/a.ts": "export const x = 1;\n",
            "scratch/bad.ts": "function f(y) { return y; }\n",
        },
    )

    result = _tsc(root)

    assert result["status"] == "ok"
    assert result["findings"] == []
    assert _scope(result)["excluded_files"] == [
        {"path": str(root / "scratch/bad.ts"), "reason": "excluded_by_config"}
    ]


# ---------------------------------------------------------------------------
# Group 7 -- unclassifiable syntax and an unavailable parser (A3.2, A8).
# ---------------------------------------------------------------------------


def test_t12_tsc_unclassifiable_syntax_is_explicit_scope_error(tmp_path: Path) -> None:
    """A15: a requested file tree-sitter cannot parse is TSC_UNCLASSIFIABLE
    with no clean claim; tsc's own TS1134 finding is kept (`requested`)."""
    import tree_sitter_typescript
    from tree_sitter import Language, Parser

    src = b"export const = ;\n"
    tree = Parser(Language(tree_sitter_typescript.language_typescript())).parse(src)
    assert tree.root_node.has_error, "fixture must itself be genuinely unparseable"
    root = _tsc_root(tmp_path / "root", {"a.ts": src.decode()})

    result = _tsc(root / "a.ts")

    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_UNCLASSIFIABLE"
    assert _error(result)["message"] == (
        "tsc: could not classify 1 file(s) as module or script (parse_error): "
        f"{root / 'a.ts'}"
    )
    assert _scope(result)["unclassifiable"] is True
    assert _scope(result)["unclassifiable_files"] == [str(root / "a.ts")]
    assert [row for row in _findings(result, root) if row[3] == "TS1134"] == [
        ("a.ts", 1, 14, "TS1134", "requested")
    ]


def test_t12_tsc_unavailable_parser_zero_spawns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A3.2: an unavailable grammar is a run-level TSC_UNCLASSIFIABLE error
    (`reason="parser_unavailable"`) with zero spawns and zero writes."""
    root = _tsc_root(tmp_path / "root", {"a.ts": "export const x = 1;\n"})
    before = _tree_bytes(root)
    monkeypatch.setitem(sys.modules, "tree_sitter_typescript", None)
    calls = _spawn_spy(monkeypatch)

    result = _tsc(root / "a.ts")

    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_UNCLASSIFIABLE"
    assert _error(result)["reason"] == "parser_unavailable"
    assert _error(result)["message"].startswith(
        "tsc: tree-sitter-typescript grammar unavailable: "
    )
    assert _engine_calls(calls, "tsc", include_version=True) == []
    assert _tree_bytes(root) == before


# ---------------------------------------------------------------------------
# Group 8 -- grants and the owned temporary directory (S12.4, finding 27).
# ---------------------------------------------------------------------------


def test_t12_tsc_cache_write_denied_zero_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R12.4: without cache-write the tsc child is skipped before any spawn
    (including `--showConfig` and `--version`) and before any write.
    Granted positive control: the same spy records tsc spawns."""
    root = _tsc_root(tmp_path / "root", {"a.ts": "export const x = 1;\n"})
    before = _tree_bytes(root)
    calls = _spawn_spy(monkeypatch)

    denied = _run_typecheck(root / "a.ts")

    assert calls == []
    assert _tree_bytes(root) == before
    assert denied["status"] == "skipped"
    assert "requires permission: --allow-cache-write" in denied["summary"]

    granted = _tsc(root / "a.ts")
    assert granted["status"] == "ok"
    assert _engine_calls(calls, "tsc"), "granted control must spawn tsc"


@pytest.mark.parametrize("link", [".rush", ".rush/tmp"])
def test_t12_tsc_symlinked_dotrush_is_containment_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link: str
) -> None:
    """Amendment T12 #6 (finding 27): a symlinked `.rush` or `.rush/tmp` is
    TSC_TEMP_CONTAINMENT with zero spawns and nothing written in the
    symlink target."""
    root = _tsc_root(tmp_path / "root", {"a.ts": "export const x = 1;\n"})
    outside = tmp_path / "outside"
    outside.mkdir()
    link_path = root / link
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(outside, target_is_directory=True)
    calls = _spawn_spy(monkeypatch)

    result = _tsc(root / "a.ts")

    assert result["status"] == "error"
    assert _error(result)["code"] == "TSC_TEMP_CONTAINMENT"
    assert _error(result)["message"].startswith(
        "tsc: temporary directory rejected: [SYMLINK_DISALLOWED] "
    )
    assert _engine_calls(calls, "tsc", include_version=True) == []
    assert list(outside.iterdir()) == []


def test_t12_tsc_staged_bytes(tmp_path: Path) -> None:
    """Amendment T12 #4 (finding 10): the scoped config is built from the
    staged tree, so results reflect staged bytes, and findings come back
    as logical absolute paths."""
    from rush.engines.staging import stage_inventory, staging_scope

    root = _tsc_root(
        tmp_path / "root",
        {"tsconfig.json": "{}", "a.ts": "export const x: number = 'bad';\n"},
    )
    staging = stage_inventory(
        root, tmp_path / "staged", ["a.ts", "tsconfig.json", "rush.toml"]
    )
    with staging_scope(staging):
        (root / "a.ts").write_text("export const x: number = 1;\n", encoding="utf-8")
        result = _tsc(root / "a.ts")

    assert result["status"] == "fail"
    assert [
        (f["path"], f["line"], f["column"], f["rule"]) for f in result["findings"]
    ] == [(str(root / "a.ts"), 1, 14, "TS2322")]
    assert result["findings"][0]["extensions"]["scope"] == "requested"
    assert _scope(result)["requested_targets"] == [str(root / "a.ts")]
    assert [p.name for p in (root / ".rush" / "tmp").iterdir()] == []


# ---------------------------------------------------------------------------
# Group 9 -- explicit `--typecheck-config` / MCP `typecheck_config` (S12.7).
# ---------------------------------------------------------------------------


def _loose_fixture(root: Path) -> Path:
    return _tsc_root(
        root,
        {
            "tsconfig.json": "{}",
            "tsconfig.loose.json": json.dumps({"compilerOptions": {"strict": False}}),
            "a.ts": "export function f(y) { return y; }\n",
        },
    )


def test_t12_explicit_typecheck_config_wins_over_auto_detection(
    tmp_path: Path,
) -> None:
    """S12.7/A5.1: auto-detection picks `tsconfig.json` (strict -> TS7006);
    the explicit config wins and the same file is clean."""
    root = _loose_fixture(tmp_path / "root")

    auto = _tsc(root / "a.ts")
    explicit = _tsc(root / "a.ts", typecheck_config=str(root / "tsconfig.loose.json"))

    assert auto["status"] == "fail"
    assert _findings(auto, root) == [("a.ts", 1, 19, "TS7006", "requested")]
    assert explicit["status"] == "ok"
    assert _scope(explicit)["groups"][0]["config"] == str(root / "tsconfig.loose.json")
    assert _scope(explicit)["explicit_override"] is False


def test_t12_typecheck_config_outside_root_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S12.7/R12.5: a config outside the logical root is an error, before
    any spawn."""
    root = _loose_fixture(tmp_path / "root")
    outside = tmp_path / "elsewhere" / "tsconfig.json"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")
    calls = _spawn_spy(monkeypatch)

    result = _tsc(root / "a.ts", typecheck_config=str(outside))

    assert result["status"] == "error"
    assert _error(result)["code"] == "TYPECHECK_CONFIG_OUTSIDE_ROOT"
    assert _error(result)["message"] == (
        f"typecheck: --typecheck-config {outside.resolve()} lies outside the "
        f"project root {root}"
    )
    assert calls == []


@pytest.mark.parametrize(
    "engine_args",
    [["-p", "other.json"], ["--project", "other.json"], ["--config-file=mypy.ini"]],
)
def test_t12_typecheck_config_conflicts_with_freeform_engine_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine_args: list[str]
) -> None:
    """S12.7: freeform engine args (`[tools.typecheck] engine_args` in
    rush.toml) that select a config conflict with the validated explicit
    selection -> TYPECHECK_CONFIG_CONFLICT, zero spawns."""
    root = _loose_fixture(tmp_path / "root")
    (root / "rush.toml").write_text(
        "[tools.typecheck]\nengine_args = " + json.dumps(engine_args) + "\n",
        encoding="utf-8",
    )
    calls = _spawn_spy(monkeypatch)

    result = _tsc(root / "a.ts", typecheck_config=str(root / "tsconfig.loose.json"))

    assert result["status"] == "error"
    assert _error(result)["code"] == "TYPECHECK_CONFIG_CONFLICT"
    assert _error(result)["message"] == (
        f"typecheck: engine_args {engine_args[0]!r} conflicts with "
        f"--typecheck-config {root / 'tsconfig.loose.json'}"
    )
    assert calls == []


def test_t12_typecheck_config_family_checked(tmp_path: Path) -> None:
    """S12.7: a config that belongs to no typecheck engine family is an
    error (R12.5 routes `.json` to tsc and mypy/pyrefly files to Python)."""
    root = _loose_fixture(tmp_path / "root")
    (root / "weird.yaml").write_text("x: 1\n", encoding="utf-8")

    result = _tsc(root / "a.ts", typecheck_config=str(root / "weird.yaml"))

    assert result["status"] == "error"
    assert _error(result)["code"] == "TYPECHECK_CONFIG_INVALID"


def test_t12_typecheck_config_routes_python_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R12.5: a Python-family explicit config reaches mypy as
    `--config-file`, and its directory is mypy's cwd."""
    root = tmp_path.resolve()
    _write_tree(
        root,
        {
            "rush.toml": "",
            "configs/mypy.ini": "[mypy]\n",
            "src/a.py": "x: int = 1\n",
        },
    )
    calls = _spawn_spy(monkeypatch)

    result = _run_typecheck(
        root / "src" / "a.py", typecheck_config=str(root / "configs" / "mypy.ini")
    )

    assert result["status"] == "ok"
    [(argv, cwd)] = _engine_calls(calls, "mypy")
    assert argv[argv.index("--config-file") + 1] == str(root / "configs" / "mypy.ini")
    assert cwd == str(root / "configs")


def test_t12_cli_typecheck_config_anchored_to_invocation_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S12.7/finding 7: CLI `--typecheck-config` is anchored to the
    invocation cwd."""
    from click.testing import CliRunner

    from rush.cli import cli

    root = _loose_fixture(tmp_path / "root")
    monkeypatch.chdir(root)

    run = CliRunner().invoke(
        cli,
        [
            "typecheck",
            str(root / "a.ts"),
            "--typecheck-config",
            "tsconfig.loose.json",
            "--allow-cache-write",
            "--no-cache",
            "--json",
        ],
    )

    assert run.exit_code == 0, run.output
    assert json.loads(run.output)["status"] == "ok"


def test_t12_mcp_typecheck_config_anchored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment T12 #7 (finding 7): MCP `typecheck_config` is anchored to
    the declared root, else to the server-start anchor; stable across a
    `chdir`; an error outside the root."""
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import make_tool_wrapper
    from rush.workflows.projects import register_project

    root = _loose_fixture(tmp_path / "root")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "tsconfig.loose.json").write_text("{}", encoding="utf-8")
    tool = TypecheckTool()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)

    wrapper = make_tool_wrapper(tool, executor, anchor_cwd=root)
    monkeypatch.chdir(elsewhere)
    anchored = wrapper(
        path="a.ts", typecheck_config="tsconfig.loose.json", allow_cache_write=True
    )
    assert anchored["status"] == "ok"

    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: data_root)
    declared = make_tool_wrapper(tool, executor, anchor_cwd=elsewhere)(
        path="a.ts",
        typecheck_config="tsconfig.loose.json",
        allow_cache_write=True,
        project=record.project_id,
    )
    assert declared["status"] == "ok"

    outside = wrapper(
        path="a.ts",
        typecheck_config="../elsewhere/tsconfig.loose.json",
        allow_cache_write=True,
    )
    assert outside["status"] == "error"
    assert outside["metadata"]["error"]["code"] == "TYPECHECK_CONFIG_OUTSIDE_ROOT"
