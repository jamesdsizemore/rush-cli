"""Phase 07.C Cosign reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import cosign
from rush.engines.cosign import CosignEngine
from rush.tools import common


def test_cosign_runs_verify_blob_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="Verified OK\n", stderr="")

    monkeypatch.setattr(cosign, "resolve_binary", lambda _binary: "C:/bin/cosign")
    monkeypatch.setattr(cosign, "run_subprocess", fake_run)

    raw = CosignEngine().run(
        tmp_path / "artifact.tar.gz", ["--key", "cosign.pub"], cwd=tmp_path
    )

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/cosign",
            "verify-blob",
            "--key",
            "cosign.pub",
            str(tmp_path / "artifact.tar.gz"),
        ]
    ]


def test_cosign_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = CosignEngine()
    monkeypatch.setattr(CosignEngine, "version", lambda _self: "2.4.0")

    clean = engine.normalize(
        {"exit_code": 0, "stdout": "Verified OK"}, tmp_path, "release"
    )
    finding = engine.normalize(
        {
            "exit_code": 1,
            "stderr": "error: signature verification failed",
        },
        tmp_path,
        "release",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "release"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "signature-verification-failed"


def test_cosign_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = CosignEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="release")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        cosign,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("cosign", 60)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="release")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
