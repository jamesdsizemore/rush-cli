"""AI Code Attribution and Provenance Auditor Tool (PR50.4).

Parses Git commit trailers (Co-authored-by, Generated-by, Model, Agent) to audit
AI code provenance, detects shallow repository history, and deterministically
records 30/60/90-day survival states per D50-12 / PR50.0.5.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, ClassVar

from .base import Finding, ToolFn, ToolResult
from .common import elapsed_ms, now_ms, run_subprocess, skipped_result


class ProvenanceAiTool(ToolFn):
    """Audits AI code attribution and provenance across Git commit history."""

    name = "provenance-ai"

    AI_KEYWORDS: ClassVar[set[str]] = {
        "claude",
        "copilot",
        "cursor",
        "chatgpt",
        "openai",
        "anthropic",
        "gemini",
        "deepseek",
        "codex",
        "qwen",
        "rush-cli-agent",
        "bot",
        "[bot]",
        "ai-assistant",
    }

    @property
    def mcp_description(self) -> str:
        return (
            "Audit AI code attribution via Git trailers and shallow history check at <path>. "
            "Returns survival and attribution states."
        )

    def __call__(
        self,
        path: Path,
        *,
        max_commits: int = 500,
    ) -> ToolResult:
        return self.run(path, max_commits=max_commits)

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        max_commits: int = 500,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        perms = permissions or ExecutionPermissions()
        root = path.resolve() if path.is_dir() else path.parent.resolve()

        # Check if git repository
        git_check = run_subprocess(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=root
        )
        if git_check.returncode != 0 or git_check.stdout.strip() != "true":
            res = skipped_result(
                self.name,
                "git",
                f"provenance-ai: target path '{path}' is not a git repository",
                duration_ms=elapsed_ms(start),
            )
            res["metadata"] = {
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="provenance-ai",
                )
            }
            return res

        # Check for shallow repository
        is_shallow = False
        if (root / ".git" / "shallow").exists():
            is_shallow = True
        else:
            shallow_cmd = run_subprocess(
                ["git", "rev-parse", "--is-shallow-repository"], cwd=root
            )
            if shallow_cmd.returncode == 0 and shallow_cmd.stdout.strip() == "true":
                is_shallow = True

        # Extract git commit log with format
        log_res = run_subprocess(
            [
                "git",
                "log",
                f"-n{max_commits}",
                "--format=%H%x00%an%x00%ae%x00%at%x00%B%x01",
            ],
            cwd=root,
        )

        findings: list[Finding] = []
        if is_shallow:
            findings.append(
                Finding(
                    path=".",
                    line=1,
                    column=1,
                    rule="shallow-history",
                    rule_id="WARN_SHALLOW_HISTORY",
                    severity="warn",
                    message="Repository is a shallow clone; historical commit provenance is truncated.",
                    fingerprint="git:shallow_clone",
                )
            )

        if log_res.returncode != 0 or not log_res.stdout.strip():
            # Empty repo or no commits
            status = "warn" if is_shallow else "ok"
            return ToolResult(
                tool=self.name,
                engine="git-trailer-parser",
                engine_version="1.0.0",
                status=status,
                duration_ms=elapsed_ms(start),
                summary="provenance-ai: no commit history found to audit",
                findings=findings,
                raw={
                    "commits_audited": 0,
                    "ai_generated_count": 0,
                    "ai_assisted_count": 0,
                    "human_count": 0,
                    "shallow_history": is_shallow,
                },
                metadata={
                    "survival_states": {
                        "30d": "unknown",
                        "60d": "unknown",
                        "90d": "unknown",
                        "reason": "Deterministic baseline: line lifecycle causal analysis deferred",
                    },
                    "defect_correlation": {
                        "state": "unknown",
                        "reason": "Causal bug attribution across AI vs human commits deferred",
                    },
                    "execution": build_execution_metadata(
                        mode="executed",
                        requested=perms,
                        granted=perms,
                        producer="provenance-ai",
                    ),
                },
            )

        raw_records = log_res.stdout.split("\x01")
        now_ts = int(time.time())

        ai_generated_count = 0
        ai_assisted_count = 0
        human_count = 0
        c_30d = 0
        c_60d = 0
        c_90d = 0

        for rec in raw_records:
            parts = rec.strip().split("\x00")
            if len(parts) < 5:
                continue
            commit_hash, author_name, author_email, ts_str, body = (
                parts[0],
                parts[1],
                parts[2],
                parts[3],
                parts[4],
            )

            try:
                commit_ts = int(ts_str)
                age_days = (now_ts - commit_ts) / 86400.0
                if age_days >= 30:
                    c_30d += 1
                if age_days >= 60:
                    c_60d += 1
                if age_days >= 90:
                    c_90d += 1
            except ValueError:
                pass

            # Inspect trailers and author
            generated_by_match = re.search(r"Generated-by:\s*(.+)", body, re.IGNORECASE)
            co_authored_match = re.search(
                r"Co-authored-by:\s*(.+)", body, re.IGNORECASE
            )
            agent_match = re.search(r"Agent:\s*(.+)", body, re.IGNORECASE)
            model_match = re.search(r"Model:\s*(.+)", body, re.IGNORECASE)
            ai_assisted_match = re.search(r"AI-Assisted:\s*(.+)", body, re.IGNORECASE)

            is_ai_gen = False
            is_ai_assist = False
            trailer_detail = ""

            if generated_by_match:
                is_ai_gen = True
                trailer_detail = f"Generated-by: {generated_by_match.group(1).strip()}"
            elif agent_match:
                is_ai_gen = True
                trailer_detail = f"Agent: {agent_match.group(1).strip()}"
            elif co_authored_match:
                co_val = co_authored_match.group(1).strip().lower()
                if any(kw in co_val for kw in self.AI_KEYWORDS):
                    is_ai_assist = True
                    trailer_detail = (
                        f"Co-authored-by: {co_authored_match.group(1).strip()}"
                    )
            elif model_match or ai_assisted_match:
                is_ai_assist = True
                model_str = (
                    model_match.group(1).strip() if model_match else "AI-Assisted"
                )
                trailer_detail = f"Model: {model_str}"
            else:
                author_lower = (author_name + " " + author_email).lower()
                if any(kw in author_lower for kw in self.AI_KEYWORDS):
                    is_ai_gen = True
                    trailer_detail = f"Author: {author_name} <{author_email}>"

            if is_ai_gen:
                ai_generated_count += 1
                findings.append(
                    Finding(
                        path=".",
                        line=1,
                        column=1,
                        rule="ai-attribution",
                        rule_id="INFO_AI_GENERATED",
                        severity="info",
                        message=f"Commit {commit_hash[:8]} generated by AI: {trailer_detail}",
                        provenance=trailer_detail,
                        fingerprint=f"git:{commit_hash}:ai_gen",
                    )
                )
            elif is_ai_assist:
                ai_assisted_count += 1
                findings.append(
                    Finding(
                        path=".",
                        line=1,
                        column=1,
                        rule="ai-attribution",
                        rule_id="INFO_AI_ASSISTED",
                        severity="info",
                        message=f"Commit {commit_hash[:8]} assisted by AI: {trailer_detail}",
                        provenance=trailer_detail,
                        fingerprint=f"git:{commit_hash}:ai_assist",
                    )
                )
            else:
                human_count += 1

        total_audited = ai_generated_count + ai_assisted_count + human_count
        status = "warn" if is_shallow else "ok"
        summary = (
            f"provenance-ai: audited {total_audited} commits "
            f"({ai_generated_count} AI-generated, {ai_assisted_count} AI-assisted, {human_count} human). "
            f"Shallow history: {is_shallow}. Survival states: 30d/60d/90d=unknown."
        )

        return ToolResult(
            tool=self.name,
            engine="git-trailer-parser",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            raw={
                "commits_audited": total_audited,
                "ai_generated_count": ai_generated_count,
                "ai_assisted_count": ai_assisted_count,
                "human_count": human_count,
                "shallow_history": is_shallow,
                "commits_older_than_30d": c_30d,
                "commits_older_than_60d": c_60d,
                "commits_older_than_90d": c_90d,
            },
            metadata={
                "survival_states": {
                    "30d": "unknown",
                    "60d": "unknown",
                    "90d": "unknown",
                    "reason": "Deterministic baseline: line lifecycle causal analysis deferred",
                },
                "defect_correlation": {
                    "state": "unknown",
                    "reason": "Causal bug attribution across AI vs human commits deferred",
                },
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="provenance-ai",
                ),
            },
        )
