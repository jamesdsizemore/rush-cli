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
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

from rush.config import RushConfigError, load_config
from rush.discovery.stack import detect_project_stacks
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
) -> dict[str, Any]:
    """Read-only preview of every setup stage, its exact change and grants.

    Creates nothing and makes no network request unless ``resolve=True``,
    which requires the `network` grant in ``permissions`` and requests only
    the URLs listed under ``resolution.requests``.
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
    review["review_id"] = _review_id(review)
    return review


def _needed_grants(review: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Stage -> grants for the effects this review would actually perform."""
    needed: dict[str, tuple[str, ...]] = {}
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


def _stale_precondition(review: dict[str, Any]) -> tuple[str, str] | None:
    root = Path(review["project_root"])
    config_path = root / "rush.toml"
    try:
        current: str | None = _sha256(config_path.read_bytes())
    except FileNotFoundError:
        current = None
    except OSError as exc:
        return "config", f"cannot read {config_path}: {exc}"
    expected = (
        None if review["config"]["action"] == "create" else review["config"]["sha256"]
    )
    if current != expected:
        return "config", f"{config_path} changed after the review"
    now = _registration_stage(root, Path(review["data_root"]))
    then = review["registration"]
    if (now["state"], now.get("project_id"), now.get("revision")) != (
        then["state"],
        then.get("project_id"),
        then.get("revision"),
    ):
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

    def config(self) -> None:
        stage = self.review["config"]
        path = self.root / "rush.toml"
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
        if stage["already_configured"]:
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
    review: dict[str, Any], permissions: ExecutionPermissions | None
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for stage, grants in _needed_grants(review).items():
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
) -> dict[str, Any]:
    """Apply a setup review: config -> register -> configure -> engines.

    With ``consent`` the review is shown and confirmed first, and only the
    reviewed grants become permissions (``permissions`` is not consulted).
    Without it, ``permissions`` must hold every grant the review needs.
    Decline/EOF/interrupt, a missing grant, or a stale precondition returns
    before any effect. A config/registration failure compensates this
    transaction's own writes; engine failures are reported per engine and
    completed verified engines are kept.
    """
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
    fakes: dict[str, Any] = {
        "http_get": http_get,
        "downloader": downloader,
        "runner": runner,
        "prober": prober,
        "which": which,
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
) -> dict[str, Any]:
    """The ordered stages, run while `.rush/setup.lock` is held: every
    precondition is rechecked under the lock before the first write."""
    stale = _stale_precondition(review)
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


# --- CLI orchestration (kept here so `setup_cmd` stays a thin handler) -------

_EXIT_CODES = {
    "ok": 0,
    "skipped": 0,
    "partial": 1,
    "recovery_required": 1,
    "permission_denied": 1,
    "error": 2,
}


def _exit_code(result: dict[str, Any]) -> int:
    if result.get("reason") == "interrupt":
        return 130
    return _EXIT_CODES.get(str(result.get("status")), 2)


def _usage(reason: str, message: str) -> tuple[dict[str, Any], int]:
    return {"status": "error", "reason": reason, "message": message}, 2


def _apply_saved_review(
    root: Path,
    plan_file: Path | None,
    plan_id: str | None,
    yes: bool,
    permissions: ExecutionPermissions,
) -> tuple[dict[str, Any], int]:
    if not (yes and plan_file is not None and plan_id):
        return _usage(
            "usage",
            "non-interactive apply needs --apply --yes --plan-file PATH --plan-id ID "
            "plus the --allow-* grants the saved review lists",
        )
    try:
        payload = json.loads(plan_file.read_text(encoding="utf-8"))
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
    return result, _exit_code(result)


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
) -> tuple[dict[str, Any], int]:
    """Mode selection for `rush setup`. Returns (payload, exit code).

    --apply consumes a saved reviewed payload with explicit grants. Otherwise
    an interactive terminal (stdin and stdout TTYs, no --json, no
    --non-interactive) previews then asks; everything else previews only.
    --interactive forces the interactive review and needs a stdin TTY.
    """
    if apply:
        return _apply_saved_review(root, plan_file, plan_id, yes, permissions)
    if non_interactive is False and (as_json or not stdin_tty):
        return _usage(
            "tty_required",
            "--interactive needs an interactive terminal (TTY) on stdin and cannot "
            "be combined with --json",
        )
    if non_interactive is None and not (stdin_tty and stdout_tty):
        non_interactive = True
    if non_interactive or as_json:
        review = build_setup_review(
            root, resolve=permissions.network, permissions=permissions
        )
        needed = {g for stage in _needed_grants(review).values() for g in stage}
        if review["resolution"]["required"]:
            needed.add("network")
        return {
            "status": "skipped",
            "reason": "preview_only",
            "review": review,
            "apply_flags": _flags(needed),
        }, 0
    result = apply_setup_review(build_setup_review(root), None, TerminalConsentIO())
    return result, _exit_code(result)


def render_setup_result(payload: dict[str, Any]) -> str:
    """Plain-text rendering of a `run_setup_command` payload."""
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
    return "\n".join(lines)
