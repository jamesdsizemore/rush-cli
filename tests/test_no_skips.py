"""Owner rule: zero SKIPPED tests anywhere in this repo, ever (see
`project_no_skipped_tests` memory). A `skip`/`skipif` marker whose condition
is true on this platform means the test would actually be reported SKIPPED
in a real run -- that is a defect, not an acceptable outcome, so this test
fails the suite the moment a new one is added instead of letting it slide by
quietly in `-rs` output.

Dynamic skips (an in-body `pytest.skip(...)`, a fixture that skips, an
`importorskip`, a module-level skip) are caught at run time: conftest.py
records every skipped report and fails the session, naming each one; the
pytester tests below prove each kind does.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

pytest_plugins = ["pytester"]

ROOT = Path(__file__).resolve().parents[1]
_CONFTEST = ROOT / "tests" / "conftest.py"

_COLLECTOR_PLUGIN = """
import json


def pytest_collection_modifyitems(config, items):
    offenders = []
    for item in items:
        if item.get_closest_marker("skip") is not None:
            offenders.append(item.nodeid)
            continue
        marker = item.get_closest_marker("skipif")
        if marker is not None and marker.args and marker.args[0]:
            offenders.append(item.nodeid)
    print("SKIP_OFFENDERS=" + json.dumps(offenders))
"""


def test_no_collected_test_carries_a_live_skip_marker(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no_skips_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "_no_skips_collector.py").write_text(
        _COLLECTOR_PLUGIN, encoding="utf-8"
    )

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(plugin_dir), env.get("PYTHONPATH")])
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "_no_skips_collector",
            "tests/",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    marker_line = next(
        line
        for line in result.stdout.splitlines()
        if line.startswith("SKIP_OFFENDERS=")
    )
    offenders = json.loads(marker_line.removeprefix("SKIP_OFFENDERS="))
    assert offenders == [], f"live skip/skipif marker(s) on this platform: {offenders}"


_SKIPPERS = {
    "in_body": "import pytest\n\ndef test_x():\n    pytest.skip('no')\n",
    "fixture": (
        "import pytest\n\n@pytest.fixture\ndef gone():\n    pytest.skip('no')\n\n"
        "def test_x(gone):\n    pass\n"
    ),
    "importorskip": (
        "import pytest\n\ndef test_x():\n"
        "    pytest.importorskip('rush_no_such_module')\n"
    ),
    "module_level": (
        "import pytest\n\npytest.skip('no', allow_module_level=True)\n\n"
        "def test_x():\n    pass\n"
    ),
    "module_importorskip": (
        "import pytest\n\npytest.importorskip('rush_no_such_module')\n\n"
        "def test_x():\n    pass\n"
    ),
    "skip_marker": "import pytest\n\n@pytest.mark.skip\ndef test_x():\n    pass\n",
    "xfail": "import pytest\n\n@pytest.mark.xfail\ndef test_x():\n    assert False\n",
}


@pytest.mark.parametrize("kind", sorted(_SKIPPERS))
def test_every_kind_of_skip_fails_the_session(
    pytester: pytest.Pytester, kind: str
) -> None:
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_skipper=_SKIPPERS[kind], test_fine="def test_ok():\n    pass\n"
    )
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    assert result.ret == pytest.ExitCode.TESTS_FAILED, result.stdout.str()
    result.stdout.fnmatch_lines(["*ZERO SKIP GUARD*", "*test_skipper.py*"])


def test_a_session_without_skips_passes(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(test_fine="def test_ok():\n    pass\n")
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    assert result.ret == pytest.ExitCode.OK, result.stdout.str()
    assert "ZERO SKIP GUARD" not in result.stdout.str()


class _Item:
    def __init__(self, *markers: str) -> None:
        self.markers = markers

    def iter_markers(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name=name) for name in self.markers]


def _which(present: set[str]) -> Callable[[str], str | None]:
    return lambda binary: f"/bin/{binary}" if binary in present else None


@pytest.mark.parametrize(
    ("markers", "platform", "present", "expected"),
    [
        (("posix_only",), {"is_windows": True}, set(), "posix_only"),
        (("posix_only",), {}, set(), None),
        (("posix_nonroot",), {"is_windows": True}, set(), "posix_nonroot"),
        (("posix_nonroot",), {"is_root": True}, set(), "posix_nonroot"),
        (("posix_nonroot",), {}, set(), None),
        (("windows_only",), {}, set(), "windows_only"),
        (("windows_only",), {"is_windows": True}, set(), None),
        (("atheris_only",), {}, set(), "atheris_only"),
        (("atheris_only",), {"is_linux_x86_64": True}, set(), None),
        (("needs_promptfoo",), {}, set(), "needs_promptfoo"),
        (("needs_promptfoo",), {}, {"promptfoo"}, None),
        (("needs_pip_audit",), {}, {"pip-audit"}, None),
        (("needs_pip_audit",), {}, {"pip_audit"}, "needs_pip_audit"),
        (("needs_npm_audit",), {}, {"npm"}, None),
        (("needs_npm_audit",), {}, set(), "needs_npm_audit"),
        ((), {"is_windows": True, "is_root": True}, set(), None),
    ],
)
def test_deselection_rules(
    markers: tuple[str, ...],
    platform: dict[str, bool],
    present: set[str],
    expected: str | None,
) -> None:
    from conftest import _deselected_by

    item = cast(pytest.Item, _Item(*markers))
    deselected = _deselected_by(
        item,
        is_windows=platform.get("is_windows", False),
        is_linux_x86_64=platform.get("is_linux_x86_64", False),
        is_root=platform.get("is_root", False),
        which=_which(present),
    )
    assert deselected == expected


def test_missing_binary_marker_is_deselected_and_counted(
    pytester: pytest.Pytester,
) -> None:
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_needs="""
        import pytest


        @pytest.mark.needs_rush_no_such_binary
        def test_gone():
            raise AssertionError("must be deselected")


        @pytest.mark.posix_only
        def test_posix():
            import os

            assert os.name != "nt"


        def test_ok():
            pass
        """
    )
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=2, deselected=1)
    result.stdout.fnmatch_lines(
        ["*needs_rush_no_such_binary: 1 deselected (rush-no-such-binary not on PATH)*"]
    )
