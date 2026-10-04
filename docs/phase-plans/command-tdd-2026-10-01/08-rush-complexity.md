# Q08 — complexity

Implement `complexity` corrections and retained expansions from binding audit.

## Feature and goal

Remediate complete Q08 scope. Planning only; production changes and tests below proposed, unimplemented and unexecuted. Grounding: main `c78e445ba1e575ca373e35840142cd627b055d6a`; clean Phase70 `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70` at `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`. Read `AGENTS.md`, `docs/templates/task-block-template.md`, `README.md`, `00-shared-foundation.md` in this plan directory first. Foundation is defined dependency/owner. Audit `docs/reports/cli-mcp-command-audit-2026-09-26.md` SHA256 `8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f`; remediation `docs/reports/command-tdd-2026-10-01-plan-remediation.md` SHA256 `362dae4489fbe8f6322217e30ae69ed3ad8a888732a37029641a0040cd8ef633`. Binding C-01–C-29 overrides contradictory older fixes. Earlier report probe outcomes do not verify corrected proposed code.

## Required behavior

Preserve scanner provisioning, connected specialist local models, selectable voice/live speech and 3D companion as user baseline. Command expansions remain separate. F1 strict flat schema rejects unknown keys/string grants with MCP isError=false, ToolResult error, raw error.code=INVALID_REQUEST; valid-field rejection uses metadata.error.code=invalid_argument; escape uses path_escape. F2 canonical engines/scope, no duplicate child arrays or partial booleans. F3 whole-operation denial: skipped, execution cause permission_denied, operation block denied/build_or_slow_denied, zero spawns/writes. Verify-only row denial preserves base assessment. Runtime absolute, never cwd-anchored; F4 validates platform/runtime before image. F4/F5/F6 exact foundation contracts retained. Shared aggregate choice remains README decision, no local override.

## Deliverables and file map

Create new file tests/test_complexity.py (absent both revisions). Source/fixture/test patches below proposed only. Shared CLI/MCP/catalog/reference/permissions/CHANGELOG/coverage rows are Foundation-owned serialized Q08-DOC rows in same packet. Existing Phase70 discovery/permission/provenance/zero-skip gates retained.

## Dependencies and ordered tasks

1. Finish foundation interfaces and ratify open choices; no report default is approval.
2. Record interface-absent RED separately; assert exported interface/metadata before new-option invocation. Require behavior assertion RED once interface exists.
3. Apply local source/fixtures/tests; preserve existing protocols and unrelated code.
4. Run narrow gates and same-packet docs; future final full-suite acceptance only after implementation.

## Constraints

This remediation writes plans only; no production/tests/source/config writes, downloads, hooks, commits/pushes/releases. pytest runtime dependency (`pyproject.toml:27`). Terms: producer-qualified metric has engine, unit, actual value and source digest; TP/FP/TN/FN are observed labeled counts; isolation means actual foundation OCI boundary. Any edit invalidates frozen review.

## Proposed source changes

```python
import difflib, json, os, shutil, subprocess
from pathlib import Path
import rush.tools.complexity as module
from rush.tools.complexity import ComplexityTool
from rush.engines.radon import RadonEngine
from rush.engines.jscpd import JscpdEngine

def test_malformed_reports_not_clean(tmp_path, monkeypatch):
    radon = RadonEngine(); jscpd = JscpdEngine()
    for engine in (radon,jscpd):
        monkeypatch.setattr(engine,"version",lambda:"fixture-protocol")
    for text, code in [("{",0),("[]",0),("{}",2),
                       ('{"a.py":[{"name":"f","lineno":1,"complexity":"12"}]}',0)]:
        assert radon.normalize({"stdout":text,"exit_code":code},tmp_path,"complexity")[
            "status"] == "error"
    for report in (None,{"statistics":{"total":{"sources":0,"clones":0,
            "duplicatedLines":0}},"duplicates":[]},
            {"statistics":{"total":{"sources":2,"clones":1,"duplicatedLines":0}},
             "duplicates":[]}):
        assert jscpd.normalize({"parsed":report,"exit_code":0},tmp_path,"complexity")[
            "status"] == "error"
    clean = {"statistics":{"total":{"sources":2,"clones":0,"duplicatedLines":0}},
             "duplicates":[]}
    assert jscpd.normalize({"parsed":clean,"exit_code":0},tmp_path,"complexity")[
        "status"] == "ok"

def test_declared_engines_accounted_for(tmp_path, monkeypatch):
    (tmp_path/"a.py").write_text("def f(n):\n"+"".join(
        f"    if n == {i}:\n        return {i}\n" for i in range(11))+"    return -1\n")
    duplicate = "".join(f"export const value{i} = {i};\n" for i in range(7))
    (tmp_path/"a.js").write_text(duplicate)
    (tmp_path/"b.js").write_text(duplicate)
    calls = []
    radon = RadonEngine(); jscpd = JscpdEngine()
    monkeypatch.setattr(radon,"version",lambda:"fixture")
    monkeypatch.setattr(jscpd,"version",lambda:"5.2.0")
    def scan(engine,path,args,**kwargs):
        calls.append(engine.name)
        if engine.name=="radon":
            return radon.normalize({"exit_code":0,"stdout":json.dumps({
                "a.py":[{"name":"f","lineno":1,"complexity":12}]})},path,"complexity")
        if engine.name=="jscpd":
            clone = {"lines":7,"firstFile":{"name":"a.js","start":1},
                     "secondFile":{"name":"b.js","start":1}}
            return jscpd.normalize({"exit_code":0,"parsed":{"duplicates":[clone],
                "statistics":{"total":{"sources":2,"clones":1,"duplicatedLines":7}}}},
                path,"complexity")
        return dict(tool="complexity",engine=engine.name,engine_version=None,
            status="skipped",duration_ms=0,summary="controlled availability",findings=[])
    monkeypatch.setattr(module,"run_engine",scan)
    result = ComplexityTool().run(tmp_path)
    assert calls.count("clines") == 1
    children = {c["engine"]:c for c in result["metadata"]["children"]}
    assert children["clines"]["status"] == "skipped"
    assert children["radon"]["metrics"] == [
        {"path":"a.py","symbol":"f","metric":"cyclomatic","unit":"score","value":12}]
    assert children["jscpd"]["metrics"] == [
        {"path":str(tmp_path),"symbol":None,"metric":"duplicated_lines","unit":"lines","value":7}]
    assert result["metadata"]["scope"]["coverage"] == "partial"

def test_hotspot_evidence_without_refactor(tmp_path):
    assert shutil.which("radon"), "Version-pinned Radon is required"
    source = tmp_path/"a.py"
    source.write_text("def f(n):\n"+"".join(
        f"    if n == {i}:\n        return {i}\n" for i in range(11))+"    return -1\n")
    env = {**os.environ,"GIT_AUTHOR_DATE":"2000-01-01T00:00:00Z",
           "GIT_COMMITTER_DATE":"2000-01-01T00:00:00Z"}
    for args in (["init","-q"],["add","."],["-c","user.name=Fixture",
            "-c","user.email=f@example.test","commit","-qm","old fixture"]):
        subprocess.run(["git",*args],cwd=tmp_path,env=env,check=True,capture_output=True)
    result = ComplexityTool().run(tmp_path,view="hotspots")
    row = next(r for r in result["metadata"]["hotspots"] if r["metric"]=="cyclomatic")
    assert (row["value"],row["unit"]) == (12,"score")
    assert row["churn_window"] == {"days":30,"commits":0}
    assert row["observed_failure_count"] is None
    assert row["failure_evidence_status"] == "unavailable"
    assert row["options"] == ["no_refactor"]

def test_refactor_trial_requires_metric_and_test_improvement(tmp_path):
    for binary in ("radon","jscpd","clines","tach","sentrux"):
        assert shutil.which(binary), f"Comparable complete assessment requires {binary}"
    (tmp_path/"src").mkdir(); (tmp_path/"tests").mkdir(); (tmp_path/"fixes").mkdir()
    original = "def f(n):\n    if n > 0:\n        return True\n    if n <= 0:\n        return False\n"
    source = tmp_path/"src/calc.py"; source.write_text(original)
    (tmp_path/"src/a.js").write_text("export const value = 1;\n")
    (tmp_path/"tests/test_calc.py").write_text("from src.calc import f\ndef test_f():\n"
        "    assert [f(n) for n in (-1,0,1)] == [False,False,True]\n")
    for name,replacement in [("good","def f(n):\n    return n > 0\n"),
                             ("bad","def f(n):\n    return False\n")]:
        (tmp_path/f"fixes/{name}.diff").write_text("".join(difflib.unified_diff(
            original.splitlines(True),replacement.splitlines(True),
            fromfile="a/src/calc.py",tofile="b/src/calc.py")))
    for args in (["init","-q"],["add","."],["-c","user.name=Fixture",
            "-c","user.email=f@example.test","commit","-qm","fixture"]):
        subprocess.run(["git",*args],cwd=tmp_path,check=True,capture_output=True)
    before = source.read_bytes()
    args = dict(verification_tests=["tests/test_calc.py"],
        runtime_path=Path(os.environ["RUSH_TEST_OCI_RUNTIME"]),
        image_ref=os.environ["RUSH_TEST_RUSH_IMAGE"],allow_build=True,allow_slow=True)
    good = ComplexityTool().run(tmp_path,trial_refactor=Path("fixes/good.diff"),**args)[
        "metadata"]["refactor_trial"]
    assert good["status"] == "verified_candidate"
    assert (good["before_cyclomatic_total"],good["after_cyclomatic_total"]) == (5,3)
    assert (good["before_duplicated_lines"],good["after_duplicated_lines"]) == (0,0)
    bad = ComplexityTool().run(tmp_path,trial_refactor=Path("fixes/bad.diff"),**args)[
        "metadata"]["refactor_trial"]
    assert bad["status"] == "rejected"
    assert source.read_bytes() == before
```



## Remediation reconciliation

Individual report Fix verification indexed by exact ID/line; safe replacements read frozen corrected plan, future behavior checks remain pending. No self-matching grep command copied into plan.

| ID | Substantive correction | Live evidence / exact check | Outcome / gap |
|---|---|---|---|
| Q08-01 | Correct "Existing test module" tests/test_complexity.py does not exist; replacement in proposed packet/binding amendments below | report:10743, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-02 | Correct Check command names nonexistent test files and omits regressions, mypy and the docs gate; replacement in proposed packet/binding amendments below | report:10751, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-03 | Correct Trial RED expects cyclomatic totals (3,1); real Radon gives (5,3); replacement in proposed packet/binding amendments below | report:10772, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-04 | Correct Trial fixture `a.js` gives jscpd `sources=0`; the directory protocol also scans the wrong set; replacement in proposed packet/binding amendments below | report:10783, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-05 | Correct "Complete comparable assessment" is undefined; tach, sentrux and clines cannot complete on the fixture; replacement in proposed packet/binding amendments below | report:10828, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-06 | Correct Aggregate semantics contradict phase/70 T16; replacement in proposed packet/binding amendments below | report:10849, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-07 | Correct "Foundation" owner has no artifact; replacement in proposed packet/binding amendments below | report:10876, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-08 | Correct W18 isolation has no artifact; in-container command undefined; replacement in proposed packet/binding amendments below | report:10903, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-09 | Correct Grant flags already exist; mechanism unspecified; at c78e445 no per-tool option mechanism exists; replacement in proposed packet/binding amendments below | report:10932, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-10 | Correct Isolation names drift from the audit; replacement in proposed packet/binding amendments below | report:10955, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-11 | Correct Hotspot schema drifts from the audit; replacement in proposed packet/binding amendments below | report:10962, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-12 | Correct Trial status vocabulary and decision rule drift; replacement in proposed packet/binding amendments below | report:10969, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-13 | Correct Audit's `terminal_reason:"malformed_output"` dropped; replacement in proposed packet/binding amendments below | report:10976, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-14 | Correct Audit test IDs merged; disposition has no field; replacement in proposed packet/binding amendments below | report:10983, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-15 | Correct Parity test exercises only `--view metrics`; rejection paths untested; invented key; replacement in proposed packet/binding amendments below | report:11044, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-16 | Correct RED bodies fail for non-assertion reasons; replacement in proposed packet/binding amendments below | report:11076, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-17 | Correct Real Radon JSON shape not handled; the finding's closure rule is wrong; replacement in proposed packet/binding amendments below | report:11092, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-18 | Correct Existing tests and fixtures broken by the protocol change are unlisted; replacement in proposed packet/binding amendments below | report:11114, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-19 | Correct Existing `rush.hotspots` package ignored; replacement in proposed packet/binding amendments below | report:11139, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-20 | Correct Hotspot dependency/failure evidence undefined; the finding's dependency source is mislabeled; replacement in proposed packet/binding amendments below | report:11162, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-21 | Correct Selected-test execution depends on Q04 and phase/70; the finding's argv omits `--test-environment active`; replacement in proposed packet/binding amendments below | report:11182, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-22 | Correct Baseline runs on the host, candidate in OCI; replacement in proposed packet/binding amendments below | report:11198, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-23 | Correct PatchSandboxManager clean-git and `.rush/` writes unstated; replacement in proposed packet/binding amendments below | report:11205, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-24 | Correct Clines rows and units undefined; hand-written fixtures contradict "capture real fixtures"; replacement in proposed packet/binding amendments below | report:11212, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-25 | Correct R3 cites `aggregate_results`, which the plan does not own; the finding's 66c6c79 line numbers are wrong; replacement in proposed packet/binding amendments below | report:11239, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-26 | Correct Strict-boolean requirement has no mechanism; replacement in proposed packet/binding amendments below | report:11253, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-27 | Correct Does not follow the task-block template; `needs-info` unexplained; replacement in proposed packet/binding amendments below | report:11275, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-28 | Correct No production patch code, against AGENTS.md "Concrete Fixes"; replacement in proposed packet/binding amendments below | report:11284, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-29 | Correct Docs work covers 3 pages vaguely; 13 affected docs omitted; docs gate not mentioned; replacement in proposed packet/binding amendments below | report:11306, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-30 | Correct Text from other plans leaked in; replacement in proposed packet/binding amendments below | report:11330, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-31 | Correct Undefined shorthand; replacement in proposed packet/binding amendments below | report:11337, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-32 | Correct "pytest is already installed by dev extra" is false; replacement in proposed packet/binding amendments below | report:11344, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-33 | Correct Only the "version-pinned" assertion holds; replacement in proposed packet/binding amendments below | report:11351, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-34 | Correct Ledger line ranges off; replacement in proposed packet/binding amendments below | report:11361, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q08-35 | Correct Metric-row path conventions inconsistent; the finding's base is unavailable in direct calls; replacement in proposed packet/binding amendments below | report:11368, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |

## Checks to run before reporting`; add `## Completion`: "complete only when the RED bodies pass, the commands in Checks pass, and only the Deliverables paths changed".
  2. Replace line 2 with `Status: needs-info — waiting on user decisions D1 (implementation base), D2 (W18 ownership), D3 (trial grants), D4 (scratch location), D5 (source_digest on rows), D6 (strict-grant mechanism).` Once the decisions are recorded, the status becomes `ready`.

Evidence/check: remediation report:11275, Q08-27 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-28 — No production patch code, against AGENTS.md "Concrete Fixes"

add a section `## Proposed source changes (unexecuted)`. Embed these audit blocks verbatim, each with its amendments, in this order:
  1. `ComplexityTool.run` clines scheduling (audit 3576-3582). Amendment: the call is `run_engine(engine, root, [], tool_name=self.name)`.
  2. `RadonEngine.normalize` (audit 3584-3604). Amendments: `error_result` import from `..runtime.result_helpers`; unit summing per Q08-17 (function/method plus closures, never class rows or nested methods); `engine` and `source_digest` on rows.
  3. `JscpdEngine.run`/`normalize` (audit 3606-3639). Amendments: `--format` and `--ignore` per Q08-04; `zero_assessed_sources` and `terminal_reason`; `error_result` import.
  4. `ComplexityTool.run` post-aggregation (audit 3640-3647). Replace the `children`/`partial` code with the Q08-06 `metadata.metrics` and `metadata.engine_dispositions`; delete the `partial`/skipped lines.
  5. `_build_hotspots` (audit 3657-3676). Amendments: Q08-11 fields (90d), Q08-19 `extract_window`, Q08-20 evidence fields; `churn is None` gives `unavailable`.
  6. `_trial_refactor` (audit 3700-3750). Amendments:
     - replace `-m rush` with `-m rush.cli`;
     - add `--test-environment active --allow-build`;
     - run the baseline in an unpatched sandbox in the same image;
     - use the `decision` rule of Q08-12;
     - scratch under D4;
     - define `metrics()` over `metadata.metrics` rows, not `duplicate child array`;
     - the `before_digest` hashes only single-file targets, so for directory targets use the sorted per-file digest list.
  7. `__call__`/`run` typed signature (audit 3808-3817) with `isolation_*` names.
  Every helper must be defined in the section or cited at a verified path.

Evidence/check: remediation report:11284, Q08-28 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-29 — Docs work covers 3 pages vaguely; 13 affected docs omitted; docs gate not mentioned

replace lines 79-80 with the docs deliverable below (this plan owns it).
  - `docs/reference/cli-reference.md` (complexity row), `docs/CLI_REFERENCE.md:66`: engines "Radon, jscpd, Tach, Clines, Sentrux"; the five new options; trial needs `--allow-build --allow-slow` (plus `--allow-artifact-write` under D3 Option A).
  - `docs/reference/mcp-tool-reference.md`: new `### rush_complexity` section with parameters, types, defaults, and one example per view and for the trial.
  - `docs/MCP_REFERENCE.md:82,161`: add the `rush_complexity` parameter list (line 82 is the tool list, line 161 a one-line claim; neither has parameters).
  - `docs/reference/result-reference.md`: `metadata.metrics` row schema with units (cyclomatic=score, duplicated_lines=lines), `metadata.engine_dispositions`, `metadata.hotspots` fields, `metadata.refactor_trial` fields and statuses, and `terminal_reason` values `malformed_output`, `zero_assessed_sources`, `source_parse_error`, `invalid_view`, `path_escape`, `grant_required`.
  - `docs/JSON_SCHEMA.md:73-76`: top-level `metrics` unchanged; unit rows live in `metadata.metrics`.
  - `docs/reference/engine-directory.md:22-23,194` and `docs/ENGINES.md:24-25,196`: jscpd JSON report plus format/ignore scope and the threshold rule; clines scheduled once when JS/TS is present; radon malformed output is an error.
  - `docs/ENGINE_COMPATIBILITY.md:48-49,156`: jscpd 5.2.0 JSON protocol, radon 6.0.1.
  - `docs/TOOL_CATALOG.md:28`: drop Depcruise, Scaphandre, Readability, Memray, Statoscope, Bloaty (complexity.py runs none of them).
  - `docs/CLI_COOKBOOK.md:79-81`: same engine-list correction plus hotspots and trial examples.
  - New `docs/tools/complexity.md` in the existing docs/tools format.
  - `CHANGELOG.md`: entry under the next version.
  - `docs/reports/phase-64-66-documentation-coverage.md`: recompute `document_digest` for every changed or new doc and update the `complexity` contract parameters so `scripts/sync_docs.py --check` passes.

Evidence/check: remediation report:11306, Q08-29 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-30 — Text from other plans leaked in

as in the findings file (delete lines 95 and 131). OK.

Evidence/check: remediation report:11330, Q08-30 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-31 — Undefined shorthand

after line 15 insert `Terms: R1–R3 = repairs; E1 = ordinary qualified-hotspot extension; X1 = agent-side expansion (the isolated refactor trial), per the ledger below; W18 = audit Command 45/79 isolation contract (audit lines 13810–13891).` "Shared documentation owner" disappears under Q08-29 and "Foundation" under Q08-07.

Evidence/check: remediation report:11337, Q08-31 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-32 — "pytest is already installed by dev extra" is false

as in the findings file. OK.

Evidence/check: remediation report:11344, Q08-32 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-33 — Only the "version-pinned" assertion holds

add to the hotspot and trial bodies `assert subprocess.run(["radon","--version"],capture_output=True,text=True).stdout.strip() == "6.0.1"`, and for jscpd `assert subprocess.run(["jscpd","--version"],capture_output=True,text=True).stdout.strip().endswith("5.2.0")` (observed `jscpd 5.2.0`; `ci.yml:101,104` pin both). Leave the check commands unchanged.

Evidence/check: remediation report:11351, Q08-33 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-34 — Ledger line ranges off

as in the findings file (`radon.py:37–63`, `Audit Q08:3692–3819`). OK.

Evidence/check: remediation report:11361, Q08-34 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

### Q08-35 — Metric-row path conventions inconsistent; the finding's base is unavailable in direct calls

insert after line 134: "All metadata.metrics and hotspot paths are POSIX paths relative to the resolved target root (path itself when a directory, else its parent) — the same root the hotspot join uses. The jscpd whole-run row uses path '.'; jscpd clone file names are re-rooted from the scanned directory to the target root." Change line 200's expected path to `"."`.

Evidence/check: remediation report:11368, Q08-35 Fix verification, main/Phase70 snapshot above. Outcome: document check pending freeze; implementation check NOT RUN. Gap: implementation prerequisites/open decisions below.

## Checks to run before reporting

Run frozen-document checks only now. Exact future behavior gates below await applied source/tests. No broad runner or full-suite execution during remediation.

## Completion

Full numbered/M/X/C reconciliation, substantive review and frozen-byte outcomes required. Implementation acceptance remains pending source application, decision ratification, real engine fixtures and OCI gate. Dirty AGENTS.md and user-owned untracked plans/report/audit preserved.

## Binding amendments and complete command packets

Q08-P1 preserves five engines radon,jscpd,tach,clines,sentrux and canonical aggregate_results; top-level metrics first-producer behavior unchanged (`routing.py:543-545`, R3 resolution). New unit rows live metadata.metrics; each row engine,path,symbol,metric,unit,value,source_digest. Paths POSIX relative to the resolved target root (directory itself, otherwise parent). Whole jscpd path '.'. Radon class aggregate is excluded; real methods counted once plus nested closures. Parse errors retain other engine evidence and use source_parse_error; invalid adapter JSON terminal_reason malformed_output. All engine dispositions accounted for, including unsupported_language/no_matching_targets/skipped/applicable. Engine scopes retain actual consumed evidence.

Q08-E1 hotspot output: churn_window='90d', churn_commits, source_digest, decision='no_refactor' or 'review'; use 90 days Git history. Python reverse imports are dependency evidence; TemporalCouplingAnalyzer supplies separate co_change evidence. No test-failure artifact source exists here: failure_evidence=null, failure_evidence_reason='no_failure_source'. Git failure is unavailable, not zero churn. Add GitChurnExtractor.extract_window without changing risk_matrix caller's extract_churn contract.

Q08-X1 trial: comparable scope only radon cyclomatic points and jscpd duplicated_lines. other_engine_partial separate; excluded engines cannot fabricate comparable evidence. Baseline/candidate same OCI image/config/engine versions/file set; version drift engine_version_mismatch => inconclusive. Final status inconclusive/rejected/verified_candidate/no_improvement; improvement is CC OR duplication lower with neither increased; candidate selected tests must pass with zero skipped/errors/empty collection. Baseline and candidate rescan `/work` with `entrypoint='/usr/local/bin/python'`, argv=['-m','rush.cli','complexity','/work','--json']; never host baseline. Foundation F5 selected tests, no Q04 tool-option dependency. Required grants enforce F3 whole-operation refusal before worktree creation.

DECISION REQUIRED Q08-D3: sandbox .rush/.gitignore/worktree writes require extra artifact_write grant, or documented build+slow grants cover only invocation-owned sandbox artifacts. Both preserve no source writes and explicit audit trail; variant below requires artifact_write and remains proposal. Q08-D4: reuse PatchSandboxManager `.rush/worktrees` (actual behavior) or implement equivalent owned sibling TemporaryDirectory provider staging; sibling choice requires explicit containment/cleanup design and test before implementation. No default approved. Shared provider naming/aggregate/image/runtime choices remain README. Resolved binding choices: base Phase70, strict booleans, required row digest, F4/F5 contracts; remove older decision duplicates.

Concrete proposed helper module `src/rush/tools/complexity_evidence.py` (Q08-P1/X1), referenced from ComplexityTool.run after collecting children:

```python
from __future__ import annotations
import hashlib
import json
import tempfile
from pathlib import Path
from rush.io.physical_paths import PhysicalRoot
from rush.patch.applier import PatchApplier
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.contracts import DirtyWorkspaceError, PatchVerificationError
from rush.runtime.isolated_process import IsolationUnavailable, check_isolation_inputs, run_isolated_argv
from rush.runtime.isolated_tests import run_selected_tests_isolated

class SourceParseError(ValueError):
    def __init__(self,rows,paths):
        super().__init__('source_parse_error');self.rows=rows;self.paths=paths

def radon_rows(report, root):
    rows = [];unassessed=[]
    if not isinstance(report, dict):
        raise ValueError('malformed_output')
    def add(block, rel, digest, parent=None):
        if not isinstance(block, dict):
            raise ValueError('malformed_output')
        if block.get('type') != 'class':
            value = block.get('complexity')
            if type(value) is not int or value < 1:
                raise ValueError('malformed_output')
            rows.append(dict(engine='radon',path=rel,symbol=(parent+'.' if parent else (block.get('classname')+'.' if block.get('classname') else ''))+block.get('name','<module>'),line=block.get('lineno'),metric='cyclomatic_complexity',unit='points',value=value,source_digest=digest))
        for closure in block.get('closures', []):
            add(closure, rel, digest, (parent+'.' if parent else '')+block.get('name','<module>'))
    for name, blocks in report.items():
        file = Path(name)
        if not file.is_absolute():
            file = root / file
        rel = file.resolve().relative_to(root.resolve()).as_posix()
        data = PhysicalRoot(root).open_contained(rel).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if isinstance(blocks, dict) and 'error' in blocks:
            unassessed.append(rel); continue
        if not isinstance(blocks, list):
            raise ValueError('malformed_output')
        for block in blocks:
            add(block, rel, digest)
    if unassessed:raise SourceParseError(rows,unassessed)
    return rows

def jscpd_rows(report, root, selected):
    total = report['statistics']['total']
    if type(total.get('sources')) is not int or total['sources'] <= 0:
        raise ValueError('zero_assessed_sources')
    value = total.get('duplicatedLines')
    if type(value) is not int or value < 0:
        raise ValueError('malformed_output')
    digest = hashlib.sha256()
    for rel in sorted(selected):
        digest.update(rel.encode()); digest.update(b'\0')
        digest.update(PhysicalRoot(root).open_contained(rel).read_bytes())
    return [dict(engine='jscpd',path='.',symbol=None,metric='duplicated_lines',unit='lines',value=value,source_digest=digest.hexdigest())]

def comparable(result):
    rows = result.get('metadata', {}).get('metrics', [])
    engines = {r['engine'] for r in rows}
    if engines != {'radon', 'jscpd'}:
        raise ValueError('incomplete_comparable_assessment')
    versions = {e['engine']: e.get('engine_version') for e in result['metadata']['engines'] if e['engine'] in engines}
    if any(versions.get(e) is None for e in engines):
        raise ValueError('missing_engine_version')
    return (sum(r['value'] for r in rows if r['metric']=='cyclomatic_complexity'),sum(r['value'] for r in rows if r['metric']=='duplicated_lines')), versions

def _trial_refactor(root, patch_file, nodes, runtime_path, image_ref):
    # Contingent on Q08-D3/D4: caller has already checked chosen grant policy.
    root = root.resolve()
    check_isolation_inputs(root,runtime_path=runtime_path,image_ref=image_ref)
    if not isinstance(nodes,list) or not nodes or len(nodes)!=len(set(nodes)):
        raise ValueError('invalid verification_tests')
    for node in nodes:
        if not isinstance(node,str) or node.startswith('-') or '\0' in node:
            raise ValueError('invalid verification_tests')
        PhysicalRoot(root).open_contained(node.split('::',1)[0])
    patch = PhysicalRoot(root).open_contained(patch_file).read_text(encoding='utf-8')
    manager = PatchSandboxManager(root)
    sandbox = None
    try:
        sandbox = manager.create_sandbox()
        applied, message = PatchApplier.apply_patch_to_dir(sandbox, patch)
        if not applied:
            return {'status':'rejected','reason':'patch_rejected','message':message}
        reports = []
        receipts = []
        with tempfile.TemporaryDirectory(prefix='rush-trial-') as out:
            for label, snapshot in [('baseline',root),('candidate',sandbox)]:
                scratch = Path(out)/label; scratch.mkdir(mode=0o700)
                run = run_isolated_argv(snapshot,scratch,runtime_path=runtime_path,image_ref=image_ref,entrypoint='/usr/local/bin/python',argv=['-m','rush.cli','complexity','/work','--json'],timeout_s=120)
                if run.returncode not in (0,1):
                    return {'status':'inconclusive','reason':'rescan_failed','returncode':run.returncode}
                reports.append(json.loads(run.stdout)); receipts.append(run.receipt)
            tests_out=Path(out)/'tests'; tests_out.mkdir(mode=0o700)
            tests=run_selected_tests_isolated(sandbox,tests_out,nodes=nodes,runtime_path=runtime_path,image_ref=image_ref,python_entrypoint='/usr/local/bin/python',timeout_s=120)
            if tests.outcome!='passed' or tests.counts['failed'] or tests.counts['skipped'] or tests.counts['error'] or not tests.counts['passed']:
                return {'status':'rejected','reason':'selected_tests_not_passed','test_outcome':tests.outcome}
        def inputs(report):
            scopes=report['metadata']['engines']
            return sorted((e['engine'],e.get('config'),e.get('scope',{}).get('requested_targets')) for e in scopes if e['engine'] in ('radon','jscpd'))
        if inputs(reports[0])!=inputs(reports[1]):
            return {'status':'inconclusive','reason':'scope_or_config_mismatch'}
        before, bv = comparable(reports[0]); after, av = comparable(reports[1])
        if bv != av:
            return {'status':'inconclusive','reason':'engine_version_mismatch'}
        if any(a>b for a,b in zip(after,before)):
            status='rejected'
        elif any(a<b for a,b in zip(after,before)):
            status='verified_candidate'
        else:
            status='no_improvement'
        return {'status':status,'before':before,'after':after,'metric_scope':['radon','jscpd'],'other_engine_partial':any(e['status'] in ('skipped','error') for e in reports[1]['metadata']['engines'] if e['engine'] not in ('radon','jscpd')),'actual_scanned_root':'/work','snapshot_scope':'whole_git_HEAD','receipts':receipts}
    except (DirtyWorkspaceError,PatchVerificationError):
        return {'status':'inconclusive','reason':'dirty_or_non_git_workspace'}
    except IsolationUnavailable:
        return {'status':'skipped','reason':'isolation_unavailable'}
    except (ValueError,KeyError,TypeError) as exc:
        return {'status':'inconclusive','reason':str(exc)}
    finally:
        if sandbox is not None:
            manager.cleanup_sandbox(sandbox)
```

Controller prerequisites must validate nodes via F5 before first rescan, strict runtime/image via F4 before manager writes, patch path via PhysicalRoot and root identity Git clean/current HEAD before create. Source snapshot set/digest/config parity must compare baseline/candidate relative filenames excluding intended patch targets and fixed config digest; disagreement => inconclusive scope_or_config_mismatch. Concrete preflight/input comparison in helper above is part of proposed controller, not exercised by unchanged production. Subdirectory targets record whole_git_HEAD actual scope and original requested relative target separately; clean Git prevents silently ignoring uncommitted source. Cleanup failure is surfaced, never converted to verified_candidate.

Exact JscpdEngine.run argv replacement in src/rush/engines/jscpd.py: use json reporter into owned TemporaryDirectory; selected JS/TS directory protocol `['--reporters','json','--output',str(out),'--format','javascript,jsx,typescript,tsx','--ignore',','.join('**/'+d+'/**' for d in sorted(_SKIP_DIRS)) + ',**/.*/*',str(path)]`; read out/jscpd-report.json before cleanup and normalize strict statistics/duplicates. `_SKIP_DIRS` imported from tools.routing (existing declaration). Zero sources returns error terminal_reason zero_assessed_sources; partial sources retained actual count not invented per-file rows. Real protocol tests capture sources1/clones0 token-rich seven-function JS; clone fixture lines7/duplicatedLines6; malformed JSON/nonzero/zero report errors distinct. Radon normalize json parses raw stdout into radon_rows, source_parse_error error rather than clean, malformed_output error; leave existing raw and provenance contract. Clines shape/units remain evidence blocker: clines executable not installed; capture version+stdout real clean/nonempty/error reports before implementing clines metric mapping. Handwritten clines dict cannot satisfy capture.

Q08-M1–M6: scope contamination corrected flags/skip globs; docs gate covered; catalog all five actual engines plus truthful discovery prose FoundationF10, workflow suite warn/error regression; subdirectory sandbox receipt test; every metric digest retained; clines capture blocked with bounded version/stdout capture. X01–X18/C01–C29 applicable shared strict schema, base/grants/scope, provider, F5, docs and final zero-skip gates preserve full scope. C20 check union includes transport_parity and Phase70 t27/t16; C21 installed radon6.0.1/jscpd5.2.0 version assertions (`['radon','--version']`, `['jscpd','--version']`), local OCI test deselected by marker if runtime absent; supplied runtime missing image fails. No BLOCKED sentinel test pass.

Q08-DOC inventory serialized Foundation ownership: docs/reference/cli-reference.md, docs/reference/mcp-tool-reference.md, docs/reference/result-reference.md, docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/JSON_SCHEMA.md, docs/reference/engine-directory.md, docs/ENGINES.md, docs/ENGINE_COMPATIBILITY.md, docs/TOOL_CATALOG.md, docs/CLI_COOKBOOK.md, docs/tools/complexity.md new, docs/permissions.md, docs/user-guide/understanding-results.md, CHANGELOG.md, docs/reports/phase-64-66-documentation-coverage.md. Top-level metrics unchanged, new rows and trial decisions examples added. Audit Q08:3692–3819, engines/radon.py:37–63 corrected citations.

Future narrow commands NOT RUN (requires proposed packet/F1/F2/F4/F5/F6/new tests/real fixtures):

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_complexity.py tests/test_radon_reference.py tests/test_jscpd_reference.py tests/test_clines_reference.py tests/test_static_tools.py tests/test_phase57_invocation_context.py tests/test_workflows.py tests/test_transport_parity.py tests/test_cli_registry.py tests/test_mcp.py tests/test_sync_docs.py tests/test_phase70_t16.py tests/test_phase70_t27.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk git diff --check
```

Concrete test additions in new tests/test_complexity.py (F6 dependency, proposed NOT RUN):

```python
from transport_parity import run_cli, run_mcp

def test_metrics_keep_units(tmp_path, monkeypatch):
    test_declared_engines_accounted_for(tmp_path, monkeypatch)

def test_complexity_options_cli_mcp_parity(tmp_path):
    (tmp_path/'a.py').write_text('def f(x):\n    return 1 if x else 0\n')
    code, left = run_cli('complexity',tmp_path,cli_options=('--view','metrics'))
    right = run_mcp('rush_complexity',{'path':str(tmp_path),'view':'metrics'})
    assert code == 1
    assert [(x['engine'],x['metric'],x['unit'],x['value']) for x in left['metadata']['metrics']] == [(x['engine'],x['metric'],x['unit'],x['value']) for x in right['metadata']['metrics']]
    assert left['metadata']['engine_dispositions'] == right['metadata']['engine_dispositions']
    assert left['metadata']['scope']['coverage'] == right['metadata']['scope']['coverage']

def test_complexity_rejects_invalid_inputs_before_execution(tmp_path,monkeypatch):
    import rush.tools.complexity as module
    def forbidden(*args,**kwargs):
        raise AssertionError('invalid input must not run engine')
    monkeypatch.setattr(module,'run_engine',forbidden)
    result=module.ComplexityTool().run(tmp_path,view='invalid')
    assert result['status']=='error'
    assert result['metadata']['error']['code']=='invalid_argument'
```

Metrics parity deterministic prerequisites: captured engine protocol versions and controlled PATH identical both transports; expected CLI code1 only when captured fixture has warn/partial, assert exact snapshot result not permissive membership. Trial RED actual radon total before/after == (5,3), includes test_f comprehension complexity2. Token-rich JS fixture writes seven exported functions each taking a,b; captures sources1/clones0. Engine malformed tests assert error and terminal_reason malformed_output, zero-source fixture asserts zero_assessed_sources. No fake test assertion counts as live engine acceptance.

Exact ComplexityTool public/run replacements (Q08-P1/E1/X1) in src/rush/tools/complexity.py, retain mcp_description property and imports; add imports shown. Engine adapters must first implement raw JSON normalization described above. All grants/invalid arguments pre-engine.

```python
import json
from typing import Literal
from pydantic import StrictBool
from rush.permissions import ExecutionPermissions, build_execution_metadata, check_permissions
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.tools.complexity_evidence import radon_rows,jscpd_rows,_trial_refactor

class ComplexityToolPublicPatch:
    def __call__(self,path:Path,view:Literal['metrics','hotspots']='metrics',trial_refactor:Path|None=None,verification_tests:list[str]|None=None,runtime_path:Path|None=None,image_ref:str|None=None,allow_build:StrictBool=False,allow_slow:StrictBool=False,allow_artifact_write:StrictBool=False):
        return self.run(path,view=view,trial_refactor=trial_refactor,verification_tests=verification_tests,runtime_path=runtime_path,image_ref=image_ref,permissions=ExecutionPermissions(build=allow_build,slow=allow_slow,artifact_write=allow_artifact_write))

    def run(self,path,config=None,*,view='metrics',trial_refactor=None,verification_tests=None,runtime_path=None,image_ref=None,permissions=None):
        from rush.engines import ENGINES
        from rush.tools.common import error_result,run_engine
        from rush.tools.routing import collect_files,aggregate_results
        root=(path if path.is_dir() else path.parent).resolve()
        if view not in ('metrics','hotspots') or (trial_refactor is not None and not verification_tests):
            result=error_result(self.name,None,'invalid complexity options')
            result['metadata']={'error':{'code':'invalid_argument','message':result['summary']}}
            return result
        if trial_refactor is not None:
            # Contingent Q08-D3: artifact_write variant; alternative removes this requirement/flag.
            requested=ExecutionPermissions(build=True,slow=True,artifact_write=True)
            allowed,missing=check_permissions(requested,permissions)
            if not allowed:
                return dict(tool=self.name,engine=None,engine_version=None,status='skipped',duration_ms=0,summary='requires permission: '+', '.join(missing),findings=[],metadata={'execution':build_execution_metadata('executed',requested=requested,granted=permissions,extra={'disposition':'not_run','cause':'permission_denied'}),'refactor_trial':{'status':'denied','reason':'build_or_slow_denied'}})
        children=[];dispositions=[];selected_js=[]
        for name in ('radon','jscpd','tach','clines','sentrux'):
            engine=ENGINES[name]
            files=collect_files(path,set(engine.file_extensions))
            if name=='clines':
                files=collect_files(path,{'py','pyi','js','jsx','mjs','cjs','ts','tsx'})
            disposition='applicable' if files else 'unsupported_language'
            if not files:
                dispositions.append({'engine':name,'disposition':disposition,'status':'skipped'})
                continue
            args=[str(f) for f in files]
            if name=='jscpd':
                selected_js=[f.resolve().relative_to(root).as_posix() for f in files]
                args=[] # adapter owns restricted directory flags, selected scope receipt explicit
            child=run_engine(engine,path,args,tool_name=self.name)
            children.append(child);dispositions.append({'engine':name,'disposition':disposition,'status':child['status']})
        result=aggregate_results(self.name,children)
        metadata=result.setdefault('metadata',{}); rows=[]
        for child in children:
            rows.extend(child.get('metadata',{}).get('metrics',[]))
            if child['engine'] not in ('radon','jscpd') or child['status'] not in ('ok','warn','fail'):
                continue
            try:
                report=json.loads(child['raw']) if isinstance(child['raw'],str) else child['raw']
                rows.extend(radon_rows(report,root) if child['engine']=='radon' else jscpd_rows(report,root,selected_js))
            except (ValueError,KeyError,TypeError) as exc:
                result['status']='error';metadata['terminal_reason']=str(exc)
        metadata['metrics']=rows; metadata['engine_dispositions']=dispositions
        if view=='hotspots':
            from rush.hotspots.churn import GitChurnExtractor
            from rush.tools.blast_radius_graph import build_reverse_import_graph
            churn=GitChurnExtractor(root).extract_window(since_days=90)
            graph=build_reverse_import_graph(root)
            from rush.hotspots.coupling import TemporalCouplingAnalyzer
            from dataclasses import asdict
            pairs=TemporalCouplingAnalyzer(root).analyze_coupling(min_co_changes=2,report_unavailable=True)
            metadata['hotspots']=[dict(row,churn_window='90d',churn_commits=churn[row['path']].commit_count if churn is not None and row['path'] in churn else None,churn_evidence_status='available' if churn is not None else 'unavailable',dependency_evidence_status='available' if row['path'].endswith('.py') else 'unavailable',dependent_count=len(graph.get(Path(row['path']).stem,[])) if row['path'].endswith('.py') else None,failure_evidence=None,failure_evidence_reason='no_failure_source',decision='review' if churn is not None and row['path'] in churn and churn[row['path']].commit_count>0 else 'no_refactor') for row in rows]
            for row in metadata['hotspots']:
                row['co_change_status']='unavailable' if pairs is None else 'available'
                row['co_change_evidence']=None if pairs is None else [asdict(pair) for pair in pairs if row['path'] in (pair.file_a,pair.file_b)]
        if trial_refactor is not None:
            try:
                patch_path=Path(trial_refactor)
                if patch_path.is_absolute():patch_path=patch_path.relative_to(root)
                metadata['refactor_trial']=_trial_refactor(root,patch_path,verification_tests,runtime_path,image_ref)
                if metadata['refactor_trial']['status']=='skipped':result['status']='skipped'
            except (ValueError,ContainmentError) as exc:
                result['status']='error';metadata['error']={'code':'path_escape' if isinstance(exc,ContainmentError) else 'invalid_argument','message':str(exc)}
        return result
```

Class above is patch container only: transplant methods into existing ComplexityTool, never add second runtime class. `_SKIP_DIRS` directory scanning preserves actual selected files; child_scope unavailable for self-discovery remains honest until directory runner confirms restricted input receipt. Clines rows withheld until real protocol capture; no placeholder metric.

Q08-E1 exact additive method `GitChurnExtractor.extract_window` in src/rush/hotspots/churn.py; imports/dataclass/run_subprocess already exist. extract_churn unchanged.

```python
    def extract_window(self, since_days: int = 90) -> dict[str, FileChurnStats] | None:
        if type(since_days) is not int or since_days < 1:
            raise ValueError('since_days must be positive integer')
        proc=run_subprocess(['git','--no-pager','log',f'--since={since_days} days ago','--numstat','--format=COMMIT|%an|%s'],cwd=self.repo_root)
        if proc.returncode!=0:
            return None
        data={}; author='unknown'
        for line in proc.stdout.splitlines():
            if line.startswith('COMMIT|'):
                author=line.split('|',2)[1]; continue
            parts=line.split('\t')
            if len(parts)!=3:continue
            try:ins,dels=int(parts[0]),int(parts[1])
            except ValueError:continue
            row=data.setdefault(parts[2],{'commits':0,'ins':0,'dels':0,'authors':set()})
            row['commits']+=1;row['ins']+=ins;row['dels']+=dels;row['authors'].add(author)
        return {fp:FileChurnStats(file_path=fp,commit_count=d['commits'],insertions=d['ins'],deletions=d['dels'],total_churn=d['ins']+d['dels'],unique_authors=d['authors']) for fp,d in data.items()}
```

Q08-P1 exact RadonEngine.normalize replacement in src/rush/engines/radon.py (retain existing run argv/ownership/version probes):

```python
    def normalize(self,raw:EngineResult,path:Path,tool_name:str)->ToolResult:
        from rush.tools.complexity_evidence import radon_rows
        root=(path if path.is_dir() else path.parent).resolve()
        try:
            if raw.get('exit_code')!=0:
                raise ValueError('nonzero_exit')
            report=json.loads(raw.get('stdout') or '')
            rows=radon_rows(report,root)
        except (ValueError,KeyError,TypeError) as exc:
            return ToolResult(tool=tool_name,engine=self.name,engine_version=self.version(),status='error',duration_ms=0,summary=f'radon: {exc}',findings=[],metadata={'terminal_reason':str(exc) if str(exc) in ('source_parse_error','nonzero_exit') else 'malformed_output','metrics':getattr(exc,'rows',[]),'unassessed_paths':getattr(exc,'paths',[])})
        findings=[Finding(path=r['path'],line=r['line'],rule='radon',severity='warn',message=f"{r['symbol']}: complexity {r['value']}") for r in rows if r['value']>10]
        return ToolResult(tool=tool_name,engine=self.name,engine_version=self.version(),status='warn' if findings else 'ok',duration_ms=0,summary=f'radon: {len(findings)} complex item(s)',findings=findings,raw=report,metrics={'cyclomatic_complexity':sum(r['value'] for r in rows)})
```

Radon JSONDecodeError carries malformed_output exactly, not exception text. Regression fixtures assert real threshold/current rule identity and line values; existing rule radon/threshold10/message/line contract preserved from engines/radon.py:37–63. Top-level radon metrics additions remain compatible first-producer behavior, not shared routing overwrite.

Q08-P1 exact JscpdEngine.run/normalize in src/rush/engines/jscpd.py, import tempfile,json and _SKIP_DIRS. Preserve owner_instance_id/run_id and existing resolve_binary/ownership_kwargs/run_subprocess imports.

```python
    def run(self,path:Path,args:list[str],cwd:Path|None=None,*,owner_instance_id=None,run_id=None)->EngineResult:
        import tempfile
        from rush.tools.routing import _SKIP_DIRS
        binary=resolve_binary(self.binary) or self.binary
        scan=path if path.is_dir() else path.parent
        with tempfile.TemporaryDirectory(prefix='rush-jscpd-') as output:
            ignore=','.join('**/'+d+'/**' for d in sorted(_SKIP_DIRS))+',**/.*/*'
            argv=[binary,'--reporters','json','--output',output,'--format','javascript,jsx,typescript,tsx','--ignore',ignore,str(path)]
            proc=run_subprocess(argv,cwd=cwd or scan,timeout=120,**ownership_kwargs(owner_instance_id,run_id))
            report=Path(output)/'jscpd-report.json'
            return {'exit_code':proc.returncode,'stdout':report.read_text(encoding='utf-8') if report.is_file() else '', 'stderr':proc.stderr,'argv':argv}

    def normalize(self,raw:EngineResult,path:Path,tool_name:str)->ToolResult:
        try:
            if raw.get('exit_code')!=0:raise ValueError('nonzero_exit')
            report=json.loads(raw.get('stdout') or '')
            total=report['statistics']['total'];duplicates=report['duplicates']
            if not isinstance(duplicates,list) or type(total.get('sources')) is not int or type(total.get('duplicatedLines')) is not int:
                raise ValueError('malformed_output')
            if total['sources']==0:raise ValueError('zero_assessed_sources')
            findings=[]
            for clone in duplicates:
                first=clone['firstFile'];second=clone['secondFile'];lines=clone['lines']
                for location,other in [(first,second),(second,first)]:
                    findings.append(Finding(path=location['name'],line=location['start'],rule='jscpd',severity='warn',message=f"duplicates {other['name']} ({lines} lines)"))
        except (ValueError,KeyError,TypeError) as exc:
            reason=str(exc) if str(exc) in ('nonzero_exit','zero_assessed_sources') else 'malformed_output'
            return ToolResult(tool=tool_name,engine=self.name,engine_version=self.version(),status='error',duration_ms=0,summary=f'jscpd: {reason}',findings=[],metadata={'terminal_reason':reason})
        return ToolResult(tool=tool_name,engine=self.name,engine_version=self.version(),status='warn' if findings else 'ok',duration_ms=0,summary=f'jscpd: {len(findings)} duplicate(s)',findings=findings,raw=json.dumps(report),metrics={'duplicated_lines':total['duplicatedLines']},metadata={'assessed_sources':total['sources']})
```

Jscpd explicit single-file target uses final positional path, never parent directory. Scanned file-set and hidden/vendor exclusion regression includes Python file and node_modules/venv/dist.

Q08-E1 additive opt-in unavailable carrier in `src/rush/hotspots/coupling.py`; default callers retain existing list contract, new evidence caller receives None on Git failure. Existing parser/calculation unchanged.

```diff
-    def analyze_coupling(self, min_co_changes: int = 2) -> list[CoChangePair]:
+    def analyze_coupling(self, min_co_changes: int = 2, *, report_unavailable: bool = False) -> list[CoChangePair] | None:
@@
         if proc.returncode != 0:
-            return []
+            return None if report_unavailable else []
```

Clines capture prerequisite, Q08-24/M6: installed actual executable with successful `clines --version`; version is unknown until captured, never invented. Existing grounded engine argv is `[resolved_clines, '--json', str(fixture_root)]` (`engines/clines.py:13–90`), cwd fixture_root, timeout120. Empty explicit args avoid duplicate selected paths plus directory. Fixture contains real Python/JS sources; capture stdout, stderr, exit code, argv and version for clean and warning/error runs as `tests/fixtures/engine_reports/clines/captured-<actual-version>.json` and adjacent version/argv receipt. Only then derive producer metric keys/units from authoritative report and add ClinesEngine mapping plus exact-value test. Current handwritten findings.json proves neither protocol nor total_loc/lines. Until installation/capture exists, this is prerequisite failure and no metric key/unit is asserted. Missing engine remains skipped with canonical unavailable scope; installed malformed/nonzero report remains error. Real jscpd fixtures are `tests/fixtures/engine_reports/jscpd-5.2.0-{clean,clone,zero-source}.json`; captured clone.lines7 and statistics.total.duplicatedLines6 deliberately differ.

Required new co-change regression invokes real proposed `analyze_coupling(report_unavailable=True)`: mocked git returncode2 -> None/unavailable, returncode0 empty stdout -> []/available, two commits changing a.py+b.py -> pair(a.py,b.py,2,100.0). Existing default returncode2 still []. This is computation/availability check, not fabricated receipt arithmetic.
