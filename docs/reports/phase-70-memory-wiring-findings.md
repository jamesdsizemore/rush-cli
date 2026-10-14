# Phase 70 T22: causal findings for empty memory tables

This report explains why each of four memory tables in a project's `.rush/memory.db` can hold
zero rows: `memory_relations`, `memory_embeddings`, `memory_behavior_success` and
`memory_handoff_receipts`. The Phase 70 plan records this as evidence row E14 ("Empty
relations/embeddings/behavior-success/handoff-receipt tables do not share one cause",
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md:38`) and assigns it to task
T22 ("T22 — Publish causal findings for empty memory tables", same file, lines 264-269).

For each table the report gives the producer and consumer functions, every production,
benchmark-script and test caller, the trigger, the grant and capability prerequisites, a
controlled demonstration that was executed for this report, and the limitations of that
evidence.

This is a research deliverable only. No application code, test or configuration file was
changed to produce it. It does not propose, plan or promise any new wiring. The T22 packet's
own Constraints line (plan line 267) says "Finding precedes any proposed wiring", and its
Completion line (plan line 269) says the "Research-only deliverable remains research, not a
promise of new behavioral-learning wiring."

## Summary of the four conclusions

The four tables are empty for four different reasons. No single cause explains all of them.
In every case a zero row count, taken alone, shows neither that a feature is broken nor that
the system learned anything. It only shows that the one code path that writes that table has
not run to completion against that store.

| Table | Only writer | What has to happen for one row to exist | Why a store commonly has zero rows |
|---|---|---|---|
| `memory_relations` | `rush.memory.relations.add_relation` | A caller explicitly issues the `link` memory operation with the `cache_write` grant, naming two existing artifact versions and a supported relation kind. | Nothing in Rush creates relations automatically. The only production caller is the explicit `link` operation. |
| `memory_embeddings` | `TypedArtifactStore.put_embedding` | A compact hybrid `ask`/`recall`/`list` call through MCP or in-process Python, with the `network` and `cache_write` grants, an explicit embedding endpoint, model and model digest, and a reachable engine that returns valid vectors for a candidate whose vector is not already cached. | The CLI has no hybrid route, and the dashboard and benchmark hybrid callers never pass an embedding engine, so they always fall back to lexical retrieval without writing vectors. |
| `memory_behavior_success` | `TypedArtifactStore.write_pass` | A direct Python call to `rush.memory.experience.record_behavior_success`. | `record_behavior_success` has no production caller. Only tests call it. |
| `memory_handoff_receipts` | `TypedArtifactStore.acknowledge_handoff` | A receiver calls the `receive` memory operation with a non-empty `ack` list whose every entry names a granted artifact, a stored version, and the SHA-256 of that version's exact stored bytes, under a valid, unexpired handoff session and capability. | Preparing, receiving and scan-handoff "acknowledge" do not write receipts. Only a digest-checked read-back ACK does. |

## Source revision

The worktree's uncommitted state is part of the evidence. Another Phase 70 task (T8) was
editing files under `src/` while this report was written, so a HEAD hash alone would not
describe the tree.

- `git rev-parse HEAD` and `git status --porcelain`, captured when this file was written:

```text
$ git rev-parse HEAD
4f1414f3491818cf62e480c2bc5d1afe20969008
$ git status --porcelain
 M src/rush/cli.py
 M src/rush/cli_support/rendering.py
 M src/rush/invocation/models.py
 M src/rush/invocation/resolver.py
 M src/rush/invocation/targets.py
 M src/rush/mcp.py
 M src/rush/mcp_support/tool_registry.py
 M src/rush/tui.py
 M src/rush/workflows/project_run.py
 M src/rush/workflows/suites.py
 M tests/test_phase60_characterization.py
?? docs/reports/phase-70-memory-wiring-findings.md
?? tests/test_phase70_result_trust.py
```

- HEAD moved while this report was being written. The demonstration source export was taken at
  `ccc781051ff78f13395109b7a90a6a5912c1872c`, and HEAD was
  `4f1414f3491818cf62e480c2bc5d1afe20969008` when the block above was captured. The only change
  between the two commits is 9 inserted lines in
  `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`
  (`git diff --stat ccc7810 4f1414f`). `git diff --quiet ccc7810 4f1414f -- src scripts tests
  .gitignore` exits 0, so every cited source, script and test file is identical at both commits.
  The demonstrations, caller listings and test runs therefore apply to either commit. Plan line
  numbers in this report are for `4f1414f`.
- Line numbers in this report are for the HEAD blob of each file. For every cited file that
  is unchanged from HEAD, the HEAD line number is also the working-tree line number. Five cited
  files differ from HEAD because of T8's in-progress edits: `src/rush/cli.py`, `src/rush/mcp.py`,
  `src/rush/mcp_support/tool_registry.py`, `src/rush/tui.py` and
  `src/rush/workflows/project_run.py`. Citations into those five files name the symbol first and
  give the HEAD line number, which you can read with `git show HEAD:<path>`. One more
  T8-modified file, `src/rush/cli_support/rendering.py`, is named only in the demonstration
  tracebacks, which ran against the HEAD export.
- Every demonstration below ran against a `git archive HEAD` export of `src/`, so none of the
  demonstrated behavior depends on T8's uncommitted edits.
- sha256 of every cited repository file, both the working-tree bytes at write time and the HEAD
  blob bytes (`git show HEAD:<path> | shasum -a 256`). The table covers:
  - every repository file named in this report's prose;
  - `src/rush/cli_support/rendering.py` and `src/rush/invocation/executor.py`, which are named
    only in the demonstration tracebacks;
  - `pyproject.toml` and `src/rush/__init__.py`, which the harness description names.

  All rows were recomputed at the final write. "DIFFERS" marks the T8-modified files, whose
  working-tree hash was still changing while this report was written. The report also names
  files that are not repository files, so they have no table row:
  - the scratch harness scripts, each reproduced verbatim in Appendix B, with these sha256
    values:
    - `rush_head.py`: `bbedb1764f2b57f24bccf55f487e85db6c82b80e78b9c2acc1bf4318b4041351`;
    - `t22_demo.py`: `25604d123b83fd5dc83e55ae3799b18bb23f79ac3d40a5a2d80000a2247ac096`;
    - `t22_demo_round1.py`:
      `4b011f63f7ca86875b82dbe8ad8f4e120c3c60fbcec882ca80fd219201e74801`;
    - `t22_demo_round2.py`:
      `39235082a168d2240d5ee34dc2c0bc2e559095715bdd95aba47a09ae43336d14`;
    - `callers.sh`: `d957f630baa68ae8896991afdf2bf6bd38d05894530a406db242786df791b4b1`;
    - `callers_round1.sh`: `7f6630a5b4cbc84540b32f8d470eb4b27ef339c013a7449ad166f533a75546a3`;
  - the fixture files that each transcript prints with `cat`;
  - the registry file `~/Library/Application Support/Rush/projects.json`.

| File | Working tree sha256 | HEAD blob sha256 | Working tree vs HEAD |
|---|---|---|---|
| `src/rush/memory/relations.py` | `10f8734916712771ba2c38d025bf1967f8db0fc6cf197474c9657249d3c5b4db` | `10f8734916712771ba2c38d025bf1967f8db0fc6cf197474c9657249d3c5b4db` | same |
| `src/rush/memory/store.py` | `0129a89503d77d0d0683c24f41b0f458d461a24693098b9b93916f861e856b90` | `0129a89503d77d0d0683c24f41b0f458d461a24693098b9b93916f861e856b90` | same |
| `src/rush/memory/retrieval.py` | `5a52fb1debba58da96af71456ccde1d7fa88aff5b122e412df8e3408a30639b5` | `5a52fb1debba58da96af71456ccde1d7fa88aff5b122e412df8e3408a30639b5` | same |
| `src/rush/memory/embeddings.py` | `acd9778f905b324b2c3d5d38181b0bf0f3d0852b22c855100f7ca97b68f0f624` | `acd9778f905b324b2c3d5d38181b0bf0f3d0852b22c855100f7ca97b68f0f624` | same |
| `src/rush/memory/experience.py` | `40a12ca92315707349540924801b31c0e87bb3720414b6e4dde7d8ce157f789a` | `40a12ca92315707349540924801b31c0e87bb3720414b6e4dde7d8ce157f789a` | same |
| `src/rush/memory/handoff.py` | `8d235de0bc234ba546375f9c9345e8aed2dfdc8f0b3ec83db30c6910eb3cd46f` | `8d235de0bc234ba546375f9c9345e8aed2dfdc8f0b3ec83db30c6910eb3cd46f` | same |
| `src/rush/memory/transport.py` | `a6893ff7065965b12a30f55e629735dc523479fa7fa9b8e5c52f08298ee88bbc` | `a6893ff7065965b12a30f55e629735dc523479fa7fa9b8e5c52f08298ee88bbc` | same |
| `src/rush/memory/verification.py` | `512638681bc96491a5ee7beb4daa617d2883ffe08113568b975784943bbc8e8d` | `512638681bc96491a5ee7beb4daa617d2883ffe08113568b975784943bbc8e8d` | same |
| `src/rush/tools/memory.py` | `c0951d63b56cc950f915b4deb60e8f36837473b596f4865bd5927d6252b43df0` | `c0951d63b56cc950f915b4deb60e8f36837473b596f4865bd5927d6252b43df0` | same |
| `src/rush/tools/scan_handoff.py` | `b468d05e9b39987439c431a198af3aa45f0f1c1d65c3b31fb7c0b5b78caa2bd4` | `b468d05e9b39987439c431a198af3aa45f0f1c1d65c3b31fb7c0b5b78caa2bd4` | same |
| `src/rush/dashboard/server.py` | `b91e89b62cd4248abbaf74c5cfe1a753468147272fa623a3356a492b2c5185d1` | `b91e89b62cd4248abbaf74c5cfe1a753468147272fa623a3356a492b2c5185d1` | same |
| `src/rush/tui.py` | `1aceed992b66a346bc76323d694d19fe9d310846434befe3293ddc7e3f70f8ea` | `df8b3ac7e3de5f93446d26b5052e9e258bd357acbf8d2acb03bf0a68b0ac751a` | DIFFERS |
| `src/rush/setup/provision.py` | `89c9410edc66559f31855b0569ca5fdf728ccf9c4dd954e974786c43f0df560a` | `89c9410edc66559f31855b0569ca5fdf728ccf9c4dd954e974786c43f0df560a` | same |
| `src/rush/cli.py` | `dc08fbc941ca428a2e9ebd3bb8f9ab2d416f61096d6a2a42981dff687315a8bf` | `586880ae6c8f7cf3063ee786a27fb902516a0c4fabac2e6bd389114d1c262c19` | DIFFERS |
| `src/rush/mcp.py` | `fef398d1eb2dbd95cfde6001b74794dd239750ea7a86970969ff37dac25a44c3` | `55211ac6b642e73c8fa968c2e703a3fc052fb94079b21d437665552ed7beb438` | DIFFERS |
| `src/rush/mcp_support/tool_registry.py` | `ced041cb614a7404f773ba456459905ecb0f14658c12b07986c4ee44524c6e0f` | `4143efb6c2489902103881d68e212ce2cb4e6a6386cdd90f873988dd354510ab` | DIFFERS |
| `src/rush/workflows/project_run.py` | `021cf52c903432396a7b83ce7bc54e3b71d3b79052ee0aa26c5996cee2b26cad` | `420c3c1207eea3ff6154320e4d680d5491be20addd87e74970f8767b88813e67` | DIFFERS |
| `scripts/benchmarks/run.py` | `0bb39fd06b801b438c1f70c617d07f665e64503ab57325b6e487deba09501126` | `0bb39fd06b801b438c1f70c617d07f665e64503ab57325b6e487deba09501126` | same |
| `scripts/benchmarks/memory.py` | `8a6016c1b43f7052800b7702614164d93ac32787a353265b58cda93916627a26` | `8a6016c1b43f7052800b7702614164d93ac32787a353265b58cda93916627a26` | same |
| `tests/test_memory_relations.py` | `e162144f11d1f4cf4869f60724b8837299f11dc919dd48273c67ae2570512f79` | `e162144f11d1f4cf4869f60724b8837299f11dc919dd48273c67ae2570512f79` | same |
| `tests/test_memory_hybrid.py` | `ff08625589b388d943f846e03744d96b6532c5b1d0c94ae8517e67077ad5a1ae` | `ff08625589b388d943f846e03744d96b6532c5b1d0c94ae8517e67077ad5a1ae` | same |
| `tests/test_memory_last_success.py` | `fa816a3506c0ed7a547b8d1ffc1ec4fe9cb1317ff2367a71b832d9bd07d9c930` | `fa816a3506c0ed7a547b8d1ffc1ec4fe9cb1317ff2367a71b832d9bd07d9c930` | same |
| `tests/test_memory_handoff.py` | `c4d32cfaae5298d2f0af784335c8d9ddd27c596a1c78b1fccae55ed9b31a6b0b` | `c4d32cfaae5298d2f0af784335c8d9ddd27c596a1c78b1fccae55ed9b31a6b0b` | same |
| `tests/test_memory_public_contract.py` | `baa3b79a1d9204b0f5eb9b596c5809e95c63a4450cc9310fd52a81aec4d42478` | `baa3b79a1d9204b0f5eb9b596c5809e95c63a4450cc9310fd52a81aec4d42478` | same |
| `tests/test_memory_retrieval.py` | `e27210dce1d33266264ee7cc5f4f62cbcea2329c86647d60da2b20cac28af380` | `e27210dce1d33266264ee7cc5f4f62cbcea2329c86647d60da2b20cac28af380` | same |
| `tests/test_memory_acceptance.py` | `680316abd56cb44e0863c9551972e82e8162bcf374f6ce07630b652dfd2d0960` | `680316abd56cb44e0863c9551972e82e8162bcf374f6ce07630b652dfd2d0960` | same |
| `tests/test_benchmark_memory_agents.py` | `de1d6b2563af675c4a0e037ca5d6329eeda91d3e3a94181666d06db52ba92be4` | `de1d6b2563af675c4a0e037ca5d6329eeda91d3e3a94181666d06db52ba92be4` | same |
| `tests/test_scan_handoff.py` | `8b4af28c63a29ad5f89c6bcaa4313d6dc947e1c9cece674f3c2a2c042a99f44f` | `8b4af28c63a29ad5f89c6bcaa4313d6dc947e1c9cece674f3c2a2c042a99f44f` | same |
| `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` | `d519607d261de38f21327891a98276e01b028919a7afa36052b77941032ad0d2` | `d519607d261de38f21327891a98276e01b028919a7afa36052b77941032ad0d2` | same |
| `.gitignore` | `0a38e173010b6d2c9bf8886bc27693704460561cb19abb6f65f81d5d433d54d3` | `0a38e173010b6d2c9bf8886bc27693704460561cb19abb6f65f81d5d433d54d3` | same |
| `tests/test_project_evidence.py` | `5e70282186402dad9f8acaf10732f6146cca4c8e4a0d89f3a5dd34f0dd9a2e2d` | `5e70282186402dad9f8acaf10732f6146cca4c8e4a0d89f3a5dd34f0dd9a2e2d` | same |
| `tests/test_dashboard.py` | `7ccbbb3c93f5fa76b95fe91c28fd600436ac7249d806fac90f4492814de98745` | `7ccbbb3c93f5fa76b95fe91c28fd600436ac7249d806fac90f4492814de98745` | same |
| `tests/test_memory_versions.py` | `d5a83904aef594ff53338a9fece9b8326f030879615e1c82ddca927158f591ba` | `d5a83904aef594ff53338a9fece9b8326f030879615e1c82ddca927158f591ba` | same |
| `tests/test_dashboard_map.py` | `f3fcccc53a1b111b7f5e0d6bda96283cd82ca6b73b8dfc6787194051970e708b` | `f3fcccc53a1b111b7f5e0d6bda96283cd82ca6b73b8dfc6787194051970e708b` | same |
| `tests/test_phase61_transport.py` | `ce853b8d5fa4cca4b571389779ea5243e5c46e7990fd090904afdbba03ea39ab` | `ce853b8d5fa4cca4b571389779ea5243e5c46e7990fd090904afdbba03ea39ab` | same |
| `pyproject.toml` | `2b2be60f71b578a20f2349f9e964b555a70f1df51fb88182fdda6d3cfb9b4160` | `2b2be60f71b578a20f2349f9e964b555a70f1df51fb88182fdda6d3cfb9b4160` | same |
| `src/rush/__init__.py` | `d99e645600f8f56261cb8406b5d16696e65144f6fe1d42e4a57201485e8c6cec` | `d99e645600f8f56261cb8406b5d16696e65144f6fe1d42e4a57201485e8c6cec` | same |
| `src/rush/cli_support/rendering.py` | `42a0f9044ad32aba929820b6a1d71612d1a0d457b1996a5441652d59e6f75760` | `0b6b2e862e3a2c9fe22e103ea097038c44b8ffee0b93644aa77b2797c4f61fd2` | DIFFERS |
| `src/rush/invocation/executor.py` | `5e510f76548b24a75c99ec4fa85eb7441c6ccc296ad80b8e2c40d7a303f581f8` | `5e510f76548b24a75c99ec4fa85eb7441c6ccc296ad80b8e2c40d7a303f581f8` | same |

## How the evidence was gathered

### Caller enumeration

Callers were enumerated two ways for every producer and consumer:

- `grep -rn --include='*.py' -E '\b<symbol>\(' src scripts tests` from the worktree root. At
  write time this searched all 864 `*.py` files under those three directories: 465 under `src/`,
  23 under `scripts/` and 376 under `tests/`.
- `graft callers <symbol>` (graft 0.10.1, the repository's precomputed call graph). The first
  call refreshed the graph under `graft/`, which is gitignored (`.gitignore:42` is `graft/`).
  Graft returns ranked graph edges, not a complete caller list. For example, graft reports "no
  indexed callers" for `write_pass`, but grep shows the real call at
  `src/rush/memory/experience.py:475`. Where the two disagree, this report relies on grep.

Both listings are working-tree output at write time. For the T8-modified files, line numbers
inside a listing are working-tree positions and can differ from the HEAD line numbers cited in
the prose. The script that produced every listing is in Appendix B. Graft's own token-savings
status lines (lines starting with `[graft]`) are filtered out of the listings. Nothing else is
filtered.

### Demonstration harness

- **Source under test.** `git archive --format=tar HEAD src | tar -x -C <SCRATCH>/export`,
  imported with `PYTHONPATH=<SCRATCH>/export/src`. `<SCRATCH>` is a session scratch directory
  outside the repository. The transcript's first lines print the imported `rush/__init__.py`
  path, which confirms the export is the package being imported.
- **Interpreter.** Python 3.12.12 from the worktree's `.venv`. `rush` in the transcripts is
  `rush_head.py`, which calls the `rush.cli:cli` entry point that `pyproject.toml` declares under
  `[project.scripts]`. Table counts use `/usr/bin/sqlite3` 3.51.0.
- **Isolation.** Each run creates a brand-new base directory `<DEMO>`, with one project
  directory per section, `HOME=<DEMO>/home` and `TMPDIR=<DEMO>/tmp`. The environment is
  scrubbed to `HOME`, `PATH=/usr/bin:/bin`, `PYTHONPATH`, `TMPDIR` and `TIKTOKEN_CACHE_DIR`. On
  macOS the Rush data root is `$HOME/Library/Application Support/Rush`
  (`rush.setup.provision.default_data_root`, `src/rush/setup/provision.py:112`), so the
  demonstrations cannot touch the real registry. The scan-handoff step also passes an explicit
  `data_root=<DEMO>/rush-data`. The transcript shows `<DEMO>/home` empty both before and after.
  The real registry file `~/Library/Application Support/Rush/projects.json` had the same mtime
  (1789903582) and size (5112 bytes) before and after the runs.
- **No network.** The driver runs inside
  `sandbox-exec -p '(version 1)(allow default)(deny network*)'`. It refuses to start unless a
  loopback connect fails with `PermissionError` (errno 1), which happens only when the sandbox
  denies networking. Unsandboxed, the same connect fails with `ConnectionRefusedError`
  (errno 61), and the driver exits with "network not denied". The transcript's first line
  records the canary result. tiktoken, which Rush uses for token budgets, reads
  `TIKTOKEN_CACHE_DIR=<SCRATCH>/tiktoken-cache`. That directory holds a copy of the machine's
  pre-existing `cl100k_base` cache file, whose sha256
  `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` equals the `expected_hash`
  that tiktoken checks for that encoding. The one embedding endpoint the demonstrations
  configure uses an unregistered URL scheme, which `urllib` rejects before it opens any socket.
- **Disclosure: early trial runs used the network.** The earlier, unsandboxed trial runs of this
  harness set `TMPDIR` to an empty directory and had no `TIKTOKEN_CACHE_DIR`, so tiktoken
  downloaded `cl100k_base.tiktoken` over HTTPS from `openaipublic.blob.core.windows.net`. The
  first sandboxed attempt exposed this: tiktoken failed with `NameResolutionError`. That fetch
  was made by the tokenizer library, not by any Rush embedding or memory path. None of those
  trial runs produced the transcripts in this report. The transcripts below come only from the
  sandboxed runs with the pre-seeded cache.
- **Normalization.** Only volatile values are replaced:
  - the base directory path becomes `<DEMO>`;
  - every `duration_ms` value becomes `<MS>`;
  - every `tokens` value becomes `<TOKENS>`, because tiktoken counts text that embeds random
    uuid4 artifact ids (the `bytes` values do not vary and are kept);
  - wall-clock `created_at`, `expires_at` and `updated_at` values become `<TS>`;
  - each generated artifact id becomes `<ID-name>`;
  - the handoff session id becomes `<HANDOFF_ID>`;
  - the raw capability becomes `<CAPABILITY>`.
- **Determinism check.** The driver was run twice under the sandbox. The two normalized
  transcripts are byte-identical (`diff` prints nothing), and both have sha256
  `361e94e006c1a1b8c3590f58b96fd6591483d8ad0666d0d5880919045f988acc`.
- **To reproduce.** From the scratch directory that holds the export, `rush_head.py`,
  `t22_demo.py` and `tiktoken-cache/`, run:
  `sandbox-exec -p '(version 1)(allow default)(deny network*)' <worktree>/.venv/bin/python t22_demo.py`.
  Both scripts are reproduced verbatim in Appendix B.
- **Additional demonstrations (fix round 1).** `t22_demo_round1.py` imports the same harness
  from `t22_demo.py` and runs the rejected-attempt and replay fixtures. It uses the same
  sandbox guard and normalization, and additionally replaces its own directory path with
  `<SCRATCH>`. It was run twice under the same sandbox command, and the two transcripts are
  byte-identical, both with sha256
  `5c389cd1f7b75d5d52025d4da8bcc87849e39e5d3d21aa659b24d5b2e3caef7a`. Its first line is
  `network canary: loopback connect -> PermissionError errno=1`, and its last line is
  `home after: []`. Its sections are reproduced under Findings 1, 2 and 4.
- **Additional demonstrations (fix round 2).** `t22_demo_round2.py` reuses the same harness
  through `t22_demo_round1.py`, and runs the CLI `--input` rejections and the two
  oversized-integer crashes. It was run twice under the same sandbox command, and the two
  transcripts are byte-identical, both with sha256
  `4f4ed3b3a8a2a4b73fdf45b307ac27d49ab0b8c400f725a7d0720b994cbeb01f`. Its first line is
  `network canary: loopback connect -> PermissionError errno=1`, and its last line is
  `home after: []`. Its sections are reproduced under Findings 1 and 4.

Harness header and isolation lines from the recorded transcript. The `...` line stands for the
four finding sections, which are reproduced verbatim under each finding:

```text
network canary: loopback connect -> PermissionError errno=1
rush package: <SCRATCH>/export/src/rush/__init__.py
python: 3.12.12
home before: []
...
===== isolation =====
home after: []
```

### Regression and characterization tests

The following suites ran against the worktree, which includes T8's in-progress edits. The
memory source files these findings rest on (`src/rush/memory/*.py` as cited, and
`src/rush/tools/memory.py`) are byte-identical to HEAD according to the hash table above. The
second command's `tests/test_memory_public_contract.py` and `tests/test_scan_handoff.py` also
exercise T8-modified files (`cli.py`, `tool_registry.py`, `project_run.py`), so that result
describes the working tree at write time.

```text
$ rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_last_success.py tests/test_memory_handoff.py tests/test_memory_hybrid.py -q -m "" -p no:cacheprovider
...................................                                      [100%]
35 passed in 3.53s
[exit 0]
$ rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_relations.py tests/test_memory_public_contract.py tests/test_scan_handoff.py tests/test_memory_acceptance.py tests/test_benchmark_memory_agents.py -q -m "" -p no:cacheprovider
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 14.81s
[exit 0]
```

## Finding 1: `memory_relations`

### Conclusion

A relation row exists only when a caller explicitly asks for one. The `link` memory operation
is the only production path to the only writer, and it requires the `cache_write` grant.
Rush has no automatic relation producer: no scan, review, consolidation, handoff or recall step
creates edges. A store with zero rows has therefore never completed a successful `link`, meaning
one that returned `OK` with a `sequence`. An attempted `link` also leaves the table without a new
row when it ends in any of these outcomes:

- no `cache_write` grant: `E_PERMISSION` (`src/rush/tools/memory.py:853-860`);
- no request at all: `E_INPUT` (`tools/memory.py:861-864`);
- a request key outside `_LINK_REQUEST_KEYS`: `E_INPUT` (`tools/memory.py:865-872`);
- a missing or wrongly typed `source_id`, `source_version`, `target_id`, `target_version`, `kind`
  or `origin_ref`: `E_INPUT` (`tools/memory.py:879-899`);
- a `kind` outside the seven `RELATION_KINDS`: `E_INPUT` (`src/rush/memory/relations.py:106-107`);
- an endpoint that is not a stored `(id, version)` pair: `E_INPUT` (`relations.py:114-118`);
- a `supersedes` edge that would close a cycle: `E_INPUT` (`relations.py:119-125`);
- a `source_version` or `target_version` too large for SQLite, for example `2**70`:
  - it passes the integer checks at `tools/memory.py:879-899`;
  - `_endpoint_exists`, called at `relations.py:114`, then raises an uncaught
    `OverflowError: Python int too large to convert to SQLite INTEGER` from its `SELECT` at
    `relations.py:58-62`;
  - the CLI call ends with a traceback and exit 1;
  - this is a product-defect finding only, and it is not described as planned or tracked;
- the CLI rejects the `--input` file before `MemoryTool` runs, in any of these cases:
  - the file does not exist: Click's `exists=True` path check (HEAD `src/rush/cli.py:2949`)
    exits 2;
  - the file is not valid JSON: `--input must be valid JSON` (HEAD `cli.py:2886-2888`);
  - the JSON is not an object: `--input JSON must decode to an object.` (HEAD
    `cli.py:2889-2890`);
  - these checks run in `_memory_input_request` (HEAD `cli.py:2882`), which each MC14 leaf
    calls at HEAD `cli.py:2909`, before `_run_tool`.

The two additional demonstrations in this finding send each of these attempts with the grant
and show that none of them writes a row. That shows nothing about whether the relation feature
works, and nothing about whether relations would have helped anyone.

### Producer and consumers

- **Producer.** `rush.memory.relations.add_relation` (`src/rush/memory/relations.py:88-141`).
  It holds the table's only `INSERT INTO memory_relations` (`relations.py:127`). Inside one
  `BEGIN IMMEDIATE` transaction it rejects an unsupported kind (seven kinds in `RELATION_KINDS`),
  an endpoint that is not a stored `(id, version)` pair, and a `supersedes` edge that would
  close a cycle. It returns `{"code": "E_INPUT", ...}` without writing anything in each of those
  cases.
- **Tool entry.** `MemoryTool._link` (`src/rush/tools/memory.py:844-911`) checks
  `_WRITE_PERMISSION` (`ExecutionPermissions(cache_write=True)`, `tools/memory.py:108`) at
  `tools/memory.py:853`. It returns `E_PERMISSION` before opening the store if the check fails,
  and calls `add_relation` at `tools/memory.py:901`. `MemoryTool.run` dispatches `"link"` at
  `tools/memory.py:507`.
- **Consumer: traversal.** `rush.memory.relations.related_artifacts`
  (`relations.py:149-249`) walks edges breadth-first, depth 1 by default and at most 2, with at
  most 32 nodes. It drops any neighbor whose source is outside the session allowlist, or whose
  current version differs from the version recorded on the edge. It is reached through
  `MemoryTool._related` (`tools/memory.py:913-985`, call at `:973`, dispatch at `:508`).
- **Consumer: delete preview.** `TypedArtifactStore.delete_batch` reports each target's
  relation reference count (`src/rush/memory/store.py:1000`).
- **Not a consumer: compact recall items.** `rush.memory.retrieval._candidate_to_item`
  (`src/rush/memory/retrieval.py:275`) hard-codes `"relations": []` (`retrieval.py:294`). Its
  comment (`retrieval.py:292`) says "MC03 (relations.py) isn't implemented yet", but relations
  do exist. The demonstration below shows a compact recall reporting `"relations": []` for an
  artifact that has a stored edge. This report records that as a finding only.
- **Not a producer or consumer: the benchmark "linked" variant.**
  `scripts/benchmarks/run.py:223-235` calls the `related` operation, but it never calls `link`,
  and it reads `data.related` (`run.py:235`). `_related` returns its edges under `data.items`,
  never under `data.related`. So that variant neither creates relation rows nor reads the ones
  that exist.

### Callers

- **Production callers of `add_relation`.** Only `MemoryTool._link` (`tools/memory.py:901`).
  The public routes into `_link` are:
  - **CLI.** `rush memory link --input FILE [--allow-cache-write] [--json]`. The command is
    built by `_build_memory_operation_command` (HEAD `src/rush/cli.py:2894`) and registered by
    the MC14 leaf loop (HEAD `cli.py:2956`, entry `("link", "link")` at HEAD `cli.py:2958`).
  - **MCP.** The `rush_memory` tool, with `operation="link"`, `request={...}` and
    `allow_cache_write=true`. It is registered by `register_all_tools`
    (HEAD `src/rush/mcp_support/tool_registry.py:96`) through `make_tool_wrapper`
    (HEAD `tool_registry.py:33`), which binds the arguments of `MemoryTool.__call__`.
  - **Not reachable.** The memory-session bridge permits only
    `("receive", "expand", "related", "resume")` (HEAD `tool_registry.py:184`). `grep -rn
    'operation="link"' src` returns nothing, so neither the dashboard nor the TUI issues `link`.
    The TUI's memory operations at HEAD are `list`, `expand`, `promote`, `delete` and `edit`
    (HEAD `src/rush/tui.py:1346`, `:1433`, `:1462`, `:1502`, `:1541`, `:1580`).
- **Production callers of `related_artifacts`.** Only `MemoryTool._related`
  (`tools/memory.py:973`). Its routes are:
  - **CLI.** `rush memory related --input FILE --session SRC` (HEAD `cli.py:2959`).
  - **MCP.** `rush_memory`.
  - **Memory-session bridge.** HEAD `tool_registry.py:184`.
  - **Dashboard.** The memory section's `related_id`/`related_version` query parameters
    (`src/rush/dashboard/server.py:3558-3570`, call at `:3566`).
- **Benchmark script.** `scripts/benchmarks/run.py:228` calls `related`.
- **Test callers.**
  - `tests/test_memory_relations.py` calls both functions directly:
    - `test_supersedes_cycle_rejected_atomically` (`:36`);
    - `test_related_hides_denied_neighbors` (`:87`);
    - `test_related_depth_node_and_token_caps` (`:127`);
    - `test_relation_version_change_invalidates_active_evidence` (`:195`).
  - `tests/test_memory_public_contract.py` sends `link` and `related` through both the CLI and
    the MCP wrapper. See `_NEW_OPERATIONS` (`:50`), the link request fixture (`:118`),
    `test_cli_mcp_operation_payload_and_permissions_match` (`:242`) and
    `test_missing_mutation_grant_fails_equally` (`:269`), which covers `link`.

Caller listings, verbatim:

```text
$ grep -rn --include='*.py' -E '\badd_relation\(' src scripts tests
src/rush/tools/memory.py:901:        result = add_relation(
src/rush/memory/relations.py:4:`add_relation()` atomically inserts one `memory_relations` row after checking both endpoints
src/rush/memory/relations.py:88:def add_relation(
tests/test_memory_relations.py:41:    forward = add_relation(
tests/test_memory_relations.py:52:    inverse = add_relation(
tests/test_memory_relations.py:64:    unsupported = add_relation(
tests/test_memory_relations.py:75:    missing_endpoint = add_relation(
tests/test_memory_relations.py:94:        add_relation(
tests/test_memory_relations.py:105:        add_relation(
tests/test_memory_relations.py:134:            add_relation(
tests/test_memory_relations.py:162:            add_relation(
tests/test_memory_relations.py:201:        add_relation(
$ graft callers add_relation

add_relation · function · src/rush/memory/relations.py:L88-L141
  calls ← _link (src/rush/tools/memory.py:L844-L911)
  calls ← test_related_depth_node_and_token_caps (tests/test_memory_relations.py:L127-L192)
  calls ← test_related_hides_denied_neighbors (tests/test_memory_relations.py:L87-L124)
  calls ← test_relation_version_change_invalidates_active_evidence (tests/test_memory_relations.py:L195-L222)
  calls ← test_supersedes_cycle_rejected_atomically (tests/test_memory_relations.py:L36-L84)
$ grep -rn --include='*.py' -E '\brelated_artifacts\(' src scripts tests
src/rush/tools/memory.py:973:        result = related_artifacts(
src/rush/memory/store.py:306:# `memory_artifacts` being mutated — `related_artifacts()` detects that by comparing the
src/rush/memory/store.py:1080:        `related_artifacts()` already compares a stored `target_version` against
src/rush/memory/relations.py:6:that the new edge wouldn't close a cycle. `related_artifacts()` walks that table breadth-first
src/rush/memory/relations.py:149:def related_artifacts(
tests/test_memory_relations.py:116:    result = related_artifacts(
tests/test_memory_relations.py:145:    default_depth = related_artifacts(
tests/test_memory_relations.py:150:    requested_beyond_cap = related_artifacts(
tests/test_memory_relations.py:173:    fanout_result = related_artifacts(
tests/test_memory_relations.py:184:    tiny_budget = related_artifacts(
tests/test_memory_relations.py:212:    before = related_artifacts(
tests/test_memory_relations.py:219:    after = related_artifacts(
$ graft callers related_artifacts

related_artifacts · function · src/rush/memory/relations.py:L149-L249
  calls ← _related (src/rush/tools/memory.py:L913-L985)
  calls ← test_related_depth_node_and_token_caps (tests/test_memory_relations.py:L127-L192)
  calls ← test_related_hides_denied_neighbors (tests/test_memory_relations.py:L87-L124)
  calls ← test_relation_version_change_invalidates_active_evidence (tests/test_memory_relations.py:L195-L222)
```

### Trigger

An explicit `link` request from a user or agent through the CLI, MCP or in-process
`MemoryTool`. Nothing else in the source triggers `add_relation`.

### Grant and capability prerequisites

- `cache_write`: CLI `--allow-cache-write`, or MCP `allow_cache_write: true`. Without it the
  call returns `E_PERMISSION` ("Memory link requires --allow-cache-write.") and writes no row.
- A request containing only the `_LINK_REQUEST_KEYS` fields, with `source_id`,
  `source_version`, `target_id`, `target_version` and `kind`.
- Both endpoints must be stored `(id, version)` pairs, `kind` must be one of the seven
  `RELATION_KINDS`, and a `supersedes` edge must not close a cycle.
- To read an edge back with `related`, the session allowlist must include the seed artifact's
  source and each neighbor's source, and each neighbor's current version must equal the version
  recorded on the edge.

### Controlled demonstration

The fixture is a fresh project. Two artifacts are written with the `demo-src` source, and a
`link.json` request names them with kind `supersedes`. The transcript shows:

- `memory_relations` has 0 rows before the link;
- a link without the grant returns `E_PERMISSION` and the count stays 0;
- the same link with `--allow-cache-write` returns `OK` with sequence 1 and the count becomes 1;
- `related` returns the edge;
- a compact recall through the MCP wrapper still reports `"relations": []` for the linked
  artifact.

```text
===== memory_relations =====
$ rush memory write domain_knowledge demo-src --content '{"text": "alpha relation source"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-A>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "alpha relation source"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/relations"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ rush memory write domain_knowledge demo-src --content '{"text": "beta relation target"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-B>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "beta relation target"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/relations"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link.json
{
  "source_id": "<ID-A>",
  "source_version": 1,
  "target_id": "<ID-B>",
  "target_version": 1,
  "kind": "supersedes"
}
$ rush memory link --input link.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "fail",
  "duration_ms": <MS>,
  "summary": "memory link returned E_PERMISSION.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "E_PERMISSION",
    "data": {
      "message": "Memory link requires --allow-cache-write."
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ rush memory link --input link.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory link returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "OK",
    "data": {
      "sequence": 1
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
1
[exit 0]
$ cat related.json
{
  "id": "<ID-A>",
  "version": 1
}
$ rush memory related --input related.json --session demo-src --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory related returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "related",
    "code": "OK",
    "data": {
      "items": [
        {
          "id": "<ID-B>",
          "version": 1,
          "kind": "supersedes",
          "direction": "outgoing"
        }
      ],
      "complete": true,
      "tokens": <TOKENS>,
      "bytes": 112,
      "encoding": "cl100k_base"
    }
  },
  "metadata": {
    "operation": "related"
  }
}
[exit 0]
$ cat recall_compact.json
{
  "operation": "recall",
  "subject": "domain_knowledge",
  "query": "alpha",
  "session_allowlist": [
    "demo-src"
  ],
  "request": {
    "view": "compact"
  }
}
$ python mcp_call.py recall_compact.json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory recall returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "recall",
    "code": "OK",
    "data": {
      "items": [
        {
          "id": "<ID-A>",
          "version": 1,
          "excerpt": "alpha relation source",
          "source": "demo-src",
          "trust": "EXTERNAL_WRITE",
          "freshness": "fresh",
          "relations": []
        }
      ],
      "next_cursor": null,
      "complete": true,
      "tokens": <TOKENS>,
      "bytes": 243,
      "encoding": "cl100k_base"
    }
  },
  "metadata": {
    "operation": "recall"
  }
}
[exit 0]
```

### Additional demonstration: authorized attempts that write no row

This fixture is a fresh project with two artifacts from source `demo-src`. It sends every
rejected `link` shape from the conclusion with the `cache_write` grant, and counts
`memory_relations` after each one:

- no request, through the MCP wrapper, returns `E_INPUT`, count 0;
- an unknown request key returns `E_INPUT`, count 0;
- a missing `kind` returns `E_INPUT`, count 0;
- an unsupported kind (`resembles`) returns `E_INPUT`, count 0;
- a target version that does not exist (9) returns `E_INPUT`, count 0;
- a valid `supersedes` link returns `OK`, count 1;
- the inverse `supersedes` link, which would close a cycle, returns `E_INPUT`, and the count stays
  at 1.

It was produced by `t22_demo_round1.py` (Appendix B), with the same harness, sandbox and
normalization as the main demonstrations.

```text
===== memory_relations: authorized link attempts that write no row =====
$ rush memory write domain_knowledge demo-src --content '{"text": "alpha relation source"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-A>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "alpha relation source"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/relations"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ rush memory write domain_knowledge demo-src --content '{"text": "beta relation target"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-B>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "beta relation target"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/relations"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_no_request.json
{
  "operation": "link",
  "allow_cache_write": true
}
$ python mcp_call.py link_no_request.json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "error",
  "duration_ms": <MS>,
  "summary": "memory link returned E_INPUT.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "E_INPUT",
    "data": {
      "message": "memory link requires request."
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_unknown_key.json
{
  "source_id": "<ID-A>",
  "source_version": 1,
  "target_id": "<ID-B>",
  "target_version": 1,
  "kind": "supersedes",
  "note": "x"
}
$ rush memory link --input link_unknown_key.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "error",
  "duration_ms": <MS>,
  "summary": "memory link returned E_INPUT.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "E_INPUT",
    "data": {
      "message": "unknown request field(s): ['note']"
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 2]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_missing_kind.json
{
  "source_id": "<ID-A>",
  "source_version": 1,
  "target_id": "<ID-B>",
  "target_version": 1
}
$ rush memory link --input link_missing_kind.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "error",
  "duration_ms": <MS>,
  "summary": "memory link returned E_INPUT.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "E_INPUT",
    "data": {
      "message": "memory link requires source_id, source_version, target_id, target_version and kind."
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 2]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_bad_kind.json
{
  "source_id": "<ID-A>",
  "source_version": 1,
  "target_id": "<ID-B>",
  "target_version": 1,
  "kind": "resembles"
}
$ rush memory link --input link_bad_kind.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "error",
  "duration_ms": <MS>,
  "summary": "memory link returned E_INPUT.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "E_INPUT",
    "data": {
      "message": "unsupported relation kind: 'resembles'"
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 2]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_missing_endpoint.json
{
  "source_id": "<ID-A>",
  "source_version": 1,
  "target_id": "<ID-B>",
  "target_version": 9,
  "kind": "supersedes"
}
$ rush memory link --input link_missing_endpoint.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "error",
  "duration_ms": <MS>,
  "summary": "memory link returned E_INPUT.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "E_INPUT",
    "data": {
      "message": "unknown endpoint '<ID-B>'@9"
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 2]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_ok.json
{
  "source_id": "<ID-A>",
  "source_version": 1,
  "target_id": "<ID-B>",
  "target_version": 1,
  "kind": "supersedes"
}
$ rush memory link --input link_ok.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory link returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "OK",
    "data": {
      "sequence": 1
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
1
[exit 0]
$ cat link_cycle.json
{
  "source_id": "<ID-B>",
  "source_version": 1,
  "target_id": "<ID-A>",
  "target_version": 1,
  "kind": "supersedes"
}
$ rush memory link --input link_cycle.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "error",
  "duration_ms": <MS>,
  "summary": "memory link returned E_INPUT.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "link",
    "code": "E_INPUT",
    "data": {
      "message": "supersedes '<ID-B>'->'<ID-A>' would create a cycle"
    }
  },
  "metadata": {
    "operation": "link"
  }
}
[exit 2]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
1
[exit 0]
```

### Additional demonstration (round 2): CLI input rejections and an oversized version

This fixture is a fresh project with two artifacts from source `demo-src`. Each `link` below is
sent with `--allow-cache-write`, and `memory_relations` is counted after each one:

- an `--input` file containing `[]` exits 1 with `--input JSON must decode to an object.`,
  count 0;
- an `--input` file containing `{not json` exits 1 with `--input must be valid JSON`, count 0;
- a missing `--input` file exits 2 with a Click usage error, count 0;
- a `source_version` of `2**70` (1180591620717411303424) ends in an uncaught `OverflowError`
  traceback raised from `_endpoint_exists`, with exit 1, count 0.

It was produced by `t22_demo_round2.py` (Appendix B), with the same harness, sandbox and
normalization. The traceback's `.venv` frame paths are printed verbatim; they are identical in
both runs.

```text
===== memory_relations: CLI rejections before the tool, and an oversized version =====
$ rush memory write domain_knowledge demo-src --content '{"text": "alpha relation source"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-A>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "alpha relation source"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/relations"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ rush memory write domain_knowledge demo-src --content '{"text": "beta relation target"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-B>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "beta relation target"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/relations"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_not_object.json
[]
$ rush memory link --input link_not_object.json --allow-cache-write --json
[stderr] Error: --input JSON must decode to an object.
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_not_json.json
{not json
$ rush memory link --input link_not_json.json --allow-cache-write --json
[stderr] Error: --input must be valid JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ rush memory link --input no_such_file.json --allow-cache-write --json
[stderr] Usage: rush memory link [OPTIONS]
Try 'rush memory link --help' for help.

Error: Invalid value for '--input': File 'no_such_file.json' does not exist.
[exit 2]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
$ cat link_big_version.json
{
  "source_id": "<ID-A>",
  "source_version": 1180591620717411303424,
  "target_id": "<ID-B>",
  "target_version": 1,
  "kind": "supersedes"
}
$ rush memory link --input link_big_version.json --allow-cache-write --json
[stderr] Traceback (most recent call last):
  File "<SCRATCH>/rush_head.py", line 14, in <module>
    cli(prog_name="rush")
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1569, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1490, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1970, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1970, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1353, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 907, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/cli.py", line 2910, in _cmd
    _run_tool(
  File "<SCRATCH>/export/src/rush/cli_support/rendering.py", line 119, in _run_tool
    result = executor.execute(context)
             ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/invocation/executor.py", line 466, in execute
    result = operation.handler(*args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 315, in __call__
    return self.run(
           ^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 533, in run
    return dispatch_table[operation]()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 507, in <lambda>
    "link": lambda: self._link(started, root, granted, request),
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 901, in _link
    result = add_relation(
             ^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/memory/relations.py", line 114, in add_relation
    if not _endpoint_exists(conn, endpoint_id, endpoint_version):
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/memory/relations.py", line 59, in _endpoint_exists
    row = conn.execute(
          ^^^^^^^^^^^^^
OverflowError: Python int too large to convert to SQLite INTEGER
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_relations;"
0
[exit 0]
```

### Limitations

- The demonstration proves that the explicit path writes and reads an edge. It says nothing
  about whether any user or agent has invoked `link` against a real store.
- The MCP route ran in-process through the HEAD `make_tool_wrapper` with an
  `InvocationExecutor`, the same pattern `tests/test_memory_public_contract.py` uses. The MCP
  stdio transport was not exercised.
- Only the `supersedes` kind was written successfully. The two additional demonstrations cover
  the rejections: unknown endpoint (target version 9), unsupported kind, cycle, the
  request-shape errors, the CLI `--input` errors and the oversized version. The other six valid
  kinds were not exercised by any demonstration here.
- The dashboard `related_id` route was not exercised. It has no test caller: `grep -rln
  related_id tests` returns nothing.

## Finding 2: `memory_embeddings`

### Conclusion

A vector row exists only after a hybrid compact retrieval that meets every one of these
conditions:

- it arrives through MCP or in-process Python;
- it carries the `network` grant and an explicit embedding endpoint, model and model digest;
- the engine is reachable and returns valid vectors for a candidate whose vector is not already
  cached;
- it carries the `cache_write` grant.

The CLI cannot make this call. The dashboard's `memory_query` action and the benchmark's
`hybrid` variant can request hybrid retrieval, but neither forwards an embedding engine, so both
always take the lexical fallback and write nothing. Applying a memory delete removes a deleted
artifact's vectors (`src/rush/memory/store.py:1027`). A store with zero rows has therefore
never completed a successful vector write, or has had every vectored artifact deleted. A
successful vector write is a hybrid call in which the engine returned valid vectors for at least
one uncached candidate while `cache_write` was granted. A hybrid attempt, even one with a
configured engine and both grants, leaves the table without a new row when it ends in any of
these outcomes:

- request validation fails with `E_INPUT`:
  - an unknown request key (`src/rush/tools/memory.py:603-609`);
  - `view` other than `compact` (`tools/memory.py:610-616`);
  - a missing subject, or a missing query for `ask`/`recall` (`tools/memory.py:618-627`);
  - an unsupported `retrieval` value (`tools/memory.py:629-635`);
  - a wrongly typed field (`tools/memory.py:645-673`);
- an empty `session_allowlist`: `E_PERMISSION` (`tools/memory.py:674-683`);
- no `network` grant: `E_PERMISSION` (`tools/memory.py:687-695`);
- `embedding_endpoint`, `embedding_model` and `embedding_model_digest` not all set, so no engine
  is configured (`tools/memory.py:697`, `src/rush/memory/retrieval.py:753-754`), followed by the
  `E_EMBEDDING_UNAVAILABLE` lexical fallback (`retrieval.py:931`);
- no authorized candidate: the allowlist names no source that has an artifact under that
  subject, so `hybrid_candidates` returns `available: True` with no rows before calling the
  engine (`retrieval.py:773-778`), and the page is `OK` with no items;
- a candidate whose stored content is not JSON is skipped and never embedded
  (`retrieval.py:783-786`);
- the engine is unreachable: `EmbeddingEngineUnavailable` (`src/rush/memory/embeddings.py:74-77`,
  caught at `retrieval.py:823-824`);
- the engine returns an invalid response: `EmbeddingResponseError` (raised by
  `validate_embedding_response`, `embeddings.py:83`, through `embeddings.py:80`, or by the
  1 MiB response cap, `embeddings.py:78-79`; caught at
  `retrieval.py:825-826`);
- `cache_write` not granted: vectors are computed for ranking only and never persisted
  (`retrieval.py:812`);
- a direct in-process call to `hybrid_candidates` or `hybrid_page` with an empty allowlist
  (`retrieval.py:751-752`, `retrieval.py:891-895`). Through `MemoryTool` this cannot happen,
  because `_compact_query` rejects an empty allowlist first.

`embed_chunks` returns vectors only after every candidate batch succeeds
(`embeddings.py:57-60`), so an engine failure on any candidate batch persists nothing. A failure
while embedding the query (`retrieval.py:822`) happens after the candidate vectors were
persisted, so those rows stay.

Of these outcomes, the unreachable engine and the missing engine are shown in the main
demonstration, and the no-authorized-candidate case in the additional demonstration. That
shows neither that embeddings are broken nor that retrieval learned anything.

### Producer and consumers

- **Producer.** `TypedArtifactStore.put_embedding` (`src/rush/memory/store.py:1256-1286`). It
  holds the table's only `INSERT OR REPLACE INTO memory_embeddings` (`store.py:1271`).
- **Its only caller.** `rush.memory.retrieval.hybrid_candidates`
  (`src/rush/memory/retrieval.py:719-849`) calls it at `retrieval.py:814`, inside
  `if cache_write:` (`retrieval.py:812`), and only for candidates that had no cached vector,
  after `embed_fn` (default `rush.memory.embeddings.embed_chunks`) returned vectors
  (`retrieval.py:809`).
  - When `embed_config` is `None`, `hybrid_candidates` returns
    `{"available": False, "reason": "no embedding engine configured"}` (`retrieval.py:754`)
    before any vector work.
  - Engine failures (`EmbeddingEngineUnavailable` at `retrieval.py:823`,
    `EmbeddingResponseError` at `:825`) also return `available: False`. When the failure comes
    from the query embedding, vectors already persisted earlier in the same call stay persisted.
- **Engine client.** `embed_chunks` (`src/rush/memory/embeddings.py:50`) POSTs to
  `{endpoint}/api/embed` through `urllib.request.urlopen` (`embeddings.py:74`). Any connection or
  URL failure becomes `EmbeddingEngineUnavailable` (`embeddings.py:77`).
- **Consumer.** `TypedArtifactStore.get_embedding` (`store.py:1228-1254`), called at
  `retrieval.py:795` to reuse a cached vector keyed by artifact, version, content hash, model
  digest and chunking version.
- **Deleter.** `TypedArtifactStore.delete_batch` apply runs
  `DELETE FROM memory_embeddings WHERE artifact_id = ?` (`store.py:1027`).
- **Call chain above the writer.**
  - `hybrid_page` (`retrieval.py:852-975`) is the only production caller of
    `hybrid_candidates` (`retrieval.py:901`). On `available: False` it returns a lexical page
    labelled `code: "E_EMBEDDING_UNAVAILABLE"` (`retrieval.py:931`).
  - `MemoryTool._compact_query` (`src/rush/tools/memory.py:576-748`) is the only production
    caller of `hybrid_page` (`tools/memory.py:704`). It reaches that call only when
    `retrieval == "hybrid"` (`tools/memory.py:686`) and `granted.network` is true (checked at
    `tools/memory.py:687`, otherwise `E_PERMISSION`). It builds an `EmbeddingConfig` only when
    `embedding_endpoint`, `embedding_model` and `embedding_model_digest` are all non-empty
    (`tools/memory.py:697`).
  - `_compact_query` runs only for `ask`/`recall`/`list` calls that pass a `request`
    (`tools/memory.py:398`, `:419`, `:440`, each branching on `request is not None` at `:414`,
    `:435`, `:456`).

### Callers

- **Production caller chain.** `MemoryTool._compact_query` → `hybrid_page` → `hybrid_candidates`
  → `put_embedding`. There are no other production callers of any of the three retrieval
  functions.
- **Routes that can reach `_compact_query` with an embedding engine.**
  - **MCP.** `rush_memory` with `operation` set to `ask`, `recall` or `list`, `request` set to
    `{"view": "compact", "retrieval": "hybrid", "embedding_endpoint": ..., "embedding_model":
    ..., "embedding_model_digest": ...}`, plus `allow_network` and `allow_cache_write`.
  - **In-process.** `MemoryTool().run(..., request=...)` or `__call__`.
- **Routes that cannot.**
  - **CLI.** `memory_ask_cmd` (HEAD `src/rush/cli.py:2549`), `memory_recall_cmd` (HEAD
    `cli.py:2578`) and `memory_list_cmd` (HEAD `cli.py:2612`) call `MemoryTool().run` without a
    `request`, so they always take the legacy `_query` path. The MC14 leaf loop (HEAD
    `cli.py:2956`) does not include `ask`, `recall` or `list`. The demonstration's
    `rush memory recall --help` output shows no `--input` option.
  - **Dashboard `memory_query` action.** `_dispatch_memory_query`
    (`src/rush/dashboard/server.py:2733`) accepts `retrieval: "hybrid"` behind a `network` grant
    (`server.py:2771-2773`). It copies only `limit`, `max_tokens`, `max_bytes`, `encoding` and
    `cursor` into the request (`server.py:2775`), never an embedding key, so the call always
    reaches `hybrid_candidates` with `embed_config=None`. The dashboard's memory browse uses the
    legacy `list` (`server.py:3594`).
  - **Benchmark.** The `hybrid` variant sets `request["retrieval"] = "hybrid"` with no embedding
    keys (`scripts/benchmarks/run.py:206-207`).
  - **Memory-session bridge.** It permits only `receive`, `expand`, `related` and `resume`.
- **Test callers.**
  - `tests/test_memory_hybrid.py` calls `hybrid_candidates` and `hybrid_page` directly with an
    injected test-double engine, `_fixed_vector_adapter` (`:48`). That returns fixed vectors and
    is not a real engine.
  - `test_model_digest_change_invalidates_vectors` (`:243`) asserts that vectors are persisted
    with `cache_write`.
  - `test_read_only_hybrid_never_persists_vectors` (`:393`) asserts zero rows without
    `cache_write`.
  - `test_missing_engine_reports_lexical_fallback_explicitly` (`:156`) drives `MemoryTool`
    hybrid with `network` and no engine.
  - `tests/test_memory_retrieval.py:473`, in
    `test_persisted_attribution_columns_match_the_public_invocation_id_on_every_success_and_fallback_branch`
    (`:427`), sends a hybrid request without an engine.
  - `TypedArtifactStore.get_embedding` is called directly by tests at
    `tests/test_memory_hybrid.py:261`, `:298`, `:305`, `:324`, `:332`, `:354` and `:413`. These
    call sites sit inside `test_model_digest_change_invalidates_vectors` (`:243`) and
    `test_read_only_hybrid_never_persists_vectors` (`:393`). Its only production caller is
    `hybrid_candidates` (`src/rush/memory/retrieval.py:795`).
- **Callers of the deleter `TypedArtifactStore.delete_batch`** (`src/rush/memory/store.py:926`).
  - **Production.** Only `MemoryTool._run_delete` (`src/rush/tools/memory.py:2064-2220`, call at
    `:2174`). Apply mode requires `cache_write` (`tools/memory.py:2159-2167`). The routes into
    `_run_delete` are:
    - **CLI.** `rush memory delete --input FILE` (HEAD `src/rush/cli.py:2970`, entry
      `("delete", "delete")`).
    - **MCP.** `rush_memory` with `operation="delete"`.
    - **Dashboard.** `_dispatch_memory_delete` (`src/rush/dashboard/server.py:2460`, which calls
      `MemoryTool().run` at `:2500`).
    - **TUI.** HEAD `src/rush/tui.py:1502` and `:1541`.
  - **Tests.**
    - `tests/test_project_evidence.py:256`;
    - `tests/test_dashboard.py:803`, `:812` and `:827`;
    - `tests/test_memory_versions.py:406`, `:439`, `:450` and `:480`.

Caller listings, verbatim:

```text
$ grep -rn --include='*.py' -E '\bput_embedding\(' src scripts tests
src/rush/memory/store.py:1256:    def put_embedding(
src/rush/memory/retrieval.py:743:    call's ranking only and is never persisted (`TypedArtifactStore.put_embedding()` is only
src/rush/memory/retrieval.py:814:                    store.put_embedding(
$ graft callers put_embedding

put_embedding · method · src/rush/memory/store.py:L1256-L1286
  calls ← hybrid_candidates (src/rush/memory/retrieval.py:L719-L849)
$ grep -rn --include='*.py' -E '\bhybrid_candidates\(' src scripts tests
src/rush/memory/store.py:370:# `rush.memory.retrieval.hybrid_candidates()` owns all read/write logic; this module only
src/rush/memory/store.py:1266:        """MC12 §6.7: persists one vector. Always writes -- the caller (`hybrid_candidates()`)
src/rush/memory/retrieval.py:719:def hybrid_candidates(
src/rush/memory/retrieval.py:877:    """MC12 §6.7 hybrid retrieval page: `hybrid_candidates()`'s RRF-fused ranking, applying
src/rush/memory/retrieval.py:901:    fused = hybrid_candidates(
tests/test_memory_hybrid.py:101:    fused_first = hybrid_candidates(
tests/test_memory_hybrid.py:109:    fused_second = hybrid_candidates(
tests/test_memory_hybrid.py:140:    fused = hybrid_candidates(
tests/test_memory_hybrid.py:208:    under_cap = hybrid_candidates(
tests/test_memory_hybrid.py:220:    truncated = hybrid_candidates(
tests/test_memory_hybrid.py:251:    hybrid_candidates(
tests/test_memory_hybrid.py:270:    hybrid_candidates(
tests/test_memory_hybrid.py:288:    hybrid_candidates(
tests/test_memory_hybrid.py:342:    hybrid_candidates(
tests/test_memory_hybrid.py:400:    fused = hybrid_candidates(
$ graft callers hybrid_candidates

hybrid_candidates · function · src/rush/memory/retrieval.py:L719-L849
  calls ← hybrid_page (src/rush/memory/retrieval.py:L852-L975)
  calls ← test_candidate_truncation_reported_when_scan_cap_hit (tests/test_memory_hybrid.py:L194-L240)
  calls ← test_denied_source_never_sent_to_endpoint (tests/test_memory_hybrid.py:L131-L153)
  calls ← test_model_digest_change_invalidates_vectors (tests/test_memory_hybrid.py:L243-L360)
  calls ← test_read_only_hybrid_never_persists_vectors (tests/test_memory_hybrid.py:L393-L424)
  calls ← test_rrf_order_is_deterministic (tests/test_memory_hybrid.py:L83-L128)
$ grep -rn --include='*.py' -E '\bhybrid_page\(' src scripts tests
src/rush/tools/memory.py:704:            page = hybrid_page(
src/rush/memory/retrieval.py:206:    `expand_artifact()`/`hybrid_page()`, not reused from `request_id`.
src/rush/memory/retrieval.py:852:def hybrid_page(
tests/test_memory_hybrid.py:69:    page = hybrid_page(
tests/test_memory_hybrid.py:160:    page = hybrid_page(
tests/test_memory_hybrid.py:232:    page = hybrid_page(
$ graft callers hybrid_page

hybrid_page · function · src/rush/memory/retrieval.py:L852-L975
  calls ← _compact_query (src/rush/tools/memory.py:L576-L748)
  calls ← test_candidate_truncation_reported_when_scan_cap_hit (tests/test_memory_hybrid.py:L194-L240)
  calls ← test_hybrid_retrieves_lexical_paraphrase_miss (tests/test_memory_hybrid.py:L56-L80)
  calls ← test_missing_engine_reports_lexical_fallback_explicitly (tests/test_memory_hybrid.py:L156-L191)
```

Additional caller listings for `get_embedding` and `delete_batch`, verbatim, produced by
`callers_round1.sh embeddings` (Appendix B). `[grep exit N]` records grep's exit status.

```text
$ grep -rn --include='*.py' -E '\bget_embedding\(' src scripts tests
src/rush/memory/store.py:1228:    def get_embedding(
src/rush/memory/retrieval.py:795:        cached = store.get_embedding(
tests/test_memory_hybrid.py:261:    assert store.get_embedding(
tests/test_memory_hybrid.py:298:    assert store.get_embedding(
tests/test_memory_hybrid.py:305:    assert store.get_embedding(
tests/test_memory_hybrid.py:324:    assert store.get_embedding(
tests/test_memory_hybrid.py:332:        store.get_embedding(
tests/test_memory_hybrid.py:354:    assert store.get_embedding(
tests/test_memory_hybrid.py:413:        store.get_embedding(
[grep exit 0]
$ graft callers get_embedding

get_embedding · method · src/rush/memory/store.py:L1228-L1254
  calls ← hybrid_candidates (src/rush/memory/retrieval.py:L719-L849)
  calls ← test_model_digest_change_invalidates_vectors (tests/test_memory_hybrid.py:L243-L360)
  calls ← test_read_only_hybrid_never_persists_vectors (tests/test_memory_hybrid.py:L393-L424)
$ grep -rn --include='*.py' -E '\bdelete_batch\(' src scripts tests
src/rush/tools/memory.py:2174:            result = store.delete_batch(
src/rush/memory/store.py:52:    """Raised by `delete_batch()` when a batch member's actual `subject` doesn't match
src/rush/memory/store.py:388:# transaction as the effect itself (write()/edit()/archive()/delete_batch()/promote()/
src/rush/memory/store.py:912:        """P65-07.2/.3: minimal, content-free provenance for artifacts `delete_batch()`
src/rush/memory/store.py:926:    def delete_batch(
src/rush/memory/store.py:1068:        Mirrors `delete_batch()`'s validate-then-write shape but for one id: verifies
src/rush/memory/store.py:1169:        gets its own audit row, exactly mirroring `edit()`/`delete_batch()`'s atomicity.
src/rush/memory/store.py:1340:        `subject` column `delete_batch()`'s tombstone rows use for provenance (mirrors
src/rush/memory/store.py:2125:        compare-and-swap contract `edit()`/`archive()`/`delete_batch()`
tests/test_project_evidence.py:256:    store.delete_batch(
tests/test_dashboard.py:803:    store.delete_batch(
tests/test_dashboard.py:812:    store.delete_batch(
tests/test_dashboard.py:827:    store.delete_batch(
tests/test_memory_versions.py:348:    `edit()`/`archive()`/`delete_batch()` already enforce (P69-07). A wrong
tests/test_memory_versions.py:406:        store.delete_batch(
tests/test_memory_versions.py:429:    receipt id mapping) makes `delete_batch()` persist one real receipt per
tests/test_memory_versions.py:439:    preview = store.delete_batch(
tests/test_memory_versions.py:450:    store.delete_batch(
tests/test_memory_versions.py:480:    store.delete_batch(
[grep exit 0]
$ graft callers delete_batch

delete_batch · method · src/rush/memory/store.py:L926-L1053
  calls ← _run_delete (src/rush/tools/memory.py:L2064-L2220)
  calls ← test_crash_recovery_for_delete_uses_tombstone_not_object_lookup (tests/test_dashboard.py:L824-L849)
  calls ← test_recovery_receipt_for_delete_exists_only_after_real_commit_not_before (tests/test_dashboard.py:L797-L821)
  calls ← test_delete_batch_legacy_scalar_receipt_id_still_writes_one_whole_batch_receipt (tests/test_memory_versions.py:L470-L491)
  calls ← test_delete_batch_with_one_wrong_owner_member_writes_zero_rows (tests/test_memory_versions.py:L398-L422)
  calls ← test_delete_batch_writes_one_distinct_receipt_per_target_from_mapping (tests/test_memory_versions.py:L425-L467)
  calls ← test_deleted_memory_artifact_reference_remains_discoverable_with_provenance (tests/test_project_evidence.py:L240-L268)
```

### Trigger

A compact hybrid retrieval request from an MCP client or in-process caller that carries an
embedding engine configuration.

### Grant and capability prerequisites

- `network` grant: MCP `allow_network: true`. Without it the call returns `E_PERMISSION`
  ("memory recall retrieval=hybrid requires network.").
- `cache_write` grant: MCP `allow_cache_write: true`. Without it vectors are computed for that
  call's ranking only and never persisted.
- `request.view == "compact"`, `request.retrieval == "hybrid"`, a non-empty `session_allowlist`,
  and a subject. `ask` and `recall` also require a query.
- `embedding_endpoint`, `embedding_model` and `embedding_model_digest`, all non-empty.
  `embedding_chunking_version` defaults to `mc12-v1`.
- A reachable Ollama-compatible `/api/embed` engine that returns one finite, non-zero,
  consistent-dimension vector per input.
- At least one authorized candidate whose vector for that exact key is not already cached.

### Controlled demonstration

The fixture is a fresh project with one artifact from source `demo-src`. The transcript shows
`memory_embeddings` at 0 rows before and after each of the following:

- the CLI `recall --help`, which shows no request input;
- a hybrid recall through the MCP wrapper without `network`, which returns `E_PERMISSION`;
- a hybrid recall with `network` and `cache_write` but no engine, which returns
  `E_EMBEDDING_UNAVAILABLE` with `retrieval: "lexical"` and the reason
  "no embedding engine configured";
- a hybrid recall with `network`, `cache_write` and an engine configured at an unreachable
  endpoint, which returns `E_EMBEDDING_UNAVAILABLE` with the `urllib` error as the reason.

The second and third calls are real production outcomes of the only writer's call chain. The
positive write path was not demonstrated against a real engine, because doing so needs network
access or a local model server. It is characterized only by `tests/test_memory_hybrid.py` with
the injected test double; that suite passes, as shown in the test output above.

```text
===== memory_embeddings =====
$ rush memory write domain_knowledge demo-src --content '{"text": "alpha embedding candidate"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-E>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "alpha embedding candidate"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/embeddings"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_embeddings;"
0
[exit 0]
$ rush memory recall --help
Usage: rush memory recall [OPTIONS] {active_context|episodic|preference|failur
                          e|architectural_decision|domain_knowledge|skill_patt
                          ern} QUERY

  Recall memory artifacts, scoped to an explicit session allowlist.

Options:
  --session TEXT  Source to scope this query to; repeat for multiple. Fail-
                  closed if omitted.
  --json          Print raw ToolResult JSON.
  -h, --help      Show this message and exit.
[exit 0]
$ cat hybrid_no_network.json
{
  "operation": "recall",
  "subject": "domain_knowledge",
  "query": "alpha",
  "session_allowlist": [
    "demo-src"
  ],
  "request": {
    "view": "compact",
    "retrieval": "hybrid"
  },
  "allow_cache_write": true
}
$ python mcp_call.py hybrid_no_network.json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "fail",
  "duration_ms": <MS>,
  "summary": "memory recall returned E_PERMISSION.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "recall",
    "code": "E_PERMISSION",
    "data": {
      "message": "memory recall retrieval=hybrid requires network."
    }
  },
  "metadata": {
    "operation": "recall"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_embeddings;"
0
[exit 0]
$ cat hybrid_no_engine.json
{
  "operation": "recall",
  "subject": "domain_knowledge",
  "query": "alpha",
  "session_allowlist": [
    "demo-src"
  ],
  "request": {
    "view": "compact",
    "retrieval": "hybrid"
  },
  "allow_network": true,
  "allow_cache_write": true
}
$ python mcp_call.py hybrid_no_engine.json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "warn",
  "duration_ms": <MS>,
  "summary": "memory recall returned E_EMBEDDING_UNAVAILABLE.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "recall",
    "code": "E_EMBEDDING_UNAVAILABLE",
    "data": {
      "items": [
        {
          "id": "<ID-E>",
          "version": 1,
          "excerpt": "alpha embedding candidate",
          "source": "demo-src",
          "trust": "EXTERNAL_WRITE",
          "freshness": "fresh",
          "relations": []
        }
      ],
      "next_cursor": null,
      "complete": true,
      "tokens": <TOKENS>,
      "bytes": 247,
      "encoding": "cl100k_base",
      "retrieval": "lexical",
      "embedding_status": "skipped",
      "hybrid_unavailable_reason": "no embedding engine configured"
    }
  },
  "metadata": {
    "operation": "recall"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_embeddings;"
0
[exit 0]
$ cat hybrid_unavailable_engine.json
{
  "operation": "recall",
  "subject": "domain_knowledge",
  "query": "alpha",
  "session_allowlist": [
    "demo-src"
  ],
  "request": {
    "view": "compact",
    "retrieval": "hybrid",
    "embedding_endpoint": "unregistered-scheme://embedding-engine",
    "embedding_model": "demo-model",
    "embedding_model_digest": "demo-digest"
  },
  "allow_network": true,
  "allow_cache_write": true
}
$ python mcp_call.py hybrid_unavailable_engine.json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "warn",
  "duration_ms": <MS>,
  "summary": "memory recall returned E_EMBEDDING_UNAVAILABLE.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "recall",
    "code": "E_EMBEDDING_UNAVAILABLE",
    "data": {
      "items": [
        {
          "id": "<ID-E>",
          "version": 1,
          "excerpt": "alpha embedding candidate",
          "source": "demo-src",
          "trust": "EXTERNAL_WRITE",
          "freshness": "fresh",
          "relations": []
        }
      ],
      "next_cursor": null,
      "complete": true,
      "tokens": <TOKENS>,
      "bytes": 247,
      "encoding": "cl100k_base",
      "retrieval": "lexical",
      "embedding_status": "skipped",
      "hybrid_unavailable_reason": "<urlopen error unknown url type: unregistered-scheme>"
    }
  },
  "metadata": {
    "operation": "recall"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_embeddings;"
0
[exit 0]
```

### Additional demonstration: configured engine with no authorized candidate

This fixture is a fresh project with one artifact from source `demo-src`. A hybrid recall
through the MCP wrapper names only `other-src` in its allowlist, and carries the grants and a
configured, unreachable engine. The call returns `OK` with `retrieval: "hybrid"` and no items,
and `memory_embeddings` stays at 0. The engine is never called, because `hybrid_candidates`
returns at `retrieval.py:773-778` before any embedding.

```text
===== memory_embeddings: configured engine, no authorized candidate =====
$ rush memory write domain_knowledge demo-src --content '{"text": "alpha embedding candidate"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-E>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "alpha embedding candidate"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/embeddings"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ cat hybrid_no_candidate.json
{
  "operation": "recall",
  "subject": "domain_knowledge",
  "query": "alpha",
  "session_allowlist": [
    "other-src"
  ],
  "request": {
    "view": "compact",
    "retrieval": "hybrid",
    "embedding_endpoint": "unregistered-scheme://embedding-engine",
    "embedding_model": "demo-model",
    "embedding_model_digest": "demo-digest"
  },
  "allow_network": true,
  "allow_cache_write": true
}
$ python mcp_call.py hybrid_no_candidate.json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory recall returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "recall",
    "code": "OK",
    "data": {
      "items": [],
      "next_cursor": null,
      "complete": true,
      "tokens": <TOKENS>,
      "bytes": 72,
      "encoding": "cl100k_base",
      "retrieval": "hybrid",
      "candidates_truncated": false
    }
  },
  "metadata": {
    "operation": "recall"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_embeddings;"
0
[exit 0]
```

### Limitations

- No real embedding engine was run, so no vector was written in the demonstration. The persist
  path is evidenced only by the test double in `tests/test_memory_hybrid.py`.
- The unreachable-engine case used an unregistered URL scheme, which `urllib` rejects without a
  socket. DNS failure, connection refused, timeout and malformed-response engines were not
  exercised against `embed_chunks` here. Malformed-response validation is covered by
  `test_nonfinite_wrong_dimension_or_truncated_embedding_rejected`, which calls
  `validate_embedding_response` directly.
- The dashboard `memory_query` hybrid route was established by reading the source, not by
  running it. It has no hybrid test: `grep -rn memory_query tests` finds no hybrid use.
- The MCP route ran in-process through the HEAD `make_tool_wrapper`, not over stdio.

## Finding 3: `memory_behavior_success`

### Conclusion

The writer exists and is transactional, but no production code calls it.
`record_behavior_success` is called only by tests. A store produced by the shipped
application therefore has zero rows in this table no matter how many checks, tests or sandboxed
patch attempts have passed. Zero rows here shows neither that anything failed nor that anything
was learned. Every reader of this table reports "no recorded baseline" for every behavior; for
example, `last_success_diagnose` returns `baseline_ref: null`.

### Producer and consumers

- **Producer.** `TypedArtifactStore.write_pass` (`src/rush/memory/store.py:1794-1832`) holds
  the table's only `INSERT INTO memory_behavior_success` (`store.py:1815`). In the same
  `BEGIN IMMEDIATE` transaction it inserts the passing observation artifact and advances the
  `(namespace, behavior_id, runtime_digest)` pointer.
- **Its only caller.** `rush.memory.experience.record_behavior_success`
  (`src/rush/memory/experience.py:440-477`, call at `experience.py:475`).
- **Consumers.**
  - `TypedArtifactStore.get_behavior_success` (`store.py:1834-1846`) is called by
    `compare_last_success` (`experience.py:480-575`, at `experience.py:503`).
  - `TypedArtifactStore.find_any_behavior_success` (`store.py:1848-1862`) is called:
    - by `compare_last_success` when `historical` is true (`experience.py:508`);
    - by `rush.memory.handoff.prepare_handoff` (`src/rush/memory/handoff.py:107`), but only
      when `intent_behavior_ids` is non-empty.
  - The only production code that passes `intent_behavior_ids` is
    `rush.memory.transport.dispatch_handoff` (`src/rush/memory/transport.py:166-254`, argument at
    `transport.py:212`). A `grep -rn "dispatch_handoff("` over `src`, `scripts` and `tests` finds
    no caller of that function. Every call site with that name calls the unrelated
    `rush.workflows.project_run.dispatch_handoff`.
  - `MemoryTool._handoff` (`tools/memory.py:1961`) and `project_run.build_handoff` (HEAD
    `src/rush/workflows/project_run.py:2229`) call `prepare_handoff` without
    `intent_behavior_ids`.
- **Tool entry for the reader.** `MemoryTool._last_success_diagnose`
  (`tools/memory.py:1804-1853`, call at `:1847`, dispatch at `:524`) has no permission gate.
- **An executed pass that does not advance the pointer.** `rush.memory.verification.verify_attempt`
  (`src/rush/memory/verification.py:77`) records a passing sandbox verification through
  `write_observation` with `evidence_kind="sandbox_verification"` (`verification.py:157`). It
  never calls `record_behavior_success`. This is a statement about current source, not a
  proposal.

### Callers

- **Production callers of `record_behavior_success`.** None. `grep` finds only the definition
  under `src` and no call under `scripts`.
- **Production callers of `write_pass`.** Only `record_behavior_success`
  (`experience.py:475`).
- **Reader routes.**
  - **CLI.** `rush memory last-success-diagnose --input FILE` (HEAD `src/rush/cli.py:2967`).
  - **MCP.** `rush_memory` with `operation="last_success_diagnose"`.
  - **Benchmark.** `scripts/benchmarks/memory.py:937`.
- **Test callers of `record_behavior_success`.**
  - `tests/test_memory_last_success.py` at lines 31, 53, 93, 112, 157, 181, 236 and 275, inside:
    - `test_success_is_per_behavior_and_environment` (`:30`);
    - `test_skipped_or_cached_check_cannot_advance_success` (`:71`);
    - `test_code_dependency_and_config_changes_are_distinguished` (`:111`);
    - `test_unavailable_engine_is_not_application_regression` (`:156`);
    - `test_only_controlled_reproduction_confirms_cause` (`:180`);
    - `test_later_failure_does_not_destroy_last_success` (`:235`);
    - `test_memory_tool_last_success_diagnose_operation_returns_diagnosis` (`:272`).
  - `tests/test_memory_handoff.py:505`, inside
    `test_guest_intent_and_last_success_survive_readback`.

Caller listings, verbatim:

```text
$ grep -rn --include='*.py' -E '\bwrite_pass\(' src scripts tests
src/rush/memory/store.py:326:# never a second source of truth -- the only writer is `TypedArtifactStore.write_pass()`,
src/rush/memory/store.py:1693:        """Shared pre-insert step for `write()`/`write_pass()`: enforces Invariant 1
src/rush/memory/store.py:1724:        """Shared insert body for `write()`/`write_pass()`: the artifact row plus its
src/rush/memory/store.py:1794:    def write_pass(
src/rush/memory/experience.py:450:    `TypedArtifactStore.write_pass()` -- never a separate/parallel write path. This is the
src/rush/memory/experience.py:475:    return TypedArtifactStore(project_root).write_pass(
$ graft callers write_pass

write_pass · method · src/rush/memory/store.py:L1794-L1832
  no indexed callers — the graph has no incoming call/reference edges for this symbol as written. Check the name (try the bare symbol, or "Type.method"), or find its uses with graft grep "write_pass". Fall back to raw grep -rn only for unindexed files
$ grep -rn --include='*.py' -E '\brecord_behavior_success\(' src scripts tests
src/rush/memory/experience.py:440:def record_behavior_success(
tests/test_memory_handoff.py:505:    passed = record_behavior_success(
tests/test_memory_last_success.py:31:    passed = record_behavior_success(
tests/test_memory_last_success.py:53:    record_behavior_success(
tests/test_memory_last_success.py:93:    passed = record_behavior_success(
tests/test_memory_last_success.py:112:    record_behavior_success(
tests/test_memory_last_success.py:157:    record_behavior_success(
tests/test_memory_last_success.py:181:    record_behavior_success(
tests/test_memory_last_success.py:236:    passed = record_behavior_success(
tests/test_memory_last_success.py:275:    record_behavior_success(
$ graft callers record_behavior_success

record_behavior_success · function · src/rush/memory/experience.py:L440-L477
  calls ← test_guest_intent_and_last_success_survive_readback (tests/test_memory_handoff.py:L492-L556)
  calls ← test_code_dependency_and_config_changes_are_distinguished (tests/test_memory_last_success.py:L111-L153)
  calls ← test_later_failure_does_not_destroy_last_success (tests/test_memory_last_success.py:L235-L269)
  calls ← test_memory_tool_last_success_diagnose_operation_returns_diagnosis (tests/test_memory_last_success.py:L272-L295)
  calls ← test_only_controlled_reproduction_confirms_cause (tests/test_memory_last_success.py:L180-L232)
  calls ← test_skipped_or_cached_check_cannot_advance_success (tests/test_memory_last_success.py:L71-L108)
  calls ← test_success_is_per_behavior_and_environment (tests/test_memory_last_success.py:L30-L68)
  calls ← test_unavailable_engine_is_not_application_regression (tests/test_memory_last_success.py:L156-L177)
$ grep -rn --include='*.py' -E '\bget_behavior_success\(' src scripts tests
src/rush/memory/store.py:1834:    def get_behavior_success(
src/rush/memory/experience.py:503:    pointer = store.get_behavior_success(
tests/test_memory_handoff.py:552:    assert store.get_behavior_success(
tests/test_memory_last_success.py:48:    assert store.get_behavior_success(
tests/test_memory_last_success.py:59:    assert store.get_behavior_success(
tests/test_memory_last_success.py:64:        store.get_behavior_success(
tests/test_memory_last_success.py:85:        store.get_behavior_success(
tests/test_memory_last_success.py:106:    assert store.get_behavior_success(
tests/test_memory_last_success.py:257:    assert store.get_behavior_success(
$ grep -rn --include='*.py' -E '\bfind_any_behavior_success\(' src scripts tests
src/rush/memory/store.py:1848:    def find_any_behavior_success(
src/rush/memory/handoff.py:107:            pointer = store.find_any_behavior_success(
src/rush/memory/experience.py:508:        pointer = store.find_any_behavior_success(
$ grep -rn --include='*.py' -E '\bcompare_last_success\(' src scripts tests
src/rush/tools/memory.py:1847:        result = compare_last_success(
src/rush/memory/experience.py:480:def compare_last_success(
tests/test_memory_last_success.py:119:    code_only = compare_last_success(
tests/test_memory_last_success.py:129:    dependency_only = compare_last_success(
tests/test_memory_last_success.py:142:    config_only = compare_last_success(
tests/test_memory_last_success.py:164:    result = compare_last_success(
tests/test_memory_last_success.py:188:    diagnosis = compare_last_success(
tests/test_memory_last_success.py:209:    still_candidate = compare_last_success(
tests/test_memory_last_success.py:227:    confirmed = compare_last_success(
tests/test_memory_last_success.py:261:    diagnosis = compare_last_success(
$ graft callers compare_last_success

compare_last_success · function · src/rush/memory/experience.py:L480-L575
  calls ← _last_success_diagnose (src/rush/tools/memory.py:L1804-L1853)
  calls ← test_code_dependency_and_config_changes_are_distinguished (tests/test_memory_last_success.py:L111-L153)
  calls ← test_later_failure_does_not_destroy_last_success (tests/test_memory_last_success.py:L235-L269)
  calls ← test_only_controlled_reproduction_confirms_cause (tests/test_memory_last_success.py:L180-L232)
  calls ← test_unavailable_engine_is_not_application_regression (tests/test_memory_last_success.py:L156-L177)
```

Additional `graft callers` listings for the two readers, verbatim, produced by
`callers_round1.sh behavior` (Appendix B). The grep listings for both readers are in the block
above:

```text
$ graft callers get_behavior_success

get_behavior_success · method · src/rush/memory/store.py:L1834-L1846
  calls ← compare_last_success (src/rush/memory/experience.py:L480-L575)
  calls ← test_guest_intent_and_last_success_survive_readback (tests/test_memory_handoff.py:L492-L556)
  calls ← test_later_failure_does_not_destroy_last_success (tests/test_memory_last_success.py:L235-L269)
  calls ← test_skipped_or_cached_check_cannot_advance_success (tests/test_memory_last_success.py:L71-L108)
  calls ← test_success_is_per_behavior_and_environment (tests/test_memory_last_success.py:L30-L68)
$ graft callers find_any_behavior_success

find_any_behavior_success · method · src/rush/memory/store.py:L1848-L1862
  calls ← compare_last_success (src/rush/memory/experience.py:L480-L575)
  calls ← prepare_handoff (src/rush/memory/handoff.py:L64-L148)
```

### Trigger

A direct Python call to `record_behavior_success`. No CLI command, MCP operation, dashboard
action, workflow or benchmark issues that call.

### Grant and capability prerequisites

None at the function level. `record_behavior_success` takes no permission argument. It is not
reachable from any tool surface, so no grant can enable it. Reading the pointer through
`last_success_diagnose` needs no grant either.

### Controlled demonstration

The fixture is a fresh project with one seed artifact, so the store exists. The transcript
shows:

- `memory_behavior_success` has 0 rows;
- `rush memory last-success-diagnose` returns `baseline_ref: null` and `cause_state:
  "candidate"`, both for the exact environment and with `historical: true`;
- the count is still 0 afterwards, so the reader does not write.

The writer's behavior when it is called directly is characterized by
`tests/test_memory_last_success.py`, which passes; see the test output above.

```text
===== memory_behavior_success =====
$ rush memory write domain_knowledge demo-src --content '{"text": "seed so the store exists"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-S>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "seed so the store exists"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/behavior"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_behavior_success;"
0
[exit 0]
$ cat diagnose.json
{
  "behavior_id": "demo-behavior",
  "conditions": {
    "runtime": "cpython/3.12",
    "platform": "darwin-arm64"
  }
}
$ rush memory last-success-diagnose --input diagnose.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory last_success_diagnose returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "last_success_diagnose",
    "code": "OK",
    "data": {
      "baseline_ref": null,
      "code_changes": null,
      "config_changes": null,
      "dependency_changes": null,
      "engine_changes": null,
      "environment_compatible": true,
      "cause_state": "candidate"
    }
  },
  "metadata": {
    "operation": "last_success_diagnose"
  }
}
[exit 0]
$ cat diagnose_historical.json
{
  "behavior_id": "demo-behavior",
  "conditions": {
    "runtime": "cpython/3.12",
    "platform": "darwin-arm64"
  },
  "historical": true
}
$ rush memory last-success-diagnose --input diagnose_historical.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory last_success_diagnose returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "last_success_diagnose",
    "code": "OK",
    "data": {
      "baseline_ref": null,
      "code_changes": null,
      "config_changes": null,
      "dependency_changes": null,
      "engine_changes": null,
      "environment_compatible": true,
      "cause_state": "candidate"
    }
  },
  "metadata": {
    "operation": "last_success_diagnose"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_behavior_success;"
0
[exit 0]
```

### Limitations

- A production writer cannot be demonstrated because none exists. The writer's semantics
  (per-environment pointer, skip or cache never advancing it, later failure never erasing it)
  are evidenced only by tests that call it directly.
- `verify_attempt` was not executed in the demonstration. It needs the `cache_write`,
  `artifact_write` and `build` grants, a clean git sandbox and declared checks. Its
  observation-only recording is established by reading `verification.py`.
- `last_success_diagnose` returns the same "no baseline" payload for a behavior that never
  passed and for one that passed without being recorded, so its output alone cannot tell those
  two cases apart.

## Finding 4: `memory_handoff_receipts`

### Conclusion

A receipt row exists only after a receiver proves it read exact stored bytes. It must send
`receive` with an `ack` entry whose SHA-256 digest matches the stored version, under a valid
handoff session id and raw capability. None of the following writes a receipt: preparing a
handoff, receiving a delta without `ack`, an ACK with a wrong digest, or the scan-handoff
workflow's own "acknowledge" step, which changes the scan handoff's state instead.

A store with zero receipt rows has therefore never completed a successful read-back ACK. A
session row exists after a prepare alone, as the main demonstration shows, so a store with
session rows and zero receipts shows only that no ACK succeeded under those sessions. It does
not show that anything was delivered to, or read by, a receiver. An attempt leaves the table
without a new row when it ends in any of these outcomes:

- a prepare with no later ACK: the session is created (`src/rush/tools/memory.py:1961`) and no
  receipt is written;
- `receive` with no `ack`, or with an empty `ack` list: `_receive` calls `acknowledge_readback`
  only when `ack` is non-empty (`tools/memory.py:2047`);
- `receive` request validation fails with `E_INPUT`: no request, an unknown key, a missing
  `session_id` or `capability`, or a wrongly typed `cursor`, `page_size` or `ack`
  (`tools/memory.py:2001-2044`);
- an unknown or revoked session, a wrong capability, or an expired session: `E_PERMISSION`
  (`src/rush/memory/handoff.py:166-177`);
- an `ack` entry without a string `id`, an integer `version` and a string `digest`: `E_INPUT`
  (`handoff.py:329-338`);
- an `ack` entry naming an artifact not in the session's `granted_ids`: `E_PERMISSION`
  (`handoff.py:339-343`);
- an `ack` entry naming a version that is not in `memory_artifact_versions`: `E_VERSION`
  (`src/rush/memory/store.py:2041-2045`, mapped at `handoff.py:347-348`);
- an `ack` entry whose digest does not match the stored bytes: `E_VERSION`
  (`store.py:2049-2053`);
- an `ack` element that is not a JSON object: `acknowledge_readback` calls `entry.get` on it
  (`handoff.py:326`) and raises `AttributeError`. `_receive` catches only `HandoffError`
  (`tools/memory.py:2058`), so the CLI call ends with an uncaught traceback and exit 1. The
  additional demonstration in this finding shows this. It is recorded as a finding only;
- an `ack` `version` too large for SQLite, for example `2**70`:
  - it passes the entry checks at `handoff.py:329-338`;
  - the version lookup `SELECT` at `store.py:2036-2040` then raises an uncaught
    `OverflowError: Python int too large to convert to SQLite INTEGER`, inside the receipt
    transaction and before any row is written;
  - `_receive` catches only `HandoffError` (`tools/memory.py:2058`), so the CLI call ends with a
    traceback and exit 1, with 0 receipt rows;
  - the round-2 demonstration in this finding shows this;
  - this is a product-defect finding only, and it is not described as planned or tracked;
- the scan-handoff `acknowledge` step (HEAD `src/rush/workflows/project_run.py:2499-2527`);
- `handoff` actions `dispatch` and `status`: `E_UNAVAILABLE` (`tools/memory.py:1904-1913`).

One bad entry in a multi-entry `ack` raises inside the receipt transaction
(`store.py:2042`, `store.py:2050`), so no entry in that call is written. That shows neither
that handoffs failed nor that a receiver used the content.

### Producer and consumers

- **Producer.** `TypedArtifactStore.acknowledge_handoff` (`src/rush/memory/store.py:2010-2067`)
  holds the table's only `INSERT INTO memory_handoff_receipts` (`store.py:2058`).
  - Before writing any row, it checks every `(artifact_id, version, digest)` triple against
    `memory_artifact_versions`: the version must exist, and the digest must equal the SHA-256 of
    that version's stored content.
  - One bad entry raises `VersionConflictError` and rolls the whole transaction back.
  - A replayed ACK for the same or a lower version, with a correct digest, still passes the same
    version and digest checks (`store.py:2041-2053`). It then runs the upsert
    (`store.py:2057-2065`). For each artifact, the value written is the higher of the stored
    and replayed versions (`store.py:2054-2055`), and the conflict clause keeps
    `MAX(acknowledged_version, excluded.acknowledged_version)` (`store.py:2062`). The replay
    therefore leaves the row count and `acknowledged_version` unchanged, but rewrites `updated_at`
    to the replay's time (`store.py:2063`). The additional demonstration in this finding shows a
    same-version replay: 1 row before and after, `acknowledged_version` 1 before and after, and
    a later `updated_at`.
- **Its only caller.** `rush.memory.handoff.acknowledge_readback`
  (`src/rush/memory/handoff.py:310-348`, call at `handoff.py:346`). It validates the session and
  capability through `load_session` (`handoff.py:151-187`), rejects artifacts that are not in
  `granted_ids` with `E_PERMISSION`, and maps `VersionConflictError` to `E_VERSION`.
- **Its only production caller.** `MemoryTool._receive` (`src/rush/tools/memory.py:1989-2062`,
  call at `tools/memory.py:2048`), and only when the request's `ack` list is non-empty.
- **Consumer.** `TypedArtifactStore.get_handoff_receipts` (`store.py:1999-2008`), used by
  `_bounded_session_delta` (`handoff.py:202`) to leave already-acknowledged versions out of the
  next delta.
- **Session producers (a prerequisite, not the receipt writer).**
  - `MemoryTool._handoff` with `action: "prepare"` (`tools/memory.py:1855-1987`). It checks
    `cache_write` at `:1873`, calls `prepare_handoff` at `:1961`, and returns `handoff_id` and
    `capability` at `:1982`.
  - `project_run.build_handoff` (HEAD `src/rush/workflows/project_run.py:2114`,
    `prepare_handoff` at HEAD `:2229`).
  - `rush.memory.transport.dispatch_handoff` (`transport.py:166`, `prepare_handoff` at `:205`),
    which has no callers.
- **Not receipt writers.**
  - `project_run.acknowledge_handoff` (HEAD `project_run.py:2499-2527`) is the scan-handoff
    `acknowledge` step. It validates the delivery nonce and persists the scan handoff with state
    `acknowledged`, and never touches `memory_handoff_receipts`.
  - `TypedArtifactStore.write_handoff_delivery_receipt` (`store.py:1965-1997`) writes
    `mutation_receipts` rows of kind `delivery_transition`.
  - `MemoryTool._handoff` actions `dispatch` and `status` return `E_UNAVAILABLE`
    (`tools/memory.py:1904-1913`), which this report records as a finding only.

### Callers

- **Production callers of `acknowledge_readback`.** Only `MemoryTool._receive`. The routes into
  `_receive` are:
  - **CLI.** `rush memory receive --input FILE` (HEAD `src/rush/cli.py:2969`).
  - **MCP.** `rush_memory` with `operation="receive"`.
  - **Memory-session bridge.** `build_memory_bridge_handler` (HEAD
    `src/rush/mcp_support/tool_registry.py:187`) injects the session id and capability and calls
    `receive` (HEAD `tool_registry.py:231`). It is served by `rush mcp serve --memory-session ID`
    (HEAD `cli.py:576`, `serve` at HEAD `cli.py:584`). `build_server` (HEAD `src/rush/mcp.py:41`)
    reads `RUSH_MEMORY_CAPABILITY` (HEAD `mcp.py:60`) and registers only the bridge tool (HEAD
    `mcp.py:68`).
  - The native transport's receiver prompt tells the receiving agent to call `receive` and to
    `expand` each version exactly before acknowledging it (`src/rush/memory/transport.py:291`).
- **Production callers of `store.acknowledge_handoff`.** Only `acknowledge_readback`
  (`handoff.py:346`). The other `acknowledge_handoff(` call sites are
  `rush.workflows.project_run.acknowledge_handoff`, a different function that writes no
  receipt:
  - `src/rush/tools/scan_handoff.py:252` and `:357`;
  - `scripts/benchmarks/run.py:650`;
  - `tests/test_scan_handoff.py:123`, `:249` and `:267`.
- **Benchmark script.** `scripts/benchmarks/memory.py` runs `handoff` prepare, then `receive`,
  `expand` and `receive` with `ack` (`memory.py:760-818`).
- **Test callers.**
  - `tests/test_memory_handoff.py` calls `acknowledge_readback` directly at lines 90, 135, 158,
    167, 212, 243 and 539.
  - `tests/test_memory_acceptance.py`, in
    `test_end_to_end_intent_repair_recipe_check_and_real_receiver` (`:169`), sends `receive` with
    `ack` through an MCP client on the restricted memory-session server (`:442`, `:448`).
  - `tests/test_benchmark_memory_agents.py`:
    - `test_handoff_score_requires_receiver_readback` (`:144`) runs a no-ACK episode;
    - `test_all_named_episodes_run_for_real` (`:217`) runs the benchmark episodes, including
      the ACK.

Caller listings, verbatim:

```text
$ grep -rn --include='*.py' -E '\backnowledge_readback\(' src scripts tests
src/rush/tools/memory.py:2048:                acknowledge_readback(
src/rush/memory/handoff.py:11:concept from a memory read-back acknowledgement here: only `acknowledge_readback()`, given the
src/rush/memory/handoff.py:310:def acknowledge_readback(
scripts/benchmarks/memory.py:495:    `acknowledge_readback()` accepted every entry's exact content digest) --
tests/test_memory_handoff.py:90:    acknowledge_readback(
tests/test_memory_handoff.py:135:    acknowledge_readback(
tests/test_memory_handoff.py:158:        acknowledge_readback(
tests/test_memory_handoff.py:167:    acknowledge_readback(
tests/test_memory_handoff.py:212:    acknowledge_readback(
tests/test_memory_handoff.py:243:        acknowledge_readback(
tests/test_memory_handoff.py:539:    acknowledge_readback(
$ graft callers acknowledge_readback

acknowledge_readback · function · src/rush/memory/handoff.py:L310-L348
  calls ← _receive (src/rush/tools/memory.py:L1989-L2062)
  calls ← test_delivery_ack_does_not_advance_cursor (tests/test_memory_handoff.py:L108-L141)
  calls ← test_delta_contains_only_changed_authorized_versions (tests/test_memory_handoff.py:L73-L105)
  calls ← test_guest_intent_and_last_success_survive_readback (tests/test_memory_handoff.py:L492-L556)
  calls ← test_partial_page_and_replay_are_atomic (tests/test_memory_handoff.py:L176-L221)
  calls ← test_receiver_reads_exact_versions_before_ack (tests/test_memory_handoff.py:L144-L173)
  calls ← test_scope_change_requires_new_snapshot (tests/test_memory_handoff.py:L224-L258)
$ grep -rn --include='*.py' -E '\backnowledge_handoff\(' src scripts tests
src/rush/tools/scan_handoff.py:252:            handoff = acknowledge_handoff(
src/rush/tools/scan_handoff.py:357:            handoff = acknowledge_handoff(project, handoff_id, delivery_nonce)
src/rush/memory/store.py:2010:    def acknowledge_handoff(
src/rush/memory/handoff.py:346:        return store.acknowledge_handoff(session_id, updates)
src/rush/workflows/project_run.py:2521:def acknowledge_handoff(
scripts/benchmarks/run.py:650:    acknowledge_handoff(
tests/test_scan_handoff.py:123:    acknowledged = acknowledge_handoff(
tests/test_scan_handoff.py:249:        acknowledge_handoff(
tests/test_scan_handoff.py:267:        acknowledge_handoff(
$ graft callers acknowledge_handoff

acknowledge_handoff · method · src/rush/memory/store.py:L2010-L2067
  calls ← acknowledge_readback (src/rush/memory/handoff.py:L310-L348)

acknowledge_handoff · function · src/rush/workflows/project_run.py:L2521-L2549
  calls ← run_project_journey (scripts/benchmarks/run.py:L514-L721)
  calls ← _dispatch (src/rush/tools/scan_handoff.py:L196-L271)
  calls ← _handle_request_unsafe (src/rush/tools/scan_handoff.py:L292-L375)
  calls ← test_acknowledge_before_dispatch_is_invalid_state (tests/test_scan_handoff.py:L258-L269)
  calls ← test_delivered_without_ack_remains_unacknowledged (tests/test_scan_handoff.py:L233-L255)
  calls ← test_prepare_dispatch_acknowledge_complete_round_trip (tests/test_scan_handoff.py:L106-L143)
$ grep -rn --include='*.py' -E '\bget_handoff_receipts\(' src scripts tests
src/rush/memory/store.py:1999:    def get_handoff_receipts(self, session_id: str) -> dict[str, int]:
src/rush/memory/store.py:2067:        return self.get_handoff_receipts(session_id)
src/rush/memory/handoff.py:202:    receipts = store.get_handoff_receipts(session_id)
tests/test_memory_handoff.py:133:    assert store.get_handoff_receipts(session.session_id) == {}
tests/test_memory_handoff.py:141:    assert store.get_handoff_receipts(session.session_id) == {"A1": 1}
tests/test_memory_handoff.py:165:    assert store.get_handoff_receipts(session.session_id) == {}
tests/test_memory_handoff.py:173:    assert store.get_handoff_receipts(session.session_id) == {"A1": 1}
tests/test_memory_handoff.py:221:    assert store.get_handoff_receipts(session.session_id) == {"A1": 1, "A2": 1}
tests/test_memory_acceptance.py:477:    assert store.get_handoff_receipts(session.session_id) == {
```

Additional caller listings, verbatim, produced by `callers_round1.sh handoff` (Appendix B):

- `graft callers get_handoff_receipts`;
- grep and `graft callers` for `dispatch_handoff`, covering both definitions;
- a grep for every module that imports `rush.memory.transport`.

The zero-callers evidence for `rush.memory.transport.dispatch_handoff` (`transport.py:166`) comes
from these listings, as follows.

- Graft reports "no indexed callers" for both `dispatch_handoff` definitions. It says itself that
  the name is ambiguous across two files, so it drops cross-file callers and "may undercount".
  Its result for `project_run.dispatch_handoff` is contradicted by grep, so graft cannot settle
  this question.
- The grep lists 17 lines matching `dispatch_handoff(`. Two of them are the definitions
  (`transport.py:166`, `project_run.py:2358` in the working tree). Each of the other 15 call
  sites resolves to `rush.workflows.project_run.dispatch_handoff`:
  - `src/rush/tools/scan_handoff.py` imports it from `rush.workflows.project_run`
    (`scan_handoff.py:34`, `:40`);
  - `src/rush/dashboard/server.py` imports it at `:62` and `:74`;
  - the TUI binds `pr.dispatch_handoff`, where `pr` is `rush.workflows.project_run` (HEAD
    `src/rush/tui.py:302`, `:342`);
  - `scripts/benchmarks/run.py` imports it from `rush.workflows.project_run` at `:547` and `:551`;
  - `tests/test_scan_handoff.py` imports it at `:26` and `:34`;
  - `tests/test_dashboard_map.py` calls it on `project_run_module`, which is
    `rush.workflows.project_run` (`:58`).
- The only modules that import `rush.memory.transport` are two test files,
  `tests/test_phase61_transport.py:17` and `tests/test_memory_handoff.py:23`. Neither contains
  the string `dispatch_handoff`: `grep -n dispatch_handoff` on both exits 1.

```text
$ graft callers get_handoff_receipts

get_handoff_receipts · method · src/rush/memory/store.py:L1999-L2008
  calls ← _bounded_session_delta (src/rush/memory/handoff.py:L190-L231)
  calls ← acknowledge_handoff (src/rush/memory/store.py:L2010-L2067)
  calls ← test_end_to_end_intent_repair_recipe_check_and_real_receiver (tests/test_memory_acceptance.py:L169-L508)
  calls ← test_delivery_ack_does_not_advance_cursor (tests/test_memory_handoff.py:L108-L141)
  calls ← test_partial_page_and_replay_are_atomic (tests/test_memory_handoff.py:L176-L221)
  calls ← test_receiver_reads_exact_versions_before_ack (tests/test_memory_handoff.py:L144-L173)
$ grep -rn --include='*.py' -E '\bdispatch_handoff\(' src scripts tests
src/rush/tools/scan_handoff.py:237:            handoff = dispatch_handoff(
src/rush/tools/scan_handoff.py:341:            handoff = dispatch_handoff(project, handoff_id, session_capability)
src/rush/memory/transport.py:166:def dispatch_handoff(
src/rush/workflows/project_run.py:2358:def dispatch_handoff(
src/rush/dashboard/server.py:2320:        dispatch_handoff(
src/rush/tui.py:1301:            dispatched = actions.dispatch_handoff(
scripts/benchmarks/run.py:644:    dispatch_handoff(
tests/test_dashboard_map.py:3516:            dispatched = project_run_module.dispatch_handoff(
tests/test_scan_handoff.py:118:    dispatched = dispatch_handoff(
tests/test_scan_handoff.py:222:        dispatch_handoff(
tests/test_scan_handoff.py:241:    dispatch_handoff(
tests/test_scan_handoff.py:280:    dispatch_handoff(
tests/test_scan_handoff.py:306:        dispatch_handoff(
tests/test_scan_handoff.py:651:    delivered = dispatch_handoff(
tests/test_scan_handoff.py:680:        dispatch_handoff(
tests/test_scan_handoff.py:716:    dispatched = dispatch_handoff(
tests/test_scan_handoff.py:751:    dispatch_handoff(
[grep exit 0]
$ graft callers dispatch_handoff

dispatch_handoff · function · src/rush/memory/transport.py:L166-L254
  no indexed callers — the graph has no incoming call/reference edges for this symbol as written. 2 definitions share the name "dispatch_handoff"; a cross-file caller of an ambiguous name is dropped rather than guessed, so this may undercount. Check the name (try the bare symbol, or "Type.method"), or find its uses with graft grep "dispatch_handoff". Fall back to raw grep -rn only for unindexed files

dispatch_handoff · function · src/rush/workflows/project_run.py:L2358-L2417
  no indexed callers — the graph has no incoming call/reference edges for this symbol as written. 2 definitions share the name "dispatch_handoff"; a cross-file caller of an ambiguous name is dropped rather than guessed, so this may undercount. Check the name (try the bare symbol, or "Type.method"), or find its uses with graft grep "dispatch_handoff". Fall back to raw grep -rn only for unindexed files
$ grep -rn --include='*.py' -E 'memory\.transport|memory import .*transport' src scripts tests
tests/test_phase61_transport.py:17:from rush.memory import transport
tests/test_memory_handoff.py:23:from rush.memory import handoff, transport
[grep exit 0]
```

### Trigger

A receiver's `receive` call carrying a non-empty `ack` list after it has read the exact
versions.

### Grant and capability prerequisites

- **To create the session.** `cache_write` for `MemoryTool._handoff`: CLI `--allow-cache-write`,
  or MCP `allow_cache_write: true`. Otherwise the call returns `E_PERMISSION`. The request needs
  `receiver_audience`, `goal` and a non-empty `selected_refs`. `receiver_namespace`, when given,
  becomes the session's allowlist.
- **To write a receipt.** No `ExecutionPermissions` grant is involved: `_receive` takes none, and
  the capability authorizes the receipt write. The request must carry:
  - the session id;
  - the raw capability, which is returned exactly once at prepare time and stored only as a
    hash;
  - an unexpired, unrevoked session;
  - for each `ack` entry, an artifact in the session's `granted_ids`, a version present in
    `memory_artifact_versions`, and `digest` equal to the SHA-256 of that version's exact stored
    bytes. The receiver can get those bytes from `expand`'s `content_base64`.

### Controlled demonstration

The fixture is a fresh project with one artifact from source `demo-src`. The transcript shows:

- sessions and receipts both at 0;
- prepare without the grant returns `E_PERMISSION` (0 sessions);
- prepare with `--allow-cache-write` creates 1 session with 0 receipts;
- `receive` without `ack` returns the pending change and 0 receipts;
- `expand` provides the stored bytes, and the driver computes their SHA-256;
- an `ack` with a wrong digest returns `E_VERSION` with 0 receipts;
- an `ack` with the correct digest returns `OK` with an empty next delta, and 1 receipt;
- `handoff` action `dispatch` returns `E_UNAVAILABLE`.

A second fixture then drives the scan-handoff workflow in-process. It writes a run manifest with
one finding, registers the project under `<DEMO>/rush-data`, and runs `build_handoff`,
`dispatch_handoff` and `acknowledge_handoff`. The scan handoff reaches state `acknowledged`
with 1 memory session and 0 memory receipts.

```text
===== memory_handoff_receipts =====
$ rush memory write domain_knowledge demo-src --content '{"text": "handoff evidence"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-H>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "handoff evidence"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/handoff"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_sessions;"
0
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat prepare.json
{
  "action": "prepare",
  "receiver_audience": "demo-receiver",
  "receiver_namespace": "demo-src",
  "goal": "share one artifact",
  "selected_refs": [
    {
      "id": "<ID-H>",
      "version": 1
    }
  ]
}
$ rush memory handoff --input prepare.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "fail",
  "duration_ms": <MS>,
  "summary": "memory handoff returned E_PERMISSION.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "handoff",
    "code": "E_PERMISSION",
    "data": {
      "message": "Memory handoff requires --allow-cache-write."
    }
  },
  "metadata": {
    "operation": "handoff"
  }
}
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_sessions;"
0
[exit 0]
$ rush memory handoff --input prepare.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory handoff returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "handoff",
    "code": "OK",
    "data": {
      "handoff_id": "<HANDOFF_ID>",
      "capability": "<CAPABILITY>",
      "expires_at": <TS>,
      "delta": {
        "session_id": "<HANDOFF_ID>",
        "audience": "demo-receiver",
        "changes": [
          {
            "id": "<ID-H>",
            "version": 1,
            "trust_tier": "EXTERNAL_WRITE",
            "source": "demo-src"
          }
        ],
        "constraints": {
          "goal": "share one artifact",
          "unresolved_decisions": [],
          "budgets": {}
        },
        "cursor": null
      }
    }
  },
  "metadata": {
    "operation": "handoff"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_sessions;"
1
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat receive.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>"
}
$ rush memory receive --input receive.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory receive returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "OK",
    "data": {
      "session_id": "<HANDOFF_ID>",
      "audience": "demo-receiver",
      "changes": [
        {
          "id": "<ID-H>",
          "version": 1,
          "trust_tier": "EXTERNAL_WRITE",
          "source": "demo-src"
        }
      ],
      "constraints": {
        "goal": "share one artifact",
        "unresolved_decisions": [],
        "budgets": {}
      },
      "cursor": null
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat expand.json
{
  "id": "<ID-H>",
  "version": 1
}
$ rush memory expand --input expand.json --session demo-src --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory expand returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "expand",
    "code": "OK",
    "data": {
      "id": "<ID-H>",
      "version": 1,
      "offset": 0,
      "next_offset": null,
      "complete": true,
      "content_base64": "eyJ0ZXh0IjogImhhbmRvZmYgZXZpZGVuY2UifQ==",
      "tokens": <TOKENS>,
      "bytes": 121,
      "encoding": "cl100k_base"
    }
  },
  "metadata": {
    "operation": "expand"
  }
}
[exit 0]
digest = sha256(base64decode(expand raw.data.content_base64)) = 903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6
$ cat ack_wrong.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-H>",
      "version": 1,
      "digest": "0000000000000000000000000000000000000000000000000000000000000000"
    }
  ]
}
$ rush memory receive --input ack_wrong.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "fail",
  "duration_ms": <MS>,
  "summary": "memory receive returned E_VERSION.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "E_VERSION",
    "data": {
      "message": "artifact '<ID-H>' version 1 read-back digest does not match the exact stored content."
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat ack.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-H>",
      "version": 1,
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory receive returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "OK",
    "data": {
      "session_id": "<HANDOFF_ID>",
      "audience": "demo-receiver",
      "changes": [],
      "constraints": {
        "goal": "share one artifact",
        "unresolved_decisions": [],
        "budgets": {}
      },
      "cursor": null
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
1
[exit 0]
$ cat dispatch.json
{
  "action": "dispatch"
}
$ rush memory handoff --input dispatch.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "warn",
  "duration_ms": <MS>,
  "summary": "memory handoff returned E_UNAVAILABLE.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "handoff",
    "code": "E_UNAVAILABLE",
    "data": {
      "message": "handoff dispatch is not yet implemented: rush.memory.handoff has no dispatch/status entry point."
    }
  },
  "metadata": {
    "operation": "handoff"
  }
}
[exit 1]
$ cat app.py
def unreviewed():
    pass
$ cat scan_handoff_demo.py
import json
import sys
from pathlib import Path

from rush.workflows.project_run import acknowledge_handoff, build_handoff, dispatch_handoff
from rush.workflows.projects import register_project

root = Path.cwd()
data_root = Path(sys.argv[1])
run_dir = root / ".rush" / "runs" / "run-demo" / "attempts" / "attempt-1"
run_dir.mkdir(parents=True)
finding = {
    "finding_id": "finding-1", "path": "app.py", "line": 1, "column": 0,
    "rule": "seeded-rule", "severity": "warn", "message": "issue",
    "provenance": "review/no-engine",
}
(run_dir / "manifest.json").write_text(json.dumps({
    "schema_version": 1, "run_id": "run-demo", "attempt_id": "attempt-1",
    "plan_id": "fixture-plan", "run_state": "completed",
    "aggregate": {"findings": [finding]}, "scheduled": [],
    "totals": {"finding_count": 1},
}), encoding="utf-8")
project_id = register_project(root, data_root=data_root).project_id
handoff = build_handoff(project_id, "run-demo", "codex-cli", data_root=data_root)
print("build_handoff state:", handoff.state)
delivered = dispatch_handoff(
    project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
)
print("dispatch_handoff state:", delivered.state)
acked = acknowledge_handoff(
    project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
)
print("acknowledge_handoff state:", acked.state)
$ python scan_handoff_demo.py <DEMO>/rush-data
build_handoff state: prepared
dispatch_handoff state: delivered
acknowledge_handoff state: acknowledged
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_sessions;"
1
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
```

### Additional demonstration: receive attempts that write no row, and a replay

This fixture is a fresh project with two artifacts from source `demo-src`. Only `<ID-H>` is
granted to the prepared session. Each `receive` below is followed by a receipt count:

- an empty `ack` returns `OK`, count 0;
- a wrong capability returns `E_PERMISSION`, count 0;
- a string `version` returns `E_INPUT`, count 0;
- an artifact that was not granted returns `E_PERMISSION`, count 0;
- version 2, which was never stored, returns `E_VERSION`, count 0;
- a non-object `ack` element produces an uncaught `AttributeError` traceback with exit 1,
  count 0;
- the correct ACK returns `OK`, count 1;
- a same-version replay returns `OK`, count 1. `acknowledged_version` is 1 before and after, and
  `updated_at` is rewritten to a later value.

The driver prints the replay comparison lines after reading the table directly with Python's
`sqlite3`. The traceback's `.venv` frame paths are printed verbatim; they are identical in both
runs.

```text
===== memory_handoff_receipts: receive attempts that write no row, and a replay =====
$ rush memory write domain_knowledge demo-src --content '{"text": "handoff evidence"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-H>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "handoff evidence"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/handoff"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ rush memory write domain_knowledge demo-src --content '{"text": "not granted to the session"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-O>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "not granted to the session"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/handoff"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ cat prepare.json
{
  "action": "prepare",
  "receiver_audience": "demo-receiver",
  "receiver_namespace": "demo-src",
  "goal": "share one artifact",
  "selected_refs": [
    {
      "id": "<ID-H>",
      "version": 1
    }
  ]
}
$ rush memory handoff --input prepare.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory handoff returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "handoff",
    "code": "OK",
    "data": {
      "handoff_id": "<HANDOFF_ID>",
      "capability": "<CAPABILITY>",
      "expires_at": <TS>,
      "delta": {
        "session_id": "<HANDOFF_ID>",
        "audience": "demo-receiver",
        "changes": [
          {
            "id": "<ID-H>",
            "version": 1,
            "trust_tier": "EXTERNAL_WRITE",
            "source": "demo-src"
          }
        ],
        "constraints": {
          "goal": "share one artifact",
          "unresolved_decisions": [],
          "budgets": {}
        },
        "cursor": null
      }
    }
  },
  "metadata": {
    "operation": "handoff"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat expand.json
{
  "id": "<ID-H>",
  "version": 1
}
$ rush memory expand --input expand.json --session demo-src --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory expand returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "expand",
    "code": "OK",
    "data": {
      "id": "<ID-H>",
      "version": 1,
      "offset": 0,
      "next_offset": null,
      "complete": true,
      "content_base64": "eyJ0ZXh0IjogImhhbmRvZmYgZXZpZGVuY2UifQ==",
      "tokens": <TOKENS>,
      "bytes": 121,
      "encoding": "cl100k_base"
    }
  },
  "metadata": {
    "operation": "expand"
  }
}
[exit 0]
digest = sha256(base64decode(expand raw.data.content_base64)) = 903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6
$ cat ack_empty.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": []
}
$ rush memory receive --input ack_empty.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory receive returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "OK",
    "data": {
      "session_id": "<HANDOFF_ID>",
      "audience": "demo-receiver",
      "changes": [
        {
          "id": "<ID-H>",
          "version": 1,
          "trust_tier": "EXTERNAL_WRITE",
          "source": "demo-src"
        }
      ],
      "constraints": {
        "goal": "share one artifact",
        "unresolved_decisions": [],
        "budgets": {}
      },
      "cursor": null
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat ack_bad_capability.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "not-the-capability",
  "ack": [
    {
      "id": "<ID-H>",
      "version": 1,
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack_bad_capability.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "fail",
  "duration_ms": <MS>,
  "summary": "memory receive returned E_PERMISSION.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "E_PERMISSION",
    "data": {
      "message": "Invalid handoff capability."
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat ack_malformed.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-H>",
      "version": "1",
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack_malformed.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "error",
  "duration_ms": <MS>,
  "summary": "memory receive returned E_INPUT.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "E_INPUT",
    "data": {
      "message": "Each readback requires id (str), version (int) and digest (str)."
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 2]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat ack_not_granted.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-O>",
      "version": 1,
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack_not_granted.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "fail",
  "duration_ms": <MS>,
  "summary": "memory receive returned E_PERMISSION.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "E_PERMISSION",
    "data": {
      "message": "Artifact '<ID-O>' was never granted to this session."
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat ack_unknown_version.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-H>",
      "version": 2,
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack_unknown_version.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "fail",
  "duration_ms": <MS>,
  "summary": "memory receive returned E_VERSION.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "E_VERSION",
    "data": {
      "message": "artifact '<ID-H>' version 2 was never delivered to this store (cannot skip an unseen change)."
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat ack_not_object.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    "not-an-object"
  ]
}
$ rush memory receive --input ack_not_object.json --json
[stderr] Traceback (most recent call last):
  File "<SCRATCH>/rush_head.py", line 14, in <module>
    cli(prog_name="rush")
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1569, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1490, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1970, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1970, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1353, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 907, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/cli.py", line 2910, in _cmd
    _run_tool(
  File "<SCRATCH>/export/src/rush/cli_support/rendering.py", line 119, in _run_tool
    result = executor.execute(context)
             ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/invocation/executor.py", line 466, in execute
    result = operation.handler(*args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 315, in __call__
    return self.run(
           ^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 533, in run
    return dispatch_table[operation]()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 528, in <lambda>
    "receive": lambda: self._receive(started, root, request),
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 2048, in _receive
    acknowledge_readback(
  File "<SCRATCH>/export/src/rush/memory/handoff.py", line 326, in acknowledge_readback
    artifact_id = entry.get("id")
                  ^^^^^^^^^
AttributeError: 'str' object has no attribute 'get'
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
$ cat ack.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-H>",
      "version": 1,
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory receive returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "OK",
    "data": {
      "session_id": "<HANDOFF_ID>",
      "audience": "demo-receiver",
      "changes": [],
      "constraints": {
        "goal": "share one artifact",
        "unresolved_decisions": [],
        "budgets": {}
      },
      "cursor": null
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
1
[exit 0]
$ cat ack_replay.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-H>",
      "version": 1,
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack_replay.json --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory receive returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "receive",
    "code": "OK",
    "data": {
      "session_id": "<HANDOFF_ID>",
      "audience": "demo-receiver",
      "changes": [],
      "constraints": {
        "goal": "share one artifact",
        "unresolved_decisions": [],
        "budgets": {}
      },
      "cursor": null
    }
  },
  "metadata": {
    "operation": "receive"
  }
}
[exit 0]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
1
[exit 0]
replay: receipt rows before/after = 1 1
replay: acknowledged_version before/after = 1 1
replay: updated_at rewritten to a later value = True
```

### Additional demonstration (round 2): oversized ACK version

This fixture is a fresh project with one artifact, `<ID-H>`, from source `demo-src`. After a
granted prepare and an `expand`, a `receive` sends an `ack` whose `version` is `2**70`, with the
correct digest for version 1. It ends in an uncaught `OverflowError` traceback raised from the
`SELECT` in `TypedArtifactStore.acknowledge_handoff`, with exit 1, and `memory_handoff_receipts`
stays at 0.

```text
===== memory_handoff_receipts: oversized ack version =====
$ rush memory write domain_knowledge demo-src --content '{"text": "handoff evidence"}' --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "Wrote memory artifact to subject 'domain_knowledge'.",
  "findings": [],
  "raw": {
    "id": "<ID-H>",
    "family": "memory",
    "subject": "domain_knowledge",
    "trust_tier": "EXTERNAL_WRITE",
    "content": {
      "text": "handoff evidence"
    },
    "source": "demo-src",
    "created_at": <TS>,
    "symbol_ref": null,
    "content_hash": null,
    "corroboration_count": 0,
    "promoted_at": null,
    "stale": false,
    "signature": null,
    "origin_kind": null,
    "origin_id": null,
    "expired": false,
    "artifact_version": 1,
    "owner_scope": {
      "kind": "project",
      "id": "<DEMO>/handoff"
    }
  },
  "metadata": {
    "operation": "write"
  }
}
[exit 0]
$ cat prepare.json
{
  "action": "prepare",
  "receiver_audience": "demo-receiver",
  "receiver_namespace": "demo-src",
  "goal": "share one artifact",
  "selected_refs": [
    {
      "id": "<ID-H>",
      "version": 1
    }
  ]
}
$ rush memory handoff --input prepare.json --allow-cache-write --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory handoff returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "handoff",
    "code": "OK",
    "data": {
      "handoff_id": "<HANDOFF_ID>",
      "capability": "<CAPABILITY>",
      "expires_at": <TS>,
      "delta": {
        "session_id": "<HANDOFF_ID>",
        "audience": "demo-receiver",
        "changes": [
          {
            "id": "<ID-H>",
            "version": 1,
            "trust_tier": "EXTERNAL_WRITE",
            "source": "demo-src"
          }
        ],
        "constraints": {
          "goal": "share one artifact",
          "unresolved_decisions": [],
          "budgets": {}
        },
        "cursor": null
      }
    }
  },
  "metadata": {
    "operation": "handoff"
  }
}
[exit 0]
$ cat expand.json
{
  "id": "<ID-H>",
  "version": 1
}
$ rush memory expand --input expand.json --session demo-src --json
{
  "tool": "memory",
  "engine": null,
  "engine_version": null,
  "status": "ok",
  "duration_ms": <MS>,
  "summary": "memory expand returned OK.",
  "findings": [],
  "raw": {
    "schema_version": 1,
    "operation": "expand",
    "code": "OK",
    "data": {
      "id": "<ID-H>",
      "version": 1,
      "offset": 0,
      "next_offset": null,
      "complete": true,
      "content_base64": "eyJ0ZXh0IjogImhhbmRvZmYgZXZpZGVuY2UifQ==",
      "tokens": <TOKENS>,
      "bytes": 121,
      "encoding": "cl100k_base"
    }
  },
  "metadata": {
    "operation": "expand"
  }
}
[exit 0]
digest = sha256(base64decode(expand raw.data.content_base64)) = 903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6
$ cat ack_big_version.json
{
  "session_id": "<HANDOFF_ID>",
  "capability": "<CAPABILITY>",
  "ack": [
    {
      "id": "<ID-H>",
      "version": 1180591620717411303424,
      "digest": "903e3dc07a5ab5d3da2d35dc976cc8516c13c2f030d2f0ed461833505152a7e6"
    }
  ]
}
$ rush memory receive --input ack_big_version.json --json
[stderr] Traceback (most recent call last):
  File "<SCRATCH>/rush_head.py", line 14, in <module>
    cli(prog_name="rush")
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1569, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1490, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1970, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1970, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 1353, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/lib/python3.12/site-packages/click/core.py", line 907, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/cli.py", line 2910, in _cmd
    _run_tool(
  File "<SCRATCH>/export/src/rush/cli_support/rendering.py", line 119, in _run_tool
    result = executor.execute(context)
             ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/invocation/executor.py", line 466, in execute
    result = operation.handler(*args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 315, in __call__
    return self.run(
           ^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 533, in run
    return dispatch_table[operation]()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 528, in <lambda>
    "receive": lambda: self._receive(started, root, request),
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/tools/memory.py", line 2048, in _receive
    acknowledge_readback(
  File "<SCRATCH>/export/src/rush/memory/handoff.py", line 346, in acknowledge_readback
    return store.acknowledge_handoff(session_id, updates)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<SCRATCH>/export/src/rush/memory/store.py", line 2036, in acknowledge_handoff
    stored_content = conn.execute(
                     ^^^^^^^^^^^^^
OverflowError: Python int too large to convert to SQLite INTEGER
[exit 1]
$ sqlite3 .rush/memory.db "SELECT COUNT(*) FROM memory_handoff_receipts;"
0
[exit 0]
```

### Limitations

- The receipt was written through the CLI `receive` route. The memory-session bridge over stdio
  and the native SDK or ACP transports were not exercised here. The bridge ACK path is covered by
  `tests/test_memory_acceptance.py`, which passes.
- Whether a real receiving agent follows the prompt and sends an `ack` depends on that agent,
  and it was not evaluated.
- Session expiry and revocation were not demonstrated. They are covered in
  `tests/test_memory_handoff.py`.
- The scan-handoff fixture writes a run manifest directly, the same way
  `tests/test_scan_handoff.py` does, instead of executing a real scan.

## Appendix A: what these findings do not claim

- They do not claim that any table is broken, and they do not claim that any table's rows would
  mean the system learned something. Each finding names only the path that writes the table and
  what it requires.
- They do not describe any wiring as planned or tracked. No plan file or section is cited as
  owning new producers for these tables.
- They make no claim about real user stores. Every row count in this report comes from
  disposable fixtures.

## Appendix B: harness sources

`rush_head.py`:

```python
"""Runs the `rush` CLI entry point (`rush.cli:cli`, per pyproject [project.scripts]) from
whatever `rush` package PYTHONPATH selects. The T22 demo sets PYTHONPATH to a `git archive
HEAD` export so the demo never imports the worktree's uncommitted T8 edits."""

import sys

import rush
from rush.cli import cli

if __name__ == "__main__":
    if sys.argv[1:2] == ["--which-rush"]:
        print(rush.__file__)
        sys.exit(0)
    cli(prog_name="rush")
```

`t22_demo.py`:

```python
"""Phase 70 T22 controlled demonstrations.

Every run creates a brand-new disposable base directory (project + HOME + TMPDIR) under
this script's directory, runs the real `rush` CLI (`rush.cli:cli`) as a subprocess with a
scrubbed environment (`HOME`, `PATH`, `PYTHONPATH`, `TMPDIR` only) against a `git archive
HEAD` export of `src/`, and prints a normalized transcript. No network: the driver refuses to
run unless the macOS sandbox denies networking (see `network_denied`), tiktoken reads a
pre-seeded local cache, and the only configured embedding endpoint uses an unregistered URL
scheme, which urllib rejects before opening any socket.

Normalization (volatile values only): the base directory path -> <DEMO>; every
`duration_ms` -> <MS>; every
`tokens` -> <TOKENS> (tiktoken count over text that embeds random uuid4 ids); wall-clock floats (`created_at`, `expires_at`, `updated_at`) -> <TS>;
generated artifact ids -> <ID-name>; handoff id -> <HANDOFF_ID>; capability -> <CAPABILITY>.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPORT_SRC = HERE / "export" / "src"
PY = "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv/bin/python"
RUSH = HERE / "rush_head.py"
SQLITE = "/usr/bin/sqlite3"

MCP_CALL = '''import json
import sys
from pathlib import Path

from rush.invocation import InvocationExecutor
from rush.mcp_support.tool_registry import make_tool_wrapper
from rush.tools.memory import MemoryTool

kwargs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
tool = MemoryTool()
executor = InvocationExecutor()
executor.register("memory", tool.__call__)
wrapper = make_tool_wrapper(tool, executor)
print(json.dumps(dict(wrapper(path=Path.cwd(), **kwargs)), indent=2))
'''


SCAN_HANDOFF = '''import json
import sys
from pathlib import Path

from rush.workflows.project_run import acknowledge_handoff, build_handoff, dispatch_handoff
from rush.workflows.projects import register_project

root = Path.cwd()
data_root = Path(sys.argv[1])
run_dir = root / ".rush" / "runs" / "run-demo" / "attempts" / "attempt-1"
run_dir.mkdir(parents=True)
finding = {
    "finding_id": "finding-1", "path": "app.py", "line": 1, "column": 0,
    "rule": "seeded-rule", "severity": "warn", "message": "issue",
    "provenance": "review/no-engine",
}
(run_dir / "manifest.json").write_text(json.dumps({
    "schema_version": 1, "run_id": "run-demo", "attempt_id": "attempt-1",
    "plan_id": "fixture-plan", "run_state": "completed",
    "aggregate": {"findings": [finding]}, "scheduled": [],
    "totals": {"finding_count": 1},
}), encoding="utf-8")
project_id = register_project(root, data_root=data_root).project_id
handoff = build_handoff(project_id, "run-demo", "codex-cli", data_root=data_root)
print("build_handoff state:", handoff.state)
delivered = dispatch_handoff(
    project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
)
print("dispatch_handoff state:", delivered.state)
acked = acknowledge_handoff(
    project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
)
print("acknowledge_handoff state:", acked.state)
'''


class Demo:
    def __init__(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="run.", dir=HERE))
        self.home = self.base / "home"
        self.tmp = self.base / "tmp"
        self.home.mkdir()
        self.tmp.mkdir()
        self.names: dict[str, str] = {}
        self.env = {
            "HOME": str(self.home),
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(EXPORT_SRC),
            "TMPDIR": str(self.tmp),
            # Pre-seeded offline copy of tiktoken's cl100k_base file; without it tiktoken
            # downloads the encoding over HTTPS on first use.
            "TIKTOKEN_CACHE_DIR": str(HERE / "tiktoken-cache"),
        }

    def project(self, name: str) -> Path:
        root = self.base / name
        root.mkdir()
        (root / "mcp_call.py").write_text(MCP_CALL, encoding="utf-8")
        return root

    def name(self, value: str, label: str) -> None:
        self.names[value] = label

    def norm(self, text: str) -> str:
        text = text.replace(str(self.base), "<DEMO>")
        for value, label in self.names.items():
            text = text.replace(value, label)
        text = re.sub(r'"duration_ms": \d+', '"duration_ms": <MS>', text)
        # tiktoken counts over page text that embeds the random uuid4 artifact ids, so the
        # count varies run to run even though `bytes` (fixed-length ids) does not.
        text = re.sub(r'"tokens": \d+', '"tokens": <TOKENS>', text)
        text = re.sub(
            r'"(created_at|expires_at|updated_at)": \d+(\.\d+)?', r'"\1": <TS>', text
        )
        return text

    def fixture(self, root: Path, filename: str, payload: object) -> None:
        body = json.dumps(payload, indent=2)
        (root / filename).write_text(body, encoding="utf-8")
        print(f"$ cat {filename}")
        print(self.norm(body))

    def _run(self, root: Path, argv: list[str], shown: str) -> str:
        proc = subprocess.run(
            argv, cwd=root, env=self.env, capture_output=True, text=True, check=False
        )
        print(f"$ {shown}")
        out = proc.stdout.rstrip("\n")
        if out:
            print(self.norm(out))
        if proc.stderr.strip():
            print("[stderr] " + self.norm(proc.stderr.rstrip("\n")))
        print(f"[exit {proc.returncode}]")
        return proc.stdout

    def rush(self, root: Path, *args: str) -> dict:
        out = self._run(root, [PY, str(RUSH), *args], shlex.join(["rush", *args]))
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {}

    def mcp(self, root: Path, filename: str, kwargs: dict) -> dict:
        self.fixture(root, filename, kwargs)
        out = self._run(
            root, [PY, "mcp_call.py", filename], f"python mcp_call.py {filename}"
        )
        return json.loads(out)

    def count(self, root: Path, table: str) -> None:
        sql = f"SELECT COUNT(*) FROM {table};"
        self._run(
            root,
            [SQLITE, ".rush/memory.db", sql],
            f'sqlite3 .rush/memory.db "{sql}"',
        )

    def write(self, root: Path, label: str, text: str) -> str:
        result = self.rush(
            root,
            "memory",
            "write",
            "domain_knowledge",
            "demo-src",
            "--content",
            json.dumps({"text": text}),
            "--allow-cache-write",
            "--json",
        )
        artifact_id = result["raw"]["id"]
        self.name(artifact_id, f"<ID-{label}>")
        return artifact_id


def section(title: str) -> None:
    print()
    print(f"===== {title} =====")


def network_denied() -> str:
    """Refuse to run outside `sandbox-exec -p '(version 1)(allow default)(deny network*)'`:
    a loopback connect is EPERM (PermissionError) only when the sandbox denies networking;
    unsandboxed it is ECONNREFUSED."""
    import socket

    try:
        socket.create_connection(("127.0.0.1", 9), timeout=2).close()
    except PermissionError as exc:
        return f"PermissionError errno={exc.errno}"
    except OSError as exc:
        raise SystemExit(f"network not denied ({type(exc).__name__}); run under sandbox-exec")
    raise SystemExit("network not denied (connect succeeded); run under sandbox-exec")


def main() -> Demo:
    canary = network_denied()
    demo = Demo()
    print("network canary: loopback connect ->", canary)
    print("rush package:", demo.norm(subprocess.run(
        [PY, str(RUSH), "--which-rush"], env=demo.env, capture_output=True, text=True,
        check=True,
    ).stdout.strip()).replace(str(HERE), "<SCRATCH>"))
    print("python:", sys.version.split()[0])
    print("home before:", sorted(p.name for p in demo.home.iterdir()))

    section("memory_relations")
    rel = demo.project("relations")
    a = demo.write(rel, "A", "alpha relation source")
    b = demo.write(rel, "B", "beta relation target")
    demo.count(rel, "memory_relations")
    demo.fixture(
        rel,
        "link.json",
        {
            "source_id": a,
            "source_version": 1,
            "target_id": b,
            "target_version": 1,
            "kind": "supersedes",
        },
    )
    demo.rush(rel, "memory", "link", "--input", "link.json", "--json")
    demo.count(rel, "memory_relations")
    demo.rush(rel, "memory", "link", "--input", "link.json", "--allow-cache-write", "--json")
    demo.count(rel, "memory_relations")
    demo.fixture(rel, "related.json", {"id": a, "version": 1})
    demo.rush(rel, "memory", "related", "--input", "related.json", "--session", "demo-src", "--json")
    demo.mcp(
        rel,
        "recall_compact.json",
        {
            "operation": "recall",
            "subject": "domain_knowledge",
            "query": "alpha",
            "session_allowlist": ["demo-src"],
            "request": {"view": "compact"},
        },
    )

    section("memory_embeddings")
    emb = demo.project("embeddings")
    demo.write(emb, "E", "alpha embedding candidate")
    demo.count(emb, "memory_embeddings")
    demo._run(emb, [PY, str(RUSH), "memory", "recall", "--help"], "rush memory recall --help")
    base_call = {
        "operation": "recall",
        "subject": "domain_knowledge",
        "query": "alpha",
        "session_allowlist": ["demo-src"],
    }
    demo.mcp(
        emb,
        "hybrid_no_network.json",
        {**base_call, "request": {"view": "compact", "retrieval": "hybrid"},
         "allow_cache_write": True},
    )
    demo.count(emb, "memory_embeddings")
    demo.mcp(
        emb,
        "hybrid_no_engine.json",
        {**base_call, "request": {"view": "compact", "retrieval": "hybrid"},
         "allow_network": True, "allow_cache_write": True},
    )
    demo.count(emb, "memory_embeddings")
    demo.mcp(
        emb,
        "hybrid_unavailable_engine.json",
        {
            **base_call,
            "request": {
                "view": "compact",
                "retrieval": "hybrid",
                "embedding_endpoint": "unregistered-scheme://embedding-engine",
                "embedding_model": "demo-model",
                "embedding_model_digest": "demo-digest",
            },
            "allow_network": True,
            "allow_cache_write": True,
        },
    )
    demo.count(emb, "memory_embeddings")

    section("memory_behavior_success")
    beh = demo.project("behavior")
    demo.write(beh, "S", "seed so the store exists")
    demo.count(beh, "memory_behavior_success")
    demo.fixture(
        beh,
        "diagnose.json",
        {
            "behavior_id": "demo-behavior",
            "conditions": {"runtime": "cpython/3.12", "platform": "darwin-arm64"},
        },
    )
    demo.rush(beh, "memory", "last-success-diagnose", "--input", "diagnose.json", "--json")
    demo.fixture(
        beh,
        "diagnose_historical.json",
        {
            "behavior_id": "demo-behavior",
            "conditions": {"runtime": "cpython/3.12", "platform": "darwin-arm64"},
            "historical": True,
        },
    )
    demo.rush(
        beh, "memory", "last-success-diagnose", "--input", "diagnose_historical.json", "--json"
    )
    demo.count(beh, "memory_behavior_success")

    section("memory_handoff_receipts")
    hand = demo.project("handoff")
    h = demo.write(hand, "H", "handoff evidence")
    demo.count(hand, "memory_handoff_sessions")
    demo.count(hand, "memory_handoff_receipts")
    prepare = {
        "action": "prepare",
        "receiver_audience": "demo-receiver",
        "receiver_namespace": "demo-src",
        "goal": "share one artifact",
        "selected_refs": [{"id": h, "version": 1}],
    }
    demo.fixture(hand, "prepare.json", prepare)
    demo.rush(hand, "memory", "handoff", "--input", "prepare.json", "--json")
    demo.count(hand, "memory_handoff_sessions")
    prepared = demo.rush(
        hand, "memory", "handoff", "--input", "prepare.json", "--allow-cache-write", "--json"
    )
    data = prepared["raw"]["data"]
    demo.name(data["handoff_id"], "<HANDOFF_ID>")
    demo.name(data["capability"], "<CAPABILITY>")
    demo.count(hand, "memory_handoff_sessions")
    demo.count(hand, "memory_handoff_receipts")
    session = {"session_id": data["handoff_id"], "capability": data["capability"]}
    demo.fixture(hand, "receive.json", session)
    demo.rush(hand, "memory", "receive", "--input", "receive.json", "--json")
    demo.count(hand, "memory_handoff_receipts")
    demo.fixture(hand, "expand.json", {"id": h, "version": 1})
    expanded = demo.rush(
        hand, "memory", "expand", "--input", "expand.json", "--session", "demo-src", "--json"
    )
    import base64
    import hashlib

    digest = hashlib.sha256(
        base64.b64decode(expanded["raw"]["data"]["content_base64"])
    ).hexdigest()
    print("digest = sha256(base64decode(expand raw.data.content_base64)) =", digest)
    demo.fixture(
        hand,
        "ack_wrong.json",
        {**session, "ack": [{"id": h, "version": 1, "digest": "0" * 64}]},
    )
    demo.rush(hand, "memory", "receive", "--input", "ack_wrong.json", "--json")
    demo.count(hand, "memory_handoff_receipts")
    demo.fixture(
        hand,
        "ack.json",
        {**session, "ack": [{"id": h, "version": 1, "digest": digest}]},
    )
    demo.rush(hand, "memory", "receive", "--input", "ack.json", "--json")
    demo.count(hand, "memory_handoff_receipts")
    demo.fixture(hand, "dispatch.json", {"action": "dispatch"})
    demo.rush(hand, "memory", "handoff", "--input", "dispatch.json", "--allow-cache-write", "--json")

    scan = demo.project("scanhandoff")
    (scan / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    (scan / "scan_handoff_demo.py").write_text(SCAN_HANDOFF, encoding="utf-8")
    print("$ cat app.py")
    print((scan / "app.py").read_text(encoding="utf-8").rstrip("\n"))
    print("$ cat scan_handoff_demo.py")
    print(SCAN_HANDOFF.rstrip("\n"))
    demo._run(
        scan,
        [PY, "scan_handoff_demo.py", str(demo.base / "rush-data")],
        "python scan_handoff_demo.py <DEMO>/rush-data",
    )
    demo.count(scan, "memory_handoff_sessions")
    demo.count(scan, "memory_handoff_receipts")

    section("isolation")
    print("home after:", sorted(p.name for p in demo.home.iterdir()))
    return demo


if __name__ == "__main__":
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        demo_obj = main()
    sys.stdout.write(demo_obj.norm(buffer.getvalue()))
```

`callers.sh`, run from the worktree root once per section (`relations`, `embeddings`,
`behavior`, `handoff`):

```bash
#!/bin/bash
# Caller evidence for T22: exhaustive grep plus graft's precomputed call graph.
# Usage: callers.sh <section> ; run from the worktree root.
set -u
grep_calls() {
  echo "\$ grep -rn --include='*.py' -E '\\b$1\\(' src scripts tests"
  grep -rn --include='*.py' -E "\\b$1\\(" src scripts tests
}
graft_calls() {
  echo "\$ graft callers $1"
  graft callers "$1" 2>&1 | grep -v '^\[graft\]'
}
case "$1" in
  relations)
    grep_calls add_relation; graft_calls add_relation
    grep_calls related_artifacts; graft_calls related_artifacts ;;
  embeddings)
    grep_calls put_embedding; graft_calls put_embedding
    grep_calls hybrid_candidates; graft_calls hybrid_candidates
    grep_calls hybrid_page; graft_calls hybrid_page ;;
  behavior)
    grep_calls write_pass; graft_calls write_pass
    grep_calls record_behavior_success; graft_calls record_behavior_success
    grep_calls get_behavior_success
    grep_calls find_any_behavior_success
    grep_calls compare_last_success; graft_calls compare_last_success ;;
  handoff)
    grep_calls acknowledge_readback; graft_calls acknowledge_readback
    grep_calls acknowledge_handoff; graft_calls acknowledge_handoff
    grep_calls get_handoff_receipts ;;
esac
```

`t22_demo_round1.py` (fix round 1), run from the same scratch directory as `t22_demo.py`, with
`sandbox-exec -p '(version 1)(allow default)(deny network*)' <worktree>/.venv/bin/python t22_demo_round1.py`:

```python
"""Phase 70 T22 fix round 1: supplementary demonstrations of zero-row outcomes that follow an
attempt. Reuses the harness in t22_demo.py (same export, scrubbed environment, network-deny
sandbox guard, and normalization), plus <SCRATCH> for this directory's path.
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import sys

from t22_demo import HERE, PY, RUSH, Demo, network_denied, section


class Demo1(Demo):
    def norm(self, text: str) -> str:
        return super().norm(text).replace(str(HERE), "<SCRATCH>")

    def link(self, root, filename: str, payload: dict) -> None:
        self.fixture(root, filename, payload)
        self.rush(root, "memory", "link", "--input", filename, "--allow-cache-write", "--json")
        self.count(root, "memory_relations")

    def receive(self, root, filename: str, payload: dict) -> None:
        self.fixture(root, filename, payload)
        self.rush(root, "memory", "receive", "--input", filename, "--json")
        self.count(root, "memory_handoff_receipts")


def main() -> Demo1:
    canary = network_denied()
    demo = Demo1()
    print("network canary: loopback connect ->", canary)

    section("memory_relations: authorized link attempts that write no row")
    rel = demo.project("relations")
    a = demo.write(rel, "A", "alpha relation source")
    b = demo.write(rel, "B", "beta relation target")
    demo.count(rel, "memory_relations")
    demo.mcp(rel, "link_no_request.json", {"operation": "link", "allow_cache_write": True})
    demo.count(rel, "memory_relations")
    good = {"source_id": a, "source_version": 1, "target_id": b, "target_version": 1}
    demo.link(rel, "link_unknown_key.json", {**good, "kind": "supersedes", "note": "x"})
    demo.link(rel, "link_missing_kind.json", good)
    demo.link(rel, "link_bad_kind.json", {**good, "kind": "resembles"})
    demo.link(rel, "link_missing_endpoint.json", {**good, "target_version": 9, "kind": "supersedes"})
    demo.link(rel, "link_ok.json", {**good, "kind": "supersedes"})
    demo.link(
        rel,
        "link_cycle.json",
        {"source_id": b, "source_version": 1, "target_id": a, "target_version": 1,
         "kind": "supersedes"},
    )

    section("memory_embeddings: configured engine, no authorized candidate")
    emb = demo.project("embeddings")
    demo.write(emb, "E", "alpha embedding candidate")
    demo.mcp(
        emb,
        "hybrid_no_candidate.json",
        {
            "operation": "recall",
            "subject": "domain_knowledge",
            "query": "alpha",
            "session_allowlist": ["other-src"],
            "request": {
                "view": "compact",
                "retrieval": "hybrid",
                "embedding_endpoint": "unregistered-scheme://embedding-engine",
                "embedding_model": "demo-model",
                "embedding_model_digest": "demo-digest",
            },
            "allow_network": True,
            "allow_cache_write": True,
        },
    )
    demo.count(emb, "memory_embeddings")

    section("memory_handoff_receipts: receive attempts that write no row, and a replay")
    hand = demo.project("handoff")
    h = demo.write(hand, "H", "handoff evidence")
    other = demo.write(hand, "O", "not granted to the session")
    demo.fixture(
        hand,
        "prepare.json",
        {
            "action": "prepare",
            "receiver_audience": "demo-receiver",
            "receiver_namespace": "demo-src",
            "goal": "share one artifact",
            "selected_refs": [{"id": h, "version": 1}],
        },
    )
    prepared = demo.rush(
        hand, "memory", "handoff", "--input", "prepare.json", "--allow-cache-write", "--json"
    )
    data = prepared["raw"]["data"]
    demo.name(data["handoff_id"], "<HANDOFF_ID>")
    demo.name(data["capability"], "<CAPABILITY>")
    session = {"session_id": data["handoff_id"], "capability": data["capability"]}
    demo.count(hand, "memory_handoff_receipts")
    import base64
    import hashlib

    expanded = demo.rush(
        hand, "memory", "expand", "--input",
        demo_fixture_path(demo, hand, "expand.json", {"id": h, "version": 1}),
        "--session", "demo-src", "--json",
    )
    digest = hashlib.sha256(
        base64.b64decode(expanded["raw"]["data"]["content_base64"])
    ).hexdigest()
    print("digest = sha256(base64decode(expand raw.data.content_base64)) =", digest)
    demo.receive(hand, "ack_empty.json", {**session, "ack": []})
    demo.receive(hand, "ack_bad_capability.json",
                 {**session, "capability": "not-the-capability",
                  "ack": [{"id": h, "version": 1, "digest": digest}]})
    demo.receive(hand, "ack_malformed.json",
                 {**session, "ack": [{"id": h, "version": "1", "digest": digest}]})
    demo.receive(hand, "ack_not_granted.json",
                 {**session, "ack": [{"id": other, "version": 1, "digest": digest}]})
    demo.receive(hand, "ack_unknown_version.json",
                 {**session, "ack": [{"id": h, "version": 2, "digest": digest}]})
    demo.receive(hand, "ack_not_object.json", {**session, "ack": ["not-an-object"]})
    demo.receive(hand, "ack.json", {**session, "ack": [{"id": h, "version": 1, "digest": digest}]})
    db = hand / ".rush" / "memory.db"
    with sqlite3.connect(db) as conn:
        before = conn.execute(
            "SELECT acknowledged_version, updated_at FROM memory_handoff_receipts"
        ).fetchall()
    demo.receive(hand, "ack_replay.json",
                 {**session, "ack": [{"id": h, "version": 1, "digest": digest}]})
    with sqlite3.connect(db) as conn:
        after = conn.execute(
            "SELECT acknowledged_version, updated_at FROM memory_handoff_receipts"
        ).fetchall()
    print("replay: receipt rows before/after =", len(before), len(after))
    print("replay: acknowledged_version before/after =", before[0][0], after[0][0])
    print("replay: updated_at rewritten to a later value =", after[0][1] > before[0][1])

    section("isolation")
    print("home after:", sorted(p.name for p in demo.home.iterdir()))
    return demo


def demo_fixture_path(demo: Demo1, root, filename: str, payload: dict) -> str:
    demo.fixture(root, filename, payload)
    return filename


if __name__ == "__main__":
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        demo_obj = main()
    sys.stdout.write(demo_obj.norm(buffer.getvalue()))
    _ = (json, PY, RUSH)
```

`callers_round1.sh` (fix round 1), run from the worktree root once per section (`embeddings`,
`behavior`, `handoff`):

```bash
#!/bin/bash
# T22 fix round 1: caller listings not recorded in the first pass.
# Usage: callers_round1.sh <section> ; run from the worktree root.
set -u
grep_calls() {
  echo "\$ grep -rn --include='*.py' -E '\\b$1\\(' src scripts tests"
  grep -rn --include='*.py' -E "\\b$1\\(" src scripts tests
  echo "[grep exit $?]"
}
graft_calls() {
  echo "\$ graft callers $1"
  graft callers "$1" 2>&1 | grep -v '^\[graft\]'
}
case "$1" in
  embeddings)
    grep_calls get_embedding; graft_calls get_embedding
    grep_calls delete_batch; graft_calls delete_batch ;;
  behavior)
    graft_calls get_behavior_success
    graft_calls find_any_behavior_success ;;
  handoff)
    graft_calls get_handoff_receipts
    grep_calls dispatch_handoff; graft_calls dispatch_handoff
    echo "\$ grep -rn --include='*.py' -E 'memory\\.transport|memory import .*transport' src scripts tests"
    grep -rn --include='*.py' -E 'memory\.transport|memory import .*transport' src scripts tests
    echo "[grep exit $?]" ;;
esac
```

`t22_demo_round2.py` (fix round 2), run from the same scratch directory, with
`sandbox-exec -p '(version 1)(allow default)(deny network*)' <worktree>/.venv/bin/python t22_demo_round2.py`:

```python
"""Phase 70 T22 fix round 2: CLI rejections before the tool runs, and the two oversized-integer
crashes. Reuses the harness in t22_demo.py and t22_demo_round1.py (same export, scrubbed
environment, network-deny sandbox guard, and normalization)."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import sys

from t22_demo import network_denied, section
from t22_demo_round1 import Demo1

BIG = 2**70  # 1180591620717411303424: a JSON integer that Python accepts but SQLite cannot store


def raw_file(demo: Demo1, root, filename: str, body: str) -> None:
    (root / filename).write_text(body, encoding="utf-8")
    print(f"$ cat {filename}")
    print(body)


def main() -> Demo1:
    canary = network_denied()
    demo = Demo1()
    print("network canary: loopback connect ->", canary)

    section("memory_relations: CLI rejections before the tool, and an oversized version")
    rel = demo.project("relations")
    a = demo.write(rel, "A", "alpha relation source")
    b = demo.write(rel, "B", "beta relation target")
    demo.count(rel, "memory_relations")
    raw_file(demo, rel, "link_not_object.json", "[]")
    demo.rush(rel, "memory", "link", "--input", "link_not_object.json", "--allow-cache-write", "--json")
    demo.count(rel, "memory_relations")
    raw_file(demo, rel, "link_not_json.json", "{not json")
    demo.rush(rel, "memory", "link", "--input", "link_not_json.json", "--allow-cache-write", "--json")
    demo.count(rel, "memory_relations")
    demo.rush(rel, "memory", "link", "--input", "no_such_file.json", "--allow-cache-write", "--json")
    demo.count(rel, "memory_relations")
    demo.link(
        rel,
        "link_big_version.json",
        {"source_id": a, "source_version": BIG, "target_id": b, "target_version": 1,
         "kind": "supersedes"},
    )

    section("memory_handoff_receipts: oversized ack version")
    hand = demo.project("handoff")
    h = demo.write(hand, "H", "handoff evidence")
    demo.fixture(
        hand,
        "prepare.json",
        {
            "action": "prepare",
            "receiver_audience": "demo-receiver",
            "receiver_namespace": "demo-src",
            "goal": "share one artifact",
            "selected_refs": [{"id": h, "version": 1}],
        },
    )
    prepared = demo.rush(
        hand, "memory", "handoff", "--input", "prepare.json", "--allow-cache-write", "--json"
    )
    data = prepared["raw"]["data"]
    demo.name(data["handoff_id"], "<HANDOFF_ID>")
    demo.name(data["capability"], "<CAPABILITY>")
    session = {"session_id": data["handoff_id"], "capability": data["capability"]}
    demo.fixture(hand, "expand.json", {"id": h, "version": 1})
    expanded = demo.rush(
        hand, "memory", "expand", "--input", "expand.json", "--session", "demo-src", "--json"
    )
    digest = hashlib.sha256(
        base64.b64decode(expanded["raw"]["data"]["content_base64"])
    ).hexdigest()
    print("digest = sha256(base64decode(expand raw.data.content_base64)) =", digest)
    demo.receive(hand, "ack_big_version.json",
                 {**session, "ack": [{"id": h, "version": BIG, "digest": digest}]})

    section("isolation")
    print("home after:", sorted(p.name for p in demo.home.iterdir()))
    return demo


if __name__ == "__main__":
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        demo_obj = main()
    sys.stdout.write(demo_obj.norm(buffer.getvalue()))
```
