"""MC12 §6.7 configured embedding adapter.

Stdlib-only HTTP client for an Ollama-compatible `/api/embed` endpoint, plus response
validation. There is no bundled embedding model and no implicit download: a caller must
supply an explicit endpoint, model name and model digest (`EmbeddingConfig`); a missing or
unreachable engine raises `EmbeddingEngineUnavailable` so `rush.memory.retrieval` can fall
back to a plainly-labelled lexical result instead of reporting hybrid success.

72-T08 (D39, D14a): only `http`/`https` endpoints are contacted, redirects are never
followed, a timeout raises the typed `EmbeddingEngineTimeout`, and `/api/tags` verifies the
implicit-default model identity. The endpoint/model/digest/chunking predicates here are the
single definition the in-process request check, the MCP request models and the
configuration check share.
"""

from __future__ import annotations

import dataclasses
import http.client
import ipaddress
import json
import math
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from typing import Any

MAX_BATCH = 32
_TIMEOUT_SECONDS = 10.0
_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MiB
# Control, format, surrogate and separator code points (U+0000-U+0020 and U+007F among
# them): refused on the raw string, before `urlsplit` strips or rewrites any of them.
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zs", "Zl", "Zp"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_HOST_RE = re.compile(r"[a-z0-9.-]+")
_DIGEST_RE = re.compile(r"[0-9a-f]{12,64}")
_FULL_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class EmbeddingEngineUnavailable(Exception):
    """No reachable embedding engine: connection refused, timed out, redirected, a
    non-http(s) endpoint, or DNS/URL failure. Never raised for a response the engine
    actually returned -- that is `EmbeddingResponseError`."""


class EmbeddingEngineTimeout(EmbeddingEngineUnavailable):
    """The engine did not answer within the client timeout."""


class EmbeddingResponseError(Exception):
    """A reachable engine returned a response that fails validation: wrong vector count,
    wrong or inconsistent dimension, a non-finite or zero-norm value, or a body that is
    truncated/malformed and does not parse as the expected shape."""


@dataclasses.dataclass(frozen=True)
class EmbeddingConfig:
    """Explicit, per-call embedding engine identity. `model_digest` is the caller-asserted
    exact model identity used as part of the vector cache key -- `/api/embed` has no digest
    field, so it is checked against `/api/tags` only for the implicit default (D14a);
    asserting a wrong digest otherwise only means the cache never reuses a vector embedded
    under a different asserted identity, never that the wrong model actually ran."""

    endpoint: str
    model: str
    model_digest: str
    chunking_version: str = "mc12-v1"


def _bad_chars(value: str) -> bool:
    return any(unicodedata.category(char) in _BAD_CATEGORIES for char in value)


def _endpoint_parts(raw: object) -> urllib.parse.SplitResult | None:
    """The checks both endpoint predicates share: a clean string with no userinfo, no
    path beyond `/`, no query or fragment and a port, when present, in 1-65535."""
    if not isinstance(raw, str) or not raw or _bad_chars(raw):
        return None
    try:
        parts = urllib.parse.urlsplit(raw)
        port = parts.port
    except ValueError:
        return None
    if (
        "@" in parts.netloc
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        return None
    return parts


def config_endpoint_ok(raw: object) -> bool:
    """A `rush.toml` (or benchmark manifest) endpoint: loopback `http` with an explicit
    port. Anything else is never contacted."""
    parts = _endpoint_parts(raw)
    return (
        parts is not None
        and parts.scheme == "http"
        and parts.hostname in _LOOPBACK_HOSTS
        and parts.port is not None
    )


def request_endpoint_error(raw: object) -> str | None:
    """`None` for an acceptable explicit request endpoint (any `http`/`https` host the
    caller names under its network grant), else why `embedding_endpoint` is refused."""
    parts = _endpoint_parts(raw)
    if parts is None or parts.scheme not in ("http", "https"):
        return (
            "embedding_endpoint must be an http(s) URL with no credentials, path, "
            "query, fragment or control characters"
        )
    host = parts.hostname
    if not host:
        return "embedding_endpoint must name a host"
    if not _HOST_RE.fullmatch(host):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return "embedding_endpoint host is not a DNS name or IP address"
    return None


def valid_model(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 256
        and "/" not in value
        and ".." not in value
        and not _bad_chars(value)
    )


def valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def valid_chunking(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 64 and not _bad_chars(value)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A 3xx answer is an error (`HTTPError`), never a request to the new location."""

    def redirect_request(  # type: ignore[override]
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _http(url: str, data: bytes | None) -> bytes:
    """One request through a no-redirect opener; returns at most 1 MiB + 1 bytes."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise EmbeddingEngineUnavailable("embedding endpoint must be http or https")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            body: bytes = response.read(_MAX_RESPONSE_BYTES + 1)
    except TimeoutError as exc:
        raise EmbeddingEngineTimeout("embedding engine timed out") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise EmbeddingEngineTimeout("embedding engine timed out") from exc
        raise EmbeddingEngineUnavailable(str(exc)) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise EmbeddingEngineUnavailable(str(exc)) from exc
    return body


def embed_chunks(config: EmbeddingConfig, chunks: Sequence[str]) -> list[list[float]]:
    """POSTs `chunks` to `{endpoint}/api/embed` in batches of at most `MAX_BATCH`,
    `truncate=false`. Returns one validated vector per input chunk, in order. Raises
    `EmbeddingEngineUnavailable` (`EmbeddingEngineTimeout` for a timeout) for any
    connection failure and `EmbeddingResponseError` for a malformed or invalid response."""
    if not chunks:
        return []
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), MAX_BATCH):
        vectors.extend(_embed_batch(config, list(chunks[start : start + MAX_BATCH])))
    return vectors


def _embed_batch(config: EmbeddingConfig, batch: list[str]) -> list[list[float]]:
    payload = json.dumps(
        {"model": config.model, "input": batch, "truncate": False}
    ).encode("utf-8")
    body = _http(config.endpoint.rstrip("/") + "/api/embed", payload)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise EmbeddingResponseError("embedding response exceeded 1 MiB cap")
    return validate_embedding_response(body, expected_count=len(batch))


def fetch_model_tags(endpoint: str) -> Any:
    """GET `{endpoint}/api/tags`, parsed. Raises `EmbeddingEngineUnavailable` /
    `EmbeddingEngineTimeout` like `_embed_batch`, `EmbeddingResponseError` for a body over
    1 MiB or one that is not JSON."""
    body = _http(endpoint.rstrip("/") + "/api/tags", None)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise EmbeddingResponseError("model tags response exceeded 1 MiB cap")
    try:
        return json.loads(body)
    except (TypeError, ValueError, RecursionError) as exc:
        raise EmbeddingResponseError("malformed model tags response") from exc


def model_matches(tags: object, model: str, digest: str) -> bool:
    """Some `/api/tags` entry names `model` (or `model:latest` for an untagged name) with a
    full 64-hex digest that starts with `digest`."""
    if not isinstance(tags, dict) or not isinstance(digest, str):
        return False
    models = tags.get("models")
    if not isinstance(models, list):
        return False
    for entry in models:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        entry_digest = entry.get("digest")
        if not (name == model or (":" not in model and name == f"{model}:latest")):
            continue
        if (
            isinstance(entry_digest, str)
            and _FULL_DIGEST_RE.fullmatch(entry_digest)
            and entry_digest.startswith(digest)
        ):
            return True
    return False


def validate_embedding_response(
    body: bytes, *, expected_count: int, expected_dimension: int | None = None
) -> list[list[float]]:
    """Parses and validates one `/api/embed`-shaped response body: `{"embeddings": [[...]]}`
    with exactly `expected_count` vectors, all sharing one dimension (`expected_dimension`
    when given), every value finite, and no zero-norm vector. Raises `EmbeddingResponseError`
    on any violation, including a truncated/malformed body that fails to parse."""
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise EmbeddingResponseError(f"malformed embedding response: {exc}") from exc
    if not isinstance(parsed, dict) or "embeddings" not in parsed:
        raise EmbeddingResponseError("embedding response missing 'embeddings' field")
    embeddings = parsed["embeddings"]
    if not isinstance(embeddings, list) or len(embeddings) != expected_count:
        got = len(embeddings) if isinstance(embeddings, list) else "non-list"
        raise EmbeddingResponseError(
            f"expected {expected_count} embedding(s), got {got}"
        )

    dimension = expected_dimension
    vectors: list[list[float]] = []
    for vector in embeddings:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingResponseError("embedding vector missing or empty")
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            raise EmbeddingResponseError("inconsistent embedding dimension")
        floats: list[float] = []
        for value in vector:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise EmbeddingResponseError("non-numeric embedding value")
            number = float(value)
            if not math.isfinite(number):
                raise EmbeddingResponseError("non-finite embedding value")
            floats.append(number)
        if math.sqrt(sum(v * v for v in floats)) == 0.0:
            raise EmbeddingResponseError("zero-norm embedding vector")
        vectors.append(floats)
    return vectors
