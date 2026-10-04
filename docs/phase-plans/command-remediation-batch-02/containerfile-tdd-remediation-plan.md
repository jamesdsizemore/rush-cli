# Q15 — containerfile TDD remediation development plan

Goal: discover ordinary container source names and report exact assessed files; preserve Phase70 Hadolint/parser/transport guarantees. Scope includes complete audit Q15 lines 5421–5796, image-context extension assessment and separate repeat-build proposal. No production changes made.

## Requirement ledger

| Requirement/category | Current evidence | Exact proposed change / acceptance |
|---|---|---|
| Repair: ordinary filenames | ContainerfileTool src/rush/tools/containerfile.py:6–13 inherits suffix-only ContentTool; collect_files routing.py:438–475 | T1 selects Dockerfile, Containerfile, Dockerfile.*, Containerfile.*; one Hadolint invocation per selected file; exact assessed_files |
| Repair: selected file and staged scope | HadolintEngine.run :27–56 ignores args but honors path | Pass actual selected file as path; never directory; T1 file/staged/changed test |
| Preserve implemented parser | engines/hadolint.py:57–85 validates JSON/exit agreement; owned empty config and sanitized environment exist | Preserve tests/test_hadolint_reference.py; no duplicate adapter rewrite |
| Preserve already fixed aggregation | routing.py:478–612 preserves child engines; mixed status fixed | Reuse aggregate_results; add factual versioned file scope, no nested duplicate full children |
| Ordinary extension, proposed/unapproved | No literal_stages exists | T2 image_context parses literal FROM and records digest/stage/source; no build on parse |
| Distinct expansion, proposed/unapproved | No repeat-build operation exists | T4 runs two explicitly granted local Docker builds, exports/tar-compares files/config; no push or cross-builder claim |
| Baseline provisioning/model/voice/companion | Shared baseline described below | Preserve grants/redaction and factual scanner outputs; not counted as innovation |

## Evidence and first executable task

2026-10-01 safe source-bound reproduction executed through current ContainerfileTool.run(root): root contained Dockerfile with FROM scratch. Controlled run_engine returned canonical ok if called. Observed status skipped, engine_calls=0; assertion status==ok failed. No invented keyword or missing-engine crash. Python3.12.12, uv offline. Hadolint is not installed in inspected environment; real engine acceptance below remains unexecuted.

Implement exact container source selection in rush-cli. Read source AGENTS.md, Phase70 T8/T9/T16 and this packet; user references listed below binding.

# Feature: T1 — container source names reach Hadolint once

## Required behavior

path: Path required; existing __call__(path) and run(path,*,config=None) remain valid. Direct missing path returns error; empty existing directory skipped with version1 files coverage none and no_supported_targets. Select case-sensitive Dockerfile/Containerfile plus nonempty dotted suffix variants. Preserve exclusion of hidden/generated directories from routing._SKIP_DIRS. Reject symlink source or escaping path through PhysicalRoot before scan. Existing Dockerfile file target must not widen to siblings; staged route must pass staged bytes while user-facing scope uses logical names.

Canonical ToolResult keeps tool/engine/engine_version/status/duration_ms/summary/findings/raw. Add metadata.scope version1,kind=files,logical_root,requested_targets,assessed_files,matched_file_count,consumed_file_count,coverage and reason. assessed_files are actual successfully invoked input paths, not discovery guesses. Missing/error child makes coverage partial/none; genuine parser findings still complete analysis. Per-engine metadata stays intact. For absent engines no assessed_files and consumed_file_count=0.

## Deliverables

Command owner: src/rush/tools/containerfile.py::ContainerfileTool.run and new tests/test_containerfile.py. Existing src/rush/engines/hadolint.py remains unchanged. Shared integration owner: command descriptions/config/reference/transport paths explicitly listed below.

Runnable first RED, proposed tests/test_containerfile.py:
~~~python
from pathlib import Path
from unittest.mock import patch
from rush.tools.containerfile import ContainerfileTool

def test_standard_names_and_exact_inputs(tmp_path):
    for name in ("Dockerfile", "Containerfile", "Dockerfile.dev", "README"):
        (tmp_path / name).write_text("FROM scratch\n")
    selected = []
    def child(engine, path, args, **kwargs):
        selected.append(path.name)
        return dict(tool="containerfile", engine="hadolint",
            engine_version="fixture", status="ok", duration_ms=0,
            summary="clean", findings=[], raw=None)
    with patch("rush.tools.content.run_engine", side_effect=child), \
         patch("rush.tools.common.run_engine", side_effect=child), \
         patch("rush.tools.containerfile.run_engine", side_effect=child, create=True):
        result = ContainerfileTool().run(tmp_path)
    assert selected == ["Containerfile", "Dockerfile", "Dockerfile.dev"]
    assert result["status"] == "ok"
    assert result["metadata"]["scope"]["assessed_files"] == [
        str(tmp_path / n) for n in selected]
~~~

Minimum GREEN core, replace inherited run with this explicit discovery/dispatch in containerfile.py; surrounding result error/scope branches are required below:
~~~python
from pathlib import Path
from rush.io.physical_paths import PhysicalRoot
from rush.invocation.executor import current_execution_root, current_invocation_root
from rush.tools.common import run_engine
from rush.tools.routing import _SKIP_DIRS, aggregate_results
from rush.engines import ENGINES

def selected_containerfiles(path: Path) -> list[Path]:
    root = current_execution_root() or (path if path.is_dir() else path.parent)
    physical = PhysicalRoot(root)
    candidates = [path] if path.is_file() else path.rglob("*")
    selected = []
    for item in candidates:
        relative = item.relative_to(root)
        if any(p in _SKIP_DIRS or p.startswith(".") for p in relative.parts[:-1]):
            continue
        name = item.name
        if name not in {"Dockerfile", "Containerfile"} and not (
            name.startswith(("Dockerfile.", "Containerfile.")) and not name.endswith(".")
        ):
            continue
        checked = physical.open_contained(relative)
        if checked.is_file():
            selected.append(checked)
    return sorted(set(selected))

def run_selected(path: Path):
    files = selected_containerfiles(path)
    children = [run_engine(ENGINES["hadolint"], f, [], tool_name="containerfile",
                           consumed_paths=[str(f)]) for f in files]
    result = aggregate_results("containerfile", children)
    execution = current_execution_root() or (path if path.is_dir() else path.parent)
    logical = current_invocation_root() or execution
    assessed = [f for f, child in zip(files, children, strict=True)
                if child["status"] not in {"skipped", "error"}]
    coverage = "complete" if assessed and len(assessed) == len(files) else (
        "partial" if assessed else "none")
    result["metadata"]["scope"] = {
        "version": 1, "kind": "files", "logical_root": str(logical),
        "requested_targets": [str(path.relative_to(execution))],
        "assessed_files": [str(logical / f.relative_to(execution)) for f in assessed],
        "matched_file_count": len(files), "consumed_file_count": len(assessed),
        "coverage": coverage,
        "reason": None if coverage == "complete" else (
            "no_supported_targets" if not files else "incomplete_engine_execution")}
    return result
~~~
These two functions live in same command module and ContainerfileTool.run invokes run_selected after validating path exists. Catch only OSError/ContainmentError/ValueError into error_result with sanitized fixed summary; no raw source contents. Empty result remains skipped; aggregate already controls status. Preserve actual child metadata and version facts.

Regression/refactor: test_file_and_staged_target asserts only Dockerfile.dev and staged FROM bytes; test_excluded_and_symlink_sources asserts generated/hidden exclusions, symlink error before scanner; test_missing_hadolint records skipped/no consumed files; test_error_plus_skip_preserves_error asserts error precedence and two engine entries. No extraction into generic discovery framework.

## Constraints

No formatter, build, network, registry contact, memory write or setup during normal lint. Existing Hadolint config policy cannot be replaced by project auto-config. Scope uses actual dispatch; no directory scan claim.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_containerfile.py::test_standard_names_and_exact_inputs tests/test_containerfile.py::test_file_and_staged_target tests/test_hadolint_reference.py -q

## Completion

All four basename patterns and exact file/staged dispatch behave as specified; source parser guarantees remain; only literal files in packet/shared ownership map changed.

# Feature: T2 — literal image context (ordinary extension, proposed)

## Required behavior

New request image_context: bool=False; CLI --image-context. New ContainerfileTool.__call__(path,*,image_context=False,compare_builds=False,build_context:Path|None=None,docker_binary:str|None=None,allow_network=False,allow_download=False,allow_cache_write=False,allow_build=False,allow_slow=False,allow_artifact_write=False). Explicit strict type checks before effects. run accepts same operation options plus config=None/permissions=None. Default unchanged.

literal_stages(root,files)->list[dict] reads ≤1MiB each, max1000 files, UTF-8 strictly; source SHA256 exact bytes. Parse logical backslash continuations with start line; shlex tokens only for FROM instructions, skip comments/non-FROM entirely. Reject backtick escape, malformed FROM, duplicate case-insensitive stage alias, dangling continuation; report unresolved variable bases as literal/unresolved, never resolve ARG or contact registry. FROM [--platform=X] BASE [AS NAME]; stage ordinal resets per file. Internal alias references compare case-insensitively; scratch external=false. Fields file(relative logical),line,stage,base_reference,platform,external,source_digest,resolution=literal|unresolved. More complex syntax produces explicit error, not invented resolved image.

Before: lint has no base relation evidence. After FROM python:3.12 AS build / FROM build AS final gives two records, second external=false, zero image builds. This is ordinary Dockerfile parsing, not claimed innovation.

## Deliverables

Command owner adds literal_stages in src/rush/tools/containerfile.py; tests/test_containerfile.py::test_multistage_context and ::test_stage_parser_rejects_unsupported. Shared owner adds literal click.Option(["--image-context"],is_flag=True,default=False) and relevant reference/schema rows.

## Constraints

No build/security/SBOM auto-chaining. Parse-only requires no effect grants. Return bounded exact evidence, not truncated false completeness.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_containerfile.py::test_multistage_context tests/test_containerfile.py::test_stage_parser_rejects_unsupported -q

## Completion

Exact stage/source identities returned through CLI/MCP and no child beyond Hadolint; remains proposed until separately authorized.

# Feature: T4 — two-build repeatability evidence (distinct proposal, unapproved)

## Required behavior

compare_builds=False, build_context=None, docker_binary=None; CLI --compare-builds --build-context PATH --docker-binary PATH. Requires exactly one selected Dockerfile and all six grants network/download/cache_write/build/slow/artifact_write before runtime or scratch. Explicit Docker path must absolute executable. Build context physically contained in logical project; every included source symlink rejected. All external FROM bases require SHA256 digest pins, unresolved variables rejected. Unlike P0 offline launcher, Docker build daemon may contact registry even with --pull=false; --network=none constrains RUN only. No isolation claim for daemon builds.

Define repeat_image_build(root,dockerfile,*,docker_binary,permissions)->dict in command module. Complete algorithm: hash sorted full context (excluding .git/.rush), copy twice into owned temporary contexts, verify equal inventories; validate pins; for each invoke existing run_subprocess([docker,"build","--no-cache","--pull=false","--network=none","--iidfile",iid,"-f",copied_dockerfile,context],timeout=600). Require fresh IID sha256:64hex; inspect one image; reject Config.Volumes because export omits volume contents. Create never-started container with --network=none --entrypoint /__rush_never_started; validate owned returned ID; export tar into owned scratch timeout180. Stream tar entries without extraction; reject absolute/traversal/duplicate paths, unknown entry types and >1GiB archive/100000 entries. Compare keyed type/mode/uid/gid/link/contentSHA256, Config/Os/Architecture; ignore timestamps only. Do not drop device metadata: block char/block devices as unsupported. Finally remove only newly created container IDs with checked return, preserve images (content IDs may be shared). Return retained image IDs for explicit user cleanup. Rehash original context before returning; drift => error no repeatability claim.

Return metadata.build_repeatability={status:divergent|repeatable_on_this_builder,images:[id,id],source_digest,changed_count,changed_paths:first100,configuration_changed,normalization:"ignore timestamps; compare content/type/mode/owner/link",cross_builder_reproducibility_proven:false}. Divergent => fail unless error already; absent approved runtime => incomplete warn with trial skipped and lint retained; launched failures => error. Timeout cleanup failure => error with owned identity; never silently pass.

## Deliverables

Same command module repeat_image_build; tests/test_containerfile.py::test_repeat_build_detects_nondeterministic_file, ::test_repeat_build_denied_zero_effects, ::test_build_cleanup_and_source_drift. Fixtures built within tmp_path: Dockerfile FROM scratch plus COPY payload /payload, payload bytes alpha. Controlled Docker boundary writes actual tar bytes alpha then beta; expect changed_paths=["payload"], source unchanged. Real Docker node runs exact pinned source twice; deterministic fixture expects repeatable_on_this_builder; nondeterministic RUN fixture requires approved base image and must detect changing /payload. T1 never waits for this unapproved expansion.

## Constraints

No push, tag, image deletion by shared digest, live source mutation, cross-builder guarantee or implicit approval. No shell command strings. Record exact local Docker version/runtime grants. Agent value is evidence against candidate reproducibility assumption; commodity build remains underlying mechanism.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_containerfile.py::test_repeat_build_detects_nondeterministic_file tests/test_containerfile.py::test_repeat_build_denied_zero_effects tests/test_containerfile.py::test_build_cleanup_and_source_drift -q

## Completion

Two real builds and exported actual-byte comparison pass required fixture, source stable and own containers cleaned; no proposal approval inferred from this plan.

### Runnable image-context and two-build acceptance

Proposed additions to tests/test_containerfile.py; future interface absence is separate from T1 RED.
~~~python
def test_multistage_context(tmp_path):
    from rush.tools.containerfile import literal_stages
    file=tmp_path/"Dockerfile"
    file.write_text("FROM scratch AS base\nFROM base AS final\n")
    rows=literal_stages(tmp_path,[file])
    assert len(rows)==2
    assert [(x["stage"],x["base_reference"],x["external"],x["line"]) for x in rows]==[
        ("base","scratch",False,1),("final","base",False,2)]
    assert rows[0]["source_digest"]==rows[1]["source_digest"]

def test_repeat_build_detects_nondeterministic_file(tmp_path):
    import io,json,subprocess,tarfile
    from pathlib import Path
    from unittest.mock import patch
    from rush.tools.containerfile import repeat_image_build
    from rush.permissions import ExecutionPermissions
    root=tmp_path/"source"; root.mkdir()
    (root/"Dockerfile").write_text("FROM scratch\n")
    runtime=tmp_path/"docker"; runtime.write_text("#!/bin/sh\nexit 0\n"); runtime.chmod(0o700)
    build=-1; removed=[];live={}
    def child(argv,**kwargs):
        nonlocal build
        output=""
        if argv[1]=="version":
            output="27.0.0"
        elif argv[1]=="build":
            build+=1
            Path(argv[argv.index("--iidfile")+1]).write_text("sha256:"+str(build+1)*64)
        elif argv[1:3]==["image","inspect"]:
            output=json.dumps([{"Config":{},"Os":"linux","Architecture":"arm64"}])
        elif argv[1]=="create":
            output=str(build+3)*64
            name=argv[argv.index("--name")+1]
            token=argv[argv.index("--label")+1].split("=",1)[1]
            live[name]={"Id":output,"Config":{"Labels":{"io.rush.invocation":token}}}
        elif argv[1:3]==["container","inspect"]:
            if argv[-1] not in live:
                return subprocess.CompletedProcess(argv,1,"","No such container")
            output=json.dumps([live[argv[-1]]])
        elif argv[1]=="export":
            with tarfile.open(argv[argv.index("--output")+1],"w") as archive:
                payload=("port="+str(8000+build)).encode()
                item=tarfile.TarInfo("app/config"); item.size=len(payload); item.mode=0o644
                archive.addfile(item,io.BytesIO(payload))
        elif argv[1]=="rm":
            removed.append(argv[-1])
            live.pop(next(name for name,row in live.items() if row["Id"]==argv[-1]))
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv,0,output,"")
    grants=ExecutionPermissions(network=True,download=True,cache_write=True,
                                build=True,slow=True,artifact_write=True)
    with patch("rush.runtime.subprocesses.run_subprocess",side_effect=child):
        result=repeat_image_build(root,"Dockerfile",docker_binary=str(runtime),
                                  permissions=grants)
    assert result["status"]=="divergent"
    assert result["changed_paths"]==["app/config"]
    assert result["changed_count"]==1
    assert result["cross_builder_reproducibility_proven"] is False
    assert removed==["3"*64,"4"*64]
    assert (root/"Dockerfile").read_text()=="FROM scratch\n"
~~~
Docker helper imports run_subprocess inside helper so patch targets actual process boundary. This exercises full two-build controller and actual TAR bytes, not genuine Docker execution. Genuine engine/runtime acceptance remains separate.


## Complete implementation and route packet — review corrections

These literal bodies implement earlier algorithms; they are proposed replacements in the future implementation checkout, not code installed during planning. Preserve existing imports/helpers not replaced. Every helper below has its exact caller in the full class replacement; no hidden dispatcher or second runtime. Command owner owns command-local definitions; Batch integration owner owns catalog/CLI/MCP/reference changes. Request-only options cannot be activated by project configuration.

### Complete command-local controllers
Insert these module-level bodies in src/rush/tools/containerfile.py; replace earlier pseudocode descriptions, preserve T1 existing repair/parser.
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

def literal_stages(root,files):
    import hashlib,shlex
    from pathlib import Path
    from rush.workflows.projects import open_contained_file
    import os
    if len(files)>1000:
        raise ValueError("containerfile_limit")
    stages=[]
    for file in files:
        relative=Path(file).relative_to(root) if Path(file).is_absolute() else Path(file)
        fd=open_contained_file(root,relative.as_posix())
        try:
            with os.fdopen(fd,"rb",closefd=False) as stream:
                raw=stream.read(1024*1024+1)
        finally:
            os.close(fd)
        if len(raw)>1024*1024:
            raise ValueError("containerfile_too_large")
        digest=hashlib.sha256(raw).hexdigest();aliases=set();pending="";start=1;ordinal=0
        for number,line in enumerate(raw.decode("utf-8").splitlines(),1):
            text=line.strip()
            if text.lower().startswith("# escape=") and not text.endswith("\\"):
                raise ValueError("unsupported_escape")
            if not pending and (not text or text.startswith("#")):
                continue
            if not pending:
                start=number
            pending+=text[:-1]+" " if text.endswith("\\") else text
            if text.endswith("\\"):
                continue
            logical=pending;pending=""
            if logical.split(None,1)[0].upper()!="FROM":
                continue
            words=shlex.split(logical);words.pop(0);platform=None
            if words and words[0].startswith("--platform="):
                platform=words.pop(0).split("=",1)[1]
                if not platform:
                    raise ValueError("malformed_FROM")
            if len(words) not in {1,3} or (len(words)==3 and words[1].upper()!="AS"):
                raise ValueError("malformed_FROM")
            base=words[0];external=base.lower() not in aliases and base.lower()!="scratch"
            if len(words)==3:
                alias=words[2].lower()
                if not alias or alias in aliases:
                    raise ValueError("duplicate_stage_alias")
                aliases.add(alias)
            stages.append({"file":relative.as_posix(),"line":start,"stage":ordinal,
                "base_reference":base,"platform":platform,"external":external,
                "source_digest":digest,"resolution":"unresolved" if "$" in base else "literal"})
            ordinal+=1
        if pending:
            raise ValueError("dangling_continuation")
    return stages


def _tar_inventory(path):
    import hashlib,tarfile
    from pathlib import PurePosixPath
    if path.stat().st_size>1024**3:
        raise ValueError("archive_limit")
    rows={}
    with tarfile.open(path,"r|*") as archive:
        for item in archive:
            name=PurePosixPath(item.name)
            if name.is_absolute() or ".." in name.parts or item.name in rows or len(rows)>=100000:
                raise ValueError("unsafe_archive")
            if not (item.isfile() or item.isdir() or item.issym() or item.islnk()):
                raise ValueError("unsupported_archive_entry")
            digest=None
            if item.isfile():
                stream=archive.extractfile(item)
                if stream is None:
                    raise ValueError("missing_archive_content")
                hasher=hashlib.sha256()
                while block:=stream.read(1024*1024):
                    hasher.update(block)
                digest=hasher.hexdigest()
            rows[item.name]=(item.type.decode("ascii"),item.mode,item.uid,item.gid,item.linkname,digest)
    return rows


def repeat_image_build(root,dockerfile,*,docker_binary,permissions):
    import json,os,re,shutil,tempfile,uuid
    from pathlib import Path
    from rush.permissions import ExecutionPermissions,check_permissions
    from rush.runtime.subprocesses import run_subprocess
    allowed,missing=check_permissions(ExecutionPermissions(network=True,download=True,
        cache_write=True,build=True,slow=True,artifact_write=True),permissions)
    if not allowed:
        raise PermissionError(", ".join(missing))
    root=Path(root);docker=Path(docker_binary)
    if not docker.is_absolute() or not docker.is_file() or not os.access(docker,os.X_OK):
        raise ValueError("docker_unavailable")
    before=source_manifest(root)
    relative=Path(dockerfile).relative_to(root) if Path(dockerfile).is_absolute() else Path(dockerfile)
    stages=literal_stages(root,[root/relative])
    if not stages or any(row["resolution"]!="literal" or
            (row["external"] and not re.search(r"@sha256:[0-9a-f]{64}$",row["base_reference"])) for row in stages):
        raise ValueError("unpinned_build_base")
    def child(args,timeout=180,cleanup=False):
        result=run_subprocess([str(docker),*args],timeout=timeout,
            **({"cancel_check":lambda:False} if cleanup else {}))
        if result.returncode:
            raise ValueError("docker_phase_failed:"+args[0])
        return result
    version=child(["version","--format","{{.Server.Version}}"],30).stdout.strip()
    if not version:
        raise ValueError("docker_version_missing")
    images=[];inventories=[];configs=[]
    with tempfile.TemporaryDirectory(prefix="rush-build-") as folder:
        work=Path(folder)
        for index in range(2):
            context=work/f"context-{index}";context.mkdir()
            _copy_snapshot(root,context,before)
            if source_manifest(context)!=before:
                raise ValueError("context_copy_changed")
            iid=work/f"image-{index}.id"
            child(["build","--no-cache","--pull=false","--network=none","--iidfile",str(iid),
                   "-f",str(context/relative),str(context)],600)
            image=iid.read_text().strip()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}",image):
                raise ValueError("image_id_invalid")
            images.append(image)
            inspection=json.loads(child(["image","inspect",image]).stdout)
            if not isinstance(inspection,list) or len(inspection)!=1:
                raise ValueError("image_inspect_invalid")
            info=inspection[0];config=info.get("Config")
            if not isinstance(config,dict) or config.get("Volumes"):
                raise ValueError("image_volume_unsupported")
            configs.append({key:info.get(key) for key in ("Config","Os","Architecture")})
            token=uuid.uuid4().hex;name="rush-build-"+token
            # Name is known before create so timed-out create cannot leak an unnamed container.
            try:
                created=child(["create","--name",name,"--label","io.rush.invocation="+token,
                    "--network=none","--entrypoint","/__rush_never_started",image]).stdout.strip()
                if not re.fullmatch(r"[0-9a-f]{64}",created):
                    raise ValueError("container_id_invalid")
                tar=work/f"inventory-{index}.tar"
                child(["export","--output",str(tar),created])
                inventories.append(_tar_inventory(tar))
            finally:
                inspected=run_subprocess([str(docker),"container","inspect",name],timeout=30,cancel_check=lambda:False)
                if inspected.returncode==0:
                    rows=json.loads(inspected.stdout)
                    if (not isinstance(rows,list) or len(rows)!=1 or
                            rows[0].get("Config",{}).get("Labels",{}).get("io.rush.invocation")!=token):
                        raise ValueError("container_cleanup_ownership_failed")
                    child(["rm","--force",rows[0]["Id"]],30,True)
                    absent=run_subprocess([str(docker),"container","inspect",name],timeout=30,cancel_check=lambda:False)
                    if absent.returncode==0:
                        raise ValueError("container_cleanup_failed")
                elif "No such" not in inspected.stderr and "not found" not in inspected.stderr:
                    raise ValueError("container_cleanup_unverified")
    if source_manifest(root)!=before:
        raise ValueError("source_changed")
    changed=sorted(name for name in inventories[0].keys()|inventories[1].keys()
                   if inventories[0].get(name)!=inventories[1].get(name))
    config_changed=configs[0]!=configs[1]
    return {"status":"divergent" if changed or config_changed else "repeatable_on_this_builder",
        "images":images,"source_digest":source_digest(before),"changed_count":len(changed),
        "changed_paths":changed[:100],"configuration_changed":config_changed,"docker_version":version,
        "normalization":"ignore timestamps; compare content/type/mode/owner/link",
        "cross_builder_reproducibility_proven":False}
~~~

### Complete callable and method insertion
Module-level utilities below, followed by full ContainerfileTool replacement. Existing ContentTool import is retained for its subclasses. Config is verified existing ToolConfig: any nonempty options fails request_only_options; unknown config keys already fail catalog validation. Pins/effect selections stay explicit request fields. Runtime source and logical destination anchors use existing executor accessors, not process cwd.
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

class ContainerfileTool(ContentTool):
    name="containerfile"
    engine_name="hadolint"
    extensions=("dockerfile","containerfile")
    @property
    def mcp_description(self):
        return "Inspect containerfile using shared local engines; explicit effect grants remain required."

    def __call__(self, path: Path, *,
                 image_context: bool = False,
                 compare_builds: bool = False,
                 build_context: str | None = None,
                 docker_binary: str | None = None,
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
        return self.run(path,image_context=image_context,compare_builds=compare_builds,build_context=build_context,docker_binary=docker_binary,permissions=permissions)
    
    def run(self, path: Path, *,
            image_context: bool = False,
            compare_builds: bool = False,
            build_context: str | None = None,
            docker_binary: str | None = None,
            config=None, permissions=None) -> ToolResult:
        try:
            if config is not None and config.options:
                raise ValueError("request_only_options")
            path,logical,target=_roots(path)
            if type(image_context) is not bool or type(compare_builds) is not bool:
                raise ValueError("invalid_request")
            if compare_builds:
                _require_grants(permissions,network=True,download=True,cache_write=True,build=True,slow=True,artifact_write=True)
            files=selected_containerfiles(path)
            result=run_selected(path)
            if image_context:
                result.setdefault("metadata",{})["image_context"]=literal_stages(path if path.is_dir() else path.parent,files)
            if compare_builds:
                if len(files)!=1 or not build_context or not docker_binary:
                    raise ValueError("one_dockerfile_context_and_runtime_required")
                from rush.io.physical_paths import PhysicalRoot
                context=PhysicalRoot(logical).open_contained(build_context)
                file=target/files[0].relative_to(path if path.is_dir() else path.parent)
                trial=repeat_image_build(context,file.relative_to(context),docker_binary=docker_binary,permissions=permissions)
                result.setdefault("metadata",{})["build_repeatability"]=trial
                if trial["status"]=="divergent" and result["status"]!="error":
                    result["status"]="fail"
            return result
        except (OSError,ValueError,TypeError,RuntimeError,TimeoutExpired,SubprocessCancelled,ContainmentError) as error:
            return _operation_error(self.name,error)
    
~~~

### Literal transport and configuration edits
In src/rush/catalog.py preserve this command's existing ToolSpec and set exact `option_specs=()`. ToolOptionSpec declarations are intentionally an empty tuple: all operation options are request-only, so adding config declarations would contradict the grant and runtime-input contract. This is explicit configuration exclusion, not an unspecified tuple. Existing canonical table remains `[tools.containerfile]`; `docs/CONFIGURATION.md` and `examples/rush.toml` retain an empty table with comment `# Operation arguments and grants are supplied per invocation.` No config can choose an executable/image or silently request a trial.

Insert this literal entry into existing src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS; preserve all other entries:
~~~python
_TOOL_CLI_OPTIONS["containerfile"]=(
    click.Option(["--image-context"],is_flag=True,default=False),
    click.Option(["--compare-builds"],is_flag=True,default=False),
    click.Option(["--build-context"],type=click.Path(),default=None),
    click.Option(["--docker-binary"],type=click.Path(dir_okay=False),default=None),
)
~~~

MCP _CWD_RELATIVE_ARGS: keep all listed containerfile secondary operands out of cwd anchoring; class resolves them against selected logical target except approved absolute runtime binary. Absolute contained output_path remains accepted. `project` remains wrapper injection. CLI path flags intentionally retain raw strings for identical root-relative semantics; no abspath callback. MCP exact property/default inventory:
~~~json
{
  "image_context": {
    "type": "bool",
    "default": "False"
  },
  "compare_builds": {
    "type": "bool",
    "default": "False"
  },
  "build_context": {
    "type": "str | None",
    "default": "None"
  },
  "docker_binary": {
    "type": "str | None",
    "default": "None"
  }
}
~~~
Shared owner edits exact command rows in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/reference/cli-reference.md, docs/reference/mcp-tool-reference.md, docs/reference/result-reference.md, docs/reference/configuration-reference.md, docs/CONFIGURATION.md and examples/rush.toml. CLI/MCP rows list every option above and defaults; result row includes nested operation evidence described here plus per-engine source/executable/version/scope and exact skipped/error behavior. These are user-facing rows only after executable route passes. Update tests/fixtures/phase70/cli-outcomes.json touched command cases; tests/test_cli_registry.py and tests/test_mcp.py assert exact reflected parameter names/types/defaults. scripts/sync_docs.py is check-only, not a generator: `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check` and `python -m pytest tests/test_sync_docs.py -q`.

### Command-specific requested baseline applicability
Specialist may propose a source patch informed by exact Hadolint rule and FROM graph; this command does not invoke a model because repeatability uses actual image bytes as its oracle. Voice may read source path/rule and repeatability verdict; never speak raw build log or claim cross-builder reproducibility. Companion may show two retained image IDs and changed paths only after both exports and cleanup succeed; incomplete/missing Docker stays visibly incomplete.

### Additional literal adapter and genuine runtime acceptance

These proposed tests require preinstalled real engines and explicit runtime pins; failure to supply them is a failed acceptance prerequisite, not a successful skip. No installation/download is performed by tests.
~~~python
def test_real_hadolint_and_two_builds(tmp_path):
    import os
    from rush.tools.containerfile import ContainerfileTool,repeat_image_build
    from rush.runtime.binaries import resolve_binary
    from rush.permissions import ExecutionPermissions
    assert resolve_binary("hadolint",project_root=tmp_path),"preinstalled Hadolint required"
    file=tmp_path/"Dockerfile";file.write_text("FROM alpine:latest\n")
    scanned=ContainerfileTool().run(tmp_path)
    assert [(f["line"],f["rule"]) for f in scanned["findings"] if f["rule"]=="DL3007"]==[(1,"DL3007")]
    assert scanned["engine_version"]
    file.write_text("FROM scratch\nCOPY payload /payload\n")
    (tmp_path/"payload").write_bytes(b"alpha")
    grants=ExecutionPermissions(network=True,download=True,cache_write=True,build=True,slow=True,artifact_write=True)
    result=repeat_image_build(tmp_path,"Dockerfile",docker_binary=os.environ["RUSH_TEST_DOCKER"],permissions=grants)
    assert result["status"]=="repeatable_on_this_builder"
    assert result["changed_paths"]==[] and result["changed_count"]==0
    assert result["configuration_changed"] is False
    assert len(result["images"])==2 and all(x.startswith("sha256:") for x in result["images"])
    assert (tmp_path/"payload").read_bytes()==b"alpha"


def test_create_timeout_reaps_owned_named_container(tmp_path,monkeypatch):
    import json,subprocess
    from pathlib import Path
    import rush.runtime.subprocesses as runtime
    from rush.permissions import ExecutionPermissions
    from rush.tools.containerfile import repeat_image_build
    (tmp_path/"Dockerfile").write_text("FROM scratch\n")
    executable=tmp_path.parent/"docker-fixture";executable.write_text("#!/bin/sh\n");executable.chmod(0o700)
    live={};calls=[]
    def child(argv,**kwargs):
        calls.append(argv)
        if argv[1]=="version":
            return subprocess.CompletedProcess(argv,0,"fixture-1","")
        if argv[1]=="build":
            Path(argv[argv.index("--iidfile")+1]).write_text("sha256:"+"a"*64)
        elif argv[1:3]==["image","inspect"]:
            return subprocess.CompletedProcess(argv,0,json.dumps([{"Config":{},"Os":"linux","Architecture":"arm64"}]),"")
        elif argv[1]=="create":
            name=argv[argv.index("--name")+1];token=argv[argv.index("--label")+1].split("=",1)[1]
            live[name]={"Id":"b"*64,"Config":{"Labels":{"io.rush.invocation":token}}}
            raise subprocess.TimeoutExpired(argv,1)
        elif argv[1:3]==["container","inspect"]:
            assert kwargs["cancel_check"]() is False
            if argv[-1] not in live:return subprocess.CompletedProcess(argv,1,"","No such container")
            return subprocess.CompletedProcess(argv,0,json.dumps([live[argv[-1]]]),"")
        elif argv[1]=="rm":
            assert argv[-1]=="b"*64;live.clear()
        return subprocess.CompletedProcess(argv,0,"","")
    monkeypatch.setattr(runtime,"run_subprocess",child)
    try:
        repeat_image_build(tmp_path,"Dockerfile",docker_binary=str(executable),
            permissions=ExecutionPermissions(network=True,download=True,cache_write=True,build=True,slow=True,artifact_write=True))
    except subprocess.TimeoutExpired:
        pass
    else:raise AssertionError("create timeout hidden")
    assert live=={}
    assert sum(a[1]=="rm" for a in calls)==1
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

def test_containerfile_granted_optional_foreign_stdio(tmp_path):
    import json,os,subprocess
    root,foreign,registry,project,env,python=_registered_transport_fixture(tmp_path)
    (root/"Dockerfile").write_text("FROM scratch\nCOPY payload /payload\n")
    (root/"payload").write_bytes(b"alpha")
    docker=os.environ["RUSH_TEST_DOCKER"]
    flags=["--image-context","--compare-builds","--build-context",".","--docker-binary",docker,
        "--allow-network","--allow-download","--allow-cache-write","--allow-build","--allow-slow","--allow-artifact-write"]
    cli=subprocess.run([python,"-m","rush","containerfile",str(root),*flags,"--json"],
        cwd=foreign,env=env,capture_output=True,text=True,timeout=1800)
    left=json.loads(cli.stdout)
    right=exchange_stdio(python,foreign,env,"rush_containerfile",
        {"path":".","project":project,"image_context":True,"compare_builds":True,
         "build_context":".","docker_binary":docker,"allow_network":True,"allow_download":True,
         "allow_cache_write":True,"allow_build":True,"allow_slow":True,"allow_artifact_write":True},
        registry_root=registry)
    for result in (left,right):
        _assert_engine_identities(result,["hadolint"])
        assert result["metadata"]["image_context"][0]["base_reference"]=="scratch"
        trial=result["metadata"]["build_repeatability"]
        assert trial["status"]=="repeatable_on_this_builder"
        assert trial["changed_count"]==0 and trial["changed_paths"]==[]
    project_result=lambda r:(r["status"],r["findings"],r["metadata"]["image_context"],
        r["metadata"]["build_repeatability"]["source_digest"],r["metadata"]["build_repeatability"]["configuration_changed"])
    assert project_result(left)==project_result(right)
    assert not (foreign/".rush").exists()
    assert (root/"payload").read_bytes()==b"alpha"
~~~

Complete missing-engine shared-dispatch regression (current resolver injection is verified tools.common.engine_on_path); result is not fabricated:
~~~python
def test_containerfile_missing_engine_no_process(tmp_path):
    from unittest.mock import patch
    from rush.tools.containerfile import ContainerfileTool
    from rush.permissions import ExecutionPermissions
    (tmp_path/"Dockerfile").write_text("FROM scratch\n")
    with patch("rush.tools.common.engine_on_path",return_value=False), patch("rush.runtime.subprocesses.run_subprocess") as process:
        result=ContainerfileTool().run(tmp_path)
    assert result["status"]=="skipped"
    assert result["findings"]==[]
    assert all(row["status"]=="skipped" for row in result["metadata"]["engines"])
    process.assert_not_called()
~~~

~~~python
def test_containerfile_malformed_engine_report_is_error(tmp_path):
    from rush.engines import ENGINES
    (tmp_path/"Dockerfile").write_text("FROM scratch\n")
    for name in ["hadolint"]:
        result=ENGINES[name].normalize({"exit_code":0,"stdout":"[not-json","stderr":""},tmp_path,"containerfile")
        assert result["status"]=="error"
        assert result["findings"]==[]
~~~

Literal root-anchor integration, Batch integration owner, src/rush/mcp_support/tool_registry.py::_CWD_RELATIVE_ARGS (retain every other entry):

~~~python
_CWD_RELATIVE_ARGS["containerfile"] = ()
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

Exact displayed first-RED receipt: extracted the first complete test body from this document and executed against SOURCE 66c6c799eaa5b6017776d659e9e0de2b4a8878a5 with Python 3.12.12, offline uv, cleared PYTHONPATH, and TemporaryDirectory fixture. `test_standard_names_and_exact_inputs`: AssertionError at displayed code line 18, expected selected input list; current engine calls were empty. No interface/import/fixture error preceded the assertion. Future-interface tests below remain unexecuted proposals.

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
def test_q15_containerfile_cli_and_initialized_stdio(tmp_path):
    import json, os, subprocess, sys
    from pathlib import Path
    root=tmp_path/"project"; root.mkdir()
    (root/"rush.toml").write_text("[tools.containerfile]\n")
    (root/"Dockerfile").write_text("FROM scratch\n")
    bindir=tmp_path/"bin"; bindir.mkdir()
    log=tmp_path/"engine-calls.jsonl"
    scripts={"hadolint": "print('[]')"}
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
    argv=[sys.executable,"-m","rush","containerfile",str(root),*["--no-cache"],"--json"]
    cli=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert cli.returncode==0,cli.stderr
    left=json.loads(cli.stdout)
    pass
    right=exchange_stdio(sys.executable,root,env,"rush_containerfile",{"path":str(root),"no_cache":True})
    assert left["tool"]==right["tool"]=="containerfile"
    assert left["status"]==right["status"]=="ok"
    assert left["findings"]==right["findings"]==[]
    assert left["metadata"]["scope"]["assessed_files"]==right["metadata"]["scope"]["assessed_files"]==[str(root/"Dockerfile")]
    records=[json.loads(line) for line in log.read_text().splitlines()]
    records=[row for row in records if "--version" not in row[1] and "--help" not in row[1]]
    assert [row[0] for row in records]==["hadolint","hadolint"]
    assert all("Secret" not in json.dumps(value) for value in (left,right))
    before_dirs=sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir())
    before={p.relative_to(root).as_posix():p.read_bytes()
            for p in root.rglob("*") if p.is_file()}
    log_before=log.read_bytes()
    denied_cli=subprocess.run([sys.executable,"-m","rush","containerfile",str(root),
        *["--compare-builds","--docker-binary",str(bindir/"docker"),"--no-cache"],"--json"],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    denied_left=json.loads(denied_cli.stdout)
    denied_right=exchange_stdio(sys.executable,root,env,"rush_containerfile",{"path":str(root),"compare_builds":True,"docker_binary":str(bindir/"docker"),"no_cache":True})
    assert denied_cli.returncode==0,denied_cli.stderr
    assert denied_left["status"]==denied_right["status"]=="skipped"
    assert log.read_bytes()==log_before
    invalid=exchange_stdio(sys.executable,root,env,"rush_containerfile",{
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

Use actual subprocess CLI and initialized JSON-RPC stdio. Complete tests/test_mcp.py::test_q15_containerfile_cli_and_initialized_stdio body above supplies literal command, fixture, fields and denial assertions. Shared exchange_stdio helper below is defined once by Batch integration owner. Add tests/test_cli_registry.py::test_q15_containerfile_cli_options for all explicit flags, invalid enums, missing/empty/staged cases. Actual engine fixture logs every call including --version; genuine-engine acceptance remains separate.

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
        expected={"image_context":(["boolean"],False),
            "compare_builds":(["boolean"],False),
            "build_context":(["string","null"],None),
            "docker_binary":(["string","null"],None)}
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


## Exact acceptance fixture and readiness

Transport fixture: real executable named hadolint in test-owned bin outside project. --version prints fixture-1; every scan appends argv JSON to test log and prints []; scanner exit0. Fixture project rush.toml contains [tools.containerfile], Dockerfile contains FROM scratch. CLI [sys.executable,"-m","rush","containerfile",str(root),"--json","--no-cache"]; MCP rush_containerfile arguments {path:str(root),no_cache:true}. Assert status ok, findings [], assessed_files=[root/Dockerfile] and exactly one input Dockerfile for each transport. New image-context transport case requires two parsed stages and no docker log. Denied --compare-builds with no grants returns skipped/not_run before even Hadolint/version/scratch; then full grants exercise controlled build branch separately.

Live tests/test_containerfile.py::test_real_hadolint_standard_name resolves installed Hadolint, executes Dockerfile FROM alpine:latest and requires rule DL3007 with exact file/line; source existing hadolint parser is exercised, not substituted. Missing executable is external acceptance blocker; all inspected engines absent. No installation performed. Run:
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_containerfile.py tests/test_hadolint_reference.py tests/test_cli_registry.py tests/test_mcp.py -q

Repair readiness: current callable RED observed, minimum repair concrete, shared ownership/file map and downstream tests specified. Proposed extension/build packets remain unapproved separately. Planning has not passed future implementation/live-engine acceptance. Future command PR order: T1 repair plus shared integration first; T2 separately approved extension; P0 prerequisite before any batch isolated trial; T4 separately approved build trial. No PR created.

Frozen review checklist: Q15 discovery/argv/scope repair, parser preservation, literal context, repeat-build proposal, baseline applicability, grants, real transport, missing engines, source drift/cleanup and exact file ownership reconciled. Future acceptance blocked only by supplying already approved local real engines/runtime/images; this does not block beginning T1.
