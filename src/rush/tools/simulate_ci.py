"""Zero-cloud GitHub Actions workflow emulator."""

import os
import shlex
import tempfile
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from .common import run_subprocess

_IS_WINDOWS = os.name == "nt"
_SHELLS: dict[str, list[str]] = {
    "bash": ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"],
    "sh": ["sh", "-e", "-c"],
    "pwsh": ["pwsh", "-Command"],
    "powershell": ["powershell", "-Command"],
    "cmd": ["cmd", "/D", "/E:ON", "/V:OFF", "/S", "/C"],
    "python": ["python", "-c"],
}


class SimulateCi:
    """Emulates local execution of GitHub Actions .github/workflows/*.yml steps."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def run_workflow(self, workflow_name: str = "ci.yml") -> dict[str, Any]:
        wf_path = self.project_root / ".github" / "workflows" / workflow_name
        if not wf_path.exists():
            # T27: a missing workflow never passes by default.
            return {
                "passed": False,
                "not_found": True,
                "steps_executed": 0,
                "failed_step": None,
                "error": f"workflow {workflow_name!r} not found at {wf_path}",
            }

        doc = YAML(typ="safe").load(wf_path.read_text(encoding="utf-8")) or {}
        workflow_shell = ((doc.get("defaults") or {}).get("run") or {}).get("shell")

        results = []
        for job in (doc.get("jobs") or {}).values():
            job_shell = ((job.get("defaults") or {}).get("run") or {}).get("shell")
            for step in job.get("steps") or []:
                cmd_clean = str(step.get("run") or "").strip()
                if not cmd_clean or cmd_clean.startswith("echo"):
                    continue
                shell = (
                    step.get("shell")
                    or job_shell
                    or workflow_shell
                    or ("pwsh" if _IS_WINDOWS else None)
                )
                if shell is None:
                    argv = ["bash", "-e", "-c", cmd_clean]
                elif shell in _SHELLS:
                    argv = [*_SHELLS[shell], cmd_clean]
                elif "{0}" in shell:
                    with tempfile.TemporaryDirectory() as tmp:
                        script = Path(tmp) / "step"
                        script.write_text(cmd_clean)
                        argv = [
                            part.replace("{0}", str(script))
                            for part in shlex.split(shell)
                        ]
                        res = run_subprocess(argv, cwd=self.project_root)
                    results.append({"command": cmd_clean, "returncode": res.returncode})
                    if res.returncode != 0:
                        return {
                            "passed": False,
                            "failed_step": cmd_clean,
                            "error": res.stderr,
                            "steps": results,
                        }
                    continue
                else:
                    return {
                        "passed": False,
                        "failed_step": cmd_clean,
                        "error": f"shell {shell!r} has no {{0}} placeholder",
                        "steps": results,
                    }

                res = run_subprocess(argv, cwd=self.project_root)
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


SimulateCiTool = SimulateCi
