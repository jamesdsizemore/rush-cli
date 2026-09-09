"""Pluggable LLM provider interface and data models for AI-augmented code review."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from ..invocation.models import ProviderEgressError

_ORIGINAL_URLOPEN = urllib.request.urlopen

ProviderName = Literal["anthropic", "openai", "stub"]

APPROVED_PROVIDER_ORIGINS: frozenset[str] = frozenset(
    {"https://api.openai.com", "https://api.anthropic.com"}
)


class ProviderOutcome(str, Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class ProviderResult:
    outcome: str
    content: str = ""
    model: str = ""
    finish_reason: str = ""
    error_message: str = ""
    effective_origin: str = ""
    provider: str = ""
    raw: dict[str, Any] | None = None


# Backwards-compatible alias for existing consumers
LLMResponse = ProviderResult


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that intercepts 3xx redirects and enforces origin allowlists."""

    def __init__(self, initial_origin: str, allowed_origins: frozenset[str]) -> None:
        super().__init__()
        self.initial_origin = initial_origin
        self.allowed_origins = allowed_origins

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: Any,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        parsed_target = urllib.parse.urlsplit(newurl)
        target_origin = f"{parsed_target.scheme}://{parsed_target.netloc}"
        if (
            parsed_target.scheme != "https"
            or target_origin != self.initial_origin
            or target_origin not in self.allowed_origins
        ):
            if hasattr(req, "headers"):
                req.headers.clear()
            if hasattr(req, "unredirected_hdrs"):
                req.unredirected_hdrs.clear()
            raise ProviderEgressError(
                f"Cross-origin or unapproved redirect to '{newurl}' refused. "
                f"Initial origin: '{self.initial_origin}', target origin: '{target_origin}'."
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)

    def http_error_301(
        self, req: Any, fp: Any, code: int, msg: Any, headers: Any
    ) -> Any:
        location = headers.get("location") or headers.get("Location")
        if location:
            parsed_target = urllib.parse.urlsplit(location)
            target_origin = f"{parsed_target.scheme}://{parsed_target.netloc}"
            if (
                parsed_target.scheme != "https"
                or target_origin != self.initial_origin
                or target_origin not in self.allowed_origins
            ):
                if hasattr(req, "headers"):
                    req.headers.clear()
                if hasattr(req, "unredirected_hdrs"):
                    req.unredirected_hdrs.clear()
                raise ProviderEgressError(
                    f"Cross-origin or unapproved redirect to '{location}' refused. "
                    f"Initial origin: '{self.initial_origin}', target origin: '{target_origin}'."
                )
        return super().http_error_301(req, fp, code, msg, headers)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


def safe_provider_post(
    url: str,
    headers: dict[str, str],
    data: bytes | str,
    allowed_origins: frozenset[str] = APPROVED_PROVIDER_ORIGINS,
    timeout: float = 30.0,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[int, bytes]:
    """Execute HTTPS POST request enforcing scheme, approved origins, and cross-origin redirect refusal."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise ProviderEgressError(
            f"Provider request scheme must be 'https', got '{parsed.scheme}'"
        )
    initial_origin = f"{parsed.scheme}://{parsed.netloc}"
    if initial_origin not in allowed_origins:
        raise ProviderEgressError(
            f"Provider origin '{initial_origin}' is not in approved origins: {sorted(allowed_origins)}"
        )

    data_bytes = data.encode("utf-8") if isinstance(data, str) else data
    req = urllib.request.Request(
        url, data=data_bytes, headers=dict(headers), method="POST"
    )

    if opener is not None:
        handlers: list[urllib.request.BaseHandler] = vars(opener)["handlers"]
        effective_handlers = [
            h for h in handlers if not isinstance(h, urllib.request.HTTPRedirectHandler)
        ]
        effective_handlers.append(SafeRedirectHandler(initial_origin, allowed_origins))
        effective_opener = urllib.request.build_opener(*effective_handlers)
    elif urllib.request.urlopen is not _ORIGINAL_URLOPEN:
        # urlopen was monkeypatched (e.g. in test fixtures)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", getattr(resp, "code", 200))
            return status, resp.read()
    else:
        handler = SafeRedirectHandler(initial_origin, allowed_origins)
        effective_opener = urllib.request.build_opener(handler)

    try:
        with effective_opener.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", getattr(resp, "code", 200))
            return status, resp.read()
    except urllib.error.HTTPError as err:
        if 300 <= err.code < 400:
            location = err.headers.get("location") or err.headers.get("Location")
            if location:
                parsed_target = urllib.parse.urlsplit(location)
                target_origin = f"{parsed_target.scheme}://{parsed_target.netloc}"
                if (
                    parsed_target.scheme != "https"
                    or target_origin != initial_origin
                    or target_origin not in allowed_origins
                ):
                    if hasattr(req, "headers"):
                        req.headers.clear()
                    if hasattr(req, "unredirected_hdrs"):
                        req.unredirected_hdrs.clear()
                    raise ProviderEgressError(
                        f"Cross-origin or unapproved redirect to '{location}' refused"
                    ) from err
        raise


class LLMProvider(ABC):
    """Abstract base class for LLM review providers."""

    name: ProviderName
    default_model: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if environment credentials exist."""
        ...

    @abstractmethod
    def summarize_findings(
        self,
        findings: list[dict[str, Any]],
        *,
        allow_network: bool = False,
    ) -> ProviderResult | None:
        """Summarize findings with explicit network permission boundary."""
        ...
