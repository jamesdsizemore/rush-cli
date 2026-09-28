"""Full-scan engine applicability: an engine with no owning tool and catalog
`project_markers` is planned only when one of those markers exists at the
project root. Otherwise it is `not_applicable` with the absent markers as
its reason and is never scheduled (pitest must not run `mvn` on a Python
project, even with a real `mvn` on PATH)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rush.catalog import ENGINE_SPECS, TOOL_SPECS
from rush.runtime.binaries import clear_binary_cache
from rush.workflows.project_run import ScanCandidate, plan_scan
from rush.workflows.projects import register_project

_OWNED = {name for spec in TOOL_SPECS.values() for name in spec.engine_names}
GATED_ENGINES = sorted(
    name
    for name, spec in ENGINE_SPECS.items()
    if name not in _OWNED and spec.capability != "workflow" and spec.project_markers
)


def test_gated_engine_set_is_enumerated_from_the_catalog() -> None:
    assert GATED_ENGINES == [
        "backstop",
        "cargo-mutants",
        "cosmic-ray",
        "depcruise",
        "detect-secrets",
        "fawltydeps",
        "flake8-bugbear",
        "infection",
        "lost-pixel",
        "memray",
        "pip-licenses",
        "pitest",
        "refurb",
        "scorecard",
        "stryker",
        "stylelint",
        "tach",
        "ts-prune",
    ]


def _plan(tmp_path: Path, root: Path) -> dict[str, ScanCandidate]:
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    plan = plan_scan(record.project_id, data_root=data_root)
    return {c.candidate_id: c for c in plan.candidates}


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    return root


def _reason(name: str) -> str:
    return "project_marker_absent:" + ",".join(ENGINE_SPECS[name].project_markers)


def test_python_project_with_mvn_on_path_plans_no_pitest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "mvn"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    clear_binary_cache()
    try:
        by_id = _plan(tmp_path, root)
    finally:
        clear_binary_cache()

    pitest = by_id["pitest"]
    assert pitest.disposition == "not_applicable"
    assert pitest.reason == "project_marker_absent:pom.xml"


def test_java_project_still_plans_pitest(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pom.xml").write_text("<project/>\n", encoding="utf-8")

    by_id = _plan(tmp_path, root)

    assert by_id["pitest"].disposition == "applicable"


@pytest.mark.parametrize("engine", GATED_ENGINES)
def test_gated_engine_without_marker_is_not_applicable(
    tmp_path: Path, engine: str
) -> None:
    by_id = _plan(tmp_path, _project(tmp_path))

    assert by_id[engine].disposition == "not_applicable"
    assert by_id[engine].reason == _reason(engine)


@pytest.mark.parametrize("engine", GATED_ENGINES)
def test_gated_engine_with_marker_is_applicable(tmp_path: Path, engine: str) -> None:
    root = _project(tmp_path)
    for marker in ENGINE_SPECS[engine].project_markers:
        target = root / marker
        if marker == ".github/workflows":
            target.mkdir(parents=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        by_id = _plan(tmp_path, root)
        assert by_id[engine].disposition == "applicable", marker
        if target.is_dir():
            target.rmdir()
        else:
            target.unlink()
