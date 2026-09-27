"""Setup wizard: reviewed, consented project setup (Phase 70 T24).

Architecture §8, Phase 23. Phase 65 §6.2 routes every engine install through
the declarative `rush.setup.engine_packages` allowlist and the
`rush.setup.provision` plan builder/applier, so engines install under their
canonical registry package identity (e.g. `@biomejs/biome`), never a bare
executable name. Phase 70 T24 removes the legacy per-stack installer
entirely: the only install path is `apply_provision_plan`.

`build_setup_review` is a read-only preview of four ordered stages -- config
(create from the `generate_initial_config` template, or reuse a valid
`rush.toml` byte-for-byte), registration, configuration, and engines -- with
the grants each stage needs. `apply_setup_review` applies that review only
after consent (interactive) or explicit grants (non-interactive),
revalidates every precondition immediately before its effect, and
compensates config/registry writes only while they still hold exactly what
this transaction wrote.

Phase 70 T26 extends the same review with one selected LLM CLI host (Claude
Code or Codex CLI): its project-bound MCP registration, the separately
consented instruction block, hooks and capability probe, and the session
selection the server binds to. The versioned envelope
`{kind:"setup", schema_version:1, review, setup_plan_id}` carries it to a
saved-plan apply; `setup_plan_id` is the canonical SHA-256 of `review`.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import shutil
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

from rush.config import RushConfigError, load_config
from rush.discovery.stack import detect_project_stacks
from rush.integrations.agent_hooks import (
    activation_record_path,
    read_activation_record,
    set_hook_activation,
)
from rush.integrations.agents import (
    ADAPTERS,
    HOST_BINARIES,
    HOST_LOGIN_ACTIONS,
    HOST_PROBE_ARGS,
    HOST_READBACK_ARGS,
    INSTRUCTION_TARGETS,
    AgentConnectionError,
    HostCommandError,
    HostRunner,
    apply_agent_instructions,
    apply_project_registration,
    host_readback_connected,
    installed_plugin_roots,
    observed_status_project_ids,
    parse_host_tool_calls,
    plan_agent_instructions,
    plan_manual_entry_removal,
    plan_project_registration,
    read_project_registration_entry,
    resolve_rush_binary,
    run_host_command,
    same_server_entry,
)
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions, check_permissions
from rush.setup.engine_packages import ENGINE_PACKAGES
from rush.setup.provision import (
    Downloader,
    HttpGet,
    Prober,
    ProvisionPlan,
    ProvisionResult,
    Runner,
    apply_provision_plan,
    build_provision_plan,
    current_os_arch,
    default_data_root,
    plan_from_dict,
    plan_is_complete,
    plan_to_dict,
    resolve_and_apply_provision_plan,
    resolve_provision_identities,
)
from rush.tools.init_config import generate_initial_config
from rush.workflows import projects as registry

logger = get_logger("tools.setup_wizard")

STAGE_GRANTS: dict[str, tuple[str, ...]] = {
    "config_create": ("artifact_write",),
    "register": ("cache_write", "artifact_write"),
    "configure": ("cache_write",),
    "identity_resolution": ("network",),
}

_SKIP_REASONS = {"n": "declined", "eof": "eof", "interrupt": "interrupt"}

# Phase 70 T26: the LLM CLI hosts `rush setup --agent` connects (Cursor is out
# of Phase 70 scope) and the grants each host stage needs.
SETUP_HOSTS: dict[str, str] = {"claude": "claude-code", "codex": "codex"}
HOST_STAGE_GRANTS: dict[str, tuple[str, ...]] = {
    "host_registration": ("cache_write",),
    "select": ("cache_write",),
    "guidance": ("cache_write", "artifact_write"),
    # The same grants `rush agent connect` needs to write the activation.
    "hooks": ("cache_write", "artifact_write"),
    "probe": ("network",),
    # The representative check: `build` lets its test step run pytest;
    # `cache_write` covers the Rush-owned fixture under the data root.
    "check": ("build", "cache_write"),
}
_PROJECT_ID_PLACEHOLDER = "<project_id>"
# The check stage's fixture: a known F401 (unused import) plus one passing
# test, so every step of the six-step check has something real to run.
_PROBE_MARKER = ".rush-probe-owner.json"
_PROBE_FILES = {
    "pyproject.toml": '[project]\nname = "rush-probe"\nversion = "0.0.0"\n',
    "probe.py": "import os\n",
    "test_probe.py": "def test_probe() -> None:\n    assert True\n",
}
_CHECK_DEADLINE_SECONDS = 300.0


def _check_stage(data_root: Path, requested: bool) -> dict[str, Any]:
    """T17/T26 representative check: `rush check` on a Rush-owned fixture
    under `data_root/probes/<nonce>/`, never the user's project, run by setup
    only on its own consent (--run-check, or "y" to its question)."""
    fixture = data_root / "probes" / "<nonce>"
    return {
        "requested": requested,
        "state": "pending" if requested else "not_requested",
        "fixture": str(fixture),
        "command": f"rush check {_quote(str(fixture))} --json",
    }


def _create_probe_fixture(data_root: Path) -> tuple[Path, str]:
    """A fresh `data_root/probes/<nonce>/` holding the ownership marker and
    the known-faulty fixture. Raises OSError."""
    nonce = uuid.uuid4().hex
    probes = data_root / "probes"
    probes.mkdir(parents=True, exist_ok=True)
    fixture = probes / nonce
    fixture.mkdir()
    (fixture / _PROBE_MARKER).write_text(
        json.dumps({"owner": "rush-setup-check", "nonce": nonce}), encoding="utf-8"
    )
    for name, text in _PROBE_FILES.items():
        (fixture / name).write_text(text, encoding="utf-8")
    return fixture, nonce


def _remove_probe_fixture(fixture: Path, nonce: str) -> bool:
    """Delete the fixture only while its ownership marker still names this
    run's nonce; anything else there is left untouched."""
    try:
        marker = json.loads((fixture / _PROBE_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(marker, dict) or marker.get("nonce") != nonce:
        return False
    shutil.rmtree(fixture, ignore_errors=True)
    return not fixture.exists()


def _check_failed(
    command: str, blocker: str, detail: str, recovery: str
) -> dict[str, Any]:
    return {
        "state": "failed",
        "blocker": blocker,
        "detail": detail,
        "recovery_actions": [recovery],
        "command": command,
    }


def _run_check_stage(
    review: dict[str, Any],
    choices: dict[str, bool],
    permissions: ExecutionPermissions | None,
) -> dict[str, Any]:
    """Run the shared `CheckTool` once on a Rush-owned fixture (never the
    user's project) with the check stage's grants only, bounded by a
    deadline, and report its real result; nothing runs without consent.
    Callers run this outside `_setup_lock`."""
    check = review["check"]
    command = check["command"]
    if choices.get("check") is False:
        return {"state": "declined", "command": command}
    if not choices.get("check"):
        if not check.get("requested"):
            return {"state": "not_requested", "command": command}
        return {
            "state": "pending",
            "reason": "not authorized: pass --run-check",
            "command": command,
        }
    from rush.runtime.binaries import AnalysisScope, analysis_scope
    from rush.tools.check import CheckTool

    granted = permissions or ExecutionPermissions()
    try:
        fixture, nonce = _create_probe_fixture(Path(review["data_root"]))
    except OSError as exc:
        return _check_failed(
            command,
            "probe_fixture_unavailable",
            str(exc),
            f"{review['resume_command']} --run-check",
        )
    deadline = time.monotonic() + _CHECK_DEADLINE_SECONDS
    try:
        # Engines resolve as for the project's own check: from the
        # toolchains manifests setup provisioned for the project root.
        with analysis_scope(AnalysisScope(Path(review["project_root"]))):
            result: dict[str, Any] = dict(
                CheckTool().run(
                    fixture,
                    # Only this stage's grants: the test step's build, no more.
                    permissions=ExecutionPermissions(build=granted.build),
                    cancel_check=lambda: time.monotonic() >= deadline,
                    cancel_cause="setup_check_deadline",
                    invocation_start_cwd=fixture,
                )
            )
    except Exception as exc:  # noqa: BLE001 -- a failed check is reported, setup completes
        removed = _remove_probe_fixture(fixture, nonce)
        return {
            **_check_failed(
                command,
                "check_crashed",
                f"{type(exc).__name__}: {exc}",
                f"{review['resume_command']} --run-check",
            ),
            "fixture": str(fixture),
            "fixture_removed": removed,
        }
    removed = _remove_probe_fixture(fixture, nonce)
    children = (result.get("metadata") or {}).get("children") or []
    return {
        "state": "ran",
        "fixture": str(fixture),
        "fixture_removed": removed,
        "finding_rules": sorted(
            {str(f.get("rule")) for f in result.get("findings") or []}
        ),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "steps": [
            {
                "tool": child.get("tool"),
                "status": child.get("status"),
                "disposition": (child.get("execution") or {}).get("disposition"),
                "cause": (child.get("execution") or {}).get("cause"),
            }
            for child in children
        ],
        "findings": len(result.get("findings") or []),
        "command": command,
    }


def run_setup_wizard(
    root: Path,
    non_interactive: bool = True,
    *,
    install: bool = False,
    permissions: ExecutionPermissions | None = None,
    project_id: str | None = None,
    data_root: Path | None = None,
    http_get: HttpGet | None = None,
    downloader: Downloader | None = None,
    runner: Runner | None = None,
    prober: Prober | None = None,
) -> dict[str, Any]:
    """Detect stacks and recommend engines for unattended callers.

    Callers: InstallTool, `rush scan --install`, and the dashboard setup and
    provision routes. ``install=False`` only detects and recommends.
    ``install=True`` builds the provision plan; with ``permissions`` it
    resolves identities under the caller's own network grant and applies
    that plan in the same invocation (`identity_source="resolved_at_apply"`).
    ``non_interactive`` is kept for caller compatibility and no longer
    selects any install behavior: nothing installs outside
    `apply_provision_plan`.
    """
    del non_interactive  # kept only so existing callers keep working
    stacks = detect_project_stacks(root)
    suggested = [e for stack in stacks for e in stack.suggested_engines]
    results: dict[str, Any] = {
        "stacks": [s.language for s in stacks],
        "installed": [],
        "skipped": suggested,
    }
    log_subsystem("setup", "INFO", f"Detected project stacks: {results['stacks']}")
    if not install:
        return results

    known_engine_ids = sorted({e for e in suggested if e in ENGINE_PACKAGES})
    results["unsupported_engines"] = sorted(set(suggested) - set(known_engine_ids))
    resolved_data_root = data_root or default_data_root()
    plan: ProvisionPlan = build_provision_plan(
        root, known_engine_ids, data_root=resolved_data_root
    )
    results["plan_id"] = plan.plan_id
    if permissions is None:
        results["provision"] = {"plan_only": True}
        return results
    fakes: dict[str, Any] = {
        "http_get": http_get,
        "downloader": downloader,
        "runner": runner,
        "prober": prober,
    }
    outcome = resolve_and_apply_provision_plan(
        plan,
        permissions,
        project_id=project_id or str(root.resolve()),
        data_root=resolved_data_root,
        **{k: v for k, v in fakes.items() if v is not None},
    )
    results["installed"] = sorted(outcome.applied)
    results["provision"] = {
        "applied": sorted(outcome.applied),
        "failed": outcome.failed,
        "permission_blocked": outcome.permission_blocked,
        "requires_input": outcome.requires_input,
        "reused": sorted(outcome.reused),
        "recovery_required": outcome.recovery_required,
        "identity_source": outcome.identity_source,
    }
    return results


# --- Review ------------------------------------------------------------------


class ConsentIO(Protocol):
    """Interactive consent channel. `ask` returns exactly one of "y", "n",
    "eof" (input closed) or "interrupt" (Ctrl-C); `write` shows text."""

    def ask(self, prompt: str) -> str: ...

    def write(self, text: str) -> None: ...


class TerminalConsentIO:
    """ConsentIO over the process's own stdin/stdout terminal."""

    def ask(self, prompt: str) -> str:
        try:
            answer = input(prompt)
        except EOFError:
            return "eof"
        except KeyboardInterrupt:
            return "interrupt"
        return "y" if answer.strip().lower() in ("y", "yes") else "n"

    def write(self, text: str) -> None:
        print(text, flush=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _config_diagnostic(root: Path) -> str | None:
    try:
        load_config(root)
    except (RushConfigError, ValueError, TypeError, OSError) as exc:
        return f"{exc}; fix or move rush.toml, then rerun `rush setup`"
    return None


def _config_stage(root: Path) -> dict[str, Any]:
    path = root / "rush.toml"
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        content = generate_initial_config(root)
        return {
            "action": "create",
            "path": str(path),
            "sha256": _sha256(content.encode("utf-8")),
            "content": content,
        }
    except OSError as exc:
        return {
            "action": "invalid",
            "path": str(path),
            "sha256": None,
            "diagnostic": f"cannot read {path}: {exc}",
        }
    diagnostic = _config_diagnostic(root)
    if diagnostic is not None:
        return {
            "action": "invalid",
            "path": str(path),
            "sha256": _sha256(raw),
            "diagnostic": diagnostic,
        }
    return {"action": "reuse", "path": str(path), "sha256": _sha256(raw)}


def _registration_stage(root: Path, data_root: Path) -> dict[str, Any]:
    state = registry.read_registry_strict(data_root)
    if state["state"] in ("corrupt", "unreadable"):
        return {
            "state": state["state"],
            "path": state["path"],
            "sha256": state["sha256"],
            "diagnostic": (
                f"project registry {state['path']} is {state['state']} "
                f"({state['error']}); repair or move it, then rerun `rush setup`"
            ),
        }
    projects = (state["registry"] or {}).get("projects", {})
    for project_id, entry in projects.items():
        if entry.get("root") == str(root):
            return {
                "state": "existing",
                "project_id": project_id,
                "revision": int(entry.get("revision", 1)),
                "configured": bool(entry.get("configured", False)),
            }
    return {"state": "new", "project_id": None, "revision": None}


def _review_id(review: dict[str, Any]) -> str:
    body = {k: v for k, v in review.items() if k != "review_id"}
    return _sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())


def _with_plan(review: dict[str, Any], plan: ProvisionPlan) -> dict[str, Any]:
    updated = {**review, "provision": plan_to_dict(plan)}
    updated["grants"] = {**review["grants"], "engines": _engine_grants(plan)}
    updated["resolution"] = _resolution(updated["provision"])
    updated["review_id"] = _review_id(updated)
    return updated


def _engine_grants(plan: ProvisionPlan) -> dict[str, tuple[str, ...]]:
    return {
        e.engine_id: e.required_grants
        for e in plan.entries
        if e.disposition == "applicable"
    }


def _resolution(provision: dict[str, Any]) -> dict[str, Any]:
    requests = [
        e["resolution_url"] for e in provision["entries"] if e["resolution_url"]
    ]
    unresolved = [
        e["engine_id"]
        for e in provision["entries"]
        if e["disposition"] == "applicable" and e["identity_state"] == "unresolved"
    ]
    return {"required": bool(unresolved), "engines": unresolved, "requests": requests}


def build_setup_review(
    root: Path,
    data_root: Path | None = None,
    *,
    resolve: bool = False,
    permissions: ExecutionPermissions | None = None,
    which: Callable[[str], str | None] = shutil.which,
    http_get: HttpGet | None = None,
    host: str | None = None,
    home: Path | None = None,
    rush_binary: str | None = None,
    install_guidance: bool = False,
    enable_hooks: bool = False,
    verify_host: bool = False,
    run_check: bool = False,
) -> dict[str, Any]:
    """Read-only preview of every setup stage, its exact change and grants.

    Creates nothing and makes no network request unless ``resolve=True``,
    which requires the `network` grant in ``permissions`` and requests only
    the URLs listed under ``resolution.requests``.

    With ``host`` (T26: "claude" or "codex") the review also binds that
    host's project-bound registration (found with ``which``, reading host
    config under ``home``), the separately requested instruction block
    (``install_guidance``), hooks (``enable_hooks``) and capability probe
    (``verify_host``), the representative `rush check` (``run_check``), and
    the exact interactive resume command.
    """
    root = Path(root).resolve()
    data_root = data_root or default_data_root()
    stacks = detect_project_stacks(root)
    suggested = sorted({e for stack in stacks for e in stack.suggested_engines})
    known = [e for e in suggested if e in ENGINE_PACKAGES]
    plan = build_provision_plan(root, known, data_root=data_root, which=which)
    if resolve:
        extra = {"http_get": http_get} if http_get is not None else {}
        plan = resolve_provision_identities(plan, permissions, **extra)
    registration = _registration_stage(root, data_root)
    provision = plan_to_dict(plan)
    review: dict[str, Any] = {
        "kind": "setup_review",
        "schema_version": 1,
        "project_root": str(root),
        "data_root": str(data_root),
        "os": plan.os_name,
        "arch": plan.arch,
        "stacks": [s.language for s in stacks],
        "unsupported_engines": sorted(set(suggested) - set(known)),
        "config": _config_stage(root),
        "registration": registration,
        "configure": {
            "configured": True,
            "settings": {},
            "plan_id": registry.compute_settings_plan_id({}),
            "already_configured": bool(registration.get("configured", False)),
        },
        "provision": provision,
        "resolution": _resolution(provision),
        "grants": {**STAGE_GRANTS, "engines": _engine_grants(plan)},
    }
    if host is not None:
        _add_host_stages(
            review,
            host,
            home=home or Path.home(),
            which=which,
            rush_binary=rush_binary,
            choices={
                "guidance": install_guidance,
                "hooks": enable_hooks,
                "probe": verify_host,
                "check": run_check,
            },
        )
    review["review_id"] = _review_id(review)
    return review


def _needed_grants(
    review: dict[str, Any], choices: dict[str, bool] | None = None
) -> dict[str, tuple[str, ...]]:
    """Stage -> grants for the effects this review would actually perform.

    Host stages (T26) count only when the review selects a host; guidance
    and the probe count when requested in the review, or -- with
    ``choices`` -- only when also chosen now.
    """
    needed: dict[str, tuple[str, ...]] = {}
    if review.get("host") is not None:
        needed.update(_host_needed_grants(review, choices))
    if review["config"]["action"] == "create":
        needed["config_create"] = STAGE_GRANTS["config_create"]
    if review["registration"]["state"] == "new":
        needed["register"] = STAGE_GRANTS["register"]
    if not review["configure"]["already_configured"]:
        needed["configure"] = STAGE_GRANTS["configure"]
    for entry in review["provision"]["entries"]:
        if entry["disposition"] == "applicable" and entry["required_grants"]:
            needed[f"engine:{entry['engine_id']}"] = tuple(entry["required_grants"])
    return needed


def _flags(grants: tuple[str, ...] | set[str]) -> list[str]:
    _, flags = check_permissions(
        ExecutionPermissions(**{g: True for g in grants}), ExecutionPermissions()
    )
    return flags


def render_setup_review(review: dict[str, Any]) -> str:
    """Plain-text preview of every stage, its change, and its grants."""
    config = review["config"]
    lines = [f"Rush setup review for {review['project_root']}"]
    if config["action"] == "create":
        lines.append(f"  1. Config: create rush.toml (sha256 {config['sha256'][:12]})")
    elif config["action"] == "reuse":
        lines.append(
            f"  1. Config: reuse rush.toml unchanged (sha256 {config['sha256'][:12]})"
        )
    else:
        lines.append(f"  1. Config: INVALID -- {config['diagnostic']}")
    reg = review["registration"]
    if reg["state"] == "new":
        lines.append(
            f"  2. Register: add project to {review['data_root']}/projects.json"
        )
    elif reg["state"] == "existing":
        lines.append(
            f"  2. Register: already {reg['project_id']} (revision {reg['revision']})"
        )
    else:
        lines.append(f"  2. Register: BLOCKED -- {reg['diagnostic']}")
    configure = review["configure"]
    lines.append(
        "  3. Configure: already configured"
        if configure["already_configured"]
        else f"  3. Configure: mark configured, default settings (plan {configure['plan_id'][:12]})"
    )
    lines.append(f"  4. Engines (plan {review['provision']['plan_id'][:12]}):")
    lines.extend(_render_entry(e) for e in review["provision"]["entries"])
    if review["unsupported_engines"]:
        lines.append(
            f"     not installable by Rush: {', '.join(review['unsupported_engines'])}"
        )
    if review["resolution"]["required"]:
        lines.append("  Resolution-only network requests (needs --allow-network):")
        lines.extend(f"     GET {url}" for url in review["resolution"]["requests"])
    if review.get("host") is not None:
        lines.extend(_render_host_stages(review))
    needed = sorted({g for grants in _needed_grants(review).values() for g in grants})
    lines.append(f"  Grants: {' '.join(_flags(set(needed))) or 'none'}")
    lines.append(f"  review_id: {review['review_id']}")
    return "\n".join(lines)


def _render_entry(entry: dict[str, Any]) -> str:
    name = entry["engine_id"]
    identity = entry.get("identity")
    if entry["disposition"] == "requires_input":
        return f"     - {name}: requires input, not installed by setup"
    if entry["identity_state"] == "reuse_verified" and identity:
        return f"     - {name} {identity['version']}: verified install reused"
    status = (
        f"{identity['version']} via {entry['manager']} -> {entry['destination']} "
        f"[{entry['integrity']}]"
        if entry["identity_state"] == "resolved" and identity
        else entry["identity_state"]
        + (f" ({entry['resolution_error']})" if entry.get("resolution_error") else "")
    )
    blocked = (
        f" BLOCKED: {entry['blocked_reason']}" if entry.get("blocked_reason") else ""
    )
    grants = " ".join(_flags(tuple(entry["required_grants"])))
    return f"     - {name}: {status}{blocked} grants: {grants or 'none'}"


# --- Apply -------------------------------------------------------------------


class _StageConflict(Exception):
    def __init__(self, component: str, detail: str) -> None:
        super().__init__(detail)
        self.component = component
        self.detail = detail


def _skipped(answer: str, review: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": _SKIP_REASONS.get(answer, "declined"),
        "review_id": review["review_id"],
    }


def _review_problem(review: dict[str, Any]) -> dict[str, Any] | None:
    """Rejections that need no consent and have no effect."""
    if review.get("review_id") != _review_id(review):
        return {"status": "error", "reason": "review_tampered"}
    if (review["os"], review["arch"]) != current_os_arch():
        return {"status": "error", "reason": "wrong_platform"}
    if review["config"]["action"] == "invalid":
        return {
            "status": "recovery_required",
            "conflict": "config",
            "diagnostic": review["config"]["diagnostic"],
        }
    if review["registration"]["state"] not in ("new", "existing"):
        return {
            "status": "recovery_required",
            "conflict": "registration",
            "diagnostic": review["registration"]["diagnostic"],
        }
    return None


def _obtain_consent(
    review: dict[str, Any], consent: ConsentIO, http_get: HttpGet | None
) -> tuple[dict[str, Any], ExecutionPermissions] | dict[str, Any]:
    """Ask before any effect. Resolution needs its own yes; the resolved
    engines are then shown and the whole review needs a second yes. Only the
    grants the review needs become permissions."""
    consent.write(render_setup_review(review))
    if review["resolution"]["required"]:
        answer = consent.ask(
            "Allow the network requests listed above to resolve exact engine versions? [y/N] "
        )
        if answer != "y":
            return _skipped(answer, review)
        extra = {"http_get": http_get} if http_get is not None else {}
        plan = resolve_provision_identities(
            plan_from_dict(review["provision"]),
            ExecutionPermissions(network=True),
            **extra,
        )
        review = _with_plan(review, plan)
        consent.write(render_setup_review(review))
    answer = consent.ask("Apply these setup changes? [y/N] ")
    if answer != "y":
        return _skipped(answer, review)
    grants = {g for stage in _needed_grants(review).values() for g in stage}
    return review, ExecutionPermissions(**{g: True for g in grants})


def _config_state(review: dict[str, Any]) -> str:
    """`pending` (the review's precondition holds), `done` (rush.toml already
    holds exactly the reviewed bytes) or `stale` (anything else)."""
    config_path = Path(review["project_root"]) / "rush.toml"
    try:
        current: str | None = _sha256(config_path.read_bytes())
    except FileNotFoundError:
        current = None
    except OSError:
        return "stale"
    stage = review["config"]
    if current == stage["sha256"]:
        return "done"
    return "pending" if stage["action"] == "create" and current is None else "stale"


def _registration_state(review: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """`pending`, `done` (registered and configured -- the reviewed target)
    or `stale`, plus the registry's current view of the root."""
    now = _registration_stage(Path(review["project_root"]), Path(review["data_root"]))
    then = review["registration"]
    if then["state"] == "new" and now["state"] == "new":
        return "pending", now
    if (
        now["state"] == "existing"
        and now["configured"]
        and (then["state"] == "new" or now["project_id"] == then.get("project_id"))
    ):
        return "done", now
    if then["state"] == "existing" and (
        now.get("project_id"),
        now.get("revision"),
    ) == (then["project_id"], then["revision"]):
        return "pending", now
    return "stale", now


def _stale_precondition(
    review: dict[str, Any], *, resume: bool = False
) -> tuple[str, str] | None:
    """A stage that is not at its reviewed precondition.

    T24's bare review is strict: replaying it after it was applied is stale
    (`recovery_required`). A T26 envelope is resumable (``resume``): a stage
    already at its reviewed target counts as completed, not stale.
    """
    root = Path(review["project_root"])
    config = _config_state(review)
    config_ok = config == "pending" or (
        config == "done" and (resume or review["config"]["action"] == "reuse")
    )
    if not config_ok:
        return "config", f"{root / 'rush.toml'} changed after the review"
    registration, now = _registration_state(review)
    then = review["registration"]
    unchanged = (now["state"], now.get("project_id"), now.get("revision")) == (
        then["state"],
        then.get("project_id"),
        then.get("revision"),
    )
    if not (unchanged or (resume and registration == "done")):
        return "registration", "the project registry entry changed after the review"
    return None


def _create_config_exclusive(path: Path, content: bytes) -> None:
    """O_EXCL create: fails if any file appeared at `path` since the review."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise _StageConflict("config", f"{path} was created concurrently") from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        path.unlink(missing_ok=True)
        raise


SETUP_LOCK_RELATIVE_PATH = ".rush/setup.lock"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _acquire_setup_lock(lock: Path) -> int:
    """O_EXCL lock file holding the owner pid. A lock whose recorded pid no
    longer exists (crashed setup) is reclaimed once; any other existing lock,
    including one whose pid is not yet written, is a concurrent setup."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(2):
        try:
            fd = os.open(lock, flags, 0o600)
        except FileExistsError:
            try:
                owner = int(lock.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner = None
            if owner is None or _pid_alive(owner):
                raise _StageConflict(
                    "setup_lock",
                    f"another setup holds {lock}"
                    + (f" (pid {owner})" if owner is not None else "")
                    + "; wait for it to finish, or remove the file if no setup runs",
                ) from None
            lock.unlink(missing_ok=True)
            continue
        os.write(fd, str(os.getpid()).encode("ascii"))
        return fd
    raise _StageConflict("setup_lock", f"could not acquire {lock}")


@contextmanager
def _setup_lock(root: Path) -> Iterator[None]:
    """Hold the project's `.rush/setup.lock` for the whole apply. A `.rush`
    directory this lock had to create is removed again if left empty."""
    rush_dir = root / ".rush"
    if rush_dir.is_symlink():
        raise _StageConflict(
            "setup_lock", f"{rush_dir} is a symlink; refusing to use it"
        )
    created_dir = not rush_dir.exists()
    rush_dir.mkdir(exist_ok=True)
    lock = root / SETUP_LOCK_RELATIVE_PATH
    try:
        fd = _acquire_setup_lock(lock)
    except _StageConflict:
        if created_dir:
            with suppress(OSError):
                rush_dir.rmdir()
        raise
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)
        if created_dir:
            with suppress(OSError):
                rush_dir.rmdir()  # only succeeds when empty


class _SetupTransaction:
    """Records exactly what this apply wrote, for owned-only compensation."""

    def __init__(self, review: dict[str, Any]) -> None:
        self.review = review
        self.root = Path(review["project_root"])
        self.data_root = Path(review["data_root"])
        self.created_config: bytes | None = None
        self.registered: tuple[str, int] | None = None
        self.already_configured = False

    def config(self) -> None:
        stage = self.review["config"]
        path = self.root / "rush.toml"
        if _config_state(self.review) == "done":
            return  # already exactly the reviewed bytes (a completed rerun)
        if stage["action"] == "reuse":
            try:
                unchanged = _sha256(path.read_bytes()) == stage["sha256"]
            except OSError:
                unchanged = False
            if not unchanged:
                raise _StageConflict("config", f"{path} changed after the review")
            return
        content = stage["content"].encode("utf-8")
        _create_config_exclusive(path, content)
        self.created_config = content

    def register(self) -> tuple[str, int]:
        stage = self.review["registration"]
        state, now = _registration_state(self.review)
        if state == "done":
            self.already_configured = True
            return now["project_id"], int(now["revision"])
        if stage["state"] == "existing":
            return stage["project_id"], int(stage["revision"])
        try:
            record = registry.register_project(
                self.root, data_root=self.data_root, expect_new=True
            )
        except registry.ProjectRevisionConflictError as exc:
            raise _StageConflict("registration", str(exc)) from exc
        self.registered = (record.project_id, record.revision)
        return self.registered

    def configure(self, project_id: str, revision: int) -> None:
        stage = self.review["configure"]
        if stage["already_configured"] or self.already_configured:
            return
        try:
            view = registry.configure_project(
                project_id,
                stage["settings"],
                expected_revision=revision,
                apply=True,
                plan_id=stage["plan_id"],
                data_root=self.data_root,
            )
        except (
            registry.ProjectRevisionConflictError,
            registry.ProjectPlanStaleError,
            registry.ProjectNotFoundError,
        ) as exc:
            raise _StageConflict("registration", str(exc)) from exc
        if self.registered is not None:
            self.registered = (project_id, int(view["revision"]))

    def compensate(self, component: str, detail: str) -> dict[str, Any]:
        """Undo only what still holds exactly this transaction's writes."""
        kept: list[str] = []
        if self.registered is not None:
            project_id, revision = self.registered
            try:
                registry.unregister_project(
                    project_id, expected_revision=revision, data_root=self.data_root
                )
            except (registry.ProjectError, OSError):
                kept.append("registration")
        if self.created_config is not None:
            path = self.root / "rush.toml"
            try:
                if path.read_bytes() == self.created_config:
                    path.unlink()
                else:
                    kept.append("config")
            except OSError:
                kept.append("config")
        return {
            "status": "recovery_required",
            "conflict": component,
            "detail": detail,
            "review_id": self.review["review_id"],
            "compensation_conflicts": kept,
        }


def _provision_summary(result: ProvisionResult) -> dict[str, Any]:
    return {
        "plan_id": result.plan_id,
        "identity_source": result.identity_source,
        "applied": {k: m.to_dict() for k, m in result.applied.items()},
        "reused": {k: m.to_dict() for k, m in result.reused.items()},
        "failed": result.failed,
        "permission_blocked": result.permission_blocked,
        "requires_input": result.requires_input,
        "recovery_required": result.recovery_required,
    }


def _missing_grants(
    review: dict[str, Any],
    permissions: ExecutionPermissions | None,
    choices: dict[str, bool] | None = None,
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for stage, grants in _needed_grants(review, choices).items():
        ok, flags = check_permissions(
            ExecutionPermissions(**{g: True for g in grants}), permissions
        )
        if not ok:
            missing[stage] = flags
    return missing


def apply_setup_review(
    review: dict[str, Any],
    permissions: ExecutionPermissions | None,
    consent: ConsentIO | None,
    *,
    http_get: HttpGet | None = None,
    downloader: Downloader | None = None,
    runner: Runner | None = None,
    prober: Prober | None = None,
    which: Callable[[str], str | None] | None = None,
    host_runner: HostRunner | None = None,
    atomic_write_bytes: Callable[..., Any] | None = None,
    choices: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Apply a setup review: config -> register -> configure -> engines.

    With ``consent`` the review is shown and confirmed first, and only the
    reviewed grants become permissions (``permissions`` is not consulted).
    Without it, ``permissions`` must hold every grant the review needs.
    Decline/EOF/interrupt, a missing grant, or a stale precondition returns
    before any effect. A config/registration failure compensates this
    transaction's own writes; engine failures are reported per engine and
    completed verified engines are kept.

    T26: a `{kind:"setup"}` envelope continues with the host stages
    (`_apply_setup_envelope`; ``host_runner`` runs host CLI commands,
    ``atomic_write_bytes`` writes host config files, ``choices`` carries the
    non-interactive guidance/hooks/probe flags). A `{kind:"provision"}`
    payload applies only its engine plan.
    """
    fakes: dict[str, Any] = {
        "http_get": http_get,
        "downloader": downloader,
        "runner": runner,
        "prober": prober,
        "which": which,
    }
    kind = review.get("kind") if isinstance(review, dict) else None
    if kind == "setup":
        return _apply_setup_envelope(
            review,
            permissions,
            consent,
            fakes,
            host_fakes={"runner": host_runner, "writer": atomic_write_bytes},
            choices=choices,
        )
    if kind == "provision":
        return _apply_legacy_provision(review, permissions, consent, fakes)
    problem = _review_problem(review)
    if problem is not None:
        return problem
    if consent is not None:
        decision = _obtain_consent(review, consent, http_get)
        if isinstance(decision, dict):
            return decision
        review, permissions = decision
    missing = _missing_grants(review, permissions)
    if missing:
        return {
            "status": "permission_denied",
            "missing": missing,
            "review_id": review["review_id"],
        }
    try:
        with _setup_lock(Path(review["project_root"])):
            return _apply_locked(review, permissions, fakes)
    except _StageConflict as exc:
        return {
            "status": "recovery_required",
            "conflict": exc.component,
            "detail": exc.detail,
            "review_id": review["review_id"],
            "compensation_conflicts": [],
        }


def _apply_locked(
    review: dict[str, Any],
    permissions: ExecutionPermissions | None,
    fakes: dict[str, Any],
    *,
    resume: bool = False,
) -> dict[str, Any]:
    """The ordered stages, run while `.rush/setup.lock` is held: every
    precondition is rechecked under the lock before the first write."""
    stale = _stale_precondition(review, resume=resume)
    txn = _SetupTransaction(review)
    if stale is not None:
        return txn.compensate(*stale)
    stage = "config"
    try:
        txn.config()
        stage = "registration"
        project_id, revision = txn.register()
        txn.configure(project_id, revision)
    except _StageConflict as exc:
        return txn.compensate(exc.component, exc.detail)
    except (OSError, registry.ProjectError) as exc:
        return txn.compensate(stage, str(exc))
    outcome = apply_provision_plan(
        plan_from_dict(review["provision"]),
        permissions,
        project_id=project_id,
        data_root=txn.data_root,
        reviewed_plan_id=review["provision"]["plan_id"],
        **{k: v for k, v in fakes.items() if v is not None},
    )
    provision = _provision_summary(outcome)
    complete = not (outcome.failed or outcome.permission_blocked)
    return {
        "status": "ok" if complete else "partial",
        "review_id": review["review_id"],
        "project_id": project_id,
        "config": {
            "action": review["config"]["action"],
            "sha256": review["config"]["sha256"],
        },
        "provision": provision,
    }


# --- T26: host review stages ---------------------------------------------------


def _quote(value: str) -> str:
    """One argument quoted for the user's shell: PowerShell single quotes
    (a `'` doubled) on Windows, POSIX `shlex.quote` elsewhere."""
    if platform.system() == "Windows":
        return "'" + value.replace("'", "''") + "'"
    return shlex.quote(value)


def setup_resume_command(root: Path, host: str | None = None) -> str:
    """The exact, shell-quoted `rush setup` line that resumes setup interactively."""
    line = f"rush setup {_quote(str(root))}"
    return f"{line} --agent {host}" if host else line


def detected_setup_hosts(
    which: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    """The supported hosts whose CLI is on PATH, in `SETUP_HOSTS` order."""
    return [
        host
        for host, agent_id in SETUP_HOSTS.items()
        if which(HOST_BINARIES[agent_id]) is not None
    ]


def setup_plan_id(review: dict[str, Any]) -> str:
    """Canonical SHA-256 of a setup review: the envelope's `setup_plan_id`."""
    return _sha256(
        json.dumps(review, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def setup_envelope(review: dict[str, Any]) -> dict[str, Any]:
    """The strict versioned envelope a saved or guided setup applies."""
    return {
        "kind": "setup",
        "schema_version": 1,
        "review": review,
        "setup_plan_id": setup_plan_id(review),
    }


def _blocked(
    stage: dict[str, Any], blocker: str, action: str, detail: str | None = None
) -> dict[str, Any]:
    blocked = {**stage, "blocker": blocker, "recovery_actions": [action]}
    if detail:
        blocked["detail"] = detail
    return blocked


def _plugin_conversion(
    agent_id: str, home: Path, data_root: Path
) -> dict[str, Any] | None:
    """T2: the manual `rush` entry the installed plugin would replace, if any."""
    config_path = ADAPTERS[agent_id].config_paths(platform.system(), home)[0]
    try:
        removal = plan_manual_entry_removal(agent_id, config_path, data_root=data_root)
    except (AgentConnectionError, OSError, ValueError):
        return None
    return removal.to_dict() if removal is not None else None


def _host_registration_stage(
    review: dict[str, Any],
    host: str,
    *,
    home: Path,
    which: Callable[[str], str | None],
    rush_binary: str | None,
) -> dict[str, Any]:
    root = Path(review["project_root"])
    data_root = Path(review["data_root"])
    agent_id = SETUP_HOSTS[host]
    adapter = ADAPTERS[agent_id]
    binary_name = HOST_BINARIES[agent_id]
    project_id = review["registration"].get("project_id")
    resume = setup_resume_command(root, host)
    stage: dict[str, Any] = {
        "host": host,
        "agent_id": agent_id,
        "display_name": adapter.display_name,
        "session": f"{host}:{project_id or _PROJECT_ID_PLACEHOLDER}",
        "host_binary": which(binary_name),
        "rush_binary": None,
        "method": None,
        "scope": None,
        "config_path": None,
        "expected_sha256": None,
        "planned_entry": None,
        "diff": "",
        "host_change": False,
        "unchanged": False,
        "blocker": None,
        "recovery_actions": [],
    }
    if stage["host_binary"] is None:
        return _blocked(
            stage,
            "absent_host",
            f"Install {adapter.display_name} so `{binary_name}` is on PATH, "
            f"then run: {resume}",
        )
    try:
        stage["rush_binary"] = resolve_rush_binary(rush_binary)
    except AgentConnectionError as exc:
        return _blocked(
            stage,
            "rush_binary_missing",
            "Install Rush with scripts/install.sh (scripts/install.ps1 on Windows), "
            f"then run: {resume}",
            str(exc),
        )
    if installed_plugin_roots(host, data_root):
        # T2: the native plugin already registers Rush for this host; a manual
        # entry as well would run two Rush servers.
        return {
            **stage,
            "method": "native_plugin",
            "conversion": _plugin_conversion(agent_id, home, data_root),
        }
    try:
        step = plan_project_registration(
            agent_id,
            rush_binary=stage["rush_binary"],
            project_root=root,
            project_id=project_id or _PROJECT_ID_PLACEHOLDER,
            home=home,
            which=which,
        )
    except (AgentConnectionError, OSError, ValueError) as exc:
        config_path = adapter.config_paths(platform.system(), home)[0]
        return _blocked(
            stage,
            "host_config_unreadable",
            f"Fix or move {config_path}, then run: {resume}",
            str(exc),
        )
    return {
        **stage,
        "method": step.method,
        "scope": step.scope,
        "config_path": str(step.config_path),
        "expected_sha256": step.expected_sha256,
        "planned_entry": step.entry,
        "diff": step.diff,
        "host_change": step.requires_consent,
        "unchanged": step.unchanged,
    }


def _guidance_stage(
    root: Path, data_root: Path, agent_id: str, requested: bool
) -> dict[str, Any]:
    if agent_id not in INSTRUCTION_TARGETS:
        return {"requested": requested, "state": "unsupported"}
    plan = plan_agent_instructions(agent_id, project_root=root, data_root=data_root)
    report = plan.to_dict()
    report.pop("agent_id", None)
    if plan.conflict is not None:
        state = "conflict"
    else:
        state = "pending" if plan.new_bytes is not None else "unchanged"
    return {"requested": requested, **report, "state": state}


def _add_host_stages(
    review: dict[str, Any],
    host: str,
    *,
    home: Path,
    which: Callable[[str], str | None],
    rush_binary: str | None,
    choices: dict[str, bool],
) -> None:
    """Bind the selected host's stages into a T24 review (in place)."""
    if host not in SETUP_HOSTS:
        raise ValueError(
            f"unknown host {host!r}; expected one of {sorted(SETUP_HOSTS)}"
        )
    root = Path(review["project_root"])
    agent_id = SETUP_HOSTS[host]
    display = ADAPTERS[agent_id].display_name
    review["host"] = host
    review["home"] = str(home)
    stage = _host_registration_stage(
        review, host, home=home, which=which, rush_binary=rush_binary
    )
    review["registration"] = {**review["registration"], **stage}
    review["guidance"] = _guidance_stage(
        root, Path(review["data_root"]), agent_id, choices["guidance"]
    )
    review["hooks"] = _hooks_stage(
        root, Path(review["data_root"]), host, choices["hooks"]
    )
    binary = stage["host_binary"]
    review["probe"] = {
        "requested": choices["probe"],
        "cwd": str(root),
        "readback_argv": [binary, *HOST_READBACK_ARGS[agent_id]] if binary else None,
        "probe_argv": [binary, *HOST_PROBE_ARGS[agent_id]] if binary else None,
        "boundary": (
            f"launches {display} non-interactively in the project: it starts the "
            "Rush MCP server and sends one model request over the network, "
            f"billed to your {display} account"
        ),
    }
    review["check"] = _check_stage(
        Path(review["data_root"]), choices.get("check", False)
    )
    review["grants"] = {**review["grants"], **HOST_STAGE_GRANTS}
    review["resume_command"] = setup_resume_command(root, host)


def _registration_needs_write(review: dict[str, Any]) -> bool:
    reg = review["registration"]
    return not (
        reg.get("blocker")
        or reg.get("method") == "native_plugin"
        or reg.get("unchanged")
    )


def _hooks_stage(
    root: Path, data_root: Path, host: str, requested: bool
) -> dict[str, Any]:
    """T7 (D3): the post-edit hook activation for this host and project,
    written only on explicit --enable-agent-hooks consent. The hook runs
    `rush check` with no grants after each edit, through the Rush plugin."""
    activation = {
        "host": host,
        "canonical_root": str(root.resolve()),
        # The hooks stage is granted cache_write, so the hook may store its
        # full redacted result for recovery (T16), as `agent connect` does.
        "recovery_cache_write": "cache_write" in HOST_STAGE_GRANTS["hooks"],
    }
    stage: dict[str, Any] = {
        "requested": requested,
        "path": str(activation_record_path(data_root)),
        "activation": activation,
    }
    return {**stage, "state": "unchanged" if _hook_active(stage) else "pending"}


def _hook_active(stage: dict[str, Any]) -> bool:
    """Read-only: the activation file already holds this host's record for
    this root (no directory or file is created)."""
    wanted = stage["activation"]
    document = read_activation_record(Path(stage["path"]).parent.parent)
    records = document.get("activations") if isinstance(document, dict) else None
    return any(
        isinstance(record, dict)
        and record.get("host") == wanted["host"]
        and record.get("canonical_root") == wanted["canonical_root"]
        for record in records or []
    )


def _host_needed_grants(
    review: dict[str, Any], choices: dict[str, bool] | None
) -> dict[str, tuple[str, ...]]:
    """Without ``choices`` (preview, saved plan) guidance and the probe count
    when the review requested them; with ``choices`` (answers given, or
    flags already checked against the review) exactly when chosen."""

    def wanted(key: str) -> bool:
        if choices is None:
            return bool(review[key].get("requested"))
        return bool(choices.get(key))

    needed: dict[str, tuple[str, ...]] = {"select": HOST_STAGE_GRANTS["select"]}
    registration_chosen = choices is None or choices.get("registration", True)
    if _registration_needs_write(review) and registration_chosen:
        needed["host_registration"] = HOST_STAGE_GRANTS["host_registration"]
    if review["guidance"].get("state") == "pending" and wanted("guidance"):
        needed["guidance"] = HOST_STAGE_GRANTS["guidance"]
    if review["hooks"].get("state") == "pending" and wanted("hooks"):
        needed["hooks"] = HOST_STAGE_GRANTS["hooks"]
    if not review["registration"].get("blocker") and wanted("probe"):
        needed["probe"] = HOST_STAGE_GRANTS["probe"]
    if wanted("check"):
        needed["check"] = HOST_STAGE_GRANTS["check"]
    return needed


def _render_host_stages(review: dict[str, Any]) -> list[str]:
    reg = review["registration"]
    lines = [f"  5. Host: {reg['display_name']} (session {reg['session']})"]
    if reg.get("blocker"):
        lines.append(f"     BLOCKED ({reg['blocker']}): {reg['recovery_actions'][0]}")
    elif reg["method"] == "native_plugin":
        lines.append("     Rush plugin already installed; no manual MCP entry is added")
        if reg.get("conversion"):
            lines.append(
                "     a manual rush entry also exists; convert it with "
                f"`rush install --agent-plugin {reg['host']} --convert-manual-entry`"
            )
    elif reg["unchanged"]:
        lines.append(f"     already registered in {reg['config_path']}")
    else:
        verb = (
            "REPLACE the existing rush entry"
            if reg["host_change"]
            else "add a rush entry"
        )
        lines.append(f"     {verb} in {reg['config_path']} ({reg['scope']} scope):")
        lines.extend(f"       {line}" for line in reg["diff"].splitlines())
    guidance = review["guidance"]
    if not guidance.get("requested"):
        lines.append("  6. Guidance: not requested (--install-guidance)")
    else:
        lines.append(
            f"  6. Guidance: {guidance['state']} {guidance.get('target_path') or ''}"
        )
        lines.extend(f"       {line}" for line in guidance.get("diff", "").splitlines())
    hooks = review["hooks"]
    if not hooks["requested"]:
        lines.append("  7. Hooks: not requested (--enable-agent-hooks)")
    else:
        lines.append(
            f"  7. Hooks: {hooks['state']} -- after each edit, the Rush plugin's "
            "hook runs `rush check` on the edited file with no grants and shows "
            f"the result to the model (activation in {hooks['path']})"
        )
    lines.append(f"  8. Session: select this project for {reg['session']}")
    probe = review["probe"]
    if probe["requested"] and probe["probe_argv"]:
        lines.append(
            f"  9. Capability probe: `{shlex.join(probe['readback_argv'])}` then "
            f"`{shlex.join(probe['probe_argv'])}` -- {probe['boundary']}"
        )
    else:
        lines.append("  9. Capability probe: not requested (--verify-host)")
    check = review["check"]
    lines.append(
        f"  10. Check: run the representative `{check['command']}` on a "
        "Rush-owned fixture after setup, with the build and cache_write grants"
        if check["requested"]
        else f"  10. Check: not requested (--run-check); run `{check['command']}` yourself"
    )
    lines.append(f"  Resume: {review['resume_command']}")
    return lines


# --- T26: applying an envelope -------------------------------------------------

_HOST_RAW_STAGES = ("registration", "guidance", "hooks", "select", "probe", "check")
_READINESS_ORDER = (
    "blocked",
    "installed",
    "configured",
    "restart_required",
    "authenticated",
    "connected",
    "capability_verified",
)


def _pending_host_stages(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        **{stage: {"state": "pending", "reason": reason} for stage in _HOST_RAW_STAGES},
    }


def _current_project_id(review: dict[str, Any]) -> str | None:
    now = _registration_state(review)[1]
    return now.get("project_id") if now.get("state") == "existing" else None


def _replan_registration(review: dict[str, Any], project_id: str) -> Any:
    reg = review["registration"]
    host_binary = reg["host_binary"]
    return plan_project_registration(
        reg["agent_id"],
        rush_binary=reg["rush_binary"],
        project_root=Path(review["project_root"]),
        project_id=project_id,
        home=Path(review["home"]),
        which=lambda _name: host_binary,
    )


def _host_target_reached(review: dict[str, Any], project_id: str | None) -> bool:
    if project_id is None:
        return False
    try:
        return bool(_replan_registration(review, project_id).unchanged)
    except (AgentConnectionError, OSError, ValueError):
        return False


def _host_current_digest(review: dict[str, Any]) -> str | None:
    """What the review's `expected_sha256` measures, as it is now (Codex: the
    config file's digest; Claude Code: this project's local entry digest)."""
    planned_id = review["registration"].get("project_id") or _PROJECT_ID_PLACEHOLDER
    return _replan_registration(review, planned_id).expected_sha256


def _host_stale(review: dict[str, Any]) -> tuple[str, str] | None:
    """The host config changed since the review and is not already at target."""
    reg = review["registration"]
    if review.get("host") is None or not _registration_needs_write(review):
        return None
    try:
        current = _host_current_digest(review)
    except (AgentConnectionError, OSError, ValueError) as exc:
        return "host_config", f"cannot read {reg['config_path']}: {exc}"
    if current == reg["expected_sha256"]:
        return None
    if _host_target_reached(review, _current_project_id(review)):
        return None
    return "host_config", f"{reg['config_path']} changed after the review"


def _host_problem(review: dict[str, Any]) -> dict[str, Any] | None:
    host = review.get("host")
    if host is None:
        return None
    if host not in SETUP_HOSTS or review["registration"].get("host") != host:
        return {"status": "error", "reason": "unknown_host", "host": host}
    return None


def _selected_project_id(session_id: str, data_root: Path) -> str | None:
    view = registry.get_selected_project(session_id, data_root=data_root)
    return view["project_id"] if view else None


def _pending_work(review: dict[str, Any]) -> bool:
    """Whether any stage of this review still has an effect to perform."""
    if _config_state(review) != "done" or _registration_state(review)[0] != "done":
        return True
    if not plan_is_complete(plan_from_dict(review["provision"])):
        return True
    host = review.get("host")
    if host is None:
        return False
    project_id = _current_project_id(review)
    if _registration_needs_write(review) and not _host_target_reached(
        review, project_id
    ):
        return True
    data_root = Path(review["data_root"])
    if _selected_project_id(f"{host}:{project_id}", data_root) != project_id:
        return True
    if review["hooks"].get("requested") and not _hook_active(review["hooks"]):
        return True
    if (
        review["guidance"].get("requested")
        and review["guidance"]["state"] != "unsupported"
    ):
        agent_id = SETUP_HOSTS[host]
        plan = plan_agent_instructions(
            agent_id, project_root=Path(review["project_root"]), data_root=data_root
        )
        if plan.conflict is None and plan.new_bytes is not None:
            return True
    return bool(review["probe"].get("requested") or review["check"].get("requested"))


def _host_questions(review: dict[str, Any]) -> list[tuple[str, str]]:
    """The separate consent questions for host stages (never merged)."""
    reg = review["registration"]
    questions: list[tuple[str, str]] = []
    if _registration_needs_write(review):
        verb = (
            "Replace the existing rush entry and register"
            if reg["host_change"]
            else "Register"
        )
        questions.append(
            (
                "registration",
                (
                    f"{verb} Rush with {reg['display_name']} for this project "
                    f"({reg['config_path']})? [y/N] "
                ),
            )
        )
    # Interactive setup offers guidance and the probe as their own questions;
    # the --install-guidance/--verify-host flags matter only without a terminal.
    guidance = review["guidance"]
    if guidance.get("state") == "pending":
        questions.append(
            (
                "guidance",
                f"Write the Rush instruction block into {guidance['target_path']}? [y/N] ",
            )
        )
    # D3: hooks are offered only when --enable-agent-hooks bound them.
    hooks = review["hooks"]
    if hooks.get("requested") and hooks.get("state") == "pending":
        questions.append(
            (
                "hooks",
                (
                    "Enable Rush's post-edit check for this host and project (runs "
                    "`rush check` with no grants after each edit)? [y/N] "
                ),
            )
        )
    if not reg.get("blocker"):
        questions.append(
            (
                "probe",
                f"Verify the connection now? This {review['probe']['boundary']}. [y/N] ",
            )
        )
    # The representative check is offered when the review bound it
    # (--run-check, or the guided interactive setup).
    if review["check"].get("requested"):
        questions.append(
            (
                "check",
                (
                    f"Run the representative check `{review['check']['command']}` "
                    "now on a Rush-owned fixture (format, lint, typecheck, dead, "
                    "slop and test, with the build and cache_write grants)? [y/N] "
                ),
            )
        )
    return questions


def _obtain_envelope_consent(
    review: dict[str, Any], consent: ConsentIO, http_get: HttpGet | None
) -> tuple[dict[str, Any], ExecutionPermissions, dict[str, bool]] | dict[str, Any]:
    """T24's resolution and project questions, then one question per host
    stage. Every answer is collected before any effect."""
    decision = _obtain_consent(review, consent, http_get)
    if isinstance(decision, dict):
        return decision
    review, _ = decision
    choices: dict[str, bool] = {"registration": True}
    for key, prompt in _host_questions(review):
        answer = consent.ask(prompt)
        if answer in ("eof", "interrupt"):
            return _skipped(answer, review)
        choices[key] = answer == "y"
    grants = {g for stage in _needed_grants(review, choices).values() for g in stage}
    return review, ExecutionPermissions(**{g: True for g in grants}), choices


def _run_registration_stage(
    review: dict[str, Any],
    project_id: str,
    choices: dict[str, bool],
    host_fakes: dict[str, Any],
) -> dict[str, Any]:
    reg = review["registration"]
    base = {
        "host": reg["host"],
        "method": reg.get("method"),
        "config_path": reg.get("config_path"),
    }
    if reg.get("blocker"):
        return {
            **base,
            "outcome": "blocked",
            "blocker": reg["blocker"],
            "recovery_actions": reg["recovery_actions"],
        }
    if reg["method"] == "native_plugin":
        return {**base, "outcome": "native_plugin", "conversion": reg.get("conversion")}
    if not choices.get("registration", True):
        return {**base, "outcome": "declined"}
    try:
        step = _replan_registration(review, project_id)
    except (AgentConnectionError, OSError, ValueError) as exc:
        return {**base, "outcome": "failed", "detail": str(exc)}
    if step.method != reg["method"] or str(step.config_path) != reg["config_path"]:
        return {
            **base,
            "outcome": "failed",
            "detail": "the host registration target changed after the review",
        }
    if not step.unchanged and step.expected_sha256 != reg["expected_sha256"]:
        return {
            **base,
            "outcome": "failed",
            "conflict": "host_config",
            "detail": f"{reg['config_path']} changed after the review",
        }
    result = apply_project_registration(
        step,
        consent=True,
        data_root=Path(review["data_root"]),
        runner=host_fakes.get("runner"),
        writer=host_fakes.get("writer"),
    )
    if not result.ok:
        return {**base, "outcome": "failed", "detail": result.error}
    return {**base, "outcome": "unchanged" if step.unchanged else "applied"}


def _run_guidance_stage(
    review: dict[str, Any], choices: dict[str, bool]
) -> dict[str, Any]:
    guidance = review["guidance"]
    if guidance["state"] == "unsupported":
        return {"state": "unsupported"}
    if choices.get("guidance") is False:
        return {"state": "declined"}
    if not choices.get("guidance"):
        if not guidance.get("requested"):
            return {"state": "not_requested"}
        return {"state": "pending", "reason": "not authorized: pass --install-guidance"}
    if guidance["state"] != "pending":
        return {"state": guidance["state"], "conflict": guidance.get("conflict")}
    plan = plan_agent_instructions(
        SETUP_HOSTS[review["host"]],
        project_root=Path(review["project_root"]),
        data_root=Path(review["data_root"]),
    )
    if plan.existing_sha256 != guidance.get("existing_sha256"):
        return {"state": "conflict", "conflict": "changed_since_preview"}
    applied = apply_agent_instructions(plan, consent=True)
    return {
        "state": applied.status,
        "conflict": applied.conflict,
        "target_path": str(applied.target_path),
        "recovery": list(applied.recovery),
    }


def _run_hooks_stage(
    review: dict[str, Any],
    choices: dict[str, bool],
    permissions: ExecutionPermissions | None = None,
) -> dict[str, Any]:
    """T7: write the hook activation only on explicit consent (the flag, or a
    "y" to its own question)."""
    hooks = review["hooks"]
    if choices.get("hooks") is False:
        return {"state": "declined"}
    if not choices.get("hooks"):
        if not hooks.get("requested"):
            return {"state": "not_requested"}
        return {
            "state": "pending",
            "reason": "not authorized: pass --enable-agent-hooks",
        }
    try:
        result = set_hook_activation(
            SETUP_HOSTS[review["host"]],
            Path(review["project_root"]),
            enable=True,
            recovery_cache_write=bool(permissions and permissions.cache_write),
            data_root=Path(review["data_root"]),
        )
    except (AgentConnectionError, ValueError, OSError) as exc:
        return {
            "state": "failed",
            "blocker": "hook_activation_failed",
            "detail": str(exc),
            "recovery_actions": [f"{review['resume_command']} --enable-agent-hooks"],
        }
    if result.get("state") == "conflict":
        # not_owned, unreadable, or a CAS conflict on the activation ledger:
        # the hook is not active, so setup is never reported ok.
        return {
            **result,
            "blocker": "hook_activation_conflict",
            "recovery_actions": [f"{review['resume_command']} --enable-agent-hooks"],
        }
    return result


def _run_select_stage(
    session_id: str, project_id: str, data_root: Path
) -> dict[str, Any]:
    if _selected_project_id(session_id, data_root) == project_id:
        return {"state": "unchanged", "session": session_id}
    try:
        registry.select_project(session_id, project_id, data_root=data_root)
    except (registry.ProjectError, OSError) as exc:
        return {"state": "failed", "session": session_id, "detail": str(exc)}
    return {"state": "applied", "session": session_id}


def _host_version(runner: HostRunner, binary: str, cwd: str) -> str:
    try:
        output = runner((binary, "--version"), cwd).strip()
    except HostCommandError:
        return "unknown"
    return output.splitlines()[0] if output else "unknown"


def _run_probe_stage(
    review: dict[str, Any],
    project_id: str,
    choices: dict[str, bool],
    registration: dict[str, Any],
    runner: HostRunner,
) -> dict[str, Any]:
    """Host readback (`connected`), then the model probe: `capability_verified`
    only from an observed `rush_status` call reporting this project."""
    probe = review["probe"]
    if choices.get("probe") is False:
        return {"state": "declined"}
    if not choices.get("probe"):
        if not probe.get("requested"):
            return {"state": "not_requested"}
        return {"state": "pending", "reason": "not authorized: pass --verify-host"}
    if registration["outcome"] in ("blocked", "declined", "failed"):
        return {
            "state": "pending",
            "reason": f"host registration {registration['outcome']}",
        }
    agent_id = SETUP_HOSTS[review["host"]]
    cwd = probe["cwd"]
    readback_argv = tuple(probe["readback_argv"])
    probe_argv = tuple(probe["probe_argv"])
    report: dict[str, Any] = {
        "commands": [
            {"argv": list(readback_argv), "kind": "readback"},
            {"argv": list(probe_argv), "kind": "model_probe"},
        ],
        "connected": False,
    }
    try:
        report["connected"] = host_readback_connected(
            agent_id, runner(readback_argv, cwd)
        )
    except HostCommandError as exc:
        report["readback_error"] = exc.detail
    try:
        output = runner(probe_argv, cwd)
    except HostCommandError as exc:
        return {
            **report,
            "state": "failed",
            "authenticated": "unverified",
            "detail": exc.detail,
        }
    calls = parse_host_tool_calls(output)
    if not calls and output.lstrip()[:1] not in ("{", "["):
        version = _host_version(runner, probe_argv[0], cwd)
        return {
            **report,
            "state": "unsupported",
            "reason": f"host_probe_unsupported:{version}",
            "authenticated": "unverified",
        }
    observed = observed_status_project_ids(calls)
    return {
        **report,
        "state": "observed" if observed else "no_status_call",
        "authenticated": True,
        "tool_calls": [call["name"] for call in calls],
        "observed_project_ids": observed,
        "capability_verified": project_id in observed,
    }


def _readiness(
    review: dict[str, Any],
    project_id: str,
    registration: dict[str, Any],
    probe: dict[str, Any],
) -> dict[str, Any]:
    """The host's readiness state: the highest one actually observed."""
    if registration["outcome"] == "blocked":
        return {"state": "blocked", "ready": False}
    reg = review["registration"]
    agent_id = reg["agent_id"]
    configured = registration["outcome"] == "native_plugin"
    if not configured:
        try:
            _, entry = read_project_registration_entry(
                agent_id,
                project_root=Path(review["project_root"]),
                home=Path(review["home"]),
            )
            target = _replan_registration(review, project_id).entry
        except (AgentConnectionError, OSError, ValueError):
            entry, target = None, None
        configured = target is not None and same_server_entry(entry, target)
    verified = bool(probe.get("capability_verified"))
    connected = bool(probe.get("connected")) or verified
    authenticated = probe.get("authenticated") is True
    state = "installed"
    if configured:
        state = "configured"
        if ADAPTERS[agent_id].restart_required and not connected:
            state = "restart_required"
    if authenticated:
        state = "authenticated"
    if connected:
        state = "connected"
    if verified:
        state = "capability_verified"
    return {
        "state": state,
        "configured": configured,
        "connected": connected,
        "authenticated": True if authenticated else "unverified",
        "capability_verified": verified,
        "ready": verified,
    }


def _evidence_commands(
    review: dict[str, Any], registration: dict[str, Any], probe: dict[str, Any]
) -> list[dict[str, Any]]:
    """Commands the user still has to run, by kind (plan command accounting)."""
    agent_id = SETUP_HOSTS[review["host"]]
    commands = [
        {"argv": action, "kind": "recovery"}
        for action in registration.get("recovery_actions", [])
    ]
    if registration.get("state") == "restart_required":
        commands.append(
            {"argv": f"restart {ADAPTERS[agent_id].display_name}", "kind": "reload"}
        )
    if probe.get("authenticated") == "unverified":
        commands.append({"argv": HOST_LOGIN_ACTIONS[agent_id], "kind": "login"})
    return commands


def _apply_host_stages(
    review: dict[str, Any],
    project_id: str,
    choices: dict[str, bool],
    host_fakes: dict[str, Any],
    permissions: ExecutionPermissions | None = None,
) -> dict[str, Any]:
    host = review.get("host")
    if host is None:
        return {
            "schema_version": 1,
            **{stage: {"state": "not_selected"} for stage in _HOST_RAW_STAGES},
        }
    data_root = Path(review["data_root"])
    session_id = f"{host}:{project_id}"
    runner: HostRunner = host_fakes.get("runner") or run_host_command
    registration = _run_registration_stage(review, project_id, choices, host_fakes)
    guidance = _run_guidance_stage(review, choices)
    hooks = _run_hooks_stage(review, choices, permissions)
    select = _run_select_stage(session_id, project_id, data_root)
    probe = _run_probe_stage(review, project_id, choices, registration, runner)
    registration = {
        **registration,
        **_readiness(review, project_id, registration, probe),
    }
    return {
        "schema_version": 1,
        "session": session_id,
        "registration": registration,
        "guidance": guidance,
        "hooks": hooks,
        "select": select,
        "probe": probe,
        # Filled by the caller after `_setup_lock` is released (the check
        # runs for minutes and never needs the lock).
        "check": {"state": "pending", "command": review["check"]["command"]},
        "evidence": {"commands": _evidence_commands(review, registration, probe)},
    }


def _host_outcome_status(status: str, raw: dict[str, Any]) -> tuple[str, str | None]:
    outcome = raw["registration"].get("outcome")
    if outcome == "failed":
        return "error", "host_registration_failed"
    if raw["select"].get("state") == "failed":
        return "error", "session_select_failed"
    if outcome in ("blocked", "declined") and status == "ok":
        return "partial", f"host_{outcome}"
    if status == "ok":
        # A stage that failed is never an ok setup: its stage result names
        # the blocker and the one recovery command.
        for stage in ("hooks", "check"):
            state = (raw.get(stage) or {}).get("state")
            if state in ("failed", "conflict"):
                return "partial", f"{stage}_{state}"
    return status, None


def _already_complete(
    review: dict[str, Any], host_fakes: dict[str, Any]
) -> dict[str, Any]:
    """A rerun of a fully applied review: report it, ask and write nothing."""
    project_id = _current_project_id(review) or ""
    result: dict[str, Any] = {
        "status": "ok",
        "reason": "already_complete",
        "review_id": review["review_id"],
        "setup_plan_id": setup_plan_id(review),
        "project_id": project_id,
    }
    if review.get("host") is None:
        return {**result, "raw": _apply_host_stages(review, project_id, {}, host_fakes)}
    reg = review["registration"]
    registration: dict[str, Any] = {"host": reg["host"], "method": reg.get("method")}
    if reg.get("blocker"):
        registration.update(
            outcome="blocked",
            blocker=reg["blocker"],
            recovery_actions=reg["recovery_actions"],
        )
    else:
        registration["outcome"] = (
            "native_plugin" if reg["method"] == "native_plugin" else "unchanged"
        )
    probe = {"state": "not_requested"}
    registration = {
        **registration,
        **_readiness(review, project_id, registration, probe),
    }
    raw = {
        "schema_version": 1,
        "session": f"{review['host']}:{project_id}",
        "registration": registration,
        "guidance": {
            "state": "unchanged"
            if review["guidance"].get("requested")
            else "not_requested"
        },
        "hooks": {
            "state": "unchanged" if review["hooks"]["requested"] else "not_requested"
        },
        "select": {"state": "unchanged", "session": f"{review['host']}:{project_id}"},
        "probe": probe,
        "check": {"state": "not_requested", "command": review["check"]["command"]},
        "evidence": {"commands": _evidence_commands(review, registration, probe)},
    }
    status, reason = _host_outcome_status("ok", raw)
    return {
        **result,
        "status": status,
        "reason": reason or "already_complete",
        "raw": raw,
    }


def _envelope_preflight(
    envelope: dict[str, Any],
) -> tuple[dict[str, Any], None] | tuple[None, dict[str, Any]]:
    """Every rejection that needs no consent and has no effect: the review,
    or the rejection result."""
    review = envelope.get("review")
    if envelope.get("schema_version") != 1 or not isinstance(review, dict):
        return None, {"status": "error", "reason": "invalid_setup_envelope"}
    if "setup_plan_id" in envelope and envelope["setup_plan_id"] != setup_plan_id(
        review
    ):
        return None, {"status": "error", "reason": "setup_plan_tampered"}
    try:
        problem = _review_problem(review) or _host_problem(review)
        if problem is not None:
            return None, problem
        stale = _stale_precondition(review, resume=True) or _host_stale(review)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        return None, {
            "status": "error",
            "reason": "invalid_setup_envelope",
            "detail": str(exc),
        }
    if stale is not None:
        return None, {
            "status": "error",
            "reason": "recovery_required",
            "conflict": stale[0],
            "detail": stale[1],
            "review_id": review["review_id"],
            "setup_plan_id": setup_plan_id(review),
        }
    return review, None


def _apply_setup_envelope(
    envelope: dict[str, Any],
    permissions: ExecutionPermissions | None,
    consent: ConsentIO | None,
    fakes: dict[str, Any],
    *,
    host_fakes: dict[str, Any],
    choices: dict[str, bool] | None,
) -> dict[str, Any]:
    """Apply a `{kind:"setup"}` envelope: T24's project stages, then host
    registration -> guidance -> hooks -> session selection -> probe.

    Tampering, a wrong platform, an unknown host or a stale precondition is
    rejected before consent and before any effect. A completed rerun asks
    nothing and writes nothing. Non-interactive ``choices`` may only enable
    what the review bound (`unbound_choice` otherwise).
    """
    review, rejection = _envelope_preflight(envelope)
    if rejection is not None:
        return rejection
    assert review is not None
    if not _pending_work(review):
        return _already_complete(review, host_fakes)
    if consent is not None:
        decision = _obtain_envelope_consent(review, consent, fakes["http_get"])
        if isinstance(decision, dict):
            return decision
        review, permissions, chosen = decision
    else:
        # A flag not passed is "not authorized", never an answer of "no".
        chosen = {
            "registration": True,
            **{key: True for key, value in (choices or {}).items() if value},
        }
        unbound = sorted(
            key
            for key in ("guidance", "hooks", "probe", "check")
            if chosen.get(key) and not review.get(key, {}).get("requested")
        )
        if unbound:
            return {
                "status": "error",
                "reason": "unbound_choice",
                "choices": unbound,
                "review_id": review["review_id"],
            }
    missing = _missing_grants(review, permissions, chosen)
    if missing:
        return {
            "status": "permission_denied",
            "missing": missing,
            "review_id": review["review_id"],
        }
    try:
        with _setup_lock(Path(review["project_root"])):
            result = _apply_locked(review, permissions, fakes, resume=True)
            if "project_id" not in result:
                return {
                    **result,
                    "raw": _pending_host_stages("project setup did not complete"),
                }
            raw = _apply_host_stages(
                review, result["project_id"], chosen, host_fakes, permissions
            )
        if review.get("host") is not None:
            raw["check"] = _run_check_stage(review, chosen, permissions)
    except _StageConflict as exc:
        return {
            "status": "recovery_required",
            "conflict": exc.component,
            "detail": exc.detail,
            "review_id": review["review_id"],
            "compensation_conflicts": [],
            "raw": _pending_host_stages("project setup did not complete"),
        }
    status, reason = _host_outcome_status(result["status"], raw)
    outcome = {
        **result,
        "status": status,
        "setup_plan_id": setup_plan_id(review),
        "ready": bool(raw.get("registration", {}).get("ready")),
        "raw": raw,
    }
    if reason is not None:
        outcome["reason"] = reason
    if review.get("resume_command"):
        outcome["resume_command"] = review["resume_command"]
    return outcome


def _registered_project_id(root: str, data_root: str) -> str | None:
    state = registry.read_registry_strict(Path(data_root))
    for project_id, entry in ((state["registry"] or {}).get("projects") or {}).items():
        if entry.get("root") == root:
            return str(project_id)
    return None


def _apply_legacy_provision(
    payload: dict[str, Any],
    permissions: ExecutionPermissions | None,
    consent: ConsentIO | None,
    fakes: dict[str, Any],
) -> dict[str, Any]:
    """A provision-only payload: its engine plan for an already-registered
    project, nothing else. Host, guidance, hooks and probe stay pending."""
    raw = _pending_host_stages(
        "a provision-only payload authorizes only its engine plan; run "
        "`rush setup PATH --agent HOST` for the host stages"
    )
    review = payload.get("review")
    provision = review.get("provision") if isinstance(review, dict) else None
    if not isinstance(provision, dict):
        return {"status": "error", "reason": "invalid_provision_plan", "raw": raw}
    try:
        plan = plan_from_dict(provision)
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "status": "error",
            "reason": "invalid_provision_plan",
            "detail": str(exc),
            "raw": raw,
        }
    project_id = _registered_project_id(plan.project_root, plan.data_root)
    if project_id is None:
        return {"status": "error", "reason": "project_not_registered", "raw": raw}
    if consent is not None:
        consent.write("\n".join(_render_entry(e) for e in provision["entries"]))
        answer = consent.ask("Apply this engine plan? [y/N] ")
        if answer != "y":
            return {
                "status": "skipped",
                "reason": _SKIP_REASONS.get(answer, "declined"),
                "raw": raw,
            }
        grants = {g for e in plan.entries for g in e.required_grants}
        permissions = ExecutionPermissions(**{g: True for g in grants})
    outcome = apply_provision_plan(
        plan,
        permissions,
        project_id=project_id,
        data_root=Path(plan.data_root),
        reviewed_plan_id=str(provision.get("plan_id")),
        **{k: v for k, v in fakes.items() if v is not None},
    )
    complete = not (outcome.failed or outcome.permission_blocked)
    return {
        "status": "ok" if complete else "partial",
        "project_id": project_id,
        "provision": _provision_summary(outcome),
        "raw": raw,
    }


# --- T26: consent from the controlling terminal ---------------------------------


class DeviceConsentIO:
    """ConsentIO over the controlling terminal -- POSIX `/dev/tty`, Windows
    `CONIN$`/`CONOUT$` -- never the process's stdin, which on the guided
    bootstrap route is the downloaded install script. Each call opens the
    device afresh, so nothing stays open between questions."""

    def __init__(self, input_name: str, output_name: str) -> None:
        self._input = input_name
        self._output = output_name

    @classmethod
    def open(cls) -> DeviceConsentIO | None:
        """The terminal channel, or None without a controlling terminal."""
        names = ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
        try:
            with (
                open(names[0], encoding="utf-8"),
                open(names[1], "w", encoding="utf-8"),
            ):
                pass
        except OSError:
            return None
        return cls(*names)

    def _emit(self, text: str) -> None:
        with open(self._output, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()

    def ask(self, prompt: str) -> str:
        self._emit(prompt)
        try:
            with open(self._input, encoding="utf-8") as terminal:
                line = terminal.readline()
        except KeyboardInterrupt:
            return "interrupt"
        except OSError:
            return "eof"
        if not line:
            return "eof"
        return "y" if line.strip().lower() in ("y", "yes") else "n"

    def write(self, text: str) -> None:
        self._emit(text + "\n")


# --- CLI orchestration (kept here so `setup_cmd` stays a thin handler) -------

_EXIT_CODES = {
    "ok": 0,
    "skipped": 0,
    "partial": 1,
    "recovery_required": 1,
    "permission_denied": 1,
    "error": 2,
}


# T26 failures of a valid request (not usage errors): exit 1.
_RUNTIME_ERROR_REASONS = frozenset(
    {"host_registration_failed", "session_select_failed", "recovery_required"}
)


def _exit_code(result: dict[str, Any]) -> int:
    if result.get("reason") == "interrupt":
        return 130
    if result.get("reason") in _RUNTIME_ERROR_REASONS:
        return 1
    return _EXIT_CODES.get(str(result.get("status")), 2)


def _usage(reason: str, message: str) -> tuple[dict[str, Any], int]:
    return {"status": "error", "reason": reason, "message": message}, 2


def _apply_saved_envelope(
    root: Path,
    payload: dict[str, Any],
    plan_id: str,
    host: str | None,
    permissions: ExecutionPermissions,
    choices: dict[str, bool],
) -> tuple[dict[str, Any], int]:
    """A saved T26 envelope: --plan-id, PATH and --agent must equal what it binds."""
    review = payload.get("review")
    if not isinstance(review, dict):
        return _usage("invalid_plan_file", "the saved setup plan has no review")
    if plan_id != payload.get("setup_plan_id"):
        return _usage(
            "plan_id_mismatch", "--plan-id does not match the saved setup_plan_id"
        )
    if review.get("project_root") != str(root):
        return _usage(
            "project_mismatch",
            f"the saved setup plan is for {review.get('project_root')}",
        )
    if review.get("host") != host:
        return _usage(
            "host_mismatch",
            f"the saved setup plan is for --agent {review.get('host')}; pass exactly "
            "that host",
        )
    result = apply_setup_review(payload, permissions, None, choices=choices)
    return result, _exit_code(result)


def _apply_saved_review(
    root: Path,
    plan_file: Path | None,
    plan_id: str | None,
    yes: bool,
    permissions: ExecutionPermissions,
    *,
    host: str | None = None,
    choices: dict[str, bool] | None = None,
) -> tuple[dict[str, Any], int]:
    if not (yes and plan_file is not None and plan_id):
        return _usage(
            "usage",
            "non-interactive apply needs --apply --yes --plan-file PATH --plan-id ID "
            "plus the --allow-* grants the saved review lists",
        )
    try:
        payload = json.loads(plan_file.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("kind") == "setup":
            return _apply_saved_envelope(
                root, payload, plan_id, host, permissions, choices or {}
            )
        if isinstance(payload, dict) and payload.get("kind") == "provision":
            legacy = apply_setup_review(payload, permissions, None)
            return legacy, _exit_code(legacy)
        review = payload.get("review", payload)
        if review.get("review_id") != plan_id:
            return _usage(
                "plan_id_mismatch", "--plan-id does not match the saved review"
            )
        if review.get("project_root") != str(root):
            return _usage(
                "project_mismatch",
                f"the saved review is for {review.get('project_root')}",
            )
        result = apply_setup_review(review, permissions, None)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return _usage("invalid_plan_file", f"cannot use {plan_file}: {exc}")
    # A T24 review binds only project and engine stages (T26 legacy scope).
    result.setdefault(
        "raw",
        _pending_host_stages(
            "a T24 setup review authorizes only project and engine stages; run "
            "`rush setup PATH --agent HOST` for the host stages"
        ),
    )
    return result, _exit_code(result)


def _preview_readiness(review: dict[str, Any]) -> str:
    reg = review["registration"]
    if reg.get("blocker"):
        return "blocked"
    if reg.get("method") == "native_plugin" or reg.get("unchanged"):
        return "configured"
    return "installed"


def preview_setup(
    root: Path,
    *,
    host: str | None,
    permissions: ExecutionPermissions,
    choices: dict[str, bool],
    reason: str = "preview_only",
) -> dict[str, Any]:
    """The full read-only preview: every stage, incomplete readiness, and the
    exact command that resumes setup interactively."""
    review = build_setup_review(
        root,
        resolve=permissions.network,
        permissions=permissions,
        host=host,
        install_guidance=choices.get("guidance", False),
        enable_hooks=choices.get("hooks", False),
        verify_host=choices.get("probe", False),
        run_check=choices.get("check", False),
    )
    needed = {g for stage in _needed_grants(review).values() for g in stage}
    if review["resolution"]["required"]:
        needed.add("network")
    payload: dict[str, Any] = {
        "status": "skipped",
        "reason": reason,
        "review": review,
        "apply_flags": _flags(needed),
    }
    if host is None:
        payload["host_selection"] = {
            "state": "selection_required",
            "detected": detected_setup_hosts(),
            "choices": sorted(SETUP_HOSTS),
        }
        payload["resume_command"] = setup_resume_command(Path(review["project_root"]))
        return payload
    payload["setup_plan_id"] = setup_plan_id(review)
    payload["readiness"] = {"state": _preview_readiness(review), "complete": False}
    payload["resume_command"] = review["resume_command"]
    return payload


def _write_plan_file(path: Path, data: bytes) -> str:
    """Atomically create `path` with `data`: `created`, or `unchanged` when it
    already holds exactly `data`. Different existing bytes raise FileExistsError."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.read_bytes() == data:
            return "unchanged"
        raise FileExistsError(str(path))
    except FileNotFoundError:
        pass
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_name, path)  # never replaces a file created meanwhile
        except FileExistsError:
            if path.read_bytes() == data:
                return "unchanged"
            raise
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    return "created"


def setup_apply_command(
    root: Path,
    host: str | None,
    plan_file: Path,
    plan_id: str,
    grants: set[str],
    choices: dict[str, bool],
) -> str:
    """The exact non-interactive apply line for a saved setup plan."""
    parts = [f"rush setup {_quote(str(root))}"]
    if host:
        parts.append(f"--agent {host}")
    parts += [
        "--apply --yes",
        f"--plan-file {_quote(str(plan_file))}",
        f"--plan-id {plan_id}",
        *_flags(grants),
    ]
    for key, flag in (
        ("guidance", "--install-guidance"),
        ("hooks", "--enable-agent-hooks"),
        ("probe", "--verify-host"),
        ("check", "--run-check"),
    ):
        if choices.get(key):
            parts.append(flag)
    return " ".join(parts)


def save_setup_plan(
    root: Path,
    plan_file: Path,
    *,
    host: str | None,
    permissions: ExecutionPermissions,
    choices: dict[str, bool],
) -> tuple[dict[str, Any], int]:
    """`--save-plan`: write the complete reviewed envelope and print its exact
    apply command. Saving is artifact-write consent only, never apply consent;
    a review that still needs identity resolution is not saved as executable."""
    plan_file = Path(plan_file).resolve()
    if not permissions.artifact_write:
        return {
            "status": "permission_denied",
            "missing": {"save_plan": ["--allow-artifact-write"]},
        }, 1
    review = build_setup_review(
        root,
        resolve=permissions.network,
        permissions=permissions,
        host=host,
        install_guidance=choices.get("guidance", False),
        enable_hooks=choices.get("hooks", False),
        verify_host=choices.get("probe", False),
        run_check=choices.get("check", False),
    )
    if review["resolution"]["required"]:
        agent = f" --agent {host}" if host else ""
        return {
            "status": "error",
            "reason": "resolution_required",
            "message": "engine identities must be resolved before a plan can be applied",
            "resume_command": (
                f"rush setup {_quote(str(root))}{agent} --save-plan "
                f"{_quote(str(plan_file))} --allow-artifact-write --allow-network"
            ),
            "review": review,
        }, 1
    envelope = setup_envelope(review)
    data = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        state = _write_plan_file(plan_file, data)
    except FileExistsError:
        return {
            "status": "error",
            "reason": "plan_file_exists",
            "message": f"{plan_file} already holds a different plan; remove it or "
            "choose another --save-plan path",
        }, 1
    except OSError as exc:
        return {
            "status": "error",
            "reason": "plan_write_failed",
            "message": str(exc),
        }, 1
    grants = {g for stage in _needed_grants(review).values() for g in stage}
    return {
        "status": "ok",
        "reason": "plan_saved",
        "state": state,
        "plan_file": str(plan_file),
        "setup_plan_id": envelope["setup_plan_id"],
        "apply_command": setup_apply_command(
            root, host, plan_file, envelope["setup_plan_id"], grants, choices
        ),
        "review": review,
    }, 0


def run_interactive_setup(
    root: Path,
    host: str | None,
    consent: ConsentIO,
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[dict[str, Any], int]:
    """Interactive setup. Without ``host`` each detected host is offered in
    turn; the review (identities regenerated) is then shown and every stage
    asked separately."""
    if host is None:
        for candidate in detected_setup_hosts(which):
            name = ADAPTERS[SETUP_HOSTS[candidate]].display_name
            answer = consent.ask(f"Connect Rush to {name} for this project? [y/N] ")
            if answer in ("eof", "interrupt"):
                skipped = {"status": "skipped", "reason": _SKIP_REASONS[answer]}
                return skipped, _exit_code(skipped)
            if answer == "y":
                host = candidate
                break
    if host is None:
        result = apply_setup_review(build_setup_review(root), None, consent)
        return result, _exit_code(result)
    review = build_setup_review(
        root, host=host, install_guidance=True, verify_host=True, run_check=True
    )
    result = apply_setup_review(setup_envelope(review), None, consent)
    return result, _exit_code(result)


def run_guided_setup(
    root: Path,
    host: str | None,
    *,
    interactive: bool = True,
    open_terminal: Callable[[], DeviceConsentIO | None] = DeviceConsentIO.open,
) -> tuple[dict[str, Any], int]:
    """The guided bootstrap's setup (`rush install --setup`). Consent comes
    only from the controlling terminal; without one (or when not
    ``interactive``) the result is the full preview and the resume command."""
    no_choices = {"guidance": False, "hooks": False, "probe": False, "check": False}
    terminal = open_terminal() if interactive else None
    if terminal is None:
        reason = "no_terminal" if interactive else "preview_only"
        return preview_setup(
            root,
            host=host,
            permissions=ExecutionPermissions(),
            choices=no_choices,
            reason=reason,
        ), 0
    return run_interactive_setup(root, host, terminal)


def run_setup_command(
    root: Path,
    *,
    non_interactive: bool | None,
    apply: bool,
    yes: bool,
    plan_file: Path | None,
    plan_id: str | None,
    permissions: ExecutionPermissions,
    as_json: bool,
    stdin_tty: bool,
    stdout_tty: bool,
    host: str | None = None,
    save_plan: Path | None = None,
    install_guidance: bool = False,
    enable_hooks: bool = False,
    verify_host: bool = False,
    run_check: bool = False,
) -> tuple[dict[str, Any], int]:
    """Mode selection for `rush setup`. Returns (payload, exit code).

    --apply consumes a saved reviewed payload with explicit grants;
    --save-plan writes one. Otherwise an interactive terminal (stdin and
    stdout TTYs, no --json, no --non-interactive) previews then asks;
    everything else previews only. --interactive forces the interactive
    review and needs a stdin TTY. --agent selects the LLM CLI host (T26).
    """
    choices = {
        "guidance": install_guidance,
        "hooks": enable_hooks,
        "probe": verify_host,
        "check": run_check,
    }
    if apply:
        return _apply_saved_review(
            root, plan_file, plan_id, yes, permissions, host=host, choices=choices
        )
    if save_plan is not None:
        return save_setup_plan(
            root, save_plan, host=host, permissions=permissions, choices=choices
        )
    if non_interactive is False and (as_json or not stdin_tty):
        return _usage(
            "tty_required",
            "--interactive needs an interactive terminal (TTY) on stdin and cannot "
            "be combined with --json",
        )
    if non_interactive is None and not (stdin_tty and stdout_tty):
        non_interactive = True
    if non_interactive or as_json:
        return preview_setup(
            root, host=host, permissions=permissions, choices=choices
        ), 0
    return run_interactive_setup(root, host, TerminalConsentIO())


def render_setup_result(payload: dict[str, Any]) -> str:
    """Plain-text rendering of a `run_setup_command` payload."""
    if payload.get("reason") in ("preview_only", "no_terminal") and payload[
        "review"
    ].get("host"):
        return _render_host_preview(payload)
    if payload.get("reason") in ("plan_saved", "resolution_required"):
        return _render_saved_plan(payload)
    if payload.get("reason") == "preview_only":
        review = payload["review"]
        return (
            render_setup_review(review)
            + "\nPreview only: nothing was changed. Run `rush setup` in a terminal to "
            "review and confirm, or save `rush setup --json` output and pass it with "
            f"--apply --yes --plan-file FILE --plan-id {review['review_id']} "
            + " ".join(payload["apply_flags"])
        )
    status = payload.get("status")
    lines = [
        f"Setup {status}" + (f" ({payload['reason']})" if payload.get("reason") else "")
    ]
    for key in ("message", "conflict", "detail", "diagnostic"):
        if payload.get(key):
            lines.append(f"  {key}: {payload[key]}")
    if payload.get("missing"):
        for stage, flags in payload["missing"].items():
            lines.append(f"  {stage} needs {' '.join(flags)}")
    provision = payload.get("provision") or {}
    for label in ("applied", "reused"):
        if provision.get(label):
            lines.append(f"  engines {label}: {', '.join(sorted(provision[label]))}")
    for engine, failure in sorted((provision.get("failed") or {}).items()):
        lines.append(f"  engine {engine} failed: {failure['message']}")
    for engine, path in sorted((provision.get("recovery_required") or {}).items()):
        lines.append(f"  engine {engine}: recover {path} manually, then rerun setup")
    for engine, flags in sorted((provision.get("permission_blocked") or {}).items()):
        # Round-2 M1: a reused engine whose npm runtime must be fetched
        # needs the fetch grants; one exact recovery command names them.
        grant_flags = " ".join(f"--allow-{flag.replace('_', '-')}" for flag in flags)
        lines.append(f"  engine {engine} needs {' '.join(flags)}")
        if payload.get("resume_command"):
            lines.append(f"  recover: {payload['resume_command']} {grant_flags}")
    lines.extend(_render_host_outcome(payload.get("raw") or {}))
    if payload.get("resume_command") and not payload.get("ready"):
        lines.append(f"  resume: {payload['resume_command']}")
    return "\n".join(lines)


def _render_host_preview(payload: dict[str, Any]) -> str:
    review = payload["review"]
    lead = (
        "No terminal is available to ask for consent, so nothing was changed."
        if payload["reason"] == "no_terminal"
        else "Preview only: nothing was changed."
    )
    save = (
        f"rush setup {_quote(review['project_root'])} --agent {review['host']} "
        "--save-plan FILE --allow-artifact-write"
        + (" --allow-network" if review["resolution"]["required"] else "")
    )
    return "\n".join(
        [
            render_setup_review(review),
            f"Readiness: {payload['readiness']['state']} (incomplete)",
            lead,
            f"Resume setup interactively: {payload['resume_command']}",
            f"Unattended apply: {save}, then run the apply command it prints.",
        ]
    )


def _render_saved_plan(payload: dict[str, Any]) -> str:
    if payload["reason"] == "resolution_required":
        return (
            f"Setup plan not saved: {payload['message']}.\n"
            f"Run: {payload['resume_command']}"
        )
    verb = "Saved" if payload["state"] == "created" else "Already saved"
    return (
        f"{verb} setup plan {payload['setup_plan_id']} to {payload['plan_file']}.\n"
        "Saving applies nothing. To apply it without prompts, run:\n"
        f"  {payload['apply_command']}"
    )


def _render_host_outcome(raw: dict[str, Any]) -> list[str]:
    registration = raw.get("registration")
    if not isinstance(registration, dict) or "host" not in registration:
        return []
    lines = [
        (
            f"  host {registration['host']}: {registration.get('state')} "
            f"(registration {registration.get('outcome')})"
        )
    ]
    if registration.get("detail"):
        lines.append(f"    {registration['detail']}")
    for stage in ("guidance", "hooks", "select", "probe", "check"):
        state = (raw.get(stage) or {}).get("state")
        if state and state not in ("not_requested",):
            lines.append(f"  {stage}: {state}")
    for command in (raw.get("evidence") or {}).get("commands", []):
        lines.append(f"  next ({command['kind']}): {command['argv']}")
    return lines
