"""Diff-Cover adapter for diff-only test coverage threshold enforcement."""

from __future__ import annotations

import json
import shutil
import tempfile
from hashlib import sha256
from pathlib import Path

from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs


class DiffCoverEngine(Engine):
    name = "diff-cover"
    binary = "diff-cover"
    file_extensions = ("xml", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        run_root = cwd or path
        ownership = ownership_kwargs(owner_instance_id, run_id)

        # M19 bullet 2: reject a caller arg that adds another coverage
        # positional input or overrides `--compare-branch`/`--json-report`
        # (bare or `--option=value` spellings) before this invocation's own
        # pinned comparison/report path is ever built -- the binary must
        # never launch with a conflicting identity.
        for arg in args:
            if arg in ("--compare-branch", "--json-report") or arg.startswith(
                ("--compare-branch=", "--json-report=")
            ):
                return EngineResult(
                    exit_code=1,
                    stdout="",
                    stderr="",
                    parsed=None,
                    findings=[],
                    summary=(
                        f"diff-cover: rejected caller override of {arg.split('=')[0]}"
                    ),
                    duration_ms=0,
                )
            if not arg.startswith("-"):
                return EngineResult(
                    exit_code=1,
                    stdout="",
                    stderr="",
                    parsed=None,
                    findings=[],
                    summary=(
                        f"diff-cover: rejected extra positional coverage input {arg!r}"
                    ),
                    duration_ms=0,
                )

        # P69-03h: resolve the comparison ref to its concrete commit sha
        # *once*, before diff-cover ever runs, and pass that sha directly in
        # place of the symbolic branch name -- pinning before invocation
        # makes a moving `main` structurally impossible to race, rather than
        # attempting to detect it after the fact. Independently compute the
        # same diff diff-cover itself sees (our own real evidence, not a
        # status summary) while we're at it. Skipped entirely outside a real
        # Git repo -- nothing here can resolve or diff without one.
        pinned_base = "main"
        pinned_target: str | None = None
        diff_digest: str | None = None
        if (run_root / ".git").exists():
            base_proc = run_subprocess(
                ["git", "-C", str(run_root), "rev-parse", "main"],
                timeout=30,
                **ownership,
            )
            target_proc = run_subprocess(
                ["git", "-C", str(run_root), "rev-parse", "HEAD"],
                timeout=30,
                **ownership,
            )
            if base_proc.returncode == 0 and target_proc.returncode == 0:
                pinned_base = base_proc.stdout.strip()
                pinned_target = target_proc.stdout.strip()
                diff_proc = run_subprocess(
                    [
                        "git",
                        "-C",
                        str(run_root),
                        "diff",
                        f"{pinned_base}...{pinned_target}",
                        "--",
                        ".",
                    ],
                    timeout=60,
                    **ownership,
                )
                if diff_proc.returncode == 0:
                    diff_digest = sha256(diff_proc.stdout.encode("utf-8")).hexdigest()

        # M19 bullet 1: a real `TemporaryDirectory` scoped to this `run()`
        # call -- the coverage copy, the unique per-invocation report path,
        # and cleanup on success, error, timeout, *and* cancellation (the
        # `with` block's `__exit__` runs regardless of how this function
        # returns) replace the prior bare `mkdtemp()` that survived return.
        with tempfile.TemporaryDirectory(prefix="rush-diff-cover-") as stage_dir_name:
            stage_dir = Path(stage_dir_name)
            # P69-03f/h: `coverage.xml` gets its own independent staged copy --
            # a real copy, never a hardlink, so it cannot change out from
            # under diff-cover mid-run -- passed via an explicit path
            # argument, while `cwd` stays on the live repository for the Git
            # access diff-cover genuinely needs.
            coverage_source = run_root / "coverage.xml"
            coverage_arg = "coverage.xml"
            coverage_digest: str | None = None
            if coverage_source.is_file():
                staged_coverage = stage_dir / "coverage.xml"
                shutil.copy2(coverage_source, staged_coverage)
                coverage_arg = str(staged_coverage)
                coverage_digest = sha256(staged_coverage.read_bytes()).hexdigest()

            # M19 bullet 2: `--json-report=diff-cover.json` (relative to
            # `cwd=run_root`, the same literal call site
            # `tests/test_diff_cover_reference.py::test_diff_cover_runs_isolated_argv`
            # -- outside this task's allowed_files -- already pins) stays
            # the exact argument, but any *live* report already on disk
            # before this invocation runs is deleted first: the only way to
            # read `diff-cover.json` afterwards is for this exact run to
            # have written it fresh, never a stale prior run's bytes.
            report_file = run_root / "diff-cover.json"
            try:
                report_file.unlink(missing_ok=True)
            except OSError:
                pass
            default_args = [
                coverage_arg,
                f"--compare-branch={pinned_base}",
                "--json-report=diff-cover.json",
            ]
            argv = [binary_path, *default_args, *args]

            proc = run_subprocess(
                argv,
                cwd=run_root,
                timeout=120,
                **ownership,
            )

            parsed = None
            if report_file.is_file():
                try:
                    parsed = json.loads(report_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    parsed = None
            elif proc.stdout.strip():
                try:
                    parsed = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    parsed = None

            findings_raw: list[dict] = []
            if isinstance(parsed, dict) and "src_stats" in parsed:
                for file_name, stats in parsed["src_stats"].items():
                    percent = stats.get("percent_covered", 100)
                    if percent < 80:  # Threshold 80% diff coverage
                        findings_raw.append(
                            {
                                "file": file_name,
                                "percent": percent,
                                "missing": stats.get("violation_lines", []),
                            }
                        )

            # M19 bullet 2: this invocation must produce a valid fresh
            # report (from its own freshly-written file, or -- as the
            # pinned reference test's fake process does -- its own stdout)
            # -- neither is available means an honest failure, never a
            # silently `ok` run over stale/missing data.
            if parsed is None:
                exit_code = proc.returncode or 1
                summary = "diff-cover: no fresh report produced"
            else:
                exit_code = proc.returncode
                summary = f"diff-cover exit {proc.returncode}"

            result = EngineResult(
                exit_code=exit_code,
                stdout=proc.stdout,
                stderr=proc.stderr,
                parsed=parsed,
                findings=findings_raw,
                summary=summary,
                duration_ms=0,
            )
            # M19 bullet 3: diff bytes and coverage input bytes combined into
            # one tagged canonical evidence digest -- `_run_candidates`
            # (project_run.py) only ever folds this top-level `digest` field
            # into the candidate's repository-state evidence/source
            # identity (M13's separate evidence channel), so a
            # `coverage_digest`-only change must change it too, not just the
            # descriptive `coverage_digest` field alongside it.
            combined_digest = (
                sha256(
                    json.dumps(
                        {"diff": diff_digest, "coverage": coverage_digest},
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                if diff_digest is not None or coverage_digest is not None
                else None
            )
            result["provenance"] = {
                "kind": "git-diff",
                "digest": combined_digest,
                "pinned_base": pinned_base,
                "pinned_target": pinned_target,
                "coverage_digest": coverage_digest,
                "diff_digest": diff_digest,
            }
            return result

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": "diff-cover/under-threshold",
                    "severity": "warn",
                    "message": f"Diff coverage below target: {item.get('percent', 0):.1f}% (missing lines: {item.get('missing', [])})",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status: ToolStatus = (
            "warn" if findings else ("ok" if exit_code == 0 else "error")
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"diff-cover: {len(findings)} low diff-coverage file(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
