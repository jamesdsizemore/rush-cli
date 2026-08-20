"""Phase 12 Kube-score reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import kube_score
from rush.engines.kube_score import KubeScoreEngine


def test_kube_score_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        kube_score, "resolve_binary", lambda _binary: "C:/bin/kube-score"
    )
    monkeypatch.setattr(kube_score, "run_subprocess", fake_run)

    raw = KubeScoreEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/kube-score",
            "score",
            "--output-format",
            "json",
            str(tmp_path),
        ]
    ]


def test_kube_score_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = KubeScoreEngine()
    monkeypatch.setattr(KubeScoreEngine, "version", lambda _self: "1.18.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "iac")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "manifest": {"name": "app-deployment"},
                    "check": {
                        "check": {
                            "id": "pod-networkpolicy",
                            "name": "Pod NetworkPolicy",
                        },
                        "critical": True,
                        "comments": [
                            {"summary": "Pod is not targeted by NetworkPolicy"}
                        ],
                    },
                }
            ],
        },
        tmp_path,
        "iac",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "pod-networkpolicy" in failing["findings"][0]["rule"]
