"""Contract tests for Phase 57 Provider Egress and Effective Origin Verification.

Contracts:
- T-57.23: Denied, redirected, failed, or empty LLM response is not labeled "llm" (falls back to heuristic or error).
- T-57.24: Cross-origin redirects refuse to forward authorization headers or prompt bytes and raise ProviderEgressError fail-closed.
- T-57.25: Approved effective origin schema-valid non-empty completion is labeled "llm" with outcome "completed".
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from rush.providers.anthropic import AnthropicProvider
from rush.providers.base import (
    APPROVED_PROVIDER_ORIGINS,
    ProviderEgressError,
    ProviderOutcome,
    ProviderResult,
    safe_provider_post,
)
from rush.providers.openai import OpenAIProvider
from rush.tools.base import Finding
from rush.tools.review import ReviewTool, _maybe_call_llm

# ---------------------------------------------------------------------------
# T-57.23: test_denied_redirected_failed_or_empty_work_is_not_llm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("failure_mode", "mock_error", "mock_payload"),
    [
        ("empty_string", None, {"choices": [{"message": {"content": ""}}]}),
        ("whitespace_only", None, {"choices": [{"message": {"content": "   \n  "}}]}),
        (
            "http_401",
            urllib.error.HTTPError(
                "https://api.openai.com/v1/chat/completions",
                401,
                "Unauthorized",
                {},  # type: ignore[arg-type]
                None,
            ),
            None,
        ),
        (
            "http_403",
            urllib.error.HTTPError(
                "https://api.openai.com/v1/chat/completions",
                403,
                "Forbidden",
                {},  # type: ignore[arg-type]
                None,
            ),
            None,
        ),
        (
            "http_500",
            urllib.error.HTTPError(
                "https://api.openai.com/v1/chat/completions",
                500,
                "Internal Server Error",
                {},  # type: ignore[arg-type]
                None,
            ),
            None,
        ),
        ("timeout", TimeoutError("Request timed out after 30s"), None),
    ],
)
def test_denied_redirected_failed_or_empty_work_is_not_llm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_mode: str,
    mock_error: Exception | None,
    mock_payload: dict[str, Any] | None,
) -> None:
    """T-57.23: Asserts denied, redirected, failed, or empty LLM work is never labeled 'llm'."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-mock")

    sample_finding = Finding(
        path="src/main.py",
        line=10,
        rule="file-size",
        severity="warn",
        message="file too large",
    )

    if mock_error is not None:

        def failing_post(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
            raise mock_error

        monkeypatch.setattr("rush.providers.openai.safe_provider_post", failing_post)
    elif mock_payload is not None:

        def empty_post(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
            return 200, json.dumps(mock_payload).encode("utf-8")

        monkeypatch.setattr("rush.providers.openai.safe_provider_post", empty_post)

    provider = OpenAIProvider()

    # 1. Provider handler directly
    res = provider.summarize_findings([dict(sample_finding)], allow_network=True)
    assert res is not None
    assert isinstance(res, ProviderResult)
    assert res.outcome != ProviderOutcome.COMPLETED
    assert res.outcome in (ProviderOutcome.ERROR, ProviderOutcome.SKIPPED)

    # 2. _maybe_call_llm must not return review_kind == "llm"
    llm_res = _maybe_call_llm([sample_finding], provider=provider, allow_network=True)
    if llm_res is not None:
        assert llm_res.get("review_kind") != "llm"
    else:
        assert llm_res is None

    # 3. ReviewTool execution must remain heuristic
    test_file = tmp_path / "main.py"
    test_file.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "rush.providers.registry.get_configured_provider", lambda: provider
    )

    tool_result = ReviewTool().run(tmp_path, use_llm=True)
    assert tool_result["review_kind"] == "heuristic"
    assert "llm-summary" not in [f.get("rule") for f in tool_result["findings"]]


def test_permission_denial_network_false_is_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-57.23 (permission denial): Asserts allow_network=False yields SKIPPED outcome and heuristic review."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-mock")
    provider = OpenAIProvider()

    # Direct provider call with allow_network=False
    res = provider.summarize_findings([], allow_network=False)
    assert res is not None
    assert res.outcome == ProviderOutcome.SKIPPED
    assert res.outcome != ProviderOutcome.COMPLETED

    # _maybe_call_llm with allow_network=False
    llm_res = _maybe_call_llm([], provider=provider, allow_network=False)
    assert llm_res is None


# ---------------------------------------------------------------------------
# T-57.24: test_cross_origin_redirect_receives_no_authorization_or_prompt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("redirect_code", [301, 302, 307, 308])
@pytest.mark.parametrize(
    "redirect_target",
    [
        "https://evil.com/leak",
        "https://attacker.io/v1/intercept",
        "http://api.openai.com/v1/insecure",  # Scheme downgrade
    ],
)
def test_cross_origin_redirect_receives_no_authorization_or_prompt(
    redirect_code: int,
    redirect_target: str,
) -> None:
    """T-57.24: Asserts transport refuses redirect, sends zero secrets to target, and raises ProviderEgressError."""
    import io
    import urllib.request

    secret_key = "Bearer sk-proj-super-secret-authorization-token"
    prompt_payload = json.dumps(
        {"prompt": "confidential proprietary source code"}
    ).encode("utf-8")
    headers = {
        "Authorization": secret_key,
        "Content-Type": "application/json",
    }

    requests_made: list[urllib.request.Request] = []

    class MockRedirectHandler(urllib.request.BaseHandler):
        handler_order = 100

        def https_open(self, req: urllib.request.Request) -> Any:
            requests_made.append(req)
            msg = urllib.error.HTTPError(
                req.full_url,
                redirect_code,
                "Redirect",
                {"Location": redirect_target},  # type: ignore[arg-type]
                io.BytesIO(b"redirecting..."),
            )
            raise msg

    test_opener = urllib.request.build_opener(
        MockRedirectHandler(),
    )

    with pytest.raises(ProviderEgressError) as exc_info:
        safe_provider_post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=prompt_payload,
            allowed_origins=APPROVED_PROVIDER_ORIGINS,
            opener=test_opener,
        )

    # Fail-closed validation
    assert "redirect" in str(exc_info.value).lower()

    # Zero bytes or headers reached the redirect target
    for req in requests_made:
        assert req.full_url != redirect_target
        assert "evil.com" not in req.full_url
        assert "attacker.io" not in req.full_url
        if redirect_target in req.full_url:
            pytest.fail(f"Target {redirect_target} received network request!")


def test_safe_provider_post_scheme_and_origin_containment() -> None:
    """T-57.24: Insecure HTTP and non-approved origins fail closed immediately without dispatch."""
    with pytest.raises(ProviderEgressError) as exc_scheme:
        safe_provider_post("http://api.openai.com/v1/test", {}, b"")
    assert "https" in str(exc_scheme.value).lower()

    with pytest.raises(ProviderEgressError) as exc_origin:
        safe_provider_post("https://unapproved.origin.com/v1/test", {}, b"")
    assert (
        "approved" in str(exc_origin.value).lower()
        or "unapproved" in str(exc_origin.value).lower()
    )


# ---------------------------------------------------------------------------
# T-57.25: test_approved_effective_origin_completion_is_llm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider_cls", "env_var", "approved_origin", "valid_response"),
    [
        (
            OpenAIProvider,
            "OPENAI_API_KEY",
            "https://api.openai.com",
            {
                "model": "gpt-4o",
                "choices": [
                    {
                        "message": {
                            "content": "Identified potential buffer overrun in parser."
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        ),
        (
            AnthropicProvider,
            "ANTHROPIC_API_KEY",
            "https://api.anthropic.com",
            {
                "model": "claude-3-5-sonnet-20241022",
                "content": [
                    {
                        "type": "text",
                        "text": "Refactor nested loop to improve asymptotic complexity.",
                    }
                ],
                "stop_reason": "end_turn",
            },
        ),
    ],
)
def test_approved_effective_origin_completion_is_llm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider_cls: type[OpenAIProvider | AnthropicProvider],
    env_var: str,
    approved_origin: str,
    valid_response: dict[str, Any],
) -> None:
    """T-57.25: Asserts schema-valid non-empty completion from approved HTTPS origin produces review_kind='llm'."""
    monkeypatch.setenv(env_var, "test-approved-key")

    def mock_safe_post(
        url: str, headers: dict[str, str], data: bytes | str, **kwargs: Any
    ) -> tuple[int, bytes]:
        assert any(url.startswith(origin) for origin in APPROVED_PROVIDER_ORIGINS)
        return 200, json.dumps(valid_response).encode("utf-8")

    monkeypatch.setattr("rush.providers.openai.safe_provider_post", mock_safe_post)
    monkeypatch.setattr("rush.providers.anthropic.safe_provider_post", mock_safe_post)

    provider = provider_cls()
    sample_finding = Finding(
        path="src/lib.py",
        line=42,
        rule="missing-docstrings",
        severity="info",
        message="missing docstring",
    )

    # 1. Provider outcome
    res = provider.summarize_findings([dict(sample_finding)], allow_network=True)
    assert res is not None
    assert isinstance(res, ProviderResult)
    assert res.outcome == ProviderOutcome.COMPLETED
    assert res.effective_origin == approved_origin
    assert res.effective_origin in APPROVED_PROVIDER_ORIGINS
    assert len(res.content.strip()) > 0

    # 2. _maybe_call_llm returns review_kind == "llm"
    llm_dict = _maybe_call_llm([sample_finding], provider=provider, allow_network=True)
    assert llm_dict is not None
    assert llm_dict.get("review_kind") == "llm"
    assert llm_dict.get("outcome") == "completed"
    assert len(str(llm_dict.get("summary", "")).strip()) > 0

    # 3. ReviewTool sets review_kind == "llm"
    test_file = tmp_path / "lib.py"
    test_file.write_text("def run():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(
        "rush.providers.registry.get_configured_provider", lambda: provider
    )

    tool_result = ReviewTool().run(tmp_path, use_llm=True)
    assert tool_result["review_kind"] == "llm"
    assert tool_result["review_provider"] == provider.name
    llm_findings = [
        f for f in tool_result["findings"] if f.get("rule") == "llm-summary"
    ]
    assert len(llm_findings) == 1
    assert (
        "Identified" in llm_findings[0]["message"]
        or "Refactor" in llm_findings[0]["message"]
    )
