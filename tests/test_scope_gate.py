"""R20: ``scripts/scope_gate.py record`` / ``check`` (plan G14 and G9).

One parametrized test, ``test_scope_gate_preserved_baseline``, drives the real
CLI by absolute script path against a throwaway Git repository under
``tmp_path`` (cwd selects the repository). The repository holds byte copies of
the two test modules that carry the 30 retained G9 guard functions; every guard
mutation edits those copies and never executes them. The 30 names and the three
ordered AST lists are re-derived here, not taken from the script.

Check exit codes: 0 permitted, 1 scope or protected-AST violation, 2 invalid
invocation, baseline, source or Git failure. Every run asserts that no
traceback is printed (an uncaught exception would otherwise exit 1), and every
check asserts that baseline bytes, worktree bytes, the staged index and the Git
config are unchanged afterwards.

Some parameters carry a ``sibling`` instead of a record/check transition: they
load the script in-process and drive behavior a darwin subprocess run cannot
reach (Windows path semantics through ``ntpath``; a failing temporary-output
cleanup). They are still parameters of the one test and run inside ``ctx``.

Contract the baseline document must satisfy (found by content, so the JSON
layout stays the implementer's choice): the task id string; the repository root
as an absolute path string; the raw status bytes (base64, hex or text); each
dirty path with the sha256 of its bytes (or of the link text for a symlink) and
a type label naming ``missing``, ``symlink`` or ``regular``/``file``; every
guard name; and, per guard entry, the three ordered ``ast.dump`` lists.
"""

from __future__ import annotations

import ast
import base64
import functools
import hashlib
import importlib.util
import json
import ntpath
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "scripts" / "scope_gate.py"
TASK = "72-T01:R20-fixture"

AUTH = "tests/test_memory_authorization.py"
P72 = "tests/test_phase72_memory_correctness.py"
CONSOLIDATION = "src/rush/memory/consolidation.py"
RETRIEVAL = "src/rush/memory/retrieval.py"
ALIAS = "src/rush/memory/alias.py"
NEW_MODULE = "src/rush/memory/new_module.py"
TOOLS_MEMORY = "src/rush/tools/memory.py"
NEW_TOOL = "src/rush/tools/new_tool.py"
README = "README.md"
NOTES = "docs/notes.md"
DEFAULT_ALLOWED = (RETRIEVAL, "src/rush/tools/*.py")

# The 30 retained G9 guard functions, written out independently of the script.
PROTECTED: dict[str, tuple[str, ...]] = {
    AUTH: (
        "test_resolve_overlay_read_requires_overlay_owner",
        "test_nul_byte_paths_raise_only_policy_errors",
        "test_lone_surrogates_rejected_before_lock",
        "test_hold_policy_lock_and_load_reject_unusable_data_roots",
        "test_moved_data_root_keeps_project_grants",
        "test_binding_stale_on_tampered_fingerprint",
        "test_binding_registration_requires_setup_consent",
    ),
    P72: (
        "test_t01_fix1_promote_refuses_payload_mismatched_row",
        "test_t01_fix1_maintenance_promotion_refuses_payload_mismatched_row",
        "test_t01_fix1_defended_recall_rechecks_before_emit",
        "test_t01_fix1_store_recall_rechecks_before_emit",
        "test_t01_fix1_memory_tool_wire_carries_freshness",
        "test_t01_fix1_checkpoint_exemption_covers_names_only",
        "test_t01_fix1_mismatched_row_integrity_label",
        "test_t01_fix2_j1_noncanonical_backfill_survives_rewrite",
        "test_t01_fix2_j2_promotion_sweep_rereads_row_under_lock",
        "test_t01_fix2_j3_tampered_row_never_rebound",
        "test_t01_fix2_j4_compare_last_success_rechecks_before_emit",
        "test_t01_fix2_blob_content_never_rebound",
        "test_t01_fix2_deep_nested_content_is_corrupt_not_crash",
        "test_t01_fix2_edit_and_update_content_keep_noncanonical_bytes",
        "test_t01_fix2_second_source_scope_never_visible",
        "test_t02_fix1_f1_expiry_before_token_never_skips_a_row",
        "test_t02_fix1_f2_historical_utf8_page_reports_and_fits_real_size",
        "test_t02_fix1_m35_utf8_expand_telemetry_has_its_own_request_id",
        "test_t02_fix2_hybrid_compact_admission_refuses_before_effects",
        "test_t02_fix2_recall_page_rejects_non_string_cursor_before_store_reads",
        "test_t02_fix2_expand_rejects_unknown_representation",
        "test_t02_fix3_admission_precedes_access_view_and_telemetry",
        "test_t02_fix3_missing_store_compact_page_reports_measured_size",
    ),
}
GUARDS = [(mod, name) for mod, names in PROTECTED.items() for name in names]
assert len(GUARDS) == 30 and len({name for _, name in GUARDS}) == 30

# Representative guards chosen for the structure the mutation needs.
REP_AUTH = "test_binding_registration_requires_setup_consent"  # 15 asserts
REP_P72 = "test_t02_fix3_missing_store_compact_page_reports_measured_size"
ZERO_ASSERT = "test_t01_fix1_maintenance_promotion_refuses_payload_mismatched_row"
NESTED_RETURNS = "test_t02_fix3_admission_precedes_access_view_and_telemetry"
NESTED_RETURN_OWNER = "test_resolve_overlay_read_requires_overlay_owner"
REORDER_RETURNS = "test_t01_fix1_checkpoint_exemption_covers_names_only"
CALL_IN_ASSERT = "test_nul_byte_paths_raise_only_policy_errors"
SELECTED_WITH_ARGS = "test_hold_policy_lock_and_load_reject_unusable_data_roots"

_SELECTED_NAMES = frozenset({"raises", "skip", "xfail", "importorskip"})


# --------------------------------------------------------------------------
# independent AST predicate (plan G9)
# --------------------------------------------------------------------------


def _callee(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _selected(call: ast.Call) -> bool:
    name = _callee(call)
    return name is not None and ("assert" in name or name in _SELECTED_NAMES)


def _ordered(root: ast.AST) -> list[ast.AST]:
    return sorted(
        ast.walk(root),
        key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)),
    )


def _nodes(root: ast.AST, kind: type) -> list[Any]:
    return [n for n in _ordered(root) if isinstance(n, kind)]


def _expected_lists(fn: ast.FunctionDef) -> tuple[list[str], list[str], list[str]]:
    def dump(node: ast.AST) -> str:
        return ast.dump(node, include_attributes=False)

    nodes = _ordered(fn)
    return (
        [dump(n) for n in nodes if isinstance(n, ast.Assert)],
        [dump(n) for n in nodes if isinstance(n, ast.Call) and _selected(n)],
        [dump(n) for n in nodes if isinstance(n, ast.Return)],
    )


def _module_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(found) == 1, f"{name}: {len(found)} module-level definitions"
    return found[0]


def _parents(root: ast.AST) -> dict[ast.AST, ast.AST]:
    return {c: p for p in ast.walk(root) for c in ast.iter_child_nodes(p)}


# --------------------------------------------------------------------------
# source mutation by AST span
# --------------------------------------------------------------------------


class _Src:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.tree = ast.parse(data)
        self.starts = [0] + [m.end() for m in re.finditer(rb"\n", data)]

    def span(self, node: Any) -> tuple[int, int]:
        return (
            self.starts[node.lineno - 1] + node.col_offset,
            self.starts[node.end_lineno - 1] + node.end_col_offset,
        )

    def text(self, node: Any) -> bytes:
        start, end = self.span(node)
        return self.data[start:end]

    def func(self, name: str) -> ast.FunctionDef:
        return _module_function(self.tree, name)

    def after(self, fn: ast.FunctionDef) -> int:
        """Offset of the line following ``fn``."""
        assert fn.end_lineno is not None
        return self.starts[fn.end_lineno]

    def first_line(self, fn: ast.FunctionDef) -> int:
        lines = [d.lineno for d in fn.decorator_list] + [fn.lineno]
        return min(lines)

    def apply(self, *edits: tuple[int, int, bytes]) -> bytes:
        out = self.data
        for start, end, new in sorted(edits, reverse=True):
            out = out[:start] + new + out[end:]
        assert out != self.data
        return out


@functools.lru_cache(maxsize=16)
def _source(data: bytes) -> _Src:
    return _Src(data)


Mutation = Callable[[_Src, str], bytes]


def _insert_first(src: _Src, name: str, stmt: bytes) -> bytes:
    first = src.func(name).body[0]
    at = src.starts[first.lineno - 1] + first.col_offset
    return src.apply((at, at, stmt + b"\n" + b" " * first.col_offset))


def _must(items: list[Any], what: str) -> Any:
    assert items, f"fixture guard lacks {what}"
    return items[0]


def _m_assert_changed(src: _Src, name: str) -> bytes:
    node = _must(_nodes(src.func(name), ast.Assert), "an assert")
    start, end = src.span(node)
    return src.apply((start, end, b"assert (1 == 1)"))


def _m_assert_removed(src: _Src, name: str) -> bytes:
    node = _must(_nodes(src.func(name), ast.Assert), "an assert")
    start, end = src.span(node)
    return src.apply((start, end, b"pass"))


def _m_assert_added(src: _Src, name: str) -> bytes:
    return _insert_first(src, name, b"assert (1 == 1)")


def _m_return_added(src: _Src, name: str) -> bytes:
    return _insert_first(src, name, b"return None")


def _m_skip_added(src: _Src, name: str) -> bytes:
    return _insert_first(src, name, b'pytest.skip("scope-gate")')


def _m_xfail_added(src: _Src, name: str) -> bytes:
    return _insert_first(src, name, b'pytest.xfail("scope-gate")')


def _m_importorskip_added(src: _Src, name: str) -> bytes:
    return _insert_first(src, name, b'pytest.importorskip("scope_gate_absent")')


def _m_assertion_call_added(src: _Src, name: str) -> bytes:
    return _insert_first(src, name, b"scope_gate_assert_helper()")


def _m_raises_added(src: _Src, name: str) -> bytes:
    return _insert_first(src, name, b"pytest.raises(ValueError)")


def _decorator(line: bytes) -> Mutation:
    def mutate(src: _Src, name: str) -> bytes:
        at = src.starts[src.first_line(src.func(name)) - 1]
        return src.apply((at, at, line + b"\n"))

    return mutate


def _m_selected_removed(src: _Src, name: str) -> bytes:
    call = _must(
        [n for n in _nodes(src.func(name), ast.Call) if _selected(n)], "a selected call"
    )
    start, end = src.span(call)
    return src.apply((start, end, b"None"))


def _m_selected_swapped(src: _Src, name: str) -> bytes:
    call = _must(
        [n for n in _nodes(src.func(name), ast.Call) if _selected(n)], "a selected call"
    )
    start, end = src.span(call.func)
    return src.apply((start, end, b"pytest.xfail"))


def _nested_returns(src: _Src, name: str) -> list[ast.Return]:
    fn = src.func(name)
    parents = _parents(fn)
    found = []
    for node in _nodes(fn, ast.Return):
        owner = parents[node]
        while not isinstance(
            owner, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
        ):
            owner = parents[owner]
        if owner is not fn:
            found.append(node)
    return found


def _m_return_changed(src: _Src, name: str) -> bytes:
    node = _must(_nodes(src.func(name), ast.Return), "a return")
    start, end = src.span(node)
    return src.apply((start, end, b'return "scope-gate"'))


def _m_return_removed(src: _Src, name: str) -> bytes:
    node = _must(_nodes(src.func(name), ast.Return), "a return")
    start, end = src.span(node)
    return src.apply((start, end, b"pass"))


def _m_nested_return_changed(src: _Src, name: str) -> bytes:
    node = _must(_nested_returns(src, name), "a nested-helper return")
    start, end = src.span(node)
    return src.apply((start, end, b'return "scope-gate"'))


def _m_nested_return_removed(src: _Src, name: str) -> bytes:
    node = _must(_nested_returns(src, name), "a nested-helper return")
    start, end = src.span(node)
    return src.apply((start, end, b"pass"))


def _swap(kind: type) -> Mutation:
    def mutate(src: _Src, name: str) -> bytes:
        nodes = _nodes(src.func(name), kind)
        assert nodes, f"fixture guard lacks {kind.__name__}"
        first = nodes[0]
        other = _must(
            [n for n in nodes[1:] if ast.dump(n) != ast.dump(first)],
            f"two distinct {kind.__name__} nodes",
        )
        (s1, e1), (s2, e2) = src.span(first), src.span(other)
        return src.apply((s1, e1, src.data[s2:e2]), (s2, e2, src.data[s1:e1]))

    return mutate


def _arg_expr(call: ast.Call) -> ast.expr | None:
    for arg in call.args:
        if not isinstance(arg, ast.Starred):
            return arg
    for keyword in call.keywords:
        if keyword.arg is not None:
            return keyword.value
    return None


def _wrap(src: _Src, expr: ast.expr) -> tuple[int, int, bytes]:
    start, end = src.span(expr)
    text = src.data[start:end]
    return (start, end, b"(" + text + b" if True else " + text + b")")


def _ordinary_with_arg(root: ast.AST) -> list[ast.Call]:
    return [
        n
        for n in _nodes(root, ast.Call)
        if not _selected(n) and _arg_expr(n) is not None
    ]


def _m_arg_in_assert(src: _Src, name: str) -> bytes:
    for node in _nodes(src.func(name), ast.Assert):
        calls = _ordinary_with_arg(node)
        if calls:
            expr = _arg_expr(calls[0])
            assert expr is not None
            return src.apply(_wrap(src, expr))
    raise AssertionError("fixture guard lacks an ordinary call inside an assert")


def _m_arg_in_return(src: _Src, name: str) -> bytes:
    for node in _nodes(src.func(name), ast.Return):
        calls = _ordinary_with_arg(node)
        if calls:
            expr = _arg_expr(calls[0])
            assert expr is not None
            return src.apply(_wrap(src, expr))
    raise AssertionError("fixture guard lacks an ordinary call inside a return")


def _m_arg_in_selected(src: _Src, name: str) -> bytes:
    for call in _nodes(src.func(name), ast.Call):
        if _selected(call) and _arg_expr(call) is not None:
            expr = _arg_expr(call)
            assert expr is not None
            return src.apply(_wrap(src, expr))
    raise AssertionError("fixture guard lacks a selected call with an argument")


def _m_free_arg(src: _Src, name: str) -> bytes:
    """Change one argument of an ordinary call that sits inside no protected node."""
    fn = src.func(name)
    parents = _parents(fn)
    for call in _ordinary_with_arg(fn):
        chain = []
        node: ast.AST = call
        while node in parents:
            node = parents[node]
            chain.append(node)
        if any(
            isinstance(n, ast.Assert | ast.Return)
            or (isinstance(n, ast.Call) and _selected(n))
            for n in chain
        ):
            continue
        expr = _arg_expr(call)
        assert expr is not None
        if any(
            isinstance(n, ast.Assert | ast.Return)
            or (isinstance(n, ast.Call) and _selected(n))
            for n in ast.walk(expr)
        ):
            continue
        return src.apply(_wrap(src, expr))
    raise AssertionError("fixture guard lacks a free ordinary call")


def _m_source_hash_site(index: int) -> Mutation:
    """Change the argument of the index-th ``source_hash(`` call that sits in no
    protected Assert, selected Call or Return."""

    def mutate(src: _Src, name: str) -> bytes:
        parents = _parents(src.tree)
        sites = []
        for call in _nodes(src.tree, ast.Call):
            if _callee(call) != "source_hash" or _arg_expr(call) is None:
                continue
            chain = []
            node: ast.AST = call
            while node in parents:
                node = parents[node]
                chain.append(node)
            if not any(
                isinstance(n, ast.Assert | ast.Return)
                or (isinstance(n, ast.Call) and _selected(n))
                for n in chain
            ):
                sites.append(call)
        assert len(sites) > index, "fixture module lost a source_hash call site"
        expr = _arg_expr(sites[index])
        assert expr is not None
        start, end = src.span(expr)
        return src.apply((start, end, b"(" + src.data[start:end] + b") / 'moved.py'"))

    return mutate


def _m_missing(src: _Src, name: str) -> bytes:
    fn = src.func(name)
    start = src.starts[src.first_line(fn) - 1]
    end = src.after(fn)
    return src.apply((start, end, b""))


def _m_duplicate(src: _Src, name: str) -> bytes:
    fn = src.func(name)
    start = src.starts[src.first_line(fn) - 1]
    end = src.span(fn)[1]
    return src.apply((end, end, b"\n\n\n" + src.data[start:end]))


def _m_adjacent_test(src: _Src, name: str) -> bytes:
    fn = src.func(name)
    at = src.after(fn)
    return src.apply(
        (
            at,
            at,
            b"\n\ndef test_scope_gate_added_beside_guards():\n    assert 1 == 1\n\n",
        )
    )


def _m_shift(src: _Src, name: str) -> bytes:
    return src.apply((0, 0, b"# shifted header\n" * 9))


def _m_comments(src: _Src, name: str) -> bytes:
    fn = src.func(name)
    edits = []
    for node in _ordered(fn):
        if isinstance(node, ast.Assert | ast.Return):
            end = src.span(node)[1]
            edits.append((end, end, b"  # reviewed"))
    return src.apply(*edits)


def _m_blank_lines(src: _Src, name: str) -> bytes:
    fn = src.func(name)
    lines = {n.lineno for n in _ordered(fn) if isinstance(n, ast.Assert | ast.Return)}
    return src.apply(
        *[(src.starts[line - 1], src.starts[line - 1], b"\n") for line in lines]
    )


def _m_reparen(src: _Src, name: str) -> bytes:
    fn = src.func(name)
    edits = []
    for node in _nodes(fn, ast.Assert):
        start, end = src.span(node.test)
        edits.append((start, end, b"(" + src.data[start:end] + b")"))
    return src.apply(*edits)


def _m_syntax_error(src: _Src, name: str) -> bytes:
    return src.data + b"\ndef broken(:\n"


def _raw(append: bytes) -> Callable[[bytes], bytes]:
    return lambda data: data + append


# --------------------------------------------------------------------------
# fixture repository
# --------------------------------------------------------------------------


def _env(home: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") and k not in {"PYTHONPATH", "PYTHONHOME"}
    }
    home.mkdir(parents=True, exist_ok=True)
    config = home / ".gitconfig"
    if not config.exists():
        config.write_text(
            "[user]\n\tname = Scope Gate\n\temail = scope-gate@example.invalid\n"
            "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n"
            "[core]\n\tautocrlf = false\n",
            encoding="utf-8",
        )
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_DATA_HOME=str(home / "data"),
        LOCALAPPDATA=str(home / "local"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


def _git(cwd: Path, env: dict[str, str], *args: str) -> bytes:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, check=False
    )
    assert proc.returncode == 0, (args, proc.stderr)
    return proc.stdout


def _rmtree(path: Path) -> None:
    def retry(func: Callable[..., Any], target: str, _exc: Any) -> None:
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        func(target)

    shutil.rmtree(path, onexc=retry)


@dataclass
class Ctx:
    repo: Path
    work: Path
    out_dir: Path
    out: Path
    env: dict[str, str]
    outside: Path
    other: Path | None = None


Action = Callable[[Ctx], object]


def _write(base: Path, rel: str, data: bytes | str) -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    base = tmp_path_factory.mktemp("scope-gate-template")
    env = _env(base / "home")
    repo = base / "repo"
    repo.mkdir()
    module = "def f():\n    return 1\n"
    _write(repo, README, "readme\n")
    _write(repo, NOTES, "notes\n")
    _write(repo, ".gitignore", "ignored_*\n")
    _write(repo, CONSOLIDATION, module)
    _write(repo, RETRIEVAL, module)
    _write(repo, TOOLS_MEMORY, module)
    _write(repo, "tests/test_other.py", "def test_other():\n    assert True\n")
    for mod, names in PROTECTED.items():
        data = (HERE / Path(mod).name).read_bytes()
        tree = ast.parse(data)
        for name in names:
            _module_function(tree, name)
        _write(repo, mod, data)
    _git(repo, env, "init", "-q")
    _git(repo, env, "add", "--all")
    _git(repo, env, "commit", "-q", "-m", "fixture")
    yield repo
    _rmtree(base)


@pytest.fixture
def ctx(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Ctx]:
    home = tmp_path / "home"
    env = _env(home)
    for key in ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.setenv(key, env[key])
    work = tmp_path / "work"
    work.mkdir()
    repo = work / "repo_case"
    shutil.copytree(template, repo, symlinks=True)
    out_dir = tmp_path / "baselines"
    out_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    yield Ctx(repo, work, out_dir, out_dir / "baseline.json", env, outside)
    _rmtree(home)


# --------------------------------------------------------------------------
# running and snapshots
# --------------------------------------------------------------------------


@dataclass
class Run:
    code: int
    out: str


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> Run:
    assert SCRIPT.is_file(), f"{SCRIPT} does not exist"
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *argv],
        cwd=cwd,
        env=env,
        capture_output=True,
        timeout=180,
        check=False,
    )
    return Run(
        proc.returncode, (proc.stdout + b"\n" + proc.stderr).decode("utf-8", "replace")
    )


def _forms(text: str) -> list[str]:
    return [
        text,
        text.encode("unicode_escape").decode("ascii"),
        repr(text)[1:-1],
        json.dumps(text)[1:-1],
        json.dumps(text, ensure_ascii=False)[1:-1],
    ]


# words any refusal or the usage text contains: they identify no particular input
GENERIC_OFFENDERS = frozenset({"baseline", "usage", "git", "Git", "repository"})


def _expect(run: Run, code: int, offenders: tuple[str, ...], label: str) -> None:
    assert "Traceback" not in run.out, f"{label} raised: {run.out}"
    assert run.code == code, f"{label} exited {run.code}, expected {code}: {run.out}"
    if code != 0:
        specific = tuple(o for o in offenders if o not in GENERIC_OFFENDERS)
        assert specific, (
            f"{label} refusal case lacks a specific identifier: {offenders!r}"
        )
        refusal = "\n".join(
            line
            for line in run.out.splitlines()
            if "error:" in line or "violation:" in line
        )
        assert any(form in refusal for o in specific for form in _forms(o)), (
            f"{label} refusal lines name none of {specific!r}: {run.out}"
        )


def _tree(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def visit(directory: Path, prefix: str) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda e: e.name):
                rel = prefix + entry.name
                if rel == ".git":
                    continue
                if entry.is_symlink():
                    out[rel] = ("symlink", os.readlink(entry.path))
                elif entry.is_dir():
                    out[rel] = ("dir",)
                    visit(Path(entry.path), rel + "/")
                else:
                    try:
                        out[rel] = (
                            "file",
                            hashlib.sha256(Path(entry.path).read_bytes()).hexdigest(),
                        )
                    except OSError:
                        out[rel] = ("unreadable", stat.S_IMODE(entry.stat().st_mode))

    visit(root, "")
    return out


def _snapshot(root: Path, env: dict[str, str]) -> dict[str, Any]:
    snap: dict[str, Any] = {"tree": _tree(root)}
    git_dir = root / ".git"
    if git_dir.is_dir():
        for name in ("HEAD", "config"):
            snap[name] = (
                (git_dir / name).read_bytes() if (git_dir / name).exists() else None
            )
        ls = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "ls-files", "-s", "-z"],
            cwd=root,
            env=env,
            capture_output=True,
            check=False,
        )
        index = (
            (git_dir / "index").read_bytes() if (git_dir / "index").exists() else b""
        )
        snap["index"] = (ls.returncode, ls.stdout, index)
    return snap


def _status(repo: Path, env: dict[str, str]) -> bytes:
    return _git(repo, env, "status", "--porcelain=v1", "-z", "--untracked-files=all")


def _status_paths(status: bytes) -> list[str]:
    parts = status.split(b"\0")
    paths: list[str] = []
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        xy = entry[:2].decode("ascii")
        paths.append(os.fsdecode(entry[3:]))
        if "R" in xy or "C" in xy:
            paths.append(os.fsdecode(parts[i]))
            i += 1
    return paths


# --------------------------------------------------------------------------
# baseline document inspection (layout-agnostic)
# --------------------------------------------------------------------------


def _walk(
    node: Any, path: tuple[Any, ...] = ()
) -> Iterator[tuple[tuple[Any, ...], Any]]:
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, (*path, index))


def _get(doc: Any, path: tuple[Any, ...]) -> Any:
    for part in path:
        doc = doc[part]
    return doc


def _strings(doc: Any) -> set[str]:
    found: set[str] = set()
    for _, node in _walk(doc):
        if isinstance(node, str):
            found.add(node)
        elif isinstance(node, dict):
            found.update(k for k in node if isinstance(k, str))
    return found


def _entry_candidates(doc: Any, name: str) -> Iterator[tuple[tuple[Any, ...], Any]]:
    for path, node in _walk(doc):
        if isinstance(node, dict):
            if name in node:
                yield (*path, name), node[name]
            elif name in node.values():
                yield path, node


def _has_lists(sub: Any, expected: tuple[list[str], list[str], list[str]]) -> bool:
    found = [n for _, n in _walk(sub) if isinstance(n, list)]
    for want in expected:
        if want and want not in found:
            return False
    return sum(1 for n in found if n == []) >= sum(1 for w in expected if not w)


@functools.lru_cache(maxsize=32)
def _module_lists(
    mod: str, data: bytes
) -> dict[str, tuple[list[str], list[str], list[str]]]:
    module = ast.parse(data)
    return {
        name: _expected_lists(_module_function(module, name)) for name in PROTECTED[mod]
    }


def _guard_lists(
    repo: Path,
) -> dict[tuple[str, str], tuple[list[str], list[str], list[str]]]:
    lists = {}
    for mod in PROTECTED:
        for name, found in _module_lists(mod, (repo / mod).read_bytes()).items():
            lists[(mod, name)] = found
    return lists


def _expected_snapshot(path: Path) -> dict[str, str | None]:
    """The record the gate must hold for ``path``, derived without the script."""
    if path.is_symlink():
        link = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
        return {"type": "symlink", "sha256": link}
    if path.is_dir():
        with os.scandir(path) as entries:
            kids = sorted(entries, key=lambda e: os.fsencode(e.name))
            listing = [[e.name, _expected_snapshot(Path(e.path))] for e in kids]
        data = json.dumps(listing, separators=(",", ":")).encode("ascii")
        return {"type": "directory", "sha256": hashlib.sha256(data).hexdigest()}
    if path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"type": "regular", "sha256": digest}
    if path.exists():
        return {"type": "other", "sha256": None}
    return {"type": "missing", "sha256": None}


def _assert_record_content(doc: Any, c: Ctx, status: bytes) -> None:
    strings = _strings(doc)
    assert TASK in strings
    if status:
        raw = {
            base64.b64encode(status).decode("ascii"),
            status.hex(),
            status.decode("utf-8", "surrogateescape"),
            status.decode("latin-1"),
        }
        assert raw & strings, "baseline does not hold the raw status bytes"
    for rel in _status_paths(status):
        assert rel in strings or base64.b64encode(rel.encode()).decode() in strings, rel
        want = _expected_snapshot(c.repo / rel)
        assert any(sub == want for _, sub in _entry_candidates(doc, rel)), (
            f"baseline lacks the exact snapshot {want!r} for {rel}"
        )
    for (_mod, name), expected in _guard_lists(c.repo).items():
        assert name in strings, f"baseline lacks guard {name}"
        assert any(
            _has_lists(sub, expected) for _, sub in _entry_candidates(doc, name)
        ), f"baseline lacks the three ordered AST lists of {name}"


# --------------------------------------------------------------------------
# the case table
# --------------------------------------------------------------------------


@dataclass
class Edit:
    data: bytes
    offenders: tuple[str, ...] = ()


@dataclass
class Case:
    setup: Action | None = None
    after: Action | None = None
    allowed: tuple[str, ...] = DEFAULT_ALLOWED
    expected: int | Callable[[Ctx], int] = 0
    offenders: tuple[str, ...] = ()
    record_expected: int = 0
    record_offenders: tuple[str, ...] = ()
    record_argv: Callable[[Ctx], list[str]] | None = None
    check_argv: Callable[[Ctx], list[str]] | None = None
    record_cwd: Callable[[Ctx], Path] | None = None
    check_cwd: Callable[[Ctx], Path] | None = None
    edit: Callable[[Ctx, Any], Edit] | None = None
    sibling: Callable[[Ctx, pytest.MonkeyPatch], None] | None = None
    post: Action | None = None


def _exercise(case: Case, c: Ctx) -> None:
    if case.setup:
        case.setup(c)
    record_cwd = case.record_cwd(c) if case.record_cwd else c.repo
    argv = (
        case.record_argv(c)
        if case.record_argv
        else ["record", "--task", TASK, "--out", str(c.out)]
    )
    status = _status(c.repo, c.env) if case.record_expected == 0 else b""
    snap0 = _snapshot(record_cwd, c.env)
    record = _run(argv, record_cwd, c.env)
    _expect(record, case.record_expected, case.record_offenders, "record")
    assert _snapshot(record_cwd, c.env) == snap0, "record changed the repository"
    if case.record_expected != 0:
        assert not c.out.exists()
        assert list(c.out_dir.iterdir()) == [], "a failed record published output"
        if case.post:
            case.post(c)
        return
    assert [p.name for p in c.out_dir.iterdir()] == [c.out.name]
    doc = json.loads(c.out.read_bytes())
    _assert_record_content(doc, c, status)
    if case.after:
        case.after(c)
    offenders = case.offenders
    if case.edit:
        edit = case.edit(c, doc)
        c.out.write_bytes(edit.data)
        offenders = (*offenders, *edit.offenders)
    baseline = c.out.read_bytes()
    check_cwd = case.check_cwd(c) if case.check_cwd else c.repo
    argv = (
        case.check_argv(c)
        if case.check_argv
        else ["check", "--baseline", str(c.out), "--allowed", *case.allowed]
    )
    before = _snapshot(check_cwd, c.env)
    check = _run(argv, check_cwd, c.env)
    expected = case.expected(c) if callable(case.expected) else case.expected
    _expect(check, expected, offenders, "check")
    assert c.out.read_bytes() == baseline, "check rewrote the baseline"
    assert _snapshot(check_cwd, c.env) == before, "check changed the repository"
    if case.post:
        case.post(c)


# ---- repository actions ----


def _append(rel: str, text: str = "\n# edit\n") -> Action:
    def act(c: Ctx) -> None:
        with open(c.repo / rel, "ab") as handle:
            handle.write(text.encode("utf-8"))

    return act


def _create(rel: str, text: str = "new\n") -> Action:
    return lambda c: _write(c.repo, rel, text)


def _stage(*rels: str) -> Action:
    return lambda c: _git(c.repo, c.env, "add", "-f", "--", *rels)


def _remove(rel: str) -> Action:
    return lambda c: (c.repo / rel).unlink()


def _restore(rel: str) -> Action:
    return lambda c: (c.repo / rel).write_bytes(
        _git(c.repo, c.env, "show", f"HEAD:{rel}")
    )


def _git_mv(src: str, dst: str) -> Action:
    return lambda c: _git(c.repo, c.env, "mv", src, dst)


def _plain_mv(src: str, dst: str) -> Action:
    return lambda c: (c.repo / src).rename(c.repo / dst)


def _both(*steps: Action) -> Action:
    def act(c: Ctx) -> None:
        for step in steps:
            step(c)

    return act


def _edit_module(mod: str, mutation: Mutation, name: str) -> Action:
    def act(c: Ctx) -> None:
        path = c.repo / mod
        path.write_bytes(mutation(_source(path.read_bytes()), name))

    return act


def _edit_bytes(mod: str, fn: Callable[[bytes], bytes]) -> Action:
    def act(c: Ctx) -> None:
        path = c.repo / mod
        path.write_bytes(fn(path.read_bytes()))

    return act


def _marker(c: Ctx) -> Path:
    return c.outside / "callbacks.marker"


def _arm_git_callbacks(c: Ctx) -> None:
    """Configure a core.fsmonitor hook and a clean filter that write a marker."""
    marker = shlex.quote(str(_marker(c)))
    for name, body in (("fsmonitor.sh", "exit 1"), ("clean.sh", "cat")):
        script = c.outside / name
        script.write_text(f"#!/bin/sh\necho {name} >> {marker}\n{body}\n")
        script.chmod(0o755)
    fsmonitor = shlex.quote(str(c.outside / "fsmonitor.sh"))
    clean = shlex.quote(str(c.outside / "clean.sh"))
    _git(c.repo, c.env, "config", "core.fsmonitor", fsmonitor)
    _git(c.repo, c.env, "config", "filter.marker.clean", clean)
    (c.repo / ".git" / "info").mkdir(exist_ok=True)
    (c.repo / ".git" / "info" / "attributes").write_text("* filter=marker\n")
    _touch_tracked(c, 1_000_000_000)


def _touch_tracked(c: Ctx, stamp: int) -> None:
    """Make every worktree file stat-dirty so Git re-reads it through the filter."""
    for dirpath, dirnames, filenames in os.walk(c.repo):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            os.utime(os.path.join(dirpath, name), (stamp, stamp))


def _reset_callbacks(c: Ctx) -> None:
    _marker(c).unlink(missing_ok=True)
    _touch_tracked(c, 1_100_000_000)


def _assert_no_callbacks(c: Ctx) -> None:
    marker = _marker(c)
    ran = marker.read_text() if marker.exists() else ""
    assert not ran, f"a repository-configured Git callback ran: {ran!r}"


def _arm_lazy_fetch(c: Ctx) -> None:
    """Make origin a promisor remote whose helper (found on PATH) writes the marker."""
    helper_dir = c.outside / "helper-bin"
    helper_dir.mkdir()
    helper = helper_dir / "git-remote-marker"
    helper.write_text(
        f"#!/bin/sh\necho git-remote-marker >> {shlex.quote(str(_marker(c)))}\nexit 1\n"
    )
    helper.chmod(0o755)
    c.env["PATH"] = str(helper_dir) + os.pathsep + c.env["PATH"]
    for key, value in (
        ("core.repositoryformatversion", "1"),
        ("extensions.partialClone", "origin"),
        ("remote.origin.promisor", "true"),
        ("remote.origin.url", "marker::fixture"),
    ):
        _git(c.repo, c.env, "config", key, value)


def _delete_object(revspec: str) -> Action:
    """Remove the loose object ``revspec`` names: Git would lazily fetch it."""

    def act(c: Ctx) -> None:
        oid = _git(c.repo, c.env, "rev-parse", revspec).decode("ascii").strip()
        path = c.repo / ".git" / "objects" / oid[:2] / oid[2:]
        assert path.is_file(), f"{revspec} is not a loose object"
        path.unlink()

    return act


def _dirty_gitlink(c: Ctx) -> None:
    """vendor/lib is a Gitlink (mode 160000) whose worktree is already modified."""
    lib = c.repo / "vendor" / "lib"
    lib.mkdir(parents=True)
    _git(lib, c.env, "init", "-q")
    _write(lib, "lib.txt", "one\n")
    _git(lib, c.env, "add", "lib.txt")
    _git(lib, c.env, "commit", "-q", "-m", "lib")
    _git(c.repo, c.env, "add", "vendor/lib")
    _git(c.repo, c.env, "commit", "-q", "-m", "gitlink")
    _write(lib, "lib.txt", "two\n")


def _change_gitlink(c: Ctx) -> None:
    _write(c.repo / "vendor" / "lib", "lib.txt", "three\n")


def _assert_oracle_sees_index_rewrite(c: Ctx) -> None:
    """A rewrite that keeps every staged entry must still change the snapshot."""
    before = _snapshot(c.repo, c.env)
    _git(c.repo, c.env, "update-index", "--index-version", "4")
    assert _snapshot(c.repo, c.env) != before, "snapshot misses an index rewrite"


CASES: list[Any] = []
_IDS: set[str] = set()


def add(case_id: str, case: Case, *marks: Any) -> None:
    assert case_id not in _IDS, case_id
    _IDS.add(case_id)
    CASES.append(pytest.param(case, id=case_id, marks=list(marks)))


posix_only = pytest.mark.posix_only
posix_nonroot = pytest.mark.posix_nonroot

# ---- the nine packet cases and their boundary siblings ----

add(
    "dirty_nonallowed_preserved",
    Case(setup=_append(CONSOLIDATION), after=_append(RETRIEVAL), expected=0),
)
add(
    "dirty_nonallowed_changed",
    Case(
        setup=_append(CONSOLIDATION),
        after=_append(CONSOLIDATION, "# again\n"),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)
add(
    "dirty_nonallowed_staged",
    Case(
        setup=_append(CONSOLIDATION),
        after=_stage(CONSOLIDATION),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)
add(
    "new_nonallowed_untracked",
    Case(after=_create("stray.txt"), expected=1, offenders=("stray.txt",)),
)
add(
    "new_nonallowed_untracked_in_new_directory",
    Case(
        after=_create("brand/new/dir/stray.txt"), expected=1, offenders=("stray.txt",)
    ),
)
add(
    "dirty_allowed_changed_again_unstaged",
    Case(setup=_append(RETRIEVAL), after=_append(RETRIEVAL, "# again\n"), expected=0),
)
add(
    "dirty_allowed_changed_again_staged",
    Case(
        setup=_append(RETRIEVAL),
        after=_both(_append(RETRIEVAL, "# again\n"), _stage(RETRIEVAL)),
        expected=0,
    ),
)
add(
    "dirty_allowed_deleted_after_record",
    Case(setup=_append(RETRIEVAL), after=_remove(RETRIEVAL), expected=0),
)
add("allowed_new_untracked", Case(after=_create(NEW_TOOL), expected=0))
add("clean_repository_unchanged", Case(expected=0))
add(
    "clean_tracked_nonallowed_modified",
    Case(after=_append(README), expected=1, offenders=(README,)),
)
add(
    "clean_tracked_nonallowed_deleted",
    Case(after=_remove(README), expected=1, offenders=(README,)),
)
add(
    "ignored_file_created_is_not_dirty",
    Case(after=_create("ignored_scratch.txt"), expected=0),
)
add(
    "prefix_of_allowed_name_is_not_allowed",
    Case(
        after=_create(RETRIEVAL + ".bak"), expected=1, offenders=(RETRIEVAL + ".bak",)
    ),
)

# ---- baseline-dirty non-allowed paths that stop being dirty ----

add(
    "baseline_nonallowed_restored_to_head",
    Case(
        setup=_append(CONSOLIDATION),
        after=_restore(CONSOLIDATION),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)
add(
    "baseline_nonallowed_deleted",
    Case(
        setup=_append(CONSOLIDATION),
        after=_remove(CONSOLIDATION),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)
add(
    "baseline_nonallowed_untracked_deleted",
    Case(
        setup=_create("scratch.txt"),
        after=_remove("scratch.txt"),
        expected=1,
        offenders=("scratch.txt",),
    ),
)
add(
    "baseline_nonallowed_untracked_unchanged",
    Case(setup=_create("scratch.txt"), after=_append(RETRIEVAL), expected=0),
)
add(
    "baseline_deleted_tracked_stays_deleted",
    Case(setup=_remove(CONSOLIDATION), after=_append(RETRIEVAL), expected=0),
)
add(
    "baseline_deleted_tracked_restored",
    Case(
        setup=_remove(CONSOLIDATION),
        after=_restore(CONSOLIDATION),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)

# ---- staging ----

add(
    "staged_nonallowed_preexisting_unchanged",
    Case(
        setup=_both(_append(CONSOLIDATION), _stage(CONSOLIDATION)),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)
add(
    "staged_nonallowed_new_file",
    Case(
        after=_both(_create("stray.txt"), _stage("stray.txt")),
        expected=1,
        offenders=("stray.txt",),
    ),
)
add(
    "staged_allowed_unstaged_baseline",
    Case(after=_both(_append(RETRIEVAL), _stage(RETRIEVAL)), expected=0),
)

# ---- renames: both endpoints count ----

add(
    "rename_allowed_to_nonallowed_staged",
    Case(
        allowed=(RETRIEVAL,),
        after=_git_mv(RETRIEVAL, "src/rush/memory/retrieval_old.py"),
        expected=1,
        offenders=("src/rush/memory/retrieval_old.py",),
    ),
)
add(
    "rename_allowed_to_nonallowed_unstaged",
    Case(
        allowed=(RETRIEVAL,),
        after=_plain_mv(RETRIEVAL, "src/rush/memory/retrieval_old.py"),
        expected=1,
        offenders=("src/rush/memory/retrieval_old.py",),
    ),
)
add(
    "rename_nonallowed_to_allowed_staged",
    Case(
        allowed=(RETRIEVAL, ALIAS),
        after=_git_mv(CONSOLIDATION, ALIAS),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)
add(
    "rename_nonallowed_to_allowed_unstaged",
    Case(
        allowed=(RETRIEVAL, ALIAS),
        after=_plain_mv(CONSOLIDATION, ALIAS),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
)
add(
    "rename_allowed_to_allowed",
    Case(allowed=(RETRIEVAL, ALIAS), after=_git_mv(RETRIEVAL, ALIAS), expected=0),
)
add(
    "baseline_rename_allowed_to_allowed_unchanged",
    Case(allowed=(RETRIEVAL, ALIAS), setup=_git_mv(RETRIEVAL, ALIAS), expected=0),
)
add(
    "baseline_rename_nonallowed_staged_endpoint",
    Case(
        setup=_git_mv(CONSOLIDATION, "src/rush/memory/consolidation2.py"),
        expected=1,
        offenders=(CONSOLIDATION, "src/rush/memory/consolidation2.py"),
    ),
)
add(
    "baseline_rename_both_endpoints_allowed",
    Case(
        allowed=(RETRIEVAL, CONSOLIDATION, "src/rush/memory/consolidation2.py"),
        setup=_git_mv(CONSOLIDATION, "src/rush/memory/consolidation2.py"),
        after=_append("src/rush/memory/consolidation2.py"),
        expected=0,
    ),
)

# ---- G8 predicates, one row per operand form ----
#   P1: path outside A keeps its recorded bytes
#   P2: every staged path is inside A
#   P3: no new dirty path appears outside A

_FORMS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "exact": ((RETRIEVAL, NEW_MODULE), RETRIEVAL, NEW_MODULE),
    "glob": (("src/rush/tools/*.py",), TOOLS_MEMORY, NEW_TOOL),
    "mixed_operands": (
        (NOTES, RETRIEVAL, "src/rush/tools/*.py"),
        TOOLS_MEMORY,
        NEW_TOOL,
    ),
}
for _form, (_allowed, _tracked, _new) in _FORMS.items():
    add(
        f"operand_{_form}-p1-allowed_modified",
        Case(allowed=_allowed, after=_append(_tracked), expected=0),
    )
    add(
        f"operand_{_form}-p1-nonallowed_modified",
        Case(
            allowed=_allowed,
            after=_append(CONSOLIDATION),
            expected=1,
            offenders=(CONSOLIDATION,),
        ),
    )
    add(
        f"operand_{_form}-p2-allowed_staged",
        Case(
            allowed=_allowed,
            after=_both(_append(_tracked), _stage(_tracked)),
            expected=0,
        ),
    )
    add(
        f"operand_{_form}-p2-nonallowed_staged",
        Case(
            allowed=_allowed,
            after=_both(_append(CONSOLIDATION), _stage(CONSOLIDATION)),
            expected=1,
            offenders=(CONSOLIDATION,),
        ),
    )
    add(
        f"operand_{_form}-p3-allowed_new",
        Case(allowed=_allowed, after=_create(_new), expected=0),
    )
    add(
        f"operand_{_form}-p3-nonallowed_new",
        Case(
            allowed=_allowed,
            after=_create("src/rush/memory/stray.py"),
            expected=1,
            offenders=("src/rush/memory/stray.py",),
        ),
    )

# ---- guards: each of the 30 functions, missing and duplicated ----

for _mod, _name in GUARDS:
    add(
        f"missing_guard-{_name}",
        Case(
            allowed=(_mod,),
            after=_edit_module(_mod, _m_missing, _name),
            expected=1,
            offenders=(_name,),
        ),
    )
    add(
        f"duplicate_guard-{_name}",
        Case(
            allowed=(_mod,),
            after=_edit_module(_mod, _m_duplicate, _name),
            expected=1,
            offenders=(_name,),
        ),
    )
    _first_mutation = _m_assert_added if _name == ZERO_ASSERT else _m_assert_changed
    add(
        f"{'assert_added' if _name == ZERO_ASSERT else 'assert_changed'}-{_name}",
        Case(
            allowed=(_mod,),
            after=_edit_module(_mod, _first_mutation, _name),
            expected=1,
            offenders=(_name,),
        ),
    )

# ---- guards: protected node mutations (module allowed) ----


def _guard(
    case_id: str, mod: str, name: str, mutation: Mutation, expected: int, *marks: Any
) -> None:
    add(
        case_id,
        Case(
            allowed=(mod,),
            after=_edit_module(mod, mutation, name),
            expected=expected,
            offenders=(name,) if expected else (),
        ),
        *marks,
    )


_guard("guard_assert_removed-auth", AUTH, REP_AUTH, _m_assert_removed, 1)
_guard("guard_assert_removed-p72", P72, REP_P72, _m_assert_removed, 1)
_guard("guard_assert_changed-p72", P72, REP_P72, _m_assert_changed, 1)
_guard("guard_return_added-auth", AUTH, REP_AUTH, _m_return_added, 1)
_guard("guard_return_added-p72", P72, REP_P72, _m_return_added, 1)
_guard("guard_return_added-zero_assert", P72, ZERO_ASSERT, _m_return_added, 1)
_guard("guard_skip_added-auth", AUTH, REP_AUTH, _m_skip_added, 1)
_guard("guard_skip_added-p72", P72, REP_P72, _m_skip_added, 1)
_guard("guard_skip_added-zero_assert", P72, ZERO_ASSERT, _m_skip_added, 1)
_guard("guard_xfail_added-p72", P72, REP_P72, _m_xfail_added, 1)
_guard("guard_xfail_added-auth", AUTH, REP_AUTH, _m_xfail_added, 1)
_guard("guard_importorskip_added-p72", P72, REP_P72, _m_importorskip_added, 1)
_guard("guard_importorskip_added-auth", AUTH, REP_AUTH, _m_importorskip_added, 1)
_guard("guard_assertion_call_added-p72", P72, REP_P72, _m_assertion_call_added, 1)
_guard("guard_assertion_call_added-auth", AUTH, REP_AUTH, _m_assertion_call_added, 1)
_guard("guard_raises_call_added-p72", P72, REP_P72, _m_raises_added, 1)
_guard("guard_raises_call_added-zero_assert", P72, ZERO_ASSERT, _m_raises_added, 1)
_guard(
    "guard_decorator_skip_added-p72",
    P72,
    NESTED_RETURNS,
    _decorator(b'@pytest.mark.skip(reason="x")'),
    1,
)
_guard(
    "guard_decorator_xfail_added-auth",
    AUTH,
    REP_AUTH,
    _decorator(b'@pytest.mark.xfail(reason="x")'),
    1,
)
_guard(
    "guard_selected_call_removed-zero_assert", P72, ZERO_ASSERT, _m_selected_removed, 1
)
_guard(
    "guard_selected_call_removed-auth", AUTH, SELECTED_WITH_ARGS, _m_selected_removed, 1
)
_guard(
    "guard_selected_call_swapped-zero_assert", P72, ZERO_ASSERT, _m_selected_swapped, 1
)
_guard(
    "guard_selected_call_swapped-auth", AUTH, SELECTED_WITH_ARGS, _m_selected_swapped, 1
)
_guard("guard_return_changed-p72", P72, REP_P72, _m_return_changed, 1)
_guard("guard_return_removed-p72", P72, REP_P72, _m_return_removed, 1)
_guard(
    "guard_nested_helper_return_changed-auth",
    AUTH,
    NESTED_RETURN_OWNER,
    _m_nested_return_changed,
    1,
)
_guard(
    "guard_nested_helper_return_removed-auth",
    AUTH,
    NESTED_RETURN_OWNER,
    _m_nested_return_removed,
    1,
)
_guard(
    "guard_nested_helper_return_changed-p72",
    P72,
    NESTED_RETURNS,
    _m_nested_return_changed,
    1,
)
_guard("guard_assert_reordered-auth", AUTH, REP_AUTH, _swap(ast.Assert), 1)
_guard("guard_assert_reordered-p72", P72, NESTED_RETURNS, _swap(ast.Assert), 1)
_guard("guard_return_reordered-p72", P72, REORDER_RETURNS, _swap(ast.Return), 1)
_guard("guard_return_reordered-nested", P72, NESTED_RETURNS, _swap(ast.Return), 1)
_guard(
    "guard_argument_changed_in_assert-auth", AUTH, CALL_IN_ASSERT, _m_arg_in_assert, 1
)
_guard("guard_argument_changed_in_assert-p72", P72, NESTED_RETURNS, _m_arg_in_assert, 1)
_guard(
    "guard_argument_changed_in_selected_call-auth",
    AUTH,
    SELECTED_WITH_ARGS,
    _m_arg_in_selected,
    1,
)
_guard(
    "guard_argument_changed_in_selected_call-p72",
    P72,
    ZERO_ASSERT,
    _m_arg_in_selected,
    1,
)
_guard("guard_argument_changed_in_return-p72", P72, NESTED_RETURNS, _m_arg_in_return, 1)
_guard(
    "guard_argument_changed_in_return-checkpoint",
    P72,
    REORDER_RETURNS,
    _m_arg_in_return,
    1,
)

# ordinary call arguments outside protected nodes pass
_guard("guard_ordinary_call_argument_changed-auth", AUTH, REP_AUTH, _m_free_arg, 0)
_guard("guard_ordinary_call_argument_changed-p72", P72, REP_P72, _m_free_arg, 0)
_guard(
    "guard_ordinary_call_argument_changed-nested_returns",
    P72,
    NESTED_RETURNS,
    _m_free_arg,
    0,
)
for _index in range(3):
    _guard(
        f"guard_source_hash_argument_changed-site_{_index}",
        P72,
        "source_hash",
        _m_source_hash_site(_index),
        0,
    )

# new test beside the guards, formatting-only edits
_guard("adjacent_new_test_added-auth", AUTH, REP_AUTH, _m_adjacent_test, 0)
_guard("adjacent_new_test_added-p72_last_in_file", P72, REP_P72, _m_adjacent_test, 0)
_guard("adjacent_new_test_added-zero_assert", P72, ZERO_ASSERT, _m_adjacent_test, 0)
for _mod, _name, _tag in ((AUTH, REP_AUTH, "auth"), (P72, NESTED_RETURNS, "p72")):
    _guard(f"formatting_only_shifted_lines-{_tag}", _mod, _name, _m_shift, 0)
    _guard(f"formatting_only_trailing_comments-{_tag}", _mod, _name, _m_comments, 0)
    _guard(f"formatting_only_blank_lines-{_tag}", _mod, _name, _m_blank_lines, 0)
    _guard(f"formatting_only_reparenthesized-{_tag}", _mod, _name, _m_reparen, 0)

# whole-file permission never overrides guard preservation; scope still applies
add(
    "glob_allowing_every_test_still_protects_guards",
    Case(
        allowed=("tests/*.py",),
        after=_edit_module(P72, _m_assert_changed, REP_P72),
        expected=1,
        offenders=(REP_P72,),
    ),
)
add(
    "formatting_only_edit_of_nonallowed_guard_module",
    Case(
        allowed=(RETRIEVAL,),
        after=_edit_module(AUTH, _m_shift, REP_AUTH),
        expected=1,
        offenders=(AUTH,),
    ),
)
add(
    "dirty_guard_module_at_baseline_new_guard_edit",
    Case(
        allowed=(AUTH,),
        setup=_edit_module(AUTH, _m_shift, REP_AUTH),
        after=_edit_module(AUTH, _m_assert_changed, REP_AUTH),
        expected=1,
        offenders=(REP_AUTH,),
    ),
)
add(
    "dirty_guard_module_at_baseline_formatting_only_again",
    Case(
        allowed=(AUTH,),
        setup=_edit_module(AUTH, _m_shift, REP_AUTH),
        after=_edit_module(AUTH, _m_comments, REP_AUTH),
        expected=0,
    ),
)

# ---- staged protected source: the index is what a commit records ----


def _unstage_delete(rel: str) -> Action:
    """Stage the deletion of ``rel`` and keep the file in the worktree."""

    def act(c: Ctx) -> None:
        _git(c.repo, c.env, "rm", "--cached", "-q", "--", rel)

    return act


def _staged_guard(
    case_id: str,
    mod: str,
    name: str,
    mutation: Mutation,
    expected: int,
    *marks: Any,
) -> None:
    """Stage the mutation, then put the worktree bytes back to HEAD."""
    offender = name if expected == 1 else mod
    add(
        case_id,
        Case(
            allowed=(mod,),
            after=_both(_edit_module(mod, mutation, name), _stage(mod), _restore(mod)),
            expected=expected,
            offenders=(offender,) if expected else (),
        ),
        *marks,
    )


_staged_guard("staged_guard_assert_changed-auth", AUTH, REP_AUTH, _m_assert_changed, 1)
_staged_guard("staged_guard_assert_changed-p72", P72, REP_P72, _m_assert_changed, 1)
_staged_guard("staged_guard_assert_removed-p72", P72, REP_P72, _m_assert_removed, 1)
_staged_guard("staged_guard_return_added-zero", P72, ZERO_ASSERT, _m_return_added, 1)
_staged_guard("staged_guard_skip_added-auth", AUTH, REP_AUTH, _m_skip_added, 1)
_staged_guard(
    "staged_guard_selected_call_removed-auth",
    AUTH,
    SELECTED_WITH_ARGS,
    _m_selected_removed,
    1,
)
_staged_guard(
    "staged_guard_assert_reordered-auth", AUTH, REP_AUTH, _swap(ast.Assert), 1
)
_staged_guard(
    "staged_guard_return_reordered-p72", P72, REORDER_RETURNS, _swap(ast.Return), 1
)
_staged_guard(
    "staged_guard_argument_changed_in_assert-auth",
    AUTH,
    CALL_IN_ASSERT,
    _m_arg_in_assert,
    1,
)
_staged_guard("staged_guard_deleted-p72", P72, REP_P72, _m_missing, 1)
_staged_guard("staged_guard_duplicated-auth", AUTH, REP_AUTH, _m_duplicate, 1)
_staged_guard("staged_guard_syntax_error-p72", P72, REP_P72, _m_syntax_error, 2)
_staged_guard("staged_ordinary_argument_changed-auth", AUTH, REP_AUTH, _m_free_arg, 0)
_staged_guard("staged_ordinary_argument_changed-p72", P72, REP_P72, _m_free_arg, 0)
_staged_guard("staged_adjacent_new_test-auth", AUTH, REP_AUTH, _m_adjacent_test, 0)
_staged_guard("staged_formatting_only-p72", P72, NESTED_RETURNS, _m_reparen, 0)
add(
    "staged_module_deleted_from_index_file_kept",
    Case(
        allowed=(AUTH,),
        after=_unstage_delete(AUTH),
        expected=1,
        offenders=(AUTH,),
    ),
)

# ---- unusable protected source ----

add(
    "check_protected_source_syntax_error",
    Case(
        allowed=(P72,),
        after=_edit_module(P72, _m_syntax_error, REP_P72),
        expected=2,
        offenders=(P72,),
    ),
)
add(
    "check_protected_source_nul_byte",
    Case(
        allowed=(P72,),
        after=_edit_bytes(P72, _raw(b"\n# \x00\n")),
        expected=2,
        offenders=(P72,),
    ),
)
add(
    "check_protected_source_invalid_utf8",
    Case(
        allowed=(P72,),
        after=_edit_bytes(P72, _raw(b'\nscope_gate_bad = "\xff"\n')),
        expected=2,
        offenders=(P72,),
    ),
)
add(
    "check_protected_source_unreadable",
    Case(
        allowed=(P72,),
        after=lambda c: (c.repo / P72).chmod(0),
        expected=2,
        offenders=(P72,),
    ),
    posix_nonroot,
)
_guard(
    "check_protected_source_depth_dump",
    AUTH,
    REP_AUTH,
    lambda src, name: _insert_first(src, name, b"assert " + b"+".join([b"1"] * 1000)),
    2,
)
add(
    "check_protected_source_depth_parse",
    Case(
        allowed=(AUTH,),
        after=_edit_bytes(AUTH, _raw(b"\nx=" + b"+".join([b"1"] * 10000) + b"\n")),
        expected=2,
        offenders=(AUTH,),
    ),
)
add(
    "record_protected_source_depth_parse",
    Case(
        setup=_edit_bytes(AUTH, _raw(b"\nx=" + b"+".join([b"1"] * 10000) + b"\n")),
        record_expected=2,
        record_offenders=(AUTH,),
    ),
)
add(
    "record_protected_source_depth_dump",
    Case(
        setup=_edit_module(
            AUTH,
            lambda src, name: _insert_first(
                src, name, b"assert " + b"+".join([b"1"] * 1000)
            ),
            REP_AUTH,
        ),
        record_expected=2,
        record_offenders=(REP_AUTH,),
    ),
)
add(
    "snapshot_oracle_detects_index_rewrite",
    Case(setup=_assert_oracle_sees_index_rewrite, expected=0),
)
add(
    "record_protected_source_syntax_error",
    Case(
        setup=_edit_module(P72, _m_syntax_error, REP_P72),
        record_expected=2,
        record_offenders=(P72,),
    ),
)
add(
    "record_protected_source_nul_byte",
    Case(
        setup=_edit_bytes(P72, _raw(b"\n# \x00\n")),
        record_expected=2,
        record_offenders=(P72,),
    ),
)
add(
    "record_protected_source_invalid_utf8",
    Case(
        setup=_edit_bytes(AUTH, _raw(b'\nscope_gate_bad = "\xff"\n')),
        record_expected=2,
        record_offenders=(AUTH,),
    ),
)
add(
    "record_protected_source_unreadable",
    Case(
        setup=lambda c: (c.repo / AUTH).chmod(0),
        record_expected=2,
        record_offenders=(AUTH,),
    ),
    posix_nonroot,
)
add(
    "record_protected_module_missing",
    Case(setup=_remove(AUTH), record_expected=2, record_offenders=(AUTH,)),
)
add(
    "record_guard_definition_missing",
    Case(
        setup=_edit_module(P72, _m_missing, REP_P72),
        record_expected=2,
        record_offenders=(REP_P72,),
    ),
)
add(
    "record_guard_definition_duplicated",
    Case(
        setup=_edit_module(AUTH, _m_duplicate, REP_AUTH),
        record_expected=2,
        record_offenders=(REP_AUTH,),
    ),
)

# ---- Git filenames: NUL-delimited data, never split or unquoted ----

_UNUSUAL: list[tuple[str, str, tuple[Any, ...]]] = [
    ("space", "dir with space/file name.txt", ()),
    ("zero_width_cf", "zero\u200bwidth.txt", ()),
    ("leading_dash", "-dash.txt", ()),
    ("newline", "new\nline.txt", (posix_only,)),
    ("control_cc", "ctl\x01char.txt", (posix_only,)),
    ("tab", "tab\tname.txt", (posix_only,)),
    ("double_quote", '"quoted".txt', (posix_only,)),
    ("arrow", "a -> b.txt", (posix_only,)),
    ("leading_space", " lead.txt", (posix_only,)),
]
for _tag, _fname, _marks in _UNUSUAL:
    add(
        f"unusual_name-{_tag}-unchanged_baseline",
        Case(setup=_create(_fname), after=_append(RETRIEVAL), expected=0),
        *_marks,
    )
    add(
        f"unusual_name-{_tag}-modified",
        Case(
            setup=_create(_fname),
            after=_append(_fname, "more\n"),
            expected=1,
            offenders=(_fname,),
        ),
        *_marks,
    )
    add(
        f"unusual_name-{_tag}-new_sibling",
        Case(
            setup=_create(_fname),
            after=_create(_fname + ".new"),
            expected=1,
            offenders=(_fname + ".new",),
        ),
        *_marks,
    )
    add(
        f"unusual_name-{_tag}-deleted",
        Case(
            setup=_create(_fname),
            after=_remove(_fname),
            expected=1,
            offenders=(_fname,),
        ),
        *_marks,
    )

# ---- symlinks: hashed as links, never followed ----


def _symlink(rel: str, target: str | Callable[[Ctx], str]) -> Action:
    def act(c: Ctx) -> None:
        path = c.repo / rel
        if path.is_symlink() or path.exists():
            path.unlink()
        os.symlink(target(c) if callable(target) else target, path)

    return act


def _outside_file(data: bytes) -> Action:
    return lambda c: (c.outside / "target.txt").write_bytes(data)


add(
    "symlink_replaces_regular_nonallowed_file",
    Case(
        setup=_append(CONSOLIDATION),
        after=_both(_remove(CONSOLIDATION), _symlink(CONSOLIDATION, README)),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
    posix_only,
)
add(
    "symlink_target_text_changed_nonallowed",
    Case(
        setup=_symlink("link_a", README),
        after=_symlink("link_a", NOTES),
        expected=1,
        offenders=("link_a",),
    ),
    posix_only,
)
add(
    "symlink_outside_target_bytes_not_followed",
    Case(
        setup=_both(
            _outside_file(b"first\n"),
            _symlink("link_out", lambda c: str(c.outside / "target.txt")),
        ),
        after=_outside_file(b"second\n"),
        expected=0,
    ),
    posix_only,
)
add(
    "symlink_dangling_recorded",
    Case(
        setup=_symlink("link_gone", "no_such_target"),
        after=_append(RETRIEVAL),
        expected=0,
    ),
    posix_only,
)
add(
    "symlink_loop_in_worktree_recorded",
    Case(setup=_symlink("loop_a", "loop_a"), after=_append(RETRIEVAL), expected=0),
    posix_only,
)
add(
    "symlink_to_directory_recorded_as_link",
    Case(setup=_symlink("link_dir", "docs"), after=_append(RETRIEVAL), expected=0),
    posix_only,
)
add(
    "symlink_replaced_by_regular_file",
    Case(
        setup=_symlink("link_a", README),
        after=_both(_remove("link_a"), _create("link_a", "now a file\n")),
        expected=1,
        offenders=("link_a",),
    ),
    posix_only,
)
add(
    "staged_module_replaced_by_symlink_file_restored",
    Case(
        allowed=(AUTH,),
        after=_both(
            _symlink(AUTH, README),
            _stage(AUTH),
            _remove(AUTH),
            _restore(AUTH),
        ),
        expected=1,
        offenders=(AUTH,),
    ),
    posix_only,
)

# ---- repository-configured Git callbacks never run ----

add(
    "git_callbacks_check_unchanged_tree_runs_none",
    Case(
        setup=_arm_git_callbacks,
        after=_reset_callbacks,
        expected=0,
        post=_assert_no_callbacks,
    ),
    posix_only,
)
add(
    "git_callbacks_rejected_record_runs_none",
    Case(
        setup=_both(_arm_git_callbacks, _remove(AUTH)),
        record_expected=2,
        record_offenders=(AUTH,),
        post=_assert_no_callbacks,
    ),
    posix_only,
)
add(
    "git_lazy_fetch_check_missing_staged_blob_runs_no_helper",
    Case(
        allowed=(AUTH,),
        after=_both(
            _append(AUTH),
            _stage(AUTH),
            _delete_object(f":{AUTH}"),
            _arm_lazy_fetch,
        ),
        expected=2,
        offenders=("cat-file",),
        post=_assert_no_callbacks,
    ),
    posix_only,
)
add(
    "git_lazy_fetch_rejected_record_missing_head_tree_runs_no_helper",
    Case(
        setup=_both(_delete_object("HEAD^{tree}"), _arm_lazy_fetch),
        record_expected=2,
        record_offenders=("git status",),
        post=_assert_no_callbacks,
    ),
    posix_only,
)

# ---- a dirty Gitlink is hashed by its contents ----

add(
    "gitlink_dirty_unchanged_contents_passes",
    Case(setup=_dirty_gitlink, after=_append(RETRIEVAL), expected=0),
)
add(
    "gitlink_dirty_changed_contents_outside_allowed",
    Case(
        setup=_dirty_gitlink,
        after=_change_gitlink,
        expected=1,
        offenders=("vendor/lib",),
    ),
)

# ---- allowed operands ----

add(
    "operand_absolute_inside_repository_refused",
    Case(
        check_argv=lambda c: [
            "check",
            "--baseline",
            str(c.out),
            "--allowed",
            str(c.repo / RETRIEVAL),
        ],
        expected=2,
        offenders=(RETRIEVAL,),
    ),
)
add(
    "operand_absolute_outside_repository_refused",
    Case(
        check_argv=lambda c: [
            "check",
            "--baseline",
            str(c.out),
            "--allowed",
            str(c.outside / "x.py"),
        ],
        expected=2,
        offenders=("x.py",),
    ),
)
add(
    "operand_parent_traversal_refused",
    Case(
        check_argv=lambda c: [
            "check",
            "--baseline",
            str(c.out),
            "--allowed",
            "../x.py",
        ],
        expected=2,
        offenders=("../x.py",),
    ),
)
add(
    "operand_embedded_traversal_escaping_refused",
    Case(
        check_argv=lambda c: [
            "check",
            "--baseline",
            str(c.out),
            "--allowed",
            RETRIEVAL,
            "src/../../x.py",
        ],
        expected=2,
        offenders=("src/../../x.py",),
    ),
)

# ---- command line ----


def _argv(*parts: str) -> Callable[[Ctx], list[str]]:
    def build(c: Ctx) -> list[str]:
        return [p.replace("{out}", str(c.out)) for p in parts]

    return build


for _tag, _parts, _offender in (
    ("no_subcommand", (), "arguments are required: command"),
    ("unknown_subcommand", ("bogus",), "bogus"),
    ("missing_task_and_out", ("record",), "--task"),
    ("missing_out", ("record", "--task", TASK), "--out"),
    ("missing_task", ("record", "--out", "{out}"), "--task"),
    (
        "unsupported_option",
        ("record", "--task", TASK, "--out", "{out}", "--bogus"),
        "--bogus",
    ),
    (
        "allowed_is_not_a_record_option",
        ("record", "--task", TASK, "--out", "{out}", "--allowed", "x"),
        "--allowed",
    ),
    (
        "baseline_is_not_a_record_option",
        ("record", "--task", TASK, "--out", "{out}", "--baseline", "x"),
        "--baseline",
    ),
):
    add(
        f"cli_record_{_tag}",
        Case(
            record_argv=_argv(*_parts), record_expected=2, record_offenders=(_offender,)
        ),
    )
for _ctag, _cparts, _coffender in (
    ("no_arguments", ("check",), "--baseline"),
    ("missing_allowed", ("check", "--baseline", "{out}"), "--allowed"),
    ("missing_baseline", ("check", "--allowed", "a.py"), "--baseline"),
    (
        "allowed_without_operand",
        ("check", "--baseline", "{out}", "--allowed"),
        "--allowed",
    ),
    (
        "unsupported_option",
        ("check", "--baseline", "{out}", "--allowed", "a.py", "--bogus"),
        "--bogus",
    ),
    (
        "out_is_not_a_check_option",
        ("check", "--baseline", "{out}", "--allowed", "a.py", "--out", "x"),
        "--out",
    ),
    (
        "task_is_not_a_check_option",
        ("check", "--baseline", "{out}", "--allowed", "a.py", "--task", "t"),
        "--task",
    ),
):
    add(
        f"cli_check_{_ctag}",
        Case(check_argv=_argv(*_cparts), expected=2, offenders=(_coffender,)),
    )
add(
    "cli_check_allowed_before_baseline",
    Case(
        check_argv=_argv("check", "--allowed", RETRIEVAL, "--baseline", "{out}"),
        expected=0,
    ),
)

# ---- unusable baseline and output paths ----

add(
    "baseline_file_missing",
    Case(
        check_argv=lambda c: [
            "check",
            "--baseline",
            str(c.out_dir / "absent.json"),
            "--allowed",
            RETRIEVAL,
        ],
        expected=2,
        offenders=("absent.json",),
    ),
)
add(
    "baseline_path_is_a_directory",
    Case(
        check_argv=lambda c: [
            "check",
            "--baseline",
            str(c.out_dir),
            "--allowed",
            RETRIEVAL,
        ],
        expected=2,
        offenders=("baselines",),
    ),
)
add(
    "baseline_path_is_empty_string",
    Case(
        check_argv=_argv("check", "--baseline", "", "--allowed", RETRIEVAL),
        expected=2,
        offenders=('cannot read baseline ""',),
    ),
)
add(
    "baseline_path_symlink_loop",
    Case(
        setup=lambda c: os.symlink("loop", c.work / "loop"),
        check_argv=lambda c: [
            "check",
            "--baseline",
            str(c.work / "loop"),
            "--allowed",
            RETRIEVAL,
        ],
        expected=2,
        offenders=("loop",),
    ),
    posix_only,
)
add(
    "record_out_is_an_existing_directory",
    Case(
        record_argv=lambda c: ["record", "--task", TASK, "--out", str(c.out_dir)],
        record_expected=2,
        record_offenders=("baselines",),
    ),
)
add(
    "record_out_parent_is_a_regular_file",
    Case(
        setup=lambda c: (c.work / "afile").write_text("x"),
        record_argv=lambda c: [
            "record",
            "--task",
            TASK,
            "--out",
            str(c.work / "afile" / "b.json"),
        ],
        record_expected=2,
        record_offenders=("afile",),
    ),
)
add(
    "record_out_parent_symlink_loop",
    Case(
        setup=lambda c: os.symlink("loop", c.work / "loop"),
        record_argv=lambda c: [
            "record",
            "--task",
            TASK,
            "--out",
            str(c.work / "loop" / "b.json"),
        ],
        record_expected=2,
        record_offenders=("loop",),
    ),
    posix_only,
)

# ---- Git failure, other repository, moved repository ----

add(
    "record_outside_a_git_repository",
    Case(
        setup=lambda c: (c.work / "nogit").mkdir(),
        record_cwd=lambda c: c.work / "nogit",
        record_expected=2,
        record_offenders=("nogit",),
    ),
)
add(
    "check_outside_a_git_repository",
    Case(
        setup=lambda c: (c.work / "nogit").mkdir(),
        check_cwd=lambda c: c.work / "nogit",
        expected=2,
        offenders=("nogit",),
    ),
)
add(
    "record_with_corrupt_git_index",
    Case(
        setup=lambda c: (c.repo / ".git" / "index").write_bytes(b"not an index"),
        record_expected=2,
        record_offenders=("index",),
    ),
)
add(
    "record_with_corrupt_git_head",
    Case(
        setup=lambda c: (c.repo / ".git" / "HEAD").write_bytes(b"not a head"),
        record_expected=2,
        record_offenders=("repo_case",),
    ),
)
add(
    "check_with_corrupt_git_index",
    Case(
        after=lambda c: (c.repo / ".git" / "index").write_bytes(b"not an index"),
        expected=2,
        offenders=("index",),
    ),
)
add(
    "check_with_corrupt_git_head",
    Case(
        after=lambda c: (c.repo / ".git" / "HEAD").write_bytes(b"not a head"),
        expected=2,
        offenders=("repo_case",),
    ),
)


def _copy_repo(c: Ctx) -> None:
    c.other = c.work / "other_case"
    shutil.copytree(c.repo, c.other, symlinks=True)


def _move_repo(c: Ctx) -> None:
    moved = c.work / "moved_case"
    c.repo.rename(moved)
    c.repo = moved


def _alias_symlink(c: Ctx) -> Path:
    link = c.work / "alias_link"
    if not link.exists():
        os.symlink(c.repo, link)
    return link


add(
    "baseline_from_a_different_repository",
    Case(
        after=_copy_repo,
        check_cwd=lambda c: c.other or c.repo,
        expected=2,
        offenders=("repo_case",),
    ),
)
add(
    "baseline_after_the_repository_moved",
    Case(after=_move_repo, expected=2, offenders=("repo_case",)),
)
add(
    "same_root_spelled_with_dotdot_alias",
    Case(check_cwd=lambda c: c.repo / ".." / c.repo.name, expected=0),
)
add(
    "same_root_through_a_symlink_alias",
    Case(
        setup=lambda c: _alias_symlink(c),
        check_cwd=lambda c: c.work / "alias_link",
        after=_append(RETRIEVAL),
        expected=0,
    ),
    posix_only,
)
add(
    "record_through_a_symlink_alias_check_real_root",
    Case(
        setup=lambda c: _alias_symlink(c),
        record_cwd=lambda c: c.work / "alias_link",
        after=_append(RETRIEVAL),
        expected=0,
    ),
    posix_only,
)
add(
    "same_root_through_a_symlink_alias_nonallowed_change",
    Case(
        setup=lambda c: _alias_symlink(c),
        check_cwd=lambda c: c.work / "alias_link",
        after=_append(CONSOLIDATION),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
    posix_only,
)

# ---- corrupt baseline documents ----

_HUGE = "1" + "0" * 5000
_SHAPES: dict[str, Any] = {
    "null": None,
    "int": 7,
    "bool": True,
    "huge_int": "__HUGE__",
    "nan": "__NAN__",
    "inf": "__INF__",
    "float": 1.5,
    "str": "x",
    "list": [],
    "nested_list": [[]],
    "dict": {},
    "nested_dict": {"a": []},
    "short_list": [1],
    "long_list": [1, 2, 3],
    "str_pair": ["1", "2"],
    "bool_pair": [True, True],
    "negative_pair": [-1, 5],
    "float_pair": [1.0, 2.0],
    "null_pair": [None, None],
    "huge_pair": ["__HUGE__", 1],
    "nan_pair": ["__NAN__", 1],
}
_SCALARS = ("null", "int", "bool", "huge_int", "nan", "inf", "float")
_NOT_STR = (*_SCALARS, "list", "nested_list", "dict", "nested_dict")
_NOT_CONTAINER = (*_SCALARS, "str")
_NOT_LIST = (*_SCALARS, "str", "dict", "nested_dict")
_BAD_IDENTITY = (
    *_NOT_LIST,
    "list",
    "nested_list",
    "short_list",
    "long_list",
    "str_pair",
    "bool_pair",
    "negative_pair",
    "float_pair",
    "null_pair",
    "huge_pair",
    "nan_pair",
)


def _dump(doc: Any) -> bytes:
    text = json.dumps(doc, allow_nan=True)
    for token, raw in (
        ('"__HUGE__"', _HUGE),
        ('"__NAN__"', "NaN"),
        ('"__INF__"', "Infinity"),
    ):
        text = text.replace(token, raw)
    return text.encode("utf-8")


def _first_path(
    doc: Any, predicate: Callable[[Any], bool], what: str
) -> tuple[Any, ...]:
    for path, node in _walk(doc):
        if path and predicate(node):
            return path
    raise AssertionError(f"baseline holds no {what}")


def _loc_task(c: Ctx, doc: Any) -> tuple[Any, ...]:
    return _first_path(doc, lambda n: n == TASK, "task id string")


def _loc_root(c: Ctx, doc: Any) -> tuple[Any, ...]:
    return _first_path(
        doc,
        lambda n: (
            isinstance(n, str)
            and os.path.isabs(n)
            and Path(n.rstrip("/\\")).name == c.repo.name
        ),
        "absolute repository root string",
    )


def _loc_identity(c: Ctx, doc: Any) -> tuple[Any, ...]:
    st = os.stat(c.repo)
    return _first_path(
        doc, lambda n: n == [st.st_dev, st.st_ino], "repository identity pair"
    )


def _loc_pathmap(c: Ctx, doc: Any) -> tuple[Any, ...]:
    digest = hashlib.sha256((c.repo / CONSOLIDATION).read_bytes()).hexdigest()
    best: tuple[Any, ...] | None = None
    for path, node in _walk(doc):
        direct = (
            isinstance(node, dict)
            and (CONSOLIDATION in node or CONSOLIDATION in node.values())
        ) or (isinstance(node, list) and CONSOLIDATION in node)
        if (
            path
            and direct
            and digest in _strings(node)
            and (best is None or len(path) > len(best))
        ):
            best = path
    assert best is not None, "baseline holds no path snapshot for a dirty path"
    return best


def _loc_entry(c: Ctx, doc: Any) -> tuple[Any, ...]:
    expected = _guard_lists(c.repo)[(AUTH, REP_AUTH)]
    for path, node in _entry_candidates(doc, REP_AUTH):
        if path and _has_lists(node, expected):
            return path
    raise AssertionError("baseline holds no guard entry")


def _loc_ast_list(c: Ctx, doc: Any) -> tuple[Any, ...]:
    entry = _loc_entry(c, doc)
    asserts = _guard_lists(c.repo)[(AUTH, REP_AUTH)][0]
    for rel, node in _walk(_get(doc, entry)):
        if node == asserts:
            return (*entry, *rel)
    raise AssertionError("guard entry holds no assert list")


def _loc_element(c: Ctx, doc: Any) -> tuple[Any, ...]:
    return (*_loc_ast_list(c, doc), 0)


def _offender_keys(path: tuple[Any, ...], *extra: str) -> tuple[str, ...]:
    return (*[p for p in path if isinstance(p, str)], *extra)


# shapes the JSON parser itself refuses, so the refusal names the parser's detail
_UNPARSEABLE = {
    "huge_int": "digits",
    "huge_pair": "digits",
    "nan": "constant NaN",
    "nan_pair": "constant NaN",
    "inf": "constant Infinity",
}


def _corrupt(
    locate: Callable[[Ctx, Any], tuple[Any, ...]], shape: str, extra: tuple[str, ...]
) -> Callable[[Ctx, Any], Edit]:
    def edit(c: Ctx, doc: Any) -> Edit:
        path = locate(c, doc)
        _get(doc, path[:-1])[path[-1]] = _SHAPES[shape]
        if shape in _UNPARSEABLE:
            return Edit(_dump(doc), (_UNPARSEABLE[shape],))
        return Edit(_dump(doc), _offender_keys(path, *extra))

    return edit


def _delete(
    locate: Callable[[Ctx, Any], tuple[Any, ...]],
) -> Callable[[Ctx, Any], Edit]:
    def edit(c: Ctx, doc: Any) -> Edit:
        path = locate(c, doc)
        del _get(doc, path[:-1])[path[-1]]
        return Edit(_dump(doc), _offender_keys(path, REP_AUTH))

    return edit


def _dirty_consolidation(c: Ctx) -> None:
    _append(CONSOLIDATION)(c)


for _target, _locate, _shapes, _extra in (
    ("task", _loc_task, _NOT_STR, ()),
    ("repository_root", _loc_root, _NOT_STR, ("absolute path string",)),
    ("repository_identity", _loc_identity, _BAD_IDENTITY, ()),
    ("path_snapshots", _loc_pathmap, _NOT_CONTAINER, (CONSOLIDATION,)),
    ("guard_entry", _loc_entry, _NOT_CONTAINER, (REP_AUTH,)),
    ("guard_ast_list", _loc_ast_list, _NOT_LIST, (REP_AUTH,)),
    ("guard_ast_list_element", _loc_element, _NOT_STR, (REP_AUTH,)),
):
    for _shape in _shapes:
        add(
            f"baseline_wrong_type-{_target}-{_shape}",
            Case(
                setup=_dirty_consolidation,
                edit=_corrupt(_locate, _shape, _extra),
                expected=2,
            ),
        )
for _shape in ("list", "dict"):
    add(
        f"baseline_snapshot_type-{_shape}",
        Case(
            setup=_dirty_consolidation,
            edit=_corrupt(
                lambda c, d: (*_loc_pathmap(c, d), CONSOLIDATION, "type"),
                _shape,
                (CONSOLIDATION,),
            ),
            expected=2,
        ),
    )
add(
    "baseline_incomplete_inventory-repository_identity_removed",
    Case(setup=_dirty_consolidation, edit=_delete(_loc_identity), expected=2),
)
add(
    "baseline_incomplete_inventory-guard_entry_removed",
    Case(setup=_dirty_consolidation, edit=_delete(_loc_entry), expected=2),
)
add(
    "baseline_incomplete_inventory-guard_ast_list_removed",
    Case(setup=_dirty_consolidation, edit=_delete(_loc_ast_list), expected=2),
)


def _rename_strings(node: Any, old: str, new: str) -> Any:
    if isinstance(node, str):
        return node.replace(old, new)
    if isinstance(node, list):
        return [_rename_strings(n, old, new) for n in node]
    if isinstance(node, dict):
        return {
            _rename_strings(k, old, new): _rename_strings(v, old, new)
            for k, v in node.items()
        }
    return node


def _bad_pathname(replacement: str) -> Callable[[Ctx, Any], Edit]:
    def edit(c: Ctx, doc: Any) -> Edit:
        bad = CONSOLIDATION.replace("consolidation", replacement)
        return Edit(_dump(_rename_strings(doc, CONSOLIDATION, bad)), (bad,))

    return edit


add(
    "baseline_pathname_with_nul",
    Case(
        setup=_dirty_consolidation, edit=_bad_pathname("consoli\x00dation"), expected=2
    ),
)
add(
    "baseline_pathname_with_lone_surrogate",
    Case(
        setup=_dirty_consolidation,
        edit=_bad_pathname("consoli\ud800dation"),
        expected=2,
    ),
)


def _edit_root(rewrite: Callable[[Path], str]) -> Callable[[Ctx, Any], Edit]:
    def edit(c: Ctx, doc: Any) -> Edit:
        path = _loc_root(c, doc)
        original = _get(doc, path)
        new = rewrite(Path(original))
        _get(doc, path[:-1])[path[-1]] = new
        return Edit(_dump(doc), (new,))

    return edit


def _case_variant_expected(c: Ctx) -> int:
    variant = c.repo.with_name(c.repo.name.swapcase())
    try:
        same = variant.exists() and os.path.samefile(variant, c.repo)
    except OSError:
        same = False
    return 0 if same else 2


add(
    "baseline_root_names_a_missing_directory",
    Case(edit=_edit_root(lambda p: str(p) + "_missing"), expected=2),
)
add(
    "baseline_root_lone_surrogate",
    Case(edit=_edit_root(lambda p: str(p) + "/\ud800"), expected=2),
)
add(
    "baseline_root_case_variant_follows_the_filesystem",
    Case(
        edit=_edit_root(lambda p: str(p.with_name(p.name.swapcase()))),
        expected=_case_variant_expected,
    ),
)


def _raw_edit(
    transform: Callable[[bytes], bytes], detail: str
) -> Callable[[Ctx, Any], Edit]:
    def edit(c: Ctx, doc: Any) -> Edit:
        return Edit(transform(c.out.read_bytes()), (detail,))

    return edit


# tag -> (byte transform, the detail the real refusal names for that damage)
_RAW: dict[str, tuple[Callable[[bytes], bytes], str]] = {
    "utf8_bom": (lambda b: b"\xef\xbb\xbf" + b, "UTF-8 BOM"),
    "utf16": (lambda b: b.decode("utf-8").encode("utf-16"), "0xff"),
    "invalid_utf8": (lambda b: b[:1] + b'"\xff":1,' + b[1:], "0xff"),
    "truncated": (lambda b: b[: len(b) // 2], "not a JSON document"),
    "empty": (lambda b: b"", "Expecting value"),
    "whitespace_only": (lambda b: b" \n ", "Expecting value"),
    "top_level_array": (lambda b: b"[]", "top level"),
    "top_level_null": (lambda b: b"null", "top level"),
    "top_level_number": (lambda b: b"1", "top level"),
    "top_level_string": (lambda b: b'"x"', "top level"),
    "trailing_garbage": (lambda b: b + b" x", "Extra data"),
    "two_documents": (lambda b: b + b, "Extra data"),
    "trailing_nul": (lambda b: b + b"\x00", "Extra data"),
    "nan_constant_in_unknown_key": (
        lambda b: b.rstrip()[:-1] + b', "zz": NaN}',
        "constant NaN",
    ),
    "infinity_constant_in_unknown_key": (
        lambda b: b.rstrip()[:-1] + b', "zz": Infinity}',
        "constant Infinity",
    ),
    "negative_infinity_constant_in_unknown_key": (
        lambda b: b.rstrip()[:-1] + b', "zz": -Infinity}',
        "constant -Infinity",
    ),
}
for _tag, (_transform, _detail) in _RAW.items():
    add(
        f"baseline_bytes-{_tag}",
        Case(
            setup=_dirty_consolidation,
            edit=_raw_edit(_transform, _detail),
            expected=2,
        ),
    )


# --------------------------------------------------------------------------
# repository root: the exact pathname, and the repository identity
# --------------------------------------------------------------------------


def _rename_root(suffix: str) -> Action:
    def act(c: Ctx) -> None:
        renamed = c.work / (c.repo.name + suffix)
        c.repo.rename(renamed)
        c.repo = renamed

    return act


def _root_with_populated_stripped_sibling(c: Ctx) -> None:
    """A populated clean repository sits at the root's name without its LF."""
    shutil.copytree(c.repo, c.work / (c.repo.name + "_lf"), symlinks=True)
    _rename_root("_lf\n")(c)
    _append(CONSOLIDATION)(c)


def _replace_repo(c: Ctx) -> None:
    """Swap a byte-identical copy into the recorded pathname."""
    replacement = c.work / "replacement_case"
    shutil.copytree(c.repo, replacement, symlinks=True)
    c.repo.rename(c.work / "original_case")
    replacement.rename(c.repo)


add(
    "root_trailing_lf_preserves_scope",
    Case(
        setup=_root_with_populated_stripped_sibling,
        after=_append(CONSOLIDATION, "# again\n"),
        expected=1,
        offenders=(CONSOLIDATION,),
    ),
    posix_only,
)
for _tag, _suffix in (("lf", "\n"), ("cr", "\r"), ("crlf", "\r\n")):
    add(
        f"root_suffix-{_tag}",
        Case(setup=_rename_root(_suffix), after=_append(RETRIEVAL), expected=0),
        posix_only,
    )
add(
    "baseline_repository_replaced_at_the_same_pathname",
    Case(after=_replace_repo, expected=2, offenders=("repo_case", "was replaced")),
)


# --------------------------------------------------------------------------
# in-process siblings: behavior a darwin subprocess cannot reach
# --------------------------------------------------------------------------


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location("scope_gate_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scope_gate_windows_baseline_path_refused(
    _c: Ctx, monkeypatch: pytest.MonkeyPatch, rel: str
) -> None:
    """Windows path semantics (ntpath, backslash separator) refuse every escape."""
    module = _load_script()
    monkeypatch.setattr(module, "os", types.SimpleNamespace(path=ntpath, sep="\\"))
    with pytest.raises(module.GateError):
        module._valid_rel(rel, "baseline paths")


def _scope_gate_windows_baseline_path_accepts_git_spelling(
    _c: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    monkeypatch.setattr(module, "os", types.SimpleNamespace(path=ntpath, sep="\\"))
    assert module._valid_rel("src/rush/x.py", "baseline paths") == "src/rush/x.py"


def _scope_gate_posix_baseline_path_keeps_literal_backslash(
    _c: Ctx, _monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    assert module._valid_rel("a\\b.txt", "baseline paths") == "a\\b.txt"


def _scope_gate_record_cleanup_failure_is_a_gate_error(
    c: Ctx, monkeypatch: pytest.MonkeyPatch, publish_fails: bool
) -> None:
    module = _load_script()

    def deny_unlink(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("cleanup denied")

    def deny_link(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("publish denied")

    class FailingOs:
        unlink = staticmethod(deny_unlink)
        if publish_fails:
            link = staticmethod(deny_link)

        def __getattr__(self, name: str) -> Any:
            return getattr(os, name)

    monkeypatch.chdir(c.repo)
    monkeypatch.setattr(module, "os", FailingOs())
    with pytest.raises(module.GateError) as caught:
        module._record(TASK, str(c.out))
    message = str(caught.value)
    assert "cleanup denied" in message
    assert ("publish denied" in message) == publish_fails
    assert c.out.exists() != publish_fails


def _toplevel_drops_only_the_output_delimiter(
    _c: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows git writes no CR into a root; only LF ends its output line."""
    module = _load_script()
    monkeypatch.setattr(
        module,
        "os",
        types.SimpleNamespace(name="nt", path=ntpath, fsdecode=os.fsdecode),
    )
    monkeypatch.setattr(module, "_git", lambda *_a: b"C:/work/repo\r\n")
    assert module._toplevel() == ntpath.abspath("C:/work/repo")
    monkeypatch.setattr(
        module,
        "os",
        types.SimpleNamespace(name="posix", path=os.path, fsdecode=os.fsdecode),
    )
    monkeypatch.setattr(module, "_git", lambda *_a: b"/work/repo\r\n")
    assert module._toplevel() == "/work/repo\r"


def _nest(base: Path, depth: int) -> None:
    """``base/n/n/...`` ``depth`` levels deep, with a file at the bottom."""
    leaf = base.joinpath(*["n"] * depth)
    leaf.mkdir(parents=True)
    (leaf / "f.txt").write_text("x\n")


def _stack_depth() -> int:
    depth = 0
    frame: types.FrameType | None = sys._getframe()
    while frame is not None:
        depth, frame = depth + 1, frame.f_back
    return depth


def _snapshot_nesting_is_a_gate_error(c: Ctx, _monkeypatch: pytest.MonkeyPatch) -> None:
    """Directory hashing recurses; running out of stack is a named refusal."""
    module = _load_script()
    _nest(c.work / "deep", 180)
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_stack_depth() + 60)
    try:
        with pytest.raises(module.GateError) as caught:
            module._snapshot(str(c.work), "deep")
    finally:
        sys.setrecursionlimit(limit)
    assert "deep" in str(caught.value) and "recursion limit" in str(caught.value)


def _cli_nesting_exits_2_without_traceback(
    c: Ctx, _monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dirty Gitlink 250 directories deep: record names it and exits 2."""
    _dirty_gitlink(c)
    _nest(c.repo / "vendor" / "lib" / "deep", 250)
    wrapper = (
        "import runpy, sys\n"
        "sys.setrecursionlimit(200)\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-B", "-c", wrapper, str(SCRIPT)]
        + ["record", "--task", TASK, "--out", str(c.out)],
        cwd=c.repo,
        env=c.env,
        capture_output=True,
        timeout=180,
        check=False,
    )
    run = Run(
        proc.returncode, (proc.stdout + b"\n" + proc.stderr).decode("utf-8", "replace")
    )
    _expect(run, 2, ("vendor/lib", "recursion limit"), "record")
    assert not c.out.exists()
    assert list(c.out_dir.iterdir()) == []


for _tag, _rel in (
    ("dotdot_backslash", "..\\secret.txt"),
    ("embedded_dotdot", "safe\\..\\..\\secret.txt"),
    ("drive_relative", "C:secret.txt"),
    ("drive_absolute", "D:\\abs.txt"),
    ("rooted", "\\rooted.txt"),
    ("unc", "\\\\server\\share\\x.txt"),
    ("mixed_separator", "ok/..\\x.txt"),
):
    add(
        f"sibling_windows_baseline_path_refused-{_tag}",
        Case(
            sibling=functools.partial(
                _scope_gate_windows_baseline_path_refused, rel=_rel
            )
        ),
    )
add(
    "sibling_windows_baseline_path_accepts_git_spelling",
    Case(sibling=_scope_gate_windows_baseline_path_accepts_git_spelling),
)
add(
    "sibling_posix_baseline_path_keeps_literal_backslash",
    Case(sibling=_scope_gate_posix_baseline_path_keeps_literal_backslash),
    posix_only,
)
for _publish_fails in (False, True):
    add(
        f"sibling_record_cleanup_failure_is_a_gate_error-publish_fails_{_publish_fails}",
        Case(
            sibling=functools.partial(
                _scope_gate_record_cleanup_failure_is_a_gate_error,
                publish_fails=_publish_fails,
            )
        ),
    )
add(
    "toplevel_windows_output_drops_only_lf",
    Case(sibling=_toplevel_drops_only_the_output_delimiter),
)
add(
    "sibling_snapshot_nesting_is_a_gate_error",
    Case(sibling=_snapshot_nesting_is_a_gate_error),
)
add(
    "sibling_cli_nesting_exits_2_without_traceback",
    Case(sibling=_cli_nesting_exits_2_without_traceback),
    posix_only,
)


# --------------------------------------------------------------------------
# the test
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_scope_gate_preserved_baseline(
    case: Case, ctx: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    if case.sibling:
        case.sibling(ctx, monkeypatch)
        return
    _exercise(case, ctx)
