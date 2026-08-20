"""Phase 13 GraphQL-Inspector reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import graphql_inspector
from rush.engines.graphql_inspector import GraphQLInspectorEngine


def test_graphql_inspector_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        graphql_inspector,
        "resolve_binary",
        lambda _binary: "C:/bin/graphql-inspector",
    )
    monkeypatch.setattr(graphql_inspector, "run_subprocess", fake_run)

    raw = GraphQLInspectorEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/graphql-inspector",
            "validate",
            str(tmp_path),
            "--format",
            "json",
        ]
    ]


def test_graphql_inspector_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = GraphQLInspectorEngine()
    monkeypatch.setattr(GraphQLInspectorEngine, "version", lambda _self: "3.5.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "type": "FIELD_REMOVED",
                    "criticality": {"level": "BREAKING"},
                    "message": "Field 'user.address' was removed",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "graphql/field_removed" in failing["findings"][0]["rule"]
