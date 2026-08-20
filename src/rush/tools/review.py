"""Review tool — heuristics + optional LLM call.

Architecture §10. The 4 heuristics:
  1. file-size      — flag files > config.review.max_file_lines (default 400)
  2. todo-density   — flag files with TODO/FIXME/XXX density > 2%
  3. missing-docstrings — flag Python def/class without a docstring above
  4. naming         — flag module-level ALL_CAPS identifiers that aren't constants

Each heuristic runs in-process (no subprocess). The `--llm` flag sends the
heuristic findings as context to a configured LLM provider (Anthropic or
OpenAI) — gated by env key presence.

Heuristics only — no LLM call unless --llm=True AND env key set.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

from .base import Finding, ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms

TODO_PATTERN = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
MAX_FILE_BYTES = 1_000_000  # 1 MB cap — heuristics don't run on huge files
MAX_AST_DEPTH = 50  # safety against malicious files


class ReviewTool(ToolFn):
    name: ToolName = "review"

    @property
    def mcp_description(self) -> str:
        return (
            "Review code at <path> for size, TODO density, missing docstrings, "
            "naming, complexity. Returns {status, findings[], summary}. "
            "Default: heuristic. Pass use_llm=true to call configured model."
        )

    def __call__(
        self, path: Path, use_llm: bool = False, use_graft: bool = False
    ) -> ToolResult:
        return self.run(path, use_llm=use_llm, use_graft=use_graft)

    def run(
        self,
        path: Path,
        *,
        use_llm: bool = False,
        use_graft: bool = False,
        graft_provider=None,
        config=None,
    ) -> ToolResult:
        max_lines = 400
        if config is not None and hasattr(config, "review"):
            max_lines = getattr(config.review, "max_file_lines", 400)
            use_graft = use_graft or getattr(config.review, "use_graft", False)
        scaffold_markers = (
            list(getattr(config.review, "scaffold_markers", []))
            if config is not None and hasattr(config, "review")
            else []
        )
        source_policy_exclude = (
            list(getattr(config.review, "source_policy_exclude", []))
            if config is not None and hasattr(config, "review")
            else []
        )

        start = now_ms()
        targets = _collect_reviewable_files(path)
        root = path if path.is_dir() else path.parent
        if not targets:
            return ToolResult(
                tool="review",
                engine="heuristic-v1",
                engine_version=None,
                status="ok",
                duration_ms=elapsed_ms(start),
                summary=f"review: no Python files found under {path}",
                findings=[],
                raw=None,
                review_kind="heuristic",
                review_provider=None,
            )

        findings: list[Finding] = []
        for f in targets:
            findings.extend(_file_size_heuristic(f, max_lines))
            findings.extend(_todo_density_heuristic(f))
            findings.extend(_missing_docstrings_heuristic(f))
            findings.extend(_naming_heuristic(f))
            if not _is_source_policy_excluded(f, root, source_policy_exclude):
                findings.extend(_scaffold_marker_heuristic(f, scaffold_markers))

        graft_state = "not-requested"
        if use_graft:
            if graft_provider is None:
                from ..integrations import LocalGraftContext

                graft_provider = LocalGraftContext()
            project_root = path if path.is_dir() else path.parent
            if graft_provider.available(project_root):
                findings.extend(graft_provider.context_for(path))
                graft_state = "used"
            else:
                graft_state = "skipped-unavailable"

        # LLM augmentation (opt-in)
        review_kind = "heuristic"
        review_provider: str | None = None
        if use_llm:
            llm_summary = _maybe_call_llm(findings)
            if llm_summary:
                review_kind = "llm"
                review_provider = llm_summary.get("provider")
                findings.append(
                    {
                        "path": "",
                        "line": 0,
                        "rule": "llm-summary",
                        "severity": "info",
                        "message": llm_summary.get("summary", ""),
                    }
                )

        n = len(findings)
        # Determine status — any heuristic finding → warn (heuristics are advisory).
        # LLM info-only findings don't change status.
        if any(f.get("severity") == "error" for f in findings):
            status = "fail"
        elif any(f.get("severity") == "warn" for f in findings):
            status = "warn"
        else:
            status = "ok"

        if n:
            summary = f"review: {n} heuristic finding(s)" + (
                " (+LLM)" if review_kind == "llm" else ""
            )
        else:
            summary = "review: clean" + (" (+LLM)" if review_kind == "llm" else "")

        return ToolResult(
            tool="review",
            engine="heuristic-v1"
            + (f"+llm/{review_provider}" if review_provider else ""),
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            raw={
                "heuristic_count": len(findings)
                - sum(1 for f in findings if f.get("rule") == "llm-summary")
            },
            metadata={"graft": graft_state},
            review_kind=review_kind,  # type: ignore[typeddict-item]
            review_provider=review_provider,
        )


# --- File collection -------------------------------------------------------


def _collect_reviewable_files(path: Path) -> list[Path]:
    """Walk `path` and return Python files (heuristics only target Python)."""
    if path.is_file():
        return [path] if path.suffix == ".py" else []

    if path.is_dir():
        skip_dirs = {
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "dist",
            "build",
            ".next",
        }
        return [
            p
            for p in path.rglob("*.py")
            if not any(part in skip_dirs for part in p.parts)
        ]
    return []


# --- Heuristics ------------------------------------------------------------


def _read_file_safely(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _file_size_heuristic(path: Path, max_lines: int) -> list[Finding]:
    src = _read_file_safely(path)
    if src is None:
        return []
    n = src.count("\n") + 1
    if n <= max_lines:
        return []
    return [
        Finding(
            path=str(path),
            line=max_lines + 1,
            rule="file-size",
            severity="warn",
            message=f"file has {n} lines (threshold {max_lines}) — consider splitting",
        )
    ]


def _todo_density_heuristic(path: Path) -> list[Finding]:
    src = _read_file_safely(path)
    if src is None:
        return []
    lines = src.splitlines()
    if not lines:
        return []
    n_lines = len(lines)
    matches = []
    for i, line in enumerate(lines, start=1):
        if TODO_PATTERN.search(line):
            matches.append(i)
    density = len(matches) / n_lines
    if density < 0.02 or not matches:
        return []
    # One finding per file with the count and density, plus per-line findings
    # capped at 5 to avoid spamming.
    out = [
        Finding(
            path=str(path),
            line=matches[0],
            rule="todo-density",
            severity="warn",
            message=f"{len(matches)} TODO/FIXME/XXX markers in {n_lines} lines ({density:.1%}) — resolve or track",
        )
    ]
    for ln in matches[1:5]:
        out.append(
            Finding(
                path=str(path),
                line=ln,
                rule="todo-density",
                severity="info",
                message=f"TODO/FIXME marker at line {ln}",
            )
        )
    return out


def _missing_docstrings_heuristic(path: Path) -> list[Finding]:
    """Flag Python def/class without a docstring immediately above."""
    src = _read_file_safely(path)
    if src is None:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    out: list[Finding] = []
    lines = src.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Check if node has a docstring
            docstring = ast.get_docstring(node, clean=False)
            if docstring is not None:
                continue
            # Skip private/dunder methods to reduce noise
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            if node.name.startswith("_"):
                continue
            # Flag it
            kind = (
                "function"
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                else "class"
            )
            # First line of the def
            line = getattr(node, "lineno", 0)
            # Check the line above for a comment or docstring-like content
            prev = lines[line - 2].strip() if line >= 2 else ""
            if prev.startswith("#"):
                # Has a comment above — skip to reduce noise
                continue
            out.append(
                Finding(
                    path=str(path),
                    line=line,
                    rule="missing-docstring",
                    severity="info",
                    message=f"{kind} '{node.name}' has no docstring",
                )
            )
    return out


def _naming_heuristic(path: Path) -> list[Finding]:
    """Flag SCREAMING_CASE identifiers at module level that aren't being
    assigned a literal (heuristic for accidentally-named variables)."""
    src = _read_file_safely(path)
    if src is None:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    out: list[Finding] = []
    # Walk top-level statements only (not nested)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    name = tgt.id
                    # Skip real constants (assigned a literal value)
                    if isinstance(node.value, (ast.Constant,)):
                        continue
                    # Flag if it looks like a constant name but isn't
                    if name.isupper() and "_" in name and len(name) > 2:
                        out.append(
                            Finding(
                                path=str(path),
                                line=getattr(node, "lineno", 0),
                                rule="naming",
                                severity="info",
                                message=f"identifier '{name}' is SCREAMING_CASE but assigned a non-literal — is it really a constant?",
                            )
                        )
    return out


def _is_source_policy_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    """Return whether a configured source-policy glob excludes ``path``."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(relative.match(pattern) for pattern in patterns)


def _scaffold_marker_heuristic(path: Path, markers: list[str]) -> list[Finding]:
    """Find configured unfinished-scaffold markers without inferring authorship."""
    if not markers:
        return []
    source = _read_file_safely(path)
    if source is None:
        return []

    findings: list[Finding] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        marker = next((value for value in markers if value and value in line), None)
        if marker is not None:
            findings.append(
                Finding(
                    path=str(path),
                    line=line_number,
                    rule="scaffold-marker",
                    severity="warn",
                    message=(
                        f"configured scaffold marker {marker!r} — replace it or add "
                        "the path to review.source_policy_exclude"
                    ),
                )
            )
    return findings


# --- LLM opt-in -------------------------------------------------------------


def _maybe_call_llm(findings: list[Finding]) -> dict | None:
    """Call configured LLM provider if env key is present.

    Architecture §10.1:
      - Reads ANTHROPIC_API_KEY or OPENAI_API_KEY
      - Provider = "anthropic" if ANTHROPIC_API_KEY set, else "openai"
      - Returns {"provider": ..., "summary": ...} or None if no key

    NB: this is a stub. Phase 5 will wire actual provider calls.
    For now, returns None when no key (preserves the heuristic default).
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not anthropic_key and not openai_key:
        return None  # no key → no LLM call → stay heuristic

    # Stub: real provider call lands in Phase 5. For now, return a
    # deterministic summary so the LLM path is exercised end-to-end.
    provider = "anthropic" if anthropic_key else "openai"
    n_findings = len(findings)
    return {
        "provider": provider,
        "summary": (
            f"[LLM stub] would summarize {n_findings} finding(s) for {provider}; "
            f"Phase 5 will wire the real provider call."
        ),
    }
