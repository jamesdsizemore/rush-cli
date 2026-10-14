"""72-T08: optional hybrid retrieval, honest fallback and the paired evaluation.

Every test imports a symbol that an earlier or this task adds (`retrieval.HYBRID_DEFAULT_VERDICT`,
`embeddings.fetch_model_tags`, `reporting.aggregate_hybrid_verdict`, ...) inside its own body, so the
module always collects and each test fails on its own until its producer lands. The module-level
imports below are code that exists today.

Fixture F8 (brief section 1): project P is a git repo under `tmp_path`, registered; grant A owns
`user:alice`, sources `["s1"]`, operations `ask, list, expand`; rows `h1` (`needle alpha`), `h2`
(`needle beta`) and `h3` (no `needle`, embedding-near the query) are written through
`TypedArtifactStore(P).write` with source `s1`. `rush.memory.embeddings._embed_batch` is replaced by a
deterministic vector function with a call spy; `rush.memory.embeddings.fetch_model_tags` by a stub.
`HOME`, `XDG_DATA_HOME` and `LOCALAPPDATA` are redirected into `tmp_path` by the autouse
`_isolated_home` fixture of `tests/conftest.py`.

The verdict-row contract these tests pin (rows handed to `reporting.aggregate_hybrid_verdict`) is
documented at `_verdict_row`.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import http.server
import importlib
import json
import os
import shutil
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pytest

from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.tools.memory import MemoryOperation, MemoryTool, _family_for_subject
from rush.workflows.projects import register_project

SUBJECT: Final = "domain_knowledge"
ALICE = OwnerScope("user", "alice")
BOB = OwnerScope("user", "bob")
READER = OwnerScope("user", "p72-reader")
DAY = 86400.0
ENDPOINT = "http://127.0.0.1:11434"
MODEL = "nomic-embed-text"
DIGEST = "0123456789ab"
FULL_DIGEST = DIGEST + "0" * 52
CHUNKING = "mc12-v1"
MAX_EMBEDDED_TEXTS = (
    2 * 512 + 1
)  # retrieval._MAX_EMBEDDED_TEXTS (2 * _VECTOR_SCAN_CAP + 1)
VERDICT = {
    "verdict": "benefit",
    "model": MODEL,
    "model_digest": DIGEST,
    "cases_sha256": "0" * 64,
    "verdict_report_sha256": "1" * 64,
}
# Brief section 3.1 FALLBACK_REASONS: the fixed `hybrid_unavailable_reason` text per code.
FALLBACK_TEXT = {
    "cursor_continuation": "hybrid retrieval has no cursor; this page continues lexically",
    "empty_query": "hybrid retrieval needs a non-empty query",
    "network_not_granted": "hybrid retrieval needs the network permission",
    "config_invalid": "rush.toml could not be loaded",
    "no_engine_configured": "no embedding engine configured",
    "endpoint_not_loopback": "configured embedding endpoint is not loopback http",
    "model_digest_mismatch": "embedding model or digest does not match",
    "engine_unreachable": "embedding engine unreachable",
    "engine_timeout": "embedding engine timed out",
    "invalid_vectors": "embedding engine returned invalid vectors",
}
LABEL_KEYS = (
    "retrieval",
    "embedding_status",
    "embedding_fallback_code",
    "hybrid_unavailable_reason",
    "embedded_texts",
    "candidates_truncated",
    "incomplete_reason",
)


def embedding_text_of(content: dict[str, Any]) -> str:
    """`retrieval.embedding_text`: sorted-key JSON; an independent copy so a changed
    production text rule is caught here."""
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- frozen corpus and queries (plan 72-T08, transcribed from the plan tables) -----
# (id, role, source, owner id, symbol_ref, text); subject/trust_tier/owner kind are fixed.
FROZEN_CORPUS: tuple[tuple[str, str, str, str, str | None, str], ...] = (
    (
        "p72-a-L01",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The invoice retry limit is 7 attempts before the job is parked.",
    ),
    (
        "p72-a-L02",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The session cookie name is rush_sid_v2 for the dashboard.",
    ),
    (
        "p72-a-L03",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The nightly backup window starts at 02:15 UTC.",
    ),
    (
        "p72-a-L04",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The webhook signing header is X-Ledger-Signature.",
    ),
    (
        "p72-a-L05",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The export batch size is 750 rows per request.",
    ),
    (
        "p72-a-L06",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The staging database host is pg-stage-3.internal.",
    ),
    (
        "p72-a-L07",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The audit log retention is 400 days.",
    ),
    (
        "p72-a-L08",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The feature flag for bulk refunds is bulk_refund_v3.",
    ),
    (
        "p72-a-L09",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The release branch prefix is ship/ for hotfix builds.",
    ),
    (
        "p72-a-L10",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The rate limiter bucket size is 120 requests per minute.",
    ),
    (
        "p72-a-L11",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The search index alias is orders_live_b.",
    ),
    (
        "p72-a-L12",
        "literal_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The worker queue name is ledger-settlements.",
    ),
    (
        "p72-a-P01",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Customers can cancel a subscription without a fee during the first 21 days.",
    ),
    (
        "p72-a-P02",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Password reset links expire after 35 minutes.",
    ),
    (
        "p72-a-P03",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Uploaded avatars are resized to 256 pixels square.",
    ),
    (
        "p72-a-P04",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "The on-call engineer is paged after 3 consecutive health check failures.",
    ),
    (
        "p72-a-P05",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Deleted projects stay recoverable in the trash for 9 days.",
    ),
    (
        "p72-a-P06",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "API keys are rotated every 90 days by the security team.",
    ),
    (
        "p72-a-P07",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Invoices are emailed to customers on the 3rd business day of each month.",
    ),
    (
        "p72-a-P08",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Free plan accounts may store at most 2 GB of attachments.",
    ),
    (
        "p72-a-P09",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Mobile builds are signed with the certificate named kestrel-ios-dist.",
    ),
    (
        "p72-a-P10",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Support tickets marked urgent must get a first reply within 45 minutes.",
    ),
    (
        "p72-a-P11",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Translations are synced from the vendor portal every Tuesday.",
    ),
    (
        "p72-a-P12",
        "paraphrase_positive",
        "p72-notes",
        "p72-reader",
        None,
        "Load tests run against a copy of production scaled to 40 percent.",
    ),
    (
        "p72-a-N01",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The invoice retry limit was debated in the March planning review without a decision.",
    ),
    (
        "p72-a-N02",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The session cookie name appears in the browser privacy notice draft.",
    ),
    (
        "p72-a-N03",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The nightly backup window is listed on the infrastructure wiki homepage.",
    ),
    (
        "p72-a-N04",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The webhook signing header was mentioned in a partner onboarding call.",
    ),
    (
        "p72-a-N05",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The export batch size question came up during the analytics sync.",
    ),
    (
        "p72-a-N06",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The staging database host is documented in the old runbook archive.",
    ),
    (
        "p72-a-N07",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The audit log retention topic belongs to the compliance working group.",
    ),
    (
        "p72-a-N08",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The feature flag for bulk refunds is owned by the payments squad.",
    ),
    (
        "p72-a-N09",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The release branch prefix convention was proposed in an architecture note.",
    ),
    (
        "p72-a-N10",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The rate limiter bucket size dashboard lives in the observability folder.",
    ),
    (
        "p72-a-N11",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The search index alias rename is tracked in the platform backlog.",
    ),
    (
        "p72-a-N12",
        "near_neighbor",
        "p72-notes",
        "p72-reader",
        None,
        "The worker queue name collision was reported by the platform team.",
    ),
    (
        "p72-a-D01",
        "denied_owner",
        "p72-notes",
        "p72-other",
        None,
        "The invoice retry limit is 2 attempts in the archived billing fork.",
    ),
    (
        "p72-a-D02",
        "denied_owner",
        "p72-notes",
        "p72-other",
        None,
        "The session cookie name is legacy_sid for the old admin portal.",
    ),
    (
        "p72-a-D03",
        "denied_owner",
        "p72-notes",
        "p72-other",
        None,
        "The nightly backup window starts at 23:40 UTC on the retired cluster.",
    ),
    (
        "p72-a-D04",
        "denied_owner",
        "p72-notes",
        "p72-other",
        None,
        "The webhook signing header is X-Old-Signature in the deprecated API.",
    ),
    (
        "p72-a-R01",
        "revoked_source",
        "p72-revoked",
        "p72-reader",
        None,
        "Customers can cancel a subscription without a fee during the first 5 days.",
    ),
    (
        "p72-a-R02",
        "revoked_source",
        "p72-revoked",
        "p72-reader",
        None,
        "Password reset links expire after 4 hours.",
    ),
    (
        "p72-a-R03",
        "revoked_source",
        "p72-revoked",
        "p72-reader",
        None,
        "Uploaded avatars are resized to 64 pixels square.",
    ),
    (
        "p72-a-R04",
        "revoked_source",
        "p72-revoked",
        "p72-reader",
        None,
        "The on-call engineer is paged after 10 consecutive health check failures.",
    ),
    (
        "p72-a-S01",
        "stale_hash",
        "p72-anchored",
        "p72-reader",
        "src/p72_settings.py::",
        "The export batch size is 300 rows per request.",
    ),
    (
        "p72-a-S02",
        "stale_hash",
        "p72-anchored",
        "p72-reader",
        "src/p72_settings.py::",
        "The staging database host is pg-stage-1.internal.",
    ),
    (
        "p72-a-S03",
        "stale_hash",
        "p72-anchored",
        "p72-reader",
        "src/p72_settings.py::",
        "Deleted projects stay recoverable in the trash for 30 days.",
    ),
    (
        "p72-a-S04",
        "stale_hash",
        "p72-anchored",
        "p72-reader",
        "src/p72_settings.py::",
        "API keys are rotated every 365 days by the security team.",
    ),
)

# (question_id, split, query, question, answer, relevant id)
FROZEN_QUERIES: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "p72-q01",
        "literal",
        "invoice retry limit",
        "What is the invoice retry limit?",
        "7 attempts",
        "p72-a-L01",
    ),
    (
        "p72-q02",
        "literal",
        "session cookie name",
        "What is the session cookie name?",
        "rush_sid_v2",
        "p72-a-L02",
    ),
    (
        "p72-q03",
        "literal",
        "nightly backup window",
        "When does the nightly backup window start?",
        "02:15 UTC",
        "p72-a-L03",
    ),
    (
        "p72-q04",
        "literal",
        "webhook signing header",
        "What is the webhook signing header?",
        "X-Ledger-Signature",
        "p72-a-L04",
    ),
    (
        "p72-q05",
        "literal",
        "export batch size",
        "What is the export batch size?",
        "750 rows",
        "p72-a-L05",
    ),
    (
        "p72-q06",
        "literal",
        "staging database host",
        "What is the staging database host?",
        "pg-stage-3.internal",
        "p72-a-L06",
    ),
    (
        "p72-q07",
        "literal",
        "audit log retention",
        "What is the audit log retention?",
        "400 days",
        "p72-a-L07",
    ),
    (
        "p72-q08",
        "literal",
        "feature flag for bulk refunds",
        "What is the feature flag for bulk refunds?",
        "bulk_refund_v3",
        "p72-a-L08",
    ),
    (
        "p72-q09",
        "literal",
        "release branch prefix",
        "What is the release branch prefix?",
        "ship/",
        "p72-a-L09",
    ),
    (
        "p72-q10",
        "literal",
        "rate limiter bucket size",
        "What is the rate limiter bucket size?",
        "120 requests",
        "p72-a-L10",
    ),
    (
        "p72-q11",
        "literal",
        "search index alias",
        "What is the search index alias?",
        "orders_live_b",
        "p72-a-L11",
    ),
    (
        "p72-q12",
        "literal",
        "worker queue name",
        "What is the worker queue name?",
        "ledger-settlements",
        "p72-a-L12",
    ),
    (
        "p72-q13",
        "paraphrase",
        "how long is the free cancellation period",
        "How long is the free cancellation period?",
        "21 days",
        "p72-a-P01",
    ),
    (
        "p72-q14",
        "paraphrase",
        "how long until a credential recovery email stops working",
        "How long until a credential recovery email stops working?",
        "35 minutes",
        "p72-a-P02",
    ),
    (
        "p72-q15",
        "paraphrase",
        "what dimensions are profile pictures scaled to",
        "What dimensions are profile pictures scaled to?",
        "256 pixels",
        "p72-a-P03",
    ),
    (
        "p72-q16",
        "paraphrase",
        "when does someone get woken up by monitoring alerts",
        "When does someone get woken up by monitoring alerts?",
        "3 consecutive",
        "p72-a-P04",
    ),
    (
        "p72-q17",
        "paraphrase",
        "grace period before a removed workspace is gone for good",
        "Grace period before a removed workspace is gone for good?",
        "9 days",
        "p72-a-P05",
    ),
    (
        "p72-q18",
        "paraphrase",
        "how often are service credentials replaced",
        "How often are service credentials replaced?",
        "90 days",
        "p72-a-P06",
    ),
    (
        "p72-q19",
        "paraphrase",
        "when do clients receive their monthly bills",
        "When do clients receive their monthly bills?",
        "3rd business day",
        "p72-a-P07",
    ),
    (
        "p72-q20",
        "paraphrase",
        "storage quota on the no-cost tier",
        "Storage quota on the no-cost tier?",
        "2 GB",
        "p72-a-P08",
    ),
    (
        "p72-q21",
        "paraphrase",
        "which signing identity do phone app releases use",
        "Which signing identity do phone app releases use?",
        "kestrel-ios-dist",
        "p72-a-P09",
    ),
    (
        "p72-q22",
        "paraphrase",
        "response time target for high priority customer requests",
        "Response time target for high priority customer requests?",
        "45 minutes",
        "p72-a-P10",
    ),
    (
        "p72-q23",
        "paraphrase",
        "what weekday do localized strings get imported",
        "What weekday do localized strings get imported?",
        "Tuesday",
        "p72-a-P11",
    ),
    (
        "p72-q24",
        "paraphrase",
        "how big is the performance testing environment relative to live",
        "How big is the performance testing environment relative to live?",
        "40 percent",
        "p72-a-P12",
    ),
)

# --- helpers (existing code and stdlib only) ---------------------------------------------

_F8_VECTORS: dict[str, list[float]] = {
    "needle": [1.0, 0.0, 0.0, 0.0],
    embedding_text_of({"text": "needle alpha"}): [1.0, 0.0, 0.0, 0.0],
    embedding_text_of({"text": "needle beta"}): [0.5, 0.866, 0.0, 0.0],
    embedding_text_of({"text": "similar idea without the keyword"}): [
        0.99,
        0.14,
        0.0,
        0.0,
    ],
}


def f8_vectors(batch: Sequence[str]) -> list[list[float]]:
    """Deterministic vectors: `h1` is nearest the query `needle`, then `h3`, then `h2`; any
    other text is orthogonal to the query."""
    return [list(_F8_VECTORS.get(text, [0.0, 0.0, 1.0, 0.0])) for text in batch]


def tags_payload(model: str = MODEL, digest: str = FULL_DIGEST) -> dict[str, Any]:
    return {"models": [{"name": f"{model}:latest", "digest": digest}]}


@dataclasses.dataclass
class Env:
    root: Path
    data_root: Path
    auth: Any
    owner: OwnerScope
    grant: dict[str, Any] | None
    store: TypedArtifactStore | None
    embed_calls: list[list[str]] = dataclasses.field(default_factory=list)
    embed_configs: list[Any] = dataclasses.field(default_factory=list)
    tags_calls: list[str] = dataclasses.field(default_factory=list)
    urlopen_calls: list[str] = dataclasses.field(default_factory=list)
    vector_fn: Callable[[Sequence[str]], list[list[float]]] = f8_vectors
    engine_error: Exception | None = None
    tags: Any = dataclasses.field(default_factory=tags_payload)
    tags_error: Exception | None = None
    on_embed: Callable[[int, list[str]], None] | None = None

    @property
    def embedded(self) -> list[str]:
        return [text for batch in self.embed_calls for text in batch]


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            *args,
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def git_project(path: Path, files: dict[str, str] | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for rel, text in (files or {}).items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(path, "init", "-q", "--initial-branch=main")
    if files:
        _git(path, "add", "-A")
        _git(path, "commit", "-q", "-m", "fixture")
    return path


def revision(auth: Any, data_root: Path) -> int:
    return int(auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0)


def grant_scope(
    auth: Any,
    root: Path,
    owner: OwnerScope,
    data_root: Path,
    *,
    sources: Sequence[str] = ("s1",),
    ops: Sequence[str] = ("ask", "list", "expand"),
) -> dict[str, Any]:
    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )


def revoke_scope(auth: Any, data_root: Path, grant: dict[str, Any]) -> None:
    auth.revoke_memory_scope(
        grant_id=grant["grant_id"],
        expected_policy_revision=revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )


def write_row(
    store: TypedArtifactStore,
    artifact_id: str,
    text: str,
    *,
    source: str = "s1",
    owner: OwnerScope = ALICE,
    trust: str = "DERIVED",
    created_at: float | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
    content: dict[str, Any] | None = None,
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject=SUBJECT,  # type: ignore[arg-type]
            trust_tier=trust,  # type: ignore[arg-type]
            content=content if content is not None else {"text": text},
            source=source,
            created_at=created_at if created_at is not None else time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
            owner_scope=owner,
        )
    )


F8_ROWS = (
    ("h1", "needle alpha"),
    ("h2", "needle beta"),
    ("h3", "similar idea without the keyword"),
)


def make_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    ops: Sequence[str] = ("ask", "list", "expand"),
    sources: Sequence[str] = ("s1",),
    owner: OwnerScope = ALICE,
    rows: Sequence[tuple[str, str]] | None = F8_ROWS,
    policy: bool = True,
    store: bool = True,
    name: str = "project",
    patch_engine: bool = True,
) -> Env:
    """Fixture F8. `rows=None` writes none; `store=False` leaves no `.rush/memory.db`;
    `patch_engine=False` leaves the real embedding client for a loopback `StubEngine`."""
    import rush.memory.embeddings as emb
    from rush.memory import authorization as auth

    data_root = default_data_root()
    root = git_project(tmp_path / name)
    register_project(root, data_root=data_root)
    root = root.resolve()
    opened: TypedArtifactStore | None = None
    if store:
        opened = TypedArtifactStore(root)
        for artifact_id, text in rows or ():
            write_row(opened, artifact_id, text, owner=owner)
    grant = (
        grant_scope(auth, root, owner, data_root, sources=sources, ops=ops)
        if policy
        else None
    )
    env = Env(
        root=root,
        data_root=data_root,
        auth=auth,
        owner=owner,
        grant=grant,
        store=opened,
    )

    def fake_batch(config: Any, batch: list[str]) -> list[list[float]]:
        env.embed_calls.append(list(batch))
        env.embed_configs.append(config)
        if env.on_embed is not None:
            env.on_embed(len(env.embed_calls), list(batch))
        if env.engine_error is not None:
            raise env.engine_error
        return env.vector_fn(batch)

    def fake_tags(endpoint: str, *args: Any, **kwargs: Any) -> Any:
        env.tags_calls.append(endpoint)
        if env.tags_error is not None:
            raise env.tags_error
        return env.tags

    def blocked(*args: Any, **kwargs: Any) -> Any:
        env.urlopen_calls.append(repr(args[:1]))
        raise urllib.error.URLError("network blocked in tests")

    if patch_engine:
        monkeypatch.setattr(emb, "_embed_batch", fake_batch)
        monkeypatch.setattr(emb, "fetch_model_tags", fake_tags, raising=False)
        monkeypatch.setattr(urllib.request, "urlopen", blocked)
        monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    return env


def install_verdict(
    monkeypatch: pytest.MonkeyPatch, verdict: dict[str, Any] | None = None
) -> None:
    from rush.memory import retrieval

    monkeypatch.setattr(
        retrieval,
        "HYBRID_DEFAULT_VERDICT",
        dict(VERDICT) if verdict is None else verdict,
        raising=False,
    )


def write_config(
    root: Path,
    *,
    endpoint: str | None = ENDPOINT,
    model: str | None = MODEL,
    digest: str | None = DIGEST,
    raw: str | None = None,
) -> Path:
    if raw is None:
        lines = ["[tools.memory]"]
        if endpoint is not None:
            lines.append(f"embedding_endpoint = {json.dumps(endpoint)}")
        if model is not None:
            lines.append(f"embedding_model = {json.dumps(model)}")
        if digest is not None:
            lines.append(f"embedding_model_digest = {json.dumps(digest)}")
        raw = "\n".join(lines) + "\n"
    path = root / "rush.toml"
    path.write_text(raw, encoding="utf-8")
    return path


def hy(**over: Any) -> dict[str, Any]:
    """An explicit hybrid compact request carrying valid embedding fields; a key given as
    `None` is removed."""
    request: dict[str, Any] = {
        "view": "compact",
        "retrieval": "hybrid",
        "embedding_endpoint": ENDPOINT,
        "embedding_model": MODEL,
        "embedding_model_digest": DIGEST,
    }
    for key, value in over.items():
        if value is None:
            request.pop(key, None)
        else:
            request[key] = value
    return request


def lex(**over: Any) -> dict[str, Any]:
    request: dict[str, Any] = {"view": "compact"}
    request.update(over)
    return request


@dataclasses.dataclass
class Out:
    result: Any
    raw: dict[str, Any]
    code: Any
    status: Any
    data: dict[str, Any]
    ids: list[str]

    @property
    def reason(self) -> Any:
        return self.raw.get("reason") or self.data.get("reason")


def out_of(result: Any) -> Out:
    raw = result.get("raw") if hasattr(result, "get") else None
    raw = raw if isinstance(raw, dict) else {}
    data = cast(
        dict[str, Any], raw.get("data") if isinstance(raw.get("data"), dict) else {}
    )
    items = data.get("items") or []
    return Out(
        result=result,
        raw=raw,
        code=raw.get("code"),
        status=result.get("status") if hasattr(result, "get") else None,
        data=data,
        ids=[i["id"] for i in items if isinstance(i, dict) and "id" in i],
    )


_MCP_SERVER: Any = None


def mcp_call(arguments: dict[str, Any]) -> Any:
    """One real `rush_memory` `tools/call` through the FastMCP server object (strict request
    models, then the executor wrapper) -- the in-process MCP transport."""
    global _MCP_SERVER
    if _MCP_SERVER is None:
        from rush.mcp import build_server

        _MCP_SERVER = build_server()
    response = asyncio.run(_MCP_SERVER.call_tool("rush_memory", arguments))
    structured = getattr(response, "structuredContent", None)
    if structured is None:
        structured = json.loads(response.content[0].text)
    return structured


def tool_call(
    env: Env,
    op: str,
    *,
    transport: str = "inproc",
    query: str = "needle",
    request: dict[str, Any] | None = None,
    network: bool = True,
    cache_write: bool = False,
    allowlist: list[str] | None = None,
    owner: OwnerScope | None | str = "env",
    extra: dict[str, Any] | None = None,
    root: Path | None = None,
) -> Out:
    owner_scope = cast("OwnerScope | None", env.owner if owner == "env" else owner)
    where = root if root is not None else env.root
    if transport == "inproc":
        kwargs: dict[str, Any] = {
            "operation": op,
            "subject": SUBJECT,
            "query": query,
            "owner_scope": owner_scope.as_dict() if owner_scope is not None else None,
            "session_allowlist": allowlist,
            "request": request,
            "permissions": ExecutionPermissions(
                network=network, cache_write=cache_write
            ),
        }
        kwargs.update(extra or {})
        return out_of(MemoryTool().run(where, **kwargs))
    if transport == "mcp":
        args: dict[str, Any] = {
            "path": str(where),
            "operation": op,
            "subject": SUBJECT,
            "query": query,
            "request": request,
            "allow_network": network,
            "allow_cache_write": cache_write,
        }
        if owner_scope is not None:
            args["owner_scope"] = owner_scope.as_dict()
        if allowlist is not None:
            args["session_allowlist"] = allowlist
        args.update(extra or {})
        return out_of(mcp_call(args))
    raise AssertionError(f"unknown transport {transport!r}")


def digest_tree(base: Path, skip: Sequence[str] = ()) -> dict[str, str]:
    out: dict[str, str] = {}
    if not base.exists():
        return out
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base).as_posix()
        if (
            rel == ".git"
            or rel.startswith(".git/")
            or any(rel.startswith(s) for s in skip)
        ):
            continue
        if path.is_file() and not path.is_symlink():
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            out[rel] = "<dir>" if path.is_dir() else "<link>"
    return out


def effects(env: Env) -> dict[str, dict[str, str]]:
    """Everything a no-write route must leave unchanged: the project tree (git internals
    excluded) and the data root (the lock directory excluded)."""
    return {
        "root": digest_tree(env.root),
        "data": digest_tree(env.data_root, skip=("dashboard/project_locks",)),
    }


def embedding_rows(root: Path) -> list[tuple[Any, ...]]:
    db = root / ".rush" / "memory.db"
    if not db.exists():
        return []
    # immutable=1 keeps a read from creating -shm/-wal sidecars; it is unsafe only when a
    # non-empty WAL holds uncheckpointed rows, so open plain read-only in that case.
    wal = Path(f"{db}-wal")
    flags = "mode=ro" if wal.exists() and wal.stat().st_size else "mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(f"file:{db}?{flags}", uri=True)) as conn:
        try:
            return [
                tuple(r)
                for r in conn.execute(
                    "SELECT artifact_id, artifact_version, content_hash, model_digest, "
                    "chunking_version FROM memory_embeddings ORDER BY artifact_id, "
                    "artifact_version"
                )
            ]
        except sqlite3.OperationalError:
            return []


def tamper(root: Path, artifact_id: str) -> None:
    """Rewrite one row's persisted payload behind the store's back (valid JSON)."""
    db = root / ".rush" / "memory.db"
    with contextlib.closing(sqlite3.connect(db)) as conn:
        (raw,) = conn.execute(
            "SELECT content FROM memory_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        content = json.loads(raw)
        content["tampered"] = True
        text = json.dumps(content)
        version = conn.execute(
            "SELECT artifact_version FROM memory_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = ?", (text, artifact_id)
        )
        conn.execute(
            "UPDATE memory_artifact_versions SET content = ? "
            "WHERE artifact_id = ? AND artifact_version = ?",
            (text, artifact_id, version),
        )
        conn.commit()


def stamp_expiry(root: Path, artifact_id: str, *, at: float | None = None) -> None:
    db = root / ".rush" / "memory.db"
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET expires_at = ? WHERE id = ?",
            (time.time() - 10.0 if at is None else at, artifact_id),
        )
        conn.commit()


def drop_payload_columns(db: Path) -> None:
    """An older store: both payload-hash columns removed from both tables (reads then
    report the migration state)."""
    with contextlib.closing(sqlite3.connect(db)) as conn:
        for table in ("memory_artifacts", "memory_artifact_versions"):
            for column in ("payload_hash", "payload_hash_origin"):
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()


# Schema additions of the earlier tasks whose migrations a read must never run (decisions.md,
# 72-T02): `writable_open_ddl_free` covers them through one shared declaration, so a store
# missing only one task's additions is read through its read-only view and never migrated.
SCHEMA_ADDITIONS: dict[str, dict[str, Any]] = {
    "72-T05": {
        "columns": {
            "memory_artifacts": (
                "applicability",
                "task_project_id",
                "task_worktree_id",
                "task_id",
            ),
            "memory_artifact_versions": (
                "applicability",
                "task_project_id",
                "task_worktree_id",
                "task_id",
                "binding_recorded",
            ),
            "memory_handoff_sessions": ("sender_task_id",),
        },
        "indexes": (),
    },
    "72-T06": {
        "columns": {
            "mutation_receipts": ("invocation_id", "effect_id", "request_digest"),
        },
        "indexes": ("idx_mutation_receipts_v2",),
    },
}


def drop_schema_additions(db: Path, task: str) -> list[str]:
    """Remove the `task`'s schema additions from an existing store; returns what was
    present and removed (empty when that task's code is not in this tree yet)."""
    spec = SCHEMA_ADDITIONS[task]
    dropped: list[str] = []
    with contextlib.closing(sqlite3.connect(db)) as conn:
        for index in spec["indexes"]:
            conn.execute(f"DROP INDEX IF EXISTS {index}")
        for table, columns in spec["columns"].items():
            present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column in columns:
                if column in present:
                    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
                    dropped.append(f"{table}.{column}")
        conn.commit()
    return dropped


def label_extra(data: dict[str, Any]) -> dict[str, Any]:
    """Every page key that is not one of the four base keys or a size: the labels (and
    `required`) a measured size must include."""
    base = {"code", "items", "next_cursor", "complete", "encoding", "tokens", "bytes"}
    return {k: v for k, v in data.items() if k not in base}


def measured(data: dict[str, Any]) -> tuple[int, int]:
    """The size of the `data` payload the way `retrieval._measure_page` measures it, with
    every label the page carries counted."""
    from rush.memory.retrieval import _measure_page

    return _measure_page(
        data["items"],
        data["next_cursor"],
        data["complete"],
        data["encoding"],
        label_extra(data) or None,
    )


class StubEngine:
    """A loopback Ollama-shaped server: `/api/embed` returns `vector_fn` vectors, `/api/tags`
    a configurable body. Every request is recorded."""

    def __init__(
        self,
        vector_fn: Callable[[Sequence[str]], list[list[float]]] = f8_vectors,
        *,
        tags_mode: str = "normal",
        embed_mode: str = "normal",
    ) -> None:
        self.requests: list[tuple[str, str]] = []
        self.vector_fn = vector_fn
        self.tags_mode = tags_mode
        self.embed_mode = embed_mode
        engine = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                return

            def _send(
                self, status: int, body: bytes, headers: dict[str, str] | None = None
            ) -> None:
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                engine.requests.append(("GET", self.path))
                if engine.tags_mode == "redirect":
                    self._send(302, b"", {"Location": "http://10.255.255.1/"})
                elif engine.tags_mode == "oversize":
                    self._send(200, b"{" + b" " * (2 * 1024 * 1024) + b"}")
                elif engine.tags_mode == "non_json":
                    self._send(200, b"not json at all")
                elif engine.tags_mode == "no_models":
                    self._send(200, b'{"other": []}')
                else:
                    self._send(200, json.dumps(tags_payload()).encode())

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                engine.requests.append(("POST", self.path))
                if engine.embed_mode == "redirect":
                    self._send(302, b"", {"Location": "http://10.255.255.1/"})
                    return
                vectors = engine.vector_fn(body.get("input", []))
                self._send(200, json.dumps({"embeddings": vectors}).encode())

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self._server = Server(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def stub_engine() -> Iterator[Callable[..., StubEngine]]:
    made: list[StubEngine] = []

    def make(*args: Any, **kwargs: Any) -> StubEngine:
        engine = StubEngine(*args, **kwargs)
        made.append(engine)
        return engine

    try:
        yield make
    finally:
        for engine in made:
            engine.close()


SECURITY_ROLES = frozenset({"denied_owner", "revoked_source", "stale_hash"})
SETTINGS_REL = "src/p72_settings.py"
QUERY_REQUEST = {"view": "compact", "limit": 8, "max_tokens": 2048, "max_bytes": 8192}
PHASE72_FIXTURE_REVISION = (
    "6639c7806c3a5180621074c5746491e52833aa241578a9e1f16c78729c5938ed"
)
CORPUS_SHA256 = "9cef78f698caa7a8e12af1de416c7869b7723c3154d02053f23c6082ecd4a4e3"
QUERIES_SHA256 = "ffd2bbb00ee3b2234cb07b3139b74ffc78d36c78b9dfaa3df5c3060a9a2a5e0a"
CASES_SHA256 = "235854622857c3a5a5149101cfd32113f554fa491825d1df2275722c562a32ff"


def corpus_records() -> list[dict[str, Any]]:
    """The 48 frozen corpus records as `memory_datasets.json` section
    `phase72_hybrid_corpus` holds them."""
    return [
        {
            "id": rid,
            "role": role,
            "subject": "domain_knowledge",
            "trust_tier": "EXTERNAL_WRITE",
            "content": {"text": text},
            "source": source,
            "owner_scope": {"kind": "user", "id": owner},
            "symbol_ref": symbol_ref,
        }
        for rid, role, source, owner, symbol_ref, text in FROZEN_CORPUS
    ]


def query_records() -> list[dict[str, Any]]:
    """The 24 frozen query records as section `phase72_hybrid_queries` holds them."""
    return [
        {
            "question_id": qid,
            "split": split,
            "question": question,
            "answer": answer,
            "relevant_ids": [rel],
        }
        for qid, split, _query, question, answer, rel in FROZEN_QUERIES
    ]


def records_digest(records: list[dict[str, Any]]) -> str:
    """`memory_datasets._records_digest`: sha256 of compact sorted-key JSON."""
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def manifest_cases() -> list[dict[str, Any]]:
    """The 24 frozen `p72-` manifest cases, in id order."""
    return [
        {
            "id": qid,
            "kind": "dataset_answer",
            "family": "phase72_retrieval",
            "variant": "base",
            "retrieval_required": True,
            "inputs": {
                "section": "phase72_hybrid_queries",
                "corpus_section": "phase72_hybrid_corpus",
                "record_id": qid,
                "query": query,
            },
            "fixture_revision": PHASE72_FIXTURE_REVISION,
            "grants": ["cache_write", "network"],
            "permitted_actions": ["answer"],
            "editable_paths": [],
            "budget": {
                "max_total_tokens": 16000,
                "output_reserve_tokens": 1024,
                "max_steps": 12,
                "timeout_s": 600,
            },
            "acceptance": {
                "evaluator": "normalized_contains",
                "behavior_ids": [],
                "required_commands": [],
                "handoff": None,
            },
        }
        for qid, _split, query, _question, _answer, _rel in sorted(FROZEN_QUERIES)
    ]


def seed_frozen(env: Env, records: list[dict[str, Any]] | None = None) -> None:
    """Packet seeding, in a fresh root: write `src/p72_settings.py`, grant g1 over the three
    sources, write the 48 records, revoke g1, grant the two live sources, edit the settings
    file so the anchored rows go stale. `records` defaults to the transcribed literal; the
    fixture-checking tests pass the records loaded from `memory_datasets.json`."""
    from rush.memory.retrieval import SourceValidationMemo

    corpus = records if records is not None else corpus_records()

    settings = env.root / SETTINGS_REL
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("EXPORT_BATCH_SIZE = 300\n", encoding="utf-8")
    g1 = grant_scope(
        env.auth,
        env.root,
        READER,
        env.data_root,
        sources=("p72-anchored", "p72-notes", "p72-revoked"),
        ops=("ask", "expand", "list"),
    )
    store = TypedArtifactStore(env.root)
    source_hash = SourceValidationMemo().source_hash(env.root, SETTINGS_REL)
    for record in corpus:
        store.write(
            MemoryArtifact(
                id=record["id"],
                family=_family_for_subject(record["subject"]),
                subject=record["subject"],
                trust_tier=record["trust_tier"],
                content=record["content"],
                source=record["source"],
                created_at=time.time(),
                symbol_ref=record["symbol_ref"],
                content_hash=source_hash if record["symbol_ref"] else None,
                owner_scope=OwnerScope(
                    record["owner_scope"]["kind"], record["owner_scope"]["id"]
                ),
            )
        )
    revoke_scope(env.auth, env.data_root, g1)
    env.grant = grant_scope(
        env.auth,
        env.root,
        READER,
        env.data_root,
        sources=("p72-anchored", "p72-notes"),
        ops=("ask", "expand", "list"),
    )
    settings.write_text("EXPORT_BATCH_SIZE = 750\n", encoding="utf-8")
    env.owner = READER
    env.store = store


def frozen_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    env = make_env(tmp_path, monkeypatch, rows=None, policy=False, store=False)
    seed_frozen(env)
    env.vector_fn = oracle_vectors
    return env


_TEXT_DIM = {
    embedding_text_of({"text": text}): index
    for index, (_rid, _role, _source, _owner, _sym, text) in enumerate(FROZEN_CORPUS)
}
_QUERY_DIM = {
    query: next(i for i, rec in enumerate(FROZEN_CORPUS) if rec[0] == rel)
    for _qid, _split, query, _question, _answer, rel in FROZEN_QUERIES
}


def oracle_vectors(batch: Sequence[str]) -> list[list[float]]:
    """The oracle embedding: a record and its query share one axis, so the relevant record is
    the single nearest vector to its query; any other text lies on a spare axis."""
    width = len(FROZEN_CORPUS) + 1
    vectors = []
    for text in batch:
        axis = _TEXT_DIM.get(text, _QUERY_DIM.get(text, width - 1))
        vector = [0.0] * width
        vector[axis] = 1.0
        vectors.append(vector)
    return vectors


def uniform_vectors(batch: Sequence[str]) -> list[list[float]]:
    return [[1.0, 0.0, 0.0] for _ in batch]


def p72_recall(
    env: Env,
    query: str,
    *,
    request: dict[str, Any] | None = None,
    network: bool = True,
    cache_write: bool = False,
) -> Out:
    return tool_call(
        env,
        "recall",
        query=query,
        owner=READER,
        request=request if request is not None else lex(**QUERY_REQUEST),
        network=network,
        cache_write=cache_write,
    )


def assert_fallback(out: Out, code: str, *, status: str = "warn") -> None:
    """A labelled lexical fallback: never `retrieval == "hybrid"`, exactly one code, the
    fixed reason text."""
    assert out.code == "E_EMBEDDING_UNAVAILABLE", (out.code, out.data)
    assert out.status == status, out.status
    data = out.data
    assert data["retrieval"] == "lexical", data
    assert data["embedding_status"] == "skipped", data
    assert data["embedding_fallback_code"] == code, data
    assert data["hybrid_unavailable_reason"] == FALLBACK_TEXT[code], data


def lexical_required(env: Env) -> dict[str, int]:
    """The `required` size the lexical admission reports for caps of one byte/token."""
    out = tool_call(env, "recall", request=lex(max_bytes=1, max_tokens=1))
    assert out.code == "E_INPUT", out.data
    return out.data["required"]


def hybrid_required(env: Env, encoding: str = "cl100k_base") -> tuple[int, int]:
    """Brief section 3.3: the elementwise maximum, over every zero-item envelope the hybrid
    route can emit, of the measured size, plus the framing the lexical admission adds on
    top of its own page minimum."""
    from rush.memory.retrieval import _measure_page

    lexical_min = _measure_page([], None, False, encoding)
    required = lexical_required(env)
    framing = (
        required["max_bytes"] - lexical_min[0],
        required["max_tokens"] - lexical_min[1],
    )
    sizes = [
        _measure_page(
            [],
            None,
            False,
            encoding,
            {
                "retrieval": "hybrid",
                "candidates_truncated": False,
                "incomplete_reason": "candidate_cap",
                "embedded_texts": MAX_EMBEDDED_TEXTS,
            },
        )
    ]
    for code, text in FALLBACK_TEXT.items():
        sizes.append(
            _measure_page(
                [],
                None,
                False,
                encoding,
                {
                    "retrieval": "lexical",
                    "embedding_status": "skipped",
                    "embedding_fallback_code": code,
                    "hybrid_unavailable_reason": text,
                    "embedded_texts": MAX_EMBEDDED_TEXTS,
                },
            )
        )
    return (
        max(b for b, _ in sizes) + framing[0],
        max(t for _, t in sizes) + framing[1],
    )


# --- R1 ----------------------------------------------------------------------------------


def test_t08_scope_fallback_and_heldout_relevance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = frozen_env(tmp_path, monkeypatch)
    forbidden_ids = {r[0] for r in FROZEN_CORPUS if r[1] in SECURITY_ROLES}
    forbidden_texts = {
        embedding_text_of({"text": r[5]})
        for r in FROZEN_CORPUS
        if r[1] in SECURITY_ROLES
    }
    eligible_texts = {
        embedding_text_of({"text": r[5]})
        for r in FROZEN_CORPUS
        if r[1] not in SECURITY_ROLES
    }
    assert len(forbidden_ids) == 12 and len(eligible_texts) == 36

    # Held-out relevance under the oracle: every literal and every paraphrase query returns
    # its relevant record in the top 8 as a hybrid page; only eligible rows are embedded.
    hits = {"literal": 0, "paraphrase": 0}
    request = hy(limit=8, max_tokens=2048, max_bytes=8192)
    for qid, split, query, _question, _answer, relevant in FROZEN_QUERIES:
        env.embed_calls.clear()
        out = p72_recall(env, query, request=request)
        assert out.code == "OK", (qid, out.code, out.data)
        assert out.data["retrieval"] == "hybrid", (qid, out.data)
        assert not (set(out.ids) & forbidden_ids), (qid, out.ids)
        assert len(out.ids) <= 8
        hits[split] += relevant in out.ids
        sent = env.embedded
        assert set(sent) == eligible_texts | {query}, qid
        assert len(sent) == 37, (qid, len(sent))
        assert not (set(sent) & forbidden_texts), qid
        assert out.data["embedded_texts"] == 37, (qid, out.data)
        assert out.data["next_cursor"] is None
    assert hits == {"literal": 12, "paraphrase": 12}, hits

    # Labelled fallbacks, one precise reason each; lexical items stay authorized.
    literal_query = FROZEN_QUERIES[0][2]
    literal_relevant = FROZEN_QUERIES[0][5]
    env.embed_calls.clear()
    no_engine = p72_recall(
        env, literal_query, request=lex(retrieval="hybrid", **QUERY_REQUEST)
    )
    assert_fallback(no_engine, "no_engine_configured")
    assert literal_relevant in no_engine.ids
    assert not (set(no_engine.ids) & forbidden_ids)
    assert env.embed_calls == [] and env.urlopen_calls == []

    no_network = p72_recall(env, literal_query, request=request, network=False)
    assert_fallback(no_network, "network_not_granted")
    assert literal_relevant in no_network.ids
    assert env.embed_calls == [] and env.urlopen_calls == []

    from rush.memory import embeddings

    timeout_error = getattr(
        embeddings, "EmbeddingEngineTimeout", embeddings.EmbeddingEngineUnavailable
    )
    for error, code in (
        (timeout_error("slow"), "engine_timeout"),
        (embeddings.EmbeddingEngineUnavailable("down"), "engine_unreachable"),
    ):
        env.embed_calls.clear()
        env.engine_error = error
        failed = p72_recall(env, literal_query, request=request)
        assert_fallback(failed, code)
        assert literal_relevant in failed.ids
        assert not (set(failed.ids) & forbidden_ids)
        assert failed.data["embedded_texts"] == len(env.embedded) > 0
    env.engine_error = None

    env.vector_fn = lambda batch: [[float("nan"), 0.0] for _ in batch]
    invalid = p72_recall(env, literal_query, request=request)
    assert_fallback(invalid, "invalid_vectors")
    assert not (set(invalid.ids) & forbidden_ids)


# --- R2 ----------------------------------------------------------------------------------


def test_t08_fallback_keeps_budget_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, monkeypatch)
    required_bytes, required_tokens = hybrid_required(env)
    request = lex(
        retrieval="hybrid",
        max_bytes=required_bytes + 10,
        max_tokens=required_tokens + 10,
    )
    out = tool_call(env, "recall", request=request)
    assert out.code == "E_BUDGET", (out.code, out.data)
    assert out.data["items"] == []
    assert out.data["retrieval"] == "lexical", out.data
    assert out.data["embedding_fallback_code"] == "no_engine_configured", out.data
    assert (
        out.data["hybrid_unavailable_reason"] == FALLBACK_TEXT["no_engine_configured"]
    )
    assert (out.data["bytes"], out.data["tokens"]) == measured(out.data)
    assert out.data["bytes"] <= required_bytes + 10
    assert out.data["tokens"] <= required_tokens + 10

    # The same budget over a fitting row is an ordinary labelled fallback page.
    fitting = make_env(tmp_path, monkeypatch, name="fits")
    roomy = lex(
        retrieval="hybrid",
        max_bytes=required_bytes + 2000,
        max_tokens=required_tokens + 2000,
    )
    page = tool_call(fitting, "recall", request=roomy)
    assert_fallback(page, "no_engine_configured")
    assert page.ids == ["h1", "h2"], page.data


# --- R3 ----------------------------------------------------------------------------------


def test_t08_page_sizes_include_retrieval_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, monkeypatch)
    hybrid = tool_call(env, "recall", request=hy())
    assert hybrid.code == "OK" and hybrid.data["retrieval"] == "hybrid"
    for key in ("candidates_truncated", "incomplete_reason", "embedded_texts"):
        assert key in hybrid.data, (key, hybrid.data)
    assert (hybrid.data["bytes"], hybrid.data["tokens"]) == measured(hybrid.data)

    fallback = tool_call(env, "recall", request=lex(retrieval="hybrid"))
    assert_fallback(fallback, "no_engine_configured")
    assert "embedded_texts" in fallback.data
    assert (fallback.data["bytes"], fallback.data["tokens"]) == measured(fallback.data)

    no_network = tool_call(env, "recall", request=hy(), network=False)
    assert_fallback(no_network, "network_not_granted")
    assert (no_network.data["bytes"], no_network.data["tokens"]) == measured(
        no_network.data
    )


# --- R4 ----------------------------------------------------------------------------------


def test_t08_fallback_cursor_labelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [(f"r{i}", f"needle row {i}") for i in range(5)]
    env = make_env(tmp_path, monkeypatch, rows=rows)
    install_verdict(monkeypatch)
    write_config(env.root)

    first = tool_call(env, "recall", request=lex(limit=2), network=False)
    assert_fallback(first, "network_not_granted")
    assert len(first.ids) == 2 and first.data["next_cursor"] is not None
    assert first.data["complete"] is False

    # Explicit hybrid never continues a cursor.
    explicit = tool_call(
        env, "recall", request=hy(limit=2, cursor=first.data["next_cursor"])
    )
    assert explicit.code == "E_INPUT", (explicit.code, explicit.data)

    # An implicit default (configured, verdict matches) continues it as labelled lexical.
    seen = list(first.ids)
    cursor = first.data["next_cursor"]
    pages = 0
    while cursor is not None:
        page = tool_call(env, "recall", request=lex(limit=2, cursor=cursor))
        assert_fallback(page, "cursor_continuation")
        assert page.data["retrieval"] != "hybrid"
        seen.extend(page.ids)
        cursor = page.data["next_cursor"]
        pages += 1
        assert pages < 10
    assert sorted(seen) == sorted(r[0] for r in rows), seen
    assert len(seen) == len(set(seen))
    assert env.embed_calls == [] and env.urlopen_calls == []

    # Explicit lexical + cursor is today's unlabelled continuation.
    lexical_first = tool_call(env, "recall", request=lex(limit=2, retrieval="lexical"))
    assert lexical_first.code == "OK" and "retrieval" not in lexical_first.data
    lexical_seen = list(lexical_first.ids)
    cursor = lexical_first.data["next_cursor"]
    while cursor is not None:
        page = tool_call(
            env, "recall", request=lex(limit=2, retrieval="lexical", cursor=cursor)
        )
        assert page.code == "OK"
        assert (
            "retrieval" not in page.data and "embedding_fallback_code" not in page.data
        )
        lexical_seen.extend(page.ids)
        cursor = page.data["next_cursor"]
    assert sorted(lexical_seen) == sorted(r[0] for r in rows)

    # Without a default (no configuration) an implicit cursor page stays unlabelled lexical.
    (env.root / "rush.toml").unlink()
    plain_first = tool_call(env, "recall", request=lex(limit=2))
    plain = tool_call(
        env, "recall", request=lex(limit=2, cursor=plain_first.data["next_cursor"])
    )
    assert plain.code == "OK" and "embedding_fallback_code" not in plain.data


# --- R5 ----------------------------------------------------------------------------------


def test_t08_no_store_hybrid_page_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, monkeypatch, store=False)
    assert not (env.root / ".rush" / "memory.db").exists()
    before = effects(env)
    hybrid = tool_call(env, "recall", request=hy())
    assert hybrid.code == "OK", (hybrid.code, hybrid.data)
    data = hybrid.data
    assert data["items"] == [] and data["next_cursor"] is None
    assert data["complete"] is True
    assert data["retrieval"] == "hybrid"
    assert data["candidates_truncated"] is False
    assert data["embedded_texts"] == 0
    assert data["bytes"] > 0 and data["tokens"] > 0
    assert (data["bytes"], data["tokens"]) == measured(data)

    fallback = tool_call(env, "recall", request=lex(retrieval="hybrid"))
    assert_fallback(fallback, "no_engine_configured")
    assert fallback.data["items"] == [] and fallback.data["embedded_texts"] == 0
    assert (fallback.data["bytes"], fallback.data["tokens"]) == measured(fallback.data)

    no_network = tool_call(env, "recall", request=hy(), network=False)
    assert_fallback(no_network, "network_not_granted")
    assert (no_network.data["bytes"], no_network.data["tokens"]) == measured(
        no_network.data
    )

    # The lexical empty page keeps its measured size (a retained guard).
    from rush.memory.retrieval import _measure_page

    lexical = tool_call(env, "recall", request=lex())
    assert lexical.code == "OK"
    assert (lexical.data["bytes"], lexical.data["tokens"]) == _measure_page(
        [], None, True, "cl100k_base"
    )
    assert env.embed_calls == [] and env.urlopen_calls == []
    assert not (env.root / ".rush" / "memory.db").exists()
    assert effects(env) == before


# --- R6 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("op", ["ask", "recall", "list"])
def test_t08_hybrid_admission_minimum_per_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, op: str
) -> None:
    """Caps below the hybrid envelope minimum -> `E_INPUT` with `required`, before access, the
    store, telemetry, any embedding call or any network call."""
    env = make_env(tmp_path, monkeypatch)
    required_bytes, required_tokens = hybrid_required(env)
    before = effects(env)
    for caps in (
        {"max_bytes": required_bytes - 1},
        {"max_tokens": required_tokens - 1},
    ):
        out = tool_call(env, op, request=hy(**caps), cache_write=True)
        assert out.code == "E_INPUT", (op, caps, out.code, out.data)
        assert out.data["required"] == {
            "max_bytes": required_bytes,
            "max_tokens": required_tokens,
        }, (op, out.data)
        assert env.embed_calls == [] and env.urlopen_calls == []
        assert env.tags_calls == []
        assert effects(env) == before
        assert not (env.root / ".rush" / "telemetry").exists()
    # The same caps are enough for a lexical request (the minimum is hybrid-specific).
    lexical = tool_call(
        env,
        op,
        request=lex(max_bytes=required_bytes - 1, max_tokens=required_tokens - 1),
    )
    assert lexical.code in {"OK", "E_BUDGET"}, lexical.data
    # Exactly the minimum is admitted.
    admitted = tool_call(
        env, op, request=hy(max_bytes=required_bytes, max_tokens=required_tokens)
    )
    assert admitted.code != "E_INPUT", admitted.data


def test_t08_hybrid_admission_minimum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct callers get the same admission: `hybrid_page` and `hybrid_admission`."""
    from rush.memory.retrieval import hybrid_admission, hybrid_page, recall_admission

    store = TypedArtifactStore(tmp_path / "direct")
    write_row(store, "a1", "needle one", source="allowed")
    lexical_refusal = recall_admission(
        limit=8, max_bytes=1, max_tokens=1, encoding="cl100k_base"
    )
    assert lexical_refusal is not None and lexical_refusal["code"] == "E_INPUT"
    refusal = hybrid_admission(
        limit=8, max_bytes=1, max_tokens=1, encoding="cl100k_base"
    )
    assert refusal is not None and refusal["code"] == "E_INPUT"
    required = refusal["required"]
    assert required["max_bytes"] > lexical_refusal["required"]["max_bytes"]
    assert required["max_tokens"] > lexical_refusal["required"]["max_tokens"]
    assert (
        hybrid_admission(
            limit=8,
            max_bytes=required["max_bytes"],
            max_tokens=required["max_tokens"],
            encoding="cl100k_base",
        )
        is None
    )
    assert (
        cast(
            dict[str, Any],
            hybrid_admission(
                limit=0, max_bytes=10**6, max_tokens=10**6, encoding="cl100k_base"
            ),
        )["code"]
        == "E_INPUT"
    )
    assert (
        cast(
            dict[str, Any],
            hybrid_admission(
                limit=8,
                max_bytes=10**6,
                max_tokens=10**6,
                encoding="cl100k_base",
                cursor=123,
            ),
        )["code"]
        == "E_INPUT"
    )
    calls: list[list[str]] = []

    def embed(config: Any, texts: Sequence[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    page = hybrid_page(
        store,
        subject=SUBJECT,
        query="needle",
        session_allowlist=["allowed"],
        embed_config=None,
        max_bytes=1,
        max_tokens=1,
        embed_fn=embed,
    )
    assert page["code"] == "E_INPUT" and calls == []
    assert page["required"] == required


# --- R7 ----------------------------------------------------------------------------------

ENC = "cl100k_base"


def _plain_embed(config: Any, texts: Sequence[str]) -> list[list[float]]:
    return [[1.0, float(len(text) % 5)] for text in texts]


def _pool_config() -> Any:
    from rush.memory.embeddings import EmbeddingConfig

    return EmbeddingConfig(endpoint=ENDPOINT, model=MODEL, model_digest=DIGEST)


def _build_pool(
    root: Path, count: int, *, extra: str | None = None
) -> TypedArtifactStore:
    """`count` active rows `h-0000..` (one source each, so an allowlist selects a pool of
    exactly that many), optionally followed by one more `archived` / `tampered` row."""
    store = TypedArtifactStore(root)
    total = count + (1 if extra else 0)
    for i in range(total):
        write_row(store, f"h-{i:04d}", f"needle h-{i:04d}", source=f"s{i}")
    if extra == "archived":
        store.archive(
            f"h-{count:04d}",
            expected_version=1,
            scope=SUBJECT,
            owner_scope=ALICE,
            apply=True,
        )
    elif extra == "tampered":
        tamper(root, f"h-{count:04d}")
    return store


def _exact_fit(items: list[dict[str, Any]]) -> tuple[int, int]:
    """The (bytes, tokens) of a page holding exactly `items`, maximised over every label
    variant the final page can carry."""
    from rush.memory.retrieval import _measure_page

    sizes = []
    for truncated in (False, True):
        for reason in (
            None,
            "candidate_cap",
            "item_limit",
            "byte_budget",
            "token_budget",
        ):
            for complete in (True, False):
                sizes.append(
                    _measure_page(
                        items,
                        None,
                        complete,
                        ENC,
                        {
                            "retrieval": "hybrid",
                            "candidates_truncated": truncated,
                            "incomplete_reason": reason,
                            "embedded_texts": MAX_EMBEDDED_TEXTS,
                        },
                    )
                )
    return max(b for b, _ in sizes), max(t for _, t in sizes)


def _hybrid(
    store: TypedArtifactStore, sources: list[str], **kwargs: Any
) -> dict[str, Any]:
    from rush.memory.retrieval import hybrid_page

    return hybrid_page(
        store,
        subject=SUBJECT,
        query="needle",
        session_allowlist=sources,
        embed_config=_pool_config(),
        embed_fn=_plain_embed,
        **kwargs,
    )


def test_t08_hybrid_complete_false_when_capped(tmp_path: Path) -> None:
    big = _build_pool(tmp_path / "big", 513)
    archived = _build_pool(tmp_path / "archived", 511, extra="archived")
    tampered = _build_pool(tmp_path / "tampered", 512, extra="tampered")

    def srcs(n: int) -> list[str]:
        return [f"s{i}" for i in range(n)]

    huge = {"limit": 1000, "max_bytes": 10**9, "max_tokens": 10**9}
    pools: list[tuple[str, TypedArtifactStore, list[str], int, bool]] = [
        # label, store, allowlist, active rows, capped scan
        ("0", big, [], 0, False),
        ("1", big, srcs(1), 1, False),
        ("30", big, srcs(30), 30, False),
        ("511", big, srcs(511), 511, False),
        ("512", big, srcs(512), 512, False),
        ("513", big, srcs(513), 513, True),
        ("511+archived", archived, srcs(512), 511, False),
        ("512+tampered", tampered, srcs(513), 512, True),
    ]
    for label, store, sources, active, capped in pools:
        if not sources:
            # An empty allowlist denies (fail closed); pool 0 is an empty store instead.
            continue
        page = _hybrid(store, sources, **huge)
        assert page["code"] == "OK", (label, page)
        assert page["retrieval"] == "hybrid" and page["next_cursor"] is None, label
        shown = min(active, 512) if capped else active
        assert len(page["items"]) == shown, (label, len(page["items"]))
        assert page["candidates_truncated"] is capped, label
        assert page["complete"] is (not capped), (label, page["complete"])
        assert page["incomplete_reason"] == ("candidate_cap" if capped else None), label
        assert (page["bytes"], page["tokens"]) == measured(page), label

    empty = TypedArtifactStore(tmp_path / "empty")
    page = _hybrid(empty, ["s0"], **huge)
    assert page["code"] == "OK" and page["items"] == [] and page["complete"] is True
    assert page["incomplete_reason"] is None and page["next_cursor"] is None

    # Item limit: stop wins over the candidate cap; a pool of exactly `limit` is complete.
    for label, store, sources, active, _capped in pools[2:]:
        page = _hybrid(store, sources, limit=20, max_bytes=10**9, max_tokens=10**9)
        assert len(page["items"]) == 20, label
        assert page["complete"] is False, label
        assert page["incomplete_reason"] == "item_limit", (
            label,
            page["incomplete_reason"],
        )
    exact = _hybrid(big, srcs(20), limit=20, max_bytes=10**9, max_tokens=10**9)
    assert len(exact["items"]) == 20 and exact["complete"] is True
    assert exact["incomplete_reason"] is None
    for n in (0, 1):
        under = _hybrid(
            big, srcs(n) or ["none"], limit=20, max_bytes=10**9, max_tokens=10**9
        )
        assert under["complete"] is True and under["incomplete_reason"] is None

    # Byte and token budgets: caps that fit exactly three items stop at three.
    reference = _hybrid(big, srcs(30), **huge)
    first_three = reference["items"][:3]
    fit_bytes, fit_tokens = _exact_fit(first_three)
    for label, store, sources, active, _capped in pools[2:]:
        by_bytes = _hybrid(
            store, sources, limit=1000, max_bytes=fit_bytes, max_tokens=10**9
        )
        assert [i["id"] for i in by_bytes["items"]] == [i["id"] for i in first_three], (
            label
        )
        assert by_bytes["complete"] is False, label
        assert by_bytes["incomplete_reason"] == "byte_budget", (label, by_bytes)
        assert by_bytes["bytes"] <= fit_bytes
        by_tokens = _hybrid(
            store, sources, limit=1000, max_bytes=10**9, max_tokens=fit_tokens
        )
        assert [i["id"] for i in by_tokens["items"]] == [
            i["id"] for i in first_three
        ], label
        assert by_tokens["complete"] is False, label
        assert by_tokens["incomplete_reason"] == "token_budget", (label, by_tokens)
        assert by_tokens["tokens"] <= fit_tokens
    one = _hybrid(big, srcs(1), limit=1000, max_bytes=fit_bytes, max_tokens=fit_tokens)
    assert one["complete"] is True and one["incomplete_reason"] is None

    # A first item that exceeds the budget is an `E_BUDGET` page with the stop reason.
    from rush.memory.retrieval import hybrid_admission

    floor = hybrid_admission(limit=8, max_bytes=1, max_tokens=1, encoding=ENC)
    assert floor is not None
    over = _hybrid(
        big,
        srcs(1),
        limit=8,
        max_bytes=floor["required"]["max_bytes"] + 2,
        max_tokens=10**9,
    )
    assert over["code"] == "E_BUDGET", over
    assert over["items"] == [] and over["retrieval"] == "hybrid"
    assert over["incomplete_reason"] == "byte_budget"
    assert (over["bytes"], over["tokens"]) == measured(over)


# --- verdict rows (the contract pinned for `reporting.aggregate_hybrid_verdict`) -------------

PROVIDERS = ("openai-codex-oauth-cli-live", "anthropic-claude-code-live")
SEEDS = (1, 2, 3)
BUDGETS = {
    "max_total_tokens": 16000,
    "output_reserve_tokens": 1024,
    "max_steps": 12,
    "timeout_s": 600,
}
BASELINE_CASES = (
    "lme-q-001",
    "lme-q-002",
    "upload-repair",
    "guest-handoff",
    "diagnosis-handoff",
)
CHANCE = 8 / 36  # min(1, n_i / E_i) with n_i = 8 returned items and E_i = 36


def verdict_row(
    provider: str,
    arm: str,
    case_id: str,
    seed: int,
    *,
    split: str | None,
    recall: float | None,
    passed: bool,
    case_tokens: float = 3000.0,
    case_ms: float = 1000.0,
    chance: float | None = CHANCE,
    security: int = 0,
    false_inclusion: int = 0,
    retrieval: str | None = None,
    fallback: str | None = None,
    override_skipped: str | None = None,
    required: bool = True,
    route_available: bool = True,
    fixture_revision: str = PHASE72_FIXTURE_REVISION,
) -> dict[str, Any]:
    """One arm/case/seed observation, the row `reporting.aggregate_hybrid_verdict` takes.

    Pairing key: `(provider, case_id, seed, fixture_revision, grants, budgets)` across the
    three arms (`current`, `hybrid`, `metadata`). `split` is `literal` / `paraphrase` for a
    `p72-` case and `None` for a baseline case (which has no relevant ids, so it counts only
    toward unsafe inclusion, availability and passes). `recall_at_8` / `chance_recall` are the
    harness values (`reporting.recall_at_k`, `reporting.chance_recall`); `retrieval` is the
    page label of the arm's retrieval (`hybrid` only when a hybrid page was returned);
    `embedding_fallback_code` / `override_skipped` mark a fallback page.
    """
    return {
        "provider": provider,
        "arm": arm,
        "case_id": case_id,
        "seed": seed,
        "fixture_revision": fixture_revision,
        "grants": ["cache_write", "network"],
        "budgets": dict(BUDGETS),
        "split": split,
        "retrieval_required": required,
        "recall_at_8": recall,
        "chance_recall": chance,
        "false_inclusion": false_inclusion,
        "security_inclusion": security,
        "passed": passed,
        "case_tokens": case_tokens,
        "case_ms": case_ms,
        "retrieval": retrieval
        if retrieval is not None
        else ("hybrid" if arm == "hybrid" else "lexical"),
        "embedding_fallback_code": fallback,
        "override_skipped": override_skipped,
        "route_available": route_available,
    }


def verdict_rows(
    provider: str,
    *,
    hybrid_recall: Callable[[str, str], float] = lambda qid, split: 1.0,
    current_recall: Callable[[str, str], float] = lambda qid, split: (
        1.0 if split == "literal" else 0.0
    ),
    hybrid_pass: Callable[[str, str], bool] = lambda qid, split: True,
    current_pass: Callable[[str, str], bool] = lambda qid, split: split == "literal",
    hybrid_tokens: float = 3200.0,
    current_tokens: float = 3000.0,
    hybrid_ms: float = 1200.0,
    current_ms: float = 1000.0,
    seeds: Sequence[int] = SEEDS,
    baseline: bool = False,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """The 24 `p72-` cases x seeds x three arms (plus the five baseline cases when asked)."""
    rows: list[dict[str, Any]] = []
    for qid, split, *_rest in FROZEN_QUERIES:
        for seed in seeds:
            rows.append(
                verdict_row(
                    provider,
                    "current",
                    qid,
                    seed,
                    split=split,
                    recall=current_recall(qid, split),
                    passed=current_pass(qid, split),
                    case_tokens=current_tokens,
                    case_ms=current_ms,
                )
            )
            rows.append(
                verdict_row(
                    provider,
                    "hybrid",
                    qid,
                    seed,
                    split=split,
                    recall=hybrid_recall(qid, split),
                    passed=hybrid_pass(qid, split),
                    case_tokens=hybrid_tokens,
                    case_ms=hybrid_ms,
                )
            )
            rows.append(
                verdict_row(
                    provider,
                    "metadata",
                    qid,
                    seed,
                    split=split,
                    recall=0.0,
                    passed=False,
                )
            )
    if baseline:
        for case_id in BASELINE_CASES:
            for seed in seeds:
                for arm in ("current", "hybrid", "metadata"):
                    rows.append(
                        verdict_row(
                            provider,
                            arm,
                            case_id,
                            seed,
                            split=None,
                            recall=None,
                            passed=True,
                            chance=None,
                            required=False,
                            retrieval="lexical",
                        )
                    )
    if mutate is not None:
        for row in rows:
            mutate(row)
    return rows


def verdict_name(value: Any) -> Any:
    return value["verdict"] if isinstance(value, dict) else value


def aggregate(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], Any]:
    from scripts.benchmarks.reporting import aggregate_hybrid_verdict

    result = aggregate_hybrid_verdict(rows)
    per_provider = {p: verdict_name(v) for p, v in result["per_provider"].items()}
    return per_provider, verdict_name(result["global"])


# --- R12 ---------------------------------------------------------------------------------


def _verdict_table() -> None:
    a, b = PROVIDERS

    def both(**kwargs: Any) -> list[dict[str, Any]]:
        return verdict_rows(a, **kwargs) + verdict_rows(b, **kwargs)

    def only_a(**kwargs: Any) -> list[dict[str, Any]]:
        return verdict_rows(a, **kwargs) + verdict_rows(b)

    # Row 5/4: the oracle is a benefit on both providers, with baseline cases present.
    per, global_verdict = aggregate(both(baseline=True))
    assert per == {a: "benefit", b: "benefit"} and global_verdict == "benefit"

    # Row 1: any unauthorized or stale inclusion in any arm is unsafe, and the global
    # verdict is unsafe whatever the other provider shows.
    def security_in_metadata(row: dict[str, Any]) -> None:
        if row["arm"] == "metadata" and row["case_id"] == "p72-q05":
            row["security_inclusion"] = 1

    per, global_verdict = aggregate(only_a(mutate=security_in_metadata))
    assert per[a] == "unsafe" and per[b] == "benefit" and global_verdict == "unsafe"

    def security_in_hybrid(row: dict[str, Any]) -> None:
        if row["arm"] == "hybrid" and row["case_id"] == "p72-q20":
            row["security_inclusion"] = 2

    assert aggregate(only_a(mutate=security_in_hybrid))[1] == "unsafe"

    # Row 2: any hybrid fallback or unavailable route is unavailable (and outranks harm).
    def fallback_page(row: dict[str, Any]) -> None:
        if row["arm"] == "hybrid" and row["case_id"] == "p72-q13" and row["seed"] == 2:
            row["retrieval"] = "lexical"
            row["embedding_fallback_code"] = "engine_timeout"

    per, global_verdict = aggregate(only_a(mutate=fallback_page))
    assert per[a] == "unavailable" and global_verdict == "unavailable"

    def route_down(row: dict[str, Any]) -> None:
        row["route_available"] = False

    assert aggregate(only_a(mutate=route_down))[0][a] == "unavailable"

    # Sum of seed-averaged current passes of the `p72-` cases is zero -> unavailable.
    per, _ = aggregate(
        only_a(
            current_pass=lambda qid, split: False, hybrid_pass=lambda qid, split: True
        )
    )
    assert per[a] == "unavailable"

    # Row 3: harm. Literal recall mean difference below zero.
    per, global_verdict = aggregate(
        only_a(hybrid_recall=lambda qid, split: 0.5 if split == "literal" else 1.0)
    )
    assert per[a] == "harm" and global_verdict == "harm"
    # Paraphrase paired-bootstrap ci.high below zero.
    per, _ = aggregate(
        only_a(
            current_recall=lambda qid, split: 1.0,
            hybrid_recall=lambda qid, split: 1.0 if split == "literal" else 0.0,
        )
    )
    assert per[a] == "harm"
    # Fewer total seed-averaged passes for hybrid than for current, recall otherwise equal.
    per, _ = aggregate(
        only_a(
            current_recall=lambda qid, split: 1.0,
            hybrid_recall=lambda qid, split: 1.0,
            current_pass=lambda qid, split: True,
            hybrid_pass=lambda qid, split: qid not in {"p72-q01", "p72-q02"},
        )
    )
    assert per[a] == "harm"
    # PR4: equal passes, hybrid costs more per correct answer (tokens, then milliseconds).
    per, _ = aggregate(
        only_a(
            current_pass=lambda qid, split: True,
            hybrid_tokens=4200.0,
            current_tokens=3000.0,
        )
    )
    assert per[a] == "harm"
    per, _ = aggregate(
        only_a(
            current_pass=lambda qid, split: True, hybrid_ms=2400.0, current_ms=1000.0
        )
    )
    assert per[a] == "harm"
    # The same extra cost buys twelve more passes: cost per pass falls, so no PR4 harm.
    per, _ = aggregate(only_a(hybrid_tokens=3200.0, current_tokens=3000.0))
    assert per[a] == "benefit"

    # Row 4/5: two improved paraphrase cases are not enough (the bootstrap interval keeps
    # a zero resample), and recall equal to chance on every paraphrase case is no benefit.
    two = {"p72-q13", "p72-q14"}
    per, global_verdict = aggregate(
        only_a(
            current_recall=lambda qid, split: 1.0 if split == "literal" else 0.0,
            hybrid_recall=lambda qid, split: (
                1.0 if split == "literal" or qid in two else 0.0
            ),
            hybrid_pass=lambda qid, split: split == "literal" or qid in two,
        )
    )
    assert per[a] == "no_benefit" and global_verdict == "no_benefit"
    per, _ = aggregate(
        only_a(
            hybrid_recall=lambda qid, split: 1.0 if split == "literal" else CHANCE,
        )
    )
    assert per[a] == "no_benefit"

    # Global: harm outranks a benefit; benefit needs every provider to be a benefit.
    mixed = verdict_rows(a) + verdict_rows(
        b, hybrid_recall=lambda qid, split: 0.5 if split == "literal" else 1.0
    )
    assert aggregate(mixed) == ({a: "benefit", b: "harm"}, "harm")
    mixed = verdict_rows(a) + verdict_rows(
        b,
        current_recall=lambda qid, split: 1.0 if split == "literal" else 0.0,
        hybrid_recall=lambda qid, split: (
            1.0 if split == "literal" or qid in two else 0.0
        ),
        hybrid_pass=lambda qid, split: split == "literal" or qid in two,
    )
    assert aggregate(mixed) == ({a: "benefit", b: "no_benefit"}, "no_benefit")


def _default_page(env: Env, **kwargs: Any) -> Out:
    kwargs.setdefault("request", lex())
    return tool_call(env, "recall", **kwargs)


def _default_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rush.memory import retrieval

    env = make_env(tmp_path, monkeypatch)
    write_config(env.root)

    # No verdict constant (or a non-benefit verdict) -> lexical, no label, config unread
    # for effect: zero embed, tags and network.
    for verdict in (
        None,
        {**VERDICT, "verdict": "no_benefit"},
        {**VERDICT, "verdict": "harm"},
        {**VERDICT, "verdict": "unavailable"},
        {**VERDICT, "verdict": "unsafe"},
    ):
        monkeypatch.setattr(retrieval, "HYBRID_DEFAULT_VERDICT", verdict, raising=False)
        page = _default_page(env)
        assert page.code == "OK" and "retrieval" not in page.data, (verdict, page.data)
        assert page.ids == ["h1", "h2"]
        assert (
            env.embed_calls == [] and env.tags_calls == [] and env.urlopen_calls == []
        )

    # Benefit verdict equal to the configured model and digest -> hybrid by default, after
    # one `/api/tags` check; never for explicit lexical.
    install_verdict(monkeypatch)
    page = _default_page(env)
    assert page.code == "OK", (page.code, page.data)
    assert page.data["retrieval"] == "hybrid"
    assert page.ids == ["h1", "h2", "h3"]
    assert env.tags_calls == [ENDPOINT]
    assert env.embed_configs[0].endpoint == ENDPOINT
    assert env.embed_configs[0].model == MODEL
    assert env.embed_configs[0].model_digest == DIGEST
    before_calls = len(env.embed_calls)
    explicit = _default_page(env, request=lex(retrieval="lexical"))
    assert explicit.code == "OK" and "retrieval" not in explicit.data
    assert len(env.embed_calls) == before_calls and env.tags_calls == [ENDPOINT]

    # Every one of the three options must be set; any mismatch with the verdict -> lexical.
    for kwargs in (
        {"endpoint": None},
        {"model": None},
        {"digest": None},
        {"digest": "ffffffffffff"},
        {"model": "other-model"},
    ):
        write_config(env.root, **kwargs)
        env.embed_calls.clear()
        env.tags_calls.clear()
        page = _default_page(env)
        assert page.code == "OK" and "retrieval" not in page.data, (kwargs, page.data)
        assert env.embed_calls == [] and env.tags_calls == [], kwargs
    write_config(env.root)

    # A non-loopback configured endpoint is refused with a label, never contacted.
    write_config(env.root, endpoint="http://embed.example.com:11434")
    page = _default_page(env)
    assert_fallback(page, "endpoint_not_loopback")
    assert env.embed_calls == [] and env.urlopen_calls == []
    write_config(env.root)

    # Explicit request fields win over config, per field; explicit hybrid never runs the
    # tags check.
    env.embed_calls.clear()
    env.embed_configs.clear()
    env.tags_calls.clear()
    explicit_hybrid = tool_call(
        env,
        "recall",
        request=lex(
            retrieval="hybrid",
            embedding_endpoint="http://127.0.0.1:2222",
            embedding_model="request-model",
            embedding_model_digest="aaaaaaaaaaaa",
        ),
    )
    assert (
        explicit_hybrid.code == "OK" and explicit_hybrid.data["retrieval"] == "hybrid"
    )
    config = env.embed_configs[0]
    assert (config.endpoint, config.model, config.model_digest) == (
        "http://127.0.0.1:2222",
        "request-model",
        "aaaaaaaaaaaa",
    )
    assert env.tags_calls == []
    env.embed_configs.clear()
    partial = tool_call(
        env,
        "recall",
        request=lex(retrieval="hybrid", embedding_model="request-model"),
    )
    assert partial.code == "OK" and partial.data["retrieval"] == "hybrid"
    config = env.embed_configs[0]
    assert (config.endpoint, config.model, config.model_digest) == (
        ENDPOINT,
        "request-model",
        DIGEST,
    )
    assert env.tags_calls == []


def _committed_constant(constant: dict[str, Any] | None) -> None:
    """`HYBRID_DEFAULT_VERDICT` is `None` until the committed verdict JSON says `benefit`;
    then it equals that file and the frozen manifest's embedding identity. `constant` is
    the production value, read before any test patched it."""
    repo = Path(__file__).resolve().parents[1]
    verdict_path = (
        repo / "docs" / "reports" / "phase-72-memory-eval" / "hybrid-verdict.json"
    )
    if not verdict_path.is_file():
        assert constant is None
        return
    payload = json.loads(verdict_path.read_text(encoding="utf-8"))
    global_verdict = verdict_name(payload["global"])
    if global_verdict != "benefit":
        assert constant is None, global_verdict
        return
    assert constant is not None
    assert constant["verdict"] == "benefit"
    assert (
        constant["verdict_report_sha256"]
        == hashlib.sha256(verdict_path.read_bytes()).hexdigest()
    )
    assert (
        constant["cases_sha256"] == CASES_SHA256 or len(constant["cases_sha256"]) == 64
    )
    manifest = json.loads(
        (repo / "tests" / "fixtures" / "phase75" / "task_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    embedding = manifest["phase72_embedding"]
    assert constant["model"] == embedding["model"]
    assert constant["model_digest"] == embedding["model_digest"]


def test_t08_hybrid_default_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The D14a verdict table in order, the default switch (benefit verdict, all three
    options, matching model and digest, loopback endpoint) and the committed constant."""
    from rush.memory import retrieval

    committed = retrieval.HYBRID_DEFAULT_VERDICT
    _verdict_table()
    _default_switch(tmp_path, monkeypatch)
    _committed_constant(committed)


# --- R15 ---------------------------------------------------------------------------------


def test_t08_config_options_and_network_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.config import RushConfigError, load_config

    env = make_env(tmp_path, monkeypatch)
    write_config(env.root)
    options = load_config(env.root).tools["memory"].options
    assert options["embedding_endpoint"] == ENDPOINT
    assert options["embedding_model"] == MODEL
    assert options["embedding_model_digest"] == DIGEST
    assert options["record"] is False

    write_config(env.root, raw="[tools.memory]\nrecord = true\n")
    plain = load_config(env.root).tools["memory"].options
    assert plain["record"] is True
    for key in ("embedding_endpoint", "embedding_model", "embedding_model_digest"):
        # config.py keeps no None-valued defaults, so an unset option reads back as absent.
        assert plain.get(key) is None, key

    write_config(
        env.root,
        raw='[tools.memory]\nembedding_endpoint = "http://127.0.0.1:1"\nembedding_bogus = "x"\n',
    )
    with pytest.raises(RushConfigError):
        load_config(env.root)

    # Hybrid without the network grant is a labelled lexical fallback, never E_PERMISSION:
    # explicit request fields, explicit with config fields, and the implicit default.
    write_config(env.root)
    install_verdict(monkeypatch)
    for transport in ("inproc", "mcp"):
        for request in (hy(), lex(retrieval="hybrid"), lex()):
            page = tool_call(
                env, "recall", transport=transport, request=request, network=False
            )
            assert_fallback(page, "network_not_granted")
            assert page.ids == ["h1", "h2"], (transport, request, page.data)
            assert page.code != "E_PERMISSION"
    assert env.embed_calls == [] and env.tags_calls == [] and env.urlopen_calls == []


@pytest.mark.parametrize(
    "endpoint",
    [
        pytest.param("https://127.0.0.1:{port}", id="remote_https"),
        pytest.param("http://user:secret@127.0.0.1:{port}", id="userinfo"),
        pytest.param("http://localhost.evil.test:{port}", id="localhost_suffix"),
        pytest.param("file:///etc/hosts", id="file_scheme"),
    ],
)
def test_t08_config_endpoint_must_be_loopback(
    endpoint: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_engine: Callable[..., StubEngine],
) -> None:
    engine = stub_engine()
    env = make_env(tmp_path, monkeypatch, patch_engine=False)
    port = engine.url.rsplit(":", 1)[1]
    write_config(env.root, endpoint=endpoint.format(port=port))
    install_verdict(monkeypatch)
    for request in (lex(retrieval="hybrid"), lex()):
        page = tool_call(env, "recall", request=request)
        assert_fallback(page, "endpoint_not_loopback")
        assert page.ids == ["h1", "h2"]
    assert engine.requests == []


def test_t08_default_requires_verified_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, monkeypatch)
    write_config(env.root)
    install_verdict(monkeypatch)

    def run() -> Out:
        env.embed_calls.clear()
        return tool_call(env, "recall", request=lex())

    # A matching entry (the `:latest` tag implied, or the exact name) and a digest that
    # starts with the configured one -> hybrid.
    for name in (f"{MODEL}:latest", MODEL):
        env.tags = {"models": [{"name": name, "digest": FULL_DIGEST}]}
        page = run()
        assert page.code == "OK" and page.data["retrieval"] == "hybrid", (
            name,
            page.data,
        )
    # Everything else is a labelled lexical fallback with no embedding call.
    bad = {
        "digest_prefix": {"models": [{"name": f"{MODEL}:latest", "digest": "f" * 64}]},
        "other_name": {"models": [{"name": "other:latest", "digest": FULL_DIGEST}]},
        "short_digest": {"models": [{"name": f"{MODEL}:latest", "digest": DIGEST}]},
        "upper_digest": {
            "models": [{"name": f"{MODEL}:latest", "digest": FULL_DIGEST.upper()}]
        },
        "non_string_digest": {"models": [{"name": f"{MODEL}:latest", "digest": 12}]},
        "no_models": {"models": []},
        "not_a_dict": [],
    }
    for label, payload in bad.items():
        env.tags = payload
        page = run()
        assert_fallback(page, "model_digest_mismatch")
        assert page.ids == ["h1", "h2"], label
        assert env.embed_calls == [], label
    # The check never runs for an explicit hybrid request (no tags call), and an explicit
    # non-loopback request endpoint is used under the network grant.
    env.tags = bad["digest_prefix"]
    env.tags_calls.clear()
    explicit = tool_call(
        env, "recall", request=hy(embedding_endpoint="https://embed.example.com:8443")
    )
    assert explicit.code == "OK" and explicit.data["retrieval"] == "hybrid"
    assert env.tags_calls == []
    assert env.embed_configs[-1].endpoint == "https://embed.example.com:8443"


# --- R14 ---------------------------------------------------------------------------------

WRITE_OPS = ("ask", "list", "expand", "write")


def _count_store_constructions(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counter = {"n": 0}
    original = TypedArtifactStore.__init__

    def counting(self: Any, *args: Any, **kwargs: Any) -> None:
        counter["n"] += 1
        original(self, *args, **kwargs)

    monkeypatch.setattr(TypedArtifactStore, "__init__", counting)
    return counter


def _track_policy_lock(monkeypatch: pytest.MonkeyPatch, env: Env) -> dict[str, int]:
    held = {"n": 0, "entries": 0}
    original = env.auth.hold_policy_lock

    @contextlib.contextmanager
    def tracked(*args: Any, **kwargs: Any) -> Iterator[None]:
        with original(*args, **kwargs):
            held["n"] += 1
            held["entries"] += 1
            try:
                yield
            finally:
                held["n"] -= 1

    monkeypatch.setattr(env.auth, "hold_policy_lock", tracked)
    return held


def _fill_rows(env: Env) -> dict[str, str]:
    """`artifact_id -> content_hash` of every persisted embedding row."""
    return {row[0]: row[2] for row in embedding_rows(env.root)}


def test_t08_embedding_fill_needs_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An `ask`-only grant computes embeddings and persists none; no writable store is
    # constructed and the memory database is byte-identical.
    ask_only = make_env(tmp_path, monkeypatch, name="ask_only")
    db = ask_only.root / ".rush" / "memory.db"
    db_before = hashlib.sha256(db.read_bytes()).hexdigest()
    tree_before = digest_tree(ask_only.root, skip=(".rush/telemetry",))
    constructed = _count_store_constructions(monkeypatch)
    page = tool_call(ask_only, "recall", request=hy(), cache_write=True)
    assert page.code == "OK" and page.ids == ["h1", "h2", "h3"], page.data
    assert page.data["retrieval"] == "hybrid"
    assert constructed["n"] == 0, constructed
    assert len(ask_only.embedded) == 4  # three rows and the query
    assert _fill_rows(ask_only) == {}
    assert hashlib.sha256(db.read_bytes()).hexdigest() == db_before
    # A denied `write` creates no file: the project tree is unchanged (the telemetry
    # database a cache-write read may create aside).
    assert digest_tree(ask_only.root, skip=(".rush/telemetry",)) == tree_before

    # A write-capable grant with cache_write persists one vector per embedded row, keyed by
    # the embedding-text hash; without cache_write it persists none.
    writer = make_env(tmp_path, monkeypatch, name="writer", ops=WRITE_OPS)
    off = tool_call(writer, "recall", request=hy(), cache_write=False)
    assert off.code == "OK" and _fill_rows(writer) == {}
    on = tool_call(writer, "recall", request=hy(), cache_write=True)
    assert on.code == "OK" and on.ids == ["h1", "h2", "h3"]
    assert _fill_rows(writer) == {
        artifact_id: sha_text(embedding_text_of({"text": text}))
        for artifact_id, text in F8_ROWS
    }
    # Warm cache: only the query is embedded.
    writer.embed_calls.clear()
    warm = tool_call(writer, "recall", request=hy(), cache_write=True)
    assert warm.code == "OK" and writer.embedded == ["needle"]
    assert warm.data["embedded_texts"] == 1

    # Revoke before the first endpoint call: no endpoint request, nothing persisted.
    before = make_env(tmp_path, monkeypatch, name="before", ops=WRITE_OPS)
    original_get = TypedArtifactStore.get_embedding
    state = {"revoked": False}

    def revoke_first(self: Any, **kwargs: Any) -> Any:
        if not state["revoked"]:
            state["revoked"] = True
            revoke_scope(before.auth, before.data_root, before.grant)  # type: ignore[arg-type]
        return original_get(self, **kwargs)

    monkeypatch.setattr(TypedArtifactStore, "get_embedding", revoke_first)
    denied = tool_call(before, "recall", request=hy(), cache_write=True)
    monkeypatch.setattr(TypedArtifactStore, "get_embedding", original_get)
    assert denied.code == "E_PERMISSION", (denied.code, denied.data)
    assert denied.ids == [] and before.embed_calls == []
    assert _fill_rows(before) == {}

    # Revoke between the last embedding call and the fill commit: nothing persisted.
    late = make_env(tmp_path, monkeypatch, name="late", ops=WRITE_OPS)

    def revoke_on_query(call: int, batch: list[str]) -> None:
        if batch == ["needle"]:
            revoke_scope(late.auth, late.data_root, late.grant)  # type: ignore[arg-type]

    late.on_embed = revoke_on_query
    gone = tool_call(late, "recall", request=hy(), cache_write=True)
    assert gone.code == "E_PERMISSION", (gone.code, gone.data)
    assert gone.ids == [] and _fill_rows(late) == {}

    # A content edit of one row during embedding discards that row's embedding and the
    # page is a restart.
    edit = make_env(tmp_path, monkeypatch, name="edit", ops=WRITE_OPS)

    def edit_h2(call: int, batch: list[str]) -> None:
        if call == 1 and edit.store is not None:
            edit.store.edit(
                "h2",
                {"text": "needle beta changed"},
                expected_version=1,
                scope=SUBJECT,
                owner_scope=ALICE,
                apply=True,
            )

    edit.on_embed = edit_h2
    restart = tool_call(edit, "recall", request=hy(), cache_write=True)
    assert restart.code == "E_RESTART", (restart.code, restart.data)
    assert restart.ids == []
    assert "h2" not in _fill_rows(edit)

    # The policy lock is not held while the endpoint is called.
    locked = make_env(tmp_path, monkeypatch, name="locked", ops=WRITE_OPS)
    held = _track_policy_lock(monkeypatch, locked)
    during: list[int] = []
    locked.on_embed = lambda call, batch: during.append(held["n"])
    ok = tool_call(locked, "recall", request=hy(), cache_write=True)
    assert ok.code == "OK" and during, during
    assert set(during) == {0}, during
    assert held["entries"] >= 1, (
        "the fill takes the policy lock after the endpoint calls"
    )

    # 33 missing rows go out in slices of 32 and 1, then the query.
    rows = [(f"r{i:02d}", f"needle number {i:02d}") for i in range(33)]
    many = make_env(tmp_path, monkeypatch, name="many", rows=rows, ops=WRITE_OPS)
    many.vector_fn = lambda batch: [[1.0, float(len(t) % 7)] for t in batch]
    page = tool_call(many, "recall", request=hy(limit=8), cache_write=True)
    assert page.code == "OK", (page.code, page.data)
    assert [len(batch) for batch in many.embed_calls] == [32, 1, 1], [
        len(b) for b in many.embed_calls
    ]
    assert many.embed_calls[-1] == ["needle"]
    assert len(_fill_rows(many)) == 33

    # Revoke after slice 1: no second slice and no query request, zero items, nothing kept.
    revoked = make_env(tmp_path, monkeypatch, name="revoked", rows=rows, ops=WRITE_OPS)
    revoked.vector_fn = many.vector_fn

    def revoke_after_first(call: int, batch: list[str]) -> None:
        if call == 1:
            revoke_scope(revoked.auth, revoked.data_root, revoked.grant)  # type: ignore[arg-type]

    revoked.on_embed = revoke_after_first
    page = tool_call(revoked, "recall", request=hy(limit=8), cache_write=True)
    assert page.code == "E_PERMISSION", (page.code, page.data)
    assert page.ids == [] and len(revoked.embed_calls) == 1
    assert _fill_rows(revoked) == {}

    # A grant replaced after slice 1 is a restart: no further request, nothing kept.
    replaced = make_env(
        tmp_path, monkeypatch, name="replaced", rows=rows, ops=WRITE_OPS
    )
    replaced.vector_fn = many.vector_fn

    def replace_after_first(call: int, batch: list[str]) -> None:
        if call == 1:
            revoke_scope(replaced.auth, replaced.data_root, replaced.grant)  # type: ignore[arg-type]
            grant_scope(
                replaced.auth,
                replaced.root,
                ALICE,
                replaced.data_root,
                sources=("s1", "s2"),
                ops=WRITE_OPS,
            )

    replaced.on_embed = replace_after_first
    page = tool_call(replaced, "recall", request=hy(limit=8), cache_write=True)
    assert page.code == "E_RESTART", (page.code, page.data)
    assert page.ids == [] and len(replaced.embed_calls) == 1
    assert _fill_rows(replaced) == {}

    # DDL-free fill: a store missing only one earlier task's additions (72-T05 task binding
    # columns, 72-T06 receipt columns) is read through its read-only view. Every access form
    # that would fill (policy write-capable, legacy, overlay) leaves the writable
    # constructor uncalled, the embedding table empty, every file byte-identical and no
    # migration run; the read itself answers exactly as the lexical twin does.
    from rush.memory.authorization import user_overlay_owner_scope

    overlay = user_overlay_owner_scope(data_root=default_data_root())
    forms: tuple[tuple[str, dict[str, Any]], ...] = (
        ("policy_write", {"ops": WRITE_OPS}),
        ("legacy", {"policy": False}),
        ("overlay", {"ops": (*WRITE_OPS, "overlay_read"), "owner": overlay}),
    )
    for task in SCHEMA_ADDITIONS:
        for form, options in forms:
            env = make_env(
                tmp_path,
                monkeypatch,
                name=f"ddl-{task.lower()}-{form}",
                **options,
            )
            if env.store is not None:
                env.store.close()
            dropped = drop_schema_additions(env.root / ".rush" / "memory.db", task)
            # Upstream producer present: its additions exist in a freshly created store.
            assert dropped, (task, form, "the producer's schema additions are absent")
            files_before = digest_tree(env.root, skip=(".rush/telemetry",))
            constructed = _count_store_constructions(monkeypatch)
            ask: dict[str, Any] = (
                {"allowlist": ["s1"], "owner": None} if form == "legacy" else {}
            )
            twin = tool_call(
                env, "recall", request=lex(retrieval="lexical"), cache_write=True, **ask
            )
            page = tool_call(env, "recall", request=hy(), cache_write=True, **ask)
            assert page.code == twin.code, (task, form, page.code, twin.code)
            if twin.code == "OK":
                assert page.data["retrieval"] == "hybrid", (task, form, page.data)
                assert set(page.ids) >= set(twin.ids), (task, form)
            assert constructed["n"] == 0, (task, form, constructed)
            assert embedding_rows(env.root) == [], (task, form)
            assert digest_tree(env.root, skip=(".rush/telemetry",)) == files_before, (
                task,
                form,
            )
            with contextlib.closing(
                sqlite3.connect(
                    f"file:{env.root / '.rush' / 'memory.db'}?mode=ro", uri=True
                )
            ) as conn:
                for table, columns in SCHEMA_ADDITIONS[task]["columns"].items():
                    present = {
                        row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                    }
                    assert not present & set(columns), (task, form, table, "migrated")


def test_t08_embedding_fill_access_forms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One row per access form: legacy fills under its own allowlist (mode `legacy`) and
    stops filling the moment the mode is no longer `legacy`; policy fills only when a
    `write`-capable access resolves for the same owner."""
    env = make_env(tmp_path, monkeypatch, policy=False, name="legacy")
    legacy = tool_call(
        env, "recall", request=hy(), cache_write=True, allowlist=["s1"], owner=None
    )
    assert legacy.code == "OK" and legacy.ids == ["h1", "h2", "h3"], legacy.data
    assert set(_fill_rows(env)) == {"h1", "h2", "h3"}

    # Mode flips from legacy to policy before the fill: the read is served, nothing persists.
    flip = make_env(tmp_path, monkeypatch, policy=False, name="flip")

    def enrol(call: int, batch: list[str]) -> None:
        if call == 1:
            grant_scope(flip.auth, flip.root, ALICE, flip.data_root, ops=WRITE_OPS)

    flip.on_embed = enrol
    page = tool_call(
        flip, "recall", request=hy(), cache_write=True, allowlist=["s1"], owner=None
    )
    assert page.code in {"OK", "E_RESTART", "E_PERMISSION"}, page.code
    assert _fill_rows(flip) == {}

    # Another owner holding a write grant does not authorize this owner's fill.
    other = make_env(tmp_path, monkeypatch, name="other", ops=("ask", "list", "expand"))
    grant_scope(other.auth, other.root, BOB, other.data_root, ops=WRITE_OPS)
    page = tool_call(other, "recall", request=hy(), cache_write=True)
    assert page.code == "OK" and page.ids == ["h1", "h2", "h3"]
    assert _fill_rows(other) == {}


# --- R17 ---------------------------------------------------------------------------------


def _anchored_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, ops: Sequence[str]
) -> Env:
    env = make_env(tmp_path, monkeypatch, name=name, ops=ops, rows=F8_ROWS)
    assert env.store is not None
    from rush.memory.retrieval import SourceValidationMemo

    module = env.root / "mod.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    _git(env.root, "add", "mod.py")
    _git(env.root, "commit", "-q", "-m", "mod")
    write_row(
        env.store,
        "anchor",
        "needle anchored",
        symbol_ref="mod.py::",
        content_hash=SourceValidationMemo().source_hash(env.root, "mod.py"),
    )
    return env


def _mutations(env: Env) -> dict[str, Callable[[], None]]:
    store = env.store
    assert store is not None

    def archive() -> None:
        store.archive(
            "h1", expected_version=1, scope=SUBJECT, owner_scope=ALICE, apply=True
        )

    def expiry() -> None:
        stamp_expiry(env.root, "h1")

    def edit() -> None:
        store.edit(
            "h1",
            {"text": "needle alpha edited"},
            expected_version=1,
            scope=SUBJECT,
            owner_scope=ALICE,
            apply=True,
        )

    def source_edit() -> None:
        (env.root / "mod.py").write_text("VALUE = 2\n", encoding="utf-8")

    return {
        "archive": archive,
        "stamped_expiry": expiry,
        "content_edit": edit,
        "source_edit": source_edit,
    }


def test_t08_hybrid_revalidates_after_embedding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for access, ops in (
        ("ask_only", ("ask", "list", "expand")),
        ("write_capable", WRITE_OPS),
    ):
        cache_write = access == "write_capable"
        # Each selected-row change during `embed_fn` -> restart with zero items.
        for mutation in ("archive", "stamped_expiry", "content_edit", "source_edit"):
            env = _anchored_env(tmp_path, monkeypatch, f"{access}-{mutation}", ops)
            action = _mutations(env)[mutation]
            env.on_embed = lambda call, batch, action=action: (
                action() if call == 1 else None
            )
            page = tool_call(env, "recall", request=hy(), cache_write=cache_write)
            assert page.code == "E_RESTART", (access, mutation, page.code, page.data)
            assert page.ids == []

        # Revocation during embedding -> permission denial, zero items.
        revoked = make_env(tmp_path, monkeypatch, name=f"{access}-revoke", ops=ops)
        revoked.on_embed = lambda call, batch, env=revoked: (
            revoke_scope(env.auth, env.data_root, env.grant) if call == 1 else None  # type: ignore[arg-type]
        )
        page = tool_call(revoked, "recall", request=hy(), cache_write=cache_write)
        assert page.code == "E_PERMISSION", (access, page.code, page.data)
        assert page.ids == []

        # An unrelated embedding-cache write does not change the generation -> OK.
        calm = make_env(tmp_path, monkeypatch, name=f"{access}-calm", ops=ops)

        def unrelated(call: int, batch: list[str], env: Env = calm) -> None:
            if call != 1:
                return
            db = env.root / ".rush" / "memory.db"
            with contextlib.closing(sqlite3.connect(db)) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO memory_embeddings (namespace, artifact_id, "
                    "artifact_version, content_hash, model_digest, chunking_version, "
                    "dimension, vector, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(env.root),
                        "unrelated",
                        1,
                        "0" * 64,
                        "d",
                        CHUNKING,
                        2,
                        "[1.0, 0.0]",
                        1.0,
                    ),
                )
                conn.commit()

        calm.on_embed = unrelated
        page = tool_call(calm, "recall", request=hy(), cache_write=cache_write)
        assert page.code == "OK", (access, page.code, page.data)
        assert page.ids == ["h1", "h2", "h3"]

        # A rejected task row (72-T05 applicability) mid-embedding -> restart.
        task = make_env(tmp_path, monkeypatch, name=f"{access}-reject", ops=ops)

        def reject(call: int, batch: list[str], env: Env = task) -> None:
            if call != 1:
                return
            db = env.root / ".rush" / "memory.db"
            with contextlib.closing(sqlite3.connect(db)) as conn:
                conn.execute(
                    "UPDATE memory_artifacts SET applicability = 'rejected' WHERE id = 'h1'"
                )
                conn.commit()
            preview = TypedArtifactStore.bind_store(env.root, approve=False)
            TypedArtifactStore.bind_store(
                env.root,
                approve=True,
                expected_binding_digest=preview["binding_digest"],
            )

        task.on_embed = reject
        page = tool_call(task, "recall", request=hy(), cache_write=cache_write)
        assert page.code == "E_RESTART", (
            access,
            "task_rejection",
            page.code,
            page.data,
        )
        assert page.ids == []


def test_t08_hybrid_revalidates_legacy_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The emission recheck covers the explicit-allowlist (legacy) access form too: a
    selected row archived, or its content edited, during `embed_fn` is a restart."""
    for mutation in ("archive", "content_edit"):
        env = make_env(tmp_path, monkeypatch, name=f"legacy-{mutation}", policy=False)
        action = _mutations(env)[mutation]
        env.on_embed = lambda call, batch, action=action: (
            action() if call == 1 else None
        )
        page = tool_call(
            env, "recall", request=hy(), cache_write=True, allowlist=["s1"], owner=None
        )
        assert page.code == "E_RESTART", (mutation, page.code, page.data)
        assert page.ids == []


# --- R18 ---------------------------------------------------------------------------------


def test_t08_embedding_text_hash_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.retrieval import SourceValidationMemo

    env = make_env(tmp_path, monkeypatch, ops=WRITE_OPS, rows=[("h2", "needle beta")])
    store = env.store
    assert store is not None
    module = env.root / "mod.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    _git(env.root, "add", "mod.py")
    _git(env.root, "commit", "-q", "-m", "mod")
    source_hash = SourceValidationMemo().source_hash(env.root, "mod.py")
    # Insertion order and a non-ASCII character make the stored payload text differ from the
    # sorted-key, unescaped embedding text.
    content = {"text": "needle \u00e9 anchored", "b": 2, "a": 1}
    row = write_row(
        store,
        "anchored",
        "",
        content=content,
        symbol_ref="mod.py::",
        content_hash=source_hash,
    )
    text_hash = sha_text(embedding_text_of(content))
    with contextlib.closing(sqlite3.connect(env.root / ".rush" / "memory.db")) as conn:
        payload = conn.execute(
            "SELECT payload_hash, content_hash FROM memory_artifacts WHERE id = 'anchored'"
        ).fetchone()
    assert row.id == "anchored"
    assert len({text_hash, payload[0], payload[1]}) == 3, (text_hash, payload)

    page = tool_call(env, "recall", request=hy(), cache_write=True)
    assert page.code == "OK" and "anchored" in page.ids, page.data
    persisted = {r[0]: r[2] for r in embedding_rows(env.root)}
    assert persisted["anchored"] == text_hash
    assert persisted["anchored"] not in {payload[0], payload[1]}
    # Unchanged text: the vector is reused, only the query is embedded.
    env.embed_calls.clear()
    again = tool_call(env, "recall", request=hy(), cache_write=True)
    assert again.code == "OK" and env.embedded == ["needle"]
    assert SourceValidationMemo().source_hash(env.root, "mod.py") == source_hash

    # `put_embedding` re-reads the row: a vector computed for replaced text, an older
    # version or an ungranted source is never inserted; the matching hash is.
    common: dict[str, Any] = {
        "artifact_id": "h2",
        "model_digest": DIGEST,
        "chunking_version": CHUNKING,
        "vector": [1.0, 0.0],
        "write_sources": ["s1"],
    }
    current_hash = sha_text(embedding_text_of({"text": "needle beta"}))
    # The cache_write recall above legitimately cached h2's vector; the rejected calls
    # below must add nothing to it.
    h2_before = [r for r in embedding_rows(env.root) if r[0] == "h2"]
    stale_hash = sha_text(embedding_text_of({"text": "text that was replaced"}))
    assert (
        store.put_embedding(artifact_version=1, content_hash=stale_hash, **common)
        is False
    )
    assert (
        store.put_embedding(artifact_version=7, content_hash=current_hash, **common)
        is False
    )
    assert (
        store.put_embedding(
            artifact_version=1,
            content_hash=current_hash,
            **{**common, "write_sources": ["other"]},
        )
        is False
    )
    assert [r for r in embedding_rows(env.root) if r[0] == "h2"] == h2_before
    assert (
        store.put_embedding(artifact_version=1, content_hash=current_hash, **common)
        is True
    )
    assert [r[2] for r in embedding_rows(env.root) if r[0] == "h2"] == [current_hash]

    # The text changes after the hash was taken: the old-text vector is discarded.
    store.edit(
        "h2",
        {"text": "needle beta v2"},
        expected_version=1,
        scope=SUBJECT,
        owner_scope=ALICE,
        apply=True,
    )
    assert (
        store.put_embedding(artifact_version=2, content_hash=current_hash, **common)
        is False
    )
    new_hash = sha_text(embedding_text_of({"text": "needle beta v2"}))
    assert (
        store.put_embedding(artifact_version=2, content_hash=new_hash, **common) is True
    )


# --- R19, R20 ----------------------------------------------------------------------------

TWO_IMPROVED = {"p72-q13", "p72-q14"}


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param("one_benefit_one_harm", id="one_benefit_one_harm"),
        pytest.param("missing_pair", id="missing_pair"),
        pytest.param("seeds_not_independent", id="seeds_not_independent"),
    ],
)
def test_t08_verdict_aggregation(scenario: str) -> None:
    a, b = PROVIDERS
    if scenario == "one_benefit_one_harm":
        rows = verdict_rows(a) + verdict_rows(
            b, hybrid_recall=lambda qid, split: 0.25 if split == "literal" else 1.0
        )
        per, global_verdict = aggregate(rows)
        assert per == {a: "benefit", b: "harm"}
        assert global_verdict == "harm"
    elif scenario == "missing_pair":
        # One hybrid observation absent: the pair is incomplete -> unavailable, whatever
        # the rest of that provider shows; the other provider is judged on its own rows.
        rows = [
            r
            for r in verdict_rows(a)
            if not (
                r["arm"] == "hybrid" and r["case_id"] == "p72-q07" and r["seed"] == 2
            )
        ] + verdict_rows(b)
        per, global_verdict = aggregate(rows)
        assert per == {a: "unavailable", b: "benefit"}
        assert global_verdict == "unavailable"
        # The pairing check covers all three arms: a missing metadata row counts too.
        rows = [
            r
            for r in verdict_rows(a)
            if not (
                r["arm"] == "metadata" and r["case_id"] == "p72-q20" and r["seed"] == 1
            )
        ] + verdict_rows(b)
        assert aggregate(rows)[0][a] == "unavailable"

        # Rows that differ in a pairing field are not a pair.
        def other_grants(row: dict[str, Any]) -> None:
            if row["arm"] == "hybrid" and row["case_id"] == "p72-q01":
                row["grants"] = ["network"]

        rows = verdict_rows(a, mutate=other_grants) + verdict_rows(b)
        assert aggregate(rows)[0][a] == "unavailable"
    else:
        # Two improved paraphrase cases, three identical seeds each. Seeds are averaged
        # first and the case is the bootstrap unit: 2 of 12 improved cases leave a zero
        # resample inside the interval (no benefit). Treating the 36 seed rows as
        # independent units would make the lower bound positive (a benefit).
        rows = verdict_rows(
            a,
            current_recall=lambda qid, split: 1.0 if split == "literal" else 0.0,
            hybrid_recall=lambda qid, split: (
                1.0 if split == "literal" or qid in TWO_IMPROVED else 0.0
            ),
            hybrid_pass=lambda qid, split: split == "literal" or qid in TWO_IMPROVED,
        ) + verdict_rows(b)
        per, global_verdict = aggregate(rows)
        assert per[a] == "no_benefit", per
        assert global_verdict == "no_benefit"
        # One seed per case gives the identical answer: the unit is the case.
        single = verdict_rows(
            a,
            seeds=(1,),
            current_recall=lambda qid, split: 1.0 if split == "literal" else 0.0,
            hybrid_recall=lambda qid, split: (
                1.0 if split == "literal" or qid in TWO_IMPROVED else 0.0
            ),
            hybrid_pass=lambda qid, split: split == "literal" or qid in TWO_IMPROVED,
        ) + verdict_rows(b, seeds=(1,))
        assert aggregate(single)[0][a] == "no_benefit"


def test_t08_nonretrieval_baseline_does_not_fail_hybrid_availability() -> None:
    """The five baseline cases never return a hybrid page (they have no retrieval query);
    with every `p72-` case on a hybrid page the arm is available and judged on its merits."""
    a, b = PROVIDERS
    rows = verdict_rows(a, baseline=True) + verdict_rows(b, baseline=True)
    hybrid_baseline = [
        r for r in rows if r["arm"] == "hybrid" and r["case_id"] in BASELINE_CASES
    ]
    assert len(hybrid_baseline) == 2 * len(BASELINE_CASES) * len(SEEDS)
    assert all(
        r["retrieval"] == "lexical" and not r["retrieval_required"]
        for r in hybrid_baseline
    )
    per, global_verdict = aggregate(rows)
    assert per == {a: "benefit", b: "benefit"} and global_verdict == "benefit"


def test_t08_retrieval_case_without_hybrid_page_is_unavailable() -> None:
    a, b = PROVIDERS

    def lexical_page(row: dict[str, Any]) -> None:
        if row["arm"] == "hybrid" and row["case_id"] == "p72-q15":
            row["retrieval"] = "lexical"

    per, global_verdict = aggregate(
        verdict_rows(a, mutate=lexical_page) + verdict_rows(b)
    )
    assert per[a] == "unavailable" and global_verdict == "unavailable"

    # Any case, baseline included, with a fallback page makes the arm unavailable.
    def fallback_baseline(row: dict[str, Any]) -> None:
        if row["arm"] == "hybrid" and row["case_id"] == "upload-repair":
            row["embedding_fallback_code"] = "network_not_granted"

    assert (
        aggregate(
            verdict_rows(a, baseline=True, mutate=fallback_baseline) + verdict_rows(b)
        )[0][a]
        == "unavailable"
    )

    def skipped_override(row: dict[str, Any]) -> None:
        if row["arm"] == "hybrid" and row["case_id"] == "guest-handoff":
            row["override_skipped"] = "no_request"

    assert (
        aggregate(
            verdict_rows(a, baseline=True, mutate=skipped_override) + verdict_rows(b)
        )[0][a]
        == "unavailable"
    )


# --- R24 ---------------------------------------------------------------------------------

CFG_ENDPOINTS = {
    "cfg_scheme_https": "https://127.0.0.1:{port}",
    "cfg_scheme_file": "file:///tmp/p72-embed",
    "cfg_scheme_ftp": "ftp://127.0.0.1:{port}",
    "cfg_scheme_data": "data:text/plain;base64,aGk=",
    "cfg_userinfo": "http://u:p@127.0.0.1:{port}",
    "cfg_host_localhost_suffix": "http://localhost.evil.test:{port}",
    "cfg_host_nip_io": "http://127.0.0.1.nip.io:{port}",
    "cfg_host_zero": "http://0.0.0.0:{port}",
    "cfg_host_int": "http://2130706433:{port}",
    "cfg_host_percent": "http://%31%32%37.0.0.1:{port}",
    "cfg_host_empty": "http://:{port}",
    "cfg_port_0": "http://127.0.0.1:0",
    "cfg_port_65536": "http://127.0.0.1:65536",
    # EVALUATOR decision: a config (and manifest) endpoint names its port explicitly.
    "cfg_port_absent": "http://127.0.0.1",
    "cfg_trailing_cr": "http://127.0.0.1:{port}\r",
    "cfg_trailing_lf": "http://127.0.0.1:{port}\n",
    "cfg_trailing_space": "http://127.0.0.1:{port} ",
}
CFG_MODEL_DIGEST = {
    "cfg_model_slash": ("a/b", DIGEST),
    "cfg_model_dotdot": ("a..b", DIGEST),
    "cfg_model_nul": ("a\x00b", DIGEST),
    "cfg_digest_upper": (MODEL, "ABCDEF123456"),
    "cfg_digest_11hex": (MODEL, "0123456789a"),
    "cfg_digest_65hex": (MODEL, "0" * 65),
}
CFG_INVALID_TOML = {
    "cfg_wrong_toml_type": (
        '[tools.memory]\nembedding_endpoint = 1\nembedding_model = "m"\n'
        'embedding_model_digest = "0123456789ab"\n'
    ),
    "cfg_bool": (
        '[tools.memory]\nembedding_endpoint = true\nembedding_model = "m"\n'
        'embedding_model_digest = "0123456789ab"\n'
    ),
    # A lone-surrogate escape is not a Unicode scalar value: refused at the config boundary,
    # before any network work.
    "cfg_endpoint_surrogate": (
        '[tools.memory]\nembedding_endpoint = "http://127.0.0.1:11434\\ud800"\n'
        'embedding_model = "m"\nembedding_model_digest = "0123456789ab"\n'
    ),
    "cfg_undeclared_key": (
        '[tools.memory]\nembedding_endpoint = "http://127.0.0.1:11434"\n'
        'embedding_model = "m"\nembedding_model_digest = "0123456789ab"\n'
        'embedding_bogus = "x"\n'
    ),
}
CFG_INVALID_BYTES = {
    "cfg_bom": b'\xef\xbb\xbf[tools.memory]\nembedding_model = "m"\n',
    "cfg_non_utf8": b'[tools.memory]\n# \xff\xfe\nembedding_model = "m"\n',
}
REQ_TYPES: dict[str, tuple[str, Any]] = {
    "req_endpoint_int": ("embedding_endpoint", 11434),
    "req_endpoint_bool": ("embedding_endpoint", True),
    "req_endpoint_10e400": ("embedding_endpoint", float("inf")),
    "req_endpoint_nan": ("embedding_endpoint", float("nan")),
    "req_endpoint_inf": ("embedding_endpoint", float("-inf")),
    "req_model_int": ("embedding_model", 5),
    "req_digest_int": ("embedding_model_digest", 5),
    "req_chunking_int": ("embedding_chunking_version", 5),
    "req_retrieval_bool": ("retrieval", True),
    "req_retrieval_unknown": ("retrieval", "semantic"),
    # Untrusted discriminators of every JSON shape: a list or dict never reaches a set
    # membership test or a parser and surfaces as a plain E_INPUT.
    "req_endpoint_list": ("embedding_endpoint", ["http://127.0.0.1:11434"]),
    "req_endpoint_dict": ("embedding_endpoint", {"url": "http://127.0.0.1:11434"}),
    "req_model_list": ("embedding_model", [MODEL]),
    "req_model_dict": ("embedding_model", {"name": MODEL}),
    "req_digest_list": ("embedding_model_digest", [DIGEST]),
    "req_digest_dict": ("embedding_model_digest", {"digest": DIGEST}),
    "req_chunking_list": ("embedding_chunking_version", [CHUNKING]),
    "req_chunking_dict": ("embedding_chunking_version", {"version": CHUNKING}),
    "req_retrieval_list": ("retrieval", ["hybrid"]),
    "req_retrieval_dict": ("retrieval", {"mode": "hybrid"}),
}
REQ_REJECT: dict[str, tuple[str, str]] = {
    "req_endpoint_nul": ("embedding_endpoint", "http://127.0.0.1:11434\x00"),
    "req_endpoint_surrogate": ("embedding_endpoint", "http://127.0.0.1:11434\ud800"),
    "req_endpoint_cc": ("embedding_endpoint", "http://127.0.0.1:11434\x07"),
    "req_endpoint_cf": ("embedding_endpoint", "http://127.0.0.1:11434\u200b"),
    "req_endpoint_file": ("embedding_endpoint", "file:///tmp/p72-embed"),
    "req_endpoint_ftp": ("embedding_endpoint", "ftp://127.0.0.1:21"),
    "req_endpoint_data": ("embedding_endpoint", "data:text/plain;base64,aGk="),
    "req_endpoint_userinfo": ("embedding_endpoint", "http://u:p@127.0.0.1:11434"),
    "req_endpoint_empty_host": ("embedding_endpoint", "http://:11434"),
    "req_endpoint_port0": ("embedding_endpoint", "http://127.0.0.1:0"),
    "req_endpoint_port65536": ("embedding_endpoint", "http://127.0.0.1:65536"),
    "req_endpoint_trailing_cr": ("embedding_endpoint", "http://127.0.0.1:11434\r"),
    "req_endpoint_trailing_lf": ("embedding_endpoint", "http://127.0.0.1:11434\n"),
    "req_endpoint_trailing_space": ("embedding_endpoint", "http://127.0.0.1:11434 "),
    "req_endpoint_percent_host": ("embedding_endpoint", "http://%31%32%37.0.0.1:11434"),
    "req_model_slash": ("embedding_model", "a/b"),
    "req_model_dotdot": ("embedding_model", "a..b"),
    "req_model_nul": ("embedding_model", "a\x00b"),
    "req_model_empty": ("embedding_model", ""),
    "req_model_surrogate": ("embedding_model", "a\ud800b"),
    "req_digest_surrogate": ("embedding_model_digest", "0123456789a\ud800"),
    "req_digest_upper": ("embedding_model_digest", "ABCDEF123456"),
    "req_digest_11hex": ("embedding_model_digest", "0123456789a"),
    "req_digest_65hex": ("embedding_model_digest", "0" * 65),
    "req_digest_nonhex": ("embedding_model_digest", "0123456789xz"),
    "req_chunking_nul": ("embedding_chunking_version", "a\x00b"),
    "req_chunking_cf": ("embedding_chunking_version", "a\u200bb"),
    "req_chunking_surrogate": ("embedding_chunking_version", "a\ud800b"),
}
REQ_ACCEPT = {
    "req_endpoint_https_remote": "https://embed.example.com:8443",
    "req_endpoint_nip_io": "http://127.0.0.1.nip.io:11434",
    "req_endpoint_zero": "http://0.0.0.0:11434",
    "req_endpoint_int_host": "http://2130706433:11434",
}
STUB_CASES = (
    "redirect_to_remote",
    "tags_oversize",
    "tags_non_json",
    "tags_no_models",
)
OTHER_CASES = (
    "cfg_missing",
    "cfg_case_variant_root",
    "cfg_moved_root",
    "req_owner_unhashable",
    "fill_data_root_non_path",
)
G4_NAMES = (
    *CFG_ENDPOINTS,
    *CFG_MODEL_DIGEST,
    *CFG_INVALID_TOML,
    *CFG_INVALID_BYTES,
    *REQ_TYPES,
    *REQ_REJECT,
    *REQ_ACCEPT,
    *STUB_CASES,
    *OTHER_CASES,
)


def _g4_params() -> list[Any]:
    params: list[Any] = [pytest.param(name, id=name) for name in G4_NAMES]
    params.append(
        pytest.param(
            "cfg_symlink_loop", marks=pytest.mark.posix_only, id="cfg_symlink_loop"
        )
    )
    return params


def _no_effects(env: Env, before: dict[str, Any]) -> None:
    assert env.embed_calls == [] and env.tags_calls == [] and env.urlopen_calls == []
    assert effects(env) == before


@pytest.mark.parametrize("case", _g4_params())
def test_t08_g4_embedding_fields(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_engine: Callable[..., StubEngine],
) -> None:
    if case in CFG_ENDPOINTS:
        engine = stub_engine()
        env = make_env(tmp_path, monkeypatch, patch_engine=False)
        port = engine.url.rsplit(":", 1)[1]
        write_config(env.root, endpoint=CFG_ENDPOINTS[case].replace("{port}", port))
        install_verdict(monkeypatch)
        for request in (lex(retrieval="hybrid"), lex()):
            page = tool_call(env, "recall", request=request)
            assert_fallback(page, "endpoint_not_loopback")
            assert page.ids == ["h1", "h2"], (case, page.data)
        assert engine.requests == [], (case, engine.requests)
    elif case in CFG_MODEL_DIGEST:
        engine = stub_engine()
        env = make_env(tmp_path, monkeypatch, patch_engine=False)
        model, digest = CFG_MODEL_DIGEST[case]
        write_config(env.root, endpoint=engine.url, model=model, digest=digest)
        install_verdict(monkeypatch)
        page = tool_call(env, "recall", request=lex(retrieval="hybrid"))
        assert_fallback(page, "model_digest_mismatch")
        assert page.ids == ["h1", "h2"]
        assert engine.requests == [], (case, engine.requests)
    elif case in CFG_INVALID_TOML or case in CFG_INVALID_BYTES:
        from rush.config import RushConfigError, load_config

        env = make_env(tmp_path, monkeypatch)
        config = env.root / "rush.toml"
        if case in CFG_INVALID_TOML:
            config.write_text(CFG_INVALID_TOML[case], encoding="utf-8")
            with pytest.raises(RushConfigError):
                load_config(env.root)
        else:
            config.write_bytes(CFG_INVALID_BYTES[case])
            with pytest.raises((RushConfigError, UnicodeDecodeError)):
                load_config(env.root)
        page = tool_call(env, "recall", request=lex(retrieval="hybrid"))
        assert_fallback(page, "config_invalid")
        assert page.ids == ["h1", "h2"]
        # Request fields cover the whole engine identity, so a broken file is not needed.
        direct = tool_call(env, "recall", request=hy())
        assert direct.code == "OK" and direct.data["retrieval"] == "hybrid"
        assert env.urlopen_calls == []
    elif case in ("cfg_missing", "cfg_symlink_loop"):
        env = make_env(tmp_path, monkeypatch)
        install_verdict(monkeypatch)
        if case == "cfg_symlink_loop":
            link = env.root / "rush.toml"
            link.symlink_to(link)
        implicit = tool_call(env, "recall", request=lex())
        assert implicit.code == "OK" and "retrieval" not in implicit.data
        assert implicit.ids == ["h1", "h2"]
        explicit = tool_call(env, "recall", request=lex(retrieval="hybrid"))
        assert_fallback(explicit, "no_engine_configured")
        assert env.embed_calls == [] and env.tags_calls == []
    elif case == "cfg_case_variant_root":
        env = make_env(tmp_path, monkeypatch)
        write_config(env.root)
        canonical = tool_call(env, "recall", request=hy())
        canonical_lexical = tool_call(env, "recall", request=lex())
        variant_root = env.root.parent / env.root.name.swapcase()
        env.embed_calls.clear()
        variant = tool_call(env, "recall", request=hy(), root=variant_root)
        variant_lexical = tool_call(env, "recall", request=lex(), root=variant_root)
        if variant_root.exists() and variant_root.samefile(env.root):
            # The project registry and the policy grant key a root by its spelling, so a
            # case variant is judged by that earlier rule, identically for the lexical and
            # the hybrid read: configuration never turns a denied root into a hybrid page.
            assert variant.code == variant_lexical.code
            assert variant.reason == variant_lexical.reason
            assert variant.ids == variant_lexical.ids
            assert env.embed_calls == [] or variant_lexical.code == "OK"
            if variant_lexical.code == canonical_lexical.code:
                # Same project: byte-identical to the canonical-root call.
                assert variant.code == canonical.code
                assert variant.ids == canonical.ids
                assert variant.data["retrieval"] == canonical.data["retrieval"]
        else:
            # A case-sensitive file system: the variant is another, absent directory and
            # is judged like any absent project.
            absent = tool_call(env, "recall", request=hy(), root=tmp_path / "absent")
            assert variant.code == absent.code and variant.ids == absent.ids == []
            assert not variant_root.exists()
    elif case == "cfg_moved_root":
        env = make_env(tmp_path, monkeypatch)
        write_config(env.root)
        moved = tmp_path / "moved"
        env.root.rename(moved)
        lexical = tool_call(env, "recall", request=lex(), root=moved)
        hybrid = tool_call(env, "recall", request=hy(), root=moved)
        if lexical.code != "OK":
            assert hybrid.code == lexical.code and hybrid.reason == lexical.reason
            assert env.embed_calls == [] and env.urlopen_calls == []
        else:
            assert hybrid.code in {"OK", "E_EMBEDDING_UNAVAILABLE"}
            assert set(hybrid.ids) <= set(lexical.ids) | {"h3"}
    elif case in REQ_TYPES or case in REQ_REJECT:
        field, value = (REQ_TYPES | REQ_REJECT)[case]
        for transport in ("inproc", "mcp"):
            env = make_env(tmp_path, monkeypatch, name=f"project-{transport}")
            before = effects(env)
            page = tool_call(
                env, "recall", transport=transport, request=hy(**{field: value})
            )
            assert page.code == "E_INPUT", (case, transport, page.code, page.data)
            # A value the validators refuse names its field on both transports; a wrong
            # JSON type is refused by the in-process type block (`invalid field type in
            # request`, which names no field) and by the strict model (which does).
            if case in REQ_REJECT or transport == "mcp" or field == "retrieval":
                assert field in json.dumps(page.raw, default=str), (
                    case,
                    transport,
                    page.raw,
                )
            _no_effects(env, before)
    elif case in REQ_ACCEPT:
        env = make_env(tmp_path, monkeypatch)
        endpoint = REQ_ACCEPT[case]
        page = tool_call(env, "recall", request=hy(embedding_endpoint=endpoint))
        assert page.code == "OK" and page.data["retrieval"] == "hybrid", page.data
        assert {c.endpoint for c in env.embed_configs} == {endpoint}
        env.embed_calls.clear()
        off = tool_call(
            env, "recall", request=hy(embedding_endpoint=endpoint), network=False
        )
        assert_fallback(off, "network_not_granted")
        assert env.embed_calls == [] and env.urlopen_calls == []
    elif case == "redirect_to_remote":
        engine = stub_engine(embed_mode="redirect", tags_mode="redirect")
        env = make_env(tmp_path, monkeypatch, patch_engine=False)
        page = tool_call(env, "recall", request=hy(embedding_endpoint=engine.url))
        assert_fallback(page, "engine_unreachable")
        assert engine.requests == [("POST", "/api/embed")], engine.requests
        engine.requests.clear()
        write_config(env.root, endpoint=engine.url)
        install_verdict(monkeypatch)
        implicit = tool_call(env, "recall", request=lex())
        assert_fallback(implicit, "engine_unreachable")
        assert engine.requests == [("GET", "/api/tags")], engine.requests
    elif case in STUB_CASES:
        engine = stub_engine(tags_mode=case.removeprefix("tags_"))
        env = make_env(tmp_path, monkeypatch, patch_engine=False)
        write_config(env.root, endpoint=engine.url)
        install_verdict(monkeypatch)
        page = tool_call(env, "recall", request=lex())
        assert_fallback(page, "model_digest_mismatch")
        assert engine.requests == [("GET", "/api/tags")], engine.requests
    elif case == "req_owner_unhashable":
        for transport in ("inproc", "mcp"):
            env = make_env(tmp_path, monkeypatch, name=f"project-{transport}")
            before = effects(env)
            constructed = _count_store_constructions(monkeypatch)
            bad_owner: Any = {"kind": ["user"], "id": "alice"}
            if transport == "inproc":
                result = MemoryTool().run(
                    env.root,
                    operation="ask",
                    subject=SUBJECT,
                    query="needle",
                    owner_scope=bad_owner,
                    request=hy(),
                    permissions=ExecutionPermissions(network=True),
                )
            else:
                result = mcp_call(
                    {
                        "path": str(env.root),
                        "operation": "ask",
                        "subject": SUBJECT,
                        "query": "needle",
                        "owner_scope": bad_owner,
                        "request": hy(),
                        "allow_network": True,
                    }
                )
            page = out_of(result)
            assert page.code == "E_INPUT", (transport, page.code, page.raw)
            assert constructed["n"] == 0
            _no_effects(env, before)
    elif case == "fill_data_root_non_path":
        from rush.memory.retrieval import MemoryAccess

        env = make_env(tmp_path, monkeypatch, ops=WRITE_OPS)
        original = MemoryAccess.resolve.__func__  # type: ignore[attr-defined]

        def resolve(cls: Any, *args: Any, **kwargs: Any) -> Any:
            access = original(cls, *args, **kwargs)
            if access is not None and kwargs.get("operation") == "write":
                return dataclasses.replace(access, data_root=123)
            return access

        monkeypatch.setattr(MemoryAccess, "resolve", classmethod(resolve))
        before_files = digest_tree(env.root, skip=(".rush/telemetry",))
        page = tool_call(env, "recall", request=hy(), cache_write=True)
        assert page.code == "OK" and page.ids == ["h1", "h2", "h3"], (
            page.code,
            page.data,
        )
        assert page.data["retrieval"] == "hybrid"
        assert embedding_rows(env.root) == []
        assert digest_tree(env.root, skip=(".rush/telemetry",)) == before_files
    else:  # pragma: no cover - the parameter list and this chain are the same set
        raise AssertionError(f"unhandled G4 case {case}")


def test_t08_g4_validators_pure() -> None:
    """The shared validators take any value without raising: a non-string is refused."""
    from rush.memory.embeddings import (
        config_endpoint_ok,
        model_matches,
        request_endpoint_error,
        valid_chunking,
        valid_digest,
        valid_model,
    )

    junk: Any
    for junk in (None, 1, 1.5, True, b"http://127.0.0.1", ["http://127.0.0.1"], {}):
        assert config_endpoint_ok(junk) is False
        assert request_endpoint_error(junk) is not None
        assert valid_model(junk) is False
        assert valid_digest(junk) is False
        assert valid_chunking(junk) is False
    assert config_endpoint_ok("http://127.0.0.1:11434")
    assert config_endpoint_ok("http://localhost:11434/")
    assert config_endpoint_ok("http://[::1]:11434")
    for bad in (
        "http://127.0.0.1",
        "http://127.0.0.1:",
        "http://localhost",
        "http://[::1]",
        "https://127.0.0.1:11434",
        "http://127.0.0.1:11434/api",
        "http://127.0.0.1:11434?x=1",
        "http://127.0.0.1:11434#frag",
        "http://u@127.0.0.1:11434",
        "http://127.0.0.2:11434",
        "http://LOCALHOST.evil.test",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:11434\r",
        "http://127.0.0.1:11434 ",
        "",
    ):
        assert not config_endpoint_ok(bad), bad
    for good in (
        "http://127.0.0.1:11434",
        "https://embed.example.com:8443",
        "http://localhost.evil.test:11434",
        "http://0.0.0.0:11434",
        "http://2130706433:11434",
        "http://127.0.0.1.nip.io:11434",
    ):
        assert request_endpoint_error(good) is None, good
    for bad in (
        "ftp://127.0.0.1",
        "file:///etc/hosts",
        "http://u:p@host",
        "http://:11434",
        "http://%31%32%37.0.0.1:11434",
        "http://host:0",
        "http://host:65536",
        "http://host/path",
        "http://host:11434\n",
        "",
    ):
        assert request_endpoint_error(bad) is not None, bad
    assert valid_model(MODEL) and not valid_model("a/b") and not valid_model("a..b")
    assert not valid_model("") and not valid_model("x" * 257)
    assert valid_digest("0123456789ab") and valid_digest("a" * 64)
    assert (
        not valid_digest("A" * 12)
        and not valid_digest("a" * 11)
        and not valid_digest("a" * 65)
    )
    assert (
        valid_chunking(CHUNKING)
        and not valid_chunking("")
        and not valid_chunking("x" * 65)
    )
    tags = {"models": [{"name": f"{MODEL}:latest", "digest": FULL_DIGEST}]}
    assert model_matches(tags, MODEL, DIGEST)
    assert not model_matches(tags, MODEL, "ffffffffffff")
    assert not model_matches({"models": "x"}, MODEL, DIGEST)
    assert not model_matches({}, MODEL, DIGEST)
    assert not model_matches([], MODEL, DIGEST)


def test_t08_embeddings_engine_contract(
    stub_engine: Callable[..., StubEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D39/D14a client rules: batches of 32, http(s) only, no redirects, timeouts typed."""
    from rush.memory import embeddings

    assert embeddings.MAX_BATCH == 32
    assert issubclass(
        embeddings.EmbeddingEngineTimeout, embeddings.EmbeddingEngineUnavailable
    )
    for endpoint in ("file:///etc/hosts", "ftp://127.0.0.1:21", "data:text/plain,x"):
        config = embeddings.EmbeddingConfig(
            endpoint=endpoint, model=MODEL, model_digest=DIGEST
        )
        with pytest.raises(embeddings.EmbeddingEngineUnavailable):
            embeddings._embed_batch(config, ["a"])
    engine = stub_engine(embed_mode="redirect", tags_mode="redirect")
    config = embeddings.EmbeddingConfig(
        endpoint=engine.url, model=MODEL, model_digest=DIGEST
    )
    with pytest.raises(embeddings.EmbeddingEngineUnavailable):
        embeddings._embed_batch(config, ["a"])
    with pytest.raises(embeddings.EmbeddingEngineUnavailable):
        embeddings.fetch_model_tags(engine.url)
    assert engine.requests == [("POST", "/api/embed"), ("GET", "/api/tags")]

    for raised in (
        TimeoutError("timed out"),
        urllib.error.URLError(TimeoutError("timed out")),
    ):

        def timeout(*args: Any, __raised: BaseException = raised, **kwargs: Any) -> Any:
            raise __raised

        with monkeypatch.context() as scoped:
            scoped.setattr(urllib.request.OpenerDirector, "open", timeout)
            scoped.setattr(urllib.request, "urlopen", timeout)
            with pytest.raises(embeddings.EmbeddingEngineTimeout):
                embeddings._embed_batch(config, ["a"])
    good = stub_engine()
    ok = embeddings.embed_chunks(
        embeddings.EmbeddingConfig(endpoint=good.url, model=MODEL, model_digest=DIGEST),
        [f"t{i}" for i in range(70)],
    )
    assert len(ok) == 70
    assert good.requests == [("POST", "/api/embed")] * 3
    tags = embeddings.fetch_model_tags(good.url)
    assert embeddings.model_matches(tags, MODEL, DIGEST)


# --- R25 ---------------------------------------------------------------------------------


def _section(text: str, marker: str) -> tuple[str, str]:
    """(heading line, body) of the first markdown heading containing `marker`."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("#") and marker in line:
            level = len(line) - len(line.lstrip("#"))
            body = []
            for follow in lines[index + 1 :]:
                if (
                    follow.startswith("#")
                    and len(follow) - len(follow.lstrip("#")) <= level
                ):
                    break
                body.append(follow)
            return line, "\n".join(body)
    raise AssertionError(f"no heading with {marker!r}")


def test_t08_configuration_reference_lists_memory_options() -> None:
    from rush.catalog import TOOL_SPECS
    from tests.test_phase70_t25 import _CURSOR_RE

    repo = Path(__file__).resolve().parents[1]
    names = [option.name for option in TOOL_SPECS["memory"].option_specs]
    assert {
        "record",
        "embedding_endpoint",
        "embedding_model",
        "embedding_model_digest",
    } <= set(names)
    for relative in (
        "docs/CONFIGURATION.md",
        "docs/reference/configuration-reference.md",
    ):
        text = (repo / relative).read_text(encoding="utf-8")
        heading, body = _section(text, "[tools.memory]")
        for name in names:
            assert name in body, (relative, name)
        assert "observation opt-in only" not in heading, (relative, heading)
        assert not _CURSOR_RE.search(text), relative
    reference = (repo / "docs/reference/configuration-reference.md").read_text(
        encoding="utf-8"
    )
    assert "observation opt-in only" not in reference


# --- R13: the G2 route x mode matrix ---------------------------------------------------------
#
# Cell ids follow the shared grammar `[<transport>.]<route>-<dimension>-<value>[-...]`
# (no equals sign). Every A cell varies one dimension off this baseline (brief section 5.1):
# policy access `ok`, explicit `retrieval: "hybrid"` with explicit request embedding fields,
# network on, cache_write off, store present, grant `exact` (`ask, list, expand`), rows `h1`,
# `h2`, `h3` active, a loopback engine that answers, query `needle`.

BASELINE = {
    "retrieval": "hybrid",
    "access": "policy",
    "policy_state": "ok",
    "store": "present",
    "grant_ops": "exact",
    "row_state": "active",
    "network": "on",
    "cache_write": "off",
    "config": "none",
    "engine": "ok",
    "cursor": "none",
    "query": "needle",
    "mode": "ordinary",
    "representation": "none",
    "apply": "none",
    "ack": "none",
    "capability_ids": "none",
}

# (id suffix, dimension overrides)
A_DIMENSIONS: tuple[tuple[str, dict[str, str]], ...] = (
    ("retrieval-lexical", {"retrieval": "lexical"}),
    ("retrieval-hybrid", {}),
    ("retrieval-implicit_default", {"retrieval": "implicit_default"}),
    ("retrieval-implicit_none", {"retrieval": "implicit_none"}),
    ("retrieval-implicit_malformed", {"retrieval": "implicit_malformed"}),
    ("access-legacy_allowlist", {"access": "legacy_allowlist"}),
    ("access-overlay", {"access": "overlay"}),
    ("policy_state-missing_no_marker", {"policy_state": "missing_no_marker"}),
    ("policy_state-missing_marker", {"policy_state": "missing_marker"}),
    ("policy_state-invalid", {"policy_state": "invalid"}),
    ("mode-historical", {"mode": "historical"}),
    ("representation-utf8", {"representation": "utf8"}),
    ("store-absent", {"store": "absent"}),
    ("store-old_schema", {"store": "old_schema"}),
    ("apply-apply", {"apply": "apply"}),
    (
        "cache_write-on-grant_ops-write",
        {"cache_write": "on", "grant_ops": "write"},
    ),
    ("cache_write-on-grant_ops-exact", {"cache_write": "on"}),
    ("network-off", {"network": "off"}),
    ("grant_ops-missing_one", {"grant_ops": "missing_one"}),
    ("row_state-archived", {"row_state": "archived"}),
    ("row_state-expired", {"row_state": "expired"}),
    ("row_state-tampered", {"row_state": "tampered"}),
    ("row_state-rejected", {"row_state": "rejected"}),
    ("row_state-pending", {"row_state": "pending"}),
    ("config-non_loopback", {"config": "non_loopback"}),
    ("config-verdict_digest_mismatch", {"config": "verdict_digest_mismatch"}),
    ("config-tags_digest_mismatch", {"config": "tags_digest_mismatch"}),
    ("engine-unreachable", {"engine": "unreachable"}),
    ("engine-timeout", {"engine": "timeout"}),
    ("engine-nan", {"engine": "nan"}),
    ("engine-wrong_dimension", {"engine": "wrong_dimension"}),
    ("engine-wrong_count", {"engine": "wrong_count"}),
    ("cursor-explicit_hybrid", {"cursor": "explicit_hybrid"}),
    ("cursor-implicit_default", {"cursor": "implicit_default"}),
    ("query-empty", {"query": "empty"}),
    ("ack-present", {"ack": "present"}),
    ("capability_ids-selected", {"capability_ids": "selected"}),
)
A_OPS = ("ask", "recall", "list")
A_TRANSPORTS = ("inproc", "mcp")


@dataclasses.dataclass(frozen=True)
class Cell:
    transport: str
    op: str
    suffix: str
    dims: tuple[tuple[str, str], ...]

    @property
    def dim(self) -> dict[str, str]:
        return {**BASELINE, **dict(self.dims)}

    @property
    def ident(self) -> str:
        return f"{self.transport}.{self.op}-{self.suffix}"


def a_cells() -> list[Any]:
    cells = []
    for transport in A_TRANSPORTS:
        for op in A_OPS:
            for suffix, dims in A_DIMENSIONS:
                if suffix == "query-empty" and op != "list":
                    continue
                cell = Cell(transport, op, suffix, tuple(sorted(dims.items())))
                cells.append(pytest.param(cell, id=cell.ident))
    return cells


def a_call_request(cell: Cell) -> dict[str, Any]:
    d = cell.dim
    retrieval = d["retrieval"]
    if retrieval == "hybrid":
        request = hy()
    elif retrieval == "lexical":
        request = lex(retrieval="lexical")
    else:
        request = lex()
    if d["mode"] == "historical":
        request["archive_mode"] = "historical"
    if d["representation"] != "none":
        request["representation"] = d["representation"]
    if d["apply"] != "none":
        request["apply"] = True
    if d["ack"] == "present":
        request["ack"] = [{"id": "h1", "version": 1}]
    if d["capability_ids"] == "selected":
        request["capability_ids"] = ["h1"]
    return request


def a_apply_state(env: Env, cell: Cell) -> None:
    """The policy-file states act on the shared data root, so they are applied once, after
    every project of the cell (a lexical twin included) has its grant."""
    state = cell.dim["policy_state"]
    if state == "missing_marker":
        env.auth.policy_path(data_root=env.data_root).unlink()
    elif state == "invalid":
        env.auth.policy_path(data_root=env.data_root).write_bytes(b"{")


def a_build_env(
    cell: Cell, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "project"
) -> Env:
    d = cell.dim
    needed = "list" if cell.op == "list" else "ask"
    ops: tuple[str, ...] = (
        WRITE_OPS if d["grant_ops"] == "write" else ("ask", "list", "expand")
    )
    if d["grant_ops"] == "missing_one":
        ops = tuple(o for o in ops if o != needed)
    policy = d["access"] == "policy" and d["policy_state"] != "missing_no_marker"
    owner = ALICE
    overlay = d["access"] == "overlay"
    if overlay:
        from rush.memory.authorization import user_overlay_owner_scope

        owner = user_overlay_owner_scope(data_root=default_data_root())
        ops = (*ops, "overlay_read")
    env = make_env(
        tmp_path,
        monkeypatch,
        name=name,
        ops=ops,
        owner=owner,
        policy=policy or overlay,
        store=d["store"] != "absent",
    )
    if d["store"] == "old_schema":
        drop_payload_columns(env.root / ".rush" / "memory.db")
    state = d["row_state"]
    if state != "active":
        if state == "archived":
            assert env.store is not None
            env.store.archive(
                "h2", expected_version=1, scope=SUBJECT, owner_scope=owner, apply=True
            )
        elif state == "expired":
            stamp_expiry(env.root, "h2")
        elif state == "tampered":
            tamper(env.root, "h2")
        else:
            with contextlib.closing(
                sqlite3.connect(env.root / ".rush" / "memory.db")
            ) as conn:
                conn.execute(
                    "UPDATE memory_artifacts SET applicability = ? WHERE id = 'h2'",
                    (state,),
                )
                conn.commit()
            preview = TypedArtifactStore.bind_store(env.root, approve=False)
            TypedArtifactStore.bind_store(
                env.root,
                approve=True,
                expected_binding_digest=preview["binding_digest"],
            )
    retrieval = d["retrieval"]
    config = d["config"]
    if (
        retrieval == "implicit_default"
        or config != "none"
        or d["cursor"] == "implicit_default"
    ):
        write_config(
            env.root,
            endpoint="http://embed.example.com:11434"
            if config == "non_loopback"
            else ENDPOINT,
        )
        install_verdict(
            monkeypatch,
            {**VERDICT, "model_digest": "ffffffffffff"}
            if config == "verdict_digest_mismatch"
            else None,
        )
        if config == "tags_digest_mismatch":
            env.tags = tags_payload(digest="f" * 64)
    if retrieval == "implicit_malformed":
        write_config(env.root, raw="[tools.memory]\nembedding_endpoint = 1\n")
    engine = d["engine"]
    if engine == "unreachable":
        from rush.memory.embeddings import EmbeddingEngineUnavailable

        env.engine_error = EmbeddingEngineUnavailable("down")
    elif engine == "timeout":
        from rush.memory import embeddings

        timeout_error = getattr(
            embeddings, "EmbeddingEngineTimeout", embeddings.EmbeddingEngineUnavailable
        )
        env.engine_error = timeout_error("slow")
    elif engine == "nan":
        env.vector_fn = lambda batch: [[float("nan"), 0.0, 0.0, 0.0] for _ in batch]
    elif engine == "wrong_dimension":
        env.vector_fn = lambda batch: [
            [1.0, 0.0] if i == 0 else [1.0, 0.0, 0.0, 0.0] for i, _ in enumerate(batch)
        ]
    elif engine == "wrong_count":
        env.vector_fn = lambda batch: [list(v) for v in f8_vectors(batch)][:-1]
    return env


def a_call(env: Env, cell: Cell, request: dict[str, Any], **overrides: Any) -> Out:
    d = cell.dim
    kwargs: dict[str, Any] = {
        "transport": cell.transport,
        "request": request,
        "network": d["network"] == "on",
        "cache_write": d["cache_write"] == "on",
        "query": "" if d["query"] == "empty" else "needle",
    }
    if d["access"] == "legacy_allowlist":
        kwargs["allowlist"] = ["s1"]
        kwargs["owner"] = None
    kwargs.update(overrides)
    return tool_call(env, cell.op, **kwargs)


DENIAL_SUFFIXES = (
    "policy_state-missing_no_marker",
    "policy_state-missing_marker",
    "policy_state-invalid",
    "grant_ops-missing_one",
    "store-old_schema",
)


def test_t08_route_mode_matrix_dimensions_are_unique() -> None:
    idents = [p.id for p in a_cells()]
    assert len(idents) == len(set(idents))
    assert all("=" not in i for i in idents)


@pytest.mark.parametrize("cell", a_cells())
def test_t08_route_mode_matrix(
    cell: Cell, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = cell.dim
    env = a_build_env(cell, tmp_path, monkeypatch)
    suffix = cell.suffix
    twin_suffixes = {*DENIAL_SUFFIXES, "access-overlay"}
    if suffix not in twin_suffixes:
        a_apply_state(env, cell)
    before = effects(env)
    request = a_call_request(cell)

    # --- strict-request cells: an unknown or unsupported key is one E_INPUT, no effect.
    if suffix in {
        "mode-historical",
        "representation-utf8",
        "apply-apply",
        "ack-present",
        "capability_ids-selected",
    }:
        key = {
            "mode-historical": "archive_mode",
            "representation-utf8": "representation",
            "apply-apply": "apply",
            "ack-present": "ack",
            "capability_ids-selected": "capability_ids",
        }[suffix]
        out = a_call(env, cell, request)
        assert out.code == "E_INPUT", (cell.ident, out.code, out.data)
        assert key in json.dumps(out.raw, default=str), (cell.ident, out.raw)
        assert (
            env.embed_calls == [] and env.urlopen_calls == [] and env.tags_calls == []
        )
        assert effects(env) == before
        return

    # --- explicit lexical: today's page, no label, no engine or network touched.
    if suffix == "retrieval-lexical":
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.ids == ["h1", "h2"], (cell.ident, out.data)
        assert not any(k in out.data for k in LABEL_KEYS), out.data
        assert (
            env.embed_calls == [] and env.urlopen_calls == [] and env.tags_calls == []
        )
        assert effects(env) == before
        return

    # --- denial cells: the hybrid read is denied exactly like its lexical twin, with no
    # embedding or network call and no effect.
    denial = {
        "policy_state-missing_no_marker": None,
        "policy_state-missing_marker": "policy_missing",
        "policy_state-invalid": "policy_invalid",
        "grant_ops-missing_one": "operation_not_granted",
        "store-old_schema": None,
    }
    if suffix in denial:
        twin_cell = Cell(
            cell.transport,
            cell.op,
            "retrieval-lexical",
            tuple(sorted({**dict(cell.dims), "retrieval": "lexical"}.items())),
        )
        twin_env = a_build_env(twin_cell, tmp_path, monkeypatch, name="twin")
        a_apply_state(env, cell)
        twin = a_call(twin_env, twin_cell, a_call_request(twin_cell))
        out = a_call(env, cell, request)
        assert out.code == twin.code, (cell.ident, out.code, twin.code, out.data)
        assert out.reason == twin.reason, (cell.ident, out.reason, twin.reason)
        assert out.ids == twin.ids == [] or suffix == "policy_state-missing_no_marker"
        if denial[suffix] is not None:
            assert out.code == "E_PERMISSION" and out.reason == denial[suffix], (
                cell.ident,
                out.code,
                out.reason,
            )
        if suffix == "store-old_schema":
            assert out.code == "E_MIGRATION", (cell.ident, out.code, out.data)
        assert (
            env.embed_calls == [] and env.urlopen_calls == [] and env.tags_calls == []
        )
        assert "retrieval" not in out.data or out.data.get("retrieval") != "hybrid"
        return

    # --- rows that must never be embedded or returned.
    if suffix.startswith("row_state-"):
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.data["retrieval"] == "hybrid", (
            cell.ident,
            out.data,
        )
        assert out.ids == ["h1", "h3"], (cell.ident, out.ids)
        assert embedding_text_of({"text": "needle beta"}) not in env.embedded
        assert effects(env) == before
        return

    # --- no store: a measured, honestly labelled empty page and no `.rush/memory.db`.
    if suffix == "store-absent":
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.ids == [], (cell.ident, out.code, out.data)
        assert out.data["retrieval"] == "hybrid" and out.data["embedded_texts"] == 0
        assert (out.data["bytes"], out.data["tokens"]) == measured(out.data)
        assert env.embed_calls == []
        assert not (env.root / ".rush" / "memory.db").exists()
        assert effects(env) == before
        return

    if suffix == "network-off":
        out = a_call(env, cell, request)
        assert_fallback(out, "network_not_granted")
        assert out.ids == ["h1", "h2"] and out.code != "E_PERMISSION"
        assert (
            env.embed_calls == [] and env.urlopen_calls == [] and env.tags_calls == []
        )
        assert effects(env) == before
        return

    if suffix.startswith("engine-"):
        out = a_call(env, cell, request)
        code = {
            "engine-unreachable": "engine_unreachable",
            "engine-timeout": "engine_timeout",
            "engine-nan": "invalid_vectors",
            "engine-wrong_dimension": "invalid_vectors",
            "engine-wrong_count": "invalid_vectors",
        }[suffix]
        assert_fallback(out, code)
        assert out.ids == ["h1", "h2"], (cell.ident, out.data)
        assert env.embed_calls, "the engine was reached"
        assert out.data["embedded_texts"] == len(env.embedded)
        assert embedding_rows(env.root) == []
        return

    if suffix == "config-non_loopback":
        out = a_call(env, cell, lex(retrieval="hybrid"))
        assert_fallback(out, "endpoint_not_loopback")
        assert (
            env.embed_calls == [] and env.urlopen_calls == [] and env.tags_calls == []
        )
        return

    if suffix == "config-verdict_digest_mismatch":
        out = a_call(env, cell, lex())
        assert out.code == "OK" and out.ids == ["h1", "h2"]
        assert not any(k in out.data for k in LABEL_KEYS), out.data
        assert env.embed_calls == [] and env.tags_calls == []
        return

    if suffix == "config-tags_digest_mismatch":
        out = a_call(env, cell, lex())
        assert_fallback(out, "model_digest_mismatch")
        assert out.ids == ["h1", "h2"]
        assert env.embed_calls == []
        return

    if suffix == "retrieval-implicit_none":
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.ids == ["h1", "h2"]
        assert not any(k in out.data for k in LABEL_KEYS), out.data
        assert (
            env.embed_calls == [] and env.tags_calls == [] and env.urlopen_calls == []
        )
        return

    if suffix == "retrieval-implicit_malformed":
        out = a_call(env, cell, request)
        assert_fallback(out, "config_invalid")
        assert out.ids == ["h1", "h2"]
        assert env.embed_calls == [] and env.urlopen_calls == []
        return

    if suffix == "retrieval-implicit_default":
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.data["retrieval"] == "hybrid", (
            cell.ident,
            out.data,
        )
        assert out.ids == ["h1", "h2", "h3"]
        assert env.tags_calls == [ENDPOINT]
        assert effects(env) == before
        return

    if suffix == "query-empty":
        out = a_call(env, cell, request)
        assert_fallback(out, "empty_query")
        assert env.embed_calls == [] and env.urlopen_calls == []
        return

    if suffix == "cursor-explicit_hybrid":
        first = a_call(env, cell, lex(limit=1))
        assert first.code == "OK" and first.data["next_cursor"] is not None, first.data
        out = a_call(env, cell, hy(limit=1, cursor=first.data["next_cursor"]))
        assert out.code == "E_INPUT", (cell.ident, out.code, out.data)
        assert env.embed_calls == []
        return

    if suffix == "cursor-implicit_default":
        first = a_call(env, cell, lex(limit=1), network=False)
        assert_fallback(first, "network_not_granted")
        assert first.data["next_cursor"] is not None and first.ids == ["h1"]
        out = a_call(env, cell, lex(limit=1, cursor=first.data["next_cursor"]))
        assert_fallback(out, "cursor_continuation")
        assert out.ids == ["h2"] and out.data["next_cursor"] is None
        assert out.data["retrieval"] != "hybrid"
        assert env.embed_calls == [] and env.urlopen_calls == []
        return

    if suffix == "access-overlay":
        twin_cell = Cell(
            cell.transport,
            cell.op,
            "retrieval-lexical",
            tuple(sorted({**dict(cell.dims), "retrieval": "lexical"}.items())),
        )
        twin_env = a_build_env(twin_cell, tmp_path, monkeypatch, name="twin")
        a_apply_state(env, cell)
        twin = a_call(twin_env, twin_cell, a_call_request(twin_cell))
        out = a_call(env, cell, request)
        if twin.code != "OK":
            assert out.code == twin.code and out.reason == twin.reason, (
                cell.ident,
                out.code,
                twin.code,
            )
            assert out.ids == [] and env.embed_calls == []
        else:
            assert out.code == "OK" and set(twin.ids) <= set(out.ids), (
                cell.ident,
                out.data,
            )
        assert env.urlopen_calls == []
        return

    if suffix == "access-legacy_allowlist":
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.data["retrieval"] == "hybrid", (
            cell.ident,
            out.data,
        )
        assert out.ids == ["h1", "h2", "h3"]
        assert effects(env) == before
        return

    if suffix == "cache_write-on-grant_ops-write":
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.ids == ["h1", "h2", "h3"], (
            cell.ident,
            out.data,
        )
        assert {r[0] for r in embedding_rows(env.root)} == {"h1", "h2", "h3"}
        return

    if suffix == "cache_write-on-grant_ops-exact":
        constructed = _count_store_constructions(monkeypatch)
        out = a_call(env, cell, request)
        assert out.code == "OK" and out.ids == ["h1", "h2", "h3"], (
            cell.ident,
            out.data,
        )
        assert embedding_rows(env.root) == []
        assert constructed["n"] == 0, constructed
        return

    # --- the baseline hybrid cell.
    assert suffix == "retrieval-hybrid", suffix
    out = a_call(env, cell, request)
    assert out.code == "OK", (cell.ident, out.code, out.data)
    assert out.data["retrieval"] == "hybrid" and out.data["next_cursor"] is None
    assert out.ids == ["h1", "h2", "h3"], (cell.ident, out.ids)
    assert set(env.embedded) == {
        embedding_text_of({"text": text}) for _, text in F8_ROWS
    } | {"needle"}
    assert out.data["embedded_texts"] == 4
    assert out.data["complete"] is True and out.data["incomplete_reason"] is None
    assert out.data["candidates_truncated"] is False
    assert (out.data["bytes"], out.data["tokens"]) == measured(out.data)
    assert env.urlopen_calls == [] and effects(env) == before
    del d


def test_t08_route_mode_matrix_stdio_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_engine: Callable[..., StubEngine],
) -> None:
    """`stdio`: a real `rush mcp serve` subprocess, one baseline cell per operation, against a
    loopback engine; explicit request endpoint (a real server cannot use test patches)."""
    engine = stub_engine()
    env = make_env(tmp_path, monkeypatch, patch_engine=False)
    ids_by_op: dict[str, list[str]] = {}
    import shutil

    scripts = Path(sys.executable).parent
    rush = next(
        (str(scripts / n) for n in ("rush", "rush.exe") if (scripts / n).exists()),
        shutil.which("rush"),
    )
    assert rush is not None, "no rush console script beside this interpreter"
    from mcp import types

    proc = subprocess.Popen(
        [rush, "mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=env.root,
        text=True,
        bufsize=1,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        init = types.InitializeRequestParams(
            protocolVersion=types.LATEST_PROTOCOL_VERSION,
            capabilities=types.ClientCapabilities(),
            clientInfo=types.Implementation(name="t08-matrix", version="0"),
        )
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": json.loads(
                        init.model_dump_json(by_alias=True, exclude_none=True)
                    ),
                }
            )
            + "\n"
        )
        proc.stdin.flush()
        assert "result" in json.loads(proc.stdout.readline())
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        proc.stdin.flush()
        for number, op in enumerate(A_OPS, start=2):
            call = {
                "jsonrpc": "2.0",
                "id": number,
                "method": "tools/call",
                "params": {
                    "name": "rush_memory",
                    "arguments": {
                        "path": str(env.root),
                        "operation": op,
                        "subject": SUBJECT,
                        "query": "needle",
                        "owner_scope": ALICE.as_dict(),
                        "request": hy(embedding_endpoint=engine.url),
                        "allow_network": True,
                    },
                },
            }
            proc.stdin.write(json.dumps(call) + "\n")
            proc.stdin.flush()
            response = json.loads(proc.stdout.readline())
            payload = json.loads(response["result"]["content"][0]["text"])
            page = out_of(payload)
            assert page.code == "OK", (op, page.code, page.data)
            assert page.data["retrieval"] == "hybrid", (op, page.data)
            ids_by_op[op] = page.ids
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    assert ids_by_op == {op: ["h1", "h2", "h3"] for op in A_OPS}
    assert [r for r in engine.requests if r[0] == "POST"], (
        "the subprocess reached the engine"
    )


def test_t08_route_mode_matrix_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dashboard`: `_dispatch_memory_query` with `arguments.retrieval`. Hybrid needs the
    dashboard `network` grant; the embedding identity comes from `rush.toml` (the dashboard
    sends no embedding fields); no network grant is a dashboard refusal, as before."""
    from rush.dashboard.server import _ActionDenied, _dispatch_memory_query

    env = make_env(tmp_path, monkeypatch)
    write_config(env.root)
    from rush.workflows.projects import resolve_project

    project_id = resolve_project(env.root, data_root=env.data_root)["project_id"]
    arguments = {
        "mode": "recall",
        "subject": SUBJECT,
        "query": "needle",
        "session_allowlist": ["s1"],
        "retrieval": "hybrid",
    }
    status, body = _dispatch_memory_query(project_id, arguments, {"network": True})
    page = out_of(body)
    assert status == 200, (status, body)
    assert page.data["retrieval"] == "hybrid" and page.ids == ["h1", "h2", "h3"], (
        page.data
    )
    lexical = dict(arguments, retrieval="lexical")
    _status, body = _dispatch_memory_query(project_id, lexical, {})
    lex_page = out_of(body)
    assert lex_page.ids == ["h1", "h2"] and "retrieval" not in lex_page.data
    with pytest.raises(_ActionDenied):
        _dispatch_memory_query(project_id, arguments, {})


# --- producer-staged cells (v2, schema-2 consumers) ----------------------------------------
#
# Their producers (72-T06 v2 read models, 72-T07 consumers) are earlier packets built in other
# worktrees. Until they land, each v2 cell is the single strict-model E_INPUT cell naming the
# absent field; the cell ids end `-producer-<task>` and the producer's integration flips them.


@pytest.mark.parametrize("op", A_OPS)
def test_t08_route_mode_matrix_v2_producer_72_t06(
    op: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.mcp_support.request_models import validate_and_normalize

    env = make_env(tmp_path, monkeypatch)
    arguments = {
        "path": str(env.root),
        "operation": op,
        "subject": SUBJECT,
        "query": "needle",
        "schema_version": 2,
        "retrieval": "hybrid",
    }
    outcome = validate_and_normalize("rush_memory", arguments)
    if outcome.rejected:
        text = json.dumps(outcome.result, default=str)
        assert "schema_version" in text or "retrieval" in text, text
        assert env.embed_calls == []
        return
    # The producer landed: the v2 read model carries `retrieval`; a hybrid read behaves as v1.
    page = out_of(mcp_call(arguments | {"allow_network": True}))
    assert page.data["retrieval"] == "hybrid" and page.ids == ["h1", "h2", "h3"], (
        page.data
    )


# --- A (schema-2 consumers): CLI list, TUI refresh, dashboard browse and query --------------
#
# 72-T07 turns these into request-bearing consumers (a schema-2 `list` request). They send no
# `retrieval` field, so the implicit default applies through the shared memory code: with the
# hybrid-default config, the verdict constant and no network grant, each page is the
# authorized lexical page labelled `network_not_granted`, with zero network calls. Until the
# 72-T07 producer lands in the tree a route sends a request-less `list`; the assertion that
# names the missing schema-2 request is the one that fails (UPSTREAM_PENDING 72-T07).

SCHEMA2_CONSUMERS = ("cli_list", "tui_refresh", "dashboard_browse", "dashboard_query")


def _spy_memory_run(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[dict[str, Any], Any]]:
    calls: list[tuple[dict[str, Any], Any]] = []
    original = MemoryTool.run

    def recording(self: Any, path: Any, **kwargs: Any) -> Any:
        result = original(self, path, **kwargs)
        calls.append((dict(kwargs), result))
        return result

    monkeypatch.setattr(MemoryTool, "run", recording)
    return calls


def _drive_tui_refresh(env: Env) -> None:
    from rush.tui import ProjectState, ScanActions, TuiState, _memory_refresh

    def noop(*_args: object, **_kwargs: object) -> None:
        """Unused injectable seam."""

    actions = ScanActions(
        noop, noop, noop, noop, noop, noop, noop, list, memory_run=MemoryTool().run
    )
    project = ProjectState(name="p", root=env.root)
    state = TuiState(projects=[project])
    state.memory_subject = SUBJECT
    state.memory_query_buffer = "needle"
    _memory_refresh(state, project, actions)


def _drive_dashboard(env: Env, route: str) -> None:
    from rush.dashboard.server import _build_memory_section, _dispatch_memory_query
    from rush.workflows.projects import resolve_project

    project_id = resolve_project(env.root, data_root=env.data_root)["project_id"]
    if route == "dashboard_browse":
        # A search, not a bare browse: an empty query is `empty_query` (brief 3.1 F2),
        # which outranks the missing network grant this route is asserted to report.
        _build_memory_section(project_id, {"query": ["needle"]})
        return
    with contextlib.suppress(Exception):
        _dispatch_memory_query(
            project_id,
            {
                "schema_version": 2,
                "subjects": [SUBJECT],
                "query": "needle",
                "limit": 8,
            },
            {},
        )


@pytest.mark.parametrize(
    "route",
    [pytest.param(r, id=f"{r}-producer-72-T07") for r in SCHEMA2_CONSUMERS],
)
def test_t08_route_mode_matrix_schema2_consumers(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, monkeypatch)
    write_config(env.root)
    install_verdict(monkeypatch)
    calls = _spy_memory_run(monkeypatch)
    if route == "cli_list":
        _cli("list", SUBJECT, "needle", "--session", "s1", "--json")(env)
    elif route == "tui_refresh":
        _drive_tui_refresh(env)
    else:
        _drive_dashboard(env, route)
    lists = [(k, r) for k, r in calls if k.get("operation") == "list"]
    assert lists, (route, "the route issued no MemoryTool list call")
    kwargs, result = lists[-1]
    request = kwargs.get("request")
    assert isinstance(request, dict) and request.get("schema_version") == 2, (
        f"UPSTREAM_PENDING 72-T07: {route} sends no schema-2 list request",
        sorted(kwargs),
    )
    assert "retrieval" not in request, (route, request)
    data = result["raw"]["data"]
    assert data["retrieval"] == "lexical", (route, data)
    assert data["embedding_status"] == "skipped", (route, data)
    assert data["embedding_fallback_code"] == "network_not_granted", (route, data)
    assert data["hybrid_unavailable_reason"] == FALLBACK_TEXT["network_not_granted"]
    text = json.dumps(result["raw"], default=str)
    assert "h1" in text and "h2" in text and "h3" not in text, (route, text[:400])
    assert env.embed_calls == [] and env.tags_calls == [] and env.urlopen_calls == []
    assert embedding_rows(env.root) == []


# --- B: request-bearing operations without a retrieval field --------------------------------

B_OPERATIONS = (
    "expand",
    "related",
    "link",
    "consolidate",
    "prepare",
    "resume",
    "intent",
    "recipe",
    "plan_checks",
    "last_success_diagnose",
    "handoff",
    "receive",
    "verify_attempt",
    "write",
    "promote",
    "maintain",
    "edit",
    "archive",
    "delete",
)
B_ABSENT = (
    ("history", "72-T06"),
    ("explain", "72-T06"),
    ("preference", "72-T05"),
    ("capsule", "73-T09"),
    ("import", "73-T09"),
)


def _b_arguments(op: str, root: Path) -> dict[str, Any]:
    from tests.test_phase70_t6 import MEMORY_OPERATIONS

    fields = next((f for name, f, _d in MEMORY_OPERATIONS if name == op), {})
    arguments: dict[str, Any] = {
        "path": str(root),
        "operation": op,
        **json.loads(json.dumps(fields)),
    }
    request = arguments.get("request")
    if isinstance(request, dict):
        request["retrieval"] = "hybrid"
    else:
        arguments["request"] = {"retrieval": "hybrid"}
    return arguments


@pytest.mark.parametrize("op", B_OPERATIONS)
@pytest.mark.parametrize("transport", A_TRANSPORTS)
def test_t08_route_mode_matrix_non_retrieval_rejects_field(
    op: str, transport: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only `ask`/`recall`/`list` accept `retrieval`; every other request-bearing operation
    answers one `E_INPUT` naming it, before any effect, embedding or network call."""
    env = make_env(tmp_path, monkeypatch, ops=WRITE_OPS)
    before = effects(env)
    arguments = _b_arguments(op, env.root)
    arguments["allow_network"] = True
    arguments["allow_cache_write"] = True
    if transport == "inproc":
        kwargs = {
            k: v
            for k, v in arguments.items()
            if k not in {"path", "operation", "allow_network", "allow_cache_write"}
        }
        result = MemoryTool().run(
            env.root,
            operation=cast(MemoryOperation, op),
            permissions=ExecutionPermissions(
                network=True, cache_write=True, artifact_write=True, build=True
            ),
            **kwargs,
        )
    else:
        result = mcp_call(arguments)
    page = out_of(result)
    assert page.code == "E_INPUT" or result.get("status") == "error", (
        op,
        transport,
        page.raw,
    )
    if page.code == "E_INPUT":
        text = json.dumps(page.raw, default=str)
        # `write`, `promote` and `maintain` take named parameters, so the strict MCP model
        # refuses the whole `request` object rather than the key inside it.
        assert "retrieval" in text or "request" in text, (op, transport, page.raw)
    assert env.embed_calls == [] and env.urlopen_calls == [] and env.tags_calls == []
    assert effects(env) == before, (op, transport)


@pytest.mark.parametrize(
    ("op", "producer"),
    [pytest.param(op, task, id=f"{op}-producer-{task}") for op, task in B_ABSENT],
)
def test_t08_route_mode_matrix_non_retrieval_producer_ops(
    op: str, producer: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.tools.memory import VALID_OPERATIONS

    env = make_env(tmp_path, monkeypatch, ops=WRITE_OPS)
    before = effects(env)
    arguments = {
        "path": str(env.root),
        "operation": op,
        "request": {"retrieval": "hybrid"},
    }
    if op in VALID_OPERATIONS:
        page = out_of(mcp_call(arguments | {"allow_network": True}))
        assert page.code == "E_INPUT", (op, page.raw)
    else:
        from rush.mcp_support.request_models import validate_and_normalize

        outcome = validate_and_normalize("rush_memory", arguments)
        assert outcome.rejected, (
            f"{op} is accepted before its producer {producer} landed"
        )
    assert env.embed_calls == [] and env.urlopen_calls == []
    assert effects(env) == before


# --- C: the restricted receiver bridge ------------------------------------------------------


@pytest.mark.parametrize(
    "op", ["receive", "expand", "related", "resume", "ask", "recall", "list"]
)
def test_t08_route_mode_matrix_bridge(
    op: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.mcp_support.tool_registry import build_memory_bridge_handler

    correctness = importlib.import_module("tests.test_phase72_memory_correctness")

    env = make_env(tmp_path, monkeypatch, ops=WRITE_OPS)
    prepared = correctness._prepare_handoff(
        env.root, ids=("h1",), receiver_namespace="s1"
    )
    assert out_of(prepared).code == "OK", prepared
    session_id, capability = correctness._session_of(prepared)
    handler = build_memory_bridge_handler(
        root=env.root, session_id=session_id, capability=capability
    )
    constructed = _count_store_constructions(monkeypatch)
    before = effects(env)
    request = {"retrieval": "hybrid", "id": "h1", "version": 1}
    raw = handler(op, request)
    code = raw.get("code")
    if op in {"ask", "recall", "list"}:
        assert code == "E_PERMISSION", raw
        assert constructed["n"] == 0
    else:
        assert code == "E_INPUT", (op, raw)
        assert "retrieval" in json.dumps(raw, default=str)
    assert env.embed_calls == [] and env.urlopen_calls == []
    assert effects(env) == before


# --- D: routes without a retrieval field ----------------------------------------------------
#
# Every route that has no `retrieval` field must be untouched by the T08 default: with a
# `rush.toml` holding the three embedding options, a patched verdict and the network granted
# where the route takes permissions, its output is byte-identical (minus `duration_ms`) to the
# same call without `rush.toml`, and no embedding, tags or network request is made.


def _normalized(value: Any) -> str:
    volatile = {"duration_ms", "elapsed_ms", "generated_at", "now", "timestamp"}

    def scrub(item: Any) -> Any:
        if isinstance(item, dict):
            return {k: scrub(v) for k, v in item.items() if k not in volatile}
        if isinstance(item, (list, tuple)):
            return [scrub(v) for v in item]
        return item

    return json.dumps(scrub(value), sort_keys=True, default=str)


def _legacy(op: str) -> Callable[[Env], Any]:
    def drive(env: Env) -> Any:
        return MemoryTool().run(
            env.root,
            operation=cast(MemoryOperation, op),
            subject=SUBJECT,
            query="needle",
            session_allowlist=["s1"],
            owner_scope=ALICE.as_dict(),
            permissions=ExecutionPermissions(network=True),
        )

    return drive


def _cli(*args: str) -> Callable[[Env], Any]:
    def drive(env: Env) -> Any:
        from click.testing import CliRunner

        from rush.cli import cli

        previous = os.getcwd()
        os.chdir(env.root)
        try:
            result = CliRunner().invoke(cli, ["memory", *args])
        finally:
            os.chdir(previous)
        try:
            body: Any = json.loads(result.output)
        except ValueError:
            body = result.output
        return {"exit": result.exit_code, "output": body}

    return drive


def _drive_overview(env: Env) -> Any:
    from rush.tools.memory import memory_overview

    return dict(
        memory_overview(env.root, offset=0, generation=None, include_internal=False)
    )


def _drive_status(env: Env) -> Any:
    from rush.tools.status import _memory

    return _memory(env.root)


def _drive_read_visible(env: Env) -> Any:
    from rush.memory.retrieval import MemoryAccess, read_visible

    access = MemoryAccess.resolve(
        env.root, operation="ask", owner_scope=ALICE, data_root=env.data_root
    )
    assert access is not None
    pages = read_visible(env.root, [(SUBJECT, "needle")], access=access)
    return [[a.id for a in page] for page in pages]


def _drive_telemetry(env: Env) -> Any:
    from rush.token_economy.telemetry import read_summary_readonly

    return read_summary_readonly(env.root)


def _drive_registry(env: Env) -> Any:
    from rush.workflows.projects import _readonly_memory_counts

    return _readonly_memory_counts(env.root, include_internal=False)


def _drive_preference(env: Env) -> Any:
    from rush.memory.preference_store import get_preference_readonly

    return get_preference_readonly(env.root, "k", "default")


def _drive_compare(env: Env) -> Any:
    from rush.memory.experience import compare_last_success

    return compare_last_success(project_root=env.root, behavior_id="b1", conditions={})


def _drive_attribution(env: Env) -> Any:
    from rush.session_memory import find_attribution_link

    return find_attribution_link(env.root, "f1")


D_DRIVERS: dict[str, Callable[[Env], Any]] = {
    "memory_legacy_ask": _legacy("ask"),
    "memory_legacy_recall": _legacy("recall"),
    "memory_legacy_list": _legacy("list"),
    "cli_memory_ask": _cli("ask", SUBJECT, "needle", "--session", "s1", "--json"),
    "cli_memory_recall": _cli("recall", SUBJECT, "needle", "--session", "s1", "--json"),
    "cli_memory_overview": _cli("--json"),
    "overview": _drive_overview,
    "status": _drive_status,
    "retrieval_helper": _drive_read_visible,
    "telemetry_readers": _drive_telemetry,
    "project_registry_readers": _drive_registry,
    "preferences": _drive_preference,
    "experience": _drive_compare,
    "session_memory": _drive_attribution,
}


@pytest.mark.parametrize("route", [pytest.param(r, id=r) for r in D_DRIVERS])
def test_t08_route_mode_matrix_no_field(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, monkeypatch)
    install_verdict(monkeypatch)
    drive = D_DRIVERS[route]
    without = _normalized(drive(env))
    write_config(env.root)
    with_config = _normalized(drive(env))
    assert with_config == without, route
    assert env.embed_calls == [] and env.tags_calls == [] and env.urlopen_calls == [], (
        route
    )


FORBIDDEN_NAMES = frozenset(
    {
        "urlopen",
        "urlretrieve",
        "build_opener",
        "OpenerDirector",
        "embed_chunks",
        "_embed_batch",
        "fetch_model_tags",
        "hybrid_page",
        "hybrid_candidates",
        "EmbeddingConfig",
        "HYBRID_DEFAULT_VERDICT",
    }
)
FORBIDDEN_TEXT = (
    "embedding_endpoint",
    "embedding_model",
    "/api/embed",
    "/api/tags",
)
RETRIEVAL_ROUTE_FUNCTIONS = {
    ("tools/memory.py", "_compact_query"),
    ("tools/memory.py", "_compact_page"),
}


def _no_field_pairs() -> list[Any]:
    repo = Path(__file__).resolve().parents[1]
    inventory = json.loads(
        (
            repo / "tests" / "fixtures" / "phase72" / "memory_route_inventory.json"
        ).read_text(encoding="utf-8")
    )
    pairs = []
    for pair in inventory["pairs"]:
        key = (pair["module"], pair["function"])
        if key in RETRIEVAL_ROUTE_FUNCTIONS:
            continue
        if pair["function"] == "<module>":
            # An inventoried module-level node (the 72-T07 UI state and 73-T09 capsule
            # routes) is a statement, not a function body this check can inspect.
            continue
        ident = f"{pair['route']}-{pair['module'].removesuffix('.py').replace('/', '.')}.{pair['function']}"
        pairs.append(pytest.param(pair["module"], pair["function"], id=ident))
    return pairs


@pytest.mark.parametrize(("module", "function"), _no_field_pairs())
def test_t08_route_mode_matrix_no_field_static(module: str, function: str) -> None:
    """Every inventoried function of a no-field route neither names the embedding client,
    the model-tags check, the verdict constant, a network opener nor an embedding option."""
    import ast

    repo = Path(__file__).resolve().parents[1]
    tree = ast.parse((repo / "src" / "rush" / module).read_text(encoding="utf-8"))
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function
    ]
    assert matches, f"{module}::{function} is no longer defined"
    for node in matches:
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name):
                assert inner.id not in FORBIDDEN_NAMES, (module, function, inner.id)
            elif isinstance(inner, ast.Attribute):
                assert inner.attr not in FORBIDDEN_NAMES, (module, function, inner.attr)
            elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                for text in FORBIDDEN_TEXT:
                    assert text not in inner.value, (module, function, text)


# --- G8 predicate rows without a named packet test -------------------------------------------


def test_t08_fallback_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief section 3.1: the first matching fallback wins, evaluated after admission and
    access resolution and before any network request."""
    from rush.memory import embeddings

    env = make_env(tmp_path, monkeypatch)
    install_verdict(monkeypatch)
    write_config(env.root)

    # F2 (empty query) outranks F3 (no network).
    page = tool_call(env, "list", query="", request=hy(), network=False)
    assert_fallback(page, "empty_query")
    # F3 (no network) outranks F4 (broken configuration) and F6 (non-loopback endpoint).
    write_config(env.root, raw="[tools.memory]\nembedding_endpoint = 1\n")
    page = tool_call(env, "recall", request=lex(retrieval="hybrid"), network=False)
    assert_fallback(page, "network_not_granted")
    write_config(env.root, endpoint="http://embed.example.com:1")
    page = tool_call(env, "recall", request=lex(retrieval="hybrid"), network=False)
    assert_fallback(page, "network_not_granted")
    # F4 (broken configuration) outranks F5 (no engine): a missing field the file cannot
    # supply is a configuration problem, not an absent engine.
    write_config(env.root, raw="[tools.memory]\nembedding_endpoint = 1\n")
    page = tool_call(env, "recall", request=lex(retrieval="hybrid"))
    assert_fallback(page, "config_invalid")
    # F6 (non-loopback) outranks F7 (invalid model or digest).
    write_config(
        env.root,
        endpoint="http://embed.example.com:1",
        model="a/b",
        digest="ABCDEF123456",
    )
    page = tool_call(env, "recall", request=lex(retrieval="hybrid"))
    assert_fallback(page, "endpoint_not_loopback")
    # F1' (cursor on an implicit read) outranks F2 (empty query) and F3 (no network).
    write_config(env.root)
    # The cursor binds the query, so it is minted and continued with the same empty query.
    first = tool_call(env, "list", query="", request=lex(limit=1), network=False)
    page = tool_call(
        env,
        "list",
        query="",
        request=lex(limit=1, cursor=first.data["next_cursor"]),
        network=False,
    )
    assert_fallback(page, "cursor_continuation")
    assert env.embed_calls == [] and env.urlopen_calls == []

    # F8: the model-tags check classifies a failing engine; F7 beats F8's mismatch only by
    # coming first, so an unreachable or slow tags endpoint never reaches the embed call.
    timeout_error = getattr(
        embeddings, "EmbeddingEngineTimeout", embeddings.EmbeddingEngineUnavailable
    )
    for error, code in (
        (embeddings.EmbeddingEngineUnavailable("down"), "engine_unreachable"),
        (timeout_error("slow"), "engine_timeout"),
    ):
        env.tags_error = error
        page = tool_call(env, "recall", request=lex())
        assert_fallback(page, code)
        assert page.ids == ["h1", "h2"]
    assert env.embed_calls == []


def test_t08_poisoned_cache_vectors_are_recomputed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cached vector that is not a nonempty list of finite non-bool numbers with a nonzero
    norm, or whose dimension disagrees with the query vector, is a cache miss."""
    env = make_env(tmp_path, monkeypatch, ops=WRITE_OPS)
    first = tool_call(env, "recall", request=hy(), cache_write=True)
    assert first.code == "OK" and len(embedding_rows(env.root)) == 3
    poisons = {
        "h1": "[NaN, 1.0, 0.0, 0.0]",
        "h2": "[0.0, 0.0, 0.0, 0.0]",
        "h3": "[true, 1.0, 0.0, 0.0]",
    }
    db = env.root / ".rush" / "memory.db"
    with contextlib.closing(sqlite3.connect(db)) as conn:
        for artifact_id, vector in poisons.items():
            conn.execute(
                "UPDATE memory_embeddings SET vector = ? WHERE artifact_id = ?",
                (vector, artifact_id),
            )
        conn.commit()
    env.embed_calls.clear()
    page = tool_call(env, "recall", request=hy(), cache_write=True)
    assert page.code == "OK" and page.ids == ["h1", "h2", "h3"], page.data
    assert set(env.embedded) == {
        embedding_text_of({"text": text}) for _, text in F8_ROWS
    } | {"needle"}
    for artifact_id in poisons:
        with contextlib.closing(sqlite3.connect(db)) as conn:
            (vector,) = conn.execute(
                "SELECT vector FROM memory_embeddings WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        text = embedding_text_of({"text": dict(F8_ROWS)[artifact_id]})
        assert json.loads(vector) == f8_vectors([text])[0], artifact_id
    # A dimension that disagrees with the query vector is invalid, not silently scored 0.
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_embeddings SET vector = '[1.0, 0.0]' WHERE artifact_id = 'h1'"
        )
        conn.commit()
    env.embed_calls.clear()
    again = tool_call(env, "recall", request=hy(), cache_write=False)
    assert again.code == "OK" and again.ids == ["h1", "h2", "h3"]
    assert embedding_text_of({"text": "needle alpha"}) in env.embedded


def test_t08_overlay_fill_follows_the_write_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overlay access: an overlay grant with `write` may fill (into the overlay's own
    storage root); without `write` nothing is persisted. A denied overlay read stays denied
    exactly like its lexical twin."""
    from rush.memory.authorization import user_overlay_owner_scope

    def vector_rows(env: Env) -> int:
        count = 0
        for base in (env.root, env.data_root):
            for db in base.rglob("memory.db"):
                with contextlib.closing(
                    sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                ) as conn:
                    try:
                        count += conn.execute(
                            "SELECT COUNT(*) FROM memory_embeddings"
                        ).fetchone()[0]
                    except sqlite3.OperationalError:
                        continue
        return count

    overlay = user_overlay_owner_scope(data_root=default_data_root())
    for name, ops, expect_fill in (
        ("with-write", (*WRITE_OPS, "overlay_read"), True),
        ("read-only", ("ask", "list", "expand", "overlay_read"), False),
    ):
        env = make_env(tmp_path, monkeypatch, name=name, ops=ops, owner=overlay)
        # 72-T05: an overlay owner's rows live in the overlay's own storage root, a fresh
        # store per case.
        overlay_root = Path(overlay.id)
        shutil.rmtree(overlay_root / ".rush", ignore_errors=True)
        overlay_store = TypedArtifactStore(overlay_root)
        for artifact_id, text in F8_ROWS:
            write_row(overlay_store, artifact_id, text, owner=overlay)
        overlay_store.close()
        twin = tool_call(
            env, "recall", request=lex(retrieval="lexical"), cache_write=True
        )
        page = tool_call(env, "recall", request=hy(), cache_write=True)
        if twin.code != "OK":
            assert page.code == twin.code and page.reason == twin.reason, name
            assert env.embed_calls == [], name
            assert vector_rows(env) == 0
            continue
        assert page.code == "OK" and page.data["retrieval"] == "hybrid", (
            name,
            page.data,
        )
        assert (vector_rows(env) > 0) is expect_fill, (name, vector_rows(env))


# --- G2a intersections (real cells; ids follow the canonical route/dimension grammar) --------


def _g2a_cells(suffix: str) -> list[Any]:
    return [
        pytest.param(t, op, id=f"{t}.{op}-{suffix}")
        for t in A_TRANSPORTS
        for op in A_OPS
    ]


def _narrow_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    """Policy grant over `s1` and `s2`; `h4` lives in `s2`."""
    env = make_env(tmp_path, monkeypatch, sources=("s1", "s2"))
    assert env.store is not None
    write_row(env.store, "h4", "needle delta", source="s2")
    return env


@pytest.mark.parametrize(
    ("transport", "op"), _g2a_cells("access-legacy_allowlist-policy_state-ok")
)
def test_t08_route_mode_matrix_legacy_with_policy_narrows(
    transport: str, op: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A policy grant plus a per-call `session_allowlist` is narrowed to that allowlist:
    only its rows are eligible, so only their texts reach the engine."""
    narrowed_env = _narrow_env(tmp_path / "narrow", monkeypatch)
    narrowed = tool_call(
        narrowed_env, op, transport=transport, request=hy(), allowlist=["s1"]
    )
    assert narrowed.code == "OK" and narrowed.data["retrieval"] == "hybrid", (
        narrowed.data
    )
    assert narrowed.ids == ["h1", "h2", "h3"], narrowed.ids
    assert embedding_text_of({"text": "needle delta"}) not in narrowed_env.embedded
    assert set(narrowed_env.embedded) == {
        embedding_text_of({"text": text}) for _, text in F8_ROWS
    } | {"needle"}
    wide_env = _narrow_env(tmp_path / "wide", monkeypatch)
    wide = tool_call(wide_env, op, transport=transport, request=hy())
    assert wide.code == "OK" and "h4" in wide.ids, wide.data
    assert embedding_text_of({"text": "needle delta"}) in wide_env.embedded


@pytest.mark.parametrize(
    ("transport", "op"), _g2a_cells("store-absent-grant_ops-revoked")
)
def test_t08_route_mode_matrix_no_store_denial_and_admission(
    transport: str, op: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent store + revoked grant is `E_PERMISSION revoked`; absent store + a byte cap
    below the hybrid minimum is `E_INPUT`: neither creates `.rush`, reaches the engine or
    the network."""
    denied = make_env(tmp_path / "denied", monkeypatch, store=False)
    assert denied.grant is not None
    revoke_scope(denied.auth, denied.data_root, denied.grant)
    before = effects(denied)
    rush_dir = denied.root / ".rush"
    # Setup already wrote `.rush/memory-policy.required`; the call must add nothing to it.
    rush_before = (
        sorted(p.name for p in rush_dir.rglob("*")) if rush_dir.exists() else []
    )
    out = tool_call(denied, op, transport=transport, request=hy())
    assert out.code == "E_PERMISSION" and out.reason == "revoked", (out.code, out.raw)
    assert not (rush_dir / "memory.db").exists()
    rush_after = (
        sorted(p.name for p in rush_dir.rglob("*")) if rush_dir.exists() else []
    )
    assert rush_after == rush_before
    assert denied.embed_calls == [] and denied.urlopen_calls == []
    assert denied.tags_calls == [] and effects(denied) == before

    capped = make_env(tmp_path / "capped", monkeypatch, store=False)
    before = effects(capped)
    capped_dir = capped.root / ".rush"
    capped_rush_before = (
        sorted(p.name for p in capped_dir.rglob("*")) if capped_dir.exists() else []
    )
    out = tool_call(capped, op, transport=transport, request=hy(max_bytes=1))
    assert out.code == "E_INPUT", (out.code, out.raw)
    assert not (capped_dir / "memory.db").exists()
    capped_rush_after = (
        sorted(p.name for p in capped_dir.rglob("*")) if capped_dir.exists() else []
    )
    assert capped_rush_after == capped_rush_before
    assert capped.embed_calls == [] and capped.urlopen_calls == []
    assert capped.tags_calls == [] and effects(capped) == before


@pytest.mark.parametrize(
    ("transport", "op"), _g2a_cells("access-overlay-grant_ops-revoked")
)
def test_t08_route_mode_matrix_overlay_revocation(
    transport: str, op: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An overlay grant revoked before the read is `E_PERMISSION revoked` with zero
    embedding calls; the same overlay grant before revocation reads hybrid."""
    from rush.memory.authorization import user_overlay_owner_scope

    overlay = user_overlay_owner_scope(data_root=default_data_root())
    env = make_env(
        tmp_path,
        monkeypatch,
        ops=("ask", "list", "expand", "overlay_read"),
        owner=overlay,
    )
    assert env.grant is not None
    live = tool_call(env, op, transport=transport, request=hy())
    if live.code == "OK":
        assert live.data["retrieval"] == "hybrid", live.data
    env.embed_calls.clear()
    revoke_scope(env.auth, env.data_root, env.grant)
    out = tool_call(env, op, transport=transport, request=hy())
    assert out.code == "E_PERMISSION" and out.reason == "revoked", (out.code, out.raw)
    assert out.ids == [] and env.embed_calls == [] and env.urlopen_calls == []


# --- G2a intersections whose route is a later packet's (72-T06 v2 list/query) ---------------


@pytest.mark.parametrize(
    "granted",
    [
        pytest.param(
            "list_and_history",
            id="mcp.list-mode-historical-grant_ops-exact_with_history-producer-72-T06",
        ),
        pytest.param(
            "list_only",
            id="mcp.list-mode-historical-grant_ops-missing_one-producer-72-T06",
        ),
    ],
)
def test_t08_route_mode_matrix_historical_compound_grant_producer_72_t06(
    granted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v2 `archive_mode: "historical"` needs the compound grant {list, history}: with it
    the archived row is embedded and listed, with `list` alone the read is
    `E_PERMISSION operation_not_granted` and nothing is embedded. Until 72-T06 lands the
    cell is the strict-model `E_INPUT` naming the absent field."""
    from rush.mcp_support.request_models import validate_and_normalize

    ops = (
        ("list", "ask", "expand", "history")
        if granted == "list_and_history"
        else (
            "list",
            "ask",
            "expand",
        )
    )
    env = make_env(tmp_path, monkeypatch, ops=ops)
    assert env.store is not None
    env.store.archive(
        "h2", expected_version=1, scope=SUBJECT, owner_scope=ALICE, apply=True
    )
    arguments = {
        "path": str(env.root),
        "operation": "list",
        "subject": SUBJECT,
        "query": "needle",
        "owner_scope": ALICE.as_dict(),
        "schema_version": 2,
        "archive_mode": "historical",
        "retrieval": "hybrid",
        "embedding_endpoint": ENDPOINT,
        "embedding_model": MODEL,
        "embedding_model_digest": DIGEST,
        "allow_network": True,
    }
    outcome = validate_and_normalize("rush_memory", arguments)
    if outcome.rejected:
        text = json.dumps(outcome.result, default=str)
        assert "schema_version" in text or "archive_mode" in text, text
        assert env.embed_calls == []
        return
    page = out_of(mcp_call(arguments))
    if granted == "list_and_history":
        assert page.code == "OK" and "h2" in page.ids, (page.code, page.data)
        assert embedding_text_of({"text": "needle beta"}) in env.embedded
    else:
        assert page.code == "E_PERMISSION", (page.code, page.data)
        assert page.reason == "operation_not_granted", page.raw
        assert page.ids == [] and env.embed_calls == []


@pytest.mark.parametrize(
    "cell",
    [
        pytest.param(
            "list",
            id="mcp.list-access-legacy_allowlist-policy_state-ok-producer-72-T06",
        )
    ],
)
def test_t08_route_mode_matrix_v2_top_level_session_allowlist_producer_72_t06(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """legacy-with-policy on v2: a top-level `session_allowlist` is `E_INPUT` (the v1
    narrowing key is not a v2 field). Until 72-T06 lands the schema-2 request itself is the
    strict-model `E_INPUT`."""
    from rush.mcp_support.request_models import validate_and_normalize

    env = make_env(tmp_path, monkeypatch)
    arguments = {
        "path": str(env.root),
        "operation": "list",
        "subject": SUBJECT,
        "query": "needle",
        "owner_scope": ALICE.as_dict(),
        "schema_version": 2,
        "session_allowlist": ["s1"],
        "retrieval": "hybrid",
    }
    outcome = validate_and_normalize("rush_memory", arguments)
    assert outcome.rejected, "v2 with a top-level session_allowlist must be refused"
    text = json.dumps(outcome.result, default=str)
    assert "session_allowlist" in text or "schema_version" in text, text
    assert env.embed_calls == [] and env.urlopen_calls == []
