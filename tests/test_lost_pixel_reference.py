"""Phase 17 Lost Pixel reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import lost_pixel
from rush.engines.lost_pixel import LostPixelEngine


def test_lost_pixel_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"differences": []}', stderr=""
        )

    monkeypatch.setattr(
        lost_pixel, "resolve_binary", lambda _binary: "C:/bin/lost-pixel"
    )
    monkeypatch.setattr(lost_pixel, "run_subprocess", fake_run)

    raw = LostPixelEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/lost-pixel",
            "update",
            "--json",
        ]
    ]


def test_lost_pixel_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = LostPixelEngine()
    monkeypatch.setattr(LostPixelEngine, "version", lambda _self: "3.19.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "visual")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "name": "Button-Primary-Hover",
                    "storyId": "components-button--primary",
                }
            ],
        },
        tmp_path,
        "visual",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "lost-pixel/visual-diff" in failing["findings"][0]["rule"]
