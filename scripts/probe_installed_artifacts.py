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
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
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
    mcp_initialized: bool = False


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


class UnsupportedPlatformError(ValueError):
    """Raised when no release asset is defined for a given OS/architecture pair."""


_ARCH_ALIASES = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "amd64": "x86_64",
    "x86_64": "x86_64",
}

# Canonical release asset name for each supported (OS, architecture) pair (Phase 65: P65-01).
# Mirrors the build matrix in .github/workflows/release.yml and the URLs referenced by
# packaging/homebrew/rush.rb, packaging/scoop/rush.json and packaging/winget/rush.yaml.
PLATFORM_ASSET_MATRIX: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "rush-darwin-arm64.tar.gz",
    ("darwin", "x86_64"): "rush-darwin-x86_64.tar.gz",
    ("linux", "x86_64"): "rush-linux-x86_64.tar.gz",
    ("linux", "arm64"): "rush-linux-arm64.tar.gz",
    ("windows", "x86_64"): "rush-windows-x86_64.zip",
    ("windows", "arm64"): "rush-windows-arm64.zip",
}


def select_platform_asset(system: str, machine: str) -> str:
    """Return the exact release asset filename for an OS name and CPU architecture.

    ``system`` accepts ``platform.system()`` values (Darwin/Linux/Windows, case-insensitive).
    ``machine`` accepts ``platform.machine()`` values (arm64/aarch64/x86_64/AMD64, case-insensitive).
    Raises ``UnsupportedPlatformError`` for any pair outside the six-member release matrix.
    """
    normalized_machine = _ARCH_ALIASES.get(
        machine.strip().lower(), machine.strip().lower()
    )
    key = (system.strip().lower(), normalized_machine)
    try:
        return PLATFORM_ASSET_MATRIX[key]
    except KeyError:
        raise UnsupportedPlatformError(
            f"No release asset defined for system={system!r} machine={machine!r}"
        ) from None


def compute_sha256(path: Path) -> str:
    """Return the hex sha256 digest of a file's exact bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256sums(archive_paths: list[Path], dest: Path) -> Path:
    """Write a SHA256SUMS manifest computed from each archive's exact bytes."""
    lines = [
        f"{compute_sha256(p)}  {p.name}"
        for p in sorted(archive_paths, key=lambda p: p.name)
    ]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def verify_archive_checksum(archive_path: Path, checksums_path: Path) -> bool:
    """Verify archive_path's exact sha256 bytes match its recorded SHA256SUMS entry.

    Returns False (never raises) when the archive is missing, the checksum manifest is
    missing, the archive has no entry in it, or the recorded digest does not match.
    """
    if not archive_path.is_file() or not checksums_path.is_file():
        return False
    expected = None
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, name = parts
        if name.lstrip("*") == archive_path.name:
            expected = digest
            break
    if expected is None:
        return False
    return compute_sha256(archive_path) == expected


def build_release_archive(
    binary_path: Path, dest_dir: Path, asset_name: str, version: str
) -> Path:
    """Package a self-contained binary plus a VERSION file into the named release archive."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = dest_dir / f".stage-{asset_name}"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)
    try:
        binary_name = "rush.exe" if asset_name.endswith(".zip") else "rush"
        staged_binary = stage_dir / binary_name
        shutil.copy2(binary_path, staged_binary)
        staged_binary.chmod(staged_binary.stat().st_mode | 0o111)
        (stage_dir / "VERSION").write_text(version + "\n", encoding="utf-8")

        archive_path = dest_dir / asset_name
        if asset_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in sorted(stage_dir.iterdir()):
                    zf.write(item, item.name)
        else:
            with tarfile.open(archive_path, "w:gz") as tf:
                for item in sorted(stage_dir.iterdir()):
                    tf.add(item, arcname=item.name)
        return archive_path
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def probe_native_artifact(
    archive_path: Path, checkout_root: Path, work_dir: Path
) -> ArtifactProbeResult:
    """Extract a release archive and probe its self-contained binary from a clean directory.

    PATH is reduced to bare OS directories only (no python/uv/checkout entries) to prove the
    binary needs neither a source checkout nor an installed Python interpreter. Also performs
    a real MCP stdio ``initialize`` handshake against the extracted binary.
    """
    if not archive_path.is_file():
        return ArtifactProbeResult(
            artifact_type="native",
            artifact_path=str(archive_path),
            status="failed",
            origin_verified=False,
            import_clean=False,
            stdout="",
            stderr=f"Archive not found: {archive_path}",
            mcp_initialized=False,
        )

    extract_dir = work_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_dir)
        binary_name = "rush.exe"
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(extract_dir, filter="data")
        binary_name = "rush"

    binary_path = (extract_dir / binary_name).resolve()
    external_cwd = work_dir / "cwd_native"
    external_cwd.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        bare_path = "C:\\Windows\\System32"
        env = {"PATH": bare_path, "USERPROFILE": str(work_dir)}
    else:
        bare_path = "/usr/bin:/bin"
        env = {"PATH": bare_path, "HOME": str(work_dir)}

    version_probe = subprocess.run(
        [str(binary_path), "--version"],
        cwd=external_cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    origin_verified = verify_package_origin(binary_path, checkout_root)

    mcp_initialized = False
    mcp_error = ""
    mcp_stderr = ""
    stdout_line = ""
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            [str(binary_path), "mcp", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=external_cwd,
            env=env,
            text=True,
        )
        request = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "probe", "version": "0.0.1"},
                    },
                }
            )
            + "\n"
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(request)
        proc.stdin.flush()
        stdout_line = proc.stdout.readline()
        response = json.loads(stdout_line) if stdout_line else {}
        mcp_initialized = response.get("id") == 1 and "serverInfo" in response.get(
            "result", {}
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        mcp_error = str(exc)
    finally:
        # Use communicate() (not wait()) so the MCP subprocess's own stderr is
        # actually captured instead of silently discarded -- terminate() first
        # so the process exits and communicate() can't block waiting for EOF.
        if proc is not None:
            proc.terminate()
            try:
                _, mcp_stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    _, mcp_stderr = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    mcp_stderr = ""

    if not mcp_initialized and not mcp_error:
        mcp_error = f"MCP handshake did not initialize: stdout_line={stdout_line!r}"
    if mcp_stderr.strip():
        stderr_suffix = f"mcp subprocess stderr={mcp_stderr.strip()!r}"
        mcp_error = f"{mcp_error} | {stderr_suffix}" if mcp_error else stderr_suffix

    status = (
        "passed"
        if (version_probe.returncode == 0 and origin_verified and mcp_initialized)
        else "failed"
    )

    if status == "failed":
        failure_reasons = []
        if version_probe.returncode != 0:
            failure_reasons.append("version_probe failed")
        if not origin_verified:
            failure_reasons.append("origin not verified")
        if not mcp_initialized:
            failure_reasons.append("mcp not initialized")
        detail = version_probe.stderr.strip() or mcp_error
        combined_stderr = "; ".join(failure_reasons)
        if detail:
            combined_stderr = f"{combined_stderr}: {detail}"
    else:
        combined_stderr = version_probe.stderr or mcp_error

    return ArtifactProbeResult(
        artifact_type="native",
        artifact_path=str(archive_path),
        status=status,
        origin_verified=origin_verified,
        import_clean=version_probe.returncode == 0,
        stdout=version_probe.stdout,
        stderr=combined_stderr,
        mcp_initialized=mcp_initialized,
    )


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

    uv_bin = shutil.which("uv")

    # 1. Create fresh virtual environment using uv or python -m venv
    try:
        if uv_bin:
            subprocess.run(
                [uv_bin, "venv", str(venv_dir), "--python", sys.executable],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
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

    # 2. Install the artifact using uv pip or pip in the fresh venv
    try:
        if uv_bin:
            subprocess.run(
                [
                    uv_bin,
                    "pip",
                    "install",
                    "--python",
                    str(venv_python),
                    str(artifact_path.resolve()),
                ],
                cwd=external_cwd,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        else:
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
    # Scoped to the sdist naming convention (rush_cli-*) so it never collides with the
    # native release archives (rush-{platform}-{arch}.tar.gz) that also live in dist/.
    sdists = sorted(
        dist_dir.glob("rush_cli-*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    try:
        native_asset_name: str | None = select_platform_asset(
            platform.system(), platform.machine()
        )
    except UnsupportedPlatformError:
        native_asset_name = None
    native_path = dist_dir / native_asset_name if native_asset_name else None
    native_present = native_path is not None and native_path.is_file()

    if not wheels and not sdists and not native_present:
        print(
            f"No .whl, sdist, or native release archive found in '{dist_dir}'. "
            "Build artifacts first.",
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

        if native_present:
            assert native_path is not None
            print(f"[probe:native] Testing {native_path.name}...")
            res = probe_native_artifact(native_path, checkout_root, work_dir)
            results.append(res)
            print(
                f"[probe:native] Status: {res.status} (origin_verified={res.origin_verified}, mcp_initialized={res.mcp_initialized})"
            )

    if args.json:
        out_data = [
            {
                "artifact_type": r.artifact_type,
                "artifact_path": r.artifact_path,
                "status": r.status,
                "origin_verified": r.origin_verified,
                "import_clean": r.import_clean,
                "mcp_initialized": r.mcp_initialized,
                "stderr": r.stderr,
            }
            for r in results
        ]
        print(json.dumps(out_data, indent=2))

    all_passed = all(r.status == "passed" for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
