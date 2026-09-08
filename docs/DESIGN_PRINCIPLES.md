# Rush Design Principles & Architecture Invariants

Rush is built on ten architectural principles that guide all development, engine integrations, and Model Context Protocol (MCP) implementations across Phases 01 through 19:

---

## 1. Dual Transport, Single Implementation
Both Click CLI (`src/rush/cli.py`) and FastMCP (`src/rush/mcp.py`) invoke the exact same `ToolFn` objects in `src/rush/tools/`. Transport layers never duplicate engine logic.

## 2. Safe, Local & Non-Mutating Defaults
Safe inspection is the required design contract. External test tools may write artifacts; `fix --dry-run` currently destroys user changes (F01). See [Known issues](KNOWN_ISSUES.md) before relying on current safety claims.

## 3. Dynamic Engine Discovery with Non-Fatal Absence
Rush discovers tools from the host environment. Missing optional engines return structured `status: "skipped"` results with actionable install hints—never crashing and never running silent background downloads.

## 4. Canonical Normalized Findings & Secret Redaction
All findings conform to the `Finding` schema with stable SHA-256 fingerprints, file coordinates, severity, and rule IDs. Obvious secrets and tokens are redacted as `[REDACTED]`.

## 5. Explicit Execution Permissions (`--allow-*`)
Capabilities involving network requests, database compilation, heavy mutation, long runs, or browser execution are denied by default and require explicit invocation-scoped consent flags.

## 6. Subprocess Boundary & MCP Isolation
All external engine invocations use `run_subprocess()` with `stdin=DEVNULL`, `shell=False`, and timeout management, guaranteeing that child engines cannot corrupt MCP stdio JSON-RPC streams.

## 7. Dual-Mode Operation (Import vs. Execute)
Report import exists. Mutation/contract/fuzz/load live paths currently run version probes rather than workloads; real execution remains planned in P64-08–P64-11.

## 8. Bounded Configuration Discovery
`rush.toml` discovery walks upward from the target directory and strictly stops at the `.git` repository boundary, preventing unintended inheritance from parent directories.

## 9. Fixture-First Testing & Zero-Drift Documentation
Every engine is backed by deterministic report fixtures (`tests/fixtures/engine_reports/`). The recursive checker (`scripts/sync_docs.py --check`) validates coverage, local links and current registration schemas; it does not prove prose truth or runtime readiness.

## 10. Honest Model & Privacy Boundaries
Default code review is deterministic. `--llm` can call a configured provider to summarize findings. Rush never claims AI model verification without verified implementation.
