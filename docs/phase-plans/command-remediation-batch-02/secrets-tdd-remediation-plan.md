# Q17 — secrets TDD remediation development plan

Goal: eliminate false-clean Gitleaks results, disclose history/working-tree scope and keep every result/error/persisted byte secret-free. Covers complete audit Q17 lines 6155–6558, source-bound continuity and distinct canary proposal. No production fixes applied.

## Requirement ledger

| Requirement/category | Current source | Concrete change / gate |
|---|---|---|
| Repair: exit1+[] false clean | engines/gitleaks.py:49–94 validates list but derives status from findings only | T1 strict report/exit agreement; exact report_exit_mismatch error |
| Repair: malformed entries/silent output/path escape | current default stdout=[] and permissive dict comprehension | Strict complete entry validation, fixed redacted summaries, contained paths; no raw |
| Preserve existing redaction/availability | tools/secrets.py:21–27; tests/test_supply_chain_tools.py:15–46 | No Secret/Match/stderr copied; missing engine skipped |
| Repair/compatibility: explicit history scope | adapter currently detect --source, args ignored | T2 explicit scope default history, directory-only, matching git/dir argv and scope metadata |
| Ordinary extension, proposed/unapproved | no prior-result persistence | T3 content-addressed source-bound fingerprints, clean scans too, cache grant and atomic no-clobber |
| Distinct expansion, proposed/unapproved | no canary challenge | T4 generated fake canary with exact self-contained config; actual scan detects or reports gap; no history claim |
| User baselines | shared contract below | Preserve provisioning/redacted model/voice/companion consumption; no invented capabilities |

## Observed current-boundary RED

Executed GitleaksEngine.normalize({"stdout":"[]","stderr":"","exit_code":1},root,"secrets") with only engine.version patched to fixture. Required status error; observed ok. Assertion failed at intended status; no real binary, future keyword, mock availability mismatch or invalid fixture involved. Python3.12.12 offline. Real Gitleaks absent in inspected environment.

Implement strict Gitleaks report handling in rush-cli. Read AGENTS.md, Phase70 T8/T9/T16/T27 and this plan first.

# Feature: T1 — secret findings cannot normalize to false clean

## Required behavior

Existing normalize(raw,path,tool_name) stays API. Clean iff exit0 and valid empty JSON array. Detection iff exit1 and at least one fully valid finding. Exit1+[], exit0+finding, unsupported/non-int/bool exit => error terminal_reason=report_exit_mismatch. Empty stdout, malformed JSON, non-array or malformed member => error malformed_output. Every File/RuleID nonempty string, StartLine exact positive int (bool rejected); NUL/escaping path invalid. Ignore all unneeded sensitive fields, never include raw stdout/stderr, Secret, Match or original exception values. Missing binary continues skipped. Root-relative paths become contained absolute paths; existing relative-path test expected value updated deliberately, transport logical mapping preserved.

## Deliverables

Command owner: src/rush/engines/gitleaks.py::GitleaksEngine.normalize; tests/test_secrets.py new; tests/test_supply_chain_tools.py exact normalizer path expectation only (shared owner serial edit). No change to missing-engine mechanism.

Runnable RED in tests/test_secrets.py:
~~~python
from pathlib import Path
from unittest.mock import patch
from rush.engines.gitleaks import GitleaksEngine

def test_exit_one_empty_is_error(tmp_path):
    engine=GitleaksEngine()
    with patch.object(engine,"version",return_value="fixture"):
        result=engine.normalize({"stdout":"[]","stderr":"","exit_code":1},
                                tmp_path,"secrets")
    assert result["status"]=="error"
    assert result["metadata"]["terminal_reason"]=="report_exit_mismatch"
    assert result["findings"]==[]
    assert result.get("raw") is None
~~~

Minimum GREEN replacement in src/rush/engines/gitleaks.py:
~~~python
def normalize(self, raw, path, tool_name):
    from rush.tools.common import skipped_result
    if raw.get("summary") in {"engine_missing","engine_incompatible"}:
        return skipped_result(tool_name,self.name,raw["summary"])
    from pathlib import Path
    from rush.io.physical_paths import PhysicalRoot, ContainmentError
    root = path if path.is_dir() else path.parent
    try:
        report = json.loads(raw.get("stdout", ""))
        if not isinstance(report, list):
            raise ValueError("invalid report")
        findings = []
        for item in report:
            if (not isinstance(item, dict) or not isinstance(item.get("File"), str)
                or not item["File"] or not isinstance(item.get("RuleID"), str)
                or not item["RuleID"] or type(item.get("StartLine")) is not int
                or item["StartLine"] < 1):
                raise ValueError("invalid finding")
            target = Path(item["File"])
            relative = target.relative_to(root) if target.is_absolute() else target
            checked = PhysicalRoot(root).open_contained(relative)
            findings.append({"path":str(checked),"line":item["StartLine"],
                "rule":item["RuleID"],"severity":"error",
                "message":"Potential secret detected"})
    except (TypeError, ValueError, OSError, ContainmentError):
        return error_result(tool_name,self.name,"gitleaks report malformed",
            duration_ms=raw.get("duration_ms",0),terminal_reason="malformed_output")
    code=raw.get("exit_code")
    if type(code) is not int or code not in (0,1) or (code==1)!=bool(findings):
        return error_result(tool_name,self.name,"gitleaks exit/report mismatch",
            duration_ms=raw.get("duration_ms",0),terminal_reason="report_exit_mismatch")
    return ToolResult(tool=tool_name,engine=self.name,engine_version=self.version(),
        status="fail" if findings else "ok",duration_ms=raw.get("duration_ms",0),
        summary=f"gitleaks: {len(findings)} potential secret(s)",
        findings=findings,raw=None)
~~~
Uses existing module json/error_result/ToolResult imports. Add bounded input guard at raw parse: encoded stdout max4MiB, max100000 findings; overflow returns error, never truncates to clean. Path root comes from already normalized engine target; absolute nested source path validated without following internal symlink.

Regression runnable:
~~~python
def test_synthetic_secret_redacted_everywhere(tmp_path):
    import json
    from unittest.mock import patch
    from rush.engines.gitleaks import GitleaksEngine
    token="RUSH_FAKE_NEVER_REAL_abc123"
    report=[{"File":"secret.txt","RuleID":"generic-api-key","StartLine":1,
             "Secret":token,"Match":token,"Description":token}]
    engine=GitleaksEngine()
    with patch.object(engine,"version",return_value="fixture"):
        result=engine.normalize({"stdout":json.dumps(report),"stderr":token,
                                 "exit_code":1},tmp_path,"secrets")
    assert result["status"]=="fail"
    assert token not in json.dumps(result)
    assert result["findings"][0]["message"]=="Potential secret detected"
~~~
Also test malformed entry after valid one discards partial verdict; path traversal/symlink, StartLine true, silent output, exit2 and exit0 findings all exact error. Refactor only repeated validation inside normalizer; no custom redaction framework.

## Constraints

Never expose sensitive stdout/stderr in error handling. No output-field scanning as substitute for engine normalization tests. No branch returning unknown/deferred status.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_secrets.py::test_exit_one_empty_is_error tests/test_secrets.py::test_synthetic_secret_redacted_everywhere tests/test_supply_chain_tools.py -q

## Completion

All strict report/exit cases and redaction assertions pass through current callable, no raw leaks.

# Feature: T2 — explicitly declared directory/history scope

## Required behavior

SecretsTool.__call__(path:Path,*,scope:str="history",config_path:str|None=None,prior_result_id:str|None=None,record_result:bool=False,challenge_detection:bool=False,challenge_rule:str="generic-api-key",allow_cache_write:bool=False,allow_slow:bool=False); run accepts same plus config=None,permissions=None. T2 only activates scope/config; later options remain separate proposals until authorized. scope enum history|working_tree. Directory required; history must be Git repository. Default preserves current historical scan semantics. File input errors explicitly rather than silently scanning parent/history.

GitleaksEngine.run receives ["--scope",scope] optionally ["--config",validated_absolute_config]. Reject every other argument shape. Construct [resolved_binary,"git" if history else "dir",str(path),"--report-format","json","--report-path","-","--no-banner","--redact=100",*config_pair], timeout120, ownership_kwargs preserved. Verify installed binary supports selected command and flags through local help/version capability tests; no numeric version floor invented (source policy latest_stable). Incompatible installed executable returns skipped reason incompatible_engine before analysis. Normalizer receives canonical EngineResult.

Config path contained in logical project, read at most1MiB, TOML parsed, no symlink. Reject extend.path (unbounded external closure); permit extend.useDefault. Source digest and config digest captured; never include config raw bytes. Config wins only when explicitly requested. No project executable hooks, no network or inherit GITLEAKS_CONFIG/GITLEAKS_CONFIG_TOML/GITLEAKS_CONFIG_TOML_FROM_GIT environment overrides; scrub these and credentials in child_env while preserving required runtime PATH and OS basics.

metadata.scope version1 kind=files root/logical_root, scan_kind=history|working_tree, selected_file_filter=false, requested_targets, coverage=unavailable, consumed_file_count=null, reason=engine_discovers_directory_or_history. Do not call history matched count a working-tree file count. Preserve metadata.engines and execution.

## Deliverables

src/rush/tools/secrets.py::__call__/run; src/rush/engines/gitleaks.py::run/child_env; tests/test_secrets.py::test_history_scope_explicit/::test_working_tree_scope/::test_file_target_rejected. Shared owner explicit --scope choice(default history), --config-path Path; MCP typed matching fields and relevant docs. No config-driven scope effects.

## Constraints

No silently weakened legacy detect fallback, no selected-file filter that implies narrow execution. Scope is observable evidence.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_secrets.py::test_history_scope_explicit tests/test_secrets.py::test_working_tree_scope tests/test_secrets.py::test_file_target_rejected -q

## Completion

Actual git/dir argv and scope agree across direct/CLI/MCP; history compatibility documented.

# Feature: T3 — source-bound secret-free continuity (ordinary extension, proposed)

## Required behavior

prior_result_id=None and record_result=False; CLI --prior-result-id SHA256, --record-result. Working_tree only; history rejects continuity before scanning because current-file digest cannot identify historical Git blob. Record requires cache_write before scanner/version/mkdir; read-only comparison writes nothing. No automatic memory ingestion.

Define source_manifest(root)->dict[str,str] in secrets.py: walk all ordinary contained files except .git/.rush, sorted POSIX relative paths, reject symlink/reparse, cap100000 files/1GiB total, SHA256 bytes including clean files. Capture before engine then again after; mismatch errors source_changed before continuity output/persistence. Fingerprint SHA256(canonical JSON [relative_path,source_file_SHA256,line,rule]); no token/Match/message/raw retained. Historical result payload exactly {schema_version:1,project_root:logical_root,source_hashes:map,fingerprints:sorted}. Canonical JSON sort_keys/separators, UTF8; result_id=SHA256(payload).

source_bound_history(root,result,*,before_manifest,prior_result_id=None,record_result=False,permissions=None)->dict: validate prior ID64hex, PhysicalRoot opens .rush/secret-scans/<ID>.json read-only; max4MiB, verify bytes digest, exact schema/root/types/hash values. Compare fingerprints by set intersection; source hash map inequality yields prior_source_changed=true including prior clean scan. Only complete ok/fail results record; malformed/error/skipped never record. Capture effective scope/config and engine version in payload schema_version1 as scanner_identity={scope,config_sha256,engine,engine_version}; recurring label requires equal scanner_identity as well as fingerprint (different rule configuration is not recurring execution). Return current_fingerprints,recurring_fingerprints,prior_source_changed,scanner_identity_changed,prior_evidence="content-addressed historical result; not fresh execution",result_id when written.

Write after grant through same-filesystem named temporary file in contained .rush/secret-scans mode0700, file0600, fsync, atomic os.link no-clobber then unlink temporary; existing identical payload accepted, collision error. Validate directory immediately before publish. Denied => skipped/not_run, no scan/version/mkdir. Crash before link leaves owned temp removed; after link valid content-addressed payload survives. Never delete old result or restore stale bytes.

Runnable future acceptance:
~~~python
def test_fingerprint_continuity_without_secret(tmp_path):
    import json
    from rush.tools.secrets import source_manifest, source_bound_history
    from rush.permissions import ExecutionPermissions
    file=tmp_path/"app.py"
    file.write_text("token='fake-only'\n")
    result={"status":"fail","findings":[{"path":str(file),"line":1,"rule":"generic-api-key"}],
            "engine":"gitleaks","engine_version":"fixture",
            "metadata":{"scope":{"scan_kind":"working_tree"},"config_sha256":None}}
    saved=source_bound_history(tmp_path,result,before_manifest=source_manifest(tmp_path),
        record_result=True,permissions=ExecutionPermissions(cache_write=True))
    current=source_bound_history(tmp_path,result,before_manifest=source_manifest(tmp_path),
        prior_result_id=saved["result_id"])
    assert current["recurring_fingerprints"]==saved["current_fingerprints"]
    stored=tmp_path/".rush"/"secret-scans"/(saved["result_id"]+".json")
    assert "fake-only" not in stored.read_text()
    file.write_text("token='changed-fake'\n")
    changed=source_bound_history(tmp_path,result,before_manifest=source_manifest(tmp_path),
        prior_result_id=saved["result_id"])
    assert changed["recurring_fingerprints"]==[]
    assert changed["prior_source_changed"] is True
    stored.write_text("{}")
    try:
        source_bound_history(tmp_path,result,before_manifest=source_manifest(tmp_path),
                             prior_result_id=saved["result_id"])
    except ValueError as error:
        assert str(error)=="stored result digest mismatch"
    else:
        raise AssertionError("tampered history accepted")
~~~

## Deliverables

src/rush/tools/secrets.py::source_manifest/source_bound_history and dispatch; tests/test_secrets.py::test_fingerprint_continuity_without_secret/::test_clean_scan_drift/::test_scan_drift/::test_history_denial_zero_effects/::test_scan_identity_change. Shared owner two options/schema/docs; no new memory store.

## Constraints

Source map completeness required; size/read errors stop, no partial recurring claim. No historical Git continuity until a separately designed commit/blob identity contract. Prior output provenance never becomes fresh scan evidence.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_secrets.py::test_fingerprint_continuity_without_secret tests/test_secrets.py::test_clean_scan_drift tests/test_secrets.py::test_scan_drift tests/test_secrets.py::test_history_denial_zero_effects tests/test_secrets.py::test_scan_identity_change -q

## Completion

Actual persistence/tamper rejection and changed/clean source cases pass, token absent from all result/artifact bytes. Proposed extension remains unapproved.

# Feature: T4 — scanner detection canary (distinct proposal, unapproved)

## Required behavior

challenge_detection=False, challenge_rule="generic-api-key", config_path=None; CLI --challenge-detection --challenge-rule [generic-api-key|aws-access-token] --config-path PATH --allow-slow. Slow grant and explicit contained self-contained config required BEFORE base scan/probes/temp creation. Does not execute project source, load remote rules or claim OS sandboxing; input is a new private synthetic directory. No P0 dependency because scanner consumes only generated data with self-contained rule configuration; if executable project rules become supported, P0 required before them.

challenge_detection(root,*,challenge_rule,config_path,permissions)->dict in secrets.py: hash config bytes, parse TOML reject external extend.path; resolve actual Gitleaks. Generate random fake generic token "rush-canary-"+secrets.token_hex(24), or synthetic AKIA plus16 chars A-Z234567; create mode0700 temporary directory and mode0600 rush_canary.env containing expected key assignment. Run exact selected scanner with dir, explicit config, JSON report, --redact=100, timeout60; normalize through T1 (no parallel parser). detected only exact rule and canary file match. Returned status passed iff detected and serialized canonical result excludes fake bytes, otherwise failed; parser/exit error raises unusable challenge, never gap==passed. Rehash config afterward, mismatch errors. Cleanup scratch on success/error/timeout. Return rule,detected,redacted,status,config_digest,engine_version,canary_digest,scope="synthetic directory scan; does not prove Git-history coverage". Never return token. A canary miss makes otherwise ok parent warn; fail/error retained.

Test controlled scanner boundary reads actual temp canary file and returns matching report (then miss report) to exercise adapter+normalizer; asserts temp removed/token absent. Real preinstalled Gitleaks with explicit TOML [[rules]] id="generic-api-key", regex="rush-canary-[0-9a-f]{48}" must detect generated pattern; second config removes that rule and expects failed gap. Original source/config unchanged. This tests detector/config readiness for exact synthetic pattern only; it does not certify absence of unknown secrets.

## Deliverables

src/rush/tools/secrets.py::challenge_detection plus integration; tests/test_secrets.py::test_canary_miss_reports_gap_without_leaking_token/::test_canary_config_drift_rejected/::test_real_canary_detects_configured_rule; explicit shared CLI/MCP fields above.

## Constraints

No real credentials, project writes, raw scanner logs, external config imports or invented successful challenge. No misleading history certification. Capture config/engine identity.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_secrets.py::test_canary_miss_reports_gap_without_leaking_token tests/test_secrets.py::test_canary_config_drift_rejected tests/test_secrets.py::test_real_canary_detects_configured_rule -q

## Completion

Genuine configured scanner detects generated canary and miss variant reports gap without leaks; remains separately unapproved.

### Runnable canary controller acceptance

Proposed test in tests/test_secrets.py; future helper absence is interface failure, not T1 behavioral reproduction.
~~~python
def test_canary_miss_reports_gap_without_leaking_token(tmp_path):
    import json,subprocess
    from pathlib import Path
    from unittest.mock import patch
    from rush.tools.secrets import challenge_detection
    from rush.permissions import ExecutionPermissions
    from rush.engines.gitleaks import GitleaksEngine
    cfg=tmp_path/"gitleaks.toml"
    cfg.write_text("[extend]\nuseDefault=true\n")
    cfg_bytes=cfg.read_bytes()
    seen=[]; payloads=[]
    def scanner(argv,**kwargs):
        directory=Path(argv[2]); canary=directory/"rush_canary.env"
        seen.append(directory); payloads.append(canary.read_text())
        return subprocess.CompletedProcess(argv,0,"[]","")
    engine=GitleaksEngine()
    with patch("rush.runtime.binaries.resolve_binary",return_value="/fixture/gitleaks"), \
         patch("rush.runtime.subprocesses.run_subprocess",side_effect=scanner), \
         patch.object(engine,"version",return_value="fixture"), \
         patch.dict("rush.engines.ENGINES",{"gitleaks":engine}):
        result=challenge_detection(tmp_path,challenge_rule="generic-api-key",
            config_path="gitleaks.toml",permissions=ExecutionPermissions(slow=True))
    assert len(seen)==1
    assert result["status"]=="failed"
    assert result["detected"] is False and result["redacted"] is True
    assert all(not path.exists() for path in seen)
    assert all(value not in json.dumps(result) for value in payloads)
    assert cfg.read_bytes()==cfg_bytes
    assert sorted(p.name for p in tmp_path.iterdir())==["gitleaks.toml"]
~~~
Helper imports runtime resolver/process functions internally so these exact patch boundaries apply. A corresponding detected case returns actual canary File/RuleID/StartLine with exit1 and verifies T1 normalizer erases Secret/Match. Real canary test uses exact self-contained rule from T4 with actual installed binary.


## Complete implementation and route packet — review corrections

These literal bodies implement earlier algorithms; they are proposed replacements in the future implementation checkout, not code installed during planning. Preserve existing imports/helpers not replaced. Every helper below has its exact caller in the full class replacement; no hidden dispatcher or second runtime. Command owner owns command-local definitions; Batch integration owner owns catalog/CLI/MCP/reference changes. Request-only options cannot be activated by project configuration.

### Complete command-local controllers
Insert these module-level bodies in src/rush/tools/secrets.py; replace earlier pseudocode descriptions, preserve T1 existing repair/parser.
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


def source_digest(manifest):
    import hashlib,json
    return hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _secret_bytes(root,path,limit=4*1024*1024):
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
        raise ValueError("secret_input_too_large")
    return raw


def _validated_secret_config(root,path,*,challenge=False):
    import hashlib,tomllib
    raw=_secret_bytes(root,path,1024*1024)
    payload=tomllib.loads(raw.decode("utf-8"))
    extension=payload.get("extend",{})
    if not isinstance(extension,dict) or "path" in extension or (challenge and extension):
        raise ValueError("external_secret_config_refused")
    return raw,hashlib.sha256(raw).hexdigest()


def _publish_history(root,identifier,raw):
    import os,uuid
    from rush.io.physical_paths import PhysicalRoot
    if os.open not in os.supports_dir_fd or os.link not in os.supports_dir_fd or not hasattr(os,"O_NOFOLLOW"):
        raise ValueError("race_safe_file_io_unavailable")
    PhysicalRoot(root).open_contained(".rush/secret-scans",purpose="write")
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW;fd=os.open(root,flags)
    try:
        for name in (".rush","secret-scans"):
            try:os.mkdir(name,0o700,dir_fd=fd)
            except FileExistsError:pass
            child=os.open(name,flags,dir_fd=fd);os.close(fd);fd=child
        temp=".new-"+uuid.uuid4().hex
        file=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            with os.fdopen(file,"wb",closefd=False) as stream:
                stream.write(raw);stream.flush();os.fsync(file)
        finally:os.close(file)
        try:
            try:os.link(temp,identifier+".json",src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
            except FileExistsError:
                if _secret_bytes(root,f".rush/secret-scans/{identifier}.json")!=raw:
                    raise ValueError("history_collision")
            os.fsync(fd)
        finally:os.unlink(temp,dir_fd=fd)
    finally:os.close(fd)


def source_bound_history(root,result,*,before_manifest,prior_result_id=None,record_result=False,permissions=None):
    import hashlib,json,re
    from pathlib import Path
    from rush.permissions import ExecutionPermissions,check_permissions
    if record_result:
        allowed,missing=check_permissions(ExecutionPermissions(cache_write=True),permissions)
        if not allowed:raise PermissionError(", ".join(missing))
    if source_manifest(root)!=before_manifest:
        raise ValueError("source_changed")
    if result["status"] not in {"ok","fail"}:
        raise ValueError("incomplete_secret_scan")
    identity={"scope":result.get("metadata",{}).get("scope",{}).get("scan_kind"),
        "config_sha256":result.get("metadata",{}).get("config_sha256"),
        "engine":result.get("engine"),"engine_version":result.get("engine_version")}
    if identity["scope"]!="working_tree":
        raise ValueError("history_continuity_unsupported")
    fingerprints=[]
    for finding in result["findings"]:
        path=Path(finding["path"]);relative=path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
        line,rule=finding["line"],finding["rule"]
        if relative not in before_manifest or type(line) is not int or line<1 or not isinstance(rule,str) or not rule:
            raise ValueError("invalid_fingerprint_evidence")
        encoded=json.dumps([relative,before_manifest[relative],line,rule],separators=(",",":")).encode()
        fingerprints.append(hashlib.sha256(encoded).hexdigest())
    fingerprints=sorted(set(fingerprints))
    payload={"schema_version":1,"project_root":str(Path(root).resolve()),"source_hashes":before_manifest,
             "fingerprints":fingerprints,"scanner_identity":identity}
    raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    if len(raw)>4*1024*1024:raise ValueError("stored_result_too_large")
    previous=None
    if prior_result_id is not None:
        if not isinstance(prior_result_id,str) or not re.fullmatch("[0-9a-f]{64}",prior_result_id):
            raise ValueError("invalid_prior_result_id")
        old=_secret_bytes(root,f".rush/secret-scans/{prior_result_id}.json")
        if hashlib.sha256(old).hexdigest()!=prior_result_id:
            raise ValueError("stored result digest mismatch")
        previous=json.loads(old)
        if (not isinstance(previous,dict) or set(previous)!=set(payload)
                or type(previous["schema_version"]) is not int or previous["schema_version"]!=1
                or previous["project_root"]!=payload["project_root"]
                or not isinstance(previous["source_hashes"],dict)
                or not isinstance(previous["fingerprints"],list)
                or not isinstance(previous["scanner_identity"],dict)
                or set(previous["scanner_identity"])!=set(identity)):
            raise ValueError("stored_result_invalid")
        if any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch("[0-9a-f]{64}",v)
               for k,v in previous["source_hashes"].items()):
            raise ValueError("stored_result_invalid")
        if any(not isinstance(v,str) or not re.fullmatch("[0-9a-f]{64}",v) for v in previous["fingerprints"]):
            raise ValueError("stored_result_invalid")
    identifier=hashlib.sha256(raw).hexdigest()
    if record_result:_publish_history(root,identifier,raw)
    same_identity=previous is not None and previous["scanner_identity"]==identity
    return {"current_fingerprints":fingerprints,
        "recurring_fingerprints":sorted(set(fingerprints)&set(previous["fingerprints"])) if same_identity else [],
        "prior_source_changed":previous is not None and previous["source_hashes"]!=before_manifest,
        "scanner_identity_changed":previous is not None and not same_identity,
        "prior_evidence":"content-addressed historical result; not fresh execution",
        **({"result_id":identifier} if record_result else {})}


def challenge_detection(root,*,challenge_rule,config_path,permissions):
    import hashlib,json,os,secrets,tempfile
    from pathlib import Path
    from rush.permissions import ExecutionPermissions,check_permissions
    from rush.runtime.binaries import resolve_binary
    from rush.runtime.subprocesses import run_subprocess
    from rush.engines import ENGINES
    allowed,missing=check_permissions(ExecutionPermissions(slow=True),permissions)
    if not allowed:raise PermissionError(", ".join(missing))
    if challenge_rule not in {"generic-api-key","aws-access-token"} or config_path is None:
        raise ValueError("invalid_canary_request")
    raw,digest=_validated_secret_config(root,config_path,challenge=True)
    binary=resolve_binary("gitleaks",project_root=Path(root))
    if binary is None:raise ValueError("gitleaks_unavailable")
    token=("rush-canary-"+secrets.token_hex(24) if challenge_rule=="generic-api-key"
           else "AKIA"+"".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16)))
    with tempfile.TemporaryDirectory(prefix="rush-canary-") as folder:
        scratch=Path(folder);canary=scratch/"rush_canary.env";cfg=scratch/"rules.toml"
        canary.write_text("API_KEY="+token+"\n");canary.chmod(0o600)
        cfg.write_bytes(raw);cfg.chmod(0o600)
        child=run_subprocess([binary,"dir",str(scratch),"--config",str(cfg),
            "--report-format","json","--report-path","-","--no-banner","--redact=100"],
            timeout=60,env=ENGINES["gitleaks"].child_env())
        normalized=ENGINES["gitleaks"].normalize({"exit_code":child.returncode,
            "stdout":child.stdout,"stderr":child.stderr},scratch,"secrets")
        if normalized["status"] not in {"ok","fail"}:
            raise ValueError("unusable_canary_result")
        detected=any(f["rule"]==challenge_rule and Path(f["path"])==canary for f in normalized["findings"])
        redacted=token not in json.dumps(normalized)
        version=normalized.get("engine_version")
    if _validated_secret_config(root,config_path,challenge=True)[1]!=digest:
        raise ValueError("config_changed")
    return {"rule":challenge_rule,"detected":detected,"redacted":redacted,
        "status":"passed" if detected and redacted else "failed","config_digest":digest,
        "engine_version":version,"canary_digest":hashlib.sha256(token.encode()).hexdigest(),
        "scope":"synthetic directory scan; does not prove Git-history coverage"}


run_detection_challenge=challenge_detection
~~~

### Complete callable and method insertion
Module-level utilities below, followed by full SecretsTool replacement. Existing ContentTool import is retained for its subclasses. Config is verified existing ToolConfig: any nonempty options fails request_only_options; unknown config keys already fail catalog validation. Pins/effect selections stay explicit request fields. Runtime source and logical destination anchors use existing executor accessors, not process cwd.
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

class SecretsTool(ToolFn):
    name="secrets"
    @property
    def mcp_description(self):
        return "Inspect secrets using shared local engines; explicit effect grants remain required."

    def __call__(self, path: Path, *,
                 scope: str = "history",
                 config_path: str | None = None,
                 prior_result_id: str | None = None,
                 record_result: bool = False,
                 challenge_detection: bool = False,
                 challenge_rule: str = "generic-api-key",
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
        return self.run(path,scope=scope,config_path=config_path,prior_result_id=prior_result_id,record_result=record_result,challenge_detection=challenge_detection,challenge_rule=challenge_rule,permissions=permissions)
    
    def run(self, path: Path, *,
            scope: str = "history",
            config_path: str | None = None,
            prior_result_id: str | None = None,
            record_result: bool = False,
            challenge_detection: bool = False,
            challenge_rule: str = "generic-api-key",
            config=None, permissions=None) -> ToolResult:
        try:
            if config is not None and config.options:
                raise ValueError("request_only_options")
            path,logical,target=_roots(path)
            if not path.is_dir() or scope not in {"history","working_tree"}:
                raise ValueError("directory_and_valid_scope_required")
            if type(record_result) is not bool or type(challenge_detection) is not bool:
                raise ValueError("invalid_request")
            if (record_result or prior_result_id is not None) and scope!="working_tree":
                raise ValueError("history_continuity_unsupported")
            if record_result:_require_grants(permissions,cache_write=True)
            if challenge_detection:
                _require_grants(permissions,slow=True)
                if config_path is None:raise ValueError("canary_config_required")
            from rush.engines import ENGINES
            from rush.io.physical_paths import PhysicalRoot
            if scope=="history" and not (path/".git").exists():
                raise ValueError("history_requires_repository")
            args=["--scope",scope];digest=None
            if config_path is not None:
                _,digest=_validated_secret_config(target,config_path,challenge=challenge_detection)
                args+=["--config",str(PhysicalRoot(target).open_contained(config_path))]
            before=source_manifest(target) if record_result or prior_result_id is not None else None
            result=run_engine(ENGINES["gitleaks"],path,args,tool_name="secrets")
            metadata=result.setdefault("metadata",{})
            metadata["config_sha256"]=digest
            metadata["scope"]={"version":1,"kind":"files","logical_root":str(logical),
                "requested_targets":[str(path)],"scan_kind":scope,"selected_file_filter":False,
                "consumed_file_count":None,"coverage":"unavailable","reason":"engine_discovers_directory_or_history"}
            if before is not None:
                metadata["secret_history"]=source_bound_history(target,result,before_manifest=before,
                    prior_result_id=prior_result_id,record_result=record_result,permissions=permissions)
            if challenge_detection:
                trial=run_detection_challenge(target,challenge_rule=challenge_rule,config_path=config_path,permissions=permissions)
                metadata["detection_challenge"]=trial
                if trial["status"]=="failed" and result["status"]=="ok":result["status"]="warn"
            return result
        except (OSError,ValueError,TypeError,RuntimeError,TimeoutExpired,SubprocessCancelled,ContainmentError) as error:
            return _operation_error(self.name,error)
    
~~~

### Literal transport and configuration edits
In src/rush/catalog.py preserve this command's existing ToolSpec and set exact `option_specs=()`. ToolOptionSpec declarations are intentionally an empty tuple: all operation options are request-only, so adding config declarations would contradict the grant and runtime-input contract. This is explicit configuration exclusion, not an unspecified tuple. Existing canonical table remains `[tools.secrets]`; `docs/CONFIGURATION.md` and `examples/rush.toml` retain an empty table with comment `# Operation arguments and grants are supplied per invocation.` No config can choose an executable/image or silently request a trial.

Insert this literal entry into existing src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS; preserve all other entries:
~~~python
_TOOL_CLI_OPTIONS["secrets"]=(
    click.Option(["--scope"],type=click.Choice(["history","working_tree"]),default="history"),
    click.Option(["--config-path"],type=click.Path(dir_okay=False),default=None),
    click.Option(["--prior-result-id"],type=str,default=None),
    click.Option(["--record-result"],is_flag=True,default=False),
    click.Option(["--challenge-detection"],is_flag=True,default=False),
    click.Option(["--challenge-rule"],type=click.Choice(["generic-api-key","aws-access-token"]),default="generic-api-key"),
)
~~~

MCP _CWD_RELATIVE_ARGS: keep all listed secrets secondary operands out of cwd anchoring; class resolves them against selected logical target except approved absolute runtime binary. Absolute contained output_path remains accepted. `project` remains wrapper injection. CLI path flags intentionally retain raw strings for identical root-relative semantics; no abspath callback. MCP exact property/default inventory:
~~~json
{
  "scope": {
    "type": "str",
    "default": "\"history\""
  },
  "config_path": {
    "type": "str | None",
    "default": "None"
  },
  "prior_result_id": {
    "type": "str | None",
    "default": "None"
  },
  "record_result": {
    "type": "bool",
    "default": "False"
  },
  "challenge_detection": {
    "type": "bool",
    "default": "False"
  },
  "challenge_rule": {
    "type": "str",
    "default": "\"generic-api-key\""
  }
}
~~~
Shared owner edits exact command rows in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/reference/cli-reference.md, docs/reference/mcp-tool-reference.md, docs/reference/result-reference.md, docs/reference/configuration-reference.md, docs/CONFIGURATION.md and examples/rush.toml. CLI/MCP rows list every option above and defaults; result row includes nested operation evidence described here plus per-engine source/executable/version/scope and exact skipped/error behavior. These are user-facing rows only after executable route passes. Update tests/fixtures/phase70/cli-outcomes.json touched command cases; tests/test_cli_registry.py and tests/test_mcp.py assert exact reflected parameter names/types/defaults. scripts/sync_docs.py is check-only, not a generator: `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check` and `python -m pytest tests/test_sync_docs.py -q`.

### Command-specific requested baseline applicability
Specialist receives redacted rule/path/fingerprint and may suggest remediation; secret values, Match, raw reports and scanner config never enter a model prompt. Voice reads rule/path and canary passed/failed only, never token text. Companion shows historical recurrence only when source and scanner identities match; changed or incomplete scans cannot produce a clean assurance badge.

### Additional literal adapter and genuine runtime acceptance
In src/rush/engines/gitleaks.py replace run/child_env with these method bodies (class indentation). At start of T1 normalize, handle `raw.get('summary') in {'engine_missing','incompatible_engine'}` by returning existing skipped_result(tool_name,self.name,raw['summary'],metadata={'reason':raw['summary']}); all other raw results use complete T1 parser unchanged. ownership_kwargs is already imported by this adapter from .base in current source.
~~~python
def child_env(self):
    import os
    keys=("PATH","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT","TEMP","TMP")
    return {key:os.environ[key] for key in keys if key in os.environ}


def run(self,path,args,cwd=None,*,owner_instance_id=None,run_id=None):
    from rush.runtime.binaries import resolve_binary
    from rush.runtime.subprocesses import run_subprocess
    from rush.engines.base import EngineResult,ownership_kwargs
    if len(args) not in {2,4} or args[:1]!=["--scope"] or args[1] not in {"history","working_tree"}:
        raise ValueError("invalid_gitleaks_arguments")
    if len(args)==4 and args[2]!="--config":
        raise ValueError("invalid_gitleaks_arguments")
    binary=resolve_binary(self.binary,project_root=path)
    if binary is None:return EngineResult(summary="engine_missing",exit_code=0,stdout="[]",stderr="")
    command="git" if args[1]=="history" else "dir"
    help_result=run_subprocess([binary,command,"--help"],timeout=10,env=self.child_env(),
        **ownership_kwargs(owner_instance_id,run_id))
    if help_result.returncode or any(flag not in help_result.stdout for flag in
            ("--report-format","--report-path","--redact")):
        return EngineResult(summary="incompatible_engine",exit_code=0,stdout="[]",stderr="")
    config=args[2:] if len(args)==4 else []
    proc=run_subprocess([binary,command,str(path),"--report-format","json","--report-path",
        "-","--no-banner","--redact=100",*config],cwd=cwd,timeout=120,env=self.child_env(),
        **ownership_kwargs(owner_instance_id,run_id))
    return EngineResult(exit_code=proc.returncode,stdout=proc.stdout,stderr=proc.stderr)
~~~

These proposed tests require preinstalled real engines and explicit runtime pins; failure to supply them is a failed acceptance prerequisite, not a successful skip. No installation/download is performed by tests.
~~~python
def test_real_gitleaks_and_canary(tmp_path):
    import json
    from rush.tools.secrets import SecretsTool,challenge_detection
    from rush.runtime.binaries import resolve_binary
    from rush.permissions import ExecutionPermissions
    assert resolve_binary("gitleaks",project_root=tmp_path),"preinstalled Gitleaks required"
    config=tmp_path/"gitleaks.toml"
    config.write_text('[[rules]]\nid="generic-api-key"\ndescription="Synthetic fixture"\nregex="rush-canary-[0-9a-f]{48}"\n')
    token="rush-canary-"+"a"*48
    (tmp_path/"app.env").write_text("API_KEY="+token+"\n")
    result=SecretsTool().run(tmp_path,scope="working_tree",config_path="gitleaks.toml")
    assert result["status"]=="fail"
    assert [(f["path"],f["line"],f["rule"]) for f in result["findings"]]==[
        (str(tmp_path/"app.env"),1,"generic-api-key")]
    assert token not in json.dumps(result)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    trial=challenge_detection(tmp_path,challenge_rule="generic-api-key",config_path="gitleaks.toml",
        permissions=ExecutionPermissions(slow=True))
    assert trial["status"]=="passed" and trial["detected"] is True and trial["redacted"] is True
    assert trial["engine_version"]
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before
    config.write_text('[[rules]]\nid="different-rule"\ndescription="Synthetic miss"\nregex="never-match-fixture-xyz"\n')
    missed=challenge_detection(tmp_path,challenge_rule="generic-api-key",config_path="gitleaks.toml",
        permissions=ExecutionPermissions(slow=True))
    assert missed["status"]=="failed" and missed["detected"] is False
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

def test_secrets_granted_optional_foreign_stdio(tmp_path):
    import json,subprocess
    root,foreign,registry,project,env,python=_registered_transport_fixture(tmp_path)
    (root/"gitleaks.toml").write_text('[[rules]]\nid="generic-api-key"\ndescription="Synthetic fixture"\nregex="rush-canary-[0-9a-f]{48}"\n')
    (root/"app.py").write_text("answer=42\n")
    flags=["--scope","working_tree","--config-path","gitleaks.toml","--record-result",
        "--challenge-detection","--challenge-rule","generic-api-key","--allow-cache-write","--allow-slow"]
    cli=subprocess.run([python,"-m","rush","secrets",str(root),*flags,"--json"],
        cwd=foreign,env=env,capture_output=True,text=True,timeout=180)
    left=json.loads(cli.stdout)
    right=exchange_stdio(python,foreign,env,"rush_secrets",{"path":".","project":project,
        "scope":"working_tree","config_path":"gitleaks.toml","record_result":True,
        "challenge_detection":True,"challenge_rule":"generic-api-key","allow_cache_write":True,
        "allow_slow":True},registry_root=registry)
    for result in (left,right):
        _assert_engine_identities(result,["gitleaks"])
        assert result["status"]=="ok"
        assert result["metadata"]["detection_challenge"]["status"]=="passed"
        assert result["metadata"]["secret_history"]["current_fingerprints"]==[]
    assert left["metadata"]["secret_history"]==right["metadata"]["secret_history"]
    assert left["metadata"]["detection_challenge"]["config_digest"]==right["metadata"]["detection_challenge"]["config_digest"]
    assert left["findings"]==right["findings"]==[]
    assert not (foreign/".rush").exists()
~~~

Complete missing-engine shared-dispatch regression (current resolver injection is verified tools.common.engine_on_path); result is not fabricated:
~~~python
def test_secrets_missing_engine_no_process(tmp_path):
    from unittest.mock import patch
    from rush.tools.secrets import SecretsTool
    from rush.permissions import ExecutionPermissions
    (tmp_path/"app.py").write_text("x=1\n")
    with patch("rush.tools.common.engine_on_path",return_value=False), patch("rush.runtime.subprocesses.run_subprocess") as process:
        result=SecretsTool().run(tmp_path, scope="working_tree")
    assert result["status"]=="skipped"
    assert result["findings"]==[]
    assert all(row["status"]=="skipped" for row in result["metadata"]["engines"])
    process.assert_not_called()
~~~

~~~python
def test_secrets_malformed_engine_report_is_error(tmp_path):
    from rush.engines import ENGINES
    (tmp_path/"app.py").write_text("x=1\n")
    for name in ["gitleaks"]:
        result=ENGINES[name].normalize({"exit_code":0,"stdout":"[not-json","stderr":""},tmp_path,"secrets")
        assert result["status"]=="error"
        assert result["findings"]==[]
~~~

Literal root-anchor integration, Batch integration owner, src/rush/mcp_support/tool_registry.py::_CWD_RELATIVE_ARGS (retain every other entry):

~~~python
_CWD_RELATIVE_ARGS["secrets"] = ()
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

Exact displayed first-RED receipt: extracted the first complete test body from this document and executed against SOURCE 66c6c799eaa5b6017776d659e9e0de2b4a8878a5 with Python 3.12.12, offline uv, cleared PYTHONPATH, and TemporaryDirectory fixture. `test_exit_one_empty_is_error`: AssertionError at displayed code line 10; current exit 1 with empty findings normalized to `ok`. No interface/import/fixture error preceded the assertion. Future-interface tests below remain unexecuted proposals.

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

### Complete command-specific CLI and stdio test

Save following body in existing tests/test_mcp.py beside exchange_stdio defined above. All engine doubles are actual local executables, outside project; no tool/resolver/transport stubs. Fixture asserts actual engine call receipt for each transport. It is POSIX executable-fixture acceptance; Windows requires equivalent .cmd launcher fixture and remains independently tested by existing transport suite.

~~~python
def test_q17_secrets_cli_and_initialized_stdio(tmp_path):
    import json, os, subprocess, sys
    from pathlib import Path
    root=tmp_path/"project"; root.mkdir()
    (root/"rush.toml").write_text("[tools.secrets]\n")
    (root/"app.py").write_text("safe = True\n")
    bindir=tmp_path/"bin"; bindir.mkdir()
    log=tmp_path/"engine-calls.jsonl"
    scripts={"gitleaks": "print('[]')"}
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
    argv=[sys.executable,"-m","rush","secrets",str(root),*["--scope","working_tree","--no-cache"],"--json"]
    cli=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert cli.returncode==0,cli.stderr
    left=json.loads(cli.stdout)
    pass
    right=exchange_stdio(sys.executable,root,env,"rush_secrets",{"path":str(root),"scope":"working_tree","no_cache":True})
    assert left["tool"]==right["tool"]=="secrets"
    assert left["status"]==right["status"]=="ok"
    assert left["findings"]==right["findings"]==[]
    assert left["metadata"]["scope"]["scan_kind"]==right["metadata"]["scope"]["scan_kind"]=="working_tree"
    records=[json.loads(line) for line in log.read_text().splitlines()]
    records=[row for row in records if "--version" not in row[1] and "--help" not in row[1]]
    assert [row[0] for row in records]==["gitleaks","gitleaks"]
    assert all("Secret" not in json.dumps(value) for value in (left,right))
    before_dirs=sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir())
    before={p.relative_to(root).as_posix():p.read_bytes()
            for p in root.rglob("*") if p.is_file()}
    log_before=log.read_bytes()
    denied_cli=subprocess.run([sys.executable,"-m","rush","secrets",str(root),
        *["--scope","working_tree","--record-result","--no-cache"],"--json"],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    denied_left=json.loads(denied_cli.stdout)
    denied_right=exchange_stdio(sys.executable,root,env,"rush_secrets",{"path":str(root),"scope":"working_tree","record_result":True,"no_cache":True})
    assert denied_cli.returncode==0,denied_cli.stderr
    assert denied_left["status"]==denied_right["status"]=="skipped"
    assert log.read_bytes()==log_before
    invalid=exchange_stdio(sys.executable,root,env,"rush_secrets",{
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

Use actual subprocess CLI and initialized JSON-RPC stdio. Complete tests/test_mcp.py::test_q17_secrets_cli_and_initialized_stdio body above supplies literal command, fixture, fields and denial assertions. Shared exchange_stdio helper below is defined once by Batch integration owner. Add tests/test_cli_registry.py::test_q17_secrets_cli_options for all explicit flags, invalid enums, missing/empty/staged cases. Actual engine fixture logs every call including --version; genuine-engine acceptance remains separate.

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
        expected={"scope":(["string"],"history"),
            "config_path":(["string","null"],None),
            "prior_result_id":(["string","null"],None),
            "record_result":(["boolean"],False),
            "challenge_detection":(["boolean"],False),
            "challenge_rule":(["string"],"generic-api-key")}
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

Transport fixture executable gitleaks outside project: --version fixture-1, git/dir invocation appends argv log and prints [] exit0. Project rush.toml=[tools.secrets], config TOML self-contained. Actual CLI secrets ROOT --scope working_tree --json --no-cache versus initialized rush_secrets(path=ROOT,scope="working_tree",no_cache=true): exact status ok, findings[], scan_kind working_tree, no raw, engine status/cwd match. Denied --record-result without --allow-cache-write must produce skipped/not_run before even scanner version and leave tree byte-identical. Granted persistence reaches source_bound_history and both transports produce same deterministic result_id on same root/source/config/engine. Token fixture variant must return fail through both with token absent from all JSON/stderr/artifact bytes.

Live tests/test_secrets.py::test_real_gitleaks_working_tree uses explicitly supplied local binary and custom fake-only rule; requires exact rule/path/line and failure status. Source ENGINE_PACKAGES policy latest_stable contains no numeric version floor; capability help probes must show git/dir/report-format/report-path/redact before acceptance. Planning observed no Gitleaks installed; no install/network performed.

Run rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_secrets.py tests/test_supply_chain_tools.py tests/test_cli_registry.py tests/test_mcp.py -q plus common Phase70/ruff commands.

Development-ready entry: current normalizer RED observed and T1 fix concrete, T2 repair contract resolved, full file ownership/transport/secret-handling/recovery specified. T3 ordinary extension and T4 distinct proposal remain separately unapproved. Future PR order T1, T2 integration, then independently authorized T3/T4; no PR created. Real binary absence blocks future live acceptance only. No production completion claimed.
