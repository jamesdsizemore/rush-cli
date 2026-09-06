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

from pathlib import Path
from typing import Any

from rush.review.collection import (
    MAX_AST_DEPTH,
    MAX_FILE_BYTES,
    TODO_PATTERN,
    _collect_reviewable_files,
    _file_size_heuristic,
    _is_source_policy_excluded,
    _missing_docstrings_heuristic,
    _naming_heuristic,
    _read_file_safely,
    _scaffold_marker_heuristic,
    _todo_density_heuristic,
    check_file_heuristics,
    collect_reviewable_files,
    is_source_policy_excluded,
    missing_docstrings_heuristic,
    naming_heuristic,
    read_file_safely,
    scaffold_marker_heuristic,
    todo_density_heuristic,
)
from rush.review.llm import (
    _maybe_call_llm,
    apply_llm_review,
    format_review_prompt,
    maybe_call_llm,
    parse_llm_findings,
)
from rush.review.results import (
    assemble_review_result,
    build_empty_review_result,
    build_error_review_result,
)

from .base import Finding, ToolFn, ToolName, ToolResult
from .common import now_ms


def _extract_review_config(
    config: Any, use_graft: bool
) -> tuple[int, bool, list[str], list[str]]:
    """Extract review thresholds, flags, markers, and exclusions from configuration."""
    max_lines = 400
    effective_use_graft = use_graft
    scaffold_markers: list[str] = []
    source_policy_exclude: list[str] = []

    if config is not None and hasattr(config, "review"):
        review_cfg = config.review
        max_lines = getattr(review_cfg, "max_file_lines", 400)
        effective_use_graft = use_graft or getattr(review_cfg, "use_graft", False)
        scaffold_markers = list(getattr(review_cfg, "scaffold_markers", []))
        source_policy_exclude = list(getattr(review_cfg, "source_policy_exclude", []))

    return max_lines, effective_use_graft, scaffold_markers, source_policy_exclude


def _resolve_graft_findings(
    path: Path, use_graft: bool, graft_provider: Any = None
) -> tuple[list[Finding], str]:
    """Retrieve graft context findings if requested and available."""
    if not use_graft:
        return [], "not-requested"

    provider = graft_provider
    if provider is None:
        from ..integrations import LocalGraftContext

        provider = LocalGraftContext()

    project_root = path if path.is_dir() else path.parent
    if provider.available(project_root):
        return list(provider.context_for(path)), "used"
    return [], "skipped-unavailable"


def _evaluate_target_heuristics(
    targets: list[Path],
    root: Path,
    max_lines: int,
    scaffold_markers: list[str],
    source_policy_exclude: list[str],
) -> list[Finding]:
    """Evaluate all heuristic checks across discovered reviewable targets."""
    findings: list[Finding] = []
    for target_path in targets:
        findings.extend(
            check_file_heuristics(
                target_path,
                root=root,
                max_lines=max_lines,
                scaffold_markers=scaffold_markers,
                source_policy_exclude=source_policy_exclude,
            )
        )
    return findings


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
        self,
        path: Path,
        use_llm: bool = False,
        use_graft: bool = False,
        changed_files: list[str] | None = None,
    ) -> ToolResult:
        return self.run(
            path,
            use_llm=use_llm,
            use_graft=use_graft,
            changed_files=changed_files,
        )

    def run(
        self,
        path: Path,
        *,
        use_llm: bool = False,
        use_graft: bool = False,
        changed_files: list[str] | None = None,
        graft_provider=None,
        config=None,
    ) -> ToolResult:
        max_lines, use_graft, markers, exclude = _extract_review_config(
            config, use_graft
        )
        start = now_ms()
        root = path if path.is_dir() else path.parent

        try:
            targets, scope = collect_reviewable_files(path, changed_files=changed_files)
        except ValueError as error:
            return build_error_review_result(str(error), start)

        if not targets:
            return build_empty_review_result(path, scope, start)

        findings = _evaluate_target_heuristics(
            targets, root, max_lines, markers, exclude
        )

        graft_findings, graft_state = _resolve_graft_findings(
            path, use_graft, graft_provider
        )
        findings.extend(graft_findings)

        review_kind, review_provider, llm_findings = apply_llm_review(findings, use_llm)
        findings.extend(llm_findings)

        return assemble_review_result(
            findings,
            start_ms=start,
            scope=scope,
            graft_state=graft_state,
            review_kind=review_kind,
            review_provider=review_provider,
        )


__all__ = [
    "MAX_AST_DEPTH",
    "MAX_FILE_BYTES",
    "TODO_PATTERN",
    "ReviewTool",
    "_collect_reviewable_files",
    "_file_size_heuristic",
    "_is_source_policy_excluded",
    "_maybe_call_llm",
    "_missing_docstrings_heuristic",
    "_naming_heuristic",
    "_read_file_safely",
    "_scaffold_marker_heuristic",
    "_todo_density_heuristic",
    "assemble_review_result",
    "collect_reviewable_files",
    "format_review_prompt",
    "is_source_policy_excluded",
    "maybe_call_llm",
    "missing_docstrings_heuristic",
    "naming_heuristic",
    "parse_llm_findings",
    "read_file_safely",
    "scaffold_marker_heuristic",
    "todo_density_heuristic",
]
