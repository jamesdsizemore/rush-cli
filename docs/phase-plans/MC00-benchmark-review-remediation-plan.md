# MC00 — Benchmark review remediation (commit `386a272`)

Fixes the 9 findings from `/ultrareview 386a272` ("feat: benchmark actual memory payloads
through isolated public scenarios"). Every claim below was re-verified against current source
on 2026-09-11, not against the review's own wording — two findings needed correction before
being actioned (noted inline). Target files, all under `/Users/jamesdsizemore/Developer/rush-cli`:
`scripts/benchmarks/memory.py`, `scripts/benchmarks/fixtures.py`,
`tests/test_benchmark_memory.py`, `tests/test_benchmark_contracts.py`.

## Corrections to the review's own findings

- **Finding 8** (dead path-traversal guard on `scenario_id`, `memory.py:62`): NOT dead code,
  not being removed. `tests/test_benchmark_memory.py::test_memory_probe_repeat_isolated_and_rejects_unsafe_id`
  calls `run_memory_probe(replace(_scenario("M01"), scenario_id="../outside"), ...)` directly and
  asserts `FixtureError` with `match="scenario path denied"`. `run_memory_probe` is a public
  function callable with an arbitrary `Scenario`, not only through `run.py`'s CLI dispatch (which
  does pre-whitelist `scenario_id` via dict membership at `run.py:1240` before ever calling the
  probe) — so the guard is real defense-in-depth at a public API boundary, not error handling for
  an impossible case. Left in place, unchanged.
- **Finding 9** (6-key contract frozenset "duplicated three times"): grep of
  `require_exact_keys` call sites in `fixtures.py` shows only 2 occurrences of the 6-key set
  (`scenario_id/probe/category/input/required_facts/expected_outcome`) — `fixtures.py:43`
  (`load_scenarios`) and `fixtures.py:148` (`load_memory_cases`). `fixtures.py:75`
  (`load_provider_routes`) uses an unrelated 10-key set. Task B below dedupes the real 2
  occurrences via a shared constant, not 3.

## Task A — `scripts/benchmarks/memory.py`: rewrite `run_memory_probe` and its helpers

**Status: DONE.** A1-A5 implemented per this spec, verbatim. A6's M03/M09 implemented per this
spec, verbatim. A6's M06/M10 implemented via a corrected mechanism, not the plan's original
literal wording below — see "Design Correction During Execution (M06/M10)" below and
`docs/goals/mc00-benchmark-review-remediation/goal.md`'s "Design Correction" section for the
full history.

Resolves findings 1 (case differentiation), 2 (redundant disk round-trip), 3 (tiktoken
fallback), 5 (redundant fixture re-read), 6 (dead enum-override line), 7 (duplicate
membership test). One pass — all land in the same function, sequencing them separately would
mean re-reading the same ~90 lines five times.

### A1. Finding 2 — stop writing-then-reading `source_records` just to hash them

Current (`memory.py:76-81`):
```python
source_path.write_text(
    json.dumps(source_records, ensure_ascii=True, separators=(",", ":")),
    encoding="ascii",
)
source_hash = _sha256(source_path.read_bytes())
```
`source_path` is never read back by anything else in the function (it exists purely so a hash
of the fixture payload can be recorded in metrics). Change to hash the in-memory payload
directly and only write the file for on-disk inspectability:
```python
source_payload = json.dumps(
    source_records, ensure_ascii=True, separators=(",", ":")
).encode("ascii")
source_path.write_text(source_payload.decode("ascii"), encoding="ascii")
source_hash = _sha256(source_payload)
```

### A2. Finding 3 — add the same encoder-load fallback `ContextPacker.count_tokens` already uses

`src/rush/codegraph/context_packer.py:20-30` wraps `tiktoken.get_encoding()` in
`try/except Exception` at `__init__` and falls back to `max(1, len(text) // 4)` in
`count_tokens`. Do **not** import `ContextPacker` itself — it's instantiated with
`AstSkeletonizer` and `project_root` for unrelated symbol-packing work
(`scripts/benchmarks/context.py:90` uses it because it's genuinely packing symbols, not just
counting tokens); pulling it into `memory.py` only for token counting adds an unrelated
dependency for no behavioral gain. Instead add a module-level helper mirroring the same
fallback, used everywhere `memory.py` currently calls `tiktoken.get_encoding("cl100k_base")`
directly (`memory.py:115` in `run_memory_probe`, and the `_ENCODING`-based encoder in
`run_memory_episode`):
```python
def _get_encoder() -> tiktoken.Encoding | None:
    try:
        return tiktoken.get_encoding(_ENCODING)
    except Exception:  # noqa: BLE001 - matches ContextPacker.__init__'s own fallback
        return None

def _count_tokens(encoder: tiktoken.Encoding | None, text: str) -> int:
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)
```
Move the `_ENCODING = "cl100k_base"` constant (currently defined at `memory.py:159`, after
`run_memory_probe`) above `run_memory_probe` so both call sites can use it. Replace
`run_memory_probe`'s inline `tiktoken.get_encoding("cl100k_base").encode(serialized)` with
`_count_tokens(_get_encoder(), serialized)`, and `run_memory_episode`'s
`encoder = tiktoken.get_encoding(_ENCODING)` (`memory.py:296`) with
`encoder = _get_encoder()` plus `token_count = _count_tokens(encoder, serialized)` in place of
`len(encoder.encode(serialized))` (`memory.py:307`). Add `"token_method"` value stays
`"tiktoken:cl100k_base"` when `encoder is not None`; when the fallback fires, record
`"tiktoken:cl100k_base:fallback"` instead so a metrics consumer can tell the two apart.

### A3. Finding 5 + Finding 6 — drop `_case_description()`, read the label straight off the scenario

`memory_cases.json`'s `input` object already carries the label directly (e.g.
`"input":{"fixture":"memory_cases.json","case_id":"M01",...,"label":"exact identifier
retrieval"}` — confirmed by reading `tests/fixtures/benchmarks/memory_cases.json`), and
`load_scenarios()` copies `item["input"]` verbatim onto `Scenario.input`. So
`scenario.input["label"]` already holds the description `_case_description()` re-derives by
re-reading and re-validating the whole fixture file. No test references `_case_description`
directly or its `FixtureError` (`unknown memory benchmark case`) path — confirmed via
`grep -rn "_case_description" tests/ scripts/` (0 hits outside its own definition and its one
call site). Delete `_case_description()` entirely (`memory.py:42-48`) and replace its call site
(`memory.py:64`, `description = _case_description(scenario)`) with:
```python
description = str(scenario.input.get("label", ""))
```
This also removes `_scenario_hash`'s only remaining justification issue — no, `_scenario_hash`
is separate (A4 below). This step alone drops the now-unused `load_memory_cases` import in
`memory.py` if nothing else in the file uses it — grep after the edit to confirm; the fixture
helper itself stays in `fixtures.py`, only `memory.py`'s import of it is removed if it becomes
dead.

### A4. Finding 6 — delete the dead `Outcome` override in `_scenario_hash`

`contracts.py:12` defines `class Outcome(StrEnum)`. `dataclasses.asdict(scenario)` does not
convert enum member values — `contract["expected_outcome"]` after `asdict()` is already the
`Outcome` member itself (e.g. `Outcome.PASS`), and since `StrEnum` members are `str` instances
whose value *is* the string, `json.dumps` serializes `Outcome.PASS` identically to
`scenario.expected_outcome.value` (`"pass"` either way). The override line is a genuine no-op.
Delete `memory.py:31` (`contract["expected_outcome"] = scenario.expected_outcome.value`) from
`_scenario_hash`, leaving:
```python
def _scenario_hash(scenario: Scenario) -> str:
    contract = asdict(scenario)
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256(payload)
```

### A5. Finding 7 — compute `denied_visible` once, reuse for outcome and metrics

Current (`memory.py:125` and again inline at `memory.py:140-141`):
```python
denied_visible = "D1" in visible_ids or "denied" in visible_sources
...
"denied_id_visible": "D1" in visible_ids,
"denied_source_visible": "denied" in visible_sources,
```
Compute the two booleans once and reuse them in both places:
```python
denied_id_visible = "D1" in visible_ids
denied_source_visible = "denied" in visible_sources
denied_visible = denied_id_visible or denied_source_visible
...
"denied_id_visible": denied_id_visible,
"denied_source_visible": denied_source_visible,
```

### A6. Finding 1 — make M03/M06/M09/M10 exercise genuinely distinct `MemoryTool` behavior

Verified against `src/rush/tools/memory.py` and `src/rush/memory/{store,retrieval,expiry,trust}.py`
this session (not from memory):

- `tool.run(root, operation="ask", subject=..., query=..., session_allowlist=..., request={"view": "compact", "max_bytes": N, "max_tokens": N, "limit": N}, permissions=...)` routes to
  `_compact_query` (`memory.py:337-347` dispatch table: `request is not None` branch), which
  calls `recall_page()` (`src/rush/memory/retrieval.py:308`). `recall_page` returns
  `{"code","items","next_cursor","complete","tokens","bytes","encoding"}` (`_page()`,
  `retrieval.py`); `complete=False` means the page was cut short by `max_bytes`/`max_tokens`
  or the 512-row scan cap. The tool wraps this as
  `result["raw"] = {"schema_version":1,"operation":...,"code":...,"data": <page dict>}`
  (`_envelope_result`, `memory.py:2168`+ area) with `result["status"]` derived from `code`.
  Without `request`, `ask` takes the legacy `_query()` path (`memory.py:446`), which never
  truncates and always returns everything `TypedArtifactStore.recall()` matches — this is why
  `payload_truncated` is hardcoded `False` today: the probe never exercises the one code path
  that can actually truncate.
- `tool.run(root, operation="edit", request={"scope": <subject>, "id": <artifact id>, "expected_version": <int>, "content": {...}, "apply": True}, permissions=...)` calls
  `store.edit(...)` (`_edit_or_archive`, `memory.py:2042`+). `apply=True` requires
  `check_permissions(_WRITE_PERMISSION, granted)` where `_WRITE_PERMISSION = ExecutionPermissions(cache_write=True)`
  (`memory.py:105`) — the same `permissions` object `run_memory_probe` already constructs
  (`ExecutionPermissions(cache_write=True)`, `memory.py:70`), so no new permission grant is
  needed.
- `tool.run(root, operation="maintain", task="expiry_sweep", batch_size=N, permissions=...)`
  calls `run_maintenance_cycle("expiry_sweep", ...)` → `sweep_expired()`
  (`src/rush/memory/expiry.py:54`), which stamps `expires_at`/`expired_at` on rows whose
  `created_at + ttl_seconds <= now`. Default-tier writes (`source_kind` omitted →
  `"local_tool"` → `default_entry_tier` (`src/rush/memory/trust.py:61`) → `"EXTERNAL_WRITE"`,
  30-day TTL) or `source_kind="human_derived"` (→ `"DERIVED"`, 14-day TTL,
  `src/rush/memory/expiry.py:35`) can be forced expired deterministically, without waiting, by
  directly updating `created_at` in the same sqlite DB `TypedArtifactStore` writes to
  (`TypedArtifactStore(root).db_path`) — the same "reach into the real fixture directly"
  pattern this file already uses for the git-repo fixture in `_init_upload_repair_repo`.
  Critically: `TypedArtifactStore.search()` (`src/rush/memory/store.py:1511`, used by the
  legacy `ask` path via `recall()`) filters only `archived_at IS NULL` — it does **not**
  filter `expired_at` at all. Only the compact path's `search_candidates()`
  (`store.py:572`, `include_expired: bool = False`) excludes `expired_at IS NOT NULL` rows.
  So "does an expired-but-not-archived record still come back" has a real, currently-true,
  two-path answer (legacy: yes; compact: no) — that is what M03 measures, not an assumption
  about what "should" happen.

Design for each case, branching on `scenario.input.get("case_id", scenario.scenario_id)`
inside `run_memory_probe` after the existing baseline write/recall block (baseline stays
byte-for-byte identical for all 6 cases — M01/M05's existing assertions must keep passing
unchanged):

| Case | Extra calls (beyond the shared 101-record write + baseline `ask`) | New metrics added |
|---|---|---|
| M03 stale record retrieval | Write one extra record with `source_kind="human_derived"`; open `TypedArtifactStore(root).db_path` directly and `UPDATE memory_artifacts SET created_at = ? WHERE id = ?` to backdate it 15 days; `maintain(task="expiry_sweep")`; re-`ask` via legacy path (no `request`) and via compact path (`request={"view":"compact",...}`) for a query matching the aged record | `expiry_sweep_changed: int`, `stale_visible_legacy: bool`, `stale_visible_compact: bool` |
| M06 oversized evidence payload measurement | One `ask` with `request={"view":"compact","max_bytes":4096,"max_tokens":100000,"limit":100}` against the same 100-record allowed set | `payload_truncated` (real, derived from `not data["complete"]`, replacing the hardcoded `False`), `compact_items_returned: int`, `compact_bytes: int` |
| M09 source edit measurement | Write one record, capture its `id`/`artifact_version` from the write result's `raw`; `edit` it with `expected_version` from that write, `apply=True`, changed `content`; re-`ask` and check the edited text is what comes back | `pre_edit_version: int`, `post_edit_version: int`, `edited_content_visible: bool` |
| M10 cache budget measurement | Repeated compact `ask` calls with `request={"view":"compact","max_tokens":50,"limit":100}`, following `next_cursor` until `complete=True`, counting pages | `compact_pages: int`, `compact_total_tokens: int`, `compact_paginated: bool` (`compact_pages > 1`) |

`case_description`/`case_id` stay in every result's metrics as today (via A3's simplified
`description` line) — the table above is additive metrics per case, not a change to the
function's return shape or `ProbeResult` schema (`metrics: dict[str, int | float | str]` in
`contracts.py:49` already accepts arbitrary keys, and bools are accepted the same way
`denied_id_visible`/`payload_truncated` already are today).

M01 and M05 get **no** new calls — they keep exercising exactly what they exercise today
(baseline retrieval, denied-source exclusion). Only M03/M06/M09/M10 grow real behavior.

## Task B — `scripts/benchmarks/fixtures.py`: dedupe the 6-key contract set and the memory-case validation path

**Status: DONE.** `_SCENARIO_CONTRACT_KEYS` shared constant added; both real duplicate
occurrences (in `load_scenarios` and `load_memory_cases`) deduped to use it;
`load_scenarios` now calls `load_memory_cases()`; `load_provider_routes` and every other
loader left untouched. CR1+CR2 clean.

Resolves findings 4 and 9 (corrected count: 2 occurrences, not 3).

1. Add a module-level constant above `load_scenarios`:
   ```python
   _SCENARIO_CONTRACT_KEYS = frozenset(
       {"scenario_id", "probe", "category", "input", "required_facts", "expected_outcome"}
   )
   ```
2. Replace the inline `frozenset({...})` literal at `fixtures.py:43-51` (inside
   `load_scenarios`'s loop) and at `fixtures.py:148-156` (inside `load_memory_cases`) with
   `_SCENARIO_CONTRACT_KEYS`. Do not touch `load_provider_routes`'s frozenset
   (`fixtures.py:75-85`) — it's a genuinely different 10-key contract, not part of this
   duplication.
3. Replace `load_scenarios`'s inline memory-case loading (`fixtures.py:37-41`:
   `memory_raw = json.loads(fixture_path("memory_cases.json").read_text(...)); items = [*raw.get("scenarios", []), *memory_raw.get("cases", [])]`)
   with a call to the function this same commit already added for exactly this purpose:
   ```python
   items = [*raw.get("scenarios", []), *load_memory_cases()]
   ```
   `load_memory_cases()` already does its own `require_exact_keys` validation
   (`fixtures.py:148`+) using the now-shared `_SCENARIO_CONTRACT_KEYS` constant, so validation
   stays equivalent — `load_scenarios`'s own loop still re-validates every item (including the
   ones `load_memory_cases` already validated) via the same shared constant, which is
   redundant-but-harmless (same check, same constant, not two independently-maintained
   literals) and cheaper to leave in place than to special-case scenario-vs-memory items in
   the loop.

## Task C — no code change

**Status: DONE.** Confirmed no-op — nothing changed, as planned.

Finding 8's guard stays as-is (see correction above). Nothing to implement.

## Task D — test updates

`tests/test_benchmark_contracts.py::test_fixture_path_security` (`assert len(scenarios) ==
46`) and `::test_load_scenarios_validation` (`assert categories.get("memory") == 6`) are
unaffected — Task A/B change behavior and internals, not the fixture file or scenario count.

Add to `tests/test_benchmark_memory.py` (new tests, alongside the existing ones — none of the
existing tests change):

- `test_memory_probe_detects_stale_record_via_legacy_path_only` — runs `_scenario("M03")`,
  asserts `metrics["stale_visible_legacy"] is True` and `metrics["stale_visible_compact"] is
  False` and `metrics["expiry_sweep_changed"] >= 1` (documents the real legacy/compact
  divergence found in A6, not an assumption).
- `test_memory_probe_measures_real_payload_truncation` — runs `_scenario("M06")`, asserts
  `metrics["payload_truncated"] is True` and `metrics["compact_items_returned"] < 100` given
  the tight `max_bytes` budget against the 100-record fixture.
- `test_memory_probe_measures_source_edit` — runs `_scenario("M09")`, asserts
  `metrics["post_edit_version"] > metrics["pre_edit_version"]` and
  `metrics["edited_content_visible"] is True`.
- `test_memory_probe_measures_cache_budget_pagination` — runs `_scenario("M10")`, asserts
  `metrics["compact_paginated"] is True` and `metrics["compact_pages"] > 1` given the 50-token
  page budget against the 100-record fixture.
- `test_memory_probe_token_fallback_when_encoder_unavailable` — monkeypatches
  `memory.tiktoken.get_encoding` to raise, asserts `run_memory_probe` still returns a result
  (no crash) and `metrics["token_method"] == "tiktoken:cl100k_base:fallback"`.

**Status: DONE.** All 5 tests added to `tests/test_benchmark_memory.py` and captured RED
against pre-fix source (T002) before Task A landed: `stale_visible_legacy` `KeyError` (M03),
`payload_truncated` assert-`False`-is-`True` failure (M06, still hardcoded `False`),
`post_edit_version` `KeyError` (M09), `compact_paginated` `KeyError` (M10), and an uncaught
`RuntimeError` from the unguarded `tiktoken.get_encoding` call (encoder-fallback test) — each
failing for the expected reason, not a syntax/import error. All 5 turned GREEN after Task A
landed (T004), alongside the 8 pre-existing tests passing unchanged. One additional test-file
change beyond this section's list above: this plan's claim that "none of the existing tests
change" was wrong for one case — the pre-existing `test_memory_baseline_records_over_budget_payload`'s
`payload_truncated` assertion had to flip from `False` to `True` to match A6's corrected M06
behavior (discovered during T001's drift check, fixed during T004; see "Design Correction
During Execution (M06/M10)" below).

## Design Correction During Execution (M06/M10)

Task A6's table above specified deriving M06's `payload_truncated` from `not
data["complete"]` and M10's pagination from a tight `max_tokens` budget forcing repeated
compact `ask` calls. Both were discovered mid-execution (T004) to be structurally unreachable
given `recall_page`'s real, tested, documented behavior: `complete` only ever reflects the
internal 512-row scan cap, never `max_bytes`/`max_tokens` truncation — confirmed via a full
read of `src/rush/memory/retrieval.py` and the existing, passing
`tests/test_memory_retrieval.py::test_serialized_payload_obeys_both_caps` (exercises budget
truncation without `complete` ever going `False`) and `::test_scan_cap_returns_continuation`
(exercises the real scan-cap pagination this correction now reuses) tests. This is
pre-existing, deliberately tested, documented production behavior — not a bug — and changing
it would affect every real compact-`ask` consumer outside this benchmark, not just this probe.
The user was asked and explicitly declined touching `src/rush/` to work around it.

**Corrected mechanism (implemented, CR1+CR2 clean on both slices):**
- M06 (`_probe_oversized_payload`): `payload_truncated` is computed by comparing the compact
  ask's returned item count against the known total record count the benchmark itself wrote,
  instead of `data["complete"]`.
- M10 (`_probe_cache_budget`): writes ~450 probe-local extra records (on top of the shared
  100-record baseline, untouched for every other case) so total candidates (550) genuinely
  exceed the real 512-row scan cap, combined with a loose byte/token budget — reproducing
  authentic multi-page continuation via the exact real `next_cursor`/`hit_cap` mechanism
  `test_scan_cap_returns_continuation` already exercises and trusts.

Task D's original test assertions (`payload_truncated is True`, `compact_items_returned <
100`, `compact_paginated is True`, `compact_pages > 1`) all hold unchanged under this corrected
mechanism — only the internal computation changed. Full history and the two rounds of
verification behind this decision: `docs/goals/mc00-benchmark-review-remediation/goal.md`'s
"Design Correction" section.

## Findings Resolved

9 of 9 ultrareview findings resolved: Findings 1, 2, 3, 5, 6, and 7 as code changes in Task A;
Findings 4 and 9 as code changes in Task B; Finding 8 as the already-documented no-op in
Task C (see "Corrections to the review's own findings" above).

## Verification

1. `rtk pytest tests/test_benchmark_memory.py tests/test_benchmark_contracts.py -v`
   **Outcome: PASS.** 18 passed, targeted. Re-confirmed independently across T004, T005, T007,
   T008, T009, and T011's receipts.
2. `rtk pytest -q` (full suite — confirm no regression outside the two touched test files;
   baseline per most recent session memory is 2264 passed)
   **Outcome: PASS.** 2283 passed / 0 failed / 5 skipped, full suite, run multiple times across
   T004, T005, T007, T008, T009, and T011's receipts with identical counts each time.
3. `rtk ruff check scripts/benchmarks/memory.py scripts/benchmarks/fixtures.py`
   **Outcome: PASS.** Clean on both files (T004, T005, T007 for `memory.py`; T008, T009, T011
   for `fixtures.py`).
4. `rtk mypy scripts/benchmarks/memory.py scripts/benchmarks/fixtures.py`
   **Outcome: PASS.** Clean (0 issues) on both files (T004, T005, T007 for `memory.py`; T008,
   T009, T011 for `fixtures.py`).
5. Manual: `python -m scripts.benchmarks.run --scenario M03 --output <tmp>` (and M06/M09/M10)
   and inspect the written JSON's `metrics` block for the new keys, confirming they hold real
   (not hardcoded) values.
   **Outcome: PENDING T999 final audit.** Not run by any task through T012 — this check is
   explicitly T999's responsibility (see `state.yaml`'s T999 objective), not evidenced yet.
