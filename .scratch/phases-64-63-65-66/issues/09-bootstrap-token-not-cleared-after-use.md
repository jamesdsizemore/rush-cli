# Consumed dashboard bootstrap token stays in memory after use

Status: needs-triage (low severity, non-blocking)

## Observed evidence

T301's security review of P66-01 (board `phases-64-63-65-66`) found that `src/rush/dashboard/auth.py:47-53`'s `_Bootstrap` dataclass keeps the plaintext bootstrap token string in `.token` after `use=True` is set on first exchange, rather than clearing it. The reviewer verified this is unreachable via any exposed API surface (the token is never re-served, logged, or returned after exchange) -- it is a defense-in-depth gap, not an active vulnerability.

## Intervention assessment

Low severity: exploiting this would require an attacker who already has arbitrary memory read access to the server process, at which point the bootstrap token is the least of the exposure. Still a legitimate hardening item -- clearing the field after use (e.g. setting `.token = None` or using a one-shot consume-and-discard pattern) costs nothing and removes a lingering secret from the object's lifetime.

## Scope

Outside every currently-defined task's allowed_files on the `phases-64-63-65-66` board (`src/rush/dashboard/auth.py` is P66-01's file, already closed). Fix opportunistically the next time a task legitimately edits `src/rush/dashboard/auth.py` (likely P66-02 or later Phase 66 packets), or dispatch a trivial one-line fix task if none arises before this board's final Phase 66 audit.
