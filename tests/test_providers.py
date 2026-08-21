"""Tests for LLM review provider interfaces and registry."""

from __future__ import annotations

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
        "content": [{"type": "text", "text": "Fix the missing return type annotation."}],
    }

    class MockUrlopen:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return io.BytesIO(json.dumps(mock_resp_data).encode("utf-8"))
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", MockUrlopen)
    res = provider.summarize_findings([{"rule": "typecheck", "message": "missing"}], allow_network=True)
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
        "choices": [{"message": {"content": "Resolved security vulnerability in auth."}}],
    }

    class MockUrlopen:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return io.BytesIO(json.dumps(mock_resp_data).encode("utf-8"))
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", MockUrlopen)
    res = provider.summarize_findings([{"rule": "security", "message": "auth"}], allow_network=True)
    assert res is not None
    assert "Resolved security vulnerability" in res.content

