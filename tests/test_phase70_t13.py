"""Phase 70 T13 — Deduplicate actual repeated diagnostics.

Test matrix for `.scratch/phase-70-design-gate/W2-T9-T17.md` (## T13, section 6):
same-producer identical diagnostics collapse; anything that differs in column,
message, severity or producer stays distinct; path aliases merge only on
physical identity (st_dev, st_ino), never on lexical basename alone; mixed
Python/JS counts survive aggregation untouched.

T13 is not implemented yet. `LintTool` (`src/rush/tools/lint.py`) currently
just concatenates every engine's findings with no identity/dedupe step at
all, so every "must collapse" case below is RED against real, current
code. The "must stay distinct" cases are keep-green guards: they already
pass today (there is no dedupe to over-collapse), and must keep passing
once T13 lands.

`run_engine` is monkeypatched exactly like the existing pattern in
`tests/test_tools.py::test_format_uses_ruff_format_subcommand` (fake
callable matching the real `run_engine(engine, path, args, **kwargs)`
signature) so no real engine subprocess is spawned for the aggregation
cases. The argv-equivalence case is the one exception: it shells out to a
real `ruff` binary, per the brief's "controlled argv/output test".
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from rush.tools import LintTool
from rush.tools.common import resolve_binary

pytestmark = pytest.mark.filterwarnings("ignore")


def _finding(
    *,
    path: str,
    line: int = 10,
    column: int = 1,
    rule_id: str = "F401",
    severity: str = "warn",
    message: str = "'os' imported but unused",
    fix: dict | None = None,
    evidence: dict | None = None,
    extensions: dict | None = None,
) -> dict:
    finding: dict = {
        "path": path,
        "line": line,
        "column": column,
        "rule": rule_id,
        "rule_id": rule_id,
        "severity": severity,
        "message": message,
    }
    if fix is not None:
        finding["fix"] = fix
    if evidence is not None:
        finding["evidence"] = evidence
    if extensions is not None:
        finding["extensions"] = extensions
    return finding


def _fake_run_engine(findings_by_engine: dict[str, list[dict]]):
    """Build a `run_engine` stand-in keyed by `Engine.name`.

    Signature mirrors the real `run_engine(engine, path, args, **kwargs)`
    call in `src/rush/tools/lint.py::_run_selected_engines`.
    """

    def fake(engine, _path, _args, **_kwargs):
        findings = findings_by_engine.get(engine.name, [])
        return {
            "status": "warn" if findings else "ok",
            "findings": findings,
            "engine": engine.name,
        }

    return fake


def _only_globstar_on_path(name: str) -> bool:
    return name == "globstar"


def _no_extra_engines_on_path(name: str) -> bool:
    return False


# --- MUST-FAIL cases (RED against current, unimplemented lint.py) ----------


def test_t13_diagnostic_identity(monkeypatch, tmp_path: Path):
    """Identical repeated emissions from the same producer collapse to 1.

    RED reason: `_run_selected_engines`/`_assemble_lint_result` in
    `src/rush/tools/lint.py` extend `findings_all` with no dedupe step, so
    two byte-identical ruff findings stay 2, not 1.
    """
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    duplicate = _finding(path=str(tmp_path / "mod.py"))
    monkeypatch.setattr(
        "rush.tools.lint.run_engine",
        _fake_run_engine({"ruff": [dict(duplicate), dict(duplicate)]}),
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 1


def test_t13_diagnostic_identity_path_alias_merge(monkeypatch, tmp_path: Path):
    """A symlinked-parent alias to the same physical file merges to 1.

    RED reason: lint.py has no physical-identity (`st_dev`, `st_ino`) check;
    it treats the two distinct path strings as two distinct findings.
    """
    real_root = tmp_path / "real"
    real_root.mkdir()
    real_file = real_root / "pkg" / "mod.py"
    real_file.parent.mkdir()
    real_file.write_text("import os\n")

    link_root = tmp_path / "link"
    os.symlink(real_root, link_root)
    aliased_path = link_root / "pkg" / "mod.py"
    assert (
        os.stat(aliased_path).st_ino == os.stat(real_file).st_ino
    )  # sanity: same inode

    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    findings = [_finding(path=str(real_file)), _finding(path=str(aliased_path))]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 1


# --- keep-green guards (already true today; must stay true after T13) ------


def test_t13_diagnostic_identity_distinct_column(monkeypatch, tmp_path: Path):
    """Same producer, same everything but column: stays 2 distinct findings."""
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    findings = [
        _finding(path=str(tmp_path / "mod.py"), column=1),
        _finding(path=str(tmp_path / "mod.py"), column=5),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


def test_t13_diagnostic_identity_distinct_message(monkeypatch, tmp_path: Path):
    """Same producer, same location but different message: stays 2."""
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    findings = [
        _finding(path=str(tmp_path / "mod.py"), message="'os' imported but unused"),
        _finding(path=str(tmp_path / "mod.py"), message="'sys' imported but unused"),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


def test_t13_diagnostic_identity_cross_producer_same_content(
    monkeypatch, tmp_path: Path
):
    """Byte-identical findings from two different producers never merge.

    Ruff and globstar report the same path/line/column/rule/severity/message;
    cross-engine attribution must be kept, so the count stays 2.
    """
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _only_globstar_on_path)
    duplicate = _finding(path=str(tmp_path / "mod.py"))
    monkeypatch.setattr(
        "rush.tools.lint.run_engine",
        _fake_run_engine({"ruff": [dict(duplicate)], "globstar": [dict(duplicate)]}),
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


def test_t13_diagnostic_identity_distinct_files_same_name(monkeypatch, tmp_path: Path):
    """Two distinct physical files sharing a basename never merge."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "foo.py").write_text("import os\n")
    (dir_b / "foo.py").write_text("import os\n")
    assert os.stat(dir_a / "foo.py").st_ino != os.stat(dir_b / "foo.py").st_ino

    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    findings = [
        _finding(path=str(dir_a / "foo.py")),
        _finding(path=str(dir_b / "foo.py")),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


def test_t13_diagnostic_identity_mixed_language_counts(monkeypatch, tmp_path: Path):
    """Mixed Python + JavaScript producer counts are exact, never merged."""
    (tmp_path / "mod.py").write_text("import os\n")
    (tmp_path / "app.js").write_text("var x = 1;\n")

    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    ruff_findings = [
        _finding(path=str(tmp_path / "mod.py"), line=1, message="finding 1"),
        _finding(path=str(tmp_path / "mod.py"), line=2, message="finding 2"),
    ]
    eslint_findings = [
        _finding(path=str(tmp_path / "app.js"), line=1, message="eslint 1"),
        _finding(path=str(tmp_path / "app.js"), line=2, message="eslint 2"),
        _finding(path=str(tmp_path / "app.js"), line=3, message="eslint 3"),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine",
        _fake_run_engine({"ruff": ruff_findings, "eslint": eslint_findings}),
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 5


def test_t13_diagnostic_identity_missing_file_lexical_merge(
    monkeypatch, tmp_path: Path
):
    """Same-producer identical findings for a path that does not exist on
    disk merge on normalized lexical path when `pkg/./mod.py` and
    `pkg/mod.py` name the same location.

    RED reason: lint.py has no lexical-path normalization fallback (or any
    dedupe at all), so the two distinct literal path strings stay 2, not 1.
    """
    (tmp_path / "trigger.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    missing_root = tmp_path / "missing"
    findings = [
        _finding(path=str(missing_root / "pkg" / "." / "mod.py")),
        _finding(path=str(missing_root / "pkg" / "mod.py")),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 1


def test_t13_diagnostic_identity_missing_file_distinct_lexical(
    monkeypatch, tmp_path: Path
):
    """Same-producer findings for two distinct missing lexical paths
    (`pkg/mod.py` vs `pkg/other.py`) never merge."""
    (tmp_path / "trigger.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    missing_root = tmp_path / "missing"
    findings = [
        _finding(path=str(missing_root / "pkg" / "mod.py")),
        _finding(path=str(missing_root / "pkg" / "other.py")),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


# --- W2 amendments (finding 22 / T13(3)) ------------------------------------


def test_t13_same_start_different_end_location(monkeypatch, tmp_path: Path):
    """Two findings sharing every field but `extensions.end_location` stay
    distinct: the end location is carried through lint aggregation, not
    dropped from the dedupe key."""
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    findings = [
        _finding(
            path=str(tmp_path / "mod.py"),
            extensions={"end_location": {"row": 10, "column": 20}},
        ),
        _finding(
            path=str(tmp_path / "mod.py"),
            extensions={"end_location": {"row": 11, "column": 5}},
        ),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


def test_t13_same_except_fix(monkeypatch, tmp_path: Path):
    """Two findings identical except their `fix` stay distinct."""
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    findings = [
        _finding(path=str(tmp_path / "mod.py"), fix={"applicability": "safe"}),
        _finding(path=str(tmp_path / "mod.py"), fix={"applicability": "unsafe"}),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


def test_t13_same_except_evidence(monkeypatch, tmp_path: Path):
    """Two findings identical except their `evidence` stay distinct."""
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    findings = [
        _finding(path=str(tmp_path / "mod.py"), evidence={"snippet": "import os"}),
        _finding(path=str(tmp_path / "mod.py"), evidence={"snippet": "import sys"}),
    ]
    monkeypatch.setattr(
        "rush.tools.lint.run_engine", _fake_run_engine({"ruff": findings})
    )

    result = LintTool().run(tmp_path)

    assert len(result["findings"]) == 2


def test_t13_lint_provenance_reuse(monkeypatch, tmp_path: Path):
    """Every lint finding carries `lint/<engine>` provenance, from the same
    shared helper `aggregate_results` uses (`routing.py`'s
    `finding_provenance`, design R13.1), not a second ad hoc formatter."""
    (tmp_path / "mod.py").write_text("import os\n")
    (tmp_path / "app.js").write_text("var x = 1;\n")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", _no_extra_engines_on_path)
    monkeypatch.setattr(
        "rush.tools.lint.run_engine",
        _fake_run_engine(
            {
                "ruff": [_finding(path=str(tmp_path / "mod.py"))],
                "eslint": [
                    _finding(path=str(tmp_path / "app.js"), rule_id="no-unused-vars")
                ],
            }
        ),
    )

    result = LintTool().run(tmp_path)

    provenance_by_path = {f["path"]: f.get("provenance") for f in result["findings"]}
    assert provenance_by_path[str(tmp_path / "mod.py")] == "lint/ruff"
    assert provenance_by_path[str(tmp_path / "app.js")] == "lint/eslint"


def test_t13_ruff_normalize_carries_end_location():
    """`RuffEngine.normalize` keeps ruff's `end_location` in
    `extensions.end_location` (design §3 / finding 22) instead of dropping
    it like `normalize_findings` does today, so two findings sharing every
    other field but their end location come back distinct."""
    from rush.engines.ruff import RuffEngine

    raw = {
        "exit_code": 1,
        "stdout": "",
        "stderr": "",
        "parsed": None,
        "findings": [
            {
                "filename": "mod.py",
                "location": {"row": 10, "column": 1},
                "end_location": {"row": 10, "column": 20},
                "code": "E501",
                "message": "line too long",
            },
            {
                "filename": "mod.py",
                "location": {"row": 10, "column": 1},
                "end_location": {"row": 11, "column": 5},
                "code": "E501",
                "message": "line too long",
            },
        ],
        "summary": "",
        "duration_ms": 0,
    }

    result = RuffEngine().normalize(raw, Path("mod.py"), "lint")

    end_locations = [
        (f.get("extensions") or {}).get("end_location") for f in result["findings"]
    ]
    assert end_locations == [{"row": 10, "column": 20}, {"row": 11, "column": 5}]


def test_t13_ruff_normalize_end_location_survives_message_redaction_reorder():
    """`end_location` must attach by identity, not by recomputing
    `normalize_findings`' sort key and zipping positionally:
    `normalize_findings` sorts on the REDACTED message, so a raw record
    containing something `SecretRedactor` rewrites (an AWS-shaped key here)
    can sort differently after redaction than its raw text did. A
    position-based re-sort over raw messages would then pair the wrong
    `end_location` with the wrong finding once the real sort reorders them.

    Raw order: [aws_finding, zebra_finding]. Raw message compare: "AKIA..."
    < "Zebra..." (same as input order). Redacted compare:
    "[REDACTED_AWS_ACCESS_KEY] ..." > "Zebra ..." (`[` > `Z`), so
    `normalize_findings`' real output order is [zebra, aws] -- flipped.
    """
    from rush.engines.ruff import RuffEngine

    raw = {
        "exit_code": 1,
        "stdout": "",
        "stderr": "",
        "parsed": None,
        "findings": [
            {
                "filename": "mod.py",
                "location": {"row": 1, "column": 1},
                "end_location": {"row": 1, "column": 40},
                "code": "F401",
                "message": "AKIAABCDEFGHIJKLMNOP leaked",
            },
            {
                "filename": "mod.py",
                "location": {"row": 1, "column": 1},
                "end_location": {"row": 2, "column": 5},
                "code": "F401",
                "message": "Zebra clean",
            },
        ],
        "summary": "",
        "duration_ms": 0,
    }

    result = RuffEngine().normalize(raw, Path("mod.py"), "lint")

    by_message = {
        f["message"]: (f.get("extensions") or {}).get("end_location")
        for f in result["findings"]
    }
    assert by_message["[REDACTED_AWS_ACCESS_KEY] leaked"] == {"row": 1, "column": 40}
    assert by_message["Zebra clean"] == {"row": 2, "column": 5}


def test_t13_ruff_normalize_end_location_survives_dropped_message():
    """A raw record with no message is omitted by `normalize_findings`
    (identical to today); the surviving findings around it must keep their
    own `end_location`, not one shifted by the gap."""
    from rush.engines.ruff import RuffEngine

    raw = {
        "exit_code": 1,
        "stdout": "",
        "stderr": "",
        "parsed": None,
        "findings": [
            {
                "filename": "a.py",
                "location": {"row": 1, "column": 1},
                "end_location": {"row": 1, "column": 5},
                "code": "F401",
                "message": "alpha issue",
            },
            {
                "filename": "b.py",
                "location": {"row": 2, "column": 1},
                "end_location": {"row": 2, "column": 5},
                "code": "F401",
                "message": "",
            },
            {
                "filename": "c.py",
                "location": {"row": 3, "column": 1},
                "end_location": {"row": 3, "column": 5},
                "code": "F401",
                "message": "charlie issue",
            },
        ],
        "summary": "",
        "duration_ms": 0,
    }

    result = RuffEngine().normalize(raw, Path("mod.py"), "lint")

    by_path = {
        f["path"]: (f.get("extensions") or {}).get("end_location")
        for f in result["findings"]
    }
    assert by_path == {
        "a.py": {"row": 1, "column": 5},
        "c.py": {"row": 3, "column": 5},
    }


# --- real-ruff argv enumeration equivalence probe (R13.2) -------------------


def test_t13_argv_enumeration_equivalence(tmp_path: Path):
    """Root-only vs root-plus-explicit-files argv are NOT output-equivalent
    once a config excludes a file, so enumeration cannot be dropped.

    This mirrors the exact argv shapes in `src/rush/engines/ruff.py:59-66`
    (root dir, then every explicit file appended) against a config with
    `extend-exclude` for one file. Per design R13.2 / ruff's own documented
    behavior, explicit file arguments bypass `exclude`/`extend-exclude`
    unless `--force-exclude` is passed, so root-plus-files must surface the
    excluded file's finding while root-only must not. This is a factual
    probe of real ruff, independent of unimplemented rush dedupe code, so
    it is a keep-green guard: it passes today and documents why T13 must
    not simplify away the explicit-file argv without `--force-exclude`.

    ruff is a dev dependency; this repo allows zero skipped
    tests, so a missing binary fails this test loudly instead of skipping it.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nextend-exclude = ["excluded.py"]\n'
    )
    included = tmp_path / "included.py"
    excluded = tmp_path / "excluded.py"
    included.write_text("import os\n")
    excluded.write_text("import sys\n")

    binary = resolve_binary("ruff")
    assert binary is not None, "ruff not found on PATH; it is a required dev dependency"

    def run_ruff(argv: list[str]) -> list[dict]:
        proc = subprocess.run(
            argv,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return json.loads(proc.stdout) if proc.stdout.strip() else []

    root_only = run_ruff(
        [binary, "check", "--output-format=json", "--no-cache", str(tmp_path)]
    )
    root_plus_files = run_ruff(
        [
            binary,
            "check",
            "--output-format=json",
            "--no-cache",
            str(tmp_path),
            str(included),
            str(excluded),
        ]
    )

    root_only_files = {f["filename"] for f in root_only}
    root_plus_files_files = {f["filename"] for f in root_plus_files}

    assert str(excluded) not in root_only_files
    assert str(excluded) in root_plus_files_files
    assert root_only_files != root_plus_files_files
