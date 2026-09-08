# Core remediation receipt

Base: `fc2d642`. Worktree: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes`.
No commits, pushes, main edits, delegation, or edits outside assigned paths.

## Changes

1. Maintenance dispatch passes requested project root through store, lock manager, expiry, grounding, staleness, and plugin trust lookup. Permission denial occurs before store/lock construction. CLI exposes `--allow-cache-write`; MCP description names maintenance permission.
2. Real context cache fills persist full-file Merkle hash and file anchor, including empty-symbol whole-file packs. Recall marks changed/deleted/unreadable anchors stale; untouched packs remain hits.
3. `TypedArtifactStore.promote(id, user_stated=..., candidate_sources=...)` evaluates sanitized persisted content under a write transaction, atomically persists STATED/content/signature/timestamp/count, and returns `(MemoryArtifact, PromotionResult)`. Maintenance reuses `promote_stored_artifact`; direct `write(STATED)` remains rejected. Failed row transactions roll back before next row.
4. List delegates to defended query/recall with explicit session allowlist; CLI exposes repeatable `--session`.
5. Expiry selects rows due under first-match TTL policy before applying batch limit, preventing immortal and not-yet-due rows from starving due records.

## TDD and verification

RED before production edits: `tests/test_memory_core_regressions.py`: **21 failed, 2 passed**. Failures demonstrated all six assigned findings. Two initial fixture assumptions were corrected against live implementation: local_tool enters EXTERNAL_WRITE (test now explicitly requests human_derived), and existing sanitizer emits `[REDACTED_OPENAI_KEY]`. Whole-file packing deliberately returns a skeleton; freshness assertion checks defended cache miss while symbol packing additionally verifies new body text.

Final behavioral command:

```sh
rtk proxy env -u VIRTUAL_ENV PYTHONPATH=/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest tests/test_memory_core_regressions.py tests/test_phase61_store.py tests/test_phase61_trust.py tests/test_phase61_memory_tool.py tests/test_phase62_maintenance.py tests/test_phase62_expiry.py tests/test_phase62_cache_gate.py -q --tb=short
```

**60 passed in 4.56s** (23 new regressions, 37 existing). New tests exercise denied resource construction across four sweeps; three two-root sweep paths with decoy cwd untouched; eight real pack/edit/delete/unreadable/untouched cases; persisted sanitized promotion and denial through public recall; rollback on SQLite trigger rejection; list permission/signature/Trojan defenses; bounded expiry starvation; live Click permission/session options. Existing successful maintenance callers now explicitly grant cache writes.

Formatting: `ruff format --check` across nine assigned changed files: **9 files already formatted**.

Lint: `ruff check` across same paths reports **4 existing diagnostics** whose source patterns were verified in base `fc2d642`: `maintenance.py` SIM102 renewal condition; `store.py` UP035 Iterable import and SIM102 signature guard; `memory_cache_gate.py` BLE001 fail-closed recall guard. No new lint diagnostic remains. Full-repository testing belongs to coordinator; this receipt does not claim complete repository acceptance.

## Frozen SHA-256

```text
d4bc131707c969e005d77b6b21ae532fb22227ae79e34f0eebdc71099c31472d src/rush/memory/store.py
fdd5f0cf3f0518c089e55007c809a074e2dd73a855ad5e986dfcfea7a8540a41 src/rush/tools/memory.py
cdee808a4edb7af72ff1c61312d179d08756f0ab2688e40e99b65e03118033dd src/rush/memory/maintenance.py
f4dd197979af639c53a71e8f0d8c595ec35d48deb86267446424d3a09020ce79 src/rush/memory/expiry.py
1b54457b40185f60268019c4bc0b462eb229ce42b71925d81071ba5966f1b3b0 src/rush/token_economy/memory_cache_gate.py
eee55219e2512bb39f9329cde9d2ae5cd1e2334b7002455b161af4306a12b7e7 src/rush/cli.py
c65300adc6f010aa2c0823c47f6061cb4d478737f3ecb0dc7e9b0f012f879bd8 tests/test_memory_core_regressions.py
73f491f9bbf4da6abd43708db4c0b18f0400da108d126efaa11cf5a8bf00bfa8 tests/test_phase62_maintenance.py
3e6dc977cb73bb01dbf011257ca4b7ef68c8fae342433680cf1e796bf6506c2a tests/test_phase61_memory_tool.py
```

## Independent-review cache follow-up

Initial finding 3 remediation was incomplete: legacy no-hash rows could hit, and hashing after packing could pair changed source bytes with obsolete packed text. Coordinator authorized additional producer path `src/rush/codegraph/context_packer.py`; no other additional production path changed.

RED: two deterministic regression tests failed before follow-up source edits (`test_legacy_cache_without_hash_misses_and_refills`, `test_cache_hash_covers_same_read_as_packed_payload`). First seeded a real legacy context_pack row with no baseline hash and stale body. Second wrapped real ContextPacker.pack, edited target immediately after original returned, then exercised actual pack_context write-back; subsequent cache lookup incorrectly hit old body.

Fix: ContextPacker.pack now includes `source_content_hash`, SHA-256 of exact `full_code` read used for skeleton/packed_text (same UTF-8 SHA-256 scheme as MerkleInvalidator). Cache fill persists this producer baseline without rereading the source. Missing producer hashes prevent cache fill; persisted cache candidates missing content hash or file anchor miss and refill. Existing cache-hit fixture now explicitly supplies its source baseline hash. Additional metadata is retained in returned packed payload.

Final behavioral command:

```sh
rtk proxy env -u VIRTUAL_ENV PYTHONPATH=/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest tests/test_memory_core_regressions.py tests/test_phase44_context_pack_cache.py tests/test_phase62_cache_gate.py -q --tb=short
```

**39 passed in 1.13s.** Both reproduced regressions now pass, and next actual pack returns edited body with a valid subsequent hit. Formatting check: four files already formatted. Follow-up lint paths have only two baseline diagnostics: cache gate BLE001 and existing literal Trojan fixture PLE2502 (`U+202E` verified in `fc2d642:tests/test_phase62_cache_gate.py`). No new lint diagnostic remains.

Follow-up frozen hashes below supersede matching hashes above:

```text
14baaf528feba1bbb028f77f76884c936933b003fd004cb6a5358b51388b5a3e src/rush/codegraph/context_packer.py
b619396c41fb4b8d0f4dee215e34aa35ed100ce03634b0668c8aa17975e1df05 src/rush/token_economy/memory_cache_gate.py
d4809583c877293fe6e6d163f27cff557266aafc06b84c676df38a3fc8e187a0 tests/test_memory_core_regressions.py
e0e691a2ccf9f19ad48cdbf8d32487452cc8aec83b1069be81d56364ef229ab5 tests/test_phase62_cache_gate.py
```
