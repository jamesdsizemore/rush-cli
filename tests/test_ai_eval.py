"""Tests for AiEvalTool (Phase 09)."""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.ai_eval import AiEvalTool


@pytest.mark.parametrize(
    "engine_name", ("promptfoo", "garak", "deepeval", "guardrails")
)
@pytest.mark.parametrize(
    "denied_permission", ("network", "slow", "artifact_write", "build", "default")
)
def test_eval_denies_before_provider_or_report_write(
    monkeypatch, tmp_path: Path, engine_name: str, denied_permission: str
) -> None:
    from rush.engines import ENGINES

    calls: list[object] = []
    monkeypatch.setattr(
        "rush.tools.ai_eval.run_engine", lambda *_args, **_kwargs: calls.append("run")
    )
    monkeypatch.setattr(
        "rush.tools.ai_eval.engine_on_path",
        lambda *_args: calls.append("discover"),
        raising=False,
    )
    for name in tuple(ENGINES):
        if name != engine_name:
            monkeypatch.delitem(ENGINES, name)

    granted = {"network": True, "slow": True, "artifact_write": True}
    permissions = (
        ExecutionPermissions()
        if denied_permission == "default"
        else ExecutionPermissions(build=True)
        if denied_permission == "build"
        else ExecutionPermissions(**dict(granted, **{denied_permission: False}))
    )
    result = AiEvalTool().run(tmp_path, permissions=permissions)

    assert result["status"] == "skipped"
    assert calls == []
    assert not (tmp_path / ".rush" / "runs").exists()


@pytest.mark.parametrize(
    "engine_name", ("promptfoo", "garak", "deepeval", "guardrails")
)
def test_eval_passes_exact_grants(
    monkeypatch, tmp_path: Path, engine_name: str
) -> None:
    from rush.engines import ENGINES

    calls: list[dict[str, object]] = []

    def capture_run_engine(*_args, **kwargs):
        assert _args[0].name == engine_name
        calls.append(kwargs)
        return {"status": "ok", "metadata": {}}

    monkeypatch.setattr("rush.tools.ai_eval.run_engine", capture_run_engine)
    monkeypatch.setattr(
        "rush.tools.ai_eval.engine_on_path",
        lambda binary: binary == ENGINES[engine_name].binary,
        raising=False,
    )
    grants = ExecutionPermissions(network=True, slow=True, artifact_write=True)

    result = AiEvalTool().run(tmp_path, permissions=grants)

    assert result["status"] == "ok"
    assert len(calls) == 1
    assert calls[0]["permissions"] == grants
    assert calls[0]["required_permissions"] == grants
    report_dir = calls[0]["cwd"]
    assert isinstance(report_dir, Path)
    assert report_dir.is_relative_to(tmp_path / ".rush" / "runs")
    assert report_dir.is_dir()


def test_ai_eval_skipped_when_no_engine(monkeypatch, tmp_path: Path) -> None:
    tool = AiEvalTool()
    monkeypatch.setattr(
        "rush.tools.ai_eval.engine_on_path", lambda _binary: False, raising=False
    )

    res = tool.run(
        tmp_path,
        permissions=ExecutionPermissions(network=True, slow=True, artifact_write=True),
    )
    assert res["status"] == "skipped"
    assert "no AI evaluation engine" in res["summary"]
    assert res["metadata"]["execution"]["mode"] == "executed"
    assert res["metadata"]["execution"]["producer"] == "ai-eval"


def test_ai_eval_call_interface(monkeypatch, tmp_path: Path) -> None:
    tool = AiEvalTool()

    res = tool(tmp_path, allow_slow=True, allow_network=True)
    assert res["status"] == "skipped"
    assert res["metadata"]["execution"]["requested_permissions"]["slow"] is True
    assert res["metadata"]["execution"]["requested_permissions"]["network"] is True


@pytest.mark.parametrize(
    "key", ["pre_build", "pre_build_command", "pre_build_commands"]
)
def test_eval_rejects_pre_build_before_launch(monkeypatch, tmp_path, key):
    calls = []
    monkeypatch.setattr(
        "rush.tools.ai_eval.run_engine", lambda *a, **kw: calls.append(a)
    )
    result = AiEvalTool().run(
        tmp_path,
        config={key: "echo should-not-run"},
        permissions=ExecutionPermissions(
            network=True, slow=True, artifact_write=True, build=True
        ),
    )
    assert result["status"] == "error"
    assert calls == []
    assert not (tmp_path / ".rush").exists()


def test_eval_rejects_redirected_report_directory(monkeypatch, tmp_path):
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / ".rush").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        "rush.tools.ai_eval.engine_on_path", lambda _binary: True, raising=False
    )
    monkeypatch.setattr(
        "rush.tools.ai_eval.run_engine", lambda *a, **kw: {"status": "ok"}
    )
    result = AiEvalTool().run(
        project,
        permissions=ExecutionPermissions(network=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "engine_name,report_name",
    [
        ("promptfoo", "promptfoo-report.json"),
        ("garak", "garak_report.report.jsonl"),
        ("deepeval", "deepeval-results.json"),
        ("guardrails", "guardrails-results.json"),
    ],
)
def test_eval_adapters_refuse_preexisting_reports(
    monkeypatch, tmp_path, engine_name, report_name
):
    from rush.engines import ENGINES

    report = tmp_path / report_name
    report.write_text('{"stale": true}')
    calls = []
    module = importlib.import_module(f"rush.engines.{engine_name}")
    monkeypatch.setattr(
        module,
        "run_subprocess",
        lambda *a, **kw: (
            calls.append(a) or subprocess.CompletedProcess(a, 0, stdout="{}", stderr="")
        ),
    )
    with pytest.raises(ValueError, match="preexist"):
        ENGINES[engine_name].run(tmp_path, [], cwd=tmp_path)
    assert calls == []
    assert report.read_text() == '{"stale": true}'


def test_eval_live_local_provider(monkeypatch, tmp_path):
    if shutil.which("promptfoo") is None:
        pytest.skip("Promptfoo must be installed for live local-provider acceptance")
    requests = []

    class Provider(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            body = b'{"output":"local-answer"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    secret = "sk-ant-" + "L" * 48
    config = {
        "prompts": ["Return deterministic answer"],
        "providers": [
            {
                "id": f"http://127.0.0.1:{server.server_port}/answer",
                "config": {
                    "method": "GET",
                    "transformResponse": "json.output",
                    "headers": {"Authorization": f"Bearer {secret}"},
                },
            }
        ],
    }
    stale = tmp_path / "promptfoo-report.json"
    stale.write_text('{"stale": true}')
    report_dirs = []
    try:
        for expected, status, failures in [
            ("local-answer", "ok", 0),
            ("different-answer", "fail", 1),
        ]:
            config["tests"] = [{"assert": [{"type": "equals", "value": expected}]}]
            (tmp_path / "promptfooconfig.json").write_text(json.dumps(config))
            result = AiEvalTool().run(
                tmp_path,
                permissions=ExecutionPermissions(
                    network=True, slow=True, artifact_write=True
                ),
            )
            assert result["status"] == status, result
            assert len(result["findings"]) == failures
            assert result["raw"]["results"]["stats"]["successes"] == 1 - failures
            assert result["raw"]["results"]["stats"]["failures"] == failures
            assert secret not in json.dumps(result)
            report_dir = Path(result["metadata"]["execution"]["report_path"])
            report_dirs.append(report_dir)
            assert report_dir.is_relative_to(tmp_path / ".rush/runs")
            report = report_dir / "promptfoo-report.json"
            assert secret not in report.read_text()
            assert (
                json.loads(report.read_text())["results"]["stats"]["failures"]
                == failures
            )
        assert report_dirs[0] != report_dirs[1]
        assert requests == ["/answer", "/answer"]
        assert stale.read_text() == '{"stale": true}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
