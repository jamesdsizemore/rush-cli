# Rush memory and continuity: GitHub research and adoption due diligence

Status: research and technical recommendation; no Rush source, dependency, configuration, or existing-plan changes are proposed by this document.  
Research snapshot: 2026-08-23. GitHub counts and activity are time-sensitive snapshots, not enduring quality claims.  
Companion plan reviewed in full: `innovations-memory-features-plan.md`.

## 1. Executive recommendation

### Decision record — the actual recommendation

This is the entire decision. The rest of the report is evidence, not a menu of work.

| Decision | What happens | What does **not** happen |
|---|---|---|
| **Build Rush continuity core** | Implement F1–F6 internally in the fixed order and file map in the development plan. | No external memory product is made Rush's database, runtime, or package dependency. |
| **Make token reduction a release gate** | Use the token contract fixed by the technical-evaluation decision record. | No “summarize everything” feature and no claimed savings without Rush-corpus measurements. |
| **Borrow six specific ideas** | AgentMem (proof/evaluation), Graphiti (temporal validity), Uteke (lifecycle), Hindsight (retain/recall/reflect), Basic Memory (derived Markdown), A-MEM (derived data is lower authority). | No source-code reuse from these systems. |
| **Keep technical work separate from implementation** | The separate technical-evaluation plan owns corpus, model, retrieval, token, security, portability, and protocol decisions. | No exploratory choice, benchmark, or external-product decision appears in the development plan. |
| **Decline every other external product for this roadmap** | OpenViking, TrueMemory, Memmy, Mem0, Cognee, MemOS, Letta, ClawMem, mcp-memory-service, and the remaining screened projects receive no engineering time. | No future review unless the user explicitly opens a new decision with a concrete change in constraints. |

**Owner model:** this report assigns no one to monitor external projects because there is no such role or backlog item. Reconsideration requires a user-requested roadmap review with a concrete changed constraint.

### Highest-confidence conclusion

**Rush should build its differentiated continuation substrate itself.** The plan's most valuable combination—an append-only redacted episode archive, deterministic continuation state, repository-grounded evidence/receipts, dependency invalidation, budgeted projections with recovery handles, and user-controlled portable bundles—is not supplied by any one credible external project. Integrating a general memory platform would introduce a second source of truth, broader runtime/transport dependencies, and often opaque LLM extraction precisely where Rush needs inspectable evidence and local control.

Rush should:

- **Build itself:** F1–F6's canonical event, claim, obligation, freshness, projection, bundle, and policy semantics; F8's redaction/retention/export/delete boundary; the continuation evaluation corpus; and the CLI/MCP shared-operation layer.
- **Borrow concepts, not code:** Graphiti's temporal validity/provenance; AgentMem's ground-truth-first reminder and long-run evaluation design; Basic Memory's human-readable source affordance and MCP annotations; Uteke's explicit lifecycle states; Hindsight's retain/recall/reflect separation; and A-MEM's “derived enrichment is not the original record” discipline.
- **Interoperate rather than embed:** MCP resources/tools, ACP session capability mapping, A2A artifacts/tasks, generic JSONL/Markdown continuation bundles, and optional external retrieval sidecars through a Rush-owned adapter contract.
- **Resolve technical uncertainty separately:** the dedicated technical-evaluation plan owns all model, retrieval, token, security, portability, and protocol gates before development begins.
- **Avoid as dependencies:** AGPL systems in core paths (OpenViking, TrueMemory, Basic Memory); hosted/cloud-first or provider-LLM-coupled platforms; systems that auto-install hooks/modify agent configuration; and generic vector/graph stores as the canonical evidence model.

### What is genuinely innovative in Rush's plan

The individual techniques are established. The differentiated product is their combination under a coding-quality substrate:

| Planned capability | Assessment | Why it matters |
|---|---|---|
| F1 typed, redacted, gap-aware event archive | Established event-sourcing pattern, novel application boundary | Most memory systems ingest or summarize conversations without representing unavailable source spans, redaction gaps, idempotent tool evidence, and user-controlled capture as first-class state. |
| F2 authority-aware continuation state | Differentiated for coding-agent handoff | Existing systems preserve preferences/facts; few explicitly prevent historical provider system text from becoming authority in another runtime. |
| F3 receipts + dependency invalidation | Strongest Rush-owned innovation | Temporal graphs and provenance systems provide adjacent ideas, but repository/tool/engine/instruction dependency edges tied to Rush `ToolResult` and `skipped` semantics are Rush-specific. |
| F4 obligation-gated recovery | Borrowed closed-loop pattern, differentiated proof rule | Retry classification is common; requiring fresh evidence before completion in a quality CLI is a meaningful product boundary. |
| F5 reversible, omission-accounted projection | Strong differentiation | Compression products exist, but “archive != projection,” mandatory-first budgeting, omission manifests, acknowledged deltas, and recovery handles make token reduction auditable. |
| F6 provider-neutral bundle plus target envelopes | Worth owning | Session exports exist, but portable core data with explicit authority, redaction, divergence, checksum, and consent semantics is not commodity. |
| F7 capability-advertised adapters | Established protocol-adapter pattern | MCP/ACP/A2A provide standards, but Rush should own the mapping from target capability to a safe projection. |
| F8 inspect/correct/delete controls | Necessary trust baseline | Local-only storage alone is not a privacy model; visible retention, tombstones, consented export, and transport permissions are table stakes for a credible local system. |
| F9 evidence-based coordination/learning | Defer until evidence | Leases, locks, and “self-evolving” memory are plentiful. Rush's potential contribution is learning only from attributable, invalidatable evidence—not generic automation. |

### Technical-plan inputs

The research identifies the candidate concepts and hard exclusions. The exact work to resolve remaining uncertainty is intentionally kept in [the technical-evaluation plan](innovations-memory-technical-evaluation-plan.md), not in this report.

## 2. Rush-plan traceability and verified repository baseline

### 2.1 Current Rush facts relevant to all recommendations

| Verified Rush fact | Evidence and implication |
|---|---|
| Python package, local CLI, stdio MCP | `pyproject.toml`; `src/rush/cli.py`; `src/rush/mcp.py::build_server`/`run_stdio`. External systems that require a long-running HTTP daemon, Node runtime, Docker, or cloud are optional sidecars at most. |
| Canonical result contract | `src/rush/tools/base.py::Finding`, `ToolResult`, `ToolFn`; any operation must preserve structured `ok/warn/fail/error/skipped`, findings, metadata, metrics, and artifacts. |
| Shared-implementation rule is not fully realized | `src/rush/cli.py::_run_tool` uses shared tools, while `src/rush/mcp.py::_register_tools` contains manual wrappers. An integration cannot add another transport-specific implementation path. |
| Config is intentionally narrow | `src/rush/config.py::RushConfig` and `_parse` parse project/tools/review/cache/log level, not the memory/context tables docs currently describe. A memory integration must first add a strict local `MemoryConfig`; it must not smuggle configuration through environment-only side effects. |
| Existing state is fragmented and unsafe as a canonical base | `src/rush/session_memory.py::SessionMemoryManager`; `src/rush/memory/checkpoint_journal.py::CheckpointJournal`; `FailureLedger`; `InvariantGraph`; `MerkleInvalidator`; `PreferenceStore`; `MistakeMiner`; `src/rush/tools/flight_recorder.py::FlightRecorder`. They lack the proposed provenance/redaction/authority guarantees. |
| Token primitives already exist | `src/rush/token_economy/router.py::ContentRouter`, `ccr_store.py::CCRStore`, `cache_aligner.py::CacheAligner`, `stale_sweeper.py::StaleSweeper`, `telemetry.py::TelemetryStore`, plus `src/rush/codegraph/context_packer.py::ContextPacker`. Reuse local primitives; do not outsource the projection compiler. |
| Existing multi-agent/governance locations differ from the plan's early draft paths | Current symbols are `src/rush/mcp_mesh/lock_manager.py::MeshLockManager`, `src/rush/tools/swarm_merge.py::SwarmMergeSolver`, `src/rush/governance/synchronizer.py::AgentsMdSynchronizer`, and `src/rush/governance/parity_checker.py::RuleParityChecker`. Any implementation should correct those path references before code work, without modifying the existing plan in this research task. |
| Provider layer is not an adapter layer | `src/rush/providers/base.py::LLMProvider.summarize_findings` and registry support summarization; continuation adapters need a separate capability abstraction. |
| Safety boundary exists | `src/rush/safety/redactor.py::SecretRedactor`, `src/rush/safety/workspace_boundary.py::WorkspaceBoundaryGuard`, and `src/rush/permissions.py` are the existing enforcement hooks. |

### 2.2 Feature-to-landscape traceability

| Rush feature / user-agent problem | External evidence | Recommendation | Likely Rush impact |
|---|---|---|---|
| F1: recoverable cross-session activity without raw transcripts | AgentMem captures tool-boundary effects; ai-memory and TrueMemory auto-capture; Uteke/Engram use local stores | Build typed Rush archive; borrow AgentMem's “agent is untrusted witness” principle; decline transcript-scraping defaults | `src/rush/memory/models.py`, `database.py`, `event_store.py`, `src/rush/tools/continuity.py`, CLI/MCP thin bindings |
| F2: correct authority and current frontier after handoff | Basic Memory markdown graph; MemOS MemCube; ai-memory project wiki | Build reducer/authority rules; optionally import user-approved Markdown as low-authority source | `src/rush/memory/reducer.py`, `authority.py`, `repository_frontier.py`; existing governance files |
| F3: facts that know when they stopped being true | Graphiti temporal edges, trace-mem HMAC spans, A-MEM links | Borrow temporal provenance and span design; no graph DB dependency | `claims.py`, `receipts.py`, `dependencies.py`, `freshness.py`; `ToolResult` metadata |
| F4: stop repeating failed work and prove completion | AgentMem causal links/silence-gating; Hindsight reflect; mcp-memory-service consolidation | Build local obligation/failure state, borrow evaluation ideas, decline autonomous background mutation | `obligations.py`, `failures.py`, `retry_policy.py`, `completion.py`; `permissions.py` |
| F5: smaller resume context without losing proof | Hindsight retain/recall/reflect; Uteke hybrid search; ClawMem retrieval; provider cache docs | Build Rush compiler; optional read-only retrieval adapter later; never use a memory ranking as authority | `src/rush/continuity/projection.py`, `selection.py`, `renderers.py`, `recovery.py`, `token_metrics.py` |
| F6: portable handoff across providers/worktrees | ACP sessions, A2A artifacts/tasks, ai-memory multi-agent support, Basic Memory Markdown | Own bundle v1; interoperate with generic JSONL/Markdown/ACP/A2A envelopes; do not use any product's opaque export as core | `bundle.py`, `schema.py`, `divergence.py`, `schemas/continuity/v1/` |
| F7: honest capability-dependent integration | MCP resources/tools; ACP initialize/session; A2A Agent Cards | Interoperate with standards, capability-gate adapters, retain generic fallback | `continuity/adapters/base.py`, `capabilities.py`; `src/rush/mcp.py` compatibility tests |
| F8: user sees and controls retained knowledge | Uteke soft-deprecation, Basic Memory human-readable files, TrueMemory local SQLite | Build Rush policy/deletion; borrow lifecycle UX; decline systems requiring cloud sync or background collection | `policy.py`, `retention.py`, `deletion.py`, `inspection.py`, config/docs/tests |
| F9: multiple agents avoid duplicate work and bad learning | Uteke Rooms, TencentDB team assets, ClawMem shared vault, ACP/A2A | Defer coordination; borrow append/CAS and explicit attribution; no generalized mesh dependency | later `coordination.py`, `learning.py`, `promotion.py`; existing `mcp_mesh` only as a migration input |

## 3. Methodology, cohorts, and scoring

### 3.1 Evidence method

I reviewed the existing plan completely, verified current Rush source locations/symbols, then screened repositories through their GitHub repository pages, README/source layout, releases, issues, changelogs, and primary project documentation where available. Public GitHub API metadata was captured for the first 20 systems below on 2026-08-23: language, SPDX identifier, created/pushed/release dates, stars, forks, open issues, and default branch. The remaining systems were independently screened from current repository pages and direct project materials; their selection does not rely on unverified popularity claims.

Repository-level claims are labelled in the text as **[GitHub]**. Rush facts are **[Rush]**. Recommendations are **[Inference]**. Missing license, security, or compatibility evidence is a reason to decline/defer, not an invitation to assume it away.

### 3.2 Cohort definition

- **Newer cohort:** systems created, materially released, or visibly adopted during 2025–2026; selection favors active releases/commits, not merely creation date.
- **Popular cohort:** systems with material GitHub adoption and activity, evaluated with stars/forks alongside releases, issue load, contributor/docs/testing evidence, and fit.
- A system appears only once in the main 30-system comparison where possible. The explicit overlap set is shown separately so popularity does not masquerade as novelty.

### 3.3 Scoring rubric (0–5)

| Dimension | 0 | 3 | 5 |
|---|---:|---:|---:|
| I — Integration fit | incompatible runtime/transport or hosted-only | adapter/sidecar feasible | Python/local/stdio-shaped and composable |
| A — Adoption & maintenance | abandoned/no evidence | active but uneven | sustained releases, issues, docs, contributors |
| B — Borrow value | little beyond commodity storage | one useful pattern | several well-specified patterns/evals |
| D — Decline risk | no material concern | meaningful operational/licensing risk | strong reason to avoid direct adoption |
| S — Strategic value | distracts from Rush | useful supporting capability | advances differentiated continuation/trust model |
| T — Time-to-value | multi-quarter platform work | bounded spike | small adapter/pattern test yields value |
| K — Token-efficiency contribution | none | retrieval/context help | measurable context/tool/reasoning reduction potential |
| R — Trustworthiness | opaque/no controls | partial local/provenance controls | explicit provenance, freshness, inspectability, control |

`Weighted recommendation score` is only a tie-breaker: `0.20I + 0.15A + 0.15B + 0.15S + 0.10T + 0.10K + 0.15R - 0.15D`, scaled to 0–5. It is not used to override a licensing or privacy veto.

## 4. Memory systems landscape

### 4.1 Newer cohort (15 distinct systems)

| System | Maintainer / repository | Evidence of recency and maintenance | Architecture, storage, dependencies | Local/privacy position | Initial disposition |
|---|---|---|---|---|---|
| Uteke | codecora / [codecoradev/uteke](https://github.com/codecoradev/uteke) | Created 2026-05; Rust; v0.15.0 released 2026-08-19; push 2026-08-22; 231★/25 forks/7 issues | Single Rust binary; ONNX embeddings, hybrid FTS5/HNSW/RRF, CLI and MCP/HTTP components | Local/offline by default; first run downloads an embedding model | Interoperate spike only |
| ai-memory | akitaonrails / [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory) | Created 2026-05; v1.31.0 2026-08-22; push 2026-08-23; 4,219★/310/9 | Rust binary; markdown-in-git source, SQLite derived index, hooks/MCP/visible ledger | Local-capable, but lifecycle hooks and configuration rewriting are central | Borrow visible-ledger/Markdown ideas; decline integration |
| Memmy Agent | MemTensor / [MemTensor/memmy-agent](https://github.com/MemTensor/memmy-agent) | Created 2026-07; v1.0.9 2026-08-20; push 2026-08-23; 928★/97/5 | TypeScript/Electron/desktop, memory service, agent runtime, API/gateway | Default cloud address and Node/Electron stack; hosted trial/BYOK orientation | Decline |
| TrueMemory | buildingjoshbetter / [TrueMemory](https://github.com/buildingjoshbetter/TrueMemory) | Created 2026-03; last release/commit 2026-06; 373★/47/18 | Python, SQLite/FTS5/sqlite-vec, local model tiers, MCP/hooks | Local data but optional anonymous telemetry; 1.5GB model download for full tier | Borrow benchmark discipline; decline AGPL code |
| OpenViking | Volcengine / [volcengine/OpenViking](https://github.com/volcengine/OpenViking) | Created 2026-01; v0.4.16 2026-08-21; push 2026-08-23; 32,442★/2,479/499 | Python context database combining memory/RAG/skills | Large, fast-moving platform; AGPL-3.0 | Decline |
| EverOS | EverMind AI / [EverMind-AI/EverOS](https://github.com/EverMind-AI/EverOS) | Created 2025-10; v1.2.3 2026-08-07; 12,366★/904/74 | Python, Markdown-native portable layer | Claims local-first/user-owned; validate format and security before use | No roadmap action |
| TencentDB Agent Memory | TencentCloud / [TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | Created 2026-04; v2.0.0 2026-08-03; 23,999★/2,215/689 | TypeScript team hub: chat/skill/wiki/code graph assets | Enterprise/team hub; no SPDX detected | Decline direct use; borrow asset taxonomy only |
| Engram | Gentleman Programming / [Gentleman-Programming/engram](https://github.com/Gentleman-Programming/engram) | Created 2026-02; v1.20.0 2026-07; push 2026-08-17; 6,133★/648/193 | Go binary, SQLite+FTS5, CLI/MCP/HTTP/TUI | Local binary but broad surface/daemon modes | Borrow local operational UX; sidecar only |
| AgentMem | AgentMem / [agentmem/agentmem](https://github.com/agentmem/agentmem) | 2026 repository; active docs/evals/integrations; first PyPI release still pending | Python/uv; out-of-band records, SQLite, cached reminder decision, MCP pull surface | Local store possible; LLM memory worker optional | High-value borrow/spike |
| JaceHo AgentMem | JaceHo / [JaceHo/AgentMem](https://github.com/JaceHo/AgentMem) | Current repo page reports hooks and coding-agent scope | Python, Redis 8 vector-set backend, hooks/MCP/framework adapters | Redis and auto-hook installation add operational burden | Decline; compare design only |
| trace-mem | bettyguo / [bettyguo/agent-memory](https://github.com/bettyguo/agent-memory) | v0.1 alpha; 75 commits; 6★/0 forks | Python; HMAC-signed trajectory spans, optional MCP/framework extras | Strong provenance claim, immature adoption | Borrow signed-span/integrity pattern; spike |
| ClawMem | yoloshii / [yoloshii/clawmem](https://github.com/yoloshii/clawmem) | 286 commits; 195★/32 forks; tests/docs/release notes | TypeScript/Bun; SQLite FTS5/sqlite-vec, local GGUF observer, hooks/MCP/optional HTTP | On-device but native Windows discouraged; background service/hook heavy | Borrow retrieval/eval ideas; decline integration |
| AgentMemory | KuanChen01 / [KuanChen01/AgentMemory](https://github.com/KuanChen01/AgentMemory) | Current project page; cross-agent claim | JavaScript + WASM SQLite + feature hashing; DeepSeek summarization | Hosted summarizer dependency for background path | Decline |
| A-MEM | WujiangXu / [WujiangXu/A-mem](https://github.com/WujiangXu/A-mem) | NeurIPS 2025 paper code; research repository | Python, `MemoryNote`, Chroma retrieval, LLM metadata/neighbor evolution | Persistence/trust constraints require verification; research code | Borrow links/evolution caution; decline code |
| mcp-memory-service | doobidoo / [doobidoo/mcp-memory-service](https://github.com/doobidoo/mcp-memory-service) | 2,759 commits; active changelog/issue traffic | Python MCP/REST, multiple stores, graph/consolidation/plugins | Broad server surface; 2026 read-scope write/delete advisory | Decline; security regression reference |

### 4.2 Popular cohort (15 distinct systems)

| System | Maintainer / repository | Adoption and maintenance snapshot | Architecture and dependency surface | Local/privacy / license | Initial disposition |
|---|---|---|---|---|---|
| Mem0 | mem0ai / [mem0ai/mem0](https://github.com/mem0ai/mem0) | 63,882★/7,471 forks/680 issues; active push 2026-08-23; Apache-2.0 | Python universal-memory SDK; extraction/retrieval adapters and many providers/stores | Local modes exist, but defaults/ecosystem often use LLM/vector services | Borrow API ideas; no core dependency |
| Graphiti | Zep / [getzep/graphiti](https://github.com/getzep/graphiti) | 30,225★/3,058/488; push 2026-08-21; v0.29.3; Apache-2.0 | Python temporal context graph; Neo4j/FalkorDB/Neptune/LLM extras | Self-hostable, but graph DB and telemetry/provider surface | Temporal-model spike; no integration |
| Letta | Letta / [letta-ai/letta](https://github.com/letta-ai/letta) | 24,372★/2,591/40; active 2026-08-23; Apache-2.0 | Stateful-agent platform, hosted API/clients/CLI | Model-agnostic but agent runtime/platform, not Rush substrate | Interoperate only if bundle mapping becomes useful |
| Cognee | Cognee / [topoteretes/cognee](https://github.com/topoteretes/cognee) | 30,199★/2,951/362; v1.5.3 and push 2026-08-23; Apache-2.0 | Python knowledge graph/memory platform; local API or cloud; plugins/hooks | LLM API key/local service default, broad data stack | Borrow ingestion/retrieval patterns; decline dependency |
| MemOS | MemTensor / [MemTensor/MemOS](https://github.com/MemTensor/MemOS) | 10,938★/1,004/77; v2.0.30; Apache-2.0 | TypeScript-led Memory OS / MemCube / skills/migration | Cross-task platform is wider than Rush | Borrow MemCube portability vocabulary |
| Hindsight | Vectorize / [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight) | 20,974★/1,627/114; v0.9.1; active 2026-08-23; MIT | Python service/embedded pg0, clients, retain/recall/reflect, many LLM integrations | Self-host/embedded possible but LLM/provider and server complexity | Retrieval-adapter spike only |
| memU | NevaMind AI / [NevaMind-AI/memU](https://github.com/NevaMind-AI/memU) | 14,338★/1,062/112; active 2026-08-21; no SPDX detected | Python personal cross-agent memory | License uncertainty prevents code reuse | Decline |
| Memori | MemoriLabs / [MemoriLabs/Memori](https://github.com/MemoriLabs/Memori) | 16,203★/3,227/33; active 2026-08-21; no SPDX detected | Python enterprise infrastructure across cloud/VPC/on-prem | Enterprise platform/data infrastructure; license unclear | Decline |
| Memvid | Memvid / [memvid/memvid](https://github.com/memvid/memvid) | 16,441★/1,413/35; Apache-2.0; last push 2026-07-14 | Rust single-file/serverless memory artifact | Interesting portable container, but opaque/retrieval-oriented fit | Borrow artifact idea only |
| Basic Memory | Basic Machines / [basicmachines-co/basic-memory](https://github.com/basicmachines-co/basic-memory) | 1,742 commits, 261 forks, 68 issues; active v0.22.1 release; AGPL-3.0 | Python/uv, Markdown source, SQLite/Postgres, MCP/plugins/optional cloud | Excellent local UX, but AGPL and cloud/plugin breadth | Markdown exchange spike; no code reuse |
| LangMem | LangChain / [langchain-ai/langmem](https://github.com/langchain-ai/langmem) | 1.5k★/168 forks/47 issues; no releases; issue reports stale maintenance | Python primitives + LangGraph store and LLM background manager | Requires LLM provider for key paths; LangGraph coupling | Borrow abstractions only; defer |
| BAI MemoryOS | BAI-LAB / [BAI-LAB/MemoryOS](https://github.com/BAI-LAB/MemoryOS) | 1,558★/159/23; Apache-2.0; last release 2025-07, push 2026-07 | Python research MemoryOS | Research/maintenance gap | Borrow paper patterns only |
| MemMachine | MemMachine / [MemMachine/MemMachine](https://github.com/MemMachine/MemMachine) | 3,201★/208/95; v0.3.9; active 2026-08-20; Apache-2.0 | Python interoperable memory store/retrieval platform | General infrastructure, not evidence semantics | No roadmap action |
| ByteRover CLI | Campfire / [campfirein/byterover-cli](https://github.com/campfirein/byterover-cli) | 4,948★/453/22; last push 2026-06; no SPDX detected | TypeScript coding-agent portable memory CLI | License and maintenance uncertainty | Decline |
| oxgeneral AgentMem | oxgeneral / [oxgeneral/agentmem](https://github.com/oxgeneral/agentmem) | Current page claims 206 unit/107 quality tests; zero-to-12MB design | Python SQLite, FTS5/vector, CLI/MCP/HTTP, five memory tiers | Local/no server primary path; verify license/release before any use | Borrow tier/doctor UX; spike only |

### 4.3 Overlap analysis

The 30-row cohorts are intentionally disjoint. Several systems would qualify for both: Hindsight, OpenViking, EverOS, Engram, MemMachine, TrueMemory, and Uteke are new/fast-changing while already attracting attention. They appear in the cohort that best explains why Rush should watch them, rather than double-counting them to inflate coverage.

The four mandated identities resolve as follows:

- **Uteke** → [codecoradev/uteke](https://github.com/codecoradev/uteke), a credible active Rust/offline local memory engine.
- **ai-memory** → [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory), not the unrelated similarly named repositories. It is an active Rust coding-agent memory implementation.
- **memmy-agent** → [MemTensor/memmy-agent](https://github.com/MemTensor/memmy-agent), an active TypeScript desktop/runtime product with a cloud-default service configuration.
- **true-memory** → [buildingjoshbetter/TrueMemory](https://github.com/buildingjoshbetter/TrueMemory), an active-ish local Python system. Its repository/package name is `TrueMemory` rather than `true-memory`; AGPL-3.0 is a direct-adoption veto for Rush core.

## 5. Scorecards and ranked decisions

Scores are not claims of benchmark superiority. Each score has a concise rationale; `D` is a *risk* score where higher is worse. A consequence column makes the decision legible instead of hiding tradeoffs in a blended number.

| Candidate | I | A | B | D | S | T | K | R | Weighted | Consequence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| AgentMem | 4 — Python/SQLite/MCP-compatible but its proactive worker is not Rush's core | 3 — active docs/evals but early pre-release | 5 — out-of-band evidence, causal reminders, evals are directly useful | 2 — optional LLM worker and hook integrations add risk | 5 — validates F1/F3/F4/F5 | 4 — fixture spike can start immediately | 4 — silence-gated reminders reduce redundant context | 5 — explicit evidence/citations and ground-truth checks | 4.1 | Borrow + high-value spike |
| Uteke | 3 — external Rust binary needs adapter | 3 — very active but young | 4 — hybrid local recall/lifecycle/rooms ideas | 2 — model download and sidecar boundary | 3 — optional recall helps F5/F9 only | 4 — CLI/stdio probe is small | 4 — hybrid retrieval can reduce source fetches | 3 — local/soft lifecycle but retrieval is not proof | 3.2 | Optional read-only adapter spike |
| Graphiti | 2 — graph DB/LLM extras conflict with minimal core | 5 — active, released, widely adopted | 5 — temporal validity/episode provenance are strong patterns | 3 — storage/telemetry/provider complexity | 4 — advances F3 precisely | 3 — small model spike feasible | 3 — precise retrieval helps projections | 4 — temporal provenance is explicit | 3.1 | Borrow data model only |
| Basic Memory | 3 — Python/MCP and Markdown fit, but AGPL forbids casual embedding | 4 — releases, tests, docs, active issues | 5 — human-editable exchange and tool hints | 5 — AGPL/cloud/plugin/hook breadth | 3 — only auxiliary F2/F8/F6 value | 3 — export-format spike is contained | 3 — tool discovery and notes can reduce context | 4 — human-readable source/control | 2.7 | Interoperate with derived Markdown only |
| Hindsight | 2 — service/LLM/provider stack is large | 5 — active releases, many integrations, docs/tests | 4 — retain/recall/reflect and evaluation separation | 3 — default server/cloud paths and provider coupling | 3 — F5 adapter could help but not differentiate | 2 — operational spike is nontrivial | 5 — retrieval/reflection explicitly target context cost | 3 — rich APIs but memory remains ranking-led | 2.8 | Benchmark/adapter spike, not dependency |
| ai-memory | 3 — Rust/local database can interoperate but no library fit | 4 — active daily and released | 5 — visible event ledger/Markdown wiki/handoff patterns | 4 — auto hooks/config rewrites/Git commits violate Rush constraints | 4 — cross-vendor coding-agent focus overlaps F1/F6 | 3 — read its fixtures/docs rather than integrate | 3 — handoffs reduce re-exploration | 3 — plain Markdown but automatic capture broadens exposure | 2.8 | Borrow patterns; decline integration |
| trace-mem | 4 — Python/library/MCP extras fit an optional test harness | 1 — v0.1, 6 stars, no adoption signal | 5 — HMAC trajectory-span idea is highly relevant | 3 — immature crypto/key lifecycle needs review | 5 — F3 provenance is strategic | 4 — narrow POC | 2 — integrity more than compression | 5 — strongest provenance concept screened | 3.3 | Research spike only |
| Mem0 | 3 — Python API but broad external dependency matrix | 5 — strongest adoption/activity | 4 — memory operation/API/adapter ideas | 3 — providers/stores and cloud orientation | 2 — generic memory duplicates Rush core | 2 — integration creates dual truth | 3 — retrieval may reduce context | 2 — weak fit for evidence/invalidation | 2.6 | Borrow API vocabulary; no dependency |
| Cognee | 2 — local API/LLM data stack, not composable core | 5 — high active adoption/releases | 4 — graph ingestion/plugin patterns | 3 — service, LLM key, cloud options | 2 — generic graph memory is not Rush intelligence | 2 — large POC | 3 — retrieval helps only indirectly | 2 — trust depends on extraction | 2.3 | Decline dependency |
| MemOS | 2 — TypeScript platform/runtime mismatch | 4 — active releases/adoption | 4 — MemCube portability/lifecycle concept | 3 — broad OS/skill runtime | 3 — useful vocabulary for F6 | 2 — adaptation is substantial | 3 — claims token savings but require reproduction | 3 — provenance/versioning intent | 2.5 | Borrow vocabulary; no roadmap action |
| TrueMemory | 3 — Python/SQLite/MCP shape fits | 2 — activity/release stalled since June | 4 — retrieval tiers/evaluation fixtures | 5 — AGPL-3.0 and heavy downloads | 3 — good F5 benchmark comparison | 2 — license blocks code POC | 4 — retrieval-centered approach | 3 — local but auto capture and telemetry exception | 1.8 | Decline; read benchmark methodology |
| OpenViking | 1 — AGPL platform/data model mismatch | 5 — active/high adoption | 4 — unified memory/RAG/skills taxonomy | 5 — AGPL, heavy/fast-moving platform | 2 — too broad; risks product drift | 1 — migration cost high | 4 — context DB claims | 2 — self-evolving opacity | 1.5 | Decline |
| Letta | 2 — separate agent platform/API | 5 — active ecosystem | 3 — stateful-agent memory block ideas | 3 — hosted/platform boundary | 2 — may compete with Rush's role | 2 — adapter not core | 2 — not targeted token projection | 3 — mature state model | 2.1 | ACP/bundle interop only |
| Engram | 2 — Go binary/HTTP broad surface | 4 — active/released | 4 — coding-agent local SQLite UX | 3 — daemon/API/hook breadth | 3 — adjacent to F1/F5 | 3 — CLI sidecar possible | 3 — FTS retrieval | 3 — local but not receipt-driven | 2.5 | Borrow UX; no roadmap action |
| LangMem | 3 — Python primitives, but LangGraph-specific path | 2 — no releases/stale-maintenance issue | 3 — hot/background memory interface | 3 — provider/LLM and maintenance risk | 2 — generic memory workflow | 3 — design reading only | 2 — compaction bug is a caution | 2 — automatic extraction weakens audit | 2.0 | Decline/defer |
| ClawMem | 1 — Bun/WSL/background model/hook system mismatch | 2 — small young project | 4 — retrieval/lifecycle/eval catalog | 4 — auto-hooks/service/Windows weakness | 2 — overlapping broad tool | 2 — adaptation expensive | 4 — hybrid/budget-aware retrieval | 2 — transcript mining/LLM inference | 1.7 | Borrow patterns only |
| Memmy Agent | 0 — Electron/Node/cloud-default runtime conflict | 3 — active young releases | 2 — agent-source abstraction only | 5 — hosted default/UI/runtime scope | 1 — strategic mismatch | 0 — no meaningful Rush shortcut | 2 — opaque memory distillation | 2 — cloud/default privacy concern | 0.6 | Decline |

### 5.1 Separate rankings

| Rank | Best integration / adaptation candidate | Decision |
|---:|---|---|
| 1 | No general memory repository | **Do not integrate a memory core.** Implement Rush's F1–F6 directly. |
| 2 | Uteke | Optional read-only local retrieval adapter after F5; no write-through/no dependency in core. |
| 3 | Basic Memory | Derived, consented Markdown import/export adapter only; AGPL prevents source reuse. |
| 4 | Hindsight | Bounded benchmark or optional retrieval adapter spike; keep it outside default install. |
| 5 | MCP Python SDK | Existing dependency; use its supported resources/tools after locked-version test, not a new platform. |

| Rank | Best ideas to borrow | Project/pattern | Rush destination |
|---:|---|---|---|
| 1 | Temporal validity windows and episode provenance | Graphiti | F3 claims/dependencies/freshness |
| 2 | Ground truth over agent narration; silence-gated reminders; long-run evaluations | AgentMem | F1/F3/F4/F5 + evaluation corpus |
| 3 | Explicit local lifecycle/soft deprecation | Uteke | F8 retention/deletion UX |
| 4 | Retain/recall/reflect separation | Hindsight | F1 archive vs F5 projection vs F4 evaluation |
| 5 | Human-readable derived knowledge and behavior annotations | Basic Memory | optional F2/F6 derived projection format |
| 6 | Derived metadata must not replace the source | A-MEM | F3 claim authority and F5 provenance labels |

| Rank | Best interoperability targets | Why |
|---:|---|---|
| 1 | MCP tools/resources | Rush already uses stdio MCP; resources are a read-only projection surface after version testing. |
| 2 | ACP | Its negotiated session capabilities and `session/new`/`session/load`/`session/update` map to optional provider-session envelopes, not core memory. |
| 3 | A2A | Map future bundles to tasks/artifacts/Agent Cards only when a user explicitly needs networked interop. |
| 4 | Generic JSONL and Markdown | Lowest-risk portable import/export baseline; inspectable, consented, testable. |
| 5 | Uteke CLI/MCP | Optional local semantic-recall sidecar with a strict capability contract. |

| Rank | Highest-value research inputs | Relevance |
|---:|---|---|
| 1 | AgentMem evidence model | Ground-truth-first reminders and long-run handoff evidence. |
| 2 | Graphiti temporal claim model | Validity windows and source episode provenance. |
| 3 | Uteke local retrieval | Hybrid local recovery and lifecycle semantics. |
| 4 | Basic Memory derived Markdown | Human-readable, non-authoritative exchange pattern. |
| 5 | MCP/ACP/A2A | Provider-neutral capability and envelope vocabulary. |

| Strongest decline/defer recommendation | Concrete reason |
|---|---|
| OpenViking, TrueMemory, Basic Memory as code dependencies | AGPL-3.0 is incompatible with casual core reuse and review is a hard gate. |
| Memmy Agent | Electron/Node, UI/runtime scope, and cloud-default service conflict with Rush's local CLI/stdio focus. |
| mcp-memory-service | A documented 2026 OAuth scope flaw plus broad REST/server surface contradict Rush's minimal permission boundary. |
| ai-memory/ClawMem/JaceHo AgentMem auto hooks | Automatic configuration/hook installation conflicts with Rush's explicit no-hook and user-control constraints. |
| Graphiti/Cognee/Mem0 as canonical stores | They create a parallel source of truth and rely on graph/vector/extraction semantics where Rush needs receipts/invalidation. |

## 6. Candidate-by-candidate due diligence

### 6.1 AgentMem — borrow and evaluate, do not embed

**[GitHub]** [AgentMem/agentmem](https://github.com/agentmem/agentmem) is an Apache-2.0 Python project that uses `uv`, tests with mocked LLM calls, and provides integrations for Claude Code, Claude Agent SDK, LangGraph, Aider, OpenAI Agents SDK, custom loops, and MCP pull hosts. Its public API is deliberately smaller than its integrations: `MemorySession`, triggers, a SQLite store, a cache-backed `pending_context()`, and an MCP surface. The repository calls its status early/moving fast, which constrains direct adoption.

Its strongest architecture is **asynchronous compute, synchronous injection**: tool-boundary facts are captured separately from the agent's self-description; a memory worker decides whether a reminder has decision value; next-turn reads only a cache; reminders cite bank-entry IDs; a long-horizon harness measures retention and repeated-failure avoidance. The published repository describes causal links, salience/decay/consolidation, a no-hard-delete lifecycle, JSONL telemetry, and replayable evaluations. This is unusually close to Rush's F1/F3/F4/F5 concerns.

**Compatibility and risk.** It is Python and can use SQLite, but its automatic hooks, LLM memory worker, and proactive reminder semantics are not a substitute for Rush's deterministic archive, policy control, or canonical `ToolResult`. The worker is an optional model-dependent component and must never promote a derived summary to Rush truth.

**Recommendation: Borrow + research spike.** Copy neither code nor schema. Build a 30-episode fixture harness that checks AgentMem-style claims against Rush tool receipts/Git state. Prototype a *purely deterministic* `should_surface` baseline and compare it with a model-assisted proposal lane that only emits low-authority claims. Relevant Rush files: F1–F5 proposed services plus `src/rush/tools/base.py::ToolResult`, `src/rush/tools/common.py::run_engine`, `src/rush/memory/failure_ledger.py::FailureLedger`, and `src/rush/capabilities.py::inspect_capabilities`.

### 6.2 Uteke — optional local semantic retrieval interop

**[GitHub]** [codecoradev/uteke](https://github.com/codecoradev/uteke) is Apache-2.0 Rust, created May 2026. Snapshot metadata: 231 stars, 25 forks, 7 open issues, default `develop`, v0.15.0 released 2026-08-19, and a recent 2026-08-22 commit. Its source layout separates core storage/embedding/search, CLI, server, and MCP crates. It offers CLI, stdio MCP, and optional HTTP/Docker forms; the default local story downloads an approximately 188 MB ONNX embedding model once.

The useful mechanism is hybrid FTS5 plus local vector search with reciprocal-rank fusion, namespaces/rooms with author attribution, and a documented soft-deprecate → restorable → prune lifecycle. Those are useful retrieval and user-control patterns. Its semantic store is still similarity-oriented: it cannot determine whether a claim about a Rush test, tool, instruction, or repository state remains valid.

**Compatibility and risk.** Local/offline, no API key, Apache-2.0, Windows binary release, JSON CLI output, and MCP make a future sidecar feasible. A Rust executable and downloaded model are still an optional runtime dependency; HTTP mode and shared rooms must not enlarge Rush's default threat model.

**Recommendation: Interoperate behind an adapter, not integrate.** Add no package dependency. Phase-6 spike: detect an explicitly configured executable, call a read-only `recall`, include returned results as `external_retrieval` evidence with adapter/version/query fingerprint, and require the projection compiler to label it non-authoritative. Test degraded `skipped` behavior when absent. Proposed file: `src/rush/continuity/adapters/uteke.py`; current dependency points: `src/rush/capabilities.py`, `src/rush/permissions.py`, `src/rush/tools/common.py::run_subprocess`, F5 renderer/recovery tests.

### 6.3 Graphiti — temporal facts are a model to borrow, not a database to adopt

**[GitHub]** [getzep/graphiti](https://github.com/getzep/graphiti) is Apache-2.0 Python, created 2024-08. Snapshot: 30,225 stars, 3,058 forks, 488 open issues, v0.29.3 on 2026-07-27, push 2026-08-21. Its README/source documentation shows episodes as source data, entities/relationships as derived facts, temporal validity windows, hybrid semantic/keyword/graph retrieval, Pydantic ontology types, and MCP support. It supports Neo4j, FalkorDB/FalkorDBLite, Kuzu (deprecated), and Neptune, with optional OpenAI/Azure/Anthropic/Gemini/Groq dependencies; it also documents telemetry.

**Value.** The fact model maps well to F3: preserve old facts, label their validity, link them to episode spans, and query what was true at a cursor. It is a strong counterexample to flat “latest summary wins” memory. The project has release/test/documentation evidence and active issue/PR volume, but that scale also means integration cost.

**Mismatch.** A graph database/LLM extraction pipeline is not needed to answer Rush's first claim invalidation questions, which are mostly file/symbol/config/tool/instruction dependency changes. It would force a second durable store, add database operations, and blend inferred relationships with hard engineering receipts. Cloud Zep is explicitly out of scope.

**Recommendation: Borrow temporal schema in SQLite.** Create a fixture-only spike that represents `claim → evidence event`, `claim → observed dependency digest`, and `supersedes/contradicts` in the proposed SQLite tables. Adopt a graph backend only if a published query corpus demonstrates a material correctness or latency benefit with local FalkorDBLite and no loss of inspectability. Likely Rush files: F3 `claims.py`, `dependencies.py`, `freshness.py`, `receipts.py`; existing `src/rush/memory/merkle_invalidator.py::MerkleInvalidator`; optional `src/rush/codegraph/store.py::CodeGraphStore`.

### 6.4 Basic Memory — valuable local interchange pattern, license veto on source reuse

**[GitHub]** [basicmachines-co/basic-memory](https://github.com/basicmachines-co/basic-memory) is an AGPL-3.0 Python/uv project with 1,742 commits, 261 forks, 68 issues, tests for SQLite/Postgres, a current v0.22.1 release, MCP server, Markdown source files, optional SQLite/Postgres/Milvus, and optional hosted cloud. Its README documents local Markdown as source of truth, bidirectional human/agent edits, wikilinks/observations/relations, semantic/hybrid search, optional local or LiteLLM reranking, agent plugins/skills, and MCP annotations (`readOnlyHint`, destructive, idempotent, open-world). It also contains cloud sync/auth/storage choices outside Rush's scope.

**Value.** Plain user-editable Markdown is a good *derived exchange* format; agent-visible behavior hints can improve progressive tool discovery; a source-vs-index split mirrors the plan's archive-vs-projection distinction. Its changelog and issue history also expose real sync/concurrency bugs, which reinforces the need for Rush's explicit append/CAS semantics rather than a naïve file watcher.

**Mismatch and licensing.** The license requires legal review even for reuse; do not copy code, schemas, or templates. Basic Memory's knowledge base is human-authored/edited information, not a receipt-bearing engineering event archive. Its plugin/hook/cloud surface is broader than Rush and its automatic installs are prohibited by Rush constraints.

**Recommendation: Interoperate only.** Define a `rush-derived-note-v1.md` export that contains selected, consented claims with source IDs, freshness, and redaction markers; import such Markdown as `external_low_authority` evidence. Do not ingest its database or sync machinery. Impact: F6 `bundle.py`/`schema.py`, F8 `policy.py`/`deletion.py`, `docs/specs/continuation-bundle-v1.md`, and integration-security fixtures.

### 6.5 Hindsight — benchmark and adapter candidate, not Rush's state store

**[GitHub]** [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight) is MIT, created 2025-10. Snapshot: 20,974 stars, 1,627 forks, 114 open issues, v0.9.1 published 2026-08-14, commit 2026-08-23. Its repository has 2,632 commits, Python/Node/Go clients, Docker/Helm/Python embedded modes, an embedded pg0 option, server/cloud offerings, skills, integration tests, and a documented `retain`/`recall`/`reflect` interface. It supports many LLM providers and coding-agent integrations, but most useful modes expect an LLM/provider or server process.

**Value.** Its separation between ingest, retrieval, and response/reflection is a useful mental model for F1 archive, F5 projection, and F4 decision support. Its benchmark publication and broad clients make it a credible external baseline for quality/token claims. The product is explicitly retrieval/learning-oriented rather than evidence/receipt-oriented.

**Mismatch.** Default Docker/server/cloud, LLM wrapper interception, multiple runtime languages, and managed service offerings do not match Rush's default single-process local CLI/stdio server. A wrapper that automatically retains conversations risks violating Rush's explicit capture/redaction policy. Its `bank` is not a portable continuation episode.

**Recommendation: Research spike or optional adapter only.** Compare Hindsight against Rush's own selection on the same sanitized evaluation corpus; if enabled later, use an adapter that returns typed retrieval candidates without making remote calls unless the user grants network permission. Never allow it to write canonical claims, obligations, or bundles. New optional module: `src/rush/continuity/adapters/hindsight.py`; tests must demonstrate `skipped` when unavailable and secrets remain absent.

### 6.6 ai-memory — closest product overlap, but explicitly not an integration target

**[GitHub]** [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory) is MIT Rust, created 2026-05. Snapshot: 4,219 stars, 310 forks, 9 issues, v1.31.0 released 2026-08-22, active push 2026-08-23. It uses Markdown-in-Git as a source-of-truth wiki and SQLite as a derived index with FTS5/sessions/observations/handoffs/audit data. It describes lifecycle hooks, a managed visible-event ledger, agent integrations, session handoff, and cross-vendor client support. Native Windows is marked experimental in project documentation.

**Value.** It is the strongest direct confirmation that cross-vendor coding-agent continuity is user-valued. The project/wiki/derived-index distinction, bounded capture instead of claiming complete native transcripts, and visible event ledger are patterns Rush should scrutinize.

**Mismatch.** It installs hooks, rewrites/merges agent configuration and skills, creates Git commits during consolidation, and captures broad prompts/tool lifecycle events. Those are incompatible with Rush's no-unprompted-hooks, no automatic Git history mutation, strict redaction, and explicit capture policy. It is also a competing end-to-end continuity product, not a focused library.

**Recommendation: Borrow architecture and test cases; decline direct use.** Review its non-secret public event-schema assumptions and failure cases, then write Rush-native fixtures for provider gaps, history visibility, conflict handling, and worktree drift. Do not run its hooks in Rush tests or import its data as authoritative.

### 6.7 Mem0, Cognee, and MemOS — mature ecosystem references, not a Rush dependency stack

**[GitHub]** Mem0 is Apache-2.0 Python with unusually high adoption (63,882★, 7,471 forks, active push) and broad memory/provider/vector-store abstraction. Cognee is Apache-2.0 Python (30,199★, 2,951 forks, release v1.5.3 on snapshot day) with a self-hosted knowledge graph engine, cloud/local paths, plugins, hooks, and LLM API expectations. MemOS is Apache-2.0, TypeScript-led, 10,938★/1,004 forks, active v2 releases, and frames memory as portable `MemCube`-like units spanning retrieval, lifecycle, and skills.

**What to borrow.** From Mem0: a narrow provider/store capability surface and explicit optional dependency handling. From Cognee: treat ingestion/retrieval as pluggable and do not put graph construction inside transport wrappers. From MemOS: express portable bundles in units with content, metadata, provenance, and migration compatibility rather than a provider transcript.

**Why not integrate.** All three retain/derive/recall generic knowledge and depend on models, vector/graph stores, cloud paths, or non-Python platform components for their headline capability. None captures Rush's tool receipt semantics, instruction authority, redaction gaps, or repository dependency invalidation. Adopting any would preserve a second source of truth and reduce the plan to commodity memory plumbing.

**Recommendation: Borrow concepts behind Rush-owned abstractions.** The adapter interface can resemble a subset of a memory-store contract (`probe`, `retrieve`, `render`, `ack`) but canonical events/claims stay local. Mark all retrieved external items as evidence candidates, never facts.

### 6.8 TrueMemory, OpenViking, Memori, memU, TencentDB, and ByteRover — decline direct adoption

**[GitHub]** TrueMemory is local Python/SQLite with model tiers and benchmark assets, but AGPL-3.0, 1.5GB tier downloads, an automatic capture posture, a release/commit gap since June, and optional telemetry make it unsuitable as Rush core. OpenViking is a rapidly growing AGPL-3.0 Python “context database” spanning memory/RAG/skills; its 32k-star snapshot is a monitor signal, not a license exception. Memori, memU, TencentDB Agent Memory, and ByteRover have no SPDX identifier in the snapshot and each positions a large cross-agent/enterprise/platform stack rather than a small library.

**Reasoned outcome.** These products prove demand for portable memory, code graph, skills, and team assets, but they are either license-unclear, vendor/platform-coupled, cloud/enterprise oriented, too broad, or insufficiently accountable for Rush's use. Do not copy source, depend on packages, or make their formats canonical. They receive no further work in this roadmap.

### 6.9 A-MEM, trace-mem, and oxgeneral AgentMem — research patterns with constrained maturity

**[GitHub]** A-MEM's NeurIPS 2025 repository builds LLM-enriched `MemoryNote` objects with generated metadata, Chroma retrieval, links, and neighbor evolution. Independent code review material flags process-local/unclear durable persistence and weak provenance/contradiction controls. Trace-mem is Apache-2.0 Python v0.1 alpha with HMAC-signed recalled trajectory spans and a small test/bench structure. oxgeneral's AgentMem is a claimed local SQLite/FTS/vector system with typed API, tiers, MCP/HTTP/CLI, and a visible test count, but it needs a license/release/security review before being treated as more than a design reference.

**Recommendation.** A-MEM validates that derived semantic enrichment should be explicitly distinguished from source observations; Rush must not allow it to rewrite canonical event meaning. Trace-mem validates a concrete integrity question: how to attach a compact tamper-evident provenance reference to recovered evidence. Prototype this only with a workspace-local key and rotation/deletion design; signatures cannot make a false source true. oxgeneral is a potential compact local UX reference, but no dependency decision until license, activity, threat model, and source inspection meet the same bar.

### 6.10 mcp-memory-service and ClawMem — useful negative evidence

**[GitHub]** mcp-memory-service is a broad Python REST/MCP/knowledge graph/consolidation platform with thousands of commits and multi-store support. GitHub's reviewed advisory `GHSA-2r68-g678-7qr3` documents a high-severity pre-10.65.3 path where read-scoped OAuth clients could call mutating MCP tools. ClawMem is MIT TypeScript/Bun with SQLite/FTS5/sqlite-vec, local models, many hooks/tools, optional HTTP, and a large retrieval/reranking/decay stack; it explicitly recommends WSL2 rather than native Windows.

**Recommendation.** Do not add either as a runtime component. Use the security advisory to require per-operation permission checks in Rush's MCP layer; use ClawMem's testable “memory vs context engine” separation as a terminology check: F5 handles transient projection, F1–F4 handle durable memory. Both demonstrate why a feature-rich server must not be mistaken for a safe, composable Rush dependency.

## 7. Adjacent landscape

### 7.1 Protocol and provider-neutral integration

| Project/standard | Verified scope | Rush recommendation |
|---|---|---|
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | Existing Rush dependency; tools/resources/structured output and fast-moving v2/spec work | Interoperate now through current locked SDK behavior; do a compatibility spike before F7 resources; keep stdio only. |
| [Agent Client Protocol](https://github.com/agentclientprotocol/agent-client-protocol) | Apache-2.0; stable protocol v1 negotiated by `initialize`; `session/new`, `session/load`, `session/prompt`, `session/update`; multiple official SDKs | Map an adapter envelope to negotiated capabilities. ACP native resume must remain optional and never replace Rush state/bundle. |
| [A2A](https://github.com/a2aproject/A2A) | Apache-2.0 open protocol for opaque agent applications; task/artifact/Agent Card concepts; samples warn all remote agent data is untrusted | Interoperate only after local bundle v1. No network A2A server or remote agent trust in early phases. |
| [Letta](https://github.com/letta-ai/letta) | Apache-2.0 stateful-agent platform with hosted/local client paths | No action; do not turn Rush into an agent platform. |

The protocol projects are standards/interop targets, not libraries to embed without version negotiation. This distinction is especially important because the current environment exposes MCP 1.29.0 while `pyproject.toml` declares 1.28.1, and MCP's 2026 specification/SDK line is moving quickly.

### 7.2 Context and token-efficiency systems

| Candidate | Relevant mechanism | Fit to F5 | Decision |
|---|---|---|---|
| Hindsight | retain/recall/reflect, budgeted retrieval, provider cache/usage surface | A useful benchmark/optional retrieval adapter | Spike only |
| Uteke | hybrid local FTS/vector/RRF and lifecycle | Could reduce recovery/source-search cost | Optional sidecar after F5 |
| ClawMem | intent routing, hybrid retrieval, reranking, compaction hooks | Good retrieval-pattern catalogue, high operational complexity | Borrow concepts only |
| Basic Memory | progressive MCP tool annotations, optional local reranking, Markdown source | Useful human-readable projected knowledge | Interoperate with derived Markdown only |
| Existing Rush primitives | `ContentRouter`, `ContextPacker`, `CCRStore`, `TelemetryStore`, AST skeletonizer/distillers | Direct ownership; requires correctness fixes rather than an external engine | Build/repair internally |

**[Inference]** No surveyed memory system makes Rush's token problem go away. Retrieval reduces the number of candidate objects; Rush still needs a target-token-aware compiler that preserves authority, evidence, omission accounting, and recovery. Treat stated token-savings percentages in external READMEs as claims to reproduce on Rush fixtures, not as integration evidence.

### 7.3 Coordination, shared state, provenance, and evaluation

| Candidate | Useful part | Rush boundary |
|---|---|---|
| Uteke Rooms | multi-agent shared namespace with author metadata | Borrow attribution/room semantics only; F9 still requires claim ownership, CAS, and evidence freshness. |
| TencentDB Agent Memory | chat/skill/wiki/code-graph asset taxonomy | Borrow category names only; no license-cleared/local-core evidence. |
| AgentMem | causal links, ground truth checks, long-run/ablation harnesses | Highest-priority evaluation design source. |
| trace-mem | signed trajectory-span references | Research local evidence-integrity mechanism; no trust claim without source verification. |
| Graphiti | temporal relationships and source episodes | Borrow validity/evidence concepts in F3. |
| `src/rush/mcp_mesh/lock_manager.py` | current advisory file locks | Preserve as migration input only; not sufficient shared state/concurrency control. |

### 7.4 Storage and indexing

SQLite remains the correct first persistence choice for Rush. The surveyed field validates FTS5, durable IDs, version chains, soft deprecation, and optional vectors as useful *indexes*, but it does not invalidate the plan's decision that an index is not truth. In particular, Rush should not make a vector database, external graph service, embedding model, or file watcher a phase-1 prerequisite. If semantic retrieval is later justified, require a feature-detected optional adapter and preserve exact field filters/FTS recovery.

## 8. Practical adoption recommendations

### Integrate now

- **None of the memory systems.** The only immediate external integration is continued use of the existing MCP SDK within Rush's declared/locked version boundary. This is a positive decision: it prevents a generic store from becoming a conflicting system of record.

### Adapt behind a Rush-owned abstraction

- **Uteke read-only retrieval:** optional executable adapter after F5 and only with explicit configuration/permissions.
- **Hindsight retrieval benchmark/adapter:** optional test dependency or sidecar in a separate spike environment; no default runtime requirement.
- **MCP resources:** add only after the locked dependency proves static/template resource behavior and stdio cleanliness.

### Borrow without code reuse

- AgentMem: proof-before-reminder, causal evidence, silence gating, long-run evaluations.
- Graphiti: valid-time source/evidence relationships and temporal invalidation vocabulary.
- Basic Memory: Markdown as a human-facing *derived* artifact, not internal truth; MCP tool annotations.
- Uteke: explicit soft-delete/deprecation lifecycle and attribution model.
- Hindsight: retain/recall/reflect separation and benchmark reporting.
- A-MEM: generated metadata must have lower authority than observed source content.

### Interoperate

- MCP tool/resource schemas; ACP negotiated sessions/capabilities; A2A task/artifact mapping; generic JSONL and consented Markdown formats.
- Require a version/capability record on every imported envelope; unknown required versions fail closed; imported source instructions are historical/nonportable.

### No standing external-product work

- No repository is assigned a “monitor” status. There is no watcher, owner, scheduled review, or backlog item.
- The technical-evaluation plan owns all remaining work on AgentMem, Graphiti, Uteke, Basic Memory, and MCP/ACP/A2A. Everything else is excluded from this roadmap unless a new user-requested decision names a changed constraint.

### Decline/defer

- OpenViking, TrueMemory, Basic Memory code reuse due to AGPL-3.0.
- Memmy Agent due to desktop/cloud-default scope.
- mcp-memory-service due to server complexity and documented authorization regression.
- ai-memory/ClawMem/JaceHo AgentMem lifecycle-hook integration due to no-unprompted-hook and local-control constraints.
- Mem0/Cognee/Graphiti/MemOS/Letta as a canonical state engine because that would weaken the evidence and projection differentiation Rush should own.

## 9. Plan separation

This report is evidence and recommendation only. It does not schedule experiments or implementation. The complete technical gates, including model/LLM, retrieval, token, safety, portability, and protocol work, are in [the technical-evaluation plan](innovations-memory-technical-evaluation-plan.md). The implementation-only file map and build sequence are in [the development plan](innovations-memory-development-plan.md). Development may begin only after the technical plan's D1–D6 decision record is fixed.

## 10. Risks, constraints, and questions that need decisions

| Risk / open question | Why it matters | Required mitigation or decision |
|---|---|---|
| Transcript capture default | Whole transcripts contain credentials, provider instructions, irrelevant text, and ambiguous authority. | Default to tool/task-bound typed events; raw blobs are optional private sources with span references, never automatic memory. |
| Cross-provider instruction injection | A historical system/developer message can be mistaken for current authority. | Preserve it only as a quarantined historical blob; renderer labels authority and never emits it as binding instruction. |
| False confidence from compressed summaries | A fluent projection can erase uncertainty or stale state. | Use claim status, provenance, omission manifest, and recovery IDs; abstain when mandatory evidence does not fit. |
| Token metric gaming | Reducing visible prompt tokens by hiding required material hurts task quality. | Judge F5 jointly on actual tokens, completion, recall, freshness, authority, and recovery—not token count alone. |
| SQLite concurrency / cross-worktree identity | Local projects can have multiple processes and divergent Git states. | Stable workspace/repository identity, transaction boundaries, lock policy, WAL evaluation, explicit divergence objects. |
| Embeddings / model downloads | They enlarge attack/privacy/runtime surface and cannot be assumed on an offline CLI. | FTS/exact retrieval first; semantic index optional, local, feature-detected, and disposable. |
| External license/security drift | AGPL, unclear licenses, and MCP authorization bugs can turn a shortcut into a product risk. | Keep optional experiments isolated; maintain an allowlist with license/security/release re-review. |
| Hosted or network paths | Rush is local-first and stdio-only. | No background service or network listener in core; external import data is untrusted; adapters require explicit configuration. |
| Existing state migration | Current session/checkpoint/preference artifacts have mixed semantics and incomplete provenance. | Treat them as low-authority import candidates; do not silently reinterpret them as canonical events. |
| F9 learning | “Learning” can preserve bad agent output and make it durable. | Defer; promote only attributable, evaluated, invalidatable observations with consent and rollback. |

Questions to resolve in the technical decision record: whether the bundle is per-workspace or user-portable by default; retention default and cryptographic deletion expectations; whether hashes are sufficient or local encryption-at-rest is required; exact supported provider envelope set; and the token budgets/Rush tasks that define a successful F5 release.

## 11. Appendix: repository inventory, research trail, and audit

### 11.1 Complete 30-repository inventory

The two cohorts are distinct by repository, not package name. “Local” means the project advertises an executable/self-hosted/local-store path; it does not mean Rush can safely adopt it. Activity/counts are 2026-08-23 snapshots where collected; `n/s` means the repository did not publish an SPDX identifier in the captured metadata rather than a conclusion about its legal status.

| Cohort | Repository / maintainer | Snapshot: lang, license, maturity/activity | Install/runtime, storage/provider/protocol | Memory mechanism, test/docs signal | Rush disposition / decisive risk |
|---|---|---|---|---|---|
| New | [Uteke — codecoradev](https://github.com/codecoradev/uteke) | Rust; Apache-2.0; 231★/25 forks/7 issues; v0.15.0 2026-08-19, active | Local binary; ~188MB first-run model; SQLite/FTS/HNSW; CLI/server/MCP | Rooms, author attribution, lifecycle/deprecation, hybrid RRF; strong README/release docs | Optional read-only adapter; do not delegate truth to its index. |
| New | [ai-memory — akitaonrails](https://github.com/akitaonrails/ai-memory) | Rust; MIT; 4,219★/310/9; v1.31.0 2026-08-22, active | Local CLI; Markdown-in-Git truth plus SQLite FTS5; lifecycle hooks | Sessions/observations/handoffs/audit ledger; active docs/tests | Borrow Git-visible/audit concepts; decline integration because auto config/commits/hooks violate Rush boundaries. |
| New | [memmy-agent — MemTensor](https://github.com/MemTensor/memmy-agent) | TypeScript; MIT; 928★/97/5; v1.0.9 2026-08-20, active | Node 22+, desktop/backend, cloud API default/BYOK | Consumer memory assistant; UI/cloud docs | Decline: wrong product/runtime and hosted-default scope. |
| New | [TrueMemory — buildingjoshbetter](https://github.com/buildingjoshbetter/TrueMemory) | Python; AGPL-3.0; 373★/47/18; last release/commit June | Python/MCP/hooks; SQLite FTS/sqlite-vec, tiered local models/telemetry option | Auto capture and benchmark claims; README/docs | Decline core: AGPL, large model tiers, capture posture, activity gap. |
| New | [OpenViking — Volcengine](https://github.com/volcengine/OpenViking) | Python; AGPL-3.0; 32,442★/2,479/499; v0.4.16 2026-08-21, active | Python/server-oriented context DB | Memory/RAG/skills context system; broad docs/community | Decline: AGPL and broad platform are incompatible with local Rush core. |
| New | [EverOS — EverMind-AI](https://github.com/EverMind-AI/EverOS) | Python; Apache-2.0; 12,366★/904/74; v1.2.3 2026-08-07 | Python agent memory stack; provider/model integrations | Persistent personal/agent memory docs | No roadmap action: broad platform and no Rush receipt semantics. |
| New | [TencentDB Agent Memory — TencentCloud](https://github.com/TencentCloud/TencentDB-Agent-Memory) | TypeScript; n/s; 23,999★/2,215/689; v2.0.0 2026-08-03 | Service/platform; chat, skill, wiki, code assets | Team-memory taxonomy, docs/examples | Borrow taxonomy only; unclear SPDX, service breadth, vendor coupling. |
| New | [Engram — Gentleman-Programming](https://github.com/Gentleman-Programming/engram) | Go; MIT; 6,133★/648/193; v1.20.0 2026-07-20 | CLI/service, local-oriented code knowledge workflow | Code/task memory documentation | Borrow UX vocabulary only; no canonical role. |
| New | [AgentMem — agentmem](https://github.com/agentmem/agentmem) | Python; Apache-2.0; early but actively documented | Python/uv; ground-truth repository/Git inputs; MCP surface | Out-of-band memories, causal links, pending context/silence gating, evaluation harness | Highest-value concept spike; no dependency while APIs mature. |
| New | [AgentMem — JaceHo](https://github.com/JaceHo/AgentMem) | Python; public repo, license/activity require re-check | Redis VectorSet/provider-oriented hooks | Automatic long/short-term memory | Decline: hooks, Redis/runtime, insufficient trust evidence. |
| New | [agent-memory / trace-mem — bettyguo](https://github.com/bettyguo/agent-memory) | Python; Apache-2.0; v0.1 alpha; 6★ snapshot | Python library; signed trajectory spans | HMAC provenance, small bench/test layout | Research spike only: promising integrity pattern, immature. |
| New | [ClawMem — yoloshii](https://github.com/yoloshii/clawmem) | TypeScript/Bun; MIT; 195★/32 forks | Local SQLite/FTS5/sqlite-vec/local models; MCP/hooks/optional HTTP; WSL2 recommended | 31 MCP tools, routing/rerank/decay docs | Borrow vocabulary/tests; decline runtime and hook/server complexity. |
| New | [AgentMemory — KuanChen01](https://github.com/KuanChen01/AgentMemory) | JavaScript; public prototype; license/activity require re-check | WASM SQLite/DeepSeek-backed summaries | Background memory/summary pattern | Decline: provider/background coupling and low assurance. |
| New | [A-MEM — WujiangXu](https://github.com/WujiangXu/A-mem) | Python; research code; NeurIPS 2025 | Chroma plus LLM metadata/enrichment | `MemoryNote`, links, neighbor evolution; paper/repo docs | Borrow “derived metadata is lower authority”; no dependency/persistence assumptions. |
| New | [mcp-memory-service — doobidoo](https://github.com/doobidoo/mcp-memory-service) | Python; mature/high-commit MCP server; security advisory applies pre-10.65.3 | REST/MCP, graph/consolidation, multi-store | Extensive docs/integrations; GHSA-2r68-g678-7qr3 | Decline: server complexity and documented read-to-write authorization flaw. |
| Popular | [Mem0 — mem0ai](https://github.com/mem0ai/mem0) | Python; Apache-2.0; 63,882★/7,471/680; ts-v3.1.6 2026-08-11, active | Python/TS; local/cloud/vector-LLM ecosystem | Extract/retrieve/update memories, broad SDK/docs/tests | Decline dependency: generic LLM memory creates a second source of truth. |
| Popular | [Graphiti — getzep](https://github.com/getzep/graphiti) | Python; Apache-2.0; 30,225★/3,058/488; v0.29.3 2026-07-27 | Python/MCP; Neo4j/FalkorDB/Neptune and LLM services | Episodes, temporal edges, hybrid retrieval; extensive docs | Borrow temporal/provenance design; no graph/service dependency. |
| Popular | [Letta — letta-ai](https://github.com/letta-ai/letta) | Python/API; Apache-2.0; 24,372★/2,591/40; v0.16.8 2026-05-14 | Stateful agent server/local/cloud client paths | Agent memory blocks, APIs/docs | Interoperate later only; agent-platform scope. |
| Popular | [Cognee — topoteretes](https://github.com/topoteretes/cognee) | Python; Apache-2.0; 30,199★/2,951/362; v1.5.3 2026-08-23 | Self-hosted/cloud; local API but LLM key/provider path | Knowledge graph/memory pipelines; active docs | Benchmark patterns only: dependency/model/store breadth. |
| Popular | [MemOS — MemTensor](https://github.com/MemTensor/MemOS) | TypeScript; Apache-2.0; 10,938★/1,004/77; v2.0.30 2026-08-14 | Platform SDK/services, MemCube abstractions | Memory OS, retrieval/management docs | Borrow portability vocabulary only; no roadmap action. |
| Popular | [Hindsight — vectorize-io](https://github.com/vectorize-io/hindsight) | Python; MIT; 20,974★/1,627/114; v0.9.1 2026-08-14, active | Python/Node/Go; Docker/Helm/bare/embedded pg0; provider LLMs | Retain/recall/reflect; good docs/integrations | Benchmark and optional sidecar spike, never default core. |
| Popular | [memU — NevaMind-AI](https://github.com/NevaMind-AI/memU) | Python; n/s; 14,338★/1,062/112; v1.5.1 2026-03 | Python/model/storage stack | Multimodal agent memory docs | Decline: license clarity and broad stack gap. |
| Popular | [Memori — MemoriLabs](https://github.com/MemoriLabs/Memori) | Python; n/s; 16,203★/3,227/33; v3.3.6 2026-05-28 | Python/agent platform | Long-term memory APIs/docs | Decline: SPDX/runtime scope is not acceptable core evidence. |
| Popular | [Memvid — memvid](https://github.com/memvid/memvid) | Rust; Apache-2.0; 16,441★/1,413/35; v2.0.140 2026-05-27 | Rust local durable media/container retrieval | File/container-style memory index; docs | Borrow portable-artifact ideas; not a claim/provenance engine. |
| Popular | [Basic Memory — basicmachines-co](https://github.com/basicmachines-co/basic-memory) | Python; AGPL-3.0; 1,742 commits/261 forks/68 issues; v0.22.1 in 2026 | Python/uv/MCP; Markdown truth, SQLite/Postgres/Milvus; optional cloud | Human/AI Markdown graph and tool annotations; robust docs | Derived-Markdown exchange spike only; no AGPL code/service dependency. |
| Popular | [LangMem — langchain-ai](https://github.com/langchain-ai/langmem) | Python; MIT; ~1.5k★/168/47 snapshot; no releases, maintenance concern | Python/LangGraph-native, any storage, LLM managers | Hot-path/background memory tools; docs/issues | Decline/defer: framework coupling, LLM mutation, weak maintenance signal. |
| Popular | [MemoryOS — BAI-LAB](https://github.com/BAI-LAB/MemoryOS) | Python; Apache-2.0; 1,558★/159/23; v1.2 2025-07 | Research implementation/provider stacks | Multi-level memory research code/paper | Research reference, not production dependency. |
| Popular | [MemMachine — MemMachine](https://github.com/MemMachine/MemMachine) | Python; Apache-2.0; 3,201★/208/95; v0.3.9 2026-05-18 | Python/storage/model components | Memory lifecycle/agent framework docs | No roadmap action: generic memory platform fit. |
| Popular | [ByteRover CLI — campfirein](https://github.com/campfirein/byterover-cli) | TypeScript; n/s; 4,948★/453/22; push 2026-06-25 | Developer-assistant CLI/platform | Code-memory sharing docs | Decline: service/platform, no local evidence model/license certainty. |
| Popular | [AgentMem — oxgeneral](https://github.com/oxgeneral/agentmem) | Python; public project, license/release re-check required | SQLite/FTS5/vectors; MCP/HTTP/CLI | Claims 5 tiers and 206 unit/107 quality tests | Pattern reference only pending due diligence; do not integrate. |

### 11.2 Remaining full score rationales

The main scorecard ranks the 17 candidates with a plausible near-term decision. The remaining 13 are also scored so every repository ends in build, borrow, bounded spike, no action, or decline. Scores are `I/A/B/D/S/T/K/R`; each tuple is followed by the short rationale. Weights remain `15/10/10/15/15/15/10/10` from section 3.

| Candidate | Score and rationale | Decision |
|---|---|---|
| MemMachine | `2/2/1/3/2/2/2/3` — Apache/Python help, but it remains generic lifecycle infrastructure without Rush authority/proof fit. | No roadmap action. |
| EverOS | `1/3/1/3/2/1/2/2` — broad platform demand signal, low local CLI/receipt fit. | No roadmap action. |
| TencentDB Agent Memory | `1/4/1/4/3/2/2/1` — strong uptake but vendor/service breadth and unclear SPDX make adoption risky. | Borrow taxonomy only. |
| Memvid | `2/2/2/3/2/2/3/3` — durable local artifact pattern is useful, but it solves packaged retrieval, not evidence state. | Borrow artifact concepts. |
| BAI MemoryOS | `2/2/2/3/2/2/2/2` — useful research vocabulary, weak production/integration evidence. | Research reference. |
| Memori | `1/2/1/3/2/1/2/2` — unverified license and platform scope dominate. | Decline. |
| memU | `1/3/1/3/2/1/2/2` — popularity does not offset license/model-stack uncertainty. | Decline. |
| ByteRover | `1/3/1/4/3/1/1/1` — code-memory product overlap, but service/provider coupling and no canonical-evidence fit. | Decline dependency. |
| JaceHo AgentMem | `1/2/1/4/2/2/2/2` — hooks/Redis/automatic capture conflict with the safety and local-control contract. | Decline. |
| KuanChen AgentMemory | `1/1/1/4/1/2/2/2` — prototype/provider summary mechanism is neither a stable runtime nor a trusted model. | Decline. |
| A-MEM | `1/2/4/3/4/3/2/2` — its source-versus-derived distinction is strategically useful, but research-code persistence, LLM enrichment, and Chroma dependence make it unsuitable to adopt. | Borrow authority discipline only. |
| mcp-memory-service | `1/2/1/5/2/1/0/0` — maturity is outweighed by server scope and the documented authorization regression. | Decline. |
| oxgeneral AgentMem | `2/1/3/3/2/2/3/2` — compact local SQLite/FTS ideas and reported tests are interesting, but license, release cadence, threat model, and source quality still need verification. | Pattern reference; no integration. |

### 11.3 Search/method audit and source timestamps

Searches used combinations of `agent memory`, `long-term memory`, `MCP memory`, `coding agent memory`, `context engineering`, `session handoff`, `temporal knowledge graph`, `local SQLite memory`, `AI memory GitHub`, and each mandatory name. Inclusion required a public repository with an identifiable memory/continuity mechanism; the newer cohort favored 2025–2026 releases or current rapid activity, while the popular cohort was sampled from high-visibility maintained projects. Repositories were deduplicated by GitHub owner/name, so similarly named AgentMem projects remain separate only where ownership and codebases are distinct.

Primary sources are the linked repository pages in the inventory, their READMEs, source layout, release histories, issue trackers, and the official protocol repositories linked in section 7. Repository metadata was collected/screened on **2026-08-23**; license/activity/security assertions should be re-run immediately before any dependency or code-reuse decision. Security-specific source: [GitHub advisory GHSA-2r68-g678-7qr3](https://github.com/doobidoo/mcp-memory-service/security/advisories/GHSA-2r68-g678-7qr3). Protocol primary sources: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [ACP](https://github.com/agentclientprotocol/agent-client-protocol), [A2A](https://github.com/a2aproject/A2A).

### 11.4 Requirement audit

| Requested check | Where satisfied |
|---|---|
| New document only; existing plan preserved | This report; no existing Rush/plan/config/dependency files changed. |
| Existing plan and actual Rush deeply reviewed | Sections 1–2; verified symbol/path corrections are explicitly called out. |
| 15 newer + 15 popular, 30 distinct, mandatory identities | Sections 4–6 and complete 30-row inventory in 11.1. |
| Per-repo owner, URL, language, license, activity, installs, runtime, storage, provider/protocol, mechanism, test/docs, risks | Section 11.1, with snapshot qualifications where GitHub did not expose SPDX or mature-release evidence. |
| Build/borrow/integrate/interoperate/research spike/decline decisions | Sections 1, 5–8, and every inventory row. |
| Eight-dimensional 0–5 scoring with rationale/rankings | Sections 3 and 5 plus 11.2. |
| Token reduction explicitly treated as a core deliverable | Sections 1 and 7.2; the acceptance contract is in the technical-evaluation plan. |
| File-level impact, technical plan, development plan, risks, source methodology | The two separate plans plus sections 9–11. |

No repository source, configuration, dependencies, hooks, releases, or existing plan were modified while producing this report.
