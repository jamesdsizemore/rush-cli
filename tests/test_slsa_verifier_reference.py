"""Phase 11 SLSA Verifier reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import slsa_verifier
from rush.engines.slsa_verifier import SlsaVerifierEngine


def test_slsa_verifier_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"verified": true}', stderr=""
        )

    monkeypatch.setattr(
        slsa_verifier, "resolve_binary", lambda _binary: "C:/bin/slsa-verifier"
    )
    monkeypatch.setattr(slsa_verifier, "run_subprocess", fake_run)

    raw = SlsaVerifierEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/slsa-verifier",
            "verify-artifact",
            str(tmp_path),
        ]
    ]


def test_slsa_verifier_normalizes_clean_and_failures(
    monkeypatch, tmp_path: Path
) -> None:
    engine = SlsaVerifierEngine()
    monkeypatch.setattr(SlsaVerifierEngine, "version", lambda _self: "2.5.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "release")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "stderr": "Verification failed: builder identity mismatch",
            "findings": [{"verified": False}],
        },
        tmp_path,
        "release",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "slsa/provenance-verification-failed"
