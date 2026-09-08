# Compatibility fixes receipt

Base: `fc2d642`. Worktree: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes`.
No commits, pushes, main-checkout changes, or other worker files changed.

## Changes

- `src/rush/session_memory.py`: canonical `.rush/session_memory.json` now resolves repository root; custom bare paths retain directory isolation. XML selects latest `max_records` records in chronological order. Removed redundant UTF-8 encode argument to satisfy touched-file Ruff.
- `src/rush/memory/preference_store.py`: delete accounts for migrated values and replaces canonical content with a deletion tombstone retaining migration origin. Old value cannot reappear after override deletion or migration replay; subsequent explicit set updates canonical content so migration replay preserves the new value. JSON CAS behavior retained.
- `src/rush/memory/checkpoint_journal.py`: merge migrated checkpoint origin records with physical JSON listing, retaining physical precedence, corruption receipts, newest-first ordering, and avoiding migrated duplicates. String identity preserves previously accepted non-scalar legacy IDs.
- `src/rush/memory/migration.py`: shared transactional `replace_origin_content` compares sanitized bytes, preserves unchanged approval, and resets trust/signature/promotion/corroboration/staleness/expiry metadata for changed content. Checkpoint remigration replaces changed canonical content before renaming fresh JSON; retained origins preserve deduplication. Preference set/delete reuse the same replacement path. Removed two redundant UTF-8 encode arguments to satisfy touched-file Ruff.
- `tests/test_memory_compatibility_regressions.py`: eleven focused behavior cases.

## TDD evidence

Initial focused run: **6 failed, 1 passed**. Failures reproduced:

- `test_default_session_uses_canonical_store`: canonical DB had zero records.
- `test_session_xml_keeps_latest_bounded_history`: returned all four instead of latest two.
- `test_delete_migrated_preference_never_resurrects[False]`: delete returned False.
- `test_delete_migrated_preference_never_resurrects[True]`: old value resurfaced after deletion.
- `test_migrated_checkpoints_preserve_listing_corruption_and_physical_precedence`: listing emptied after migration.
- `test_migrated_handoff_retains_provider_diff_history`: prior provider receipt missing after migration.

`test_custom_session_file_stays_isolated` passed before/after.
Minimum fixes: **7 passed**. Related existing suite: **36 passed**.
Adversarial review found new dedupe set rejected non-scalar legacy IDs. Added `test_checkpoint_listing_retains_non_scalar_legacy_id`; RED reproduced `TypeError: unhashable type: 'list'`. String identity fix followed.

Parent review added delete -> set fresh -> migrate again lifecycle assertions to both preference cases. RED: **2 failed, 6 deselected**, fresh value became None. Shared preference-local sanitized canonical update now handles set and delete; final run below includes these lifecycle assertions.

Independent review found stale STATED signatures after preference mutations and old checkpoint resurrection after second migration. Added `test_mutating_promoted_preference_discards_old_approval[set/delete]` and checkpoint remigration assertions. RED: **3 failed, 7 passed** (two `SignatureMismatchError`; remigration returned zero instead of updating). Shared replacement path fixed these: intermediate **10 passed**. Added end-to-end `test_saved_checkpoint_remigration_preserves_latest_handoff` proving latest receipt/files/list/restore/diff survive repeated save and migration; unchanged preference content retains valid prior approval.

## Final frozen verification

Final SHA-256 subject:

```text
3a31cfa706bf2c588db15173c891c391ea38200e5fb1083198d96f9aaddf227f  src/rush/session_memory.py
d23537781df00f62ba3ebe6ffd8c2caa30e1d47d05ba06d591fb3e771220f2f8  src/rush/memory/preference_store.py
e725b735a2da429791b71ee0e0337f21a7e11dbfe5282dc9c0ff96d22bbf77a6  src/rush/memory/checkpoint_journal.py
b786232071b8b3d58e10596ec000a02ef27534ab20fc74805790506970019d2a  src/rush/memory/migration.py
4f700473e4f14b2ea52bbe1aef56ca47e695e50f1e7fcc80dbe23e0dfa232695  tests/test_memory_compatibility_regressions.py
```

```bash
rtk proxy env -u VIRTUAL_ENV PYTHONPATH=src /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest tests/test_memory_compatibility_regressions.py tests/test_session_memory.py tests/test_phase41_memory_ship.py tests/test_phase53_state_writers.py tests/test_phase58_checkpoint_journals.py tests/test_phase58_map_transactions.py tests/test_phase58_persistence.py tests/test_phase61_migration.py tests/test_phase61_episodic.py -q
```

Result before final equality correction: **47 passed in 1.83s**. Owned files Ruff check passed; Ruff format check: **5 files already formatted**.

Independent re-review reproduced JSON boolean/number equality losing type changes on remigration and retaining obsolete approval. Coordinator added four `test_preference_json_type_change_survives_remigration` cases (1/true and 0/false, both directions): **4 failed, 11 deselected in 0.37s** before fix. `replace_origin_content` now compares sorted JSON serialization, preserving object-key order independence without conflating distinct JSON values. Post-fix command covering this regression file plus Phase 61 migration, Phase 41 memory, Phase 58 persistence and map transactions: **35 passed in 1.21s**. Ruff check and format check for the two changed files pass. SHA-256 values above reflect this final correction; no runtime/test writes after that verification.

## Limits

Integration baseline and frozen independent review belong to parent. This receipt proves compatibility behavior in native macOS project interpreter, not Windows execution or whole-repository acceptance. Session `max_records` retains existing positive-limit API semantics. Preference JSON and SQLite remain distinct persistence transactions; this patch does not claim cross-backend atomicity. TypedArtifactStore implementation untouched by this worker.
