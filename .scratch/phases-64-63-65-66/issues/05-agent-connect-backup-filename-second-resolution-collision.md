# Agent-connect config backup filenames collide within the same wall-clock second

Status: needs-triage

## Observed evidence

`src/rush/integrations/agents.py:655` names each pre-write config backup `f"{resolved_path.name}.rush-backup-{int(time.time())}"` -- second resolution. T209's adversarial review of P65-05 (board `phases-64-63-65-66`) reproduced live: two `apply_agent_registration` calls against the same agent config file within the same wall-clock second (e.g. two back-to-back `rush agent connect zed` invocations) collide on the identical backup filename, and `shutil.copy2` silently overwrites the earlier backup -- losing the true pre-any-edit snapshot.

The module's own docstring (lines 16-18) promises a backup "before any write." On rapid repeats, that promise silently degrades to "before the most recent write," not every write.

## Intervention assessment

The live config file itself stays fully correct in every reproduction (verified) -- this only reduces the depth of the backup audit trail, and only under same-second repeated calls, a narrow window. T209 assessed this as non-blocking for P65-05's stated invariants (config preservation, one-server idempotency), since those hold regardless. Not a violation of any plan-frozen contract text.

Fix is small and mechanical: replace `int(time.time())` with a monotonic/higher-resolution suffix (e.g. `time.time_ns()`, or an incrementing counter appended when a same-second collision is detected).

## Scope

Outside every currently-defined task's allowed_files on the `phases-64-63-65-66` board (`src/rush/integrations/agents.py` is P65-05's file, already closed). Needs its own bounded one-line fix task if/when a later packet revisits agent-connection hardening, or sooner if a real backup-loss incident surfaces.
