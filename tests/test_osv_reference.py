"""Phase 03 OSV-Scanner offline-reference contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import osv
from rush.engines.osv import OsvScannerEngine


def test_osv_uses_offline_json_lockfile_scan(monkeypatch, tmp_path: Path) -> None:
    lockfile = tmp_path / "poetry.lock"
    lockfile.write_text("fixture")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout='{"results": []}', stderr="")

    monkeypatch.setattr(osv, "resolve_binary", lambda _binary: "C:/bin/osv-scanner")
    monkeypatch.setattr(osv, "run_subprocess", fake_run)

    result = OsvScannerEngine().run(lockfile, [], cwd=tmp_path)

    assert result["parsed"] == {"results": []}
    assert calls == [
        (
            [
                "C:/bin/osv-scanner",
                "scan",
                "--offline",
                "--format",
                "json",
                "-L",
                str(lockfile),
            ],
            {"cwd": tmp_path, "timeout": 120},
        )
    ]


def test_osv_normalizes_json_vulnerabilities_and_nonzero_findings_exit() -> None:
    result = OsvScannerEngine().normalize(
        {
            "exit_code": 1,
            "parsed": {
                "results": [
                    {
                        "source": {"path": "poetry.lock"},
                        "packages": [
                            {
                                "package": {
                                    "name": "example",
                                    "version": "1.0.0",
                                    "ecosystem": "PyPI",
                                },
                                "vulnerabilities": [
                                    {"id": "GHSA-example", "fixed_version": "1.1.0"}
                                ],
                            }
                        ],
                    }
                ]
            },
        },
        Path("."),
        "security",
    )

    assert result["status"] == "fail"
    assert result["findings"] == [
        {
            "path": "poetry.lock",
            "line": 0,
            "rule": "GHSA-example",
            "severity": "error",
            "message": "PyPI example==1.0.0: fixed in 1.1.0",
        }
    ]
    assert result["metadata"]["database_freshness"] == "unknown-offline"
    assert result["metadata"]["evidence_source"] == "local-offline-database"
