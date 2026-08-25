# Safety overview

Rush is designed to make the safe action the default.

- **No implicit installs.** Missing optional engines return `skipped`.
- **No silent source rewrite.** Review/check commands are read-only; formatter mutation is an explicit path and `--check` is available.
- **No hidden publication.** Release is dry-run; publication execution is intentionally unavailable.
- **No history rewrite.** Commit-message checking never changes Git.
- **No network service.** MCP is local stdio only.
- **Explicit execution permissions.** Browser, slow, network, download, build, and artifact-write operations require explicit permission flags (`--allow-*`) and report structured `metadata.execution`.
- **No model marketing beyond implementation.** Review is deterministic; Graft is explicit; `--llm` makes no provider call.
- **No secrets in normalized logs/results.** Obvious secret assignments are redacted, but raw external tool behavior still deserves care.
- **No automatic coordination recovery.** Continuity may surface local ownership, stale evidence, merge conflicts, and redacted recovery receipts, but it never unlocks, merges, replays, or retries on the caller’s behalf.
- **No historic instruction promotion.** Session handoff stores historic-instruction presence only as quarantined evidence; it never becomes a current directive.
- **No silent stale replay.** Restore recomputes declared dependency hashes and labels changed or missing dependencies `stale`; legacy checkpoints remain `unknown` rather than being migrated automatically.
- **Autonomous Agent Safety & Worktree Sandboxing.** Dangerous shell commands (`rm -rf`, `drop table`, `reset --hard`) are intercepted via `rush guard check-cmd`; filesystem writes are strictly confined to workspace boundaries via `rush guard check-path`; AI remediation patches run in isolated Git worktree sandboxes with circuit breakers.
- **Subagent Acyclic Invocations.** Hierarchical agent execution trees are validated to guarantee bounded call depth and acyclic DAG topology.

```mermaid
flowchart TD
  A[Request / Agent Command] --> B{Safe Command & In-Bounds Path?}
  B -- no --> C[Intercept & Block Execution]
  B -- yes --> D{Ordinary local check?}
  D -- yes --> E[Run applicable installed engine]
  D -- no --> F{Explicit granted permission?}
  F -- no --> G[Return skipped / refuse]
  F -- yes --> H[Run bounded capability in Worktree Sandbox]
  E --> I[Normalize and redact result]
  H --> I
```

Read [Permissions](safety/permissions.md), [Privacy](safety/privacy-and-data-handling.md), and [Security model](safety/security-model.md).


## Context Safety, Grounding & Secret Redaction (Phases 41–43)
* **Secret Redaction**: `PackageLinter` and all Rush transports redact keys as `[REDACTED]`.
* **Phantom Package Defense**: `GroundingVerifier` parses AST imports against `sys.stdlib_module_names` and `importlib.metadata.distributions()` to block supply-chain typosquatting and hallucinated libraries.
* **Failure Ledger**: `FailureLedger` records failed patch AST fingerprints in `.rush/memory/failures.db` to prevent repetitive error loops.
