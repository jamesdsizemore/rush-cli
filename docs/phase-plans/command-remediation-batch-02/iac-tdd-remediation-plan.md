# Q16 — iac TDD remediation development plan

Goal: disclose Terraform module execution scope and preserve selected-file presentation without hiding dependency diagnostics. Covers complete audit Q16 lines 5797–6154; saved-plan association assessed separately from isolated candidate-impact proposal. No Terraform apply route.

## Requirement ledger

| Requirement/category | Source evidence | Exact change / acceptance |
|---|---|---|
| Repair: silent file-to-module widening | tools/iac.py:22–35 collects .tf then adapters discard args; tflint.py:31–48 and checkov.py:32–60 run directory | T1 group requested .tf by parent module, once per engine/module; expose execution_modules/module_context_files and unavailable actual consumption |
| Preserve missing/error children | routing.py:478–612 already preserves engines and mixed precedence | Reuse aggregate_results; no duplicate aggregation fix; test Checkov missing alongside TFLint |
| Preserve parser/config safety | current TFLint/Checkov parse structured errors and bounded paths; Checkov blocks downloads, TFLint no module traversal | Keep exact adapters, tests/test_tflint_reference.py and test_checkov_reference.py |
| Ordinary extension/fix continuation, proposed | scope and plan_evidence absent current API | T2 scope=file filters displayed findings only; saved JSON hash and exact resource-address association; no execution |
| Distinct expansion, proposed/unapproved | trial_plan_impact and isolated_process absent | T4 baseline/candidate plans from identical copied state/provider fixtures, destruction delta allowlist, never apply |
| User baselines | shared provision/model/voice/companion contract | Preserve factual redacted evidence; provisioning is not proposed innovation |

## First task and observed RED

Current API IacTool.run(root/main.tf), canonical controlled successful children, executed via offline Python3.12.12. Expected scope.module_context_files=[main.tf]; observed {"version":1,"kind":"aggregate","coverage":"unavailable","requested_targets":[],"logical_root":null}. Assertion failed on missing facts, not a future scope keyword. Current real tflint/checkov unavailable. Existing aggregate preservation is source-observed, not newly implemented.

Implement disclosed module selection in rush-cli; read AGENTS.md, Phase70 T8/T9/T16 and this document first.

# Feature: T1 — explicit Terraform module execution context

## Required behavior

Keep __call__(path:Path) and run(path,*,config=None) valid. For file, requested is only that .tf; directory discovers existing .tf under normal hidden/generated exclusions. A Terraform module is parent directory of each requested .tf. Group/deduplicate/sort parents and invoke TFLint then Checkov once per module. Each adapter already scans directory; do not pass a false selected-file argument.

Scope version1 includes kind=files, logical_root, requested_targets, requested_files, execution_modules, module_context_files, reported_findings_scope="module", dependency_context_diagnostics={count,status,paths}, coverage and consumed_file_count=null with reason engine_discovers_directory_contents. Context inventory records physically contained immediate *.tf and *.tf.json for each module; scanner discovery may be wider, so this inventory never proves consumed count. Hidden .terraform is dependency input, not requested source. Findings paths validate against execution root, then map to logical root. Preserve engine status/provenance and source environment. Invalid/empty/missing outcomes follow T9. No config/provider fetch, init, refresh or apply.

## Deliverables

Command owner modifies src/rush/tools/iac.py::IacTool.run and adds tests/test_iac.py. Adapters preserved. Shared owner changes exact command rows/docs/tests listed below.

Runnable first RED, proposed tests/test_iac.py:
~~~python
from pathlib import Path
from unittest.mock import patch
from rush.tools.iac import IacTool

def test_single_file_discloses_module_scan(tmp_path):
    (tmp_path / "main.tf").write_text('variable "x" {}\n')
    (tmp_path / "variables.tf").write_text('variable "y" {}\n')
    calls = []
    def engine_child(engine, path, args, **kwargs):
        calls.append((engine.name, path, args))
        return dict(tool="iac", engine=engine.name, engine_version="fixture",
            status="ok", duration_ms=0, summary="clean", findings=[], raw=None)
    with patch("rush.tools.iac.run_engine", side_effect=engine_child):
        result = IacTool().run(tmp_path / "main.tf")
    assert calls == [("tflint", tmp_path, []), ("checkov", tmp_path, [])]
    scope = result["metadata"]["scope"]
    assert scope["requested_files"] == [str(tmp_path / "main.tf")]
    assert scope["module_context_files"] == [
        str(tmp_path / "main.tf"), str(tmp_path / "variables.tf")]
    assert scope["consumed_file_count"] is None
~~~

Minimum GREEN dispatch replacement in src/rush/tools/iac.py::IacTool.run:
~~~python
requested = sorted(set(collect_files(path, set(self.extensions), strict=True)))
modules = sorted({p.parent for p in requested})
children = [
    run_engine(ENGINES[name], module, [], tool_name=self.name)
    for module in modules for name in self.engine_names
]
result = aggregate_results(self.name, children)
~~~
Complete surrounding algorithm: derive execution/current logical roots via existing ambient helpers; PhysicalRoot validates every requested/context file before child calls, without resolve-before-check. Reject invalid path; empty requested gives no_supported_targets/skipped. Build metadata.scope above; module_context_files sorted unique literal file paths, excluding symlink targets. Preserve metadata.engines/execution. For each finding, canonicalize contained path relative to execution root; partition requested/context sets; context status derives from underlying finding severity (error=>fail, any other diagnostic=>warn), never from absence of displayed findings. Parent status stays aggregate engine status. Coverage tracks engine coverage (directory discovery unavailable), not number of discovered filenames. A skipped child is recorded; partial requested engine execution is explicitly coverage=partial even if file count unknown.

Regression/refactor tests: test_modules_called_once covers two files same module/two modules; test_missing_checkov_partial asserts warn for TFLint ok+Checkov skipped and exact child states; test_context_failure_not_clean asserts parent fail survives requested-file filtering; test_symlink_module_rejected asserts zero scanner calls; test_staged_module_bytes uses actual staged source input, logical scope mapping. Update existing tests/test_checkov_reference.py::test_iac_aggregates_tflint_and_checkov_in_declared_order only if its exact added keyword capture requires it; no adapter protocol rewrite.

## Constraints

No file-only execution claim. No nested module auto traversal, provider installation or Terraform execution in ordinary lint. No scope null→zero inference.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_iac.py::test_single_file_discloses_module_scan tests/test_iac.py::test_modules_called_once tests/test_iac.py::test_missing_checkov_partial tests/test_tflint_reference.py tests/test_checkov_reference.py -q

## Completion

Exact parent-module dispatch and factual context metadata pass; existing parser/transport guarantees preserved.

# Feature: T2 — explicit displayed scope and digest-bound saved plan (proposed ordinary extension)

## Required behavior

IacTool.__call__ gains scope:str="module", plan_evidence:str|None=None. run accepts same plus config/permissions. CLI explicit click.Option(["--scope"],type=click.Choice(["file","module"]),default="module"), click.Option(["--plan-evidence"],type=click.Path(dir_okay=False),default=None). No auto-read saved plan or effectful config settings.

scope=file only filters returned findings to requested files; scope remains explicit full-module execution with context diagnostics count/status/paths. Empty filtered findings never changes aggregate failure. plan_evidence relative to normalized logical target module/root, contained by PhysicalRoot; when staged, read supplied saved plan from logical project but record that external saved evidence identity separately from staged source. Max4MiB UTF-8 JSON, dict resource_changes list ≤100000, unique nonempty address strings, change.actions nonempty lists whose values are no-op/create/read/update/delete/forget. Invalid/duplicate/unknown actions => error saved_plan_invalid; no partial association. SHA256 exact bytes. Never copy before/after resource values (may contain secrets).

metadata.plan_evidence={sha256,resource_count,finding_links:[{path,rule,resource_address,actions,linked,unlinked_reason}]}; linked only explicit engine field resource/resource_address matches exact address. Current Checkov parser drops resource field: extend src/rush/engines/checkov.py::_parse_checkov_report to preserve validated nonempty resource in Finding.extensions.resource_address, not invented top-level schema. TFLint lacks explicit address: stays unlinked. Do not infer from message or path. Before file-only diagnostic looked plan-linked by assumption; after exact linkage or explicit missing-address reason.

Runnable acceptance:
~~~python
def test_plan_evidence_exact_address(tmp_path):
    import json, hashlib
    from unittest.mock import patch
    from rush.tools.iac import IacTool
    (tmp_path / "main.tf").write_text('resource "aws_s3_bucket" "x" {}\n')
    raw = b'{"resource_changes":[{"address":"aws_s3_bucket.x","change":{"actions":["update"]}}]}'
    (tmp_path / "plan.json").write_bytes(raw)
    def child(engine, path, args, **kwargs):
        return dict(tool="iac",engine=engine.name,engine_version="fixture",status="warn",
            duration_ms=0,summary="finding",raw=None,findings=[{
                "path":str(tmp_path/"main.tf"),"line":1,"rule":"CKV_FIXTURE",
                "severity":"warn","message":"fixture",
                "extensions":{"resource_address":"aws_s3_bucket.x"}}])
    with patch("rush.tools.iac.run_engine",side_effect=child):
        result=IacTool().run(tmp_path/"main.tf",scope="file",plan_evidence="plan.json")
    evidence=result["metadata"]["plan_evidence"]
    assert evidence["sha256"]==hashlib.sha256(raw).hexdigest()
    assert len(evidence["finding_links"])==2
    assert evidence["finding_links"]==[{
        "path":str(tmp_path/"main.tf"),"rule":"CKV_FIXTURE",
        "resource_address":"aws_s3_bucket.x","actions":["update"],
        "linked":True,"unlinked_reason":None}]*2
~~~
Initially future keyword absence is feature absence, separate from T1 RED.

## Deliverables

Command owner: src/rush/tools/iac.py::IacTool.__call__/run and read_plan_evidence(root,path,findings)->dict with full validation algorithm above; src/rush/engines/checkov.py::_parse_checkov_report only resource preservation; tests/test_iac.py::test_plan_evidence_exact_address/::test_plan_unlinked_without_address/::test_plan_rejects_duplicate_or_escape; tests/test_checkov_reference.py resource field preservation. Shared owner explicit CLI options/MCP schema/docs.

## Constraints

No plan/apply process, no network; source-address identity mandatory. Plan import is historical evidence, not execution proof.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_iac.py::test_plan_evidence_exact_address tests/test_iac.py::test_plan_unlinked_without_address tests/test_iac.py::test_plan_rejects_duplicate_or_escape tests/test_checkov_reference.py -q

## Completion

Saved-plan bytes bound by hash; exact explicit addresses only; full module status survives filter. Proposal implementation requires separate authorization.

# Feature: T4 — candidate destructive-impact trial (distinct proposal, unapproved)

## Required behavior

Typed request additions: trial_plan_impact:str|None=None (patch path), state_fixture:str|None=None, provider_fixture:str|None=None, allowed_destroy_ids:list[str]|None=None (normalizes []), runtime_path:str|None=None,image_ref:str|None=None; allow_build/allow_slow/allow_artifact_write strict bool=False. CLI same hyphenated names; --allow-destroy repeatable maps to list. All three grants required before scanner, scratch or runtime probes when trial requested. P0 required; fixed image entrypoints /usr/bin/git and /usr/local/bin/terraform. Audit relative "git"/"terraform" violates absolute entrypoint requirement and must not be copied.

Define trial_plan_impact(root,patch_path,state_fixture,*,provider_fixture,allowed_destroy_ids,runtime_path,image_ref,permissions)->dict in iac.py. Full algorithm:
1. Validate contained patch/state/provider paths, max4MiB patch/state; state JSON Terraform format version4, no remote backend config; .terraform.lock.hcl required. Source tree rejects symlinks/reparse; snapshot all source, state, lock, provider file SHA256, excluding .git/.rush. Trial source must contain exactly one module; no live cloud credentials passed.
2. Copy source into private scratch/baseline and scratch/candidate excluding .git/.rush; inject identical selected state as terraform.tfstate and initialized offline provider fixture as .terraform. Only test-owned copies replaced. Provider bytes and lock tied to pinned image architecture; no init. Reject backend blocks unless backend type is local; set TF_DATA_DIR per copy through Terraform -chdir working directory and existing .terraform, not unrestricted extra environment.
3. P0 executes /usr/bin/git -C /out/candidate apply --check /out/candidate.patch then apply. Revalidate candidate with PhysicalRoot; reject patch change to state, lock, provider fixture, symlink or any source outside module. Hash protected inputs and source again before planning. A failed patch is error, not unchanged candidate.
4. For baseline then candidate use /usr/local/bin/terraform -chdir=/out/<name> plan -input=false -refresh=false -lock=false -out=/out/<name>.plan, timeout180, then show -json /out/<name>.plan timeout30. No init, refresh, apply or remote state route. Offline fixture/image must satisfy provider load; failures produce error and no impact claim.
5. Strict parse resource_changes (same action enum as T2), build address→actions for both; classify destructive iff delete present, including delete/create replacement. new_destructive_ids = candidate_delete_set - baseline_delete_set. Block if any new IDs outside explicit allowed_destroy_ids; allowlist cannot authorize apply. Hash plans, original state, provider lock and patch; avoid outputting resource before/after values. Rehash original root unchanged. Cleanup P0 containers and owned scratch on all outcomes.

Return metadata.plan_impact_trial={operation:"plan_impact_trial",applied:false,plans:{baseline:{actions,digest},candidate:{actions,digest}},state_digest,provider_lock_digest,patch_digest,new_destructive_ids,status:"blocked"|"candidate"}. blocked maps fail; unavailable P0 retains scanner evidence with incomplete warn; failed child error. Before lint clean says nothing about replacement; after patch changing terraform_data.x input creates delete/create and exact ID blocked.

## Deliverables

Command module helper plus tests/test_iac.py::test_candidate_plan_blocks_new_subnet_replace/::test_trial_denied_zero_child/::test_trial_state_provider_mutation_rejected/::test_real_offline_terraform_trial. Use complete test fixtures in test body, no separate provider download. Real test fixture uses preinstalled Terraform with built-in terraform_data (Terraform version whose help/fixture supports it, no invented source minimum) and local state produced beforehand in owned temp test directory with explicit setup grant; trial itself never apply. Candidate patch adds replace_triggered_by against a controlled resource change; actual plan must show delete/create. External aws_subnet example is controlled adapter case, not a real cloud claim. Exact test expects new_destructive_ids=["terraform_data.subject"], blocked then candidate when same ID explicitly allowed, source/state hashes unchanged.

Controlled test uses actual git apply in private scratch and only substitutes Terraform subprocess reports; assert six calls in order, compare actual candidate source bytes to select alternate report. A toy set-difference assertion alone is insufficient. Include real P0 denial tests inline below.

## Constraints

No production state, credentials, apply, automatic remediation or simulated provider behavior in real acceptance. Limit address count100000, output4MiB; malformed/missing/truncated plans error. Runtime and initialized offline fixture must already be approved.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_iac.py::test_candidate_plan_blocks_new_subnet_replace tests/test_iac.py::test_trial_denied_zero_child tests/test_iac.py::test_trial_state_provider_mutation_rejected tests/test_iac.py::test_real_offline_terraform_trial tests/test_isolated_process.py -q

## Completion

Actual paired plans prove introduced destructive IDs under identical state/provider constraints, source unchanged, owned resources removed. Remains proposed until separately authorized.

### T4 runnable candidate-impact controller RED

Proposed complete additions to tests/test_iac.py. The helper is absent today; initial failure is interface absence, separately from observed T1 repair. Git patch application below is real; Terraform boundary supplies paired reports selected by actual candidate bytes. This proves controller/patch/protected-state/destruction behavior, not real Terraform/provider confinement.

~~~python
def test_candidate_plan_blocks_new_subnet_replace(tmp_path):
    import json, shutil, subprocess
    from pathlib import Path
    from unittest.mock import patch
    from rush.tools.iac import trial_plan_impact
    from rush.permissions import ExecutionPermissions
    root=tmp_path/"module"; root.mkdir()
    original='resource "terraform_data" "subject" {\n  triggers_replace = "old"\n}\n'
    (root/"main.tf").write_text(original)
    (root/".terraform.lock.hcl").write_text("# built-in provider only\n")
    state={"version":4,"terraform_version":"1.5.0","serial":1,
           "lineage":"00000000-0000-4000-8000-000000000001","outputs":{},"resources":[]}
    (root/"state.json").write_text(json.dumps(state))
    (root/"change.patch").write_text(
        "diff --git a/main.tf b/main.tf\n--- a/main.tf\n+++ b/main.tf\n"
        "@@ -1,3 +1,3 @@\n resource \"terraform_data\" \"subject\" {\n"
        "-  triggers_replace = \"old\"\n+  triggers_replace = \"new\"\n }\n")
    calls=[]
    git=shutil.which("git")
    assert git is not None
    def child(source,scratch,*,entrypoint,argv,**kwargs):
        calls.append((entrypoint,list(argv)))
        if entrypoint=="/usr/bin/git":
            translated=[arg.replace("/out/",str(scratch)+"/") for arg in argv]
            return subprocess.run([git,*translated],capture_output=True,text=True,timeout=10)
        assert entrypoint=="/usr/local/bin/terraform"
        assert "apply" not in argv and "init" not in argv
        if "plan" in argv:
            assert "-refresh=false" in argv
            kind="candidate" if "candidate" in argv[0] else "baseline"
            (scratch/f"{kind}.plan").write_bytes(("binary-"+kind).encode())
        else:
            assert "show" in argv
        if "show" in argv:
            folder="candidate" if "candidate" in argv[0] else "baseline"
            source_text=(scratch/folder/"main.tf").read_text()
            actions=["delete","create"] if '"new"' in source_text else ["no-op"]
            payload={"resource_changes":[{"address":"terraform_data.subject",
                                         "change":{"actions":actions}}]}
            return subprocess.CompletedProcess(argv,0,json.dumps(payload),"")
        return subprocess.CompletedProcess(argv,0,"","")
    grants=ExecutionPermissions(build=True,slow=True,artifact_write=True)
    with patch("rush.runtime.isolated_process.run_isolated_argv",side_effect=child):
        result=trial_plan_impact(root,"change.patch","state.json",
            provider_fixture=None,allowed_destroy_ids=[],runtime_path="/fixture/docker",
            image_ref="fixture@sha256:"+"0"*64,permissions=grants)
        assert result["status"]=="blocked"
        assert result["new_destructive_ids"]==["terraform_data.subject"]
        assert result["applied"] is False
        assert [name for name,args in calls]==[
            "/usr/bin/git","/usr/bin/git","/usr/local/bin/terraform",
            "/usr/local/bin/terraform","/usr/local/bin/terraform","/usr/local/bin/terraform"]
        calls.clear()
        allowed=trial_plan_impact(root,"change.patch","state.json",
            provider_fixture=None,allowed_destroy_ids=["terraform_data.subject"],
            runtime_path="/fixture/docker",image_ref="fixture@sha256:"+"0"*64,
            permissions=grants)
        assert allowed["status"]=="candidate"
        calls.clear()
        try:
            trial_plan_impact(root,"change.patch","state.json",provider_fixture=None,
                allowed_destroy_ids=[],runtime_path="/fixture/docker",
                image_ref="fixture@sha256:"+"0"*64,permissions=ExecutionPermissions())
        except PermissionError:
            pass
        else:
            raise AssertionError("denied trial ran")
        assert calls==[]
    assert (root/"main.tf").read_text()==original
    assert json.loads((root/"state.json").read_text())==state
~~~

Concrete GREEN decision core at end of trial_plan_impact, after actual apply/plan/show algorithm:
~~~python
def destructive(actions):
    return {address for address, values in actions.items() if "delete" in values}
introduced=sorted(destructive(plans["candidate"]["actions"])
                  -destructive(plans["baseline"]["actions"]))
blocked=sorted(set(introduced)-set(allowed_destroy_ids))
return {"operation":"plan_impact_trial","applied":False,"plans":plans,
        "state_digest":hashlib.sha256(state_bytes).hexdigest(),
        "provider_lock_digest":hashlib.sha256(lock_bytes).hexdigest(),
        "patch_digest":hashlib.sha256(patch_bytes).hexdigest(),
        "new_destructive_ids":introduced,
        "status":"blocked" if blocked else "candidate"}
~~~
state_bytes/lock_bytes/patch_bytes are exact contained bytes captured before copying; plans are parsed actual show outputs by complete T4 algorithm, not caller data.

Genuine Terraform fixture, proposed tests/test_iac.py::test_real_offline_terraform_trial, uses same complete test setup above with real P0 instead of child patch and literal resource state populated:
~~~python
resource_state={"version":4,"terraform_version":"1.5.0","serial":1,
    "lineage":"00000000-0000-4000-8000-000000000001","outputs":{},
    "resources":[{"mode":"managed","type":"terraform_data","name":"subject",
      "provider":'provider["terraform.io/builtin/terraform"]',
      "instances":[{"schema_version":0,"attributes":{
        "id":"fixture-subject","input":None,"output":None,
        "triggers_replace":{"value":"old","type":"string"}},"sensitive_attributes":[]}]}]}
~~~
The following complete test uses resource_state above as its module fixture. It performs real patch, plan, and show subprocesses through P0; no provider download and no setup apply. Selected local Terraform image must accept this built-in state schema; incompatible image fails fixture acceptance. terraform_version is fixture provenance, not a numeric compatibility policy.

~~~python
def test_real_offline_terraform_trial(tmp_path):
    import json, os, subprocess
    from pathlib import Path
    from unittest.mock import patch
    import rush.runtime.isolated_process as isolated
    from rush.permissions import ExecutionPermissions
    from rush.tools.iac import trial_plan_impact
    runtime=Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image=os.environ["RUSH_TEST_TERRAFORM_IMAGE"]
    root=tmp_path/"module"; root.mkdir()
    (root/"main.tf").write_text(
        'resource "terraform_data" "subject" {\n  triggers_replace = "old"\n}\n')
    (root/".terraform.lock.hcl").write_text("# built-in provider only\n")
    resource_state={"version":4,"terraform_version":"1.5.0","serial":1,
        "lineage":"00000000-0000-4000-8000-000000000001","outputs":{},
        "resources":[{"mode":"managed","type":"terraform_data","name":"subject",
          "provider":'provider["terraform.io/builtin/terraform"]',
          "instances":[{"schema_version":0,"attributes":{
            "id":"fixture-subject","input":None,"output":None,
            "triggers_replace":{"value":"old","type":"string"}},"sensitive_attributes":[]}]}]}
    (root/"state.json").write_text(json.dumps(resource_state))
    (root/"change.patch").write_text(
        'diff --git a/main.tf b/main.tf\n--- a/main.tf\n+++ b/main.tf\n'
        '@@ -1,3 +1,3 @@\n resource "terraform_data" "subject" {\n'
        '-  triggers_replace = "old"\n+  triggers_replace = "new"\n }\n')
    before={p.name:p.read_bytes() for p in root.iterdir()}
    actual=isolated.run_subprocess
    created=[]
    def observed(argv,**kwargs):
        if len(argv)>1 and argv[1]=="create":
            created.append(argv[argv.index("--name")+1])
        return actual(argv,**kwargs)
    grants=ExecutionPermissions(build=True,slow=True,artifact_write=True)
    with patch.object(isolated,"run_subprocess",side_effect=observed):
        result=trial_plan_impact(root,"change.patch","state.json",
            provider_fixture=None,allowed_destroy_ids=[],runtime_path=str(runtime),
            image_ref=image,permissions=grants)
    assert result["status"]=="blocked"
    assert result["new_destructive_ids"]==["terraform_data.subject"]
    assert result["applied"] is False
    assert result["plans"]["baseline"]["actions"]=={"terraform_data.subject":["no-op"]}
    assert result["plans"]["candidate"]["actions"]=={"terraform_data.subject":["delete","create"]}
    assert {name:(root/name).read_bytes() for name in before}==before
    assert len(created)==6
    for name in created:
        inspected=subprocess.run([str(runtime),"container","inspect",name],
            capture_output=True,text=True,timeout=10)
        assert inspected.returncode!=0, inspected.stdout
~~~

Run explicitly with preinstalled pinned image after P0 passes:
`rtk proxy env -u PYTHONPATH UV_OFFLINE=1 uv run --python 3.12 --extra dev python -m pytest tests/test_iac.py::test_real_offline_terraform_trial -q`.
Missing RUSH_TEST_OCI_RUNTIME/RUSH_TEST_TERRAFORM_IMAGE blocks genuine-engine acceptance; this planning session did not run the future test.

## Complete implementation and route packet — review corrections

These literal bodies implement earlier algorithms; they are proposed replacements in the future implementation checkout, not code installed during planning. Preserve existing imports/helpers not replaced. Every helper below has its exact caller in the full class replacement; no hidden dispatcher or second runtime. Command owner owns command-local definitions; Batch integration owner owns catalog/CLI/MCP/reference changes. Request-only options cannot be activated by project configuration.

### Complete command-local controllers
Insert these module-level bodies in src/rush/tools/iac.py; replace earlier pseudocode descriptions, preserve T1 existing repair/parser.
~~~python
def source_manifest(root):
    import hashlib,os,stat
    from pathlib import Path
    from rush.workflows.projects import open_contained_file
    from rush.io.physical_paths import PhysicalRoot
    root=Path(root);physical=PhysicalRoot(root);found={};total=0
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in {".git",".rush"})
        for name in dirs+sorted(files):
            relative=(Path(folder)/name).relative_to(root)
            checked=physical.open_contained(relative)
            mode=checked.lstat().st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError("unsupported_source_type")
            fd=open_contained_file(root,relative.as_posix())
            try:
                digest=hashlib.sha256()
                while block:=os.read(fd,1024*1024):
                    total+=len(block)
                    if total>1024**3:
                        raise ValueError("source_limit_exceeded")
                    digest.update(block)
            finally:
                os.close(fd)
            found[relative.as_posix()]=digest.hexdigest()
            if len(found)>100000:
                raise ValueError("source_limit_exceeded")
    return dict(sorted(found.items()))


def _copy_snapshot(root,destination,manifest):
    import hashlib,os,stat
    from pathlib import Path
    from rush.workflows.projects import open_contained_file
    for name,expected in manifest.items():
        fd=open_contained_file(Path(root),name)
        try:
            target=Path(destination)/name;target.parent.mkdir(parents=True,exist_ok=True)
            digest=hashlib.sha256()
            with os.fdopen(fd,"rb",closefd=False) as source,target.open("xb") as sink:
                while chunk:=source.read(1024*1024):
                    digest.update(chunk);sink.write(chunk)
            if digest.hexdigest()!=expected:raise ValueError("source_changed")
            target.chmod(stat.S_IMODE(os.fstat(fd).st_mode)&0o777)
        finally:os.close(fd)

def source_digest(manifest):
    import hashlib,json
    return hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _contained_bytes(root,path,limit=4*1024*1024):
    import os
    from pathlib import Path
    from rush.workflows.projects import open_contained_file
    path=Path(path);root=Path(root)
    relative=path.relative_to(root) if path.is_absolute() else path
    fd=open_contained_file(root,relative.as_posix())
    try:
        with os.fdopen(fd,"rb",closefd=False) as stream:
            raw=stream.read(limit+1)
    finally:
        os.close(fd)
    if len(raw)>limit:
        raise ValueError("input_too_large")
    return raw


def _plan_actions(raw):
    import json
    payload=json.loads(raw)
    changes=payload.get("resource_changes") if isinstance(payload,dict) else None
    if not isinstance(changes,list) or len(changes)>100000:
        raise ValueError("saved_plan_invalid")
    actions={}
    for row in changes:
        if not isinstance(row,dict):
            raise ValueError("saved_plan_invalid")
        address=row.get("address");change=row.get("change")
        values=change.get("actions") if isinstance(change,dict) else None
        if (not isinstance(address,str) or not address or address in actions
                or not isinstance(values,list) or not values
                or any(v not in {"no-op","create","read","update","delete","forget"} for v in values)):
            raise ValueError("saved_plan_invalid")
        actions[address]=values
    return actions


def read_plan_evidence(root,path,findings):
    import hashlib
    raw=_contained_bytes(root,path);actions=_plan_actions(raw);links=[]
    for finding in findings:
        address=finding.get("extensions",{}).get("resource_address")
        linked=isinstance(address,str) and address in actions
        links.append({"path":finding["path"],"rule":finding["rule"],
            "resource_address":address if isinstance(address,str) else None,
            "actions":actions[address] if linked else None,"linked":linked,
            "unlinked_reason":None if linked else
                ("address_not_in_plan" if isinstance(address,str) else "engine_address_unavailable")})
    return {"sha256":hashlib.sha256(raw).hexdigest(),"resource_count":len(actions),"finding_links":links}


def trial_plan_impact(root,patch_path,state_fixture,*,provider_fixture,allowed_destroy_ids,
                      runtime_path,image_ref,permissions):
    import hashlib,json,re,shutil,tempfile
    from pathlib import Path
    from rush.permissions import ExecutionPermissions,check_permissions
    from rush.runtime.isolated_process import run_isolated_argv
    allowed,missing=check_permissions(ExecutionPermissions(build=True,slow=True,artifact_write=True),permissions)
    if not allowed:
        raise PermissionError(", ".join(missing))
    root=Path(root);before=source_manifest(root)
    patch_bytes=_contained_bytes(root,patch_path);state_bytes=_contained_bytes(root,state_fixture)
    lock_bytes=_contained_bytes(root,".terraform.lock.hcl")
    state=json.loads(state_bytes)
    if not isinstance(state,dict) or type(state.get("version")) is not int or state["version"]!=4:
        raise ValueError("invalid_state_fixture")
    if not isinstance(allowed_destroy_ids,(list,tuple)) or any(not isinstance(x,str) or not x for x in allowed_destroy_ids):
        raise ValueError("invalid_destroy_allowlist")
    for file in root.glob("*.tf"):
        for backend in re.findall(r'\bbackend\s+"([^"]+)"',_contained_bytes(root,file).decode()):
            if backend!="local":
                raise ValueError("remote_backend_refused")
    if any(Path(name).suffix==".tf" and Path(name).parent!=Path(".") for name in before):
        raise ValueError("trial_requires_single_module")
    provider=None
    if provider_fixture is not None:
        from rush.io.physical_paths import PhysicalRoot
        provider=PhysicalRoot(root).open_contained(provider_fixture)
        if not provider.is_dir():
            raise ValueError("invalid_provider_fixture")
        source_manifest(provider)
    plans={}
    with tempfile.TemporaryDirectory(prefix="rush-iac-") as folder:
        scratch=Path(folder)
        for kind in ("baseline","candidate"):
            destination=scratch/kind;destination.mkdir()
            _copy_snapshot(root,destination,{name:digest for name,digest in before.items()
                if ".terraform" not in Path(name).parts})
            (destination/"terraform.tfstate").write_bytes(state_bytes)
            if provider is not None:
                (destination/".terraform").mkdir()
                _copy_snapshot(provider,destination/".terraform",source_manifest(provider))
        (scratch/"candidate.patch").write_bytes(patch_bytes)
        common={"runtime_path":Path(runtime_path),"image_ref":image_ref,"timeout_s":180}
        for extra in (["--check"],[]):
            applied=run_isolated_argv(root,scratch,entrypoint="/usr/bin/git",
                argv=["-C","/out/candidate","apply",*extra,"/out/candidate.patch"],**common)
            if applied.returncode:
                raise ValueError("candidate_patch_failed")
        baseline=source_manifest(scratch/"baseline");candidate=source_manifest(scratch/"candidate")
        protected={name for name in baseline if Path(name).suffix!=".tf"}
        if any(candidate.get(name)!=baseline[name] for name in protected):
            raise ValueError("protected_trial_input_changed")
        if any(Path(name).suffix!=".tf" for name in candidate.keys()-baseline.keys()):
            raise ValueError("candidate_non_source_addition")
        for kind in ("baseline","candidate"):
            plan=run_isolated_argv(root,scratch,entrypoint="/usr/local/bin/terraform",
                argv=[f"-chdir=/out/{kind}","plan","-input=false","-refresh=false","-lock=false",
                      f"-out=/out/{kind}.plan"],**common)
            if plan.returncode:
                raise ValueError("candidate_plan_failed")
            show=run_isolated_argv(root,scratch,entrypoint="/usr/local/bin/terraform",
                argv=[f"-chdir=/out/{kind}","show","-json",f"/out/{kind}.plan"],
                **{**common,"timeout_s":30})
            if show.returncode:
                raise ValueError("candidate_show_failed")
            plan_bytes=_contained_bytes(scratch,f"{kind}.plan",64*1024*1024)
            plans[kind]={"sha256":hashlib.sha256(plan_bytes).hexdigest(),
                         "actions":_plan_actions(show.stdout.encode())}
    if source_manifest(root)!=before:
        raise ValueError("source_changed")
    destructive=lambda actions:{name for name,value in actions.items() if "delete" in value}
    introduced=sorted(destructive(plans["candidate"]["actions"])-destructive(plans["baseline"]["actions"]))
    blocked=sorted(set(introduced)-set(allowed_destroy_ids))
    return {"operation":"plan_impact_trial","applied":False,"plans":plans,
        "state_digest":hashlib.sha256(state_bytes).hexdigest(),
        "provider_lock_digest":hashlib.sha256(lock_bytes).hexdigest(),
        "patch_digest":hashlib.sha256(patch_bytes).hexdigest(),"new_destructive_ids":introduced,
        "status":"blocked" if blocked else "candidate"}


run_impact_trial=trial_plan_impact
~~~

### Complete callable and method insertion
Module-level utilities below, followed by full IacTool replacement. Existing ContentTool import is retained for its subclasses. Config is verified existing ToolConfig: any nonempty options fails request_only_options; unknown config keys already fail catalog validation. Pins/effect selections stay explicit request fields. Runtime source and logical destination anchors use existing executor accessors, not process cwd.
~~~python
def _roots(path):
    from pathlib import Path
    from rush.invocation.executor import current_execution_root,current_invocation_root
    path=Path(path)
    if not path.exists():
        raise ValueError("target_not_found")
    target=path if path.is_dir() else path.parent
    execution=current_execution_root() or target
    logical=current_invocation_root() or execution
    return path,Path(logical),Path(logical)/target.relative_to(execution)


def _require_grants(permissions,**required):
    from rush.permissions import ExecutionPermissions,check_permissions
    allowed,missing=check_permissions(ExecutionPermissions(**required),permissions)
    if not allowed:
        raise PermissionError(", ".join(missing))


def _operation_error(name,error):
    from rush.tools.common import error_result,skipped_result
    from subprocess import TimeoutExpired
    from rush.runtime.subprocesses import SubprocessCancelled
    if isinstance(error,SubprocessCancelled):
        return skipped_result(name,None,"cancelled",metadata={"execution":{"disposition":"cancelled","cause":"cancelled"}})
    if isinstance(error,TimeoutExpired):
        return error_result(name,None,"execution timed out",terminal_reason="timeout")
    if isinstance(error,PermissionError):
        return skipped_result(name,None,str(error),metadata={
            "execution":{"disposition":"not_run","cause":"permission_denied"}})
    return error_result(name,None,"request or execution failed",
        terminal_reason=type(error).__name__,metadata={"reason":str(error) if isinstance(error,ValueError) else type(error).__name__})

from pathlib import Path
from rush.tools.base import ToolResult,ToolFn
from rush.tools.common import run_engine
from subprocess import TimeoutExpired
from rush.runtime.subprocesses import SubprocessCancelled
from rush.io.physical_paths import ContainmentError

class IacTool(ContentTool):
    name="iac"
    engine_name="tflint"
    engine_names=("tflint","checkov")
    extensions=("tf",)
    @property
    def mcp_description(self):
        return "Inspect iac using shared local engines; explicit effect grants remain required."

    def __call__(self, path: Path, *,
                 scope: str = "module",
                 plan_evidence: str | None = None,
                 trial_plan_impact: str | None = None,
                 state_fixture: str | None = None,
                 provider_fixture: str | None = None,
                 allowed_destroy_ids: list[str] | None = None,
                 runtime_path: str | None = None,
                 image_ref: str | None = None,
                 allow_network: bool = False,
                 allow_download: bool = False,
                 allow_cache_write: bool = False,
                 allow_build: bool = False,
                 allow_slow: bool = False,
                 allow_artifact_write: bool = False,
                 allow_browser: bool = False,
                 ) -> ToolResult:
        from rush.permissions import ExecutionPermissions
        grants = [allow_network,allow_download,allow_cache_write,allow_build,allow_slow,allow_artifact_write,allow_browser]
        if any(type(value) is not bool for value in grants):
            return _operation_error(self.name,ValueError("invalid_grant_type"))
        permissions=ExecutionPermissions(network=allow_network,download=allow_download,cache_write=allow_cache_write,build=allow_build,slow=allow_slow,artifact_write=allow_artifact_write,browser=allow_browser)
        return self.run(path,scope=scope,plan_evidence=plan_evidence,trial_plan_impact=trial_plan_impact,state_fixture=state_fixture,provider_fixture=provider_fixture,allowed_destroy_ids=allowed_destroy_ids,runtime_path=runtime_path,image_ref=image_ref,permissions=permissions)
    
    def run(self, path: Path, *,
            scope: str = "module",
            plan_evidence: str | None = None,
            trial_plan_impact: str | None = None,
            state_fixture: str | None = None,
            provider_fixture: str | None = None,
            allowed_destroy_ids: list[str] | None = None,
            runtime_path: str | None = None,
            image_ref: str | None = None,
            config=None, permissions=None) -> ToolResult:
        try:
            if config is not None and config.options:
                raise ValueError("request_only_options")
            path,logical,target=_roots(path)
            if scope not in {"file","module"}:
                raise ValueError("invalid_scope")
            if trial_plan_impact is not None:
                _require_grants(permissions,build=True,slow=True,artifact_write=True)
                if not state_fixture or not runtime_path or not image_ref:
                    raise ValueError("trial_inputs_required")
            from rush.engines import ENGINES
            from rush.tools.routing import collect_files,aggregate_results
            from rush.tools.common import skipped_result
            files=collect_files(path,{"tf"},strict=True)
            if not files:
                return skipped_result("iac",None,"no supported Terraform files")
            modules=sorted({file.parent for file in files})
            results=[run_engine(ENGINES[engine],module,[],tool_name="iac")
                     for module in modules for engine in ("tflint","checkov")]
            result=aggregate_results("iac",results)
            metadata=result.setdefault("metadata",{})
            metadata.update({"requested_files":[str(file) for file in files],
                "execution_modules":[str(module) for module in modules],
                "module_context_files":[str(file) for module in modules for file in sorted(module.glob("*.tf"))]})
            if plan_evidence is not None:
                metadata["plan_evidence"]=read_plan_evidence(target,plan_evidence,result["findings"])
            if scope=="file":
                requested={str(file) for file in files}
                hidden=[f for f in result["findings"] if f["path"] not in requested]
                metadata["context_diagnostics"]={"count":len(hidden),"paths":sorted({f["path"] for f in hidden})}
                result["findings"]=[f for f in result["findings"] if f["path"] in requested]
            if trial_plan_impact is not None:
                trial=run_impact_trial(target,trial_plan_impact,state_fixture,
                    provider_fixture=provider_fixture,allowed_destroy_ids=allowed_destroy_ids or [],
                    runtime_path=runtime_path,image_ref=image_ref,permissions=permissions)
                metadata["plan_impact_trial"]=trial
                if trial["status"]=="blocked" and result["status"]!="error":
                    result["status"]="fail"
            return result
        except (OSError,ValueError,TypeError,RuntimeError,TimeoutExpired,SubprocessCancelled,ContainmentError) as error:
            return _operation_error(self.name,error)
    
~~~

### Literal transport and configuration edits
In src/rush/catalog.py preserve this command's existing ToolSpec and set exact `option_specs=()`. ToolOptionSpec declarations are intentionally an empty tuple: all operation options are request-only, so adding config declarations would contradict the grant and runtime-input contract. This is explicit configuration exclusion, not an unspecified tuple. Existing canonical table remains `[tools.iac]`; `docs/CONFIGURATION.md` and `examples/rush.toml` retain an empty table with comment `# Operation arguments and grants are supplied per invocation.` No config can choose an executable/image or silently request a trial.

Insert this literal entry into existing src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS; preserve all other entries:
~~~python
_TOOL_CLI_OPTIONS["iac"]=(
    click.Option(["--scope"],type=click.Choice(["file","module"]),default="module"),
    click.Option(["--plan-evidence"],type=click.Path(dir_okay=False),default=None),
    click.Option(["--trial-plan-impact"],type=click.Path(dir_okay=False),default=None),
    click.Option(["--state-fixture"],type=click.Path(dir_okay=False),default=None),
    click.Option(["--provider-fixture"],type=click.Path(file_okay=False),default=None),
    click.Option(["--allow-destroy","allowed_destroy_ids"],multiple=True,default=()),
    click.Option(["--runtime-path"],type=click.Path(dir_okay=False),default=None),
    click.Option(["--image-ref"],type=str,default=None),
)
~~~

MCP _CWD_RELATIVE_ARGS: keep all listed iac secondary operands out of cwd anchoring; class resolves them against selected logical target except approved absolute runtime binary. Absolute contained output_path remains accepted. `project` remains wrapper injection. CLI path flags intentionally retain raw strings for identical root-relative semantics; no abspath callback. MCP exact property/default inventory:
~~~json
{
  "scope": {
    "type": "str",
    "default": "\"module\""
  },
  "plan_evidence": {
    "type": "str | None",
    "default": "None"
  },
  "trial_plan_impact": {
    "type": "str | None",
    "default": "None"
  },
  "state_fixture": {
    "type": "str | None",
    "default": "None"
  },
  "provider_fixture": {
    "type": "str | None",
    "default": "None"
  },
  "allowed_destroy_ids": {
    "type": "list[str] | None",
    "default": "None"
  },
  "runtime_path": {
    "type": "str | None",
    "default": "None"
  },
  "image_ref": {
    "type": "str | None",
    "default": "None"
  }
}
~~~
Shared owner edits exact command rows in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/reference/cli-reference.md, docs/reference/mcp-tool-reference.md, docs/reference/result-reference.md, docs/reference/configuration-reference.md, docs/CONFIGURATION.md and examples/rush.toml. CLI/MCP rows list every option above and defaults; result row includes nested operation evidence described here plus per-engine source/executable/version/scope and exact skipped/error behavior. These are user-facing rows only after executable route passes. Update tests/fixtures/phase70/cli-outcomes.json touched command cases; tests/test_cli_registry.py and tests/test_mcp.py assert exact reflected parameter names/types/defaults. scripts/sync_docs.py is check-only, not a generator: `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check` and `python -m pytest tests/test_sync_docs.py -q`.

### Command-specific requested baseline applicability
Specialist may propose Terraform edits using exact engine resource-address evidence, but destructive trial uses actual offline Terraform plans, not model impact scoring. Voice may read newly destructive resource IDs and denied grants; state values remain excluded. Companion may visualize baseline/candidate resource actions and explicit blocked/candidate verdict, never represent candidate as applied infrastructure.

### Additional literal adapter and genuine runtime acceptance
Exact replacement src/rush/engines/checkov.py::_parse_checkov_report; existing json/parser/_root/_checkov_path imports retained:
~~~python
def _parse_checkov_report(report,path):
    reports=report if isinstance(report,list) else [report]
    if not reports or not all(isinstance(item,dict) for item in reports):
        raise StructuredIacReportError("Checkov JSON report must be an object or list")
    findings=[];parsing_errors=[]
    for item in reports:
        payload=item.get("results")
        if not isinstance(payload,dict):
            raise StructuredIacReportError("Checkov JSON report has no results object")
        checks=payload.get("failed_checks");errors=payload.get("parsing_errors")
        if not isinstance(checks,list) or not isinstance(errors,list) or not all(isinstance(e,str) for e in errors):
            raise StructuredIacReportError("Checkov result fields invalid")
        parsing_errors.extend(errors)
        for check in checks:
            if not isinstance(check,dict):
                raise StructuredIacReportError("Checkov failed check must be an object")
            row={"file_path":_checkov_path(check),"file_line_range":check.get("file_line_range"),
                "check_id":check.get("check_id"),"severity":check.get("severity"),
                "check_name":check.get("check_name")}
            parsed=parse_structured_iac_report(json.dumps({"results":[row]}),_root(path))
            address=check.get("resource")
            if address is not None:
                if not isinstance(address,str) or not address:
                    raise StructuredIacReportError("Checkov resource address invalid")
                for finding in parsed:finding["extensions"]={"resource_address":address}
            findings.extend(parsed)
    return findings,parsing_errors
~~~

These proposed tests require preinstalled real engines and explicit runtime pins; failure to supply them is a failed acceptance prerequisite, not a successful skip. No installation/download is performed by tests.
~~~python
def test_real_tflint_checkov_module_scope(tmp_path):
    from rush.runtime.binaries import resolve_binary
    from rush.tools.iac import IacTool
    for name in ("tflint","checkov"):
        assert resolve_binary(name,project_root=tmp_path),"preinstalled "+name+" required"
    (tmp_path/"main.tf").write_text('terraform { required_version = ">= 1.5.0" }\n')
    (tmp_path/"variables.tf").write_text('variable "unused" { type = string }\n')
    result=IacTool().run(tmp_path/"main.tf",scope="file")
    assert result["metadata"]["execution_modules"]==[str(tmp_path)]
    assert result["metadata"]["module_context_files"]==[str(tmp_path/"main.tf"),str(tmp_path/"variables.tf")]
    assert {row["engine"] for row in result["metadata"]["engines"]}=={"tflint","checkov"}
    assert all(row["version"] for row in result["metadata"]["engines"])
    full=IacTool().run(tmp_path,scope="module")
    assert [(f["rule"],f["line"]) for f in full["findings"] if f["rule"]=="terraform_unused_declarations"]==[
        ("terraform_unused_declarations",1)]
    assert result["metadata"]["context_diagnostics"]["count"]==1
    assert result["findings"]==[]
    assert result["status"]==full["status"]=="warn"
~~~

### Complete optional-operation public-route acceptance
Add these bodies to existing tests/test_mcp.py, using exchange_stdio below. Only registry storage root is injected into server startup for a disposable registry; no tool, parser, permission, engine, or transport code is replaced. Genuine runtime inputs are explicit environment prerequisites. Production server gains no test flag.
~~~python
def _registered_transport_fixture(tmp_path):
    import os,sys
    from rush.workflows.projects import register_project
    root=tmp_path/"project";root.mkdir()
    (root/"rush.toml").write_text("")
    foreign=tmp_path/"foreign";foreign.mkdir()
    registry=tmp_path/"registry"
    record=register_project(root,data_root=registry)
    env=dict(os.environ);env.pop("PYTHONPATH",None)
    return root,foreign,registry,record.project_id,env,sys.executable


def _assert_engine_identities(result,names):
    import hashlib
    from pathlib import Path
    entries=result["metadata"]["engines"]
    assert {entry["engine"] for entry in entries}==set(names)
    for entry in entries:
        assert entry["version"]
        executable=Path(entry["executable"]["path"])
        assert executable.is_file()
        assert entry["executable"]["sha256"]==hashlib.sha256(executable.read_bytes()).hexdigest()
        assert entry["scope"]["coverage"] in {"complete","partial","unavailable"}
        if entry["scope"]["coverage"]=="unavailable":
            assert entry["scope"]["consumed_file_count"] is None

def test_iac_granted_optional_foreign_stdio(tmp_path):
    import json,os,subprocess
    root,foreign,registry,project,env,python=_registered_transport_fixture(tmp_path)
    (root/"main.tf").write_text('resource "terraform_data" "subject" {\n  triggers_replace = "old"\n}\n')
    (root/".terraform.lock.hcl").write_text("# built-in provider only\n")
    resource_state={"version":4,"terraform_version":"1.5.0","serial":1,
        "lineage":"00000000-0000-4000-8000-000000000001","outputs":{},
        "resources":[{"mode":"managed","type":"terraform_data","name":"subject",
          "provider":'provider["terraform.io/builtin/terraform"]',
          "instances":[{"schema_version":0,"attributes":{
            "id":"fixture-subject","input":None,"output":None,
            "triggers_replace":{"value":"old","type":"string"}},"sensitive_attributes":[]}]}]}
    (root/"state.json").write_text(json.dumps(resource_state))
    (root/"plan.json").write_text('{"resource_changes":[{"address":"terraform_data.subject","change":{"actions":["no-op"]}}]}')
    (root/"change.patch").write_text('diff --git a/main.tf b/main.tf\n--- a/main.tf\n+++ b/main.tf\n'
        '@@ -1,3 +1,3 @@\n resource "terraform_data" "subject" {\n'
        '-  triggers_replace = "old"\n+  triggers_replace = "new"\n }\n')
    runtime=os.environ["RUSH_TEST_OCI_RUNTIME"];image=os.environ["RUSH_TEST_TERRAFORM_IMAGE"]
    args=["--scope","file","--plan-evidence","plan.json","--trial-plan-impact","change.patch",
        "--state-fixture","state.json","--runtime-path",runtime,"--image-ref",image,
        "--allow-build","--allow-slow","--allow-artifact-write"]
    cli=subprocess.run([python,"-m","rush","iac",str(root/"main.tf"),*args,"--json"],
        cwd=foreign,env=env,capture_output=True,text=True,timeout=1800)
    left=json.loads(cli.stdout)
    right=exchange_stdio(python,foreign,env,"rush_iac",{"path":"main.tf","project":project,
        "scope":"file","plan_evidence":"plan.json","trial_plan_impact":"change.patch",
        "state_fixture":"state.json","runtime_path":runtime,"image_ref":image,
        "allow_build":True,"allow_slow":True,"allow_artifact_write":True},registry_root=registry)
    for result in (left,right):
        _assert_engine_identities(result,["tflint","checkov"])
        assert result["status"]=="fail"
        assert result["metadata"]["plan_evidence"]["resource_count"]==1
        assert result["metadata"]["plan_impact_trial"]["new_destructive_ids"]==["terraform_data.subject"]
        assert result["metadata"]["plan_impact_trial"]["applied"] is False
    projection=lambda r:(r["status"],r["findings"],r["metadata"]["plan_evidence"],
        {k:r["metadata"]["plan_impact_trial"][k] for k in ("status","state_digest","provider_lock_digest","patch_digest","new_destructive_ids")})
    assert projection(left)==projection(right)
    assert not (foreign/".rush").exists()
~~~

Complete missing-engine shared-dispatch regression (current resolver injection is verified tools.common.engine_on_path); result is not fabricated:
~~~python
def test_iac_missing_engine_no_process(tmp_path):
    from unittest.mock import patch
    from rush.tools.iac import IacTool
    from rush.permissions import ExecutionPermissions
    (tmp_path/"main.tf").write_text('variable "x" {}\n')
    with patch("rush.tools.common.engine_on_path",return_value=False), patch("rush.runtime.subprocesses.run_subprocess") as process:
        result=IacTool().run(tmp_path)
    assert result["status"]=="skipped"
    assert result["findings"]==[]
    assert all(row["status"]=="skipped" for row in result["metadata"]["engines"])
    process.assert_not_called()
~~~

~~~python
def test_iac_malformed_engine_report_is_error(tmp_path):
    from rush.engines import ENGINES
    (tmp_path/"main.tf").write_text('variable "x" {}\n')
    for name in ["tflint","checkov"]:
        result=ENGINES[name].normalize({"exit_code":0,"stdout":"[not-json","stderr":""},tmp_path,"iac")
        assert result["status"]=="error"
        assert result["findings"]==[]
~~~

Literal root-anchor integration, Batch integration owner, src/rush/mcp_support/tool_registry.py::_CWD_RELATIVE_ARGS (retain every other entry):

~~~python
_CWD_RELATIVE_ARGS["iac"] = ()
~~~

## Frozen inputs and authority

Source: /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70, branch phase/70-agent-adoption-and-usability, HEAD 66c6c799eaa5b6017776d659e9e0de2b4a8878a5. Source clean; no relevant dirty hashes. Delivery: /Users/jamesdsizemore/Developer/rush-cli, branch codex/codex-cli-mcp-commands-review, HEAD c78e445ba1e575ca373e35840142cd627b055d6a. Delivery user AGENTS.md SHA-256 70252e9068f419b79d88e87b228ce796ae5e61fc0572f06f5354acf209f40617 and unrelated untracked docs/scratch remain untouched. Future implementation worktree must start from exact source HEAD; none created here.

Binding SHA-256 identities:
- Delivery docs/reports/cli-mcp-command-audit-2026-09-26.md: 8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.
- Source docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md: 9453032d9411a27b2b7ee2ede074d98d93969fbe85433adacdec1c7bcc89c5c7.
- docs/templates/task-block-template.md: 10fdb5380f04097258e29327cf74fe474532cdc42747a38310d0befa2107ecc3.
- Source .scratch/phase-70-design-gate/T8.md: b15a2c5e9c0fd0cab275c1bd17de78e1975f341048e6df9c403982619f12bfe2; W1-T1-T7-T23.md: 5fa3c629ef17c3f7812af1f274df1b23c3c43a00181778950902ae98f81939b3.
- Source .scratch/phase-70-design-gate/W2-T9-T17.md: a402ea6ffd4de9c5ca74860d9672cdb834242573ee45b2feb4ca2c2c5da9a0f9; W4-T23-T29.md: 47de33a0888a63ee6999a1610577f0e3d0868701642a3a27eb36111d1c1d7204.

Controlling task: delivery docs/agents/cli-command-remediation-plan-batch-prompt.md §§1–6. Historical session review supplies lessons only; Batch 1 unchanged. Planning authorized; production edits, installs, network access, commits and PR publication are not. Audit proposals remain proposals. First repair packet needs no additional approval; ordinary extensions and distinct expansions have separately stated authorization.

Author/model: gpt-6-astra/high. Command owner owns command-specific tools/engines/tests. Batch integration owner alone owns shared paths; serialize Q11 → Q12 → Q13 → Q14 → Q15 → Q16 → Q17 → Q18 → Q19 → Q20. P0 isolation runs before any authorized isolated trial, regardless of command ID.

## Binding Phase 70 reconciliation

T8: existing current_invocation_root/current_execution_root (src/rush/invocation/executor.py:41–50) distinguish logical project from staged execution root. Existing make_tool_wrapper is defined in src/rush/mcp_support/tool_registry.py:318–388; mcp.py re-exports it. Preserve original requests, fixed server-start anchor, registered project precedence and no-follow containment. Execution-relative paths map to logical paths for reporting only.

T9: missing/invalid targets return error before scanner calls; existing empty scope is skipped; missing engine is skipped; clean requires actual execution. T10: permission before constructor/mkdir side effects; project state under logical root. T16: aggregate_results already preserves engine entries and mixed-status precedence. Preserve metadata.execution, metadata.engines and metadata.scope.version=1; do not copy audit's unversioned replacement scope. Directory scan consumption count stays null with reason engine_discovers_directory_contents unless engine supplies actual inventory. Strict V1 uses extensions.metadata; service envelopes unchanged. Status precedence error > fail > warn > skipped > ok; ok+skipped becomes warn. CLI exits ok/skipped=0, warn/fail=1, error=2.

T6: typed flat schemas, strict booleans, no grant inference; wrappers already inject project and full/compact controls. T14's dependency inventory, T15's doctor/provisioning and T27's truthful human rendering remain authoritative. Compact must preserve full status, enforce existing 1–50 findings/4096–65536-byte limits, reject no-cache conflict and denied persistence before execution. Cursor removed by owner decision; real host lanes are Claude Code and Codex CLI.

Baseline features remain user requirements, not inventions: scanner provisioning uses existing ENGINE_PACKAGES/doctor/setup with explicit source grants; command execution never installs. Connected specialist local models may consume redacted results through existing agent routes; they cannot supply missing engine evidence. Voice/live speech and 3D companion consume these same factual statuses/artifact references through existing UI boundaries. Their broader implementation is not relocated into deterministic scanner commands or deleted by this plan. No automatic memory writes; result identities may be passed to separately authorized memory operations.

## P0A — Raw MCP catalog validation before SDK coercion

**Required behavior.** Shared prerequisite, Batch integration owner, implemented once with Q11 before new options. Applies only registered rush_actions, rush_yaml, rush_sql, rush_templates, rush_containerfile, rush_iac, rush_secrets, rush_sbom, rush_coverage, rush_codeql. Preserve unregistered/unknown SDK errors, existing request-model tools, and restricted memory server. Parent's current Python3.12 SDK probe proved unknown fields discarded and string "true" coerced to True before make_tool_wrapper. Wrapper-only validation is insufficient. This fixes current contract; additional options are still future interfaces.

**Deliverables.** `src/rush/mcp_support/tool_registry.py` adds two finite helpers/constants below; `src/rush/mcp.py::RushFastMCP.call_tool/list_tools` consumes them before super call; `tests/test_mcp.py::test_catalog_raw_invalid_before_sdk`, `::test_catalog_raw_type_matrix`. No dependency or validation framework.

~~~python
# src/rush/mcp_support/tool_registry.py
import math

RAW_CATALOG_TOOLS = frozenset({
    "rush_actions", "rush_yaml", "rush_sql", "rush_templates",
    "rush_containerfile", "rush_iac", "rush_secrets", "rush_sbom",
    "rush_coverage", "rush_codeql",
})

def catalog_raw_invalid_fields(arguments, schema):
    if not isinstance(arguments, dict) or any(type(k) is not str for k in arguments):
        return ["$"]
    properties = schema.get("properties", {})
    definitions = schema.get("$defs", {})

    def matches(value, shape, depth=0):
        if depth > 16:
            return False
        reference = shape.get("$ref")
        if reference is not None:
            prefix = "#/$defs/"
            return (isinstance(reference, str) and reference.startswith(prefix)
                    and reference[len(prefix):] in definitions
                    and matches(value, definitions[reference[len(prefix):]], depth + 1))
        alternatives = shape.get("anyOf")
        if alternatives is not None:
            return any(matches(value, branch, depth + 1) for branch in alternatives)
        kind = shape.get("type")
        if kind == "null":
            return value is None
        if kind == "boolean":
            return type(value) is bool
        if kind == "integer":
            return type(value) is int
        if kind == "number":
            return type(value) is int or (type(value) is float and math.isfinite(value))
        if kind == "string":
            return type(value) is str
        if kind == "array":
            return type(value) is list and all(
                matches(item, shape.get("items", {}), depth + 1) for item in value)
        if kind == "object":
            return type(value) is dict and all(type(key) is str for key in value)
        if "enum" in shape:
            return any(type(value) is type(item) for item in shape["enum"])
        if not shape:
            return (value is None or type(value) in (str, bool, int)
                    or (type(value) is float and math.isfinite(value))
                    or (type(value) is list and all(matches(v, {}, depth + 1) for v in value))
                    or (type(value) is dict and all(
                        type(k) is str and matches(v, {}, depth + 1)
                        for k, v in value.items())))
        return False

    invalid = set(arguments) - set(properties)
    invalid.update(set(schema.get("required", [])) - set(arguments))
    invalid.update(key for key, value in arguments.items()
                   if key in properties and not matches(value, properties[key]))
    return sorted(invalid)
~~~

This guard validates raw JSON types, nullable branches, required/unknown fields and array element types. Semantic choice values, bounds, path containment and grants stay existing command/shared validators. It rejects JSON-stringified arrays for these ten catalog tools; legacy JSON-string container compatibility on request-model project/scan/memory is unchanged. No expansion to other tools.

Exact insertion at the start of existing `RushFastMCP.call_tool`, before its current REQUEST_MODEL_TOOLS condition:

~~~text
from .mcp_support.tool_registry import RAW_CATALOG_TOOLS, catalog_raw_invalid_fields
from .tools.common import error_result

registered = self._tool_manager.get_tool(name)
if name in RAW_CATALOG_TOOLS and registered is not None:
    invalid = catalog_raw_invalid_fields(arguments, registered.parameters)
    if invalid:
        envelope = error_result(
            name.removeprefix("rush_"), None, "Invalid request",
            terminal_reason="INVALID_REQUEST",
            metadata={"reason": "invalid_request", "invalid_fields": invalid})
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope, indent=2))],
            structuredContent=envelope, isError=False)
~~~

The insertion is a method-body fragment: indentation belongs inside async method. Imports json/CallToolResult/TextContent already exist in defining module. Existing method body follows untouched. In `list_tools` existing loop, add independent `if tool.name in RAW_CATALOG_TOOLS: tool.inputSchema={**tool.inputSchema,"additionalProperties":False}`, importing same constant. Do not change registered.parameters or low-level SDK manager internals.

Complete current regression body, appended to existing tests/test_mcp.py:

~~~python
def test_catalog_raw_invalid_before_sdk(tmp_path):
    import asyncio, json
    from rush.mcp import build_server
    from mcp.types import CallToolResult
    server = build_server(profile="full")
    raw = asyncio.run(server.call_tool("rush_actions", {
        "path": str(tmp_path / "missing"),
        "unexpected": 1, "allow_cache_write": "true"}))
    if isinstance(raw, CallToolResult):
        value = raw.structuredContent
        if value is None:
            value = json.loads(next(c.text for c in raw.content if c.type == "text"))
    elif isinstance(raw, tuple):
        value = raw[1]
    else:
        value = json.loads(next(c.text for c in raw if c.type == "text"))
    assert value["status"] == "error"
    assert value.get("metadata", {}).get("invalid_fields") == [
        "allow_cache_write", "unexpected"]
    assert value["metadata"]["reason"] == "invalid_request"
    assert list(tmp_path.iterdir()) == []


def test_catalog_raw_type_matrix():
    from rush.mcp_support.tool_registry import catalog_raw_invalid_fields
    schema = {"type": "object", "required": ["path"], "properties": {
        "path": {"type": "string"},
        "allow_build": {"type": "boolean", "default": False},
        "limit": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None},
        "names": {"type": "array", "items": {"type": "string"}, "default": []}}}
    assert catalog_raw_invalid_fields(
        {"path": ".", "allow_build": False, "limit": None, "names": ["a"]}, schema) == []
    assert catalog_raw_invalid_fields(
        {"path": ".", "allow_build": "false", "limit": True, "names": ["a", 2]}, schema
    ) == ["allow_build", "limit", "names"]
    assert catalog_raw_invalid_fields({"path": ".", "limit": 1.0}, schema) == ["limit"]
    assert catalog_raw_invalid_fields({"path": ".", "names": '["a"]'}, schema) == ["names"]
    assert catalog_raw_invalid_fields({"path": None}, schema) == ["path"]
    assert catalog_raw_invalid_fields({}, schema) == ["path"]
    assert catalog_raw_invalid_fields([], schema) == ["$"]
~~~

First test runs current real server path with missing target, so no engine needed; current RED reaches invalid_fields assertion, not new helper import. Second checks future helper only after implementation. To prove early rejection itself, after implementation wrap `_standard_context` with a raising spy while calling each invalid case; zero calls plus unchanged root/tree. Full stdio consumer test below exercises raw wire arguments, not only SDK metadata.

**Constraints.** Guard has no root/config/permissions/runtime/engine reads; registration lookup/schema inspection only. Unknown/unregistered tools remain SDK errors. Do not reject valid nulls or coerce strings to bool/int/list.

**Checks.** `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_mcp.py::test_catalog_raw_invalid_before_sdk tests/test_mcp.py::test_catalog_raw_type_matrix -q`; each command transport invalid-input case and existing request-model/restricted-server regression.

**Completion.** Actual raw MCP invalid fields produce canonical error with sorted names before effects; every advertised new/default field follows current published type; ordinary valid calls and unaffected profiles remain compatible.



## Shared ownership and exact integration writes

Shared P0A writes also belong exclusively to Batch integration owner: src/rush/mcp.py::RushFastMCP.call_tool and ::RushFastMCP.list_tools; src/rush/mcp_support/tool_registry.py::RAW_CATALOG_TOOLS and ::catalog_raw_invalid_fields. Execute once during Q11 integration, preserve full inline design in each consuming plan.

Exact displayed first-RED receipt: extracted the first complete test body from this document and executed against SOURCE 66c6c799eaa5b6017776d659e9e0de2b4a8878a5 with Python 3.12.12, offline uv, cleared PYTHONPATH, and TemporaryDirectory fixture. `test_single_file_discloses_module_scan`: AssertionError at displayed code line 15, expected module dispatch calls; current adapter received selected file path plus args. This first RED failed the calls assertion, before later scope assertions. No interface/import/fixture error preceded the assertion. Future-interface tests below remain unexecuted proposals.

Batch integration owner exclusively owns src/rush/catalog.py::TOOL_SPECS, src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS, src/rush/cli.py::sbom_cmd, tests/test_cli_registry.py, tests/test_mcp.py, tests/test_phase60_characterization.py, tests/test_sync_docs.py, tests/fixtures/phase70/cli-outcomes.json and command rows in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/reference/cli-reference.md, docs/reference/mcp-tool-reference.md, docs/reference/result-reference.md, docs/reference/configuration-reference.md, docs/reports/phase-64-66-documentation-coverage.md. Change only relevant command rows. Existing scripts/sync_docs.py derives contract receipts; no new generator.

Catalog options use explicit click.Option entries, never a speculative introspection factory. Existing build_catalog_path_command forwards tool_options. MCP schemas derive from explicitly typed __call__ signatures. All new boolean effects default false and grants are request-only. No added canonical tool or configuration table. Existing canonical [tools.<command>] remains; unknown options fail explicitly. Proposed new operation fields are request-only unless explicitly listed below, so configuration cannot silently enable them.

Common regression commands, future implementation checkout:
~~~sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase70_result_trust.py tests/test_phase54_result_schema.py tests/test_phase54_operation_adapters.py tests/test_cli_registry.py tests/test_mcp.py tests/test_staged_scan_bytes.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
~~~
Python must report 3.12; author observed 3.12.12 with offline uv. Clear inherited PYTHONPATH. Dependencies must already exist; set UV_OFFLINE=1 in acceptance environment to prevent implicit installation/network. Future tests below remain proposed, except explicitly recorded current-boundary reproductions.

## P0 — shared offline isolation prerequisite

Implement owned OCI subprocess execution in rush-cli in future implementation worktree. Read source AGENTS.md, Phase 70 T8/T10/T16 and this contract first.

# Feature: own and confine offline child execution

## Required behavior

New src/rush/runtime/isolated_process.py defines IsolationUnavailable(RuntimeError), IsolationCleanupError(RuntimeError) and this interface (algorithm follows; signature is not an executable patch):
~~~text
def run_isolated_argv(root: Path, scratch: Path, *, runtime_path: Path,
                      image_ref: str, entrypoint: str, argv: list[str],
                      timeout_s: float, workdir_rel: str = ".",
                      environment: dict[str, str] | None = None,
                      resource_profile: Literal["standard", "analysis"] = "standard"
                      ) -> subprocess.CompletedProcess[str]:
~~~
This is a fully specified proposed interface; absence initially proves missing interface only. Complete implementation algorithm:

1. Caller invokes existing check_permissions(required, granted) BEFORE scratch creation, runtime lookup or version probes. Caller creates fresh tempfile.TemporaryDirectory, chmod 0700, owns final deletion. Provider grants nothing. POSIX only; Windows unavailable. Runtime is explicitly approved absolute executable file; image matches name@sha256:64-lowercase-hex. Validate finite 0<timeout_s<=600; argv NUL-free string list; fixed absolute entrypoint selected by command, never model text. Reject source/scratch symlink/reparse components before resolve; source and scratch must not overlap in either direction; scratch owner is current UID, no group/other mode bits. Reject NUL/comma/CR/LF in mount paths. PhysicalRoot(root).open_contained(workdir_rel) must be directory. Only SOURCE_DATE_EPOCH/TZ/LC_ALL string environment overrides, no control characters.
2. Existing run_subprocess([runtime,"image","inspect",image_ref],timeout=10,env={"PATH":"/usr/bin:/bin"}) must yield exactly one matching locally present RepoDigest and approved native OS/architecture. Missing runtime/image/daemon => IsolationUnavailable before execution, no pulls/installs. Runtime capability tested with actual denial fixture below.
3. Generate uuid4 hex identity and name rush-<identity>. Exact argv: [runtime,"create","--name",name,"--label","io.rush.invocation="+identity,"--pull=never","--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges","--pids-limit=64","--memory=512m","--cpus=1","--user",f"{os.getuid()}:{os.getgid()}","--mount",f"type=bind,src={root},dst=/work,readonly","--mount",f"type=bind,src={scratch},dst=/out","--tmpfs","/tmp:rw,nosuid,nodev,size=64m","--workdir",contained_workdir,"--env","PATH=/usr/local/bin:/usr/bin:/bin","--env","HOME=/out","--env","PYTHONDONTWRITEBYTECODE=1","--env","RUSH_CHECK_RECEIPT=/out/checks.json",*sorted_allowed_env_pairs,"--entrypoint",entrypoint,image_ref,*argv]. No HOME/socket/credential mounts. Create stdout must be 64-hex container ID.
4. Start [runtime,"start","--attach",name] with remaining timeout, then inspect container. Matching ID/label, State.Running false, StartedAt nonzero and integer State.ExitCode required. Return CompletedProcess(create_argv,actual_exit,attached.stdout,attached.stderr). The create/start/inspect split distinguishes real target exit125/126/127 from launcher failures, correcting audit run/125 ambiguity.
5. Finally inspect label/ID, rm --force only owned name, inspect known absence on success/error/timeout/cancellation, including create timeout that may already have created container. Cleanup calls use cancel_check=lambda:False so ambient cancellation cannot prevent reaping; timeout10. Existing run_subprocess inherits ambient owner_instance_id/run_id and cancellation, preserving current durable client ownership. Label mismatch, unreachable daemon or remaining container => IsolationCleanupError, never success. Re-raise original timeout/SubprocessCancelled only after confirmed cleanup. Record owned container name in sanitized error metadata for explicit recovery. No host-power-loss cleanup guarantee.

Mapping: unavailable => skipped plus metadata.reason=isolation_unavailable; cleanup failure => error plus terminal_reason=isolation_cleanup_failed. Provider preserves actual target exit; consumer applies exact domain exit/report consistency (valid finding exit1 is not universally error); unexpected exits error. Timeout/cancel retain exact existing reasons. Combined scanner+unavailable trial retains scanner evidence but incomplete/warn unless fail/error already wins. PatchSandboxManager is Git staging, not isolation; NetworkEgressGuard is interpreter-local monkeypatch, not confinement.

## Deliverables

Batch integration owner owns new src/rush/runtime/isolated_process.py and new tests/test_isolated_process.py. Existing PhysicalRoot, run_subprocess, check_permissions and owned scopes reused without modification. P0 ordered before Q11–Q16/Q18–Q20 isolated expansions; cross-reference does not replace this embedded contract.

Proposed tests in tests/test_isolated_process.py: test_missing_image_never_creates_container patches only provider run_subprocess with CompletedProcess(argv,1,"","No such image"); asserts sole call image inspect and IsolationUnavailable. test_closed_mounts_and_environment verifies exact create argv above. test_target_exit_125 supplies valid create/start/inspect lifecycle and asserts returned125. test_timeout_and_cancel_reap verifies cleanup despite ambient cancellation and unrelated container untouched.

Runnable genuine-runtime acceptance; only selected when explicit preinstalled approved runtime/image supplied. Missing environment is failure prerequisite, never successful isolation:
~~~python
def test_real_oci_denials(tmp_path):
    import json, os, subprocess, tempfile
    from pathlib import Path
    from rush.runtime.isolated_process import run_isolated_argv
    runtime = Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image = os.environ["RUSH_TEST_OCI_IMAGE"]
    root = tmp_path / "source"
    root.mkdir()
    (root / "keep").write_bytes(b"unchanged")
    home_secret = tmp_path / "host-only-secret"
    home_secret.write_bytes(b"host-canary")
    probe = (
        "import json,socket,pathlib; out={}\n"
        "try: pathlib.Path('/work/blocked').write_text('x'); out['source_write']=True\n"
        "except OSError: out['source_write']=False\n"
        "try: s=socket.create_connection(('1.1.1.1',80),timeout=1); s.close(); out['network']=True\n"
        "except OSError: out['network']=False\n"
        "try: pathlib.Path(" + repr(str(home_secret)) + ").read_bytes(); out['host_read']=True\n"
        "except OSError: out['host_read']=False\n"
        "pathlib.Path('/out/allowed').write_text('ok')\n"
        "print(json.dumps(out))\n"
    )
    with tempfile.TemporaryDirectory(prefix="rush-denial-") as folder:
        scratch = Path(folder)
        scratch.chmod(0o700)
        result = run_isolated_argv(root, scratch, runtime_path=runtime,
            image_ref=image, entrypoint="/usr/local/bin/python",
            argv=["-c", probe], timeout_s=15)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "source_write": False, "network": False, "host_read": False}
        assert (scratch / "allowed").read_text() == "ok"
        name = result.args[result.args.index("--name") + 1]
        check = subprocess.run([str(runtime), "container", "inspect", name],
            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=10)
        assert check.returncode != 0
    assert [p.name for p in root.iterdir()] == ["keep"]
    assert (root / "keep").read_bytes() == b"unchanged"
    assert home_secret.read_bytes() == b"host-canary"
~~~
Add actual infinite-sleep timeout and cancellation variants with same post-cleanup inspect. Image must contain fixed /usr/local/bin/python; approved command images additionally contain their named executables. Mocked launcher cannot satisfy this test.

## Constraints

No network/pull/install, unowned deletion, real credentials, source writes or simulated isolation receipts. Keep hard memory/CPU/PID/tmp limits and current UID/GID. Inspect local image/runtime capability; version banners alone prove no confinement.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_isolated_process.py -q

## Completion

Exact runtime denials, allowed /out write and cleanup pass with actual local runtime; only two P0 files changed. Missing approved image/runtime blocks runtime acceptance, not beginning scanner repairs.

### P0 fixed resource profiles

The function signature additionally accepts resource_profile: Literal["standard","analysis"]="standard"; import Literal from typing. Validate exact enum before any runtime call (other strings, None/bools invalid). Standard maps to --memory=512m --cpus=1 --pids-limit=64. Analysis maps to --memory=8g --cpus=2 --pids-limit=256. No arbitrary user limits. Replace the three literal standard flags in create argv with values from this fixed mapping; every other flag/environment/mount/cleanup invariant unchanged.

Q15/Q16/Q18 and Q11–Q14 use standard. Q20 CodeQL uses analysis with --ram=6144 --threads=2; Q19 local-model process uses analysis with GGUF≤4GiB/context4096/output2048. CodeQL primary evidence: https://docs.github.com/en/code-security/reference/code-scanning/codeql/hardware-resources-for-codeql — small repositories recommend8GB/2cores; 512MiB cannot satisfy promised real analysis. Host insufficient resources => unavailable before target, never reduce guarantees.

Proposed complete flag test in tests/test_isolated_process.py:
~~~python
def test_resource_profiles_reach_real_argv(tmp_path):
    import json, os, subprocess
    from pathlib import Path
    from unittest.mock import patch
    from rush.runtime import isolated_process as provider
    runtime=Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image=os.environ["RUSH_TEST_OCI_IMAGE"]
    root=tmp_path/"root"; root.mkdir()
    for profile,memory,cpu,pids in (("standard","512m","1","64"),
                                    ("analysis","8g","2","256")):
        scratch=tmp_path/profile; scratch.mkdir(mode=0o700)
        real=provider.run_subprocess
        calls=[]
        def observe(argv,**kwargs):
            calls.append(list(argv))
            return real(argv,**kwargs)
        with patch.object(provider,"run_subprocess",side_effect=observe):
            result=provider.run_isolated_argv(root,scratch,runtime_path=runtime,
                image_ref=image,entrypoint="/usr/local/bin/python",
                argv=["-c","print('ready')"],timeout_s=15,resource_profile=profile)
        assert result.returncode==0
        created=[a for a in calls if len(a)>1 and a[1]=="create"]
        assert len(created)==1
        assert "--memory="+memory in created[0]
        assert "--cpus="+cpu in created[0]
        assert "--pids-limit="+pids in created[0]
        assert "--network=none" in created[0] and "--read-only" in created[0]
    with patch.object(provider,"run_subprocess") as execute:
        try:
            provider.run_isolated_argv(root,tmp_path/"standard",runtime_path=runtime,
                image_ref=image,entrypoint="/usr/local/bin/python",argv=["-c","pass"],
                timeout_s=1,resource_profile="unlimited")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown resource profile accepted")
        execute.assert_not_called()
~~~

### P0 executable lifecycle acceptance bodies

Append these complete bodies to proposed tests/test_isolated_process.py. Interface absence is expected initial failure; no current isolation claim.

~~~python
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

def test_missing_image_never_creates_container(tmp_path):
    from rush.runtime.isolated_process import run_isolated_argv, IsolationUnavailable
    root=tmp_path/"root"; root.mkdir()
    scratch=tmp_path/"scratch"; scratch.mkdir(mode=0o700)
    runtime=tmp_path/"docker"; runtime.write_text("#!/bin/sh\nexit 0\n"); runtime.chmod(0o700)
    image="fixture@sha256:"+"0"*64
    calls=[]
    def missing(argv,**kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv,1,"","No such image")
    with patch("rush.runtime.isolated_process.run_subprocess",side_effect=missing):
        try:
            run_isolated_argv(root,scratch,runtime_path=runtime,image_ref=image,
                entrypoint="/usr/local/bin/python",argv=["-c","pass"],timeout_s=1)
        except IsolationUnavailable:
            pass
        else:
            raise AssertionError("missing image launched")
    assert calls==[[str(runtime),"image","inspect",image]]
    assert list(scratch.iterdir())==[]

def test_real_timeout_and_cancel_reap(tmp_path):
    from rush.runtime import isolated_process as provider
    from rush.runtime.subprocesses import cancel_scope, SubprocessCancelled
    runtime=Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image=os.environ["RUSH_TEST_OCI_IMAGE"]
    root=tmp_path/"root"; root.mkdir()
    (root/"keep").write_bytes(b"unchanged")
    for mode in ("timeout","cancel"):
        calls=[]
        real=provider.run_subprocess
        def observed(argv,**kwargs):
            calls.append(list(argv))
            return real(argv,**kwargs)
        with tempfile.TemporaryDirectory(prefix="rush-reap-") as folder:
            scratch=Path(folder); scratch.chmod(0o700)
            code="import pathlib,time; pathlib.Path('/out/started').write_text('yes'); time.sleep(60)"
            with patch.object(provider,"run_subprocess",side_effect=observed):
                try:
                    with cancel_scope((lambda:(scratch/"started").exists()) if mode=="cancel" else None):
                        provider.run_isolated_argv(root,scratch,runtime_path=runtime,
                            image_ref=image,entrypoint="/usr/local/bin/python",
                            argv=["-c",code],timeout_s=10)
                except subprocess.TimeoutExpired:
                    assert mode=="timeout"
                except SubprocessCancelled:
                    assert mode=="cancel"
                else:
                    raise AssertionError("sleeping child completed")
            assert (scratch/"started").read_text()=="yes"
            created=[a for a in calls if len(a)>1 and a[1]=="create"]
            assert len(created)==1
            name=created[0][created[0].index("--name")+1]
            assert [str(runtime),"rm","--force",name] in calls
            remaining=subprocess.run([str(runtime),"container","inspect",name],
                env={"PATH":"/usr/bin:/bin"},capture_output=True,text=True,timeout=10)
            assert remaining.returncode!=0
    assert (root/"keep").read_bytes()==b"unchanged"
    assert [p.name for p in root.iterdir()]==["keep"]
~~~

### Complete command-specific CLI and stdio test

Save following body in existing tests/test_mcp.py beside exchange_stdio defined above. All engine doubles are actual local executables, outside project; no tool/resolver/transport stubs. Fixture asserts actual engine call receipt for each transport. It is POSIX executable-fixture acceptance; Windows requires equivalent .cmd launcher fixture and remains independently tested by existing transport suite.

~~~python
def test_q16_iac_cli_and_initialized_stdio(tmp_path):
    import json, os, subprocess, sys
    from pathlib import Path
    root=tmp_path/"project"; root.mkdir()
    (root/"rush.toml").write_text("[tools.iac]\n")
    (root/"main.tf").write_text('variable "x" {}\n')
    (root/"variables.tf").write_text('variable "y" {}\n')
    (root/"patch.diff").write_text("fixture")
    (root/"state.json").write_text('{"version":4,"resources":[]}\n')
    bindir=tmp_path/"bin"; bindir.mkdir()
    log=tmp_path/"engine-calls.jsonl"
    scripts={"tflint": 'print(\'{"issues":[],"errors":[]}\')', "checkov": 'print(\'{"results":{"failed_checks":[],"parsing_errors":[]}}\')'}
    for name, logic in scripts.items():
        executable=bindir/name
        executable.write_text("#!"+sys.executable+"\n"
            "import sys,json\nfrom pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "with Path("+repr(str(log))+").open('a') as f: f.write(json.dumps([Path(sys.argv[0]).name,args])+'\\n')\n"
            "if '--version' in args:\n print('fixture-1'); raise SystemExit(0)\n"
            "if '--help' in args:\n print('git dir --report-format --report-path --redact --no-install-deps --fail-on-error'); raise SystemExit(0)\n"
            +logic+"\n")
        executable.chmod(0o700)
    home=tmp_path/"home"; home.mkdir()
    env=dict(os.environ)
    env.pop("PYTHONPATH",None)
    env.update(HOME=str(home),RUSH_DATA_DIR=str(tmp_path/"data"),
               PATH=str(bindir)+os.pathsep+os.defpath,NO_COLOR="1")
    argv=[sys.executable,"-m","rush","iac",str(root/"main.tf"),*["--scope","file","--no-cache"],"--json"]
    cli=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert cli.returncode==0,cli.stderr
    left=json.loads(cli.stdout)
    pass
    right=exchange_stdio(sys.executable,root,env,"rush_iac",{"path":str(root/"main.tf"),"scope":"file","no_cache":True})
    assert left["tool"]==right["tool"]=="iac"
    assert left["status"]==right["status"]=="ok"
    assert left["findings"]==right["findings"]==[]
    assert left["metadata"]["scope"]["requested_files"]==right["metadata"]["scope"]["requested_files"]==[str(root/"main.tf")]
    assert left["metadata"]["scope"]["module_context_files"]==right["metadata"]["scope"]["module_context_files"]==[str(root/"main.tf"),str(root/"variables.tf")]
    records=[json.loads(line) for line in log.read_text().splitlines()]
    records=[row for row in records if "--version" not in row[1] and "--help" not in row[1]]
    assert [row[0] for row in records]==["tflint","checkov","tflint","checkov"]
    assert all("Secret" not in json.dumps(value) for value in (left,right))
    before_dirs=sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir())
    before={p.relative_to(root).as_posix():p.read_bytes()
            for p in root.rglob("*") if p.is_file()}
    log_before=log.read_bytes()
    denied_cli=subprocess.run([sys.executable,"-m","rush","iac",str(root),
        *["--trial-plan-impact","patch.diff","--state-fixture","state.json","--runtime-path",str(bindir/"docker"),"--image-ref","fixture@sha256:"+"0"*64,"--no-cache"],"--json"],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    denied_left=json.loads(denied_cli.stdout)
    denied_right=exchange_stdio(sys.executable,root,env,"rush_iac",{"path":str(root),"trial_plan_impact":"patch.diff","state_fixture":"state.json","runtime_path":str(bindir/"docker"),"image_ref":"fixture@sha256:"+"0"*64,"no_cache":True})
    assert denied_cli.returncode==0,denied_cli.stderr
    assert denied_left["status"]==denied_right["status"]=="skipped"
    assert log.read_bytes()==log_before
    invalid=exchange_stdio(sys.executable,root,env,"rush_iac",{
        "path":str(root/"missing"),"unexpected":1,"allow_cache_write":"true"})
    assert invalid["status"]=="error"
    assert invalid["metadata"]["reason"]=="invalid_request"
    assert invalid["metadata"]["invalid_fields"]==["allow_cache_write","unexpected"]
    assert log.read_bytes()==log_before
    after={p.relative_to(root).as_posix():p.read_bytes()
           for p in root.rglob("*") if p.is_file()}
    assert before==after
    assert before_dirs==sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir())
~~~
The denied requests intentionally select effectful operations without grants; validation of syntactically valid required fields precedes no runtime, engine/version or scratch side effect. Project tree snapshot covers all files; additionally assert directories unchanged when implementing node (capture sorted directory paths in same before/after snapshot), because empty .rush creation is also forbidden.

## T3 — public transport, schema, and live-engine acceptance

Implement command transport acceptance in rush-cli. Read this plan and relevant existing CLI/MCP references first.

# Feature: identical shared behavior through actual CLI and initialized stdio MCP

## Required behavior

Use actual subprocess CLI and initialized JSON-RPC stdio. Complete tests/test_mcp.py::test_q16_iac_cli_and_initialized_stdio body above supplies literal command, fixture, fields and denial assertions. Shared exchange_stdio helper below is defined once by Batch integration owner. Add tests/test_cli_registry.py::test_q16_iac_cli_options for all explicit flags, invalid enums, missing/empty/staged cases. Actual engine fixture logs every call including --version; genuine-engine acceptance remains separate.

~~~python
def exchange_stdio(python, root, env, tool_name, arguments, *, registry_root=None):
    import json, queue, subprocess, threading
    argv=[python, "-m", "rush", "mcp", "serve", "--profile", "full"]
    if registry_root is not None:
        startup=("import sys;from pathlib import Path;from rush.workflows import projects;"
                 "projects.default_data_root=lambda:Path(sys.argv[1]);"
                 "from rush.cli import cli;cli(['mcp','serve','--profile','full'])")
        argv=[python,"-c",startup,str(registry_root)]
    child = subprocess.Popen(
        argv,
        cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1)
    output = queue.Queue()
    def collect():
        for line in child.stdout:
            output.put(line)
    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    from collections import deque
    diagnostics=deque(maxlen=1000)
    def drain_stderr():
        for line in child.stderr:
            diagnostics.append(line)
    stderr_reader=threading.Thread(target=drain_stderr,daemon=True)
    stderr_reader.start()
    def send(value):
        child.stdin.write(json.dumps(value) + "\n")
        child.stdin.flush()
    def receive(identity):
        while True:
            item = json.loads(output.get(timeout=1800))
            assert item["jsonrpc"] == "2.0"
            if item.get("id") == identity:
                assert "error" not in item, item
                return item["result"]
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "rush-remediation-test", "version": "1"}}})
        initialized = receive(1)
        assert "protocolVersion" in initialized
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = receive(2)
        schema = next(t["inputSchema"] for t in listed["tools"] if t["name"] == tool_name)
        assert schema["type"] == "object"
        expected={"scope":(["string"],"module"),
            "plan_evidence":(["string","null"],None),
            "trial_plan_impact":(["string","null"],None),
            "state_fixture":(["string","null"],None),
            "provider_fixture":(["string","null"],None),
            "allowed_destroy_ids":(["array","null"],None),
            "runtime_path":(["string","null"],None),
            "image_ref":(["string","null"],None)}
        grants={"allow_network","allow_download","allow_cache_write","allow_build","allow_slow","allow_artifact_write","allow_browser"}
        injected={"project","result_view","limit","max_bytes","no_cache"}
        assert set(schema["properties"])=={"path"}|set(expected)|grants|injected
        assert schema["required"]==["path"]
        assert schema["additionalProperties"] is False
        for name,(types,default) in expected.items():
            node=schema["properties"][name]
            assert {part.get("type") for part in node.get("anyOf",[node])}==set(types)
            assert node["default"]==default
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": tool_name, "arguments": arguments}})
        envelope = receive(3)
        assert envelope.get("isError", False) is False
        content = envelope.get("structuredContent")
        if content is None:
            content = json.loads(next(c["text"] for c in envelope["content"] if c["type"] == "text"))
        return content
    finally:
        child.terminate()
        child.wait(timeout=10)
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()
~~~

This helper belongs to existing tests/test_mcp.py, Batch integration owner; one definition reused across Q11–Q20, no production runner or new harness. The helper drains stderr concurrently into a bounded deque (1000 lines); normal fixture emits no stderr. All stdout lines must parse JSON-RPC, including notifications; plain logs fail at json.loads. Tests must compare actual CLI JSON against returned content fields: tool/status/findings, command-specific scope and digest/evidence fields, metadata.engines engine/status/cwd/config/executable identity. Exclude duration, request/run IDs, timestamps, transport spelling of original targets and recovery handles. Never compare different output paths or source roots.

CLI and MCP receive identical HOME/RUSH_DATA_DIR/PATH with fixture executable outside project. Record every non-version engine call to test-owned log; identical request must produce one expected invocation per applicable engine in each transport. No result cache; use CLI --no-cache and MCP no_cache=true where supported. SBOM handwritten CLI lacks no-cache today, so run distinct explicit outputs or delete only test-owned output between same-path calls, never add unsupported flag.

Required second transport cases: denied effectful request records zero engine/runtime/version calls and byte-identical project tree; granted request reaches real command implementation; malformed engine JSON returns error, never clean; one supported engine absent retains incomplete evidence; MCP unknown fields/invalid bool cause no effect. Preserve stdout JSON-RPC and stderr diagnostics.

## Deliverables

Shared owner writes exact transport tests above, relevant CLI option map or handwritten SBOM options, command-specific TOOL_SPECS descriptions/options, relevant MCP expected parameter sets, CLI outcome fixture and reference/coverage rows listed in shared file map. No new MCP name or transport implementation.

## Constraints

Transport fixture executable is controlled engine boundary, not real-engine proof. No network or installs. Live test requires preinstalled engine resolved by same secure resolver as execution. ENGINE_PACKAGES source policy for hadolint/tflint/checkov/gitleaks/cdxgen is latest_stable, not a numeric minimum; no invented minimum version. Capability probe requires exact documented-in-source flags/report contract; unsupported installed version yields skipped with reason incompatible_engine before analysis, not silently weaker argv. Capture actual --version in acceptance evidence.

## Checks to run before reporting

Run literal command-specific test nodes listed below plus common Phase70/ruff commands. Future real-engine acceptance may fail for missing preinstalled executable; report that external prerequisite precisely. Never treat skipped test as successful live acceptance.

## Completion

Shared implementations reached by actual CLI and initialized stdio, deterministic domain fields match, denied operations have zero effects, real engine fixture produces expected diagnosis/artifact and complete references describe only executable behavior.


## Exact transport/live fixtures and readiness

Transport executable fixtures tflint/checkov reside outside project. Each --version prints fixture-1 and logs invocation. TFLint outputs {"issues":[],"errors":[]} exit0. Checkov outputs {"results":{"failed_checks":[],"parsing_errors":[]}} exit0. Project rush.toml=[tools.iac], main.tf and variables.tf contain variable declarations. Actual CLI iac main.tf --scope file --json --no-cache versus initialized rush_iac(path=main.tf,scope="file",no_cache=true): both status ok, requested_files=[main.tf], module_context_files=[main.tf,variables.tf], each engine executes module once, consumed count null. Missing Checkov case requires warn and retained skipped child. Denied trial requires zero calls and zero .rush/scratch additions.

Live tests/test_iac.py::test_real_iac_module_scope runs preinstalled tflint/checkov against valid main.tf plus variables.tf. Require two engine records, actual module cwd and version; a deliberately malformed Terraform file must return error from parsing, not fabricated finding. Installed version policy latest_stable, capability flags derived from current adapters, no numeric minimum invented. Both binaries absent during planning, so real test unexecuted.

Run rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_iac.py tests/test_tflint_reference.py tests/test_checkov_reference.py tests/test_cli_registry.py tests/test_mcp.py -q plus common gates.

Development entry ready: T1 current-boundary RED observed and exact source/files/ownership fixed. T2 and T4 designs are complete separately classified proposals, not approved production work. Future PR sequence T1+shared command integration, then approved T2, P0 before approved T4. No PR created. Source/runtime fixture absence blocks future live acceptance only; no production pass claimed.
