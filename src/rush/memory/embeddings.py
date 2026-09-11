"""MC12 §6.7 configured embedding adapter.

Stdlib-only HTTP client for an Ollama-compatible `/api/embed` endpoint, plus response
validation. There is no bundled embedding model and no implicit download: a caller must
supply an explicit endpoint, model name and model digest (`EmbeddingConfig`); a missing or
unreachable engine raises `EmbeddingEngineUnavailable` so `rush.memory.retrieval` can fall
back to a plainly-labelled lexical result instead of reporting hybrid success.
"""

from __future__ import annotations

import dataclasses
import json
import math
import urllib.error
import urllib.request
from collections.abc import Sequence

_MAX_BATCH = 32
_TIMEOUT_SECONDS = 10.0
_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MiB


class EmbeddingEngineUnavailable(Exception):
    """No reachable embedding engine: connection refused, timed out, or DNS/URL failure.
    Never raised for a response the engine actually returned -- that is
    `EmbeddingResponseError`."""


class EmbeddingResponseError(Exception):
    """A reachable engine returned a response that fails validation: wrong vector count,
    wrong or inconsistent dimension, a non-finite or zero-norm value, or a body that is
    truncated/malformed and does not parse as the expected shape."""


@dataclasses.dataclass(frozen=True)
class EmbeddingConfig:
    """Explicit, per-call embedding engine identity. `model_digest` is the caller-asserted
    exact model identity used as part of the vector cache key -- it is never verified against
    the endpoint (the `/api/embed` contract has no digest field); asserting a wrong digest
    only means the cache never reuses a vector embedded under a different asserted identity,
    never that the wrong model actually ran."""

    endpoint: str
    model: str
    model_digest: str
    chunking_version: str = "mc12-v1"


def embed_chunks(config: EmbeddingConfig, chunks: Sequence[str]) -> list[list[float]]:
    """POSTs `chunks` to `{endpoint}/api/embed` in batches of at most 32, `truncate=false`.
    Returns one validated vector per input chunk, in order. Raises
    `EmbeddingEngineUnavailable` for any connection failure/timeout and
    `EmbeddingResponseError` for a malformed or invalid response."""
    if not chunks:
        return []
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), _MAX_BATCH):
        vectors.extend(_embed_batch(config, list(chunks[start : start + _MAX_BATCH])))
    return vectors


def _embed_batch(config: EmbeddingConfig, batch: list[str]) -> list[list[float]]:
    payload = json.dumps(
        {"model": config.model, "input": batch, "truncate": False}
    ).encode("utf-8")
    request = urllib.request.Request(
        config.endpoint.rstrip("/") + "/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise EmbeddingEngineUnavailable(str(exc)) from exc
    if len(body) > _MAX_RESPONSE_BYTES:
        raise EmbeddingResponseError("embedding response exceeded 1 MiB cap")
    return validate_embedding_response(body, expected_count=len(batch))


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
