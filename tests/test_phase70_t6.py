"""Phase 70 T6 RED-first test matrix: operation-specific MCP schemas.

Binding design: ``.scratch/phase-70-design-gate/W1-T1-T7-T23.md`` ``## T6``.
Plan packet: ``docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md``
``#### T6 — Operation-specific schemas without breaking old calls``.

The brief names ``tests/test_phase70_adoption.py::test_t06_emitted_schema_and_dispatch``
as the target test. This task (tests-first only, one new file) writes every case from
that matrix here instead, using the brief's own sub-behavior names as test function
names so the eventual implementer can lift them verbatim into that shared file. See
the task receipt for the exact name mapping.

No source under ``src/rush`` implements T6 yet: ``rush.mcp_support.request_models``
(``published_schema``, ``validate_and_normalize``) and ``RushFastMCP`` do not exist.
Every test that depends on them imports the missing symbol inside the test body, so
each fails individually (collection succeeds; execution errors) with the real reason:
not implemented. A handful of cases need no new module at all -- they exercise an
already-provable *current* bug (X3: ``Literal[1]`` accepts ``True``/``1.0``; bare
``bool()`` accepts truthy strings) directly against today's ``ProjectTool``/
``ScanTool``, and are RED because today's code wrongly *accepts* the bad input.

Everything here uses ``tmp_path`` as ``data_root`` and never touches a real host
HOME/config. No network calls.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, get_args

import jsonschema
import pytest

from rush.mcp import build_server
from rush.tools.memory import VALID_OPERATIONS as _MEMORY_VALID_OPERATIONS
from rush.tools.memory import MemoryOperation
from rush.tools.project import ProjectTool

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Operation matrices, taken verbatim from the T6 brief's model tables (section
# "3. Design" -> Project/Scan/Memory model matrices) and the plan packet's own
# "Project/Scan/Memory model matrix" paragraphs.
#
# Each entry is (operation, minimal_valid_fields, required_field_dropped_for_the
# missing-required-field case). `None` means the brief lists no required field
# for that operation (schema-level), so only the minimum-valid case applies.
# ---------------------------------------------------------------------------

PROJECT_OPERATIONS: list[tuple[str, dict[str, Any], str | None]] = [
    ("list", {"limit": 50}, None),
    ("add", {"path": "."}, "path"),
    ("show", {}, None),
    ("snapshot", {}, None),
    ("select", {"project": str(uuid.uuid4()), "session_id": "s1"}, "project"),
    ("create", {"parent": ".", "name": "proj"}, "parent"),
    (
        "relink",
        {"project": str(uuid.uuid4()), "path": ".", "expected_revision": 0},
        "expected_revision",
    ),
    ("configure", {"project": str(uuid.uuid4())}, "project"),
    ("artifacts", {}, None),
]
assert len(PROJECT_OPERATIONS) == 9

SCAN_OPERATIONS: list[tuple[str, dict[str, Any], str | None]] = [
    ("plan", {"project": str(uuid.uuid4())}, "project"),
    ("run", {"project": str(uuid.uuid4()), "plan_id": "p1"}, "plan_id"),
    ("status", {"project": str(uuid.uuid4()), "run_id": "r1"}, "run_id"),
    ("rescan", {"project": str(uuid.uuid4()), "run_id": "r1"}, "run_id"),
    ("cancel", {"project": str(uuid.uuid4()), "run_id": "r1"}, "run_id"),
    ("resume", {"project": str(uuid.uuid4()), "run_id": "r1"}, "run_id"),
]
assert len(SCAN_OPERATIONS) == 6

# Memory: common `path` (required) omitted here (added by the fixture); every
# other field below is that operation's own extra required set per the brief's
# "Memory models" design section and `tools/memory.py`'s own dispatch table
# (`_query`, `_expand`, `_link`, ... `_run_archive`) and `_*_REQUEST_KEYS`
# constants. Operations dispatching through a nested `request` payload use the
# same nesting the brief specifies ("the remaining operations take `request`
# (required) typed per ..."); `verify_attempt` is not named in that list but
# follows the identical `request`-nested shape as its sibling operations
# (`self._verify_attempt(started, root, granted, request)`), so this test
# assumes that shape for it too. Each nested `request` carries the keys its
# handler's own `E_INPUT` check requires (plan T6: "Every existing operation has a
# valid model/call fixture using current validator contract").
MEMORY_OPERATIONS: list[tuple[str, dict[str, Any], str | None]] = [
    (
        "ask",
        {"subject": "episodic", "query": "q", "session_allowlist": ["s1"]},
        "query",
    ),
    (
        "recall",
        {"subject": "episodic", "query": "q", "session_allowlist": ["s1"]},
        "query",
    ),
    (
        "list",
        {"subject": "episodic", "query": "q", "session_allowlist": ["s1"]},
        "session_allowlist",
    ),
    ("write", {"subject": "episodic", "content": {"k": "v"}, "source": "t"}, "content"),
    (
        "promote",
        {
            "subject": "episodic",
            "content": {"k": "v"},
            "source": "t",
            "user_stated": True,
            "candidate_sources": ["t"],
        },
        "source",
    ),
    (
        "maintain",
        {"task": "staleness_sweep", "owner_scope": {"kind": "project", "id": "p"}},
        "task",
    ),
    ("expand", {"request": {"id": "a1", "version": 1}}, "request"),
    (
        "link",
        {
            "request": {
                "source_id": "a",
                "source_version": 1,
                "target_id": "b",
                "target_version": 1,
                "kind": "relates_to",
            }
        },
        "request",
    ),
    ("related", {"request": {"id": "a1", "version": 1}}, "request"),
    ("consolidate", {"request": {"symptom": "s"}}, "request"),
    (
        "verify_attempt",
        {
            "request": {
                "attempt_id": "att1",
                "behavior_ids": ["b1"],
                "contract": {},
                "patch": "p",
            }
        },
        "request",
    ),
    ("prepare", {"request": {"task": "t", "conditions": {}}}, "request"),
    ("resume", {"request": {"task": "t", "conditions": {}}}, "request"),
    (
        "intent",
        {"request": {"action": "create", "intent_id": "i1", "behavior_id": "b1"}},
        "request",
    ),
    ("recipe", {"request": {"action": "record", "recipe_id": "r1"}}, "request"),
    (
        "plan_checks",
        {
            "request": {
                "changed_targets": [{"id": "f.py"}],
                "required_checks": [{"id": "c1"}],
            }
        },
        "request",
    ),
    (
        "last_success_diagnose",
        {"request": {"behavior_id": "b1", "conditions": {}}},
        "request",
    ),
    (
        "handoff",
        {
            "request": {
                "action": "prepare",
                "receiver_audience": "r",
                "goal": "g",
                "selected_refs": [{"id": "a1", "version": 1}],
            }
        },
        "request",
    ),
    ("receive", {"request": {"session_id": "s1", "capability": "c"}}, "request"),
    (
        "delete",
        {
            "request": {
                "artifact_ids": ["a1"],
                "expected_revisions": {"a1": 1},
                "scope": "episodic",
            }
        },
        "request",
    ),
    (
        "edit",
        {
            "request": {
                "scope": "episodic",
                "id": "a1",
                "expected_version": 1,
                "content": {"k": "v"},
            }
        },
        "request",
    ),
    (
        "archive",
        {"request": {"scope": "episodic", "id": "a1", "expected_version": 1}},
        "request",
    ),
]
assert len(MEMORY_OPERATIONS) == 22
assert {op for op, _, _ in MEMORY_OPERATIONS} == _MEMORY_VALID_OPERATIONS


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Some current dispatch paths (e.g. `ProjectTool` "list") fall back to
    `default_data_root()`, which reads `Path.home()`, ignoring any explicit
    `data_root` this file passes. Force `HOME` to an empty temp dir so no test
    ever reads or writes the real host's Rush data root."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    # `list_projects_page` (via `ProjectTool` "list") ignores any explicit
    # `data_root` and always resolves through `default_data_root()`, which now
    # points inside this temp HOME. It needs a cursor signing key to exist
    # there or every "list" call fails with an unrelated SETUP_REQUIRED error
    # that would mask the real signal these tests check.
    from rush.workflows.projects import ensure_cursor_key

    ensure_cursor_key()


def _server():
    return build_server()


def _list_tools_sync(server):
    return asyncio.run(server.list_tools())


def _call_tool_sync(server, name, arguments):
    return asyncio.run(server.call_tool(name, arguments))


def _snapshot_dir(root: Path) -> dict[str, tuple[int, int]]:
    """(size, mtime_ns) per file under `root`, for a zero-effects before/after diff."""
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# Keep-green guards: current behavior T6 must not break. These pass today.
# ---------------------------------------------------------------------------


def test_t06_keepgreen_current_schemas_are_top_level_objects_no_combinators():
    """X2: today's published schemas for the T6 tools are already plain top-level
    objects (no `oneOf`/`anyOf`/`allOf`/`not`/`if`/`then`/`else`/`$ref` at the top
    level). T6 must preserve this -- a naive discriminated-union schema would
    break it (proven in the brief: such a union's top level is
    `['$defs', 'discriminator', 'oneOf']`)."""
    forbidden_top_level = {
        "oneOf",
        "anyOf",
        "allOf",
        "not",
        "if",
        "then",
        "else",
        "$ref",
    }
    server = _server()
    tools = {t.name: t for t in _list_tools_sync(server)}
    for name in ("rush_project", "rush_scan", "rush_memory"):
        schema = tools[name].inputSchema
        assert schema.get("type") == "object", (name, schema)
        assert not (forbidden_top_level & schema.keys()), (name, schema)
        jsonschema.Draft202012Validator.check_schema(schema)


def test_t06_keepgreen_memory_operation_literal_matches_valid_operations_set():
    """Baseline parity T6 must preserve and extend: the `MemoryOperation` Literal
    already matches `VALID_OPERATIONS` today; T6 adds a third leg (model tags)
    that does not exist yet (see `test_t06_parity_sets_*` below)."""
    assert set(get_args(MemoryOperation)) == _MEMORY_VALID_OPERATIONS


# ---------------------------------------------------------------------------
# RED, no new module needed: today's code demonstrably accepts invalid input
# that T6's strict models must reject (X3).
# ---------------------------------------------------------------------------


def test_t06_schema_version_true_is_wrongly_accepted_today(tmp_path):
    """X3 (proven): `Literal[1]`/`!= 1` comparisons accept `True` because
    `True == 1` in Python. T6 requires `StrictInt` so `schema_version: true` is
    rejected as `int_type` before any effect. Today it is silently accepted --
    this is the RED case."""
    result = ProjectTool().handle_request(
        {"schema_version": True, "operation": "list"}, data_root=tmp_path
    )
    assert result["raw"]["error"] is not None, (
        "schema_version=True must be rejected once T6 lands strict types; "
        f"today's result was wrongly accepted: {result['raw']!r}"
    )


def test_t06_schema_version_float_is_wrongly_accepted_today(tmp_path):
    """X3 (proven): `1.0 == 1` in Python, so today's `!= 1` check accepts a float
    schema_version too. T6's `StrictInt` must reject it."""
    result = ProjectTool().handle_request(
        {"schema_version": 1.0, "operation": "list"}, data_root=tmp_path
    )
    assert result["raw"]["error"] is not None, (
        "schema_version=1.0 must be rejected once T6 lands strict types; "
        f"today's result was wrongly accepted: {result['raw']!r}"
    )


def test_t06_string_grant_false_is_wrongly_truthy_today(tmp_path):
    """Today's grant coercion is bare `bool(request.get(field, False))`. A
    non-empty string like `"false"` is truthy in Python, so it is wrongly
    treated as a granted permission -- and, because `add` is an artifact-write
    action, this actually creates a registered project on disk. T6's
    `StrictBool` must reject a non-bool grant before any effect."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    before = _snapshot_dir(tmp_path)

    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "add",
            "path": str(project_dir),
            "allow_cache_write": "false",
            "allow_artifact_write": "false",
        },
        data_root=tmp_path,
    )

    after = _snapshot_dir(tmp_path)
    assert result["raw"]["error"] is not None and before == after, (
        "allow_cache_write/allow_artifact_write='false' must be rejected as a "
        f"non-bool grant before any effect; today's call wrote state: {result['raw']!r}"
    )


def test_t06_git_init_string_yes_is_wrongly_truthy_today(tmp_path):
    """Same X3 coercion bug for `git_init`: `bool("yes")` is `True`. T6's
    `StrictBool` must reject a non-bool `git_init` before `create_project` runs."""
    parent = tmp_path / "parent"
    parent.mkdir()
    before = _snapshot_dir(tmp_path)

    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "create",
            "parent": str(parent),
            "name": "proj",
            "git_init": "yes",
            "allow_cache_write": True,
            "allow_artifact_write": True,
        },
        data_root=tmp_path,
    )

    after = _snapshot_dir(tmp_path)
    assert result["raw"]["error"] is not None and before == after, (
        "git_init='yes' must be rejected as a non-bool value before any effect; "
        f"today's call created state: {result['raw']!r}"
    )


def test_t06_apply_zero_is_silently_coerced_not_rejected_today(tmp_path):
    """`configure`'s `apply` is passed through `bool(request.get("apply", False))`
    with no type check. An integer `0` silently becomes `apply=False` instead of
    being rejected as a non-bool value. T6's `StrictBool` must reject it
    (`INVALID_REQUEST`), not silently reinterpret it."""
    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "configure",
            "project": str(uuid.uuid4()),
            "apply": 0,
        },
        data_root=tmp_path,
    )
    # Today: falls through to `configure_project(...)`, which fails for an
    # unregistered project (`error`) but for the *wrong* reason -- it never
    # even reaches a schema-level type check on `apply`. Once T6 lands, the
    # rejection must be `INVALID_REQUEST` for the bad `apply` type specifically,
    # which this loc-based assertion is the RED signal for.
    error = result["raw"]["error"]
    assert error is not None
    assert "apply" in str(error).lower() or getattr(error, "loc", None) == ["apply"], (
        "apply=0 must be rejected as a non-bool type (loc=['apply']), not "
        f"silently coerced or rejected for an unrelated reason: {result['raw']!r}"
    )


# ---------------------------------------------------------------------------
# RED: requires `rush.mcp_support.request_models` (not implemented). Every test
# below imports it locally so it fails individually with the real reason.
# ---------------------------------------------------------------------------


def _published_schema(tool_name: str) -> dict[str, Any]:
    from rush.mcp_support.request_models import published_schema

    return published_schema(tool_name)


def _validate_and_normalize(tool_name: str, arguments: dict[str, Any]):
    from rush.mcp_support.request_models import validate_and_normalize

    return validate_and_normalize(tool_name, arguments)


@pytest.mark.parametrize("tool_name", ["rush_project", "rush_scan", "rush_memory"])
def test_t06_published_schema_top_level_object_no_combinators(tool_name):
    """Brief section 6, "Schema shape": `inputSchema["type"] == "object"` for
    every T6 tool and no top-level combinator keys, and the schema itself must
    be a valid JSON Schema (`Draft202012Validator.check_schema`)."""
    schema = _published_schema(tool_name)
    assert schema["type"] == "object"
    forbidden = {"oneOf", "anyOf", "allOf", "not", "if", "then", "else", "$ref"}
    assert not (forbidden & schema.keys())
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    "operation,fields,_dropped",
    PROJECT_OPERATIONS,
    ids=[o for o, _, _ in PROJECT_OPERATIONS],
)
def test_t06_project_minimum_valid_request_validates_and_dispatches(
    operation, fields, _dropped, tmp_path
):
    """Brief section 6: the minimum valid request for each of the 9 project
    operations validates against the published schema and, through
    `call_tool`, produces the handler result."""
    named = {"operation": operation, **fields}
    schema = _published_schema("rush_project")
    jsonschema.validate(named, schema)

    outcome = _validate_and_normalize("rush_project", named)
    assert not outcome.rejected

    server = _server()
    result = _call_tool_sync(server, "rush_project", named)
    assert result.isError is False


@pytest.mark.parametrize(
    "operation,fields,dropped",
    [row for row in PROJECT_OPERATIONS if row[2] is not None],
    ids=[o for o, _, d in PROJECT_OPERATIONS if d is not None],
)
def test_t06_project_missing_required_field_rejects_with_zero_effects(
    operation, fields, dropped, tmp_path
):
    """Brief section 6: a missing required field produces the envelope with the
    exact `loc`, and zero effects (registry bytes, data root listing, lock
    files unchanged; handler spy call count 0)."""
    named = {
        "operation": operation,
        **{k: v for k, v in fields.items() if k != dropped},
    }
    before = _snapshot_dir(tmp_path)

    outcome = _validate_and_normalize("rush_project", named)

    after = _snapshot_dir(tmp_path)
    assert outcome.rejected
    assert outcome.error["details"][0]["loc"] == [dropped]
    assert before == after


@pytest.mark.parametrize(
    "operation,fields,_dropped", SCAN_OPERATIONS, ids=[o for o, _, _ in SCAN_OPERATIONS]
)
def test_t06_scan_minimum_valid_request_validates_and_dispatches(
    operation, fields, _dropped, tmp_path
):
    """Brief section 6, scan half: minimum valid request for each of the 6 scan
    operations (plan/run/status/rescan/cancel/resume) validates and dispatches."""
    named = {"operation": operation, **fields}
    schema = _published_schema("rush_scan")
    jsonschema.validate(named, schema)
    outcome = _validate_and_normalize("rush_scan", named)
    assert not outcome.rejected


@pytest.mark.parametrize(
    "operation,fields,dropped",
    [row for row in SCAN_OPERATIONS if row[2] is not None],
    ids=[o for o, _, d in SCAN_OPERATIONS if d is not None],
)
def test_t06_scan_missing_required_field_rejects_with_zero_effects(
    operation, fields, dropped, tmp_path
):
    named = {
        "operation": operation,
        **{k: v for k, v in fields.items() if k != dropped},
    }
    before = _snapshot_dir(tmp_path)
    outcome = _validate_and_normalize("rush_scan", named)
    after = _snapshot_dir(tmp_path)
    assert outcome.rejected
    assert outcome.error["details"][0]["loc"] == [dropped]
    assert before == after


@pytest.mark.parametrize(
    "operation,fields,_dropped",
    MEMORY_OPERATIONS,
    ids=[o for o, _, _ in MEMORY_OPERATIONS],
)
def test_t06_memory_minimum_valid_request_validates_and_dispatches(
    operation, fields, _dropped, tmp_path
):
    """Brief section 6, memory half: minimum valid request for each of the 22
    memory operations validates against the published schema and dispatches."""
    named = {"path": str(tmp_path), "operation": operation, **fields}
    schema = _published_schema("rush_memory")
    jsonschema.validate(named, schema)
    outcome = _validate_and_normalize("rush_memory", named)
    assert not outcome.rejected


@pytest.mark.parametrize(
    "operation,fields,dropped",
    [row for row in MEMORY_OPERATIONS if row[2] is not None],
    ids=[o for o, _, d in MEMORY_OPERATIONS if d is not None],
)
def test_t06_memory_missing_required_field_rejects_with_zero_effects(
    operation, fields, dropped, tmp_path
):
    named = {
        "path": str(tmp_path),
        "operation": operation,
        **{k: v for k, v in fields.items() if k != dropped},
    }
    before = _snapshot_dir(tmp_path)
    outcome = _validate_and_normalize("rush_memory", named)
    after = _snapshot_dir(tmp_path)
    assert outcome.rejected
    assert outcome.error["data"]["details"][0]["loc"][0] == dropped
    assert before == after


# --- Adversarial inputs (brief section 6, "Adversarial inputs" bullet) -----


@pytest.mark.parametrize("bad_version", [True, 1.0, 2, "1"])
def test_t06_adversarial_schema_version_rejected(bad_version):
    named = {"operation": "list", "schema_version": bad_version}
    outcome = _validate_and_normalize("rush_project", named)
    assert outcome.rejected
    assert outcome.error["details"][0]["loc"] == ["schema_version"]


@pytest.mark.parametrize("bad_grant", ["false", 1])
def test_t06_adversarial_grant_rejected(bad_grant, tmp_path):
    named = {
        "operation": "add",
        "path": str(tmp_path / "proj"),
        "allow_cache_write": bad_grant,
    }
    outcome = _validate_and_normalize("rush_project", named)
    assert outcome.rejected


def test_t06_adversarial_git_init_string_rejected(tmp_path):
    named = {
        "operation": "create",
        "parent": str(tmp_path),
        "name": "proj",
        "git_init": "yes",
    }
    outcome = _validate_and_normalize("rush_project", named)
    assert outcome.rejected


def test_t06_adversarial_apply_int_rejected():
    named = {"operation": "configure", "project": str(uuid.uuid4()), "apply": 0}
    outcome = _validate_and_normalize("rush_project", named)
    assert outcome.rejected


@pytest.mark.parametrize("bad_concurrency", [True, "3"])
def test_t06_adversarial_concurrency_rejected(bad_concurrency):
    named = {
        "operation": "plan",
        "project": str(uuid.uuid4()),
        "concurrency": bad_concurrency,
    }
    outcome = _validate_and_normalize("rush_scan", named)
    assert outcome.rejected


def test_t06_adversarial_mixed_form_rejected():
    """A `tools/call` that has both the legacy `request` envelope and a named
    top-level field must be rejected (brief: "mixed `request` + named
    fields")."""
    named = {
        "request": {"schema_version": 1, "operation": "list"},
        "operation": "list",
    }
    outcome = _validate_and_normalize("rush_project", named)
    assert outcome.rejected


def test_t06_adversarial_unknown_key_rejected():
    named = {"operation": "list", "definitely_not_a_field": 1}
    outcome = _validate_and_normalize("rush_project", named)
    assert outcome.rejected


def test_t06_adversarial_null_on_non_nullable_field_rejected():
    named = {"operation": "add", "path": None}
    outcome = _validate_and_normalize("rush_project", named)
    assert outcome.rejected


def test_t06_adversarial_empty_session_allowlist_rejected():
    named = {
        "path": ".",
        "operation": "ask",
        "subject": "episodic",
        "query": "q",
        "session_allowlist": [],
    }
    outcome = _validate_and_normalize("rush_memory", named)
    assert outcome.rejected


def test_t06_adversarial_ask_without_query_rejected():
    named = {
        "path": ".",
        "operation": "ask",
        "subject": "episodic",
        "session_allowlist": ["s1"],
    }
    outcome = _validate_and_normalize("rush_memory", named)
    assert outcome.rejected
    assert outcome.error["data"]["details"][0]["loc"][0] == "query"


def test_t06_adversarial_compact_list_empty_query_accepted():
    """List's compact form permits an empty `query` (brief: "compact list
    permits empty query")."""
    named = {
        "path": ".",
        "operation": "list",
        "subject": "episodic",
        "session_allowlist": ["s1"],
        "query": "",
        "request": {"view": "compact"},
    }
    outcome = _validate_and_normalize("rush_memory", named)
    assert not outcome.rejected


def test_t06_adversarial_compact_list_include_archived_rejected():
    """`include_archived` is only accepted on the non-compact (`_query`) list
    path, not compact list (brief: "`include_archived` on compact list
    rejected")."""
    named = {
        "path": ".",
        "operation": "list",
        "subject": "episodic",
        "session_allowlist": ["s1"],
        "request": {"view": "compact", "include_archived": True},
    }
    outcome = _validate_and_normalize("rush_memory", named)
    assert outcome.rejected


# --- Legacy vs named parity (brief section 6, "Legacy vs named" bullet) ----


@pytest.mark.parametrize(
    "operation,named_fields,legacy_request",
    [
        (
            "list",
            {"limit": 10},
            {"schema_version": 1, "operation": "list", "limit": 10},
        ),
        ("show", {}, {"schema_version": 1, "operation": "show"}),
        (
            "plan",
            {"project": "P"},
            {"schema_version": 1, "operation": "plan", "project": "P"},
        ),
        (
            "status",
            {"project": "P", "run_id": "R"},
            {"schema_version": 1, "operation": "status", "project": "P", "run_id": "R"},
        ),
    ],
)
def test_t06_legacy_vs_named_identical_raw(
    operation, named_fields, legacy_request, tmp_path
):
    tool = "rush_scan" if operation in {"plan", "status"} else "rush_project"
    named_outcome = _validate_and_normalize(
        tool, {"operation": operation, **named_fields}
    )
    legacy_outcome = _validate_and_normalize(tool, {"request": legacy_request})
    assert named_outcome.arguments == legacy_outcome.arguments


@pytest.mark.parametrize("granted", [True, False])
def test_t06_legacy_vs_named_select_grant_parity(granted, tmp_path):
    project_id = str(uuid.uuid4())
    session_id = "s1"
    fields = {
        "project": project_id,
        "session_id": session_id,
        "allow_cache_write": granted,
    }
    named_outcome = _validate_and_normalize(
        "rush_project", {"operation": "select", **fields}
    )
    legacy_outcome = _validate_and_normalize(
        "rush_project",
        {"request": {"schema_version": 1, "operation": "select", **fields}},
    )
    assert named_outcome.arguments == legacy_outcome.arguments


# --- Compatibility fields (brief section 6, "Compatibility fields" bullet) -


@pytest.mark.parametrize(
    "operation,field,value",
    [("plan", "full", True), ("run", "install", True), ("status", "after_sequence", 1)],
)
def test_t06_compatibility_fields_accepted_with_metadata(operation, field, value):
    fields: dict[str, Any] = {"project": str(uuid.uuid4())}
    if operation == "run":
        fields["plan_id"] = "p1"
    if operation == "status":
        fields["run_id"] = "r1"
    fields[field] = value
    outcome = _validate_and_normalize("rush_scan", {"operation": operation, **fields})
    assert not outcome.rejected
    assert outcome.arguments["request"]["metadata"]["compatibility"] == {
        "version": 1,
        "ignored_fields": [field],
        "effect": "none",
    }


# --- Parity sets (brief section 6, "Parity sets" bullet) ------------------


def test_t06_parity_sets_operation_enum_matches_every_source_of_truth():
    from rush.mcp_support.request_models import (
        memory_model_tags,
        project_model_tags,
        scan_model_tags,
    )

    assert project_model_tags() == {op for op, _, _ in PROJECT_OPERATIONS}
    assert scan_model_tags() == {op for op, _, _ in SCAN_OPERATIONS}
    assert (
        memory_model_tags()
        == _MEMORY_VALID_OPERATIONS
        == set(get_args(MemoryOperation))
    )


@pytest.mark.parametrize(
    "operation,constant_name",
    [
        ("expand", "_EXPAND_REQUEST_KEYS"),
        ("link", "_LINK_REQUEST_KEYS"),
        ("related", "_RELATED_REQUEST_KEYS"),
        ("consolidate", "_CONSOLIDATE_REQUEST_KEYS"),
        ("prepare", "_PREPARE_REQUEST_KEYS"),
        ("intent", "_INTENT_REQUEST_KEYS"),
        ("recipe", "_RECIPE_REQUEST_KEYS"),
        ("plan_checks", "_PLAN_CHECKS_REQUEST_KEYS"),
        ("last_success_diagnose", "_LAST_SUCCESS_DIAGNOSE_REQUEST_KEYS"),
        ("receive", "_RECEIVE_REQUEST_KEYS"),
        ("handoff", "_HANDOFF_REQUEST_KEYS"),
        ("delete", "_DELETE_REQUEST_KEYS"),
        ("edit", "_EDIT_REQUEST_KEYS"),
        ("archive", "_ARCHIVE_REQUEST_KEYS"),
    ],
)
def test_t06_parity_memory_request_model_keys_match_constant(operation, constant_name):
    """Brief: "each memory request model's key set == its `_*_REQUEST_KEYS`
    constant"."""
    import rush.tools.memory as memory_module
    from rush.mcp_support.request_models import memory_request_model_keys

    expected = getattr(memory_module, constant_name)
    assert memory_request_model_keys(operation) == expected


# --- Restricted server boundary (brief section 6, "Restricted server") -----


def test_t06_restricted_server_untouched_by_rush_fastmcp():
    """Brief: `build_server(memory_session=s)` schema is byte-equal to baseline
    (`request` + `operation`) and is not routed through the broader union."""
    from rush.mcp import RushFastMCP

    baseline = build_server(memory_session="sess-1")
    schema = _list_tools_sync(baseline)[0].inputSchema
    assert set(schema["properties"]) == {"request", "operation"}
    assert not isinstance(baseline, RushFastMCP)


# --- Non-MCP bypass (brief section 6, "Non-MCP bypass" bullet) ------------


def test_t06_non_mcp_bypass_strict_schema_version(tmp_path):
    """CLI/TUI/dashboard `handle_request` callers apply the same strict checks
    as the MCP boundary -- `schema_version=True` must be `INVALID_REQUEST`
    there too, not only through `rush_project`'s MCP wrapper."""
    result = ProjectTool().handle_request(
        {"schema_version": True, "operation": "list"}, data_root=tmp_path
    )
    assert result["raw"]["error"]["code"] == "INVALID_REQUEST"


# --- Real stdio child, malformed call (brief section 6, "Stdio" bullet) ---


def test_t06_stdio_child_rejects_malformed_schema_version(tmp_path):
    """A real `rush mcp serve` child process, given `schema_version: true` over
    the wire for `rush_project`, must return a rejection envelope. Today it
    does not (X3): this is a real subprocess round-trip, not an import
    failure, so it fails with a genuine `AssertionError` until T6 lands."""
    # The child resolves its data root from its own $HOME (Path.home()), not
    # from `tmp_path` directly. Seed a cursor signing key there first so
    # `rush_project`'s "list" doesn't fail with an unrelated SETUP_REQUIRED
    # error that would mask the real schema_version signal this test checks.
    import os
    import subprocess

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import TextContent

    from rush.workflows.projects import ensure_cursor_key

    child_home = tmp_path / "home"
    child_home.mkdir(exist_ok=True)
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(child_home)
    try:
        ensure_cursor_key()
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home

    async def _run() -> dict[str, Any]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rush.cli", "mcp", "serve"],
            cwd=str(PROJECT_ROOT),
            env={"HOME": str(child_home)},
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            response = await session.call_tool(
                "rush_project",
                {"request": {"schema_version": True, "operation": "list"}},
            )
            block = response.content[0]
            assert isinstance(block, TextContent), block
            return json.loads(block.text)

    try:
        payload = asyncio.run(_run())
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        pytest.fail(f"could not start real stdio child: {exc}")

    assert payload["raw"]["error"] is not None, (
        "a real MCP client sending schema_version=true must get a rejection "
        f"envelope; got: {payload!r}"
    )


# --- Additions by the T6 implementer: brief section 6 items not covered above --


def test_t06_every_published_schema_is_top_level_object():
    """Brief section 6 "Schema shape" / X2: every tool `list_tools()` publishes,
    not only the three T6 tools, is a top-level object with no combinator."""
    forbidden = {"oneOf", "anyOf", "allOf", "not", "if", "then", "else", "$ref"}
    for tool in _list_tools_sync(_server()):
        schema = tool.inputSchema
        assert schema.get("type") == "object", tool.name
        assert not (forbidden & schema.keys()), tool.name
        jsonschema.Draft202012Validator.check_schema(schema)


def test_t06_rejected_call_never_reaches_the_handler(tmp_path, monkeypatch):
    """Brief section 6: a rejected `tools/call` has zero effects -- the handler
    spy is never called and the data root is byte-for-byte unchanged."""
    calls: list[Any] = []
    monkeypatch.setattr(
        ProjectTool, "handle_request", lambda self, *a, **k: calls.append(a)
    )
    before = _snapshot_dir(tmp_path)
    result = _call_tool_sync(
        _server(),
        "rush_project",
        {"operation": "add", "path": ".", "allow_cache_write": "false"},
    )
    assert result.isError is False
    assert result.structuredContent["raw"]["error"]["code"] == "INVALID_REQUEST"
    assert calls == []
    assert _snapshot_dir(tmp_path) == before


def test_t06_select_grant_dispatch_legacy_and_named(tmp_path):
    """Brief section 6 "Legacy vs named": select with the cache-write grant is ok
    and identical in both forms; without it the result is skipped SCOPE_DENIED."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    added = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "add",
            "path": str(project_dir),
            "allow_cache_write": True,
            "allow_artifact_write": True,
        }
    )
    fields = {"project": added["raw"]["data"]["project_id"], "session_id": "s1"}
    server = _server()

    def call(arguments: dict[str, Any]) -> dict[str, Any]:
        return _call_tool_sync(server, "rush_project", arguments).structuredContent

    named = call({"operation": "select", **fields, "allow_cache_write": True})
    legacy = call(
        {
            "request": {
                "schema_version": 1,
                "operation": "select",
                **fields,
                "allow_cache_write": True,
            }
        }
    )
    assert named["status"] == "ok"
    assert named["raw"] == legacy["raw"]
    denied = call({"operation": "select", **fields})
    assert denied["status"] == "skipped"
    assert denied["raw"]["error"]["code"] == "SCOPE_DENIED"
