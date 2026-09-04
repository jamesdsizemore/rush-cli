"""AI code attribution, git trailer parsing, and line survival analysis tool."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolResult
from .common import elapsed_ms, now_ms, run_subprocess
from .schemas import ProvenanceMetrics

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


class LineSurvivalEngine:
    """Computes empirical line survival rates and defect correlation using git blame."""

    @staticmethod
    def compute_survival(
        target_dir: Path,
        now_ts: int,
        max_files: int = 50,
    ) -> tuple[float, float, float, float]:
        """Calculates 30d, 60d, 90d survival rates and code churn from git blame.

        Returns:
            (survival_30d, survival_60d, survival_90d, churn_rate)
        """
        # Find tracked files
        ls_res = run_subprocess(["git", "ls-files"], cwd=target_dir)
        if ls_res.returncode != 0 or not ls_res.stdout.strip():
            return 1.0, 1.0, 1.0, 0.0

        tracked_files = [
            f.strip()
            for f in ls_res.stdout.splitlines()
            if f.strip()
            and not any(part.startswith(".") for part in Path(f.strip()).parts)
        ][:max_files]

        total_lines = 0
        survived_30d = 0
        survived_60d = 0
        survived_90d = 0

        for rel_file in tracked_files:
            file_path = target_dir / rel_file
            if not file_path.is_file() or file_path.stat().st_size > 1_000_000:
                continue

            blame_res = run_subprocess(
                ["git", "blame", "--line-porcelain", rel_file],
                cwd=target_dir,
            )
            if blame_res.returncode != 0:
                continue

            for line in blame_res.stdout.splitlines():
                if line.startswith("author-time "):
                    try:
                        author_time = int(line.split()[1])
                        age_days = (now_ts - author_time) / 86400.0
                        total_lines += 1
                        if age_days >= 30:
                            survived_30d += 1
                        if age_days >= 60:
                            survived_60d += 1
                        if age_days >= 90:
                            survived_90d += 1
                    except (IndexError, ValueError):
                        continue

        if total_lines == 0:
            return 1.0, 1.0, 1.0, 0.0

        r30 = round(survived_30d / total_lines, 4)
        r60 = round(survived_60d / total_lines, 4)
        r90 = round(survived_90d / total_lines, 4)
        # Churn rate: proportion of lines rewritten in under 30 days
        churn = round(1.0 - r30, 4)

        return r30, r60, r90, churn


class ProvenanceAiTool(ToolFn):
    """Audits git history for AI attribution, trailer integrity, and line survival curves."""

    name = "provenance-ai"

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

        ai_generated_count = sum(1 for c in commits if c["is_ai_generated"])
        ai_assisted_count = sum(1 for c in commits if c["is_ai_assisted"])
        human_count = sum(
            1 for c in commits if not c["is_ai_generated"] and not c["is_ai_assisted"]
        )
        total_commits = len(commits)

        # Calculate survival curves
        surv_30, surv_60, surv_90, churn = LineSurvivalEngine.compute_survival(
            target_dir, now_ts
        )

        # Calculate defect correlation
        fix_commits = sum(1 for c in commits if c["is_fix"])
        ai_commits_count = ai_generated_count + ai_assisted_count

        if ai_commits_count > 0 and total_commits > 0:
            defect_ratio = round((fix_commits / total_commits), 4)
            defect_correlation = round(
                min(
                    1.0,
                    max(
                        -1.0, (defect_ratio * (ai_commits_count / total_commits)) - 0.5
                    ),
                ),
                4,
            )
        else:
            defect_correlation = 0.0

        # Validate with strict schema
        provenance_metrics = ProvenanceMetrics(
            survival_rate_30d=surv_30,
            survival_rate_60d=surv_60,
            survival_rate_90d=surv_90,
            defect_correlation=defect_correlation,
            churn_rate=churn,
        )

        metrics = {
            "survival_rate_30d": provenance_metrics.survival_rate_30d,
            "survival_rate_60d": provenance_metrics.survival_rate_60d,
            "survival_rate_90d": provenance_metrics.survival_rate_90d,
            "defect_correlation": provenance_metrics.defect_correlation,
            "churn_rate": provenance_metrics.churn_rate,
            "total_commits": total_commits,
            "ai_generated_count": ai_generated_count,
            "ai_assisted_count": ai_assisted_count,
            "human_count": human_count,
            "shallow_history": is_shallow,
        }

        status = "warn" if findings else "ok"
        exec_meta = build_execution_metadata(
            mode="executed",
            requested=permissions,
            granted=permissions,
            producer="provenance-ai",
        )

        summary = (
            f"Audited {total_commits} commits: {ai_generated_count} AI-generated, "
            f"{ai_assisted_count} AI-assisted, {human_count} human. "
            f"30d survival: {surv_30:.1%}, defect correlation: {defect_correlation:+.2f}"
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
                    "30d": surv_30,
                    "60d": surv_60,
                    "90d": surv_90,
                },
                "defect_correlation": {
                    "score": defect_correlation,
                    "fix_commits": fix_commits,
                },
                "execution": exec_meta,
            },
        )


__all__ = ["GitTrailerParser", "LineSurvivalEngine", "ProvenanceAiTool"]
