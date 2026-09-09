"""AI code attribution, git trailer parsing, and line survival analysis tool."""

from __future__ import annotations

import re
import time
from collections import Counter
from math import sqrt
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms, run_subprocess

AI_TRAILER_PATTERNS = (
    re.compile(
        r"co-authored-by:\s*.*(?:claude|gpt|copilot|gemini|anthropic|openai|cursor).*",
        re.IGNORECASE,
    ),
    re.compile(r"ai-generated:\s*true", re.IGNORECASE),
    re.compile(r"assisted-by:\s*.*", re.IGNORECASE),
    re.compile(r"model:\s*.*(?:claude|gpt|gemini).*", re.IGNORECASE),
)

FIX_PATTERNS = (
    re.compile(r"^fix(?:ing|\([^\)]+\))?:", re.IGNORECASE),
    re.compile(r"^bug(?:fix)?:", re.IGNORECASE),
    re.compile(r"fixes\s+#\d+", re.IGNORECASE),
    re.compile(r"closes\s+#\d+", re.IGNORECASE),
)


class GitTrailerParser:
    """Extracts AI attribution and author metadata from git logs."""

    @staticmethod
    def parse_commit_records(raw_log: str) -> list[dict[str, Any]]:
        commits = []
        raw_records = raw_log.split("\x01")
        for rec in raw_records:
            parts = rec.strip().split("\x00")
            if len(parts) < 5:
                continue
            commit_hash, author_name, author_email, ts_str, body = (
                parts[0].strip(),
                parts[1].strip(),
                parts[2].strip(),
                parts[3].strip(),
                parts[4].strip(),
            )
            try:
                ts = int(ts_str)
            except ValueError:
                ts = int(time.time())

            is_ai_generated = False
            is_ai_assisted = False

            if "ai-generated: true" in body.lower():
                is_ai_generated = True
            elif any(p.search(body) for p in AI_TRAILER_PATTERNS):
                is_ai_assisted = True
            elif any(
                name in author_name.lower() or name in author_email.lower()
                for name in ("claude", "copilot", "bot")
            ):
                is_ai_generated = True

            is_fix = any(p.search(body) for p in FIX_PATTERNS)

            commits.append(
                {
                    "hash": commit_hash,
                    "author": author_name,
                    "email": author_email,
                    "timestamp": ts,
                    "body": body,
                    "is_ai_generated": is_ai_generated,
                    "is_ai_assisted": is_ai_assisted,
                    "is_fix": is_fix,
                }
            )
        return commits

    @staticmethod
    def link_fix_commits_to_failure(
        commits: list[dict[str, Any]], failure_id: str, project_root: Path
    ) -> list[str]:
        """Links every `is_fix=True` commit's SHA to the failure record it fixed.

        Stores only the commit SHA (Phase 62 §6.5 Invariant 4) — never the commit body/diff.
        Returns the SHAs of the commits linked.
        """
        from ..session_memory import record_fix_attribution

        linked = []
        for commit in commits:
            if commit["is_fix"]:
                record_fix_attribution(project_root, commit, failure_id)
                linked.append(commit["hash"])
        return linked


class LineSurvivalEngine:
    """Computes empirical line survival rates and defect correlation using git blame."""

    WINDOWS = (30, 60, 90)

    @staticmethod
    def _revision_at(target_dir: Path, timestamp: int) -> str | None:
        result = run_subprocess(
            [
                "git",
                "rev-list",
                "--first-parent",
                "-1",
                f"--before=@{timestamp}",
                "HEAD",
            ],
            cwd=target_dir,
        )
        return (
            result.stdout.strip()
            if result.returncode == 0 and result.stdout.strip()
            else None
        )

    @staticmethod
    def _tree_line_origins(
        target_dir: Path, revision: str
    ) -> Counter[tuple[str, str, int]] | None:
        files_res = run_subprocess(
            ["git", "ls-tree", "-r", "-z", "--name-only", revision], cwd=target_dir
        )
        if files_res.returncode != 0:
            return None

        origins: Counter[tuple[str, str, int]] = Counter()
        for rel_file in filter(None, files_res.stdout.split("\0")):
            blame_res = run_subprocess(
                [
                    "git",
                    "blame",
                    "--line-porcelain",
                    "--follow",
                    revision,
                    "--",
                    rel_file,
                ],
                cwd=target_dir,
            )
            if blame_res.returncode != 0:
                return None
            origin = filename = None
            for line in blame_res.stdout.splitlines():
                match = re.match(r"^\^?([0-9a-f]{40}) (\d+) \d+(?: \d+)?$", line)
                if match:
                    origin = (match.group(1), int(match.group(2)))
                    filename = None
                elif line.startswith("filename "):
                    filename = line[9:]
                elif line.startswith("\t"):
                    if origin is None or filename is None:
                        return None
                    origins[(origin[0], filename, origin[1])] += 1
        return origins

    @classmethod
    def compute_windows(
        cls,
        target_dir: Path,
        now_ts: int,
        *,
        unavailable_reason: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Measure each historical line cohort through the observation time."""
        end_revision = (
            None if unavailable_reason else cls._revision_at(target_dir, now_ts)
        )
        if not unavailable_reason and end_revision is None:
            unavailable_reason = "no-history-at-observation-end"
        current = (
            None
            if unavailable_reason or end_revision is None
            else cls._tree_line_origins(target_dir, end_revision)
        )
        results: dict[str, dict[str, Any]] = {}
        for days in cls.WINDOWS:
            reason = unavailable_reason or (
                "current-cohort-unavailable" if current is None else None
            )
            cohort: Counter[tuple[str, str, int]] | None = None
            if reason is None:
                cutoff = now_ts - days * 86400
                boundary = cls._revision_at(target_dir, cutoff)
                if not boundary:
                    reason = "no-history-before-window"
                else:
                    cohort = cls._tree_line_origins(target_dir, boundary)
                    if cohort is None:
                        reason = "historical-cohort-unavailable"

            original = sum(cohort.values()) if cohort is not None else 0
            if (
                reason is None
                and current is not None
                and cohort is not None
                and original > 0
            ):
                surviving = sum(
                    min(count, current.get(origin, 0))
                    for origin, count in cohort.items()
                )
                lost = original - surviving
                survival_rate: float | None = round(surviving / original, 4)
                churn_rate: float | None = round(lost / original, 4)
            elif reason is None and original == 0:
                surviving = lost = 0
                survival_rate = churn_rate = None
                reason = "empty-cohort"
            else:
                surviving = lost = 0
                survival_rate = churn_rate = None

            results[f"{days}d"] = {
                "window_days": days,
                "original_cohort_lines": original,
                "surviving_lines": surviving,
                "lost_lines": lost,
                "survival_rate": survival_rate,
                "churn_rate": churn_rate,
                "complete": reason is None,
                "unavailable_reason": reason,
            }
        return results

    @staticmethod
    def compute_survival(
        target_dir: Path,
        now_ts: int,
        max_files: int = 50,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        """Calculates 30d, 60d, 90d survival rates and code churn from git blame.

        Returns:
            (survival_30d, survival_60d, survival_90d, churn_rate)
        """
        del max_files  # Compatibility parameter; complete windows cannot be truncated.
        windows = LineSurvivalEngine.compute_windows(target_dir, now_ts)
        rates = [windows[f"{days}d"]["survival_rate"] for days in (30, 60, 90)]
        churn = windows["30d"]["churn_rate"]
        return rates[0], rates[1], rates[2], churn


class ProvenanceAiTool(ToolFn):
    """Audits git history for AI attribution, trailer integrity, and line survival curves."""

    name = "provenance-ai"

    @staticmethod
    def compute_phi(pairs: list[tuple[bool, bool]]) -> float | None:
        """Return phi for binary attribution/linkage observations."""
        n11 = sum(1 for attributed, linked in pairs if attributed and linked)
        n10 = sum(1 for attributed, linked in pairs if attributed and not linked)
        n01 = sum(1 for attributed, linked in pairs if not attributed and linked)
        n00 = sum(1 for attributed, linked in pairs if not attributed and not linked)
        denominator = sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
        if denominator == 0:
            return None
        return round((n11 * n00 - n10 * n01) / denominator, 4)

    @staticmethod
    def _origin_attribution(target_dir: Path, commit_hash: str) -> bool | None:
        log_format = "%H%x00%an%x00%ae%x00%at%x00%B%x01"
        result = run_subprocess(
            ["git", "show", "-s", f"--format={log_format}", commit_hash],
            cwd=target_dir,
        )
        records = GitTrailerParser.parse_commit_records(result.stdout)
        if result.returncode != 0 or len(records) != 1:
            return None
        return bool(records[0]["is_ai_generated"] or records[0]["is_ai_assisted"])

    @staticmethod
    def _deleted_line_origins(
        target_dir: Path, parent: str, commit_hash: str
    ) -> set[str] | None:
        diff = run_subprocess(
            [
                "git",
                "diff",
                "--no-ext-diff",
                "--find-renames",
                "--unified=0",
                parent,
                commit_hash,
                "--",
            ],
            cwd=target_dir,
        )
        if diff.returncode != 0:
            return None

        old_path: str | None = None
        ranges: list[tuple[str, int, int]] = []
        for line in diff.stdout.splitlines():
            if line.startswith("--- "):
                value = line[4:]
                old_path = None if value == "/dev/null" else value.removeprefix("a/")
                continue
            match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+", line)
            if match and old_path is not None:
                count = int(match.group(2) or "1")
                if count > 0:
                    ranges.append((old_path, int(match.group(1)), count))

        origins: set[str] = set()
        for rel_file, start, count in ranges:
            blame = run_subprocess(
                [
                    "git",
                    "blame",
                    "--line-porcelain",
                    "-L",
                    f"{start},{start + count - 1}",
                    parent,
                    "--",
                    rel_file,
                ],
                cwd=target_dir,
            )
            if blame.returncode != 0:
                return None
            for line in blame.stdout.splitlines():
                match = re.match(r"^\^?([0-9a-f]{40})\s", line)
                if match:
                    origins.add(match.group(1))
        return origins or None

    @classmethod
    def _defect_association(
        cls,
        target_dir: Path,
        now_ts: int,
        *,
        unavailable_reason: str | None,
    ) -> dict[str, Any]:
        window_days = 90
        method = "first-parent deleted-line origin linkage"
        interpretation = "observed association, not causality"
        excluded = {
            "merge_commit": 0,
            "missing_parent": 0,
            "ambiguous_origin_link": 0,
        }
        empty_counts = {"n11": 0, "n10": 0, "n01": 0, "n00": 0}
        if unavailable_reason is not None:
            return {
                "phi": None,
                "sample_count": 0,
                "window_days": window_days,
                "linkage_method": method,
                "interpretation": interpretation,
                "counts": empty_counts,
                "excluded": excluded,
                "unavailable_reason": unavailable_reason,
            }

        cutoff = now_ts - window_days * 86400
        end_revision = LineSurvivalEngine._revision_at(target_dir, now_ts)
        boundary = LineSurvivalEngine._revision_at(target_dir, cutoff)
        if not boundary or not end_revision:
            unavailable_reason = "no-history-before-window"
            cohort_origins: set[str] = set()
        else:
            cohort = LineSurvivalEngine._tree_line_origins(target_dir, boundary)
            if cohort is None:
                unavailable_reason = "historical-cohort-unavailable"
                cohort_origins = set()
            else:
                cohort_origins = {origin[0] for origin in cohort}

        linked_origins: set[str] = set()
        if unavailable_reason is None and end_revision is not None:
            log_format = "%H%x00%an%x00%ae%x00%at%x00%B%x01"
            fixes_res = run_subprocess(
                [
                    "git",
                    "log",
                    f"--since=@{cutoff}",
                    f"--until=@{now_ts}",
                    f"--format={log_format}",
                    end_revision,
                ],
                cwd=target_dir,
            )
            if fixes_res.returncode != 0:
                unavailable_reason = "history-read-failed"
            else:
                for commit in GitTrailerParser.parse_commit_records(fixes_res.stdout):
                    if not commit["is_fix"]:
                        continue
                    parents_res = run_subprocess(
                        ["git", "rev-list", "--parents", "-n", "1", commit["hash"]],
                        cwd=target_dir,
                    )
                    parent_parts = parents_res.stdout.split()
                    if parents_res.returncode != 0 or len(parent_parts) < 2:
                        excluded["missing_parent"] += 1
                        continue
                    if len(parent_parts) > 2:
                        excluded["merge_commit"] += 1
                        continue
                    origins = cls._deleted_line_origins(
                        target_dir, parent_parts[1], commit["hash"]
                    )
                    if origins is None:
                        excluded["ambiguous_origin_link"] += 1
                        continue
                    linked_origins.update(origins & cohort_origins)

        pairs: list[tuple[bool, bool]] = []
        if unavailable_reason is None:
            for origin in sorted(cohort_origins):
                attributed = cls._origin_attribution(target_dir, origin)
                if attributed is None:
                    excluded["ambiguous_origin_link"] += 1
                    continue
                pairs.append((attributed, origin in linked_origins))

        counts = {
            "n11": sum(1 for attributed, linked in pairs if attributed and linked),
            "n10": sum(1 for attributed, linked in pairs if attributed and not linked),
            "n01": sum(1 for attributed, linked in pairs if not attributed and linked),
            "n00": sum(
                1 for attributed, linked in pairs if not attributed and not linked
            ),
        }
        phi = cls.compute_phi(pairs)
        if unavailable_reason is None and phi is None:
            unavailable_reason = "zero-variance"
        return {
            "phi": phi,
            "sample_count": len(pairs),
            "window_days": window_days,
            "linkage_method": method,
            "interpretation": interpretation,
            "counts": counts,
            "excluded": excluded,
            "unavailable_reason": unavailable_reason,
        }

    @property
    def mcp_description(self) -> str:
        return (
            "Analyze git commit trailers for AI attribution, calculate empirical code survival "
            "curves (30/60/90d), and compute defect correlation. Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, permissions=permissions)

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        max_commits: int = 100,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        target_dir = path if path.is_dir() else path.parent
        target_dir = target_dir.resolve()

        # Check if target is inside a git repository
        git_check = run_subprocess(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=target_dir
        )
        if git_check.returncode != 0 or git_check.stdout.strip() != "true":
            return ToolResult(
                tool=self.name,
                engine="git-provenance",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"provenance-ai: '{path}' is not inside a valid Git repository.",
                findings=[],
                raw=None,
            )

        # Check if shallow clone
        shallow_res = run_subprocess(
            ["git", "rev-parse", "--is-shallow-repository"], cwd=target_dir
        )
        is_shallow = (
            shallow_res.returncode == 0 and shallow_res.stdout.strip() == "true"
        ) or (target_dir / ".git" / "shallow").is_file()

        # Extract git commit history
        log_format = "%H%x00%an%x00%ae%x00%at%x00%B%x01"
        log_res = run_subprocess(
            ["git", "log", f"-n{max_commits}", f"--format={log_format}"],
            cwd=target_dir,
        )

        findings: list[Finding] = []
        if is_shallow:
            findings.append(
                Finding(
                    path=".git",
                    line=1,
                    column=1,
                    rule="provenance-ai/shallow-clone",
                    rule_id="WARN_SHALLOW_CLONE",
                    severity="warn",
                    message="Repository is a shallow clone; provenance curves reflect partial history.",
                    fingerprint="shallow-clone-warning",
                )
            )

        commits = GitTrailerParser.parse_commit_records(log_res.stdout)
        now_ts = int(time.time())
        history_reason = None
        if is_shallow:
            history_reason = "shallow-history"
        elif log_res.returncode != 0 or not commits:
            history_reason = "no-history"

        ai_generated_count = sum(1 for c in commits if c["is_ai_generated"])
        ai_assisted_count = sum(1 for c in commits if c["is_ai_assisted"])
        human_count = sum(
            1 for c in commits if not c["is_ai_generated"] and not c["is_ai_assisted"]
        )
        total_commits = len(commits)

        survival_windows = LineSurvivalEngine.compute_windows(
            target_dir,
            now_ts,
            unavailable_reason=history_reason,
        )
        fix_commits = sum(1 for c in commits if c["is_fix"])
        association = self._defect_association(
            target_dir,
            now_ts,
            unavailable_reason=history_reason,
        )

        metrics = {
            "survival_rate_30d": survival_windows["30d"]["survival_rate"],
            "survival_rate_60d": survival_windows["60d"]["survival_rate"],
            "survival_rate_90d": survival_windows["90d"]["survival_rate"],
            "churn_rate_30d": survival_windows["30d"]["churn_rate"],
            "churn_rate_60d": survival_windows["60d"]["churn_rate"],
            "churn_rate_90d": survival_windows["90d"]["churn_rate"],
            "defect_correlation": association["phi"],
            "churn_rate": survival_windows["30d"]["churn_rate"],
            "total_commits": total_commits,
            "ai_generated_count": ai_generated_count,
            "ai_assisted_count": ai_assisted_count,
            "human_count": human_count,
            "shallow_history": is_shallow,
        }

        status: ToolStatus = "warn" if findings or history_reason is not None else "ok"
        exec_meta = build_execution_metadata(
            mode="executed",
            requested=permissions,
            granted=permissions,
            producer="provenance-ai",
        )

        survival_30 = metrics["survival_rate_30d"]
        phi = association["phi"]
        if survival_30 is None or phi is None:
            summary = (
                f"Audited {total_commits} commits; historical statistic unavailable: "
                f"{association['unavailable_reason'] or survival_windows['30d']['unavailable_reason']}."
            )
        else:
            summary = (
                f"Audited {total_commits} commits: {ai_generated_count} AI-generated, "
                f"{ai_assisted_count} AI-assisted, {human_count} human. "
                f"30d survival: {survival_30:.1%}, observed association: {phi:+.2f}"
            )

        return ToolResult(
            tool=self.name,
            engine="git-provenance",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics=metrics,
            raw={
                "commits": commits[:20],
                "commits_audited": total_commits,
                "total_commits": total_commits,
                "ai_generated_count": ai_generated_count,
                "ai_assisted_count": ai_assisted_count,
                "human_count": human_count,
            },
            metadata={
                "survival_rates": {
                    key: value["survival_rate"]
                    for key, value in survival_windows.items()
                },
                "survival_windows": survival_windows,
                "defect_correlation": {
                    "score": phi,
                    "fix_commits": fix_commits,
                },
                "defect_association": association,
                "evidence": association,
                "execution": exec_meta,
            },
        )


__all__ = ["GitTrailerParser", "LineSurvivalEngine", "ProvenanceAiTool"]
