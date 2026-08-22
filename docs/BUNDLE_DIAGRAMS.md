# Rush Subsystem & Bundle Architecture Diagrams

Rush is engineered as a unified, modular quality intelligence platform. To help developers, team leads, and AI agents visualize how each capability fits together, this document provides complete, high-fidelity visual architecture and sequence diagrams for each of Rush's 9 core subsystems ("bundles").

---

## 1. Core Code Quality & Automated Remediation Bundle

The Core Code Quality bundle orchestrates static analysis, deterministic heuristics, AST pattern matching, AI anti-slop filtering, and non-destructive automated remediation.

```mermaid
flowchart TB
    subgraph Input["Source & Project Input"]
        Src["Source Files (.py, .ts, .js, .rs, .go)"]
        Config["rush.toml Configuration"]
    end

    subgraph Router["Language Router & Applicability"]
        LangDetect["Language & Framework Detection"]
        ScopeFilter["Changed-File / Staged Scope Filter"]
    end

    subgraph QualityEngines["Quality & Linting Engines"]
        direction TB
        Ruff["Ruff (Python Lint/Format)"]
        ESLint["ESLint / Biome (JS/TS)"]
        Mypy["mypy / tsc (Type Checking)"]
        SloppyLint["sloppylint (AI Anti-Slop)"]
        Radon["Radon / Sentrux (Complexity)"]
        Vulture["Vulture / Knip (Dead Code)"]
    end

    subgraph Aggregator["Canonical Normalization & Aggregation"]
        Norm["ToolResult Normalizer"]
        WorstStatus["Worst-Status-Wins Logic (error > fail > warn > ok > skipped)"]
        Redact["Secret & Token Redactor ([REDACTED])"]
    end

    subgraph Remediation["Automated Remediation (rush fix)"]
        DryRun{"--dry-run Mode?"}
        Preview["Display Unified Diff Preview"]
        Apply["Apply Confined File Modifications"]
    end

    subgraph Output["Outputs & Transports"]
        CLI_Out["Human CLI Output"]
        JSON_Out["Canonical JSON-RPC / CLI JSON"]
        SARIF_Out["SARIF 2.1.0 Static Analysis Export"]
        HTML_Out["Interactive Single-File HTML Dashboard"]
    end

    Src --> LangDetect
    Config --> LangDetect
    LangDetect --> ScopeFilter
    ScopeFilter --> QualityEngines
    QualityEngines --> Norm
    Norm --> WorstStatus
    WorstStatus --> Redact
    Redact --> DryRun
    DryRun -- Yes --> Preview
    DryRun -- No --> Apply
    Redact --> CLI_Out
    Redact --> JSON_Out
    Redact --> SARIF_Out
    Redact --> HTML_Out
```

---

## 2. Test Intelligence & Reliability Bundle

The Test Intelligence bundle provides deep confidence scoring through test execution, Test-Driven Development (TDD) validation, and dual-mode evidence importers for coverage, mutation, property-based testing, and flaky test detection.

```mermaid
flowchart TB
    subgraph TestSources["Test Code & Artifacts"]
        TestFiles["Unit / Integration Tests (*_test.py, *.spec.ts)"]
        Reports["Structured Test Reports (coverage.json, junit.xml, pact.json)"]
    end

    subgraph TDD_Gate["TDD Guard & Contract Check (rush tdd)"]
        ModCheck["Modified Source Scanner"]
        TestExist{"Contract / Test Exists?"}
        TDDFail["Status: FAIL (Missing Test Contract)"]
        TDDPass["Status: OK (Test Contract Verified)"]
    end

    subgraph ExecutionSubsystem["Execution & Dual-Mode Importers"]
        direction TB
        Pytest["pytest / Vitest (Test Runner)"]
        CoverageImp["Coverage Importer (Coverage.py / LCOV / Cobertura)"]
        MutMut["Mutation Engine (Mutmut / Stryker / Cargo-mutants)"]
        Hypothesis["Property-Based Testing (Hypothesis / fast-check)"]
        FlakyDetect["Flaky Test Quarantine & Rerun Engine"]
    end

    subgraph Permissions["Permission Gatekeeper"]
        PermSlow{"--allow-slow enabled?"}
        PermNet{"--allow-network enabled?"}
        SkipReport["Status: SKIPPED (Requires explicit permission)"]
    end

    subgraph TestMetrics["Evidence Aggregation"]
        MetricCalc["Calculate Coverage %, Branch %, Mutation Score"]
        CanonicalResult["Canonical ToolResult Normalization"]
    end

    TestFiles --> ModCheck
    ModCheck --> TestExist
    TestExist -- No --> TDDFail
    TestExist -- Yes --> TDDPass
    TDDPass --> ExecutionSubsystem
    Reports --> CoverageImp
    ExecutionSubsystem --> PermSlow
    PermSlow -- No --> SkipReport
    PermSlow -- Yes --> MetricCalc
    CoverageImp --> MetricCalc
    MetricCalc --> CanonicalResult
```

---

## 3. Security, Privacy & Supply Chain Bundle

The Security and Supply Chain bundle provides defense-in-depth across code privacy, SAST, high-entropy secrets, software bill of materials (SBOM), and AI safety evaluation.

```mermaid
flowchart LR
    subgraph Targets["Project Targets"]
        SrcCode["Source Code"]
        Dependencies["Package Manifests (uv.lock, package-lock.json)"]
        Container["Containerfile / Dockerfile"]
        Prompts["AI Prompts & Agent Systems"]
    end

    subgraph SecurityScanners["Security & Attestation Engines"]
        direction TB
        Secrets["Secret Scanners (Gitleaks, TruffleHog, detect-secrets)"]
        SAST["Deep SAST & Privacy (Semgrep, Bearer, Horusec)"]
        DepAudit["Dependency Auditing (pip-audit, npm-audit, OSV-Scanner)"]
        SBOM["SBOM & License Attestation (cdxgen, ScanCode, OpenSSF Scorecard)"]
        AIEval["AI Safety & LLM Evaluation (Promptfoo, Garak, DeepEval)"]
    end

    subgraph RedactionFilter["Safety & Redaction Filter"]
        RedactEngine["High-Entropy Token & Password Redaction ([REDACTED])"]
        PathContain["Filesystem Containment Check"]
    end

    subgraph FindingsStore["Audit Findings & Export"]
        VulnStore["Vulnerability & Copyleft Risk Ledger"]
        SARIFExport["SARIF 2.1.0 Export"]
        ScoreCard["Security Pillar Score (0–100%)"]
    end

    SrcCode --> Secrets & SAST
    Dependencies --> DepAudit & SBOM
    Prompts --> AIEval
    Secrets & SAST & DepAudit & SBOM & AIEval --> RedactEngine
    RedactEngine --> PathContain
    PathContain --> VulnStore
    VulnStore --> SARIFExport & ScoreCard
```

---

## 4. Polyglot Infrastructure & Domain Languages Bundle

Rush provides dedicated, zero-configuration parsers and linters for non-code infrastructure, databases, configuration, and documentation.

```mermaid
flowchart TD
    subgraph InfraFiles["Infrastructure & Configuration Files"]
        MD["Markdown Docs (*.md)"]
        YML["YAML & OpenAPI (*.yaml, *.yml)"]
        SQL["SQL Schemas & Migrations (*.sql)"]
        HTML["Templates (*.html, *.jinja)"]
        Docker["Dockerfiles (Dockerfile, *.containerfile)"]
        Terraform["Terraform & K8s (*.tf, *.k8s.yaml)"]
        GHA["GitHub Actions (.github/workflows/*.yml)"]
    end

    subgraph InfraEngines["Domain-Specific Adapters"]
        MDLint["markdownlint-cli (v0.49.1 JSON Isolation)"]
        Spectral["Spectral / Zally (OpenAPI & YAML Rules)"]
        SQLFluff["SQLFluff / Atlas / Squawk (Schema Safety)"]
        DjLint["djLint / HTML-Validate (Template Hygiene)"]
        Hadolint["Hadolint / Dockle (Container CIS Benchmark)"]
        TFLint["TFLint / Checkov / Terrascan (IaC Policy)"]
        Actionlint["Actionlint (GitHub Actions Syntax & Secrets)"]
    end

    subgraph NormalizedOutput["Unified Canonical Results"]
        Findings["Infrastructure Findings (Rule, Line, Col, Severity)"]
    end

    MD --> MDLint
    YML --> Spectral
    SQL --> SQLFluff
    HTML --> DjLint
    Docker --> Hadolint
    Terraform --> TFLint
    GHA --> Actionlint

    MDLint & Spectral & SQLFluff & DjLint & Hadolint & TFLint & Actionlint --> Findings
```

---

## 5. Modern Web, UI & Visual Regression Bundle

The Modern Web and UI bundle delivers comprehensive web vitals, end-to-end browser automation, visual regression baseline comparison, and bundle chunk transfer auditing.

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer / Agent
    participant CLI as Rush CLI (rush e2e / visual / bundle)
    participant Perm as Permission Interceptor
    participant Headless as Playwright / Headless Browser
    participant DiffEngine as Pixelmatch / Squoosh / BundleEngine
    participant Report as Canonical ToolResult / HTML Report

    Dev->>CLI: rush visual . --accept --allow-browser --allow-slow
    CLI->>Perm: Check --allow-browser and --allow-slow
    alt Permissions Denied
        Perm-->>CLI: Return SKIPPED (Reason: Browser execution disabled)
        CLI-->>Dev: Print structured skipped result
    else Permissions Granted
        Perm->>Headless: Launch isolated browser process
        Headless->>Headless: Capture viewport snapshot at 1280x720 & 375x667
        Headless->>DiffEngine: Compare current snapshot against baseline
        DiffEngine->>DiffEngine: Calculate visual delta & perceptual diff %
        DiffEngine-->>CLI: Visual mismatch findings or baseline update
        CLI->>Report: Compile visual evidence artifact
        Report-->>Dev: Status: OK / WARN (Visual diff report generated)
    end
```

---

## 6. Workspace, Caching & Performance Bundle

The Workspace and Caching bundle accelerates multi-package monorepos with topological DAG execution, content-hashed result caching, and real-time debounced file watching.

```mermaid
flowchart TB
    subgraph Monorepo["Monorepo & Workspace Discovery"]
        Manifests["pnpm-workspace.yaml, package.json, Cargo.toml"]
        WorkspaceDetect["Workspace Topology & Dependency DAG"]
        AffectedCalc["Git Diff Affected Package Calculator"]
    end

    subgraph Caching["Flag-Salted Merkle Result Cache (.rush/cache.db)"]
        ContentHash["Source Files Content SHA-256"]
        FlagSalt["CLI Flags & Engine Version Salt"]
        CacheLookup{"Cache Hit in SQLite?"}
        ServeCache["Serve Cached ToolResult (0ms)"]
    end

    subgraph Execution["Parallel Engine Execution"]
        TopologicalRun["Topological Package Runner"]
        Watcher["Real-Time Multi-Threaded Watcher (300ms Debounce)"]
    end

    subgraph Dashboard["Local In-Memory Dashboard (rush dashboard)"]
        HTTPServer["Ephemeral HTTP Server on 127.0.0.1"]
        SecurityGating["CSRF Origin Check + Ephemeral Token Auth"]
        RichTUI["Rich Terminal UI (rush tui)"]
    end

    Manifests --> WorkspaceDetect
    WorkspaceDetect --> AffectedCalc
    AffectedCalc --> ContentHash
    ContentHash --> FlagSalt
    FlagSalt --> CacheLookup
    CacheLookup -- Yes --> ServeCache
    CacheLookup -- No --> TopologicalRun
    Watcher --> AffectedCalc
    TopologicalRun --> HTTPServer
    HTTPServer --> SecurityGating
    SecurityGating --> RichTUI
```

---

## 7. Agentic Safety, Sandboxing & Skills Bundle

The Agentic Safety bundle surrounds autonomous coding agents (Cursor, Claude Code, Cline, Windsurf, Hermes) with strict safety boundaries, destructive command interception, ephemeral worktree sandboxes, atomic patch rollbacks, and multi-turn session memory.

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Autonomous AI Agent
    participant Safety as Rush Safety Guard (rush safety)
    participant Sandbox as Git Worktree Sandbox (rush patch)
    participant Verifier as Test & Syntax Verifier
    participant Memory as Session Memory Ledger (rush memory)
    participant Repo as Working Tree Repository

    Agent->>Safety: Propose Command: `rm -rf /` or `git reset --hard`
    Safety->>Safety: Evaluate Destructive Pattern Rules
    Safety-->>Agent: [INTERCEPTED] Destructive command blocked by safety guard

    Agent->>Sandbox: Propose Remediation Patch (diff)
    Sandbox->>Sandbox: Create isolated temporary worktree branch
    Sandbox->>Sandbox: Apply patch inside sandbox
    Sandbox->>Verifier: Run syntax checks and test suite
    alt Verifier Fails / Introduces Regression
        Verifier-->>Sandbox: Tests Failed
        Sandbox->>Sandbox: Rollback patch, destroy temporary worktree
        Sandbox->>Memory: Log failure rationale and error trace
        Sandbox-->>Agent: Patch rejected; circuit breaker engaged
    else Verifier Passes 100% Green
        Verifier-->>Sandbox: All tests and linters passed
        Sandbox->>Repo: Promote clean patch to main working tree
        Sandbox->>Memory: Record successful remediation turn
        Sandbox-->>Agent: Patch applied and verified safely
    end
```

---

## 8. Full-Stack Sync & Token Economy Bundle

The Full-Stack Sync and Token Economy bundle optimizes LLM prompt efficiency, prevents context overflow, and guarantees type safety between frontend interfaces and backend APIs.

```mermaid
flowchart LR
    subgraph FullStack["Backend APIs & Data Models"]
        FastAPI["FastAPI / Django Models"]
        OpenAPI["OpenAPI 3.1 Spec (openapi.json)"]
        EnvFiles[".env vs .env.example"]
    end

    subgraph SyncEngine["Full-Stack Sync (rush sync)"]
        ExtractSchema["Extract Server Schemas"]
        VerifyParity["Verify Contract Parity"]
        GenerateTS["Generate TypeScript Types (.d.ts)"]
        CheckEnv["Environment Variable Parity Check"]
    end

    subgraph TokenOptimization["Token Economy Engine (rush token)"]
        BPE["BPE Token Counter (tiktoken / GPT-4o / Claude)"]
        Compressor["AST Outline Compressor (strip bodies/docstrings)"]
        CacheAdvisor["Prompt Prefix Cache Optimizer"]
    end

    subgraph AgentContext["Optimized Agent Prompt Context"]
        CompactTypes["Type-Safe Synchronized TypeScript API"]
        LeanOutline["70% Compressed Source Outline"]
        CachedSystem["High-Efficiency Prompt with Minimal Token Cost"]
    end

    FastAPI --> ExtractSchema
    ExtractSchema --> OpenAPI
    OpenAPI --> VerifyParity
    VerifyParity --> GenerateTS
    EnvFiles --> CheckEnv
    GenerateTS --> CompactTypes

    BPE --> Compressor
    Compressor --> LeanOutline
    CacheAdvisor --> CachedSystem
```

---

## 9. Repository Intelligence, Governance & Consensus Bundle

The Repository Intelligence bundle combines Git churn risk analysis, multi-IDE rule synchronization, sub-second pre-commit intelligence, multi-model AI consensus reconciliation, and unified 6-pillar repository health scoring.

```mermaid
flowchart TD
    subgraph GitRepo["Git Repository & Commit History"]
        Commits["Git Commit Logs & Churn Frequency"]
        Staged["Staged Changes (.git/index)"]
        AgentsRules["Canonical AGENTS.md"]
    end

    subgraph IntelligenceEngines["Repository Intelligence Engines"]
        Hotspots["Hotspot Analyzer (Churn x McCabe Complexity = Defect Risk)"]
        HookGuard["Pre-Commit Hook Guard (AST lint, Trojan Source Unicode, Merge Markers)"]
        Governance["Rule Synchronizer (Emits .cursorrules, .clinerules, .windsurfrules)"]
    end

    subgraph ConsensusSubsystem["Multi-Model Consensus (rush consensus)"]
        ModelA["Claude 3.7 Sonnet Findings"]
        ModelB["GPT-4o Findings"]
        ModelC["Gemini 2.5 Pro Findings"]
        WeightedVote["Weighted Agreement Reconciliation Filter"]
    end

    subgraph Scorecard["6-Pillar Quality Scorecard (rush score)"]
        P1["1. Type Safety (mypy/tsc)"]
        P2["2. Test Coverage (pytest/vitest)"]
        P3["3. Code Health (ruff/eslint/complexity)"]
        P4["4. Security & Secrets (gitleaks/semgrep)"]
        P5["5. Token Economy (context density)"]
        P6["6. Governance (rule compliance)"]
        HealthScore["Deterministic Composite Health Grade (0–100% / A+ to F)"]
        SVGBadge["SVG Quality Badge & PR Card"]
    end

    Commits --> Hotspots
    Staged --> HookGuard
    AgentsRules --> Governance

    ModelA & ModelB & ModelC --> WeightedVote

    Hotspots & HookGuard & Governance & WeightedVote --> P1 & P2 & P3 & P4 & P5 & P6
    P1 & P2 & P3 & P4 & P5 & P6 --> HealthScore
    HealthScore --> SVGBadge
```
