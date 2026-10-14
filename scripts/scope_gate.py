"""Phase 72 scope gate (plan G14 and G9).

    scope_gate.py record --task <id> --out <baseline.json>
    scope_gate.py check --baseline <baseline.json> --allowed <path-or-glob>...

The repository is the Git worktree containing the current directory.

``record`` stores the task id, the repository root and its device and inode, the raw
``git status --porcelain=v1 -z --untracked-files=all`` bytes, the type and
sha256 of every dirty, staged and untracked path (a symlink is hashed by its
link text, never followed) and, for each of the 30 retained G9 guard functions,
the ordered ``ast.dump`` lists of its Assert nodes, its calls whose callee name
contains ``assert`` or is ``raises``/``skip``/``xfail``/``importorskip``, and
its Return nodes. It publishes only after every input was read and validated,
and never replaces an existing baseline.

``check`` refuses a baseline whose repository is not this directory (a copy
replacing it differs by inode). It then passes only when (1) every recorded or
currently dirty path outside the allowed operands keeps its recorded type and
bytes, (2) every staged path is allowed and (3) every guard exists exactly once
with identical lists, in the worktree and in the staged blob of each staged
protected module. It writes nothing: Git runs with optional locks disabled.

Exit codes: 0 recorded or permitted; 1 scope or protected-AST violation;
2 invalid invocation, baseline or operand, Git failure, or unusable source.
"""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import json
import os
import posixpath
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from typing import Any

PROTECTED: dict[str, tuple[str, ...]] = {
    "tests/test_memory_authorization.py": (
        "test_resolve_overlay_read_requires_overlay_owner",
        "test_nul_byte_paths_raise_only_policy_errors",
        "test_lone_surrogates_rejected_before_lock",
        "test_hold_policy_lock_and_load_reject_unusable_data_roots",
        "test_moved_data_root_keeps_project_grants",
        "test_binding_stale_on_tampered_fingerprint",
        "test_binding_registration_requires_setup_consent",
    ),
    "tests/test_phase72_memory_correctness.py": (
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
LISTS = ("asserts", "calls", "returns")
DOC_KEYS = {"task", "repository", "repository_identity", "status", "paths", "guards"}
HASHED_TYPES = {"regular", "symlink", "directory"}
UNHASHED_TYPES = {"missing", "other"}
_SELECTED_NAMES = frozenset({"raises", "skip", "xfail", "importorskip"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


class GateError(Exception):
    """Invalid input, Git failure or unusable source: exit 2."""


def _q(text: str) -> str:
    return json.dumps(text)


# ---------------------------------------------------------------- Git


_FILTER_KEYS = r"^filter\..*\.(clean|smudge|process|required)$"


def _run_git(
    args: list[str], env: dict[str, str], cwd: str | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, env=env, cwd=cwd, check=False
        )
    except OSError as exc:
        raise GateError(f"cannot run git: {exc}") from exc


def _where(cwd: str | None) -> str:
    """Quoted directory a Git command ran in (the process's own when ``None``)."""
    try:
        return _q(os.getcwd() if cwd is None else cwd)
    except OSError:
        return "the current directory"


def _detail(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stderr.decode("utf-8", "replace").strip()


def _filter_keys(env: dict[str, str], cwd: str | None = None) -> set[str]:
    """Configured filter driver commands of the repository at ``cwd``."""
    proc = _run_git(
        ["config", "--null", "--name-only", "--get-regexp", _FILTER_KEYS], env, cwd
    )
    if proc.returncode not in (0, 1):
        raise GateError(
            f"cannot inspect Git filter configuration in {_where(cwd)}: {_detail(proc)}"
        )
    return {os.fsdecode(key) for key in proc.stdout.split(b"\0") if key}


def _gitlink_filter_keys(env: dict[str, str], top: str) -> set[str]:
    """Filter drivers of every nested repository: ``git status`` runs those too."""
    keys: set[str] = set()
    todo = [top]
    seen: set[str] = set()
    while todo:
        repo = todo.pop()
        if repo in seen:
            continue
        seen.add(repo)
        proc = _run_git(
            ["-c", "core.fsmonitor=false", "ls-files", "--stage", "-z"], env, repo
        )
        if proc.returncode != 0:
            raise GateError(
                "cannot inspect nested Git repositories: git ls-files failed in "
                f"{_where(repo)}: {_detail(proc)}"
            )
        for entry in proc.stdout.split(b"\0"):
            meta, _, name = entry.partition(b"\t")
            sub = os.path.join(repo, os.fsdecode(name))
            if (
                meta.startswith(b"160000 ")
                and not os.path.islink(sub)
                and os.path.isdir(sub)
            ):
                keys |= _filter_keys(env, sub)
                todo.append(sub)
    return keys


def _git(*args: str) -> bytes:
    """Run git with the repository's own executable settings switched off.

    A repository chooses ``core.fsmonitor`` and ``filter.<driver>.clean`` (through
    ``.gitattributes``); both run commands during ``status``. Overriding them with
    ``-c`` also reaches the child ``git status`` of each nested repository, whose
    own filter drivers are collected here.
    """
    # GIT_NO_LAZY_FETCH: a partial clone would otherwise run its configured remote
    # helper (and rewrite the config) to fetch a missing object
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
    keys = _filter_keys(env)
    if args[:1] == ("status",):
        keys |= _gitlink_filter_keys(env, _toplevel())
    overrides = ["-c", "core.fsmonitor=false"]
    for key in sorted(keys):
        if "=" in key:  # `-c` splits at the first "=": the override would miss
            raise GateError(f"cannot disable Git filter {_q(key)}: its name has '='")
        overrides += ["-c", key + ("=false" if key.endswith(".required") else "=")]
    proc = _run_git([*overrides, *args], env)
    if proc.returncode != 0:
        raise GateError(
            f"git {' '.join(args)} failed in {_where(None)}: {_detail(proc)}"
        )
    return proc.stdout


def _toplevel() -> str:
    # only Git's output delimiter goes: a root name may itself end in CR or LF
    out = _git("rev-parse", "--show-toplevel").removesuffix(b"\n")
    if os.name == "nt":  # a Windows path never ends in CR
        out = out.removesuffix(b"\r")
    if not out:
        raise GateError("git reports no repository worktree root")
    return os.path.abspath(os.fsdecode(out))


def _identity(root: str) -> list[int]:
    """Device and inode of the repository root: a replacement directory differs."""
    try:
        st = os.stat(root)
    except OSError as exc:
        raise GateError(f"cannot stat repository {_q(root)}: {exc}") from exc
    return [st.st_dev, st.st_ino]


def _status_paths(status: bytes) -> list[str]:
    """Paths of a NUL-delimited porcelain v1 status, both rename/copy endpoints."""
    parts = status.split(b"\0")
    if parts[-1] != b"":
        raise GateError("git status output is not NUL-terminated")
    paths: list[str] = []
    i = 0
    while i < len(parts) - 1:
        entry = parts[i]
        i += 1
        if len(entry) < 4 or entry[2:3] != b" ":
            raise GateError(f"unparseable git status entry {_q(os.fsdecode(entry))}")
        paths.append(os.fsdecode(entry[3:]))
        if b"R" in entry[:2] or b"C" in entry[:2]:
            if i >= len(parts) - 1 or not parts[i]:
                raise GateError("git status rename entry lacks its source path")
            paths.append(os.fsdecode(parts[i]))
            i += 1
    return paths


def _staged_paths() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--no-renames", "-z")
    return [os.fsdecode(p) for p in out.split(b"\0") if p]


# ---------------------------------------------------------------- snapshots


def _behind_symlink(root: str, rel: str) -> bool:
    """True when a parent directory of ``rel`` is a symlink (Git never follows it)."""
    path = root
    for part in rel.split("/")[:-1]:
        path = os.path.join(path, part)
        try:
            if stat.S_ISLNK(os.lstat(path).st_mode):
                return True
        except OSError:
            return False
    return False


def _snapshot(root: str, rel: str) -> dict[str, str | None]:
    path = os.path.join(root, rel)
    try:
        if _behind_symlink(root, rel):
            return {"type": "missing", "sha256": None}
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            link = os.fsencode(os.readlink(path))
            return {"type": "symlink", "sha256": hashlib.sha256(link).hexdigest()}
        if stat.S_ISDIR(st.st_mode):
            with os.scandir(path) as entries:
                children = [
                    (e.name, _snapshot(root, rel + "/" + e.name))
                    for e in sorted(entries, key=lambda e: os.fsencode(e.name))
                ]
            data = json.dumps(children, separators=(",", ":")).encode("ascii")
            return {"type": "directory", "sha256": hashlib.sha256(data).hexdigest()}
        if not stat.S_ISREG(st.st_mode):
            return {"type": "other", "sha256": None}
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise GateError(f"path {_q(rel)} changed type while being read")
            digest = hashlib.sha256(handle.read()).hexdigest()
        return {"type": "regular", "sha256": digest}
    except (FileNotFoundError, NotADirectoryError):
        return {"type": "missing", "sha256": None}
    except OSError as exc:
        raise GateError(f"cannot read path {_q(rel)}: {exc}") from exc
    except RecursionError as exc:
        raise GateError(
            f"cannot read path {_q(rel)}: directory nesting exceeds Python "
            "recursion limit"
        ) from exc


def _callee(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _selected(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = _callee(node)
    return name is not None and ("assert" in name or name in _SELECTED_NAMES)


def _guard_lists(fn: ast.AST, mod: str) -> dict[str, list[str]]:
    nodes = sorted(
        ast.walk(fn),
        key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)),
    )

    def dumps(keep: Any) -> list[str]:
        try:
            return [ast.dump(n, include_attributes=False) for n in nodes if keep(n)]
        except RecursionError as exc:
            name = getattr(fn, "name", "<anonymous>")
            raise GateError(
                f"protected function {name} in {_q(mod)} is too deeply nested"
            ) from exc

    return {
        "asserts": dumps(lambda n: isinstance(n, ast.Assert)),
        "calls": dumps(_selected),
        "returns": dumps(lambda n: isinstance(n, ast.Return)),
    }


def _parse_module(root: str, mod: str) -> ast.Module | None:
    """Parsed protected module; None when no regular file is at ``mod``.

    A symlinked module or parent directory is never followed.
    """
    path = os.path.join(root, mod)
    try:
        if _behind_symlink(root, mod) or not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            data = handle.read()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise GateError(f"protected source {_q(mod)} is unreadable: {exc}") from exc
    return _parse_source(data, mod, "")


def _parse_source(data: bytes, mod: str, where: str) -> ast.Module:
    try:
        return ast.parse(data, filename=mod)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise GateError(
            f"protected source {_q(mod)}{where} does not parse: {exc}"
        ) from exc


def _staged_module(mod: str) -> ast.Module | None:
    """Parsed index blob of ``mod``; None unless one regular file is staged there."""
    out = _git("ls-files", "--stage", "-z", "--", ":(top,literal)" + mod)
    entries = [e for e in out.split(b"\0") if e]
    if len(entries) != 1:
        return None
    meta = entries[0].partition(b"\t")[0].split(b" ")
    if len(meta) != 3 or meta[0] not in (b"100644", b"100755") or meta[2] != b"0":
        return None
    blob = _git("cat-file", "blob", meta[1].decode("ascii"))
    return _parse_source(blob, mod, " in the index")


def _definitions(tree: ast.Module, name: str) -> list[ast.AST]:
    return [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name
    ]


# ---------------------------------------------------------------- record


def _record(task: str, out: str) -> None:
    if not task:
        raise GateError("--task must name a task id")
    if not out:
        raise GateError("--out must name a file")
    out_path = os.path.abspath(out)
    if os.path.lexists(out_path):
        raise GateError(f"output {_q(out_path)} already exists; it is never replaced")
    root = _toplevel()
    status = _git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    paths = {rel: _snapshot(root, rel) for rel in _status_paths(status)}
    guards: dict[str, dict[str, dict[str, list[str]]]] = {}
    for mod, names in PROTECTED.items():
        tree = _parse_module(root, mod)
        if tree is None:
            raise GateError(
                f"protected source {_q(mod)} is missing or not a regular file"
            )
        guards[mod] = {}
        for name in names:
            found = _definitions(tree, name)
            if len(found) != 1:
                raise GateError(
                    f"protected function {name} in {_q(mod)} is defined "
                    f"{len(found)} times at module level, expected once"
                )
            guards[mod][name] = _guard_lists(found[0], mod)
    doc = {
        "task": task,
        "repository": root,
        "repository_identity": _identity(root),
        "status": base64.b64encode(status).decode("ascii"),
        "paths": paths,
        "guards": guards,
    }
    data = (json.dumps(doc, indent=1, allow_nan=False) + "\n").encode("ascii")
    parent = os.path.dirname(out_path)
    try:
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=f".{os.path.basename(out_path)}.", suffix=".tmp", dir=parent
        )
    except OSError as exc:
        raise GateError(f"cannot write output {_q(out_path)}: {exc}") from exc
    errors: list[str] = []
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(tmp, out_path)  # exclusive publish: fails if out_path exists
    except OSError as exc:
        errors.append(f"cannot write output {_q(out_path)}: {exc}")
    try:
        os.unlink(tmp)
    except OSError as exc:
        errors.append(f"cannot remove temporary output {_q(tmp)}: {exc}")
    if errors:
        raise GateError("; ".join(errors))
    print(f"scope_gate: recorded {len(paths)} dirty paths and 30 guards to {_q(out)}")


# ---------------------------------------------------------------- check


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-standard JSON constant {token}")


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = dict(pairs)
    if len(out) != len(pairs):
        raise ValueError("duplicate object key")
    return out


def _valid_rel(rel: Any, where: str) -> str:
    if not isinstance(rel, str) or not rel or "\0" in rel:
        raise GateError(f"{where}: {_q(str(rel))} is not a repository path")
    try:
        rel.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError as exc:
        raise GateError(f"{where}: {_q(rel)} is not a filesystem path") from exc
    # Git reports "/" on every OS; "\" separates Windows paths but names a POSIX file.
    windows_separator = os.sep == "\\" and "\\" in rel
    if (
        posixpath.isabs(rel)
        or os.path.isabs(rel)
        or os.path.splitdrive(rel)[0]
        or ".." in rel.split("/")
        or windows_separator
    ):
        raise GateError(f"{where}: {_q(rel)} is not a repository-relative path")
    return rel


def _load_baseline(path: str) -> dict[str, Any]:
    def bad(detail: str) -> GateError:
        return GateError(f"invalid baseline {_q(path)}: {detail}")

    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise GateError(f"cannot read baseline {_q(path)}: {exc}") from exc
    try:
        doc = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_keys,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise bad(f"not a JSON document: {exc}") from exc
    if not isinstance(doc, dict) or set(doc) != DOC_KEYS:
        raise bad(f"top level must be an object with keys {sorted(DOC_KEYS)}")
    if not isinstance(doc["task"], str) or not doc["task"]:
        raise bad("task must be a non-empty string")
    repo = doc["repository"]
    if not isinstance(repo, str) or "\0" in repo or not os.path.isabs(repo):
        raise bad("repository must be an absolute path string")
    try:
        os.fsencode(repo)
    except UnicodeEncodeError as exc:
        raise bad(f"repository {_q(repo)} is not a filesystem path") from exc
    identity = doc["repository_identity"]
    if (
        not isinstance(identity, list)
        or len(identity) != 2
        or not all(type(n) is int and n >= 0 for n in identity)
    ):
        raise bad("repository_identity must be a list of two non-negative integers")
    if not isinstance(doc["status"], str):
        raise bad("status must be a base64 string")
    try:
        status = base64.b64decode(doc["status"].encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise bad(f"status is not base64: {exc}") from exc
    paths = doc["paths"]
    if not isinstance(paths, dict):
        raise bad("paths must be an object")
    for rel, snap in paths.items():
        _valid_rel(rel, f"baseline {_q(path)} paths")
        if not isinstance(snap, dict) or set(snap) != {"type", "sha256"}:
            raise bad(f"paths entry {_q(rel)} must be an object with type and sha256")
        kind, digest = snap["type"], snap["sha256"]
        if not isinstance(kind, str):
            raise bad(f"paths entry {_q(rel)} has an invalid type or sha256")
        hashed = kind in HASHED_TYPES and isinstance(digest, str)
        if not (hashed and _SHA256.fullmatch(digest)) and not (
            kind in UNHASHED_TYPES and digest is None
        ):
            raise bad(f"paths entry {_q(rel)} has an invalid type or sha256")
    try:
        status_paths = set(_status_paths(status))
    except GateError as exc:
        raise bad(f"status: {exc}") from exc
    if status_paths != set(paths):
        raise bad("paths do not match the recorded git status")
    guards = doc["guards"]
    if not isinstance(guards, dict) or set(guards) != set(PROTECTED):
        raise bad(f"guards must be an object keyed by {sorted(PROTECTED)}")
    for mod, names in PROTECTED.items():
        entries = guards[mod]
        if not isinstance(entries, dict) or set(entries) != set(names):
            raise bad(f"guards for {_q(mod)} must hold exactly its protected names")
        for name in names:
            entry = entries[name]
            if not isinstance(entry, dict) or set(entry) != set(LISTS):
                raise bad(f"guard {name} must be an object with keys {list(LISTS)}")
            for key in LISTS:
                items = entry[key]
                if not isinstance(items, list) or not all(
                    isinstance(item, str) for item in items
                ):
                    raise bad(f"guard {name} {key} must be a list of strings")
    return doc


def _operand(text: str) -> re.Pattern[str]:
    op = text.replace("\\", "/") if os.sep == "\\" else text
    if posixpath.isabs(op) or os.path.isabs(text) or os.path.splitdrive(text)[0]:
        raise GateError(f"--allowed operand {_q(text)} must be repository-relative")
    norm = posixpath.normpath(op)
    if norm in ("", ".") or norm == ".." or norm.startswith("../"):
        raise GateError(f"--allowed operand {_q(text)} escapes the repository")
    regex = ""
    parts = norm.split("/")
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part == "**":
            regex += ".*" if last else "(?:[^/]+/)*"
            continue
        regex += "".join(
            "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in part
        )
        regex += "" if last else "/"
    return re.compile(regex, re.DOTALL)


def _check(baseline: str, allowed: Iterable[str]) -> list[str]:
    patterns = [_operand(text) for text in allowed]
    doc = _load_baseline(baseline)
    root = _toplevel()
    recorded = doc["repository"]
    try:
        same = os.path.samefile(recorded, root)
    except OSError as exc:
        raise GateError(
            f"baseline repository {_q(recorded)} is unusable: {exc}"
        ) from exc
    if not same:
        raise GateError(
            f"baseline repository {_q(recorded)} is not this repository {_q(root)}"
        )
    if _identity(root) != doc["repository_identity"]:
        raise GateError(
            f"baseline repository {_q(recorded)} was replaced: the directory now at "
            "that path is not the recorded repository"
        )
    status = _git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    current = set(_status_paths(status))
    staged = _staged_paths()

    def allowed_path(rel: str) -> bool:
        return any(p.fullmatch(rel) for p in patterns)

    recorded_paths: dict[str, Any] = doc["paths"]
    violations: list[str] = []
    for rel in sorted(set(recorded_paths) | current):
        if allowed_path(rel):
            continue
        if rel not in recorded_paths:
            violations.append(f"path {_q(rel)} changed outside the allowed paths")
        elif _snapshot(root, rel) != recorded_paths[rel]:
            violations.append(
                f"path {_q(rel)} outside the allowed paths differs from its baseline"
            )
    for rel in sorted(set(staged)):
        if not allowed_path(rel):
            violations.append(f"staged path {_q(rel)} is outside the allowed paths")
    for mod in PROTECTED:
        violations += _guard_violations(_parse_module(root, mod), mod, doc, "")
    for mod in PROTECTED:
        if mod in staged:
            # a commit records the index, so the staged blob is guarded too
            violations += _guard_violations(
                _staged_module(mod), mod, doc, " in the index"
            )
    return violations


def _guard_violations(
    tree: ast.Module | None, mod: str, doc: dict[str, Any], where: str
) -> list[str]:
    violations: list[str] = []
    for name in PROTECTED[mod]:
        if tree is None:
            violations.append(
                f"protected function {name} is missing: {_q(mod)}{where} is missing "
                "or not a regular file"
            )
            continue
        found = _definitions(tree, name)
        if len(found) != 1:
            violations.append(
                f"protected function {name} in {_q(mod)}{where} is defined "
                f"{len(found)} times at module level, expected once"
            )
            continue
        lists = _guard_lists(found[0], mod)
        for key in LISTS:
            if lists[key] != doc["guards"][mod][name][key]:
                violations.append(
                    f"protected function {name} in {_q(mod)}{where}: {key} changed"
                )
    return violations


# ---------------------------------------------------------------- CLI


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scope_gate.py", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record", allow_abbrev=False)
    record.add_argument("--task", required=True)
    record.add_argument("--out", required=True)
    check = sub.add_parser("check", allow_abbrev=False)
    check.add_argument("--baseline", required=True)
    check.add_argument("--allowed", required=True, nargs="+")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = _parser().parse_args(argv)
    try:
        if args.command == "record":
            _record(args.task, args.out)
            return 0
        violations = _check(args.baseline, args.allowed)
    except GateError as exc:
        print(f"scope_gate: error: {exc}", file=sys.stderr)
        return 2
    for violation in violations:
        print(f"scope_gate: violation: {violation}", file=sys.stderr)
    if violations:
        return 1
    print("scope_gate: check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
