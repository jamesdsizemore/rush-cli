# MC11's dispatch_handoff refuses dedicated_file transport instead of plan §6.6's "pending capsule" fallback

Status: needs-triage

## Observed evidence

`docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md` §6.6 describes a file-based fallback: when live transport isn't available, "file fallback produces a pending capsule until a receiver explicitly consumes it through the same route." `src/rush/memory/transport.py`'s `dispatch_handoff` (line ~172) instead fully refuses (`status="skipped"`) the `dedicated_file` transport tier -- no capsule mechanism was implemented.

None of MC11's 12 required tests exercise this path, so it wasn't a RED/GREEN gap; T119's review (board `phases-64-63-65-66`) confirmed this independently while auditing the security model.

## Intervention assessment

Refusing is the security-safer default (a flat file can't host a live capability-gated MCP receiver the way a real bridged session can), and T119 assessed this as non-blocking for MC11's actual required contract. But it is a real, deliberate deviation from written plan text, not just an implementation-granularity choice like MC08's codegraph-bypass.

Needs a future decision: either (a) implement the capsule mechanism for real if a receiver genuinely needs offline/file-based handoff, or (b) amend the plan text to explicitly drop that fallback tier and document why refusal is the intended terminal behavior.

## Scope

Outside every currently-defined task's allowed_files on the `phases-64-63-65-66` board. Needs its own bounded task if/when Phase 63's final MC15 acceptance audit reaches R01-R20 review of the handoff subsystem, or sooner if a real use case for file-based handoff surfaces.
