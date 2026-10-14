# Your first ten minutes with Rush

This walkthrough uses the current editable source checkout, runs a local deterministic review, and returns machine-readable output. Complete beginner installation, automatic agent connection, comprehensive scan/repair/rescan, and project readiness remain planned in [Phase 65](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md).

## 1. Confirm the command and check environment health

```bash
uv run rush --help
uv run rush status .
uv run rush doctor .
```

`rush status` (also bare `uv run rush` from inside the project) prints a read-only summary: registration/config state, detected engines, current activity, latest attempt, published result, agent registration state, and useful memory count; it changes nothing. `rush doctor` diagnoses your local environment health, verifies PATH precedence, checks virtual environments, and flags binary shadowing.

## 2. Initialize and validate configuration

```bash
# Generate a tailored rush.toml configuration file
uv run rush init .

# Verify configuration validity
uv run rush config check .
```

Current `rush setup` does not provide the verified integrated installation route required by [Phase 65, P65-02](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-02--install-complete-applicable-toolchains-f3031). Do not use it as beginner installation evidence.

## 3. Run the fast inner-loop check suite

```bash
uv run rush check .
```

`rush check` runs six steps in order — `format` (check-only), `lint`, `typecheck`, `dead`, `slop`, `test` — and reports every one by default; the `test` step needs `--allow-build` and is otherwise `skipped` with the permission reason. A missing optional engine can also produce `skipped`; inspect JSON before treating the suite as complete evidence. When the run actually used or wrote memory records, the summary ends with one clause naming how many prior records it read and wrote (for example `memory: read 1 prior record, wrote 1 record`); the clause is absent when neither happened. `ok`/`skipped` exit 0, `warn`/`fail` exit 1, and `error` exits 2 — a mandatory step that comes back `skipped` still exits 0, so treat that as something to inspect, not proof it ran.

## 4. Current UI and dashboard limits

```bash
# Current one-shot terminal summary
uv run rush ui .

# Current local web prototype
uv run rush dashboard .
```

These commands exist, but current implementations do not satisfy the accepted persistent TUI and complete web workflow. **Status: planned — implementation [Phase 66](../phase-plans/phase-66-interactive-tui-and-local-web-plan.md).**

## 5. Review and safe automated remediation

```bash
# Review deterministic heuristics
uv run rush review src --json

# Inspect available fix options; bounded Ruff remediation
uv run rush fix --help
```

[`fix PATH --dry-run --force`](../phase-plans/phase-64-implementation-evidence.md#p64-01--preserve-checkoutindex-during-fixes-f01) preserves checkout/index state for Ruff-selected Python targets. Apply requires `--allow-artifact-write`; P64-04 remains planned.

## What to do next

- Build a before-PR routine with [Everyday workflow](../user-guide/everyday-workflow.md).
- Configure a project only after the defaults are understood: [Configuration cookbook](../reference/configuration-cookbook.md).
- Connect an assistant with [MCP client setup](../integrations/mcp-client-setup.md).
