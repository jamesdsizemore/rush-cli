# P1 transport dispatch receipt

Scope: `src/rush/memory/transport.py`, `tests/test_phase61_transport.py`.
No commit or push performed. No provider credentials used, model queried, or live provider launched.

## Root cause and behavior

Original `dispatch` returned `ok` from SDK/package presence without sending content.
Native Claude now calls public `claude_agent_sdk.query` with `ClaudeAgentOptions`,
consumes its result stream, and requires `ResultMessage(subtype="success", is_error=False)`.
ACP now imports actual `acp` module and requires explicit caller-supplied
`acp_command=(executable, *arguments)`; no provider commands or flags invented.
It uses `spawn_agent_process`, initializes protocol, creates session with absolute
repository cwd and no MCP servers, sends `text_block` payload and requires
`PromptResponse.stop_reason == "end_turn"`.

Payload is JSON preserving exact `source` and `content`. Both remote tiers require
`ExecutionPermissions(network=True)` before invocation. Claude receives no builtin
tools or settings sources; both permission callbacks deny tool execution and denial
makes dispatch non-success. Provider errors, absent acknowledgement, cancelled ACP
turns and timeout return `error` without exception text/payload disclosure or file
fallback. Capability absence retains existing permission-gated dedicated-file fallback.
Synchronous dispatch refuses calls inside an already-running event loop.

`timeout_seconds` defaults to 30. Native public SDK query runs in a stdlib multiprocessing
spawn worker with its own POSIX process group and fixed-token result pipe. Parent bounds
the entire call, including SDK version probe and connection initialization, then kills
the process tree and joins the worker. Windows uses `taskkill /PID pid /T /F` with a
2-second timeout; tree cleanup failure propagates non-success, with direct worker
cleanup in `finally`. Windows execution remains unverified on this macOS host.
ACP timeout surrounds protocol calls inside SDK lifecycle context; ACP waits 0.5
seconds then terminates, another 0.5 then kills. Native cleanup has bounded join waits.
Completion acknowledges protocol delivery, not durable memory retained by a model.

## TDD and empirical evidence

RED: focused file returned **15 failed, 3 passed** before production fix. Included
regression demonstrating denied network still returned original false `ok`.

After fix: **17 passed in 11.19s**. Real optional SDK distributions installed only in
`/tmp/rush-transport-sdk-check`: **claude-agent-sdk 0.2.152**,
**agent-client-protocol 0.12.1**. Project interpreter Python 3.12.12.

Command:

```sh
rtk proxy env -u VIRTUAL_ENV PYTHONPATH=src:/tmp/rush-transport-sdk-check /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest tests/test_phase61_transport.py -q --tb=short
```

Tests use real SDK serialization and stdio subprocess I/O against local deterministic
protocol peers. Claude SDK options substitute only fake CLI executable; `query`,
subprocess transport, initialization and result parser remain real. ACP SDK launches
fake adapter directly. Tests assert captured wire payload/source, ACP cwd/MCP session
arguments, exact denial responses, terminal success/error outcomes and PID absence
after completion, errors, missing results, denied tools and timeout. ACP timeout peer
ignores SIGTERM, exercising SDK kill escalation. Existing file dedupe/cleanup preserved.
Optional SDK cases explicitly skip when dependencies unavailable; isolated-SDK run above
executed them. No dependency manifest or project environment changed.

Independent review then reproduced native startup cleanup failure: a real SDK version
probe ignoring SIGTERM survived a 0.5-second timeout, with a closed-event-loop warning.
New adversarial regression was RED (PID still alive). The previous in-process timeout
was replaced by the parent-owned process tree boundary described above. Tests now cover
both hung version probe and healthy version probe followed by hung initialization,
with SIGTERM ignored. They assert non-success, bounded return and child PID absence.
Independent rerun exposed a test timing defect: the 2-second test deadline sometimes
expired during cold spawned-interpreter/SDK imports, before the peer wrote its readiness
PID. Startup tests now allow 10 seconds including those imports, explicitly require the
stage-specific readiness PID, require dispatch return in under 14 seconds including
cleanup, and require PID absence. Production timeout and lifecycle code are unchanged.
Earlier fake preflight wrote one untracked `peer.pid` in worktree; exact owned file removed.

Considered documented `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` (official SDK changelog
0.1.4); rejected as insufficient: installed SDK reads parent `os.environ` before
`options.env`, and main `connect()` also precedes query cleanup ownership. No global
environment mutation, private SDK patch, replacement protocol implementation or
additional dependency introduced. Original 17-pass result above predates this fix;
final frozen validation is reported separately by coordinator.

## API evidence and limits

- https://agentclientprotocol.github.io/python-sdk/quickstart/
- https://platform.claude.com/cookbook/claude-agent-sdk-05-building-a-session-browser
- Installed SDK signatures and lifecycle source inspected before implementation.

No provider resume integration or unrelated native Codex integration added. Graph
showed dispatch callers only in focused tests; this does not establish production
CLI/MCP routing or whole-plan acceptance. Human real-model behavior remains untested.
Read-only Graft queries auto-refreshed its index for concurrent existing changes.

Final worker run: **19 passed**; Ruff check and format check passed. Frozen subject:

```text
ab455348455e03d6b4697ad678f86dc40d2409a2e2a3eb1f542a5c9ac70afa85 src/rush/memory/transport.py
8817060aaac5c889eb5b6eff6c992822b2ace74885bb158a1e7207b37514c87c tests/test_phase61_transport.py
```

Coordinator owns final frozen whole-worktree verification, review and handoff. User authorized committing after verification; no push authorized.
