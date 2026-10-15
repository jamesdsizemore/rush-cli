"""75-T02/EVALUATOR (Phase 72 D13, D13a, D14a, D15): live decision runner,
provider parsing, strict task manifest.

Every test runs against fixtures in `tmp_path`; no test calls a real provider.
A fake provider executable (`_FAKE_PROVIDER_SRC`) stands in for `codex` and
`claude`: the provider module's `subprocess.run` seam is intercepted for the
executable only, the original argv, `stdin` and `shell` arguments are asserted,
and the fixture script is dispatched with `sys.executable`, so the tests run
without a POSIX shebang. Every other subprocess (git, the verifier) runs
unchanged.

Symbols the earlier tasks and this task add (`load_task_manifest`,
`resolve_decision_route`, ...) are imported inside the test bodies, so the
module collects on every checkout.
"""

from __future__ import annotations

import base64
import contextlib
import copy
import dataclasses
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from rush.delivery.compact import canonical_json


@pytest.mark.parametrize("layout", ["source", "installed"])
def test_codex_decision_instruction_pinned_and_kind_scoped(
    tmp_path, monkeypatch, layout
):
    import tomllib

    from scripts.benchmarks import providers

    route = providers.resolve_decision_route(
        "openai-codex-oauth-cli-live",
        allow_live_route="openai-codex-oauth-cli-live",
        provider_executable=sys.executable,
    )
    original = Path(providers.__file__).resolve().parents[2]
    root = tmp_path / 'source😀"\\path'
    fixture = root / (
        "tests/fixtures/benchmarks/codex_decision_instructions.md"
        if layout == "source"
        else "scripts/benchmarks/fixtures/codex_decision_instructions.md"
    )
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(
        (
            original / "tests/fixtures/benchmarks/codex_decision_instructions.md"
        ).read_bytes()
    )
    monkeypatch.setattr(
        providers, "__file__", str(root / "scripts/benchmarks/providers.py")
    )
    monkeypatch.setattr(providers, "FIXTURE_ROOT", fixture.parent, raising=False)
    monkeypatch.chdir(tmp_path)
    prompt = '{"kind":"dataset_answer","task":"unchanged"}'
    dataset = providers.decision_argv(route, "dataset_answer", prompt)
    episode = providers.decision_argv(route, "episode", prompt)
    config = next(x for x in dataset if x.startswith("model_instructions_file="))
    assert tomllib.loads(config)["model_instructions_file"] == str(fixture.resolve())
    assert dataset[-1] == episode[-1] == prompt
    assert "shell_tool" in dataset and "shell_tool" not in episode
    assert "unified_exec" in dataset and "unified_exec" not in episode
    assert route.protocol["instruction_files"] == ["$CODEX_HOME/AGENTS.md"]
    digest, instruction = providers.decision_protocol_digest(route)
    assert len(digest) == 64
    assert (
        instruction
        == "5b73465f7986c3d56a2c895523b3e8969e7eee5762ac0eeb1b5876e69a384df1"
    )
    fixture.write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="decision instructions changed"):
        providers.decision_argv(route, "dataset_answer", prompt)


def test_codex_instruction_override_rejects_unpinned_runtime(tmp_path, monkeypatch):
    from scripts.benchmarks import providers

    route = providers.resolve_decision_route(
        "openai-codex-oauth-cli-live",
        allow_live_route="openai-codex-oauth-cli-live",
        provider_executable=sys.executable,
    )

    def probe(argv, *args):
        if argv[-1] == "--version":
            return ("codex 0.161.0\n", "")
        return (" ".join(route.protocol["argv"]["dataset_answer"]), "")

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported runtime spawned a decision")

    monkeypatch.setattr(providers, "_probe_output", probe)
    monkeypatch.setattr(providers, "run_memory_decision", forbidden)
    report = providers.preflight_decision_route(
        route, workspace_root=tmp_path, case_budgets=[(16000, 1024)]
    )
    assert report["status"] == "unavailable"
    assert report["reason"] == "decision_instruction_runtime_unsupported"
    assert (
        report["decision_instruction_sha256"]
        == "5b73465f7986c3d56a2c895523b3e8969e7eee5762ac0eeb1b5876e69a384df1"
    )


def test_hybrid_verdict_requires_matching_decision_protocol():
    from scripts.benchmarks.reporting import aggregate_hybrid_verdict

    rows = [
        {
            "provider": "codex",
            "arm": arm,
            "case_id": "literal",
            "seed": 1,
            "fixture_revision": "fixed",
            "grants": [],
            "budgets": {},
            "split": "literal",
            "security_inclusion": 0,
            "route_available": True,
            "retrieval_required": False,
            "passed": True,
            "recall_at_8": 1.0,
            "chance_recall": 0.0,
            "case_tokens": 10,
            "case_ms": 2,
            "decision_protocol_digest": "a" * 64,
            "decision_instruction_sha256": "b" * 64,
            "decision_kind_protocol_digests": {
                "dataset_answer": "c" * 64,
                "episode": "d" * 64,
            },
        }
        for arm in ("current", "hybrid", "metadata")
    ]
    assert aggregate_hybrid_verdict(rows)["global"]["verdict"] == "no_benefit"
    rows[-1]["decision_kind_protocol_digests"]["episode"] = "e" * 64
    assert aggregate_hybrid_verdict(rows)["per_provider"]["codex"] == {
        "verdict": "unavailable",
        "reason": "missing pair",
    }
    rows[0].pop("decision_protocol_digest")
    assert aggregate_hybrid_verdict(rows)["per_provider"]["codex"] == {
        "verdict": "unavailable",
        "reason": "missing decision protocol receipt",
    }
    rows[0]["security_inclusion"] = 1
    assert aggregate_hybrid_verdict(rows)["global"]["verdict"] == "unsafe"


from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool
from scripts.benchmarks import memory as bm
from scripts.benchmarks import providers
from scripts.benchmarks import run as bench_run
from scripts.benchmarks.contracts import FixtureError

_REPO = Path(__file__).resolve().parents[1]
_SHIPPED_MANIFEST = _REPO / "tests" / "fixtures" / "phase75" / "task_manifest.json"

_CODEX_ROUTE = "openai-codex-oauth-cli-live"
_CLAUDE_ROUTE = "anthropic-claude-code-live"
_FORMAT_OF_ROUTE = {_CODEX_ROUTE: "codex", _CLAUDE_ROUTE: "claude"}

_EMPTY_REVISION = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
_UPLOAD_REVISION = "de47c4083fb7ae52158b157c912a8c09f13c27e545f79806bab6ad1146b8ee13"
_BASELINE_DIGEST = "d3cfc6e4ba1083097089bcdf0f6029f3ceef22d128340637ceefd3c118584ad6"
_BUDGET = {
    "max_total_tokens": 16000,
    "output_reserve_tokens": 1024,
    "max_steps": 12,
    "timeout_s": 600,
}
_ANSWERS = {
    "lme-q-001": "2023-05-10",
    "lme-q-002": "db-widen-ids",
    "p72-q-ext": "2023-05-10",
}

_PHASE75_DECLARED: tuple[tuple[str, str | None], ...] = (
    ("bug repair", "bug_repair"),
    ("critical late finding", None),
    ("repeated failure", None),
    ("changed dependency", None),
    ("explicit UI requirement", None),
    ("architecture seam", None),
    ("stale memory", None),
    ("contradictory correction", None),
    ("Unicode recovery", None),
    ("large log", None),
    ("agent handoff", "agent_handoff"),
    ("reuse", None),
)
_PHASE75_OPEN_VARIANTS = (
    "no reuse",
    "misleading memory",
    "search miss",
    "initially irrelevant evidence later required",
    "unsupported language",
    "duplicate symbols",
    "branch/worktree switch",
    "rename",
    "suppression",
    "expired snapshot",
    "long handoff",
)

_SECRET = "sk-ant-" + "A" * 24
_SESSION_ID = "sess-0123456789abcdef"
_UUID = "uuid-fedcba9876543210"
_THREAD_ID = "thread-abcdef0123456789"

_UPLOAD_SRC = (
    "def upload(size_bytes: int, elapsed_seconds: float) -> bool:\n"
    "    if elapsed_seconds > 30:\n"
    "        return True\n"
    "    if size_bytes > 1_000_000:\n"
    "        return True\n"
    "    return True\n"
)
_CHECK_SRC = (
    "import upload\n\n"
    'assert upload.upload(0, 999) is False, "expected timeout rejected"\n'
    'assert upload.upload(2_000_000, 0) is False, "expected oversized upload rejected"\n'
    'print("OK")\n'
)
_FIXED_BOTH_SRC = _UPLOAD_SRC.replace("return True", "return False", 2)
_FIXED_TIMEOUT_ONLY_SRC = _UPLOAD_SRC.replace("return True", "return False", 1)


def _diff(name: str, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            f"a/{name}",
            f"b/{name}",
            lineterm="\n",
        )
    )


_PATCH_BOTH = _diff("upload.py", _UPLOAD_SRC, _FIXED_BOTH_SRC)
_PATCH_TIMEOUT_ONLY = _diff("upload.py", _UPLOAD_SRC, _FIXED_TIMEOUT_ONLY_SRC)
_PATCH_CHECKER = _diff(
    "check_upload.py",
    _CHECK_SRC,
    _CHECK_SRC.replace('print("OK")', 'print("OK-edited")'),
)
_PATCH_TWO_FILES = _PATCH_BOTH + _PATCH_CHECKER

_UPLOAD_COMMANDS = [
    {"command": ["{python}", "check_upload.py"], "expected_exit_code": 0}
]
_UPLOAD_BEHAVIORS = ["upload-size-limit-fixed", "upload-timeout-fixed"]


# --------------------------------------------------------------------------
# Baseline manifest (the 5 D13a cases, written out literally)
# --------------------------------------------------------------------------


def _lme_case(index: int, query: str) -> dict[str, Any]:
    return {
        "id": f"lme-q-00{index}",
        "kind": "dataset_answer",
        "family": "longmemeval_sample",
        "variant": "base",
        "retrieval_required": False,
        "inputs": {
            "section": "longmemeval",
            "corpus_section": None,
            "record_id": f"lme-q-00{index}",
            "query": query,
        },
        "fixture_revision": _EMPTY_REVISION,
        "grants": ["cache_write", "network"],
        "permitted_actions": ["answer"],
        "editable_paths": [],
        "budget": dict(_BUDGET),
        "acceptance": {
            "evaluator": "normalized_contains",
            "behavior_ids": [],
            "required_commands": [],
            "handoff": None,
        },
    }


def _episode_case(
    case_id: str,
    family: str,
    task: str,
    revision: str,
    ops: list[str],
    editable: list[str],
    acceptance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": case_id,
        "kind": "episode",
        "family": family,
        "variant": "base",
        "retrieval_required": False,
        "inputs": {"builder": case_id, "task": task},
        "fixture_revision": revision,
        "grants": ["artifact_write", "build", "cache_write", "network"],
        "permitted_actions": ops,
        "editable_paths": editable,
        "budget": dict(_BUDGET),
        "acceptance": acceptance,
    }


def _handoff_acceptance(source: str, contains: str) -> dict[str, Any]:
    return {
        "evaluator": "receiver_readback_acknowledged",
        "behavior_ids": [],
        "required_commands": [],
        "handoff": {
            "subject": "domain_knowledge",
            "source": source,
            "write_count": 1,
            "content_contains": contains,
        },
    }


def _baseline_cases() -> list[dict[str, Any]]:
    return [
        _lme_case(1, "delayed"),
        _lme_case(2, "branch"),
        _episode_case(
            "upload-repair",
            "bug_repair",
            "Fix upload() so it correctly rejects timed-out and oversized uploads.",
            _UPLOAD_REVISION,
            ["verify_attempt", "submit"],
            ["upload.py"],
            {
                "evaluator": "verifier_receipt_completed",
                "behavior_ids": list(_UPLOAD_BEHAVIORS),
                "required_commands": copy.deepcopy(_UPLOAD_COMMANDS),
                "handoff": None,
            },
        ),
        _episode_case(
            "guest-handoff",
            "agent_handoff",
            "Hand off the guest-checkout regression note to a receiver.",
            _EMPTY_REVISION,
            ["write", "handoff", "receive", "expand", "submit"],
            [],
            _handoff_acceptance("guest-session", "promo code"),
        ),
        _episode_case(
            "diagnosis-handoff",
            "agent_handoff",
            "Diagnose the deploy-pipeline regression and hand it off.",
            _EMPTY_REVISION,
            [
                "last_success_diagnose",
                "write",
                "handoff",
                "receive",
                "expand",
                "submit",
            ],
            [],
            _handoff_acceptance("diagnosis-session", "deploy-pipeline"),
        ),
    ]


def _digest(cases: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        canonical_json(sorted(cases, key=lambda c: c["id"]))
    ).hexdigest()


def _p72_dataset_case(case_id: str = "p72-q-ext", **overrides: Any) -> dict[str, Any]:
    case = _lme_case(1, "flight")
    case["id"] = case_id
    case["retrieval_required"] = True
    case.update(overrides)
    return case


def _p72_upload_case(**overrides: Any) -> dict[str, Any]:
    case = copy.deepcopy(_baseline_cases()[2])
    case["id"] = "p72-upload-repair"
    case["retrieval_required"] = True
    case.update(overrides)
    return case


def _manifest_obj(
    extra_cases: tuple[dict[str, Any], ...] = (),
    *,
    embedding: dict[str, str] | None = None,
    with_p72_digest: bool = True,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    all_cases = copy.deepcopy(cases if cases is not None else _baseline_cases())
    all_cases.extend(copy.deepcopy(list(extra_cases)))
    obj: dict[str, Any] = {
        "schema_version": 1,
        "cases": all_cases,
        "declared": [
            {"family": family, "case_family": case_family}
            for family, case_family in _PHASE75_DECLARED
        ],
        "phase75_family_coverage": {
            "open": {
                "families": [f for f, c in _PHASE75_DECLARED if c is None],
                "variants": list(_PHASE75_OPEN_VARIANTS),
            }
        },
    }
    p72 = [c for c in all_cases if str(c.get("id", "")).startswith("p72-")]
    if p72 and with_p72_digest:
        obj["phase72_cases_sha256"] = _digest(p72)
    if embedding is not None:
        obj["phase72_embedding"] = embedding
    return obj


_EMBEDDING = {
    "endpoint": "http://127.0.0.1:11434",
    "model": "nomic-embed-text",
    "model_digest": "0a109f422b47",
}


def _write_manifest(path: Path, obj: dict[str, Any]) -> Path:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return path


def _code(exc: BaseException) -> str:
    return str(exc).split(":", 1)[0]


# --------------------------------------------------------------------------
# Fake provider
# --------------------------------------------------------------------------

_FAKE_PROVIDER_SRC = r"""
import base64
import difflib
import hashlib
import json
import os
import subprocess
import sys
import time

ARGS = sys.argv[1:]
with open(os.environ["RUSH_FAKE_PLAN"], encoding="utf-8") as fh:
    PLAN = json.load(fh)
LOG = os.environ["RUSH_FAKE_LOG"]
IS_CODEX = ARGS[:1] == ["exec"]
CLAUDE_FLAGS = ["-p", "--tools", "--output-format", "--permission-mode", "--safe-mode",
                "--strict-mcp-config", "--no-session-persistence"]
CODEX_FLAGS = ["--ephemeral", "--json", "--sandbox", "--skip-git-repo-check",
               "--ignore-user-config", "--ignore-rules", "--strict-config",
               "--enable", "--disable", "-c"]


def log(entry):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


if "--help" in ARGS:
    log({"kind": "help", "argv": ARGS})
    print("Usage: fake-provider [OPTIONS]")
    for flag in (CODEX_FLAGS if IS_CODEX else CLAUDE_FLAGS):
        if flag != PLAN.get("omit_flag"):
            print("  " + flag + "    option")
    sys.exit(0)
if ARGS == ["--version"]:
    log({"kind": "version", "argv": ARGS})
    print(PLAN.get("version", "fake 1.0"))
    print("build 123")
    sys.exit(0)

prompt = ARGS[-1]
req = None
for i, ch in enumerate(prompt):
    if ch != "{":
        continue
    try:
        cand = json.loads(prompt[i:])
    except ValueError:
        continue
    if isinstance(cand, dict) and "schema_version" in cand:
        req = cand
        break
if req is None:
    log({"kind": "unparsed", "argv": ARGS, "prompt": prompt})
    sys.exit(3)

log({"kind": "decision", "argv": ARGS, "cwd": os.getcwd(), "listdir": sorted(os.listdir(".")),
     "request": req, "prompt": prompt, "decision_kind": req.get("decision_kind"),
     "case_id": req.get("case_id"), "step": req.get("step")})


def match(when, request):
    for key, want in when.items():
        got = request.get(key)
        if isinstance(want, list):
            if got not in want:
                return False
        elif got != want:
            return False
    return True


action = {}
for rule in PLAN.get("rules", []):
    if match(rule["when"], req):
        action = rule["action"]
        break


def act(operation, kwargs):
    return {"kind": "action", "operation": operation, "kwargs": kwargs}


def submit(final):
    return {"kind": "submit", "final": final}


def git(*args):
    return subprocess.run(["git", *args], cwd=".", capture_output=True, text=True).stdout.strip()


def solve_upload(req):
    if len(req["history"]) >= 1:
        return submit("attempted")
    with open("upload.py", encoding="utf-8", newline="") as fh:
        old = fh.read().splitlines(keepends=True)
    new = list(old)
    for i in range(len(new) - 1):
        if new[i].lstrip().startswith("if ") and new[i + 1].strip() == "return True":
            new[i + 1] = new[i + 1].replace("True", "False")
    patch = "".join(difflib.unified_diff(old, new, "a/upload.py", "b/upload.py", lineterm="\n"))
    acc = req["acceptance"]
    contract = {
        "base_commit": git("rev-parse", "HEAD"),
        "base_tree_digest": git("rev-parse", "HEAD^{tree}"),
        "patch_content_digest": "live-patch-1",
        "required_commands": acc["required_commands"],
        "config_digest": "live-cfg-1",
        "review_class": "standard",
    }
    request = {"attempt_id": "live-attempt-1", "behavior_ids": acc["behavior_ids"],
               "contract": contract, "patch": patch}
    return act("verify_attempt", {"request": request})


def solve_handoff(req):
    hist = req["history"]
    h = req["acceptance"]["handoff"]
    ops = [o for o in req["permitted_actions"] if o != "submit"]
    seq = (["diagnose"] if "last_success_diagnose" in ops else []) + [
        "write", "handoff", "receive", "expand", "ack"]
    n = len(hist)
    if n >= len(seq):
        return submit("handoff complete")
    pos = {name: i for i, name in enumerate(seq)}

    def raw(name):
        return hist[pos[name]].get("raw") or {}

    name = seq[n]
    if name == "diagnose":
        return act("last_success_diagnose", {"request": {
            "behavior_id": h["content_contains"], "conditions": {"code_ref": "abc123"}}})
    if name == "write":
        return act("write", {"subject": h["subject"],
                             "content": {"text": "note: " + h["content_contains"]},
                             "source": h["source"]})
    if name == "handoff":
        written = raw("write")
        request = {
            "action": "prepare", "receiver_audience": "handoff-receiver",
            "goal": "hand off the note",
            "selected_refs": [{"id": written.get("id"), "version": written.get("artifact_version")}]}
        if "handoff_namespace" in PLAN:
            request["receiver_namespace"] = PLAN["handoff_namespace"]
        return act("handoff", {"request": request})
    prepared = (raw("handoff").get("data") or {})
    if name == "receive":
        return act("receive", {"request": {"session_id": prepared.get("handoff_id"),
                                           "capability": prepared.get("capability")}})
    changes = ((raw("receive").get("data") or {}).get("changes")) or []
    if not changes:
        return submit("no changes delivered")
    change = changes[0]
    if name == "expand":
        return act("expand", {"session_allowlist": [h["source"]],
                              "request": {"id": change["id"], "version": change["version"]}})
    content = base64.b64decode((raw("expand").get("data") or {}).get("content_base64", ""))
    return act("receive", {"request": {
        "session_id": prepared.get("handoff_id"), "capability": prepared.get("capability"),
        "ack": [{"id": change["id"], "version": change["version"],
                 "digest": hashlib.sha256(content).hexdigest()}]}})


def decide():
    if "decision" in action:
        return action["decision"]
    kind = req["decision_kind"]
    if kind == "preflight":
        return {"kind": "answer", "text": "ok"}
    if kind == "answer":
        return {"kind": "answer", "text": PLAN.get("answers", {}).get(req.get("case_id"), "unknown")}
    if "verify_attempt" in req["permitted_actions"]:
        return solve_upload(req)
    return solve_handoff(req)


if action.get("sleep"):
    time.sleep(action["sleep"])
if "text" in action:
    text = action["text"]
elif "stdout" in action or "events" in action:
    text = ""
else:
    text = json.dumps(decide())
if "usage_raw" in action:
    usage = action["usage_raw"]
elif req.get("decision_kind") == "preflight":
    usage = PLAN.get("preflight_usage_raw")
else:
    usage = PLAN.get("usage_raw")

if "stdout" in action:
    out = action["stdout"]
elif IS_CODEX:
    if "events" in action:
        events = action["events"]
    else:
        events = [{"type": "thread.started", "thread_id": PLAN["ids"]["thread"]}, {"type": "turn.started"}]
        events.append({"type": "item.completed",
                       "item": {"id": "item_0", "type": "agent_message", "text": text}})
        done = {"type": "turn.completed"}
        if usage is not None:
            done["usage"] = usage
        events.append(done)
    out = "\n".join([json.dumps(e) for e in events] + action.get("extra_lines", [])) + "\n"
else:
    obj = {"type": "result", "subtype": "success", "is_error": False, "result": text,
           "num_turns": action.get("num_turns", 1), "session_id": PLAN["ids"]["session"],
           "uuid": PLAN["ids"]["uuid"], "modelUsage": {"fake-model-1": {"costUSD": 0}}}
    if usage is not None:
        obj["usage"] = usage
    for key, value in action.get("patch", {}).items():
        if value is None:
            obj.pop(key, None)
        else:
            obj[key] = value
    out = json.dumps(obj)

sys.stdout.write(out)
if action.get("pad_stdout"):
    sys.stdout.write("x" * action["pad_stdout"])
if action.get("stderr"):
    sys.stderr.write(action["stderr"])
sys.exit(action.get("exit", 0))
"""


def _usage(
    fmt: str,
    inp: int = 100,
    out: int = 10,
    *,
    cache_creation: int = 0,
    cache_read: int = 0,
    cached: int = 0,
    extra: dict[str, int] | None = None,
) -> dict[str, Any]:
    if fmt == "codex":
        usage: dict[str, Any] = {
            "input_tokens": inp,
            "cached_input_tokens": cached,
            "output_tokens": out,
        }
    else:
        usage = {
            "input_tokens": inp,
            "cache_creation_input_tokens": cache_creation,
            "cache_read_input_tokens": cache_read,
            "output_tokens": out,
        }
    usage.update(extra or {})
    return usage


_UNSET: Any = object()


def _plan(
    fmt: str,
    *,
    rules: list[dict[str, Any]] | None = None,
    usage: Any = _UNSET,
    preflight: Any = _UNSET,
    answers: dict[str, str] | None = None,
    omit_flag: str | None = None,
) -> dict[str, Any]:
    return {
        "answers": dict(_ANSWERS if answers is None else answers),
        "version": "codex 0.162.1" if fmt == "codex" else "fake 1.0",
        "usage_raw": _usage(fmt) if usage is _UNSET else usage,
        "preflight_usage_raw": _usage(fmt, 40, 5) if preflight is _UNSET else preflight,
        "omit_flag": omit_flag,
        "ids": {"session": _SESSION_ID, "uuid": _UUID, "thread": _THREAD_ID},
        "rules": rules or [],
    }


def _rule(when: dict[str, Any], **action: Any) -> dict[str, Any]:
    return {"when": when, "action": action}


_PREFLIGHT_NORMAL = _rule({"decision_kind": "preflight"})


def _only(case_id: str, *special: dict[str, Any]) -> list[dict[str, Any]]:
    """Rules where only `case_id` is answered normally (after the `special`
    rules); every other case fails fast, so the run stays cheap."""
    return [
        _PREFLIGHT_NORMAL,
        *special,
        _rule({"case_id": case_id}),
        _rule({}, exit=1),
    ]


def _for_case(case_id: str, **action: Any) -> dict[str, Any]:
    return _rule({"case_id": case_id, "decision_kind": "episode"}, **action)


# --------------------------------------------------------------------------
# Kit: fake provider + subprocess seam + MemoryTool spy
# --------------------------------------------------------------------------


@dataclasses.dataclass
class ToolCall:
    operation: str | None
    kwargs: dict[str, Any]
    result: Any


class Kit:
    def __init__(
        self, base: Path, mp: pytest.MonkeyPatch, plan: dict[str, Any]
    ) -> None:
        self.base = base
        self.caller_home = os.environ.get("HOME")
        base.mkdir(parents=True, exist_ok=True)
        self.exe = base / "fake-provider"
        self.exe.write_text(
            f"#!{sys.executable}\n{_FAKE_PROVIDER_SRC}", encoding="utf-8"
        )
        self.exe.chmod(0o755)
        self.exe_real = str(self.exe.resolve())
        self.plan_path = base / "plan.json"
        self.log_path = base / "calls.jsonl"
        self.spawns: list[dict[str, Any]] = []
        self.tool_calls: list[ToolCall] = []
        self.set_plan(plan)
        mp.setenv("RUSH_FAKE_PLAN", str(self.plan_path))
        mp.setenv("RUSH_FAKE_LOG", str(self.log_path))
        real_run = subprocess.run
        kit = self

        def run_seam(*args: Any, **kwargs: Any) -> Any:
            argv = args[0] if args else kwargs["args"]
            if (
                isinstance(argv, (list, tuple))
                and argv
                and str(argv[0]) == kit.exe_real
            ):
                kit.spawns.append(
                    {
                        "argv": [str(x) for x in argv],
                        "cwd": None
                        if kwargs.get("cwd") is None
                        else str(kwargs["cwd"]),
                        "stdin_devnull": kwargs.get("stdin") is subprocess.DEVNULL,
                        "shell": bool(kwargs.get("shell", False)),
                        "timeout": kwargs.get("timeout"),
                        # 72-T08 (D14): the harness redirects its own in-process Rush
                        # calls, so a provider process takes the caller's environment
                        # explicitly; its HOME is the caller's, never the redirected one.
                        "env_is_caller_environment": (
                            kwargs.get("env") or os.environ
                        ).get("HOME")
                        == kit.caller_home,
                        "capture_output": kwargs.get("capture_output") is True,
                        "text": kwargs.get("text") is True,
                        "check": kwargs.get("check"),
                        "encoding": kwargs.get("encoding"),
                        "errors": kwargs.get("errors"),
                    }
                )
                return real_run(
                    [sys.executable, str(kit.exe), *[str(x) for x in argv[1:]]],
                    **kwargs,
                )
            return real_run(*args, **kwargs)

        mp.setattr(subprocess, "run", run_seam)
        real_tool_run = MemoryTool.run

        def tool_spy(self: MemoryTool, path: Any, *args: Any, **kwargs: Any) -> Any:
            result = real_tool_run(self, path, *args, **kwargs)
            kit.tool_calls.append(ToolCall(kwargs.get("operation"), kwargs, result))
            return result

        mp.setattr(MemoryTool, "run", tool_spy)

    def set_plan(self, plan: dict[str, Any]) -> None:
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")

    @property
    def log(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return [e for e in self.log if e["kind"] == "decision"]

    def decisions_for(self, case_id: str) -> list[dict[str, Any]]:
        return [e for e in self.decisions if e["case_id"] == case_id]

    @property
    def decision_spawns(self) -> list[dict[str, Any]]:
        return [
            s
            for s in self.spawns
            if "--help" not in s["argv"] and s["argv"][1:] != ["--version"]
        ]


def _parse_request(prompt: str) -> dict[str, Any]:
    for i, ch in enumerate(prompt):
        if ch != "{":
            continue
        try:
            cand = json.loads(prompt[i:])
        except ValueError:
            continue
        if isinstance(cand, dict) and "schema_version" in cand:
            return cand
    raise AssertionError("prompt carries no decision request")


def _assert_spawn_contract(spawn: dict[str, Any]) -> None:
    """The decision subprocess contract (D13a, Phase 75 line 153): an argv
    array without a shell, no stdin, captured text output, the caller's
    environment (72-T08 D14), a timeout, and no `check`."""
    assert spawn["shell"] is False
    assert spawn["stdin_devnull"] is True
    assert spawn["env_is_caller_environment"] is True
    assert spawn["capture_output"] is True
    assert spawn["text"] is True
    assert spawn["check"] is False
    assert spawn["encoding"] == "utf-8"
    assert spawn["errors"] == "replace"
    assert spawn["timeout"] is not None
    assert spawn["cwd"] is not None


def _isolate(mp: pytest.MonkeyPatch, base: Path) -> Path:
    home = base / "home"
    for sub in ("home", "xdg", "localappdata", "codex-home", "tmp"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    mp.setenv("HOME", str(home))
    mp.setenv("USERPROFILE", str(home))
    mp.setenv("XDG_DATA_HOME", str(base / "xdg"))
    mp.setenv("LOCALAPPDATA", str(base / "localappdata"))
    mp.setenv("CODEX_HOME", str(base / "codex-home"))
    for name in ("TMPDIR", "TEMP", "TMP"):
        mp.setenv(name, str(base / "tmp"))
    mp.setattr(tempfile, "tempdir", str(base / "tmp"))
    return home


@pytest.fixture(autouse=True)
def _g10_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _isolate(monkeypatch, tmp_path)
    yield
    shutil.rmtree(tmp_path / "home", ignore_errors=True)


@dataclasses.dataclass
class RunResult:
    kit: Kit
    base: Path
    out_dir: Path
    exit_code: int | None = None
    error: BaseException | None = None
    stdout: str = ""
    stderr: str = ""
    written_tmp: list[bytes] = dataclasses.field(default_factory=list)

    @property
    def report_path(self) -> Path:
        return self.out_dir / "memory-suite-report.json"

    @property
    def report(self) -> dict[str, Any]:
        assert self.error is None or isinstance(self.error, SystemExit), repr(
            self.error
        )
        assert self.report_path.exists(), (
            f"no report; exit={self.exit_code} stderr={self.stderr[-800:]}"
        )
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    @property
    def records(self) -> list[dict[str, Any]]:
        results = self.report["case_results"]
        if isinstance(results, dict):
            flat: list[dict[str, Any]] = []
            for value in results.values():
                flat.extend(value if isinstance(value, list) else [value])
            return flat
        return list(results)

    def record(self, case_id: str, seed: int | None = None) -> dict[str, Any]:
        found = [
            r
            for r in self.records
            if r["case_id"] == case_id and (seed is None or r["seed"] == seed)
        ]
        assert found, f"no record for {case_id} seed={seed}"
        return found[0]

    def ran(self) -> RunResult:
        """Fail (not error) unless `main` returned normally with exit code 0."""
        assert self.error is None, repr(self.error)
        assert self.exit_code == 0, (
            f"exit={self.exit_code} stderr={self.stderr[-1500:]}"
        )
        return self

    def tool_ops(self) -> list[str | None]:
        return [c.operation for c in self.kit.tool_calls]


def _run(
    base: Path,
    argv_fn: Callable[[Kit], list[str]],
    plan: dict[str, Any] | None = None,
    *,
    agents_md: str | None = None,
    capture_tmp: bool = False,
) -> RunResult:
    mp = pytest.MonkeyPatch()
    try:
        _isolate(mp, base)
        if agents_md is not None:
            (base / "codex-home" / "AGENTS.md").write_text(agents_md, encoding="utf-8")
        kit = Kit(base / "kit", mp, plan if plan is not None else _plan("codex"))
        argv = argv_fn(kit)
        out_dir = Path(argv[argv.index("--output") + 1])
        result = RunResult(kit=kit, base=base, out_dir=out_dir)
        if capture_tmp:
            real_replace = os.replace

            def replace_seam(src: Any, dst: Any, *a: Any, **k: Any) -> None:
                if str(src).endswith("memory-suite-report.tmp"):
                    result.written_tmp.append(Path(src).read_bytes())
                real_replace(src, dst, *a, **k)

            mp.setattr(os, "replace", replace_seam)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                result.exit_code = bench_run.main(argv)
            except SystemExit as exc:
                result.exit_code = exc.code if isinstance(exc.code, int) else 1
                result.error = exc
            except BaseException as exc:  # noqa: BLE001 - recorded, asserted by the test
                result.error = exc
        result.stdout, result.stderr = out.getvalue(), err.getvalue()
        return result
    finally:
        mp.undo()


def _live_argv(
    base: Path,
    kit: Kit,
    manifest: Path,
    route: str,
    *,
    variant: str = "none",
    seeds: str = "1",
    max_total: int = 16000,
    grant: bool = True,
    executable: bool = True,
    extra: tuple[str, ...] = (),
) -> list[str]:
    argv = [
        "--suite",
        "memory",
        "--decision-mode",
        "live",
        "--decision-route",
        route,
        "--task-manifest",
        str(manifest),
        "--variant",
        variant,
        "--seeds",
        seeds,
        "--max-total-tokens",
        str(max_total),
        "--output",
        str(base / "out"),
    ]
    if grant:
        argv += ["--allow-live-route", route]
    if executable:
        argv += ["--provider-executable", str(kit.exe)]
    return [*argv, *extra]


def _live(
    base: Path,
    route: str = _CODEX_ROUTE,
    *,
    manifest_obj: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
    plan: dict[str, Any] | None = None,
    agents_md: str | None = None,
    capture_tmp: bool = False,
    **argv_kwargs: Any,
) -> RunResult:
    base.mkdir(parents=True, exist_ok=True)
    if manifest_path is None:
        manifest_path = _write_manifest(
            base / "manifest.json",
            manifest_obj if manifest_obj is not None else _manifest_obj(),
        )
    fmt = _FORMAT_OF_ROUTE[route]
    return _run(
        base,
        lambda kit: _live_argv(base, kit, manifest_path, route, **argv_kwargs),
        plan if plan is not None else _plan(fmt),
        agents_md=agents_md,
        capture_tmp=capture_tmp,
    )


def _component(
    base: Path,
    manifest_obj: dict[str, Any] | None = None,
    *,
    manifest_path: Path | None = None,
    variant: str = "current",
    extra: tuple[str, ...] = (),
    out_dir: Path | None = None,
) -> RunResult:
    base.mkdir(parents=True, exist_ok=True)
    if manifest_path is None:
        manifest_path = _write_manifest(
            base / "manifest.json",
            manifest_obj if manifest_obj is not None else _manifest_obj(),
        )
    out = out_dir or (base / "out")
    return _run(
        base,
        lambda kit: [
            "--suite",
            "memory",
            "--task-manifest",
            str(manifest_path),
            "--variant",
            variant,
            "--output",
            str(out),
            *extra,
        ],
        _plan("codex"),
    )


def _assert_rejected(res: RunResult, code: str, *, base: Path) -> None:
    assert res.error is None, repr(res.error)
    assert res.exit_code == 1, f"exit={res.exit_code} stderr={res.stderr}"
    assert f"Memory suite error: {code}" in res.stderr, res.stderr
    assert not res.out_dir.exists(), "rejected run created --output"
    assert list((base / "tmp").glob("memory-suite-*")) == [], "workspace left behind"
    assert res.kit.spawns == [], "provider spawned before the rejection"
    assert not res.kit.log_path.exists(), "provider ran before the rejection"


# --------------------------------------------------------------------------
# Shared live runs (one per route / scenario, computed once per module)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def happy_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, RunResult]:
    runs: dict[str, RunResult] = {}
    for key, route in (("claude", _CLAUDE_ROUTE), ("codex", _CODEX_ROUTE)):
        base = tmp_path_factory.mktemp(f"happy-{key}")
        runs[key] = _live(base, route)
        shutil.rmtree(base / "home", ignore_errors=True)
    return runs


@pytest.fixture(scope="module")
def dataset_history_run(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    base = tmp_path_factory.mktemp("dataset-history")
    res = _live(
        base,
        _CODEX_ROUTE,
        plan=_plan("codex", rules=_only("lme-q-001")),
        variant="current",
    )
    shutil.rmtree(base / "home", ignore_errors=True)
    return res


# ==========================================================================
# Provider output parsing (D13a): Codex and Claude failure cells
# ==========================================================================

_TS = {"type": "thread.started", "thread_id": _THREAD_ID}
_TURN = {"type": "turn.started"}


def _msg(text: str, item_id: str = "item_0") -> dict[str, Any]:
    return {
        "type": "item.completed",
        "item": {"id": item_id, "type": "agent_message", "text": text},
    }


def _done(usage: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "turn.completed", "usage": usage or _usage("codex")}


_VALID_TEXT = json.dumps({"kind": "answer", "text": "x"})


def _codex_failure_rules(cell: str) -> list[dict[str, Any]]:
    """Rules making every decision call (dataset and episode) fail as `cell`."""
    both = {"decision_kind": ["answer", "episode"]}
    if cell == "no_agent_message":
        return [_PREFLIGHT_NORMAL, _rule(both, events=[_TS, _TURN, _done()])]
    if cell == "two_agent_messages":
        return [
            _PREFLIGHT_NORMAL,
            _rule(
                both,
                events=[
                    _TS,
                    _TURN,
                    _msg(_VALID_TEXT),
                    _msg(_VALID_TEXT, "item_1"),
                    _done(),
                ],
            ),
        ]
    if cell == "missing_turn_completed":
        return [_PREFLIGHT_NORMAL, _rule(both, events=[_TS, _TURN, _msg(_VALID_TEXT)])]
    if cell == "unsupported_event":
        return [
            _PREFLIGHT_NORMAL,
            _rule(
                both,
                events=[
                    _TS,
                    _TURN,
                    {"type": "weird.event"},
                    _msg(_VALID_TEXT),
                    _done(),
                ],
            ),
        ]
    if cell == "non_json_line":
        return [_PREFLIGHT_NORMAL, _rule(both, extra_lines=["this line is not json"])]
    if cell == "nonzero_exit":
        return [_PREFLIGHT_NORMAL, _rule(both, exit=1)]
    if cell == "malformed_decision_json":
        return [_PREFLIGHT_NORMAL, _rule(both, text="this is not json")]
    if cell == "unknown_decision_field":
        return [
            _PREFLIGHT_NORMAL,
            _rule(
                {"decision_kind": "answer"},
                decision={"kind": "answer", "text": "x", "extra": 1},
            ),
            _rule(
                {"decision_kind": "episode"},
                decision={"kind": "submit", "final": "x", "extra": 1},
            ),
        ]
    if cell == "turn_failed":
        return [
            _PREFLIGHT_NORMAL,
            _rule(
                both,
                events=[
                    _TS,
                    _TURN,
                    {"type": "turn.failed", "error": {"message": "boom"}},
                ],
            ),
        ]
    if cell == "error_event":
        return [
            _PREFLIGHT_NORMAL,
            _rule(both, events=[_TS, {"type": "error", "message": "boom"}]),
        ]
    raise AssertionError(cell)


_CODEX_FAILURE_REASON = {
    "non_json_line": "unsupported_event",
    "turn_failed": "provider_error",
    "error_event": "provider_error",
}


@pytest.mark.parametrize(
    "cell",
    [
        "no_agent_message",
        "two_agent_messages",
        "missing_turn_completed",
        "unsupported_event",
        "non_json_line",
        "nonzero_exit",
        "malformed_decision_json",
        "unknown_decision_field",
        "turn_failed",
        "error_event",
    ],
)
def test_codex_output_failures_fail_case(cell: str, tmp_path: Path) -> None:
    expected = _CODEX_FAILURE_REASON.get(cell, cell)
    res = _live(
        tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=_codex_failure_rules(cell))
    ).ran()
    records = res.records
    assert len(records) == 5
    for record in records:
        assert record["passed"] is False, record["case_id"]
        assert record["reason"] == expected, (record["case_id"], record["reason"])
        assert record["harness_completed"] is False, record["case_id"]
    aggregate = res.report["aggregate"]
    assert aggregate["total"] == 5 and aggregate["passed"] == 0
    assert aggregate["failed_by_reason"][expected] == 5


def _claude_failure_rules(cell: str) -> list[dict[str, Any]]:
    both = {"decision_kind": ["answer", "episode"]}
    if cell == "is_error_true":
        return [_PREFLIGHT_NORMAL, _rule(both, patch={"is_error": True})]
    if cell == "non_success_subtype":
        return [_PREFLIGHT_NORMAL, _rule(both, patch={"subtype": "error_max_turns"})]
    if cell == "missing_result":
        return [_PREFLIGHT_NORMAL, _rule(both, patch={"result": None})]
    if cell == "non_json_stdout":
        return [_PREFLIGHT_NORMAL, _rule(both, stdout="plain text, not json\n")]
    if cell == "nonzero_exit":
        return [_PREFLIGHT_NORMAL, _rule(both, exit=1)]
    raise AssertionError(cell)


@pytest.mark.parametrize(
    "cell",
    [
        "is_error_true",
        "non_success_subtype",
        "missing_result",
        "non_json_stdout",
        "nonzero_exit",
    ],
)
def test_claude_output_failures_fail_case(cell: str, tmp_path: Path) -> None:
    res = _live(
        tmp_path, _CLAUDE_ROUTE, plan=_plan("claude", rules=_claude_failure_rules(cell))
    ).ran()
    records = res.records
    assert len(records) == 5
    for record in records:
        assert record["passed"] is False, record["case_id"]
        assert record["reason"] == cell, (record["case_id"], record["reason"])
    assert res.report["aggregate"]["failed_by_reason"][cell] == 5


# --------------------------------------------------------------------------
# Direct `run_memory_decision` helpers
# --------------------------------------------------------------------------


def _direct_request(kind: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "decision_kind": kind,
        "case_id": "direct",
        "task": "What is the answer?",
        "step": 0,
        "history": [],
        "permitted_actions": ["answer"]
        if kind == "answer"
        else ["verify_attempt", "submit"],
        "acceptance": {"behavior_ids": [], "required_commands": [], "handoff": None},
    }


def _direct(
    kit: Kit,
    *,
    route: str = _CODEX_ROUTE,
    kind: str = "dataset_answer",
    root: Path | None = None,
    workspace: Path | None = None,
    budget: Any = None,
    timeout_s: float = 30.0,
    request: dict[str, Any] | None = None,
) -> Any:
    decision_route = providers.resolve_decision_route(
        route, allow_live_route=[route], provider_executable=kit.exe
    )
    ws = workspace if workspace is not None else kit.base / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    if root is None:
        root = ws / "case"
        root.mkdir(exist_ok=True)
    if budget is None:
        budget = providers.DecisionBudget(
            max_total_tokens=16000, output_reserve_tokens=1024, route_overhead_tokens=0
        )
    return providers.run_memory_decision(
        request or _direct_request("answer" if kind == "dataset_answer" else "episode"),
        decision_route=decision_route,
        kind=kind,
        root=root,
        workspace_root=ws,
        budget=budget,
        timeout_s=timeout_s,
    )


def _direct_kit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any]
) -> Kit:
    return Kit(tmp_path / "kit", monkeypatch, plan)


def test_codex_lifecycle_events_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        _TS,
        _TURN,
        {
            "type": "item.started",
            "item": {"id": "r1", "type": "reasoning", "text": "thinking"},
        },
        {
            "type": "item.updated",
            "item": {"id": "t1", "type": "todo_list", "items": []},
        },
        {
            "type": "item.completed",
            "item": {"id": "r1", "type": "reasoning", "text": "thought"},
        },
        {
            "type": "item.completed",
            "item": {"id": "t1", "type": "todo_list", "items": []},
        },
        {
            "type": "item.completed",
            "item": {"id": "e1", "type": "error", "message": "warning"},
        },
        _msg(json.dumps({"kind": "answer", "text": "ok"})),
        _done(),
    ]
    kit = _direct_kit(
        tmp_path, monkeypatch, _plan("codex", rules=[_rule({}, events=events)])
    )
    result = _direct(kit)
    assert result.reason is None
    assert result.tool_items == 0
    assert result.model_tokens == 110


_TOOL_ITEM_TYPES = [
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "collab_tool_call",
    "web_search",
]


@pytest.mark.parametrize(
    "cell",
    [
        *[f"codex_{t}" for t in _TOOL_ITEM_TYPES],
        "claude_num_turns_2",
        "codex_episode_allowed",
        "codex_unknown_item_type",
    ],
)
def test_answer_decision_tool_use_rejected(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def tool_item(item_type: str) -> dict[str, Any]:
        return {
            "type": "item.completed",
            "item": {"id": "tool_1", "type": item_type, "status": "completed"},
        }

    answer_text = json.dumps({"kind": "answer", "text": "ok"})
    submit_text = json.dumps({"kind": "submit", "final": "ok"})
    if cell == "claude_num_turns_2":
        kit = _direct_kit(
            tmp_path, monkeypatch, _plan("claude", rules=[_rule({}, num_turns=2)])
        )
        result = _direct(kit, route=_CLAUDE_ROUTE)
        assert result.reason == "decision_used_tools"
        return
    if cell == "codex_episode_allowed":
        events = [
            _TS,
            _TURN,
            tool_item("command_execution"),
            _msg(submit_text),
            _done(),
        ]
        kit = _direct_kit(
            tmp_path, monkeypatch, _plan("codex", rules=[_rule({}, events=events)])
        )
        result = _direct(kit, kind="episode")
        assert result.reason is None
        assert result.tool_items == 1
        return
    item_type = cell.removeprefix("codex_")
    events = [_TS, _TURN, tool_item(item_type), _msg(answer_text), _done()]
    kit = _direct_kit(
        tmp_path, monkeypatch, _plan("codex", rules=[_rule({}, events=events)])
    )
    result = _direct(kit)
    if cell == "codex_unknown_item_type":
        assert result.reason == "unsupported_event"
    else:
        assert result.reason == "decision_used_tools"
        assert result.tool_items == 1


@pytest.mark.parametrize(
    ("kind", "text", "expected"),
    [
        pytest.param(
            "dataset_answer",
            json.dumps({"kind": "answer", "text": "ok"}),
            None,
            id="answer_plain",
        ),
        pytest.param(
            "dataset_answer",
            "```json\n" + json.dumps({"kind": "answer", "text": "ok"}) + "\n```",
            None,
            id="answer_one_fence",
        ),
        pytest.param(
            "dataset_answer",
            "```\n" + json.dumps({"kind": "answer", "text": "ok"}) + "\n```",
            None,
            id="answer_bare_fence",
        ),
        pytest.param(
            "dataset_answer",
            "```json\n```json\n{}\n```\n```",
            "malformed_decision_json",
            id="answer_two_fences",
        ),
        pytest.param(
            "dataset_answer",
            "```json\n" + json.dumps({"kind": "answer", "text": "ok"}),
            "malformed_decision_json",
            id="answer_unterminated_fence",
        ),
        pytest.param(
            "dataset_answer",
            json.dumps(["not", "a", "dict"]),
            "malformed_decision_json",
            id="answer_list",
        ),
        pytest.param(
            "dataset_answer",
            '{"kind": "answer", "text": NaN}',
            "malformed_decision_json",
            id="answer_nan_constant",
        ),
        pytest.param(
            "dataset_answer",
            json.dumps({"kind": "answer", "text": 7}),
            "malformed_decision_json",
            id="answer_non_string_text",
        ),
        pytest.param(
            "dataset_answer",
            json.dumps({"kind": "answer"}),
            "malformed_decision_json",
            id="answer_missing_text",
        ),
        pytest.param(
            "dataset_answer",
            json.dumps({"kind": "other", "text": "x"}),
            "malformed_decision_json",
            id="answer_other_kind",
        ),
        pytest.param(
            "dataset_answer",
            json.dumps({"kind": "answer", "text": "x", "extra": 1}),
            "unknown_decision_field",
            id="answer_extra_field",
        ),
        pytest.param(
            "dataset_answer",
            json.dumps({"kind": "action"}),
            "action_not_permitted",
            id="answer_given_action",
        ),
        pytest.param(
            "dataset_answer",
            json.dumps({"kind": "submit"}),
            "action_not_permitted",
            id="answer_given_submit",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "submit", "final": {"a": [1, 2]}}),
            None,
            id="episode_submit",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "action", "operation": "verify_attempt", "kwargs": {}}),
            None,
            id="episode_action",
        ),
        pytest.param(
            "episode",
            json.dumps(
                {
                    "kind": "action",
                    "operation": "verify_attempt",
                    "kwargs": {},
                    "extra": 1,
                }
            ),
            "unknown_decision_field",
            id="episode_action_extra_field",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "action", "operation": "verify_attempt"}),
            "malformed_decision_json",
            id="episode_action_missing_kwargs",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "action", "operation": 5, "kwargs": {}}),
            "malformed_decision_json",
            id="episode_action_operation_not_str",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "action", "operation": "x", "kwargs": []}),
            "malformed_decision_json",
            id="episode_action_kwargs_not_dict",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "submit", "final": 1, "extra": 1}),
            "unknown_decision_field",
            id="episode_submit_extra_field",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "submit"}),
            "malformed_decision_json",
            id="episode_submit_missing_final",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "answer", "text": "x"}),
            "action_not_permitted",
            id="episode_given_answer",
        ),
        pytest.param(
            "episode",
            json.dumps({"kind": "other"}),
            "malformed_decision_json",
            id="episode_other_kind",
        ),
    ],
)
def test_decision_text_parse_rows(
    kind: str,
    text: str,
    expected: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kit = _direct_kit(
        tmp_path, monkeypatch, _plan("codex", rules=[_rule({}, text=text)])
    )
    result = _direct(kit, kind=kind)
    assert result.reason == expected


@pytest.mark.parametrize(
    ("route", "usage", "expected"),
    [
        pytest.param(
            _CLAUDE_ROUTE,
            _usage("claude", 100, 10, cache_creation=0, cache_read=5000),
            5110,
            id="claude",
        ),
        pytest.param(
            _CODEX_ROUTE, _usage("codex", 5100, 10, cached=5000), 5110, id="codex"
        ),
    ],
)
def test_usage_counts_cache_tokens(
    route: str,
    usage: dict[str, Any],
    expected: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kit = _direct_kit(
        tmp_path, monkeypatch, _plan(_FORMAT_OF_ROUTE[route], usage=usage)
    )
    result = _direct(kit, route=route)
    assert result.reason is None
    assert result.model_tokens == expected


@pytest.mark.parametrize(
    "cell",
    [
        pytest.param("claude_absent", id="claude_absent"),
        pytest.param("claude_non_int", id="claude_non_int"),
        pytest.param("claude_negative", id="claude_negative"),
        pytest.param("claude_missing_counter", id="claude_missing_counter"),
        pytest.param("codex_absent", id="codex_absent"),
        pytest.param("codex_bool", id="codex_bool"),
        pytest.param("codex_missing_output", id="codex_missing_output"),
    ],
)
def test_missing_or_ill_typed_usage_is_unavailable(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fmt, _, form = cell.partition("_")
    route = _CLAUDE_ROUTE if fmt == "claude" else _CODEX_ROUTE
    usage: Any = _usage(fmt)
    if form == "absent":
        usage = None
    elif form == "non_int":
        usage["input_tokens"] = "100"
    elif form == "negative":
        usage["output_tokens"] = -1
    elif form == "bool":
        usage["input_tokens"] = True
    elif form == "missing_counter":
        del usage["cache_read_input_tokens"]
    elif form == "missing_output":
        del usage["output_tokens"]
    kit = _direct_kit(tmp_path, monkeypatch, _plan(fmt, usage=usage))
    result = _direct(kit, route=route)
    assert result.reason == "provider_usage_unavailable"


@pytest.mark.parametrize("cell", ["timeout", "output_too_large"])
def test_decision_timeout_and_output_bound(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if cell == "timeout":
        kit = _direct_kit(
            tmp_path, monkeypatch, _plan("codex", rules=[_rule({}, sleep=20)])
        )
        result = _direct(kit, timeout_s=1.0)
        assert result.reason == "timeout"
    else:
        kit = _direct_kit(
            tmp_path,
            monkeypatch,
            _plan("codex", rules=[_rule({}, stdout="", pad_stdout=1_048_577)]),
        )
        result = _direct(kit)
        assert result.reason == "output_too_large"


def test_output_at_the_bound_is_not_too_large(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _direct_kit(
        tmp_path, monkeypatch, _plan("codex", rules=[_rule({}, stderr="e" * 1_048_000)])
    )
    result = _direct(kit)
    assert result.reason is None


# ==========================================================================
# Containment, budgets and route resolution (direct)
# ==========================================================================


def test_decision_subprocess_uses_contained_fixture_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = [
        _rule({"decision_kind": "episode"}, decision={"kind": "submit", "final": "x"})
    ]
    kit = _direct_kit(
        tmp_path, monkeypatch, _plan("codex", answers={"direct": "ok"}, rules=rules)
    )
    ws = tmp_path / "ws"
    episode_root = ws / "episode-root"
    episode_root.mkdir(parents=True)
    (episode_root / "marker.txt").write_text("fixture", encoding="utf-8")
    dataset_root = ws / "dataset-root"
    dataset_root.mkdir()

    first = _direct(kit, kind="episode", root=episode_root, workspace=ws)
    second = _direct(kit, kind="dataset_answer", root=dataset_root, workspace=ws)
    assert first.reason is None and second.reason is None
    episode_call, dataset_call = kit.decisions
    assert Path(episode_call["cwd"]).resolve() == episode_root.resolve()
    assert "marker.txt" in episode_call["listdir"]
    assert (
        Path(dataset_call["cwd"]).resolve() == (dataset_root / "decision-cwd").resolve()
    )
    assert dataset_call["listdir"] == []
    for call in (episode_call, dataset_call):
        assert Path(call["cwd"]).resolve() != Path.cwd().resolve()
        assert "pyproject.toml" not in call["listdir"]
    assert len(kit.decision_spawns) == 2
    for spawn in kit.decision_spawns:
        _assert_spawn_contract(spawn)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        pytest.param(
            "symlink_root",
            "root_not_contained",
            id="symlink_root",
            marks=pytest.mark.posix_only,
        ),
        pytest.param("foreign_root", "root_not_contained", id="foreign_root"),
        pytest.param("missing_root", "fixture_missing", id="missing_root"),
        pytest.param("workspace_itself", "root_not_contained", id="workspace_itself"),
        pytest.param(
            "symlink_component",
            "root_not_contained",
            id="symlink_component",
            marks=pytest.mark.posix_only,
        ),
    ],
)
def test_decision_root_containment_rows(
    cell: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _direct_kit(tmp_path, monkeypatch, _plan("codex"))
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if cell == "symlink_root":
        root = ws / "link"
        os.symlink(outside, root)
    elif cell == "foreign_root":
        root = outside
    elif cell == "missing_root":
        root = ws / "never-built"
    elif cell == "workspace_itself":
        root = ws
    else:
        os.symlink(outside, ws / "hop")
        (outside / "inner").mkdir()
        root = ws / "hop" / "inner"
    result = _direct(kit, root=root, workspace=ws)
    assert result.reason == expected
    assert kit.spawns == []
    assert not kit.log_path.exists()


@pytest.mark.parametrize(
    "cell", ["prompt_over_budget", "already_spent", "reserve_alone_over"]
)
def test_decision_admission_refuses_spawn(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _direct_kit(tmp_path, monkeypatch, _plan("codex"))
    if cell == "prompt_over_budget":
        budget = providers.DecisionBudget(
            max_total_tokens=50, output_reserve_tokens=0, route_overhead_tokens=0
        )
    elif cell == "already_spent":
        budget = providers.DecisionBudget(
            max_total_tokens=16000,
            output_reserve_tokens=0,
            route_overhead_tokens=0,
            model_tokens=16000,
        )
    else:
        budget = providers.DecisionBudget(
            max_total_tokens=1000, output_reserve_tokens=1000, route_overhead_tokens=0
        )
    result = _direct(kit, budget=budget)
    assert result.reason == "budget_exhausted"
    assert kit.spawns == []
    assert not kit.log_path.exists()


def test_decision_budget_admits_and_charges() -> None:
    budget = providers.DecisionBudget(
        max_total_tokens=1000, output_reserve_tokens=100, route_overhead_tokens=50
    )
    assert budget.admits(850) is True
    assert budget.admits(851) is False
    assert budget.charge(400) is True
    assert budget.model_tokens == 400
    assert budget.admits(450) is True
    assert budget.admits(451) is False
    assert budget.charge(600) is True
    assert budget.charge(1) is False
    assert budget.model_tokens == 1001


def test_presence_route_cannot_decide(tmp_path: Path) -> None:
    for route_id in (
        "antigravity-cli-presence",
        "zai-claude-code-live",
        "antigravity-agy-oauth-cli-live",
        "deepseek-openai-api-live",
        "openai-gpt-4o-fixture",
        "no-such-route",
    ):
        with pytest.raises(FixtureError) as caught:
            providers.resolve_decision_route(
                route_id, allow_live_route=[route_id], provider_executable=None
            )
        assert _code(caught.value) == "not_a_decision_route", route_id
        with pytest.raises(FixtureError) as ungranted:
            providers.resolve_decision_route(
                route_id, allow_live_route=[], provider_executable=None
            )
        assert _code(ungranted.value) == "not_a_decision_route", route_id


def test_live_mode_rejects_missing_route_grant(tmp_path: Path) -> None:
    res = _live(tmp_path, _CLAUDE_ROUTE, grant=False)
    _assert_rejected(res, "live_route_not_granted", base=tmp_path)
    other = _live(
        tmp_path / "other",
        _CLAUDE_ROUTE,
        grant=False,
        extra=("--allow-live-route", _CODEX_ROUTE),
    )
    _assert_rejected(other, "live_route_not_granted", base=tmp_path / "other")


def test_decision_route_resolution_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _direct_kit(tmp_path, monkeypatch, _plan("codex"))
    providers.resolve_decision_route(
        _CODEX_ROUTE, allow_live_route=[_CODEX_ROUTE], provider_executable=kit.exe
    )
    assert kit.spawns == [], "resolution must never spawn"
    assert not kit.log_path.exists()
    with pytest.raises(FixtureError) as ungranted:
        providers.resolve_decision_route(
            _CODEX_ROUTE, allow_live_route=[], provider_executable=kit.exe
        )
    assert _code(ungranted.value) == "live_route_not_granted"
    with pytest.raises(FixtureError) as wrong_grant:
        providers.resolve_decision_route(
            _CODEX_ROUTE, allow_live_route=[_CLAUDE_ROUTE], provider_executable=kit.exe
        )
    assert _code(wrong_grant.value) == "live_route_not_granted"
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(FixtureError) as unresolved:
        providers.resolve_decision_route(
            _CODEX_ROUTE, allow_live_route=[_CODEX_ROUTE], provider_executable=None
        )
    assert _code(unresolved.value) == "executable_not_found"


@pytest.mark.parametrize(
    "cell",
    [
        pytest.param("missing_executable", id="missing_executable"),
        pytest.param("directory_executable", id="directory_executable"),
        pytest.param(
            "not_executable", id="not_executable", marks=pytest.mark.posix_only
        ),
        pytest.param("windows_cmd_shim", id="windows_cmd_shim"),
    ],
)
def test_decision_executable_resolution(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if cell == "windows_cmd_shim":
        shim = providers._is_windows_shell_shim
        assert shim(tmp_path / "fake.cmd", os_name="nt") is True
        assert shim(tmp_path / "fake.BAT", os_name="nt") is True
        assert shim(tmp_path / "fake.cmd", os_name="posix") is False
        assert shim(tmp_path / "fake.exe", os_name="nt") is False
        bare = tmp_path / "fake"
        bare.write_text("", encoding="utf-8")
        assert shim(bare, os_name="nt") is False
        (tmp_path / "fake.cmd").write_text("", encoding="utf-8")
        assert shim(bare, os_name="nt") is True
        assert shim(bare, os_name="posix") is False
        return
    target = tmp_path / "no-such-provider"
    if cell == "directory_executable":
        target = tmp_path / "a-directory"
        target.mkdir()
    elif cell == "not_executable":
        target = tmp_path / "plain-file"
        target.write_text("not executable", encoding="utf-8")
        target.chmod(0o644)
    manifest = _write_manifest(tmp_path / "manifest.json", _manifest_obj())
    res = _run(
        tmp_path,
        lambda kit: [
            *_live_argv(tmp_path, kit, manifest, _CODEX_ROUTE, executable=False),
            "--provider-executable",
            str(target),
        ],
        _plan("codex"),
    )
    _assert_rejected(res, "executable_not_found", base=tmp_path)


@pytest.mark.parametrize(
    ("cell", "argv_extra", "code"),
    [
        pytest.param(
            "route_without_live",
            ["--decision-route", _CODEX_ROUTE],
            "decision_route_requires_live_mode",
            id="route_without_live",
        ),
        pytest.param(
            "live_without_route",
            ["--decision-mode", "live"],
            "live_requires_decision_route",
            id="live_without_route",
        ),
        pytest.param(
            "live_without_manifest",
            [
                "--decision-mode",
                "live",
                "--decision-route",
                _CODEX_ROUTE,
                "--allow-live-route",
                _CODEX_ROUTE,
            ],
            "live_requires_task_manifest",
            id="live_without_manifest",
        ),
        pytest.param(
            "live_with_scenario_suite",
            ["--suite", "scenario", "--decision-mode", "live"],
            "decision_flags_require_memory_suite",
            id="live_with_scenario_suite",
        ),
        pytest.param(
            "route_with_scenario_suite",
            ["--suite", "scenario", "--decision-route", _CODEX_ROUTE],
            "decision_flags_require_memory_suite",
            id="route_with_scenario_suite",
        ),
        pytest.param(
            "manifest_with_scenario_suite",
            ["--suite", "scenario", "--task-manifest", "manifest.json"],
            "decision_flags_require_memory_suite",
            id="manifest_with_scenario_suite",
        ),
    ],
)
def test_decision_flag_combinations_rejected(
    cell: str, argv_extra: list[str], code: str, tmp_path: Path
) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", _manifest_obj())
    argv_extra = [str(manifest) if a == "manifest.json" else a for a in argv_extra]
    needs_suite = "--suite" not in argv_extra
    res = _run(
        tmp_path,
        lambda kit: [
            *(["--suite", "memory"] if needs_suite else []),
            *argv_extra,
            *(
                ["--task-manifest", str(manifest)]
                if cell in {"route_without_live", "live_without_route"}
                else []
            ),
            "--output",
            str(tmp_path / "out"),
        ],
        _plan("codex"),
    )
    _assert_rejected(res, code, base=tmp_path)


def test_runner_help_both_forms_list_decision_flags(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "USERPROFILE": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(tmp_path / "xdg"),
        "LOCALAPPDATA": str(tmp_path / "localappdata"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    forms = {
        "script": [
            sys.executable,
            str(_REPO / "scripts" / "benchmarks" / "run.py"),
            "--help",
        ],
        "module": [sys.executable, "-m", "scripts.benchmarks.run", "--help"],
    }
    for name, argv in forms.items():
        proc = subprocess.run(
            argv,
            cwd=_REPO,
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
        assert proc.returncode == 0, (name, proc.stderr[-800:])
        for flag in ("--decision-mode", "--decision-route", "--task-manifest"):
            assert flag in proc.stdout, (name, flag)


def test_parser_decision_flag_defaults() -> None:
    args = bench_run.build_parser().parse_args(["--suite", "memory"])
    assert args.decision_mode == "component"
    assert args.decision_route is None
    assert args.task_manifest is None
    live = bench_run.build_parser().parse_args(
        [
            "--decision-mode",
            "live",
            "--decision-route",
            "r",
            "--task-manifest",
            "m.json",
        ]
    )
    assert live.decision_mode == "live" and live.decision_route == "r"
    assert live.task_manifest == Path("m.json")
    with pytest.raises(SystemExit):
        bench_run.build_parser().parse_args(["--decision-mode", "bogus"])


def test_component_mode_default_and_labeled(tmp_path: Path) -> None:
    res = _run(
        tmp_path,
        lambda kit: ["--suite", "memory", "--output", str(tmp_path / "out")],
        _plan("codex"),
    ).ran()
    report = res.report
    assert report["decision_mode"] == "component"
    per_variant = report["cross_variant_comparison"]["per_variant"]
    assert set(per_variant) == set(bench_run._MEMORY_VARIANTS)
    for variant, entry in per_variant.items():
        assert entry["score_kind"] == "harness_completion", variant
    assert any("was not exercised" in b for b in report["blockers"])
    assert res.kit.spawns == []


# ==========================================================================
# Strict task manifest
# ==========================================================================


def _load(path: Path) -> dict[str, Any]:
    return bm.load_task_manifest(path)


def test_shipped_task_manifest_baseline_frozen() -> None:
    manifest = _load(_SHIPPED_MANIFEST)
    # 72-T08 appends the frozen `p72-` cases and the two `phase72_` keys; the five
    # baseline cases stay byte-for-byte what 75-T02 shipped.
    assert set(manifest) == {
        "schema_version",
        "cases",
        "declared",
        "phase75_family_coverage",
        "phase72_cases_sha256",
        "phase72_embedding",
    }
    assert manifest["schema_version"] == 1
    baseline = [c for c in manifest["cases"] if not c["id"].startswith("p72-")]
    assert len(manifest["cases"]) - len(baseline) == 24
    assert sorted(baseline, key=lambda c: c["id"]) == sorted(
        _baseline_cases(), key=lambda c: c["id"]
    )
    assert _digest(baseline) == _BASELINE_DIGEST
    assert bm.BASELINE_CASES_SHA256 == _BASELINE_DIGEST
    assert manifest["declared"] == [
        {"family": f, "case_family": c} for f, c in _PHASE75_DECLARED
    ]
    assert manifest["phase75_family_coverage"] == {
        "open": {
            "families": [f for f, c in _PHASE75_DECLARED if c is None],
            "variants": list(_PHASE75_OPEN_VARIANTS),
        }
    }
    assert tuple(bm.PHASE75_DECLARED) == _PHASE75_DECLARED
    assert tuple(bm.PHASE75_OPEN_VARIANTS) == _PHASE75_OPEN_VARIANTS


def test_manifest_baseline_plus_valid_extension(tmp_path: Path) -> None:
    baseline_only = _component(tmp_path / "base-only", _manifest_obj()).ran()
    task_manifest = baseline_only.report["task_manifest"]
    assert task_manifest["cases_sha256"] == _BASELINE_DIGEST
    assert task_manifest["baseline_cases_sha256"] == _BASELINE_DIGEST
    assert task_manifest.get("phase72_cases_sha256") is None
    assert task_manifest["case_count"] == 5

    extended = _manifest_obj((_p72_dataset_case(),))
    path = _write_manifest(tmp_path / "extended.json", extended)
    loaded = _load(path)
    assert len(loaded["cases"]) == 6
    res = _component(tmp_path / "extended", manifest_path=path).ran()
    task_manifest = res.report["task_manifest"]
    assert task_manifest["case_count"] == 6
    assert task_manifest["cases_sha256"] == _digest(extended["cases"])
    assert task_manifest["cases_sha256"] != _BASELINE_DIGEST
    assert task_manifest["baseline_cases_sha256"] == _BASELINE_DIGEST
    assert task_manifest["phase72_cases_sha256"] == extended["phase72_cases_sha256"]
    assert res.report["aggregate"]["total"] == 6

    missing_digest = _write_manifest(
        tmp_path / "no-digest.json",
        _manifest_obj((_p72_dataset_case(),), with_p72_digest=False),
    )
    with pytest.raises(FixtureError) as caught:
        _load(missing_digest)
    assert _code(caught.value) == "missing_key"

    wrong_flag = _write_manifest(
        tmp_path / "wrong-flag.json",
        _manifest_obj((_p72_dataset_case(retrieval_required=False),)),
    )
    with pytest.raises(FixtureError) as flagged:
        _load(wrong_flag)
    assert _code(flagged.value) == "invalid_value"

    stale = _manifest_obj((_p72_dataset_case(),))
    stale["phase72_cases_sha256"] = "0" * 64
    with pytest.raises(FixtureError) as mismatch:
        _load(_write_manifest(tmp_path / "stale-digest.json", stale))
    assert _code(mismatch.value) == "phase72_cases_mismatch"

    baseline_flag = _manifest_obj()
    baseline_flag["cases"][0]["retrieval_required"] = True
    with pytest.raises(FixtureError) as baseline_true:
        _load(_write_manifest(tmp_path / "baseline-flag.json", baseline_flag))
    assert _code(baseline_true.value) == "invalid_value"


def test_manifest_phase72_embedding_schema(tmp_path: Path) -> None:
    good = _write_manifest(
        tmp_path / "good.json", _manifest_obj(embedding=dict(_EMBEDDING))
    )
    loaded = _load(good)
    assert loaded["phase72_embedding"] == _EMBEDDING
    res = _component(tmp_path / "good-run", manifest_path=good).ran()
    task_manifest = res.report["task_manifest"]
    assert task_manifest["phase72_embedding"] == _EMBEDDING
    assert task_manifest["cases_sha256"] == _BASELINE_DIGEST
    assert task_manifest.get("phase72_cases_sha256") is None

    def rejected(
        name: str, mutate: Callable[[dict[str, Any]], None], code: str
    ) -> None:
        obj = _manifest_obj(embedding=dict(_EMBEDDING))
        mutate(obj)
        with pytest.raises(FixtureError) as caught:
            _load(_write_manifest(tmp_path / f"{name}.json", obj))
        assert _code(caught.value) == code, name

    rejected(
        "extra_inner_key",
        lambda o: o["phase72_embedding"].update(extra="x"),
        "unknown_key",
    )
    rejected(
        "missing_digest",
        lambda o: o["phase72_embedding"].pop("model_digest"),
        "missing_key",
    )
    rejected(
        "int_model", lambda o: o["phase72_embedding"].update(model=7), "wrong_type"
    )
    rejected(
        "lan_endpoint",
        lambda o: o["phase72_embedding"].update(endpoint="http://10.0.0.1:11434"),
        "invalid_value",
    )
    rejected(
        "upper_digest",
        lambda o: o["phase72_embedding"].update(model_digest="0A109F422B47"),
        "invalid_value",
    )
    rejected(
        "short_digest",
        lambda o: o["phase72_embedding"].update(model_digest="0a109f422b4"),
        "invalid_value",
    )
    rejected(
        "long_digest",
        lambda o: o["phase72_embedding"].update(model_digest="0" * 65),
        "invalid_value",
    )
    rejected(
        "top_level_endpoint",
        lambda o: o.update(embedding_endpoint="http://127.0.0.1:11434"),
        "unknown_key",
    )
    rejected(
        "embedding_not_object",
        lambda o: o.update(phase72_embedding="http://127.0.0.1:11434"),
        "wrong_type",
    )

    absent = _write_manifest(tmp_path / "absent.json", _manifest_obj())
    assert "phase72_embedding" not in _load(absent)

    with_p72 = _write_manifest(
        tmp_path / "p72.json", _manifest_obj((_p72_dataset_case(),))
    )
    hybrid = _component(tmp_path / "hybrid", manifest_path=with_p72, variant="hybrid")
    _assert_rejected(
        hybrid, "hybrid_requires_phase72_embedding", base=tmp_path / "hybrid"
    )
    current = _component(
        tmp_path / "current", manifest_path=with_p72, variant="current"
    ).ran()
    assert current.report["task_manifest"].get("phase72_embedding") is None
    embedded = _write_manifest(
        tmp_path / "p72-embedded.json",
        _manifest_obj((_p72_dataset_case(),), embedding=dict(_EMBEDDING)),
    )
    _component(
        tmp_path / "hybrid-embedded", manifest_path=embedded, variant="hybrid"
    ).ran()


@pytest.mark.parametrize(
    ("endpoint", "model", "digest"),
    [
        pytest.param(
            "http://127.0.0.1:1", "nomic-embed-text", "0a109f422b47", id="port_1"
        ),
        pytest.param(
            "http://127.0.0.1:65535",
            "nomic-embed-text",
            "0a109f422b47",
            id="port_65535",
        ),
        pytest.param(
            "http://[::1]:11434", "nomic-embed-text", "0a109f422b47", id="ipv6_loopback"
        ),
        pytest.param(
            "http://localhost:11434", "nomic-embed-text", "0a109f422b47", id="localhost"
        ),
        pytest.param(
            "http://localhost:11434/",
            "nomic-embed-text",
            "0a109f422b47",
            id="trailing_slash",
        ),
        pytest.param(
            "HTTP://LOCALHOST:11434",
            "nomic-embed-text",
            "0a109f422b47",
            id="upper_case_scheme_host",
        ),
        pytest.param(
            "http://127.0.0.1:11434",
            "nomic-embed-text:latest",
            "0a109f422b47",
            id="model_with_tag",
        ),
        pytest.param(
            "http://127.0.0.1:11434", "nomic-embed-text", "0" * 64, id="digest_64_hex"
        ),
    ],
)
def test_manifest_embedding_accepted_forms(
    endpoint: str, model: str, digest: str, tmp_path: Path
) -> None:
    embedding = {"endpoint": endpoint, "model": model, "model_digest": digest}
    path = _write_manifest(
        tmp_path / "manifest.json", _manifest_obj(embedding=embedding)
    )
    assert _load(path)["phase72_embedding"] == embedding


def test_manifest_altered_baseline_rejected(tmp_path: Path) -> None:
    def altered_budget(obj: dict[str, Any]) -> None:
        obj["cases"][2]["budget"]["max_steps"] = 11

    def removed_case(obj: dict[str, Any]) -> None:
        obj["cases"] = [c for c in obj["cases"] if c["id"] != "lme-q-002"]

    def added_case(obj: dict[str, Any]) -> None:
        extra = copy.deepcopy(obj["cases"][0])
        extra["id"] = "extra-case"
        obj["cases"].append(extra)

    def altered_acceptance(obj: dict[str, Any]) -> None:
        obj["cases"][3]["acceptance"]["handoff"]["content_contains"] = "anything"

    def altered_revision(obj: dict[str, Any]) -> None:
        obj["cases"][2]["fixture_revision"] = "0" * 64

    for name, mutate in (
        ("altered_budget", altered_budget),
        ("removed_case", removed_case),
        ("added_case", added_case),
        ("altered_acceptance", altered_acceptance),
        ("altered_revision", altered_revision),
    ):
        obj = _manifest_obj()
        mutate(obj)
        path = _write_manifest(tmp_path / f"{name}.json", obj)
        with pytest.raises(FixtureError) as caught:
            _load(path)
        assert _code(caught.value) == "baseline_altered", name
        res = _component(tmp_path / name, manifest_path=path)
        _assert_rejected(res, "baseline_altered", base=tmp_path / name)


def test_manifest_post_observation_extension_rejected(tmp_path: Path) -> None:
    out = tmp_path / "shared-out"
    first = _component(
        tmp_path / "run1", _manifest_obj(embedding=dict(_EMBEDDING)), out_dir=out
    ).ran()
    before = first.report_path.read_bytes()
    listing = sorted(p.name for p in out.iterdir())

    extended = _write_manifest(
        tmp_path / "extended.json",
        _manifest_obj((_p72_dataset_case(),), embedding=dict(_EMBEDDING)),
    )
    second = _component(tmp_path / "run2", manifest_path=extended, out_dir=out)
    assert second.exit_code == 1
    assert "Memory suite error: output_manifest_mismatch" in second.stderr
    assert out.joinpath("memory-suite-report.json").read_bytes() == before
    assert sorted(p.name for p in out.iterdir()) == listing

    other_embedding = dict(_EMBEDDING, model_digest="ffffffffffff")
    changed = _write_manifest(
        tmp_path / "changed.json", _manifest_obj(embedding=other_embedding)
    )
    third = _component(tmp_path / "run3", manifest_path=changed, out_dir=out)
    assert third.exit_code == 1
    assert "Memory suite error: output_manifest_mismatch" in third.stderr
    assert out.joinpath("memory-suite-report.json").read_bytes() == before

    dropped = _write_manifest(tmp_path / "dropped.json", _manifest_obj())
    fourth = _component(tmp_path / "run4", manifest_path=dropped, out_dir=out)
    assert fourth.exit_code == 1
    assert "Memory suite error: output_manifest_mismatch" in fourth.stderr
    assert out.joinpath("memory-suite-report.json").read_bytes() == before

    unreadable = tmp_path / "bad-out"
    unreadable.mkdir()
    (unreadable / "memory-suite-report.json").write_text("not json", encoding="utf-8")
    fifth = _component(tmp_path / "run5", _manifest_obj(), out_dir=unreadable)
    assert fifth.exit_code == 1
    assert "Memory suite error: output_manifest_mismatch" in fifth.stderr
    assert (unreadable / "memory-suite-report.json").read_text(
        encoding="utf-8"
    ) == "not json"

    same = _component(
        tmp_path / "run6", _manifest_obj(embedding=dict(_EMBEDDING)), out_dir=out
    )
    assert same.exit_code == 0


# --------------------------------------------------------------------------
# Strict case schema
# --------------------------------------------------------------------------


def _schema_mutations() -> dict[str, tuple[Callable[[dict[str, Any]], None], str]]:
    def missing_key(o: dict[str, Any]) -> None:
        del o["cases"][0]["budget"]

    def unknown_key(o: dict[str, Any]) -> None:
        o["cases"][0]["extra"] = 1

    def nested_unknown_key(o: dict[str, Any]) -> None:
        o["cases"][0]["budget"]["extra"] = 1

    def unknown_evaluator(o: dict[str, Any]) -> None:
        o["cases"][0]["acceptance"]["evaluator"] = "magic"

    def unknown_builder(o: dict[str, Any]) -> None:
        o["cases"][2]["inputs"]["builder"] = "no-such-builder"

    return {
        "missing_key": (missing_key, "missing_key"),
        "unknown_key": (unknown_key, "unknown_key"),
        "nested_unknown_key": (nested_unknown_key, "unknown_key"),
        "unknown_evaluator": (unknown_evaluator, "invalid_value"),
        "unknown_builder": (unknown_builder, "invalid_value"),
    }


@pytest.mark.parametrize(
    "cell",
    [
        "missing_key",
        "unknown_key",
        "nested_unknown_key",
        "unknown_evaluator",
        "unknown_builder",
        "duplicate_object_key",
    ],
)
def test_manifest_case_schema_strict(cell: str, tmp_path: Path) -> None:
    if cell == "duplicate_object_key":
        text = json.dumps(_manifest_obj(), indent=2)
        token = '"max_total_tokens": 16000'
        assert token in text
        path = tmp_path / "manifest.json"
        path.write_text(
            text.replace(token, token + ", " + token, 1) + "\n", encoding="utf-8"
        )
        expected = "invalid_value"
    else:
        mutate, expected = _schema_mutations()[cell]
        obj = _manifest_obj()
        mutate(obj)
        path = _write_manifest(tmp_path / "manifest.json", obj)
    with pytest.raises(FixtureError) as caught:
        _load(path)
    assert _code(caught.value) == expected
    res = _live(tmp_path, _CODEX_ROUTE, manifest_path=path)
    _assert_rejected(res, expected, base=tmp_path)


def test_manifest_top_level_strict(tmp_path: Path) -> None:
    def rejected(
        name: str, mutate: Callable[[dict[str, Any]], None], code: str
    ) -> None:
        obj = _manifest_obj()
        mutate(obj)
        with pytest.raises(FixtureError) as caught:
            _load(_write_manifest(tmp_path / f"{name}.json", obj))
        assert _code(caught.value) == code, name

    rejected("unknown_top_key", lambda o: o.update(extra=1), "unknown_key")
    rejected("missing_declared", lambda o: o.pop("declared"), "missing_key")
    rejected(
        "missing_coverage", lambda o: o.pop("phase75_family_coverage"), "missing_key"
    )
    rejected("missing_cases", lambda o: o.pop("cases"), "missing_key")
    rejected("missing_schema_version", lambda o: o.pop("schema_version"), "missing_key")
    rejected("schema_version_2", lambda o: o.update(schema_version=2), "invalid_value")
    rejected(
        "schema_version_bool", lambda o: o.update(schema_version=True), "wrong_type"
    )
    rejected("schema_version_str", lambda o: o.update(schema_version="1"), "wrong_type")
    rejected("declared_reordered", lambda o: o["declared"].reverse(), "invalid_value")
    rejected(
        "declared_case_family_changed",
        lambda o: o["declared"][1].update(case_family="bug_repair"),
        "invalid_value",
    )
    rejected(
        "coverage_variant_dropped",
        lambda o: o["phase75_family_coverage"]["open"]["variants"].pop(),
        "invalid_value",
    )
    rejected(
        "coverage_family_added",
        lambda o: o["phase75_family_coverage"]["open"]["families"].append("x"),
        "invalid_value",
    )
    rejected("cases_not_list", lambda o: o.update(cases={}), "wrong_type")
    rejected(
        "duplicate_id",
        lambda o: o["cases"].append(copy.deepcopy(o["cases"][0])),
        "invalid_value",
    )
    rejected(
        "variant_not_base",
        lambda o: o["cases"][0].update(variant="other"),
        "invalid_value",
    )
    rejected("bad_id", lambda o: o["cases"][0].update(id="Bad ID"), "invalid_value")
    rejected("bad_kind", lambda o: o["cases"][0].update(kind="other"), "invalid_value")
    rejected(
        "revision_not_hex",
        lambda o: o["cases"][0].update(fixture_revision="z" * 64),
        "invalid_value",
    )
    rejected(
        "grant_unknown",
        lambda o: o["cases"][0].update(grants=["not_a_flag"]),
        "invalid_value",
    )
    rejected(
        "grants_unsorted",
        lambda o: o["cases"][0].update(grants=["network", "cache_write"]),
        "invalid_value",
    )
    rejected(
        "dataset_actions",
        lambda o: o["cases"][0].update(permitted_actions=["answer", "submit"]),
        "invalid_value",
    )
    rejected(
        "dataset_editable",
        lambda o: o["cases"][0].update(editable_paths=["x.py"]),
        "invalid_value",
    )
    rejected(
        "dataset_unknown_section",
        lambda o: o["cases"][0]["inputs"].update(section="swe_bench_verified"),
        "invalid_value",
    )
    rejected(
        "dataset_unknown_record",
        lambda o: o["cases"][0]["inputs"].update(record_id="lme-q-999"),
        "invalid_value",
    )
    rejected(
        "dataset_empty_query",
        lambda o: o["cases"][0]["inputs"].update(query=""),
        "invalid_value",
    )
    rejected(
        "episode_without_submit",
        lambda o: o["cases"][2].update(permitted_actions=["verify_attempt"]),
        "invalid_value",
    )
    rejected(
        "episode_unknown_action",
        lambda o: o["cases"][2].update(permitted_actions=["submit", "teleport"]),
        "invalid_value",
    )
    rejected(
        "episode_duplicate_action",
        lambda o: o["cases"][2].update(permitted_actions=["submit", "submit"]),
        "invalid_value",
    )
    rejected(
        "budget_zero",
        lambda o: o["cases"][0]["budget"].update(max_total_tokens=0),
        "invalid_value",
    )
    rejected(
        "budget_reserve_equals_total",
        lambda o: o["cases"][0]["budget"].update(output_reserve_tokens=16000),
        "invalid_value",
    )
    rejected(
        "budget_steps_zero",
        lambda o: o["cases"][0]["budget"].update(max_steps=0),
        "invalid_value",
    )
    rejected(
        "budget_timeout_over_day",
        lambda o: o["cases"][0]["budget"].update(timeout_s=86401),
        "invalid_value",
    )
    rejected(
        "budget_float",
        lambda o: o["cases"][0]["budget"].update(max_steps=1.5),
        "wrong_type",
    )
    rejected(
        "acceptance_dataset_commands",
        lambda o: o["cases"][0]["acceptance"].update(
            required_commands=_UPLOAD_COMMANDS
        ),
        "invalid_value",
    )
    rejected(
        "acceptance_receipt_no_commands",
        lambda o: o["cases"][2]["acceptance"].update(required_commands=[]),
        "invalid_value",
    )
    rejected(
        "acceptance_command_exit_256",
        lambda o: o["cases"][2]["acceptance"]["required_commands"][0].update(
            expected_exit_code=256
        ),
        "invalid_value",
    )
    rejected(
        "acceptance_command_extra_key",
        lambda o: o["cases"][2]["acceptance"]["required_commands"][0].update(cwd="x"),
        "unknown_key",
    )
    rejected(
        "acceptance_handoff_missing",
        lambda o: o["cases"][3]["acceptance"].update(handoff=None),
        "invalid_value",
    )
    rejected(
        "acceptance_handoff_write_count_0",
        lambda o: o["cases"][3]["acceptance"]["handoff"].update(write_count=0),
        "invalid_value",
    )
    rejected(
        "acceptance_handoff_write_count_101",
        lambda o: o["cases"][3]["acceptance"]["handoff"].update(write_count=101),
        "invalid_value",
    )
    rejected(
        "acceptance_handoff_extra_key",
        lambda o: o["cases"][3]["acceptance"]["handoff"].update(extra=1),
        "unknown_key",
    )
    rejected(
        "acceptance_handoff_empty_contains",
        lambda o: o["cases"][3]["acceptance"]["handoff"].update(content_contains=""),
        "invalid_value",
    )
    rejected(
        "acceptance_handoff_with_commands",
        lambda o: o["cases"][3]["acceptance"].update(
            required_commands=_UPLOAD_COMMANDS
        ),
        "invalid_value",
    )


# --------------------------------------------------------------------------
# G4 trust-boundary rows
# --------------------------------------------------------------------------


def _row_mutate(
    fn: Callable[[dict[str, Any]], None], *, p72: bool = False
) -> Callable[[Path], Path]:
    def build(base: Path) -> Path:
        obj = _manifest_obj((_p72_upload_case(),)) if p72 else _manifest_obj()
        fn(obj)
        if p72:
            p72_cases = [c for c in obj["cases"] if str(c.get("id")).startswith("p72-")]
            obj["phase72_cases_sha256"] = _digest(p72_cases)
        return _write_manifest(base / "manifest.json", obj)

    return build


def _row_embedding(**changes: Any) -> Callable[[Path], Path]:
    def build(base: Path) -> Path:
        obj = _manifest_obj(embedding={**_EMBEDDING, **changes})
        return _write_manifest(base / "manifest.json", obj)

    return build


def _row_endpoint(endpoint: str) -> Callable[[Path], Path]:
    return _row_embedding(endpoint=endpoint)


def _row_raw_bytes(transform: Callable[[bytes], bytes]) -> Callable[[Path], Path]:
    def build(base: Path) -> Path:
        path = base / "manifest.json"
        path.write_bytes(
            transform(json.dumps(_manifest_obj(), indent=2).encode("utf-8"))
        )
        return path

    return build


def _row_raw_text(old: str, new: str) -> Callable[[Path], Path]:
    def build(base: Path) -> Path:
        text = json.dumps(_manifest_obj(), indent=2)
        assert old in text, old
        path = base / "manifest.json"
        path.write_text(text.replace(old, new, 1) + "\n", encoding="utf-8")
        return path

    return build


def _row_symlink(base: Path) -> Path:
    target = _write_manifest(base / "real.json", _manifest_obj())
    link = base / "manifest.json"
    os.symlink(target, link)
    return link


def _row_symlink_loop(base: Path) -> Path:
    link = base / "manifest.json"
    os.symlink("manifest.json", link)
    return link


def _row_missing(base: Path) -> Path:
    return base / "absent-manifest.json"


def _set(path: tuple[Any, ...], value: Any) -> Callable[[dict[str, Any]], None]:
    def apply(obj: dict[str, Any]) -> None:
        node: Any = obj
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return apply


_UPLOAD = 2
_G4_ROWS: list[Any] = [
    pytest.param(
        _row_mutate(_set(("cases", _UPLOAD, "budget", "max_total_tokens"), "16000")),
        "wrong_type",
        id="wrong_type",
    ),
    pytest.param(
        _row_mutate(_set(("cases", _UPLOAD, "budget", "max_steps"), True)),
        "wrong_type",
        id="bool_as_int",
    ),
    pytest.param(
        _row_raw_text('"max_total_tokens": 16000', '"max_total_tokens": 1' + "0" * 400),
        "invalid_value",
        id="huge_int",
    ),
    pytest.param(
        _row_mutate(_set(("cases", _UPLOAD, "budget", "timeout_s"), float("nan"))),
        "invalid_value",
        id="nan",
    ),
    pytest.param(
        _row_mutate(_set(("cases", _UPLOAD, "budget", "timeout_s"), float("inf"))),
        "invalid_value",
        id="inf",
    ),
    pytest.param(
        _row_mutate(
            _set(("cases", _UPLOAD, "inputs", "task"), "Fix upload()\u0000 now")
        ),
        "invalid_value",
        id="nul_task",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 0, "inputs", "query"), "del\u0000ayed")),
        "invalid_value",
        id="nul_query",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 0, "inputs", "query"), "\ud800")),
        "invalid_value",
        id="lone_surrogate_query",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 0, "family"), "long\u0007memeval")),
        "invalid_value",
        id="cc_char",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 0, "family"), "long\u200bmemeval")),
        "invalid_value",
        id="cf_char",
    ),
    pytest.param(
        _row_symlink, "unsafe_path", id="manifest_symlink", marks=pytest.mark.posix_only
    ),
    pytest.param(
        _row_symlink_loop,
        "unsafe_path",
        id="manifest_symlink_loop",
        marks=pytest.mark.posix_only,
    ),
    pytest.param(_row_missing, "manifest_unreadable", id="missing_manifest"),
    pytest.param(
        _row_mutate(_set(("cases", _UPLOAD, "editable_paths"), [123])),
        "wrong_type",
        id="non_path_editable",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 0, "grants"), [["build"]])),
        "wrong_type",
        id="unhashable_grant",
    ),
    pytest.param(
        _row_raw_bytes(lambda b: b.replace(b"upload-repair", b"upload-\xffrepair", 1)),
        "manifest_unreadable",
        id="non_utf8",
    ),
    pytest.param(
        _row_raw_bytes(lambda b: b"\xef\xbb\xbf" + b), "manifest_unreadable", id="bom"
    ),
    pytest.param(
        _row_raw_bytes(lambda b: b[: len(b) // 2]),
        "manifest_unreadable",
        id="truncated_json",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 0, "editable_paths"), ["x.py"])),
        "invalid_value",
        id="dataset_editable_paths",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 5, "editable_paths"), ["/etc/passwd"]), p72=True),
        "unsafe_path",
        id="editable_absolute",
    ),
    pytest.param(
        _row_mutate(_set(("cases", 5, "editable_paths"), ["../upload.py"]), p72=True),
        "unsafe_path",
        id="editable_dotdot",
    ),
    pytest.param(
        _row_mutate(
            _set(("cases", 5, "editable_paths"), ["sub/../../upload.py"]), p72=True
        ),
        "unsafe_path",
        id="editable_nested_dotdot",
    ),
    pytest.param(
        _row_endpoint("https://127.0.0.1:11434"), "invalid_value", id="endpoint_https"
    ),
    pytest.param(
        _row_endpoint("file:///etc/passwd"), "invalid_value", id="endpoint_file"
    ),
    pytest.param(
        _row_endpoint("ftp://127.0.0.1:21"), "invalid_value", id="endpoint_ftp"
    ),
    pytest.param(
        _row_endpoint("data:text/plain,hello"), "invalid_value", id="endpoint_data"
    ),
    pytest.param(
        _row_endpoint("http://u:p@127.0.0.1:11434"),
        "invalid_value",
        id="endpoint_userinfo",
    ),
    pytest.param(
        _row_endpoint("http://localhost.evil.test:11434"),
        "invalid_value",
        id="host_evil_suffix",
    ),
    pytest.param(
        _row_endpoint("http://127.0.0.1.nip.io:11434"),
        "invalid_value",
        id="host_nip_io",
    ),
    pytest.param(_row_endpoint("http://0.0.0.0:11434"), "invalid_value", id="host_any"),
    pytest.param(
        _row_endpoint("http://2130706433:11434"), "invalid_value", id="host_decimal"
    ),
    pytest.param(
        _row_endpoint("http://%31%32%37.0.0.1:11434"),
        "invalid_value",
        id="host_percent",
    ),
    pytest.param(_row_endpoint("http://:11434"), "invalid_value", id="host_empty"),
    pytest.param(_row_endpoint("http://127.0.0.1:0"), "invalid_value", id="port_0"),
    pytest.param(
        _row_endpoint("http://127.0.0.1:65536"), "invalid_value", id="port_65536"
    ),
    pytest.param(_row_endpoint("http://127.0.0.1"), "invalid_value", id="port_missing"),
    pytest.param(
        _row_endpoint("http://127.0.0.1:11434\r"), "invalid_value", id="trailing_cr"
    ),
    pytest.param(
        _row_endpoint("http://127.0.0.1:11434\n"), "invalid_value", id="trailing_lf"
    ),
    pytest.param(
        _row_endpoint("http://127.0.0.1:11434 "), "invalid_value", id="trailing_space"
    ),
    pytest.param(
        _row_endpoint("http://127.0.0.1:11434/api"), "invalid_value", id="endpoint_path"
    ),
    pytest.param(
        _row_endpoint("http://127.0.0.1:11434?x=1"),
        "invalid_value",
        id="endpoint_query",
    ),
    pytest.param(
        _row_endpoint("http://127.0.0.1:11434/#frag"),
        "invalid_value",
        id="endpoint_fragment",
    ),
    pytest.param(_row_embedding(model="a/b"), "invalid_value", id="model_slash"),
    pytest.param(_row_embedding(model="a..b"), "invalid_value", id="model_dotdot"),
    pytest.param(_row_embedding(model="a\u0000b"), "invalid_value", id="model_nul"),
    pytest.param(_row_embedding(model=""), "invalid_value", id="model_empty"),
    pytest.param(
        _row_embedding(model_digest="8FDF8F752F6E"), "invalid_value", id="digest_upper"
    ),
    pytest.param(
        _row_embedding(model_digest="8fdf8f752f6"), "invalid_value", id="digest_short"
    ),
    pytest.param(
        _row_embedding(model_digest=123), "wrong_type", id="embedding_wrong_type"
    ),
]


def _row_fixture_pass(
    editable: str, *, symlink: bool = False
) -> Callable[[Path], tuple[Path, Callable[[pytest.MonkeyPatch], None]]]:
    """A row only the fixture-verification pass can reject: the manifest loads,
    the run is rejected with `unsafe_path` before any provider call."""

    def build(base: Path) -> tuple[Path, Callable[[pytest.MonkeyPatch], None]]:
        obj = _manifest_obj((_p72_upload_case(editable_paths=[editable]),))
        path = _write_manifest(base / "manifest.json", obj)

        def patch(mp: pytest.MonkeyPatch) -> None:
            if not symlink:
                return
            original = bm.EPISODE_BUILDERS["upload-repair"]

            def with_link(root: Path) -> tuple[str, Any]:
                built = original(root)
                os.symlink("upload.py", root / "link.py")
                return built

            mp.setitem(bm.EPISODE_BUILDERS, "upload-repair", with_link)

        return path, patch

    return build


_G4_ROWS.append(
    pytest.param(
        _row_mutate(_set(("cases", 0, "inputs", "corpus_section"), "some_corpus")),
        "invalid_value",
        id="dataset_corpus_section_set",
    )
)
_G4_FIXTURE_PASS_ROWS = [
    pytest.param(
        _row_fixture_pass("link.py", symlink=True),
        "unsafe_path",
        id="editable_symlink",
        marks=pytest.mark.posix_only,
    ),
    pytest.param(
        _row_fixture_pass("Upload.py"), "unsafe_path", id="editable_case_variant"
    ),
    pytest.param(
        _row_fixture_pass("absent.py"), "unsafe_path", id="editable_missing_file"
    ),
    pytest.param(_row_fixture_pass(".git"), "unsafe_path", id="editable_directory"),
]
_G4_ROWS.extend(_G4_FIXTURE_PASS_ROWS)


@pytest.mark.parametrize(("build", "code"), _G4_ROWS)
def test_evaluator_g4_manifest_fields(
    build: Callable[[Path], Any],
    code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = build(tmp_path)
    if isinstance(built, tuple):
        path, patch = built
        patch(monkeypatch)
    else:
        path = built
        with pytest.raises(FixtureError) as caught:
            _load(path)
        assert _code(caught.value) == code
    res = _live(tmp_path, _CODEX_ROUTE, manifest_path=path)
    _assert_rejected(res, code, base=tmp_path)


@pytest.mark.parametrize(
    "route",
    [
        pytest.param(_CODEX_ROUTE, id="codex"),
        pytest.param(_CLAUDE_ROUTE, id="claude"),
    ],
)
@pytest.mark.parametrize(("build", "code"), _G4_FIXTURE_PASS_ROWS)
def test_evaluator_g4_fixture_pass_rows(
    build: Callable[[Path], Any],
    code: str,
    route: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row only the fixture-verification pass can reject: the loader accepts
    the manifest, the pass builds the fixture under `<workspace>/verify/<index>`
    and rejects it on both routes before route preflight or any provider call."""
    path, patch = build(tmp_path)
    patch(monkeypatch)
    assert _load(path), "the loader accepts the manifest; only the pass rejects"
    original = bm.EPISODE_BUILDERS["upload-repair"]
    roots: list[Path] = []

    def recording(root: Path) -> tuple[str, Any]:
        roots.append(Path(root))
        return original(root)

    monkeypatch.setitem(bm.EPISODE_BUILDERS, "upload-repair", recording)
    res = _live(tmp_path, route, manifest_path=path)
    _assert_rejected(res, code, base=tmp_path)
    assert roots, "the verification pass built the fixture"
    assert all("verify" in r.parts for r in roots), (
        "the rejection came before any run rebuilt the fixture"
    )


# --------------------------------------------------------------------------
# Fixture revision, task binding, platform-stable bytes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cell", ["changed_builder_file", "changed_task_text"])
def test_fixture_revision_and_task_bound(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if cell == "changed_builder_file":
        monkeypatch.setattr(bm, "_UPLOAD_BUGGY", bm._UPLOAD_BUGGY + "# changed\n")
        expected = "fixture_revision_mismatch"
    else:
        original = bm.EPISODE_BUILDERS["upload-repair"]

        def changed_task(root: Path) -> tuple[str, Any]:
            task, decide = original(root)
            return task + " (changed)", decide

        monkeypatch.setitem(bm.EPISODE_BUILDERS, "upload-repair", changed_task)
        expected = "task_mismatch"
    res = _live(tmp_path, _CODEX_ROUTE)
    _assert_rejected(res, expected, base=tmp_path)


def test_fixture_revision_recomputed_before_each_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verification pass and every run rebuild the fixture; a builder that
    drifts only after the verification pass fails just that case."""
    original = bm.EPISODE_BUILDERS["upload-repair"]
    drifted: list[Path] = []

    def drifting(root: Path) -> tuple[str, Any]:
        built = original(root)
        if "verify" not in Path(root).parts:
            (Path(root) / "upload.py").write_text(
                _UPLOAD_SRC + "# drift\n", encoding="utf-8"
            )
            drifted.append(Path(root))
        return built

    monkeypatch.setitem(bm.EPISODE_BUILDERS, "upload-repair", drifting)
    res = _live(
        tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=_only("guest-handoff"))
    ).ran()
    record = res.record("upload-repair")
    assert record["passed"] is False
    assert record["reason"] == "fixture_revision_mismatch"
    assert res.kit.decisions_for("upload-repair") == []
    assert drifted, "the run rebuilt the fixture after the verification pass"


@pytest.mark.parametrize("cell", ["lf_default", "crlf_default"])
def test_upload_fixture_revision_platform_stable(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if cell == "crlf_default":
        real_write_text = Path.write_text

        def crlf_when_newline_omitted(
            self: Path,
            data: str,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> int:
            if newline is None:
                data = data.replace("\n", "\r\n")
                newline = ""
            return real_write_text(
                self, data, encoding=encoding, errors=errors, newline=newline
            )

        monkeypatch.setattr(Path, "write_text", crlf_when_newline_omitted)
    root = tmp_path / "fixture"
    root.mkdir()
    bm.EPISODE_BUILDERS["upload-repair"](root)
    assert (root / ".gitignore").read_bytes() == b".rush/\n"
    assert (root / "upload.py").read_bytes() == _UPLOAD_SRC.encode("utf-8")
    assert (root / "check_upload.py").read_bytes() == _CHECK_SRC.encode("utf-8")
    assert bm.fixture_revision(root) == _UPLOAD_REVISION


def test_fixture_revision_rules(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert bm.fixture_revision(empty) == _EMPTY_REVISION
    (empty / ".rush").mkdir()
    (empty / ".rush" / "memory.db").write_bytes(b"ignored")
    (empty / ".git").mkdir()
    (empty / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert bm.fixture_revision(empty) == _EMPTY_REVISION
    nested = tmp_path / "nested"
    (nested / "pkg").mkdir(parents=True)
    (nested / "pkg" / "mod.py").write_bytes(b"x = 1\n")
    (nested / "top.txt").write_bytes(b"top")
    expected = hashlib.sha256(
        canonical_json(
            {
                "pkg/mod.py": hashlib.sha256(b"x = 1\n").hexdigest(),
                "top.txt": hashlib.sha256(b"top").hexdigest(),
            }
        )
    ).hexdigest()
    assert bm.fixture_revision(nested) == expected
    (nested / "top.txt").write_bytes(b"top2")
    assert bm.fixture_revision(nested) != expected
    nested_git = tmp_path / "nested-git"
    (nested_git / "sub" / ".git").mkdir(parents=True)
    (nested_git / "sub" / ".git" / "config").write_bytes(b"c")
    assert bm.fixture_revision(nested_git) != _EMPTY_REVISION, (
        "only the top-level .git/.rush are excluded"
    )


# ==========================================================================
# Evaluators (G8-V)
# ==========================================================================


def test_normalized_evaluators() -> None:
    assert bm.normalized_contains("On 2023-05-10 it was delayed", "2023-05-10") is True
    assert bm.normalized_contains("ABC  \n def", "abc def") is True
    assert bm.normalized_contains("\uff21\uff22\uff23", "abc") is True, (
        "NFKC full-width"
    )
    assert bm.normalized_contains("STRASSE", "straße") is True, "casefold"
    assert bm.normalized_contains("anything", "") is False
    assert bm.normalized_contains("anything", "  \n\t ") is False
    assert bm.normalized_contains("2023-05-11", "2023-05-10") is False
    assert bm.normalized_exact("  Hello   World ", "hello world") is True
    assert bm.normalized_exact("hello world!", "hello world") is False
    assert bm.normalized_exact("anything", "") is False
    assert bm.expand_python_token(["{python}", "check.py", "{python}x"]) == [
        sys.executable,
        "check.py",
        "{python}x",
    ]
    assert unicodedata.normalize("NFKC", "\uff21") == "A"


def _perms() -> ExecutionPermissions:
    return ExecutionPermissions(cache_write=True, artifact_write=True, build=True)


def _verify_script(
    root: Path,
    *,
    commands: list[dict[str, Any]],
    behavior_ids: list[str],
    patch: str = _PATCH_BOTH,
) -> Callable[[Any], Any]:
    base_commit, base_tree = bm._init_upload_repair_repo(root)

    def decide(observation: Any) -> Any:
        if observation.step_index == 0:
            return bm.EpisodeAction(
                operation="verify_attempt",
                kwargs={
                    "request": {
                        "attempt_id": "scripted-attempt-1",
                        "behavior_ids": behavior_ids,
                        "contract": {
                            "base_commit": base_commit,
                            "base_tree_digest": base_tree,
                            "patch_content_digest": "scripted-patch-1",
                            "required_commands": commands,
                            "config_digest": "scripted-cfg-1",
                            "review_class": "standard",
                        },
                        "patch": patch,
                    }
                },
            )
        return bm.EpisodeAction(operation="submit", final="done")

    return decide


def _handoff_script(
    root: Path,
    *,
    subject: str = "domain_knowledge",
    source: str = "guest-session",
    text: str = "guest checkout regression: promo code applies twice",
    writes: int = 1,
    ack_id: str | None = None,
    bump_before_ack: bool = False,
    select_all: bool = False,
) -> Callable[[Any], Any]:
    seq = ["write"] * writes + ["handoff", "receive", "expand", "ack"]

    def decide(observation: Any) -> Any:
        n = observation.step_index
        hist = observation.history
        if n >= len(seq):
            return bm.EpisodeAction(operation="submit", final="done")
        name = seq[n]
        offset = writes
        if name == "write":
            return bm.EpisodeAction(
                operation="write",
                kwargs={
                    "subject": subject,
                    "content": {"text": f"{text} #{n}"},
                    "source": source,
                },
            )
        if name == "handoff":
            return bm.EpisodeAction(
                operation="handoff",
                kwargs={
                    "request": {
                        "action": "prepare",
                        "receiver_namespace": source,
                        "receiver_audience": "handoff-receiver",
                        "goal": "scripted handoff",
                        "selected_refs": [
                            {
                                "id": hist[k]["raw"]["id"],
                                "version": hist[k]["raw"]["artifact_version"],
                            }
                            for k in range(writes if select_all else 1)
                        ],
                    }
                },
            )
        prepared = (hist[offset].get("raw") or {}).get("data") or {}
        if name == "receive":
            return bm.EpisodeAction(
                operation="receive",
                kwargs={
                    "request": {
                        "session_id": prepared.get("handoff_id"),
                        "capability": prepared.get("capability"),
                    }
                },
            )
        changes = (
            ((hist[offset + 1].get("raw") or {}).get("data") or {}).get("changes")
        ) or []
        if not changes:
            return bm.EpisodeAction(operation="submit", final="no changes delivered")
        change = changes[0]
        if name == "expand":
            return bm.EpisodeAction(
                operation="expand",
                kwargs={
                    "session_allowlist": [source],
                    "request": {"id": change["id"], "version": change["version"]},
                },
            )
        expanded = ((hist[offset + 2].get("raw") or {}).get("data") or {}).get(
            "content_base64", ""
        )
        digest = hashlib.sha256(base64.b64decode(expanded)).hexdigest()
        if bump_before_ack:
            from rush.memory.store import TypedArtifactStore

            TypedArtifactStore(root).edit(
                change["id"],
                {"text": "edited after expand"},
                expected_version=1,
                scope=subject,
                apply=True,
            )
        return bm.EpisodeAction(
            operation="receive",
            kwargs={
                "request": {
                    "session_id": prepared.get("handoff_id"),
                    "capability": prepared.get("capability"),
                    "ack": [
                        {
                            "id": ack_id or change["id"],
                            "version": change["version"],
                            "digest": digest,
                        }
                    ],
                }
            },
        )

    return decide


def _scripted(root: Path, decide: Callable[[Any], Any]) -> Any:
    return bm.run_memory_episode(
        "scripted", "scripted task", decide, root=root, permissions=_perms()
    )


_UPLOAD_ACCEPTANCE = _baseline_cases()[2]["acceptance"]
_GUEST_ACCEPTANCE = _baseline_cases()[3]["acceptance"]


def test_evaluator_predicates_accept_correct_runs(tmp_path: Path) -> None:
    upload_root = tmp_path / "upload"
    upload_root.mkdir()
    upload = _scripted(
        upload_root,
        _verify_script(
            upload_root,
            commands=[
                {
                    "command": [sys.executable, "check_upload.py"],
                    "expected_exit_code": 0,
                }
            ],
            behavior_ids=list(_UPLOAD_BEHAVIORS),
        ),
    )
    assert bm.verifier_receipt_completed(upload.events, _UPLOAD_ACCEPTANCE) is True

    guest_root = tmp_path / "guest"
    guest_root.mkdir()
    guest = _scripted(guest_root, _handoff_script(guest_root))
    ok, bound = bm.receiver_readback_acknowledged(
        guest.events, _GUEST_ACCEPTANCE, guest_root
    )
    assert ok is True
    write_raw = guest.events[0].raw["raw"]
    assert [(b["id"], b["version"]) for b in bound] == [
        (write_raw["id"], write_raw["artifact_version"])
    ]
    expanded = next(e for e in guest.events if e.operation == "expand")
    content = base64.b64decode(expanded.raw["raw"]["data"]["content_base64"])
    assert bound[0]["digest"] == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize(
    "cell",
    [
        "wrong_task_receipt",
        "noop_contract",
        "partial_ack",
        "stale_ack",
        "submit_without_effects",
        "fabricated_ack_ref",
        "extra_handoff_write",
        "wrong_handoff_source",
        "unexpanded_python_token",
    ],
)
def test_evaluator_predicates_reject(cell: str, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    both_behaviors = list(_UPLOAD_BEHAVIORS)
    if cell == "wrong_task_receipt":
        result = _scripted(
            root,
            _verify_script(
                root,
                commands=[
                    {
                        "command": [sys.executable, "-c", "print(1)"],
                        "expected_exit_code": 0,
                    }
                ],
                behavior_ids=both_behaviors,
            ),
        )
        assert (
            result.events and result.events[0].raw["raw"].get("outcome") == "completed"
        )
        assert bm.verifier_receipt_completed(result.events, _UPLOAD_ACCEPTANCE) is False
    elif cell == "noop_contract":
        result = _scripted(
            root, _verify_script(root, commands=[], behavior_ids=both_behaviors)
        )
        assert bm.verifier_receipt_completed(result.events, _UPLOAD_ACCEPTANCE) is False
    elif cell == "unexpanded_python_token":
        result = _scripted(
            root,
            _verify_script(
                root,
                commands=[
                    {
                        "command": ["{python}", "check_upload.py"],
                        "expected_exit_code": 0,
                    }
                ],
                behavior_ids=both_behaviors,
            ),
        )
        assert bm.verifier_receipt_completed(result.events, _UPLOAD_ACCEPTANCE) is False
    elif cell == "submit_without_effects":
        result = _scripted(
            root, lambda obs: bm.EpisodeAction(operation="submit", final="done")
        )
        assert result.events == ()
        assert bm.verifier_receipt_completed(result.events, _UPLOAD_ACCEPTANCE) is False
        ok, _ = bm.receiver_readback_acknowledged(
            result.events, _GUEST_ACCEPTANCE, root
        )
        assert ok is False
    else:
        acceptance = copy.deepcopy(_GUEST_ACCEPTANCE)
        if cell == "partial_ack":
            # two writes handed off, only the first acknowledged
            acceptance["handoff"]["write_count"] = 2
            result = _scripted(root, _handoff_script(root, writes=2, select_all=True))
        elif cell == "stale_ack":
            result = _scripted(root, _handoff_script(root, bump_before_ack=True))
        elif cell == "fabricated_ack_ref":
            result = _scripted(root, _handoff_script(root, ack_id=str(uuid.uuid4())))
        elif cell == "extra_handoff_write":
            result = _scripted(root, _handoff_script(root, writes=2))
        else:
            result = _scripted(root, _handoff_script(root, source="other-session"))
        ok, _ = bm.receiver_readback_acknowledged(result.events, acceptance, root)
        assert ok is False


# ==========================================================================
# Live runs: contracts of the shared happy runs
# ==========================================================================

_ROUTE_ARGV = {
    "claude_answer": (
        "claude",
        "dataset_answer",
        [
            "-p",
            "--tools",
            "",
            "--output-format",
            "json",
            "--safe-mode",
            "--strict-mcp-config",
            "--no-session-persistence",
        ],
    ),
    "claude_episode": (
        "claude",
        "episode",
        [
            "-p",
            "--tools",
            "Read,Grep,Glob",
            "--permission-mode",
            "plan",
            "--output-format",
            "json",
            "--safe-mode",
            "--strict-mcp-config",
            "--no-session-persistence",
        ],
    ),
    "codex_answer": (
        "codex",
        "dataset_answer",
        [
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--enable",
            "skip_host_skill_discovery",
            "--disable",
            "plugins",
            "--disable",
            "apps",
            "--disable",
            "skill_search",
            "-c",
            "skills.max_context_tokens=1",
            "-c",
            "skills.include_instructions=false",
            "--disable",
            "shell_tool",
            "--disable",
            "unified_exec",
            "--disable",
            "code_mode_host",
            "--disable",
            "tool_suggest",
            "--disable",
            "sleep_tool",
            "-c",
            "model_instructions_file={decision_instructions}",
        ],
    ),
    "codex_episode": (
        "codex",
        "episode",
        [
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--enable",
            "skip_host_skill_discovery",
            "--disable",
            "plugins",
            "--disable",
            "apps",
            "--disable",
            "skill_search",
            "-c",
            "skills.max_context_tokens=1",
            "-c",
            "skills.include_instructions=false",
            "-c",
            "model_instructions_file={decision_instructions}",
        ],
    ),
}


@pytest.mark.parametrize("cell", list(_ROUTE_ARGV))
def test_live_decision_argv_hermetic(
    cell: str, happy_runs: dict[str, RunResult]
) -> None:
    key, kind, flags = _ROUTE_ARGV[cell]
    res = happy_runs[key].ran()
    exe = res.kit.exe_real
    seen = 0
    for spawn in res.kit.decision_spawns:
        argv = spawn["argv"]
        request = _parse_request(argv[-1])
        wants_dataset = request["decision_kind"] in {"answer", "preflight"}
        if (kind == "dataset_answer") != wants_dataset:
            continue
        seen += 1
        resolved_flags = [
            x.replace(
                "{decision_instructions}",
                json.dumps(
                    str(
                        Path(__file__).resolve().parent
                        / "fixtures/benchmarks/codex_decision_instructions.md"
                    ),
                    ensure_ascii=False,
                ),
            )
            for x in flags
        ]
        assert argv == [exe, *resolved_flags, argv[-1]], argv[:-1]
        assert "--max-turns" not in argv
        _assert_spawn_contract(spawn)
    assert seen >= 1
    help_argv = ["--help"] if key == "claude" else ["exec", "--help"]
    argvs = [s["argv"] for s in res.kit.spawns]
    assert [exe, *help_argv] in argvs
    assert [exe, "--version"] in argvs


def test_live_report_shape_and_labels(happy_runs: dict[str, RunResult]) -> None:
    for key, res in happy_runs.items():
        report = res.ran().report
        assert report["decision_mode"] == "live"
        assert report["seed_semantics"] == "repetition_labels"
        assert report["seeds"] == [1]
        assert report["max_total_tokens"] == 16000
        assert report["usage_accounting"]["budget_basis"] == "provider_model_tokens"
        assert not any("was not exercised" in b for b in report["blockers"])
        assert report["python"] == {
            "executable": sys.executable,
            "version": sys.version,
        }
        route = report["decision_route"]
        assert route["status"] != "unavailable"
        assert route["route_overhead_tokens"] == 45
        assert route["version"] == ("fake 1.0" if key == "claude" else "codex 0.162.1")
        assert route["format"] == (
            "claude_print_json" if key == "claude" else "codex_exec_jsonl"
        )
        task_manifest = report["task_manifest"]
        assert task_manifest["cases_sha256"] == _BASELINE_DIGEST
        assert task_manifest["case_count"] == 5
        assert report["aggregate"]["total"] == 5
        record = res.record("lme-q-001")
        assert set(record) >= {
            "case_id",
            "seed",
            "kind",
            "family",
            "variant",
            "fixture_revision",
            "passed",
            "reason",
            "harness_completed",
            "evaluator",
            "evaluator_version",
            "budget",
            "steps",
            "invocations",
            "answer",
            "bound_refs",
        }
        assert set(record["budget"]) >= {
            "max_total_tokens",
            "output_reserve_tokens",
            "model_tokens",
            "local_returned_tokens",
        }


def test_dataset_cases_pass_with_correct_answers(
    happy_runs: dict[str, RunResult],
) -> None:
    for res in happy_runs.values():
        res.ran()
        for case_id, gold in (
            ("lme-q-001", "2023-05-10"),
            ("lme-q-002", "db-widen-ids"),
        ):
            record = res.record(case_id)
            assert record["passed"] is True, record
            assert record["reason"] is None
            assert record["harness_completed"] is True
            assert record["answer"] == gold
            assert record["evaluator"] == "normalized_contains"
            assert record["evaluator_version"] == 1
            assert record["budget"]["model_tokens"] == 110
            assert record["budget"]["max_total_tokens"] == 16000


@pytest.mark.parametrize(
    "case_id", ["upload-repair", "guest-handoff", "diagnosis-handoff"]
)
def test_episode_decision_request_shows_acceptance(
    case_id: str, happy_runs: dict[str, RunResult]
) -> None:
    case = next(c for c in _baseline_cases() if c["id"] == case_id)
    for res in happy_runs.values():
        res.ran()
        calls = res.kit.decisions_for(case_id)
        assert calls, case_id
        request = calls[0]["request"]
        assert request["decision_kind"] == "episode"
        assert request["case_id"] == case_id
        assert request["task"] == case["inputs"]["task"]
        assert request["permitted_actions"] == case["permitted_actions"]
        assert request["editable_paths"] == case["editable_paths"]
        assert set(request) == {
            "schema_version",
            "decision_kind",
            "case_id",
            "task",
            "step",
            "history",
            "remaining_budget_tokens",
            "permitted_actions",
            "editable_paths",
            "acceptance",
            "operations",
            "response_schema",
        }
        assert request["schema_version"] == 1
        assert set(request["response_schema"]) == {"oneOf"}
        acceptance = request["acceptance"]
        assert set(acceptance) == {"behavior_ids", "required_commands", "handoff"}
        assert acceptance["behavior_ids"] == case["acceptance"]["behavior_ids"]
        assert (
            acceptance["required_commands"] == case["acceptance"]["required_commands"]
        )
        assert acceptance["handoff"] == case["acceptance"]["handoff"]
        if case_id == "upload-repair":
            assert acceptance["required_commands"][0]["command"][0] == "{python}"
        assert set(request["operations"]) == set(case["permitted_actions"]) - {"submit"}
        assert request["step"] == 0 and request["history"] == []
        assert request["remaining_budget_tokens"] > 0
        text = json.dumps(request)
        for forbidden in (
            "answer_session_ids",
            "has_answer",
            "gold_trajectory",
            "expected_next_action",
        ):
            assert forbidden not in text


@pytest.mark.parametrize("case_id", ["guest-handoff", "diagnosis-handoff"])
def test_handoff_cases_passable_from_decision_request(
    case_id: str, happy_runs: dict[str, RunResult]
) -> None:
    for res in happy_runs.values():
        res.ran()
        record = res.record(case_id)
        assert record["reason"] is None, record
        assert record["harness_completed"] is True
        assert record["passed"] is True
        assert record["evaluator"] == "receiver_readback_acknowledged"
        bound = record["bound_refs"]
        assert isinstance(bound, list) and len(bound) == 1
        assert set(bound[0]) == {"id", "version", "digest"}
        assert re.fullmatch(r"[0-9a-f]{64}", bound[0]["digest"])


def test_python_token_expanded_and_interpreter_recorded(
    happy_runs: dict[str, RunResult],
) -> None:
    for res in happy_runs.values():
        report = res.ran().report
        assert report["python"] == {
            "executable": sys.executable,
            "version": sys.version,
        }
        verifies = [c for c in res.kit.tool_calls if c.operation == "verify_attempt"]
        assert len(verifies) == 1
        request = verifies[0].kwargs["request"]
        assert (
            request["contract"]["required_commands"][0]["command"][0] == sys.executable
        )
        assert "{python}" not in json.dumps(request["contract"]["required_commands"])
        executed = verifies[0].result["raw"]["result"]["executed_commands"]
        assert executed[0]["command"][0] == sys.executable
        assert executed[0]["passed"] is True
        record = res.record("upload-repair")
        assert record["passed"] is True and record["reason"] is None


def test_episode_operation_schema_preserves_nested_wire_types() -> None:
    """A model copying the advertised nested request reaches strict action validation."""
    schemas = json.loads(json.dumps(bm.OPERATION_SCHEMAS))
    assert isinstance(schemas["write"]["kwargs"]["content"], dict)
    for operation, schema in schemas.items():
        if operation != "write":
            assert isinstance(schema["kwargs"]["request"], dict), operation
    case = next(c for c in _baseline_cases() if c["id"] == "upload-repair")
    kwargs = copy.deepcopy(schemas["verify_attempt"]["kwargs"])
    kwargs["request"].update(
        attempt_id="schema-request",
        behavior_ids=case["acceptance"]["behavior_ids"],
        patch=_PATCH_BOTH,
    )
    kwargs["request"]["contract"]["required_commands"] = case["acceptance"][
        "required_commands"
    ]
    reason, action = bench_run._validate_episode_action(
        case, {"kind": "action", "operation": "verify_attempt", "kwargs": kwargs}
    )
    assert reason is None and action is not None
    assert action.kwargs["request"]["attempt_id"] == "schema-request"


def test_source_aware_agent_patch_from_fixture(
    tmp_path: Path, happy_runs: dict[str, RunResult]
) -> None:
    from jsonschema import Draft202012Validator

    for res in happy_runs.values():
        res.ran()
        call = res.kit.decisions_for("upload-repair")[0]
        assert {"upload.py", "check_upload.py"} <= set(call["listdir"])
        verifies = [c for c in res.kit.tool_calls if c.operation == "verify_attempt"]
        schema = call["request"]["response_schema"]
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        action = {
            "kind": "action",
            "operation": "verify_attempt",
            "kwargs": {"request": verifies[0].kwargs["request"]},
        }
        validator.validate(action)
        parsed, reason = providers.parse_decision_text(json.dumps(action), "episode")
        assert reason is None and parsed == action
        assert not validator.is_valid({"action": action})
        assert not validator.is_valid({**action, "final": None})
        assert validator.is_valid({"kind": "submit", "final": None})
        assert not validator.is_valid({"kind": "submit"})
        assert verifies[0].kwargs["request"]["patch"] == _PATCH_BOTH
        assert verifies[0].result["raw"]["outcome"] == "completed"
        assert res.record("upload-repair")["passed"] is True

    timeout_only = _live(
        tmp_path / "timeout-only",
        _CODEX_ROUTE,
        plan=_plan(
            "codex",
            rules=_only(
                "upload-repair",
                _rule(
                    {"case_id": "upload-repair", "decision_kind": "episode", "step": 0},
                    decision={
                        "kind": "action",
                        "operation": "verify_attempt",
                        "kwargs": {
                            "request": {
                                "attempt_id": "timeout-only",
                                "behavior_ids": list(_UPLOAD_BEHAVIORS),
                                "contract": {
                                    "patch_content_digest": "p",
                                    "required_commands": copy.deepcopy(
                                        _UPLOAD_COMMANDS
                                    ),
                                    "config_digest": "c",
                                    "review_class": "standard",
                                },
                                "patch": _PATCH_TIMEOUT_ONLY,
                            }
                        },
                    },
                ),
            ),
        ),
    ).ran()
    record = timeout_only.record("upload-repair")
    assert record["passed"] is False
    assert record["reason"] == "evaluator_failed"
    assert record["harness_completed"] is True
    verifies = [
        c for c in timeout_only.kit.tool_calls if c.operation == "verify_attempt"
    ]
    assert len(verifies) == 1
    assert verifies[0].result["raw"]["outcome"] != "completed"


def test_dynamic_prompt_argv_and_result_usage(happy_runs: dict[str, RunResult]) -> None:
    for key, res in happy_runs.items():
        report = res.ran().report
        prompts = [s["argv"][-1] for s in res.kit.decision_spawns]
        assert prompts
        for prompt in prompts:
            assert prompt.startswith(providers.DECISION_PROMPT_PREAMBLE)
            assert "BENCHMARK_OK" not in prompt
        guest = [
            s["argv"][-1]
            for s in res.kit.decision_spawns
            if _parse_request(s["argv"][-1]).get("case_id") == "guest-handoff"
        ]
        assert len(guest) >= 3 and len(set(guest)) == len(guest), (
            "each step carries its own prompt"
        )
        expected_usage = _usage("claude" if key == "claude" else "codex")
        record = (
            report["case_results"][0]
            if isinstance(report["case_results"], list)
            else res.records[0]
        )
        assert record["invocations"], record
        invocation = record["invocations"][0]
        assert invocation["usage"] == expected_usage
        assert invocation["model_tokens"] == 110
        assert invocation["argv"][-1].startswith("<prompt sha256=")
        assert invocation["route_id"] in {_CODEX_ROUTE, _CLAUDE_ROUTE}
        assert set(invocation) >= {
            "step",
            "route_id",
            "argv",
            "cwd",
            "exit_code",
            "duration_ms",
            "reason",
            "model_tokens",
            "usage",
            "model",
            "tool_items",
            "stdout_excerpt",
            "stderr_excerpt",
            "decision_sha256",
        }
        assert len(invocation["stdout_excerpt"]) <= 4096


def _walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, inner in value.items():
            yield str(key)
            yield from _walk_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _walk_keys(inner)


def _normalized(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def test_live_decider_receives_actual_history(
    happy_runs: dict[str, RunResult], dataset_history_run: RunResult
) -> None:
    gold_keys = {
        "answer",
        "answer_session_ids",
        "has_answer",
        "gold_trajectory",
        "expected_next_action",
    }
    for res in happy_runs.values():
        res.ran()
        calls = res.kit.tool_calls
        start = next(
            i
            for i, c in enumerate(calls)
            if c.operation == "write" and c.kwargs.get("source") == "guest-session"
        )
        actual = [_normalized(c.result) for c in calls[start:]]
        requests = res.kit.decisions_for("guest-handoff")
        assert len(requests) >= 4
        for request_entry in requests:
            n = request_entry["step"]
            assert request_entry["request"]["history"] == actual[:n], n
            assert not gold_keys & set(_walk_keys(request_entry["request"]))
        for entry in res.kit.decisions:
            assert not gold_keys & set(_walk_keys(entry["request"]))
            if entry["decision_kind"] == "answer":
                text = json.dumps(entry["request"])
                assert "2023-05-10" not in text and "db-widen-ids" not in text

    res = dataset_history_run.ran()
    entries = res.kit.decisions_for("lme-q-001")
    assert len(entries) == 1
    request = entries[0]["request"]
    recalls = [
        c
        for c in res.kit.tool_calls
        if c.operation == "recall" and "s1" in (c.kwargs.get("session_allowlist") or [])
    ]
    assert len(recalls) == 1
    assert request["history"] == [
        {"operation": "recall", "result": _normalized(recalls[0].result)}
    ]
    assert set(request) == {
        "schema_version",
        "decision_kind",
        "case_id",
        "task",
        "question_date",
        "step",
        "variant",
        "history",
        "variant_context",
        "remaining_budget_tokens",
        "permitted_actions",
        "response_schema",
    }
    assert request["schema_version"] == 1
    assert request["decision_kind"] == "answer"
    assert request["case_id"] == "lme-q-001"
    assert request["question_date"] == "2023-05-14"
    assert request["step"] == 0
    assert request["response_schema"] == {"kind": "answer", "text": "<string>"}
    assert request["task"] == "On what date did I say my flight got delayed?"
    assert request["permitted_actions"] == ["answer"]
    assert request["variant"] == "current"
    assert "variant_context" in request
    assert not gold_keys & set(_walk_keys(request))


def test_dataset_decision_cwd_is_empty_and_contained(
    happy_runs: dict[str, RunResult],
) -> None:
    for res in happy_runs.values():
        res.ran()
        for entry in res.kit.decisions:
            cwd = Path(entry["cwd"])
            if entry["decision_kind"] in {"answer", "preflight"}:
                assert cwd.name == "decision-cwd"
                assert entry["listdir"] == []
            else:
                assert "decision-cwd" not in cwd.parts
            assert "pyproject.toml" not in entry["listdir"]
            assert cwd.resolve() != Path.cwd().resolve()
        episode_cwds = {
            e["case_id"]: e
            for e in res.kit.decisions
            if e["decision_kind"] == "episode"
        }
        assert ".git" in episode_cwds["upload-repair"]["listdir"]


# --------------------------------------------------------------------------
# Budget accounting
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cell", ["wrong_date", "gold_inside_sentence"])
def test_wrong_completed_answer_fails_quality(cell: str, tmp_path: Path) -> None:
    text = {
        "wrong_date": "2023-05-11",
        "gold_inside_sentence": "It was 2023-05-10, I think.",
    }[cell]
    rules = _only(
        "lme-q-001",
        _rule({"case_id": "lme-q-001"}, decision={"kind": "answer", "text": text}),
    )
    res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
    record = res.record("lme-q-001")
    assert record["harness_completed"] is True, (
        "the run finished; quality is judged separately"
    )
    assert record["evaluator"] == "normalized_contains"
    assert record["evaluator_version"] == 1
    assert record["answer"] == text
    assert bm.normalized_exact(text, "2023-05-10") is False
    if cell == "wrong_date":
        assert record["passed"] is False
        assert record["reason"] == "evaluator_failed"
        assert (
            res.report["aggregate"]["failed_by_reason"].get("evaluator_failed", 0) >= 1
        )
    else:
        assert record["passed"] is True
        assert record["reason"] is None


def _write_step_rules(
    case_id: str, source: str, subject: str = "domain_knowledge"
) -> list[dict[str, Any]]:
    """Episode `case_id` writes once, then submits."""
    return [
        _rule(
            {"case_id": case_id, "decision_kind": "episode", "step": 0},
            decision={
                "kind": "action",
                "operation": "write",
                "kwargs": {
                    "subject": subject,
                    "content": {"text": "one note"},
                    "source": source,
                },
            },
        ),
        _rule(
            {"case_id": case_id, "decision_kind": "episode", "step": 1},
            decision={"kind": "submit", "final": "done"},
        ),
    ]


@pytest.mark.parametrize(
    "cell",
    [
        "model_tokens_once",
        "local_tokens_separate",
        "over_budget_fails_correct_answer",
        "cli_min_case_budget",
        "missing_usage_unavailable",
    ],
)
def test_live_budget_accounting(cell: str, tmp_path: Path) -> None:
    if cell == "model_tokens_once":
        res = _live(
            tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=_only("lme-q-001"))
        ).ran()
        record = res.record("lme-q-001")
        assert record["budget"]["model_tokens"] == 110
        assert record["passed"] is True
        assert record["budget"]["local_returned_tokens"] == 0
    elif cell == "local_tokens_separate":
        rules = _only(
            "guest-handoff", *_write_step_rules("guest-handoff", "guest-session")
        )
        res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
        record = res.record("guest-handoff")
        writes = [
            c
            for c in res.kit.tool_calls
            if c.operation == "write" and c.kwargs.get("source") == "guest-session"
        ]
        assert len(writes) == 1
        encoder = bm._get_encoder()
        serialized = json.dumps(
            writes[0].result, ensure_ascii=False, separators=(",", ":"), default=str
        )
        assert record["budget"]["local_returned_tokens"] == bm._count_tokens(
            encoder, serialized
        )
        assert record["budget"]["model_tokens"] == 220, (
            "two provider calls; the local result is not charged again"
        )
    elif cell == "over_budget_fails_correct_answer":
        rules = _only(
            "lme-q-001",
            _rule({"case_id": "lme-q-001"}, usage_raw=_usage("codex", 3990, 20)),
        )
        res = _live(
            tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules), max_total=4000
        ).ran()
        record = res.record("lme-q-001")
        assert record["passed"] is False
        assert record["reason"] == "budget_exhausted"
        assert "2023-05-10" in str(record["answer"]), (
            "the correct answer is recorded but cannot pass"
        )
        assert record["budget"]["max_total_tokens"] == 4000
        assert record["budget"]["model_tokens"] == 4010
        assert res.report["aggregate"]["total"] == 5
    elif cell == "cli_min_case_budget":
        small = _p72_dataset_case(budget={**_BUDGET, "max_total_tokens": 6000})
        obj = _manifest_obj((small,))
        res = _live(
            tmp_path,
            _CODEX_ROUTE,
            manifest_obj=obj,
            plan=_plan("codex", rules=_only("lme-q-001")),
            max_total=8000,
        )
        res.ran()
        assert res.record("lme-q-001")["budget"]["max_total_tokens"] == 8000
        assert res.record("p72-q-ext")["budget"]["max_total_tokens"] == 6000
        assert res.record("upload-repair")["budget"]["max_total_tokens"] == 8000
    else:
        rules = _only("lme-q-001", _rule({"case_id": "lme-q-001"}, usage_raw=None))
        res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
        record = res.record("lme-q-001")
        assert record["passed"] is False
        assert record["reason"] == "provider_usage_unavailable"
        assert record["harness_completed"] is False


def test_memory_cost_not_double_counted(tmp_path: Path) -> None:
    usage = _usage("codex", 100, 10, cached=90)
    rules = _only("guest-handoff", *_write_step_rules("guest-handoff", "guest-session"))
    res = _live(
        tmp_path, _CODEX_ROUTE, plan=_plan("codex", usage=usage, rules=rules)
    ).ran()
    record = res.record("guest-handoff")
    assert record["budget"]["model_tokens"] == 220
    guest_writes = [
        c
        for c in res.kit.tool_calls
        if c.operation == "write" and c.kwargs.get("source") == "guest-session"
    ]
    assert len(guest_writes) == 1
    assert [i["usage"] for i in record["invocations"]] == [usage, usage]


def test_ingestion_budget_refuses_before_decider(tmp_path: Path) -> None:
    from scripts.benchmarks.memory_datasets import (
        load_dataset_section,
        run_longmemeval_case,
    )

    _manifest, records = load_dataset_section("longmemeval")

    def forbidden_decider(*args: Any) -> str:
        pytest.fail("ingestion exhausted approved budget before decider")

    result = run_longmemeval_case(
        records[0],
        decide_fn=forbidden_decider,
        max_total_tokens=1,
        workspace_root=tmp_path,
    )
    assert result.outcome == "budget_exhausted"
    assert result.prediction is None
    assert result.total_tokens > 1


def test_post_decision_budget_exhaustion(tmp_path: Path) -> None:
    rules = _only(
        "guest-handoff",
        _rule(
            {"case_id": "guest-handoff", "decision_kind": "episode", "step": 0},
            usage_raw=_usage("codex", 20000, 10),
        ),
    )
    res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
    record = res.record("guest-handoff")
    assert record["reason"] == "budget_exhausted"
    assert record["passed"] is False
    assert not [
        c for c in res.kit.tool_calls if c.kwargs.get("source") == "guest-session"
    ], "a discarded decision runs no tool"
    assert res.report["aggregate"]["total"] == 5
    assert len(res.kit.decisions_for("guest-handoff")) == 1


def test_pre_call_admission_refuses_spawn(tmp_path: Path) -> None:
    rules = _only(
        "guest-handoff",
        _rule(
            {"case_id": "guest-handoff", "decision_kind": "episode", "step": 0},
            usage_raw=_usage("codex", 2500, 0),
        ),
    )
    res = _live(
        tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules), max_total=4000
    ).ran()
    record = res.record("guest-handoff")
    assert record["reason"] == "budget_exhausted"
    assert record["passed"] is False
    assert record["budget"]["model_tokens"] == 2500
    assert len(res.kit.decisions_for("guest-handoff")) == 1, (
        "the second call is refused before spawning"
    )
    first_prompt_tokens = bm._count_tokens(
        bm._get_encoder(), res.kit.decisions_for("guest-handoff")[0]["prompt"]
    )
    assert 45 + first_prompt_tokens + 1024 <= 4000, "the first call was admitted"


def test_live_seeds_are_repetition_labels(tmp_path: Path) -> None:
    res = _live(
        tmp_path,
        _CODEX_ROUTE,
        plan=_plan("codex", rules=_only("lme-q-001")),
        seeds="1,2,3",
    ).ran()
    seeds = sorted(r["seed"] for r in res.records if r["case_id"] == "lme-q-001")
    assert seeds == [1, 2, 3]
    assert res.report["seeds"] == [1, 2, 3]
    assert res.report["seed_semantics"] == "repetition_labels"
    assert len(res.kit.decisions_for("lme-q-001")) == 3
    assert res.report["aggregate"]["total"] == 15


# --------------------------------------------------------------------------
# Route preflight
# --------------------------------------------------------------------------


def _preflight_rule(**action: Any) -> dict[str, Any]:
    return _rule({"decision_kind": "preflight"}, **action)


@pytest.mark.parametrize(
    "cell",
    [
        "within_budget_runs",
        "overhead_15000_unavailable",
        "help_missing_flag_unavailable",
        "malformed_preflight_unavailable",
        "unknown_preflight_field_unavailable",
        "preflight_nonzero_exit_unavailable",
        "preflight_usage_absent_unavailable",
    ],
)
def test_route_preflight_overhead_gate(cell: str, tmp_path: Path) -> None:
    agents = "Follow the repository rules.\n"
    route = _CODEX_ROUTE
    plan = _plan("codex", rules=[])
    expected_reason: str | None = None
    if cell == "overhead_15000_unavailable":
        plan = _plan("codex", preflight=_usage("codex", 14990, 10))
        expected_reason = "route_overhead_exceeds_budget"
    elif cell == "help_missing_flag_unavailable":
        route = _CLAUDE_ROUTE
        plan = _plan("claude", omit_flag="--safe-mode")
        expected_reason = "hermetic_flags_unsupported"
    elif cell == "malformed_preflight_unavailable":
        plan = _plan("codex", rules=[_preflight_rule(text="not json at all")])
        expected_reason = "preflight_failed"
    elif cell == "unknown_preflight_field_unavailable":
        plan = _plan(
            "codex",
            rules=[
                _preflight_rule(decision={"kind": "answer", "text": "ok", "extra": 1})
            ],
        )
        expected_reason = "preflight_failed"
    elif cell == "preflight_nonzero_exit_unavailable":
        plan = _plan("codex", rules=[_preflight_rule(exit=1)])
        expected_reason = "preflight_failed"
    elif cell == "preflight_usage_absent_unavailable":
        plan = _plan("codex", preflight=None)
        expected_reason = "preflight_failed"
    res = _live(tmp_path, route, plan=plan, agents_md=agents)
    if expected_reason is None:
        res.ran()
        decision_route = res.report["decision_route"]
        assert decision_route["status"] != "unavailable"
        assert decision_route["route_overhead_tokens"] == 45
        assert decision_route["version"] == "codex 0.162.1"
        files = decision_route["instruction_files"]
        assert len(files) == 1
        entry = files[0]
        assert entry["present"] is True
        assert Path(entry["path"]).name == "AGENTS.md"
        assert entry["sha256"] == hashlib.sha256(agents.encode("utf-8")).hexdigest()
        assert entry["cl100k_tokens"] == bm._count_tokens(bm._get_encoder(), agents)
        assert len(res.records) == 5
        assert res.kit.decisions
        preflights = [e for e in res.kit.decisions if e["decision_kind"] == "preflight"]
        assert len(preflights) == 1
        assert preflights[0]["request"] == {
            "schema_version": 1,
            "decision_kind": "preflight",
            "task": 'Reply with the JSON object {"kind": "answer", "text": "ok"}.',
            "response_schema": {"kind": "answer", "text": "<string>"},
        }
        assert preflights[0]["argv"][:8] == [
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
        ]
        assert preflights[0]["argv"][8:11] == [
            "--strict-config",
            "--enable",
            "skip_host_skill_discovery",
        ]
        assert "shell_tool" in preflights[0]["argv"]
        assert "unified_exec" in preflights[0]["argv"]
        assert preflights[0]["argv"][-2].startswith("model_instructions_file=")
        assert Path(preflights[0]["cwd"]).name == "decision-cwd"
        assert preflights[0]["listdir"] == []
        return
    assert res.error is None, repr(res.error)
    assert res.exit_code == 1, res.stderr
    report = res.report
    decision_route = report["decision_route"]
    assert decision_route["status"] == "unavailable"
    assert decision_route["reason"] == expected_reason
    assert any(
        f"decision route {route} unavailable: {expected_reason}" in b
        for b in report["blockers"]
    )
    preflight_calls = [
        e for e in res.kit.decisions if e["decision_kind"] == "preflight"
    ]
    assert [e for e in res.kit.decisions if e["decision_kind"] != "preflight"] == [], (
        "zero case calls"
    )
    if cell == "overhead_15000_unavailable":
        assert decision_route["route_overhead_tokens"] == 15000
        assert decision_route["version"] == "codex 0.162.1"
        assert len(preflight_calls) == 1
        files = decision_route["instruction_files"]
        assert files[0]["sha256"] == hashlib.sha256(agents.encode("utf-8")).hexdigest()
        assert files[0]["cl100k_tokens"] == bm._count_tokens(bm._get_encoder(), agents)
    elif cell == "help_missing_flag_unavailable":
        assert preflight_calls == [], "no preflight call after a missing hermetic flag"
        assert [e for e in res.kit.log if e["kind"] == "help"]
    elif cell == "malformed_preflight_unavailable":
        assert "malformed_decision_json" in json.dumps(decision_route)
    elif cell == "unknown_preflight_field_unavailable":
        assert "unknown_decision_field" in json.dumps(decision_route)
    elif cell == "preflight_nonzero_exit_unavailable":
        assert "nonzero_exit" in json.dumps(decision_route)
    else:
        assert "provider_usage_unavailable" in json.dumps(decision_route)


def test_dt09_registered_budget_preserves_cases_and_preflight_guard(
    tmp_path: Path,
) -> None:
    original = json.loads(_SHIPPED_MANIFEST.read_text(encoding="utf-8"))
    registered = json.loads(
        _SHIPPED_MANIFEST.with_name("task_manifest_dt09_budget.json").read_text(
            encoding="utf-8"
        )
    )
    restored = copy.deepcopy(registered)
    for before, after, restore in zip(
        original["cases"], registered["cases"], restored["cases"], strict=True
    ):
        assert after["budget"]["max_total_tokens"] == 32768 * (
            after["budget"]["max_steps"] if after["kind"] == "episode" else 1
        )
        restore["budget"]["max_total_tokens"] = before["budget"]["max_total_tokens"]
    restored["phase72_cases_sha256"] = original["phase72_cases_sha256"]
    assert restored == original
    for field, value in (
        ("family", "changed task"),
        ("grants", []),
        ("budget", {**registered["cases"][0]["budget"], "max_total_tokens": 32769}),
        ("budget", {**registered["cases"][0]["budget"], "output_reserve_tokens": 1025}),
    ):
        altered = copy.deepcopy(registered)
        altered["cases"][0][field] = value
        with pytest.raises(FixtureError, match="baseline_altered"):
            bm.load_task_manifest(_write_manifest(tmp_path / f"{field}.json", altered))

    # Reproduce measured overhead through the existing subprocess provider, not arithmetic.
    for name, manifest, cli_cap, available in (
        ("original", original, 16000, False),
        ("cli_only", original, 393216, False),
        ("registered", registered, 393216, True),
        ("cli_capped", registered, 16000, False),
    ):
        result = _live(
            tmp_path / name,
            _CODEX_ROUTE,
            manifest_obj=manifest,
            max_total=cli_cap,
            plan=_plan("codex", preflight=_usage("codex", 13993, 13)),
        )
        assert result.error is None, repr(result.error)
        route = result.report["decision_route"]
        assert route["route_overhead_tokens"] == 14006
        if available:
            assert route["status"] == "available"
            assert len(result.report["case_results"]) == len(registered["cases"])
            for case in registered["cases"]:
                assert (
                    result.record(case["id"])["budget"]["max_total_tokens"]
                    == (case["budget"]["max_total_tokens"])
                )
            assert any(
                call["decision_kind"] != "preflight" for call in result.kit.decisions
            )
        else:
            assert result.exit_code == 1
            assert route["status"] == "unavailable"
            assert route["reason"] == "route_overhead_exceeds_budget"
            assert result.report["case_results"] == []
            assert all(
                call["decision_kind"] == "preflight" for call in result.kit.decisions
            )


def test_route_preflight_gate_uses_each_cases_reserve(tmp_path: Path) -> None:
    """overhead + that case's reserve + 2048 > min(--max-total-tokens, case max)
    makes the route unavailable even when other cases would fit."""
    tight = _p72_dataset_case(
        budget={**_BUDGET, "max_total_tokens": 3000, "output_reserve_tokens": 1024}
    )
    obj = _manifest_obj((tight,))
    res = _live(tmp_path, _CODEX_ROUTE, manifest_obj=obj, plan=_plan("codex"))
    assert res.exit_code == 1
    route = res.report["decision_route"]
    assert route["status"] == "unavailable"
    assert route["reason"] == "route_overhead_exceeds_budget"
    assert [e for e in res.kit.decisions if e["decision_kind"] != "preflight"] == []
    just_fits = _p72_dataset_case(
        budget={**_BUDGET, "max_total_tokens": 3117, "output_reserve_tokens": 1024}
    )
    fits = _live(
        tmp_path / "fits",
        _CODEX_ROUTE,
        manifest_obj=_manifest_obj((just_fits,)),
        plan=_plan("codex"),
    )
    fits.ran()
    assert fits.report["decision_route"]["status"] != "unavailable"
    one_over = _p72_dataset_case(
        budget={**_BUDGET, "max_total_tokens": 3116, "output_reserve_tokens": 1024}
    )
    over = _live(
        tmp_path / "over",
        _CODEX_ROUTE,
        manifest_obj=_manifest_obj((one_over,)),
        plan=_plan("codex"),
    )
    assert over.exit_code == 1


def test_route_loader_decision_protocol_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.benchmarks import fixtures

    shipped = json.loads(
        fixtures.fixture_path("provider_routes.json").read_text(encoding="utf-8")
    )
    routes = fixtures.load_provider_routes()
    with_protocol = sorted(
        rid for rid, route in routes.items() if route.decision_protocol is not None
    )
    assert with_protocol == sorted([_CLAUDE_ROUTE, _CODEX_ROUTE])
    codex_args = {
        "dataset_answer": [
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--enable",
            "skip_host_skill_discovery",
            "--disable",
            "plugins",
            "--disable",
            "apps",
            "--disable",
            "skill_search",
            "-c",
            "skills.max_context_tokens=1",
            "-c",
            "skills.include_instructions=false",
            "--disable",
            "shell_tool",
            "--disable",
            "unified_exec",
            "--disable",
            "code_mode_host",
            "--disable",
            "tool_suggest",
            "--disable",
            "sleep_tool",
            "-c",
            "model_instructions_file={decision_instructions}",
        ],
        "episode": [
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--enable",
            "skip_host_skill_discovery",
            "--disable",
            "plugins",
            "--disable",
            "apps",
            "--disable",
            "skill_search",
            "-c",
            "skills.max_context_tokens=1",
            "-c",
            "skills.include_instructions=false",
            "-c",
            "model_instructions_file={decision_instructions}",
        ],
    }
    assert routes[_CODEX_ROUTE].decision_protocol == {
        "format": "codex_exec_jsonl",
        "help_args": ["exec", "--help"],
        "argv": codex_args,
        "instruction_files": ["$CODEX_HOME/AGENTS.md"],
    }
    claude_common = [
        "--output-format",
        "json",
        "--safe-mode",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    assert routes[_CLAUDE_ROUTE].decision_protocol == {
        "format": "claude_print_json",
        "help_args": ["--help"],
        "argv": {
            "dataset_answer": ["-p", "--tools", "", *claude_common],
            "episode": [
                "-p",
                "--tools",
                "Read,Grep,Glob",
                "--permission-mode",
                "plan",
                *claude_common,
            ],
        },
        "instruction_files": [],
    }
    shipped_codex = next(r for r in shipped["routes"] if r["route_id"] == _CODEX_ROUTE)
    assert routes[_CODEX_ROUTE].command == shipped_codex["command"], (
        "presence-probe command is unchanged"
    )
    assert shipped_codex["command"][-1].startswith("Reply with exactly BENCHMARK_OK")

    real_fixture_path = fixtures.fixture_path

    def mutated(name: str, mutate: Callable[[dict[str, Any]], None]) -> None:
        data = copy.deepcopy(shipped)
        mutate(data)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(
            fixtures,
            "fixture_path",
            lambda n: path if n == "provider_routes.json" else real_fixture_path(n),
        )
        with pytest.raises(FixtureError):
            fixtures.load_provider_routes()
        monkeypatch.setattr(fixtures, "fixture_path", real_fixture_path)

    def codex(data: dict[str, Any]) -> dict[str, Any]:
        return next(r for r in data["routes"] if r["route_id"] == _CODEX_ROUTE)

    mutated("unknown_route_key", lambda d: d["routes"][0].update(extra="x"))
    mutated(
        "unknown_protocol_key",
        lambda d: codex(d)["decision_protocol"].update(extra="x"),
    )
    mutated("bad_format", lambda d: codex(d)["decision_protocol"].update(format="x"))
    mutated(
        "empty_help_args", lambda d: codex(d)["decision_protocol"].update(help_args=[])
    )
    mutated(
        "help_args_not_strings",
        lambda d: codex(d)["decision_protocol"].update(help_args=[1]),
    )
    mutated(
        "argv_missing_kind",
        lambda d: codex(d)["decision_protocol"]["argv"].pop("episode"),
    )
    mutated(
        "argv_extra_kind",
        lambda d: codex(d)["decision_protocol"]["argv"].update(other=["x"]),
    )
    mutated(
        "argv_not_list",
        lambda d: codex(d)["decision_protocol"]["argv"].update(episode="exec"),
    )
    mutated(
        "instruction_file_other",
        lambda d: codex(d)["decision_protocol"].update(
            instruction_files=["/etc/passwd"]
        ),
    )
    mutated("protocol_not_dict", lambda d: codex(d).update(decision_protocol=["x"]))
    mutated("missing_route_key", lambda d: d["routes"][0].pop("terms_url"))


# ==========================================================================
# Redaction (D15)
# ==========================================================================


@pytest.mark.parametrize(
    "route", [_CLAUDE_ROUTE, _CODEX_ROUTE], ids=["claude", "codex"]
)
def test_live_output_redacted(route: str, tmp_path: Path) -> None:
    home = str(Path.home())
    leaky = f"2023-05-10 {_SECRET} {home}/x/"
    rules = _only(
        "lme-q-001",
        _rule(
            {"case_id": "lme-q-001"},
            decision={"kind": "answer", "text": leaky},
            stderr=f"stderr leak {_SECRET} {home}/x/",
        ),
    )
    fmt = _FORMAT_OF_ROUTE[route]
    res = _live(tmp_path, route, plan=_plan(fmt, rules=rules), capture_tmp=True).ran()
    files = [p for p in res.out_dir.rglob("*") if p.is_file()]
    assert files
    blobs = [p.read_bytes() for p in files] + res.written_tmp
    assert res.written_tmp, "the report is written through memory-suite-report.tmp"
    needles = [_SECRET, home, _SESSION_ID, _UUID, _THREAD_ID]
    for blob in blobs:
        text = blob.decode("utf-8")
        for needle in needles:
            assert needle not in text, needle
    report = res.report
    assert report["redaction_count"] >= 4
    text = res.report_path.read_text(encoding="utf-8")
    assert "~/x/" in text
    assert "[REDACTED" in text
    seen_id = _SESSION_ID if fmt == "claude" else _THREAD_ID
    assert "redacted:" + hashlib.sha256(seen_id.encode()).hexdigest()[:12] in text
    record = res.record("lme-q-001")
    assert record["passed"] is True, "redaction must not change what is evaluated"
    assert "2023-05-10" in record["answer"]


def test_live_output_redacts_dictionary_keys(tmp_path: Path) -> None:
    home = str(Path.home())
    secret_key = _SECRET
    home_key = f"{home}/counter"
    usage = _usage("codex", extra={secret_key: 7, home_key: 3})
    rules = _only("lme-q-001", _rule({"case_id": "lme-q-001"}, usage_raw=usage))
    res = _live(
        tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules), capture_tmp=True
    ).ran()
    blobs = [
        p.read_bytes() for p in res.out_dir.rglob("*") if p.is_file()
    ] + res.written_tmp
    assert blobs and res.written_tmp
    for blob in blobs:
        text = blob.decode("utf-8")
        assert _SECRET not in text
        assert home not in text
    record = res.record("lme-q-001")
    assert record["budget"]["model_tokens"] == 110, (
        "unknown counters never change the accounting"
    )
    usages = [i["usage"] for i in record["invocations"]]
    assert len(usages) == 1
    values = sorted(
        v
        for k, v in usages[0].items()
        if k not in {"input_tokens", "cached_input_tokens", "output_tokens"}
    )
    assert values == [3, 7], "counter values are kept under the redacted keys"
    redacted_keys = [
        k
        for k in usages[0]
        if k not in {"input_tokens", "cached_input_tokens", "output_tokens"}
    ]
    assert any("[REDACTED" in k for k in redacted_keys)
    assert any(k.startswith("~") for k in redacted_keys)
    baseline = _live(
        tmp_path / "plain",
        _CODEX_ROUTE,
        plan=_plan("codex", rules=_only("lme-q-001")),
        capture_tmp=True,
    ).ran()
    assert res.report["redaction_count"] > baseline.report["redaction_count"]


def test_redact_report_unit() -> None:
    from scripts.benchmarks import reporting

    home = str(Path.home())
    payload = {
        "text": f"key {_SECRET} home {home}/p and {home}",
        "nested": [
            {
                "session_id": _SESSION_ID,
                "other": f"see {_SESSION_ID} twice {_SESSION_ID}",
            }
        ],
        "uuid": _UUID,
        "thread_id": "short",
        _SECRET: 1,
        "path": Path("/tmp/x"),
        "num": 5,
        "flag": True,
        "none": None,
    }
    redacted, count = reporting.redact_report(
        payload,
        redaction_patterns=[r"zz-[a-z]{4}"],
        provider_id_values=("provider-extra-1",),
    )
    text = json.dumps(redacted)
    assert _SECRET not in text and _SESSION_ID not in text and _UUID not in text
    assert home not in text
    assert (
        redacted["num"] == 5 and redacted["flag"] is True and redacted["none"] is None
    )
    assert redacted["thread_id"] == "short", (
        "a value shorter than 8 characters is not an id"
    )
    assert redacted["path"] == "/tmp/x"
    marker = "redacted:" + hashlib.sha256(_SESSION_ID.encode()).hexdigest()[:12]
    assert redacted["nested"][0]["session_id"] == marker
    assert redacted["nested"][0]["other"] == f"see {marker} twice {marker}"
    assert count >= 6
    again, second_count = reporting.redact_report(
        redacted, redaction_patterns=[], provider_id_values=()
    )
    assert again == redacted, "an already redacted value is left unchanged"
    assert second_count == 0
    patterned, pattern_count = reporting.redact_report(
        {"a": "x zz-abcd y"}, redaction_patterns=[r"zz-[a-z]{4}"], provider_id_values=()
    )
    assert patterned == {"a": "x [REDACTED] y"} and pattern_count == 1
    extra, extra_count = reporting.redact_report(
        {"a": "has provider-extra-1 inside"},
        redaction_patterns=[],
        provider_id_values=("provider-extra-1",),
    )
    assert "provider-extra-1" not in json.dumps(extra) and extra_count == 1


def test_write_memory_suite_report_redacts_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.benchmarks import reporting

    captured: list[bytes] = []
    real_replace = os.replace

    def replace_seam(src: Any, dst: Any, *a: Any, **k: Any) -> None:
        captured.append(Path(src).read_bytes())
        real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", replace_seam)
    out = tmp_path / "out"
    path = reporting.write_memory_suite_report(
        out,
        {"leak": _SECRET, "p": Path(str(Path.home())) / "x"},
        redaction_patterns=(),
        provider_id_values=(),
    )
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["redaction_count"] >= 2
    assert _SECRET not in path.read_text(encoding="utf-8")
    assert captured and all(_SECRET.encode() not in blob for blob in captured)
    assert sorted(p.name for p in out.iterdir()) == ["memory-suite-report.json"]


# ==========================================================================
# Episode action validation (G8-A)
# ==========================================================================


def _action(operation: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "action", "operation": operation, "kwargs": kwargs}


def _verify_decision(
    *,
    patch: Any = _PATCH_BOTH,
    commands: Any = None,
    request_extra: dict[str, Any] | None = None,
    contract_extra: dict[str, Any] | None = None,
    request: Any = None,
    contract: Any = None,
    kwargs_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chosen_contract = {
        "patch_content_digest": "p",
        "required_commands": copy.deepcopy(_UPLOAD_COMMANDS)
        if commands is None
        else commands,
        "config_digest": "c",
        "review_class": "standard",
        **(contract_extra or {}),
    }
    body = {
        "attempt_id": "scripted",
        "behavior_ids": list(_UPLOAD_BEHAVIORS),
        "contract": chosen_contract if contract is None else contract,
        "patch": patch,
        **(request_extra or {}),
    }
    return _action(
        "verify_attempt",
        {"request": body if request is None else request, **(kwargs_extra or {})},
    )


_VERIFY_ROWS: list[Any] = [
    pytest.param(
        _verify_decision(patch=_PATCH_CHECKER),
        "edit_outside_editable_paths",
        id="patch_checker",
    ),
    pytest.param(
        _verify_decision(patch="not a diff at all"),
        "edit_outside_editable_paths",
        id="patch_non_diff",
    ),
    pytest.param(
        _verify_decision(patch=_PATCH_TWO_FILES),
        "edit_outside_editable_paths",
        id="patch_two_files",
    ),
    pytest.param(
        _verify_decision(patch=7), "edit_outside_editable_paths", id="patch_not_string"
    ),
    pytest.param(
        _verify_decision(commands=[{"command": ["true"], "expected_exit_code": 0}]),
        "contract_not_fixture_owned",
        id="model_command",
    ),
    pytest.param(
        _verify_decision(commands=[]), "contract_not_fixture_owned", id="empty_commands"
    ),
    pytest.param(
        _verify_decision(
            commands=[
                {"command": ["{python}", "check_upload.py"], "expected_exit_code": 0},
                {"command": ["{python}", "-c", "pass"], "expected_exit_code": 0},
            ]
        ),
        "contract_not_fixture_owned",
        id="extra_command",
    ),
    pytest.param(
        _verify_decision(
            commands=[
                {
                    "command": ["{python}", "check_upload.py"],
                    "expected_exit_code": 0,
                    "cwd_relative": "x",
                }
            ]
        ),
        "contract_not_fixture_owned",
        id="command_entry_extra_key",
    ),
    pytest.param(
        _verify_decision(
            commands=[
                {"command": ["{python}", "check_upload.py"], "expected_exit_code": 1}
            ]
        ),
        "contract_not_fixture_owned",
        id="command_exit_code_changed",
    ),
    pytest.param(
        _verify_decision(contract_extra={"sandbox_path": "/tmp"}),
        "unknown_decision_field",
        id="sandbox_path_override",
    ),
    pytest.param(
        _verify_decision(request_extra={"declared_permissions": {"build": True}}),
        "unknown_decision_field",
        id="declared_permissions",
    ),
    pytest.param(
        _verify_decision(request="not a dict"),
        "unknown_decision_field",
        id="request_not_dict",
    ),
    pytest.param(
        _verify_decision(contract="not a dict"),
        "unknown_decision_field",
        id="contract_not_dict",
    ),
    pytest.param(
        _verify_decision(kwargs_extra={"permissions": {"build": True}}),
        "unknown_decision_field",
        id="verify_kwarg_permissions",
    ),
    pytest.param(
        _verify_decision(kwargs_extra={"path": "/tmp"}),
        "unknown_decision_field",
        id="verify_kwarg_path",
    ),
    pytest.param(
        _action("recall", {"query": "x"}),
        "action_not_permitted",
        id="unoffered_operation",
    ),
    pytest.param(_action("submit", {}), "action_not_permitted", id="submit_as_action"),
    pytest.param(
        _action(
            "write",
            {"subject": "domain_knowledge", "content": {"text": "x"}, "source": "s"},
        ),
        "action_not_permitted",
        id="write_not_offered",
    ),
]


@pytest.mark.parametrize(("decision", "reason"), _VERIFY_ROWS)
def test_upload_repair_action_validation_rows(
    decision: dict[str, Any], reason: str, tmp_path: Path
) -> None:
    rules = _only("upload-repair", _for_case("upload-repair", decision=decision))
    res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
    record = res.record("upload-repair")
    assert record["reason"] == reason
    assert record["passed"] is False
    assert record["harness_completed"] is False
    assert res.tool_ops().count("verify_attempt") == 0, (
        "a refused decision never reaches MemoryTool.run"
    )
    assert not [c for c in res.kit.tool_calls if c.operation == "recall"]
    assert len(res.kit.decisions_for("upload-repair")) == 1


def test_action_outside_permitted_actions_fails(tmp_path: Path) -> None:
    rules = _only(
        "upload-repair",
        _for_case("upload-repair", decision=_action("recall", {"query": "upload"})),
    )
    res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
    record = res.record("upload-repair")
    assert record["reason"] == "action_not_permitted"
    assert record["passed"] is False
    assert res.tool_ops().count("recall") == 0
    assert "verify_attempt" not in res.tool_ops()


def test_live_patch_cannot_modify_checker(tmp_path: Path) -> None:
    rules = _only(
        "upload-repair",
        _for_case("upload-repair", decision=_verify_decision(patch=_PATCH_CHECKER)),
    )
    res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
    record = res.record("upload-repair")
    assert record["reason"] == "edit_outside_editable_paths"
    assert record["passed"] is False
    assert "verify_attempt" not in res.tool_ops()
    non_diff = _live(
        tmp_path / "non-diff",
        _CODEX_ROUTE,
        plan=_plan(
            "codex",
            rules=_only(
                "upload-repair",
                _for_case(
                    "upload-repair", decision=_verify_decision(patch="not a diff")
                ),
            ),
        ),
    ).ran()
    assert non_diff.record("upload-repair")["reason"] == "edit_outside_editable_paths"
    assert "verify_attempt" not in non_diff.tool_ops()


@pytest.mark.parametrize(
    "cell", ["model_command", "sandbox_path_override", "declared_permissions"]
)
def test_contract_must_be_fixture_owned(cell: str, tmp_path: Path) -> None:
    decisions = {
        "model_command": (
            _verify_decision(commands=[{"command": ["true"], "expected_exit_code": 0}]),
            "contract_not_fixture_owned",
        ),
        "sandbox_path_override": (
            _verify_decision(contract_extra={"sandbox_path": "/tmp"}),
            "unknown_decision_field",
        ),
        "declared_permissions": (
            _verify_decision(request_extra={"declared_permissions": {"build": True}}),
            "unknown_decision_field",
        ),
    }
    decision, reason = decisions[cell]
    res = _live(
        tmp_path,
        _CODEX_ROUTE,
        plan=_plan(
            "codex",
            rules=_only("upload-repair", _for_case("upload-repair", decision=decision)),
        ),
    ).ran()
    assert res.record("upload-repair")["reason"] == reason
    assert "verify_attempt" not in res.tool_ops()


_HANDOFF_ROWS: list[Any] = [
    pytest.param(
        0,
        "write",
        {
            "subject": "domain_knowledge",
            "content": {"text": "x"},
            "source": "guest-session",
            "permissions": {"build": True},
        },
        "unknown_decision_field",
        id="write_permissions",
    ),
    pytest.param(
        0,
        "write",
        {
            "subject": "domain_knowledge",
            "content": {"text": "x"},
            "source": "guest-session",
            "path": "/tmp",
        },
        "unknown_decision_field",
        id="write_path",
    ),
    pytest.param(
        0,
        "write",
        {
            "subject": "domain_knowledge",
            "content": {"text": "x"},
            "source": "guest-session",
            "owner_scope": {"kind": "user", "id": "x"},
        },
        "unknown_decision_field",
        id="write_owner_scope",
    ),
    pytest.param(
        0,
        "write",
        {
            "subject": "domain_knowledge",
            "content": {"text": "x"},
            "source": "guest-session",
            "user_stated": True,
        },
        "unknown_decision_field",
        id="write_user_stated",
    ),
    pytest.param(
        0,
        "write",
        {
            "subject": "domain_knowledge",
            "content": {"text": "x"},
            "source": "guest-session",
            "symbol_ref": {"path": "a.py"},
        },
        "unknown_decision_field",
        id="write_symbol_ref",
    ),
    pytest.param(
        0,
        "write",
        {
            "subject": "domain_knowledge",
            "content": {"text": "x"},
            "source": "guest-session",
            "query": "x",
        },
        "unknown_decision_field",
        id="write_query",
    ),
    pytest.param(
        1,
        "handoff",
        {"request": {"action": "prepare"}, "project_id": "x"},
        "unknown_decision_field",
        id="handoff_project_id",
    ),
    pytest.param(
        1,
        "handoff",
        {"request": {"action": "prepare"}, "invocation_id": "x"},
        "unknown_decision_field",
        id="handoff_invocation_id",
    ),
    pytest.param(
        2,
        "receive",
        {"request": {"session_id": "x"}, "session_id": "y"},
        "unknown_decision_field",
        id="receive_session_id",
    ),
    pytest.param(
        2,
        "receive",
        {"request": {"session_id": "x"}, "agent_id": "y"},
        "unknown_decision_field",
        id="receive_agent_id",
    ),
    pytest.param(
        3,
        "expand",
        {
            "session_allowlist": ["guest-session"],
            "request": {"id": "x", "version": 1},
            "include_archived": True,
        },
        "unknown_decision_field",
        id="expand_include_archived",
    ),
    pytest.param(
        3,
        "expand",
        {
            "session_allowlist": ["guest-session"],
            "request": {"id": "x", "version": 1},
            "candidate_sources": ["x"],
        },
        "unknown_decision_field",
        id="expand_candidate_sources",
    ),
    pytest.param(
        1, "recall", {"query": "x"}, "action_not_permitted", id="recall_not_offered"
    ),
    pytest.param(
        1,
        "last_success_diagnose",
        {"request": {"behavior_id": "x", "conditions": {}}},
        "action_not_permitted",
        id="diagnose_not_offered_to_guest",
    ),
    pytest.param(2, "submit", {}, "action_not_permitted", id="submit_as_action"),
]


@pytest.mark.parametrize(("step", "operation", "kwargs", "reason"), _HANDOFF_ROWS)
def test_guest_handoff_action_validation_rows(
    step: int, operation: str, kwargs: dict[str, Any], reason: str, tmp_path: Path
) -> None:
    rules = _only(
        "guest-handoff",
        _rule(
            {"case_id": "guest-handoff", "decision_kind": "episode", "step": step},
            decision=_action(operation, kwargs),
        ),
    )
    res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
    record = res.record("guest-handoff")
    assert record["reason"] == reason
    assert record["passed"] is False
    assert record["harness_completed"] is False
    assert len(res.kit.decisions_for("guest-handoff")) == step + 1
    guest_calls = [
        c
        for c in res.kit.tool_calls
        if c.operation == operation and c.operation != "submit"
    ]
    if operation in {"recall", "last_success_diagnose"}:
        assert guest_calls == []
    if step == 0:
        assert not [
            c for c in res.kit.tool_calls if c.kwargs.get("source") == "guest-session"
        ]


def test_expanded_python_token_only_exact_elements(tmp_path: Path) -> None:
    res = _live(
        tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=_only("upload-repair"))
    ).ran()
    verifies = [c for c in res.kit.tool_calls if c.operation == "verify_attempt"]
    sent = verifies[0].kwargs["request"]["contract"]["required_commands"]
    assert sent == [
        {"command": [sys.executable, "check_upload.py"], "expected_exit_code": 0}
    ]
    suffixed = [{"command": ["{python}x", "check_upload.py"], "expected_exit_code": 0}]
    res2 = _live(
        tmp_path / "suffixed",
        _CODEX_ROUTE,
        plan=_plan(
            "codex",
            rules=_only(
                "upload-repair",
                _for_case(
                    "upload-repair", decision=_verify_decision(commands=suffixed)
                ),
            ),
        ),
    ).ran()
    assert res2.record("upload-repair")["reason"] == "contract_not_fixture_owned"
    assert "verify_attempt" not in res2.tool_ops()


# ==========================================================================
# Component manifest runs
# ==========================================================================


@pytest.mark.parametrize("case_id", ["guest-handoff", "diagnosis-handoff"])
def test_handoff_refs_bound_from_store(
    case_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.store import TypedArtifactStore

    payloads: list[tuple[str, int, tuple[str, str | None] | None]] = []
    receipts: list[dict[str, int]] = []
    real_payload = TypedArtifactStore.get_version_payload
    real_receipts = TypedArtifactStore.get_handoff_receipts

    def payload_spy(self: Any, artifact_id: str, version: int) -> Any:
        found = real_payload(self, artifact_id, version)
        payloads.append((artifact_id, version, found))
        return found

    def receipts_spy(self: Any, session_id: str) -> Any:
        found = real_receipts(self, session_id)
        receipts.append(dict(found))
        return found

    monkeypatch.setattr(TypedArtifactStore, "get_version_payload", payload_spy)
    monkeypatch.setattr(TypedArtifactStore, "get_handoff_receipts", receipts_spy)
    res = _component(tmp_path, variant="none").ran()
    record = res.record(case_id)
    assert record["passed"] is True, record
    assert record["reason"] is None
    assert record["evaluator"] == "receiver_readback_acknowledged"
    source = "guest-session" if case_id == "guest-handoff" else "diagnosis-session"
    writes = [
        c
        for c in res.kit.tool_calls
        if c.operation == "write" and c.kwargs.get("source") == source
    ]
    assert len(writes) == 1
    raw = writes[0].result["raw"]
    bound = record["bound_refs"]
    assert [(b["id"], b["version"]) for b in bound] == [
        (raw["id"], raw["artifact_version"])
    ]
    expands = [
        c
        for c in res.kit.tool_calls
        if c.operation == "expand" and c.kwargs.get("session_allowlist") == [source]
    ]
    content = base64.b64decode(expands[0].result["raw"]["data"]["content_base64"])
    assert bound[0]["digest"] == hashlib.sha256(content).hexdigest()
    stored = [
        found
        for (aid, ver, found) in payloads
        if aid == raw["id"] and ver == raw["artifact_version"] and found is not None
    ]
    assert stored, "the evaluator read the stored payload"
    stored_content, payload_hash = stored[-1]
    assert (
        hashlib.sha256(stored_content.encode("utf-8")).hexdigest() == bound[0]["digest"]
    )
    assert payload_hash is None or payload_hash == bound[0]["digest"]
    assert any(r.get(raw["id"]) == raw["artifact_version"] for r in receipts)


def test_component_manifest_cases_are_harness_labeled(tmp_path: Path) -> None:
    res = _component(tmp_path, variant="none", extra=("--seeds", "4,5")).ran()
    report = res.report
    assert report["decision_mode"] == "component"
    assert report["seed_semantics"] == "bootstrap_seed"
    assert report["seeds"] == [4, 5]
    assert report["decision_route"] is None
    assert any("was not exercised" in b for b in report["blockers"])
    assert report["usage_accounting"]["budget_basis"] == "local_cl100k"
    for case_id in ("lme-q-001", "lme-q-002"):
        record = res.record(case_id)
        assert record["evaluator"] == "normalized_contains"
        assert record["budget"]["model_tokens"] is None
    assert res.kit.spawns == []


# ==========================================================================
# G10: a whole run stays inside tmp
# ==========================================================================

_AUDIT_STATE: dict[str, Any] = {"installed": False, "active": [], "busy": False}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_RUN_DIR_NAMES = {
    "home",
    "xdg",
    "localappdata",
    "codex-home",
    "tmp",
    "kit",
    "out",
    "manifest.json",
}


class _WriteAudit:
    """Every filesystem write the process attempts while the audit is active,
    split into paths inside `root` and paths outside it."""

    def __init__(self, root: Path) -> None:
        self.root = os.path.normcase(os.path.realpath(root))
        self.inside: list[str] = []
        self.outside: list[tuple[str, str]] = []

    def record(self, event: str, raw: Any, dir_fd: int | None = None) -> None:
        from urllib.parse import unquote

        if raw is None or isinstance(raw, int):
            return
        text = os.fsdecode(raw)
        if text.startswith("file:"):
            path_part, _, query = text[5:].partition("?")
            if "mode=ro" in query:
                return
            text = unquote(path_part).removeprefix("//")
        if text in {"", ":memory:"} or text == os.devnull or text.startswith("/dev/"):
            return
        base = os.getcwd()
        if dir_fd is not None and dir_fd >= 0 and not os.path.isabs(text):
            # a dir_fd-relative target resolves against the directory the fd
            # refers to, not the cwd; an fd that cannot be resolved is flagged
            fd_dir = _dir_fd_path(dir_fd)
            if fd_dir is None:
                self.outside.append((event, f"<unresolved dir_fd {dir_fd}>/{text}"))
                return
            base = fd_dir
        full = os.path.normcase(os.path.realpath(os.path.join(base, text)))
        if "__pycache__" in Path(full).parts or full.endswith(".pyc"):
            return
        if full == self.root or full.startswith(self.root + os.sep):
            self.inside.append(full)
        else:
            self.outside.append((event, full))


def _dir_fd_path(dir_fd: int) -> str | None:
    """The directory a dir_fd refers to (macOS F_GETPATH, Linux /proc/self/fd);
    None when the platform cannot say."""
    try:
        if sys.platform == "darwin":
            import fcntl

            raw = fcntl.fcntl(dir_fd, fcntl.F_GETPATH, b"\0" * 1024)
            return os.fsdecode(raw.split(b"\0", 1)[0])
        return os.readlink(f"/proc/self/fd/{dir_fd}")
    except (OSError, ImportError, AttributeError):
        return None


def _audit_hook(event: str, args: tuple[Any, ...]) -> None:
    active = _AUDIT_STATE["active"]
    if not active or _AUDIT_STATE["busy"]:
        return

    def at(index: int) -> int | None:
        return args[index] if len(args) > index else None

    # (target, dir_fd that target is relative to); the audit args carry the
    # dir_fd of os.remove/rmdir/mkdir/chmod/rename/symlink/link, but not of
    # os.open, whose relative targets therefore resolve against the cwd
    targets: list[tuple[Any, int | None]]
    if event == "open":
        flags = args[2] if len(args) > 2 else None
        if not isinstance(flags, int) or not flags & _WRITE_FLAGS:
            return
        targets = [(args[0], None)]
    elif event in {"os.remove", "os.rmdir"}:
        targets = [(args[0], at(1))]
    elif event in {"os.mkdir", "os.chmod"}:
        targets = [(args[0], at(2))]
    elif event == "os.truncate":
        targets = [(args[0], None)]
    elif event == "os.rename":
        targets = [(args[0], at(2)), (args[1], at(3))]
    elif event == "os.symlink":
        targets = [(args[1], at(2))]
    elif event == "os.link":
        targets = [(args[1], at(3))]
    elif event == "sqlite3.connect":
        targets = [(args[0], None)]
    else:
        return
    _AUDIT_STATE["busy"] = True
    try:
        # an audit hook must never break the operation it observes
        with contextlib.suppress(Exception):
            for audit in list(active):
                for target, dir_fd in targets:
                    audit.record(event, target, dir_fd)
    finally:
        _AUDIT_STATE["busy"] = False


@contextlib.contextmanager
def _audit_writes(root: Path) -> Iterator[_WriteAudit]:
    if not _AUDIT_STATE["installed"]:
        sys.addaudithook(_audit_hook)
        _AUDIT_STATE["installed"] = True
    audit = _WriteAudit(root)
    _AUDIT_STATE["active"].append(audit)
    try:
        yield audit
    finally:
        _AUDIT_STATE["active"].remove(audit)


def _within(value: Any, root: Path) -> bool:
    if not value:
        return False
    resolved = os.path.normcase(os.path.realpath(os.fspath(value)))
    top = os.path.normcase(os.path.realpath(root))
    return resolved == top or resolved.startswith(top + os.sep)


def _repo_state() -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for rel in ("scripts", "tests/fixtures", ".scratch", ".rush"):
        top = _REPO / rel
        if not top.exists():
            state[rel] = (-1, -1)
            continue
        state[rel] = (0, 0)
        for path in sorted(top.rglob("*")):
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            stat = path.lstat()
            state[path.relative_to(_REPO).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return state


def test_g10_run_stays_inside_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both live routes and a component run keep every write, every child
    process cwd and every child process HOME/XDG_DATA_HOME/LOCALAPPDATA/
    CODEX_HOME inside the test's own tmp tree; nothing is left behind and the
    repository checkout is untouched."""
    assert _within(Path.home(), tmp_path), "the autouse isolation moved HOME into tmp"
    for name in ("XDG_DATA_HOME", "LOCALAPPDATA", "CODEX_HOME"):
        assert _within(os.environ[name], tmp_path), name

    real_init = subprocess.Popen.__init__
    spawned: list[dict[str, Any]] = []

    def spy(self: Any, args: Any, *a: Any, **kw: Any) -> None:
        env = kw.get("env")
        spawned.append(
            {
                "argv": args
                if isinstance(args, str)
                else [os.fsdecode(part) for part in args],
                "cwd": kw.get("cwd"),
                "env": dict(os.environ if env is None else env),
            }
        )
        real_init(self, args, *a, **kw)

    monkeypatch.setattr(subprocess.Popen, "__init__", spy)
    repo_before = _repo_state()

    scenarios: list[tuple[str, Callable[[Path], RunResult]]] = [
        ("codex", lambda base: _live(base, _CODEX_ROUTE)),
        (
            "claude",
            lambda base: _live(
                base,
                _CLAUDE_ROUTE,
                plan=_plan("claude", rules=_only("lme-q-001")),
            ),
        ),
        ("component", lambda base: _component(base, variant="none")),
    ]
    for name, run in scenarios:
        base = tmp_path / name
        start = len(spawned)
        with _audit_writes(base) as audit:
            res = run(base).ran()
        assert audit.outside == [], (name, audit.outside[:5])
        assert audit.inside, f"{name}: the audit saw no write, so it proved nothing"
        workspace_prefix = os.path.normcase(
            os.path.join(os.path.realpath(base), "tmp", "memory-suite-")
        )
        assert any(w.startswith(workspace_prefix) for w in audit.inside), (
            f"{name}: the run never created its workspace under the isolated temp dir"
        )
        assert {p.name for p in base.iterdir()} <= _RUN_DIR_NAMES, (
            name,
            sorted(p.name for p in base.iterdir()),
        )
        assert list((base / "tmp").glob("memory-suite-*")) == [], (
            f"{name}: workspace left behind"
        )
        assert res.report_path.parent == base / "out"
        assert res.report_path.exists()
        new_spawns = spawned[start:]
        assert new_spawns, f"{name}: no child process was observed"
        for spawn in new_spawns:
            for var in ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA", "CODEX_HOME"):
                assert _within(spawn["env"].get(var), base), (
                    name,
                    var,
                    spawn["env"].get(var),
                    spawn["argv"],
                )
            if spawn["cwd"] is not None:
                assert _within(spawn["cwd"], base), (name, spawn["cwd"], spawn["argv"])
    assert _repo_state() == repo_before, "the run changed the repository checkout"


# ==========================================================================
# Handoff namespace is bound to acceptance.handoff.source (live decider)
# ==========================================================================

_SOURCE_OF_CASE = {
    "guest-handoff": "guest-session",
    "diagnosis-handoff": "diagnosis-session",
}


@pytest.mark.parametrize("case_id", ["guest-handoff", "diagnosis-handoff"])
@pytest.mark.parametrize("namespace", ["omitted", "matching", "foreign"])
def test_handoff_namespace_bound_to_source(
    case_id: str, namespace: str, tmp_path: Path
) -> None:
    source = _SOURCE_OF_CASE[case_id]
    plan = _plan("codex", rules=_only(case_id))
    if namespace == "matching":
        plan["handoff_namespace"] = source
    elif namespace == "foreign":
        plan["handoff_namespace"] = "other-session"
    res = _live(tmp_path, _CODEX_ROUTE, plan=plan).ran()

    request = res.kit.decisions_for(case_id)[0]["request"]
    schema = json.dumps(request["operations"]["handoff"])
    assert re.search(r"receiver_namespace[^,}]*acceptance\.handoff\.source", schema), (
        schema
    )
    assert "receiver_audience" in schema, "audience stays a separate field"

    record = res.record(case_id)
    writes = [
        c
        for c in res.kit.tool_calls
        if c.operation == "write" and c.kwargs.get("source") == source
    ]
    assert len(writes) == 1, "the note is written before the handoff is attempted"
    raw = writes[0].result["raw"]
    handoffs = [c for c in res.kit.tool_calls if c.operation == "handoff"]
    receives = [c for c in res.kit.tool_calls if c.operation == "receive"]

    if namespace == "foreign":
        assert record["passed"] is False
        assert record["harness_completed"] is False
        assert record["reason"] == "action_not_permitted"
        assert handoffs == [], "a foreign namespace never reaches a handoff event"
        assert receives == []
        assert [c for c in res.kit.tool_calls if c.operation == "expand"] == []
        return

    assert record["reason"] is None, record
    assert record["passed"] is True
    assert len(handoffs) == 1
    sent = handoffs[0].kwargs["request"]
    assert sent["receiver_namespace"] == source, "the bound request carries the source"
    assert sent["receiver_audience"] == "handoff-receiver"
    assert sent["action"] == "prepare"
    assert sent["goal"] == "hand off the note"
    assert sent["selected_refs"] == [
        {"id": raw["id"], "version": raw["artifact_version"]}
    ], "all other request fields are forwarded unchanged"
    assert len(receives) == 2
    delivered = receives[0].result["raw"]["data"]["changes"]
    assert [(c["id"], c["version"]) for c in delivered] == [
        (raw["id"], raw["artifact_version"])
    ], "the bare receive delivers the written ref"
    acked = receives[1].kwargs["request"]["ack"]
    assert [(a["id"], a["version"]) for a in acked] == [
        (raw["id"], raw["artifact_version"])
    ], "the acknowledgment names the written ref"
    assert [(b["id"], b["version"]) for b in record["bound_refs"]] == [
        (raw["id"], raw["artifact_version"])
    ]


# ==========================================================================
# G15: non-string discriminators, unbounded recursion, cleanup masking
# ==========================================================================

_EPISODE_ONLY_OPS = frozenset(
    {"verify_attempt", "handoff", "receive", "expand", "last_success_diagnose"}
)
_G15_MANIFEST_CELLS: dict[str, tuple[tuple[Any, ...], Callable[[Any], Any]]] = {
    "case_kind": (("cases", 0, "kind"), lambda v: v),
    "case_variant": (("cases", 0, "variant"), lambda v: v),
    "case_evaluator": (("cases", 0, "acceptance", "evaluator"), lambda v: v),
    "case_builder": (("cases", _UPLOAD, "inputs", "builder"), lambda v: v),
    "permission_entry": (("cases", 0, "grants"), lambda v: [v]),
    "action_entry": (("cases", _UPLOAD, "permitted_actions"), lambda v: ["submit", v]),
}
_G15_DECISION_CELLS = [
    "decision_kind_episode",
    "decision_kind_answer",
    "decision_operation",
]
_G15_PROVIDER_CELLS = [
    "codex_event_type",
    "codex_item_completed_type",
    "codex_item_started_type",
]
_G15_CELLS = [
    *_G15_MANIFEST_CELLS,
    "protocol_format",
    *_G15_DECISION_CELLS,
    *_G15_PROVIDER_CELLS,
]


@pytest.mark.parametrize(
    ("cell", "shape"),
    [
        pytest.param(cell, shape, id=f"{cell}-{shape}")
        for cell in _G15_CELLS
        for shape in ("list", "dict")
    ],
)
def test_evaluator_g15_enum_shapes(
    cell: str, shape: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value: Any = [] if shape == "list" else {}

    if cell in _G15_MANIFEST_CELLS:
        location, wrap = _G15_MANIFEST_CELLS[cell]
        path = _row_mutate(_set(location, wrap(value)))(tmp_path)
        with pytest.raises(FixtureError) as caught:
            _load(path)
        assert _code(caught.value) == "wrong_type", str(caught.value)
        res = _live(tmp_path, _CODEX_ROUTE, manifest_path=path)
        _assert_rejected(res, "wrong_type", base=tmp_path)
        return

    if cell == "protocol_format":
        from scripts.benchmarks import fixtures

        shipped = json.loads(
            fixtures.fixture_path("provider_routes.json").read_text(encoding="utf-8")
        )
        route = next(r for r in shipped["routes"] if r["route_id"] == _CODEX_ROUTE)
        assert route.get("decision_protocol") is not None, (
            "the shipped Codex live route carries a decision_protocol"
        )
        route["decision_protocol"]["format"] = value
        altered = tmp_path / "routes.json"
        altered.write_text(json.dumps(shipped), encoding="utf-8")
        real_fixture_path = fixtures.fixture_path
        monkeypatch.setattr(
            fixtures,
            "fixture_path",
            lambda n: altered if n == "provider_routes.json" else real_fixture_path(n),
        )
        with pytest.raises(FixtureError):
            fixtures.load_provider_routes()
        return

    if cell in _G15_DECISION_CELLS:
        if cell == "decision_kind_answer":
            case_id = "lme-q-001"
            special = _rule(
                {"case_id": case_id, "decision_kind": "answer"},
                decision={"kind": value, "text": "x"},
            )
        else:
            case_id = "upload-repair"
            decision = (
                {"kind": value, "final": "x"}
                if cell == "decision_kind_episode"
                else {"kind": "action", "operation": value, "kwargs": {}}
            )
            special = _for_case(case_id, decision=decision)
        res = _live(
            tmp_path,
            _CODEX_ROUTE,
            plan=_plan("codex", rules=_only(case_id, special)),
        ).ran()
        record = res.record(case_id)
        assert record["passed"] is False
        assert record["reason"] == "malformed_decision_json", record
        assert record["harness_completed"] is False
        refused = [c for c in res.kit.tool_calls if c.operation in _EPISODE_ONLY_OPS]
        assert refused == [], "a refused decision never reaches a tool"
        return

    if cell == "codex_event_type":
        weird: dict[str, Any] = {"type": value}
    elif cell == "codex_item_completed_type":
        weird = {
            "type": "item.completed",
            "item": {"id": "item_x", "type": value, "text": "x"},
        }
    else:
        weird = {
            "type": "item.started",
            "item": {"id": "item_x", "type": value, "text": "x"},
        }
    events = [_TS, _TURN, weird, _msg(_VALID_TEXT), _done()]
    rules = [
        _PREFLIGHT_NORMAL,
        _rule({"decision_kind": ["answer", "episode"]}, events=events),
    ]
    res = _live(tmp_path, _CODEX_ROUTE, plan=_plan("codex", rules=rules)).ran()
    assert len(res.records) == 5
    for record in res.records:
        assert record["passed"] is False, record["case_id"]
        assert record["reason"] == "unsupported_event", (
            record["case_id"],
            record["reason"],
        )
    assert [c for c in res.kit.tool_calls if c.operation in _EPISODE_ONLY_OPS] == []


_DEEP_RAW = 200_000
_DEEP_DECODED = 600


def _deep_list(depth: int) -> list[Any]:
    node: list[Any] = []
    for _ in range(depth):
        node = [node]
    return node


def _frame_depth() -> int:
    depth = 0
    frame: Any = sys._getframe()
    while frame is not None:
        depth += 1
        frame = frame.f_back
    return depth


@contextlib.contextmanager
def _python_recursion_headroom(extra: int) -> Iterator[None]:
    """Lower the interpreter recursion limit to `extra` frames above the current
    depth. The JSON C codecs do not count against it; Python-level walkers do.
    The previous limit is restored before the caller sees any exception."""
    previous = sys.getrecursionlimit()
    sys.setrecursionlimit(_frame_depth() + extra)
    try:
        yield
    finally:
        sys.setrecursionlimit(previous)


_G15_NESTED_CELLS = [
    "manifest_raw_over_limit",
    "manifest_decoded_traversal",
    "codex_envelope",
    "claude_envelope",
    "decision_json",
    "report_redact_python_limit",
    "report_redact_c_limit",
    "report_write_python_limit",
    "report_write_c_limit",
]


def _report_call(cell: str, reporting: Any, out: Path, payload: Any) -> None:
    if cell.startswith("report_redact"):
        reporting.redact_report(payload, redaction_patterns=(), provider_id_values=())
    else:
        reporting.write_memory_suite_report(
            out, payload, redaction_patterns=(), provider_id_values=()
        )


@pytest.mark.parametrize("cell", _G15_NESTED_CELLS)
def test_evaluator_g15_nested_json_refused(cell: str, tmp_path: Path) -> None:
    limit_before = sys.getrecursionlimit()
    deep_raw = "[" * _DEEP_RAW + "]" * _DEEP_RAW

    if cell == "manifest_raw_over_limit":
        path = tmp_path / "manifest.json"
        path.write_text(
            '{"schema_version":1,"cases":' + deep_raw + "}", encoding="utf-8"
        )
        with pytest.raises(FixtureError) as caught:
            _load(path)
        assert _code(caught.value) == "manifest_unreadable", str(caught.value)
        _assert_rejected(
            _live(tmp_path, _CODEX_ROUTE, manifest_path=path),
            "manifest_unreadable",
            base=tmp_path,
        )
    elif cell == "manifest_decoded_traversal":
        obj = _manifest_obj()
        obj["cases"][0]["inputs"]["query"] = _deep_list(_DEEP_DECODED)
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        with pytest.raises(FixtureError) as caught, _python_recursion_headroom(200):
            _load(path)
        assert sys.getrecursionlimit() == limit_before
        assert _code(caught.value) == "invalid_value", str(caught.value)
    elif cell in {"codex_envelope", "claude_envelope", "decision_json"}:
        both = {"decision_kind": ["answer", "episode"]}
        if cell == "codex_envelope":
            route, fmt, reason = _CODEX_ROUTE, "codex", "unsupported_event"
            action: dict[str, Any] = {"extra_lines": [deep_raw]}
        elif cell == "claude_envelope":
            route, fmt, reason = _CLAUDE_ROUTE, "claude", "non_json_stdout"
            action = {"stdout": deep_raw + "\n"}
        else:
            route, fmt, reason = _CODEX_ROUTE, "codex", "malformed_decision_json"
            action = {"text": deep_raw}
        res = _live(
            tmp_path,
            route,
            plan=_plan(fmt, rules=[_PREFLIGHT_NORMAL, _rule(both, **action)]),
        ).ran()
        assert len(res.records) == 5
        for record in res.records:
            assert record["passed"] is False, record["case_id"]
            assert record["reason"] == reason, (record["case_id"], record["reason"])
        assert [c for c in res.kit.tool_calls if c.operation in _EPISODE_ONLY_OPS] == []
    else:
        from scripts.benchmarks import reporting

        python_limit = cell.endswith("python_limit")
        payload = {"deep": _deep_list(_DEEP_DECODED if python_limit else _DEEP_RAW)}
        out = tmp_path / "out"
        out.mkdir()
        existing = out / "memory-suite-report.json"
        existing.write_bytes(b'{"keep": true}\n')
        with pytest.raises(FixtureError) as caught:
            if python_limit:
                with _python_recursion_headroom(200):
                    _report_call(cell, reporting, out, payload)
            else:
                _report_call(cell, reporting, out, payload)
        assert sys.getrecursionlimit() == limit_before
        assert _code(caught.value) == "invalid_value", str(caught.value)
        assert existing.read_bytes() == b'{"keep": true}\n', "no output write happened"
        assert sorted(p.name for p in out.iterdir()) == ["memory-suite-report.json"]

    assert sys.getrecursionlimit() == limit_before


_CLEANUP_WS = "injected-workspace-cleanup"
_CLEANUP_VIEW = "injected-view-close"
_CLEANUP_PAYLOAD = "injected-payload-read"


def _exception_chain_text(exc: BaseException) -> str:
    seen: set[int] = set()
    parts: list[str] = []
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__ or cur.__context__
    return "\n".join(parts)


@pytest.mark.parametrize(
    "cell",
    ["workspace_only", "workspace_and_primary", "view_only", "view_and_primary"],
)
def test_evaluator_cleanup_failures_preserve_primary(
    cell: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.store import TypedArtifactStore

    manifest = _write_manifest(tmp_path / "manifest.json", _manifest_obj())
    first = _component(tmp_path, manifest_path=manifest, variant="none").ran()
    before = first.report_path.read_bytes()
    leak = f"{_SECRET} {Path.home()}/x"
    real_cleanup = tempfile.TemporaryDirectory.cleanup
    real_close = TypedArtifactStore.close
    real_payload = TypedArtifactStore.get_version_payload
    real_open_view = TypedArtifactStore.open_readonly_view

    def install(mp: pytest.MonkeyPatch) -> None:
        if cell.startswith("workspace"):

            def failing_cleanup(self: Any) -> None:
                real_cleanup(self)
                if Path(self.name).name.startswith("memory-suite-"):
                    raise OSError(f"{_CLEANUP_WS} {leak}")

            mp.setattr(tempfile.TemporaryDirectory, "cleanup", failing_cleanup)
        else:
            # Fault only the read-only view the evaluator opens through its own
            # module name. A class-level patch would also fail the views the
            # product's read-only receive path opens and closes first, so the
            # evaluator's payload read would never run.
            class _EvaluatorStore(TypedArtifactStore):
                @classmethod
                def open_readonly_view(cls, *args: Any, **kwargs: Any) -> Any:
                    view, reason = real_open_view(*args, **kwargs)
                    if view is None:
                        return view, reason
                    real_view_close = view.close

                    def failing_close() -> None:
                        real_view_close()
                        raise OSError(f"{_CLEANUP_VIEW} {leak}")

                    view.close = failing_close  # type: ignore[method-assign]  # test deliberately patches the instance
                    if cell == "view_and_primary":

                        def failing_payload(artifact_id: str, version: int) -> Any:
                            raise OSError(f"{_CLEANUP_PAYLOAD} {leak}")

                        view.get_version_payload = failing_payload  # type: ignore[method-assign]  # test deliberately patches the instance
                    return view, reason

            mp.setattr(bm, "TypedArtifactStore", _EvaluatorStore)
        if cell == "workspace_and_primary":
            mp.setattr(bm, "_UPLOAD_BUGGY", bm._UPLOAD_BUGGY + "# changed\n")

    markers = {
        "workspace_only": [_CLEANUP_WS],
        "workspace_and_primary": [_CLEANUP_WS, "fixture_revision_mismatch"],
        "view_only": [_CLEANUP_VIEW],
        "view_and_primary": [_CLEANUP_VIEW, _CLEANUP_PAYLOAD],
    }[cell]

    with monkeypatch.context() as mp:
        install(mp)
        res = _component(tmp_path, manifest_path=manifest, variant="none")
    assert tempfile.TemporaryDirectory.cleanup is real_cleanup, "seam restored"
    assert TypedArtifactStore.close is real_close
    assert TypedArtifactStore.get_version_payload is real_payload
    assert bm.TypedArtifactStore is TypedArtifactStore

    assert res.error is None, repr(res.error)
    assert res.exit_code == 1, res.stderr
    assert "Memory suite error: cleanup_failed" in res.stderr, res.stderr
    for marker in markers:
        assert marker in res.stderr, (marker, res.stderr)
    assert "Traceback" not in res.stderr, "a controlled diagnostic, not a traceback"
    assert _SECRET not in res.stderr and str(Path.home()) not in res.stderr, (
        "the diagnostic is redacted"
    )
    assert list((tmp_path / "tmp").glob("memory-suite-*")) == []
    assert sorted(p.name for p in res.out_dir.iterdir()) == [
        "memory-suite-report.json"
    ], "no partial report file"
    after = res.report_path.read_bytes()
    if cell == "workspace_only":
        assert after == before or json.loads(after)["decision_mode"] == "component"
    else:
        assert after == before, "publication never occurred, the report is unchanged"

    if cell.startswith("view"):
        root = tmp_path / "direct-root"
        root.mkdir()
        guest = _scripted(root, _handoff_script(root))
        with monkeypatch.context() as mp:
            install(mp)
            with pytest.raises(FixtureError) as caught:
                bm.receiver_readback_acknowledged(guest.events, _GUEST_ACCEPTANCE, root)
        assert _code(caught.value) == "cleanup_failed", str(caught.value)
        chain = _exception_chain_text(caught.value)
        for marker in markers:
            assert marker in chain, (marker, chain)


# ==========================================================================
# Preservation oracle self-check
# ==========================================================================

_ORACLE_COMPONENTS = {
    "fixture_files",
    "db_bytes",
    "db_refs",
    "db_receipts",
    "report",
    "provider_log",
    "data_root",
    "git_status",
    "git_staged",
    "git_index_raw",
}


def _oracle_tree(root: Path, skip: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts[0] in skip:
            continue
        if path.is_symlink():
            out[rel.as_posix()] = "symlink:" + os.readlink(path)
        elif path.is_dir():
            out[rel.as_posix()] = "dir"
        else:
            out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _oracle_snapshot(
    fixture: Path, run_base: Path, report: Path, log: Path
) -> dict[str, Any]:
    import sqlite3

    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}

    def git(*args: str) -> bytes:
        proc = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *args],
            cwd=fixture,
            env=env,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, (args, proc.stderr)
        return proc.stdout

    db = fixture / ".rush" / "memory.db"
    wal = fixture / ".rush" / "memory.db-wal"
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        refs = con.execute(
            "SELECT id, artifact_version FROM memory_artifacts ORDER BY id"
        ).fetchall()
        receipts = sorted(
            repr(row) for row in con.execute("SELECT * FROM memory_handoff_receipts")
        )
    finally:
        con.close()
    data_root: dict[str, str] = {}
    for name in ("home", "xdg", "localappdata", "codex-home"):
        for rel, digest in _oracle_tree(run_base / name, ()).items():
            data_root[f"{name}/{rel}"] = digest
    return {
        "fixture_files": _oracle_tree(fixture, (".git", ".rush")),
        "db_bytes": hashlib.sha256(
            db.read_bytes() + b"\0wal\0" + (wal.read_bytes() if wal.exists() else b"")
        ).hexdigest(),
        "db_refs": [tuple(row) for row in refs],
        "db_receipts": receipts,
        "report": hashlib.sha256(report.read_bytes()).hexdigest(),
        "provider_log": hashlib.sha256(log.read_bytes()).hexdigest(),
        "data_root": data_root,
        "git_status": git("status", "--porcelain=v1", "-z", "--untracked-files=all"),
        "git_staged": (
            git("ls-files", "-s", "-z"),
            git("diff", "--cached", "--binary"),
        ),
        "git_index_raw": hashlib.sha256(
            (fixture / ".git" / "index").read_bytes()
        ).hexdigest(),
    }


def _oracle_sql(fixture: Path, statement: str) -> None:
    import sqlite3

    con = sqlite3.connect(fixture / ".rush" / "memory.db")
    try:
        con.execute(statement)
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()


def _oracle_git(fixture: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", *args],
        cwd=fixture,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, (args, proc.stderr)


def _oracle_append(path: Path, data: bytes) -> None:
    with open(path, "ab") as fh:
        fh.write(data)


def _oracle_stash(stash_root: Path, paths: list[Path]) -> Callable[[], None]:
    saved: list[tuple[Path, Path]] = []
    for index, path in enumerate(paths):
        copy = stash_root / f"{index}"
        if path.is_dir():
            shutil.copytree(path, copy, symlinks=True)
        else:
            shutil.copy2(path, copy)
        saved.append((path, copy))

    def restore() -> None:
        for path, copy in saved:
            if path.is_dir():
                shutil.rmtree(path)
                shutil.copytree(copy, path, symlinks=True)
            else:
                shutil.copy2(copy, path)

    return restore


def test_evaluator_preservation_oracle_self_check(tmp_path: Path) -> None:
    """The snapshot the zero-effect assertions rely on detects a mutation of
    each captured component, on its own where the component is independent,
    and a restored mutation returns the exact baseline."""
    run_base = tmp_path / "run"
    res = _live(
        run_base,
        _CODEX_ROUTE,
        plan=_plan("codex", rules=_only("lme-q-001")),
        agents_md="# agents\n",
    ).ran()
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    bm._init_upload_repair_repo(fixture)
    episode = _scripted(fixture, _handoff_script(fixture))
    assert [e.operation for e in episode.events][-1] == "receive"
    report, log = res.report_path, res.kit.log_path

    def snap() -> dict[str, Any]:
        return _oracle_snapshot(fixture, run_base, report, log)

    baseline = snap()
    assert set(baseline) == _ORACLE_COMPONENTS, "a successful snapshot keeps every part"
    assert "upload.py" in baseline["fixture_files"]
    assert len(baseline["db_refs"]) == 1 and len(baseline["db_receipts"]) >= 1
    assert baseline["data_root"], "the isolated data roots hold the Codex AGENTS.md"
    assert log.stat().st_size > 0 and report.stat().st_size > 0
    assert snap() == baseline, "an unchanged state snapshots identically"

    def mutate_staged() -> None:
        _oracle_append(fixture / "upload.py", b"# staged\n")
        _oracle_git(fixture, "add", "upload.py")

    # (cell id, paths to stash, mutation, components that must change, exact set?)
    cells: list[tuple[str, list[Path], Callable[[], Any], set[str], bool]] = [
        (
            "fixture_file",
            [fixture],
            lambda: _oracle_append(fixture / "upload.py", b"# mutated\n"),
            {"fixture_files"},
            False,
        ),
        (
            "db_bytes",
            [fixture],
            lambda: _oracle_sql(fixture, "PRAGMA user_version = 7"),
            {"db_bytes"},
            True,
        ),
        (
            "db_refs",
            [fixture],
            lambda: _oracle_sql(
                fixture,
                "UPDATE memory_artifacts SET artifact_version = artifact_version + 5",
            ),
            {"db_refs", "db_bytes"},
            False,
        ),
        (
            "db_receipts",
            [fixture],
            lambda: _oracle_sql(fixture, "DELETE FROM memory_handoff_receipts"),
            {"db_receipts", "db_bytes"},
            False,
        ),
        (
            "output_report",
            [report],
            lambda: _oracle_append(report, b" "),
            {"report"},
            True,
        ),
        (
            "provider_log",
            [log],
            lambda: _oracle_append(log, b'{"kind": "rogue"}\n'),
            {"provider_log"},
            True,
        ),
        (
            "data_root_inventory",
            [run_base / "xdg"],
            lambda: (run_base / "xdg" / "rogue.txt").write_bytes(b"x"),
            {"data_root"},
            True,
        ),
        (
            "git_status",
            [fixture],
            lambda: (fixture / "rogue.txt").write_bytes(b"x"),
            {"git_status", "fixture_files"},
            False,
        ),
        (
            "git_staged_content",
            [fixture],
            mutate_staged,
            {"git_staged", "git_index_raw", "fixture_files"},
            False,
        ),
        (
            "git_index_raw_bytes",
            [fixture],
            lambda: _oracle_git(fixture, "update-index", "--index-version", "4"),
            {"git_index_raw"},
            True,
        ),
    ]
    covered = set()
    for index, (cell_id, paths, mutate, expected, exact) in enumerate(cells):
        stash_root = tmp_path / f"stash-{index}"
        stash_root.mkdir()
        restore = _oracle_stash(stash_root, paths)
        try:
            mutate()
            changed = {k for k, v in snap().items() if v != baseline[k]}
            assert changed, f"{cell_id}: the snapshot did not see the mutation"
            if exact:
                assert changed == expected, (cell_id, sorted(changed))
            else:
                assert expected <= changed, (cell_id, sorted(changed))
            covered |= changed
        finally:
            restore()
        assert snap() == baseline, f"{cell_id}: restore did not return the baseline"
    assert covered == _ORACLE_COMPONENTS, "every captured component was mutated"
