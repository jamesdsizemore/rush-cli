"""Phase 02 markdownlint-cli v0.49.1 reference-adapter contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import markdownlint
from rush.engines.markdownlint import MarkdownlintEngine


def test_markdownlint_uses_pinned_json_isolation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    source.write_text("# heading\n")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(argv: list[str], **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        markdownlint, "resolve_binary", lambda _binary: "C:/bin/markdownlint"
    )
    monkeypatch.setattr(markdownlint, "run_subprocess", fake_run)

    raw = MarkdownlintEngine().run(tmp_path, [str(source)], cwd=tmp_path)

    argv, kwargs = calls[0]
    assert argv == [
        "C:/bin/markdownlint",
        "--config",
        str(markdownlint.DEFAULT_CONFIG),
        "--ignore-path",
        str(markdownlint.DEFAULT_IGNORE),
        "--json",
        str(source),
    ]
    assert "--fix" not in argv
    assert "--rules" not in argv
    assert kwargs["cwd"] == tmp_path
    assert raw["stdout"] == "[]"


def test_markdownlint_normalizes_json_and_exit_codes(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "README.md"
    source.write_text("bad\n")
    monkeypatch.setattr(MarkdownlintEngine, "version", lambda _self: "0.49.1")

    result = MarkdownlintEngine().normalize(
        {
            "exit_code": 1,
            "stdout": json.dumps(
                [
                    {
                        "lineNumber": 1,
                        "ruleNames": ["MD041"],
                        "ruleDescription": "first-line-heading",
                        "ruleInformation": None,
                        "errorDetail": None,
                        "errorContext": "bad",
                        "errorRange": None,
                        "fixInfo": None,
                    }
                ]
            ),
            "stderr": "",
        },
        source,
        "markdown",
    )

    assert result["status"] == "warn"
    assert result["findings"][0]["rule"] == "MD041"
    assert result["findings"][0]["path"] == str(source)
    assert result["findings"][0]["line"] == 1
    assert (
        MarkdownlintEngine().normalize(
            {"exit_code": 0, "stdout": "not json", "stderr": ""}, source, "markdown"
        )["status"]
        == "error"
    )
