"""Phase 02 actionlint v1.7.12 reference-adapter contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import actionlint
from rush.engines.actionlint import ActionlintEngine


def test_actionlint_uses_json_owned_config_and_no_child_linters(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / ".github" / "workflows" / "ci.yml"
    source.parent.mkdir(parents=True)
    source.write_text("name: ci\non: push\n")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        actionlint, "resolve_binary", lambda _binary: "C:/bin/actionlint"
    )
    monkeypatch.setattr(actionlint, "run_subprocess", fake_run)

    raw = ActionlintEngine().run(source, [str(source)], cwd=tmp_path)

    assert raw == {"exit_code": 0, "stdout": "[]", "stderr": ""}
    assert calls[0][0] == [
        "C:/bin/actionlint",
        "-config-file",
        str(actionlint.DEFAULT_CONFIG),
        "-shellcheck=",
        "-pyflakes=",
        "-no-color",
        "-format",
        "{{json .}}",
        str(source),
    ]


def test_actionlint_normalizes_json_findings_and_exit_codes(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / ".github" / "workflows" / "ci.yml"
    source.parent.mkdir(parents=True)
    source.write_text("name: ci\non: push\n")
    monkeypatch.setattr(ActionlintEngine, "version", lambda _self: "1.7.12")

    result = ActionlintEngine().normalize(
        {
            "exit_code": 1,
            "stdout": '[{"kind":"workflow","message":"unexpected runs-on key","filepath":".github/workflows/ci.yml","line":2,"column":1}]',
            "stderr": "",
        },
        tmp_path,
        "actions",
    )

    assert result["status"] == "warn"
    assert result["findings"] == [
        {
            "rule": "workflow",
            "severity": "warn",
            "message": "unexpected runs-on key",
            "path": str(source),
            "line": 2,
            "column": 1,
        }
    ]


def test_actionlint_rejects_malformed_or_inconsistent_json(tmp_path: Path) -> None:
    engine = ActionlintEngine()
    malformed = engine.normalize(
        {"exit_code": 1, "stdout": "not-json", "stderr": ""}, tmp_path, "actions"
    )
    inconsistent = engine.normalize(
        {
            "exit_code": 0,
            "stdout": '[{"kind":"workflow","message":"bad workflow","filepath":"ci.yml","line":1,"column":1}]',
            "stderr": "",
        },
        tmp_path,
        "actions",
    )

    assert malformed["status"] == "error"
    assert malformed["metadata"]["terminal_reason"] == "malformed_output"
    assert inconsistent["status"] == "error"
    assert inconsistent["metadata"]["terminal_reason"] == "nonzero_exit"
