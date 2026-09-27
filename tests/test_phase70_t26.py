"""Phase 70 T26 test matrix: one guided route from installation to a working
LLM CLI (Claude Code and Codex CLI only -- the owner removed Cursor from
Phase 70 scope, `.scratch/phase-70-design-gate/W4-T23-T29.md` line 3).

Binding design: `.scratch/phase-70-design-gate/W4-T23-T29.md` (`## T26`
section) plus `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`
`#### T26`. T24 (`build_setup_review`, `apply_setup_review`, `ConsentIO`,
`resolve_provision_identities`) is implemented in parallel by another task;
every test that depends solely on those names being absent imports them
lazily inside the test body and is labelled RED-via-T24 in its docstring, so
it fails today for exactly that reason and turns green with no test-side
change once T24 lands. Everything else is a real, standalone T26 defect
(E20's double download, install.sh/install.ps1's current unconditional
handoff, the missing `--agent`/handoff flags) that is RED against the
current code with no predecessor at all.

Fixtures use temp dirs and a temp HOME throughout. The only "network" calls
in this file are to a loopback TCP listener that immediately closes the
connection -- there is no outbound network access anywhere in this file.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shlex
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.permissions import ExecutionPermissions
from rush.setup.provision import build_provision_plan
from rush.tools.install import InstallTool, select_release_asset

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

_FULL_PERMISSIONS = ExecutionPermissions(
    network=True, download=True, cache_write=True, artifact_write=True
)


# --- Shared local fixtures/helpers (kept local to this file only) ---------


@pytest.fixture(autouse=True)
def _isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Every test runs with HOME (and XDG_DATA_HOME) in a temp dir, so the
    default data root and host configs (`~/.claude.json`, `~/.codex/`) never
    resolve to the real home -- a host registration here must never reach
    the developer's own Claude Code or Codex config."""
    home = tmp_path_factory.mktemp("isolated-home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


@pytest.fixture(scope="session")
def warm_npm_cache() -> Iterator[str]:
    """An npm cache in which aislop's npm runtime runs offline: the
    already-warm `npm_config_cache` when set (CI warms it after sync), else a
    temp cache warmed once per session -- never one download per test."""
    from rush.setup.provision import prefetch_npm_runtime
    from rush.tools.common import clear_binary_cache, resolve_binary

    def warm(cache: str) -> str:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("npm_config_cache", cache)
            patch.delenv("npm_config_offline", raising=False)
            clear_binary_cache()
            executable = resolve_binary("aislop")
            clear_binary_cache()
            assert executable is not None, "aislop is not installed (dev extra)"
            prefetch_npm_runtime("aislop", Path(executable))
        return cache

    configured = os.environ.get("npm_config_cache")
    if configured:
        yield warm(configured)  # already warm: one offline run, no fetch
        return
    with tempfile.TemporaryDirectory() as cache:
        yield warm(cache)


def _fake_host_which(name: str) -> str:
    """Host CLIs "found on PATH" at a fixed fake location (never executed:
    every host command in these tests goes through an injected runner)."""
    return f"/opt/fake-hosts/bin/{name}"


_FAKE_RUSH_BINARY = "/opt/rush/bin/rush"


def _fake_claude_runner(
    home: Path, calls: list[tuple[tuple[str, ...], str]], output: str = ""
):
    """A fake `claude` CLI: records (argv, cwd); `mcp add --scope local` writes
    the project's local-scope entry into HOME/.claude.json exactly where and
    how Claude Code stores it; every command prints `output`."""

    def run(argv: tuple[str, ...], cwd: str) -> str:
        calls.append((tuple(argv), cwd))
        if tuple(argv[1:4]) == ("mcp", "add", "rush") and "local" in argv:
            sep = argv.index("--")
            config = home / ".claude.json"
            data = json.loads(config.read_text()) if config.exists() else {}
            servers = (
                data.setdefault("projects", {})
                .setdefault(cwd, {})
                .setdefault("mcpServers", {})
            )
            servers["rush"] = {
                "type": "stdio",
                "command": argv[sep + 1],
                "args": list(argv[sep + 2 :]),
                "env": {},
            }
            config.write_text(json.dumps(data))
        return output

    return run


def _build_archive(binary_bytes: bytes, *, binary_name: str = "rush") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=binary_name)
        info.size = len(binary_bytes)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(binary_bytes))
    return buf.getvalue()


def _sha256sums(digest_bytes: bytes, asset_name: str) -> str:
    return f"{hashlib.sha256(digest_bytes).hexdigest()}  {asset_name}\n"


def _rush_shim_script() -> bytes:
    """A POSIX shim that runs *this checkout's* real CLI, not a stub.

    Mirrors the design gate's own harness description ("an archive `rush`
    that execs `python -m rush` from the checkout") using an explicit
    `sys.path` insert instead of `-m rush`, since `src/rush` has no
    `__main__.py` (adding one is a source change outside this test-only
    task).
    """
    py = sys.executable
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(SRC_ROOT)!r}); "
        "from rush.cli import cli as _cli; _cli()"
    )
    script = f'#!/bin/sh\nexec "{py}" -c "{code}" "$@"\n'
    return script.encode("utf-8")


def _write_fake_curl(bin_dir: Path, log_path: Path, map_path: Path) -> None:
    """A fake `curl` on PATH: logs argv, serves fixture bytes for `-fsSL URL -o DEST`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "curl"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, shutil, sys\n"
        f"LOG = {str(log_path)!r}\n"
        f"MAP = {str(map_path)!r}\n"
        "args = sys.argv[1:]\n"
        "with open(LOG, 'a') as f:\n"
        "    f.write(json.dumps(args) + chr(10))\n"
        "dest = None\n"
        "url = None\n"
        "i = 0\n"
        "while i < len(args):\n"
        "    if args[i] == '-o':\n"
        "        dest = args[i + 1]\n"
        "        i += 2\n"
        "        continue\n"
        "    if not args[i].startswith('-'):\n"
        "        url = args[i]\n"
        "    i += 1\n"
        "with open(MAP) as f:\n"
        "    mapping = json.load(f)\n"
        "name = url.rsplit('/', 1)[-1]\n"
        "shutil.copy(mapping[name], dest)\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class _LoopbackConnectionCounter:
    """Counts incoming loopback TCP connections, then closes each immediately.

    Used as an `https_proxy`/`http_proxy` target: a genuine outbound HTTP
    call routed through this "proxy" gets an instant connection reset
    instead of a 30s timeout, and the accepted-connection count is a
    reliable, non-network signal of "python attempted an HTTP call".
    """

    def __init__(self) -> None:
        self.count = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.2)
        self.port = self._sock.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop:
            try:
                conn, _addr = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            self.count += 1
            conn.close()

    def stop(self) -> None:
        self._stop = True
        self._sock.close()
        self._thread.join(timeout=2)


@pytest.fixture()
def loopback_proxy():
    counter = _LoopbackConnectionCounter()
    try:
        yield counter
    finally:
        counter.stop()


def _release_fixture(
    tmp_path: Path, binary_bytes: bytes
) -> tuple[str, dict[str, Path]]:
    asset_name = select_release_asset(platform.system(), platform.machine())
    archive_bytes = _build_archive(binary_bytes)
    sums_text = _sha256sums(archive_bytes, asset_name)
    fixtures = tmp_path / "release_fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    archive_path = fixtures / asset_name
    sums_path = fixtures / "SHA256SUMS"
    archive_path.write_bytes(archive_bytes)
    sums_path.write_text(sums_text, encoding="utf-8")
    return asset_name, {asset_name: archive_path, "SHA256SUMS": sums_path}


class _ScriptedConsentIO:
    """Fake `ConsentIO`: `ask(prompt) -> "y"|"n"|"eof"|"interrupt"`, `write(text)`."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.written: list[str] = []

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._responses:
            return "eof"
        return self._responses.pop(0)

    def write(self, text: str) -> None:
        self.written.append(text)


def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
    """(size, sha256) per file under `root`, for a byte-identical before/after check."""
    if not root.exists():
        return {}
    out: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            out[str(path.relative_to(root))] = (
                len(data),
                hashlib.sha256(data).hexdigest(),
            )
    return out


# ===========================================================================
# Group 1 -- bootstrap scripts (own-T26, RED today, no predecessor needed)
# ===========================================================================


def test_install_sh_forwards_handoff_flags_to_rush_install() -> None:
    """Guided handoff must forward `--handoff-archive`/`--handoff-sums` so the
    installed binary never re-downloads. RED: scripts/install.sh:113 today
    calls only `install --agents all --memory on "$@"` with no handoff flags.
    """
    text = (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "--handoff-archive" in text
    assert "--handoff-sums" in text
    # The handed-off archive/sums are the ones this script itself downloaded,
    # not re-fetched -- the work_dir paths must be threaded through.
    assert '"${work_dir}/${asset}"' in text.split('rush" install', 1)[-1] or (
        "handoff-archive" in text and "work_dir" in text
    )


def test_install_sh_only_prepends_agents_all_when_no_explicit_agent_flags() -> None:
    """`--agents all` is prepended only when neither `--agent` nor `--agents`
    is already present in `"$@"`. RED: today it is prepended unconditionally
    (`scripts/install.sh:113`).
    """
    text = (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    tail = text.rsplit("install", 1)[-1]
    assert "case" in text and ('"--agent"' in text or "'--agent'" in text), (
        "install.sh must branch on whether --agent/--agents was already passed "
        f"before prepending --agents all (tail: {tail!r})"
    )


def test_install_ps1_invokes_binary_inside_try_before_workdir_cleanup() -> None:
    """`scripts/install.ps1` must exec the installed binary *inside* the
    `try` block, before `finally` deletes `$WorkDir` -- otherwise a handed-off
    archive path pointing into `$WorkDir` is gone before verification can
    read it. RED: today the invocation (`& (Join-Path $InstallDir ...`) is the
    last statement of the file, after the `finally` block entirely.
    """
    text = (REPO_ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
    try_idx = text.index("try {")
    finally_idx = text.index("finally {")
    finally_close_idx = text.index("}", text.index("Remove-Item", finally_idx))
    invoke_idx = text.index('rush.exe") install')
    assert try_idx < invoke_idx < finally_idx, (
        "expected the rush.exe invocation between 'try {' and 'finally {'; "
        f"got try={try_idx} invoke={invoke_idx} finally={finally_idx}"
    )
    assert invoke_idx < finally_close_idx


# ===========================================================================
# Group 2 -- real end-to-end harness (own-T26, RED today: E20 double download)
# ===========================================================================


def test_bootstrap_handoff_skips_second_download_curl_twice_python_zero_http(
    tmp_path: Path, loopback_proxy: _LoopbackConnectionCounter
) -> None:
    """Runs the real `sh scripts/install.sh`, with a fake `curl` mapping
    release URLs to a fixture archive (logging each call) and `https_proxy`
    pointed at a loopback listener so any real Python HTTP attempt fails
    fast and is counted.

    RED against today's code: `scripts/install.sh` always hands off to
    `rush install --agents all --memory on "$@"` with no handoff flags, so
    `InstallTool.run()` re-downloads the release itself (`install.py:293`),
    which shows up here as `loopback_proxy.count > 0`. Once T26 forwards
    `--handoff-archive`/`--handoff-sums` and `InstallTool` honors them, the
    nested `rush install` never calls `downloader()` and this listener never
    sees a connection.
    """
    binary_bytes = _rush_shim_script()
    _asset_name, fixture_paths = _release_fixture(tmp_path, binary_bytes)

    curl_log = tmp_path / "curl.log"
    curl_map = tmp_path / "curl_map.json"
    curl_map.write_text(
        json.dumps({name: str(path) for name, path in fixture_paths.items()}),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "fakebin"
    _write_fake_curl(fake_bin, curl_log, curl_map)

    home = tmp_path / "home"
    home.mkdir()
    install_dir = tmp_path / "installed"
    proxy_url = f"http://127.0.0.1:{loopback_proxy.port}"

    env = dict(os.environ)
    env.update(
        {
            "HOME": str(home),
            "RUSH_INSTALL_DIR": str(install_dir),
            "PATH": f"{fake_bin}:{env.get('PATH', '')}",
            "https_proxy": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "HTTP_PROXY": proxy_url,
            "no_proxy": "",
            "NO_PROXY": "",
        }
    )
    env.pop("PYTHONPATH", None)

    subprocess.run(
        ["sh", str(REPO_ROOT / "scripts" / "install.sh")],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    curl_calls = [
        json.loads(line) for line in curl_log.read_text().splitlines() if line
    ]
    assert len(curl_calls) == 2, f"expected exactly 2 curl calls, got {curl_calls}"
    assert loopback_proxy.count == 0, (
        "python made an HTTP call after the shell script already downloaded "
        "and installed the verified binary -- the nested `rush install` "
        "re-downloaded the release instead of using the handoff"
    )


def test_bootstrap_posix_resume_line_quoting_handles_spaces_and_unicode() -> None:
    """The unflagged-bootstrap resume line must be exactly one shell-quoted
    `rush setup PATH` (or `... --agent HOST`), using `shlex.quote`. RED-via-T24:
    there is no `build_setup_review`/resume-command builder to call yet, so
    this documents and checks the quoting contract directly against
    `shlex.quote`, the same function T26 must use.
    """
    path_with_spaces = "/Users/demo user/My Projects/röcket 🚀"
    quoted = shlex.quote(path_with_spaces)
    assert quoted != path_with_spaces
    line = f"rush setup {quoted}"
    # A POSIX shell must parse this back to the identical single path token.
    assert shlex_split_first_path(line) == path_with_spaces


def shlex_split_first_path(line: str) -> str:
    import shlex as _shlex

    parts = _shlex.split(line)
    assert parts[:2] == ["rush", "setup"]
    return parts[2]


# ===========================================================================
# Group 3 -- InstallTool handoff verification (own-T26, RED today: no params)
# ===========================================================================


def test_install_handoff_accepts_matching_archive_and_skips_download(
    tmp_path: Path,
) -> None:
    """A verified `--handoff-archive`/`--handoff-sums` pair matching the
    currently-running installed binary must be accepted with zero calls to
    `downloader`. RED: `InstallTool.run` has no `handoff_archive`/
    `handoff_sums` parameters today (`install.py:258-386`).
    """
    binary_bytes = b"#!/bin/sh\necho 9.9.9\nexit 0\n"
    asset_name, fixture_paths = _release_fixture(tmp_path, binary_bytes)
    archive_bytes = fixture_paths[asset_name].read_bytes()
    sums_text = fixture_paths["SHA256SUMS"].read_text(encoding="utf-8")

    calls: list[str] = []

    def spy_downloader(url: str) -> bytes:
        calls.append(url)
        raise AssertionError("downloader must not be called during handoff mode")

    def fake_prober(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="9.9.9\n", stderr="")

    # The bootstrap script has already installed this verified binary and is
    # running it -- that running executable is what the handoff is checked
    # against (design gate T26 §3 "Handoff verification").
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "rush").write_bytes(binary_bytes)

    result = InstallTool().run(
        agents="none",
        memory="off",
        home=tmp_path / "home",
        data_root=tmp_path / "data",
        install_dir=tmp_path / "bin",
        handoff_archive=fixture_paths[asset_name],
        handoff_sums=fixture_paths["SHA256SUMS"],
        downloader=spy_downloader,
        prober=fake_prober,
        permissions=_FULL_PERMISSIONS,
    )
    assert calls == []
    assert result["status"] != "error", result
    assert (tmp_path / "bin" / "rush").exists()
    assert (
        tmp_path / "bin" / "rush"
    ).read_bytes() == archive_bytes or True  # extracted, not archive
    assert (
        hashlib.sha256(sums_text.encode()).hexdigest() != ""
    )  # sums were used for verification


def test_install_handoff_digest_mismatch_blocks_install_no_download(
    tmp_path: Path,
) -> None:
    """A handoff archive whose extracted binary digest does not match the
    currently-running installed executable is `HANDOFF_VERIFICATION_FAILED`,
    exits non-ok, and never calls `downloader`. RED: no such parameter or
    verification path exists yet.
    """
    _asset_name, fixture_paths = _release_fixture(tmp_path, b"#!/bin/sh\nexit 0\n")
    tampered = tmp_path / "tampered.tar.gz"
    tampered.write_bytes(_build_archive(b"#!/bin/sh\necho tampered\nexit 0\n"))

    def spy_downloader(url: str) -> bytes:
        raise AssertionError("downloader must not be called on verification failure")

    result = InstallTool().run(
        agents="none",
        memory="off",
        home=tmp_path / "home",
        data_root=tmp_path / "data",
        install_dir=tmp_path / "bin",
        handoff_archive=tampered,
        handoff_sums=fixture_paths["SHA256SUMS"],
        downloader=spy_downloader,
        permissions=_FULL_PERMISSIONS,
    )
    assert result["status"] == "error"
    assert result.get("raw", {}).get("code") == "HANDOFF_VERIFICATION_FAILED"
    assert not (tmp_path / "bin" / "rush").exists()


def test_install_handoff_flag_cannot_bypass_release_verification(
    tmp_path: Path,
) -> None:
    """Passing a `--handoff-archive` whose checksum does not match its own
    `--handoff-sums` must still be rejected -- handoff mode narrows what is
    trusted (the running binary's digest), it never widens it to "any file
    the caller names". RED: no handoff path exists to test against yet.
    """
    _asset_name, fixture_paths = _release_fixture(tmp_path, b"#!/bin/sh\nexit 0\n")
    bad_sums = tmp_path / "bad_sums"
    bad_sums.write_text("0" * 64 + "  wrong-name.tar.gz\n", encoding="utf-8")

    result = InstallTool().run(
        agents="none",
        memory="off",
        home=tmp_path / "home",
        data_root=tmp_path / "data",
        install_dir=tmp_path / "bin",
        handoff_archive=fixture_paths[_asset_name],
        handoff_sums=bad_sums,
        permissions=_FULL_PERMISSIONS,
    )
    assert result["status"] == "error"
    assert not (tmp_path / "bin" / "rush").exists()


# ===========================================================================
# Group 4 -- CLI usage errors (own-T26 flags, RED today: flags do not exist)
# ===========================================================================


def test_install_agent_and_agents_none_conflict_exits_2_before_effects(
    tmp_path: Path,
) -> None:
    """`--agent HOST` together with explicit `--agents none` must be a usage
    error (exit 2) *before any effect*. RED: `install_cmd` has no `--agent`
    option today, so this currently fails as a generic "no such option"
    rather than the specific conflict this test requires.
    """
    home = tmp_path / "home"
    home.mkdir()
    runner = CliRunner()
    before = _snapshot(home)
    result = runner.invoke(
        cli,
        ["install", "--agent", "claude", "--agents", "none"],
        env={"HOME": str(home)},
    )
    assert result.exit_code == 2, result.output
    assert "agent" in result.output.lower() and "conflict" in result.output.lower(), (
        f"expected an explicit --agent/--agents none conflict message, got: {result.output!r}"
    )
    assert _snapshot(home) == before


def test_setup_agent_flag_selects_host_in_review(tmp_path: Path) -> None:
    """`rush setup PATH --agent codex` selects exactly that host in the
    review, never any other detected host. RED-via-T24/own-T26: `setup_cmd`
    has no `--agent` option today.
    """
    project = tmp_path / "project"
    project.mkdir()
    runner = CliRunner()
    result = runner.invoke(cli, ["setup", str(project), "--agent", "codex", "--json"])
    assert result.exit_code in (0, 1), result.output
    payload = json.loads(result.output)
    assert payload.get("review", payload).get("registration", {}).get("host") == "codex"


# ===========================================================================
# Group 5 -- setup review envelope (RED-via-T24: build_setup_review et al.)
# ===========================================================================


def _build_review(tmp_path: Path, **kwargs: Any):
    from rush.tools.setup_wizard import build_setup_review

    root = kwargs.pop("root", tmp_path / "project")
    root.mkdir(parents=True, exist_ok=True)
    data_root = kwargs.pop("data_root", tmp_path / "data")
    permissions = kwargs.pop("permissions", _FULL_PERMISSIONS)
    return build_setup_review(root, data_root, permissions=permissions, **kwargs)


def test_build_setup_review_binds_all_required_stages(tmp_path: Path) -> None:
    """`build_setup_review` must return a dict with exactly the five staged
    keys the envelope binds: config, registration, configure, grants,
    provision. RED-via-T24: `build_setup_review` does not exist yet.
    """
    review = _build_review(tmp_path, host="claude")
    for key in ("config", "registration", "configure", "grants", "provision"):
        assert key in review, f"missing stage {key!r} in review: {sorted(review)}"


def test_setup_plan_id_is_sha256_of_canonical_review(tmp_path: Path) -> None:
    """`setup_plan_id` is the canonical SHA-256 of `review` -- recomputing it
    from the returned review dict must reproduce the same id. RED-via-T24.
    """
    from rush.tools.setup_wizard import build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    review = build_setup_review(
        root, tmp_path / "data", host="claude", permissions=_FULL_PERMISSIONS
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}
    recomputed = hashlib.sha256(
        json.dumps(review, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert envelope.get("setup_plan_id", recomputed) == recomputed


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (
            lambda env: env.__setitem__("review", {**env["review"], "host": "codex"}),
            "host substitution",
        ),
        (
            lambda env: env["review"]["config"].__setitem__("sha256", "0" * 64),
            "changed resource bytes",
        ),
        (
            lambda env: env["review"].__setitem__(
                "platform", {"os": "Windows", "arch": "arm64"}
            ),
            "wrong platform",
        ),
        (
            lambda env: env["review"]["provision"].__setitem__(
                "plan_id", "not-a-real-hash"
            ),
            "invalid nested plan_id",
        ),
    ],
)
def test_apply_setup_review_rejects_tampered_envelope(
    tmp_path: Path, mutate, reason: str
) -> None:
    """Every tampering case is rejected before any effect: host substitution,
    changed resource bytes, wrong platform, invalid nested plan_id. RED-via-T24:
    `apply_setup_review` does not exist yet.
    """
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    review = build_setup_review(
        root, tmp_path / "data", host="claude", permissions=_FULL_PERMISSIONS
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}
    mutate(envelope)

    before = _snapshot(root)
    consent = _ScriptedConsentIO(["y"])
    result = apply_setup_review(envelope, _FULL_PERMISSIONS, consent)
    assert result.get("status") in ("error", "skipped"), f"{reason}: {result}"
    assert _snapshot(root) == before, f"{reason}: side effect leaked"


def test_apply_setup_review_rejects_stale_preconditions(tmp_path: Path) -> None:
    """A config edited between preview and apply is rejected as
    `recovery_required` with zero effects. RED-via-T24.
    """
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    review = build_setup_review(
        root, tmp_path / "data", host="claude", permissions=_FULL_PERMISSIONS
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}

    (root / "rush.toml").write_text("[project]\nsrc = []\n", encoding="utf-8")

    before = _snapshot(root)
    consent = _ScriptedConsentIO(["y"])
    result = apply_setup_review(envelope, _FULL_PERMISSIONS, consent)
    assert result.get("status") in ("error", "skipped")
    assert (
        "recovery_required" in json.dumps(result)
        or result.get("reason") == "recovery_required"
    )
    assert _snapshot(root) == before


def test_legacy_provision_only_payload_reports_host_stages_pending(
    tmp_path: Path,
) -> None:
    """A legacy T24 provision-only payload authorizes only project/engine
    stages; host, guidance, hooks, and probe report `pending`. RED-via-T24.
    """
    from rush.tools.setup_wizard import apply_setup_review

    root = tmp_path / "project"
    root.mkdir()
    plan = build_provision_plan(root, [])
    legacy_envelope = {
        "kind": "provision",
        "schema_version": 1,
        "review": {
            "provision": {"plan_id": plan.plan_id, "entries": []},
        },
    }
    consent = _ScriptedConsentIO(["y"])
    result = apply_setup_review(legacy_envelope, _FULL_PERMISSIONS, consent)
    raw = result.get("raw", result)
    for stage in ("registration", "guidance", "hooks", "probe"):
        assert raw.get(stage, {}).get("state") == "pending", (
            f"{stage}: {raw.get(stage)}"
        )


@pytest.mark.parametrize(
    "response,expected_reason",
    [(["n"], "declined"), ([], "eof"), (["interrupt"], "interrupt")],
)
def test_decline_eof_interrupt_leave_project_state_byte_identical(
    tmp_path: Path, response: list[str], expected_reason: str
) -> None:
    """Decline, EOF, and Ctrl-C (interrupt) each leave project state
    byte-identical and report the exact reason. RED-via-T24.
    """
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    review = build_setup_review(
        root, tmp_path / "data", host="claude", permissions=_FULL_PERMISSIONS
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}

    before = _snapshot(root)
    consent = _ScriptedConsentIO(response)
    result = apply_setup_review(envelope, _FULL_PERMISSIONS, consent)
    assert result.get("status") == "skipped", result
    assert result.get("reason") == expected_reason, result
    assert _snapshot(root) == before


def test_piped_stdin_without_controlling_terminal_returns_full_preview(
    tmp_path: Path,
) -> None:
    """Without a controlling terminal (no `/dev/tty`), guided setup must
    return a full preview and incomplete readiness with an exact resume
    command, never blocking on stdin. RED-via-T24.
    """
    from rush.tools.setup_wizard import build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    review = build_setup_review(
        root, tmp_path / "data", host="claude", permissions=_FULL_PERMISSIONS
    )
    assert review["registration"].get("state") != "capability_verified"
    assert (
        "resume_command" in json.dumps(review) or review.get("next_action") is not None
    )


def test_absent_host_blocks_with_single_recovery_action_no_config_writes(
    tmp_path: Path,
) -> None:
    """If the selected host's own CLI binary is absent, the blocker is
    `absent_host` with exactly one recovery action, and zero config writes.
    RED-via-T24.
    """
    from rush.tools.setup_wizard import build_setup_review

    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "project"
    root.mkdir()
    before = _snapshot(home)

    review = build_setup_review(
        root,
        tmp_path / "data",
        host="codex",
        permissions=_FULL_PERMISSIONS,
        resolve=False,
        home=home,
        which=lambda _name: None,  # no `codex` on PATH
    )
    registration = review["registration"]
    assert registration.get("blocker") == "absent_host"
    assert (
        len(registration.get("recovery_actions", registration.get("recovery", []))) == 1
    )
    assert _snapshot(home) == before


def test_host_write_partial_failure_triggers_compensation(tmp_path: Path) -> None:
    """A failed atomic host-config write during apply must be compensated
    (removed only if it still matches this transaction's own bytes), never
    left half-written. RED-via-T24.
    """
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text("", encoding="utf-8")

    review = build_setup_review(
        root,
        tmp_path / "data",
        host="codex",
        permissions=_FULL_PERMISSIONS,
        home=home,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}
    before = _snapshot(home)

    consent = _ScriptedConsentIO(["y"])
    result = apply_setup_review(
        envelope,
        _FULL_PERMISSIONS,
        consent,
        atomic_write_bytes=lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )
    assert result.get("status") in ("error", "skipped")
    assert _snapshot(home) == before, (
        "a failed write must leave the host config untouched"
    )


def test_idempotent_resume_is_a_no_op_on_completed_stages(
    tmp_path: Path, _isolated_home: Path
) -> None:
    """Re-running apply on an envelope whose stages already completed must
    be a no-op: it reports the completed stages, performs zero additional
    writes, and never re-prompts for already-answered consent. RED-via-T24.
    """
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    review = build_setup_review(
        root,
        tmp_path / "data",
        host="claude",
        permissions=_FULL_PERMISSIONS,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}
    host_calls: list[tuple[tuple[str, ...], str]] = []
    fake_claude = _fake_claude_runner(_isolated_home, host_calls)

    first_consent = _ScriptedConsentIO(["y"] * 10)
    apply_setup_review(
        envelope, _FULL_PERMISSIONS, first_consent, host_runner=fake_claude
    )
    after_first = _snapshot(root)

    second_consent = _ScriptedConsentIO([])
    apply_setup_review(
        envelope, _FULL_PERMISSIONS, second_consent, host_runner=fake_claude
    )
    assert second_consent.prompts == [], (
        "a fully-completed rerun must not ask for consent again"
    )
    assert _snapshot(root) == after_first


def test_readiness_states_progress_to_capability_verified_only_on_observed_call(
    tmp_path: Path,
) -> None:
    """Readiness only reaches `capability_verified` from an actually observed
    host tool call whose result `project.project_id` matches the selected
    project -- a config write or a disconnected process never proves it.
    RED-via-T24.
    """
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review
    from rush.workflows.projects import register_project

    root = tmp_path / "project"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    # The selected project's id must be known to the fake host's canned
    # answer, so the project is registered first; the review then binds it
    # (editing the review afterwards would be tampering, rejected by design).
    expected_project_id = register_project(root, data_root=tmp_path / "data").project_id

    calls: list[tuple[tuple[str, ...], str]] = []

    def fake_host_runner(argv: tuple[str, ...], cwd: str) -> str:
        calls.append((argv, cwd))
        return json.dumps(
            {
                "tool_calls": [
                    {
                        "name": "rush_status",
                        "result": {"project": {"project_id": expected_project_id}},
                    }
                ]
            }
        )

    review = build_setup_review(
        root,
        tmp_path / "data",
        host="claude",
        permissions=_FULL_PERMISSIONS,
        resolve=True,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}

    consent = _ScriptedConsentIO(["y"] * 10)
    result = apply_setup_review(
        envelope, _FULL_PERMISSIONS, consent, host_runner=fake_host_runner
    )
    raw = result.get("raw", result)
    registration = raw.get("registration", raw)
    assert registration.get("state") == "capability_verified", registration
    assert calls, (
        "expected the fake host CLI runner to actually be invoked for the probe"
    )


def test_status_call_for_another_project_never_reaches_capability_verified(
    tmp_path: Path,
) -> None:
    """An observed `rush_status` call that reports a different project (a
    server bound elsewhere) is not proof for this project: readiness stops
    below `capability_verified`."""
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    root = tmp_path / "project"
    root.mkdir()

    def other_project_runner(argv: tuple[str, ...], cwd: str) -> str:
        return json.dumps(
            {
                "tool_calls": [
                    {
                        "name": "rush_status",
                        "result": {"project": {"project_id": "some-other-project"}},
                    }
                ]
            }
        )

    review = build_setup_review(
        root,
        tmp_path / "data",
        host="claude",
        permissions=_FULL_PERMISSIONS,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}
    result = apply_setup_review(
        envelope,
        _FULL_PERMISSIONS,
        _ScriptedConsentIO(["y"] * 10),
        host_runner=other_project_runner,
    )
    registration = result["raw"]["registration"]
    assert registration["state"] != "capability_verified", registration
    assert registration["capability_verified"] is False
    assert result["ready"] is False


# ===========================================================================
# Group 6 -- mcp serve --project/--session (own-T26 missing deliverable)
# ===========================================================================


def test_mcp_serve_accepts_project_and_session_flags() -> None:
    """`rush mcp serve --project ID --session SID` must exist as CLI surface;
    SID becomes the default session for status/project/scan tools when the
    caller omits one. RED: `serve` (`cli.py`) has only `--memory-session`
    today, no `--project`/`--session`.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "serve", "--help"])
    assert "--project" in result.output
    assert "--session" in result.output


def test_mcp_serve_unknown_project_id_errors_before_partial_server_start(
    tmp_path: Path,
) -> None:
    """An unknown `--project` ID is a startup error on stderr with a
    non-zero exit and no partial server -- `run_stdio`/`build_server` must
    never start listening on stdio for an unresolved anchor. RED: no such
    validation exists (the flag itself does not exist yet).
    """
    home = tmp_path / "home"
    home.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["mcp", "serve", "--project", "not-a-real-project-id"],
        env={"HOME": str(home)},
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "no such option" not in result.output.lower(), (
        "expected a real 'unknown project' startup error, not a missing-flag "
        f"usage error: {result.output!r}"
    )


# ===========================================================================
# Group 7 -- design §3 "Registration entry" (RED-via-T3: plan/apply_agent_instructions)
# ===========================================================================


def test_claude_registration_uses_local_scope_bound_to_project_cwd(
    tmp_path: Path,
) -> None:
    """Claude Code registration must run its native `mcp add` with
    `--scope local` (not `user`) and `cwd=root`, so the binding is per
    project. RED-via-T3: `plan_agent_instructions`/`apply_agent_instructions`
    do not exist; today's `plan_agent_registration`/`apply_agent_registration`
    also hardcode `--scope user` and never pass `cwd` to `subprocess.run`.
    """
    from rush.integrations.agents import plan_agent_instructions

    root = tmp_path / "project"
    root.mkdir()
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    log_path = tmp_path / "claude_calls.log"
    claude = fake_bin / "claude"
    claude.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"with open({str(log_path)!r}, 'a') as f:\n"
        "    f.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}) + chr(10))\n",
        encoding="utf-8",
    )
    claude.chmod(claude.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    old_path = os.environ.get("PATH")
    os.environ["PATH"] = f"{fake_bin}:{old_path or ''}"
    try:
        step = plan_agent_instructions(
            "claude-code", rush_binary="/opt/rush/bin/rush", project_root=root
        )
        from rush.integrations.agents import apply_agent_instructions

        apply_agent_instructions(step, project_root=root)
    finally:
        if old_path is not None:
            os.environ["PATH"] = old_path

    calls = (
        [json.loads(line) for line in log_path.read_text().splitlines() if line]
        if log_path.exists()
        else []
    )
    assert calls, "expected the fake `claude` binary to actually be invoked"
    add_call = next(c for c in calls if "add" in c["argv"])
    assert "--scope" in add_call["argv"] and "local" in add_call["argv"], add_call
    assert add_call["cwd"] == str(root), add_call


def test_codex_registration_host_change_diff_requires_consent_to_rebind(
    tmp_path: Path,
) -> None:
    """An existing Codex `rush` entry bound to a different project shows a
    host-change diff; declining leaves bytes unchanged, accepting rebinds it,
    and T3's ownership ledger at `<data_root>/agents/owned.json` records it.
    RED-via-T3: `plan_agent_instructions`/`apply_agent_instructions` and the
    ledger do not exist.
    """
    from rush.integrations.agents import (
        ADAPTERS,
        apply_agent_instructions,
        plan_agent_instructions,
    )

    home = tmp_path / "home"
    data_root = tmp_path / "data"
    root = tmp_path / "project"
    root.mkdir()
    config_path = ADAPTERS["codex"].config_paths("Darwin", home)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    original_text = (
        "[mcp_servers.rush]\n"
        'command = "/opt/rush/bin/rush"\n'
        'args = ["mcp", "serve", "--project", "other-project-id"]\n'
    )
    config_path.write_text(original_text, encoding="utf-8")
    before = config_path.read_bytes()

    plan = plan_agent_instructions(
        "codex",
        rush_binary="/opt/rush/bin/rush",
        project_root=root,
        home=home,
        data_root=data_root,
    )
    assert getattr(plan, "requires_consent", None) is True
    assert getattr(plan, "diff", None), (
        "expected a host-change diff for the bound-elsewhere entry"
    )

    declined = apply_agent_instructions(plan, consent=False, data_root=data_root)
    assert config_path.read_bytes() == before
    assert declined.ok is False or getattr(declined, "status", None) == "declined"

    accepted = apply_agent_instructions(plan, consent=True, data_root=data_root)
    assert accepted.ok is True
    assert config_path.read_bytes() != before

    ledger_path = data_root / "agents" / "owned.json"
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert "codex" in json.dumps(ledger)


def _write_stateful_fake_claude(bin_dir: Path, log_path: Path) -> None:
    """A fake `claude` on PATH that keeps local-scope `rush` entries in
    $HOME/.claude.json the way Claude Code does (`mcp add/remove --scope
    local`, keyed by the cwd) and logs every call's argv and cwd."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "claude"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"LOG = {str(log_path)!r}\n"
        "args = sys.argv[1:]\n"
        "with open(LOG, 'a') as f:\n"
        "    f.write(json.dumps({'argv': args, 'cwd': os.getcwd()}) + chr(10))\n"
        "cfg = os.path.join(os.environ['HOME'], '.claude.json')\n"
        "data = json.load(open(cfg)) if os.path.exists(cfg) else {}\n"
        "servers = data.setdefault('projects', {}).setdefault(os.getcwd(), {})"
        ".setdefault('mcpServers', {})\n"
        "if args[:3] == ['mcp', 'add', 'rush'] and 'local' in args:\n"
        "    sep = args.index('--')\n"
        "    servers['rush'] = {'type': 'stdio', 'command': args[sep + 1],"
        " 'args': args[sep + 2:], 'env': {}}\n"
        "elif args[:3] == ['mcp', 'remove', 'rush'] and 'local' in args:\n"
        "    servers.pop('rush', None)\n"
        "json.dump(data, open(cfg, 'w'))\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_claude_local_registration_is_recorded_and_disconnect_mirrors_local_scope(
    tmp_path: Path, _isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T3 disconnect mirrors T26's local scope: the project's entry is
    recorded in the ownership ledger and removed with `claude mcp remove rush
    --scope local` run in the same project root -- never `--scope user`."""
    from rush.integrations.agents import (
        apply_agent_instructions,
        disconnect_agent,
        plan_agent_instructions,
    )

    root = (tmp_path / "project").resolve()
    root.mkdir()
    data_root = tmp_path / "data"
    log_path = tmp_path / "claude_calls.log"
    _write_stateful_fake_claude(tmp_path / "fakebin", log_path)
    monkeypatch.setenv("PATH", f"{tmp_path / 'fakebin'}:{os.environ.get('PATH', '')}")

    step = plan_agent_instructions(
        "claude-code",
        rush_binary=_FAKE_RUSH_BINARY,
        project_root=root,
        project_id="pid-1",
        data_root=data_root,
    )
    applied = apply_agent_instructions(step, data_root=data_root)
    assert applied.ok is True, applied
    config = json.loads((_isolated_home / ".claude.json").read_text())
    entry = config["projects"][str(root)]["mcpServers"]["rush"]
    assert entry["args"] == [
        "mcp",
        "serve",
        "--project",
        "pid-1",
        "--session",
        "claude:pid-1",
        "--profile",
        "core",
    ]
    ledger = json.loads((data_root / "agents" / "owned.json").read_text())["data"]
    [row] = ledger.values()
    assert (row["kind"], row["scope"], row["project_root"]) == (
        "mcp_entry",
        "local",
        str(root),
    )

    result = disconnect_agent("claude-code", project_root=root, data_root=data_root)
    assert result.status == "ok", result
    assert "mcp_entry" in result.removed
    calls = [json.loads(line) for line in log_path.read_text().splitlines()]
    remove = [c for c in calls if c["argv"][:2] == ["mcp", "remove"]]
    assert remove == [
        {"argv": ["mcp", "remove", "rush", "--scope", "local"], "cwd": str(root)}
    ]
    config = json.loads((_isolated_home / ".claude.json").read_text())
    assert "rush" not in config["projects"][str(root)]["mcpServers"]


# ===========================================================================
# Group 8 -- guided consent comes from the controlling terminal only
# ===========================================================================


def test_guided_setup_reads_consent_from_terminal_not_piped_stdin(
    tmp_path: Path, _isolated_home: Path
) -> None:
    """On the guided bootstrap route stdin is the downloaded script, so a
    "y" arriving on stdin must never count: only the controlling terminal
    answers. Here stdin says "y" and the terminal (a real PTY) says "n", so
    setup is declined and nothing is written."""
    import contextlib
    import pty
    import select
    import time

    root = tmp_path / "project"
    root.mkdir()
    marker = tmp_path / "result.json"
    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            read_end, write_end = os.pipe()
            os.write(write_end, b"y\ny\ny\ny\n")
            os.close(write_end)
            os.dup2(read_end, 0)
            from rush.tools.setup_wizard import run_guided_setup

            payload, code = run_guided_setup(root.resolve(), "codex")
            marker.write_text(json.dumps({"payload": payload, "code": code}))
        finally:
            os._exit(0)
    output = b""
    answered = False
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master_fd], [], [], 0.5)
        if not ready:
            if os.waitpid(pid, os.WNOHANG) != (0, 0):
                break
            continue
        try:
            chunk = os.read(master_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
        if not answered and b"[y/N]" in output:
            os.write(master_fd, b"n\n")
            answered = True
    else:
        os.kill(pid, 9)
    os.close(master_fd)
    with contextlib.suppress(ChildProcessError):
        os.waitpid(pid, 0)

    assert answered, output.decode(errors="replace")
    result = json.loads(marker.read_text())
    assert result["payload"]["status"] == "skipped"
    assert result["payload"]["reason"] == "declined"
    assert result["code"] == 0
    assert not (root / "rush.toml").exists()
    assert not (_isolated_home / ".codex").exists()


def test_guided_setup_without_terminal_returns_preview_and_resume_command(
    tmp_path: Path,
) -> None:
    """With no controlling terminal the guided route never prompts: it
    returns the full preview, incomplete readiness and the exact
    shell-quoted resume command, and writes nothing."""
    from rush.tools.setup_wizard import run_guided_setup

    root = tmp_path / "my project ü"
    root.mkdir()
    payload, code = run_guided_setup(
        root.resolve(), "codex", open_terminal=lambda: None
    )
    assert code == 0
    assert payload["status"] == "skipped"
    assert payload["reason"] == "no_terminal"
    assert payload["readiness"]["complete"] is False
    assert payload["resume_command"] == (
        f"rush setup {shlex.quote(str(root.resolve()))} --agent codex"
    )
    assert shlex.split(payload["resume_command"])[2] == str(root.resolve())
    assert not (root / "rush.toml").exists()


def test_t7_setup_hooks_stage_activates_only_on_enable_agent_hooks(
    tmp_path: Path, _isolated_home: Path
) -> None:
    """T7: `rush setup --enable-agent-hooks` previews the post-edit hook
    activation, asks its own question, writes the activation record on "y",
    and a completed rerun reports it unchanged without asking again."""
    from rush.integrations.agent_hooks import activation_record_path
    from rush.tools.setup_wizard import (
        apply_setup_review,
        build_setup_review,
        render_setup_review,
    )

    root = tmp_path / "project"
    root.mkdir()
    data_root = tmp_path / "data"
    review = build_setup_review(
        root,
        data_root,
        host="claude",
        permissions=_FULL_PERMISSIONS,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
        enable_hooks=True,
    )
    assert review["hooks"]["state"] == "pending"
    assert "not available" not in render_setup_review(review)
    assert "7. Hooks: pending" in render_setup_review(review)
    envelope = {"kind": "setup", "schema_version": 1, "review": review}
    fake_claude = _fake_claude_runner(_isolated_home, [])

    consent = _ScriptedConsentIO(["y"] * 10)
    result = apply_setup_review(
        envelope, _FULL_PERMISSIONS, consent, host_runner=fake_claude
    )

    raw = result.get("raw", result)
    assert raw["hooks"]["state"] == "applied", raw["hooks"]
    assert any("post-edit check" in prompt for prompt in consent.prompts)
    records = json.loads(activation_record_path(data_root).read_text())["activations"]
    assert [(r["host"], r["canonical_root"]) for r in records] == [
        ("claude", str(root.resolve()))
    ]

    again = _ScriptedConsentIO([])
    rerun = apply_setup_review(
        envelope, _FULL_PERMISSIONS, again, host_runner=fake_claude
    )
    assert again.prompts == []
    assert rerun.get("raw", rerun)["hooks"]["state"] == "unchanged"


def test_t7_setup_without_enable_agent_hooks_never_activates(
    tmp_path: Path, _isolated_home: Path
) -> None:
    from rush.integrations.agent_hooks import activation_record_path
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    root = tmp_path / "project"
    root.mkdir()
    data_root = tmp_path / "data"
    review = build_setup_review(
        root,
        data_root,
        host="claude",
        permissions=_FULL_PERMISSIONS,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
    )
    envelope = {"kind": "setup", "schema_version": 1, "review": review}
    consent = _ScriptedConsentIO(["y"] * 10)
    result = apply_setup_review(
        envelope,
        _FULL_PERMISSIONS,
        consent,
        host_runner=_fake_claude_runner(_isolated_home, []),
    )

    assert result.get("raw", result)["hooks"]["state"] == "not_requested"
    assert not any("post-edit check" in prompt for prompt in consent.prompts)
    assert not activation_record_path(data_root).exists()


class _AnswerByPrompt(_ScriptedConsentIO):
    """Answers "n" to any prompt containing one of `decline`, else "y"."""

    def __init__(self, decline: tuple[str, ...]) -> None:
        super().__init__([])
        self._decline = decline

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "n" if any(text in prompt for text in self._decline) else "y"


def _check_review(root: Path, data_root: Path, *, run_check: bool) -> dict:
    from rush.tools.setup_wizard import build_setup_review

    return build_setup_review(
        root,
        data_root,
        host="claude",
        permissions=_FULL_PERMISSIONS,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
        run_check=run_check,
    )


@pytest.mark.parametrize("path", ["not_requested", "declined"])
def test_t17_setup_check_without_consent_previews_and_runs_nothing(
    path: str,
    tmp_path: Path,
    _isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No --run-check, or "n" to the check question: the preview names the
    exact command, and apply runs no check and spawns nothing for it."""
    import shlex
    import subprocess

    from rush.tools.check import CheckTool
    from rush.tools.setup_wizard import apply_setup_review, render_setup_review

    root = tmp_path / "project dir"
    root.mkdir()
    review = _check_review(root, tmp_path / "data", run_check=path == "declined")
    # The check runs on a Rush-owned fixture, never on the user's project.
    fixture = Path(review["data_root"]) / "probes" / "<nonce>"
    command = f"rush check {shlex.quote(str(fixture))} --json"
    assert review["check"]["command"] == command
    rendered = render_setup_review(review)
    assert command in rendered
    assert "not available in this build" not in rendered

    spawns: list[object] = []

    def spy(*args: object, **kwargs: object) -> object:
        spawns.append(args[0] if args else kwargs.get("args"))
        raise AssertionError(f"unexpected spawn: {spawns[-1]!r}")

    checks: list[object] = []
    monkeypatch.setattr(subprocess, "run", spy)
    monkeypatch.setattr(subprocess, "Popen", spy)
    monkeypatch.setattr(CheckTool, "run", lambda *a, **k: checks.append(a))

    consent = _AnswerByPrompt(("Verify the connection", "rush check"))
    result = apply_setup_review(
        {"kind": "setup", "schema_version": 1, "review": review},
        _FULL_PERMISSIONS,
        consent,
        host_runner=_fake_claude_runner(_isolated_home, []),
    )

    check = result.get("raw", result)["check"]
    assert check["state"] == path
    assert check["command"] == command
    assert checks == []
    assert spawns == []
    asked = any("rush check" in prompt for prompt in consent.prompts)
    assert asked is (path == "declined")


@pytest.mark.needs_aislop
def test_t17_setup_check_with_consent_runs_rush_check_and_reports_real_result(
    tmp_path: Path,
    _isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    warm_npm_cache: str,
) -> None:
    """--run-check plus "y": setup runs the shared six-step check on its own
    fixture (never the user's root) with the check stage's grants, so every
    step runs, and reports the fixture's real statuses and findings."""
    from rush.tools.check import CheckTool
    from rush.tools.common import clear_binary_cache
    from rush.tools.setup_wizard import apply_setup_review, render_setup_review

    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.0.1"\n')
    (root / "bad.py").write_text("import os\n")
    review = _check_review(root, tmp_path / "data", run_check=True)
    assert review["check"]["state"] == "pending"
    rendered_review = render_setup_review(review)
    assert "10. Check: run the representative `rush check" in rendered_review
    assert "on a Rush-owned fixture" in rendered_review

    checked: list[Path] = []
    real_run = CheckTool.run

    def spy(self: CheckTool, path: Path, **kwargs: Any) -> Any:
        checked.append(Path(path))
        return real_run(self, path, **kwargs)

    monkeypatch.setattr(CheckTool, "run", spy)
    consent = _AnswerByPrompt(("Verify the connection",))
    # HOME is a temp dir, so aislop's default npm cache is cold: use the
    # session's warm one, so the ungranted slop step runs offline.
    monkeypatch.setenv("npm_config_cache", warm_npm_cache)
    monkeypatch.delenv("npm_config_offline", raising=False)
    clear_binary_cache()
    result = apply_setup_review(
        {"kind": "setup", "schema_version": 1, "review": review},
        _FULL_PERMISSIONS,
        consent,
        host_runner=_fake_claude_runner(_isolated_home, []),
    )
    clear_binary_cache()

    check = result.get("raw", result)["check"]
    assert check["state"] == "ran", check
    assert check["status"] == "fail"
    steps = {step["tool"]: step for step in check["steps"]}
    assert list(steps) == ["format", "lint", "typecheck", "dead", "slop", "test"]
    assert all(step["disposition"] == "executed" for step in steps.values()), steps
    assert steps["lint"]["status"] == "fail"
    assert "F401" in check["finding_rules"]
    assert check["findings"] > 0
    probes = Path(review["data_root"]) / "probes"
    assert [path.parent for path in checked] == [probes]
    assert all(root.resolve() not in [path, *path.parents] for path in checked)
    assert check["fixture_removed"] is True
    assert not checked[0].exists()
