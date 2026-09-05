"""Tests for ReviewTool heuristics and provider egress origin verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rush.config import ReviewConfig, RushConfig
from rush.providers.base import (
    ProviderOutcome,
    ProviderResult,
)
from rush.providers.openai import OpenAIProvider
from rush.tools.base import Finding
from rush.tools.review import ReviewTool, _maybe_call_llm


def test_review_heuristics_on_dirty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "dirty_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "dirty"\n', encoding="utf-8"
    )
    (repo / "dirty.py").write_text(
        "# TODO: fix this later\n"
        "CONST_VARIABLE_NAME = 1 + 2\n"
        "def helper():\n"
        "    return 42\n",
        encoding="utf-8",
    )

    tool = ReviewTool()
    result = tool.run(repo)
    assert result["status"] in ("warn", "fail", "ok")
    assert result["tool"] == "review"
    assert result["review_kind"] == "heuristic"
    assert result["review_provider"] is None
    assert len(result["findings"]) > 0


def test_review_heuristics_on_clean_repo(tmp_path: Path) -> None:
    repo = tmp_path / "clean_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "clean"\n', encoding="utf-8"
    )
    (repo / "clean.py").write_text(
        '"""Clean module docstring."""\n\n'
        "def clean_function() -> int:\n"
        '    """Clean function docstring."""\n'
        "    return 42\n",
        encoding="utf-8",
    )

    tool = ReviewTool()
    result = tool.run(repo)
    assert result["status"] == "ok"
    assert result["tool"] == "review"
    assert result["review_kind"] == "heuristic"
    assert result["review_provider"] is None
    assert len(result["findings"]) == 0


def test_review_respects_max_file_lines_config(tmp_path: Path) -> None:
    repo = tmp_path / "size_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "size"\n', encoding="utf-8")
    lines = ["def func(): pass\n"] * 25
    (repo / "long_file.py").write_text("".join(lines), encoding="utf-8")

    cfg = RushConfig(review=ReviewConfig(max_file_lines=20))
    result = ReviewTool().run(repo, config=cfg)
    size_findings = [f for f in result["findings"] if f.get("rule") == "file-size"]
    assert len(size_findings) == 1
    assert "threshold 20" in size_findings[0]["message"]


def test_review_with_llm_approved_origin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "llm_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "llm"\n', encoding="utf-8")
    (repo / "sample.py").write_text("def sample(): pass\n", encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_response = {
        "model": "gpt-4o",
        "choices": [
            {
                "message": {
                    "content": "LLM review: Add docstrings to sample() function."
                },
                "finish_reason": "stop",
            }
        ],
    }

    def mock_safe_post(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
        return 200, json.dumps(mock_response).encode("utf-8")

    monkeypatch.setattr("rush.providers.openai.safe_provider_post", mock_safe_post)

    provider = OpenAIProvider()
    monkeypatch.setattr(
        "rush.providers.registry.get_configured_provider", lambda: provider
    )

    result = ReviewTool().run(repo, use_llm=True)
    assert result["review_kind"] == "llm"
    assert result["review_provider"] == "openai"
    llm_findings = [f for f in result["findings"] if f.get("rule") == "llm-summary"]
    assert len(llm_findings) == 1
    assert "LLM review: Add docstrings" in llm_findings[0]["message"]
    assert "(+LLM)" in result["summary"]


def test_review_with_llm_unapproved_origin_falls_back_to_heuristic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "fallback_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "fallback"\n', encoding="utf-8"
    )
    (repo / "sample.py").write_text("def sample(): pass\n", encoding="utf-8")

    class UnapprovedProvider:
        name = "rogue"
        default_model = "rogue-1"

        def is_configured(self) -> bool:
            return True

        def summarize_findings(
            self, findings: list[dict], *, allow_network: bool = False
        ) -> ProviderResult:
            return ProviderResult(
                outcome=ProviderOutcome.COMPLETED.value,
                content="Rogue completion from unapproved origin",
                model="rogue-1",
                provider="rogue",
                effective_origin="https://unapproved.origin.com",
            )

    provider = UnapprovedProvider()
    monkeypatch.setattr(
        "rush.providers.registry.get_configured_provider", lambda: provider
    )

    # Test _maybe_call_llm directly
    llm_dict = _maybe_call_llm(
        [
            Finding(
                path="sample.py", line=1, rule="rule", severity="warn", message="msg"
            )
        ],
        provider=provider,  # type: ignore[arg-type]
    )
    assert llm_dict is None

    # Test ReviewTool run
    result = ReviewTool().run(repo, use_llm=True)
    assert result["review_kind"] == "heuristic"
    assert result["review_provider"] is None
    assert "(+LLM)" not in result["summary"]


def test_review_with_llm_empty_response_falls_back_to_heuristic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "empty"\n', encoding="utf-8"
    )
    (repo / "sample.py").write_text("def sample(): pass\n", encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_response = {
        "model": "gpt-4o",
        "choices": [{"message": {"content": "   \n\t  "}}],
    }

    def mock_safe_post(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
        return 200, json.dumps(mock_response).encode("utf-8")

    monkeypatch.setattr("rush.providers.openai.safe_provider_post", mock_safe_post)

    result = ReviewTool().run(repo, use_llm=True)
    assert result["review_kind"] == "heuristic"
    assert result["review_provider"] is None
    assert "(+LLM)" not in result["summary"]


def test_review_with_llm_network_disabled_falls_back_to_heuristic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "disabled_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "disabled"\n', encoding="utf-8"
    )
    (repo / "sample.py").write_text("def sample(): pass\n", encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    provider = OpenAIProvider()

    # Calling with allow_network=False
    llm_dict = _maybe_call_llm([], provider=provider, allow_network=False)
    assert llm_dict is None
