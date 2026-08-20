"""Phase 03 cdxgen reference-adapter contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import cdxgen
from rush.engines.cdxgen import CdxgenEngine


def test_cdxgen_uses_only_caller_supplied_contained_output(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"bomFormat":"CycloneDX","components":[]}', stderr=""
        )

    monkeypatch.setattr(cdxgen, "resolve_binary", lambda _binary: "C:/bin/cdxgen")
    monkeypatch.setattr(cdxgen, "run_subprocess", fake_run)
    monkeypatch.setattr(CdxgenEngine, "version", lambda _self: "11.6.9")

    output = tmp_path / "rush-sbom.json"
    result = CdxgenEngine().run(tmp_path, ["--output", str(output)], cwd=tmp_path)

    assert result["exit_code"] == 0
    assert calls == [
        (
            ["C:/bin/cdxgen", "--output", str(output), str(tmp_path)],
            {"cwd": tmp_path, "timeout": 120},
        )
    ]


def test_cdxgen_nonzero_exit_is_an_error_not_a_finding() -> None:
    result = CdxgenEngine().normalize(
        {"exit_code": 1, "stdout": "", "stderr": "generation failed"},
        Path("."),
        "sbom",
    )

    assert result["status"] == "error"
    assert result["findings"] == []
