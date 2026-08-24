# Rush local and optional remote model intelligence — implementation workstream

Status: proposed. Research basis: [local-model research report](innovations-memory-local-models-research-report.md), dated 2026-08-23. This workstream is narrow: intelligence assists retrieval, selection, extraction, and privacy-aware packaging. It does not create a chat product, generic model runner, hosted service, or canonical memory engine.

## 1. Fixed architecture

### 1.1 Boundaries

- Canonical truth remains Rush event/claim/receipt/repository state. Models, vectors, rerank scores, and generated text are derived candidates with provenance.
- C0 works without model files, credentials, a network, GPU, daemon, or new required dependency.
- Core intelligence API lives under `src/rush/intelligence/`; public CLI/MCP operations live once in `src/rush/tools/intelligence.py` and return `ToolResult`.
- Local engines are discovered from configured executable/package/artifact paths. They never auto-download models or bind a public listener.
- Remote requests are explicit policy-governed operations. Before every egress, the final rendered payload is redacted and scanned again. Agent callers never receive or hold credentials.

### 1.2 Required data contracts

| New type / location | Public fields and purpose |
|---|---|
| `src/rush/intelligence/models.py::ModelRef` | `capability`, `publisher`, `model_id`, immutable `revision`, `artifact_sha256`, `license`, `format`, `quantization`, `runtime`, `locality`; identifies an artifact reproducibly. |
| `CapabilityStatus` | available/degraded/skipped, hardware assessment, reason, required artifact/runtime, no secret material. |
| `IntelligenceRequest` | capability, bounded source IDs/spans, target schema, token/latency budget, privacy policy, cancellation/deadline—not arbitrary agent prompt text. |
| `IntelligenceResult` | structured value, source IDs, confidence, schema check, model/runtime provenance, token/compute metrics, redaction record, bounded error. It is never a canonical claim. |
| `IntelligenceProvider` protocol | `probe()`, `invoke()`, `close()`; capability-specific implementations for local embedding/rerank/LLM/PII and remote generation. |
| `ModelManifest` | local artifact URI, revision, SHA-256, license acceptance timestamp, runtime version, compatible hardware profiles, index compatibility ID. |
| `RemoteEgressDecision` | policy result, redaction/scanner outcomes, endpoint allowlist check, confirmation receipt; records no raw payload. |

## 2. Phase plan

### P0 — research corpus, compatibility contract, and capability scaffold

**Objective:** freeze the reproducible research harness and create no user-facing inference capability yet.

| Item | Plan |
|---|---|
| Vibecoder outcome | `rush intelligence recommend` can explain C0/C1/C2 hardware capability and that Rush remains useful with intelligence disabled. |
| Coding-agent outcome | Agents can query an explicit `intelligence_status` capability and receive `ToolResult(skipped)` rather than hidden provider behavior. |
| Included | 100+ private/synthetic corpus; C0/C1/C2 hardware detector; `ModelRef`, `CapabilityStatus`, manifest schema; benchmark runner; source/provenance fixtures. |
| Excluded | Model download, embedding/rerank, remote calls, PII model, local LLM, router, or vector index. |
| Existing dependencies | `src/rush/tools/base.py::ToolResult`/`Finding`; `src/rush/tools/__init__.py`; `src/rush/cli.py::_run_tool`; `src/rush/mcp.py::_register_tools`; `src/rush/config.py::RushConfig`; `src/rush/permissions.py`; `src/rush/safety/workspace_boundary.py::WorkspaceBoundaryGuard`. |
| Existing files to modify | `config.py`: strict `[intelligence]` parse with disabled-by-default setting; `tools/__init__.py`: register one shared tool; `cli.py` and `mcp.py`: thin bindings only; `permissions.py`: inspect/provision/invoke/remote-egress permissions; docs/config example together. |
| New files | `intelligence/models.py`, `protocols.py`, `hardware.py`, `registry.py`, `manifest.py`, `benchmark/corpus.py`, `benchmark/runner.py`, `tools/intelligence.py`; `tests/test_intelligence_*`. |
| Tests | schema round-trip; hardware profile determinism; no artifact auto-download; CLI/MCP parity; unavailable capability returns `skipped`; fixture source spans/redactions. |
| Hardware/fallback | C0 is always accepted; all other profiles are advisory. Missing accelerator/runtime never blocks core quality commands. |
| Completion | benchmark corpus/metrics schema checked in; each candidate artifact has an immutable manifest template; no production inference/network code. |
| Rollback | disable `[intelligence]`; delete only generated benchmark cache, not Rush memory. |

### P1 — C0 deterministic privacy and parsing boundary

**Objective:** make durable memory/context packaging safer before any model or remote provider exists.

| Item | Plan |
|---|---|
| Vibecoder outcome | Rush automatically states when content was redacted or retained only as a redacted reference; no account or model setup. |
| Coding-agent outcome | Structured redaction findings have detector ID, safe range/fingerprint, severity, and policy result—never secret text. |
| Included | First-party credential/PII span rules; final-projection re-scan; discovered Gitleaks adapter; Pydantic/JSON Schema validation; bounded native text/JSON/YAML/TOML/Markdown/PDF extraction. |
| Excluded | Presidio/GLiNER, OCR, Docling, model inference, remote egress, automatic remediation. |
| Existing dependencies | `src/rush/safety/redactor.py::SecretRedactor`, `workspace_boundary.py`, `permissions.py`, `tools/base.py`, `session_memory.py`, future F1 archive/write path. |
| Existing files to modify | `redactor.py`: compose deterministic span findings without changing existing redaction semantics; `permissions.py`: add `persist_sensitive`/`remote_egress`; `tools/flight_recorder.py`: store redacted policy receipt only; docs/safety guide. |
| New files | `intelligence/sensitive.py`, `secret_scan.py`, `pii_rules.py`, `parse.py`, `schemas.py`, `egress.py`; `tools/intelligence.py` operations `scan`, `parse`, `redact_preview`; tests with synthetic corpus. |
| Dependencies/license | Gitleaks is a discovered MIT executable, not a Rush dependency. Pydantic/jsonschema are added only after repository dependency policy and exact pin review. |
| Tests | 100% recall for curated high-severity secret fixtures; raw secret never in `ToolResult`/log/telemetry; malformed/oversized document bounded; parser no network/path escape; egress scan catches injected/retrieved secret. |
| Hardware/fallback | C0 CPU path; Gitleaks absence returns `skipped` but first-party rules still run. |
| Completion | pre-persistence and pre-egress enforcement passes corpus; all model/provider phases are blocked until this phase passes. |
| Rollback | turn off optional Gitleaks adapter; deterministic policy remains. |

### P2 — local embedding baseline and lexical/semantic retrieval

**Objective:** add optional local semantic retrieval while keeping SQLite evidence and FTS5 authoritative for exact/lexical recovery.

| Item | Plan |
|---|---|
| Vibecoder outcome | Opt-in provisioning presents the recommended local artifact, disk/RAM estimate, license, privacy statement, and a no-model alternative. `rush context retrieve` still works lexically if declined. |
| Coding-agent outcome | `continuity_retrieve` returns ranked source IDs/spans, ranking provenance, and token estimates; no arbitrary text dump or model secret. |
| Included | SQLite FTS5 baseline; selected P2 manifest (initial research candidates: Granite 278M and BGE-small control); ONNX Runtime/FastEmbed experimental adapter; reciprocal-rank fusion; index manifest/rebuild/delete; token-aware retrieval interface. |
| Excluded | Default vector database, remote embeddings, reranker, automatic model provisioning, model-generated summary. |
| Existing dependencies | `src/rush/token_economy/router.py::ContentRouter`, `ccr_store.py::CCRStore`, `telemetry.py::TelemetryStore`, `src/rush/codegraph/context_packer.py::ContextPacker`, `src/rush/session_memory.py`, `src/rush/memory/merkle_invalidator.py::MerkleInvalidator`. |
| Existing files to modify | token router/context packer accept a `RetrievalCandidate` input and provenance; telemetry records counts/timing only; config adds per-capability model manifest references; memory invalidator schedules explicit stale-index mark. |
| New files | `intelligence/embedding.py`, `retrieval.py`, `lexical.py`, `fusion.py`, `index.py`, `provisioning.py`, `artifacts.py`; migration/schema under the future continuity database; benchmark retrieval suite. |
| Dependencies/license | ONNX Runtime/FastEmbed only after P0 exact-pin review. Granite Apache-2.0; BGE-small MIT. No `trust_remote_code`; artifact retrieval is user-confirmed and checksum verified. |
| Tests | recall/nDCG/evidence-span precision; exact FTS fallback; offline egress proof; reindex on model/revision/config change; delete/tombstone removes vector and lexical references; Windows/Linux/macOS capability tests. |
| Hardware/fallback | C0 no model: FTS5 only. C0/C1 int8 embedding is measured. Insufficient memory -> `skipped` and FTS5 fusion excludes semantic result. |
| Completion | chosen artifact improves the locked corpus without stale/secret regressions and meets profile latency/RSS thresholds. |
| Rollback | delete derived index/model cache only; canonical source/evidence untouched. |

### P3 — enhanced retrieval and token-efficient context selection

**Objective:** decide and add only the enhanced local retrieval pieces that prove a measurable, evidence-preserving token benefit.

| Item | Plan |
|---|---|
| Vibecoder outcome | Rush explains “local enhanced retrieval used/not used,” shows token reduction and omitted-item recovery handles. |
| Coding-agent outcome | Retrieval output includes selected/omitted IDs, scores, freshness, source spans, and a recoverable token budget—not a hidden RAG prompt. |
| Included | Qwen3 embedding/reranker comparison; selected optional C1 index (`hnswlib`, USearch, or sqlite-vec); top-k-only reranking; mandatory-first context selection. |
| Excluded | BGE-M3 multi-mode default, cloud vector service, opaque vector truth, a model selection UI. |
| Existing dependencies | P2 files; `ContextPacker`, `ContentRouter`, `CCRStore`, `TelemetryStore`, continuity F3/F5 receipts/freshness/projection once implemented. |
| Existing files to modify | context packer compiles selection with recovery handles; token telemetry adds model/index manifest ID and actual tokens; `ToolResult` artifacts carry redacted retrieval trace. |
| New files | `intelligence/rerank.py`, `ann.py`, `selection.py`, `metrics.py`, `adapters/onnx.py`; tests for rank/freshness/omission. |
| Tests | reranker uses same fusion candidates; improves evidence relevance **and** reduces final context; 50% median token reduction gate; zero critical-fact loss; p95 latency/RSS within C1 profile. |
| Hardware/fallback | C1 only; disable reranker then ANN then embeddings in that order. FTS5/deterministic projection always remains. |
| Completion | one selected enhanced configuration and a versioned manifest; all losing candidates removed from runtime scope. |
| Rollback | per-capability config disable; old manifests render lexical recovery rather than silently comparing incompatible vectors. |

### P4 — bounded local utility-model intelligence

**Objective:** expose carefully constrained local inference for candidate extraction/classification/reduction without making it an authority or requirement.

| Item | Plan |
|---|---|
| Vibecoder outcome | User chooses “minimal local intelligence” or “general local intelligence”; Rush shows hardware, model/license, local-only status, and falls back safely. |
| Coding-agent outcome | Agent receives a schema-valid, evidence-linked proposed delta or `skipped`; it cannot call a generic chat endpoint or obtain local runtime control. |
| Included | Selected P4 model/runtime from Qwen3-4B/Phi-4-mini/SmolLM3 and later C2 7–8B decision; llama.cpp/Ollama/MLX user-managed adapters; schema-constrained generation comparison; candidate proposal/review path. |
| Excluded | Free-form chat, chain-of-thought retention, autonomous rule/memory promotion, tool execution by model, public local server. |
| Existing dependencies | P1 sensitive/egress pipeline, P2 retrieval, `src/rush/providers/base.py::LLMProvider` (do not overload its summary API), `ToolResult`, continuity reducer/claims/authority. |
| Existing files to modify | config permits approved manifest/runtime per capability; provider registry remains remote-provider-specific; new intelligence registry owns local model selection; CLI/MCP shared tool exposes `extract`/`classify`/`propose`. |
| New files | `intelligence/generation.py`, `structured.py`, `adapters/llama_cpp.py`, `adapters/ollama.py`, `adapters/mlx.py`, `candidate.py`, `review.py`; JSON schemas and model corpus fixtures. |
| Dependencies/license | No bundled runtime. llama.cpp MIT, Ollama MIT, MLX MIT; model card/license/revision/hash preflight required. |
| Tests | schema validity; evidence-span precision/recall; contradiction retention; hallucinated-claim rate; output token cap; cancellation/timeouts; offline loopback/egress test; no hidden reasoning/raw transcript persistence. |
| Hardware/fallback | C0: disabled. C1: 3–4B Q4 at tested context. C2: 7–8B only after hardware gate. Missing model/runtime -> deterministic extract/classify or `skipped`. |
| Completion | selected model improves locked handoff corpus without authority/privacy/token regression; every generated field is reviewable and non-canonical. |
| Rollback | disable the capability; delete derived candidate cache; canonical archive unchanged. |

### P5 — optional remote intelligence, OAuth, existing CLIs, and named routers

**Objective:** let a user choose direct API, provider-supported OAuth, or an already-authenticated local coding CLI without making Rush a credential broker, a generic agent runner, or a provider lock-in point.

| Item | Plan |
|---|---|
| Vibecoder outcome | rush intelligence provider status <name> says which of API key, official OAuth, or installed CLI is usable; it names what leaves the machine, retention caveat, model, cost if exposed, and confirmation behavior. connect --mode cli verifies a user-owned CLI profile; it does not ask Rush to obtain or display its tokens. |
| Coding-agent outcome | Agents request a named, policy-approved capability and get a bounded result/provenance receipt. They cannot see keys, OAuth tokens, CLI config paths, raw endpoint settings, or select an unapproved provider. |
| Included | Direct OpenAI, Anthropic, Gemini, Z.AI, DeepSeek, and Mistral adapters; provider-documented OAuth with user browser/PKCE flow only where supported; user-authorized CLI bridges for Codex, Claude Code, and Antigravity; user-owned Claude Code/OpenCode profiles for Z.AI and DeepSeek; named 9Router and OmniRouter verification/integration tracks; policy/capability probes and local_only, redact_before_remote, confirm_before_remote, no_retention policies. |
| Explicit routes | Codex CLI OAuth is via the user's Codex sign-in and a noninteractive JSONL bridge; Claude Code OAuth is via the user's Claude login and a bounded JSON/stream-JSON bridge; Antigravity is via the user's Google sign-in/SSH OAuth/ADC/key and agy documented headless mode. Z.AI and DeepSeek currently have official API-key/compatible-CLI routes, not a Rush-owned OAuth claim. |
| 9Router / OmniRouter | Preserve both as named candidates. P5 creates router_verification.py evidence records for exact legal entity/product, official domain, API/OAuth/CLI contract, terms, retention, provider authorization, endpoint/TLS, credential boundary, routing controls, and redaction conformance. OmniRouter also requires an explicit product/vendor selection because multiple products use the name. A named adapter/bridge follows the verified record; neither is silently converted to unsupported or an anonymous generic endpoint. |
| Excluded | OAuth/session-token extraction or copying; reading provider CLI home/config/keychain files; subscription/account pooling; automatic login/browser opening; automatic provider failover/routing; hidden CLI configuration changes; hosted Rush service. |
| Existing dependencies | src/rush/providers/base.py::LLMProvider, provider registry; permissions.py; SecretRedactor; P1 egress.py; CLI/MCP tool boundary; ToolResult; standard-library subprocess management. |
| Existing files to modify | Provider base gains no intelligence-specific semantics; config.py adds an allowlisted named-provider/CLI-profile schema without secret literals; permissions.py adds remote_egress, oauth_connect, and cli_bridge; CLI/MCP expose the same explicit connect/probe/invoke operations. |
| New files | intelligence/remote.py, credentials.py, policy.py, cli_bridge.py, oauth.py, router_verification.py, remote_audit.py; adapters/openai.py, anthropic.py, gemini.py, zai.py, deepseek.py, mistral.py, codex_cli.py, claude_cli.py, antigravity_cli.py, zai_cli.py, deepseek_cli.py, nine_router.py, omni_router.py; provider/CLI contract fixtures using mock subprocesses and mock HTTP server. |
| Dependencies/license | Official SDKs remain optional and exact-pinned only when the existing HTTP utility cannot safely implement a selected direct API. OAuth uses the provider's documented user flow; CLI auth stays inside the provider CLI/OS credential store. No model/router/CLI is a bundled Rush dependency. |
| Tests | Final payload re-scan; no key/token/config path in logs/results; cancellation/timeout/output-size limits; CLI binary allowlist and version probe; command-profile rejects writes/shell escalation; JSON/JSONL protocol validation; no credential read; no credentials/not signed in -> skipped; mock OAuth state/PKCE/redirect validation where applicable; router identity/terms/retention evidence required; endpoint SSRF/allowlist defense; no automatic cross-provider retry. |
| Hardware/fallback | Remote and CLI paths are never automatic fallback. Local-only policy denies egress even when a model/CLI is missing; capability returns skipped and C0 remains useful. |
| Completion | Each named track is visibly ready, blocked, or needs user selection with its evidence record. Direct/CLI routes pass policy fixtures before enablement; 9Router and OmniRouter stay present until their named verification records decide the concrete adapter/bridge. |
| Rollback | Disable one named provider/profile, revoke it through its provider/CLI, and remove its derived receipt/cache; no canonical data depends on its response. |

### P6 — hardening, reproducibility, and release readiness

**Objective:** make selected capabilities inspectable, reproducible, removable, and safe across machines.

| Item | Plan |
|---|---|
| Included | model/index/remote provenance inspection; usage/cost/compute telemetry without content; artifact cache management; export manifests; docs; migration; benchmark report. |
| Excluded | model marketplace, background updater, generic router, F9 coordination/learning. |
| Existing dependencies | `TelemetryStore`, `SecretRedactor`, workspace guard, config docs/examples, CLI/MCP test suites. |
| New files | `intelligence/inspect.py`, `usage.py`, `export.py`, `doctor.py`, documentation and reproducibility fixtures. |
| Completion | clean machine can reproduce capability using manifest; disabled intelligence does not change core quality-tool behavior; all selected optional engines return standard skipped behavior when removed. |

## 3. Configuration and command surface

Proposed strict configuration (names are design targets; add only after P0):

    [intelligence]
    enabled = false
    privacy_mode = "local_only" # local_only | redact_before_remote | confirm_before_remote | no_retention

    [intelligence.local.embedding]
    manifest = ".rush/models/granite-278m.manifest.json"
    runtime = "onnx"

    [intelligence.remote.openai]
    enabled = false
    credential_ref = "env:OPENAI_API_KEY"
    allowed_models = ["pinned-model-id"]

    [intelligence.cli.codex]
    enabled = false
    executable = "codex"
    profile = "read_only_jsonl"
    auth_source = "provider_cli"

    [intelligence.cli.claude]
    enabled = false
    executable = "claude"
    profile = "bounded_json"
    auth_source = "provider_cli"

    [intelligence.cli.antigravity]
    enabled = false
    executable = "agy"
    profile = "scoped_headless"
    auth_source = "provider_cli"

    [intelligence.router.nine_router]
    enabled = false
    verification_record = ".rush/intelligence/providers/9router.json"

    [intelligence.router.omni_router]
    enabled = false
    verification_record = ".rush/intelligence/providers/omnirouter.json"

CLI: `rush intelligence status|recommend|inspect|scan|parse|retrieve|provision|disable`; `rush intelligence provider status|connect|invoke <name> --mode api|oauth|cli`; and `rush intelligence router verify 9router|omnirouter`. Connect is explicit: OAuth opens only a provider-documented user flow; CLI mode only probes/uses a user-installed, already-authorized CLI without reading its credentials. MCP provides matching read/explicit-action tools via the same `src/rush/tools/intelligence.py` operation. Provision, OAuth, CLI invocation, router enablement, and any remote call require explicit user-controlled flags/permissions. All responses use `ToolResult` with findings, metrics, provenance artifacts, and `skipped` where appropriate.

## 4. First pull request

**PR title:** `feat(intelligence): add disabled capability registry and hardware/status contract`

Expected files: modify `src/rush/config.py`, `src/rush/tools/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/permissions.py`, configuration docs/example, and relevant registry tests. Add `src/rush/intelligence/{__init__,models,hardware,manifest,registry,protocols}.py`, `src/rush/tools/intelligence.py`, `tests/test_intelligence_registry.py`, `tests/test_intelligence_cli_mcp_parity.py`, and synthetic fixture definitions.

No dependency, model, network client, artifact download, provider account, or secret handling is added in this PR. Acceptance: disabled default; exact hardware result on fixtures; manifest rejects absent revision/hash/license; CLI/MCP response parity; missing capability is a structured `skipped`; no stdout corruption in stdio mode.

## 5. Decision and benchmark record

Before P2/P4/P5, record chosen and rejected candidates with source URL/research date, immutable revision, SHA-256, license, runtime/version, quantization, tested hardware, 1K/4K/8K/16K metrics, privacy policy, and corpus result. Required metrics: retrieval Recall@k/nDCG/evidence span precision; stale retrieval rate; actual context tokens; p50/p95 latency; peak RSS/VRAM; token/cost accounting; structured-output validity; critical-fact loss; secret/PII leakage; and offline egress evidence.

No model/index/provider becomes enabled because of star count, generic benchmark, or a successful demo. It must pass its phase corpus and preserve canonical evidence/authority.

## 6. What not to build

- No mandatory model/runtime, implicit cloud fallback, public server, generic chat, auto-download, provider OAuth token import, account pool, or anonymous/unverified model router. Named 9Router and OmniRouter tracks remain in scope under their verification records.
- No vector/LLM output as canonical memory, governance, policy, or completion proof.
- No model-provided PII/secret detection as the sole privacy barrier.
- No brand-name-only router integration. 9Router and OmniRouter remain named workstreams: their concrete adapter or CLI bridge is selected from a versioned verification record for the intended product, identity, auth, security, terms, privacy, and capability contract.
