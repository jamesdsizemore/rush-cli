# Deep Repository Review — 2026-09-06

Scope: whole repo (738 Python files, ~83.5k LOC across `src/` + `tests/`). Produced via
independent manual pass (this section) plus a parallel multi-agent `/code-review` run at
high effort (appended below once it completes).

## Repo shape

- 432 files / 1928 symbols under `src/`, 306 test files / 1474 symbols under `tests/`.
- Largest files: `src/rush/cli.py` (2992 lines — flat Click command-registration table,
  ~120 thin commands, not itself a correctness risk since each command just extracts
  options and delegates to `src/rush/tools/*`), `src/rush/catalog.py` (1852 lines),
  `src/rush/release/provenance_policy.py` (859 lines).
- Central hubs (by fan-in): `run_subprocess` (172 callers), `resolve_binary` (137),
  `Engine` base class (122), `elapsed_ms`/`now_ms`/`error_result`/`skipped_result`
  (runtime/result_helpers.py).
- Historical context: `phase50-adversarial-review.md` rejected an earlier plan for (among
  other things) fake SLSA-L3 claims; commit history (phases 51–60) shows a completed
  remediation program ending at `c4e140f`. Spot-checked that the SLSA/provenance claim is
  now backed by real fail-closed DSSE signature verification (see below) — that historical
  finding reads as resolved, not live.

## Verified findings (independently confirmed against current source)

### 1. SVG "security sanitizer" is a bypassable regex blocklist (Medium-High, security)
`src/rush/tools/media_opt.py` — `_sanitize_svg_content()` / `MediaOptTool.run()`.

The tool's own docstring calls this a "SVG security sanitizer" and, when given
`--allow-artifact-write`, it **rewrites the file on disk** after stripping only three
regex patterns:
- `_SCRIPT_TAG_PATTERN`: `<script>...</script>` / self-closing `<script/>`
- `_EVENT_HANDLER_PATTERN`: `\bon[a-z]+\s*=\s*['"][^'"]*['"]`
- `_JS_URI_PATTERN`: `(href|src|xlink:href)\s*=\s*['"]\s*javascript:...['"]`

This is a blocklist over raw text, not a parsed/allowlist-based sanitizer, and known SVG
XSS vectors bypass it, e.g.:
- SMIL attribute injection: `<animate attributeName="onload" to="alert(1)" />` never
  contains the literal text `on...=`, so the event-handler regex never matches it, yet it
  sets a live `onload` handler at render time.
- `data:` URI script vectors (`href="data:image/svg+xml;base64,..."`,
  `xlink:href="data:text/html,<script>..."`) — only `javascript:` is checked, not `data:`.
- `<foreignObject>`/`<use>`/`<iframe>` embedding, and legacy `vbscript:`.

Rewriting the file in place means a "sanitized" artifact can still carry a live payload —
worse than leaving it flagged, because the finding disappears (`sanitized_svg_count`
increments, no more `svg-script-injection` finding) while the risk persists.
**Fix direction:** either drop the auto-fix/write path and keep this purely a detector, or
sanitize through a real XML parser with an attribute/element allowlist (e.g. mirror
DOMPurify's SVG profile) instead of a fixed regex set.

### 2. `ExecutionPermissions` construction duplicated in 30 tool files (DRY / simplification)
`src/rush/cli_support/options.py::_extract_permissions()` already exists and is used
correctly by the CLI layer (`cli.py`, `cli_support/catalog_commands.py`). But 30 files
under `src/rush/tools/` re-implement the identical 8-line
`ExecutionPermissions(network=..., download=..., cache_write=..., build=..., slow=...,
artifact_write=..., browser=...)` construction inline inside their own `__call__`:
`pbt.py, iam_audit.py, benchmark.py, tdd_guard.py, mutation.py, license_matrix.py,
security.py, ai_eval.py, media_opt.py, coverage.py, dead_asset.py, sbom.py, codeql.py,
cold_start.py, prompt_eval.py, semantic_drift.py, offline_runner.py, pr_synthesize.py,
commit_msg.py, tui_diff.py, attest.py, load.py, fuzz.py, contract.py, quality.py,
error_catalog.py, provenance_ai.py, snapshot.py, mem_profile.py, flaky.py`.
~240 duplicated lines total. Verified via `grep -rl "permissions = ExecutionPermissions("
src/rush/tools` (30 hits) vs `grep -rl "_extract_permissions" src/rush` (CLI layer only).
**Fix direction:** move `_extract_permissions` (or an equivalent) somewhere importable
from `tools/`, and have each `__call__` delegate to it instead of rebuilding the dataclass.

## Checked and found solid (no finding — noted so this isn't re-litigated)

- `run_subprocess` (`src/rush/runtime/subprocesses.py`): `shell=False` always, list-only
  argv, `stdin=DEVNULL`, binary resolution restricted to venv Scripts/bin + PATH (cannot
  be pointed at an arbitrary path via project config) — no shell-injection surface found.
- `sanitize_value`/`SecretRedactor` (`src/rush/safety/redactor.py`): recursive, handles
  circular references, sanitizes dict keys too, fails closed on unsupported types.
- `ProvenancePolicyVerifier` (`src/rush/release/provenance_policy.py`): real DSSE envelope
  + in-toto/SLSA-v1 statement verification, fail-closed when `trusted_roots` or
  `allowed_signers` is empty, `allow_unsigned` defaults to `False`. This is what the
  now-resolved phase50 "fraudulent SLSA claim" finding was about — current code backs the
  claim with actual signature verification rather than an unsigned local JSON stamp.
- `normalize_findings`/`finding_fingerprint` (`src/rush/runtime/result_helpers.py`): bounds
  processing to 10k records, redacts messages, deterministic sort/fingerprint.
- Dashboard HTTP server (`src/rush/dashboard/server.py`): binds loopback only, checks
  `Host`/`Origin` headers, requires a random per-launch token. Minor: token comparison
  (`token != self.auth_token`) is not constant-time (`secrets.compare_digest` would be
  more defensible), but exposure is local-loopback only — low severity, worth a one-line
  fix, not flagged as a real vulnerability given the threat model.

## Multi-agent `/code-review` findings (high effort, whole-repo) — independently re-verified

The parallel fork returned 10 findings claiming "all source-verified." Per this session's
own verification standard, a subagent's claim of "verified" is not treated as verification
— every one of the 10 was independently re-checked against current source below, each with
the exact line(s) read and the concrete trigger confirmed. All 10 hold. Ranked
worst-first.

### 3a. Governance file protection has two independent bypasses via a bare `./` prefix (Critical)

**`src/rush/safety/guard.py:25-38`** — `AgentSafetyGuard.is_file_protected()`: the `Path`
branch resolves relative to `repo_root` before comparing; the `str` branch does not — it
only does `target_path.replace("\\", "/")` and checks that raw string against
`PROTECTED_GOVERNANCE_FILES`. `guard_check_path` (`cli.py:1378`) receives `file_path` as a
plain `str` from Click (no `path_type=Path`), so `rush guard check-path ./CLAUDE.md` takes
the unnormalized string branch: `'./CLAUDE.md' != 'CLAUDE.md'` → reports `[ALLOWED]` for a
file the tool exists specifically to protect.

**`src/rush/patch/diff_parser.py:56-67`** — `UnifiedDiffParser.parse_patch()`: the
traversal check resolves `(repo_root / target_path).resolve()` and correctly passes for
`./CLAUDE.md`, but the very next line checks `if target_path in GOVERNANCE_BLOCKED_FILES`
against the same *unresolved* string. A diff with header `--- a/./CLAUDE.md` /
`+++ b/./CLAUDE.md` passes both checks and `PatchApplier` applies it, overwriting
`CLAUDE.md` — the exact file this mechanism claims to make immutable.

Both are the same root cause (compare a raw string instead of a normalized path) in two
independent enforcement points. Fix: normalize (`Path(x).as_posix()` stripped of leading
`./`, or resolve-and-compare like the `Path` branch already does) before the membership
test, in both places.

### 3b. `rm -fr` (flag order swapped) bypasses the destructive-command interceptor (Critical)

**`src/rush/safety/interceptor.py:25`** — the regex
`\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+[\/\.]` requires an `r` to appear before an `f` in the
flag cluster. `rm -rf /path` matches; `rm -fr /path` — equally common, byte-for-byte as
destructive — does not, so `inspect_command("rm -fr /some/path")` returns `(True, None)`:
`[SAFE] Command authorized`. Fix: match flag characters as an unordered set
(`-[a-zA-Z]*` containing both `r` and `f` in any order, e.g. two lookaheads) rather than a
fixed order.

### 3c. Plugin "descriptor" secret channel hangs the child forever (Critical)

**`src/rush/plugins/secret_channels.py:112-123`** creates a pipe and hands the child the
*read* end via `pass_fds`, returning `parent_fd=write_fd` in the `SecretDeliveryContext`.
Confirmed by full-text search: `parent_fd`, `write_fd`, `os.write`, and `os.close` do not
appear anywhere in **`src/rush/plugins/executor.py`** (the only consumer of this context) —
`pass_fds` is used to launch the child (line 233/250), but `resolved_secrets` is never
serialized and written to `write_fd`, and the fd is never closed. A plugin declaring the
`descriptor` channel reads its `RUSH_SECRET_FD` and blocks on `read()` forever: no data
ever arrives, and EOF never comes because the write end stays open in the parent. This is
the entire descriptor secret-delivery feature being non-functional, not an edge case.

### 3d. Provider egress redirect protection is disabled process-wide by an unrelated global monkeypatch (High)

**`src/rush/providers/base.py:139-142`** — `safe_provider_post()`'s cross-origin redirect
allowlist (`SafeRedirectHandler`) is skipped whenever
`urllib.request.urlopen is not _ORIGINAL_URLOPEN` is true, falling back to a bare
`urlopen(req, timeout=timeout)` call with zero redirect enforcement. This is a global
mutable-state check, not scoped to the current request or caller: once anything in the
process — a test fixture, an imported plugin, any third-party library — monkeypatches
`urllib.request.urlopen` and doesn't restore it, every subsequent `safe_provider_post` call
for the rest of the process permanently loses cross-origin-redirect protection with no
warning.

### 3e. `PatchApplier` rollback silently no-ops in a fresh/commit-less repo, leaving a syntax-broken patch applied on disk (High)

**`src/rush/patch/applier.py:56-90`** — `pre_patch_head` stays `None` whenever
`git rev-parse HEAD` fails (e.g. a repo with zero commits). `_rollback()`'s first branch
(`git reset --hard` + `git clean -fd`) is gated on `if target_commit:` — with `None` it's
skipped entirely, and only stale-worktree cleanup runs. So: `git apply` mutates the working
tree, the post-patch AST syntax check fails, `_rollback(target_dir, None)` is called and
does nothing, and `apply_patch_to_dir` returns `False, "Post-patch syntax check failed..."`
— a caller reading that `False` return has no reason to believe the target directory was
left mutated, but it was.

### 3f. Pre-commit hook checks working-tree content, not the staged git index it's meant to gate (High)

**`src/rush/hook/staged_scanner.py:16-38`** returns on-disk `Path` objects for files listed
by `git diff --cached --name-only`. **`hook_run_cmd`** (`cli.py:1713-1752`) then runs
`FastIncrementalAstLinter.lint_staged_python`, `TrojanSourceDetector.inspect_file`, and
`ConflictMarkerGuard.inspect_file` — all three call `Path.read_text()` on those working-tree
paths (confirmed: `ast_linter.py:20`, `trojan_source.py:31`, `conflict_guard.py:23`), never
`git show :path` against the index. Sequence that defeats the guard: `git add
malicious.py` (contains a bidi trojan-source override), then edit the working copy to
strip the dangerous bytes *without re-staging* — `rush hook run` reads the now-clean disk
file and passes, but `git commit` commits the still-dangerous staged index content. The
guard validates the wrong artifact.

### 3g. AST 3-way merge silently drops any class (or other non-function top-level node) added only by the other side (Medium)

**`src/rush/tools/swarm_merge.py:10-59`** — `merged_body` is seeded only from
`ours_tree.body` nodes that are *not* `FunctionDef`/`AsyncFunctionDef` (line 39-41); the
per-name reconciliation loop below it only iterates `all_func_names` (function names
only). If "ours" adds `def foo()` and "theirs" independently adds `class Bar:` at module
level, the merge reports `success: True` with zero conflicts, but `class Bar` is not in
`ours_tree.body`'s non-function nodes (it only exists in `theirs_tree`) and is never a
"function name," so it is silently absent from `merged_code`. `continuity/coordination.py`'s
`preview_merge` surfaces this result to callers as a clean, conflict-free merge.

### 3h. `rush attest --verify`'s builder-identity check is a no-op by default (Medium)

**`src/rush/tools/attest.py:139-141`** — when `--allowed-builders` isn't passed and
`rush.toml` doesn't configure `allowed_builders`, the policy falls back to
`(builder_id,)` where `builder_id` defaults to the hardcoded constant
`"https://rush-cli.org/builder/v1"` (the same value every `rush attest` invocation writes
into its own statements, visible at `attest.py:37`). Any forged envelope that copies this
well-known public string as its `builderId` trivially satisfies the check. This doesn't
defeat the envelope's actual signature/trusted-root verification (still fail-closed per
§"Checked and found solid" above), but the builder-identity check specifically provides no
assurance until an operator explicitly configures `allowed_builders`, with nothing in the
tool's output flagging that it's running on the unconfigured default.

## Severity summary

| # | Area | Severity | Confirmed |
|---|------|----------|-----------|
| 1 | SVG sanitizer bypass (media_opt.py) | High (security) | mine |
| 3a | Governance file protection, 2 bypasses | Critical | fork, re-verified |
| 3b | `rm -fr` interceptor bypass | Critical | fork, re-verified |
| 3c | Descriptor secret channel hang | Critical | fork, re-verified |
| 3d | Redirect protection disabled by global monkeypatch | High | fork, re-verified |
| 3e | Patch rollback no-op, corrupted worktree left in place | High | fork, re-verified |
| 3f | Pre-commit hook checks wrong content (working tree vs. index) | High | fork, re-verified |
| 3g | 3-way AST merge drops classes silently | Medium | fork, re-verified |
| 3h | Attest builder-ID check no-op by default | Medium | fork, re-verified |
| 2 | `ExecutionPermissions` duplicated across 30 files | Low (simplification) | mine |

All 10 fork findings and both independent findings were checked against the file's actual
current content (not the subagent's paraphrase, not memory) before being written above.

## Installation gap: `rush` not usable after following the README

Hit live during this review: after installing per the README, `rush` was not runnable
from a plain terminal. Root cause confirmed on this machine — `.venv/bin/rush` existed
(the package built fine into the project's `uv`-managed venv), but nothing put it on
`$PATH`: `$VIRTUAL_ENV` was empty and `.venv/bin` was absent from `$PATH`. The README does
not state that the venv must be activated (or the tool installed globally) before `rush`
works as a bare terminal command — this is not implicit from the current install
instructions. Not fixed in the README per instruction; documented here only.

**Working fix, verified on this machine:**

```bash
uv tool install --editable .
```

Confirmed: installs `rush-cli` and 51 dependencies, links one executable (`rush`) into
`~/.local/bin/rush`. After a fresh-shell `hash -r`, `which rush` resolves to
`~/.local/bin/rush` and `rush --version` prints `0.3.0` with no venv activation needed.
This is the recommended fix for "I installed this but can't run `rush` in my terminal" —
it makes `rush` a normal global command, editable (source edits in this repo take effect
immediately, no reinstall).

**Alternatives (not installed here, for reference):**

- Per-terminal-session, without a global install: `source .venv/bin/activate`, then `rush
  ...` works for that shell only; must be re-run every new terminal/tab.
- One-off invocation with no activation at all: `.venv/bin/rush ...` (full/relative path
  to the venv's own executable).

`~/.local/bin` must itself be on `$PATH` for the global-install fix to work from any
directory; on this machine it already was. If a user's `$PATH` doesn't include
`~/.local/bin`, `uv tool install` alone will not make `rush` runnable — they'd also need
to add `~/.local/bin` to `$PATH` (`uv tool update-shell` handles this automatically on
most shells).
