"""72-T09: truthful documentation and frozen live acceptance (G5 tests).

Test author: 72-T09 design brief (`phase72-gates/72-T09.md`, including the
pre-gate addendum), owner resolutions and `decisions.md`.

Every symbol an earlier task adds (`MemoryAccess`, schema-2 request models, the
`rush memory grant|revoke|bind-store|history|explain|preference|capsule`
leaves, ...) is reached only inside a test body, so this module always collects.
The module-level imports below are existing code and stdlib only.

Environment isolation (G10): every test that touches Rush state points `HOME`,
`USERPROFILE`, `XDG_DATA_HOME` and `LOCALAPPDATA` into `tmp_path` before any
Rush call, and every child process receives the same variables. Child
processes resolve Rush from this checkout's `src/` (`PYTHONPATH`), so a child
never imports another worktree's editable install.

Live lanes: `test_t09_live_installed_routes` is always collected; with no
`RUSH_T09_LIVE_*` variable it judges this checkout's installed `rush` console
script and writes no receipt. The other `test_t09_live_*` drivers are defined
only when such a variable is present (precedent `tests/test_tui_terminal.py`),
so no skip or deselection hides them; once any such variable is set, every
driver asserts its inputs first and fails on a missing one.

Pins derived from producer commits (`_T07_*`, `_T08_*`) are empty until the
integration step computes them with `_section_bytes` from
`git show <sha>:docs/reports/phase-72-memory-acceptance.md`; `test_t09_report_schema`
fails with that instruction while they are empty. Tests never read git history.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import dataclasses
import functools
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Self

import click
import pytest
from ruamel.yaml import YAML

from rush.memory.store import OwnerScope, TypedArtifactStore, legacy_owner_scope
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.tools.memory import MemoryTool
from rush.workflows.projects import register_project

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
THIS_FILE = "tests/test_phase72_memory_acceptance.py"
REPORT = REPO / "docs/reports/phase-72-memory-acceptance.md"
CONTRACT = REPO / "docs/phase-plans/memory-program-contract.md"
CI_YML = REPO / ".github/workflows/ci.yml"
CLI_REFERENCE = REPO / "docs/reference/cli-reference.md"

# The real host HOME, captured before any per-test isolation. Live drivers use
# it only for host CLIs (`claude`, `codex`) and to refuse a receipt directory
# under it.
_HOST_HOME = os.environ.get("HOME", "")

SUBJECT = "architectural_decision"
SEVEN_SUBJECTS = (
    "active_context",
    "episodic",
    "preference",
    "failure",
    "architectural_decision",
    "domain_knowledge",
    "skill_pattern",
)
OVERLAY_SOURCE = "personal-preferences"
# The grant a project carries for the integrated scenario: every compound
# operation the scenario exercises (read, expand, write/edit/record, history).
PROJECT_OPS = ("ask", "list", "expand", "write", "history")
OVERLAY_OPS = ("list", "overlay_read", "write")

# --- R2: report grammar -----------------------------------------------------

REPORT_H2 = (
    "## Source hash",
    "## Installed artifact hash",
    "## Commands",
    "## Results",
    "## Platform and client versions",
    "## Grants",
    "## Lanes",
    "## Failures and blockers",
    "## Plan-vs-code check",
    "## 72-T07 walkthrough",
    "## 72-T08 hybrid evaluation",
)
T07_HEADING = "## 72-T07 walkthrough"
T08_HEADING = "## 72-T08 hybrid evaluation"
LANE_HEADER = "| lane | implementation_gate | live_acceptance | blocker | evidence |"
LANES = (
    "installed-artifact-cli-mcp",
    "dashboard-memory-api",
    "pty-terminal",
    "personal-overlay-two-projects",
    "two-agent-same-project",
    "e06-e25-rejection-reversal",
    "pas-import",
    "portable-route-release",
    "native-linux-ci",
    "native-windows-ci",
    "native-macos",
    "hybrid-evaluation",
    "r5b-frame-receipts",
    "phase70-t28d-g5-g8",
    "phase71-p07",
)
R5B_BLOCKER = "Phase 75 75-T01 frame columns not landed"
PORTABLE_BLOCKER = (
    "Phase 73 73-T09 final release (75-T01 receipts, 75-T03/T04 budget and "
    "recovery) not landed"
)
SOURCE_HASH_PATTERNS = (
    r"freeze_commit: [0-9a-f]{40}",
    r"tree\.src: [0-9a-f]{40}",
    r"tree\.tests: [0-9a-f]{40}",
    r"tree\.scripts: [0-9a-f]{40}",
    r"tree\.\.github: [0-9a-f]{40}",
    r"phase70_ref: phase/70-agent-adoption-and-usability [0-9a-f]{7,40}",
    r"phase70_parity: empty",
)
PLATFORM_PATTERNS = (
    r"python: 3\.12\.\d+",
    r"rush: \S+",
    r"os: .+",
    r"claude: .+",
    r"codex: .+",
    r"pyinstaller: .+",
    r"gh: .+",
)
REDACTION_PATTERNS = (
    (r"\b[0-9a-f]{32}\b", "32-hex token"),
    (
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "uuid",
    ),
    (r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])", "43-char token"),
    (r"/Users/[^/\s]+", "macOS home path"),
    (r"/home/[^/\s]+", "linux home path"),
    (r"\bsk-[A-Za-z0-9]{16,}", "api key"),
    (r"Bearer\s", "bearer credential"),
)

# Producer pins (empty until integration derives them; see the module docstring).
_T07_COMMIT = ""
_T07_WALKTHROUGH_SHA256 = ""
_T08_COMMIT = ""
_T08_EVALUATION_SHA256 = ""

# --- R3: leaf set -----------------------------------------------------------

REQUIRED_LEAVES = (
    ("archive",),
    ("ask",),
    ("consolidate",),
    ("delete",),
    ("edit",),
    ("expand",),
    ("handoff",),
    ("intent",),
    ("last-success-diagnose",),
    ("link",),
    ("list",),
    ("maintain",),
    ("plan-checks",),
    ("prepare",),
    ("promote",),
    ("recall",),
    ("receive",),
    ("recipe",),
    ("related",),
    ("resume",),
    ("verify-attempt",),
    ("write",),
    ("preference",),
    ("history",),
    ("explain",),
    ("capsule", "preview-export"),
    ("capsule", "export"),
    ("capsule", "preview-import"),
    ("capsule", "import"),
    ("capsule", "bridge"),
    ("capsule", "mapping", "create"),
    ("capsule", "mapping", "revoke"),
    ("grant",),
    ("revoke",),
    ("bind-store",),
)

# --- R4: truth labels -------------------------------------------------------

C01_SENTENCE = (
    "There is no claim of isolation against mutually hostile processes running "
    "as the same OS user."
)
C05_SENTENCE = (
    "Rush counts memory tokens using the request's declared encoding, defaulting "
    "to `cl100k_base`. Counts for another host tokenizer are estimates. An "
    "admitted delivered frame obeys its UTF-8 `max_bytes`; if that tokenizer "
    "consumes at least one byte per token, its token count cannot exceed those "
    "delivered bytes. No measured cross-tokenizer margin is claimed."
)
GUIDES = (
    "docs/user-guide/working-with-ai-agents.md",
    "docs/user-guide/interactive-tui.md",
)
CLAIM_DOCS = (
    *GUIDES,
    "docs/architecture/rush-epistemic-memory-and-agent-substrate.md",
    "docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md",
    "docs/phase-plans/MC13.md",
)
CLAIM_HEADING = "## Memory claim status"
CLAIM_HEADER = "| Claim | Status | Revision | Route | Evidence |"
CLAIM_STATUSES = ("proposed", "implemented", "integrated", "evaluated", "live-checked")

# Phase 63 / MC13 are historical: their original bytes stay and the claim table
# is appended (RB-4). (length, sha256) of the bytes at the T09 test-author HEAD.
ORIGINAL_PREFIX = {
    "docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md": (
        85063,
        "7eab4b7525eb8c999445c30345907422060410acde0f77bf671b0f51b11b1263",
    ),
    "docs/phase-plans/MC13.md": (
        20898,
        "8c2706455d197203a8f20a94989249591f1ee3c8fddb3ac8c7d5358cd6af5b1c",
    ),
}

# The claim-to-source-anchor inventory (addendum "R2-R4"). Every anchor must
# appear in the Claim cell of a row of that doc's table. A `source` regex is
# checked against the doc's original text (`None` for routes the guides publish
# after T09); a `leaf` is a `rush memory` path that must exist as a Click leaf.
CLAIM_ANCHORS: dict[str, tuple[tuple[str, str | None, tuple[str, ...] | None], ...]] = {
    "docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md": tuple(
        (f"R{n:02d}", rf"^\| R{n:02d} \|", None) for n in range(1, 21)
    )
    + (
        ("contract:6.1", r"^### 6\.1 Versioned authority and migration", None),
        ("contract:6.2", r"^### 6\.2 Retrieval and expansion", None),
        ("contract:6.3", r"^### 6\.3 Relations and consolidation", None),
        ("contract:6.4", r"^### 6\.4 Observed execution, trust and agent choice", None),
        (
            "contract:6.5",
            r"^### 6\.5 Repair, intent, recipe, checks and diagnosis",
            None,
        ),
        (
            "contract:6.6",
            r"^### 6\.6 Delta handoff and restricted receiving route",
            None,
        ),
        (
            "contract:6.7",
            r"^### 6\.7 Optional hybrid retrieval and measurements",
            None,
        ),
    ),
    "docs/architecture/rush-epistemic-memory-and-agent-substrate.md": (
        ("primitive:epistemic-classes", r"PROVEN_EVIDENCE", None),
        ("primitive:grounding-hash", r"\*\*Grounding Hash\*\*", None),
        ("primitive:invalidation-watchers", r"\*\*Invalidation Watchers\*\*", None),
        ("primitive:scope-levels", r"\*\*Scope\*\*", None),
        ("lifecycle:context-hydration", r"^### Step 1: Just-in-Time", None),
        ("lifecycle:automatic-invalidation", r"^### Step 2: Automatic", None),
        ("lifecycle:negative-invariants", r"^### Step 3: Learning from Real", None),
        ("lifecycle:structured-handoffs", r"^### Step 4: Structured Task", None),
        ("tool:rush_memory_hydrate", r"`rush_memory_hydrate`", None),
        ("tool:rush_memory_record_intent", r"`rush_memory_record_intent`", None),
        ("tool:rush_memory_record_proof", r"`rush_memory_record_proof`", None),
        ("tool:rush_memory_invalidate", r"`rush_memory_invalidate`", None),
        ("tool:rush_task_capsule", r"`rush_task_capsule`", None),
        (
            "recovery:bounded-recovery-references",
            r"^## Bounded recovery references",
            None,
        ),
    ),
    "docs/phase-plans/MC13.md": (
        ("mc13:dataset-adapters", r"^## Dataset adapters", None),
        ("mc13:real-agent-episodes", r"^## Real agent episodes", None),
        ("mc13:cli-wiring", r"^## CLI wiring", None),
        ("mc13:mc13.4-fix", r"^### MC13\.4 fix", None),
        ("mc13:fixture", r"^## Fixture", None),
        ("mc13:test-evidence", r"^## Test evidence", None),
        ("mc13:real-local-run", r"^## Real local run", None),
        ("mc13:named-blockers", r"^## Named blockers", None),
        ("mc13:verification", r"^## Verification", None),
    ),
    "docs/user-guide/working-with-ai-agents.md": (
        ("mcp:rush_memory-scope", None, None),
        ("mcp:rush_memory-operations", None, None),
        ("two-agent:exact-revision-handoff", None, None),
        ("recovery:denied-stale-revoked", None, None),
        ("cli:grant", None, ("grant",)),
        ("cli:revoke", None, ("revoke",)),
        ("cli:bind-store", None, ("bind-store",)),
        ("cli:list", None, ("list",)),
        ("cli:expand", None, ("expand",)),
        ("cli:edit", None, ("edit",)),
        ("cli:history", None, ("history",)),
        ("cli:explain", None, ("explain",)),
        ("cli:preference", None, ("preference",)),
        ("cli:capsule-preview-import", None, ("capsule", "preview-import")),
        ("cli:capsule-import", None, ("capsule", "import")),
        ("cli:capsule-preview-export", None, ("capsule", "preview-export")),
        ("cli:capsule-export", None, ("capsule", "export")),
    ),
    "docs/user-guide/interactive-tui.md": (
        ("tui:search", None, None),
        ("tui:filter", None, None),
        ("tui:subject-cycle", None, None),
        ("tui:paging", None, None),
        ("tui:expand-exact-version", None, None),
        ("tui:history", None, None),
        ("tui:explain", None, None),
        ("tui:correct", None, None),
        ("tui:import-review", None, None),
        ("tui:representation-toggle", None, None),
        ("tui:denied-state", None, None),
        ("tui:revoked-state", None, None),
        ("tui:expired-state", None, None),
        ("tui:conflict-state", None, None),
    ),
}

# --- R8: route and dimension vocabulary ------------------------------------

ROUTE_KEYS = [
    "ask",
    "recall",
    "list",
    "expand",
    "related",
    "link",
    "consolidate",
    "write",
    "promote",
    "edit",
    "archive",
    "delete",
    "mutation_view",
    "maintain",
    "verify_attempt",
    "prepare",
    "resume",
    "intent",
    "recipe",
    "plan_checks",
    "last_success_diagnose",
    "handoff",
    "receive",
    "overview",
    "history",
    "explain",
    "preference",
    "capsule",
    "import",
    "cli_memory",
    "cli_other_readers",
    "mcp_bridge",
    "dashboard",
    "dashboard_readers",
    "dashboard_admission_reconcile",
    "tui",
    "project_registry_readers",
    "scan_handoff",
    "session_memory",
    "flight_recorder",
    "skills_generator",
    "cache_gate",
    "telemetry_readers",
    "review_citations",
    "status",
    "continuity_tool",
    "checkpoint_journal",
    "continuity_package",
    "patch_memory",
    "experience",
    "intent_module",
    "recipes",
    "maintenance_expiry",
    "migration",
    "preferences",
    "retrieval_helper",
    "invariant_graph",
    "hook_signatures",
    "internal_d4",
]
DIMENSIONS = {
    "access": ("policy", "legacy_allowlist", "overlay"),
    "policy_state": ("missing_no_marker", "missing_marker", "ok", "invalid"),
    "mode": ("ordinary", "inspect", "historical"),
    "representation": ("base64", "utf8"),
    "retrieval": ("lexical", "hybrid"),
    "store": ("present", "absent", "old_schema"),
    "apply": ("preview", "apply"),
    "cache_write": ("on", "off"),
    "grant_ops": ("exact", "missing_one"),
    "row_state": ("active", "archived", "expired", "rejected", "pending", "tampered"),
    "ack": ("ack", "no_ack"),
    "capability_ids": ("selected", "unselected"),
}
TRANSPORT_PREFIXES = ("inproc", "mcp", "bridge", "cli", "dashboard", "tui", "internal")
MATRIX_NODE_IDS = (
    "tests/test_phase72_memory_correctness.py::test_t01_fix_policy_mode_matrix",
    "tests/test_phase72_memory_correctness.py::test_t02_route_mode_matrix",
    "tests/test_phase72_memory_correctness.py::test_t03_route_mode_matrix",
    "tests/test_phase72_memory_correctness.py::test_t04_route_mode_matrix",
    "tests/test_phase72_memory_correctness.py::test_consent_route_mode_matrix",
    "tests/test_phase72_preferences.py::test_t05_route_mode_matrix",
    "tests/test_phase72_memory_public.py::test_t06_route_mode_matrix",
    "tests/test_phase72_memory_ui.py::test_t07_route_mode_matrix",
    "tests/test_phase72_memory_hybrid.py::test_t08_route_mode_matrix",
    "tests/test_memory_capsule.py::test_codec_route_mode_matrix",
)

# --- R10: published operation docs -----------------------------------------

OPERATION_DOCS = (
    "docs/MCP_REFERENCE.md",
    "docs/MCP.md",
    "docs/reference/mcp-tool-reference.md",
    "docs/CLI_REFERENCE.md",
    "docs/TOOL_CATALOG.md",
)
FORBIDDEN_DOC_STRINGS = (
    "require a non-empty `session_allowlist`",
    "require `subject`, `query`, and a non-empty `session_allowlist`",
    "at least one `--session SOURCE`",
)
SKILL_COPIES = (
    "src/rush/integrations/agent_assets/skills/rush/SKILL.md",
    "src/rush/integrations/agent_assets/claude/skills/rush/SKILL.md",
    "src/rush/integrations/agent_assets/codex/skills/rush/SKILL.md",
)

# --- native CI --------------------------------------------------------------

LIVE_LINUX_NODES = (
    "test_t09_live_installed_routes",
    "test_t09_live_pas_import",
    "test_t09_live_pty_walkthrough",
)
LIVE_WINDOWS_NODES = (
    "test_t09_live_installed_routes",
    "test_t09_live_pas_import",
    "test_t09_live_windows_console",
)
# windows_only functions the producer tasks own (T01 brief B1, T06 R15,
# BOOTSTRAP-CONSENT A7.4/A7.5); each needs at least one literal-id node.
PRODUCER_WINDOWS_FUNCTIONS = (
    (
        "tests/test_phase72_memory_correctness.py",
        "test_t01_policy_lock_windows_timeout_native",
        "72-T01",
    ),
    (
        "tests/test_phase72_memory_correctness.py",
        "test_t01_source_swap_between_validation_and_open",
        "72-T01",
    ),
    (
        "tests/test_phase72_memory_correctness.py",
        "test_t01_store_binding_key_windows_native",
        "72-T01",
    ),
    (
        "tests/test_phase72_memory_correctness.py",
        "test_next_action_preserves_owner_and_grant_operations",
        "73-T02/BOOTSTRAP-CONSENT",
    ),
    (
        "tests/test_memory_authorization.py",
        "test_os_principal_windows_sid",
        "72-T01",
    ),
)
T06_WINDOWS_IMPORT_IDS = (
    "windows_junction_rush",
    *(f"windows_rename_rush_injection_{n}" for n in range(1, 5)),
    *(f"windows_rename_root_injection_{n}" for n in range(1, 5)),
)
# D11: 22 operations at fe1ffb0, +preference (72-T05), +history and +explain
# (72-T06), +capsule (CODEC) = 26.
REQUIRED_OPERATIONS = (
    "archive",
    "ask",
    "consolidate",
    "delete",
    "edit",
    "expand",
    "handoff",
    "intent",
    "last_success_diagnose",
    "link",
    "list",
    "maintain",
    "plan_checks",
    "prepare",
    "promote",
    "recall",
    "receive",
    "recipe",
    "related",
    "resume",
    "verify_attempt",
    "write",
    "preference",
    "history",
    "explain",
    "capsule",
)


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------


def _sha(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm(text: str) -> str:
    """Whitespace-collapsed text, so a sentence may wrap across lines."""
    return re.sub(r"\s+", " ", text).strip()


def _read(rel: str) -> str:
    path = REPO / rel
    assert path.is_file(), f"{rel} does not exist"
    return path.read_text(encoding="utf-8")


def _tree_digest(root: Path) -> list[tuple[str, str]]:
    """Sorted (relative path, sha256) of every file under `root`."""
    if not root.exists():
        return []
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rows.append((path.relative_to(root).as_posix(), _sha_file(path)))
    return rows


def _child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for a Rush child: the isolated HOME/XDG/LOCALAPPDATA already in
    `os.environ`, this checkout's `src/` first on `PYTHONPATH`."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("NO_COLOR", None)
    if extra:
        env.update(extra)
    return env


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """G10: HOME, USERPROFILE, XDG_DATA_HOME and LOCALAPPDATA inside `tmp_path`.
    Returns the resulting Rush data root."""
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    local = tmp_path / "la"
    for path in (home, xdg, local):
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    data_root = default_data_root()
    assert tmp_path in data_root.parents, data_root
    return data_root


def _rush_bin() -> str:
    candidate = Path(sys.executable).with_name("rush")
    if os.name == "nt":
        candidate = Path(sys.executable).with_name("rush.exe")
    assert candidate.exists(), "expected a sibling rush console script"
    return str(candidate)


def _register(path: Path, data_root: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    register_project(path, data_root=data_root)
    return path.resolve()


def _policy_revision(auth: Any, data_root: Path) -> int:
    return int(auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0)


def _grant(
    root: Path,
    owner: OwnerScope,
    data_root: Path,
    *,
    sources: Sequence[str],
    ops: Sequence[str],
) -> dict[str, Any]:
    from rush.memory import authorization as auth

    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=_policy_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )


def _revoke(grant: Mapping[str, Any], data_root: Path) -> None:
    from rush.memory import authorization as auth

    auth.revoke_memory_scope(
        grant_id=grant["grant_id"],
        expected_policy_revision=_policy_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )


def _store_version(db: Path, artifact_id: str) -> int:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        row = conn.execute(
            "SELECT artifact_version FROM memory_artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
    assert row is not None, artifact_id
    return int(row[0])


def _count_ids(db: Path, artifact_id: str) -> int:
    if not db.is_file():
        return 0
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM memory_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()[0]
        )


def _raw(result: Any) -> dict[str, Any]:
    """The ToolResult `raw` mapping; a result without one (an operation or shape
    an earlier task has not added yet) becomes a `NO_RAW` mapping that carries
    the tool's own summary, so a failing assertion shows what came back."""
    raw = result.get("raw")
    if isinstance(raw, dict):
        return raw
    return {
        "code": "NO_RAW",
        "data": {"status": result.get("status"), "summary": result.get("summary")},
    }


def _refs(items: Sequence[Mapping[str, Any]]) -> list[tuple[str, int]]:
    return [
        (item["reference"]["artifact_id"], item["reference"]["artifact_version"])
        for item in items
    ]


def _strip_ansi(text: str) -> str:
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-9;?<>=!]*[ -/]*[@-~]", "", text)
    return re.sub(r"\x1b[()#][A-Za-z0-9]|\x1b[=>78cDEHMNOZ]", "", text)


def _text_input(name: str, value: object) -> str:
    """A path-like or enum-like input is text the OS can encode; anything else
    fails with a named assertion before any filesystem or subprocess effect."""
    assert isinstance(value, str), f"{name} must be text, got {type(value).__name__}"
    assert "\0" not in value, f"{name} contains a NUL character"
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AssertionError(f"{name} is not valid UTF-8 text") from None
    return value


def _choice(name: str, value: object, allowed: Sequence[str]) -> str:
    """Membership that never hashes or compares an untyped value."""
    text = _text_input(name, value)
    assert text in allowed, f"unknown {name} {text!r}"
    return text


def _loads_json(text: str, where: str) -> Any:
    """`json.loads` whose parse and nesting failures name `where`."""
    try:
        return json.loads(text)
    except RecursionError:
        raise AssertionError(f"{where}: JSON nested too deeply") from None
    except ValueError as exc:
        raise AssertionError(f"{where}: not valid JSON ({exc})") from None


def _parse_source(rel: str, text: str) -> ast.Module:
    """`ast.parse` whose failures name the file."""
    try:
        return ast.parse(text)
    except (SyntaxError, RecursionError, MemoryError, ValueError) as exc:
        raise AssertionError(f"{rel}: cannot parse ({type(exc).__name__})") from None


def _run_cleanups(exc: Sequence[object], *steps: Callable[[], None]) -> None:
    """Run every owned cleanup step. A cleanup failure never hides the failure
    already propagating: one `AssertionError` names both."""
    primary = exc[1] if len(exc) == 3 and isinstance(exc[1], BaseException) else None
    failed: list[str] = []
    for step in steps:
        try:
            step()
        except Exception as error:  # noqa: BLE001 - every owned step must run
            failed.append(f"{step.__name__}: {type(error).__name__}: {error}")
    if failed:
        detail = "; ".join(failed)
        if primary is None:
            raise AssertionError(f"cleanup failed ({detail})")
        raise AssertionError(
            f"cleanup failed ({detail}) while handling "
            f"{type(primary).__name__}: {primary}"
        ) from primary


# ---------------------------------------------------------------------------
# transports: in-process, CLI subprocess, stdio MCP subprocess, dashboard HTTP,
# TUI in-process
# ---------------------------------------------------------------------------


def _run_cli(
    exe: Sequence[str],
    cwd: Path,
    args: Sequence[str],
    env: Mapping[str, str],
    *,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Run `<exe> memory <args>` and return the parsed `--json` ToolResult."""
    proc = subprocess.run(
        [*exe, "memory", *args],
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise AssertionError(
            f"rush memory {' '.join(args)} printed non-JSON (rc={proc.returncode})\n"
            f"stdout={proc.stdout[:2000]!r}\nstderr={proc.stderr[:2000]!r}"
        ) from exc
    assert isinstance(payload, dict), payload
    return payload


class _McpSession:
    """One stdio `rush mcp serve` child driven with hand-framed JSON-RPC."""

    def __init__(
        self,
        exe: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        extra_args: Sequence[str] = (),
    ) -> None:
        self._argv = [*exe, "mcp", "serve", *extra_args]
        self._cwd = cwd
        self._env = dict(env)
        self._next_id = 0
        self._lines: list[str] = []
        self._cond = threading.Condition()
        self._proc: subprocess.Popen[str] | None = None
        self._stderr_path = cwd.parent / f".t09-mcp-{uuid.uuid4().hex[:8]}.stderr"

    def __enter__(self) -> Self:
        self._stderr_file = open(self._stderr_path, "w", encoding="utf-8")
        self._proc = subprocess.Popen(
            self._argv,
            cwd=self._cwd,
            env=self._env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()
        from mcp import types

        params = types.InitializeRequestParams(
            protocolVersion=types.LATEST_PROTOCOL_VERSION,
            capabilities=types.ClientCapabilities(),
            clientInfo=types.Implementation(name="t09-acceptance", version="0"),
        )
        response = self._request(
            "initialize",
            json.loads(params.model_dump_json(by_alias=True, exclude_none=True)),
        )
        assert "result" in response, response
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *exc: object) -> None:
        proc = self._proc
        assert proc is not None

        def close_stdin() -> None:
            with contextlib.suppress(OSError, ValueError):
                assert proc.stdin is not None
                proc.stdin.close()

        def stop_child() -> None:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

        def close_stderr() -> None:
            self._stderr_file.close()

        def remove_stderr() -> None:
            with contextlib.suppress(OSError):
                self._stderr_path.unlink()

        _run_cleanups(exc, close_stdin, stop_child, close_stderr, remove_stderr)

    def _pump(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            with self._cond:
                self._lines.append(line)
                self._cond.notify_all()
        with self._cond:
            self._lines.append("")
            self._cond.notify_all()

    def _send(self, message: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _recv(self, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._lines:
                remaining = deadline - time.monotonic()
                assert remaining > 0, "stdio MCP server did not answer in time"
                self._cond.wait(remaining)
            line = self._lines.pop(0)
        assert line.strip(), "stdio MCP server closed stdout"
        message = json.loads(line)
        assert isinstance(message, dict), message
        return message

    def _request(
        self, method: str, params: dict[str, Any], timeout: float = 120.0
    ) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        while True:
            message = self._recv(timeout)
            if message.get("id") == request_id:
                return message

    def list_tools(self) -> list[dict[str, Any]]:
        response = self._request("tools/list", {})
        return list(response["result"]["tools"])

    def call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """`tools/call rush_memory`; returns the parsed ToolResult payload."""
        response = self._request(
            "tools/call", {"name": "rush_memory", "arguments": arguments}
        )
        assert "result" in response, response
        text = response["result"]["content"][0]["text"]
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise AssertionError(f"MCP result is not JSON: {text[:2000]!r}") from exc
        assert isinstance(payload, dict), payload
        return payload


def _http(url: str, *, headers: Mapping[str, str], body: bytes | None, method: str):
    request = urllib.request.Request(
        url, data=body, headers=dict(headers), method=method
    )
    try:
        return urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as exc:
        return exc


class _Dashboard:
    """The dashboard memory API over real HTTP: a source server started
    in-process, or an installed `<artifact> dashboard --no-open --json` child."""

    def __init__(
        self,
        project_id: str,
        root: Path,
        *,
        exe: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.project_id = project_id
        self._root = root
        self._exe = list(exe) if exe else None
        self._env = dict(env) if env else _child_env()
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[str] | None = None
        self.base_url = ""
        self._cookie = ""
        self._csrf = ""

    def __enter__(self) -> Self:
        if self._exe is None:
            self._start_source()
        else:
            self._start_installed()
        response = _http(
            f"{self.base_url}/api/session",
            headers={"Authorization": f"Bearer {self._token}"},
            body=b"",
            method="POST",
        )
        assert response.status == 200, response.status
        payload = json.loads(response.read())
        self._cookie = response.headers.get("Set-Cookie").split(";")[0]
        self._csrf = payload["csrf_token"]
        return self

    def _start_source(self) -> None:
        from rush.dashboard.server import create_dashboard_server

        snapshot = {
            "schema_version": 1,
            "project_id": self.project_id,
            "source_identity": str(self._root),
            "root": str(self._root),
            "files": [],
            "findings": [],
            "memories": [],
            "agents": [],
        }
        server, ctx, token = create_dashboard_server({self.project_id: snapshot})
        self._server = server
        self._token = token
        self.base_url = ctx.launch_origin
        self._thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self._thread.start()

    def _start_installed(self) -> None:
        assert self._exe is not None
        self._proc = subprocess.Popen(
            [*self._exe, "dashboard", str(self._root), "--no-open", "--json"],
            cwd=self._root,
            env=self._env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        ready = json.loads(line)
        assert ready.get("ready") is True, ready
        url, _, token = str(ready["url"]).partition("#token=")
        assert token, ready
        self.base_url = url.rstrip("/")
        self._token = token

    def __exit__(self, *exc: object) -> None:
        def stop_server() -> None:
            if self._server is not None:
                self._server.shutdown()
                self._server.server_close()
                if self._thread is not None:
                    self._thread.join(timeout=10)

        def stop_child() -> None:
            if self._proc is not None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=10)

        _run_cleanups(exc, stop_server, stop_child)

    def action(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        grants: Mapping[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body = json.dumps(
            {
                "schema_version": 1,
                "operation": operation,
                "arguments": dict(arguments),
                "grants": dict(grants or {}),
                "expected": {},
                "request_id": str(uuid.uuid4()),
            }
        ).encode("utf-8")
        response = _http(
            f"{self.base_url}/api/projects/{self.project_id}/actions",
            headers={
                "Cookie": self._cookie,
                "X-Rush-CSRF": self._csrf,
                "Origin": self.base_url,
                "Content-Type": "application/json",
            },
            body=body,
            method="POST",
        )
        return response.status, json.loads(response.read())


def _dash_result(body: Mapping[str, Any]) -> dict[str, Any]:
    """The ToolResult inside a dashboard action envelope
    (`{schema_version, request_id, project_id, sequence, data}`)."""
    data = body.get("data")
    return dict(data) if isinstance(data, dict) else dict(body)


def _ui_state(body: Mapping[str, Any]) -> dict[str, Any] | None:
    """The `ui_state` a dashboard body carries (envelope, ToolResult, raw or data)."""
    result = _dash_result(body)
    for holder in (
        body,
        result,
        result.get("raw"),
        (result.get("raw") or {}).get("data"),
    ):
        if isinstance(holder, dict) and isinstance(holder.get("ui_state"), dict):
            return holder["ui_state"]
    return None


def _tui_items(root: Path, subject: str) -> tuple[Any, list[dict[str, Any]]]:
    """Open the TUI Memory section on `root`, cycle to `subject`, return the
    state and the rows it read."""
    from rush.tui import (
        ProjectState,
        TuiState,
        _dispatch_key,
        _pump,
        default_scan_actions,
    )

    state = TuiState(projects=[ProjectState(name=root.name, root=root, results=[])])
    actions = default_scan_actions()

    def key(name: str) -> None:
        _dispatch_key(state, name, actions)
        deadline = time.monotonic() + 10
        _pump(state, actions)
        while state.memory_request is not None:
            assert time.monotonic() < deadline, "TUI memory request still in flight"
            time.sleep(0.005)
            _pump(state, actions)

    key("M")
    for _ in range(len(SEVEN_SUBJECTS) + 1):
        if state.memory_subject == subject:
            break
        key("S")
    assert state.memory_subject == subject, state.memory_subject
    return state, list(state.memory_items)


_DASHBOARD_ACTIONS = {
    "expand": "memory_expand",
    "ask": "memory_query",
    "recall": "memory_query",
    "list": "memory_query",
}


@dataclasses.dataclass
class _Ctx:
    """The transports of one scenario: source (all five) or installed (CLI, MCP,
    dashboard)."""

    tmp: Path
    exe: list[str]
    env: dict[str, str]
    mcp: _McpSession | None = None
    dash: _Dashboard | None = None
    installed: bool = False
    _n: int = 0
    current: str = ""
    trace: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    @property
    def transports(self) -> tuple[str, ...]:
        if self.installed:
            return ("cli", "mcp", "dashboard")
        return ("inproc", "cli", "mcp", "dashboard", "tui")

    def _input_file(self, request: Mapping[str, Any]) -> str:
        self._n += 1
        path = self.tmp / f"request-{self._n}.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        return str(path)

    def call(
        self,
        transport: str,
        root: Path,
        operation: str,
        request: Mapping[str, Any],
        *,
        cache_write: bool = False,
        agent: str = "agent-a",
    ) -> dict[str, Any]:
        """One schema-2 call on `transport`; the ToolResult `raw` mapping.
        Every call is recorded in `trace` (step label, transport, request and
        result digests, result code) for the machine-generated receipts."""
        raw = self._call(
            transport, root, operation, request, cache_write=cache_write, agent=agent
        )
        self.trace.append(
            {
                "step": self.current,
                "transport": transport,
                "operation": operation,
                "request_sha256": _sha(json.dumps(dict(request), sort_keys=True)),
                "code": raw.get("code"),
                "result_sha256": _sha(json.dumps(raw, sort_keys=True, default=str)),
            }
        )
        return raw

    def _call(
        self,
        transport: str,
        root: Path,
        operation: str,
        request: Mapping[str, Any],
        *,
        cache_write: bool = False,
        agent: str = "agent-a",
    ) -> dict[str, Any]:
        _choice("transport", transport, ("inproc", "cli", "mcp", "dashboard"))
        _text_input("operation", operation)
        if transport == "inproc":
            result = MemoryTool().run(
                root,
                operation=operation,  # type: ignore[arg-type]
                request=dict(request),
                permissions=ExecutionPermissions(cache_write=cache_write),
                agent_id=agent,
            )
            return _raw(result)
        if transport == "cli":
            args = [operation.replace("_", "-"), "--input", self._input_file(request)]
            args.append("--json")
            if cache_write:
                args.append("--allow-cache-write")
            return _raw(_run_cli(self.exe, root, args, self.env))
        if transport == "mcp":
            assert self.mcp is not None
            arguments: dict[str, Any] = {
                "path": str(root),
                "operation": operation,
                "request": dict(request),
                "agent_id": agent,
            }
            if cache_write:
                arguments["allow_cache_write"] = True
            return _raw(self.mcp.call(arguments))
        if transport == "dashboard":
            assert self.dash is not None
            action = _DASHBOARD_ACTIONS.get(operation)
            assert action, f"the dashboard has no action for operation {operation!r}"
            arguments = dict(request)
            if action == "memory_query":
                arguments["mode"] = operation
            _status, body = self.dash.action(
                action,
                arguments,
                grants={"cache_write": cache_write} if cache_write else None,
            )
            raw = _dash_result(body).get("raw")
            assert isinstance(raw, dict), body
            return raw
        raise AssertionError(f"unknown transport {transport}")

    def list_items(
        self, transport: str, root: Path, subject: str = SUBJECT
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """List `subject` on `transport`; returns (raw, items)."""
        _text_input("transport", transport)
        _choice("subject", subject, SEVEN_SUBJECTS)
        if transport == "tui":
            state, items = _tui_items(root, subject)
            return {"code": "OK", "state": state}, items
        if transport == "cli":
            owner = f"project:{root}"
            raw = _raw(
                _run_cli(
                    self.exe,
                    root,
                    ["list", "--subject", subject, "--owner", owner, "--json"],
                    self.env,
                )
            )
        else:
            raw = self.call(
                transport,
                root,
                "list",
                {"schema_version": 2, "subjects": [subject], "query": ""},
            )
        return raw, list(raw.get("items") or [])

    def refs(
        self, transport: str, root: Path, subject: str = SUBJECT
    ) -> list[tuple[str, int]]:
        raw, items = self.list_items(transport, root, subject)
        assert raw.get("code") == "OK", (transport, raw)
        return _refs(items)

    def expand(
        self,
        transport: str,
        root: Path,
        artifact_id: str,
        version: int,
        *,
        representation: str = "utf8",
    ) -> dict[str, Any]:
        _choice("representation", representation, ("base64", "utf8"))
        return self.call(
            transport,
            root,
            "expand",
            {
                "schema_version": 2,
                "artifact_id": artifact_id,
                "artifact_version": version,
                "representation": representation,
            },
        )


# ---------------------------------------------------------------------------
# the integrated world (D20: registered projects, consented grants)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _World:
    tmp: Path
    data_root: Path
    p1: Path
    p2: Path
    p3: Path
    p1_id: str
    p2_id: str
    overlay: OwnerScope
    grants: dict[str, dict[str, Any]]

    @property
    def overlay_db(self) -> Path:
        return self.data_root / "user" / ".rush" / "memory.db"


def _world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _World:
    """P1 and P2 registered with consented grants (project owner and personal
    overlay owner); P3 an unregistered directory with no `.rush`."""
    from rush.memory import authorization as auth

    data_root = _isolate(tmp_path, monkeypatch)
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    p3 = tmp_path / "p3"
    p3.mkdir()
    ids = {}
    for name, path in (("p1", p1), ("p2", p2)):
        path.mkdir()
        ids[name] = register_project(path, data_root=data_root).project_id
    p1, p2, p3 = p1.resolve(), p2.resolve(), p3.resolve()
    overlay = auth.user_overlay_owner_scope(data_root=data_root)
    grants = {
        "p1": _grant(
            p1,
            legacy_owner_scope(p1),
            data_root,
            sources=("s1",),
            ops=PROJECT_OPS,
        ),
        "p2": _grant(
            p2,
            legacy_owner_scope(p2),
            data_root,
            sources=("s1", "capsule:import"),
            ops=PROJECT_OPS,
        ),
        "p1_overlay": _grant(
            p1, overlay, data_root, sources=(OVERLAY_SOURCE,), ops=OVERLAY_OPS
        ),
        "p2_overlay": _grant(
            p2, overlay, data_root, sources=(OVERLAY_SOURCE,), ops=OVERLAY_OPS
        ),
    }
    return _World(
        tmp=tmp_path,
        data_root=data_root,
        p1=p1,
        p2=p2,
        p3=p3,
        p1_id=ids["p1"],
        p2_id=ids["p2"],
        overlay=overlay,
        grants=grants,
    )


@contextlib.contextmanager
def _source_ctx(world: _World) -> Iterator[_Ctx]:
    """All five transports against this checkout's source."""
    env = _child_env()
    with (
        _McpSession([_rush_bin()], world.p1, env) as mcp,
        _Dashboard(world.p1_id, world.p1) as dash,
    ):
        yield _Ctx(
            tmp=world.tmp,
            exe=[_rush_bin()],
            env=env,
            mcp=mcp,
            dash=dash,
        )


def _uid() -> str:
    return str(uuid.uuid4())


def _write_request(subject: str, text: str, source: str = "s1") -> dict[str, Any]:
    return {
        "schema_version": 2,
        "subject": subject,
        "content": {"text": text},
        "source": source,
        "apply": True,
        "invocation_id": _uid(),
        "effect_id": _uid(),
    }


# ---------------------------------------------------------------------------
# R1: integrated route and scope
# ---------------------------------------------------------------------------


def _seed_row(
    root: Path,
    artifact_id: str,
    text: str,
    *,
    source: str,
    subject: str = SUBJECT,
    family: str = "memory",
    content: dict[str, Any] | None = None,
    owner: OwnerScope | None = None,
) -> None:
    from rush.memory.store import MemoryArtifact

    TypedArtifactStore(root).write(
        MemoryArtifact(
            id=artifact_id,
            family=family,  # type: ignore[arg-type]
            subject=subject,  # type: ignore[arg-type]
            trust_tier="DERIVED",
            content=content if content is not None else {"text": text},
            source=source,
            created_at=time.time(),
            owner_scope=owner,
        )
    )


def _reader(ctx: _Ctx) -> str:
    return "inproc" if "inproc" in ctx.transports else "mcp"


def _version_rows(db: Path, artifact_id: str) -> list[int]:
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return [
            int(row[0])
            for row in conn.execute(
                "SELECT artifact_version FROM memory_artifact_versions "
                "WHERE artifact_id = ? ORDER BY artifact_version",
                (artifact_id,),
            )
        ]


def _version_content(db: Path, artifact_id: str, version: int) -> str:
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        row = conn.execute(
            "SELECT content FROM memory_artifact_versions "
            "WHERE artifact_id = ? AND artifact_version = ?",
            (artifact_id, version),
        ).fetchone()
    assert row is not None, (artifact_id, version)
    return str(row[0])


def _event_count(root: Path) -> int:
    db = root / ".rush" / "telemetry" / "tokens.db"
    if not db.is_file():
        return 0
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        try:
            return int(conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0])
        except sqlite3.OperationalError:
            return 0


def _step_a_to_f(ctx: _Ctx, w: _World, writer: str) -> str:
    """Steps a-f: A writes r1@1, B reads and acts on v1, A corrects, B rejects the
    cached v1, history lists both versions."""
    ctx.current = "a-f"
    reader = _reader(ctx)
    db = w.p1 / ".rush" / "memory.db"

    # a. A writes
    wrote = ctx.call(
        writer, w.p1, "write", _write_request(SUBJECT, "r1 body"), cache_write=True
    )
    assert wrote.get("code") == "OK", wrote
    ((r1, v1),) = _refs(wrote["items"])
    assert v1 == 1

    # b. B reads v1 on every transport; the ordered references are equal
    seen = {t: ctx.refs(t, w.p1) for t in ctx.transports}
    for transport, refs in seen.items():
        assert (r1, 1) in refs, (transport, refs)
    assert len({tuple(refs) for refs in seen.values()}) == 1, seen
    if reader == "inproc":
        as_b = ctx.call(
            "inproc",
            w.p1,
            "list",
            {"schema_version": 2, "subjects": [SUBJECT], "query": ""},
            agent="agent-b",
        )
        assert _refs(as_b["items"]) == seen["inproc"]

    # c. B acts on v1: exact bytes, digest equals the reference payload hash
    expanded = ctx.expand("mcp", w.p1, r1, 1)
    assert expanded.get("code") == "OK", expanded
    item = expanded["items"][0]
    assert _sha(item["content_utf8"]) == item["reference"]["payload_hash"]
    assert "r1 body" in item["content_utf8"]
    assert "r1 body" in _version_content(db, r1, 1)

    # d. A corrects to v2
    edited = ctx.call(
        writer,
        w.p1,
        "edit",
        {
            "schema_version": 2,
            "subject": SUBJECT,
            "artifact_id": r1,
            "expected_version": 1,
            "content": {"text": "r1 body v2"},
            "apply": True,
            "invocation_id": _uid(),
            "effect_id": _uid(),
        },
        cache_write=True,
    )
    assert edited.get("code") == "OK", edited
    assert (r1, 2) in _refs(edited["items"])
    assert _store_version(db, r1) == 2

    # e. B reads v2 everywhere and rejects the cached v1
    for transport in ctx.transports:
        refs = ctx.refs(transport, w.p1)
        assert (r1, 2) in refs and (r1, 1) not in refs, (transport, refs)
    for transport in (
        "cli",
        "mcp",
        "dashboard",
        *(("inproc",) if reader == "inproc" else ()),
    ):
        stale = ctx.expand(transport, w.p1, r1, 1)
        assert stale.get("code") == "E_VERSION", (transport, stale)
        dump = json.dumps(stale)
        assert "content_base64" not in dump or '"content_base64": null' in dump
        assert "r1 body" not in dump, transport
    refused = ctx.call(
        writer,
        w.p1,
        "edit",
        {
            "schema_version": 2,
            "subject": SUBJECT,
            "artifact_id": r1,
            "expected_version": 1,
            "content": {"text": "stale write"},
            "apply": True,
            "invocation_id": _uid(),
            "effect_id": _uid(),
        },
        cache_write=True,
    )
    assert refused.get("code") == "E_VERSION", refused
    assert _store_version(db, r1) == 2

    # f. history lists both versions (D31)
    history = ctx.call(
        writer, w.p1, "history", {"schema_version": 2, "artifact_id": r1}
    )
    assert history.get("code") == "OK", history
    assert [v["reference"]["artifact_version"] for v in history["versions"]] == [1, 2]
    via_cli = ctx.call("cli", w.p1, "history", {"schema_version": 2, "artifact_id": r1})
    assert via_cli.get("code") == "OK", via_cli
    assert [v["reference"]["artifact_version"] for v in via_cli["versions"]] == [1, 2]
    return r1


def _preference_entry(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    assert raw.get("code") == "OK", raw
    entries = [p for p in raw["data"]["preferences"] if p["key"] == key]
    assert len(entries) == 1, raw
    return entries[0]


def _step_g_overlay(ctx: _Ctx, w: _World, writer: str) -> None:
    """Step g: a consented personal key is shared by two projects; each
    project's private row is absent from the other; no project DB holds the
    overlay row; reads leave the overlay DB untouched."""
    ctx.current = "g"
    reader = _reader(ctx)

    def record(root: Path, **fields: Any) -> dict[str, Any]:
        raw = ctx.call(
            writer,
            root,
            "preference",
            {
                "action": "record",
                "authority": "explicit",
                "user_stated": True,
                "apply": True,
                **fields,
            },
            cache_write=True,
        )
        assert raw.get("code") == "OK", raw
        return raw["data"]

    personal = record(
        w.p1,
        key="format",
        value="compact",
        scope="personal",
        source=OVERLAY_SOURCE,
        owner_scope=w.overlay.as_dict(),
    )
    overlay_id = personal["artifact_id"]
    p1_row = record(w.p1, key="ui.panel", value="wide", scope="project", source="s1")
    p2_row = record(w.p2, key="p2.only", value="yes", scope="project", source="s1")
    p1_private, p2_private = p1_row["artifact_id"], p2_row["artifact_id"]
    assert w.overlay_db.is_file()
    overlay_sha = _sha_file(w.overlay_db)

    transcripts: list[str] = []
    for transport in ("cli", "mcp", *(("inproc",) if reader == "inproc" else ())):
        from_p2 = ctx.call(
            transport, w.p2, "preference", {"action": "resolve", "key": "format"}
        )
        entry = _preference_entry(from_p2, "format")
        assert entry["status"] == "applied", (transport, entry)
        assert entry["selected"]["value"] == "compact"
        assert entry["selected"]["storage"] == "personal"
        assert entry["selected"]["artifact_id"] == overlay_id
        transcripts.append(json.dumps(from_p2))

        panel = ctx.call(
            transport, w.p2, "preference", {"action": "resolve", "key": "ui.panel"}
        )
        panel_entry = _preference_entry(panel, "ui.panel")
        assert panel_entry["status"] == "none", (transport, panel_entry)
        assert panel_entry["selected"] is None
        transcripts.append(json.dumps(panel))

        from_p1 = ctx.call(
            transport, w.p1, "preference", {"action": "resolve", "key": "p2.only"}
        )
        assert _preference_entry(from_p1, "p2.only")["status"] == "none", transport
        assert "yes" not in json.dumps(from_p1["data"]["preferences"])
    for dump in transcripts:
        assert p1_private not in dump

    listing_p2 = ctx.call(
        reader,
        w.p2,
        "list",
        {"schema_version": 2, "subjects": ["preference"], "query": ""},
    )
    assert p1_private not in json.dumps(listing_p2)
    listing_p1 = ctx.call(
        reader,
        w.p1,
        "list",
        {"schema_version": 2, "subjects": ["preference"], "query": ""},
    )
    assert "p2.only" not in json.dumps(listing_p1)
    assert p2_private not in json.dumps(listing_p1)

    for root in (w.p1, w.p2):
        assert _count_ids(root / ".rush" / "memory.db", overlay_id) == 0, root
    assert _sha_file(w.overlay_db) == overlay_sha


def _step_h_cross_owner(ctx: _Ctx, w: _World) -> None:
    """Step h (kills M3): P2 refuses P1's owner."""
    ctx.current = "h"
    from rush.memory.store import legacy_owner_scope as owner_of

    raw = ctx.call(
        _reader(ctx),
        w.p2,
        "list",
        {
            "schema_version": 2,
            "subjects": [SUBJECT],
            "query": "",
            "owner_scope": owner_of(w.p1).as_dict(),
        },
    )
    assert raw.get("code") == "E_OWNER", raw
    assert raw["data"]["reason"] == "owner_not_granted", raw
    assert not raw.get("items"), raw


def _next_action(raw: Mapping[str, Any]) -> Any:
    data = raw.get("data")
    nested = data.get("next_action") if isinstance(data, dict) else None
    return raw.get("next_action") or nested


def _step_j_revocation(ctx: _Ctx, w: _World) -> None:
    """Step j (kills M2): after the P1 grant is revoked, the next use on every
    transport is denied with `revoked` and a next action, and P1 is untouched."""
    ctx.current = "j"
    db = w.p1 / ".rush" / "memory.db"
    db_sha = _sha_file(db)
    events = _event_count(w.p1)
    _revoke(w.grants["p1"], w.data_root)
    for transport in ctx.transports:
        if transport in ("dashboard", "tui"):
            continue
        raw, items = ctx.list_items(transport, w.p1)
        assert raw.get("code") == "E_PERMISSION", (transport, raw)
        assert raw["data"]["reason"] == "revoked", (transport, raw)
        assert _next_action(raw), (transport, raw)
        assert not items
    if ctx.dash is not None:
        _status, body = ctx.dash.action(
            "memory_query",
            {"schema_version": 2, "mode": "list", "subjects": [SUBJECT], "query": ""},
        )
        ui = _ui_state(body)
        assert ui is not None and ui["state"] == "revoked", body
        assert not (_dash_result(body).get("raw", {}).get("items") or []), body
    if "tui" in ctx.transports:
        state, items = _tui_items(w.p1, SUBJECT)
        assert state.memory_view_state["state"] == "revoked", state.memory_view_state
        assert items == []
    assert _sha_file(db) == db_sha
    assert _event_count(w.p1) == events


def _identity_of(w: _World, root: Path) -> dict[str, Any]:
    from rush.memory import authorization as auth

    return dict(auth.project_identity(root, data_root=w.data_root))  # type: ignore[attr-defined]  # added by sibling task T058; absent in this copy


def _capsule_tree(w: _World) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    data = [
        row for row in _tree_digest(w.data_root) if not row[0].startswith("dashboard/")
    ]
    return _tree_digest(w.p2), data


def _step_i_pas_import(
    ctx: _Ctx,
    w: _World,
    review: Callable[[list[dict[str, Any]]], None] | None = None,
) -> None:
    """Step i: the PAS session (forged verification) imports as IMPORTED /
    imported_unverified / pending; only the explicitly confirmed constraint
    becomes active; the local choice is preserved."""
    ctx.current = "i"
    fixture = REPO / "tests/fixtures/memory_capsule/pas_session_schema1.json"
    sidecar = fixture.with_name(fixture.name + ".rush-manifest.json")
    assert fixture.is_file(), "CODEC fixture pas_session_schema1.json is absent"
    assert sidecar.is_file(), (
        "CODEC sidecar pas_session_schema1.json.rush-manifest.json"
    )
    db = w.p2 / ".rush" / "memory.db"
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        local_before = conn.execute(
            "SELECT id, artifact_version, payload_hash FROM memory_artifacts "
            "WHERE json_extract(content, '$.key') = 'p2.only'"
        ).fetchall()
    assert len(local_before) == 1, local_before

    before = _capsule_tree(w)
    preview = _run_cli(
        ctx.exe,
        w.p2,
        [
            "capsule",
            "preview-import",
            "--project",
            str(w.p2),
            "--input",
            str(fixture),
            "--format",
            "pas_v1",
            "--json",
        ],
        ctx.env,
    )["raw"]
    assert preview.get("code") == "OK", preview
    assert _capsule_tree(w) == before, "preview-import created or changed a file"
    data = preview["data"]
    records = data["records"]
    constraints = [
        r for r in records if r["foreign_origin_id"].startswith("constraint:")
    ]
    forged = [
        r
        for r in constraints
        if re.search(
            r"verif|passed|tests? pass", str(r["content"]["text"]), re.IGNORECASE
        )
    ]
    intended = [r for r in constraints if r not in forged]
    assert forged and intended, (
        f"fixture lacks the intended or forged constraint: {constraints}"
    )
    confirm = intended[0]["content"]["constraint_id"]
    if review is not None:
        review(records)

    applied = _run_cli(
        ctx.exe,
        w.p2,
        [
            "capsule",
            "import",
            "--project",
            str(w.p2),
            "--input",
            str(fixture),
            "--format",
            "pas_v1",
            "--apply",
            "--confirm-constraint-id",
            confirm,
            "--expected-digest",
            data["digest"],
            "--expected-store-revision",
            str(data["store_revision"]),
            "--invocation-id",
            data["invocation_id"],
            "--allow-cache-write",
            "--json",
        ],
        ctx.env,
    )["raw"]
    assert applied.get("code") == "OK", applied
    mappings = {m["foreign_origin_id"]: m for m in applied["data"]["mappings"]}
    assert mappings[intended[0]["foreign_origin_id"]]["applicability"] == "active"
    for record in forged:
        assert mappings[record["foreign_origin_id"]]["applicability"] == "pending"
    active = [m for m in mappings.values() if m["applicability"] == "active"]
    assert len(active) == 1, "confirmation must never activate unconfirmed records"

    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        for mapping in mappings.values():
            row = conn.execute(
                "SELECT trust_tier, source, content FROM memory_artifacts WHERE id = ?",
                (mapping["artifact_id"],),
            ).fetchone()
            assert row is not None, mapping
            assert row[0] == "IMPORTED" and row[0] != "STATED", row[:2]
            assert row[1] == "capsule:import", row[:2]
            assert json.loads(row[2]).get("authority") == "imported_unverified"
        local_after = conn.execute(
            "SELECT id, artifact_version, payload_hash FROM memory_artifacts "
            "WHERE json_extract(content, '$.key') = 'p2.only'"
        ).fetchall()
    assert local_after == local_before


def _checkpoint_content(w: _World) -> dict[str, Any]:
    identity = _identity_of(w, w.p2)
    return {
        "kind": "checkpoint",
        "schema_version": 1,
        "project_id": identity["project_id"],
        "worktree_id": identity["worktree_id"],
        "task_id": "t09-task",
        "event_kind": "checkpoint",
        "description": "T09 acceptance task",
        "objective": "export and re-import a task capsule",
        "next_action": "re-import the exported capsule",
        "implemented": ["seeded rows"],
        "unresolved": [],
        "decisions": [],
        "blockers": [],
        "discoveries": [],
        "disproved": [],
        "requirements": [
            {
                "id": "c-keep-small",
                "text": "keep the change small",
                "authority": "user",
                "provenance": "/requirements/0",
            }
        ],
        "checks": [
            {
                "command": ["pytest", "-q"],
                "exit_code": 0,
                "status": "passed",
                "source_revision": "abc1234",
                "receipt_id": "receipt-1",
            }
        ],
        "evidence_refs": [{"artifact_id": "t09-evidence", "version": 1}],
        "source": {"commit": None, "branch": None, "dirty": False},
    }


def _step_i2_rush_capsule(ctx: _Ctx, w: _World) -> None:
    """Step i (Rush capsule): export a task from P2 and re-import it into P2
    through the codec route (origin equals destination: `claimed`)."""
    ctx.current = "i2"
    _seed_row(
        w.p2, "t09-evidence", "evidence body", source="s1", subject="domain_knowledge"
    )
    _seed_row(
        w.p2,
        "t09-checkpoint",
        "",
        source="s1",
        subject="episodic",
        family="experience",
        content=_checkpoint_content(w),
    )
    out = w.tmp / "t09-task.rush-capsule.json"
    preview = _run_cli(
        ctx.exe,
        w.p2,
        [
            "capsule",
            "preview-export",
            "--project",
            str(w.p2),
            "--output",
            str(out),
            "--json",
        ],
        ctx.env,
    )["raw"]
    assert preview.get("code") == "OK", preview
    assert not out.exists(), "preview-export wrote the output"
    exported = _run_cli(
        ctx.exe,
        w.p2,
        [
            "capsule",
            "export",
            "--project",
            str(w.p2),
            "--output",
            str(out),
            "--expected-digest",
            preview["data"]["digest"],
            "--invocation-id",
            preview["data"]["invocation_id"],
            "--allow-artifact-write",
            "--json",
        ],
        ctx.env,
    )["raw"]
    assert exported.get("code") == "OK", exported
    capsule = json.loads(out.read_text(encoding="utf-8"))
    assert capsule["format"] == "rush_v1"
    assert str(w.p2) not in out.read_text(encoding="utf-8")

    imported_preview = _run_cli(
        ctx.exe,
        w.p2,
        [
            "capsule",
            "preview-import",
            "--project",
            str(w.p2),
            "--input",
            str(out),
            "--json",
        ],
        ctx.env,
    )["raw"]
    assert imported_preview.get("code") == "OK", imported_preview
    assert imported_preview["data"].get("origin_match") == "claimed"
    data = imported_preview["data"]
    constraint = next(
        r for r in data["records"] if r["foreign_origin_id"].startswith("constraint:")
    )
    applied = _run_cli(
        ctx.exe,
        w.p2,
        [
            "capsule",
            "import",
            "--project",
            str(w.p2),
            "--input",
            str(out),
            "--apply",
            "--confirm-constraint-id",
            constraint["content"]["constraint_id"],
            "--expected-digest",
            data["digest"],
            "--expected-store-revision",
            str(data["store_revision"]),
            "--invocation-id",
            data["invocation_id"],
            "--allow-cache-write",
            "--json",
        ],
        ctx.env,
    )["raw"]
    assert applied.get("code") == "OK", applied
    db = w.p2 / ".rush" / "memory.db"
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        for mapping in applied["data"]["mappings"]:
            row = conn.execute(
                "SELECT trust_tier, source FROM memory_artifacts WHERE id = ?",
                (mapping["artifact_id"],),
            ).fetchone()
            assert tuple(row) == ("IMPORTED", "capsule:import"), mapping
            expected = (
                "active"
                if mapping["foreign_origin_id"] == constraint["foreign_origin_id"]
                else "pending"
            )
            assert mapping["applicability"] == expected, mapping


def _step_k_legacy(ctx: _Ctx, w: _World) -> None:
    """Step k (access form `legacy_allowlist`): three distinct contracts on the
    never-enrolled P3, plus the enrolled-without-policy case."""
    ctx.current = "k"
    assert not (w.p3 / ".rush").exists(), "P3 must start with no .rush"
    _seed_row(w.p3, "p3-a", "needle a", source="s1")
    _seed_row(w.p3, "p3-b", "needle b", source="s2")
    tool = MemoryTool()
    narrowed = _raw(
        tool.run(
            w.p3,
            operation="list",
            subject=SUBJECT,  # type: ignore[arg-type]
            session_allowlist=["s1"],
            request={"view": "compact"},
        )
    )
    assert narrowed.get("code") == "OK", narrowed
    assert [i["id"] for i in narrowed["data"]["items"]] == ["p3-a"]

    before = _tree_digest(w.p3)
    omitted = tool.run(
        w.p3,
        operation="list",
        subject=SUBJECT,  # type: ignore[arg-type]
    )
    assert omitted["status"] == "skipped", omitted
    assert not (_raw(omitted).get("data") or {}).get("items")
    assert _tree_digest(w.p3) == before

    v2 = _raw(
        tool.run(
            w.p3,
            operation="list",
            request={"schema_version": 2, "subjects": [SUBJECT], "query": ""},
        )
    )
    assert v2.get("code") == "E_PERMISSION", v2
    assert v2["data"]["reason"] == "policy_missing", v2

    assert ctx.mcp is not None
    empty = _raw(
        ctx.mcp.call(
            {
                "path": str(w.p3),
                "operation": "list",
                "subject": SUBJECT,
                "session_allowlist": [],
                "request": {"view": "compact"},
            }
        )
    )
    assert empty.get("code") == "E_INPUT", empty
    details = empty["data"].get("details")
    if details:
        assert any(d["loc"][0] == "session_allowlist" for d in details), details
    else:
        assert "session_allowlist" in json.dumps(empty)

    from rush.memory import authorization as auth

    policy = auth.policy_path(data_root=w.data_root)
    moved = policy.with_name(policy.name + ".t09-moved")
    policy.rename(moved)
    try:
        enrolled = _raw(
            tool.run(
                w.p1,
                operation="list",
                subject=SUBJECT,  # type: ignore[arg-type]
                session_allowlist=["s1"],
                request={"view": "compact"},
            )
        )
    finally:
        moved.rename(policy)
    assert enrolled.get("code") == "E_PERMISSION", enrolled
    assert enrolled["data"]["reason"] == "policy_missing", enrolled
    assert not enrolled["data"].get("items")


def test_t09_integrated_route_and_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1: one authorized project, two agents, two projects, one consented
    personal key, across in-process, CLI, stdio MCP, dashboard HTTP and TUI."""
    w = _world(tmp_path, monkeypatch)
    with _source_ctx(w) as ctx:
        _step_a_to_f(ctx, w, "inproc")
        _step_g_overlay(ctx, w, "inproc")
        _step_h_cross_owner(ctx, w)
        _step_i_pas_import(ctx, w)
        _step_i2_rush_capsule(ctx, w)
        _step_j_revocation(ctx, w)
        _step_k_legacy(ctx, w)
    # l. G3: reads with cache_write off created no telemetry anywhere
    assert not (w.p1 / ".rush" / "telemetry" / "tokens.db").exists()
    assert not (w.p2 / ".rush" / "telemetry" / "tokens.db").exists()
    assert not (w.p3 / ".rush" / "telemetry").exists()


# ---------------------------------------------------------------------------
# G8 rows: one row per access form
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _light_ctx(w: _World) -> Iterator[_Ctx]:
    env = _child_env()
    with _McpSession([_rush_bin()], w.p1, env) as mcp:
        ctx = _Ctx(tmp=w.tmp, exe=[_rush_bin()], env=env, mcp=mcp)
        yield ctx


@pytest.mark.parametrize(
    "form",
    [
        pytest.param("policy", id="policy"),
        pytest.param("legacy_allowlist", id="legacy_allowlist"),
        pytest.param("overlay", id="overlay"),
    ],
)
def test_t09_access_form_rows(
    form: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G8: the scope predicate holds for each access form on in-process, CLI and
    stdio MCP; the policy and overlay forms also deny after revocation."""
    w = _world(tmp_path, monkeypatch)
    with _light_ctx(w) as ctx:
        transports = ("inproc", "cli", "mcp")
        if form == "policy":
            wrote = ctx.call(
                "inproc",
                w.p1,
                "write",
                _write_request(SUBJECT, "form row"),
                cache_write=True,
            )
            assert wrote.get("code") == "OK", wrote
            ((row, _),) = _refs(wrote["items"])
            seen = [ctx.refs(t, w.p1) for t in transports]
            assert seen[0] == seen[1] == seen[2], seen
            assert (row, 1) in seen[0]
            _revoke(w.grants["p1"], w.data_root)
            for transport in transports:
                raw, items = ctx.list_items(transport, w.p1)
                assert raw.get("code") == "E_PERMISSION", (transport, raw)
                assert raw["data"]["reason"] == "revoked", (transport, raw)
                assert not items
        elif form == "legacy_allowlist":
            _seed_row(w.p3, "legacy-s1", "needle s1", source="s1")
            _seed_row(w.p3, "legacy-s2", "needle s2", source="s2")
            inproc = _raw(
                MemoryTool().run(
                    w.p3,
                    operation="list",
                    subject=SUBJECT,  # type: ignore[arg-type]
                    session_allowlist=["s1"],
                    request={"view": "compact"},
                )
            )
            via_mcp = _raw(
                ctx.mcp.call(  # type: ignore[union-attr]
                    {
                        "path": str(w.p3),
                        "operation": "list",
                        "subject": SUBJECT,
                        "session_allowlist": ["s1"],
                        "request": {"view": "compact"},
                    }
                )
            )
            via_cli = _raw(
                _run_cli(
                    ctx.exe,
                    w.p3,
                    ["list", "--subject", SUBJECT, "--session", "s1", "--json"],
                    ctx.env,
                )
            )
            for raw in (inproc, via_mcp):
                assert raw.get("code") == "OK", raw
                assert [i["id"] for i in raw["data"]["items"]] == ["legacy-s1"]
            assert via_cli.get("code") == "OK", via_cli
            assert "legacy-s2" not in json.dumps(via_cli)
        else:
            personal = ctx.call(
                "inproc",
                w.p1,
                "preference",
                {
                    "action": "record",
                    "key": "format",
                    "value": "compact",
                    "scope": "personal",
                    "authority": "explicit",
                    "source": OVERLAY_SOURCE,
                    "owner_scope": w.overlay.as_dict(),
                    "user_stated": True,
                    "apply": True,
                },
                cache_write=True,
            )
            assert personal.get("code") == "OK", personal
            overlay_id = personal["data"]["artifact_id"]
            owner = w.overlay.as_dict()
            request = {
                "schema_version": 2,
                "subjects": ["preference"],
                "query": "",
                "owner_scope": owner,
            }
            for transport in ("inproc", "mcp"):
                raw = ctx.call(transport, w.p1, "list", request)
                assert raw.get("code") == "OK", (transport, raw)
                assert overlay_id in [r[0] for r in _refs(raw["items"])]
            via_cli = _raw(
                _run_cli(
                    ctx.exe,
                    w.p1,
                    [
                        "list",
                        "--subject",
                        "preference",
                        "--owner",
                        f"{owner['kind']}:{owner['id']}",
                        "--json",
                    ],
                    ctx.env,
                )
            )
            assert overlay_id in [r[0] for r in _refs(via_cli["items"])]
            _revoke(w.grants["p1_overlay"], w.data_root)
            for transport in ("inproc", "mcp"):
                raw = ctx.call(transport, w.p1, "list", request)
                assert raw.get("code") == "E_PERMISSION", (transport, raw)
                assert raw["data"]["reason"] == "revoked", (transport, raw)
                assert not raw.get("items")


# ---------------------------------------------------------------------------
# R5a: a receipt matches what was delivered
# ---------------------------------------------------------------------------


def _events(root: Path) -> list[tuple[str, str, str, int]] | None:
    """`(invocation_id, event_id, kind, tokens)` rows of the project telemetry,
    or None when the telemetry DB does not exist."""
    db = root / ".rush" / "telemetry" / "tokens.db"
    if not db.is_file():
        return None
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        try:
            rows = conn.execute(
                "SELECT invocation_id, event_id, kind, tokens FROM memory_events "
                "ORDER BY rowid"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [(str(r[0]), str(r[1]), str(r[2]), int(r[3])) for r in rows]


def _receipt_project(
    tmp_path: Path,
    data_root: Path,
    name: str,
    *,
    ops: Sequence[str] = ("ask", "list", "expand"),
) -> tuple[Path, dict[str, Any]]:
    root = _register(tmp_path / name, data_root)
    for index in range(3):
        _seed_row(root, f"rc-{index}", f"needle alpha {index}", source="s1")
    grant = _grant(root, legacy_owner_scope(root), data_root, sources=("s1",), ops=ops)
    return root, grant


def _deliver(
    root: Path,
    operation: str,
    *,
    cache_write: bool,
    network: bool = False,
    invocation_id: str | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = MemoryTool().run(
        root,
        operation=operation,  # type: ignore[arg-type]
        subject=SUBJECT,  # type: ignore[arg-type]
        query="needle" if operation in ("ask", "recall") else "",
        request=request if request is not None else {"view": "compact"},
        permissions=ExecutionPermissions(cache_write=cache_write, network=network),
        invocation_id=invocation_id or _uid(),
    )
    return _raw(result)


_FORMS = ("v1", "v2")
_V2_CAPS = {"max_bytes": 6000, "max_tokens": 2000}


def _form_request(form: str, operation: str, **extra: Any) -> dict[str, Any]:
    """A compact read page request in the legacy (`v1`) or public schema-2 form."""
    if form == "v1":
        return {"view": "compact", **extra}
    base: dict[str, Any] = {"schema_version": 2, "subjects": [SUBJECT]}
    if operation in ("ask", "recall"):
        base["query"] = "needle"
    return {**base, **extra}


def _form_expand(
    form: str, artifact_id: str, version: int, representation: str
) -> dict[str, Any]:
    if form == "v1":
        return {"id": artifact_id, "version": version, "representation": representation}
    return {
        "schema_version": 2,
        "artifact_id": artifact_id,
        "artifact_version": version,
        "representation": representation,
    }


def _deliver_form(
    form: str,
    root: Path,
    operation: str,
    *,
    cache_write: bool,
    network: bool = False,
    invocation_id: str | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if form == "v1":
        return _deliver(
            root,
            operation,
            cache_write=cache_write,
            network=network,
            invocation_id=invocation_id,
            request=request,
        )
    result = MemoryTool().run(
        root,
        operation=operation,  # type: ignore[arg-type]
        request=request if request is not None else _form_request(form, operation),
        permissions=ExecutionPermissions(cache_write=cache_write, network=network),
        invocation_id=invocation_id or _uid(),
    )
    return _raw(result)


def _form_items(form: str, raw: Mapping[str, Any]) -> list[Any]:
    if form == "v1":
        return list(raw["data"]["items"])
    return list(raw.get("items") or raw.get("data", {}).get("items") or [])


def _frame_fits(raw: Mapping[str, Any], max_bytes: int) -> bool:
    """C05: a delivered page, serialized, never exceeds its `max_bytes` UTF-8
    bytes (the response `raw` is a part of the frame, so it fits when the frame
    does)."""
    text = json.dumps(raw, separators=(",", ":"), ensure_ascii=False, default=str)
    return len(text.encode("utf-8")) <= max_bytes


def test_t09_receipt_matches_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5a / C06: with cache_write each delivered page writes exactly one
    receipt whose tokens equal the page's `data.tokens`; without cache_write,
    for a denied, admission-failed or stale-version request, and for a retry of
    the same invocation, no row is added. The legacy request form and the public
    schema-2 form (admitted frame within its caps, cursor pages one receipt
    each, admission refusal naming the cap) are both held to it."""
    from rush.token_economy.telemetry import read_artifact_expansion_receipts_readonly

    data_root = _isolate(tmp_path, monkeypatch)
    for form in _FORMS:
        _receipt_scenario(
            form, tmp_path, data_root, read_artifact_expansion_receipts_readonly
        )


def _receipt_scenario(
    form: str,
    tmp_path: Path,
    data_root: Path,
    read_receipts: Callable[[Path, str, int], list[dict[str, Any]]],
) -> None:
    where = f"[{form}]"
    root, _grant_row = _receipt_project(tmp_path, data_root, f"{form}-delivered")
    delivered = 0

    for operation in ("ask", "recall", "list"):
        before = _events(root) or []
        raw = _deliver_form(form, root, operation, cache_write=True)
        assert raw.get("code") == "OK", (where, operation, raw)
        after = _events(root)
        assert after is not None and len(after) == len(before) + 1, (
            where,
            operation,
            after,
        )
        _inv, _event, kind, tokens = after[-1]
        assert kind == "retrieval", (where, operation, after[-1])
        assert tokens == raw["data"]["tokens"], (
            where,
            operation,
            after[-1],
            raw["data"],
        )
        delivered += 1

    if form == "v2":
        # cursor pages: one receipt per delivered page, every page inside its caps
        seen: list[tuple[str, int]] = []
        cursor: str | None = None
        for _page in range(5):
            before = _events(root) or []
            extra: dict[str, Any] = {"limit": 1, **_V2_CAPS}
            if cursor:
                extra["cursor"] = cursor
            raw = _deliver_form(
                form,
                root,
                "list",
                cache_write=True,
                request=_form_request(form, "list", **extra),
            )
            assert raw.get("code") == "OK", (where, "cursor page", raw)
            assert len(_form_items(form, raw)) == 1, (where, raw)
            assert _frame_fits(raw, _V2_CAPS["max_bytes"]), (where, "frame over cap")
            after = _events(root)
            assert after is not None and len(after) == len(before) + 1, (where, after)
            assert after[-1][2] == "retrieval", (where, after[-1])
            assert after[-1][3] == raw["data"]["tokens"], (
                where,
                after[-1],
                raw["data"],
            )
            seen.extend(_refs(_form_items(form, raw)))
            delivered += 1
            cursor = raw.get("next_cursor")
            if not cursor:
                break
        assert len(seen) == 3 and len(set(seen)) == 3, (where, seen)

    # hybrid without an embedding configuration falls back to lexical
    before = _events(root) or []
    hybrid = _deliver_form(
        form,
        root,
        "ask",
        cache_write=True,
        network=True,
        request=_form_request(form, "ask", retrieval="hybrid"),
    )
    assert hybrid.get("code") in ("OK", "E_EMBEDDING_UNAVAILABLE"), (where, hybrid)
    assert _form_items(form, hybrid), (where, "the lexical fallback delivered no page")
    after = _events(root)
    assert after is not None and len(after) == len(before) + 1, (where, after)
    assert after[-1][3] == hybrid["data"]["tokens"], (where, after[-1], hybrid["data"])
    delivered += 1

    # expansion, both representations: one `expansion` row each, readable back
    expansions: dict[str, tuple[str, int]] = {}
    for representation in ("base64", "utf8"):
        before = _events(root) or []
        invocation = _uid()
        raw = _deliver_form(
            form,
            root,
            "expand",
            cache_write=True,
            invocation_id=invocation,
            request=_form_expand(form, "rc-0", 1, representation),
        )
        assert raw.get("code") == "OK", (where, representation, raw)
        after = _events(root)
        assert after is not None and len(after) == len(before) + 1, (where, after)
        assert after[-1][2] == "expansion", (where, after[-1])
        assert after[-1][3] == raw["data"]["tokens"], (where, after[-1], raw["data"])
        expansions[invocation] = (representation, int(raw["data"]["tokens"]))
        delivered += 1
    receipts = read_receipts(root, "rc-0", 1)
    assert {(r["id"], r["tokens"]) for r in receipts} == {
        (inv, tokens) for inv, (_rep, tokens) in expansions.items()
    }, (where, receipts)

    # a retry of the same invocation adds nothing
    retry_id = _uid()
    before = _events(root) or []
    first = _deliver_form(form, root, "ask", cache_write=True, invocation_id=retry_id)
    assert first.get("code") == "OK", (where, first)
    delivered += 1
    mid = _events(root)
    assert mid is not None and len(mid) == len(before) + 1, (where, mid)
    again = _deliver_form(form, root, "ask", cache_write=True, invocation_id=retry_id)
    assert again.get("code") == "OK", (where, again)
    assert _events(root) == mid, where

    total = _events(root)
    assert total is not None and len(total) == delivered, (
        where,
        len(total or []),
        delivered,
    )

    # cache_write off on a fresh root: no telemetry DB
    off_root, _ = _receipt_project(tmp_path, data_root, f"{form}-cache-off")
    assert _deliver_form(form, off_root, "ask", cache_write=False)["code"] == "OK"
    assert not (off_root / ".rush" / "telemetry" / "tokens.db").exists(), where

    # a revoked grant: the first call is denied and creates no telemetry DB
    revoked_root, revoked_grant = _receipt_project(
        tmp_path, data_root, f"{form}-revoked"
    )
    _revoke(revoked_grant, data_root)
    denied = _deliver_form(form, revoked_root, "ask", cache_write=True)
    assert denied.get("code") == "E_PERMISSION", (where, denied)
    if form == "v2":
        assert denied["data"]["reason"] == "revoked", (where, denied)
    assert not (revoked_root / ".rush" / "telemetry" / "tokens.db").exists(), where

    # admission failure (max_bytes=1): E_INPUT, no row, no DB on a fresh root
    admit_root, _ = _receipt_project(tmp_path, data_root, f"{form}-admission")
    refused = _deliver_form(
        form,
        admit_root,
        "ask",
        cache_write=True,
        request=_form_request(form, "ask", max_bytes=1),
    )
    assert refused.get("code") == "E_INPUT", (where, refused)
    if form == "v2":
        assert "max_bytes" in json.dumps(refused, default=str), (where, refused)
    assert not (admit_root / ".rush" / "telemetry" / "tokens.db").exists(), where
    assert (_events(root) or []) == total, where

    # a superseded version: E_VERSION, no row, no DB on a fresh root
    stale_root, _ = _receipt_project(tmp_path, data_root, f"{form}-stale")
    TypedArtifactStore(stale_root).update_content(
        "rc-0", {"text": "needle alpha 0 edited"}, expected_version=1
    )
    stale = _deliver_form(
        form,
        stale_root,
        "expand",
        cache_write=True,
        request=_form_expand(form, "rc-0", 1, "utf8"),
    )
    assert stale.get("code") == "E_VERSION", (where, stale)
    if form == "v2":
        assert "content_utf8" not in json.dumps(stale, default=str), (where, stale)
    assert not (stale_root / ".rush" / "telemetry" / "tokens.db").exists(), where


# ---------------------------------------------------------------------------
# R2: the acceptance report
# ---------------------------------------------------------------------------


def _h2_spans(text: str) -> list[tuple[str, int, int]]:
    matches = list(re.finditer(r"^## .*$", text, re.MULTILINE))
    spans = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        spans.append((match.group(0).rstrip(), match.start(), end))
    return spans


def _sections(text: str) -> dict[str, str]:
    """Heading line through the line before the next `^## ` (or EOF)."""
    sections: dict[str, str] = {}
    for heading, start, end in _h2_spans(text):
        assert heading not in sections, f"duplicate heading {heading!r}"
        sections[heading] = text[start:end]
    return sections


def _section_bytes(section: str) -> bytes:
    """The pinned form of a section: trailing blank lines removed, one final
    newline. Producer commits and this test hash the same form."""
    return (section.rstrip("\n") + "\n").encode("utf-8")


def _gfm_tables(text: str) -> list[list[str]]:
    tables: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            current.append(line.strip())
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _unquote(cell: str) -> str:
    return cell.strip().strip("`")


def _lane_rows(section: str) -> tuple[list[str], list[dict[str, str]]]:
    problems: list[str] = []
    tables = _gfm_tables(section)
    if len(tables) != 1:
        return [f"## Lanes must hold exactly one table, found {len(tables)}"], []
    table = tables[0]
    if table[0] != LANE_HEADER:
        problems.append(f"lanes header is {table[0]!r}, expected {LANE_HEADER!r}")
    rows = []
    for line in table[2:]:
        cells = _cells(line)
        if len(cells) != 5:
            problems.append(f"lane row has {len(cells)} cells: {line!r}")
            continue
        rows.append(
            {
                "lane": _unquote(cells[0]),
                "implementation_gate": _unquote(cells[1]),
                "live_acceptance": _unquote(cells[2]),
                "blocker": cells[3],
                "evidence": cells[4],
            }
        )
    return problems, rows


def _passed_lanes() -> set[str]:
    if not REPORT.is_file():
        return set()
    try:
        section = _sections(REPORT.read_text(encoding="utf-8")).get("## Lanes", "")
        _problems, rows = _lane_rows(section)
    except AssertionError:
        return set()
    return {r["lane"] for r in rows if r["live_acceptance"] == "passed"}


def test_t09_report_schema() -> None:
    """R2/R7: the acceptance report follows the brief's grammar; the 72-T07 and
    72-T08 sections are byte-pinned; lanes carry one exact blocker each."""
    assert REPORT.is_file(), f"{REPORT.relative_to(REPO)} does not exist"
    text = REPORT.read_text(encoding="utf-8")
    problems: list[str] = []
    headings = [h for h, _s, _e in _h2_spans(text)]
    for heading in REPORT_H2:
        if headings.count(heading) != 1:
            problems.append(f"{heading!r} appears {headings.count(heading)} times")
    unknown = [h for h in headings if h not in REPORT_H2]
    if unknown:
        problems.append(f"unknown H2 headings: {unknown}")
    assert not [p for p in problems if "appears" in p], problems
    sections = _sections(text)

    def lines(heading: str) -> list[str]:
        return [
            line.strip()
            for line in sections[heading].splitlines()[1:]
            if line.strip() and not line.strip().startswith("```")
        ]

    for heading, patterns in (
        ("## Source hash", SOURCE_HASH_PATTERNS),
        ("## Installed artifact hash", (r"installed_artifact_sha256: [0-9a-f]{64}",)),
        ("## Platform and client versions", PLATFORM_PATTERNS),
    ):
        body = lines(heading)
        for pattern in patterns:
            hits = [line for line in body if re.fullmatch(pattern, line)]
            if len(hits) != 1:
                problems.append(f"{heading}: {len(hits)} lines match {pattern!r}")

    lane_problems, rows = _lane_rows(sections["## Lanes"])
    problems.extend(lane_problems)
    ids = [r["lane"] for r in rows]
    if sorted(ids) != sorted(LANES):
        problems.append(f"lane ids {sorted(ids)} != closed set {sorted(LANES)}")
    by_id = {r["lane"]: r for r in rows}
    for row in rows:
        gate, live = row["implementation_gate"], row["live_acceptance"]
        if gate not in ("passed", "open") or live not in ("passed", "open"):
            problems.append(f"{row['lane']}: status not in passed|open")
        both = gate == "passed" and live == "passed"
        blocker = row["blocker"]
        if both != (blocker == "—"):
            problems.append(f"{row['lane']}: blocker must be — iff both passed")
        if not both and (not blocker.strip() or ";" in blocker or "<br" in blocker):
            problems.append(f"{row['lane']}: exactly one blocker required: {blocker!r}")
        if not row["evidence"].strip():
            problems.append(f"{row['lane']}: evidence is empty")
    fixed = by_id.get("r5b-frame-receipts")
    if fixed is not None and (
        (fixed["implementation_gate"], fixed["live_acceptance"]) != ("open", "open")
        or fixed["blocker"] != R5B_BLOCKER
        or "tests/test_phase75_usage.py::test_memory_event_frame_receipt_columns"
        not in fixed["evidence"]
    ):
        problems.append(f"r5b-frame-receipts row is not the fixed row: {fixed}")
    portable = by_id.get("portable-route-release")
    if portable is not None and (
        portable["live_acceptance"] != "open" or portable["blocker"] != PORTABLE_BLOCKER
    ):
        problems.append(f"portable-route-release row is not the fixed row: {portable}")
    for lane in ("phase70-t28d-g5-g8", "phase71-p07"):
        if lane in by_id and by_id[lane]["live_acceptance"] != "open":
            problems.append(f"{lane} must stay live_acceptance=open (R7)")

    # byte pins of the producer sections
    for heading, commit, digest, label in (
        (T07_HEADING, _T07_COMMIT, _T07_WALKTHROUGH_SHA256, "72-T07"),
        (T08_HEADING, _T08_COMMIT, _T08_EVALUATION_SHA256, "72-T08"),
    ):
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(
            r"[0-9a-f]{64}", digest
        ):
            problems.append(
                f"{label} pin not derived: set the commit and the sha256 of "
                f"_section_bytes() of {heading!r} from "
                f"`git show <{label} sha>:docs/reports/phase-72-memory-acceptance.md`"
            )
        elif _sha(_section_bytes(sections[heading])) != digest:
            problems.append(f"{heading!r} differs from its {label} commit {commit}")

    # redaction over every section (T09-owned sections and the pinned ones)
    for heading, section in sections.items():
        producer = heading in (T07_HEADING, T08_HEADING)
        for pattern, label in REDACTION_PATTERNS:
            hit = re.search(pattern, section)
            if hit:
                problems.append(
                    f"{heading!r}{' (producer section)' if producer else ''}: "
                    f"{label} {hit.group(0)[:12]!r}"
                )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# R3, R10: the CLI and MCP documentation covers every leaf and operation
# ---------------------------------------------------------------------------


def _click_leaves(
    group: click.Group, prefix: tuple[str, ...] = ()
) -> list[tuple[str, ...]]:
    leaves: list[tuple[str, ...]] = []
    for name, command in sorted(group.commands.items()):
        path = (*prefix, name)
        if isinstance(command, click.Group):
            leaves.extend(_click_leaves(command, path))
        else:
            leaves.append(path)
    return leaves


def _memory_group() -> click.Group:
    from rush.cli import cli

    group = cli.commands["memory"]
    assert isinstance(group, click.Group)
    return group


def test_t09_cli_reference_lists_memory_leaves() -> None:
    """R3: every Click leaf under `rush memory` (recursive; a superset of the 35
    required leaves) appears delimited by non-[\\w-] characters in the CLI
    reference."""
    leaves = _click_leaves(_memory_group())
    problems = [
        f"missing Click leaf: rush memory {' '.join(path)}"
        for path in REQUIRED_LEAVES
        if path not in leaves
    ]
    text = _read("docs/reference/cli-reference.md")
    for path in leaves:
        citation = "rush memory " + " ".join(path)
        if not re.search(rf"(?<![\w-]){re.escape(citation)}(?![\w-])", text):
            problems.append(f"docs/reference/cli-reference.md lacks `{citation}`")
    assert not problems, "\n".join(problems)


def _memory_operations() -> list[str]:
    from rush.mcp import build_server

    tools = asyncio.run(build_server().list_tools())
    tool = next(t for t in tools if t.name == "rush_memory")
    schema = tool.inputSchema["properties"]["operation"]
    values = schema.get("enum")
    if values is None:
        values = [
            option["const"] for option in schema.get("anyOf", []) if "const" in option
        ]
    assert values, schema
    return [str(v) for v in values]


def test_t09_memory_operation_docs_parity() -> None:
    """R10: every `rush_memory` operation is documented, backticked, in the five
    operation docs, none of which keeps an unconditional allowlist claim."""
    operations = _memory_operations()
    problems = []
    absent = [op for op in REQUIRED_OPERATIONS if op not in operations]
    if absent:
        problems.append(
            f"rush_memory operation enum lacks {absent} (72-T05/72-T06/CODEC not integrated)"
        )
    operations = sorted({*operations, *REQUIRED_OPERATIONS})
    for rel in OPERATION_DOCS:
        text = _norm(_read(rel))
        missing = [op for op in operations if f"`{op}`" not in text]
        if missing:
            problems.append(f"{rel} lacks operations {missing}")
        for forbidden in FORBIDDEN_DOC_STRINGS:
            if forbidden in text:
                problems.append(f"{rel} still says {forbidden!r}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# R4: truth labels
# ---------------------------------------------------------------------------


@functools.cache
def _test_functions(rel: str) -> frozenset[str]:
    path = REPO / rel
    if not path.is_file():
        return frozenset()
    tree = _parse_source(rel, path.read_text(encoding="utf-8"))
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    )


def _claim_table(rel: str, text: str) -> tuple[list[str], list[list[str]]]:
    problems: list[str] = []
    sections = _sections(text)
    headings = [h for h, _s, _e in _h2_spans(text) if h == CLAIM_HEADING]
    if len(headings) != 1:
        return [f"{rel}: {len(headings)} `{CLAIM_HEADING}` sections"], []
    tables = _gfm_tables(sections[CLAIM_HEADING])
    if len(tables) != 1:
        return [f"{rel}: claim section holds {len(tables)} tables"], []
    table = tables[0]
    if table[0] != CLAIM_HEADER:
        problems.append(f"{rel}: claim table header is {table[0]!r}")
    rows = [_cells(line) for line in table[2:]]
    if not rows:
        problems.append(f"{rel}: claim table has no rows")
    return problems, rows


def _leaf_exists(path: tuple[str, ...]) -> bool:
    return path in _click_leaves(_memory_group())


def test_t09_docs_truth_labels() -> None:
    """R4: C01 and C05 sentences, a claim-status table per reconciled doc with
    resolvable evidence per status, and every inventoried claim covered."""
    problems: list[str] = []
    contract_lines = _read("docs/phase-plans/memory-program-contract.md").splitlines()
    if C01_SENTENCE not in contract_lines[37]:
        problems.append(
            "memory-program-contract.md:38 no longer holds the C01 sentence"
        )
    for rel in GUIDES:
        text = _norm(_read(rel))
        for label, sentence in (("C01", C01_SENTENCE), ("C05", C05_SENTENCE)):
            if sentence not in text:
                problems.append(f"{rel} lacks the verbatim {label} sentence")

    passed = _passed_lanes()
    for rel in CLAIM_DOCS:
        text = _read(rel)
        if rel in ORIGINAL_PREFIX:
            length, digest = ORIGINAL_PREFIX[rel]
            if _sha(text.encode("utf-8")[:length]) != digest:
                problems.append(f"{rel}: original bytes were rewritten (RB-4)")
        table_problems, rows = _claim_table(rel, text)
        problems.extend(table_problems)
        for cells in rows:
            if len(cells) != 5:
                problems.append(f"{rel}: claim row has {len(cells)} cells: {cells}")
                continue
            claim, status, revision, route, evidence = cells
            label = claim[:60]
            if status.strip("`") not in CLAIM_STATUSES or not status.startswith("`"):
                problems.append(f"{rel}: {label!r}: status {status!r}")
                continue
            kind = status.strip("`")
            if not re.fullmatch(r"`[0-9a-f]{7,40}`", revision):
                problems.append(f"{rel}: {label!r}: revision {revision!r}")
            if kind != "proposed" and route in ("", "—"):
                problems.append(f"{rel}: {label!r}: {kind} needs a route")
            if kind in ("implemented", "integrated"):
                refs = re.findall(r"(tests/[\w/.-]+\.py)::(\w+)", evidence)
                if not refs or any(
                    name not in _test_functions(path) for path, name in refs
                ):
                    problems.append(
                        f"{rel}: {label!r}: no resolvable test in {evidence!r}"
                    )
            elif kind == "evaluated":
                paths = re.findall(
                    r"docs/reports/phase-72-memory-eval/[^\s`|)]+", evidence
                )
                if not paths or any(not (REPO / p).exists() for p in paths):
                    problems.append(
                        f"{rel}: {label!r}: no eval artifact in {evidence!r}"
                    )
            elif kind == "live-checked":
                lanes = [lane for lane in LANES if lane in evidence]
                if (
                    "docs/reports/phase-72-memory-acceptance.md#lanes" not in evidence
                    or not any(lane in passed for lane in lanes)
                ):
                    problems.append(f"{rel}: {label!r}: no passed lane in {evidence!r}")
        claims = " \n".join(cells[0] for cells in rows if cells)
        for anchor, source, leaf in CLAIM_ANCHORS.get(rel, ()):
            if anchor not in claims:
                problems.append(f"{rel}: no claim row covers {anchor!r}")
            if source is not None and not re.search(source, text, re.MULTILINE):
                problems.append(
                    f"{rel}: anchor {anchor!r} has no source text {source!r}"
                )
            if leaf is not None and not _leaf_exists(leaf):
                problems.append(f"{rel}: anchor {anchor!r} names a missing leaf {leaf}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# shipped memory-scope text (D1, owned by 72-T01; aligned by 72-T09)
# ---------------------------------------------------------------------------

_SCOPE_RULES = (
    (r"\bgrant\b", "enrolled calls resolve the memory grant"),
    (r"`session_allowlist`[^.]*\bnarrow", "a session_allowlist only narrows"),
    (r"revoked", "a revoked grant is denied"),
    (r"expired", "an expired grant is denied"),
    (r"(never|not) (had|been|enrolled)|legacy", "the never-enrolled legacy rule"),
    (r"non-empty `session_allowlist`", "legacy reads need a non-empty allowlist"),
    (r"skipped", "omission in legacy mode is skipped"),
    (r"allow_cache_write", "mutations need allow_cache_write"),
    (r"restricted[^.]*handoff|handoff[^.]*restricted", "restricted handoff"),
    (r"data, never instructions", "memory content is data"),
)


def _memory_scope_body(text: str) -> str:
    match = re.search(
        r"^## Memory scope\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert match, "no `## Memory scope` section"
    return _norm(match.group(1))


def test_t09_shipped_scope_text_parity() -> None:
    """The three skill copies and advanced-checks.md state the T01-owned
    mode-dependent memory-scope rule, byte-identical copies, no leftover
    unconditional claim; the served wording agrees."""
    problems: list[str] = []
    copies = [(REPO / rel).read_bytes() for rel in SKILL_COPIES]
    if len({_sha(c) for c in copies}) != 1:
        problems.append("the three SKILL.md copies differ")
    surfaces = {rel: _memory_scope_body(_read(rel)) for rel in SKILL_COPIES[:1]}
    advanced = _norm(_read("docs/user-guide/advanced-checks.md"))
    anchor = advanced.find("session_allowlist")
    surfaces["docs/user-guide/advanced-checks.md"] = advanced[
        max(0, anchor - 600) : anchor + 1400
    ]
    for rel, body in surfaces.items():
        for pattern, label in _SCOPE_RULES:
            if not re.search(pattern, body, re.IGNORECASE):
                problems.append(f"{rel}: lacks {label}")
        if re.search(
            r"reads only (the )?sessions named in a non-empty", body, re.IGNORECASE
        ):
            problems.append(f"{rel}: keeps the unconditional allowlist claim")
        if "omitting it returns `skipped` without content" in body:
            problems.append(f"{rel}: keeps the unconditional omission claim")
    for rel in ("docs/user-guide/working-with-ai-agents.md",):
        text = _norm(_read(rel))
        if re.search(
            r"reads only sessions named in a non-empty `session_allowlist`", text
        ):
            problems.append(f"{rel}: keeps the unconditional allowlist claim")
    from rush.catalog import TOOL_SPECS
    from rush.mcp import build_server_instructions

    served = _norm(build_server_instructions())
    if not re.search(r"`?session_allowlist`? only narrows", served):
        problems.append(
            "build_server_instructions() does not state that it only narrows"
        )
    description = TOOL_SPECS["memory"].mcp_description
    if len(description) >= 200 or "grant" not in description:
        problems.append(
            f"catalog memory description is not the T01 wording: {description!r}"
        )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# citation resolver (G9)
# ---------------------------------------------------------------------------


def _load_test_module(rel: str, name: str) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_cli() -> click.Group:
    """A three-level command tree shaped like `rush memory capsule mapping ...`."""

    def option(*names: str, flag: bool = False) -> click.Option:
        return click.Option(list(names), is_flag=flag)

    mapping = click.Group("mapping")
    mapping.add_command(
        click.Command(
            "create",
            params=[
                option("--input"),
                option("--expected-policy-revision"),
                option("--approve", flag=True),
                option("--json", flag=True),
            ],
        )
    )
    capsule = click.Group("capsule")
    capsule.add_command(
        click.Command(
            "preview-import",
            params=[
                option("--project"),
                option("--input"),
                option("--json", flag=True),
            ],
        )
    )
    capsule.add_command(mapping)
    memory = click.Group("memory")
    memory.add_command(capsule)
    memory.add_command(
        click.Command("list", params=[option("--subject"), option("--json", flag=True)])
    )
    root = click.Group("rush")
    root.add_command(memory)
    return root


def _check_citations(resolve: Callable[[str], str | None], where: str) -> list[str]:
    problems: list[str] = []

    def expect_ok(citation: str) -> None:
        message = resolve(citation)
        if message is not None:
            problems.append(f"{where}: {citation!r} should resolve, got {message!r}")

    def expect_error(citation: str, needle: str) -> None:
        message = resolve(citation)
        if not message or needle not in message:
            problems.append(
                f"{where}: {citation!r} should fail with {needle!r}: {message!r}"
            )

    expect_ok(
        "rush memory capsule preview-import --project PROJECT --input FILE --json"
    )
    expect_ok(
        "rush memory capsule mapping create --input FILE "
        "--expected-policy-revision N --approve --json"
    )
    expect_error(
        "rush memory capsule preview-import --does-not-exist", "--does-not-exist"
    )
    expect_error(
        "rush memory capsule mapping create --does-not-exist", "--does-not-exist"
    )
    expect_error("rush memory capsule no-such-command", "unknown subcommand")
    expect_error(
        "rush memory capsule mapping no-such-leaf --json", "unknown subcommand"
    )
    return problems


def test_t09_citation_resolver_nested_commands() -> None:
    """`_resolve_citation` checks flags against the deepest named subcommand, so
    valid `rush memory capsule ...` citations resolve and bad ones still fail;
    existing two-level and placeholder behavior is unchanged."""
    module = _load_test_module("tests/test_phase70_t25.py", "t09_phase70_t25")
    resolve = module._resolve_citation
    real_cli = module.cli
    module.cli = _synthetic_cli()
    try:
        problems = _check_citations(resolve, "synthetic tree")
        assert resolve("rush memory list --subject domain_knowledge --json") is None
        assert "unknown flag" in (resolve("rush memory list --nope") or "")
        assert resolve("rush memory <COMMAND> --help") is None
        assert "unknown subcommand" in (resolve("rush memory bogus") or "")
        assert "unknown command" in (resolve("rush bogus") or "")
    finally:
        module.cli = real_cli
    problems += _check_citations(resolve, "real command tree")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# documented examples come from executed commands
# ---------------------------------------------------------------------------

EXAMPLE_MARKER = re.compile(
    r"<!--\s*t09-example:\s*([\w.-]+)\s*-->\s*\n```[^\n]*\n(.*?)\n```", re.DOTALL
)
EXAMPLE_DOCS = (
    *CLAIM_DOCS,
    "docs/reference/cli-reference.md",
    "docs/MCP.md",
    "docs/MCP_REFERENCE.md",
    "docs/reference/mcp-tool-reference.md",
    "docs/CLI_REFERENCE.md",
    "docs/TOOL_CATALOG.md",
    "docs/user-guide/advanced-checks.md",
)


def _example_receipts(section: str) -> list[dict[str, Any]]:
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match, "## Commands holds no ```json receipts block"
    receipts = _loads_json(match.group(1), "## Commands receipts block")
    assert isinstance(receipts, list), receipts
    return receipts


def _valid_flags(path: tuple[str, ...]) -> set[str] | None:
    command: click.Command = _memory_group()
    for name in path:
        if not isinstance(command, click.Group) or name not in command.commands:
            return None
        command = command.commands[name]
    flags = {"--help"}
    for param in command.params:
        flags.update(getattr(param, "opts", []) or [])
    return flags


def test_t09_documented_memory_examples_match_receipts() -> None:
    """RB-5: every example the docs publish (marked `t09-example`) equals a
    machine-recorded executed argv/request/key sequence in the report's
    `## Commands` receipts, taken on the freeze commit; name resolution or
    `--help` success alone is not execution."""
    assert REPORT.is_file(), "acceptance report does not exist"
    text = REPORT.read_text(encoding="utf-8")
    sections = _sections(text)
    problems: list[str] = []
    receipts = _example_receipts(sections["## Commands"])
    freeze = re.search(
        r"^freeze_commit: ([0-9a-f]{40})$", sections["## Source hash"], re.MULTILINE
    )
    by_id: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        example_id = receipt.get("example_id")
        if not isinstance(example_id, str) or example_id in by_id:
            problems.append(f"receipt id missing or duplicated: {example_id!r}")
            continue
        by_id[example_id] = receipt
        if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("result_sha256", ""))):
            problems.append(f"{example_id}: result_sha256 is not a sha256")
        if freeze is None or receipt.get("frozen_commit") != freeze.group(1):
            problems.append(f"{example_id}: not executed on the freeze commit")
        kind = receipt.get("kind")
        if kind == "cli":
            argv = receipt.get("argv")
            if not (
                isinstance(argv, list)
                and argv[:2] == ["rush", "memory"]
                and all(isinstance(a, str) for a in argv)
            ):
                problems.append(
                    f"{example_id}: cli receipt argv is not `rush memory ...`"
                )
                continue
            words = [a for a in argv[2:] if not a.startswith("-")]
            for depth in range(len(words), 0, -1):
                flags = _valid_flags(tuple(words[:depth]))
                if flags is not None:
                    unknown = [
                        a for a in argv[2:] if a.startswith("--") and a not in flags
                    ]
                    if unknown:
                        problems.append(f"{example_id}: unknown flags {unknown}")
                    break
            else:
                problems.append(f"{example_id}: {argv[2:]} names no Click leaf")
        elif kind == "request":
            if not isinstance(receipt.get("request"), dict) or not isinstance(
                receipt.get("operation"), str
            ):
                problems.append(
                    f"{example_id}: request receipt needs operation and request"
                )
        elif kind == "tui":
            if not (
                isinstance(receipt.get("keys"), list)
                and re.fullmatch(
                    r"[0-9a-f]{64}", str(receipt.get("observed_sha256", ""))
                )
            ):
                problems.append(
                    f"{example_id}: tui receipt needs keys and observed_sha256"
                )
        else:
            problems.append(f"{example_id}: unknown receipt kind {kind!r}")

    markers: dict[str, list[str]] = {}
    for rel in EXAMPLE_DOCS:
        for example_id, block in EXAMPLE_MARKER.findall(_read(rel)):
            markers.setdefault(rel, []).append(example_id)
            marked = by_id.get(example_id)
            if marked is None:
                problems.append(f"{rel}: example {example_id!r} has no receipt")
                continue
            body = block.strip()
            if marked.get("kind") == "cli":
                if body.lstrip("$ ").strip() != shlex.join(marked["argv"]):
                    problems.append(
                        f"{rel}: {example_id!r} differs from the executed argv"
                    )
            elif marked.get("kind") == "request":
                try:
                    published = json.loads(body)
                except ValueError:
                    published = None
                if published != marked["request"]:
                    problems.append(
                        f"{rel}: {example_id!r} differs from the executed request"
                    )
            elif marked.get("kind") == "tui" and body != " ".join(marked["keys"]):
                problems.append(f"{rel}: {example_id!r} differs from the driven keys")
    for rel in GUIDES:
        if not markers.get(rel):
            problems.append(f"{rel} publishes no executed example")
    unused = set(by_id) - {i for ids in markers.values() for i in ids}
    if unused:
        problems.append(f"receipts no doc publishes: {sorted(unused)}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# R8: the union of the ten route x mode matrices
# ---------------------------------------------------------------------------

_COLLECTED = re.compile(r"^(tests/\S+?)::(test_\w+)\[(.+)\]$")


def _cell_parts(cell: str) -> tuple[str, list[tuple[str, str]]]:
    """`[<transport>.]<route>-<dimension>-<value>[-<dimension>-<value>...]
    [-producer-<task>]` -> (route, [(dimension, value), ...])."""
    body = re.sub(r"-producer-\S+$", "", cell)
    head, separator, rest = body.partition(".")
    if separator and head in TRANSPORT_PREFIXES:
        body = rest
    tokens = body.split("-")
    return tokens[0], list(zip(tokens[1::2], tokens[2::2], strict=False))


def _pytest_children(
    args: Sequence[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "", "-p", "no:cacheprovider", *args],
        cwd=REPO,
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _uncovered_pairs(cell_ids: Sequence[str]) -> list[tuple[str, str, str]]:
    """Every (route, dimension, value) with no cell id carrying it."""
    covered: set[tuple[str, str, str]] = set()
    for cell in cell_ids:
        route, pairs = _cell_parts(cell)
        covered.update((route, dimension, value) for dimension, value in pairs)
    return [
        (route, dimension, value)
        for route in ROUTE_KEYS
        for dimension, values in DIMENSIONS.items()
        for value in values
        if (route, dimension, value) not in covered
    ]


def test_t09_matrix_cell_grammar() -> None:
    """The cell-id grammar and coverage arithmetic R8 relies on."""
    assert _cell_parts("inproc.ask-access-policy-cache_write-on") == (
        "ask",
        [("access", "policy"), ("cache_write", "on")],
    )
    assert _cell_parts("mcp.expand-representation-utf8-producer-72-T06") == (
        "expand",
        [("representation", "utf8")],
    )
    assert _cell_parts("cli_memory-apply-preview-store-old_schema") == (
        "cli_memory",
        [("apply", "preview"), ("store", "old_schema")],
    )
    assert _cell_parts("dashboard.dashboard_readers-row_state-tampered") == (
        "dashboard_readers",
        [("row_state", "tampered")],
    )
    assert len(ROUTE_KEYS) == 59 and len(set(ROUTE_KEYS)) == 59
    assert sum(len(values) for values in DIMENSIONS.values()) == 33
    every = [
        f"inproc.{route}-{dimension}-{value}"
        for route in ROUTE_KEYS
        for dimension, values in DIMENSIONS.items()
        for value in values
    ]
    assert len(every) == 1947 and _uncovered_pairs(every) == []
    assert _uncovered_pairs(every[1:]) == [("ask", "access", "policy")]
    assert len(_uncovered_pairs([])) == 1947


@pytest.mark.slow
def test_t09_route_mode_matrix_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8 / G2a: the ten matrices collect and pass in a subprocess, carry no
    `-producer-` id, and together cover every (route, dimension, value)."""
    _isolate(tmp_path, monkeypatch)
    collect = _pytest_children(["--collect-only", "-q", *MATRIX_NODE_IDS], timeout=900)
    problems: list[str] = []
    cells: dict[tuple[str, str], list[str]] = {}
    for line in collect.stdout.splitlines():
        found = _COLLECTED.match(line.strip())
        if found:
            cells.setdefault((found.group(1), found.group(2)), []).append(
                found.group(3)
            )
    if collect.returncode != 0:
        problems.append(
            f"collection failed (rc={collect.returncode}):\n{collect.stdout[-1500:]}"
            f"\n{collect.stderr[-500:]}"
        )
    for node in MATRIX_NODE_IDS:
        path, _, name = node.partition("::")
        if not cells.get((path, name)):
            problems.append(f"matrix {node} collects no cells")
    all_ids = [cell for ids in cells.values() for cell in ids]
    producer = [cell for cell in all_ids if "-producer-" in cell]
    if producer:
        problems.append(f"{len(producer)} producer-staged ids, first: {producer[:3]}")
    missing = _uncovered_pairs(all_ids)
    if missing:
        problems.append(
            f"{len(missing)} of {len(ROUTE_KEYS) * sum(map(len, DIMENSIONS.values()))} "
            f"(route, dimension, value) pairs are uncovered, first: {missing[:5]}"
        )
    inventory = json.loads(
        (REPO / "tests/fixtures/phase72/memory_route_inventory.json").read_text()
    )
    stray = sorted({p["route"] for p in inventory["pairs"]} - set(ROUTE_KEYS))
    if stray:
        problems.append(f"route inventory uses routes outside the 59 keys: {stray}")
    assert not problems, "\n".join(problems)

    run = _pytest_children(["-q", *MATRIX_NODE_IDS], timeout=3600)
    summary = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ""
    passed = re.search(r"(\d+) passed", summary)
    assert run.returncode == 0, run.stdout[-3000:]
    assert passed and int(passed.group(1)) == len(all_ids), (summary, len(all_ids))
    assert not re.search(r"skipped|xfailed|xpassed|error", summary), summary


# ---------------------------------------------------------------------------
# R9: every windows_only test is selected by a windows-contracts step
# ---------------------------------------------------------------------------


def _chain(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _is_marker(node: ast.AST, aliases: set[str]) -> bool:
    if _chain(node) == "pytest.mark.windows_only":
        return True
    return isinstance(node, ast.Name) and node.id in aliases


def _has_marker(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return any(_is_marker(element, aliases) for element in node.elts)
    return _is_marker(node, aliases)


def _literal_id(call: ast.Call) -> str | None:
    for keyword in call.keywords:
        if (
            keyword.arg == "id"
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        ):
            return keyword.value.value
    return None


def _param_calls(argvalues: ast.AST) -> list[ast.Call] | None:
    elements: list[ast.AST]
    if isinstance(argvalues, ast.List | ast.Tuple):
        elements = list(argvalues.elts)
    elif isinstance(argvalues, ast.ListComp):
        elements = [argvalues.elt]
    else:
        return None
    return [
        e
        for e in elements
        if isinstance(e, ast.Call) and _chain(e.func) == "pytest.param"
    ]


def _windows_only_nodes(
    rel: str, source: str | None = None
) -> tuple[list[str], list[str]]:
    """`(node ids, problems)` of the windows_only tests in one test file (or in
    `source`, read as that file). A parse or traversal failure names the file."""
    text = source if source is not None else _read(rel)
    tree = _parse_source(rel, text)
    aliases = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign) and _is_marker(node.value, set())
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    def marked_by_pytestmark(body: Sequence[ast.stmt]) -> bool:
        return any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
            )
            and _has_marker(node.value, aliases)
            for node in body
        )

    def flatten(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
        for node in body:
            if isinstance(node, ast.If):
                yield from flatten(node.body)
                yield from flatten(node.orelse)
            else:
                yield node

    nodes: list[str] = []
    problems: list[str] = []

    def unit(
        func: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str, inherited: bool
    ) -> None:
        whole = inherited or any(_is_marker(d, aliases) for d in func.decorator_list)
        parametrize = [
            d
            for d in func.decorator_list
            if isinstance(d, ast.Call) and _chain(d.func) == "pytest.mark.parametrize"
        ]
        windows_params: list[ast.Call] = []
        all_params: list[ast.Call] = []
        explicit_ids: list[str] | None = None
        for decorator in parametrize:
            values = decorator.args[1] if len(decorator.args) > 1 else None
            calls = _param_calls(values) if values is not None else None
            for call in calls or []:
                all_params.append(call)
                for keyword in call.keywords:
                    if keyword.arg == "marks" and _has_marker(keyword.value, aliases):
                        windows_params.append(call)
            for keyword in decorator.keywords:
                if keyword.arg == "ids" and isinstance(keyword.value, ast.List):
                    explicit_ids = [
                        e.value
                        for e in keyword.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    ]
        name = f"{rel}::{prefix}{func.name}"
        where = f"{rel}:{func.lineno}"
        if whole:
            if not parametrize:
                nodes.append(name)
            elif all_params and all(_literal_id(c) for c in all_params):
                nodes.extend(f"{name}[{_literal_id(c)}]" for c in all_params)
            elif explicit_ids:
                nodes.extend(f"{name}[{i}]" for i in explicit_ids)
            else:
                problems.append(f"{where}: marked parametrized test has no literal ids")
        elif windows_params:
            if len(parametrize) > 1:
                problems.append(f"{where}: windows_only param with several parametrize")
            for call in windows_params:
                literal = _literal_id(call)
                if literal is None:
                    problems.append(
                        f"{rel}:{call.lineno}: windows_only param lacks id="
                    )
                else:
                    nodes.append(f"{name}[{literal}]")

    try:
        for node in flatten(tree.body):
            if isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef
            ) and node.name.startswith("test_"):
                unit(node, "", marked_by_pytestmark(tree.body))
            elif isinstance(node, ast.ClassDef):
                class_marked = (
                    marked_by_pytestmark(tree.body)
                    or marked_by_pytestmark(node.body)
                    or any(_is_marker(d, aliases) for d in node.decorator_list)
                )
                for member in node.body:
                    if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef) and (
                        member.name.startswith("test_")
                    ):
                        unit(member, f"{node.name}::", class_marked)
    except RecursionError:
        raise AssertionError(
            f"{rel}: _windows_only_nodes traversal nested too deeply"
        ) from None
    return sorted(set(nodes)), problems


def _ci_pytest_lines(job: str) -> list[dict[str, Any]]:
    workflow = YAML(typ="safe").load(CI_YML.read_text(encoding="utf-8"))
    selected = []
    for step in workflow["jobs"][job]["steps"]:
        for line in str(step.get("run", "")).splitlines():
            try:
                tokens = shlex.split(line.strip())
            except ValueError:
                continue
            if tokens[:3] == ["uv", "run", "pytest"] or tokens[:4] == [
                "uv",
                "run",
                "--no-sync",
                "pytest",
            ]:
                marker = tokens[tokens.index("-m") + 1] if "-m" in tokens[:-1] else None
                selected.append(
                    {
                        "files": {
                            t for t in tokens if t.endswith(".py") and "::" not in t
                        },
                        "ids": {t for t in tokens if "::" in t},
                        "marker": marker,
                    }
                )
    return selected


def test_t09_windows_only_tests_selected_by_ci() -> None:
    """R9: an AST scan of the Phase 72 tests and the authorization tests finds
    each windows_only test, with a literal id per param, selected by a step of
    the `windows-contracts` job."""
    files = sorted(
        p.relative_to(REPO).as_posix()
        for p in (REPO / "tests").glob("test_phase72_*.py")
    )
    files.append("tests/test_memory_authorization.py")
    lines = _ci_pytest_lines("windows-contracts")
    problems: list[str] = []
    nodes: list[str] = []
    for rel in files:
        found, found_problems = _windows_only_nodes(rel)
        nodes.extend(found)
        problems.extend(found_problems)
    for node in nodes:
        rel = node.split("::")[0]
        base = node.split("[")[0]
        selected = any(
            (rel in line["files"] and line["marker"] == "windows_only")
            or node in line["ids"]
            or base in line["ids"]
            for line in lines
        )
        if not selected:
            problems.append(f"{node} is not selected by a windows-contracts step")
        print(f"T09_WINDOWS_ONLY_NODEID={node}")
    assert nodes, "no windows_only test was found"
    # The producers' native cells must exist for the scan to select them: a
    # producer that lands without its windows_only cells leaves the lane empty.
    found_nodes = set(nodes)
    for rel, function, producer in PRODUCER_WINDOWS_FUNCTIONS:
        if not any(n.split("[")[0] == f"{rel}::{function}" for n in found_nodes):
            problems.append(
                f"{rel}::{function} has no windows_only node ({producer} not integrated)"
            )
    for param_id in T06_WINDOWS_IMPORT_IDS:
        node = (
            "tests/test_phase72_memory_public.py"
            f"::test_t06_import_path_containment[{param_id}]"
        )
        if node not in found_nodes:
            problems.append(f"{node} is missing (72-T06 not integrated)")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# native CI: the T09 live drivers run on Linux, Windows and macOS runners
# ---------------------------------------------------------------------------


def _node(name: str) -> str:
    return f"{THIS_FILE}::{name}"


def test_t09_native_driver_ci_selection() -> None:
    """Each native job runs exactly the T09 driver node ids for its OS against
    the archive and SHA256SUMS it built, with a runner-temp receipt directory;
    the earlier Windows Phase 72 step stays as it is."""
    workflow = YAML(typ="safe").load(CI_YML.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    problems: list[str] = []

    def find_step(job: str, nodes: Sequence[str]) -> tuple[int, dict[str, Any]] | None:
        for index, step in enumerate(jobs[job]["steps"]):
            run = str(step.get("run", ""))
            if all(_node(n) in run for n in nodes):
                return index, step
        problems.append(f"{job}: no step runs {[_node(n) for n in nodes]}")
        return None

    def index_of(job: str, needle: str) -> int:
        for index, step in enumerate(jobs[job]["steps"]):
            if needle in str(step.get("run", "")):
                return index
        return -1

    expectations = (
        (
            "quality",
            LIVE_LINUX_NODES,
            "${{ github.workspace }}/dist/rush-linux-x86_64.tar.gz",
            "build_release_archive",
        ),
        (
            "windows-contracts",
            LIVE_WINDOWS_NODES,
            "${{ github.workspace }}/dist/rush-windows-x86_64.zip",
            "build_release_archive",
        ),
    )
    for job, nodes, archive, build in expectations:
        located = find_step(job, nodes)
        if located is None:
            continue
        index, step = located
        env = step.get("env") or {}
        run = str(step["run"])
        if env.get("RUSH_T09_LIVE_ARCHIVE") != archive:
            problems.append(
                f"{job}: RUSH_T09_LIVE_ARCHIVE is {env.get('RUSH_T09_LIVE_ARCHIVE')!r}"
            )
        if env.get("RUSH_T09_LIVE_SUMS") != "${{ github.workspace }}/dist/SHA256SUMS":
            problems.append(
                f"{job}: RUSH_T09_LIVE_SUMS is {env.get('RUSH_T09_LIVE_SUMS')!r}"
            )
        if not str(env.get("RUSH_T09_LIVE_RECEIPT_DIR", "")).startswith(
            "${{ runner.temp }}/"
        ):
            problems.append(
                f"{job}: RUSH_T09_LIVE_RECEIPT_DIR is not under runner.temp"
            )
        if "pytest" not in run or "-q" not in run or "-rA" not in run:
            problems.append(f"{job}: the step must run pytest -q -rA")
        if "--no-sync" not in run and job == "quality":
            problems.append(f"{job}: use `uv run --no-sync pytest`")
        if not (0 <= index_of(job, build) < index):
            problems.append(f"{job}: the T09 step must come after the archive build")
        extra = {n for n in re.findall(r"test_t09_live_\w+", run)} - set(nodes)
        if extra:
            problems.append(f"{job}: runs unexpected drivers {sorted(extra)}")

    located = find_step("artifact-probes", LIVE_LINUX_NODES)
    if located is not None:
        index, step = located
        run = str(step["run"])
        if "macOS" not in str(step.get("if", "")):
            problems.append("artifact-probes: the T09 step must be macOS only")
        if "dist/rush-darwin-*.tar.gz" not in run or "dist/SHA256SUMS" not in (
            run + json.dumps(step.get("env") or {})
        ):
            problems.append(
                "artifact-probes: the step must select the darwin archive and SHA256SUMS"
            )
        build_index = next(
            (
                i
                for i, s in enumerate(jobs["artifact-probes"]["steps"])
                if s.get("name") == "Build native macOS candidate"
            ),
            -1,
        )
        if not 0 <= build_index < index:
            problems.append(
                "artifact-probes: the T09 step must follow `Build native macOS candidate`"
            )

    contracts_steps = jobs["windows-contracts"]["steps"]
    t01_index = next(
        (
            i
            for i, st in enumerate(contracts_steps)
            if st.get("name") == "Verify Windows Phase 72 memory contracts"
        ),
        -1,
    )
    t06_index = next(
        (
            i
            for i, st in enumerate(contracts_steps)
            if "tests/test_phase72_memory_public.py" in str(st.get("run", ""))
            and "windows_only" in str(st.get("run", ""))
        ),
        -1,
    )
    if t06_index < 0:
        problems.append(
            "windows-contracts: no step runs tests/test_phase72_memory_public.py "
            "-m windows_only (72-T06 import-publication step not integrated)"
        )
    elif not t01_index < t06_index:
        problems.append(
            "windows-contracts: the 72-T06 step must follow the 72-T01 step"
        )
    windows_steps = [
        s
        for s in contracts_steps
        if s.get("name") == "Verify Windows Phase 72 memory contracts"
    ]
    if len(windows_steps) != 1 or "tests/test_phase72_memory_correctness.py" not in str(
        windows_steps[0].get("run", "")
    ):
        problems.append(
            "the existing `Verify Windows Phase 72 memory contracts` step changed"
        )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# T09's own G2 cells (route x access x cache_write x grant_ops, in-process)
# ---------------------------------------------------------------------------

_MATRIX_ROUTES = ("ask", "list", "expand")
_MATRIX_OP = {"ask": "ask", "list": "list", "expand": "expand"}


def _matrix_cells() -> list[Any]:
    cells = []
    for route in _MATRIX_ROUTES:
        for access in ("policy", "legacy_allowlist"):
            for cache_write in ("on", "off"):
                for grant_ops in ("exact", "missing_one"):
                    cell = (
                        f"inproc.{route}-access-{access}-cache_write-{cache_write}"
                        f"-grant_ops-{grant_ops}"
                    )
                    cells.append(
                        pytest.param(route, access, cache_write, grant_ops, id=cell)
                    )
    return cells


@pytest.mark.parametrize(
    ("route", "access", "cache_write", "grant_ops"), _matrix_cells()
)
def test_t09_route_mode_matrix(
    route: str,
    access: str,
    cache_write: str,
    grant_ops: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G2 for the routes T09 itself drives. Policy: an exact grant delivers
    (a receipt only with cache_write on); a grant missing the route's operation
    is denied with zero effects. Legacy allowlist: the allowlist delivers; its
    omission is `skipped` with zero effects."""
    data_root = _isolate(tmp_path, monkeypatch)
    needed = _MATRIX_OP[route]
    request: dict[str, Any] = {"view": "compact"}
    if route == "expand":
        request = {"id": "rc-0", "version": 1, "representation": "utf8"}
    perms = ExecutionPermissions(cache_write=cache_write == "on")

    def run(root: Path, **extra: Any) -> Any:
        return MemoryTool().run(
            root,
            operation=route,  # type: ignore[arg-type]
            subject=SUBJECT,  # type: ignore[arg-type]
            query="needle" if route == "ask" else "",
            request=request,
            permissions=perms,
            invocation_id=_uid(),
            **extra,
        )

    if access == "policy":
        root = _register(tmp_path / "proj", data_root)
        for index in range(3):
            _seed_row(root, f"rc-{index}", f"needle {index}", source="s1")
        ops = ["ask", "list", "expand"]
        if grant_ops == "missing_one":
            ops.remove(needed)
        _grant(root, legacy_owner_scope(root), data_root, sources=("s1",), ops=ops)
        db_sha = _sha_file(root / ".rush" / "memory.db")
        raw = _raw(run(root))
        if grant_ops == "exact":
            assert raw.get("code") == "OK", raw
            events = _events(root)
            if cache_write == "on":
                kind = "expansion" if route == "expand" else "retrieval"
                assert events is not None and [e[2] for e in events] == [kind], events
            else:
                assert events is None
        else:
            assert raw.get("code") == "E_PERMISSION", raw
            assert _events(root) is None
            assert _sha_file(root / ".rush" / "memory.db") == db_sha
    else:
        root = tmp_path / "legacy"
        root.mkdir()
        for index in range(3):
            _seed_row(root, f"rc-{index}", f"needle {index}", source="s1")
        before = _tree_digest(root)
        if grant_ops == "exact":
            result = run(root, session_allowlist=["s1"])
            assert _raw(result)["code"] == "OK", result
            events = _events(root)
            if cache_write == "on":
                assert events is not None and len(events) == 1, events
            else:
                assert events is None
        else:
            # the HEAD fail-closed result: no allowlist reads nothing (plain
            # ask/list are `skipped`; expand refuses), zero effects
            result = MemoryTool().run(
                root,
                operation=route,  # type: ignore[arg-type]
                subject=SUBJECT,  # type: ignore[arg-type]
                query="needle" if route == "ask" else "",
                request=request if route == "expand" else None,
                permissions=perms,
                invocation_id=_uid(),
            )
            assert result["status"] != "ok", result
            if route != "expand":
                assert result["status"] == "skipped", result
            assert "needle" not in json.dumps(result, default=str), result
            assert _tree_digest(root) == before
            assert _events(root) is None


# ---------------------------------------------------------------------------
# G4: live-driver input validation (pure; asserts before any project effect)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _LiveInputs:
    binary: Path
    binary_sha256: str
    archive_sha256: str | None
    version: str | None
    receipt_dir: Path


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _contained_member(base: Path, name: object) -> Path:
    """`name` resolved under `base` by the host's own path rules. A traversal,
    absolute or drive-relative name is refused where the host reads it that way;
    on POSIX a name holding a backslash or a colon is one literal file name."""
    text = _text_input("archive member name", name)
    assert text, "archive member name is empty"
    assert not os.path.isabs(text) and not os.path.splitdrive(text)[0], (
        f"archive path traversal: {text!r}"
    )
    target = (base / text).resolve()
    assert _inside(target, base.resolve()), f"archive path traversal: {text!r}"
    return target


def _check_archive_members(names: Sequence[str], binary_name: str, base: Path) -> None:
    for name in names:
        _contained_member(base, name)
    assert sorted(names) == sorted(["VERSION", binary_name]), (
        f"unexpected archive members: {sorted(names)}"
    )


def _extract_archive(archive: Path, workdir: Path) -> tuple[Path, str]:
    """Extract exactly `VERSION` and the platform binary of a verified archive."""
    zipped = archive.suffix == ".zip"
    binary_name = "rush.exe" if zipped else "rush"
    contents: dict[str, bytes] = {}
    if zipped:
        with zipfile.ZipFile(archive) as package:
            _check_archive_members(package.namelist(), binary_name, workdir)
            contents = {name: package.read(name) for name in package.namelist()}
    else:
        with tarfile.open(archive, "r:gz") as package:
            members = package.getmembers()
            _check_archive_members([m.name for m in members], binary_name, workdir)
            for member in members:
                assert member.isfile(), f"archive member {member.name!r} is not a file"
                handle = package.extractfile(member)
                assert handle is not None
                contents[member.name] = handle.read()
    workdir.mkdir(parents=True, exist_ok=True)
    binary = workdir / binary_name
    binary.write_bytes(contents[binary_name])
    binary.chmod(binary.stat().st_mode | 0o111)
    return binary, contents["VERSION"].decode("utf-8").strip()


def _live_inputs(
    env: Mapping[str, str],
    *,
    workdir: Path,
    repo_root: Path = REPO,
    host_home: str = _HOST_HOME,
) -> _LiveInputs:
    """Validate the live-lane inputs; every failure is an `AssertionError`
    naming the variable, raised before any project, store or telemetry effect."""
    from scripts.probe_installed_artifacts import (
        compute_sha256,
        verify_archive_checksum,
    )

    def need(name: str) -> str:
        value = env.get(name)
        assert value, f"{name} is required for the live lanes"
        return _text_input(name, value)

    def optional(name: str) -> str | None:
        value = env.get(name)
        return None if value is None else _text_input(name, value)

    receipt_text = need("RUSH_T09_LIVE_RECEIPT_DIR")
    receipt_dir = Path(receipt_text)
    assert receipt_dir.is_absolute(), "RUSH_T09_LIVE_RECEIPT_DIR must be absolute"
    assert receipt_dir.is_dir(), "RUSH_T09_LIVE_RECEIPT_DIR does not exist"
    resolved = receipt_dir.resolve()
    assert not _inside(resolved, repo_root.resolve()), (
        "RUSH_T09_LIVE_RECEIPT_DIR is inside the repository"
    )
    runner_temp = optional("RUNNER_TEMP")
    if host_home and not (
        runner_temp and _inside(resolved, Path(runner_temp).resolve())
    ):
        assert not _inside(resolved, Path(host_home).resolve()), (
            "RUSH_T09_LIVE_RECEIPT_DIR is under the host HOME"
        )

    artifact = optional("RUSH_T09_LIVE_ARTIFACT")
    archive = optional("RUSH_T09_LIVE_ARCHIVE")
    assert bool(artifact) != bool(archive), (
        "set exactly one of RUSH_T09_LIVE_ARTIFACT (with RUSH_T09_LIVE_ARTIFACT_SHA256) "
        "or RUSH_T09_LIVE_ARCHIVE (with RUSH_T09_LIVE_SUMS)"
    )
    if artifact:
        binary = Path(artifact)
        assert binary.is_absolute() and binary.exists(), (
            "RUSH_T09_LIVE_ARTIFACT does not exist"
        )
        assert not binary.is_symlink(), "RUSH_T09_LIVE_ARTIFACT is a symlink"
        assert binary.is_file(), "RUSH_T09_LIVE_ARTIFACT is not a regular file"
        expected = need("RUSH_T09_LIVE_ARTIFACT_SHA256").lower()
        assert re.fullmatch(r"[0-9a-f]{64}", expected), (
            "RUSH_T09_LIVE_ARTIFACT_SHA256 is not a sha256"
        )
        actual = compute_sha256(binary)
        assert actual == expected, (
            "RUSH_T09_LIVE_ARTIFACT sha256 does not match RUSH_T09_LIVE_ARTIFACT_SHA256"
        )
        return _LiveInputs(binary, actual, None, None, receipt_dir)

    archive_path = Path(archive or "")
    assert archive_path.is_absolute() and archive_path.exists(), (
        "RUSH_T09_LIVE_ARCHIVE does not exist"
    )
    assert not archive_path.is_symlink(), "RUSH_T09_LIVE_ARCHIVE is a symlink"
    assert archive_path.is_file(), "RUSH_T09_LIVE_ARCHIVE is not a regular file"
    sums = Path(need("RUSH_T09_LIVE_SUMS"))
    assert sums.is_file() and not sums.is_symlink(), "RUSH_T09_LIVE_SUMS is not a file"
    assert verify_archive_checksum(archive_path, sums), (
        "RUSH_T09_LIVE_ARCHIVE sha256 does not match RUSH_T09_LIVE_SUMS"
    )
    binary, version = _extract_archive(archive_path, workdir)
    return _LiveInputs(
        binary,
        compute_sha256(binary),
        compute_sha256(archive_path),
        version,
        receipt_dir,
    )


def _require_agents(
    env: Mapping[str, str], which: Callable[[str], str | None] = shutil.which
) -> None:
    """`RUSH_T09_LIVE_AGENTS=1` demands both host CLIs; never deselects."""
    if env.get("RUSH_T09_LIVE_AGENTS") == "1":
        for name in ("claude", "codex"):
            assert which(name), f"RUSH_T09_LIVE_AGENTS=1 but {name} is not on PATH"


def _fake_archive(
    directory: Path, *, zipped: bool = False, members: Mapping[str, bytes] | None = None
) -> tuple[Path, Path]:
    """A tiny release archive with a SHA256SUMS file (a stand-in binary)."""
    from scripts.probe_installed_artifacts import write_sha256sums

    directory.mkdir(parents=True, exist_ok=True)
    binary_name = "rush.exe" if zipped else "rush"
    files = (
        dict(members)
        if members is not None
        else {
            binary_name: b"#!/bin/sh\necho rush\n",
            "VERSION": b"0.0.0\n",
        }
    )
    archive = directory / ("rush-test.zip" if zipped else "rush-test.tar.gz")
    if zipped:
        with zipfile.ZipFile(archive, "w") as package:
            for name, data in files.items():
                package.writestr(name, data)
    else:
        import io

        with tarfile.open(archive, "w:gz") as package:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                package.addfile(info, io.BytesIO(data))
    sums = write_sha256sums([archive], directory / "SHA256SUMS")
    return archive, sums


_CI_LIVE_JOBS = (
    ("quality", LIVE_LINUX_NODES),
    ("windows-contracts", LIVE_WINDOWS_NODES),
    ("artifact-probes", LIVE_LINUX_NODES),
)
_CI_LIVE_VARIABLES = (
    "RUSH_T09_LIVE_ARCHIVE",
    "RUSH_T09_LIVE_SUMS",
    "RUSH_T09_LIVE_RECEIPT_DIR",
)


def _ci_supplied_inputs(base: Path) -> list[str]:
    """Problems found feeding the driver input reader exactly what each native
    CI job's T09 step supplies: the archive and SHA256SUMS written by the
    product's `build_release_archive` / `write_sha256sums`, and a receipt
    directory under the runner temp directory. A job without its step, or whose
    variables the reader rejects, is a problem."""
    from scripts.probe_installed_artifacts import (
        build_release_archive,
        write_sha256sums,
    )

    workflow = YAML(typ="safe").load(CI_YML.read_text(encoding="utf-8"))
    problems: list[str] = []
    for job, nodes in _CI_LIVE_JOBS:
        steps = [
            s
            for s in workflow["jobs"][job]["steps"]
            if all(_node(n) in str(s.get("run", "")) for n in nodes)
        ]
        if len(steps) != 1:
            problems.append(f"{job}: {len(steps)} steps run {list(nodes)}, expected 1")
            continue
        env = dict(steps[0].get("env") or {})
        run = str(steps[0]["run"])
        if job == "artifact-probes":
            # the macOS archive name is selected by a glob in the step's shell
            problems.extend(
                f"{job}: the step never supplies {name}"
                for name in _CI_LIVE_VARIABLES
                if name not in run and name not in env
            )
            continue
        workspace = base / job / "workspace"
        runner_temp = base / job / "runner-temp"
        stand_in = base / job / "stand-in"
        stand_in.parent.mkdir(parents=True, exist_ok=True)
        stand_in.write_bytes(b"#!/bin/sh\necho rush\n")

        def resolve(
            value: object, workspace: Path = workspace, temp: Path = runner_temp
        ):
            return (
                str(value)
                .replace("${{ github.workspace }}", workspace.as_posix())
                .replace("${{ runner.temp }}", temp.as_posix())
            )

        resolved = {k: resolve(v) for k, v in env.items() if k.startswith("RUSH_T09_")}
        missing = [n for n in _CI_LIVE_VARIABLES if n not in resolved]
        if missing:
            problems.append(f"{job}: the step env lacks {missing}")
            continue
        archive = Path(resolved["RUSH_T09_LIVE_ARCHIVE"])
        built = build_release_archive(stand_in, archive.parent, archive.name, "9.9.9")
        write_sha256sums([built], Path(resolved["RUSH_T09_LIVE_SUMS"]))
        Path(resolved["RUSH_T09_LIVE_RECEIPT_DIR"]).mkdir(parents=True)
        try:
            accepted = _live_inputs(
                resolved,
                workdir=base / job / "work",
                repo_root=base / "no-repo",
                host_home=str(base / "no-home"),
            )
        except AssertionError as exc:
            problems.append(
                f"{job}: the driver reader rejects the step's inputs: {exc}"
            )
            continue
        expected = "rush.exe" if archive.suffix == ".zip" else "rush"
        if accepted.binary.name != expected or accepted.version != "9.9.9":
            problems.append(
                f"{job}: extracted {accepted.binary.name} {accepted.version}"
            )
    return problems


def test_t09_live_driver_inputs(tmp_path: Path) -> None:
    """G4: every bad live input fails with an assertion naming the variable,
    before any project, store or telemetry effect."""
    fake_repo = tmp_path / "fakerepo"
    host_home = tmp_path / "hosthome"
    receipts = tmp_path / "receipts"
    project = tmp_path / "project"
    for path in (fake_repo / "inside", host_home / "inside", receipts, project):
        path.mkdir(parents=True)
    archive, sums = _fake_archive(tmp_path / "good")
    work = tmp_path / "work"

    def good() -> dict[str, str]:
        return {
            "RUSH_T09_LIVE_RECEIPT_DIR": str(receipts),
            "RUSH_T09_LIVE_ARCHIVE": str(archive),
            "RUSH_T09_LIVE_SUMS": str(sums),
        }

    def check(env: dict[str, str], needle: str) -> None:
        with pytest.raises(AssertionError) as raised:
            _live_inputs(
                env, workdir=work, repo_root=fake_repo, host_home=str(host_home)
            )
        assert needle in str(raised.value), (needle, str(raised.value))

    before = (_tree_digest(project), _tree_digest(receipts))
    ok = _live_inputs(
        good(), workdir=work, repo_root=fake_repo, host_home=str(host_home)
    )
    assert ok.binary.name == "rush" and ok.version == "0.0.0"
    assert len(ok.binary_sha256) == 64 and ok.archive_sha256 is not None

    env = good()
    del env["RUSH_T09_LIVE_RECEIPT_DIR"]
    check(env, "RUSH_T09_LIVE_RECEIPT_DIR")
    check(
        {**good(), "RUSH_T09_LIVE_RECEIPT_DIR": str(tmp_path / "missing")},
        "does not exist",
    )
    check(
        {**good(), "RUSH_T09_LIVE_RECEIPT_DIR": str(fake_repo / "inside")},
        "inside the repository",
    )
    check(
        {**good(), "RUSH_T09_LIVE_RECEIPT_DIR": str(host_home / "inside")}, "host HOME"
    )
    # the runner temp directory may sit under the runner HOME
    runner = _live_inputs(
        {
            **good(),
            "RUSH_T09_LIVE_RECEIPT_DIR": str(host_home / "inside"),
            "RUNNER_TEMP": str(host_home),
        },
        workdir=work / "runner",
        repo_root=fake_repo,
        host_home=str(host_home),
    )
    assert runner.receipt_dir == host_home / "inside"
    # no live mode, or two at once
    check({"RUSH_T09_LIVE_RECEIPT_DIR": str(receipts)}, "exactly one of")
    check({**good(), "RUSH_T09_LIVE_ARTIFACT": str(archive)}, "exactly one of")
    # archive inputs
    check(
        {**good(), "RUSH_T09_LIVE_ARCHIVE": str(tmp_path / "gone.tar.gz")},
        "RUSH_T09_LIVE_ARCHIVE",
    )
    check(
        {k: v for k, v in good().items() if k != "RUSH_T09_LIVE_SUMS"},
        "RUSH_T09_LIVE_SUMS",
    )
    link = tmp_path / "link.tar.gz"
    link.symlink_to(archive)
    check({**good(), "RUSH_T09_LIVE_ARCHIVE": str(link)}, "symlink")
    check({**good(), "RUSH_T09_LIVE_ARCHIVE": str(tmp_path)}, "not a regular file")
    wrong_sums = tmp_path / "SHA256SUMS.wrong"
    wrong_sums.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")
    check(
        {**good(), "RUSH_T09_LIVE_SUMS": str(wrong_sums)},
        "does not match RUSH_T09_LIVE_SUMS",
    )
    extra, extra_sums = _fake_archive(
        tmp_path / "extra",
        members={"rush": b"x", "VERSION": b"1\n", "stowaway": b"y"},
    )
    check(
        {
            **good(),
            "RUSH_T09_LIVE_ARCHIVE": str(extra),
            "RUSH_T09_LIVE_SUMS": str(extra_sums),
        },
        "unexpected archive members",
    )
    evil, evil_sums = _fake_archive(
        tmp_path / "evil", members={"../rush": b"x", "VERSION": b"1\n"}
    )
    check(
        {
            **good(),
            "RUSH_T09_LIVE_ARCHIVE": str(evil),
            "RUSH_T09_LIVE_SUMS": str(evil_sums),
        },
        "path traversal",
    )
    # binary inputs
    binary = tmp_path / "bin" / "rush"
    binary.parent.mkdir()
    binary.write_bytes(b"binary")
    digest = _sha(b"binary")
    mode = {
        "RUSH_T09_LIVE_RECEIPT_DIR": str(receipts),
        "RUSH_T09_LIVE_ARTIFACT": str(binary),
        "RUSH_T09_LIVE_ARTIFACT_SHA256": digest,
    }
    assert (
        _live_inputs(
            mode, workdir=work, repo_root=fake_repo, host_home=str(host_home)
        ).binary_sha256
        == digest
    )
    check(
        {**mode, "RUSH_T09_LIVE_ARTIFACT_SHA256": "0" * 64},
        "does not match RUSH_T09_LIVE_ARTIFACT_SHA256",
    )
    check(
        {k: v for k, v in mode.items() if k != "RUSH_T09_LIVE_ARTIFACT_SHA256"},
        "RUSH_T09_LIVE_ARTIFACT_SHA256",
    )
    check({**mode, "RUSH_T09_LIVE_ARTIFACT": str(binary.parent)}, "not a regular file")
    binary_link = tmp_path / "bin" / "rush-link"
    binary_link.symlink_to(binary)
    check({**mode, "RUSH_T09_LIVE_ARTIFACT": str(binary_link)}, "symlink")
    check(
        {**mode, "RUSH_T09_LIVE_ARTIFACT": str(tmp_path / "bin" / "none")},
        "RUSH_T09_LIVE_ARTIFACT",
    )
    # the selected host CLIs must exist; never deselected
    with pytest.raises(AssertionError, match="claude is not on PATH"):
        _require_agents({"RUSH_T09_LIVE_AGENTS": "1"}, which=lambda _name: None)
    with pytest.raises(AssertionError, match="codex is not on PATH"):
        _require_agents(
            {"RUSH_T09_LIVE_AGENTS": "1"},
            which=lambda name: "/bin/claude" if name == "claude" else None,
        )
    _require_agents({}, which=lambda _name: None)
    # no failure touched the project or the receipt directory
    assert (_tree_digest(project), _tree_digest(receipts)) == before
    # the inputs each native CI job's T09 step supplies are accepted
    ci_problems = _ci_supplied_inputs(tmp_path / "ci-supplied")
    assert not ci_problems, "\n".join(ci_problems)
    # RB-3: an executable that is not this checkout's rush is rejected, by the
    # version it reports and by a required leaf it cannot serve ...
    import rush

    child_env = _child_env()
    wrong_version = [sys.executable, "-c", "print('rush 0.0.0-not-this-checkout')"]
    with pytest.raises(AssertionError):
        _assert_installed_cli_parity(wrong_version, child_env, REQUIRED_LEAVES[:1])
    version_only = [
        sys.executable,
        "-c",
        (
            f"import sys; print('rush {rush.__version__}');"
            "sys.exit(0 if sys.argv[1:] == ['--version'] else 2)"
        ),
    ]
    with pytest.raises(AssertionError) as raised:
        _assert_installed_cli_parity(version_only, child_env, REQUIRED_LEAVES[:1])
    assert "archive" in str(raised.value), raised.value
    # ... and this checkout's installed rush serves every required leaf.
    _assert_installed_cli_parity([_rush_bin()], child_env, REQUIRED_LEAVES)


# ---------------------------------------------------------------------------
# G3 / G4 rows (G15 classes): native paths, hostile text, untyped discriminators,
# deep input, cleanup that must not mask the primary failure
# ---------------------------------------------------------------------------


def _live_env(tmp_path: Path, *, mode: str) -> tuple[dict[str, str], Path, Path]:
    """A valid live environment (`archive` or `binary` mode) with a fake repo
    root and a fake host HOME inside `tmp_path`."""
    fake_repo = tmp_path / "fakerepo"
    host_home = tmp_path / "hosthome"
    receipts = tmp_path / "receipts"
    for path in (fake_repo, host_home, receipts):
        path.mkdir(parents=True, exist_ok=True)
    env = {"RUSH_T09_LIVE_RECEIPT_DIR": str(receipts)}
    if mode == "archive":
        archive, sums = _fake_archive(tmp_path / "good")
        env["RUSH_T09_LIVE_ARCHIVE"] = str(archive)
        env["RUSH_T09_LIVE_SUMS"] = str(sums)
    else:
        binary = tmp_path / "bin" / "rush"
        binary.parent.mkdir()
        binary.write_bytes(b"binary")
        env["RUSH_T09_LIVE_ARTIFACT"] = str(binary)
        env["RUSH_T09_LIVE_ARTIFACT_SHA256"] = _sha(b"binary")
    return env, fake_repo, host_home


@pytest.mark.parametrize(
    ("name", "refused", "in_archive"),
    [
        pytest.param("../secret.txt", True, True, id="native-slash-dotdot-refused"),
        pytest.param("/secret.txt", True, False, id="native-absolute-refused"),
        pytest.param(
            "..\\secret.txt",
            True,
            True,
            marks=pytest.mark.windows_only,
            id="windows-backslash-dotdot-refused",
        ),
        pytest.param(
            "C:secret.txt",
            True,
            True,
            marks=pytest.mark.windows_only,
            id="windows-drive-relative-refused",
        ),
        pytest.param(
            "safe\\..\\..\\secret.txt",
            True,
            True,
            marks=pytest.mark.windows_only,
            id="windows-nested-backslash-dotdot-refused",
        ),
        pytest.param(
            "..\\secret.txt",
            False,
            True,
            marks=pytest.mark.posix_only,
            id="posix-literal-backslash-name-kept",
        ),
        pytest.param(
            "C:secret.txt",
            False,
            True,
            marks=pytest.mark.posix_only,
            id="posix-literal-colon-name-kept",
        ),
        pytest.param(
            "safe\\..\\..\\secret.txt",
            False,
            True,
            marks=pytest.mark.posix_only,
            id="posix-nested-literal-backslash-name-kept",
        ),
    ],
)
def test_t09_native_path_rows(
    tmp_path: Path, name: str, refused: bool, in_archive: bool
) -> None:
    """G15-1: persisted names are read with the host's own path rules. Windows
    refuses a backslash traversal and a drive-relative name; POSIX keeps them
    as literal file names (still refused as archive members, which are exactly
    `VERSION` and the binary)."""
    base = tmp_path / "base"
    base.mkdir()
    if refused:
        with pytest.raises(AssertionError, match="path traversal"):
            _contained_member(base, name)
    else:
        kept = _contained_member(base, name)
        assert kept.parent == base.resolve() and kept.name == name
    assert _tree_digest(base) == []
    if not in_archive:
        return
    zipped = os.name == "nt"
    archive, _sums = _fake_archive(
        tmp_path / "pkg",
        zipped=zipped,
        members={
            "rush.exe" if zipped else "rush": b"x",
            "VERSION": b"1\n",
            name: b"y",
        },
    )
    work = tmp_path / "work"
    needle = "path traversal" if refused else "unexpected archive members"
    with pytest.raises(AssertionError, match=needle):
        _extract_archive(archive, work)
    assert not work.exists()
    assert not (tmp_path / "secret.txt").exists()


@pytest.mark.posix_only
def test_t09_member_symlink_escape_refused(tmp_path: Path) -> None:
    """G15-1: containment is decided on the resolved path, not on the spelling:
    a name that walks through a symlink out of the base is refused."""
    base = tmp_path / "base"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    (base / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AssertionError, match="path traversal"):
        _contained_member(base, "link/secret.txt")
    assert _contained_member(base, "plain/secret.txt").parent.name == "plain"
    assert _tree_digest(outside) == []


_LIVE_FIELDS = (
    pytest.param("RUSH_T09_LIVE_RECEIPT_DIR", "archive", id="receipt-dir"),
    pytest.param("RUSH_T09_LIVE_ARCHIVE", "archive", id="archive"),
    pytest.param("RUSH_T09_LIVE_SUMS", "archive", id="sums"),
    pytest.param("RUSH_T09_LIVE_ARTIFACT", "binary", id="artifact"),
    pytest.param("RUSH_T09_LIVE_ARTIFACT_SHA256", "binary", id="artifact-sha256"),
)
_HOSTILE_VALUES = (
    pytest.param("\ud800bad", "not valid UTF-8", id="lone-surrogate"),
    pytest.param("bad\0name", "NUL character", id="nul-character"),
    pytest.param(["x"], "must be text, got list", id="list"),
    pytest.param({"x": 1}, "must be text, got dict", id="dict"),
)


@pytest.mark.parametrize(("field", "mode"), _LIVE_FIELDS)
@pytest.mark.parametrize(("value", "needle"), _HOSTILE_VALUES)
def test_t09_live_input_text_rows(
    tmp_path: Path, field: str, mode: str, value: object, needle: str
) -> None:
    """G15-2 / G15-3: a live input that is not encodable text fails by name,
    before any filesystem effect, whether it is a path or a checksum."""
    env, fake_repo, host_home = _live_env(tmp_path, mode=mode)
    work = tmp_path / "work"
    before = _tree_digest(tmp_path)
    env[field] = value  # type: ignore[assignment]
    with pytest.raises(AssertionError) as raised:
        _live_inputs(env, workdir=work, repo_root=fake_repo, host_home=str(host_home))
    assert field in str(raised.value) and needle in str(raised.value), raised.value
    assert not work.exists()
    assert _tree_digest(tmp_path) == before


def _good_receipt() -> dict[str, Any]:
    return {
        "lane": "pty-terminal",
        "artifact_sha256": "a" * 64,
        "steps": [
            {
                "step": "S",
                "argv_redacted": "S",
                "transcript_sha256": "b" * 64,
                "observed": "12 characters",
                "expected": "subject rows",
                "independent_check": "MemoryTool readback",
            }
        ],
    }


def _step_with(**changes: object) -> Callable[[dict[str, Any]], object]:
    def transform(receipt: dict[str, Any]) -> object:
        receipt["steps"][0].update(changes)
        return receipt

    return transform


def _drop_step_key(key: str) -> Callable[[dict[str, Any]], object]:
    def transform(receipt: dict[str, Any]) -> object:
        del receipt["steps"][0][key]
        return receipt

    return transform


def _top_with(**changes: object) -> Callable[[dict[str, Any]], object]:
    def transform(receipt: dict[str, Any]) -> object:
        receipt.update(changes)
        return receipt

    return transform


@pytest.mark.parametrize(
    ("transform", "needle"),
    [
        pytest.param(lambda r: [], "receipt must be an object", id="not-an-object"),
        pytest.param(
            _top_with(lane=[]), "receipt lane must be text, got list", id="lane-list"
        ),
        pytest.param(
            _top_with(lane={}), "receipt lane must be text, got dict", id="lane-dict"
        ),
        pytest.param(
            _top_with(lane="no-such-lane"), "unknown receipt lane", id="lane-unknown"
        ),
        pytest.param(
            _top_with(lane="..\\secret.txt"),
            "unknown receipt lane",
            id="lane-traversal",
        ),
        pytest.param(
            _top_with(lane="\ud800"),
            "receipt lane is not valid UTF-8",
            id="lane-surrogate",
        ),
        pytest.param(
            _top_with(artifact_sha256="zz"),
            "receipt artifact_sha256 must be a sha256",
            id="artifact-hash-not-hex",
        ),
        pytest.param(
            _top_with(artifact_sha256=[]),
            "receipt artifact_sha256 must be a sha256",
            id="artifact-hash-list",
        ),
        pytest.param(
            _top_with(archive_sha256={}),
            "receipt archive_sha256 must be a sha256",
            id="archive-hash-dict",
        ),
        pytest.param(
            _top_with(steps=[]),
            "receipt steps must be a non-empty list",
            id="steps-empty",
        ),
        pytest.param(
            _top_with(steps={}),
            "receipt steps must be a non-empty list",
            id="steps-dict",
        ),
        pytest.param(
            _top_with(steps=[[]]), "receipt steps[0] must be an object", id="step-list"
        ),
        pytest.param(
            _drop_step_key("independent_check"),
            "receipt steps[0].independent_check is missing",
            id="step-key-missing",
        ),
        pytest.param(
            _step_with(transcript_sha256="nope"),
            "receipt steps[0].transcript_sha256 must be a sha256",
            id="step-hash-not-hex",
        ),
        pytest.param(
            _step_with(observed=7),
            "receipt steps[0].observed must be text, got int",
            id="observed-int",
        ),
        pytest.param(
            _step_with(observed=["ok", {}]),
            "receipt steps[0].observed must be text, got dict",
            id="observed-list-with-dict",
        ),
        pytest.param(
            _step_with(step="\ud800"),
            "receipt steps[0].step is not valid UTF-8",
            id="step-surrogate",
        ),
    ],
)
def test_t09_receipt_shape_rows(
    transform: Callable[[dict[str, Any]], object], needle: str
) -> None:
    """G4 / G15-2 / G15-3: a malformed receipt fails with the field named; an
    untyped value never reaches a set or dict membership test."""
    _validate_receipt(_good_receipt())
    with pytest.raises(AssertionError) as raised:
        _validate_receipt(transform(_good_receipt()))
    assert needle in str(raised.value), (needle, str(raised.value))


def test_t09_receipt_write_and_read_rows(tmp_path: Path) -> None:
    """G4 / G15-3 / G15-4: a rejected receipt leaves the directory untouched; an
    unreadable, undecodable, malformed or absurdly nested receipt file fails by
    name instead of raising a raw decode or recursion error."""
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    inputs = _LiveInputs(Path("rush"), "a" * 64, None, None, receipts)
    steps = _good_receipt()["steps"]
    written = _write_receipt(inputs, "pty-terminal", steps)
    assert written == receipts / "pty-terminal.json"
    assert _read_receipt(written)["steps"] == steps
    before = _tree_digest(receipts)

    for lane, needle in (
        ([], "receipt lane must be text, got list"),
        ({}, "receipt lane must be text, got dict"),
        ("..\\secret.txt", "unknown receipt lane"),
        ("\ud800", "receipt lane is not valid UTF-8"),
    ):
        with pytest.raises(AssertionError, match=re.escape(needle)):
            _write_receipt(inputs, lane, steps)  # type: ignore[arg-type]
    with pytest.raises(AssertionError, match=r"steps\[0\]\.step is not valid UTF-8"):
        _write_receipt(inputs, "pas-import", [{**steps[0], "step": "\ud800"}])
    with pytest.raises(AssertionError, match="steps must be a non-empty list"):
        _write_receipt(inputs, "pas-import", [])
    assert _tree_digest(receipts) == before

    broken = receipts / "broken.json"
    for payload, needle in (
        (b"\xff\xfe{", "receipt is not valid UTF-8 text"),
        (b"{", "not valid JSON"),
        (b"[" * 200_000, "JSON nested too deeply"),
        (b"[]", "receipt must be an object"),
    ):
        broken.write_bytes(payload)
        with pytest.raises(AssertionError) as raised:
            _read_receipt(broken)
        assert "broken.json" in str(raised.value) or "receipt" in str(raised.value)
        assert needle in str(raised.value), (needle, str(raised.value))


@pytest.mark.parametrize(
    "value", [pytest.param([], id="list"), pytest.param({}, id="dict")]
)
@pytest.mark.parametrize(
    "field",
    [
        pytest.param("transport", id="transport"),
        pytest.param("operation", id="operation"),
        pytest.param("representation", id="representation"),
        pytest.param("subject", id="subject"),
        pytest.param("lane", id="lane"),
    ],
)
def test_t09_discriminator_rows(tmp_path: Path, field: str, value: object) -> None:
    """G15-2: an untyped discriminator is refused by name before any request
    file, store or receipt is created; it never reaches a dict or set lookup."""
    ctx = _Ctx(tmp=tmp_path, exe=["rush"], env={})
    before = _tree_digest(tmp_path)
    calls: dict[str, Callable[[], object]] = {
        "transport": lambda: ctx.call(value, tmp_path, "list", {}),  # type: ignore[arg-type]
        "operation": lambda: ctx.call("dashboard", tmp_path, value, {}),  # type: ignore[arg-type]
        "representation": lambda: ctx.expand(
            "inproc",
            tmp_path,
            "a",
            1,
            representation=value,  # type: ignore[arg-type]
        ),
        "subject": lambda: ctx.list_items("cli", tmp_path, value),  # type: ignore[arg-type]
        "lane": lambda: _receipt_destination(tmp_path, value),
    }
    with pytest.raises(
        AssertionError, match=f"{field} must be text, got {type(value).__name__}"
    ):
        calls[field]()
    assert _tree_digest(tmp_path) == before


def _nested_ifs(depth: int) -> str:
    lines = ["if x:"]
    lines += [" " * level + "if x:" for level in range(1, depth)]
    lines.append(" " * depth + "pass")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("source", "needle"),
    [
        pytest.param("def (:\n", "cannot parse (SyntaxError)", id="syntax-error"),
        pytest.param(
            "x = " + "(" * 400 + ")" * 400,
            "cannot parse (SyntaxError)",
            id="nested-parentheses",
        ),
        pytest.param(
            "x = " + "+".join(["1"] * 50_000),
            "cannot parse (RecursionError)",
            id="deep-expression",
        ),
        pytest.param(
            "x = a" + ".b" * 50_000,
            "cannot parse (RecursionError)",
            id="deep-attribute-chain",
        ),
        pytest.param("x = 1\0\n", "cannot parse", id="nul-byte"),
        pytest.param(_nested_ifs(150), "cannot parse", id="too-deep-indentation"),
        pytest.param(_nested_ifs(60), None, id="nested-ifs-within-limit"),
    ],
)
def test_t09_source_reader_rows(source: str, needle: str | None) -> None:
    """G15-4: the R9 reader turns a hostile test source into a controlled
    failure naming the file; a deep but legal nesting is traversed."""
    rel = "tests/test_demo.py"
    if needle is None:
        assert _windows_only_nodes(rel, source=source) == ([], [])
        return
    with pytest.raises(AssertionError) as raised:
        _windows_only_nodes(rel, source=source)
    message = str(raised.value)
    assert message.startswith(rel) and needle in message, message


def test_t09_cleanup_keeps_primary_failure(tmp_path: Path) -> None:
    """G15-5: cleanup runs every owned step, fails alone with its own cause, and
    never replaces the failure already propagating; both causes stay in one
    diagnostic, and only the session's own child is stopped."""
    ran: list[str] = []

    def good() -> None:
        ran.append("good")

    def bad() -> None:
        ran.append("bad")
        raise OSError("cleanup boom")

    def last() -> None:
        ran.append("last")

    none = (None, None, None)
    with pytest.raises(AssertionError, match=r"cleanup failed \(bad: OSError") as alone:
        _run_cleanups(none, good, bad, last)
    assert ran == ["good", "bad", "last"] and alone.value.__cause__ is None
    ran.clear()
    primary = AssertionError("driver step failed")
    _run_cleanups((AssertionError, primary, None), good, last)
    assert ran == ["good", "last"]
    with pytest.raises(AssertionError) as both:
        _run_cleanups((AssertionError, primary, None), bad, good)
    assert "cleanup boom" in str(both.value) and "driver step failed" in str(both.value)
    assert both.value.__cause__ is primary

    def worse() -> None:
        raise ValueError("second boom")

    with pytest.raises(AssertionError) as every:
        _run_cleanups((AssertionError, primary, None), bad, worse, good)
    for cause in ("bad: OSError: cleanup boom", "worse: ValueError: second boom"):
        assert cause in str(every.value), every.value
    assert "driver step failed" in str(every.value)

    class ExplodingFile:
        def close(self) -> None:
            raise RuntimeError("close boom")

    owned = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=subprocess.PIPE,
        text=True,
    )
    sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        session = _McpSession([sys.executable], tmp_path, {})
        session._proc = owned
        session._stderr_file = ExplodingFile()  # type: ignore[assignment]
        session._stderr_path = tmp_path / "stderr.log"
        session._stderr_path.write_text("log", encoding="utf-8")
        with pytest.raises(AssertionError) as masked:
            session.__exit__(AssertionError, primary, None)
        assert "close_stderr: RuntimeError: close boom" in str(masked.value)
        assert "driver step failed" in str(masked.value)
        assert masked.value.__cause__ is primary
        assert owned.poll() is not None, "the session's own child was not stopped"
        assert not session._stderr_path.exists(), "later cleanup steps did not run"
        assert sibling.poll() is None, "cleanup touched a process it does not own"
    finally:
        sibling.kill()
        sibling.wait(timeout=10)
        if owned.poll() is None:
            owned.kill()
            owned.wait(timeout=10)


# ---------------------------------------------------------------------------
# RB-1 / G15-6 / G15-7: the frozen source trees, as three independent views
# ---------------------------------------------------------------------------

FREEZE_DIRS = ("src", "tests", "scripts", ".github")


def _git(
    repo: Path, *args: str, stdin: bytes | None = None, check: bool = True
) -> bytes:
    env = dict(os.environ)
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "t09",
            "GIT_AUTHOR_EMAIL": "t09@example.invalid",
            "GIT_COMMITTER_NAME": "t09",
            "GIT_COMMITTER_EMAIL": "t09@example.invalid",
            "LC_ALL": "C",
        }
    )
    proc = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=off",
            "-c",
            "core.autocrlf=false",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        env=env,
        input=stdin,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if check:
        assert proc.returncode == 0, (
            f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace')[:500]}"
        )
    return proc.stdout


def _nul_split(data: bytes) -> list[str]:
    return [
        item.decode("utf-8", "surrogateescape") for item in data.split(b"\0") if item
    ]


def _head_listing(repo: Path, directory: str) -> list[str]:
    """HEAD's files under `directory` as `<mode> <blob> 0\t<path>`."""
    lines = []
    for entry in _nul_split(_git(repo, "ls-tree", "-r", "-z", "HEAD", "--", directory)):
        meta, path = entry.split("\t", 1)
        mode, _kind, blob = meta.split()
        lines.append(f"{mode} {blob} 0\t{path}")
    return sorted(lines)


def _index_listing(repo: Path, directory: str) -> list[str]:
    """The index entries under `directory`, stage included."""
    return sorted(_nul_split(_git(repo, "ls-files", "-s", "-z", "--", directory)))


def _worktree_listing(repo: Path, directory: str) -> list[str]:
    """The files on disk under `directory` (tracked or untracked, not ignored),
    in the same line format: mode from the disk entry, blob from its bytes (a
    symlink hashes its target text)."""
    paths = sorted(
        set(
            _nul_split(
                _git(
                    repo,
                    "ls-files",
                    "-z",
                    "-c",
                    "-o",
                    "--exclude-standard",
                    "--",
                    directory,
                )
            )
        )
    )
    files: list[tuple[str, str]] = []
    links: list[tuple[str, str]] = []
    for rel in paths:
        assert "\n" not in rel, f"{rel!r} holds a newline"
        full = repo / rel
        if full.is_symlink():
            links.append((rel, "120000"))
        elif full.is_file():
            executable = os.name != "nt" and bool(full.stat().st_mode & 0o111)
            files.append((rel, "100755" if executable else "100644"))
    lines = []
    if files:
        blobs = (
            _git(
                repo,
                "hash-object",
                "--no-filters",
                "--stdin-paths",
                stdin="\n".join(rel for rel, _mode in files).encode(
                    "utf-8", "surrogateescape"
                ),
            )
            .decode("ascii")
            .split()
        )
        assert len(blobs) == len(files)
        lines += [
            f"{mode} {blob} 0\t{rel}"
            for (rel, mode), blob in zip(files, blobs, strict=True)
        ]
    for rel, mode in links:
        blob = (
            _git(
                repo,
                "hash-object",
                "--stdin",
                stdin=os.fsencode(os.readlink(repo / rel)),
            )
            .decode("ascii")
            .strip()
        )
        lines.append(f"{mode} {blob} 0\t{rel}")
    return sorted(lines)


def _freeze_views(repo: Path, directory: str) -> dict[str, list[str]]:
    return {
        "head": _head_listing(repo, directory),
        "staged": _index_listing(repo, directory),
        "worktree": _worktree_listing(repo, directory),
    }


def _head_tree(repo: Path, directory: str) -> str:
    out = _git(repo, "rev-parse", "--verify", "-q", f"HEAD:{directory}", check=False)
    return out.decode("ascii").strip() or "absent"


def _freeze_trees(repo: Path) -> dict[str, str]:
    return {directory: _head_tree(repo, directory) for directory in FREEZE_DIRS}


def _freeze_snapshot(repo: Path) -> dict[tuple[str, str], str]:
    """The freeze oracle: one digest per (view, directory). The head view is the
    tree id; the staged view hashes every index entry with its stage; the
    worktree view hashes every file's mode and bytes, every symlink target and
    every untracked file, so any change to one view is visible on its own."""
    snapshot: dict[tuple[str, str], str] = {}
    for directory in FREEZE_DIRS:
        views = _freeze_views(repo, directory)
        snapshot["head", directory] = _head_tree(repo, directory)
        snapshot["staged", directory] = _sha("\n".join(views["staged"]))
        snapshot["worktree", directory] = _sha("\n".join(views["worktree"]))
    return snapshot


def _freeze_findings(repo: Path, recorded: Mapping[str, str]) -> list[tuple[str, str]]:
    """`(view, directory)` for every view that no longer equals the freeze: the
    HEAD tree against the recorded tree, and the index and the working tree
    against HEAD. Checking HEAD alone is not enough."""
    found = []
    for directory in FREEZE_DIRS:
        if _head_tree(repo, directory) != recorded[directory]:
            found.append(("head", directory))
        views = _freeze_views(repo, directory)
        if views["staged"] != views["head"]:
            found.append(("staged", directory))
        if views["worktree"] != views["head"]:
            found.append(("worktree", directory))
    return found


def _freeze_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    files = {
        ".gitignore": "__pycache__/\n",
        "src/a.py": "A = 1\n",
        "src/b.py": "B = 2\n",
        "tests/test_a.py": "def test_a():\n    assert True\n",
        "scripts/run.py": "print('run')\n",
        ".github/ci.yml": "name: ci\n",
    }
    repo.mkdir()
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "--", *files)
    _git(repo, "commit", "-q", "-m", "freeze")
    return repo


def _write(repo: Path, rel: str, text: str = "changed\n") -> None:
    (repo / rel).write_text(text, encoding="utf-8")


def _stage_then_restore(repo: Path, rel: str, text: bytes | str) -> None:
    original = (repo / rel).read_bytes()
    (repo / rel).write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    _git(repo, "add", "--", rel)
    (repo / rel).write_bytes(original)


def _mutate_worktree_changed(rel: str) -> Callable[[Path], None]:
    return lambda repo: _write(repo, rel)


def _mutate_committed(repo: Path) -> None:
    _write(repo, "src/a.py")
    _git(repo, "add", "--", "src/a.py")
    _git(repo, "commit", "-q", "-m", "after the freeze")


def _mutate_deleted(repo: Path) -> None:
    (repo / "src/b.py").unlink()


def _mutate_staged_deletion(repo: Path) -> None:
    _git(repo, "rm", "--cached", "-q", "--", "src/b.py")


def _mutate_duplicated(repo: Path) -> None:
    shutil.copyfile(repo / "src/a.py", repo / "src/a_copy.py")


def _mutate_duplicated_staged_removed(repo: Path) -> None:
    shutil.copyfile(repo / "src/a.py", repo / "src/a_copy.py")
    _git(repo, "add", "--", "src/a_copy.py")
    (repo / "src/a_copy.py").unlink()


def _mutate_unparseable_worktree(repo: Path) -> None:
    (repo / "src/a.py").write_bytes(b"def (:\n\xff\x00")


def _mutate_unparseable_staged(repo: Path) -> None:
    _stage_then_restore(repo, "src/a.py", b"def (:\n\xff\x00")


def _mutate_staged_changed(repo: Path) -> None:
    _stage_then_restore(repo, "src/a.py", "changed\n")


def _mutate_restage(repo: Path) -> None:
    _git(repo, "add", "--", "src/a.py")


def _mutate_ignored(repo: Path) -> None:
    cache = repo / "src/__pycache__"
    cache.mkdir()
    (cache / "a.cpython-312.pyc").write_bytes(b"\0")


def _mutate_conflict_stage(repo: Path) -> None:
    blob = _git(repo, "rev-parse", "HEAD:src/a.py").decode("ascii").strip()
    _git(
        repo,
        "update-index",
        "--index-info",
        stdin=f"0 {'0' * 40}\tsrc/a.py\n100644 {blob} 1\tsrc/a.py\n".encode("ascii"),
    )


def _mutate_chmod_worktree(repo: Path) -> None:
    (repo / "src/a.py").chmod(0o755)


def _mutate_chmod_staged(repo: Path) -> None:
    _git(repo, "update-index", "--chmod=+x", "--", "src/a.py")


def _mutate_symlink_worktree(repo: Path) -> None:
    (repo / "src/a.py").unlink()
    (repo / "src/a.py").symlink_to("b.py")


def _mutate_symlink_staged(repo: Path) -> None:
    original = (repo / "src/a.py").read_bytes()
    (repo / "src/a.py").unlink()
    (repo / "src/a.py").symlink_to("b.py")
    _git(repo, "add", "--", "src/a.py")
    (repo / "src/a.py").unlink()
    (repo / "src/a.py").write_bytes(original)


_NONE: frozenset[tuple[str, str]] = frozenset()


def _only(view: str, directory: str = "src") -> frozenset[tuple[str, str]]:
    return frozenset({(view, directory)})


@pytest.mark.parametrize(
    ("mutate", "changed", "found"),
    [
        pytest.param(lambda repo: None, _NONE, _NONE, id="control-untouched"),
        pytest.param(_mutate_restage, _NONE, _NONE, id="restage-unchanged-bytes"),
        pytest.param(
            _mutate_ignored, _NONE, _NONE, id="ignored-bytecode-is-not-source"
        ),
        pytest.param(
            _mutate_worktree_changed("src/a.py"),
            _only("worktree"),
            _only("worktree"),
            id="worktree-changed-src",
        ),
        pytest.param(
            _mutate_worktree_changed("tests/test_a.py"),
            _only("worktree", "tests"),
            _only("worktree", "tests"),
            id="worktree-changed-tests",
        ),
        pytest.param(
            _mutate_worktree_changed("scripts/run.py"),
            _only("worktree", "scripts"),
            _only("worktree", "scripts"),
            id="worktree-changed-scripts",
        ),
        pytest.param(
            _mutate_worktree_changed(".github/ci.yml"),
            _only("worktree", ".github"),
            _only("worktree", ".github"),
            id="worktree-changed-github",
        ),
        pytest.param(
            _mutate_staged_changed,
            _only("staged"),
            _only("staged"),
            id="staged-changed-only",
        ),
        pytest.param(
            _mutate_committed,
            frozenset({("head", "src"), ("staged", "src"), ("worktree", "src")}),
            _only("head"),
            id="committed-after-freeze",
        ),
        pytest.param(
            _mutate_deleted,
            _only("worktree"),
            _only("worktree"),
            id="deleted-in-worktree",
        ),
        pytest.param(
            _mutate_staged_deletion,
            _only("staged"),
            _only("staged"),
            id="deleted-in-index-file-kept",
        ),
        pytest.param(
            _mutate_duplicated,
            _only("worktree"),
            _only("worktree"),
            id="duplicated-untracked",
        ),
        pytest.param(
            _mutate_duplicated_staged_removed,
            _only("staged"),
            _only("staged"),
            id="duplicated-staged-then-removed",
        ),
        pytest.param(
            _mutate_unparseable_worktree,
            _only("worktree"),
            _only("worktree"),
            id="unparseable-source-worktree-only",
        ),
        pytest.param(
            _mutate_unparseable_staged,
            _only("staged"),
            _only("staged"),
            id="unparseable-source-staged-only",
        ),
        pytest.param(
            _mutate_conflict_stage,
            _only("staged"),
            _only("staged"),
            id="index-conflict-stage",
        ),
        pytest.param(
            _mutate_chmod_worktree,
            _only("worktree"),
            _only("worktree"),
            marks=pytest.mark.posix_only,
            id="mode-changed-worktree-only",
        ),
        pytest.param(
            _mutate_chmod_staged,
            _only("staged"),
            _only("staged"),
            marks=pytest.mark.posix_only,
            id="mode-changed-staged-only",
        ),
        pytest.param(
            _mutate_symlink_worktree,
            _only("worktree"),
            _only("worktree"),
            marks=pytest.mark.posix_only,
            id="symlinked-source-worktree-only",
        ),
        pytest.param(
            _mutate_symlink_staged,
            _only("staged"),
            _only("staged"),
            marks=pytest.mark.posix_only,
            id="symlinked-source-staged-only",
        ),
    ],
)
def test_t09_freeze_fixture_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[Path], None],
    changed: frozenset[tuple[str, str]],
    found: frozenset[tuple[str, str]],
) -> None:
    """G15-6 / G15-7: in an isolated Git fixture, a change confined to one view
    (HEAD tree, index with stage, working tree bytes, mode, symlink target,
    untracked or ignored file) moves exactly that view's snapshot digest, and
    the freeze check names exactly the views that no longer equal the freeze."""
    _isolate(tmp_path, monkeypatch)
    repo = _freeze_fixture(tmp_path)
    recorded = _freeze_trees(repo)
    before = _freeze_snapshot(repo)
    assert _freeze_findings(repo, recorded) == []
    mutate(repo)
    after = _freeze_snapshot(repo)
    assert frozenset(key for key in before if before[key] != after[key]) == changed
    assert frozenset(_freeze_findings(repo, recorded)) == found


def test_t09_freeze_source_views() -> None:
    """RB-1: the trees the report records for `src`, `tests`, `scripts` and
    `.github` are the trees at HEAD, and the index and the working tree equal
    HEAD for those directories (all three views, not HEAD alone)."""
    assert REPORT.is_file(), f"{REPORT.relative_to(REPO)} does not exist"
    source = _sections(REPORT.read_text(encoding="utf-8")).get("## Source hash", "")
    recorded = {}
    for directory in FREEZE_DIRS:
        match = re.search(
            rf"^tree\.{re.escape(directory)}: ([0-9a-f]{{40}})$", source, re.MULTILINE
        )
        assert match, f"## Source hash has no tree.{directory} line"
        recorded[directory] = match.group(1)
    findings = _freeze_findings(REPO, recorded)
    assert not findings, "\n".join(
        f"{view} view of {directory} differs from the freeze"
        for view, directory in findings
    )


# ---------------------------------------------------------------------------
# live lanes: terminal script shared by the PTY and the Windows console driver
# ---------------------------------------------------------------------------

_FAMILY_BY_SUBJECT = {
    "active_context": "handoff",
    "episodic": "experience",
    "preference": "memory",
    "failure": "memory",
    "architectural_decision": "memory",
    "domain_knowledge": "memory",
    "skill_pattern": "skill",
}
HOSTILE_TEXT = "\x1b[2K\r\x07HOSTILEMARK"
# bidi override: 72-T01 blocks such a row from ordinary and inspect reads
# (`integrity_trojan_source`), so it must never be listed or rendered.
BIDI_TEXT = "\u202eBIDIMARK"
_NAMED_KEYS = {
    "enter": "\r",
    "tab": "\t",
    "escape": "\x1b",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
}


def _installed_env() -> dict[str, str]:
    """Environment for an installed artifact: no source path leaks in."""
    env = dict(os.environ)
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"):
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _redact_text(text: str, tmp: Path) -> str:
    out = text.replace(str(tmp), "<tmp>")
    return re.sub(r"\b([0-9a-f]{8})[0-9a-f-]{8,}\b", r"\1…", out)


_HEX64 = re.compile(r"[0-9a-f]{64}")


def _receipt_destination(receipt_dir: Path, lane: object) -> Path:
    return receipt_dir / f"{_choice('receipt lane', lane, LANES)}.json"


def _validate_receipt(receipt: object) -> dict[str, Any]:
    """The shape of a machine receipt; every failure names the field."""
    assert isinstance(receipt, dict), (
        f"receipt must be an object, got {type(receipt).__name__}"
    )
    _choice("receipt lane", receipt.get("lane"), LANES)
    for key, required in (("artifact_sha256", True), ("archive_sha256", False)):
        if required or key in receipt:
            digest = receipt.get(key)
            assert isinstance(digest, str) and _HEX64.fullmatch(digest), (
                f"receipt {key} must be a sha256"
            )
    if "version" in receipt:
        _text_input("receipt version", receipt["version"])
    steps = receipt.get("steps")
    assert isinstance(steps, list) and steps, "receipt steps must be a non-empty list"
    for index, step in enumerate(steps):
        where = f"steps[{index}]"
        assert isinstance(step, dict), f"receipt {where} must be an object"
        for key in ("step", "argv_redacted", "expected", "independent_check"):
            assert key in step, f"receipt {where}.{key} is missing"
            _text_input(f"receipt {where}.{key}", step[key])
        assert "transcript_sha256" in step, (
            f"receipt {where}.transcript_sha256 is missing"
        )
        digest = step["transcript_sha256"]
        assert isinstance(digest, str) and _HEX64.fullmatch(digest), (
            f"receipt {where}.transcript_sha256 must be a sha256"
        )
        assert "observed" in step, f"receipt {where}.observed is missing"
        observed = step["observed"]
        for item in observed if isinstance(observed, list) else [observed]:
            _text_input(f"receipt {where}.observed", item)
    return receipt


def _read_receipt(path: Path) -> dict[str, Any]:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise AssertionError(f"{path.name}: receipt is not valid UTF-8 text") from None
    return _validate_receipt(_loads_json(text, f"{path.name}: receipt"))


def _write_receipt(
    inputs: _LiveInputs, lane: str, steps: Sequence[Mapping[str, Any]]
) -> Path:
    """One machine-generated receipt: validated, written, re-read, compared,
    announced. A rejected receipt leaves the receipt directory untouched."""
    path = _receipt_destination(inputs.receipt_dir, lane)
    receipt: dict[str, Any] = {
        "lane": lane,
        "artifact_sha256": inputs.binary_sha256,
        "steps": [dict(step) for step in steps],
    }
    if inputs.archive_sha256:
        receipt["archive_sha256"] = inputs.archive_sha256
    if inputs.version:
        receipt["version"] = inputs.version
    _validate_receipt(receipt)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    assert _read_receipt(path) == receipt
    print(f"T09_RECEIPT={path} sha256={_sha_file(path)}")
    return path


def _trace_steps(
    ctx: _Ctx,
    tmp: Path,
    expectations: Mapping[str, str],
    transports: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Receipt steps from the recorded calls, grouped per scenario step."""
    steps = []
    for label, expected in expectations.items():
        entries = [
            e
            for e in ctx.trace
            if e["step"] == label
            and (transports is None or e["transport"] in transports)
        ]
        assert entries, f"no recorded call for step {label!r}"
        steps.append(
            {
                "step": label,
                "argv_redacted": _redact_text(
                    "; ".join(f"{e['transport']} {e['operation']}" for e in entries),
                    tmp,
                ),
                "transcript_sha256": _sha(
                    "".join(str(e["result_sha256"]) for e in entries)
                ),
                "observed": [str(e.get("code")) for e in entries],
                "expected": expected,
                "independent_check": "persisted sqlite rows and file digests read back",
            }
        )
    return steps


def _row_versions(db: Path) -> dict[str, int]:
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return {
            str(row[0]): int(row[1])
            for row in conn.execute("SELECT id, artifact_version FROM memory_artifacts")
        }


def _seed_terminal_rows(w: _World) -> dict[str, Any]:
    """One row per subject, 22 paging rows and one hostile row in P1."""
    subjects: dict[str, str] = {}
    for index, subject in enumerate(SEVEN_SUBJECTS):
        row_id = f"{index}{uuid.uuid4().hex[:11]}"
        _seed_row(
            w.p1,
            row_id,
            f"terminal marker {subject}",
            source="s1",
            subject=subject,
            family=_FAMILY_BY_SUBJECT[subject],
        )
        subjects[subject] = row_id
    paging = []
    for number in range(22):
        row_id = f"9{uuid.uuid4().hex[:11]}"
        _seed_row(
            w.p1,
            row_id,
            f"needle page {number:02d}",
            source="s1",
            subject="domain_knowledge",
            family="memory",
        )
        paging.append(row_id)
    hostile = f"h{uuid.uuid4().hex[:11]}"
    _seed_row(
        w.p1,
        hostile,
        "",
        source="s1",
        subject="failure",
        family="memory",
        content={"text": HOSTILE_TEXT},
    )
    bidi = f"b{uuid.uuid4().hex[:11]}"
    _seed_row(
        w.p1,
        bidi,
        "",
        source="s1",
        subject="failure",
        family="memory",
        content={"text": BIDI_TEXT},
    )
    return {"subjects": subjects, "paging": paging, "hostile": hostile, "bidi": bidi}


class _PtyTerminal:
    """`<artifact> ui <project>` on a pseudo-terminal (POSIX)."""

    def __init__(self, argv: Sequence[str], env: Mapping[str, str], cwd: Path) -> None:
        self._argv = list(argv)
        self._env = dict(env)
        self._cwd = cwd
        self._master = -1
        self._proc: subprocess.Popen[bytes] | None = None
        self.last_raw = ""

    def __enter__(self) -> Self:
        import fcntl
        import pty
        import struct
        import termios

        master, slave = pty.openpty()
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 45, 150, 0, 0))
        code = (
            "import fcntl, os, sys, termios\n"
            "fcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
            "argv = sys.argv[1:]\n"
            "os.execv(argv[0], argv)\n"
        )
        env = dict(self._env)
        env["TERM"] = "xterm-256color"
        env.pop("NO_COLOR", None)
        self._proc = subprocess.Popen(
            [sys.executable, "-c", code, *self._argv],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            cwd=self._cwd,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave)
        self._master = master
        return self

    def __exit__(self, *exc: object) -> None:
        proc = self._proc
        assert proc is not None

        # Closing the master first hangs the child up; a child blocked writing
        # to an unread pty could otherwise survive terminate() and kill().
        def close_master() -> None:
            with contextlib.suppress(OSError):
                os.close(self._master)

        def stop_child() -> None:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)

        _run_cleanups(exc, close_master, stop_child)

    def press(self, *tokens: str) -> None:
        for token in tokens:
            data = _NAMED_KEYS.get(token, token)
            os.write(self._master, data.encode("utf-8"))
            time.sleep(0.05)

    def observe(self, quiet: float = 0.8, limit: float = 20.0) -> str:
        import select

        chunks: list[bytes] = []
        deadline = time.monotonic() + limit
        last = time.monotonic()
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self._master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(self._master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
                last = time.monotonic()
            elif chunks and time.monotonic() - last >= quiet:
                break
        self.last_raw = b"".join(chunks).decode("utf-8", errors="replace")
        return _strip_ansi(self.last_raw)

    def exited(self, timeout: float = 15.0) -> bool:
        assert self._proc is not None
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        return True


def _terminal_step(
    term: Any, receipts: list[dict[str, Any]], label: str, expected: str, *tokens: str
) -> str:
    term.press(*tokens)
    text = term.observe()
    receipts.append(
        {
            "step": label,
            "argv_redacted": " ".join(
                t if t in _NAMED_KEYS or len(t) == 1 else f"text({len(t)})"
                for t in tokens
            ),
            "transcript_sha256": _sha(text),
            "observed": f"{len(text)} characters",
            "expected": expected,
            "independent_check": "MemoryTool and sqlite readback in the driver",
        }
    )
    return text


def _run_terminal_script(
    make_term: Callable[[Path], Any],
    w: _World,
    seeded: Mapping[str, Any],
    receipts: list[dict[str, Any]],
) -> None:
    """The grant-controlled TUI journey: seven subjects, search, paging, exact
    expansion, history, hostile text, correction, cancel, conflict, revocation,
    expiry. Each observed state is compared with a persisted readback."""
    db = w.p1 / ".rush" / "memory.db"
    subjects: Mapping[str, str] = seeded["subjects"]
    paging: Sequence[str] = seeded["paging"]
    hostile: str = seeded["hostile"]

    with make_term(w.p1) as term:
        term.observe(quiet=2.0, limit=60.0)  # first frame
        text = _terminal_step(
            term, receipts, "memory-section", "Memory section opens", "M"
        )
        assert "emory" in text, text[-800:]

        seen: set[str] = set()
        for _ in SEVEN_SUBJECTS:
            text = _terminal_step(
                term, receipts, "subject-cycle", "next subject lists", "S"
            )
            seen.update(s for s, rid in subjects.items() if rid[:8] in text)
        assert seen == set(SEVEN_SUBJECTS), (
            f"subjects never listed: {set(SEVEN_SUBJECTS) - seen}"
        )

        # hostile text renders as literal escapes (cycle until the failure rows)
        for _ in SEVEN_SUBJECTS:
            if hostile[:8] in text:
                break
            text = _terminal_step(
                term, receipts, "hostile-row", "failure rows list", "S"
            )
        assert hostile[:8] in text, "hostile row never listed"
        raw = getattr(term, "last_raw", text)
        assert HOSTILE_TEXT not in raw, "hostile control bytes reached the terminal"
        assert "\x07" not in text and "\u202e" not in raw, "raw control text rendered"
        assert "HOSTILEMARK" in text
        assert re.search(r"\\x1b|\\u001b|\\033|\\e|\u241b", text), text[-800:]
        assert seeded["bidi"][:8] not in text and "BIDIMARK" not in text, (
            "a bidi-override row must stay out of ordinary reads"
        )

        for _ in SEVEN_SUBJECTS:
            if any(p[:8] in text for p in paging):
                break
            text = _terminal_step(
                term, receipts, "to-domain", "domain_knowledge lists", "S"
            )
        first_page = _terminal_step(
            term, receipts, "search", "query lists matches", "/", "needle", "enter"
        )
        assert any(p[:8] in first_page for p in paging), first_page[-800:]
        second_page = _terminal_step(
            term, receipts, "page-forward", "next page differs", "]"
        )
        assert second_page != first_page
        _terminal_step(term, receipts, "page-back", "first page returns", "[")
        expanded = _terminal_step(
            term, receipts, "expand", "exact version expands", "x"
        )
        assert any(p[:8] in expanded for p in paging)
        _terminal_step(term, receipts, "history", "history opens", "v")
        _terminal_step(term, receipts, "explain", "explain opens", "E")

        before = _row_versions(db)
        digest_before = _sha_file(db)
        _terminal_step(
            term, receipts, "correct-cancel", "cancel writes nothing", "c", "escape"
        )
        assert _sha_file(db) == digest_before, "a cancelled correction wrote"

        _terminal_step(
            term,
            receipts,
            "correct-apply",
            "version n+1 persisted",
            "c",
            "tab",
            "tab",
            "corrected by terminal",
            "enter",
            "y",
        )
        after = _row_versions(db)
        bumped = [
            rid for rid, version in after.items() if version == before.get(rid, 0) + 1
        ]
        assert len(bumped) == 1, (before, after)
        corrected = bumped[0]
        assert "corrected by terminal" in _version_content(
            db, corrected, after[corrected]
        )

        # concurrent edit between opening the form and applying it: conflict,
        # the typed input stays
        term.press("c", "tab", "tab", "typed after conflict")
        term.observe()
        concurrent = _raw(
            MemoryTool().run(
                w.p1,
                operation="edit",
                request={
                    "schema_version": 2,
                    "subject": "domain_knowledge",
                    "artifact_id": corrected,
                    "expected_version": after[corrected],
                    "content": {"text": "concurrent edit"},
                    "apply": True,
                    "invocation_id": _uid(),
                    "effect_id": _uid(),
                },
                permissions=ExecutionPermissions(cache_write=True),
            )
        )
        assert concurrent.get("code") == "OK", concurrent
        text = _terminal_step(
            term, receipts, "correct-conflict", "conflict keeps input", "enter", "y"
        )
        assert "conflict" in text.lower(), text[-800:]
        assert "typed after conflict" in text, text[-800:]
        term.press("escape")
        term.observe()

        _revoke(w.grants["p1"], w.data_root)
        text = _terminal_step(term, receipts, "revoked", "revoked state shown", "S")
        assert "revoked" in text.lower(), text[-800:]
        term.press("q")
        term.observe()

    # an expired grant: its own short-lived project
    from rush.memory import authorization as auth

    expiring = _register(w.tmp / "p4", w.data_root)
    auth.grant_memory_scope(
        project_root=expiring,
        owner_scope=legacy_owner_scope(expiring),
        approved_sources=["s1"],
        allowed_operations=list(PROJECT_OPS),
        expected_policy_revision=_policy_revision(auth, w.data_root),
        consent=True,
        expires_at=time.time() + 4,
        data_root=w.data_root,
    )
    time.sleep(5)
    with make_term(expiring) as term:
        term.observe(quiet=2.0, limit=60.0)  # first frame
        text = _terminal_step(term, receipts, "expired", "expired state shown", "M")
        assert "expired" in text.lower(), text[-800:]
        term.press("q")
        term.observe()


# ---------------------------------------------------------------------------
# Windows native console (ctypes), run in a child that owns its console
# ---------------------------------------------------------------------------


def _world_to_json(w: _World) -> dict[str, Any]:
    return {
        "tmp": str(w.tmp),
        "data_root": str(w.data_root),
        "p1": str(w.p1),
        "p2": str(w.p2),
        "p3": str(w.p3),
        "p1_id": w.p1_id,
        "p2_id": w.p2_id,
        "overlay": w.overlay.as_dict(),
        "grants": w.grants,
    }


def _world_from_json(data: Mapping[str, Any]) -> _World:
    return _World(
        tmp=Path(data["tmp"]),
        data_root=Path(data["data_root"]),
        p1=Path(data["p1"]),
        p2=Path(data["p2"]),
        p3=Path(data["p3"]),
        p1_id=data["p1_id"],
        p2_id=data["p2_id"],
        overlay=OwnerScope.from_value(data["overlay"]),
        grants=dict(data["grants"]),
    )


def _make_windows_console(binary: str, env: Mapping[str, str]) -> Callable[[Path], Any]:
    """Factory of `make_term(project)` context managers over one real Windows
    console (the pattern of `tests/test_windows_import_safety.py`)."""
    import ctypes

    from rush.dashboard.terminal_input import _windows_kernel32

    class Coord(ctypes.Structure):
        _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]

    class Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_short),
            ("top", ctypes.c_short),
            ("right", ctypes.c_short),
            ("bottom", ctypes.c_short),
        ]

    class BufferInfo(ctypes.Structure):
        _fields_ = [
            ("size", Coord),
            ("cursor", Coord),
            ("attributes", ctypes.c_uint16),
            ("window", Rect),
            ("max_window", Coord),
        ]

    class Key(ctypes.Structure):
        _fields_ = [
            ("down", ctypes.c_int),
            ("repeat", ctypes.c_uint16),
            ("virtual", ctypes.c_uint16),
            ("scan", ctypes.c_uint16),
            ("char", ctypes.c_wchar),
            ("control", ctypes.c_uint32),
        ]

    class Event(ctypes.Union):
        _fields_: ClassVar = [("key", Key), ("padding", ctypes.c_byte * 16)]

    class Record(ctypes.Structure):
        _fields_ = [("kind", ctypes.c_uint16), ("event", Event)]

    kernel = _windows_kernel32()
    user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    kernel.CreateFileW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetConsoleScreenBufferInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(BufferInfo),
    )
    kernel.ReadConsoleOutputCharacterW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        Coord,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.WriteConsoleInputW.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(Record),
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.SetStdHandle.argtypes = (ctypes.c_uint32, ctypes.c_void_p)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    named = {
        "enter": (0x0D, "\r"),
        "tab": (0x09, "\t"),
        "escape": (0x1B, "\x1b"),
        "up": (0x26, "\0"),
        "down": (0x28, "\0"),
        "right": (0x27, "\0"),
        "left": (0x25, "\0"),
    }

    class WindowsConsole:
        def __init__(self, project: Path) -> None:
            self._project = project
            self._proc: subprocess.Popen[bytes] | None = None
            self._input = None
            self._output = None
            self.last_raw = ""

        def __enter__(self) -> Self:
            assert kernel.FreeConsole() or ctypes.get_last_error() == 6  # type: ignore[attr-defined]  # Windows-only ctypes API
            assert kernel.AllocConsole(), "no console could be allocated"
            self._input = kernel.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
            self._output = kernel.CreateFileW(
                "CONOUT$", 0xC0000000, 3, None, 3, 0, None
            )
            os.set_handle_inheritable(self._input, True)  # type: ignore[attr-defined]  # Windows-only os API
            os.set_handle_inheritable(self._output, True)  # type: ignore[attr-defined]  # Windows-only os API
            for which, handle in (
                (-10, self._input),
                (-11, self._output),
                (-12, self._output),
            ):
                assert kernel.SetStdHandle(which, handle)
            startup = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
            startup.dwFlags |= subprocess.STARTF_USESTDHANDLES  # type: ignore[attr-defined]
            startup.hStdInput = self._input
            startup.hStdOutput = self._output
            startup.hStdError = self._output
            startup.lpAttributeList = {"handle_list": [self._input, self._output]}
            self._proc = subprocess.Popen(
                [binary, "ui", str(self._project)],
                cwd=self._project,
                env=dict(env),
                startupinfo=startup,
                close_fds=True,
            )
            return self

        def __exit__(self, *exc: object) -> None:
            def stop_child() -> None:
                if self._proc is not None and self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                        self._proc.wait(timeout=10)

            def close_handles() -> None:
                for handle in (self._input, self._output):
                    if handle:
                        kernel.CloseHandle(handle)

            _run_cleanups(exc, stop_child, close_handles)

        def _key(self, virtual: int, scan: int, char: str, control: int = 0) -> None:
            records = (Record * 2)()
            for index, down in enumerate((1, 0)):
                records[index].kind = 1
                records[index].event.key = Key(down, 1, virtual, scan, char, control)
            written = ctypes.c_uint32()
            assert kernel.WriteConsoleInputW(
                self._input, records, 2, ctypes.byref(written)
            )
            assert written.value == 2

        def press(self, *tokens: str) -> None:
            for token in tokens:
                if token in named:
                    virtual, char = named[token]
                    self._key(virtual, user32.MapVirtualKeyW(virtual, 0), char)
                else:
                    for char in token:
                        packed = user32.VkKeyScanW(ord(char))
                        virtual = packed & 0xFF
                        control = 0x10 if packed & 0x100 else 0
                        self._key(
                            virtual, user32.MapVirtualKeyW(virtual, 0), char, control
                        )
                time.sleep(0.05)

        def observe(self, quiet: float = 0.8, limit: float = 20.0) -> str:
            deadline = time.monotonic() + limit
            previous = None
            stable_since = time.monotonic()
            frame = ""
            while time.monotonic() < deadline:
                frame = self._screen()
                if frame == previous:
                    if time.monotonic() - stable_since >= quiet:
                        break
                else:
                    previous = frame
                    stable_since = time.monotonic()
                time.sleep(0.1)
            self.last_raw = frame
            return frame

        def _screen(self) -> str:
            handle = kernel.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
            try:
                info = BufferInfo()
                assert kernel.GetConsoleScreenBufferInfo(handle, ctypes.byref(info))
                width = info.window.right - info.window.left + 1
                lines = []
                for row in range(info.window.top, info.window.bottom + 1):
                    chars = ctypes.create_unicode_buffer(width + 1)
                    count = ctypes.c_uint32()
                    assert kernel.ReadConsoleOutputCharacterW(
                        handle,
                        chars,
                        width,
                        Coord(info.window.left, row),
                        ctypes.byref(count),
                    )
                    lines.append(chars.value.rstrip())
                return "\n".join(lines)
            finally:
                kernel.CloseHandle(handle)

        def exited(self, timeout: float = 15.0) -> bool:
            assert self._proc is not None
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                return False
            return True

    return WindowsConsole


def _windows_console_script(
    binary: str, world: dict[str, Any], seeded: dict[str, Any], receipt_path: str
) -> None:
    """Child entry point: owns the console, runs the shared script, writes the
    step receipts for the parent."""
    w = _world_from_json(world)
    env = {
        "PATH": os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
        "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows"),
        "windir": os.environ.get("windir", "C:\\Windows"),
        "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
        "USERPROFILE": os.environ["USERPROFILE"],
        "HOME": os.environ["HOME"],
        "XDG_DATA_HOME": os.environ["XDG_DATA_HOME"],
        "NO_COLOR": "1",
    }
    receipts: list[dict[str, Any]] = []
    _run_terminal_script(_make_windows_console(binary, env), w, seeded, receipts)
    Path(receipt_path).write_text(json.dumps(receipts), encoding="utf-8")


# ---------------------------------------------------------------------------
# live lanes: env-gated drivers (all but `test_t09_live_installed_routes` are
# not collected without a RUSH_T09_LIVE_* variable)
# ---------------------------------------------------------------------------

_LIVE = any(name.startswith("RUSH_T09_LIVE_") for name in os.environ)
_NATIVE_LANE = {
    "Darwin": "native-macos",
    "Linux": "native-linux-ci",
    "Windows": "native-windows-ci",
}


def _import_review(
    term: Any, fixture: Path, snippets: Sequence[str], receipts: list[dict[str, Any]]
) -> None:
    """TUI import review: the PAS records show as pending until locally
    confirmed; nothing is applied from the terminal."""
    _terminal_step(term, receipts, "memory-section", "Memory section opens", "M")
    _terminal_step(term, receipts, "import-open", "import prompt opens", "I")
    text = _terminal_step(
        term,
        receipts,
        "import-preview",
        "records show as pending",
        str(fixture),
        "enter",
    )
    assert "pending" in text.lower(), text[-800:]
    for snippet in snippets:
        assert snippet in text, (snippet, text[-800:])
    _terminal_step(term, receipts, "import-leave", "review closes", "escape")


def _windows_import_review_child(
    binary: str, project: str, fixture: str, snippets: list[str], receipt_path: str
) -> None:
    env = {
        "PATH": os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
        "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows"),
        "windir": os.environ.get("windir", "C:\\Windows"),
        "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
        "USERPROFILE": os.environ["USERPROFILE"],
        "HOME": os.environ["HOME"],
        "XDG_DATA_HOME": os.environ["XDG_DATA_HOME"],
        "NO_COLOR": "1",
    }
    receipts: list[dict[str, Any]] = []
    with _make_windows_console(binary, env)(Path(project)) as term:
        _import_review(term, Path(fixture), snippets, receipts)
    Path(receipt_path).write_text(json.dumps(receipts), encoding="utf-8")


def _json_object(text: str) -> dict[str, Any]:
    """The last JSON object embedded in an agent's final message."""
    for match in reversed(list(re.finditer(r"\{.*\}", text, re.DOTALL))):
        try:
            value = json.loads(match.group(0))
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise AssertionError(f"no JSON object in agent output: {text[-1500:]!r}")


def _claude_text(stdout: str) -> str:
    payload = json.loads(stdout)
    return str(payload.get("result", ""))


def _codex_text(stdout: str) -> str:
    final = ""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "agent_message":
            final = str(item.get("text", final))
        message = event.get("msg") if isinstance(event, dict) else None
        if isinstance(message, dict) and message.get("type") == "agent_message":
            final = str(message.get("message", final))
    return final


def _assert_installed_cli_parity(
    exe: Sequence[str], env: Mapping[str, str], leaves: Sequence[Sequence[str]]
) -> None:
    """RB-3: the executable reports this checkout's version and answers
    `--help` for every given `rush memory` leaf."""
    import rush

    version = subprocess.run(
        [*exe, "--version"],
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert version.returncode == 0 and rush.__version__ in version.stdout, version
    for leaf in leaves:
        helped = subprocess.run(
            [*exe, "memory", *leaf, "--help"],
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert helped.returncode == 0, (leaf, helped.stderr[-500:])


def test_t09_live_installed_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6 / RB-3: an installed `rush`, not the in-process source, serves CLI,
    stdio MCP and the dashboard memory API for steps a-f, g, h and j, and
    answers `--help` for every required and every actual `rush memory` leaf.

    With a live lane selected (any `RUSH_T09_LIVE_*` variable) the executable is
    the verified release artifact and the lane receipts are written. Without
    one the same assertions run against this checkout's installed `rush`
    console script and no receipt is written: the driver is always collected
    and judged, never deselected."""
    inputs = _live_inputs(os.environ, workdir=tmp_path / "installed") if _LIVE else None
    w = _world(tmp_path, monkeypatch)
    if inputs is None:
        exe = [_rush_bin()]
        env = _child_env()
    else:
        exe = [str(inputs.binary)]
        env = _installed_env()
    from rush.mcp import build_server

    _assert_installed_cli_parity(
        exe, env, sorted({*REQUIRED_LEAVES, *_click_leaves(_memory_group())})
    )
    with (
        _McpSession(exe, w.p1, env) as mcp,
        _Dashboard(w.p1_id, w.p1, exe=exe, env=env) as dash,
    ):
        installed_tool = next(t for t in mcp.list_tools() if t["name"] == "rush_memory")
        source_tool = next(
            t
            for t in asyncio.run(build_server().list_tools())
            if t.name == "rush_memory"
        )
        assert installed_tool["inputSchema"] == json.loads(
            json.dumps(source_tool.inputSchema)
        ), "installed rush_memory schema differs from the source schema"
        ctx = _Ctx(tmp=w.tmp, exe=exe, env=env, mcp=mcp, dash=dash, installed=True)
        _step_a_to_f(ctx, w, "mcp")
        _step_g_overlay(ctx, w, "mcp")
        _step_h_cross_owner(ctx, w)
        _step_j_revocation(ctx, w)
    expectations = {
        "a-f": "write, read, correct, stale rejection and history on every transport",
        "g": "personal key shared by two projects, private rows isolated",
        "h": "cross-project owner refused",
        "j": "revoked grant denied on the next use",
    }
    all_steps = _trace_steps(ctx, tmp_path, expectations)
    dash_steps = _trace_steps(
        ctx,
        tmp_path,
        {"a-f": expectations["a-f"], "j": expectations["j"]},
        transports=("dashboard",),
    )
    if inputs is None:
        return
    _write_receipt(inputs, "installed-artifact-cli-mcp", all_steps)
    _write_receipt(inputs, "dashboard-memory-api", dash_steps)
    _write_receipt(
        inputs,
        "personal-overlay-two-projects",
        [s for s in all_steps if s["step"] == "g"],
    )
    _write_receipt(inputs, _NATIVE_LANE[platform.system()], all_steps)


if _LIVE:

    def test_t09_live_pas_import(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R6: the installed CLI previews and imports the pinned PAS session and
        one Rush capsule; the terminal review shows the records pending; the
        preserved local choice and the forged verification stay as in R1 step i."""
        inputs = _live_inputs(os.environ, workdir=tmp_path / "installed")
        w = _world(tmp_path, monkeypatch)
        exe = [str(inputs.binary)]
        env = _installed_env()
        ctx = _Ctx(tmp=w.tmp, exe=exe, env=env, installed=True)
        ctx.current = "pre"
        local = ctx.call(
            "cli",
            w.p2,
            "preference",
            {
                "action": "record",
                "key": "p2.only",
                "value": "yes",
                "scope": "project",
                "authority": "explicit",
                "source": "s1",
                "user_stated": True,
                "apply": True,
            },
            cache_write=True,
        )
        assert local.get("code") == "OK", local
        fixture = REPO / "tests/fixtures/memory_capsule/pas_session_schema1.json"
        receipts: list[dict[str, Any]] = []

        def review(records: list[dict[str, Any]]) -> None:
            constraints = [
                r for r in records if r["foreign_origin_id"].startswith("constraint:")
            ]
            snippets = [str(r["content"]["text"])[:24] for r in constraints]
            if os.name == "nt":
                receipt = tmp_path / "windows-import-review.json"
                from _process_children import spawn_child

                child = spawn_child(
                    "test_phase72_memory_acceptance",
                    "_windows_import_review_child",
                    [
                        str(inputs.binary),
                        str(w.p2),
                        str(fixture),
                        snippets,
                        str(receipt),
                    ],
                )
                assert child.wait(timeout=300) == 0, (
                    "Windows console import review failed"
                )
                receipts.extend(json.loads(receipt.read_text(encoding="utf-8")))
            else:
                with _PtyTerminal([*exe, "ui", str(w.p2)], env, w.p2) as term:
                    _import_review(term, fixture, snippets, receipts)

        ctx.current = "i"
        _step_i_pas_import(ctx, w, review=review)
        ctx.current = "i2"
        _step_i2_rush_capsule(ctx, w)
        steps = _trace_steps(
            ctx,
            tmp_path,
            {
                "i": "PAS import: IMPORTED, imported_unverified, pending",
                "i2": "Rush capsule round trip",
            },
        )
        _write_receipt(inputs, "pas-import", [*steps, *receipts])

    @pytest.mark.windows_only
    def test_t09_live_windows_console(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R6: the same grant-controlled journey on a real Windows console."""
        from _process_children import spawn_child

        inputs = _live_inputs(os.environ, workdir=tmp_path / "installed")
        w = _world(tmp_path, monkeypatch)
        seeded = _seed_terminal_rows(w)
        receipt = tmp_path / "windows-console-steps.json"
        child = spawn_child(
            "test_phase72_memory_acceptance",
            "_windows_console_script",
            [str(inputs.binary), _world_to_json(w), seeded, str(receipt)],
        )
        assert child.wait(timeout=1800) == 0, "native console journey failed"
        steps = json.loads(receipt.read_text(encoding="utf-8"))
        assert steps, "the console journey recorded no step"
        _write_receipt(inputs, "native-windows-ci", steps)

    if os.name != "nt":

        @pytest.mark.posix_only
        def test_t09_live_pty_walkthrough(
            tmp_path: Path, monkeypatch: pytest.MonkeyPatch
        ) -> None:
            """R6: the installed `rush ui` on a real pseudo-terminal."""
            inputs = _live_inputs(os.environ, workdir=tmp_path / "installed")
            w = _world(tmp_path, monkeypatch)
            seeded = _seed_terminal_rows(w)
            env = _installed_env()
            receipts: list[dict[str, Any]] = []

            def make_term(project: Path) -> _PtyTerminal:
                return _PtyTerminal(
                    [str(inputs.binary), "ui", str(project)], env, project
                )

            _run_terminal_script(make_term, w, seeded, receipts)
            _write_receipt(inputs, "pty-terminal", receipts)

    if os.environ.get("RUSH_T09_LIVE_AGENTS") == "1":

        def _preference_rows(w: _World, key: str) -> list[tuple[str, int]]:
            db = w.p1 / ".rush" / "memory.db"
            with contextlib.closing(
                sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            ) as conn:
                return [
                    (str(r[0]), int(r[1]))
                    for r in conn.execute(
                        "SELECT id, artifact_version FROM memory_artifacts "
                        "WHERE subject = 'preference' AND json_extract(content, '$.key') = ?",
                        (key,),
                    )
                ]

        def test_t09_live_two_agent(
            tmp_path: Path, monkeypatch: pytest.MonkeyPatch
        ) -> None:
            """R6: two real agents on one project. A (`claude -p`) writes and
            corrects; B (`codex exec`) recalls the exact revision, rejects the
            stale one, treats a denied source as denied, and honors an explicit
            rejection and its later reversal only where it applies."""
            host_home = os.environ["HOME"]
            _require_agents(os.environ)
            inputs = _live_inputs(os.environ, workdir=tmp_path / "installed")
            w = _world(tmp_path, monkeypatch)
            rush_env = {
                "HOME": os.environ["HOME"],
                "USERPROFILE": os.environ["HOME"],
                "XDG_DATA_HOME": os.environ["XDG_DATA_HOME"],
                "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
            }
            host_env = {**os.environ, "HOME": host_home, "USERPROFILE": host_home}
            host_env.pop("PYTHONPATH", None)
            exe = [str(inputs.binary)]
            cli_env = _installed_env()
            steps: list[dict[str, Any]] = []

            def mcp_args(project: Path) -> list[str]:
                return ["mcp", "serve", "--project", str(project), "--profile", "core"]

            def run_a(prompt: str, project: Path) -> str:
                config = tmp_path / f"claude-{len(steps)}.json"
                config.write_text(
                    json.dumps(
                        {
                            "mcpServers": {
                                "rush": {
                                    "command": exe[0],
                                    "args": mcp_args(project),
                                    "env": rush_env,
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                done = subprocess.run(
                    [
                        "claude",
                        "-p",
                        prompt,
                        "--strict-mcp-config",
                        "--mcp-config",
                        str(config),
                        "--output-format",
                        "json",
                        "--allowedTools",
                        "mcp__rush__rush_memory",
                    ],
                    cwd=project,
                    env=host_env,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
                assert done.returncode == 0, done.stderr[-1500:]
                return _claude_text(done.stdout)

            def run_b(prompt: str, project: Path) -> dict[str, Any]:
                env_table = ", ".join(
                    f"{k} = {json.dumps(v)}" for k, v in rush_env.items()
                )
                done = subprocess.run(
                    [
                        "codex",
                        "exec",
                        "--json",
                        "--skip-git-repo-check",
                        "-c",
                        f"mcp_servers.rush.command={json.dumps(exe[0])}",
                        "-c",
                        f"mcp_servers.rush.args={json.dumps(mcp_args(project))}",
                        "-c",
                        f"mcp_servers.rush.env={{{env_table}}}",
                        prompt,
                    ],
                    cwd=project,
                    env=host_env,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
                assert done.returncode == 0, done.stderr[-1500:]
                answer = _json_object(_codex_text(done.stdout))
                steps.append(
                    {
                        "step": f"agent-b-{len(steps)}",
                        "argv_redacted": "codex exec --json",
                        "transcript_sha256": _sha(done.stdout),
                        "observed": sorted(answer),
                        "expected": "strict JSON decision checked against persisted rows",
                        "independent_check": "sqlite rows and MemoryTool readback",
                    }
                )
                return answer

            db = w.p1 / ".rush" / "memory.db"
            # A writes r1@1
            before = set(_row_versions(db)) if db.is_file() else set()
            write_args = _write_request(SUBJECT, "r1 body")
            run_a(
                "Call the rush_memory tool once with these arguments, then reply "
                f"DONE: {json.dumps({'path': str(w.p1), 'operation': 'write', 'request': write_args, 'allow_cache_write': True})}",
                w.p1,
            )
            created = set(_row_versions(db)) - before
            assert len(created) == 1, "A did not write exactly one row"
            (r1,) = created
            assert _row_versions(db)[r1] == 1
            _seed_row(w.p1, "denied-row", "secret denied body", source="forbidden-src")

            question = (
                'Use the rush_memory tool (operation list, subjects ["architectural_decision"], '
                "schema_version 2). Reply with only a JSON object "
                '{"cited_refs": ["<artifact_id>@<version>", ...], "stale_v1": "<code or none>", '
                '"denied_without_content": true|false, "decision": "<one line>"}. '
                "Also try expanding artifact_version 1 of the row you cite if a newer version exists, "
                "report its error code in stale_v1, and try operation expand on artifact id denied-row "
                "version 1: set denied_without_content true only if it is refused without content."
            )
            first = run_b(question, w.p1)
            assert first["cited_refs"] == [f"{r1}@1"], first
            assert "secret denied body" not in json.dumps(first)

            # A corrects to v2
            run_a(
                "Call the rush_memory tool once with these arguments, then reply DONE: "
                + json.dumps(
                    {
                        "path": str(w.p1),
                        "operation": "edit",
                        "allow_cache_write": True,
                        "request": {
                            "schema_version": 2,
                            "subject": SUBJECT,
                            "artifact_id": r1,
                            "expected_version": 1,
                            "content": {"text": "r1 body v2"},
                            "apply": True,
                            "invocation_id": _uid(),
                            "effect_id": _uid(),
                        },
                    }
                ),
                w.p1,
            )
            assert _row_versions(db)[r1] == 2
            second = run_b(question, w.p1)
            assert second["cited_refs"] == [f"{r1}@2"], second
            assert second.get("stale_v1") == "E_VERSION", second
            assert second.get("denied_without_content") is True, second

            # E06 / E25: an explicit rejection, its held-out rewording, a lookalike,
            # another project, then the explicit reversal
            reject = ctx_call_cli(exe, cli_env, w.p1, w.tmp, "reject")
            rejection_ref = f"{reject['artifact_id']}@{reject['artifact_version']}"

            def decide(prompt: str, project: Path) -> dict[str, Any]:
                return run_b(
                    prompt
                    + ' Use rush_memory operation preference action resolve key "avoid.requests-library" '
                    "(schema omitted, plain request). Reply with only JSON "
                    '{"decision": "requests"|"httpx", "cited_refs": ["<artifact_id>@<version>", ...]}.',
                    project,
                )

            reworded = decide(
                "We need a synchronous HTTP GET helper for the sync job. May we use the popular "
                "third-party HTTP package everyone installs first, or a modern alternative?",
                w.p1,
            )
            assert reworded["decision"] == "httpx", reworded
            assert rejection_ref in reworded["cited_refs"], reworded
            lookalike = decide(
                "Add a metric named requests_total counting incoming calls (no HTTP client involved).",
                w.p1,
            )
            assert lookalike["cited_refs"] == [], lookalike
            other = decide(
                "We need a synchronous HTTP GET helper for the sync job. May we use the popular "
                "third-party HTTP package everyone installs first?",
                w.p2,
            )
            assert other["cited_refs"] == [], other
            reverse = ctx_call_cli(exe, cli_env, w.p1, w.tmp, "reverse")
            reversal_ref = f"{reverse['artifact_id']}@{reverse['artifact_version']}"
            honored = decide(
                "We need a synchronous HTTP GET helper for the sync job. May we use the popular "
                "third-party HTTP package everyone installs first?",
                w.p1,
            )
            assert honored["decision"] == "requests", honored
            assert reversal_ref in honored["cited_refs"], honored
            assert all(
                ref
                in {
                    f"{i}@{v}" for i, v in _preference_rows(w, "avoid.requests-library")
                }
                for ref in honored["cited_refs"]
            )
            _write_receipt(inputs, "two-agent-same-project", steps[:2])
            _write_receipt(inputs, "e06-e25-rejection-reversal", steps[2:])

        def ctx_call_cli(
            exe: Sequence[str], env: Mapping[str, str], root: Path, tmp: Path, mode: str
        ) -> dict[str, Any]:
            """The driver records the user's explicit rejection (or its reversal)
            through the installed CLI, project scope."""
            ctx = _Ctx(tmp=tmp, exe=list(exe), env=dict(env), installed=True)
            value = (
                {
                    "rejected": True,
                    "use_instead": "httpx",
                    "reason": "owner banned requests",
                }
                if mode == "reject"
                else {"rejected": False, "reason": "owner reversed the ban"}
            )
            raw = ctx.call(
                "cli",
                root,
                "preference",
                {
                    "action": "record",
                    "key": "avoid.requests-library",
                    "value": value,
                    "scope": "project",
                    "authority": "explicit",
                    "source": "s1",
                    "user_stated": True,
                    "apply": True,
                },
                cache_write=True,
            )
            assert raw.get("code") == "OK", raw
            return dict(raw["data"])
