"""Unit tests for the git diff symbol and placeholder verification script."""

from __future__ import annotations

from scripts.verify_diff_symbols import (
    check_diff_for_banned_tokens,
    check_diff_for_required_symbols,
    parse_diff_added_lines,
)

SAMPLE_DIFF_BAD = """diff --git a/src/rush/tools/sample.py b/src/rush/tools/sample.py
index 1111111..2222222 100644
--- a/src/rush/tools/sample.py
+++ b/src/rush/tools/sample.py
@@ -10,3 +10,4 @@ def test():
     x = 1
+    status = "unknown"
     return x
"""

SAMPLE_DIFF_GOOD = """diff --git a/src/rush/tools/sample.py b/src/rush/tools/sample.py
index 1111111..2222222 100644
--- a/src/rush/tools/sample.py
+++ b/src/rush/tools/sample.py
@@ -10,3 +10,4 @@ def test():
     x = 1
+    status = "ok"
     return x
"""


def test_parse_diff_added_lines() -> None:
    added = parse_diff_added_lines(SAMPLE_DIFF_BAD)
    assert len(added) == 1
    filename, _lineno, content = added[0]
    assert filename == "src/rush/tools/sample.py"
    assert 'status = "unknown"' in content


def test_detects_banned_token_in_diff() -> None:
    violations = check_diff_for_banned_tokens(SAMPLE_DIFF_BAD)
    assert len(violations) == 1
    assert "Added banned placeholder 'unknown'" in violations[0]


def test_passes_on_clean_diff() -> None:
    violations = check_diff_for_banned_tokens(SAMPLE_DIFF_GOOD)
    assert violations == []


def test_detects_missing_required_symbols() -> None:
    missing = check_diff_for_required_symbols(
        SAMPLE_DIFF_GOOD, ["Licensing().parse", "hcl2.loads"]
    )
    assert len(missing) == 2
    assert (
        "Diff lacks required engine symbol or call: 'Licensing().parse'" in missing[0]
    )
    assert "Diff lacks required engine symbol or call: 'hcl2.loads'" in missing[1]


def test_passes_when_required_symbols_present() -> None:
    diff_with_symbol = """diff --git a/src/rush/tools/license.py b/src/rush/tools/license.py
+++ b/src/rush/tools/license.py
@@ -1,3 +1,4 @@
+from license_expression import Licensing
+result = Licensing().parse("MIT OR Apache-2.0")
"""
    missing = check_diff_for_required_symbols(diff_with_symbol, ["Licensing().parse"])
    assert missing == []
