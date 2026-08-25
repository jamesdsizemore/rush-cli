# Rush Platform Master Backlog & Feature Tracker

> **Repository:** `jamesdsizemore/rush-cli`  
> **Python Baseline:** Python 3.12 (uv)  
> **Status:** All Milestones Complete (v0.3.0 Flagship)  
> **Core Contract:** FastMCP stdio transport, stderr NDJSON diagnostics, deterministic offline execution, zero docs drift.

---

## 1. Master Milestone Status (Phases 01–50)

| Phase Range | Milestone Focus | Key CLI Commands / Tools | Status |
|:---:|---|---|:---:|
| **00–08** | Core Platform Baseline | Canonical `ToolResult` shape, subprocess isolation, FastMCP stdio server | **Complete** |
| **09–19** | Core Quality Tools | Lint, format, typecheck, security, license, sbom, dead-code | **Complete** |
| **Phase 20** | AI Anti-Slop & Modular Boundaries | `rush slop`, `rush tdd`, AST anti-slop heuristics, Tach boundaries | **Complete** |
| **Phase 21** | Incremental Merkle Cache & Git Scoping | `rush cache`, SQLite WAL cache, SHA-256 flag salting, `--staged`/`--changed` | **Complete** |
| **Phase 22** | Unified Automated Remediation | `rush fix`, multi-engine auto-fixing, dry-run diff preview, rollback journal | **Complete** |
| **Phase 23** | Stack Onboarding & Config Init | `rush init`, `rush setup`, `rush config check`, 10+ stack heuristics | **Complete** |
| **Phase 24** | Workflow Suites & Environment Doctor | `rush check`, `rush audit`, `rush gate`, `rush doctor`, anti-shadowing | **Complete** |
| **Phase 25** | Real-Time File System Watcher | `rush watch`, async event loop, debouncing coalescer, process supervisor | **Complete** |
| **Phase 26** | Monorepo & Workspace Boundaries | `rush workspace list`, `graph`, `affected`, boundary import guard | **Complete** |
| **Phase 27** | Ephemeral Dashboard & Rich TUI | `rush dashboard`, `rush ui`, Starlette ASGI, session tokens, Textual | **Complete** |
| **Phase 28** | Trust-Gated Plugins & Agent Skills | `rush trust`, `rush plugin`, SHA-256 trust store, `SKILL.md` generator | **Complete** |
| **Phase 29** | Isolated AI Patch Remediation | `rush patch`, Git worktree sandbox, circuit breaker, SQLite memory | **Complete** |
| **Phase 30** | Packaging, Versioning & Hardened CI | `rush release`, `rush ci`, SemVer validator, 40-char SHA GitHub Actions | **Complete** |
| **Phase 31** | Agent Safety & Worktree Sandboxing | `rush guard`, command interceptor, Shannon entropy secret redactor | **Complete** |
| **Phase 32** | Token Economy & Context Optimization | `rush token count`, `outline`, BPE tokenizer, AST outline compressor | **Complete** |
| **Phase 33** | Full-Stack Sync & Type Safety Gates | `rush sync openapi`, `orm`, `zod`, FastAPI static AST route extractor | **Complete** |
| **Phase 34** | Codebase Hygiene & Merge Resolution | `rush hygiene dead-code`, `rush conflict solve`, 3-way AST merger | **Complete** |
| **Phase 35** | Polyglot AST Slicing & CodeGraph | `rush codegraph explore`, `slice`, Tree-Sitter polyglot, CPG store | **Complete** |
| **Phase 36** | Frontend Asset & Bundle Optimization | `rush bundle analyze`, `budget`, `dead-assets`, barrel auditor | **Complete** |
| **Phase 37** | Git Hotspots & Code Velocity | `rush hotspots analyze`, `churn`, `bus-factor`, temporal coupling | **Complete** |
| **Phase 38** | Agent Governance & Repo Scaffolding | `rush governance sync`, `scaffold init`, AGENTS.md compiler | **Complete** |
| **Phase 39** | Git Pre-Commit Intelligence & Hooks | `rush hook run`, `install`, `verify`, SHA-256 hook tamper detection | **Complete** |
| **Phase 40** | Multi-Model Consensus & Scorecard | `rush score compute`, `consensus reconcile`, 0–100% 6-pillar score | **Complete** |
| **Phase 41** | Foundations, BPE Distillers & Base Ship | `rush distill`, `rush ship init`, BPE token metrics | **Complete** |
| **Phase 42** | TOON v4.1, AST Skeletons & Ship Gate Cockpit | `rush toon-inspect`, `rush skeletonize`, `rush ship gate` | **Complete** |
| **Phase 43** | CCR Chunk Store, Grounding & Mistake Memory | `rush context-cache`, `rush ccr-retrieve`, `rush hallu-guard`, `rush context-mistakes` | **Complete** |
| **Phase 44** | Context Packing & Prompt Cache Alignment | `rush context pack`, `rush context align-prompt`, `rush_context_pack` | **Complete** |
| **Phase 45** | GAIN TUI Telemetry & Terse Persona | `rush context gain`, `rush context persona`, `rush_context_gain_stats` | **Complete** |
| **Phase 46** | Blast Radius & Architecture Guard | `rush blast-radius`, `rush arch-guard`, `rush_blast_radius`, `rush_arch_guard` | **Complete** |
| **Phase 47** | Test-Heal & Public API Diff | `rush test-heal`, `rush api-diff`, `rush_test_heal`, `rush_api_diff` | **Complete** |
| **Phase 48** | DB Drift, Simplify & Strictify | `rush db-drift`, `rush simplify`, `rush strictify`, `rush_db_drift`, `rush_simplify` | **Complete** |
| **Phase 49** | Traceability, Flight Recorder & Swarm Merge | `rush trace`, `rush flight-recorder`, `rush swarm-merge`, `rush simulate-ci` | **Complete** |
| **Phase 50** | SLSA Attestation, Security Suite & Flagship Release | `rush attest`, `rush license-matrix`, `rush iam-audit`, `rush dead-asset`, `rush pr-synthesize` | **Complete** |
| **Benchmark Harness** | Reproducible Verification & Provider Routing (Phases B1–B6) | `scripts.benchmarks.run`, 40 declared scenarios, 11 decision records, CI harness | **Complete** |

---

## 2. Continuity implementation program

| Backlog ID | Title | Status | Priority | Planned phase | Related tasks | Dependencies | User / agent value | Priority reason | Deferral rationale | Linked issues | Linked commit |
|---|---|---|:---:|---|---|---|---|---|---|---|---|
| BL-P1-00 | Phase 1 discovery and seam selection | Complete | P0 | P1 | P1-T00 | Clean worktree; local RTK/Graft/context-mode evidence | Grounds the shared continuity contract in existing code | All later phases require an exact parity seam | None | ISS-P1-00 | Phase 1 commit |
| BL-P1-01 | Shared session continuity ToolResult seam | Complete | P0 | P1 | P1-T01 | BL-P1-00 | Gives CLI and MCP one canonical save/list/restore contract | Required base contract | None | ISS-P1-01 | Phase 1 commit |
| BL-P1-02 | Continuity permission and catalog contract | Complete — existing contract used | P0 | P1 | P1-T02 | BL-P1-01 | Makes write behavior explicit, denied by default, and inspectable | Prevents unauthorised state writes | No configuration added: only invocation permission may grant persistence | ISS-P1-01 | Phase 1 commit |
| BL-P1-03 | Phase 1 tracker and documentation reconciliation | Complete | P0 | P1 | P1-T03, P1-DOC, P1-V | BL-P1-01, BL-P1-02 | Keeps public contract, documentation, and implementation aligned | Required phase completion evidence | None | ISS-P1-00, ISS-P1-01, ISS-P1-DOC-COUNT, ISS-P1-VERIFY, ISS-PROGRAM-GATES | Phase 1 commit |
| BL-P2-00 | Provenance-aware handoff | Active | P0 | P2 | P2-T00–P2-T02 | P1 commit; BG-PRIV | Gives a resumed agent redacted, authority-labelled evidence | P2-T01 produces the missing authority evidence before receipt integration | ISS-BG-AUTH, ISS-BG-PRIV | None | Pending P2 commit |
| BL-P2-01 | Authority/redaction evidence contract | Planned | P0 | P2 | P2-T01 | BL-P2-00; BG-PRIV | Prevents historic instructions and secrets from becoming active handoff state | Required before receipt integration | BG-AUTH is generated from P2-T01 red/green evidence | ISS-BG-AUTH, ISS-BG-PRIV | Pending P2 commit |
| BL-P2-02 | Inspectable handoff receipts | Planned | P0 | P2 | P2-T02 | BL-P2-01; BG-AUTH pass | Gives user and MCP bounded goal/frontier/failure evidence | Required restore outcome without a completion claim | None | ISS-BG-AUTH | Pending P2 commit |
| BL-P3-00 | Grounded context envelope | Blocked | P0 | P3 | P3-T00–P3-T03 | P2 commit; BG-CTX | Gives agents bounded selected context and recovery handles | Context envelope semantics require an approved gate | ISS-PROGRAM-GATES | Missing decision record and P2 predecessor | N/A |
| BL-P4-00 | Coordination and recovery evidence | Blocked | P0 | P4 | P4-T00–P4-T03 | P3 commit; BG-COORD | Prevents silent ownership conflicts and stale recovery | New coordination semantics require an approved gate | ISS-PROGRAM-GATES | Missing decision record and P3 predecessor | N/A |
| BL-P5-00 | Approved provider interoperability | Blocked | P0 | P5 | P5-T00–P5-T03 | P4 commit; route-specific BG-PROV/BG-9R/BG-OMNI/BG-PROTO | Lets users deliberately select only validated provider/CLI routes | No adapter is permitted without its named route decision | ISS-PROGRAM-GATES | Missing canonical route records and P4 predecessor | N/A |
