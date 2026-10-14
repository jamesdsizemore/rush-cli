"""TypeScript compiler adapter for Rush type checking.

T12 (S12.6): the requested files are analyzed through the project's own
configuration. For each owning config Rush writes one scoped tsconfig into an
owned temporary directory under `<logical_root>/.rush/tmp/`, extending the
owner with the requested files plus their ambient roots, and runs exactly one
`tsc -p SCOPED --noEmit --listFiles --pretty false` per owner. Diagnostics are
kept and classified (`requested`, `dependency`, `configuration`,
`engine_library`); nothing is post-filtered.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import subprocess
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs

if TYPE_CHECKING:
    from .staging import StagingContext

#: E13: the file family tsc's own wildcard expansion considers.
FAMILY_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
_TSX_GRAMMAR_SUFFIXES = (".tsx", ".jsx", ".js", ".mjs", ".cjs")
_WILDCARD_SKIP_DIRS = frozenset({"node_modules", "bower_components", "jspm_packages"})
_NODE_MODULE_KINDS = frozenset({"node16", "node18", "node20", "nodenext"})
_DECL_RE = re.compile(r"\.d\.([mc]?ts|[^./]+\.ts)$")
_HEAD_RE = re.compile(
    r"^(?P<path>.+?)\((?P<line>\d+),(?P<col>\d+)\): "
    r"(?P<sev>error|warning|message) (?P<code>TS\d+): (?P<msg>.*)$",
    re.DOTALL,
)
_GLOBAL_RE = re.compile(
    r"^(?P<sev>error|warning|message) (?P<code>TS\d+): (?P<msg>.*)$"
)
#: A11: codes that describe configuration, not source (E4, E6, E7, E8, E12).
_CONFIG_CODES = frozenset(
    {"TS6053", "TS6059", "TS6305", "TS6306", "TS6307", "TS6504", "TS18003"}
)
_SEVERITY: dict[str, Literal["error", "warn", "info"]] = {
    "error": "error",
    "warning": "warn",
    "message": "info",
}
_TRUNCATED = "[TRUNCATED]"
_MAX_HEAD_BYTES = 4096
_MARKER = ".rush-tsc-owner"
_KNOWN_TEMP_NAME = re.compile(
    r"^g\d+\.(tsconfig\.json|closure\.tsconfig\.json|tsbuildinfo)$"
)
_SCOPED_CONFIG_NAME = re.compile(r"^g\d+\.(closure\.)?tsconfig\.json$")
_TIMEOUT = 120
_OUTPUT_TRUNCATED_MESSAGE = (
    "tsc: output truncated at 256 KiB before any consumed-file line; "
    "diagnostics may be missing"
)


class TscScopeError(Exception):
    """A named owning-config or scope failure (A12)."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.diagnostics = list(diagnostics or [])


class TsClassification(NamedTuple):
    kind: Literal["module", "script"] | None
    declares_global: bool
    reason: str | None


@dataclass
class ParsedTscOutput:
    """A10: diagnostics (with `path` None for global ones), consumed files
    from `--listFiles`, and everything that could not be parsed."""

    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    consumed: list[str] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)
    redacted: int = 0
    truncated: bool = False

    @property
    def listfiles_seen(self) -> bool:
        return bool(self.consumed)

    def merge(self, other: ParsedTscOutput) -> None:
        self.diagnostics.extend(other.diagnostics)
        self.consumed.extend(other.consumed)
        self.unparsed.extend(other.unparsed)
        self.redacted += other.redacted
        self.truncated = self.truncated or other.truncated


# -- output parsing (A10) ---------------------------------------------------


def _record_at(
    lines: list[str], i: int, cwd: str, exists: Callable[[str], bool]
) -> tuple[int, dict[str, Any] | None, str | None]:
    """A diagnostic head or an absolute consumed file starting at line `i`,
    reassembled across newline-split lines (E12). Returns lines taken."""
    k = 0
    while i + k < len(lines) and (
        len("\n".join(lines[i : i + k]).encode("utf-8")) <= _MAX_HEAD_BYTES
    ):
        joined = "\n".join(lines[i : i + k + 1])
        match = _HEAD_RE.match(joined)
        if match and (k == 0 or exists(os.path.join(cwd, match["path"]))):
            return (
                k + 1,
                {
                    "path": os.path.normpath(os.path.join(cwd, match["path"])),
                    "line": int(match["line"]),
                    "column": int(match["col"]),
                    "rule": match["code"],
                    "severity": match["sev"],
                    "message": match["msg"],
                },
                None,
            )
        if os.path.isabs(joined) and exists(joined):
            return k + 1, None, joined
        k += 1
    return 0, None, None


def parse_tsc_output(
    text: str, cwd: Path, *, exists: Callable[[str], bool] = os.path.exists
) -> ParsedTscOutput:
    """Parse `--pretty false --listFiles` output conservatively (A10)."""
    out = ParsedTscOutput()
    if text.endswith(_TRUNCATED):
        out.truncated = True
        lines = text[: -len(_TRUNCATED)].split("\n")[:-1]
    else:
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
    base = str(cwd)
    open_diagnostic = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if open_diagnostic and line[:1] in (" ", "\t"):
            out.diagnostics[-1]["message"] += "\n" + line
            i += 1
            continue
        if line == "":
            open_diagnostic = False
            i += 1
            continue
        taken, diagnostic, consumed = _record_at(lines, i, base, exists)
        open_diagnostic = diagnostic is not None
        if diagnostic is not None:
            out.diagnostics.append(diagnostic)
        elif consumed is not None:
            out.consumed.append(consumed)
        else:
            taken = 1
            glob = _GLOBAL_RE.match(line)
            if glob:
                out.diagnostics.append(
                    {
                        "path": None,
                        "rule": glob["code"],
                        "severity": glob["sev"],
                        "message": glob["msg"],
                    }
                )
                open_diagnostic = True
            elif "[REDACTED]" in line:
                out.redacted += 1
            else:
                out.unparsed.append(line)
        i += taken
    return out


def _parse_streams(stdout: str, stderr: str, cwd: Path) -> ParsedTscOutput:
    parsed = parse_tsc_output(stdout or "", cwd)
    if stderr:
        parsed.merge(parse_tsc_output(stderr, cwd))
    return parsed


# -- module/script classification (A8) --------------------------------------


def _grammars() -> tuple[Any, Any]:
    """Both tree-sitter-typescript grammars; raises when unavailable."""
    import tree_sitter_typescript
    from tree_sitter import Language

    return (
        Language(tree_sitter_typescript.language_typescript()),
        Language(tree_sitter_typescript.language_tsx()),
    )


def _nodes(root: Any) -> Iterator[Any]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


def _package_type(directory: Path) -> tuple[bool, Any]:
    """(valid, `type`) of the nearest ancestor `package.json`."""
    for candidate in (directory, *directory.parents):
        manifest = candidate / "package.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return False, None
            if not isinstance(data, dict):
                return False, None
            return True, data.get("type")
    return True, None


def classify_ts_file(
    path: Path, options: Mapping[str, Any], *, grammars: tuple[Any, Any] | None = None
) -> TsClassification:
    """Module or script under the effective `moduleDetection` (A8, E11)."""
    from tree_sitter import Parser

    ts_lang, tsx_lang = grammars if grammars is not None else _grammars()
    name = path.name
    suffix = path.suffix
    try:
        data = path.read_bytes()
    except OSError:
        return TsClassification(None, False, "unreadable")
    tree = Parser(tsx_lang if suffix in _TSX_GRAMMAR_SUFFIXES else ts_lang).parse(data)
    root = tree.root_node
    if root.has_error:
        return TsClassification(None, False, "parse_error")
    top = root.children
    syntax = any(
        child.type == "import_statement"
        or (
            child.type == "export_statement"
            and [c.type for c in child.children[:3]] != ["export", "as", "namespace"]
        )
        for child in top
    )
    all_nodes = list(_nodes(root))
    syntax = syntax or any(
        node.type == "meta_property" and (node.text or b"").startswith(b"import")
        for node in all_nodes
    )
    declares_global = any(
        child.type == "ambient_declaration"
        and any(c.type == "global" for c in child.children)
        for child in top
    )
    decl = bool(_DECL_RE.search(name))
    module = str(options.get("module", "")).lower()
    detection = str(
        options.get(
            "moduleDetection", "force" if module in _NODE_MODULE_KINDS else "auto"
        )
    ).lower()
    if detection == "force":
        is_module = syntax or not decl
    elif detection == "legacy":
        is_module = syntax
    elif syntax:
        is_module = True
    elif decl:
        is_module = False
    elif suffix in (".mts", ".cts", ".mjs", ".cjs"):
        is_module = True
    else:
        is_module = False
        if module in _NODE_MODULE_KINDS and suffix in (".ts", ".tsx", ".js", ".jsx"):
            valid, package_type = _package_type(path.parent)
            if not valid:
                return TsClassification(None, False, "package_json_invalid")
            is_module = package_type == "module"
        if not is_module and str(options.get("jsx", "")).lower() in {
            "react-jsx",
            "react-jsxdev",
        }:
            is_module = any(
                node.type in ("jsx_element", "jsx_self_closing_element")
                for node in all_nodes
            )
    return TsClassification("module" if is_module else "script", declares_global, None)


# -- file selection helpers (A6, A7) ----------------------------------------


def _skip_dir(name: str) -> bool:
    return name in _WILDCARD_SKIP_DIRS or name.startswith(".")


def directory_pool(directory: Path) -> list[Path]:
    """A6.1/OR-5: the files tsc's own wildcard rules would consider."""
    pool: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(n for n in dirnames if not _skip_dir(n))
        pool.extend(
            Path(dirpath) / name
            for name in sorted(filenames)
            if not name.startswith(".") and Path(name).suffix in FAMILY_SUFFIXES
        )
    return pool


def _noconfig_files(exec_root: Path) -> set[str]:
    """A7/OR-7: TypeScript files outside every subtree with its own config."""
    files: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(exec_root):
        dirnames[:] = [
            n
            for n in dirnames
            if not _skip_dir(n)
            and not os.path.isfile(os.path.join(dirpath, n, "tsconfig.json"))
        ]
        files.update(
            os.path.realpath(os.path.join(dirpath, name))
            for name in filenames
            if not name.startswith(".") and Path(name).suffix in _TS_SUFFIXES
        )
    return files


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _real_within(real: str, root_real: str) -> bool:
    return real == root_real or real.startswith(root_real.rstrip(os.sep) + os.sep)


def _engine_root(executable: str) -> str:
    """A3.3: the TypeScript package directory holding the engine libraries."""
    real = Path(os.path.realpath(executable))
    for directory in real.parents:
        manifest = directory / "package.json"
        if not manifest.is_file():
            continue
        try:
            name = json.loads(manifest.read_text(encoding="utf-8")).get("name")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(name, str) and (
            name == "typescript" or name.startswith("@typescript/")
        ):
            return str(directory)
    return str(real.parent.parent)


# -- owned temporary directory (A3.4, A14) ----------------------------------

_OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)


def _write_owned(path: Path, text: str) -> None:
    fd = os.open(path, _OPEN_FLAGS, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)


@dataclass
class _TempDir:
    root: PhysicalRoot
    name: str
    path: Path
    token: str

    @classmethod
    def create(cls, logical_root: Path) -> _TempDir:
        root = PhysicalRoot(logical_root)
        for rel in (".rush", ".rush/tmp"):
            candidate = root.open_contained(rel, purpose="write")
            if not os.path.lexists(candidate):
                os.mkdir(candidate, 0o700)
            elif not candidate.is_dir():
                raise ContainmentError(
                    "NOT_A_DIRECTORY", f"'{candidate}' is not a directory", rel
                )
        name = "tsc-" + uuid.uuid4().hex
        path = root.open_contained(".rush/tmp/" + name, purpose="write")
        os.mkdir(path, 0o700)
        token = secrets.token_hex(32)
        _write_owned(path / _MARKER, token)
        return cls(root, name, path, token)

    def write_json(self, name: str, payload: dict[str, Any]) -> Path:
        target = self.path / name
        _write_owned(target, json.dumps(payload, ensure_ascii=False))
        return target

    def cleanup(self) -> list[str]:
        """Remove the directory only when the ownership marker matches and it
        holds nothing but Rush's own regular files; else report residue."""
        try:
            path = self.root.open_contained(".rush/tmp/" + self.name, purpose="write")
            fd = os.open(path / _MARKER, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                marker = os.read(fd, 1024).decode("utf-8", "replace")
            finally:
                os.close(fd)
            names = sorted(entry.name for entry in os.scandir(path))
            if not hmac.compare_digest(marker, self.token) or any(
                (name != _MARKER and not _KNOWN_TEMP_NAME.match(name))
                or not os.path.isfile(path / name)
                or os.path.islink(path / name)
                for name in names
            ):
                return names
            for name in [n for n in names if n != _MARKER] + [_MARKER]:
                os.unlink(path / name)
            os.rmdir(path)
            return []
        except (ContainmentError, OSError):
            try:
                return sorted(os.listdir(self.path)) or [self.name]
            except OSError:
                return [self.name]


# -- owning-config selection (A4, A5, A6) -----------------------------------


@dataclass
class _Config:
    path: Path
    real: str
    options: dict[str, Any]
    effective: set[str]
    refs: list[Path]
    raw_refs: list[str]

    @property
    def solution(self) -> bool:
        return not self.effective and bool(self.refs)


@dataclass
class _Group:
    config: _Config | None
    explicit_override: bool
    requested: list[str] = field(default_factory=list)


class _Planner:
    """Everything that decides which config owns which requested file."""

    def __init__(
        self,
        exe: str,
        exec_root: Path,
        logical_root: Path,
        spawn: Callable[[list[str], Path], subprocess.CompletedProcess[str]],
        display: Callable[[str], str],
    ) -> None:
        self.exe = exe
        # Config walks compare physical paths, so a requested path reached
        # through an alias (`/tmp` -> `/private/tmp`) still finds its config.
        self.exec_root = Path(os.path.realpath(exec_root))
        self.exec_root_real = str(self.exec_root)
        self.logical_root = logical_root
        self.physical = PhysicalRoot(exec_root)
        self._spawn = spawn
        self.display = display
        self._configs: dict[str, _Config] = {}
        self._noconfig: set[str] | None = None

    # A4
    def show(self, cfg: Path) -> _Config:
        real = os.path.realpath(cfg)
        cached = self._configs.get(real)
        if cached is not None:
            return cached
        proc = self._spawn([self.exe, "-p", str(cfg), "--showConfig"], cfg.parent)
        try:
            data = json.loads(proc.stdout) if proc.returncode == 0 else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            parsed = _parse_streams(proc.stdout, proc.stderr, cfg.parent)
            raise TscScopeError(
                "TSC_CONFIG_UNREADABLE",
                f"tsc: --showConfig failed for {self.display(real)} "
                f"(exit {proc.returncode})",
                {"config": self.display(real), "exit_code": proc.returncode},
                diagnostics=parsed.diagnostics,
            )
        options = data.get("compilerOptions")
        refs: list[Path] = []
        raw_refs: list[str] = []
        for ref in data.get("references") or []:
            joined = os.path.normpath(
                os.path.join(cfg.parent, str(ref.get("path", "")))
            )
            raw_refs.append(joined)
            refs.append(
                Path(joined) / "tsconfig.json"
                if os.path.isdir(joined)
                else Path(joined)
            )
        config = _Config(
            path=cfg,
            real=real,
            options=options if isinstance(options, dict) else {},
            effective={
                os.path.realpath(os.path.join(cfg.parent, str(f)))
                for f in data.get("files") or []
            },
            refs=refs,
            raw_refs=raw_refs,
        )
        self._configs[real] = config
        return config

    # A5.6
    def dfs(self, start: Path) -> list[_Config]:
        visited: set[str] = set()
        order: list[_Config] = []

        def visit(cfg: Path, stack: list[str]) -> None:
            real = os.path.realpath(cfg)
            if real in stack:
                cycle = [self.display(c) for c in [*stack[stack.index(real) :], real]]
                raise TscScopeError(
                    "TSC_REFERENCE_CYCLE",
                    "tsc: project references form a cycle: " + " -> ".join(cycle),
                    {"cycle": cycle},
                )
            if real in visited or not os.path.isfile(real):
                return
            visited.add(real)
            config = self.show(cfg)
            order.append(config)
            for ref in config.refs:
                visit(ref, [*stack, real])

        visit(start, [])
        return order

    def _contained_config(self, candidate: Path) -> Path:
        try:
            self.physical.open_contained(
                candidate.relative_to(self.exec_root), purpose="read"
            )
        except ContainmentError as exc:
            real = os.path.realpath(candidate)
            raise TscScopeError(
                "TSC_OWNER_OUTSIDE_ROOT",
                f"tsc: owning config {self.display(real)} lies outside the "
                f"project root {self.logical_root}",
                {"config": self.display(real), "reason": exc.code},
            ) from None
        return candidate

    def _ancestor_configs(self, target: Path) -> Iterator[Path]:
        directory = Path(os.path.realpath(target)).parent
        while _within(directory, self.exec_root):
            candidate = directory / "tsconfig.json"
            if candidate.is_file():
                yield self._contained_config(candidate)
            if directory == self.exec_root:
                return
            directory = directory.parent

    # A5.2
    def candidate(self, target: Path) -> Path | None:
        return next(self._ancestor_configs(target), None)

    def nearest_non_solution(self, target: Path) -> Path | None:
        return next(
            (c for c in self._ancestor_configs(target) if not self.show(c).solution),
            None,
        )

    # A5.5
    def referenced_owner(self, target: Path, graph: list[_Config]) -> _Config | None:
        real = os.path.realpath(target)
        owners = [c for c in graph[1:] if real in c.effective and not c.solution]
        if not owners:
            return None
        depth = max(_depth(c) for c in owners)
        top = sorted((c for c in owners if _depth(c) == depth), key=lambda c: c.real)
        if len(top) > 1:
            configs = [self.display(c.real) for c in top]
            raise TscScopeError(
                "TSC_AMBIGUOUS_OWNER",
                f"tsc: {self.display(str(target))} is owned by more than one equally "
                f"deep config: {', '.join(configs)}; pass --typecheck-config to "
                "choose one",
                {"configs": configs},
            )
        owner = top[0]
        if not _real_within(owner.real, self.exec_root_real):
            raise TscScopeError(
                "TSC_OWNER_OUTSIDE_ROOT",
                f"tsc: owning config {self.display(owner.real)} lies outside the "
                f"project root {self.logical_root}",
                {"config": self.display(owner.real)},
            )
        return owner

    def owner_for_file(
        self, target: Path, explicit: Path | None
    ) -> tuple[_Config | None, bool]:
        """A5: (owner or None for no-config mode, explicit_override)."""
        real = os.path.realpath(target)
        if explicit is not None:
            self.dfs(explicit)
            config = self.show(explicit)
            return config, real not in config.effective
        candidate = self.candidate(target)
        if candidate is None:
            return None, False
        graph = self.dfs(candidate)
        first = self.show(candidate)
        if real in first.effective:
            return first, False
        owner = self.referenced_owner(target, graph)
        if owner is not None:
            return owner, False
        fallback = self.nearest_non_solution(target)
        if fallback is not None:
            self.dfs(fallback)
            return self.show(fallback), True
        raise TscScopeError(
            "TYPECHECK_CONFIG_REQUIRED",
            f"tsc: {self.display(str(target))} is not owned by any project "
            f"referenced from the solution config {self.display(first.real)}; "
            "pass --typecheck-config",
            {
                "target": self.display(str(target)),
                "solution_config": self.display(first.real),
            },
        )

    def noconfig_files(self) -> set[str]:
        if self._noconfig is None:
            self._noconfig = _noconfig_files(self.exec_root)
        return self._noconfig

    def place_pool_file(self, target: Path) -> _Config | None | str:
        """A6.3: an owner, None (no-config group) or an exclusion reason."""
        real = os.path.realpath(target)
        candidate = self.candidate(target)
        if candidate is None:
            return (
                None if real in self.noconfig_files() else "excluded_by_default_rules"
            )
        graph = self.dfs(candidate)
        first = self.show(candidate)
        if real in first.effective:
            return first
        owner = self.referenced_owner(target, graph)
        if owner is not None:
            return owner
        return "no_owning_project" if first.solution else "excluded_by_config"


def _depth(config: _Config) -> int:
    """OR-4: directory depth of the config's realpath."""
    return len(Path(config.real).parent.parts)


# -- the engine ---------------------------------------------------------------


def _parse_args(args: list[str]) -> tuple[Path | None, list[Path]]:
    """(`-p` explicit config, explicit requested files). Each explicit file is
    owned exactly like a single-file request (A5); no other flag is taken,
    so a caller can never slip an unscoped option past the scoped config."""
    explicit: Path | None = None
    targets: list[Path] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-p", "--project") and index + 1 < len(args):
            explicit = Path(os.path.abspath(args[index + 1]))
            index += 2
            continue
        if arg.startswith("-"):
            raise ValueError(f"tsc adapter does not accept the option {arg!r}")
        targets.append(Path(os.path.abspath(arg)))
        index += 1
    return explicit, targets


def _roots(path: Path) -> tuple[StagingContext | None, Path, Path]:
    """A3.1: (staging, logical root, execution root)."""
    from ..invocation.targets import resolve_logical_root
    from .staging import active_staging

    staging = active_staging()
    target = Path(os.path.abspath(path))
    if staging is not None and _within(target, staging.staged_root):
        live = staging.original_root / target.relative_to(staging.staged_root)
        logical = Path(resolve_logical_root(live))
        return staging, logical, staging.stage_path(logical) or logical
    logical = Path(resolve_logical_root(target))
    return None, logical, logical


def _display_for(staging: StagingContext | None) -> Callable[[str], str]:
    if staging is None:
        return lambda value: value
    from .staging import map_staged_path

    return lambda value: map_staged_path(
        value, staging.staged_root, staging.original_root
    )


def _ancestry(
    owner_dir: Path, staging: StagingContext | None, logical: Path
) -> list[Path]:
    """A9.1/OR-11: owner dir and its ancestors, nearest first; under staging
    the staged chain stops at the staged root and continues in the live tree
    above the logical root."""
    chain = [owner_dir, *owner_dir.parents]
    if staging is None or not _within(owner_dir, staging.staged_root):
        return chain
    staged = [d for d in chain if _within(d, staging.staged_root)]
    return [*staged, *logical.parents]


def _type_roots(
    owner_dir: Path, options: Mapping[str, Any], ancestry: list[Path]
) -> list[str]:
    if isinstance(options.get("typeRoots"), list):
        roots = [
            os.path.normpath(os.path.join(owner_dir, str(r)))
            for r in options["typeRoots"]
        ]
    else:
        roots = [
            str(d / "node_modules" / "@types")
            for d in ancestry
            if (d / "node_modules" / "@types").is_dir()
        ]
    types = options.get("types")
    if isinstance(types, list) and types and "*" not in types:
        roots += [
            str(d / "node_modules") for d in ancestry if (d / "node_modules").is_dir()
        ]
    return roots


class TscEngine(Engine):
    name = "tsc"
    binary = "tsc"
    # OR-1: `.mts`/`.cts` are TypeScript sources too (E13).
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> EngineResult:
        explicit, targets = _parse_args(args)
        exe = resolve_binary(self.binary) or self.binary
        staging, logical_root, exec_root = _roots(path)
        display = _display_for(staging)
        tsc: dict[str, Any] = {
            "version": 1,
            "mode": "files" if targets else "directory" if path.is_dir() else "file",
            "targets": [str(target) for target in targets],
            "exec_root": str(exec_root),
            "logical_root": str(logical_root),
            "engine_root": None,
            "temp": {"dir": None, "removed": False, "residue": []},
            "excluded": [],
            "groups": [],
            "run_errors": [],
            "pool_size": 1,
            "spawned": False,
        }
        try:
            grammars = _grammars()
        except (ImportError, OSError, ValueError, TypeError, AttributeError) as exc:
            tsc["run_errors"].append(
                {
                    "code": "TSC_UNCLASSIFIABLE",
                    "message": f"tsc: tree-sitter-typescript grammar unavailable: {exc}",
                    "details": {"reason": "parser_unavailable"},
                }
            )
            return EngineResult(
                exit_code=0, stdout="", stderr="", cwd=_result_cwd(tsc), tsc=tsc
            )
        tsc["engine_root"] = _engine_root(exe)
        try:
            temp = _TempDir.create(logical_root)
        except ContainmentError as exc:
            return self._temp_rejected(tsc, exc.code, exc.message)
        except OSError as exc:
            return self._temp_rejected(tsc, "OS_ERROR", str(exc))
        tsc["temp"]["dir"] = str(temp.path)

        def spawn(argv: list[str], run_cwd: Path) -> subprocess.CompletedProcess[str]:
            tsc["spawned"] = True
            # An unowned call keeps the exact unowned kwargs (ownership_kwargs).
            if not ownership_kwargs(owner_instance_id, run_id):
                return run_subprocess(argv, cwd=run_cwd, timeout=_TIMEOUT)
            return run_subprocess(
                argv,
                cwd=run_cwd,
                timeout=_TIMEOUT,
                owner_instance_id=owner_instance_id,
                run_id=run_id,
            )

        try:
            planner = _Planner(exe, exec_root, logical_root, spawn, display)
            groups, errors = self._plan(
                planner, Path(os.path.abspath(path)), targets, explicit, tsc
            )
            for index, group in enumerate(groups):
                tsc["groups"].append(
                    self._run_group(
                        planner,
                        temp,
                        index,
                        group,
                        grammars,
                        staging,
                        logical_root,
                        spawn,
                    )
                )
            tsc["groups"].extend(errors)
        finally:
            residue = temp.cleanup()
            tsc["temp"] = {
                "dir": str(temp.path),
                "removed": not residue,
                "residue": residue,
            }
        exit_code = max((g.get("exit_code") or 0 for g in tsc["groups"]), default=0)
        return EngineResult(
            exit_code=exit_code, stdout="", stderr="", cwd=_result_cwd(tsc), tsc=tsc
        )

    @staticmethod
    def _temp_rejected(tsc: dict[str, Any], code: str, message: str) -> EngineResult:
        tsc["run_errors"].append(
            {
                "code": "TSC_TEMP_CONTAINMENT",
                "message": f"tsc: temporary directory rejected: [{code}] {message}",
                "details": {"reason": code},
            }
        )
        return EngineResult(
            exit_code=0, stdout="", stderr="", cwd=_result_cwd(tsc), tsc=tsc
        )

    @staticmethod
    def _plan(
        planner: _Planner,
        target: Path,
        targets: list[Path],
        explicit: Path | None,
        tsc: dict[str, Any],
    ) -> tuple[list[_Group], list[dict[str, Any]]]:
        """A5 (file mode, one file or explicit files) / A6 (directory mode):
        owner groups in A6.4 order plus error groups."""
        groups: dict[tuple[str | None, bool], _Group] = {}
        errors: dict[tuple[str, str], dict[str, Any]] = {}

        def add(config: _Config | None, override: bool, file: Path) -> None:
            key = (None if config is None else config.real, override)
            group = groups.setdefault(key, _Group(config, override))
            group.requested.append(os.path.realpath(file))

        def fail(exc: TscScopeError, file: Path) -> None:
            entry = errors.setdefault(
                (exc.code, exc.message),
                {
                    "config": None,
                    "explicit_override": False,
                    "requested": [],
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                    "diagnostics": [_stored(d) for d in exc.diagnostics],
                },
            )
            entry["requested"].append(os.path.realpath(file))

        if targets or not target.is_dir():
            files = targets or [target]
            tsc["pool_size"] = len(files)
            for file in files:
                try:
                    owner, override = planner.owner_for_file(file, explicit)
                    add(owner, override, file)
                except TscScopeError as exc:
                    fail(exc, file)
        else:
            pool = directory_pool(target)
            tsc["pool_size"] = len(pool)
            explicit_config = None
            if explicit is not None:
                try:
                    planner.dfs(explicit)
                    explicit_config = planner.show(explicit)
                except TscScopeError as exc:
                    for file in pool:
                        fail(exc, file)
                    pool = []
            for file in pool:
                if explicit_config is not None:
                    if os.path.realpath(file) in explicit_config.effective:
                        add(explicit_config, False, file)
                    else:
                        tsc["excluded"].append(
                            {"target": str(file), "reason": "excluded_by_config"}
                        )
                    continue
                try:
                    placed = planner.place_pool_file(file)
                except TscScopeError as exc:
                    fail(exc, file)
                    continue
                if isinstance(placed, str):
                    tsc["excluded"].append({"target": str(file), "reason": placed})
                else:
                    add(placed, False, file)
        ordered = sorted(
            groups.values(),
            key=lambda g: (
                g.config is None,
                "" if g.config is None else str(g.config.path),
            ),
        )
        return ordered, list(errors.values())

    def _run_group(
        self,
        planner: _Planner,
        temp: _TempDir,
        index: int,
        group: _Group,
        grammars: tuple[Any, Any],
        staging: StagingContext | None,
        logical_root: Path,
        spawn: Callable[[list[str], Path], subprocess.CompletedProcess[str]],
    ) -> dict[str, Any]:
        """A8-A9: ambient roots, scoped config, closure, one analysis."""
        config = group.config
        options = config.options if config is not None else {}
        owner_dir = config.path.parent if config is not None else planner.exec_root
        effective = config.effective if config is not None else planner.noconfig_files()
        requested = sorted(set(group.requested))
        ambient, unclassifiable, reasons = _ambient_roots(
            effective, requested, options, grammars
        )
        compiler: dict[str, Any] = {
            "tsBuildInfoFile": str(temp.path / f"g{index}.tsbuildinfo"),
            "typeRoots": _type_roots(
                owner_dir, options, _ancestry(owner_dir, staging, logical_root)
            ),
        }
        if options.get("composite") and "rootDir" not in options:
            compiler["rootDir"] = str(owner_dir)
        scoped: dict[str, Any] = {
            "files": sorted(set(requested) | set(ambient)),
            "include": [],
            "compilerOptions": compiler,
        }
        configs_used: list[str] = []
        if config is not None:
            scoped = {
                "extends": str(config.path),
                **scoped,
                "references": [{"path": ref} for ref in config.raw_refs],
            }
            configs_used = [
                str(config.path),
                *(str(r) for r in config.refs if r.is_file()),
            ]
        if options.get("composite"):
            closure = temp.write_json(f"g{index}.closure.tsconfig.json", scoped)
            probe = spawn(
                [planner.exe, "-p", str(closure), "--listFilesOnly"], owner_dir
            )
            listed = _parse_streams(probe.stdout, probe.stderr, owner_dir).consumed
            engine_root = _engine_root(planner.exe)
            extra = {
                real
                for real in (os.path.realpath(f) for f in listed)
                if real in effective
                or (
                    group.explicit_override
                    and not _real_within(real, engine_root)
                    and "node_modules" not in Path(real).parts
                    and not _DECL_RE.search(Path(real).name)
                )
            }
            scoped["files"] = sorted(set(scoped["files"]) | extra)
        final = temp.write_json(f"g{index}.tsconfig.json", scoped)
        argv = [
            planner.exe,
            "-p",
            str(final),
            "--noEmit",
            "--listFiles",
            "--pretty",
            "false",
        ]
        proc = spawn(argv, owner_dir)
        parsed = _parse_streams(proc.stdout, proc.stderr, owner_dir)
        if staging is not None:
            for file in parsed.consumed:
                staging.record_consumption(Path(file))
        return {
            "config": None if config is None else str(config.path),
            "explicit_override": group.explicit_override,
            "cwd": str(owner_dir),
            "requested": requested,
            "ambient": sorted(ambient),
            "unclassifiable": sorted(unclassifiable),
            "unclassifiable_reason": reasons[0] if reasons else None,
            "configs_used": configs_used,
            "argv": argv,
            "exit_code": proc.returncode,
            "diagnostics": [_stored(d) for d in parsed.diagnostics],
            "consumed": parsed.consumed,
            "unparsed": parsed.unparsed,
            "redacted": parsed.redacted,
            "truncated": parsed.truncated,
            "error": None,
        }

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        from .staging import active_staging

        data = raw.get("tsc")
        legacy = not isinstance(data, dict)
        if not isinstance(data, dict):
            data = _legacy_data(raw, path)
        staging = active_staging()
        result = _Normalizer(data, path, _display_for(staging)).result(tool_name)
        # The version probe is a spawn: never one on a zero-spawn error path.
        if legacy or data.get("spawned"):
            result["engine_version"] = self.version()
        return result


def _result_cwd(tsc: Mapping[str, Any]) -> str:
    """A13/finding 10: the first group's cwd, else the execution root."""
    return next(
        (str(g["cwd"]) for g in tsc.get("groups") or [] if g.get("cwd")),
        str(tsc["exec_root"]),
    )


def _stored(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    """A13: raw keeps no key named `path`, so staging's generic remap cannot
    rewrite values normalize still compares against staged paths."""
    stored = {k: v for k, v in diagnostic.items() if k != "path"}
    stored["at"] = diagnostic.get("path")
    return stored


def _ambient_roots(
    effective: set[str],
    requested: list[str],
    options: Mapping[str, Any],
    grammars: tuple[Any, Any],
) -> tuple[list[str], list[str], list[str]]:
    """A8: ambient roots, unclassifiable files, and their reasons."""
    ambient: list[str] = []
    unclassifiable: list[str] = []
    reasons: list[str] = []
    wanted = set(requested)
    for file in sorted(effective - wanted):
        name = Path(file).name
        if _DECL_RE.search(name):
            ambient.append(file)
            continue
        if Path(file).suffix not in FAMILY_SUFFIXES:
            continue
        kind, declares_global, reason = classify_ts_file(
            Path(file), options, grammars=grammars
        )
        if kind is None:
            ambient.append(file)
            unclassifiable.append(file)
            reasons.append(str(reason))
        elif kind == "script" or declares_global:
            ambient.append(file)
    for file in requested:
        kind, _, reason = classify_ts_file(Path(file), options, grammars=grammars)
        if kind is None:
            unclassifiable.append(file)
            reasons.append(str(reason))
    return ambient, unclassifiable, reasons


def _legacy_data(raw: EngineResult, path: Path) -> dict[str, Any]:
    """A11: raw output from a caller that ran tsc itself; relative paths join
    the recorded `cwd` (finding 10), else the run path's directory."""
    recorded = raw.get("cwd")
    cwd = Path(
        os.path.abspath(
            recorded if recorded else (path if path.is_dir() else path.parent)
        )
    )
    parsed = _parse_streams(raw.get("stdout", ""), raw.get("stderr", ""), cwd)
    return {
        "version": 1,
        "mode": "legacy",
        "exec_root": str(cwd),
        "logical_root": str(cwd),
        "engine_root": None,
        "temp": {"dir": None, "removed": True, "residue": []},
        "excluded": [],
        "run_errors": [],
        "pool_size": 0 if path.is_dir() else 1,
        "groups": [
            {
                "config": None,
                "explicit_override": False,
                "cwd": str(cwd),
                "requested": [] if path.is_dir() else [os.path.realpath(path)],
                "ambient": [],
                "unclassifiable": [],
                "unclassifiable_reason": None,
                "configs_used": [],
                "argv": ["tsc"],
                "exit_code": raw.get("exit_code", 0),
                "diagnostics": [_stored(d) for d in parsed.diagnostics],
                "consumed": parsed.consumed,
                "unparsed": parsed.unparsed,
                "redacted": parsed.redacted,
                "truncated": parsed.truncated,
                "error": None,
            }
        ],
    }


class _Normalizer:
    """A11-A13: findings, per-group status and codes, and the child scope."""

    def __init__(self, data: dict[str, Any], path: Path, display: Callable[[str], str]):
        self.data = data
        self.path = path
        self.display = display
        engine_root = data.get("engine_root")
        self.engine_root = os.path.realpath(engine_root) if engine_root else None
        temp_dir = (data.get("temp") or {}).get("dir")
        self.temp_real = os.path.realpath(temp_dir) if temp_dir else None

    def _is_library(self, real: str) -> bool:
        return self.engine_root is not None and _real_within(real, self.engine_root)

    def _finding(
        self,
        index: int,
        group: dict[str, Any],
        diagnostic: dict[str, Any],
        consumed: set[str],
    ) -> Finding:
        extensions: dict[str, Any] = {}
        finding = Finding(
            rule=diagnostic["rule"],
            severity=_SEVERITY.get(diagnostic.get("severity", "error"), "error"),
            message=diagnostic["message"],
        )
        at = diagnostic.get("at")
        real = os.path.realpath(at) if at else None
        if (
            real is not None
            and self.temp_real is not None
            and os.path.dirname(real) == self.temp_real
            and _SCOPED_CONFIG_NAME.match(os.path.basename(real))
        ):
            extensions["reported_in"] = "rush_scoped_config"
            at = group.get("config")
            real = os.path.realpath(at) if at else None
        elif at is not None:
            finding["line"] = diagnostic["line"]
            finding["column"] = diagnostic["column"]
        if at is not None:
            finding["path"] = at
        rule = diagnostic["rule"]
        if (
            real is None
            or rule.startswith("TS5")
            or rule in _CONFIG_CODES
            or (real.endswith(".json") and real not in consumed)
        ):
            extensions["scope"] = "configuration"
        elif real in set(group.get("requested") or []):
            extensions["scope"] = "requested"
        elif self._is_library(real):
            extensions["scope"] = "engine_library"
        else:
            extensions["scope"] = "dependency"
            extensions["dependency_kind"] = (
                "ambient" if real in set(group.get("ambient") or []) else "import"
            )
        config = group.get("config")
        extensions["config"] = None if config is None else self.display(config)
        extensions["group"] = index
        finding["extensions"] = extensions
        return finding

    def _group_error(
        self, group: dict[str, Any], findings: list[Finding], consumed: set[str]
    ) -> tuple[list[str], dict[str, Any] | None, list[str]]:
        """(codes in A12 table order, error, partial-coverage reasons)."""
        if group.get("error"):
            error = group["error"]
            return (
                [error["code"]],
                {
                    "code": error["code"],
                    "message": error["message"],
                    **error["details"],
                },
                [],
            )
        codes: list[str] = []
        messages: dict[str, str] = {}
        unclassifiable = group.get("unclassifiable") or []
        if unclassifiable:
            codes.append("TSC_UNCLASSIFIABLE")
            messages["TSC_UNCLASSIFIABLE"] = (
                f"tsc: could not classify {len(unclassifiable)} file(s) as module or "
                f"script ({group.get('unclassifiable_reason')}): "
                f"{self.display(unclassifiable[0])}"
            )
        configuration = [
            f for f in findings if f["extensions"]["scope"] == "configuration"
        ]
        if configuration:
            codes.append("TSC_CONFIG_DIAGNOSTICS")
            messages["TSC_CONFIG_DIAGNOSTICS"] = (
                f"tsc: {len(configuration)} configuration diagnostic(s); first: "
                + self._first_configuration(configuration[0])
            )
        if group.get("truncated") and not consumed:
            codes.append("TSC_OUTPUT_TRUNCATED")
            messages["TSC_OUTPUT_TRUNCATED"] = _OUTPUT_TRUNCATED_MESSAGE
        unparsed = group.get("unparsed") or []
        if unparsed:
            codes.append("TSC_OUTPUT_UNPARSED")
            messages["TSC_OUTPUT_UNPARSED"] = (
                f"tsc: {len(unparsed)} output line(s) could not be parsed"
            )
        exit_code = group.get("exit_code") or 0
        if not codes and not findings and exit_code != 0:
            codes.append("TSC_EXIT_UNEXPLAINED")
            messages["TSC_EXIT_UNEXPLAINED"] = (
                f"tsc: exited {exit_code} without diagnostics"
            )
        partial = []
        if group.get("truncated") and consumed:
            partial.append("tsc_listfiles_truncated")
        if group.get("redacted"):
            partial.append("tsc_output_redacted")
        error = {"code": codes[0], "message": messages[codes[0]]} if codes else None
        return codes, error, partial

    def _first_configuration(self, finding: Finding) -> str:
        rule = finding["rule"]
        path = finding.get("path")
        if path is None:
            return f"{rule}: {finding['message']}"
        if "line" in finding:
            return f"{rule} at {self.display(path)}:{finding['line']}:{finding.get('column')}"
        return f"{rule} at {self.display(path)}"

    def result(self, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        group_scopes: list[dict[str, Any]] = []
        statuses: list[ToolStatus] = []
        errors: list[dict[str, Any]] = []
        partial_reasons: list[str] = []
        consumed_all: set[str] = set()
        requested_all: set[str] = set()
        ambient_all: set[str] = set()
        configs: set[str] = set()
        unclassifiable: set[str] = set()
        matched = 0
        analyzed = 0
        for index, group in enumerate(self.data.get("groups") or []):
            consumed = {os.path.realpath(c) for c in group.get("consumed") or []}
            group_findings = [
                self._finding(index, group, d, consumed)
                for d in group.get("diagnostics") or []
            ]
            codes, error, partial = self._group_error(group, group_findings, consumed)
            status: ToolStatus
            if codes:
                status = "error"
            elif any(f.get("severity") == "error" for f in group_findings):
                status = "fail"
            elif group_findings:
                status = "warn"
            else:
                status = "ok"
            statuses.append(status)
            if error is not None:
                errors.append(error)
            partial_reasons.extend(partial)
            findings.extend(group_findings)
            requested = set(group.get("requested") or [])
            if not group.get("error"):
                matched += len(requested)
                analyzed += 1
            requested_all |= requested
            ambient_all |= set(group.get("ambient") or [])
            consumed_all |= consumed
            configs |= set(group.get("configs_used") or [])
            unclassifiable |= set(group.get("unclassifiable") or [])
            source = {c for c in consumed if not self._is_library(c)}
            group_scopes.append(
                {
                    "config": None
                    if group.get("config") is None
                    else self.display(group["config"]),
                    "explicit_override": bool(group.get("explicit_override")),
                    "cwd": None
                    if group.get("cwd") is None
                    else self.display(group["cwd"]),
                    "status": status,
                    "codes": codes,
                    "requested_files": self._show(requested),
                    "dependency_files": self._show(source - requested),
                    "ambient_files": self._show(
                        source & set(group.get("ambient") or [])
                    ),
                    "consumed_file_count": len(source),
                }
            )
        run_errors = list(self.data.get("run_errors") or [])
        residue = (self.data.get("temp") or {}).get("residue") or []
        if residue:
            run_errors.insert(
                0,
                {
                    "code": "TSC_TEMP_RESIDUE",
                    "message": (
                        f"tsc: temporary files left in "
                        f"{self.data['temp']['dir']}: {', '.join(residue)}"
                    ),
                    "details": {"residue": residue},
                    "status": "warn",
                },
            )
        status = self._status(statuses, run_errors)
        error = next(
            (
                {"code": e["code"], "message": e["message"], **(e.get("details") or {})}
                for e in run_errors
            ),
            errors[0] if errors else None,
        )
        source_all = {c for c in consumed_all if not self._is_library(c)}
        excluded = [
            {"path": self.display(e["target"]), "reason": e["reason"]}
            for e in self.data.get("excluded") or []
        ]
        scope = {
            "version": 1,
            "kind": "file",
            "logical_root": self.data.get("logical_root"),
            "requested_targets": [
                self.display(target)
                for target in self.data.get("targets") or [str(self.path)]
            ],
            "requested_file_count": self.data.get("pool_size", 1),
            "matched_file_count": matched,
            "consumed_file_count": len(source_all),
            "dependency_files": self._show(source_all - requested_all),
            "ambient_files": self._show(source_all & ambient_all),
            "configuration_files": self._show(configs),
            "excluded_files": excluded,
            "unclassifiable": bool(unclassifiable),
            "unclassifiable_files": self._show(unclassifiable),
            "explicit_override": any(g["explicit_override"] for g in group_scopes),
            "engine_library_file_count": len(consumed_all - source_all),
            "groups": group_scopes,
        }
        scope["coverage"], scope["reason"] = _coverage(
            analyzed, bool(excluded), bool(errors) or bool(run_errors), partial_reasons
        )
        metadata: dict[str, Any] = {"scope": scope}
        if error is not None:
            metadata["error"] = error
        summary = (
            error["message"]
            if error is not None
            else f"tsc: {len(findings)} finding(s) in {len(group_scopes)} config group(s)"
        )
        return ToolResult(
            tool=tool_name,
            engine="tsc",
            engine_version=None,
            status=status,
            duration_ms=0,
            summary=summary,
            findings=findings,
            raw=None,
            metadata=metadata,
        )

    def _show(self, values: set[str]) -> list[str]:
        return sorted(self.display(v) for v in values)

    @staticmethod
    def _status(
        statuses: list[ToolStatus], run_errors: list[dict[str, Any]]
    ) -> ToolStatus:
        """T16 S16.3: one aggregate over every config group and run error --
        no `skipped` start value, which the new precedence would read as a
        skipped group next to an ok one. No group at all (no TypeScript in
        scope) is `skipped`, with the empty scope recorded by `_coverage`."""
        from ..tools.routing import aggregate_status

        return aggregate_status(
            [*statuses, *(str(e.get("status", "error")) for e in run_errors)]
        )


def _coverage(
    analyzed: int, excluded: bool, errored: bool, partial_reasons: list[str]
) -> tuple[str, str | None]:
    if analyzed == 0:
        return "none", "no_group_analyzed"
    if partial_reasons:
        return "partial", partial_reasons[0]
    if errored:
        return "partial", "group_error"
    if excluded:
        return "partial", "files_excluded"
    return "complete", None
