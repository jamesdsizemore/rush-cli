# T014: Design gate for 72-T09 (goal-judge report, recorded verbatim)

The text below the line is the goal-judge's T014 report, copied unchanged.

## PM re-checks (run on 07775f1)

1. **The pinned digests match.** `shasum -a 256` gives `8c2706455d197203a8f20a94989249591f1ee3c8fddb3ac8c7d5358cd6af5b1c` for `docs/phase-plans/MC13.md` and `7eab4b7525eb8c999445c30345907422060410acde0f77bf671b0f51b11b1263` for `docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md`.
2. **CLI reference coverage.** The Click registry has 22 `rush memory` leaves. 20 of them do not appear literally in `docs/reference/cli-reference.md`.

verified-by:
- `shasum -a 256` on both files;
- a Click walk of `rush.cli.cli.commands['memory']`, with each leaf checked by substring against the reference doc, which printed `22 20`.

**Owner decisions pending:** OD1 (release-artifact build), OD2 (live model usage for the two-agent lanes) and OD3 (push for the Linux and Windows CI lanes).

**Not re-run by the PM:** the rest of the report. The T050 RED author re-checks the code map at HEAD (stop_if).

---

## (A) Note body for notes/T014-design-gate-72-t09.md

# T014: Design gate for 72-T09, truthful docs and live acceptance

Worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`. Source bytes are those of `07775f1`. HEAD has since moved to `17f7645`, a commit that adds only board docs; `src`/`scripts`/`tests` are unchanged. The tree was clean when read. I did not edit, run tests, install anything or run graft, because the graft tools were not loadable in this session. The code map comes from `rtk grep`/`sed` and live Click/registry introspection through `.venv/bin/python`.

### 1. Testable behavior

1. `docs/reports/phase-72-memory-acceptance.md` holds exactly one fenced block, ```` ```rush-phase72-acceptance-v1 ````. It is JSON whose `schema` is `"rush-phase72-acceptance/v1"`, and it has the exact top-level keys from §3.1. Prose sections mirror the block. The block is the source the test checks.
2. The ledger has exactly 9 rows, and each requirement string equals a left cell of the live plan §4 table (L116–124, parsed at test time and not hardcoded).
   - A `pass` row cites test node IDs that exist, unit commands recorded with exit 0 and `N passed` with no `skipped`, and lanes that are all `pass`.
   - An `open` row has exactly one single-line blocker.
3. The PAS case list equals the 7 names parsed from the plan §8 "Required cases are …" sentence. Each name is defined in `tests/test_phase72_portable_memory_policy.py` (AST check). A `L-pas-import-walkthrough` lane exists.
4. The frozen source identity is real and stays verifiable for good:
   - `frozen.commit` is a commit and an ancestor of HEAD.
   - `frozen.product_digest` equals the digest recomputed from that commit's blobs (algorithm in §3.2).
   - Every `pass` lane's `product_digest` equals `frozen.product_digest`. Any other lane is `open` or `superseded` and gives a reason.
5. Interface matrix:
   - It covers the required operation set (§3.1).
   - Each CLI cell resolves in the Click registry (`tests/test_phase70_t25.py::_resolve_citation`, loaded through importlib).
   - Each MCP cell's operation is in `typing.get_args(rush.tools.memory.MemoryOperation)`.
   - Each TUI key appears in the `docs/user-guide/interactive-tui.md` §5 table.
   - Each dashboard control string appears in `src/rush/dashboard/application.js` (or `panels.js` if it exists).
6. Claims:
   - Every claim's `quote` is an exact substring of its doc's current text.
   - `label` is one of {proposed, implemented, integrated, evaluated, live-verified, superseded}. (verified-by: grep matched plan L421 for the label vocabulary)
   - `revision` resolves to a commit.
   - A `live-verified` claim (label from plan L421; verified-by: grep) cites only `pass` lanes. An `integrated` or `evaluated` claim cites resolvable test IDs or lanes.
   - A `superseded` claim has `explanation` and `superseded_by` set.
   - Each of the 6 plan-§3 docs has at least 1 claim.
   - The three F23 contradictions are labeled `superseded`:
     - phase-63 L7, "Implementation status: not started for Phase 63";
     - phase-63 §11 MC15, "Benefit: confirmed" (verified-by: grep matched phase-63 plan line 510);
     - the MC13 line "all five named episodes ran for real".
7. Historical receipts stay intact and carry a revision label.
   - `MC13.md` and the phase-63 plan start with `Current status: `, and their `historical_body_digest` equals the pinned digests: MC13 `8c2706455d197203a8f20a94989249591f1ee3c8fddb3ac8c7d5358cd6af5b1c`; phase-63 `7eab4b7525eb8c999445c30345907422060410acde0f77bf671b0f51b11b1263`. These are their current full-file sha256 values.
   - Their coverage entries switch to `authority: historical`, `superseded: true` and `immutable_body_sha256` equal to the pinned value. From then on the existing sync_docs mechanism keeps the bodies immutable.
   - Each status paragraph contains a commit-ish that resolves and the link `../reports/phase-72-memory-acceptance.md`.
8. Lanes:
   - The lane IDs include the exact required set (§4). Extra IDs are allowed only with the prefix `T041-`.
   - A `pass` lane has `blocker: null` and non-empty `commands`/`actions`, `observed` and `route`/`executable`.
   - An `open` lane has one non-empty blocker line with no newline.
   - A `superseded` lane has a `superseded_reason`.
   - Each entry in `evidence_files` has a sha256 that matches the file on disk.
9. Every fenced-code line in the 3 user and reference docs that starts with `rush memory` (or contains `rush_memory`) appears in `examples[]`, recorded with its executed command, exit code and observed result.
10. Every registered `rush memory <sub>` leaf in Click (22 today, more after T06/CODEC) appears literally in `docs/reference/cli-reference.md`. Today 20 are missing.
11. `plan_vs_code[]`: every `path::Name` or `path::Class.method` symbol resolves by an AST parse of `git show <frozen.commit>:<path>`.
12. Local integration (`test_t09_integrated_route_and_scope`) runs the scenario in §3.3 through public routes. The observed dictionary equals `report.integration` exactly.
13. The report contains no secrets:
    - no `token=`;
    - no `"capability"` value;
    - no 43-char `[A-Za-z0-9_-]` run (that is, `token_urlsafe(32)`) containing an uppercase letter and a digit;
    - no `http://127.0.0.1:` URL with a query string.
14. Unit commands and gates:
    - The set of `unit_commands[].command` values equals the set of pytest commands parsed from plan §5 72-T01..T08 plus §8 L471. Each has exit 0, and its `result` matches `^\d+ passed` with no `skipped`.
    - The `gates[]` commands equal the plan L437 commands.
    - The `python --version` result starts with `Python 3.12`.
    - The full-suite entry records 0 skipped, and its `failures` are a subset of the T001 baseline pair: `tests/test_phase70_t28f_review1.py::test_plus_minus_expand_and_collapse_detail_in_git_and_memory` and `tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts`.

### 2. Doc and code map

**Docs, exactly as listed in plan §3 L98–111** (each exists at `07775f1` unless noted):

| Doc | Coverage owner / authority now | T09 action |
|---|---|---|
| `docs/user-guide/working-with-ai-agents.md` | user-guides / current | Memory section: consent, the personal overlay, all-subject search, explain, correct/reject/supersede, denied/stale/recovery states, PAS/capsule review. Reconcile L85 and L105 ("reads need a non-empty `session_allowlist`") with v2 owner_scope/sources/grant. It must keep passing `test_phase70_t25::test_doc_reconciliation` (`_CURSOR_RE` product-name check, citations) and `test_phase70_t1` (file exists). |
| `docs/user-guide/interactive-tui.md` | user-guides / current | Rewrite the §5 Memory key table to match T07's actual keys (history, explain, correct, import review). Keys only after they have been executed. |
| `docs/reference/cli-reference.md` | reference / current | Document every `rush memory` leaf literally, plus v2/history/explain/capsule examples. It must keep `rush help`, `--help-all`, the category names and the everyday set (`test_help_docs_document_the_new_surface`). |
| `docs/architecture/rush-epistemic-memory-and-agent-substrate.md` | fallback / planned | Rewrite only its L3 `Current status:` paragraph. Label §§1–5 (L9, L20, L39, L56–95, L107, L119) as proposed, or as implemented at the frozen commit with evidence. Remove the stale "Phase 63 implements the connected memory outcomes" and name Phase 72–75 and the memory-program contract. The body stays as it is. It is not a receipt, so no pin applies. |
| `docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md` | plans-templates-agents / planned | Add a leading `Current status:` paragraph only, and keep the body byte-identical. Coverage moves to historical + superseded. |
| `docs/phase-plans/MC13.md` | plans-templates-agents / current | Same treatment. The label says the MC13 episodes are scripted component evidence (F20), that this is a historical receipt at `55e994b`, and that the full-suite line "1826 passed, 5 skipped" is historical. |
| `docs/reports/phase-72-memory-acceptance.md` | historical / historical (missing now) | New receipt, following the precedent of `phase-70-implementation-evidence.md`. Every writer refreshes `sha256` and `immutable_body_sha256` and appends an evidence line naming the previous sha. |
| `docs/reports/phase-64-66-documentation-coverage.md` | coverage report | Receipts for every doc changed or added. It also refreshes the `contracts` block from `collect_runtime_contracts(root)`, which absorbs the CLI/MCP drift from T06/CODEC/T07/T08/EVALUATOR. The payload may be re-dumped with `json.dumps(payload, separators=(",",":"))` (key order kept), because the existing serialization is mixed and the checker only parses it. |

**Code consumed (read-only):**
- `scripts/sync_docs.py`: `BLOCK_RE:28`, `REPORT_PATH:27`, `document_digest:56`, `historical_body_digest:60`, `documentation_owner:70`, `_cli_contracts:279`, `collect_runtime_contracts:437`, `read_coverage_receipt:530`, `check_docs`.
  - Callers: `tests/test_sync_docs.py` (fixture roots only) and `.github/workflows/ci.yml:107`. No full-suite test runs `--check` on the real repo.
- `tests/test_phase70_t25.py`: `_extract_rush_citations`, `_resolve_citation` (used at :580 and :679), `_CURSOR_RE`.
- `src/rush/tools/memory.py`: `MemoryOperation:72`, `MemoryTool.run:401`.
- `src/rush/setup/provision.py::default_data_root:122`, which uses `Path.home()` on Darwin, so `HOME` isolates it.
- `src/rush/dashboard/application.js::renderMemorySection:1230`.
- Created by earlier units:
  - 73-T02/POLICY: `authorization.grant_memory_scope`, `revoke_memory_scope`, `resolve_memory_scope`, `load_policy_readonly`.
  - 72-T01: `retrieval.evaluate_artifact_visibility`.
  - 72-T06: `TypedArtifactStore.apply_import_records`.
  - 73-T09/CODEC: `src/rush/memory/capsule.py` and the `rush memory capsule` CLI.
  - 72-T05: user overlay at `default_data_root()/user`.
- **Missing from the packet:** the coverage report, `tests/test_phase70_t25.py` (it guards 3 T09 docs), and the runtime `contracts` block (drift from earlier units).

**Earlier-unit outputs T09 depends on:**
- 73-T02/POLICY: grants and revocation.
- 72-T01: visibility and reason codes.
- 72-T02: exact version/digest expansion and cursor.
- 72-T03: contrary evidence for explain.
- 72-T04: owner-isolated maintenance.
- 72-T05: the consented personal overlay.
- 72-T06: v2 requests, history/explain, correction kinds and the atomic import seam.
- 73-T09/CODEC: the capsule/PAS route.
- 72-T07: CLI/TUI/dashboard search, correction and explanation, plus T041 evidence.
- 75-T02/EVALUATOR and 72-T08: the hybrid eval lane, its T048 record and `docs/reports/phase-72-memory-eval/`.

### 3. Design

**3.1 Report schema.** Top-level keys, exactly:

`schema, frozen, ledger, pas_cases, claims, interfaces, examples, lanes, unit_commands, gates, integration, plan_vs_code`

- `frozen`:
  `{commit, product_digest, product_paths:["src","scripts","pyproject.toml","uv.lock"], python, platform, executables:[{route, path, sha256, version}], clients:[{name, version}]}`
- `ledger[]`:
  `{requirement, owner, status:"pass"|"open", tests[], commands[], lanes[], blocker}`
  Fixed row-to-lane mapping:
  - rows 1–4: tests only;
  - row 5 (F15/B05/E06/E25): `L-two-project-personal-overlay`, `L-e06-e25-rejection-reversal`, `L-two-agent-ab`;
  - row 6 (A02/AP01/AP07 admin): `L-installed-cli`, `L-stdio-mcp`;
  - row 7 (F18–F19/E19): `L-pty-keyboard`, `L-browser-desktop-1280x800`, `L-browser-mobile-390x844`, `L-installed-cli`, `L-stdio-mcp`;
  - row 8 (R02/R08): `L-hybrid-eval`;
  - row 9 (F23/AP08): every required lane.
- `pas_cases[]`: `{test, file, status, blocker}`.
- `claims[]`: `{doc, quote, label, revision, evidence[], explanation, superseded_by}`.
- `interfaces[]`: `{operation, cli, mcp, tui, dashboard, label}`. The required operations are:
  `list, query, expand, history, explain, edit-correct, edit-reject, edit-supersede, archive, restore, delete, promote, link, maintain, capsule-preview, capsule-import`.
  If an interface genuinely lacks an operation, its cell is `null`, and the row label names the reason.
- `examples[]`: `{doc, example, executed_command, exit, observed}`.
- `lanes[]`:
  `{id, status:"pass"|"open"|"superseded", observed_commit, product_digest, route, executable, executable_sha256, version, platform, commands[], actions[], observed[], identities[] (redacted id@version), evidence_files[{path, sha256}], blocker, superseded_reason}`
- `unit_commands[]`: `{unit, command, exit, result}`.
- `gates[]`: `{command, exit, result, failures[]}`.
- `integration`: the dictionary from §3.3.
- `plan_vs_code[]`: `{requirement, symbols[]}`.

Prose sections, in order:
1. Frozen source and environment
2. Requirement ledger
3. PAS cases
4. Documentation truth labels
5. Interface matrix
6. Executed doc examples
7. Local integration
8. Live lanes
9. Unit commands on frozen bytes
10. Full gates
11. Open lanes and exact blockers
12. Earlier-unit observations (T041/T048, revision-labeled)

**3.2 Product digest**, used by T041, T048, T051, T052 and the test:

```
sha256 over sorted(paths) of  path + "\0" + sha256(bytes).hexdigest() + "\n"
```

- On a working tree, paths come from `git ls-files -z --cached --others --exclude-standard -- src scripts pyproject.toml uv.lock` (existing files only).
- At a commit, paths come from `git ls-tree -r -z --name-only <c> -- …` and bytes from `git cat-file --batch`.
- There is no `.gitattributes`, so the two methods agree on a clean tree. 527 files today.

The test verifies the digest against the commit, not the working tree. Later phases can change `src` without breaking it.

**3.3 Integration test scenario.** It runs through public routes in `tmp_path` with `HOME` monkeypatched, two git projects P1 and P2, and real grants through 73-T02 functions (no hand-written policy files).

1. Agent binding A writes `domain_knowledge` r1, which becomes v1.
2. B's all-subject v2 query returns r1@1 as an exact ref, and B's expansion digest matches.
3. A corrects with `edit` `correction.kind="correct"`, which creates v2. B's query returns v2, and B's ordinary `expand(version=1)` returns `E_VERSION`.
4. The personal-overlay key, written with consent, is visible from both P1 and P2. The private P1 and P2 rows are absent from each other's views, including counts and IDs.
5. After `revoke_memory_scope` for B, B's next query and expansion return the denial code with no content.
6. E06/E25 component case: reject, then an unrelated lookalike stays allowed, then a supersede reversal is honored.
7. PAS session import with a forged `verified:true` (verified-by: plan L471 forged-verification case): the record stays imported and pending, never STATED or verified. Confirming the constraint does not mark the source tests verified.

Observed dictionary keys:

`a_write_version, b_read_version, corrected_version, b_cached_v1_code, p1_sees_p2_private, p2_sees_p1_private, personal_key_visible_in, revoked_code, pas_forged_trust, pas_constraint_state_before_confirm, pas_source_tests_verified_after_confirm, e06_unrelated_allowed, e25_reversal_honored`

The test asserts `report["integration"] == observed`. Error codes follow plan §2.1 #3. If the landed T02/T06 code differs, the test author returns to the PM.

**3.4 Revision labels.** Receipts are never rewritten. Only a leading `Current status:` paragraph is added, and the sync_docs historical+superseded flags then enforce immutability. Superseded verdicts are explained in that paragraph and in `claims[]`. The architecture doc keeps authority planned, with only its status paragraph edited.

### 4. Live lanes

All lanes run on frozen bytes, from a single Python driver (heredoc, no file) holding a `tempfile.TemporaryDirectory()`. The environment is `HOME=<tmp>/home`, `PYTHONPATH` unset, `TERM=xterm-256color`, `LANG=en_US.UTF-8`, with projects `<tmp>/proj ü one` and `<tmp>/proj two` (git init and commit). Grants go only through the public consent route that the docs record.

Required lane IDs, exactly:

`L-installed-cli, L-installed-artifact, L-stdio-mcp, L-pty-keyboard, L-browser-desktop-1280x800, L-browser-mobile-390x844, L-two-agent-ab, L-e06-e25-rejection-reversal, L-two-project-personal-overlay, L-revoked-grant, L-pas-import-walkthrough, L-hybrid-eval, L-native-linux, L-native-windows`

- **L-installed-cli:** `.venv/bin/rush`, a console-script entry for the editable install pointing at this worktree. Record sha256 and `rush --version` (`0.3.0` today). Execute every `examples[]` command verbatim: write, list, query/search across all seven subjects, expand, history, explain, correct, reject, supersede, archive/restore, and capsule preview/import.
- **L-installed-artifact:** the release-route frozen binary (PyInstaller, Phase 70 precedent). PyInstaller is absent from `.venv`, and D4 forbids another env. Until OD1 is answered: open, blocker "release artifact not buildable: PyInstaller absent from the single phase-72 .venv and D4 forbids another environment".
- **L-stdio-mcp:** spawn `.venv/bin/rush mcp serve --profile full` and send JSON-RPC over stdio: `initialize`, then `notifications/initialized`, then `tools/list` (assert `rush_memory` is present), then `tools/call rush_memory` for write, query, expand, edit-correct, history, explain and revoked-next-use. Record the same IDs and versions the CLI lane records.
- **L-pty-keyboard:** `pty.fork` running `rush ui "<P1>" "<P2>"` at 80x24, 120x40 and 60x20. Send exactly the §5 keys documented by T051, in this order:
  1. `M`;
  2. `S` cycling all seven subjects;
  3. `/` with a query and Enter;
  4. `x` (version/digest shown);
  5. the history and explain keys;
  6. `e` correction, then preview, then `y`;
  7. `o` owner;
  8. an out-of-band revoke, then refresh (denied state);
  9. import review;
  10. resize;
  11. `q`.

  Record ANSI-stripped screen excerpts.
- **L-browser-desktop-1280x800 and L-browser-mobile-390x844:** `rush dashboard "<P1>" --no-open --json --port 0` (plus the grants T07 requires). The PM dispatches browser-qa-agent, following the T041 precedent, with the URL; the token is never written to the report. Same action set as the PTY lane. Text receipts only; screenshots only if requested.
- **L-two-agent-ab and L-e06-e25-rejection-reversal** (gated by OD2):
  - Agent A: `claude -p … --mcp-config <tmp>/mcp.json --strict-mcp-config --output-format json`, where `mcpServers.rush72` uses `.venv/bin/rush mcp serve` and `env.HOME=<tmp>/home`.
  - Agent B: `codex exec --cd "<P1>" -c mcp_servers.rush72.command=… -c mcp_servers.rush72.env.HOME=…`. The worker confirms the flags with `codex exec --help` first.
  - No user config is written.
  - Pass criteria:
    - B cites r1@1 and acts on it.
    - After A corrects to v2, B uses v2 and rejects the cached v1.
    - E06/E25: B picks an allowed alternative only within the affected scope for a held-out rewording, cites the rejection ref, allows the unrelated lookalike and honors the later reversal.
- **L-two-project-personal-overlay and L-revoked-grant:** run through the CLI and MCP routes as in §3.3.
- **L-pas-import-walkthrough:**
  - Export a Rush capsule from P2 with `rush memory capsule`.
  - Build a PAS schema-1 session containing a forged `verified:true` (verified-by: plan L471) and two constraints, inside the temp directory.
  - In P1, preview and then import both through the CLI and the app review.
  - Assert the forged claim stays pending, confirm only the intended constraint, and check that the unrelated local choice is preserved.
- **L-hybrid-eval:** T048's record. If its `product_digest` is not the frozen one, the lane is superseded and is rerun with the D1 commands under the same route grant. Otherwise it is open with the route blocker.
- **L-native-linux and L-native-windows:** open, blocker "no Linux/Windows runner on this macOS host and CI needs a push that is not approved" (OD3).

Open-lane format: `status:"open"`, a one-line `blocker` that names the exact missing route, grant or runner, and empty `observed`. Cleanup: capture PIDs, stop them, confirm with `ps -axo pid,command` that no lane PID remains, and confirm the temp HOME is gone.

### 5. Cross-task conflicts

- **X1:** T041 (72-T07 live) and T048 (72-T08 live) write the report before T050/T051 run. Both must write §3.1-conformant lane records (T041 uses the `T041-` prefix), append-only, with the §3.2 digest. That is a required board update. T051 merges and does not overwrite.
- **X2:** T041, T048 and T052 lack the coverage report in `allowed_files`, so `sync_docs --check` fails after their writes. T048's eval JSON under `docs/` also needs receipts.
- **X3:** No earlier unit runs `sync_docs --check` (T037's verify, for example). CLI/MCP contract drift accumulates, and T051 absorbs it by regenerating `contracts`.
- **X4:** The board notes under `docs/goals/phase-72-memory-correctness/` need receipts (legacy-evidence, untracked). T051 and T052 add receipts for every path present at their check, and the PM covers later notes.
- **X5:** `test_phase70_t25` guards three T09 docs: the `_CURSOR_RE` product-name check, citations, and the `rush help` / categories content.
- **X6:** If T06 changed the `rush_memory` description or SKILL.md, the guide's quotes at L85 and L105 must match. SKILL.md is not a T09 file.
- **X7:** The T003–T013 gates run in parallel, so the T050 author re-verifies symbol names at HEAD.
- **X8:** `tests/test_phase71_dashboard_integration.py` (plan L367) must exist from 72-T07. Otherwise that unit command fails, which is a stop_if.
- **X9:** The report is historical, so each writer refreshes `sha256` and `immutable_body_sha256`.
- **X10:** T052 may write only the report and the coverage report, so all fixtures live in the temp directory.
- **X11:** Never run `scripts/update_phase_docs.py`; it appends to the guide.
- **X12:** The report must not close Phase 70 T28-D/G5–G8 or Phase 71 P07 broader acceptance.
- **X13:** RED design. T041 and T048 may create the report before T050, so every test includes at least one assertion on a section only T051 or T052 supplies (interfaces, claims, ledger, unit_commands, examples, frozen, the full lane set). The behavior half of the integration test may already be green.
- **X14:** T051 has to mark the T09 lanes open, with blocker "pending L-* execution in T052", because the tests require every lane to be present. T053 must reject any final report that still has that blocker.

### 6. Test matrix (`tests/test_phase72_memory_acceptance.py`; import helpers inside the test bodies)

| Test | Fixture | Assertion | Expected RED failure |
|---|---|---|---|
| `test_t09_integrated_route_and_scope` | tmp_path, HOME monkeypatch, P1/P2, 73-T02 grants | §3.3 behavior, and `report.integration == observed` | report missing, or no `integration` key |
| `test_t09_report_block_schema_and_no_secrets` | report file | exactly one block, exact keys and enums, secret scan | file or block missing (FileNotFoundError, or keys mismatch if T041 created it) |
| `test_t09_ledger_rows_match_plan_section_4` | plan file | 9 rows equal §4; pass and open rules; eval evidence digests | `ledger` missing |
| `test_t09_pas_cases_match_plan_section_8` | plan file and AST | 7 names; walkthrough lane present | `pas_cases` missing |
| `test_t09_frozen_source_identity_is_real` | git | commit, ancestry, digest recomputed from blobs, pass-lane digests | `frozen` missing |
| `test_t09_interface_matrix_routes_resolve` | Click registry, `MemoryOperation`, TUI doc, application.js | required operation set covered and every route resolves | `interfaces` missing |
| `test_t09_claims_anchor_to_real_text` | the 6 docs | quotes exist, enums, revisions, evidence, the 3 F23 supersessions | `claims` missing |
| `test_t09_historical_receipts_intact_and_revision_labeled` | MC13/phase-63 plus coverage | `Current status:` prefix, pinned body digests, historical+superseded entries, link | MC13 lacks the prefix; entry authority is current/planned |
| `test_t09_lanes_complete_and_open_lanes_have_one_blocker` | report | exact required set, plus `T041-` extras; status rules | required lanes missing |
| `test_t09_doc_examples_were_executed` | 3 user/reference docs | each fenced `rush memory` / `rush_memory` line is in `examples` with exit and observed | `examples` missing |
| `test_t09_cli_reference_covers_every_memory_subcommand` | `sync_docs._cli_contracts()` | every `rush memory <leaf>` is literal in cli-reference | 20 leaves missing today |
| `test_t09_unit_commands_and_gates_recorded` | plan file | command sets equal the parsed plan commands; exit, passed, no skipped; failures limited to the baseline pair | `unit_commands` missing |
| `test_t09_plan_vs_code_symbols_resolve_at_frozen_commit` | git show and ast | every symbol resolves | `plan_vs_code` missing |

### 7. Worker packages: see the receipt.

## (B) Receipt

```json
{
  "goalbuddy_receipt_v1": {
    "result": "done",
    "task_id": "T014",
    "board_path": "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml",
    "decision": "approved",
    "full_outcome_complete": false,
    "rationale": "72-T09 is buildable as docs plus a reality-bound acceptance report, with a JSON block checked by 13 tests against the plan's own §4/§8 text, git commit blobs, the Click/MCP registries and the doc bytes. Historical receipts keep their bodies and are labeled through the existing sync_docs historical+superseded mechanism. The frozen digest is checked against a commit, so later phases cannot break it. The report gets written before T051 (by T041/T048), and the coverage report is missing from the live cards, so board updates are required. Three lanes need owner grants (OD1-OD3) or stay open with exact blockers.",
    "worker_package": {
      "red": {
        "objective": "Write tests/test_phase72_memory_acceptance.py with the 13 T014 matrix tests (section 6), importing not-yet-existing symbols inside test bodies. Parse plan §4/§8 and plan commands live from the plan file; load test_phase70_t25 helpers via importlib; pin MC13/phase-63 body digests 8c2706455d197203a8f20a94989249591f1ee3c8fddb3ac8c7d5358cd6af5b1c / 7eab4b7525eb8c999445c30345907422060410acde0f77bf671b0f51b11b1263; prove every test fails.",
        "allowed_files": ["tests/test_phase72_memory_acceptance.py"],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_memory_acceptance.py','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_acceptance.py --collect-only -q -p no:cacheprovider  # expect 13 tests collected",
          "rtk proxy uv run --python 3.12 --extra dev ruff check tests/test_phase72_memory_acceptance.py",
          "rtk proxy uv run --python 3.12 --extra dev ruff format --check tests/test_phase72_memory_acceptance.py"
        ],
        "stop_if": [
          "Need files outside allowed_files (PM amends only with gate-note justification).",
          "Behavior is ambiguous against the gate note, or a T01-T06/POLICY/CODEC public symbol or error code differs from plan §2.1 at HEAD (return to PM for a gate delta).",
          "Any test passes at RED (each must carry a T051/T052-only assertion, X13).",
          "Verification fails twice."
        ]
      },
      "implement": {
        "objective": "Reconcile the plan §3 docs with truth labels, create the report and its rush-phase72-acceptance-v1 block (freeze: record HEAD and the §3.2 product digest with the product paths clean), execute every doc example and all T01-T08 plus §8 commands on frozen bytes, refresh coverage receipts and runtime contracts, until the acceptance test and all gates are green. Merge existing T041/T048 records; never overwrite them.",
        "allowed_files": [
          "docs/user-guide/working-with-ai-agents.md",
          "docs/user-guide/interactive-tui.md",
          "docs/reference/cli-reference.md",
          "docs/architecture/rush-epistemic-memory-and-agent-substrate.md",
          "docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md",
          "docs/phase-plans/MC13.md",
          "docs/reports/phase-72-memory-acceptance.md",
          "docs/reports/phase-64-66-documentation-coverage.md"
        ],
        "verify": [
          "rtk proxy git status --porcelain -- src scripts pyproject.toml uv.lock  # must be empty (frozen product bytes)",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t01 -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_retrieval.py tests/test_phase61_trust.py tests/test_memory_versions.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t02 -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_handoff.py tests/test_memory_retrieval.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t03 -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_relations.py tests/test_memory_consolidation.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t04 -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase62_maintenance.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_preferences.py tests/test_memory_compatibility_regressions.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_public.py tests/test_memory_public_contract.py tests/test_phase61_memory_tool.py tests/test_mcp.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_ui.py tests/test_phase70_tui_usability.py -k 't07 or t28d' -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase71_dashboard_integration.py tests/test_dashboard_memory_tokens.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_hybrid.py tests/test_memory_hybrid.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_portable_memory_policy.py tests/test_memory_public_contract.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version  # must print 3.12",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_acceptance.py tests/test_phase70_t25.py tests/test_phase70_t1.py tests/test_sync_docs.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m ''  # expect: no failure beyond the 2 T001 baseline failures, zero SKIPPED",
          "rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev mypy src/rush",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check",
          "rtk git diff --check"
        ],
        "stop_if": [
          "Need files outside allowed_files (PM amends only with gate-note justification).",
          "Product paths (src/scripts/pyproject.toml/uv.lock) dirty or drifting during verification.",
          "A T01-T08/§8 unit command fails or its test file is absent (record the exact blocker and return to PM; do not substitute a narrower command).",
          "A defect in tests/test_phase72_memory_acceptance.py (return to PM; never edit or weaken it).",
          "A doc example cannot be executed (do not publish it).",
          "Behavior is ambiguous against the gate note.",
          "Verification fails twice."
        ]
      },
      "live": {
        "objective": "Run every T014 §4 lane on frozen bytes from one TemporaryDirectory-held driver with temp HOME: installed CLI, release artifact (OD1), stdio MCP, PTY at 80x24/120x40/60x20, browser 1280x800 and 390x844 (PM dispatches browser-qa-agent), two-agent A/B and E06/E25 (OD2), two-project overlay, revoked grant, PAS and Rush-capsule import walkthrough, hybrid-eval digest check, native Linux/Windows (OD3). Write lane records only; each unavailable lane is open with one exact blocker.",
        "allowed_files": [
          "docs/reports/phase-72-memory-acceptance.md",
          "docs/reports/phase-64-66-documentation-coverage.md"
        ],
        "verify": [
          "rtk proxy git status --porcelain -- src scripts pyproject.toml uv.lock  # must be empty",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_acceptance.py -q",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check",
          "rtk git diff --check",
          "rtk proxy ps -axo pid,command  # no lane-started rush ui/dashboard/mcp serve/claude/codex PIDs remain; temp HOME deleted"
        ],
        "stop_if": [
          "Need files outside allowed_files (PM amends only with gate-note justification).",
          "Lane needs credentials, paid model usage, a push or a build route not granted (OD1-OD3): record the lane open with the exact blocker and continue the other lanes.",
          "Unauthorized or cross-owner exposure, a hidden write, or changed product bytes observed (stop the acceptance claim and return to PM).",
          "Browser lane requires agent dispatch the worker cannot perform (return that lane to PM).",
          "Behavior is ambiguous against the gate note.",
          "Verification fails twice."
        ]
      }
    },
    "owner_decisions_needed": [
      "OD1 L-installed-artifact: build the release-route binary by adding PyInstaller to the single phase-72 .venv (uv pip install pyinstaller), or build wheel/sdist and run scripts/probe_installed_artifacts.py, which builds its own environment against D4. Either option delivers the lane.",
      "OD2 L-two-agent-ab and L-e06-e25: grant live model usage of claude -p (Agent A) and codex exec (Agent B) with Rush MCP injected per invocation (--mcp-config/--strict-mcp-config, -c overrides, server HOME=temp), with no user config writes.",
      "OD3 L-native-linux and L-native-windows: approve pushing the phase branch so CI runs the Linux/Windows lanes (push is currently not approved)."
    ],
    "evidence": [
      "plan L98-111 docs list, L112-125 ledger, L408-456 72-T09 packet, L457-475 §8 read",
      "state.yaml T041/T048/T050-T052 cards: no coverage report in live allowed_files; T041 and T048 write the report before T051",
      "scripts/sync_docs.py: owner docs/reports=historical; historical requires immutable_body_sha256; superseded:true requires a 'Current status: ' prefix; contracts block checks CLI/MCP/catalog/engines",
      "Coverage now: MC13 authority current, phase-63 planned, architecture planned (owner fallback); sync_docs --check passes at HEAD",
      "Click registry: 22 'rush memory' leaves, 20 absent literally from cli-reference.md",
      "tests/test_phase70_t25.py:457-466,567,690 guard working-with-ai-agents, interactive-tui and cli-reference",
      "Tools present: .venv/bin/rush (editable, 0.3.0), claude 2.1.289, codex-cli 0.160.0, Chrome app; PyInstaller and playwright absent from .venv",
      "T001 baseline: 2 failed, 6491 passed, 0 skipped, 14 deselected",
      "HEAD moved to 17f7645 (board docs only); product bytes are those of 07775f1"
    ],
    "subgoal_contract": null,
    "parallel_safety": null,
    "blocked_tasks": [],
    "missing_evidence": [
      "graft call-graph traversal not run (graft tools not loadable in this session); caller map built with rtk grep",
      "Exact landed names and error codes of 73-T02/T01-T07/CODEC symbols (gates run in parallel; the T050 author re-verifies at HEAD)"
    ],
    "required_board_updates": [
      "T041 and T048: add docs/reports/phase-64-66-documentation-coverage.md to allowed_files; add constraint 'write lane records into the rush-phase72-acceptance-v1 block per T014 §3.1, append-only (T041 ids prefixed T041-; T048 id L-hybrid-eval), record product_digest by the T014 §3.2 algorithm, refresh sha256 and immutable_body_sha256'",
      "T048: receipts for every docs/reports/phase-72-memory-eval/ file",
      "T050/T051/T052: replace allowed_files/verify/stop_if with this receipt's packages",
      "T053 and T999: reject a final report with any 'pending L-* execution in T052' blocker; rerun the product digest check and the lane-PID/temp-HOME cleanup check",
      "Units changing CLI/MCP (T034, T037, T040, T044, T047): add sync_docs --check, or accept that T051 regenerates the contracts block (X3)",
      "PM: add coverage receipts for every new board note before each sync_docs --check"
    ]
  }
}
```

Paths: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md`, `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/scripts/sync_docs.py`, `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/reports/phase-64-66-documentation-coverage.md`, `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/tests/test_phase70_t25.py`, `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml`.