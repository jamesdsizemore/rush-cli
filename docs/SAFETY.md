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

