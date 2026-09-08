from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts.sync_docs import check_docs, main

REPORT = "docs/reports/phase-64-66-documentation-coverage.md"
CONTRACTS = {
    "cli": {
        "rush check": {
            "parameters": [
                {
                    "default": None,
                    "kind": "argument",
                    "name": "path",
                    "required": True,
                    "type": "path",
                }
            ]
        }
    },
    "mcp": {
        "rush_check": {
            "parameters": [
                {
                    "default": None,
                    "kind": "parameter",
                    "name": "path",
                    "required": True,
                    "type": "string:path",
                }
            ]
        }
    },
    "catalog": {
        "check": {
            "parameters": [
                {
                    "default": False,
                    "kind": "option",
                    "name": "changed",
                    "required": False,
                    "type": "bool",
                }
            ]
        }
    },
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _owner(path: str) -> str:
    if "/goals/" in path or "/.goalbuddy-board/" in path:
        return "legacy-evidence"
    if path.startswith(("docs/phase-plans/", "docs/templates/", "docs/agents/")):
        return "plans-templates-agents"
    if (
        path.startswith(("docs/adr/", "docs/maintainers/adr/", "docs/reports/"))
        or "/research/" in path
        or "/brainstorm/" in path
    ):
        return "historical"
    if path.startswith(("docs/tools/", "docs/specs/")) or path in {
        "docs/ENGINES.md",
        "docs/TOOL_CATALOG.md",
    }:
        return "tool-docs"
    if path.startswith(
        (
            "docs/getting-started/",
            "docs/tutorials/",
            "docs/user-guide/",
            "docs/integrations/",
            "docs/vibecoding/",
        )
    ):
        return "user-guides"
    if path.startswith("docs/reference/") or path in {
        "docs/CLI_REFERENCE.md",
        "docs/MCP_REFERENCE.md",
        "docs/CONFIGURATION.md",
    }:
        return "reference"
    if path.startswith(("docs/developer/", "docs/maintainers/")):
        return "developer-maintainer"
    return "fallback"


def _body_digest(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("Current status: "):
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    return _sha256("".join(lines).encode())


def _entry(root: Path, relative: str, **overrides: object) -> dict[str, object]:
    path = root / relative
    data = path.read_bytes()
    entry: dict[str, object] = {
        "path": relative,
        "sha256": None if relative == REPORT else _sha256(data),
        "audience": "Rush users",
        "authority": "current",
        "evidence": ["Verified fixture section"],
        "owner": _owner(relative),
        "media_type": "text/markdown" if path.suffix == ".md" else "image/png",
        "referrers": [],
        "source_state": "tracked",
    }
    entry.update(overrides)
    return entry


def _write_report(
    root: Path, entries: list[dict[str, object]], contracts=CONTRACTS
) -> None:
    report = root / REPORT
    report.parent.mkdir(parents=True, exist_ok=True)
    entries = [entry for entry in entries if entry["path"] != REPORT]
    entries.append(
        _entry(root, REPORT)
        if report.exists()
        else {
            "path": REPORT,
            "sha256": None,
            "audience": "Rush maintainers",
            "authority": "generated",
            "evidence": ["P64-00 coverage receipt"],
            "owner": "historical",
            "media_type": "text/markdown",
            "referrers": [],
            "source_state": "tracked",
        }
    )
    payload = {
        "schema": "rush-doc-coverage/v1",
        "documents": sorted(entries, key=lambda item: str(item["path"])),
        "contracts": contracts,
    }
    report.write_text(
        "# Coverage\n\n```rush-doc-coverage-v1\n"
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        + "\n```\n",
        encoding="utf-8",
    )


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "docs"], cwd=root, check=True)


def _fixture(tmp_path: Path) -> Path:
    (tmp_path / "docs/nested").mkdir(parents=True)
    (tmp_path / "docs/index.md").write_text(
        "# Home\n\n[Nested](nested/guide.md#repeat-1)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/nested/guide.md").write_text(
        "# Repeat\n\n## Repeat\n",
        encoding="utf-8",
    )
    _write_report(
        tmp_path,
        [_entry(tmp_path, "docs/index.md"), _entry(tmp_path, "docs/nested/guide.md")],
    )
    _git_init(tmp_path)
    return tmp_path


def test_nested_document_is_checked(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    assert check_docs(root, contracts=CONTRACTS) == []
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 0
    nested = root / "docs/nested/guide.md"
    nested.write_text("# Changed\n", encoding="utf-8")
    errors = check_docs(root, contracts=CONTRACTS)
    assert any("docs/nested/guide.md: stale sha256" in error for error in errors)
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1


def test_broken_link_and_anchor_fail(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    index = root / "docs/index.md"
    index.write_text(
        "# Home\n\n"
        "`Superseded by [ADR](nested/inline-missing.md)` "
        "``template with ` [Title](nested/long-inline-missing.md)`` "
        "[Gone](nested/deleted.md) [Bad](nested/guide.md#missing)\n",
        encoding="utf-8",
    )
    entries = [_entry(root, "docs/index.md"), _entry(root, "docs/nested/guide.md")]
    _write_report(root, entries)
    errors = check_docs(root, contracts=CONTRACTS)
    assert any("docs/index.md: nested/deleted.md: missing target" in e for e in errors)
    assert any(
        "docs/index.md: nested/guide.md#missing: missing anchor" in e for e in errors
    )
    assert not any("inline-missing.md" in error for error in errors)
    assert len(errors) == 2
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1


def test_missing_registered_command_fails(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    incomplete = {**CONTRACTS, "cli": {}}
    _write_report(
        root,
        [_entry(root, "docs/index.md"), _entry(root, "docs/nested/guide.md")],
        incomplete,
    )
    errors = check_docs(root, contracts=CONTRACTS)
    assert "contracts.cli: missing registered command rush check" in errors
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1


def test_historical_claim_retains_text_and_current_link(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    historical = root / "docs/reports/history.md"
    historical.parent.mkdir(parents=True, exist_ok=True)
    historical.write_text(
        "Current status: planned; current contract: [Phase 64](../phase-plans/p64.md); "
        "evidence: [review](review.md).\n\n# Original result\n\nPassed in 2024.\n",
        encoding="utf-8",
    )
    (root / "docs/phase-plans/p64.md").parent.mkdir(exist_ok=True)
    (root / "docs/phase-plans/p64.md").write_text("# Phase 64\n", encoding="utf-8")
    (root / "docs/reports/review.md").write_text("# Review\n", encoding="utf-8")
    entries = [
        _entry(root, "docs/index.md"),
        _entry(root, "docs/nested/guide.md"),
        _entry(
            root,
            "docs/reports/history.md",
            authority="historical",
            immutable_body_sha256=_body_digest(historical.read_text()),
            superseded=True,
        ),
        _entry(root, "docs/phase-plans/p64.md", authority="planned"),
        _entry(
            root,
            "docs/reports/review.md",
            authority="historical",
            immutable_body_sha256=_body_digest("# Review\n"),
        ),
    ]
    _write_report(root, entries)
    subprocess.run(["git", "add", "docs"], cwd=root, check=True)
    assert check_docs(root, contracts=CONTRACTS) == []
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 0
    original = historical.read_text(encoding="utf-8")
    historical.write_text(original.split("\n\n", 1)[1], encoding="utf-8")
    assert any(
        "docs/reports/history.md: missing current-status cross-reference" in error
        for error in check_docs(root, contracts=CONTRACTS)
    )
    historical.write_text(original, encoding="utf-8")
    historical.write_text(
        historical.read_text().replace("Passed", "Failed"), encoding="utf-8"
    )
    errors = check_docs(root, contracts=CONTRACTS)
    assert any("docs/reports/history.md: historical body changed" in e for e in errors)
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1


def test_new_document_invalidates_coverage(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    added = root / "docs/new.md"
    added.write_text("# New\n", encoding="utf-8")
    errors = check_docs(root, contracts=CONTRACTS)
    assert "docs/new.md: missing coverage receipt" in errors
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1
    entries = [
        _entry(root, "docs/index.md"),
        _entry(root, "docs/nested/guide.md"),
        _entry(root, "docs/new.md", source_state="untracked"),
    ]
    _write_report(root, entries)
    assert check_docs(root, contracts=CONTRACTS) == []
    subprocess.run(["git", "add", "docs/new.md"], cwd=root, check=True)
    assert check_docs(root, contracts=CONTRACTS) == []


def test_ordered_ownership_covers_all_paths(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    nested = root / "docs/developer/research/phase-notes.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("# Research\n", encoding="utf-8")
    entries = [
        _entry(root, "docs/index.md"),
        _entry(root, "docs/nested/guide.md"),
        _entry(root, "docs/developer/research/phase-notes.md", owner="historical"),
    ]
    _write_report(root, entries)
    subprocess.run(["git", "add", "docs"], cwd=root, check=True)
    assert check_docs(root, contracts=CONTRACTS) == []
    entries[-1]["owner"] = "developer-maintainer"
    _write_report(root, entries)
    assert any(
        "docs/developer/research/phase-notes.md: owner developer-maintainer != historical"
        in e
        for e in check_docs(root, contracts=CONTRACTS)
    )
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1


def test_binary_digest_and_reference_preserved(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    image = root / "docs/nested/diagram.png"
    image.write_bytes(b"\x89PNG\r\nfixture")
    text_records = {
        "docs/nested/data.json": b'{"state":"historical"}\n',
        "docs/nested/state.yaml": b"state: historical\n",
        "docs/nested/notes.txt": b"historical receipt\n",
    }
    for relative, content in text_records.items():
        path = root / relative
        path.write_bytes(content)
    guide = root / "docs/nested/guide.md"
    guide.write_text(
        "# Repeat\n\n## Repeat\n\n![Diagram](diagram.png)\n", encoding="utf-8"
    )
    entries = [
        _entry(root, "docs/index.md"),
        _entry(root, "docs/nested/guide.md"),
        _entry(root, "docs/nested/diagram.png", referrers=["docs/nested/guide.md"]),
        *[
            _entry(
                root,
                relative,
                media_type="application/json"
                if relative.endswith(".json")
                else "text/plain",
            )
            for relative in text_records
        ],
    ]
    _write_report(root, entries)
    subprocess.run(["git", "add", "docs"], cwd=root, check=True)
    assert check_docs(root, contracts=CONTRACTS) == []
    entries[2]["referrers"] = []
    _write_report(root, entries)
    assert (
        "docs/nested/diagram.png: binary asset requires referring document paths"
        in check_docs(root, contracts=CONTRACTS)
    )
    entries[2]["referrers"] = ["docs/nested/guide.md"]
    _write_report(root, entries)
    image.write_bytes(b"changed")
    errors = check_docs(root, contracts=CONTRACTS)
    assert any("docs/nested/diagram.png: stale sha256" in e for e in errors)
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1


def test_mcp_parameter_default_mismatch_fails(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    bad = json.loads(json.dumps(CONTRACTS))
    bad["mcp"]["rush_check"]["parameters"][0]["required"] = False
    bad["mcp"]["rush_check"]["parameters"][0]["default"] = "."
    _write_report(
        root,
        [_entry(root, "docs/index.md"), _entry(root, "docs/nested/guide.md")],
        bad,
    )
    errors = check_docs(root, contracts=CONTRACTS)
    assert any(
        "contracts.mcp.rush_check.path: default/required/type mismatch" in e
        for e in errors
    )
    assert main(["--check"], repo_root=root, contracts=CONTRACTS) == 1
