"""Phase 02 TFLint v0.64.0 reference-adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import tflint
from rush.engines.tflint import TflintEngine
from rush.tools import common


def test_tflint_uses_local_json_argv_without_init_or_positional_files(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"issues": [], "errors": []}', stderr=""
        )

    monkeypatch.setattr(tflint, "resolve_binary", lambda _binary: "C:/bin/tflint")
    monkeypatch.setattr(tflint, "run_subprocess", fake_run)

    raw = TflintEngine().run(tmp_path, [str(tmp_path / "main.tf")], cwd=tmp_path)

    assert raw == {
        "exit_code": 0,
        "stdout": '{"issues": [], "errors": []}',
        "stderr": "",
    }
    assert calls == [
        [
            "C:/bin/tflint",
            "--chdir",
            str(tmp_path),
            "--format",
            "json",
            "--call-module-type",
            "none",
        ]
    ]
    assert "--init" not in calls[0]
    assert "--force" not in calls[0]
    assert str(tmp_path / "main.tf") not in calls[0]


def test_tflint_normalizes_clean_findings_and_structured_errors(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "main.tf"
    source.write_text('resource "example" "test" {}\n')
    monkeypatch.setattr(TflintEngine, "version", lambda _self: "0.64.0")
    engine = TflintEngine()

    clean = engine.normalize(
        {"exit_code": 0, "stdout": '{"issues": [], "errors": []}'}, tmp_path, "iac"
    )
    finding = engine.normalize(
        {
            "exit_code": 2,
            "stdout": (
                '{"issues": [{"rule": {"name": "terraform_required_version", '
                '"severity": "warning"}, "message": "Missing version", '
                '"range": {"filename": "main.tf", "start": {"line": 1, '
                '"column": 1}}}], "errors": []}'
            ),
        },
        tmp_path,
        "iac",
    )
    structured_error = engine.normalize(
        {
            "exit_code": 1,
            "stdout": '{"issues": [], "errors": [{"message": "invalid config"}]}',
        },
        tmp_path,
        "iac",
    )
    malformed = engine.normalize(
        {"exit_code": 1, "stdout": "not-json"}, tmp_path, "iac"
    )

    assert clean["status"] == "ok"
    assert finding["status"] == "warn"
    assert finding["findings"] == [
        {
            "path": str(source),
            "line": 1,
            "column": 1,
            "rule": "terraform_required_version",
            "severity": "warn",
            "message": "Missing version",
        }
    ]
    assert structured_error["status"] == "error"
    assert structured_error["metadata"]["terminal_reason"] == "engine_error"
    assert malformed["status"] == "error"
    assert malformed["metadata"]["terminal_reason"] == "malformed_output"


def test_tflint_missing_and_timeout_are_structured(monkeypatch, tmp_path: Path) -> None:
    engine = TflintEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="iac")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        tflint,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("tflint", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="iac")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
