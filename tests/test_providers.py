"""Tests for LLM review provider interfaces and registry."""

from __future__ import annotations

import pytest

from rush.providers import (
    AnthropicProvider,
    OpenAIProvider,
    get_configured_provider,
)


def test_anthropic_provider_unconfigured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicProvider()
    assert not provider.is_configured()
    assert provider.summarize_findings([]) is None


def test_anthropic_provider_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    provider = AnthropicProvider()
    assert provider.is_configured()
    res = provider.summarize_findings([{"rule": "test-rule", "message": "sample"}])
    assert res is not None
    assert res.provider == "anthropic"
    assert "1 code review finding" in res.content
    assert res.model == provider.default_model


def test_openai_provider_unconfigured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider()
    assert not provider.is_configured()
    assert provider.summarize_findings([]) is None


def test_openai_provider_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")
    provider = OpenAIProvider()
    assert provider.is_configured()
    res = provider.summarize_findings([{"rule": "test-rule", "message": "sample"}])
    assert res is not None
    assert res.provider == "openai"
    assert "1 code review finding" in res.content
    assert res.model == provider.default_model


def test_get_configured_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_configured_provider() is None

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-key")
    prov = get_configured_provider()
    assert prov is not None
    assert prov.name == "openai"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-key")
    prov2 = get_configured_provider()
    assert prov2 is not None
    assert prov2.name == "anthropic"


def test_anthropic_provider_allow_network_mock(monkeypatch):
    import io
    import json
    import urllib.request

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    provider = AnthropicProvider()

    mock_resp_data = {
        "model": "claude-3-5-sonnet-20241022",
        "content": [
            {"type": "text", "text": "Fix the missing return type annotation."}
        ],
    }

    class MockUrlopen:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return io.BytesIO(json.dumps(mock_resp_data).encode("utf-8"))

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", MockUrlopen)
    res = provider.summarize_findings(
        [{"rule": "typecheck", "message": "missing"}], allow_network=True
    )
    assert res is not None
    assert "Fix the missing return type" in res.content


def test_openai_provider_allow_network_mock(monkeypatch):
    import io
    import json
    import urllib.request

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")
    provider = OpenAIProvider()

    mock_resp_data = {
        "model": "gpt-4o",
        "choices": [
            {"message": {"content": "Resolved security vulnerability in auth."}}
        ],
    }

    class MockUrlopen:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return io.BytesIO(json.dumps(mock_resp_data).encode("utf-8"))

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", MockUrlopen)
    res = provider.summarize_findings(
        [{"rule": "security", "message": "auth"}], allow_network=True
    )
    assert res is not None
    assert "Resolved security vulnerability" in res.content


def test_continuity_provider_resume_uses_a_user_owned_claude_cli_profile(
    monkeypatch, tmp_path
):
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    saved = SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="handoff.json",
        handoff={
            "current_goal": "finish the adapter",
            "open_work": ["add a focused test"],
            "historic_instruction": "do not expose this",
        },
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert saved["status"] == "ok"

    class Process:
        returncode = 0
        stdout = '{"result":"BENCHMARK_OK","token":"sk-ant-abcdefghijklmnopqrstuvwxyz012345"}'
        stderr = ""

    calls = []
    monkeypatch.setattr("shutil.which", lambda binary: "C:/tools/claude.cmd")
    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **kwargs: calls.append((command, kwargs)) or Process(),
    )

    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff.json",
        provider_id="claude_code",
        permissions=ExecutionPermissions(network=True),
    )

    assert result["status"] == "ok"
    assert calls[0][0][:5] == [
        "cmd.exe",
        "/d",
        "/c",
        "C:/tools/claude.cmd",
        "-p",
    ]
    assert calls[0][1]["shell"] is False
    assert "do not expose this" not in str(calls[0][0])
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz012345" not in str(result)
    assert result["metadata"]["provider_route"] == {
        "provider_id": "claude_code",
        "transport": "cli",
        "state": "completed",
    }


def test_continuity_provider_resume_defers_zai_without_starting_a_process(
    monkeypatch, tmp_path
):
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    monkeypatch.setattr(
        "subprocess.run", lambda *_args, **_kwargs: pytest.fail("must not run Z.AI")
    )
    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        provider_id="zai",
        permissions=ExecutionPermissions(network=True),
    )

    assert result["status"] == "skipped"
    assert result["metadata"]["provider_route"] == {
        "provider_id": "zai",
        "transport": "cli",
        "state": "deferred",
    }


@pytest.mark.parametrize("provider_id", ["9router_api"])
def test_continuity_provider_resume_does_not_invoke_unimplemented_router_routes(
    monkeypatch, provider_id, tmp_path
):
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    monkeypatch.setattr(
        "subprocess.run", lambda *_args, **_kwargs: pytest.fail("must not invoke route")
    )
    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        provider_id=provider_id,
        permissions=ExecutionPermissions(network=True),
    )
    assert result["status"] == "skipped"
    assert result["metadata"]["provider_route"]["state"] == "unavailable"


def test_continuity_provider_resume_posts_only_bounded_handoff_to_omniroute(
    monkeypatch, tmp_path
):
    import json

    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    saved = SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="handoff",
        handoff={
            "current_goal": "finish the router adapter",
            "open_work": ["verify the bounded API request"],
            "historic_instruction": "do not expose this history",
            "failure_fingerprint": "failed-patch-must-not-leave",
        },
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert saved["status"] == "ok"
    observed: dict[str, object] = {}

    class Response:
        status = 200

        def read(self):
            return b'{"choices":[{"message":{"content":"accepted"}}]}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def open_request(request, *, timeout):
        observed["url"] = request.full_url
        observed["method"] = request.get_method()
        observed["body"] = request.data.decode("utf-8")
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff",
        provider_id="omniroute_api",
        permissions=ExecutionPermissions(network=True),
    )

    payload = json.loads(str(observed["body"]))
    assert observed["url"] == "http://127.0.0.1:20128/v1/chat/completions"
    assert observed["method"] == "POST"
    assert observed["timeout"] == 30.0
    assert payload["model"] == "auto"
    assert payload["stream"] is False
    assert "finish the router adapter" in payload["messages"][0]["content"]
    assert "do not expose this history" not in payload["messages"][0]["content"]
    assert "failed-patch-must-not-leave" not in payload["messages"][0]["content"]
    assert result["status"] == "ok"
    assert result["raw"] is None
    assert result["metadata"]["provider_route"] == {
        "provider_id": "omniroute_api",
        "transport": "openai-compatible-api",
        "state": "completed",
        "endpoint_class": "fixed-loopback",
    }


@pytest.mark.parametrize("response_body", [b"not-json", b'{"choices":[]}'])
def test_omniroute_provider_resume_rejects_nonsemantic_success(
    monkeypatch, response_body, tmp_path
):
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="handoff",
        permissions=ExecutionPermissions(cache_write=True),
    )

    class Response:
        status = 200

        def read(self):
            return response_body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff",
        provider_id="omniroute_api",
        permissions=ExecutionPermissions(network=True),
    )

    assert result["status"] == "error"
    assert result["raw"] is None
    assert result["metadata"]["provider_route"]["state"] == "invalid_response"


def test_omniroute_resume_requires_network_permission_before_request(
    monkeypatch, tmp_path
):
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="handoff",
        permissions=ExecutionPermissions(cache_write=True),
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("must not request"),
    )
    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff",
        provider_id="omniroute_api",
        permissions=ExecutionPermissions(),
    )

    assert result["status"] == "skipped"
    assert result["metadata"]["provider_route"]["state"] == "permission_denied"


def test_omniroute_resume_surfaces_rejected_response_without_body(
    monkeypatch, tmp_path
):
    import urllib.error

    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="handoff",
        permissions=ExecutionPermissions(cache_write=True),
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.HTTPError(
                "http://127.0.0.1:20128/v1/chat/completions", 401, "", {}, None
            )
        ),
    )
    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff",
        provider_id="omniroute_api",
        permissions=ExecutionPermissions(network=True),
    )

    assert result["status"] == "error"
    assert result["raw"] is None
    assert result["metadata"]["provider_route"]["state"] == "rejected"


@pytest.mark.parametrize("exception", [OSError("offline"), TimeoutError("slow")])
def test_omniroute_resume_reports_local_transport_unavailable(
    monkeypatch, exception, tmp_path
):
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="handoff",
        permissions=ExecutionPermissions(cache_write=True),
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(exception),
    )

    result = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff",
        provider_id="omniroute_api",
        permissions=ExecutionPermissions(network=True),
    )

    assert result["status"] == "skipped"
    assert result["raw"] is None
    assert result["metadata"]["provider_route"]["state"] == "unavailable"


@pytest.mark.parametrize(
    ("provider_id", "binary", "required_args"),
    [
        (
            "codex_cli",
            "codex",
            ["exec", "--ephemeral", "--json", "--sandbox", "read-only"],
        ),
        (
            "antigravity_cli",
            "agy",
            ["-p", "--output-format", "json", "--sandbox", "--print-timeout", "2m"],
        ),
    ],
)
def test_continuity_provider_resume_uses_verified_cli_contracts(
    provider_id, binary, required_args
):
    from rush.tools.continuity import SessionContinuityTool

    command_binary, command = SessionContinuityTool._provider_command(
        provider_id,
        {"current_goal": "continue", "open_work": [], "freshness": "current"},
    )

    assert command_binary == binary
    for argument in required_args:
        assert argument in command


@pytest.mark.parametrize(
    "provider_id, binary", [("codex_cli", "codex"), ("antigravity_cli", "agy")]
)
def test_direct_cli_resume_has_permission_gated_bounded_process_behavior(
    monkeypatch, provider_id, binary, tmp_path
):
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="handoff",
        handoff={
            "current_goal": "complete the route",
            "open_work": ["run focused verification"],
            "historic_instruction": "never forward this",
        },
        permissions=ExecutionPermissions(cache_write=True),
    )
    calls = []
    monkeypatch.setattr("shutil.which", lambda candidate: f"C:/tools/{candidate}.cmd")
    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **kwargs: (
            calls.append((command, kwargs)) or type("Process", (), {"returncode": 0})()
        ),
    )

    denied = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff",
        provider_id=provider_id,
        permissions=ExecutionPermissions(),
    )
    allowed = SessionContinuityTool().run(
        tmp_path,
        operation="provider_resume",
        name="handoff",
        provider_id=provider_id,
        permissions=ExecutionPermissions(network=True),
    )

    assert denied["status"] == "skipped"
    assert denied["metadata"]["provider_route"]["state"] == "permission_denied"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert binary in str(command)
    assert "never forward this" not in str(command)
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 120
    assert allowed["status"] == "ok"
    assert allowed["raw"] is None
