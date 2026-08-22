"""Zero-cloud GitHub Actions workflow emulator."""

import re
from pathlib import Path
from typing import Any

from src.rush.tools.common import run_subprocess


class SimulateCi:
    """Emulates local execution of GitHub Actions .github/workflows/*.yml steps."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def run_workflow(self, workflow_name: str = "ci.yml") -> dict[str, Any]:
        wf_path = self.project_root / ".github" / "workflows" / workflow_name
        if not wf_path.exists():
            return {
                "passed": True,
                "steps_executed": 0,
                "message": f"Workflow {workflow_name} not found, passing by default.",
            }

        text = wf_path.read_text(encoding="utf-8", errors="ignore")
        runs = re.findall(r"run:\s*(.+)", text)

        results = []
        for cmd in runs:
            cmd_clean = cmd.strip().strip("|").strip()
            if cmd_clean and not cmd_clean.startswith("echo"):
                res = run_subprocess(
                    ["powershell", "-Command", cmd_clean], cwd=self.project_root
                )
                results.append(
                    {
                        "command": cmd_clean,
                        "returncode": res.returncode,
                    }
                )
                if res.returncode != 0:
                    return {
                        "passed": False,
                        "failed_step": cmd_clean,
                        "error": res.stderr,
                        "steps": results,
                    }

        return {
            "passed": True,
            "steps_executed": len(results),
            "steps": results,
        }
