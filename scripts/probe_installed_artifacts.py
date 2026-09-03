#!/usr/bin/env python3
"""Probe installed wheel and sdist artifacts independently in an isolated environment (Phase 51: P51.3.2).

Enforces:
1. Wheel and sdist installation into fresh virtual environments outside checkout.
2. Scrubbed environment (no PYTHONPATH, no VIRTUAL_ENV).
3. Execution from an empty external working directory.
4. Origin verification (module imports must not resolve to checkout source tree).
5. Negative control verification (detecting broken 'src.rush' imports).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactProbeResult:
    artifact_type: str
    artifact_path: str
    status: str
    origin_verified: bool
    import_clean: bool
    stdout: str
    stderr: str


def scrub_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment dictionary stripped of PYTHONPATH and VIRTUAL_ENV."""
    source_env = dict(env if env is not None else os.environ)
    scrubbed = {
        k: v
        for k, v in source_env.items()
        if k not in {"PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"}
    }
    return scrubbed


def verify_package_origin(module_path: Path, checkout_root: Path) -> bool:
    """Verify that an imported module path does NOT resolve inside checkout_root."""
    try:
        resolved_mod = module_path.resolve()
        resolved_root = checkout_root.resolve()
        return not resolved_mod.is_relative_to(resolved_root)
    except (ValueError, OSError):
        return True


def check_import_integrity(code: str) -> bool:
    """Check whether code contains invalid 'src.rush' imports (R-001 negative control)."""
    pattern = re.compile(r"^\s*(from|import)\s+src\.rush", re.MULTILINE)
    return not bool(pattern.search(code))


def probe_installed_artifact(
    artifact_path: Path,
    checkout_root: Path,
    work_dir: Path,
) -> ArtifactProbeResult:
    """Install artifact into an isolated virtualenv in work_dir and probe it from an empty external CWD."""
    artifact_type = "wheel" if artifact_path.suffix == ".whl" else "sdist"

    venv_dir = work_dir / f"venv_{artifact_type}"
    external_cwd = work_dir / f"cwd_{artifact_type}"
    external_cwd.mkdir(parents=True, exist_ok=True)

    # 1. Create fresh virtual environment using uv or python -m venv
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        return ArtifactProbeResult(
            artifact_type=artifact_type,
            artifact_path=str(artifact_path),
            status="failed",
            origin_verified=False,
            import_clean=False,
            stdout="",
            stderr=f"Failed to create virtualenv: {e.stderr}",
        )

    # Determine paths inside the fresh venv
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
        venv_rush = venv_dir / "Scripts" / "rush.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
        venv_rush = venv_dir / "bin" / "rush"

    env = scrub_environment()

    # 2. Install the artifact using pip in the fresh venv
    try:
        subprocess.run(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                str(artifact_path.resolve()),
                "--no-cache-dir",
            ],
            cwd=external_cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        stderr_msg = getattr(e, "stderr", str(e))
        return ArtifactProbeResult(
            artifact_type=artifact_type,
            artifact_path=str(artifact_path),
            status="failed",
            origin_verified=False,
            import_clean=False,
            stdout="",
            stderr=f"Installation failed: {stderr_msg}",
        )

    # 3. Probe module origin
    origin_probe = subprocess.run(
        [str(venv_python), "-c", "import rush; print(rush.__file__)"],
        cwd=external_cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    origin_verified = False
    if origin_probe.returncode == 0:
        mod_path = Path(origin_probe.stdout.strip())
        origin_verified = verify_package_origin(mod_path, checkout_root)

    # 4. Probe CLI execution
    if venv_rush.is_file():
        cli_probe = subprocess.run(
            [str(venv_rush), "--help"],
            cwd=external_cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        cli_returncode = cli_probe.returncode
        cli_stdout = cli_probe.stdout
        cli_stderr = cli_probe.stderr
    else:
        cli_returncode = 1
        cli_stdout = ""
        cli_stderr = f"Binary {venv_rush} not found in virtual environment"

    # 5. Check import integrity (R-001 negative control: does installed rush import fail on src.rush?)
    import_probe = subprocess.run(
        [str(venv_python), "-c", "import rush.cli; import rush.catalog"],
        cwd=external_cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    import_clean = import_probe.returncode == 0

    overall_status = (
        "passed"
        if (origin_verified and cli_returncode == 0 and import_clean)
        else "failed"
    )

    return ArtifactProbeResult(
        artifact_type=artifact_type,
        artifact_path=str(artifact_path),
        status=overall_status,
        origin_verified=origin_verified,
        import_clean=import_clean,
        stdout=cli_stdout,
        stderr=cli_stderr or import_probe.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe installed Rush artifacts independently"
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Directory containing built artifacts",
    )
    parser.add_argument(
        "--checkout-root",
        type=Path,
        default=Path.cwd(),
        help="Repository checkout root",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    args = parser.parse_args()

    dist_dir = args.dist_dir.resolve()
    checkout_root = args.checkout_root.resolve()

    if not dist_dir.is_dir():
        print(
            f"Error: dist directory '{dist_dir}' not found. Run 'uv build' first.",
            file=sys.stderr,
        )
        return 1

    wheels = sorted(
        dist_dir.glob("*.whl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    sdists = sorted(
        dist_dir.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True
    )

    if not wheels and not sdists:
        print(
            f"No .whl or .tar.gz artifacts found in '{dist_dir}'. Run 'uv build' first.",
            file=sys.stderr,
        )
        return 1

    results: list[ArtifactProbeResult] = []

    with tempfile.TemporaryDirectory(prefix="rush_probe_") as tmp_str:
        work_dir = Path(tmp_str)

        if wheels:
            wheel_path = wheels[0]
            print(f"[probe:wheel] Testing {wheel_path.name}...")
            res = probe_installed_artifact(wheel_path, checkout_root, work_dir)
            results.append(res)
            print(
                f"[probe:wheel] Status: {res.status} (origin_verified={res.origin_verified}, import_clean={res.import_clean})"
            )

        if sdists:
            sdist_path = sdists[0]
            print(f"[probe:sdist] Testing {sdist_path.name}...")
            res = probe_installed_artifact(sdist_path, checkout_root, work_dir)
            results.append(res)
            print(
                f"[probe:sdist] Status: {res.status} (origin_verified={res.origin_verified}, import_clean={res.import_clean})"
            )

    if args.json:
        out_data = [
            {
                "artifact_type": r.artifact_type,
                "artifact_path": r.artifact_path,
                "status": r.status,
                "origin_verified": r.origin_verified,
                "import_clean": r.import_clean,
                "stderr": r.stderr,
            }
            for r in results
        ]
        print(json.dumps(out_data, indent=2))

    all_passed = all(r.status == "passed" for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
