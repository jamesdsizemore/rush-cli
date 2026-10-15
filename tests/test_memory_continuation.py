"""Real bootstrap and capsule producers through shared continuation boundary."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_memory_activation_lifecycle import bootstrap, bootstrap_world
from test_memory_capsule import COMMIT, export_file, tree_state

from rush.memory import authorization as auth


def world(tmp_path):
    env, request = bootstrap_world(tmp_path)
    packet = bootstrap(env, request)
    return env, request, packet, packet["raw"]["data"]["scope"]


def project(delivery, scope, **kwargs):
    from rush.tools.agent_connection import project_continuation

    return project_continuation(
        delivery,
        COMMIT,
        scope,
        "a" * 64,
        kwargs.pop("capsule_digest", None),
        kwargs.pop("expected_effects", {"import": None, "bridge": None}),
        **kwargs,
    )


def test_native_bootstrap_real_checkpoint_projection(tmp_path: Path):
    from rush.integrations.agent_hooks import deliver_continuation

    env, request, packet, scope = world(tmp_path)
    before = tree_state(env.root, env.data_root)
    result = deliver_continuation(
        env.root, request, "returned", sys.executable, scope, packet
    )
    assert result["mode"] == "live" and result["channel"] == "managed_live"
    view = project(result, scope)
    assert view["intent"] == packet["raw"]["data"]["intent"]
    assert view["task"]["remaining"] == ["wire the CLI flag"]
    assert view["unresolved"] == ["wire the CLI flag"]
    assert view["next_action"] == {"text": "Wire the CLI flag and rerun the suite"}
    assert view["progress_state"] == "checkpoint_available"
    assert view["locally_verified_progress"] is None
    assert tree_state(env.root, env.data_root) == before


def test_native_first_then_cli_real_shared_packet(tmp_path: Path, monkeypatch):
    from rush.integrations.agent_hooks import deliver_continuation

    env, request, packet, scope = world(tmp_path)
    calls = []

    def child(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, json.dumps(packet), "")

    monkeypatch.setattr(subprocess, "run", child)
    native = deliver_continuation(
        env.root, request, "not_attempted", sys.executable, scope
    )
    assert native["reason"] == "native_bootstrap_required" and calls == []
    assert native["recovery"]["action"] == {
        "tool": "rush_memory",
        "operation": "bootstrap",
        "request": request,
    }
    live = deliver_continuation(env.root, request, "unavailable", sys.executable, scope)
    assert live["mode"] == "live" and live["channel"] == "cli_live"
    argv, options = calls[0]
    assert argv[:5] == [
        str(Path(sys.executable).resolve()),
        "memory",
        "bootstrap",
        "--project",
        str(env.root),
    ]
    assert argv[-2:] == ["--session-binding", request["session_binding"]]
    assert options["shell"] is False and options["check"] is False


def test_cli_unavailable_reads_real_approved_snapshot(tmp_path: Path):
    from rush.integrations.agent_hooks import deliver_continuation

    env, request, _, scope = world(tmp_path)
    capsule = export_file(env)
    document = json.loads(capsule.read_bytes())
    before = tree_state(env.root, env.data_root)
    result = deliver_continuation(
        env.root,
        request,
        "unavailable",
        env.root / "missing-rush",
        scope,
        approved_capsule={
            "path": str(capsule),
            "format": "rush_v1",
            "digest": document["payload_sha256"],
        },
    )
    assert (
        result["mode"] == "offline_snapshot" and result["channel"] == "offline_capsule"
    )
    view = project(result, scope, capsule_digest=document["payload_sha256"], now=0)
    assert view["task"]["constraints"] == document["task"]["constraints"]
    assert view["unresolved"] == ["wire the CLI flag"]
    assert view["claimed_progress"]["authority"] == "imported_unverified"
    assert (
        view["locally_verified_progress"] is None
        and view["stages"]["reread"] == "not_requested"
    )
    assert tree_state(env.root, env.data_root) == before


@pytest.mark.parametrize("channel", ["native", "cli"])
def test_partial_envelope_terminal_without_fallback(
    tmp_path: Path, monkeypatch, channel
):
    from rush.integrations.agent_hooks import deliver_continuation
    from rush.memory import capsule

    env, request, packet, scope = world(tmp_path)
    malformed = [{"raw": packet["raw"]}]
    for key in (
        "tool",
        "engine",
        "engine_version",
        "status",
        "duration_ms",
        "summary",
        "findings",
        "metadata",
        "raw",
    ):
        missing = copy.deepcopy(packet)
        missing.pop(key)
        malformed.append(missing)
    malformed.extend(
        {**packet, k: v}
        for k, v in (
            ("duration_ms", True),
            ("findings", None),
            ("raw", None),
            ("raw", {"code": "OK"}),
        )
    )

    def no_fallback(*args, **kwargs):
        pytest.fail("malformed live packet cannot authorize snapshot")

    monkeypatch.setattr(capsule, "read_snapshot", no_fallback)
    for bad in malformed:
        if channel == "native":
            result = deliver_continuation(
                env.root, request, "returned", sys.executable, scope, bad
            )
        else:
            monkeypatch.setattr(
                subprocess,
                "run",
                lambda argv, bad=bad, **kw: subprocess.CompletedProcess(
                    argv, 0, json.dumps(bad), ""
                ),
            )
            result = deliver_continuation(
                env.root,
                request,
                "unavailable",
                sys.executable,
                scope,
                approved_capsule={
                    "path": "unused",
                    "format": "rush_v1",
                    "digest": "c" * 64,
                },
            )
        assert (
            result["mode"] == "unavailable"
            and result["reason"] == "invalid_result"
            and result["data"] == {}
        )


def test_cli_publication_rechecks_revoked_scope(tmp_path: Path, monkeypatch):
    from rush.integrations.agent_hooks import deliver_continuation

    env, request, packet, scope = world(tmp_path)

    def child(argv, **kwargs):
        auth.revoke_memory_scope(
            grant_id=env.grant["grant_id"],
            expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
            consent=True,
        )
        return subprocess.CompletedProcess(argv, 0, json.dumps(packet), "")

    monkeypatch.setattr(subprocess, "run", child)
    result = deliver_continuation(
        env.root, request, "unavailable", sys.executable, scope
    )
    assert result["mode"] == "unavailable" and result["data"] == {}
    assert result["reason"] == "binding_revoked"


@pytest.mark.parametrize("reason", ["binding_revoked", "scope_required"])
def test_live_denial_never_reads_approved_capsule(tmp_path: Path, monkeypatch, reason):
    from rush.integrations.agent_hooks import deliver_continuation
    from rush.memory import capsule

    env, request, packet, scope = world(tmp_path)
    denied = {
        **packet,
        "status": "fail",
        "raw": {
            "schema_version": 1,
            "operation": "bootstrap",
            "code": "E_PERMISSION",
            "data": {"items": [], "scope": None, "reason": reason},
        },
    }
    monkeypatch.setattr(
        capsule,
        "read_snapshot",
        lambda *a, **k: pytest.fail("live denial cannot fallback"),
    )
    result = deliver_continuation(
        env.root,
        request,
        "returned",
        sys.executable,
        scope,
        denied,
        approved_capsule={"path": "unused", "format": "rush_v1", "digest": "c" * 64},
    )
    assert (
        result["mode"] == "unavailable"
        and result["reason"] == reason
        and result["data"] == {}
    )


def test_reducer_observed_host_matches_committed_effect(tmp_path: Path):
    from rush.integrations.agent_hooks import deliver_continuation

    env, request, packet, scope = world(tmp_path)
    live = deliver_continuation(
        env.root, request, "returned", sys.executable, scope, packet
    )
    effect, digest = "b" * 64, "c" * 64
    base = {
        "receipt_id": "host-r1",
        "source_revision": COMMIT,
        "source_sha256": "a" * 64,
        "scope": scope,
        "capsule_digest": digest,
        "effect_id": effect,
    }
    host = {
        "host_id": "codex",
        "host_version": "observed-1",
        "receipt_id": "host-r1",
        "instructions_sha256": "d" * 64,
        "capsule_digest": digest,
        "effect_id": effect,
    }
    bridge = {
        **base,
        "kind": "capsule_bridge",
        "state": "written",
        "host_id": None,
        "host_version": None,
        "instructions_sha256": None,
    }
    reread = {**base, **host, "kind": "host_reread", "state": "observed"}
    view = project(
        live,
        scope,
        capsule_digest=digest,
        expected_effects={"import": None, "bridge": effect},
        stage_receipts={"bridge": bridge, "reread": reread},
        observed_host=host,
    )
    assert view["stages"] == {
        "import": "not_requested",
        "bridge": "written",
        "reread": "observed",
    }
    for key, value in (
        ("state", "fake"),
        ("source_revision", "other"),
        ("effect_id", "e" * 64),
        ("host_version", "other"),
        ("kind", "capsule_import"),
    ):
        with pytest.raises(ValueError):
            project(
                live,
                scope,
                capsule_digest=digest,
                expected_effects={"import": None, "bridge": effect},
                stage_receipts={"bridge": bridge, "reread": {**reread, key: value}},
                observed_host=host,
            )


def test_offline_changed_digest_exposes_no_content(tmp_path: Path):
    from rush.integrations.agent_hooks import deliver_continuation

    env, request, _, scope = world(tmp_path)
    path = export_file(env)
    before = tree_state(env.root, env.data_root)
    result = deliver_continuation(
        env.root,
        request,
        "unavailable",
        env.root / "missing-rush",
        scope,
        approved_capsule={"path": str(path), "format": "rush_v1", "digest": "f" * 64},
    )
    assert (
        result["mode"] == "unavailable"
        and result["reason"] == "capsule_changed"
        and result["data"] == {}
    )
    assert tree_state(env.root, env.data_root) == before


def test_reducer_rejects_forged_observation(tmp_path: Path):
    from rush.integrations.agent_hooks import deliver_continuation

    env, request, packet, scope = world(tmp_path)
    live = deliver_continuation(
        env.root, request, "returned", sys.executable, scope, packet
    )
    effect, digest = "b" * 64, "c" * 64
    receipt = {
        "kind": "host_reread",
        "state": "observed",
        "receipt_id": "host-r1",
        "source_revision": COMMIT,
        "source_sha256": "a" * 64,
        "scope": scope,
        "capsule_digest": digest,
        "effect_id": effect,
        "host_id": "codex",
        "host_version": "observed-1",
        "instructions_sha256": "d" * 64,
    }
    with pytest.raises(ValueError, match="unobserved continuation reread"):
        project(
            live,
            scope,
            capsule_digest=digest,
            expected_effects={"import": None, "bridge": effect},
            stage_receipts={"reread": receipt},
        )


@pytest.mark.parametrize("host", [None, "claude", "codex"])
def test_native_skill_bootstrap_example_real_request(tmp_path: Path, host):
    import re

    env, request, _, _ = world(tmp_path)
    base = Path(__file__).resolve().parents[1] / "src/rush/integrations/agent_assets"
    asset = (
        base / "skills/rush/SKILL.md"
        if host is None
        else base / host / "skills/rush/SKILL.md"
    )
    example = json.loads(
        re.search(
            r"```json rush-bootstrap-example\n(.*?)\n```", asset.read_text(), re.DOTALL
        ).group(1)
    )
    example["request"]["session_binding"] = request["session_binding"]
    example["request"]["max_tokens"] = 16384
    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, example["request"])
    assert example["operation"] == "bootstrap" and result["raw"]["code"] == "OK"
    assert result["raw"]["data"]["task"]["remaining"] == ["wire the CLI flag"]
    assert result["raw"]["data"]["intent"]["query"] == "current task objective"
    assert tree_state(env.root, env.data_root) == before


def test_unavailable_projection_rejects_held_content(tmp_path: Path):
    _env, _, packet, scope = world(tmp_path)
    held = {
        "mode": "unavailable",
        "channel": None,
        "reason": "binding_revoked",
        "data": packet["raw"]["data"],
        "recovery": {"reason": "binding_revoked", "action": "Reauthorize"},
    }
    with pytest.raises(ValueError, match="unavailable continuation content"):
        project(held, scope)


def test_offline_wrapper_budget_preserves_no_content(tmp_path: Path):
    from rush.delivery.compact import canonical_json
    from rush.integrations.agent_hooks import deliver_continuation
    from rush.memory.capsule import read_snapshot
    from rush.memory.retrieval import DEFAULT_ENCODING, _count_tokens

    env, request, _, scope = world(tmp_path)
    path = export_file(env)
    document = json.loads(path.read_bytes())
    snapshot = read_snapshot(
        env.root, path, "rush_v1", document["payload_sha256"], 16384
    )
    assert snapshot["code"] == "OK"
    budget = _count_tokens(canonical_json(snapshot).decode(), DEFAULT_ENCODING) + 1
    before = tree_state(env.root, env.data_root)
    result = deliver_continuation(
        env.root,
        {**request, "max_tokens": budget},
        "unavailable",
        env.root / "missing-rush",
        scope,
        approved_capsule={
            "path": str(path),
            "format": "rush_v1",
            "digest": document["payload_sha256"],
        },
    )
    assert (
        result["mode"] == "unavailable"
        and result["reason"] == "snapshot_blocked"
        and result["data"] == {}
    )
    assert result["recovery"]["action"]["required"]["tokens"] > budget
    assert tree_state(env.root, env.data_root) == before
