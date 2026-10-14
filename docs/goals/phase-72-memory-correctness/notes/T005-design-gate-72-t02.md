# T005: Design gate for 72-T02 (goal-judge report, recorded verbatim)

Below the line is the goal-judge's T005 report, copied unchanged. It contains the note body (A) and the receipt (B).

**PM edit (2026-10-05).** The PM made two renames in the report:

- the HMAC domain-separation labels, from the gate's original "rush" + "cursor" label prefix to `rush.page-cursor.*` (these are internal constants, so the design behaves the same);
- the capitalized word for the paging cursor, now "Paging cursor".

Both renames were needed because `tests/test_phase70_t25.py::test_no_cursor_product_mention_in_docs` applies `_CURSOR_RE` to the docs tree, including `docs/goals/`, and the original wording matched it. T022 must use the `rush.page-cursor.*` labels.

## PM re-checks (run on 07775f1)

The PM ran a TemporaryDirectory probe through `.venv/bin/python`:

- `TypedArtifactStore.write` of `{"text":"café needle 🙂"}` stores `{"text": "caf\u00e9 needle \ud83d\ude42"}`, so stored content is ASCII-escaped.
- `store.search("domain_knowledge","café")` returns 0 hits. `store.search("domain_knowledge","needle")` returns 1.

Both of the gate's UTF-8 findings hold.

verified-by: the probe above, which printed the raw content row and `0 1`.

Not re-run by the PM: the rest of the report. The T021 RED author re-checks the code map at HEAD before writing tests (stop_if).

## PM gate delta (after T021)

**R8 fixture.** The R8 row's fixture (`created_at = now0 - 14d + 60` alone) cannot meet its own precondition at the 72-T01 commit. T01 treats a row as expired only when `expired_at` is set or a stamped `expires_at <= now` (`retrieval.py` `_lifecycle_reasons`; T004 note: an elapsed TTL alone is the sweep's job), and `write()` stamps no `expires_at`. T021 therefore also sets p3's `expires_at = created_at + 14d` (= now0+60) with raw SQL; that write leaves the store generation unchanged. The PM accepts this: the row still tests that page 2 rechecks expiry against its own `now`, and "not `E_RESTART`" still holds. T022 must not change T01's expiry rule.

**R13 status mapping.** An unknown code already maps to status `error` in `_envelope_result`. T022 still adds `E_OFFSET` to `_CODE_STATUS` explicitly.

verified-by: PM re-run at ef24aeb of the 4 T02 test files (17 failed, the R1-R14 and A1-A3 node ids; 99 passed; 0 skipped) and `-k t02 --collect-only` (14/78 collected).

---

# T005 design gate for 72-T02: approved, nothing written

T005 (72-T02 "Honest pagination and exact UTF-8 recovery") is approved, with 5 board updates the PM needs to make (section 7 below). No owner decisions are needed. I made no file changes; the PM writes part A to `docs/goals/phase-72-memory-correctness/notes/T005-design-gate-72-t02.md`.

Things the PM should know first:
- **The plan's UTF-8 fixture can't be built through the write API.** Every write path stores ASCII-escaped JSON (`json.dumps(content)`). I checked with a sandbox write: `{"text": "café needle 🙂"}` is stored as `{"text": "café needle 🙂"}`. So "stored JSON text contains 🙂é𐍈" needs the fixture in part A section 6.
- **Non-ASCII memory search is broken today.** The same probe returned 0 hits for "café" and 1 for "needle". That belongs to T06/T07 (all-subject search), not T02; routed in section 7.
- **`payload_hash` storage is assigned to T01, not T02.** T02's file list has no `store.py`. If the T004 note leaves it out, it needs a T004 delta.
- **`hybrid_page` false completion stays with T08.** It always reports `complete: true`, but plan line 386 makes the "labeled incomplete" result a T08 deliverable.
- **The dashboard `expectedSha256` question (T002 item 6) is closed with no change.** That option belongs to the project run-artifact download route, not memory.

---

## (A) Note body: `notes/T005-design-gate-72-t02.md`

# T005: design gate for 72-T02, honest pagination and exact UTF-8 recovery

Worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`, HEAD `07775f1`, branch `phase/72-memory-correctness-and-user-control`. This note was mapped at 07775f1. 72-T02 runs after 73-T02/POLICY and 72-T01 are committed.

### 0. What T02 assumes from earlier units (RED author: check these first)

These T01 and 73-T02 changes are **expected**. Do not stop because they exist; use the names T01 actually committed.

1. **73-T02/POLICY** provides `src/rush/memory/authorization.py` with `grant_memory_scope`, `revoke_memory_scope`, `resolve_memory_scope` and `load_policy_readonly`. Their signatures follow the plan's L157 fixture.
2. **72-T01** adds a resolved-access parameter (called `access` here) to `recall_page`, `expand_artifact` and `hybrid_page`.
   - It threads that access from `MemoryTool._compact_query` and `MemoryTool._expand`.
   - It adds per-candidate eligibility (`evaluate_artifact_visibility` / `VisibilityDecision`) inside the `recall_page` loop.
   - It may add a `now=` injection and a re-resolution hook used before emitting a page.
3. **72-T01 stores `payload_hash`** (plan §2.1 item 2):
   - a nullable `payload_hash` column on `memory_artifacts` and `memory_artifact_versions`;
   - computed on every authorized write;
   - backfilled by the write-authorized `TypedArtifactStore.upgrade`;
   - plus one store reader that returns `(content, payload_hash)` for an exact version.
   - **T02 does not edit `store.py`.**
4. **Stop and ask the PM for a gate delta if:**
   - item 3 is missing;
   - access is not threaded through recall, expand, compact or `_expand`;
   - any mapped symbol changed in a way not listed above.

### 1. Testable behavior

- **B1, exact-once paging.**
  - `recall_page` returns `complete: true` only when no eligible candidate remains.
  - Whenever a page stops because of `limit`, a byte or token cap, or the 512-row scan cap, it returns `complete: false` and a cursor. The cursor points at the first candidate not yet consumed.
  - Following cursors returns every eligible record exactly once, in rank order (bm25, then id).
  - Corrupt or ineligible rows count as consumed.
- **B2, reaching the limit.** When the page reaches `limit`, it keeps scanning until it finds another eligible row, which is not consumed (so `complete: false`), or until it finds none (so `complete: true`). Example: three matches with `limit=2` give `[p1, p2]`, `complete: false`, then `[p3]`, `complete: true`.
- **B3, record too big for the budget.** If the first eligible record at the resume point fits in no page:
  - the response is `E_BUDGET` with `items: []`, `next_cursor: null`, `complete: false`;
  - it includes `required: {max_bytes, max_tokens}`, the size of that one record plus its cursor;
  - the resume position does not move;
  - repeating the call returns the same `E_BUDGET`, never an empty OK page;
  - retrying with the `required` caps returns that record.
- **B4, admission check.**
  - A cap below the size of the smallest canonical `E_BUDGET` envelope returns `E_INPUT` with `required`, and `tokens` and `bytes` set to 0.
  - This happens before any store read, key read or cursor decode. It records no telemetry.
  - The same applies to `limit < 1` and to an unknown `encoding`.
  - Every response that passes admission fits both caps, including its cursor.
  - The `required` diagnostics are included only if they still fit.
- **B5, cursor binding.** The cursor is bound by HMAC to:
  - namespace (the project root), `project_id`, `worktree_id`, owner, `policy_revision`, `grant_id`;
  - subject, query, the sorted sources, archive mode `active`, and ranking version;
  - store generation and scan position.

  Any change, a malformed or foreign cursor, or a legacy-format cursor returns `E_RESTART` with no items, `next_cursor: null` and `complete: false`. The cursor is opaque: `^m2\.[A-Za-z0-9_-]{27}$`. It exposes no IDs, offset or generation.
- **B6, snapshot check.** The store generation is read before the scan and again before the page is emitted. If it changed, the response is `E_RESTART` with no items. If T01's hook reports a changed or revoked policy, the response is `E_RESTART` or T01's denial with no content. Expiry is re-checked against `now` on every page.
- **B7, no read-side keys.** If the cursor key is unavailable (a read-only view with no key row), the response is `E_MIGRATION` with no items. Nothing is created.
- **B8, UTF-8 expansion mode.** `expand_artifact(..., representation="utf8")` returns:

  ```
  {code, id, version, representation: "utf8", offset, next_offset, complete,
   content_utf8, payload_hash, total_bytes, tokens, bytes, encoding}
  ```

  - Offsets are byte offsets into the exact persisted UTF-8 JSON.
  - Each slice runs from one scalar boundary to another. Joining the slices gives back the exact bytes, and `sha256 == payload_hash`.
  - The measured payload is every key except `code`, `tokens` and `bytes`.
- **B9, offset errors.**
  - A negative offset, or one beyond the total (either mode), returns `E_OFFSET`. Offsets are never clamped.
  - In utf8 mode, an offset that is not on a scalar boundary returns `E_OFFSET`.
  - `offset == total` returns OK with empty content and `complete: true`.
- **B10, utf8 budget errors.**
  - If the envelope plus one scalar can't fit, the response is `E_BUDGET`: no content, `next_offset: null`, `complete: false`, `required` equal to the one-scalar page size. Retrying with those caps returns exactly one scalar.
  - Caps below the minimum utf8 `E_BUDGET` envelope return `E_INPUT` before any store read.
- **B11, utf8 integrity.**
  - A persisted `payload_hash` that differs from `sha256(stored bytes)` returns `E_NOT_VISIBLE`, with the same body as a missing artifact.
  - A null `payload_hash` returns `E_MIGRATION` with no content.
  - Asking for an outdated version returns `E_VERSION`.
- **B12, base64 unchanged.** base64 stays the default. Its OK key set and values are unchanged byte-for-byte. Error envelopes may add a `required` key (on `E_BUDGET` and `E_INPUT`) and nothing else.
- **B13, public routes.**
  - `MemoryTool` `expand` and the MCP `rush_memory` `expand` accept `representation` set to `"base64"` or `"utf8"`; any other value is `E_INPUT`.
  - The restricted receiver bridge forwards it.
  - `E_OFFSET` maps to status `error`.
  - A compact request with `retrieval: "hybrid"` plus a `cursor` returns `E_INPUT`. It is checked before the permission check, because hybrid has no continuation and a cursor sent to it would silently restart.
- **B14, receiver check.** `transport.reassemble_utf8_expansion(pages, *, artifact_id, version)` returns `(bytes, sha256_hex)` and rejects:
  - a non-utf8 or malformed page: `E_INPUT`;
  - a gap, overlap, wrong order, zero-progress page or length mismatch: `E_OFFSET`;
  - an id, version, `payload_hash` or `total_bytes` that differs between pages, or a final digest that doesn't match: `E_VERSION`.

  The resulting digest acknowledges through `receive` / `ack`.
- **B15, §2.2 probe.** After T01 and T02, the probe prints all four fields `true`.

### 2. Code and caller map (07775f1)

**`src/rush/memory/retrieval.py`**

| Symbol | Line | Note |
|---|---|---|
| `_SCAN_CAP`, `_BATCH_SIZE`, `_RANKING_VERSION` | 56–58 | |
| `DEFAULT_LIMIT`, `DEFAULT_MAX_TOKENS` (2048), `DEFAULT_MAX_BYTES` (8192) | 64, 66, 67 | |
| `_encode_cursor` / `_decode_cursor` | 248 / 255 | Called only by `recall_page` (graft, depth 1). No tests use them. |
| `_candidate_to_item` | 300 | |
| `_measure_page` | 325 | Also used by `tests/test_phase70_ts.py`. |
| `_contains_special_token` | 341 | |
| `_trial_page_bytes` | 347 | Called by `recall_page` and `hybrid_page`. |
| `_page` | 378 | |
| `recall_page` | 399–569 | |
| `_measure_expand`, `_expand` | 572, 585 | |
| `expand_artifact` | 612–769 | |
| `hybrid_page` | 923–1055 | Lexical fallback at 981–1000; packing at 1007–1024. |

Defects I found by reading the source:
- **D1, line 524.** `complete = not (hit_cap and not exhausted and len(items) < limit)`. Pages stopped by `limit` or budget report `complete: true` with no cursor.
- **D2, line 512.** `scan_offset += len(batch)` runs even after a break mid-batch, so unconsumed rows are skipped.
- **D3.** A zero-item budget stop returns OK, empty, `complete: true`. The oversized record can never be recovered.
- **D4, line 483.** The floor `E_BUDGET` at `max_bytes=1` is itself larger than the cap it reports against.
- **D5.** The cursor is about 380 characters of plaintext base64 JSON. It contains the root path and the generation, and binds no owner, project, worktree or policy.
- **D6, line 684.** `offset = max(0, min(offset, total))` clamps the offset.
- **D7.** There is no utf8 mode and no digest.
- **D8, line 446.** `store.cursor_key()` is called unconditionally. On a read-only view with no key row it raises `TypeError`.

**Callers** (from `graft callers --depth all`):
- `recall_page`:
  - production: `hybrid_page`; `tools/memory.py::_compact_query` → `MemoryTool.run`/`__call__`;
  - benchmarks: `scripts/benchmarks/memory.py` (`_probe_*`, `run_memory_probe`, `run_memory_episode`), `memory_datasets.run_longmemeval_case`, `run.py` (`_variant_hypothesis`, `run_project_journey`, `run_dashboard_user_journey`);
  - tests: `test_memory_retrieval`, `test_phase70_ts` (r5 x3), `test_phase70_t19:1187`, `test_dashboard_memory_tokens:1680`, `test_memory_hybrid`, `test_memory_efficiency`, `test_memory_acceptance`, `test_memory_versions:642`, `test_phase70_t28d_backend:317`, `test_benchmark_memory_datasets`, `test_memory_repairs`.
- `expand_artifact`: `tools/memory.py::_expand` → `MemoryTool.run`, plus the same benchmark and test set.
- Other `expand` consumers (all base64, all unchanged by T02):
  - `mcp_support/tool_registry.py:606` `build_memory_bridge_handler`: the restricted receiver. It forwards `request` to `MemoryTool` with no strict model, so `representation` passes through.
  - `dashboard/server.py:3033–3075`, the `memory_expand` action. It passes `offset` and `max_*` through, so an out-of-range offset now returns `E_OFFSET`.
  - `tui.py:3488` `_memory_expand_selected`. It decodes base64 at 3585 and only resends the previous `next_offset`.
  - `cli.py:3373` (render) and `3864` (`rush memory expand`).
  - `scripts/benchmarks/memory.py:801`, `:1002`: base64 decode.

**`src/rush/tools/memory.py`**

| Symbol | Line | Note |
|---|---|---|
| `_CODE_STATUS` | 138–158 | No `E_OFFSET` entry. |
| `_COMPACT_REQUEST_KEYS` | 160 | |
| `_RETRIEVAL_MODES` | 173 | |
| `_EXPAND_REQUEST_KEYS` | 174–181 | |
| `_compact_query` | 885–1057 | The hybrid branch at 989–1011 silently ignores `cursor`. |
| `_expand` | 1059–1155 | Its telemetry `request_id` is `f"{id}:{version}:{offset}"`. |

**`src/rush/mcp_support/request_models.py`**

| Symbol | Line | Note |
|---|---|---|
| `_BUDGET`, `_ARTIFACT_VERSION` | 270–275 | |
| `MemoryExpandRequest` | 399–402 | Uses `extra="forbid"`, so `representation` is rejected today. |
| `validate_and_normalize` | 1025 | |

`tests/test_phase70_t6.py:791–813` requires `memory_request_model_keys("expand") == _EXPAND_REQUEST_KEYS`, so both must change together.

**`src/rush/memory/transport.py`**
- There is no receiver decode today.
- Its imports already include `hashlib`, `Mapping`, `Sequence` and `HandoffError` (`handoff.py:39`, `HandoffError(message, *, code=...)`).
- The receiver flow is: `expand` pages → reassemble → `receive` with `ack` → `handoff.acknowledge_readback:314` → `store.acknowledge_handoff:2456`. That last step compares `sha256(content.encode("utf-8"))`, the same definition as `payload_hash`.

**`src/rush/memory/store.py` (read only, owned by T01)**
- `cursor_key` 1046; `current_generation` 1055; `search_candidates` 1175; `get_current` 1670; `get_version_content` 1684; `open_readonly_view` 1844; `_connect` returns the read-only connection for views.
- ASCII-escaped content is written by `_write_version` at 675 and by `write` at 2179 and 2202 (also 1505 and 2548).
- `_backfill_legacy_row` at 2029 copies legacy content verbatim.
- `mark_artifact_orphaned` at 2405 does not bump the generation.
- `expiry.sweep_expired:128` does bump it, through `_write_version`.

**Files missing from the plan packet:**
- `src/rush/mcp_support/request_models.py` (the `representation` key; required by the parity test and the MCP route);
- `src/rush/tools/memory.py::_expand`, `_EXPAND_REQUEST_KEYS`, `_CODE_STATUS`;
- `retrieval.py` helpers: `_measure_page`, `_trial_page_bytes`, `_page`, `_expand`, the module docstring;
- `scripts/benchmarks/memory.py:134–139`: the docstring says recall's `complete` "only ever reflects the internal 512-row scan cap ... not a bug". That becomes false after T02.
- Existing tests that must change (proof in section 4): `tests/test_memory_retrieval.py` (2 tests) and `tests/test_phase70_ts.py` (1 test).

**Not a T02 change: `dashboard/application.js:1023` `downloadArtifactContentPages` with `{expectedSha256}`.**
- It serves the project run-artifact download route, `/api/projects/{id}/artifacts/{ref}` → `server.py:3394–3470` → `workflows/projects.py::read_project_artifact_page`.
- `expectedSha256` is the captured file-snapshot sha256, not a memory digest.

### 3. Design of the hard parts

**Paging-cursor format (`retrieval.py`).** Deterministic, opaque, 30 characters. Determinism is required so the same input always produces the same page boundaries.

```python
_CURSOR_PREFIX = "m2."
_CURSOR_BODY_CHARS = 27  # base64url, no padding, of 20 bytes: nonce4 + sealed offset4 + tag12

def _cursor_binding(*, namespace: str, project_id: str | None, worktree_id: str | None,
                    owner: tuple[str, str] | None, policy_revision: int | None,
                    grant_id: str | None, subject: str, query: str,
                    sources: Sequence[str]) -> bytes:
    body = {"v": 2, "namespace": namespace, "project_id": project_id,
            "worktree_id": worktree_id, "owner": list(owner) if owner else None,
            "policy_revision": policy_revision, "grant_id": grant_id, "subject": subject,
            "query": query, "sources": sorted(sources), "archive_mode": "active",
            "ranking_version": _RANKING_VERSION}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).digest()

def _encode_cursor(key: bytes, binding: bytes, generation: int, scan_offset: int) -> str:
    offset_bytes, gen = scan_offset.to_bytes(4, "big"), generation.to_bytes(8, "big")
    nonce = hmac.new(key, b"rush.page-cursor.nonce\x00" + binding + gen + offset_bytes, hashlib.sha256).digest()[:4]
    stream = hmac.new(key, b"rush.page-cursor.stream\x00" + nonce, hashlib.sha256).digest()[:4]
    sealed = bytes(a ^ b for a, b in zip(offset_bytes, stream, strict=True))
    tag = hmac.new(key, b"rush.page-cursor.tag\x00" + nonce + sealed + binding + gen, hashlib.sha256).digest()[:12]
    return _CURSOR_PREFIX + base64.urlsafe_b64encode(nonce + sealed + tag).rstrip(b"=").decode("ascii")

def _decode_cursor(key: bytes, cursor: str, binding: bytes, generation: int) -> int | None:
    """Scan offset, or None (restart) for anything malformed, non-canonical, foreign or drifted."""
    if not cursor.startswith(_CURSOR_PREFIX):
        return None
    body = cursor[len(_CURSOR_PREFIX):]
    if len(body) != _CURSOR_BODY_CHARS:
        return None
    try:
        raw = base64.urlsafe_b64decode(body + "=")
    except ValueError:
        return None
    if len(raw) != 20 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != body:
        return None  # rejects variants that change only the 2 unused bits
    nonce, sealed, tag = raw[:4], raw[4:8], raw[8:]
    gen = generation.to_bytes(8, "big")
    expected = hmac.new(key, b"rush.page-cursor.tag\x00" + nonce + sealed + binding + gen, hashlib.sha256).digest()[:12]
    if not hmac.compare_digest(tag, expected):
        return None
    stream = hmac.new(key, b"rush.page-cursor.stream\x00" + nonce, hashlib.sha256).digest()[:4]
    return int.from_bytes(bytes(a ^ b for a, b in zip(sealed, stream, strict=True)), "big")
```

- I prototyped this in a sandbox. Round trip works; a changed generation or binding returns `None`; a flipped unused bit, a non-ASCII character or extra characters return `None`; output is deterministic.
- **Size, measured with tiktoken:** a 1-item page plus this cursor is about 266 bytes and 74–85 tokens. The current 380-character cursor gives 616 bytes and 314 tokens, which would push `test_serialized_payload_obeys_both_caps` (400 bytes / 100 tokens) to `E_BUDGET`.
- **Values:** the namespace is `str(store.project_root)`. The project, worktree, owner, revision and grant come from T01's resolved access, and are all `None` on the legacy explicit-allowlist route.

**Page measurement.**
- `_measure_page(items, next_cursor, complete, encoding, extra=None)` keeps its four positional arguments; `extra` merges extra keys.
- Add a token-free `_page_bytes(...)` helper.
- `_trial_page_bytes(..., reserve_cursor: str | None = None)` returns the cursor-free base page's bytes when the trial page fits, otherwise `None`. The trial page is `items + [item]` with `next_cursor=reserve_cursor` and `complete=(reserve_cursor is None)`.
  - Bytes reserved: `len(c) + 2 - 4 + 1`.
  - It keeps the existing shortcut: fully tokenize only when `reserved_bytes > max_tokens` or `_contains_special_token(item_text, encoding)`. This is safe because cl100k tokens are always at least one byte each.
  - `_contains_special_token` must still be consulted on every trial; the amended r5 oracle depends on it.
  - `hybrid_page` keeps calling it without `reserve_cursor`, so its behavior is identical.

**Admission and error pages.**

```python
def _recall_required(max_bytes: int, max_tokens: int, encoding: str) -> dict[str, int] | None:
    min_bytes, min_tokens = _measure_page([], None, False, encoding)
    if max_bytes < min_bytes or max_tokens < min_tokens:
        return {"max_bytes": min_bytes, "max_tokens": min_tokens}
    return None

def _budget_page(encoding: str, required: tuple[int, int], max_bytes: int, max_tokens: int) -> dict[str, Any]:
    extra = {"required": {"max_bytes": required[0], "max_tokens": required[1]}}
    size = _measure_page([], None, False, encoding, extra)
    if size[0] > max_bytes or size[1] > max_tokens:  # diagnostics don't fit: canonical minimum only
        extra = {}
        size = _measure_page([], None, False, encoding)
    page = _page("E_BUDGET", encoding=encoding, tokens=size[1], bytes_=size[0])
    page.update(extra)
    return page
```

**`recall_page` order of checks.**
1. Empty allowlist: unchanged, returns OK complete.
2. `limit` is not an `int` or is less than 1 → `E_INPUT`.
3. `cursor` is neither `None` nor a `str` → `E_INPUT`.
4. `_encoder(encoding)` raises `ValueError` → `E_INPUT`.
5. `_recall_required(...)` returns a value → `E_INPUT` with `required`, `tokens=0`, `bytes=0`, no telemetry.
6. Read the key (`TypeError` or `sqlite3.OperationalError` → `E_MIGRATION`). Read `generation = store.current_generation()`. Build the binding. Decode the cursor (`None` → `E_RESTART`).
7. Run the scan loop below.

**The scan loop.** The eligibility step is T01's committed per-candidate decision followed by `_candidate_to_item`; it returns `None` for corrupt or ineligible rows.

```python
    items: list[dict[str, Any]] = []
    base_bytes = _page_bytes([], None, True, encoding)
    position = last_fit = scan_offset
    pending: tuple[dict[str, Any], int] | None = None   # (item, start): fits only as the final page
    blocked: tuple[dict[str, Any], int] | None = None   # (item, start): fits no page
    more = exhausted = False
    scanned = 0
    while not more and not exhausted and scanned < _SCAN_CAP:
        batch_limit = min(_BATCH_SIZE, _SCAN_CAP - scanned)
        batch = store.search_candidates(subject, query, source_allowlist=allowed_sources,
                                        scan_offset=position, scan_limit=batch_limit)
        for row in batch:
            item = eligible_item(row)
            if item is not None and (pending is not None or len(items) >= limit):
                more = True                      # eligible row left, not consumed
                break
            start, position, scanned = position, position + 1, scanned + 1
            if item is None:
                continue                         # corrupt or ineligible: consumed
            fit = _trial_page_bytes(items, base_bytes, item, max_bytes=max_bytes, max_tokens=max_tokens,
                                    encoding=encoding,
                                    reserve_cursor=_encode_cursor(key, binding, generation, position))
            if fit is not None:
                items.append(item); base_bytes = fit; last_fit = position
                continue
            final = _trial_page_bytes(items, base_bytes, item, max_bytes=max_bytes,
                                      max_tokens=max_tokens, encoding=encoding)
            if final is not None:
                pending = (item, start)
                continue
            blocked, position, scanned, more = (item, start), start, scanned - 1, True
            break
        if not more and len(batch) < batch_limit:
            exhausted = True
```

**After the loop.** In every branch below that emits a cursor, the cursor is `_encode_cursor(key, binding, generation, resume)`.
- **`pending` and the scan reached the end:** append the pending item. The page is complete with no cursor.
- **`pending`, more remain:** `resume = pending.start`.
- **`blocked`:** `resume = blocked.start`.
- **Scan reached the end with nothing pending:** the page is complete.
- **Otherwise:** `resume = position`.
- **Complete page:** measure it. If it somehow exceeds a cap, emit the items with the `last_fit` cursor and `complete: false`; that combination was already measured to fit.
- **Incomplete page with items:** measure with the `resume` cursor. If it exceeds a cap, use the `last_fit` cursor; that text is identical to the accepted trial.
- **Incomplete page, no items, with a stuck record (pending or blocked):** return `_budget_page(encoding, _measure_page([stuck], _encode_cursor(key, binding, generation, resume + 1), False, encoding), ...)`.
- **Incomplete page, no items, nothing stuck** (the scan cap was spent on ineligible rows): emit an OK empty page with a cursor if it fits, otherwise `E_BUDGET` with that size as `required`.
- **Before emitting:** if `store.current_generation() != generation`, return `E_RESTART` with no items. Then run T01's policy re-resolution if it exists; a changed revision gives `E_RESTART`, a revoked grant gives T01's denial.
- **Telemetry:** only OK pages record an event.
- **Tokenizer calls:** at most admission + final + one fallback, which is at most 3 (`test_r5_recall_page_does_not_retokenize_each_trial_page`).
- **`now`:** add `now: float | None = None` to `recall_page` if T01 hasn't, and pass it to T01's eligibility.

**`expand_artifact`.** New keyword `representation: Literal["base64", "utf8"] = "base64"`. Order of checks:
1. `representation` is not one of the two values → `E_INPUT`.
2. `offset < 0` → `E_OFFSET`.
3. Admission: the utf8 minimum is the measured `_utf8_payload` with every content field null and `complete: false`; the base64 minimum is `{"content_base64": null, "next_offset": null, "complete": false, "encoding": enc}`. Below either → `E_INPUT` with `required`, before any store read.
4. T01 eligibility fails → `E_NOT_VISIBLE`.
5. Version mismatch → `E_VERSION`.
6. Read `(content, payload_hash)`.
7. **utf8 only:** a null hash → `E_MIGRATION`; `sha256(data) != payload_hash` → `E_NOT_VISIBLE`.
8. `offset > total`, or in utf8 mode an offset that is not a boundary → `E_OFFSET`.
9. Slice.

base64 slicing keeps the legacy shrink loop. Its `E_BUDGET` gains `required` from the one-byte chunk measurement.

```python
def _is_boundary(data: bytes, offset: int) -> bool:
    return offset == len(data) or (data[offset] & 0xC0) != 0x80

def _utf8_slice_end(data: bytes, offset: int, fits: Callable[[int], bool]) -> int | None:
    total = len(data)
    first = offset + 1
    while first < total and not _is_boundary(data, first):
        first += 1                                   # end of one scalar
    end = total
    while True:
        while end > first and not _is_boundary(data, end):
            end -= 1
        if end <= first:
            return first if fits(first) else None
        if fits(end):
            return end
        span = end - offset
        end = offset + span - max(1, span // 4)
```

The utf8 payload builder is:

```python
_utf8_payload(*, artifact_id, version, offset, next_offset, complete, content_utf8, payload_hash, total_bytes, encoding) -> dict
```

It returns those keys plus `"representation": "utf8"`. The measurement is `json.dumps(payload, ensure_ascii=False, separators=(",", ":"))`, giving UTF-8 byte length and `_count_tokens`.
- `fits(end)` builds the OK payload with `next_offset = end if end < total else None` and `content_utf8 = data[offset:end].decode("utf-8")`.
- `offset == total` uses the same fit check, so an empty OK page still has to fit.
- `E_BUDGET` and `E_OFFSET` use null content, null hash and null `total_bytes`. The exception: `E_OFFSET` after the store read reports the real `total_bytes`.
- `E_NOT_VISIBLE` bodies are identical for missing, denied and tampered artifacts (`version: null`).
- A successful utf8 expansion records an `"expansion"` telemetry event. I checked the slicing prototype for every cap from 1 to 44 bytes on `{"text":"needle 🙂é𐍈 é 🙂é𐍈"}`: every result was exact, and every end fell on a boundary.

**Receiver check (`transport.py`, the only change in that file).**

```python
def reassemble_utf8_expansion(pages: Sequence[Mapping[str, Any]], *, artifact_id: str,
                              version: int) -> tuple[bytes, str]:
    if not pages:
        raise HandoffError("no expansion pages", code="E_INPUT")
    chunks: list[bytes] = []
    expected = 0
    payload_hash: str | None = None
    total: int | None = None
    for index, page in enumerate(pages):
        text = page.get("content_utf8")
        if page.get("representation") != "utf8" or not isinstance(text, str):
            raise HandoffError("expansion page is not a utf8 slice", code="E_INPUT")
        if page.get("id") != artifact_id or page.get("version") != version:
            raise HandoffError("expansion page names another artifact version", code="E_VERSION")
        page_hash, page_total = page.get("payload_hash"), page.get("total_bytes")
        if index == 0:
            if not (isinstance(page_hash, str) and len(page_hash) == 64
                    and all(c in "0123456789abcdef" for c in page_hash)) or type(page_total) is not int:
                raise HandoffError("expansion page lacks a payload digest", code="E_INPUT")
            payload_hash, total = page_hash, page_total
        elif page_hash != payload_hash or page_total != total:
            raise HandoffError("payload digest changed between pages", code="E_VERSION")
        try:
            chunk = text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HandoffError("expansion page is not valid UTF-8 text", code="E_INPUT") from exc
        last = index == len(pages) - 1
        if page.get("offset") != expected or (not chunk and not last):
            raise HandoffError("expansion pages are out of sequence", code="E_OFFSET")
        expected += len(chunk)
        nxt = page.get("next_offset")
        if page.get("complete") is not last or (nxt is None) != last or (nxt is not None and nxt != expected):
            raise HandoffError("expansion pages are out of sequence", code="E_OFFSET")
        chunks.append(chunk)
    data = b"".join(chunks)
    if len(data) != total:
        raise HandoffError("reassembled length differs from total_bytes", code="E_OFFSET")
    digest = hashlib.sha256(data).hexdigest()
    if digest != payload_hash:
        raise HandoffError("reassembled bytes do not match payload_hash", code="E_VERSION")
    return data, digest
```

**Public routes.**
- `tools/memory.py`:
  - add `"representation"` to `_EXPAND_REQUEST_KEYS`;
  - add `"E_OFFSET": "error"` to `_CODE_STATUS`;
  - `_expand` validates that `representation` is a `str` with one of the two values (otherwise `E_INPUT`), passes it through, and appends `":utf8"` to the telemetry `request_id` only in utf8 mode (base64 IDs unchanged);
  - `_compact_query` returns `E_INPUT` for `retrieval == "hybrid"` with a non-None `cursor`, inside the existing type-check block before the permission checks. Limit, caps and encoding are checked in `retrieval.py`.
- `request_models.py`: add `"representation": (Literal["base64", "utf8"], _OPTIONAL)` to `MemoryExpandRequest`.
- Docstrings: the `retrieval.py` module and `recall_page` docstrings, and `scripts/benchmarks/memory.py:134–139` (docstring only).

### 4. Existing tests that must change, with the reason

- **`tests/test_memory_retrieval.py::test_serialized_payload_obeys_both_caps`.**
  - Its tail sends `max_bytes=1` and expects `E_BUDGET`, but that envelope (about 72 bytes) is itself larger than the cap. Plan §2.1 item 5 bans exactly that "oversized purportedly in-budget E_BUDGET".
  - Change: assert `E_INPUT` with `items == []` and `data["required"]["max_bytes"] > 1`.
  - Also assert the budget-stopped page has `complete is False`, a non-null `next_cursor` and at least one item.
- **`::test_unicode_expansion_reconstructs_exact_original`.** Same reason for its `max_bytes=1` tail. Change it to `E_INPUT` with `content_base64 is None`.
- **`tests/test_phase70_ts.py::test_r5_recall_page_matches_the_old_loop_across_budgets`.**
  - Its oracle `_old_budget_loop` measures every trial with `next_cursor=None` and `complete=True`. That encodes the false completion, and with honest cursors item choice must reserve cursor space.
  - Change: for each budget,
    - compare `page` with a reference computed under `monkeypatch.setattr(retrieval, "_contains_special_token", lambda text, encoding: True)`, which forces full tokenization. The whole dicts must be equal.
    - On `E_BUDGET`: assert `items == []`, `next_cursor is None`, `complete is False`.
    - Otherwise: `items == full["items"][:len(items)]`; `complete == (len(items) == 40)`; `(bytes, tokens) == retrieval._measure_page(items, next_cursor, complete, "cl100k_base")`, both within the caps.
  - `test_r5_hybrid_page_matches_the_old_loop_across_budgets` is unchanged.
- **Unchanged and still valid:** `test_scan_cap_returns_continuation` and `test_cursor_rejects_scope_or_generation_change`. The tamper in the latter flips the last character between `"0"` and `"1"`; the canonical re-encode check turns that into `E_RESTART`.

### 5. Cross-task conflicts

- **72-T01.** T02 rewrites the `recall_page` loop that T01 just edited. It must keep T01's per-candidate eligibility check, denial codes and access threading. Earlier units change: `recall_page`, `expand_artifact`, `hybrid_page`, `MemoryTool._compact_query`/`_expand`/`run`, `store.search_candidates`/`_write_version`/`open_readonly_view` and the `payload_hash` columns. T01 must provide `payload_hash` storage (section 0, item 3).
- **73-T02/POLICY.** Supplies the grant, revoke and resolve functions used in R7.
- **72-T03.** `_candidate_to_item` calls `relations.related_artifacts`, which T03 owns. T02 doesn't change it. Item size may grow, which shifts budget-driven page boundaries but not correctness.
- **72-T06.** Strict v2 must keep `representation`, the cursor, `E_OFFSET` and T02's admission helpers (`_recall_required` and the expand minimum). On top of those it adds transport framing, `limit` 1–100 and v2 keys, without re-implementing them.
- **72-T07.** TUI, dashboard and CLI stay on base64 in T02; T07 may adopt utf8. The TUI page cache (`tui.py:3488`) is unaffected.
- **72-T08.**
  - `hybrid_page` always returns `complete: true` even when truncated by `limit`, budget or the candidate cap (`retrieval.py:1027–1048`).
  - Its lexical fallback overwrites `recall_page`'s `E_BUDGET`/`E_INPUT` code with `E_EMBEDDING_UNAVAILABLE` (line 996).
  - Plan T08 line 386 owns "explicitly labeled incomplete", so T02 leaves `hybrid_page` alone apart from the shared `_trial_page_bytes`, whose behavior there is identical.
- **72-T09.** Documents `representation`, `E_OFFSET`, `E_INPUT` admission, the opaque cursor and `required`, and fixes the MC02 truth labels.
- **73-T05.** Later edits `transport.py` and `tests/test_memory_handoff.py`. `reassemble_utf8_expansion` is an added pure function it can reuse for its "after successful actual expansion" receipt.
- **Phase 70.** One amended r5 test. T28-D UI tests are unaffected because base64 is unchanged.
- **Phase 71, 73-T09, 75-T02.** No overlap. Benchmark probes follow cursors to `complete` and still terminate.
- **Finding for T06/T07, verified:** stored memory JSON is ASCII-escaped, so lexical search for non-ASCII terms returns 0 hits (the sandbox probe: "café" → 0, "needle" → 1). This is F18 territory, not T02. (verified-by: PM re-ran the sandbox probe at 07775f1, which printed `0 1`.)

### 6. Test matrix

**Shared fixtures**
- **`_t02_literal_utf8(root)`:**
  - write `u1` (DERIVED, `domain_knowledge`, `source-a`) through `store.write` with value `{"text": "needle 🙂é𐍈 é 🙂é𐍈 é"}`;
  - then rewrite `memory_artifacts.content` and `memory_artifact_versions.content` for version 1 to `json.dumps(value, ensure_ascii=False)`, setting T01's `payload_hash` to its sha256 (use T01's backfill helper if one exists, otherwise raw SQL);
  - precondition: the stored bytes contain `b"\xf0\x9f\x99\x82"` and `b"\xcc\x81"`.

  These are the same bytes `_backfill_legacy_row` keeps from pre-MC01 rows.
- **Rank oracle:** a page with `limit=100` and caps of 1e6.
- **Recall caps:** every recall test also checks that `bytes` and `tokens` equal an independent `json.dumps` + tiktoken measurement.

**What the RED run fails on.** RED runs at T01's commit, so every "expected RED failure" below is against post-T01 code.

| ID | Fixture | Action | Assertion | Expected RED failure (at T01 HEAD) |
|---|---|---|---|---|
| R1 `test_t02_exact_once_paging_and_utf8_recovery` | p1, p2, p3 with identical "needle" text; `_t02_literal_utf8` | `limit=2`, then follow the cursor. Expand utf8 from every offset 0..total, (a) with caps of 1e6 and (b) with `max_bytes` = empty-OK `bytes` + 8, following pages. Also expand base64 with no representation and with `"base64"`. | Pages are `[p1, p2]` (`complete` False, cursor set), then `[p3]` (`complete` True, cursor None), with no repeats. Each boundary offset joins back to `data[o:]`, every `next_offset` is a boundary, and `sha256(data) == payload_hash`. Non-boundary offsets give `E_OFFSET` with `content_utf8` None. base64 keys are exactly `{id, version, offset, next_offset, complete, content_base64, tokens, bytes, encoding}`, and the omitted and `"base64"` results are equal. | `complete is True` on page 1; then `TypeError` from `representation` |
| R2 `test_t02_scan_cap_and_limit_pages_recover_513_once_with_corrupt_rows` | 513 records via `store.write` ("scanme cap cNNNN"); 2 raw corrupt rows | Run A: `limit=10000`, caps 1e6. Run B: `limit=100`. | A: 2 pages, the first not complete. B: 6 pages, only the last complete. Both have 513 unique IDs equal to the valid set, and B's order equals A's. | B page 1 reports `complete: true` |
| R3 `test_t02_budget_and_limit_pages_are_bounded_and_exact_once` | 40 mixed ASCII, CJK and accented records | For each of (3, 8192, 2048), (100, 900, 400), (100, 2000, 150), (7, 400, 150) as (limit, bytes, tokens): follow cursors. On `E_BUDGET`, retry once with `required`, then return to the original caps. | Joined pages equal the oracle exactly once. Each OK page is exact and within caps. `complete` is True only on the last page. No OK page with no items repeats the incoming cursor. | page 1 `complete: true` |
| R4 `test_t02_oversized_record_no_progress_budget_then_recovery` | p1, p3 short; p2's text is "needle " + 200×"🙂" | Follow pages with `max_bytes=700`; repeat the `E_BUDGET` call; retry with `required`. | The oversized record gives `E_BUDGET`: items [], cursor None, complete False, `required.max_bytes > 700`, size within caps; repeating gives the same dict. The retry returns exactly that record. Every record arrives once in oracle order. | no cursor / `complete: true` |
| R5 `test_t02_recall_admission_rejects_caps_below_minimum_before_effects` | 3 records; `search_candidates`, `current_generation` and `cursor_key` patched to raise | `max_bytes=1`; `max_tokens=1`; `Bmin-1`; `Tmin-1`; `limit=0`; `encoding="nope"`; then unpatched at exactly (Bmin, Tmin). `MemoryTool` compact with `cache_write`. | Each is `E_INPUT`. `required` equals the measured `{"items":[],"next_cursor":null,"complete":false,"encoding":"cl100k_base"}`, `tokens == bytes == 0`, nothing patched is called. At exactly the minimum: `E_BUDGET`, `bytes == Bmin`, `tokens == Tmin`, no `required` key. No retrieval telemetry for `E_INPUT` or `E_BUDGET`; one event for an OK page. | gets `E_BUDGET` / OK instead of `E_INPUT` |
| R6 `test_t02_cursor_binding_rejects_drift_and_forgery` | 3 records, `limit=1` cursor; a second store with the same seeds | Change sources, query, subject; write a new record; `archive(p3)`; `sweep_expired` a seeded DERIVED row (old `created_at`); send `""`, `"m2."`, `"garbage"`, `c[:-1]`, `c + "A"`, `c` with only its unused bit flipped, the old v1 format (base64 JSON + `.` + hex HMAC with `store.cursor_key()`), and the foreign store's cursor. | Each gives `E_RESTART`, items [], `next_cursor` None, complete False. The cursor matches `^m2\.[A-Za-z0-9_-]{27}$`. | no cursor at `limit=1` |
| R7 `test_t02_grant_revision_and_revocation_refuse_continuation` | 73-T02 grant for `source-a` (L157 fixture, `data_root=tmp_path/"user-data"`); 3 records | Page 1 through T01 access. Grant again so the revision rises, then page 2 with the cursor and a fresh resolve. Revoke, then page with the cursor. | After the revision change: `E_RESTART`, items [], cursor None. After revocation: `E_PERMISSION`, items [], cursor None, and the serialized page contains no seeded ID. | page 1 has no cursor |
| R8 `test_t02_expiry_rechecked_each_page` | p1, p2 plus p3 DERIVED with `created_at = now0 - 14d + 60` | `limit=2` at `now=now0`; page 2 at `now=now0+120`. | Page 1 `[p1, p2]` not complete. Page 2 is OK, `[]`, complete True; not `E_RESTART`, since the generation didn't change. Precondition: T01 eligibility for p3 at `now0+120` is not visible. | page 1 `complete: true` / `now` kwarg |
| R9 `test_t02_readonly_view_paging_creates_no_key_or_files` | 3 records; snapshot (size, mtime) of everything under `.rush` | Page through `open_readonly_view` with `limit=2` (a new view per page). Then `DELETE FROM memory_cursor_key`, open a new view, `limit=2`. | First run: exact once, no file changes. Second run: `E_MIGRATION`, items [], key rows still 0, no file changes. | no cursor; then `TypeError` |
| R10 `test_t02_utf8_expansion_admission_budget_and_offsets` | `_t02_literal_utf8`; for the `E_INPUT` cases, `get_current`, `get_version_content` and T01's reader patched to raise | utf8 with `max_bytes=1`; `max_tokens=1`; min−1 on each cap; exactly the min; caps of one-scalar size − 1; exactly the one-scalar size at the 🙂 offset; offsets −1, total+1, the 3 inner bytes of 🙂, and total. base64 at −1, total+1 and an inner byte. `MemoryTool` with `cache_write`. | `E_INPUT` with `required`, no reads. Exactly the min → `E_BUDGET` with null content, `next_offset` None, complete False, measured size within caps. One-scalar − 1 → `E_BUDGET` whose `required` equals the one-scalar size. Exactly that size → OK with `next_offset == offset + 4`. utf8 offsets −1, total+1 and inner bytes → `E_OFFSET`; total → OK "" complete. base64 −1 and total+1 → `E_OFFSET`, inner byte → OK. No expansion telemetry for `E_INPUT`/`E_BUDGET`; one for OK. | `TypeError` on `representation` |
| R11 `test_t02_utf8_integrity_migration_and_version_refusals` | `_t02_literal_utf8` | Change one byte of the stored version content but keep the hash; set the hash to NULL; `update_content`, then expand v1. | Tampered → `E_NOT_VISIBLE` with no content, a body equal to a missing ID's body except `id`, for both utf8 and base64. NULL hash, utf8 → `E_MIGRATION`, no content. Old version → `E_VERSION` with `version == 2`. | `TypeError` |
| R12 `test_t02_public_routes_accept_representation_and_preserve_base64` | written record | `MemoryTool` expand with utf8, base64, omitted, and `"hex"`. `validate_and_normalize("rush_memory", {"path", "operation": "expand", "request": {..., "representation": X}})`. `memory_request_model_keys("expand")`. | utf8 data keys are exactly the B8 set. base64 and omitted results are equal, with the legacy keys. `"hex"` → `E_INPUT`. MCP accepts utf8, rejects `"hex"`. `"representation"` is in both the model keys and `_EXPAND_REQUEST_KEYS`. | `E_INPUT` "unknown request field" |
| R13 `test_t02_compact_query_rejects_hybrid_cursor_and_maps_offset_code` | written record | Compact `{"retrieval": "hybrid", "cursor": "m2.x"}` without network; expand with `offset = total + 1`; compact with `limit` 0 and `max_bytes` 1. | `E_INPUT` with status `error` (the hybrid one before `E_PERMISSION`). Expand → `E_OFFSET` with status `error`. `limit` 0 and `max_bytes` 1 → `E_INPUT`, and the latter carries `data["required"]`. | `E_PERMISSION` / clamped OK |
| R14 `tests/test_memory_handoff.py::test_t02_receiver_digest_reconstruction` | `_t02_literal_utf8` (helper copied locally); `prepare_handoff` granting `u1` | Bridge `expand` utf8 with `max_bytes` set for 3 or more pages; `reassemble_utf8_expansion`; bridge `receive` with `ack`. Then tamper: one character of one page's `content_utf8`; one page's `payload_hash`; a dropped middle page; swapped pages; a base64 page; mixing v1 and v2 pages after `update_content`; acking a wrong digest. | Reassembly gives the stored bytes, and the digest equals sha256 and `payload_hash`. Receipts become `{"u1": 1}`. The tampered cases raise `HandoffError` with codes `E_VERSION`, `E_VERSION`, `E_OFFSET`, `E_OFFSET`, `E_INPUT`, `E_VERSION`. The wrong-digest ack returns `E_VERSION` and receipts are unchanged. | `AttributeError` (no `reassemble_utf8_expansion`) |
| A1, A2, A3 | amended existing tests (section 4) | — | — | `E_BUDGET` ≠ `E_INPUT`; `complete is True` |

All tests use pytest `tmp_path`. Skips are not allowed. Imports of symbols that don't exist yet go inside test bodies.

### 7. Worker packages

Both packages are in part B, `worker_package`.

---

## (B) Receipt

```json
{
  "goalbuddy_receipt_v1": {
    "result": "done",
    "task_id": "T005",
    "board_path": "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml",
    "decision": "approved",
    "full_outcome_complete": false,
    "rationale": "72-T02 maps cleanly onto 07775f1. I found 8 defects (D1-D8) by reading the source in retrieval.py. The design (deterministic sealed cursor, peek-to-prove completeness, admission before effects, UTF-8 scalar slicing, receiver reassembly) is fully specified with code. Three files are missing from the packet (request_models.py, MemoryTool._expand/_CODE_STATUS, the benchmark docstring), and three existing tests are proven wrong. payload_hash storage is assigned to T01 and hybrid completeness to T08, as the plan says. No owner decision is needed.",
    "worker_package": {
      "red": {
        "objective": "Write the T005 matrix R1-R14 and amend A1-A3 exactly as in notes/T005-design-gate-72-t02.md sections 4 and 6. Prove every selected test FAILS at the 72-T01 commit before any production change.",
        "allowed_files": [
          "tests/test_phase72_memory_correctness.py",
          "tests/test_memory_handoff.py",
          "tests/test_memory_retrieval.py",
          "tests/test_phase70_ts.py"
        ],
        "verify": [
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_memory_correctness.py','tests/test_memory_handoff.py','-k','t02','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_memory_retrieval.py::test_serialized_payload_obeys_both_caps','tests/test_memory_retrieval.py::test_unicode_expansion_reconstructs_exact_original','tests/test_phase70_ts.py::test_r5_recall_page_matches_the_old_loop_across_budgets','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py tests/test_memory_handoff.py -k t02 --collect-only -q -p no:cacheprovider  # must list exactly 14 tests (R1-R14)"
        ],
        "stop_if": [
          "The 72-T01 commit lacks payload_hash persistence (columns on memory_artifacts and memory_artifact_versions, computed on writes, backfilled by upgrade) or a reader returning the persisted payload_hash for one version.",
          "The 72-T01 commit lacks resolved-access threading through recall_page, expand_artifact, MemoryTool._compact_query and MemoryTool._expand, or 73-T02's grant/revoke/resolve differ from the plan L157 fixture beyond parameter spelling.",
          "Any mapped symbol changed in a way not listed as an expected T01/73-T02 delta in note section 0.",
          "At the T01 commit, one recall item plus the 30-character cursor cannot fit (400 bytes, 100 tokens) in amended A1 (item shape grew). Return for a gate delta; never loosen the caps.",
          "Any selected test passes, skips, xfails or errors at collection, or the -k t02 count differs from 14.",
          "A file outside allowed_files is needed, or behavior is ambiguous against the note.",
          "Verification fails twice."
        ]
      },
      "implement": {
        "objective": "Implement 72-T02 exactly as in notes/T005-design-gate-72-t02.md sections 1 and 3 until R1-R14 and A1-A3 pass, with the full suite, ruff, format, mypy and git diff --check green. Dispatch on Opus (trust boundary).",
        "allowed_files": [
          "src/rush/memory/retrieval.py",
          "src/rush/tools/memory.py",
          "src/rush/memory/transport.py",
          "src/rush/mcp_support/request_models.py",
          "scripts/benchmarks/memory.py"
        ],
        "verify": [
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py tests/test_memory_handoff.py -k t02 -q -p no:cacheprovider",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t02 -q",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_handoff.py tests/test_memory_retrieval.py -q",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py tests/test_phase70_ts.py tests/test_memory_hybrid.py tests/test_phase70_t6.py tests/test_memory_public_contract.py tests/test_memory_efficiency.py tests/test_phase61_handoff.py tests/test_phase70_t28d.py tests/test_phase70_memory_visibility.py tests/test_phase70_t19.py tests/test_dashboard_memory_tokens.py tests/test_memory_acceptance.py tests/test_memory_relations.py tests/test_memory_versions.py tests/test_benchmark_memory.py tests/test_benchmark_memory_agents.py tests/test_benchmark_memory_datasets.py tests/test_mcp.py -q -p no:cacheprovider",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy sed -n 50,92p docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md | rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -  # plan §2.2 probe: must print all four fields true and exit 0",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m '' -p no:cacheprovider",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev mypy src/rush",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy git diff --check",
          "rush_check on the changed files (MCP), status ok"
        ],
        "stop_if": [
          "A RED test looks wrong; return it to the PM and never edit tests.",
          "store.py or any file outside allowed_files is needed (the payload_hash reader is T01's job).",
          "The base64 OK response key set or values would change, or the scripts/benchmarks/memory.py edit would go beyond the _probe_oversized_payload docstring.",
          "An existing test other than A1-A3 fails because of intended T02 behavior; return for a gate delta.",
          "The §2.2 probe 'paging' field is false (T02 defect), or another field is false (report it as a T01 regression).",
          "_contains_special_token is no longer consulted on every _trial_page_bytes trial, or hybrid_page behavior changes.",
          "More than two fix rounds; after round 2 the PM finishes directly."
        ]
      }
    },
    "owner_decisions_needed": [],
    "evidence": [
      "retrieval.py:524 complete formula and :512 scan_offset += len(batch) (read at 07775f1); §2.2 probe baseline paging=false (T002 note)",
      "retrieval.py:684 offset clamp; :446 unconditional cursor_key(); cursor payload JSON includes namespace path and generation (:529-541)",
      "tools/memory.py:174-181 _EXPAND_REQUEST_KEYS; :138-158 _CODE_STATUS has no E_OFFSET; :989-1011 hybrid ignores cursor",
      "request_models.py:399-402 MemoryExpandRequest is extra=forbid; tests/test_phase70_t6.py:791-813 parity of model keys and _EXPAND_REQUEST_KEYS",
      "store.py:675/2179/2202 json.dumps(content) ASCII-escapes; sandbox probe stored '{\"text\": \"caf\\\\u00e9 needle \\\\ud83d\\\\ude42\"}', search 'café' -> 0 hits, 'needle' -> 1",
      "store.py:2029 _backfill_legacy_row copies legacy content verbatim; store.acknowledge_handoff:2456 digest = sha256(content.encode())",
      "tiktoken: 1 item + 30-char sealed cursor = 266 bytes / 74-85 tokens; old cursor = 616 bytes / 314 tokens",
      "Sandbox prototype: cursor round trip, generation/binding drift, unused-bit flip, non-ASCII and extra chars all rejected, deterministic; UTF-8 slicer exact for every cap 1..44 bytes",
      "graft callers --depth all: recall_page, expand_artifact, _encode_cursor, _decode_cursor, _measure_page, _candidate_to_item, _trial_page_bytes",
      "application.js:1023 downloadArtifactContentPages targets /api/projects/{id}/artifacts (server.py:3394-3470, workflows/projects.py), not memory",
      "Plan T08 L386: hybrid no-cursor or capped result must be explicitly labeled incomplete (T08 deliverable)"
    ],
    "subgoal_contract": null,
    "parallel_safety": null,
    "blocked_tasks": [],
    "missing_evidence": [
      "The T004 (72-T01) gate note does not exist yet; the payload_hash split and the access/now parameter names are assumptions the RED author must re-check at the T01 commit"
    ],
    "required_board_updates": [
      "T004/T020 (72-T01): include §2.1 item 2 payload_hash storage (nullable columns on memory_artifacts and memory_artifact_versions, computed in every authorized write path including _write_version, write, update_content, edit, archive and expiry/maintenance version writes, backfilled by upgrade) plus a (content, payload_hash) version reader, and resolved-access plus optional now threading. If the T004 note omits these, issue a T004 delta; store.py stays T01's file.",
      "72-T08 gate input: hybrid_page returns complete=True when truncated (retrieval.py:1027-1048), and its lexical fallback overwrites E_BUDGET/E_INPUT with E_EMBEDDING_UNAVAILABLE (:996). Owned by plan T08 L386.",
      "72-T06 gate input: strict v2 must keep representation, the cursor and E_OFFSET, and reuse T02's _recall_required and expand-minimum admission, adding transport framing and limit 1-100.",
      "72-T06/T07 gate input: defect reproduced by the PM probe (verified-by: café gives 0 hits, needle gives 1), persisted memory JSON is ASCII-escaped so non-ASCII lexical search returns 0 hits (F18 search).",
      "72-T09 gate input: document representation/utf8, E_OFFSET, E_INPUT admission with required, the opaque m2 cursor and honest complete; fix the MC02.md truth labels.",
      "Copy worker_package.red into T021 and worker_package.implement into T022, superseding the prep-time allowed_files and verify."
    ],
    "summary": "Approved. T02 fixes the false complete flag, rows skipped mid-batch, unrecoverable oversized records, oversized E_BUDGET envelopes, the unbound plaintext cursor, offset clamping and the missing utf8 mode. It adds a sealed deterministic 30-character cursor, a peek to prove completeness, admission before effects, scalar-boundary utf8 slicing with a payload_hash check, and transport.reassemble_utf8_expansion. The test matrix is R1-R14 plus 3 amended existing tests. request_models.py and MemoryTool._expand were added to the packet; hybrid completeness goes to T08 and payload_hash storage to T01. No owner decisions.",
    "note": "notes/T005-design-gate-72-t02.md"
  }
}
```