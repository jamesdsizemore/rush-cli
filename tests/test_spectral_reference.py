"""Phase 02 Spectral v6.16.3 reference-adapter contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import spectral
from rush.engines.spectral import SpectralEngine


def test_spectral_uses_owned_ruleset_and_json_without_custom_resolver(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "openapi.yaml"
    source.write_text("openapi: 3.0.0\ninfo: {}\npaths: {}\n")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(spectral, "resolve_binary", lambda _binary: "C:/bin/spectral")
    monkeypatch.setattr(spectral, "run_subprocess", fake_run)

    raw = SpectralEngine().run(source, [str(source)], cwd=tmp_path)

    assert raw == {"exit_code": 0, "stdout": "[]", "stderr": ""}
    assert calls[0][0] == [
        "C:/bin/spectral",
        "lint",
        "--ruleset",
        str(spectral.DEFAULT_RULESET),
        "--format",
        "json",
        "--fail-severity",
        "warn",
        "--ignore-unknown-format",
        str(source),
    ]
    assert "--resolver" not in calls[0][0]
    assert "--output" not in calls[0][0]


def test_spectral_normalizes_json_findings_and_exit_codes(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "openapi.yaml"
    source.write_text("openapi: 3.0.0\ninfo: {}\npaths: {}\n")
    monkeypatch.setattr(SpectralEngine, "version", lambda _self: "6.16.3")

    result = SpectralEngine().normalize(
        {
            "exit_code": 1,
            "stdout": '[{"code":"rush-openapi-info","path":["info"],"message":"OpenAPI info is required","severity":1,"range":{"start":{"line":1,"character":0}}}]',
            "stderr": "",
        },
        tmp_path,
        "yaml",
    )

    assert result["status"] == "warn"
    assert result["findings"] == [
        {
            "rule": "rush-openapi-info",
            "severity": "warn",
            "message": "OpenAPI info is required",
            "path": str(tmp_path),
            "line": 2,
            "column": 1,
        }
    ]


def test_spectral_rejects_remote_references_and_malformed_or_inconsistent_json(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.yaml"
    remote.write_text("$ref: https://example.invalid/schema.yaml\n")
    engine = SpectralEngine()

    remote_result = engine.run(remote, [str(remote)], cwd=tmp_path)
    malformed = engine.normalize(
        {"exit_code": 1, "stdout": "not-json", "stderr": ""}, tmp_path, "yaml"
    )
    inconsistent = engine.normalize(
        {
            "exit_code": 0,
            "stdout": '[{"code":"rush-openapi-info","path":[],"message":"missing info","severity":1,"range":{"start":{"line":0,"character":0}}}]',
            "stderr": "",
        },
        tmp_path,
        "yaml",
    )

    assert remote_result["exit_code"] == 2
    assert "remote reference blocked" in remote_result["stderr"]
    assert malformed["status"] == "error"
    assert malformed["metadata"]["terminal_reason"] == "malformed_output"
    assert inconsistent["status"] == "error"
    assert inconsistent["metadata"]["terminal_reason"] == "nonzero_exit"


def test_spectral_blocks_inline_remote_references(tmp_path: Path) -> None:
    source = tmp_path / "nested.yaml"
    source.write_text("components: {schema: {$ref: file:///outside.yaml}}\n")

    result = SpectralEngine().run(source, [str(source)], cwd=tmp_path)

    assert result["exit_code"] == 2
    assert "remote reference blocked" in result["stderr"]
