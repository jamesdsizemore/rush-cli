"""73-T09/CODEC: `pas_v1` interoperability (pinned PAS-Agent `0c9515a` schema 1).

Written against owner resolution (c) of the phase-72 gate: field encodings come
from the pinned `session.rs` / `storage.rs` (chrono `write_rfc3339(...,
SecondsFormat::AutoSi, true)` timestamps, lowercase hyphenated UUIDs,
`serde_json::to_string_pretty` bytes). `json.dumps(obj, indent=2,
ensure_ascii=False)` is the independent oracle for those bytes: two-space indent,
`": "`, struct field order as inserted, UTF-8 output, `\\"` `\\\\` `\\b` `\\f` `\\n` `\\r`
`\\t` short escapes and `\\u00xx` lowercase hex for every other control character,
and no trailing newline.

Symbols CODEC adds are imported inside each test, so the module collects at a
HEAD that has none of them.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from test_memory_capsule import CapEnv, R

_cap = importlib.import_module("tests.test_memory_capsule")
HEX64 = _cap.HEX64
UUID_RE = _cap.UUID_RE
approved_mapping = _cap.approved_mapping
assert_denied = _cap.assert_denied
call_inproc = _cap.call_inproc
canon = _cap.canon
expected_records = _cap.expected_records
exported = _cap.exported
fixture_bytes = _cap.fixture_bytes
imported = _cap.imported
imported_rows = _cap.imported_rows
make_env = _cap.make_env
new_uuid = _cap.new_uuid
plant_content = _cap.plant_content
record_view = _cap.record_view
row_of = _cap.row_of
sha = _cap.sha
verify_rush_v1 = _cap.verify_rush_v1

# Drive-relative, drive-qualified and traversing spellings of a portable relative
# path: invalid on whichever host the PAS file is read.
WINDOWS_PATH_SPELLINGS = (
    "C:x.py",
    "C:\\x.py",
    "c:/x.py",
    "..\\x.py",
    "a\\..\\..\\b.py",
    "x/..\\..\\y",
)

PAS_SESSION_KEYS = [
    "schema_version",
    "id",
    "project_name",
    "created_at",
    "updated_at",
    "task",
    "git",
    "checkpoints",
]
PAS_TASK_KEYS = [
    "description",
    "objective",
    "completed",
    "remaining",
    "next_action",
    "blockers",
    "decisions",
    "constraints",
    "discoveries",
]
PAS_GIT_KEYS = ["branch", "commit", "dirty"]
PAS_CHECKPOINT_KEYS = [
    "id",
    "timestamp",
    "message",
    "task_snapshot",
    "git",
    "files_changed",
]
SIDECAR_KEYS = {
    "schema_version",
    "pas_sha256",
    "pas_session_id",
    "capsule_digest",
    "loss",
    "capsule",
    "export_effect",
}
JOURNAL_KEYS = {"schema_version", "export_effect", "receipt", "pas", "sidecar"}
TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{3}|\d{6}|\d{9}))?Z$"
)


def pretty(obj: Any) -> bytes:
    """`serde_json::to_string_pretty` bytes of `obj` (the independent oracle)."""
    # a lone surrogate has no UTF-8 form: it is written as the JSON `\\udXXX` escape
    return json.dumps(obj, indent=2, ensure_ascii=False).encode(
        "utf-8", "backslashreplace"
    )


def assert_pas_timestamp(text: str) -> None:
    """chrono AutoSi: no fraction for zero nanoseconds, else 3, 6 or 9 digits by
    divisibility, then `Z`."""
    match = TIMESTAMP_RE.match(text)
    assert match, text
    fraction = match.group(1)
    if fraction is None:
        return
    nanos = int(fraction.ljust(9, "0"))
    assert nanos != 0, text
    if nanos % 1_000_000 == 0:
        assert len(fraction) == 3, text
    elif nanos % 1_000 == 0:
        assert len(fraction) == 6, text
    else:
        assert len(fraction) == 9, text


def sidecar_path(pas: Path) -> Path:
    return Path(str(pas) + ".rush-manifest.json")


def journal_path(pas: Path) -> Path:
    return Path(str(pas) + ".rush-journal.json")


def write_pair(
    directory: Path, pas: bytes, sidecar: bytes | None, name: str = "x.json"
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(pas)
    if sidecar is not None:
        sidecar_path(target).write_bytes(sidecar)
    return target


def fixture_session() -> dict[str, Any]:
    return json.loads(fixture_bytes("pas_session_schema1.json"))


def fixture_sidecar() -> dict[str, Any]:
    return json.loads(fixture_bytes("pas_session_schema1.json.rush-manifest.json"))


def repackage(
    session_mut: Any = None,
    sidecar_mut: Any = None,
    *,
    capsule_mut: Any = None,
    rebind: bool = True,
) -> tuple[bytes, bytes]:
    """The fixture pair after mutating the session, the sidecar or the embedded
    capsule; the sidecar's `pas_sha256` / `capsule_digest` are recomputed unless
    `rebind` is false (a deliberately stale binding)."""
    session = fixture_session()
    if session_mut is not None:
        session_mut(session)
    sidecar = fixture_sidecar()
    pas = pretty(session)
    if capsule_mut is not None:
        capsule_mut(sidecar["capsule"])
        sidecar["capsule"].pop("payload_sha256", None)
        sidecar["capsule"]["payload_sha256"] = sha(canon(sidecar["capsule"]))
        if rebind:
            sidecar["capsule_digest"] = sidecar["capsule"]["payload_sha256"]
    if rebind:
        sidecar["pas_sha256"] = sha(pas)
        sidecar["pas_session_id"] = session["id"]
    if sidecar_mut is not None:
        sidecar_mut(sidecar)
    return pas, canon(sidecar)


def preview_pas(env: CapEnv, path: Path, **extra: Any) -> R:
    return call_inproc(
        env.root,
        {
            "action": "preview_import",
            "format": "pas_v1",
            "input": str(path),
            "invocation_id": new_uuid(),
            **extra,
        },
    )


def assert_pas_invalid(env: CapEnv, path: Path, label: str, **extra: Any) -> None:
    before = env.effects()
    res = preview_pas(env, path, **extra)
    assert res.code == "E_INPUT" and res.reason == "capsule_invalid", (label, res)
    assert env.effects() == before, label
    assert not imported_rows(env), label


def pas_env(tmp_path: Path, name: str = "project") -> CapEnv:
    return make_env(tmp_path, name)


# --- byte variants (G4 input-bytes rows for PAS and its sidecar) -------------------


def pas_byte_variants() -> dict[str, tuple[bytes, bytes | None]]:
    """Hostile PAS inputs: `name -> (pas bytes, sidecar bytes or None)`. A `None`
    sidecar is a standalone PAS file; every variant must be `capsule_invalid`."""
    variants: dict[str, tuple[bytes, bytes | None]] = {}

    def solo(name: str, mutate: Any) -> None:
        session = fixture_session()
        mutate(session)
        variants[name] = (pretty(session), None)

    def paired(name: str, session_mut: Any = None, **kwargs: Any) -> None:
        variants[name] = repackage(session_mut, **kwargs)

    base = pretty(fixture_session())
    solo("schema_version_2", lambda s: s.__setitem__("schema_version", 2))
    solo("schema_version_true", lambda s: s.__setitem__("schema_version", True))
    solo("unknown_top_key", lambda s: s.__setitem__("extra", 1))
    solo("missing_id", lambda s: s.pop("id"))
    solo("missing_created_at", lambda s: s.pop("created_at"))
    solo("missing_updated_at", lambda s: s.pop("updated_at"))
    solo("missing_task", lambda s: s.pop("task"))
    solo("id_not_a_uuid", lambda s: s.__setitem__("id", "not-a-uuid"))
    solo("id_int", lambda s: s.__setitem__("id", 7))
    solo("created_at_number", lambda s: s.__setitem__("created_at", 1760000000))
    solo("created_at_true", lambda s: s.__setitem__("created_at", True))
    solo("created_at_huge_int", lambda s: s.__setitem__("created_at", 10**400))
    solo("created_at_garbage", lambda s: s.__setitem__("created_at", "yesterday"))
    solo("updated_at_float", lambda s: s.__setitem__("updated_at", 1.5))
    solo(
        "checkpoint_timestamp_number",
        lambda s: s["checkpoints"][0].__setitem__("timestamp", 5),
    )
    solo("unknown_task_key", lambda s: s["task"].__setitem__("zzz", 1))
    solo(
        "task_array_non_string", lambda s: s["task"].__setitem__("completed", [1, "x"])
    )
    solo("task_array_dict", lambda s: s["task"].__setitem__("remaining", [{"a": 1}]))
    solo("task_string_int", lambda s: s["task"].__setitem__("description", 5))
    solo("next_action_int", lambda s: s["task"].__setitem__("next_action", 5))
    solo("git_string", lambda s: s.__setitem__("git", "main"))
    solo("git_dirty_string", lambda s: s["git"].__setitem__("dirty", "no"))
    solo("git_unknown_key", lambda s: s["git"].__setitem__("tag", "v1"))
    solo("checkpoints_not_list", lambda s: s.__setitem__("checkpoints", {}))
    solo("checkpoint_unknown_key", lambda s: s["checkpoints"][0].__setitem__("zzz", 1))
    solo(
        "checkpoint_snapshot_missing",
        lambda s: s["checkpoints"][0].pop("task_snapshot"),
    )
    solo(
        "file_status_unknown",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "status", "Moved"
        ),
    )
    solo(
        "file_status_lowercase",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "status", "added"
        ),
    )
    solo(
        "file_status_object_unknown",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "status", {"Copied": {"from": "a"}}
        ),
    )
    solo(
        "renamed_from_absolute",
        lambda s: s["checkpoints"][0]["files_changed"][2]["status"][
            "Renamed"
        ].__setitem__("from", "/etc/passwd"),
    )
    solo(
        "renamed_from_dotdot",
        lambda s: s["checkpoints"][0]["files_changed"][2]["status"][
            "Renamed"
        ].__setitem__("from", "../outside"),
    )
    solo(
        "renamed_from_drive",
        lambda s: s["checkpoints"][0]["files_changed"][2]["status"][
            "Renamed"
        ].__setitem__("from", "C:\\\\Windows\\\\x"),
    )
    status: Any
    for index, status in enumerate(
        (
            ["Added"],
            {},
            None,
            {"Renamed": []},
            {"Renamed": {"from": ["a"]}},
            {"Renamed": {"from": {"k": "v"}}},
            {"Renamed": {}},
            {"Renamed": {"from": "a"}, "Added": {}},
            {"Added": {}},
        )
    ):
        solo(
            f"file_status_shape_{index}",
            lambda s, status=status: s["checkpoints"][0]["files_changed"][
                0
            ].__setitem__("status", status),
        )
    for index, spelling in enumerate(WINDOWS_PATH_SPELLINGS):
        solo(
            f"path_windows_{index}",
            lambda s, spelling=spelling: s["checkpoints"][0]["files_changed"][
                0
            ].__setitem__("path", spelling),
        )
        solo(
            f"renamed_from_windows_{index}",
            lambda s, spelling=spelling: s["checkpoints"][0]["files_changed"][2][
                "status"
            ]["Renamed"].__setitem__("from", spelling),
        )
    solo(
        "renamed_from_lone_surrogate",
        lambda s: s["checkpoints"][0]["files_changed"][2]["status"][
            "Renamed"
        ].__setitem__("from", "a\ud800b"),
    )
    solo(
        "path_lone_surrogate",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "path", "a\ud800b.py"
        ),
    )
    solo(
        "renamed_from_int",
        lambda s: s["checkpoints"][0]["files_changed"][2]["status"][
            "Renamed"
        ].__setitem__("from", 4),
    )
    solo(
        "path_absolute",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "path", "/abs/path.py"
        ),
    )
    solo(
        "path_dotdot",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "path", "a/../../b.py"
        ),
    )
    solo(
        "path_nul",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__("path", "a\x00b"),
    )
    solo(
        "path_control_char",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "path", "a\u202eb"
        ),
    )
    solo(
        "over_10_checkpoints",
        lambda s: s.__setitem__(
            "checkpoints", [dict(s["checkpoints"][0], id=new_uuid()) for _ in range(11)]
        ),
    )
    solo(
        "over_50_files",
        lambda s: s["checkpoints"][0].__setitem__(
            "files_changed",
            [{"path": f"f{i}.py", "status": "Added"} for i in range(51)],
        ),
    )
    solo(
        "lone_surrogate_text", lambda s: s["task"].__setitem__("description", "\ud800")
    )
    solo("nul_in_text", lambda s: s["task"].__setitem__("objective", "a\x00b"))
    solo("checkpoint_id_bad", lambda s: s["checkpoints"][0].__setitem__("id", "zzz"))
    variants["duplicate_key"] = (
        base[:-1] + b',\n  "id": "0b9a3c5e-1d2f-4a6b-8c7d-9e0f1a2b3c4d"\n}',
        None,
    )
    variants["bom"] = (b"\xef\xbb\xbf" + base, None)
    variants["non_utf8"] = (base[:30] + b"\xff\xfe" + base[30:], None)
    variants["nan_token"] = (base.replace(b'"dirty": false', b'"dirty": NaN', 1), None)
    variants["top_level_array"] = (b"[]", None)
    variants["empty_file"] = (b"", None)
    variants["trailing_garbage"] = (base + b"x", None)
    variants["array_bomb_100000"] = (
        b'{"schema_version":1,"x":' + b"[" * 100000 + b"]" * 100000 + b"}",
        None,
    )
    variants["object_bomb_100000"] = (
        b'{"schema_version":1,"x":' + b'{"a":' * 100000 + b"1" + b"}" * 100000 + b"}",
        None,
    )
    variants["leading_array_bomb"] = (b"[" * 100000 + b"]" * 100000, None)
    variants["depth_over_16"] = (
        pretty({**fixture_session(), "extra_nested": json.loads("[" * 20 + "]" * 20)}),
        None,
    )

    # --- sidecar faults: a present but invalid sidecar is never a standalone import ---
    side = fixture_bytes("pas_session_schema1.json.rush-manifest.json")
    pas_ok = fixture_bytes("pas_session_schema1.json")
    variants["sidecar_array_bomb"] = (pas_ok, b"[" * 100000 + b"]" * 100000)
    variants["sidecar_object_bomb"] = (
        pas_ok,
        b'{"a":' * 100000 + b"1" + b"}" * 100000,
    )
    variants["sidecar_not_json"] = (pas_ok, b"{")
    variants["sidecar_empty"] = (pas_ok, b"")
    variants["sidecar_bom"] = (pas_ok, b"\xef\xbb\xbf" + side)
    variants["sidecar_array"] = (pas_ok, b"[]")
    variants["sidecar_non_utf8"] = (pas_ok, side[:10] + b"\xff\xfe" + side[10:])
    variants["sidecar_duplicate_key"] = (pas_ok, side[:-1] + b',"schema_version":1}')
    paired(
        "sidecar_schema_version_2",
        sidecar_mut=lambda d: d.__setitem__("schema_version", 2),
    )
    paired("sidecar_unknown_key", sidecar_mut=lambda d: d.__setitem__("extra", 1))
    paired("sidecar_missing_loss", sidecar_mut=lambda d: d.pop("loss"))
    paired("sidecar_missing_capsule", sidecar_mut=lambda d: d.pop("capsule"))
    paired(
        "sidecar_missing_export_effect", sidecar_mut=lambda d: d.pop("export_effect")
    )
    paired(
        "sidecar_pas_sha256_stale",
        lambda s: s["task"].__setitem__("description", "edited after the sidecar"),
        rebind=False,
    )
    variants["sidecar_pas_sha256_mismatch"] = repackage(
        None, lambda d: d.__setitem__("pas_sha256", "0" * 64), rebind=False
    )
    variants["sidecar_pas_sha256_uppercase"] = repackage(
        None, lambda d: d.__setitem__("pas_sha256", d["pas_sha256"].upper())
    )
    variants["sidecar_session_id_mismatch"] = repackage(
        None, lambda d: d.__setitem__("pas_session_id", new_uuid())
    )
    variants["sidecar_capsule_digest_mismatch"] = repackage(
        None, lambda d: d.__setitem__("capsule_digest", "1" * 64)
    )
    variants["sidecar_capsule_tampered"] = repackage(
        None,
        lambda d: d["capsule"]["task"].__setitem__("description", "changed"),
        rebind=True,
    )
    variants["sidecar_capsule_format_wrong"] = repackage(
        capsule_mut=lambda c: c.__setitem__("format", "pas_v1")
    )
    variants["sidecar_loss_not_list"] = repackage(
        None, lambda d: d.__setitem__("loss", {})
    )
    variants["sidecar_loss_entry_missing_key"] = repackage(
        None, lambda d: d["loss"][0].pop("disposition")
    )
    variants["sidecar_loss_entry_unknown_key"] = repackage(
        None, lambda d: d["loss"][0].__setitem__("zzz", 1)
    )
    variants["sidecar_export_effect_bad"] = repackage(
        None, lambda d: d["export_effect"].__setitem__("effect_id", "xyz")
    )
    variants["sidecar_export_effect_unknown_key"] = repackage(
        None, lambda d: d["export_effect"].__setitem__("zzz", "x")
    )
    variants["sidecar_pas_for_other_session"] = repackage(
        lambda s: s.__setitem__("id", new_uuid()), rebind=False
    )
    return variants


def test_pas_unknown_version_or_partial_sidecar_rejected(tmp_path: Path) -> None:
    env = pas_env(tmp_path)
    mapping_id = approved_mapping(env, fixture_sidecar()["capsule"]["origin"])
    # control: the unmodified fixture pair previews through its approved mapping
    good = write_pair(
        tmp_path / "good",
        fixture_bytes("pas_session_schema1.json"),
        fixture_bytes("pas_session_schema1.json.rush-manifest.json"),
    )
    assert preview_pas(env, good, mapping_id=mapping_id).code == "OK"
    variants = pas_byte_variants()
    assert len(variants) >= 60
    for name, (pas, sidecar) in sorted(variants.items()):
        path = write_pair(tmp_path / f"v-{name}", pas, sidecar)
        assert_pas_invalid(env, path, name, mapping_id=mapping_id)

    # a PAS file whose journal exists is an incomplete pair, never a standalone import
    crashed = write_pair(
        tmp_path / "journal", fixture_bytes("pas_session_schema1.json"), None
    )
    journal_path(crashed).write_bytes(canon({"schema_version": 1}))
    assert_pas_invalid(env, crashed, "journal-present")
    # unknown format value
    res = call_inproc(
        env.root,
        {
            "action": "preview_import",
            "format": "pas_v2",
            "input": str(good),
            "invocation_id": new_uuid(),
        },
    )
    assert res.code == "E_INPUT", res


def test_pas_schema1_unicode_status_roundtrip(tmp_path: Path) -> None:
    env = pas_env(tmp_path)
    # --- the writer: exact serde_json::to_string_pretty bytes ---
    out, _preview, done = exported(env, "rt.json", fmt="pas_v1")
    assert done.code == "OK", done
    raw = out.read_bytes()
    session = json.loads(raw)
    assert raw == pretty(session), "exact pretty bytes, no trailing newline"
    assert not raw.endswith(b"\n")
    assert list(session) == PAS_SESSION_KEYS
    assert session["schema_version"] == 1
    assert session["id"] == session["id"].lower() and UUID_RE.match(session["id"])
    assert list(session["task"]) == PAS_TASK_KEYS
    assert_pas_timestamp(session["created_at"])
    assert_pas_timestamp(session["updated_at"])
    for key in (
        "completed",
        "remaining",
        "blockers",
        "decisions",
        "constraints",
        "discoveries",
    ):
        assert all(isinstance(x, str) for x in session["task"][key]), key
    assert session["git"] is None or list(session["git"]) == PAS_GIT_KEYS
    for checkpoint in session["checkpoints"]:
        assert list(checkpoint) == PAS_CHECKPOINT_KEYS
        assert_pas_timestamp(checkpoint["timestamp"])
        assert list(checkpoint["task_snapshot"]) == PAS_TASK_KEYS
    assert "Never rewrite history ünïcode".encode() in raw, "unicode written as UTF-8"
    assert session["task"]["constraints"][0] == "Never rewrite history ünïcode"
    side = json.loads(sidecar_path(out).read_bytes())
    assert set(side) == SIDECAR_KEYS
    assert side["pas_sha256"] == sha(raw)
    assert side["pas_session_id"] == session["id"]
    assert side["capsule_digest"] == side["capsule"]["payload_sha256"]
    assert side["capsule"]["payload_sha256"] == sha(
        canon({k: v for k, v in side["capsule"].items() if k != "payload_sha256"})
    )

    # --- meaning survives: the pair imports to the same records as the rush_v1 export ---
    rush_out, _p, rush_done = exported(env, "rt-rush.json")
    assert rush_done.code == "OK"
    rush_capsule = verify_rush_v1(rush_out.read_bytes())
    pair_preview = preview_pas(env, out)
    assert pair_preview.code == "OK", pair_preview
    pair_records = record_view(pair_preview.data["records"])
    rush_records = expected_records(rush_capsule, "rush_v1")
    assert len(pair_records) == len(rush_records)
    for got, want in zip(pair_records, rush_records, strict=True):
        assert (
            got["foreign_origin_id"].split(":")[0]
            == want["foreign_origin_id"].split(":")[0]
        )
        if want["content"].get("kind") == "imported_task":
            assert got["content"]["task"] == want["content"]["task"]
        else:
            assert got["content"] == want["content"]
            assert got["foreign_owner"] == want["foreign_owner"]
            assert got["foreign_symbol_ref"] == want["foreign_symbol_ref"]
            assert got["foreign_content_hash"] == want["foreign_content_hash"]

    # --- the pinned fixture: order, text, provenance and every FileStatus form ---
    fixture = fixture_session()
    statuses = [f["status"] for f in fixture["checkpoints"][0]["files_changed"]]
    assert {"Renamed": {"from": "older/name.py"}} in statuses
    mapping_id = approved_mapping(env, fixture_sidecar()["capsule"]["origin"])
    pair = write_pair(
        tmp_path / "fx",
        fixture_bytes("pas_session_schema1.json"),
        fixture_bytes("pas_session_schema1.json.rush-manifest.json"),
    )
    previewed = preview_pas(env, pair, mapping_id=mapping_id)
    assert previewed.code == "OK", previewed
    assert record_view(previewed.data["records"]) == expected_records(
        fixture_sidecar()["capsule"], "pas_v1"
    )
    constraints = [r["content"]["text"] for r in previewed.data["records"][1:3]]
    assert (
        constraints
        == fixture["task"]["constraints"]
        == [
            "Never rewrite published history",
            "Keep the suite green ✓ ünï",
        ]
    )

    # --- the reader accepts chrono's relaxed RFC 3339 and every Uuid::from_str form ---
    def solo_ok(label: str, mutate: Any) -> R:
        session = fixture_session()
        mutate(session)
        path = write_pair(tmp_path / f"ok-{label}", pretty(session), None)
        res = preview_pas(env, path)
        assert res.code == "OK", (label, res)
        return res

    base_id = fixture["id"]
    for label, ident in (
        ("upper", base_id.upper()),
        ("simple", base_id.replace("-", "")),
        ("braced", "{" + base_id + "}"),
        ("urn", "urn:uuid:" + base_id),
    ):
        res = solo_ok(f"id-{label}", lambda s, i=ident: s.__setitem__("id", i))
        assert res.data["records"][0]["foreign_origin_id"] == "task:" + base_id, label
    for label, stamp in (
        ("space", "2026-01-02 03:04:05Z"),
        ("lower-t", "2026-01-02t03:04:05Z"),
        ("plus-colon", "2026-01-02T03:04:05+00:00"),
        ("plus", "2026-01-02T03:04:05+0000"),
        ("utc", "2026-01-02T03:04:05UTC"),
        ("offset", "2026-01-02T08:34:05+05:30"),
        ("nanos", "2026-01-02T03:04:05.123456789Z"),
    ):
        solo_ok(f"ts-{label}", lambda s, v=stamp: s.__setitem__("created_at", v))
    for key in ("Added", "Modified", "Deleted", "Untracked"):
        solo_ok(
            f"status-{key}",
            lambda s, k=key: s["checkpoints"][0]["files_changed"][0].__setitem__(
                "status", k
            ),
        )
    solo_ok(
        "unicode-path",
        lambda s: s["checkpoints"][0]["files_changed"][0].__setitem__(
            "path", "docs/ünï/✓.md"
        ),
    )
    # a numeric timestamp is rejected, never converted
    bad = write_pair(
        tmp_path / "num-ts",
        pretty({**fixture_session(), "created_at": 1760000000.5}),
        None,
    )
    assert_pas_invalid(env, bad, "numeric-timestamp")


def test_pas_loss_manifest_and_required_rejection(tmp_path: Path) -> None:
    env = pas_env(tmp_path, "rich")
    content = json.loads(row_of(env, "cp1")["content"])
    structured = {"step": "wire", "done": True}
    content["implemented"] = [structured, "plain step"]
    content["unresolved"] = ["tidy up", {"todo": "docs", "owner": "me"}]
    plant_content(env, "cp1", content)
    out, _preview, done = exported(env, "loss.json", fmt="pas_v1")
    assert done.code == "OK", done
    session = json.loads(out.read_bytes())
    side = json.loads(sidecar_path(out).read_bytes())

    # structured items become canonical JSON strings; nothing is dropped
    assert session["task"]["completed"] == [canon(structured).decode(), "plain step"]
    assert session["task"]["remaining"] == [
        "tidy up",
        canon({"todo": "docs", "owner": "me"}).decode(),
    ]
    # task strings keep their text
    assert session["task"]["constraints"] == [
        q["text"] for q in content["requirements"]
    ]
    assert content["decisions"][0]["text"] in session["task"]["decisions"]
    assert session["task"]["blockers"] == [b["text"] for b in content["blockers"]]
    assert session["task"]["discoveries"] == [d["text"] for d in content["discoveries"]]
    assert session["task"]["next_action"] == content["next_action"]
    # failed approaches appear, explicitly labeled, among the decisions
    failed = content["disproved"][0]["text"]
    labeled = [d for d in session["task"]["decisions"] if failed in d]
    assert labeled and all("failed" in d.lower() for d in labeled), session["task"][
        "decisions"
    ]

    # the ledger: every Rush-only field has an entry with the three keys
    loss = side["loss"]
    assert loss and all(set(e) == {"field", "disposition", "pas_field"} for e in loss)
    assert all(isinstance(e["field"], str) and e["field"] for e in loss)
    assert all(isinstance(e["disposition"], str) and e["disposition"] for e in loss)
    assert all(e["pas_field"] is None or isinstance(e["pas_field"], str) for e in loss)
    fields = " ".join(e["field"] for e in loss)
    for rush_only in (
        "failed_approaches",
        "last_verified_checkpoint",
        "origin_ref",
        "evidence",
        "origin",
        "scope",
    ):
        assert rush_only in fields, (rush_only, fields)
    # the sidecar retains every Rush-only value and carries no authority
    capsule = side["capsule"]
    assert capsule["task"]["failed_approaches"] == content["disproved"]
    assert capsule["task"]["last_verified_checkpoint"]["status"] == "passed"
    assert [e["artifact_id"] for e in capsule["evidence"]] == ["ev1", "ev2"]
    text = sidecar_path(out).read_text(encoding="utf-8")
    assert env.grant is not None and env.grant["grant_id"] not in text
    assert str(env.root) not in text and str(env.data_root) not in text

    # required meaning that PAS cannot hold refuses the export, with no output
    for name, mutate in (
        ("no-next-action", lambda c: c.__setitem__("next_action", "")),
        ("no-passing-check", lambda c: c.__setitem__("checks", [])),
    ):
        blocked = pas_env(tmp_path, f"blocked-{name}")
        stored = json.loads(row_of(blocked, "cp1")["content"])
        mutate(stored)
        plant_content(blocked, "cp1", stored)
        target = blocked.outside / "b.json"
        res = call_inproc(
            blocked.root,
            {
                "action": "preview_export",
                "format": "pas_v1",
                "output": str(target),
                "invocation_id": new_uuid(),
            },
        )
        assert_denied(res, "E_PERMISSION", "export_blocked")
        assert not target.exists() and not sidecar_path(target).exists()


def test_pas_sidecar_exact_byte_pair_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_tamper_cases(tmp_path, monkeypatch)
    env = pas_env(tmp_path)
    first, _p1, d1 = exported(env, "a.json", fmt="pas_v1")
    second, _p2, d2 = exported(env, "b.json", fmt="pas_v1")
    assert d1.code == "OK" and d2.code == "OK"
    pas_a, side_a = first.read_bytes(), sidecar_path(first).read_bytes()
    pas_b, side_b = second.read_bytes(), sidecar_path(second).read_bytes()
    assert pas_a != pas_b and side_a != side_b

    ok = preview_pas(env, first)
    assert ok.code == "OK", ok
    # mix-and-match valid files: A's PAS with B's sidecar (and the reverse)
    for label, pas, side in (("a+b", pas_a, side_b), ("b+a", pas_b, side_a)):
        path = write_pair(tmp_path / f"mix-{label}", pas, side)
        assert_pas_invalid(env, path, label)
    # one byte of whitespace in the PAS file breaks the sidecar's byte digest
    reformatted = pretty(json.loads(pas_a)).replace(b"\n  ", b"\n   ", 1)
    path = write_pair(tmp_path / "reformat-pas", reformatted, side_a)
    assert_pas_invalid(env, path, "reformatted-pas")
    # the same sidecar content in other bytes is a different input: the preview
    # digest changes, and applying with the old digest conflicts
    pretty_side = pretty(json.loads(side_a))
    path = write_pair(tmp_path / "reformat-side", pas_a, pretty_side)
    other = preview_pas(env, path)
    assert other.code == "OK", other
    base = {"format": "pas_v1", "invocation_id": new_uuid()}
    preview_a = call_inproc(
        env.root, {**base, "action": "preview_import", "input": str(first)}
    )
    preview_b = call_inproc(
        env.root, {**base, "action": "preview_import", "input": str(path)}
    )
    assert preview_a.data["digest"] != preview_b.data["digest"]
    before = env.effects()
    stale = call_inproc(
        env.root,
        {
            **base,
            "action": "import",
            "apply": True,
            "input": str(path),
            "expected_digest": preview_a.data["digest"],
            "expected_store_revision": preview_store_rev(preview_a),
        },
    )
    assert_denied(stale, "E_VERSION", "recovery_required")
    assert env.effects() == before and not imported_rows(env)
    # a valid pair applies
    preview_i, done = imported(env, first, fmt="pas_v1")
    assert preview_i.code == "OK" and done.code == "OK", (preview_i, done)
    assert len(imported_rows(env)) == 5
    _cleanup_failure_cases(tmp_path, monkeypatch)


def preview_store_rev(res: R) -> int:
    data = res.data
    if "store_revision" in data:
        return int(data["store_revision"])
    return int(data["preview_binding"]["store_revision"])


def test_pas_nullable_git_next_action_and_serde_defaults(tmp_path: Path) -> None:
    env = pas_env(tmp_path)
    # --- the pinned defaults file: git null, next_action null, defaults omitted ---
    path = write_pair(
        tmp_path / "defaults", fixture_bytes("pas_standalone_defaults.json"), None
    )
    res = preview_pas(env, path)
    assert res.code == "OK", res
    assert res.data["origin_match"] == "absent"
    record = res.data["records"][0]
    assert record["foreign_origin_id"] == "task:9c8b7a65-4d3e-4f21-8a09-b8c7d6e5f4a3"
    task = record["content"]["task"]
    assert task["next_action"] is None
    assert task["description"] == "Standalone limited task"
    assert task.get("completed", []) == [] and task.get("remaining", []) == []
    assert len(res.data["records"]) == 1, "no constraints were declared"
    # missing continuation facts are declared in the preview, not hidden
    declared = json.dumps({k: v for k, v in res.data.items() if k != "records"})
    assert "next_action" in declared
    # it is limited, unverified task evidence: nothing imports as complete continuation
    _prev, done = imported(env, path, fmt="pas_v1")
    assert done.code == "OK", done
    assert {m["applicability"] for m in done.data["mappings"]} == {"pending"}
    rows = imported_rows(env)
    assert (
        len(rows) == 1
        and json.loads(rows[0]["content"])["authority"] == "imported_unverified"
    )

    # --- serde defaults: an empty task, omitted schema_version/git/checkpoints ---
    minimal = {
        "id": new_uuid(),
        "project_name": "m",
        "created_at": "2026-02-03T04:05:06Z",
        "updated_at": "2026-02-03T04:05:06Z",
        "task": {},
    }
    ok = preview_pas(env, write_pair(tmp_path / "minimal", pretty(minimal), None))
    assert ok.code == "OK", ok
    assert ok.data["records"][0]["content"]["task"]["next_action"] is None
    # a git object defaults its omitted keys; an explicit null git is accepted
    git_object = preview_pas(
        env,
        write_pair(
            tmp_path / "git-obj", pretty({**minimal, "git": {"branch": None}}), None
        ),
    )
    assert git_object.code == "OK", git_object
    # absent id / timestamps / task, a wrong default type, or an unknown field still error
    for label, broken in (
        ("no-id", {k: v for k, v in minimal.items() if k != "id"}),
        ("no-timestamps", {k: v for k, v in minimal.items() if k != "created_at"}),
        ("no-task", {k: v for k, v in minimal.items() if k != "task"}),
        ("dirty-not-bool", {**minimal, "git": {"dirty": "no"}}),
        ("next-action-int", {**minimal, "task": {"next_action": 3}}),
        ("unknown-field", {**minimal, "mystery": 1}),
    ):
        assert_pas_invalid(
            env, write_pair(tmp_path / f"b-{label}", pretty(broken), None), label
        )

    # --- the writer emits explicit defaults and nulls; a missing next action refuses ---
    bare = pas_env(tmp_path, "nulls")
    stored = json.loads(row_of(bare, "cp1")["content"])
    stored["source"] = {
        "commit": None,
        "branch": None,
        "dirty": False,
        "file_sha256": None,
    }
    plant_content(bare, "cp1", stored)
    out, _p, done_export = exported(bare, "nulls.json", fmt="pas_v1")
    assert done_export.code == "OK", done_export
    session = json.loads(out.read_bytes())
    assert list(session) == PAS_SESSION_KEYS, "every top-level key is written"
    assert session["git"] in (None, {"branch": None, "commit": None, "dirty": False})
    assert out.read_bytes() == pretty(session)
    stored["next_action"] = ""
    plant_content(bare, "cp1", stored)
    refused = call_inproc(
        bare.root,
        {
            "action": "preview_export",
            "format": "pas_v1",
            "output": str(bare.outside / "refused.json"),
            "invocation_id": new_uuid(),
        },
    )
    assert_denied(refused, "E_PERMISSION", "export_blocked")


# --- two-file publication (G8-T9) ------------------------------------------------


def _pas_export_request(env: CapEnv, name: str) -> tuple[Path, dict[str, Any]]:
    out = env.outside / name
    base = {"format": "pas_v1", "output": str(out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    assert preview.code == "OK", preview
    return out, {**base, "action": "export", "expected_digest": preview.data["digest"]}


def test_pas_second_replace_failure_preserves_concurrent_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace

    def failing_second(edit: bytes | None, target: Path) -> Any:
        def replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
            if str(dst).endswith(".rush-manifest.json"):
                if edit is not None:
                    target.write_bytes(edit)
                raise OSError("simulated failure replacing the sidecar")
            return real_replace(src, dst, *args, **kwargs)

        return replace

    # a failure with no concurrent edit restores the first file to its prior state
    env = pas_env(tmp_path, "plain")
    out, request = _pas_export_request(env, "p.json")
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", failing_second(None, out))
        res = call_inproc(env.root, request)
    assert_denied(res, "E_VERSION", "recovery_required")
    assert not out.exists() and not sidecar_path(out).exists(), "restored to absent"
    assert not journal_path(out).exists(), (
        "the journal is removed after a clean restore"
    )

    # a concurrent edit of the first file keeps both files' bytes and the journal
    env = pas_env(tmp_path, "edited")
    out, request = _pas_export_request(env, "e.json")
    edited = b'{"edited": "concurrently"}'
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", failing_second(edited, out))
        res = call_inproc(env.root, request)
    assert_denied(res, "E_VERSION", "recovery_required")
    assert out.read_bytes() == edited, "the concurrent edit is preserved"
    assert not sidecar_path(out).exists()
    assert journal_path(out).exists(), "recovery state is kept"

    # an existing target restores its old bytes
    env = pas_env(tmp_path, "prior")
    out = env.outside / "old.json"
    out.write_bytes(b"previous owner bytes")
    base = {"format": "pas_v1", "output": str(out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    request = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", failing_second(None, out))
        res = call_inproc(env.root, request)
    assert_denied(res, "E_VERSION", "recovery_required")
    assert out.read_bytes() == b"previous owner bytes"
    assert not journal_path(out).exists()

    _second_replace_sidecar_cases(tmp_path, monkeypatch)
    _second_replace_backup_cases(tmp_path, monkeypatch)


_CRASH_CHILD = """
import json, os, sys
from pathlib import Path
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

root, request = sys.argv[1:3]
real = os.replace

def replace(src, dst, *args, **kwargs):
    if str(dst).endswith('.rush-manifest.json'):
        os._exit(7)
    return real(src, dst, *args, **kwargs)

os.replace = replace
MemoryTool().run(
    Path(root),
    operation='capsule',
    request=json.loads(request),
    permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
)
os._exit(0)
"""


# --- recovery after a partial publication (G8-T9 and the pre-gate overrides) ------


def _journal(out: Path) -> dict[str, Any]:
    return json.loads(journal_path(out).read_bytes())


def _crash_state(
    env: CapEnv, name: str, *, prior: bool = False
) -> tuple[Path, dict[str, Any]]:
    """Run an export in a child that dies between the two replaces. With `prior` the
    target pair already holds another owner's files; the preview binds them."""
    import rush

    out = env.outside / name
    if prior:
        out.write_bytes(b"old pas bytes")
        sidecar_path(out).write_bytes(b"old sidecar bytes")
    _out, request = _pas_export_request(env, name)
    src_dir = str(Path(rush.__file__).resolve().parents[1])
    child = subprocess.run(
        [sys.executable, "-c", _CRASH_CHILD, str(env.root), json.dumps(request)],
        env={**os.environ, "PYTHONPATH": src_dir},
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert child.returncode == 7, child.stderr.decode("utf-8", "replace")[-2000:]
    return out, request


def _assert_recovery_kept(
    env: CapEnv, request: dict[str, Any], out: Path, label: str
) -> None:
    """The identical retry refuses and leaves every byte, including the journal."""
    watched = [out, sidecar_path(out), journal_path(out)]
    before = {p: (p.read_bytes() if p.exists() else None) for p in watched}
    res = call_inproc(env.root, request)
    assert_denied(res, "E_VERSION", "recovery_required")
    after = {p: (p.read_bytes() if p.exists() else None) for p in watched}
    assert after == before, label
    assert journal_path(out).exists(), label


def _crash_recovery_cases(tmp_path: Path) -> None:
    # a sidecar created behind the crashed export: kept, never overwritten
    env = pas_env(tmp_path, "crash-created")
    out, request = _crash_state(env, "created.json")
    sidecar_path(out).write_bytes(b"created by someone else")
    _assert_recovery_kept(env, request, out, "sidecar created")
    sidecar_path(out).unlink()  # back to the recorded (absent) state
    done = call_inproc(env.root, request)
    assert done.code == "OK" and done.data["replayed"] is True, done
    assert not journal_path(out).exists()

    # a prior sidecar edited or deleted behind the crashed export
    for label, action in (
        ("edited", lambda p: p.write_bytes(b"edited by someone else")),
        ("deleted", lambda p: p.unlink()),
    ):
        env = pas_env(tmp_path, f"crash-{label}")
        out, request = _crash_state(env, f"{label}.json", prior=True)
        side = sidecar_path(out)
        assert side.read_bytes() == b"old sidecar bytes"
        action(side)
        _assert_recovery_kept(env, request, out, f"sidecar {label}")
        side.write_bytes(b"old sidecar bytes")  # the recorded old state again
        done = call_inproc(env.root, request)
        assert done.code == "OK", (label, done)
        assert json.loads(side.read_bytes())["pas_sha256"] == sha(out.read_bytes())
        assert not journal_path(out).exists()

    # the published PAS file deleted: neither old nor intended, everything is kept
    env = pas_env(tmp_path, "crash-pas-deleted")
    out, request = _crash_state(env, "gone.json")
    out.unlink()
    _assert_recovery_kept(env, request, out, "pas deleted")
    assert not sidecar_path(out).exists()

    # a forged journal never steers a replace or an unlink to an unrelated file
    for field in (
        "pas.path",
        "pas.stage",
        "pas.backup",
        "sidecar.path",
        "sidecar.stage",
    ):
        env = pas_env(tmp_path, f"forged-{field}")
        out, request = _crash_state(env, "forged.json", prior=True)
        victim = env.outside / "victim.txt"
        victim.write_bytes(b"unrelated bytes")
        stamp = (victim.read_bytes(), victim.stat().st_mtime_ns)
        journal = _journal(out)
        section, key = field.split(".")
        journal[section][key] = str(victim)
        journal_path(out).write_bytes(canon(journal))
        _assert_recovery_kept(env, request, out, field)
        assert (victim.read_bytes(), victim.stat().st_mtime_ns) == stamp, field


def _second_replace_sidecar_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidecar replace fails after a concurrent create, edit or delete of the
    sidecar: its bytes are kept, the journal stays, and restoring the recorded state
    lets the identical retry finish."""
    real_replace = os.replace
    cases = (
        ("created", False, lambda side: side.write_bytes(b"created concurrently")),
        ("edited", True, lambda side: side.write_bytes(b"edited concurrently")),
        ("deleted", True, lambda side: side.unlink()),
    )
    for label, prior, action in cases:
        env = pas_env(tmp_path, f"side-{label}")
        out = env.outside / f"{label}.json"
        side = sidecar_path(out)
        if prior:
            out.write_bytes(b"old pas bytes")
            side.write_bytes(b"old sidecar bytes")
        _out, request = _pas_export_request(env, f"{label}.json")

        def failing(dst_side: Path = side, act: Any = action) -> Any:
            def replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
                if str(dst).endswith(".rush-manifest.json"):
                    act(dst_side)
                    raise OSError("simulated failure replacing the sidecar")
                return real_replace(src, dst, *args, **kwargs)

            return replace

        with monkeypatch.context() as scoped:
            scoped.setattr(os, "replace", failing())
            res = call_inproc(env.root, request)
        assert_denied(res, "E_VERSION", "recovery_required")
        journal = _journal(out)
        assert sha(out.read_bytes()) == journal["pas"]["intended_sha256"], label
        if label == "deleted":
            assert not side.exists()
        else:
            assert side.read_bytes() == (
                b"created concurrently"
                if label == "created"
                else b"edited concurrently"
            )
        _assert_recovery_kept(env, request, out, label)
        if prior:
            side.write_bytes(b"old sidecar bytes")
        else:
            side.unlink()
        done = call_inproc(env.root, request)
        assert done.code == "OK", (label, done)
        assert not journal_path(out).exists()


def _second_replace_backup_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tampered backup is never restored over the published file."""
    real_replace = os.replace
    env = pas_env(tmp_path, "backup-tamper")
    out = env.outside / "bk.json"
    out.write_bytes(b"old pas bytes")
    _out, request = _pas_export_request(env, "bk.json")

    def replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
        if str(dst).endswith(".rush-manifest.json"):
            for entry in env.outside.iterdir():
                if ".rush-backup-" in entry.name:
                    entry.write_bytes(b"tampered backup")
            raise OSError("simulated failure replacing the sidecar")
        return real_replace(src, dst, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", replace)
        res = call_inproc(env.root, request)
    assert_denied(res, "E_VERSION", "recovery_required")
    journal = _journal(out)
    assert sha(out.read_bytes()) == journal["pas"]["intended_sha256"]
    backups = [p for p in env.outside.iterdir() if ".rush-backup-" in p.name]
    assert len(backups) == 1 and backups[0].read_bytes() == b"tampered backup"
    assert journal_path(out).exists()


def _cleanup_failure_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every cleanup step fails alone and together with the primary publication
    failure: a controlled recovery result, retained recovery evidence, a redacted
    diagnostic and no escaping cleanup exception."""
    real_unlink, real_remove, real_replace = os.unlink, os.remove, os.replace
    sentinel = f"SENTINEL-{tmp_path}"

    def faults(fragments: tuple[str, ...], restore: bool, primary: bool) -> Any:
        def hit(path: Any) -> bool:
            name = os.path.basename(os.fspath(path))
            return any(
                name == f[1:] if f.startswith("=") else f in name for f in fragments
            )

        def unlink(path: Any, *args: Any, **kwargs: Any) -> Any:
            if hit(path):
                raise PermissionError(13, sentinel)
            return real_unlink(path, *args, **kwargs)

        def remove(path: Any, *args: Any, **kwargs: Any) -> Any:
            if hit(path):
                raise PermissionError(13, sentinel)
            return real_remove(path, *args, **kwargs)

        def replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
            if primary and str(dst).endswith(".rush-manifest.json"):
                raise OSError("simulated failure replacing the sidecar")
            if restore and ".rush-backup-" in os.path.basename(os.fspath(src)):
                raise PermissionError(13, sentinel)
            return real_replace(src, dst, *args, **kwargs)

        return unlink, remove, replace

    scenarios = (
        # (label, name fragments whose unlink fails, restore replace fails, primary)
        ("backup", (".rush-backup-",), False, False),
        ("journal", (".rush-journal.json",), False, False),
        ("backup+journal", (".rush-backup-", ".rush-journal.json"), False, False),
        ("primary+journal", (".rush-journal.json",), False, True),
        ("primary+restore", (), True, True),
        ("primary+restore+journal", (".rush-journal.json",), True, True),
        ("primary+unlink-target", ("=target.json",), False, True),
    )
    for label, fragments, restore, primary in scenarios:
        env = pas_env(tmp_path, f"cleanup-{label}")
        has_prior = label != "primary+unlink-target"
        name = "target.json" if not has_prior else f"{label.replace('+', '-')}.json"
        out = env.outside / name
        if has_prior:
            out.write_bytes(b"old pas bytes")
            sidecar_path(out).write_bytes(b"old sidecar bytes")
        _out, request = _pas_export_request(env, name)
        unlink, remove, replace = faults(fragments, restore, primary)
        with monkeypatch.context() as scoped:
            scoped.setattr(os, "unlink", unlink)
            scoped.setattr(os, "remove", remove)
            scoped.setattr(os, "replace", replace)
            res = call_inproc(env.root, request)  # no exception may escape
        assert_denied(res, "E_VERSION", "recovery_required")
        assert sentinel not in json.dumps(res.result, default=str), label
        assert isinstance(res.data.get("message"), str) and res.data["message"], label
        if not primary or restore or "journal" in "".join(fragments):
            assert journal_path(out).exists(), label
        if not primary:
            published = json.loads(sidecar_path(out).read_bytes())
            assert published["pas_sha256"] == sha(out.read_bytes()), label
        # without the injected faults the identical retry is controlled again; after a
        # completed publication it finishes the export from the journal
        retry = call_inproc(env.root, request)
        if not primary:
            assert retry.code == "OK" and retry.data["replayed"] is True, (label, retry)
            assert not journal_path(out).exists(), label
            assert json.loads(sidecar_path(out).read_bytes())["pas_sha256"] == sha(
                out.read_bytes()
            )
            assert preview_pas(env, out).code == "OK", label


def _stage_tamper_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Staged and published files are two views of one pair: bytes altered after
    staging (the journal is written after both stages exist) are never published."""
    from rush.io import atomic_file

    original = atomic_file.AtomicFile.write_bytes
    for which in ("pas", "sidecar"):
        env = pas_env(tmp_path, f"stage-{which}")
        out, request = _pas_export_request(env, f"stage-{which}.json")

        def spy(
            self: Any,
            name: str,
            sanitized: Any,
            *args: Any,
            _which: str = which,
            _dir: Path = env.outside,
            **kwargs: Any,
        ) -> Any:
            if name.endswith(".rush-journal.json"):
                for entry in _dir.iterdir():
                    if f".rush-stage-{_which}-" in entry.name:
                        entry.write_bytes(entry.read_bytes() + b" ")
            return original(self, name, sanitized, *args, **kwargs)

        with monkeypatch.context() as scoped:
            scoped.setattr(atomic_file.AtomicFile, "write_bytes", spy)
            res = call_inproc(env.root, request)
        assert_denied(res, "E_VERSION", "recovery_required")
        assert not sidecar_path(out).exists(), "an altered stage is never published"
        if which == "pas":
            assert not out.exists(), "an altered PAS stage is never published"


def test_pas_export_crash_journal_retry(tmp_path: Path) -> None:
    import rush

    env = pas_env(tmp_path)
    out, request = _pas_export_request(env, "crash.json")
    src_dir = str(Path(rush.__file__).resolve().parents[1])
    child = subprocess.run(
        [sys.executable, "-c", _CRASH_CHILD, str(env.root), json.dumps(request)],
        env={**os.environ, "PYTHONPATH": src_dir},
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert child.returncode == 7, child.stderr.decode("utf-8", "replace")[-2000:]
    assert out.exists() and not sidecar_path(out).exists()
    journal = json.loads(journal_path(out).read_bytes())
    assert set(journal) == JOURNAL_KEYS and journal["schema_version"] == 1
    intended = journal["pas"]["intended_sha256"]
    assert HEX64.match(intended) and sha(out.read_bytes()) == intended

    # the incomplete pair is rejected on read and reported for recovery
    assert_pas_invalid(env, out, "incomplete-pair")
    before_files = {p: p.read_bytes() for p in (out, journal_path(out))}

    # a retry that changes the request conflicts; the journal stays
    changed = call_inproc(env.root, {**request, "max_bytes": 70000})
    assert_denied(changed, "E_VERSION", "effect_digest_conflict")
    assert journal_path(out).exists()
    assert {p: p.read_bytes() for p in before_files} == before_files

    # a concurrent edit of the PAS file keeps both files and asks for recovery
    out.write_bytes(b"{}")
    edited = call_inproc(env.root, request)
    assert_denied(edited, "E_VERSION", "recovery_required")
    assert out.read_bytes() == b"{}" and journal_path(out).exists()
    assert not sidecar_path(out).exists()
    out.write_bytes(before_files[out])

    # the identical retry publishes the sidecar, completes the pair and clears the journal
    retry = call_inproc(env.root, request)
    assert retry.code == "OK", retry
    assert sha(out.read_bytes()) == intended
    side = json.loads(sidecar_path(out).read_bytes())
    assert side["pas_sha256"] == intended
    assert side["capsule"]["capsule_id"] == journal["receipt"]["capsule_id"]
    assert retry.data["capsule_id"] == journal["receipt"]["capsule_id"]
    assert not journal_path(out).exists()
    assert preview_pas(env, out).code == "OK"
    leftovers = [
        p.name for p in env.outside.iterdir() if p.name.startswith(".crash.json")
    ]
    assert leftovers == []
    _crash_recovery_cases(tmp_path)


def test_pas_export_binds_sidecar_prestate(tmp_path: Path) -> None:
    env = pas_env(tmp_path)
    for label in ("created", "changed"):
        out = env.outside / f"{label}.json"
        side = sidecar_path(out)
        if label == "changed":
            side.write_bytes(b"old sidecar")
        base = {"format": "pas_v1", "output": str(out), "invocation_id": new_uuid()}
        preview = call_inproc(env.root, {**base, "action": "preview_export"})
        assert preview.code == "OK", preview
        side.write_bytes(b"created or changed behind the preview")
        res = call_inproc(
            env.root,
            {**base, "action": "export", "expected_digest": preview.data["digest"]},
        )
        assert_denied(res, "E_VERSION", "recovery_required")
        assert not out.exists(), label
        assert side.read_bytes() == b"created or changed behind the preview"
        assert not journal_path(out).exists()
    # control: an unchanged pre-state publishes both files
    out = env.outside / "control.json"
    base = {"format": "pas_v1", "output": str(out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    done = call_inproc(
        env.root,
        {**base, "action": "export", "expected_digest": preview.data["digest"]},
    )
    assert done.code == "OK", done
    assert (
        out.exists() and sidecar_path(out).exists() and not journal_path(out).exists()
    )
    assert done.data["bytes"] == len(out.read_bytes()) + len(
        sidecar_path(out).read_bytes()
    )
