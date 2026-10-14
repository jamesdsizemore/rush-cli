# T003: Design gate for 73-T02/POLICY (`src/rush/memory/authorization.py`)

Worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`, HEAD `07775f1`. This gate is read-only. A goal-judge agent wrote it. The PM re-ran its load-bearing claims; see the next section.

## PM re-checks (run on 07775f1 with `.venv/bin/python`; outputs quoted)

1. **The secret redactor corrupts real paths.** `sanitize_value({'project_root':'/Users/j/Developer/desk-assistant-project-v2','src':'token:abc'})` returned `{'project_root': '/Users/j/Developer/de[REDACTED_OPENAI_KEY]', 'src': 'token:[REDACTED]'}` with `redaction_count=2`. The plan mandates `CASMapTransaction`, which sanitizes everything it writes, so plain paths would be corrupted. This is why the design hex-encodes stored values (section 3).
2. **Importing some modules drags in large parts of the codebase.**
   - In a fresh interpreter, `import rush.dashboard.state` loads `rush.dashboard.server`, `rush.memory.retrieval`, `rush.memory.store` and `rush.tools*`.
   - `import rush.workflows.projects` loads `rush.memory.retrieval`, `rush.memory.store` and `rush.tools*`.
   - `rush.setup.provision`, `rush.memory.transactions`, `rush.io.atomic_file`, `rush.io.physical_paths` and `rush.safety.redactor` each load none of these.
3. **`CASMapTransaction` creates directories when constructed.** `self.root_path.mkdir(parents=True, exist_ok=True)` runs at `src/rush/memory/transactions.py:75` and `:85`. It therefore cannot be used on the read path.

verified-by: `.venv/bin/python -c "from rush.safety.redactor import sanitize_value; print(sanitize_value({...}))"`; for each module, `.venv/bin/python -c "import sys,<module>; print(sorted(m for m in sys.modules if m.startswith(('rush.tools','rush.dashboard.server','rush.memory.retrieval','rush.memory.store','rush.workflows'))))"`; `sed -n 71,96p src/rush/memory/transactions.py | grep -n mkdir`.

**PM design flag: hex encoding.** The design hex-encodes stored path and identity fields so that values survive `CASMapTransaction` sanitization. The other option was to bypass sanitization for this one file. That would mean not using the writer the plan mandates, so hex encoding is the option that stays within the plan. One consequence: all consumers must read the policy through `load_policy_readonly`.

**Not re-run by the PM:**
- the `register_project` / `relink_project` probe;
- the transitive-caller counts;
- the `cross_process_project_lock` path (`state.py:44-58`).

The T015 RED author re-checks these when the task starts (see its stop_if).

## PM amendment after T015 (matrix row `test_relink_and_foreign_worktree_rejected`)

The T015 author found that the original row contradicted §3's resolve stage table in two places:

- **Old path after the move.** The path is absent, so stage 3 returns `project_missing`, not `project_not_registered`.
- **`worktree_mismatch` was unreachable after the relink.** The grant's root no longer matches any registered root, so every reading returns `relinked`.

The stage table stays as designed. The row is corrected as follows:

- The old path (absent after the move) resolves `project_missing`.
- `worktree_mismatch` uses a second project that is never relinked: grant on project C, rename C's directory away, `mkdir` the same path, `register_project` it again (it returns the same project_id), then resolve. Expect `worktree_mismatch`.

The other assertions in the row are unchanged: the worktree resolves `no_grant`; the moved path resolves `relinked` with and without the binding; registering a binding on the relinked grant gives `E_GRANT_INACTIVE`.

T015's other choices are recorded as the meaning of this matrix:

- **Invalid-file reasons:**
  - `bool_version` gives `revision_invalid`;
  - `bool_policy_revision` gives `revision_mismatch`;
  - `unknown_grant_field` gives `record_invalid`;
  - `directory_at_file` gives `not_regular_file`;
  - both symlink cases give `symlink`.
- **Test conventions:**
  - The signature check covers all 8 §3 functions.
  - `policy_path` and `project_root` are compared as str or Path.

## Scope

This checkpoint does not pass 73-T02 on its own. BOOTSTRAP keeps the dispatcher, the CLI and MCP schema, `tests/test_memory_activation_lifecycle.py`, the setup and connect callers, and the config-mutation permission check in those callers.

POLICY runs first, so no earlier unit changes the code it depends on. The primitives it reuses are in no Phase 72 file map.

## 1. Testable behavior

1. **Missing-policy reads create nothing.** `load_policy_readonly` and `resolve_memory_scope` are called with no policy, an absent or empty data root, or `data_root=None` under a patched HOME, XDG_DATA_HOME or LOCALAPPDATA.
   - They create no data root, `user/`, `.rush/`, policy file, `dashboard/project_locks/` lock, registry, or project `.rush/`.
   - Load returns `state="missing"`, `reason="policy_missing"`, `policy_revision=0`.
   - Resolve returns `access="denied"`, `reason="policy_missing"`.
2. **Writers check consent first.** When `consent is not True`, a writer raises `MemoryPolicyError(code="E_CONSENT")` before any filesystem effect.
3. **CAS revision.**
   - A successful mutation writes outer `version = N+1` and inner `data.policy_revision = N+1`.
   - The file shape is `{"schema_version":"1.0.0","version":N,"data":{"schema_version":1,"policy_revision":N,"grants":{},"bindings":{},"mappings":{}}}`.
   - A stale `expected_policy_revision` raises `E_VERSION` and leaves the file bytes unchanged. There is no retry.
4. **Idempotent no-op.** An identical active grant or binding returns the existing record without a write, even at a stale expected revision. Any real change needs `expected == current`.
5. **One active grant per scope key.**
   - The scope key is `(principal, project_id, project_root, worktree_id, owner_scope)`.
   - A changed grant supersedes the old one in the same CAS write: `revoked=true`, `revoked_revision=N+1`, `superseded_by=<new id>`.
   - The old grant's bindings are revoked.
6. **Cross-process serialization.**
   - Writers hold `cross_process_project_lock("memory-policy:" + str(policy_path), data_root=<resolved data root>)` from reread through atomic replace.
   - With two subprocess writers at revision N, exactly one commits N+1 and the other gets `E_VERSION`.
7. **Resolve rechecks everything on every call.** It rebinds principal, canonical root, registry project ID, worktree, revocation, expiry, owner, operation, sources and binding. A denial carries one exact reason, `grant_id=None`, `owner_scope=None`, `approved_sources=[]` and `allowed_operations=[]`.
8. **Reads change nothing.** Repeated load and resolve calls leave the file's sha256 and `st_mtime_ns` unchanged.
9. **Strict loader.**
   - It returns `state="invalid"` with an exact reason for: duplicate JSON keys, non-UTF-8 or malformed JSON, a bad envelope, a bool or non-int revision, an outer/inner revision mismatch, an unsupported schema, unknown or missing fields, a dangling binding, duplicate active grants, a symlinked component, a non-regular file, or (on POSIX) a file owned by another uid.
   - Resolve maps any invalid state to `policy_invalid`.
   - Writers refuse with `E_POLICY_INVALID` and never overwrite the file.
10. **Bindings.**
    - A binding is validated against its grant. A forged, unknown, revoked, stale or cross-project binding is denied.
    - A binding only narrows the candidate set; it never widens it.
    - Host and session values are attribution only; `resolve_memory_scope` has no host or session parameter.
11. **The personal overlay needs its own grant.** That grant has owner `user_overlay_owner_scope(data_root)` and operation `"overlay_read"`. It is never selected implicitly (`owner_scope=None`), and project grants cannot carry `overlay_read`.
12. **Every persisted value survives the secret redactor.** See PM re-check 1.

## 2. Code and caller map (07775f1)

**Create:** `src/rush/memory/authorization.py`. It does not exist yet and has no callers.

**Reused, not edited:**

| Symbol | Location | Role |
|---|---|---|
| `CASMapTransaction` | `src/rush/memory/transactions.py:68-215` | Writers only, because the constructor runs `mkdir` (`:71-95`). `read` (`:97`) uses plain `json.loads` with no duplicate-key check. `write(new_data, expected_version)` (`:151-189`) re-reads the file, raises `CASConflictError`, and writes the `"1.0.0"` envelope through `SanitizedJsonValue` and `AtomicFile`. Its lock is process-local only (`RLock`, `:60-65`). Callers: `integrations/agents.py:987,1522`, `memory/invariant_graph.py:20`, `merkle_invalidator.py:20`, `migration.py:291`, `preference_store.py:15`. |
| `AtomicFile` | `src/rush/io/atomic_file.py:63-159` | `write_bytes` opens the target contained, creates the parent directory, writes a 0600 temp file, fsyncs, re-checks for symlinks, then calls `os.replace`. |
| `PhysicalRoot` | `src/rush/io/physical_paths.py:20-109` | Raises `ValueError` when the root is missing and creates nothing. `open_contained` rejects absolute paths, `..`, symlinks and paths that escape the root. |
| `default_data_root` | `src/rush/setup/provision.py:124` | Darwin: `~/Library/Application Support/Rush`. Windows: `%LOCALAPPDATA%/Rush`, else `DataRootUnavailableError`. Otherwise: `$XDG_DATA_HOME/rush`, or `~/.local/share/rush`. |
| `cross_process_project_lock` | `src/rush/dashboard/state.py:64-106`, acquire `:110-145` | Reentrant per thread and identity. POSIX `flock` on `<data_root>/dashboard/project_locks/<sha256(id)>.lock` (`:44-58`); a mutex on Windows. |
| `read_registry_strict` | `src/rush/workflows/projects.py:293` | Not in the plan packet. Read-only. Returns `missing`, `ok`, `corrupt` or `unreadable` for `<data_root>/projects.json`. Entries look like `{project_id: {root, revision, ...}}`. |
| `register_project`, `relink_project` | `src/rush/workflows/projects.py:413`, `:928` | Not in the plan packet. Used by tests only. |
| `OwnerScope`, `legacy_owner_scope` | `src/rush/memory/store.py:249`, `:290` | `OwnerScope.kind` is one of `user`, `project`, `session`, `agent`. |
| `sanitize_value`, `SecretRedactor.redact_text` | `src/rush/safety/redactor.py:52`, `:150` | Not in the plan packet. Used for the redaction precheck and to reject secret-like labels. |

**Import rule.** At module level, import only stdlib plus `rush.setup.provision`, `rush.memory.transactions`, `rush.io.*` and `rush.safety.redactor`. Import `cross_process_project_lock`, `read_registry_strict` and `OwnerScope` lazily inside functions, and use `TYPE_CHECKING` for annotations. Otherwise 72-T01, which imports `authorization` from `retrieval.py`, `store.py` and `tools/memory.py`, creates a cycle. This rests on PM re-check 2.

**Future consumers** import this module but never edit its loader or writers:

| Unit | Files | What it uses |
|---|---|---|
| 72-T01 | `memory/retrieval.py`, `memory/store.py`, `tools/memory.py`, `tools/review.py`, `token_economy/memory_cache_gate.py` | `resolve_memory_scope` and `load_policy_readonly` |
| 72-T05 | `memory/preference_store.py` | Overlay resolve |
| 72-T06 | `tools/memory.py` and `store.apply_import_records` | `hold_policy_lock` and resolve |
| 73-T02/BOOTSTRAP | `tools/agent_connection.py`, `integrations/agents.py`, `tools/install.py`, `cli.py` | Grant and binding writers |
| 73-T06/T09 | (not named) | `mappings` writers |

Phase 70's `integrations/agents.py:975-987` writes `default_data_root()/user/.rush/agent_memory.json`. That is a sibling file; it does not collide and is never authority.

## 3. Design of the hard parts

**Public API.** All parameters are keyword-only. The first five signatures are the plan's.

```python
GRANT_OPERATIONS = frozenset({"ask","bootstrap","expand","list","write","history","overlay_read"})
POLICY_RELATIVE_PATH = Path("user/.rush/memory_authorization.json")
class MemoryPolicyError(Exception):  # .code, .reason (str|None)
def policy_path(*, data_root: Path | None = None) -> Path
def user_overlay_owner_scope(*, data_root: Path | None = None) -> OwnerScope  # OwnerScope("user", str((root/"user").resolve()))
@contextmanager
def hold_policy_lock(*, data_root: Path | None = None) -> Iterator[None]
def load_policy_readonly(*, data_root: Path | None = None) -> dict[str, Any]
def grant_memory_scope(*, project_root: Path, owner_scope: OwnerScope, approved_sources: Sequence[str], allowed_operations: Sequence[str], expected_policy_revision: int, consent: bool, expires_at: float | None = None, data_root: Path | None = None) -> dict[str, Any]
def revoke_memory_scope(*, grant_id: str, expected_policy_revision: int, consent: bool, data_root: Path | None = None) -> dict[str, Any]
def resolve_memory_scope(*, project_root: Path, operation: str, owner_scope: OwnerScope | None = None, requested_sources: Sequence[str] = (), session_binding: str | None = None, data_root: Path | None = None) -> dict[str, Any]
def register_memory_binding(*, grant_id: str, session_id: str, host_id: str, expected_policy_revision: int, consent: bool, data_root: Path | None = None) -> dict[str, Any]
```

**Test seams:**
- `_current_os_principal()` returns `uid:{os.getuid()}` on POSIX. On Windows it returns `sid:` plus the token-user SID, read with ctypes and marked `pragma: no cover`. It raises on failure.
- `_now()` returns `time.time()`.

**Operations:**
- `write` resolves to `access="write"`. Every other operation resolves to `"read"`.
- `history` serves 72-T06's explicitly authorized historical reads.
- `overlay_read` serves 72-T05. It is valid only with `user_overlay_owner_scope`; with any other owner it raises `E_INPUT`.

**Data root:** `Path(data_root or default_data_root()).resolve()`.
- The policy file is `root/user/.rush/memory_authorization.json`.
- The lock is under `root/dashboard/project_locks/`.
- The registry is `root/projects.json`.

**Identity:**
- `project_id` is the registry UUID whose `root == str(Path(project_root).resolve())`. An unregistered root raises `E_PROJECT_NOT_REGISTERED`.
- `worktree_id` is `sha256(f"{canonical_root}\0{os.stat(root).st_ino}")`, as a hex string. It does not use `st_dev`, which can change across reboots. Replacing or moving the directory changes the id. Each git worktree is a separate registered root.

**Persisted records.** Path and identity strings are stored as lowercase UTF-8 hex. `[0-9a-f]` matches none of the `SECRET_PATTERNS`.

Grant:

```
{grant_id(uuid4), principal, project_id, project_root_hex, worktree_id, owner_scope:{kind,id_hex},
 approved_sources_hex:[sorted by decoded], allowed_operations:[sorted], consented_at:float,
 expires_at:float|null, granted_revision:int, revoked:bool, revoked_at:float|null,
 revoked_revision:int|null, superseded_by:uuid|null}
```

Binding:

```
{binding_id(uuid4), grant_id, policy_revision, project_id, worktree_id, scope_fingerprint,
 host_id_hex, session_id_hex, revoked}
```

**Binding labels.** `host_id` and `session_id` must be non-empty, at most 256 characters, and free of control characters. If `SecretRedactor.redact_text(v) != v`, the writer raises `E_INPUT/secret_like_value`.

**`scope_fingerprint`:** sha256 of the canonical JSON of `{grant_id, granted_revision, principal, project_id, project_root, worktree_id, owner_scope, approved_sources, allowed_operations, expires_at}`.

**`mappings`:** keys are canonical UUIDs and values are objects. Writers preserve the map unchanged. Its schema belongs to 73-T06/T09.

**Redaction precheck:** before every write, if `sanitize_value(new_data).redaction_count != 0`, the writer raises `E_POLICY_REDACTION` and writes nothing.

**Loader views** decode stored fields back to the plan's names:
- **Grant view:** `project_root`, `owner_scope={"kind","id"}` and `approved_sources`.
- **Binding view:** exactly 9 keys: `binding_id`, `grant_id`, `policy_revision`, `project_id`, `worktree_id`, `scope_fingerprint`, `host_id`, `session_id`, `revoked`.

**`load_policy_readonly`** creates nothing. It checks in this order:

1. **Data root.**
   - `DataRootUnavailableError` gives `unavailable/data_root_unavailable`.
   - An absent root gives `missing`.
   - A root that is not a directory gives `invalid/not_directory`.
2. **Containment.** `PhysicalRoot(root).open_contained(POLICY_RELATIVE_PATH)`. A failure gives `symlink` or `path_escape`.
3. **Path components.** `lstat` each of `user`, `user/.rush` and the file.
   - Absent gives `missing`.
   - A symlink gives `symlink`.
   - A component that is not a directory gives `not_directory`.
   - A file that is not regular gives `not_regular_file`.
4. **Ownership (POSIX).** A `uid:{st_uid}` that differs from the principal gives `foreign_owner`.
5. **Open.** `os.open(O_RDONLY|O_NOFOLLOW)`, then `fstat`.
   - A `(st_dev, st_ino)` that differs from the `lstat` gives `file_changed`.
   - An `OSError` gives `unreadable`.
6. **Parse.** `json.loads(..., object_pairs_hook=<reject duplicates>)`. Failures give `duplicate_key`, `not_utf8` or `malformed_json`.
7. **Envelope.** The keys must be `{schema_version,version,data}`, `schema_version` must be `"1.0.0"`, and `version` must be an int of at least 1. Failures give `envelope_invalid` or `revision_invalid`.
8. **Data.** The keys must be `{schema_version,policy_revision,grants,bindings,mappings}`, `data.schema_version` must be the int 1, and `policy_revision` must be an int equal to `version`. Failures give `schema_version_unsupported`, `revision_mismatch`, `unknown_field` or `missing_field`.
9. **Records.**
   - Every record must have its exact keys and types, a map key equal to its id, hex fields that decode, and revisions within bounds.
   - The principal must match `^(uid:\d+|sid:S-1(-\d+)+)$`.
   - Failures give `record_invalid`, `dangling_binding` or `duplicate_active_grant`.
10. **Result.** Returns `{"state","reason","policy_path","policy_revision","content_sha256","grants","bindings","mappings"}`. When the state is not `ok`, the revision is 0, the maps are empty and the sha is `None`.

**Writer skeleton** (grant, revoke, register):

1. **Before any effect,** check, in order:
   - `consent is True`, else `E_CONSENT`.
   - Pure inputs, else `E_INPUT`, `E_PROJECT_NOT_REGISTERED`, or an error that the project root is not a directory:
     - the expected revision is a non-bool int ≥ 0;
     - sources are a non-`str` sequence that is non-empty, stripped, duplicate-free and contains no `"*"`;
     - operations are a non-empty, duplicate-free subset of `GRANT_OPERATIONS`;
     - `expires_at` is `None` or a finite, non-bool number greater than `_now()`.
2. **Inside `hold_policy_lock`.** An `OSError` here raises `E_LOCK`.
   1. Reload the policy strictly. An invalid policy raises `E_POLICY_INVALID`.
   2. A no-op returns without writing.
   3. If `expected != current`, raise `E_VERSION`.
   4. Set `revision = current + 1` and run the redaction precheck.
   5. Write with `CASMapTransaction(file_path=POLICY_RELATIVE_PATH, root_path=root).write(new, expected_version=current)`.
      - `CASConflictError` raises `E_VERSION`.
      - `StoreError`, `ContainmentError` or `ValueError` raises `E_POLICY_IO`.
      - A written snapshot that differs from the new data raises `E_POLICY_IO`.
3. **Per-writer behavior:**
   - **Grant** checks that the principal matches. It returns exactly `{grant_id, policy_revision, project_id, worktree_id, owner_scope:{kind,id}, approved_sources, allowed_operations}`.
   - **Revoke:** an unknown grant raises `E_GRANT_NOT_FOUND`, a foreign principal raises `E_PRINCIPAL`, and an already revoked grant is a no-op. Otherwise it revokes the grant and its bindings and returns `{grant_id, policy_revision, revoked: True, revoked_bindings: [sorted ids]}`.
   - **Register** needs an active, unexpired grant with the same principal, still mapped to the same `project_id` and the current `worktree_id`. Otherwise it raises `E_GRANT_INACTIVE` with reason `revoked`, `expired` or `relinked`. It returns the 9-key binding view.

**`resolve_memory_scope`** never raises. It runs these stages in order. The first stage that empties the candidate set supplies the reason.

| Stage | Check | Denial reason |
|---|---|---|
| 0 | Request types and operation name | `invalid_request` |
| 1 | Policy state (returned before any registry or project access) | `policy_missing`, or `policy_invalid` (also covers `unavailable`) |
| 2 | OS principal | `principal_unavailable` |
| 3 | Canonical root is a directory | `project_missing` |
| 4 | `read_registry_strict` | `project_registry_invalid` (corrupt or unreadable). A missing registry or entry sets `project_id=None` |
| 5 | Session binding, if given; candidates narrow to its grant | `binding_unknown`, `binding_revoked` |
| 6 | Related grants (root or `project_id` match) | `binding_scope_mismatch` with a binding; `project_not_registered` if `project_id is None`; otherwise `no_grant` |
| 7 | Principal | `principal_mismatch` |
| 8 | Project id and root | `relinked` |
| 9 | Worktree | `worktree_mismatch` |
| 10 | Revocation | `revoked` |
| 11 | Expiry (`_now() < expires_at`) | `expired` |
| 12 | Owner. Explicit: must equal the grant's owner. `None`: overlay owners excluded, then 0 distinct owners or more than 1 deny | `owner_not_granted` (no match, or 0 owners); `owner_required` (more than 1) |
| 13 | Operation | `operation_not_granted` |
| 14 | Sources (an empty request means all of the grant's sources) | `source_not_granted` |
| 15 | Binding fingerprint, project and worktree | `binding_stale` |

Success returns `access` set to `read` or `write`, and `reason="granted"`.

**Result keys** are the same on success and denial:

```
{"access","reason","operation","grant_id","grant_revision","policy_revision","project_id","worktree_id","project_root","owner_scope","approved_sources","allowed_operations","session_binding"}
```

On a denial, every grant-derived field is `None` or `[]`. `policy_revision` is the current revision, or 0.

**Lock order:** take the policy OS lock first, then the SQLite transaction. Never take a dashboard project lock while holding the policy lock.

## 4. Cross-task conflicts

1. **72-T01 and 72-T05 fixtures** must call `register_project(root, data_root=tmp_path/"user-data")` before the exact grant call. Consumers map memory operations to grant operations:

   | Memory operation | Grant operation |
   |---|---|
   | `ask`, `recall`, `related`, `explain` | `ask` |
   | `list` | `list` |
   | `expand` | `expand` |
   | `history`, and archive mode `historical` | `history` |
   | Any mutation | `write` |

   A continuation compares `policy_revision` across pages, so any policy change closes it.
2. **72-T05 overlay.** The overlay grant uses `owner_scope=user_overlay_owner_scope(data_root=...)` and includes `"overlay_read"`. Callers resolve it with that owner explicitly and `operation="overlay_read"`.
3. **72-T06 and §8.**
   - Mutators and `apply_import_records` run inside `hold_policy_lock` and re-resolve before commit.
   - The import owners prove that a grant revoked before commit means zero records are written (§8 `test_changed_capsule_policy_and_artifact_version_conflict`, and 73-T09).
   - POLICY proves the lock serializes writers (`test_policy_lock_serializes_revoke`).
4. **73-T02/BOOTSTRAP.**
   - The setup and connect callers enforce the config-mutation permission before calling `grant_memory_scope` or `register_memory_binding`.
   - Bootstrap reads through `load_policy_readonly`.
   - The lifecycle tests stay with BOOTSTRAP.
5. **73-T06/T09** add the `mappings` schema and its writers. POLICY only validates UUID keys and object values.
6. **Phase 70** keeps `agent_memory.json` as a sibling file with no collision. The lock id is `sha256("memory-policy:"…)`. Phases 71 and 75 have no conflicts.
7. **Every consumer** reads through `load_policy_readonly`, because stored fields are hex-encoded.

## 5. Test matrix (`tests/test_memory_authorization.py`, new)

- Each test imports `rush.memory.authorization` inside its body.
- Top-level imports are limited to existing code: `register_project`, `relink_project`, `OwnerScope`, `legacy_owner_scope`, `CASMapTransaction`.
- Tests use only `tmp_path` and `data_root=tmp_path/"user-data"`.
- Subprocess tests run `sys.executable` with `PYTHONPATH=<repo>/src`.
- Expected RED failure: in-process tests raise `ModuleNotFoundError: No module named 'rush.memory.authorization'`. Subprocess tests fail with an `AssertionError` on the child's return code or output.

| test id | fixture | action | assertion |
|---|---|---|---|
| `test_missing_policy_read_does_not_initialize_data_root` | unregistered root; absent data root; empty data root; `data_root=None` with HOME, XDG_DATA_HOME and LOCALAPPDATA patched to tmp | load and resolve(`ask`) in each case | load returns exactly `{"state":"missing","reason":"policy_missing","policy_revision":0,"content_sha256":None,"grants":{},"bindings":{},"mappings":{},"policy_path":...}`; resolve returns `denied`/`policy_missing` with no grant fields; tmp's sorted `rglob` is the same before and after; no `dashboard/` and no `root/.rush` |
| `test_explicit_setup_grant_and_cas_revision` | registered root | grant with `consent=False`; grant with `consent=True` at expected 0; second-owner grant at expected 0, then at 1; identical retry at stale 0; 5 resolves | no-consent gives `E_CONSENT` and creates no data root or lock dir; exact 7-key result with `policy_revision==1`; raw file has version 1 inner and outer, `"1.0.0"`, `data.schema_version==1`; stale grant gives `E_VERSION` with bytes unchanged; then rev 2; identical retry returns the same `grant_id`, rev stays 2, bytes unchanged; resolve gives `read`/`granted`, and `write` gives `access="write"`; sha and `mtime_ns` unchanged across resolves |
| `test_concurrent_grant_conflict_preserves_first` | registered root, initial grant at rev 1 | 2 subprocesses wait on a go-file, then grant different owners at expected 1 | exactly one ok at rev 2 and one `E_VERSION`; grants are {initial, winner} |
| `test_policy_lock_serializes_revoke` | grant at rev 1 | parent holds `hold_policy_lock`; child writes a marker, then revokes at expected 1; parent waits for the marker, sleeps 0.5 s | while the lock is held, `child.poll() is None` and bytes are unchanged; after release the child exits 0 and resolve gives `revoked` |
| `test_revocation_and_expiry_rechecked` | grant A; grant B expiring at `fake_now+60` with `_now` patched; binding on A | resolve; revoke without consent; revoke at a stale revision; revoke; revoke again; advance `_now`; grant with a past expiry | `E_CONSENT` and `E_VERSION`, bytes unchanged; revoke returns `revoked=True`, `revoked_bindings=[binding_id]`; A gives `revoked`; the binding gives `binding_revoked`; second revoke is a no-op; B gives `expired`; past expiry gives `E_INPUT` |
| `test_relink_and_foreign_worktree_rejected` | git repo with one commit plus `git worktree add`, both registered; grant on main; binding | resolve at the worktree; move main and `relink_project`; resolve at the new and old paths; rename the directory away, recreate and register it at the same path | worktree gives `no_grant`; moved path gives `relinked`, with or without the binding; old path gives `project_not_registered`; recreated dir gives `worktree_mismatch`; registering a binding on the relinked grant gives `E_GRANT_INACTIVE` |
| `test_forged_host_session_or_binding_cannot_grant` | projects A and B, each with a grant; binding on A | resolve with `session_binding="forged"`; A's binding at B; register with `consent=False`; register on an unknown grant; crafted file with a dangling binding; `inspect.signature(resolve_memory_scope)` | `binding_unknown` and `binding_scope_mismatch` with no grant fields; `E_CONSENT` and `E_GRANT_NOT_FOUND`, bytes unchanged; load gives `invalid/dangling_binding` and resolve gives `policy_invalid`; parameters are exactly the plan's (no host or session parameter) |
| `test_wrong_os_user_denied` (posix_only) | grant; `_current_os_principal` patched to `uid:<uid+1>`; crafted file whose grant principal is `uid:99999` | load, resolve, grant, revoke under the patch; resolve and revoke on the crafted file | under the patch: `invalid/foreign_owner`, `policy_invalid`, `E_POLICY_INVALID` with bytes unchanged; crafted file: `principal_mismatch` and `E_PRINCIPAL` |
| `test_owner_source_operation_filters` | alice: `agent`, sources a and b, operations ask and list; bob: `agent`, source c, all 5 operations | resolve matrix plus invalid grant inputs | owner `None` gives `owner_required`; alice ask with `[source-a]` gives `["source-a"]` and with `()` gives both; `[source-c]` gives `source_not_granted`; alice expand or write gives `operation_not_granted`; bob write gives `write`; carol gives `owner_not_granted`; `"bogus"` operation or a `str` sources value gives `invalid_request`; these grant inputs give `E_INPUT` with bytes unchanged: empty, duplicate or `"*"` sources, an unknown operation, `overlay_read` on a project owner, a bool expected revision; after bob is revoked, owner `None` resolves alice |
| `test_preferences_need_separate_approval` | project grant (`legacy_owner_scope`, 5 operations) | overlay resolves; separate overlay grant (`user_overlay_owner_scope`, `["overlay_read"]`, `["personal-preferences"]`); revoke the project grant, then the overlay grant | before the overlay grant: `owner_not_granted`, and `operation_not_granted` for project plus `overlay_read`; overlay grant has its own `grant_id` and gives `read`; owner `None` with `ask` still selects the project grant; overlay survives the project revoke, then gives `revoked`; `user_overlay_owner_scope(data_root=d) == OwnerScope("user", str((d/"user").resolve()))` |
| `test_binding_registration_requires_setup_consent` | grant at rev N | register with `consent=False`; register at N; retry at stale N; another session at stale N; resolve with the binding; superseding grant (same owner, new sources) | `E_CONSENT`, bytes unchanged; exact 9-key record (UUID, `policy_revision == N+1`, 64-hex fingerprint, `revoked=False`); file at rev N+1; retry returns the identical record with bytes unchanged; another session gives `E_VERSION`; resolve returns `session_binding == binding_id`; after the supersede, the old binding gives `binding_revoked` and the old grant has `superseded_by` |
| `test_policy_values_survive_secret_redactor` | root dir `desk-assistant-project-v2`; owner `agent` with id `"token:alice"`; source `"token:abc"` | grant, load, resolve; register with `host_id="token:abc"` | values round-trip exactly and the raw file contains no `REDACTED`; register gives `E_INPUT/secret_like_value` |
| `test_load_policy_rejects_invalid_file[duplicate_key, malformed_json, not_utf8, bool_version, revision_mismatch, schema_version_unsupported, unknown_field, unknown_grant_field, bool_policy_revision, duplicate_active_grant, symlink_file, symlink_user_dir, directory_at_file]` (symlink cases posix_only) | crafted raw files | load, resolve, grant | `state="invalid"` with that exact reason; `policy_invalid`; `E_POLICY_INVALID`, with the bytes or symlink target unchanged |
| `test_module_import_is_cycle_free` | fresh subprocess | import `rush.memory.authorization`; list `sys.modules` | none of `rush.tools*`, `rush.dashboard*`, `rush.workflows*`, `rush.memory.store`, `rush.memory.retrieval` |
| `test_t01_fixture_call_contract` | registered root | the exact 72-T01 grant and resolve calls; `inspect.signature` of the 5 functions | exactly the 13 result keys and values (`read`, `granted`, resolved IDs); signatures equal the plan's |
| `test_os_principal_posix` (posix_only); `test_os_principal_windows_sid` (windows_only) | none | `_current_os_principal()` | POSIX: `f"uid:{os.getuid()}"`, equal to the grant's principal. Windows: matches `^sid:S-1(-\d+)+$` |

## 6. Worker packages

The packages are copied onto card T015 (RED) and card T016 (implementation) in `state.yaml`. They replace the scopes set at prep time.

## Coverage on macOS

The Windows SID branch is exercised only by `test_os_principal_windows_sid`, which carries the `windows_only` marker. `tests/conftest.py:64-80` deselects `windows_only` on non-Windows hosts, and the Windows CI job collects it. The T001 baseline run on this Mac recorded `windows_only: 13 deselected (not Windows)`.
