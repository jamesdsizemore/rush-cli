import json
import shutil
from pathlib import Path
from typing import Protocol

from ..tools.base import Finding
from ..tools.common import run_subprocess


class GraftContextProvider(Protocol):
    def available(self, project_root: Path) -> bool: ...
    def context_for(self, path: Path) -> list[Finding]: ...


class LocalGraftContext:
    """Invokes local Graft CLI to extract dependency and architectural graph context."""

    def available(self, project_root: Path) -> bool:
        return (
            shutil.which("graft") is not None
            and (
                (project_root / ".hermes/graft").exists()
                or (project_root / ".graft").exists()
            )
        )

    def context_for(self, path: Path) -> list[Finding]:
        project_root = path if path.is_dir() else path.parent
        if not self.available(project_root):
            return []

        target_name = path.name

        try:
            proc = run_subprocess(
                ["graft", "ask", f"callers of {target_name}"],
                cwd=project_root,
                timeout=10.0,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                stdout_clean = proc.stdout.strip()
                if "(empty)" in stdout_clean or "no matching symbols" in stdout_clean:
                    return []
                lines = [l.strip() for l in stdout_clean.splitlines() if l.strip()]
                summary = " | ".join(lines[:3])
                finding: Finding = {
                    "path": str(path),
                    "line": 1,
                    "column": 1,
                    "rule": "graft-context",
                    "severity": "info",
                    "message": f"Graft call graph context: {summary}",
                }
                return [finding]
        except Exception:
            pass
        return []


