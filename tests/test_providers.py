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
