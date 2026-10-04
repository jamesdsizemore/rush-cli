# Q09 — slop

Implement `slop` corrections and retained expansions from binding audit.

## Feature and goal

Remediate complete Q09 scope. Planning only; production changes and tests below proposed, unimplemented and unexecuted. Grounding: main `c78e445ba1e575ca373e35840142cd627b055d6a`; clean Phase70 `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70` at `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`. Read `AGENTS.md`, `docs/templates/task-block-template.md`, `README.md`, `00-shared-foundation.md` in this plan directory first. Foundation is defined dependency/owner. Audit `docs/reports/cli-mcp-command-audit-2026-09-26.md` SHA256 `8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f`; remediation `docs/reports/command-tdd-2026-10-01-plan-remediation.md` SHA256 `362dae4489fbe8f6322217e30ae69ed3ad8a888732a37029641a0040cd8ef633`. Binding C-01–C-29 overrides contradictory older fixes. Earlier report probe outcomes do not verify corrected proposed code.

## Required behavior

Preserve scanner provisioning, connected specialist local models, selectable voice/live speech and 3D companion as user baseline. Command expansions remain separate. F1 strict flat schema rejects unknown keys/string grants with MCP isError=false, ToolResult error, raw error.code=INVALID_REQUEST; valid-field rejection uses metadata.error.code=invalid_argument; escape uses path_escape. F2 canonical engines/scope, no duplicate child arrays or partial booleans. F3 whole-operation denial: skipped, execution cause permission_denied, operation block denied/build_or_slow_denied, zero spawns/writes. Verify-only row denial preserves base assessment. Runtime absolute, never cwd-anchored; F4 validates platform/runtime before image. F4/F5/F6 exact foundation contracts retained. Shared aggregate choice remains README decision, no local override.

## Deliverables and file map

Create new file tests/test_slop.py (absent both revisions). Source/fixture/test patches below proposed only. Shared CLI/MCP/catalog/reference/permissions/CHANGELOG/coverage rows are Foundation-owned serialized Q09-DOC rows in same packet. Existing Phase70 discovery/permission/provenance/zero-skip gates retained.

## Dependencies and ordered tasks

1. Finish foundation interfaces and ratify open choices; no report default is approval.
2. Record interface-absent RED separately; assert exported interface/metadata before new-option invocation. Require behavior assertion RED once interface exists.
3. Apply local source/fixtures/tests; preserve existing protocols and unrelated code.
4. Run narrow gates and same-packet docs; future final full-suite acceptance only after implementation.

## Constraints

This remediation writes plans only; no production/tests/source/config writes, downloads, hooks, commits/pushes/releases. pytest runtime dependency (`pyproject.toml:27`). Terms: producer-qualified metric has engine, unit, actual value and source digest; TP/FP/TN/FN are observed labeled counts; isolation means actual foundation OCI boundary. Any edit invalidates frozen review.

## Proposed source changes

```python
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..permissions import ExecutionPermissions
from ..runtime.binaries import analysis_scope
from ..runtime.subprocesses import _engine_analysis_scope
from .base import Finding, ToolFn, ToolResult
from .common import elapsed_ms, engine_on_path, error_result, now_ms, run_engine
from .routing import aggregate_scope, aggregate_status, collect_files
from pydantic import StrictBool
from .routing import child_scope

_JS = {"js", "jsx", "mjs", "cjs", "ts", "tsx"}
_RULE_KEYS = {"id", "literal", "message"}
MARKER_MESSAGE = (
    "Literal marker {literal!r} matched; text match only, not evidence "
    "of authorship or a functional defect"
)


def _language(file: Path) -> str:
    return "typescript" if file.suffix.lower() in {".ts", ".tsx"} else "javascript"


def _contained(root: Path, value: Path | str) -> Path:
    if Path(value).is_absolute():
        raise ContainmentError(
            "ABSOLUTE_PATH_DISALLOWED",
            "Path must be relative to the scanned directory",
            str(value),
        )
    target = PhysicalRoot(root).open_contained(Path(value))
    if not target.is_file():
        raise ContainmentError("NOT_A_FILE", "Path is not a regular file", str(value))
    return target


def _valid_rule(rule: Any) -> bool:
    return (
        isinstance(rule, dict)
        and {"id", "literal"} <= set(rule) <= _RULE_KEYS
        and all(isinstance(rule[k], str) and rule[k] for k in rule)
    )


def _load_project_rules(config_file: Path) -> tuple[list[dict[str, str]], str]:
    data = config_file.read_bytes()
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid project-style rules: {exc}") from None
    rules = parsed.get("rules") if isinstance(parsed, dict) else None
    if (
        not isinstance(parsed, dict)
        or set(parsed) != {"version", "rules"}
        or type(parsed["version"]) is not int
        or parsed["version"] != 1
        or not isinstance(rules, list)
        or not all(_valid_rule(r) for r in rules)
        or len({r["id"] for r in rules}) != len(rules)
    ):
        raise ValueError(
            'invalid project-style rules: need {"version":1,"rules":[...]} with '
            "unique non-empty id/literal (optional message) and no other keys"
        )
    return rules, hashlib.sha256(data).hexdigest()


def _calibrate_literal_rule(rule_file: Path, fixture_file: Path) -> dict[str, Any]:
    rule_bytes, fixture_bytes = rule_file.read_bytes(), fixture_file.read_bytes()
    try:
        candidate = json.loads(rule_bytes.decode("utf-8"))
        samples = json.loads(fixture_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid calibration JSON: {exc}") from None
    if not _valid_rule(candidate):
        raise ValueError("invalid calibration rule: need non-empty id and literal")
    if (
        not isinstance(samples, list)
        or len(samples) < 3
        or not all(
            isinstance(s, dict)
            and set(s) == {"id", "code", "label"}
            and isinstance(s["id"], str)
            and s["id"]
            and isinstance(s["code"], str)
            and type(s["label"]) is bool
            for s in samples
        )
        or len({s["id"] for s in samples}) != len(samples)
        or all(s["label"] for s in samples)
        or not any(s["label"] for s in samples)
    ):
        raise ValueError(
            "invalid calibration data: need >=3 unique {id,code,label:bool} rows with both labels"
        )
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    counterexamples: list[str] = []
    for s in samples:
        matched = candidate["literal"] in s["code"]
        cell = ("tp" if s["label"] else "fp") if matched else ("fn" if s["label"] else "tn")
        counts[cell] += 1
        if cell in ("fp", "fn"):
            counterexamples.append(s["id"])
    proposable = counts["tp"] >= 2 and counts["fp"] == 0
    return {
        "candidate_digest": hashlib.sha256(rule_bytes).hexdigest(),
        "fixture_digest": hashlib.sha256(fixture_bytes).hexdigest(),
        **counts,
        "counterexample_ids": counterexamples,
        "proposable": proposable,
        "proposed_config_entry": dict(candidate) if proposable else None,
    }
```
  Replace `__call__` and `run` (:22–105) with:
```python
    def __call__(
        self,
        path: Path,
        allow_download: StrictBool = False,
        rule_profile: Literal["markers", "project_style"] = "markers",
        rule_config_path: Path | None = None,
        calibrate_rule: Path | None = None,
        calibration_fixture: Path | None = None,
    ) -> ToolResult:
        if type(allow_download) is not bool:
            return _slop_error(self.name,None,"allow_download must be a bool")
        # aislop may fetch its npm package only under the download grant.
        return self.run(
            path,
            permissions=ExecutionPermissions(download=allow_download),
            rule_profile=rule_profile,
            rule_config_path=rule_config_path,
            calibrate_rule=calibrate_rule,
            calibration_fixture=calibration_fixture,
        )

    def run(
        self,
        path: Path,
        *,
        config=None,
        permissions: ExecutionPermissions | None = None,
        rule_profile: Literal["markers", "project_style"] = "markers",
        rule_config_path: Path | None = None,
        calibrate_rule: Path | None = None,
        calibration_fixture: Path | None = None,
    ) -> ToolResult:
        from ..engines import ENGINES
        from ..engines.aislop import aislop_grants

        start = now_ms()
        if rule_profile not in ("markers", "project_style"):
            return _slop_error(self.name, None, f"invalid rule_profile {rule_profile!r}")
        if (calibrate_rule is None) != (calibration_fixture is None):
            return _slop_error(
                self.name, None, "calibrate_rule and calibration_fixture must be given together"
            )
        if rule_config_path is not None and rule_profile != "project_style":
            return _slop_error(
                self.name, None, "rule_config_path requires rule_profile='project_style'"
            )
        root = (path if path.is_dir() else path.parent).resolve()
        if rule_profile == "project_style" and rule_config_path is None:
            try:
                from ..config import RushConfigError, load_config, resolve_tool_options

                cfg = config if config is not None else load_config(path)
                tool_cfg = (
                    None if isinstance(cfg, Mapping) else getattr(cfg, "tools", {}).get("slop")
                )
                config_options = (
                    cfg.get("options", cfg)
                    if isinstance(cfg, Mapping)
                    else getattr(tool_cfg, "options", {})
                )
                rule_config_path = resolve_tool_options("slop", config_options, {}).get(
                    "rule_config_path"
                )
            except (RushConfigError, TypeError, ValueError, KeyError) as exc:
                return _slop_error(
                    self.name, None, f"slop: invalid options: {exc}", duration_ms=elapsed_ms(start)
                )
        rules: list[dict[str, str]] | None = None
        digest: str | None = None
        trial: dict[str, Any] | None = None
        try:
            if rule_profile == "project_style":
                if rule_config_path is not None:
                    rules, digest = _load_project_rules(_contained(root, rule_config_path))
                elif (root / ".rush" / "slop-rules.json").is_file():
                    rules, digest = _load_project_rules(_contained(root, ".rush/slop-rules.json"))
            if calibrate_rule is not None and calibration_fixture is not None:
                trial = _calibrate_literal_rule(
                    _contained(root, calibrate_rule), _contained(root, calibration_fixture)
                )
        except (ContainmentError, ValueError, OSError) as exc:
            return _slop_error(self.name, None, str(exc), duration_ms=elapsed_ms(start))

        python_files = collect_files(path, {"py", "pyi"})
        js_files = collect_files(path, _JS)
        texts = {
            f: f.read_text(encoding="utf-8", errors="ignore").splitlines()
            for f in [*python_files, *js_files]
        }
        findings: list[Finding] = []
        rows: list[dict[str, Any]] = []
        statuses: list[str] = []
        for language in ("javascript", "typescript"):
            files = [f for f in js_files if _language(f) == language]
            if not files:
                continue
            hits: list[Finding] = []
            for file in files:
                for number, line in enumerate(texts[file], 1):
                    literal = (
                        "TODO: AI"
                        if "TODO: AI" in line
                        else ("generated by ai" if "generated by ai" in line.lower() else None)
                    )
                    if literal:
                        hits.append(
                            {
                                "path": file.relative_to(root).as_posix(),
                                "line": number,
                                "rule": "rush-ai-marker",
                                "severity": "warn",
                                "message": MARKER_MESSAGE.format(literal=literal),
                            }
                        )
            findings.extend(hits)
            status = "warn" if hits else "ok"
            statuses.append(status)
            rows.append(
                {
                    "language": language,
                    "engine": "rush",
                    "rules": ["rush-ai-marker"],
                    "paths": [f.relative_to(root).as_posix() for f in files],
                    "status": status,
                }
            )

        child: ToolResult | None = None
        if python_files:
            aislop = ENGINES["aislop"]
            # Probe in the same scope run_engine dispatches in, so a verified
            # setup-provisioned aislop (project manifest) is found like PATH.
            with analysis_scope(_engine_analysis_scope(aislop, path, None)):
                has_aislop = engine_on_path(aislop.binary)
            engine_to_use = aislop if has_aislop else ENGINES["sloppylint"]
            # aislop scans the directory itself (one positional); sloppylint
            # takes the explicit file list.
            files_arg = [] if engine_to_use.name == "aislop" else [str(f) for f in python_files]
            with aislop_grants(permissions or ExecutionPermissions()):
                child = run_engine(engine_to_use, path, files_arg, tool_name=self.name)
            findings.extend(child["findings"])
            statuses.append(child["status"])
            entries = (child.get("metadata") or {}).get("engines") or [{}]
            rows.append(
                {
                    "language": "python",
                    "engine": engine_to_use.name,
                    "rules": sorted({str(f.get("rule", "")) for f in child["findings"]}),
                    "paths": [f.relative_to(root).as_posix() for f in python_files],
                    "engine_scope": entries[0].get("scope"),
                    "status": child["status"],
                }
            )

        metadata: dict[str, Any] = dict((child or {}).get("metadata") or {})
        if rule_profile == "project_style":
            if rules is None:
                metadata["project_style"] = {
                    "status": "unassessed",
                    "reason": "no_project_style_rules",
                }
                metadata["reason"] = "no_project_style_rules"
                statuses.append("skipped")
            else:
                matches: list[Finding] = [
                    {
                        "path": file.relative_to(root).as_posix(),
                        "line": number,
                        "rule": rule["id"],
                        "rule_id": rule["id"],
                        "severity": "warn",
                        "message": rule.get("message")
                        or f"project-style literal match: {rule['literal']}",
                        "extensions": {"source_config_digest": digest},
                    }
                    for file, lines in texts.items()
                    for number, line in enumerate(lines, 1)
                    for rule in rules
                    if rule["literal"] in line
                ]
                findings.extend(matches)
                status = ("warn" if matches else "ok") if texts else "skipped"
                statuses.append(status)
                rows.append(
                    {
                        "language": "project_style",
                        "engine": "rush",
                        "rules": [r["id"] for r in rules],
                        "paths": [f.relative_to(root).as_posix() for f in texts],
                        "status": status,
                    }
                )
                metadata["project_style"] = {
                    "status": "assessed" if texts else "unassessed",
                    "source_config_digest": digest,
                    "rules": [r["id"] for r in rules],
                }
                if not texts:
                    metadata["project_style"]["reason"] = "no_selected_files"
                metadata["rule_config_digest"] = digest
        if trial is not None:
            metadata["rule_trial"] = trial
        metadata["assessed"] = rows
        assessment_results = []
        for row in rows:
            scope = row.get("engine_scope")
            if scope is None:
                unavailable = row["status"] in ("skipped", "error")
                scope = child_scope(
                    "unavailable" if unavailable else "complete",
                    reason="engine_error" if row["status"] == "error" else "engine_unavailable" if unavailable else None,
                    requested_targets=row["paths"], matched_file_count=len(row["paths"]),
                    consumed_file_count=0 if unavailable else len(row["paths"]),
                )
            assessment_results.append({"metadata": {"scope": scope}})
        if rule_profile == "project_style" and rules is None:
            assessment_results.append({"metadata": {"scope": child_scope("unavailable", reason="no_project_style_rules")}})
        metadata["scope"] = aggregate_scope(assessment_results)

        engines = {r["engine"] for r in rows}
        if not rows:
            summary = f"slop: no supported source files found under {path}"
        elif len(rows) == 1 and child is not None:
            summary = child["summary"]  # Python-only keeps the engine's own summary/skip reason
        else:
            summary = (
                "slop: "
                + ", ".join(f"{r['language']}={r['status']}" for r in rows)
                + f"; {len(findings)} finding(s)"
                + (
                    f"; python: {child['summary']}"
                    if child is not None and child["status"] in ("skipped", "error")
                    else ""
                )
            )
        return ToolResult(
            tool=self.name,
            engine=(next(iter(engines)) if len(engines) == 1 else "rush") if rows else None,
            engine_version=child["engine_version"] if child is not None and len(rows) == 1 else None,
            status=aggregate_status(statuses),  # decision D1; option (b) changes routing.aggregate_status
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=sorted(
                findings,
                key=lambda i: (i.get("path", ""), i.get("line") or 0, i.get("rule", "")),
            ),
            raw=(child or {}).get("raw"),
            metadata=metadata,
        )
```
  In `src/rush/engines/sloppylint.py`, replace `normalize` (:37–63):
```python
    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        exit_code = raw.get("exit_code")
        try:
            parsed = json.loads(raw.get("stdout") or "")
        except json.JSONDecodeError:
            parsed = None
        issues = parsed.get("issues") if isinstance(parsed, dict) else None
        if (
            exit_code != 0
            or not isinstance(issues, list)
            or not all(isinstance(i, dict) for i in issues)
        ):
            stderr = (raw.get("stderr") or "").strip()[:500]
            return ToolResult(
                tool=tool_name,
                engine=self.name,
                engine_version=self.version(),
                status="error",
                duration_ms=0,
                summary=f"sloppylint produced no valid JSON report (exit {exit_code})"
                + (f": {stderr}" if stderr else ""),
                findings=[],
                raw=None,
                metadata={"terminal_reason":"malformed_output" if exit_code == 0 else "nonzero_exit"},
            )
        findings: list[Finding] = [
            {
                "path": issue.get("file", str(path)),
                "line": issue.get("line"),
                "rule": issue.get("pattern_id", "sloppylint"),
                "severity": "error"
                if issue.get("severity") in {"critical", "high"}
                else "warn",
                "message": issue.get("message", "AI slop detected"),
            }
            for issue in issues
        ]
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=0,
            summary=f"sloppylint: {len(findings)} issue(s)",
            findings=findings,
            raw=json.dumps(parsed),
        )
```

## Remediation reconciliation

Individual report Fix verification indexed by exact ID/line; safe replacements read frozen corrected plan, future behavior checks remain pending. No self-matching grep command copied into plan.

| ID | Substantive correction | Live evidence / exact check | Outcome / gap |
|---|---|---|---|
| Q09-01 | Correct `tests/test_slop.py` does not exist at either revision; replacement in proposed packet/binding amendments below | report:11469, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-02 | Correct Path rules contradict the RED bodies; replacement in proposed packet/binding amendments below | report:11490, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-03 | Correct The plan targets the c78e445 aislop adapter that phase 70 rewrote; replacement in proposed packet/binding amendments below | report:11530, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-04 | Correct "Partial and otherwise clean ⇒ skipped" contradicts phase-70 S16.3 (decision D1); replacement in proposed packet/binding amendments below | report:11585, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-05 | Correct The interface omits `allow_download` / `permissions`; replacement in proposed packet/binding amendments below | report:11622, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-06 | Correct At 66c6c79 aislop scans the whole directory, so the "python" row misreports scope; replacement in proposed packet/binding amendments below | report:11646, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-07 | Correct audit acceptance `test_benign_ai_mention_no_marker` was dropped; replacement in proposed packet/binding amendments below | report:11671, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-08 | Correct `test_engine_crash_not_clean` has no body; protocol tests assert status only; replacement in proposed packet/binding amendments below | report:11697, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-09 | Correct Audit fixture changed to `.js`; language IDs, top-level status/engine, row `engine`/`rules` undefined; replacement in proposed packet/binding amendments below | report:11750, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-10 | Correct Project-style config contract drifted from the audit and is underspecified; replacement in proposed packet/binding amendments below | report:11776, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-11 | Correct Calibration contract gaps; listed validation cases have no bodies; replacement in proposed packet/binding amendments below | report:11820, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-12 | Correct No production patch code; replacement in proposed packet/binding amendments below | report:11889, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-13 | Correct CLI/MCP transport owner ("Foundation") undefined; the mechanism is stale; replacement in proposed packet/binding amendments below | report:12313, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-14 | Correct Boilerplate copied from other plans misdirects a coding agent; replacement in proposed packet/binding amendments below | report:12374, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-15 | Correct Docs work is vague and covers 3 of ~20 affected pages; replacement in proposed packet/binding amendments below | report:12401, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-16 | Correct The check list omits mypy, `sync_docs --check` and existing slop tests; replacement in proposed packet/binding amendments below | report:12459, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-17 | Correct Marker message and catalog descriptions still claim AI authorship; replacement in proposed packet/binding amendments below | report:12480, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-18 | Correct Template nonconformance; replacement in proposed packet/binding amendments below | report:12504, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-19 | Correct Citation errors; replacement in proposed packet/binding amendments below | report:12536, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |
| Q09-20 | Correct RED evidence fails on KeyError/TypeError; CLI exit code not asserted; replacement in proposed packet/binding amendments below | report:12547, original Fix verification; grounded Phase70 | Frozen-document outcome below; behavioral NOT RUN, apply packet / ratify decisions |

## Checks to run before reporting

Run frozen-document checks only now. Exact future behavior gates below await applied source/tests. No broad runner or full-suite execution during remediation.

## Completion

Full numbered/M/X/C reconciliation, substantive review and frozen-byte outcomes required. Implementation acceptance remains pending source application, decision ratification, real engine fixtures and OCI gate. Dirty AGENTS.md and user-owned untracked plans/report/audit preserved.

## Binding amendments and retained decisions

Foundation F2 adds child_scope to src/rush/tools/routing.py; import that single helper. Local assessment results feed aggregate_scope; retained Python metadata.engines unchanged, JS/project rows canonical scopes. Python-only result preserves child summary, version, raw and engine; benign TS-only returns ok/rush/zero findings; error child scope unavailable/engine_error. Metadata.assessed paths and Finding paths relative to scanned root. Missing project rules creates unavailable scope, never fictitious author/policy claims. No OCI dependency for this command.

Exact additional helper in `src/rush/tools/slop.py`, before SlopTool:

```python
def _slop_error(tool, engine, message, *, duration_ms=0):
    result = error_result(tool, engine, message, duration_ms=duration_ms)
    result["metadata"] = {"error": {"code": "path_escape" if "OUTSIDE_ROOT" in message or "SYMLINK" in message else "invalid_argument", "message": message}}
    return result
```

DECISION REQUIRED Q09-D3: keep catalog engine_names=("sloppylint",) or add aislop; adding changes capabilities/project engine-only candidates and requires capabilities/full_project_scan/phase70_engine_applicability gates. Q09-D4: allow empty version1 rules list (audited proposal), or reject empty list; rejecting alternative changes `_load_project_rules` condition to `or not rules` and test expects invalid_argument. Q09-D5: retain metadata.reason alias no_project_style_rules, or nested project_style reason only (remove assignment); both preserve scope and nested reason. Shared aggregate question remains README D5; report D2 duplicate partial boolean superseded C01. No choice approved. Current source does not resolve Slop options; proposed `resolve_tool_options` route at remediation12079–12086 is new config-backed option behavior.

Q09-P1 owns slop.py helpers/__call__/run and sloppylint.py normalize only (remediation11908–12309 exact packet). Aislop protocol/grants regression-only: valid exit1 diagnostics remain fail, child offline environment unchanged. Capture sloppylint0.5.1 clean/findings/process-failure and aislop0.16.1 fixtures before claiming protocol acceptance. Preserve strict real label validation and candidate/config/source bytes; configured finding digest lives in Finding.extensions.source_config_digest, not arbitrary top-level field.

Q09-M1–M4: benign TS coverage, directory-discovery unavailable scope, zero selected project rule scope and config provenance are exercised via complete report bodies Q09-07–12; no authorship inference. X01–X18 and C01–C29 applicable shared transport, docs, grant, base, schema, template, no-skip and parity corrections use Foundation; no duplicate wrappers.

Q09-DOC-options Foundation: register ToolOptionSpec rule_config_path (str, path_kind=file); CLI profile/config/calibration values forward unchanged; MCP only path cwd-anchored, new inputs contained relative to scan root. Docs same-packet inventory: docs/reference/cli-reference.md, docs/reference/mcp-tool-reference.md, docs/reference/result-reference.md, docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/JSON_SCHEMA.md, docs/TOOL_CATALOG.md, docs/ENGINES.md, docs/reference/engine-directory.md, docs/ENGINE_COMPATIBILITY.md, docs/CLI_COOKBOOK.md, docs/tools/slop.md, docs/user-guide/checking-code.md, docs/user-guide/checking-project-files.md, docs/user-guide/understanding-results.md, docs/COMPATIBILITY.md, docs/reference/compatibility.md, docs/ARCHITECTURE.md, docs/developer-guide.md, docs/permissions.md, CHANGELOG.md, docs/reports/phase-64-66-documentation-coverage.md. Replace AI authorship and Markdown-Unfluff claims with literal marker + explicit rules + labeled calibration; shared F10 discovery prose carries truthful current engines and options.

Future command (NOT RUN; prerequisites applied packet/F1/F2/F6/new tests/captured protocols):

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_slop.py tests/test_static_tools.py tests/test_aislop_reference.py tests/test_sloppylint_reference.py tests/test_phase20_slop_tdd.py tests/test_transport_parity.py tests/test_cli_registry.py tests/test_mcp.py tests/test_workflows.py tests/test_sync_docs.py tests/test_phase70_t7_fixes.py tests/test_phase70_t17.py tests/test_phase70_t26.py tests/test_onboarding.py tests/test_project_run_lifecycle.py tests/test_dashboard_http_contract.py tests/test_catalog.py tests/test_phase70_t16.py tests/test_project_journey.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk git diff --check
```

## Complete command test bodies

Proposed new tests/test_slop.py. Prefix imports hashlib,json,pytest,Path and SlopTool/module/SloppylintEngine/AislopEngine as referenced; tests invoke actual proposed controller.

```python
import hashlib
import json
from pathlib import Path
import pytest
import rush.tools.slop as module
from rush.tools.slop import SlopTool
from rush.engines.aislop import AislopEngine
from rush.engines.sloppylint import SloppylintEngine
from transport_parity import run_cli, run_mcp
```

```python
def test_benign_ai_mention_no_marker(tmp_path):
    (tmp_path/"app.ts").write_text("const aiClient = new AIModelClient()\n"
        "// review AI output for accuracy\n// human-written migration\n")
    result = SlopTool().run(tmp_path)
    assert [f for f in result["findings"] if f["rule"] == "rush-ai-marker"] == []
    assert result["status"] == "ok"
    assert result["engine"] == "rush"
    assert {r["language"]: r["status"] for r in result["metadata"]["assessed"]} == {"typescript": "ok"}
    assert result["metadata"]["scope"]["coverage"] == "complete"
```

```python
import json
from pathlib import Path
FIXTURES = Path(__file__).parent / "fixtures" / "engine_reports"

def _sloppylint(monkeypatch):
    engine = SloppylintEngine()
    monkeypatch.setattr(engine, "version", lambda: "0.5.1")
    return engine

def test_malformed_engine_output_is_error(tmp_path, monkeypatch):
    engine = _sloppylint(monkeypatch)
    clean = engine.normalize({"exit_code": 0, "stdout": (FIXTURES/"sloppylint-clean-0.5.1.json").read_text(), "stderr": ""}, tmp_path, "slop")
    assert (clean["status"], clean["findings"]) == ("ok", [])
    found = engine.normalize({"exit_code": 0, "stdout": (FIXTURES/"sloppylint.json").read_text(), "stderr": ""}, tmp_path, "slop")
    assert (found["status"], [(f["path"], f["line"], f["rule"], f["severity"]) for f in found["findings"]]) == (
        "warn", [("src/example.py", 12, "verbose-comment", "warn")])
    invalid = "sloppylint produced no valid JSON report (exit 0)"
    for stdout in ("{", "[]", '{"issues": {}}', '{"issues": [1]}', ""):
        out = engine.normalize({"exit_code": 0, "stdout": stdout, "stderr": ""}, tmp_path, "slop")
        assert (out["status"], out["summary"], out["findings"]) == ("error", invalid, [])
    aislop = AislopEngine(); monkeypatch.setattr(aislop, "version", lambda: "0.16.1")
    report = json.loads((FIXTURES/"aislop"/"diagnostics-0.16.1.json").read_text())
    result = aislop.normalize({"exit_code": 1, "parsed": report, "findings": report["diagnostics"], "stderr": "", "cwd": str(tmp_path)}, tmp_path, "slop")
    assert result["status"] == "fail" and len(result["findings"]) == 3  # fixture: 2 error + 1 warning diagnostics
    bad = aislop.normalize({"exit_code": 0, "stdout": "{", "parsed": None, "findings": []}, tmp_path, "slop")
    assert (bad["status"], bad["summary"]) == ("error", "aislop produced no JSON report (exit 0)")

def test_engine_crash_not_clean(tmp_path, monkeypatch):
    engine = _sloppylint(monkeypatch)
    crash = json.loads((FIXTURES/"sloppylint-process-failure-0.5.1.json").read_text())
    out = engine.normalize(crash, tmp_path, "slop")
    assert (out["status"], out["findings"]) == ("error", [])
    assert out["summary"].startswith("sloppylint produced no valid JSON report (exit 2): ")
    assert "unrecognized arguments" in out["summary"]
    silent = engine.normalize({"exit_code": 2, "stdout": "", "stderr": ""}, tmp_path, "slop")
    assert (silent["status"], silent["summary"]) == ("error", "sloppylint produced no valid JSON report (exit 2)")
    aislop = AislopEngine(); monkeypatch.setattr(aislop, "version", lambda: "0.16.1")
    quiet = aislop.normalize({"exit_code": 1, "parsed": None, "findings": [], "stderr": ""}, tmp_path, "slop")
    assert (quiet["status"], quiet["summary"]) == ("error", "aislop produced no JSON report (exit 1)")
```

```python
def test_rule_calibration_rejects_false_positive(tmp_path):
    root = tmp_path/"scan"; root.mkdir()
    (root/"app.js").write_text("// TODO: AI rewrite\n")
    rule = root/"rule.json"; rule.write_text(json.dumps({"id":"no_placeholder","literal":"TODO: AI"}))
    labels = root/"labels.json"
    samples = [
        {"id":"p1","code":"// TODO: AI rewrite","label":True},
        {"id":"p2","code":"# TODO: AI placeholder","label":True},
        {"id":"n1","code":"AI model client initialization","label":False},
        {"id":"n2","code":"human-written migration","label":False},
        {"id":"n3","code":"review AI output for accuracy","label":False}]
    labels.write_text(json.dumps(samples))
    before = {p:p.read_bytes() for p in (rule,labels,root/"app.js")}
    args = dict(calibrate_rule="rule.json",calibration_fixture="labels.json")
    good = SlopTool().run(root,**args)["metadata"]["rule_trial"]
    assert (good["tp"],good["fp"],good["tn"],good["fn"]) == (2,0,3,0)
    assert good["proposable"] is True and good["counterexample_ids"] == []
    assert good["proposed_config_entry"] == {"id":"no_placeholder","literal":"TODO: AI"}
    assert good["candidate_digest"] == hashlib.sha256(rule.read_bytes()).hexdigest()
    assert good["fixture_digest"] == hashlib.sha256(labels.read_bytes()).hexdigest()
    assert {p:p.read_bytes() for p in before} == before
    assert sorted(p.name for p in root.iterdir()) == ["app.js","labels.json","rule.json"]
    samples[2]["code"] = "TODO: AI client initialization"
    labels.write_text(json.dumps(samples))
    bad = SlopTool().run(root,**args)["metadata"]["rule_trial"]
    assert (bad["tp"],bad["fp"],bad["tn"],bad["fn"]) == (2,1,2,0)
    assert bad["proposable"] is False and bad["counterexample_ids"] == ["n1"]
    assert bad["proposed_config_entry"] is None
    samples[0]["label"] = "true"; labels.write_text(json.dumps(samples))
    assert SlopTool().run(root,**args)["status"] == "error"
    assert SlopTool().run(root,calibrate_rule="rule.json")["status"] == "error"
    assert SlopTool().run(root,calibration_fixture="labels.json")["status"] == "error"
    samples[0]["label"] = True
    for broken in (samples[:2], [s|{"label":True} for s in samples],
                   samples+[dict(samples[0])], [s|{"extra":1} for s in samples]):
        labels.write_text(json.dumps(broken))
        assert SlopTool().run(root,**args)["status"] == "error"
    labels.write_text(json.dumps(samples))
    rule.write_text(json.dumps({"id":"no_placeholder","literal":""}))
    assert SlopTool().run(root,**args)["status"] == "error"
    rule.write_text(json.dumps({"id":"no_placeholder","literal":"TODO: AI"}))
    outside = tmp_path/"outside.json"; outside.write_text("[]")
    (root/"link.json").symlink_to(outside)
    for kw in (dict(calibrate_rule=str(rule),calibration_fixture="labels.json"),
               dict(calibrate_rule="../outside.json",calibration_fixture="labels.json"),
               dict(calibrate_rule="rule.json",calibration_fixture="link.json"),
               dict(calibrate_rule="rule.json",calibration_fixture="nope.json"),
               dict(calibrate_rule="rule.json",calibration_fixture=".")):
        assert SlopTool().run(root,**kw)["status"] == "error"
```

```python
def test_js_marker_does_not_hide_missing_python_engine(tmp_path,monkeypatch):
    (tmp_path/'app.py').write_text('x=1\n'); (tmp_path/'app.ts').write_text('// TODO: AI rewrite\n')
    monkeypatch.setattr(module,'engine_on_path',lambda name:False)
    monkeypatch.setattr(module,'run_engine',lambda engine,*a,**k:dict(tool='slop',engine=engine.name,engine_version=None,status='skipped',duration_ms=0,summary='engine missing',findings=[],metadata={'scope':module.child_scope('unavailable',reason='engine_unavailable')}))
    result=SlopTool().run(tmp_path)
    assert 'assessed' in result['metadata']
    rows={row['language']:row for row in result['metadata']['assessed']}
    assert rows['python']['status']=='skipped'
    assert rows['typescript']['status']=='warn'
    assert rows['python']['paths']==['app.py']
    assert result['metadata']['scope']['coverage']=='partial'
    assert [(f['path'],f['line'],f['rule']) for f in result['findings']]==[('app.ts',1,'rush-ai-marker')]

def test_slop_options_cli_mcp_parity(tmp_path):
    (tmp_path/'app.ts').write_text('// PROJECT_PLACEHOLDER\n')
    config={'version':1,'rules':[{'id':'placeholder','literal':'PROJECT_PLACEHOLDER','message':'project marker'}]}
    (tmp_path/'rules.json').write_text(json.dumps(config))
    options=('--rule-profile','project_style','--rule-config-path','rules.json')
    code,left=run_cli('slop',tmp_path,cli_options=options)
    right=run_mcp('rush_slop',{'path':str(tmp_path),'rule_profile':'project_style','rule_config_path':'rules.json'})
    assert code==1
    assert left['findings']==right['findings']
    assert left['metadata']['assessed']==right['metadata']['assessed']
    assert left['metadata']['project_style']['source_config_digest']==hashlib.sha256((tmp_path/'rules.json').read_bytes()).hexdigest()
```
