"""Owner rule: zero SKIPPED tests anywhere in this repo, ever (see
`project_no_skipped_tests` memory). A `skip`/`skipif` marker whose condition
is true on this platform means the test would actually be reported SKIPPED
in a real run -- that is a defect, not an acceptable outcome, so this test
fails the suite the moment a new one is added instead of letting it slide by
quietly in `-rs` output.

This does not (and cannot, by static collection) catch a dynamic in-body
`pytest.skip(...)` call -- those are removed at the source instead (see
`test_executed_modes.py::test_fuzz_real_workload`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
