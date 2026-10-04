#!/usr/bin/env python3
"""Fixture test for test-acceptance.py: AST assert/pytest.fail-gate check,
bullet-map validation, and the real (no-network) must-fail pytest run
against a base checkout."""

import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "test-acceptance.py")

GOOD_TEST = '''
import pytest

def test_should_fail():
    assert 1 == 2

def test_should_pass():
    assert 1 == 1

def test_uses_raises():
    with pytest.raises(ValueError):
        raise ValueError("boom")

def test_gate_then_assert():
    pytest.fail("not implemented")
    assert False
'''

BAD_TEST = '''
import pytest

def test_no_assertion():
    x = 1 + 1

def test_gate_no_after():
    pytest.fail("todo")
'''


def write(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    fail = 0
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "base")
        os.makedirs(base)
        write(os.path.join(base, "pyproject.toml"), "[tool.pytest.ini_options]\n")

        good_file = os.path.join(d, "test_good.py")
        bad_file = os.path.join(d, "test_bad.py")
        write(good_file, GOOD_TEST)
        write(bad_file, BAD_TEST)

        # --- AST check: bad file fails on both no-assert and gate-no-after ---
        empty_map = os.path.join(d, "empty_map.txt")
        write(empty_map, "")
        code, out = run(bad_file, base, empty_map)
        if code == 0:
            print("FAIL: bad test file should be rejected")
            fail = 1
        if "test_no_assertion" not in out or "test_gate_no_after" not in out:
            print(f"FAIL: expected both bad functions named in output, got: {out!r}")
            fail = 1

        # --- AST check: good file passes with no must-fail bullets ---
        code, out = run(good_file, base, empty_map)
        if code != 0:
            print(f"FAIL: good test file should pass AST check, got: {out!r}")
            fail = 1

        # --- bullet map: unmapped bullet and bad-mapped id both rejected ---
        bad_map = os.path.join(d, "bad_map.txt")
        write(bad_map, "some bullet -> \nother bullet -> test_does_not_exist\n")
        code, out = run(good_file, base, bad_map)
        if code == 0:
            print("FAIL: unmapped/bad-mapped bullets should be rejected")
            fail = 1
        if "unmapped" not in out:
            print(f"FAIL: expected 'unmapped' in output, got: {out!r}")
            fail = 1
        if "test_does_not_exist" not in out:
            print(f"FAIL: expected bad mapped id named, got: {out!r}")
            fail = 1

        # --- bullet map: valid mapping passes ---
        good_map = os.path.join(d, "good_map.txt")
        write(good_map, "bullet one -> test_should_fail\nbullet two -> test_should_pass\n")
        code, out = run(good_file, base, good_map)
        if code != 0:
            print(f"FAIL: valid bullet map should pass, got: {out!r}")
            fail = 1

        # --- must-fail: real pytest run, test_should_fail actually fails ---
        must_fail_ok = os.path.join(d, "must_fail_ok.txt")
        write(must_fail_ok, "b -> test_should_fail\nmust-fail: test_should_fail\n")
        code, out = run(good_file, base, must_fail_ok)
        if code != 0:
            print(f"FAIL: must-fail on a genuinely failing test should pass, got: {out!r}")
            fail = 1

        # --- must-fail: listed test actually passes -> rejected ---
        must_fail_bad = os.path.join(d, "must_fail_bad.txt")
        write(must_fail_bad, "b -> test_should_pass\nmust-fail: test_should_pass\n")
        code, out = run(good_file, base, must_fail_bad)
        if code == 0:
            print("FAIL: must-fail on a passing test should be rejected")
            fail = 1
        if "did not fail" not in out:
            print(f"FAIL: expected 'did not fail' in output, got: {out!r}")
            fail = 1

        # --- plan F2/F27: red means an assertion, not an import error; a missing raise is red;
        # ---              a stated signature must appear in the failure ---
        red_file = os.path.join(d, "test_red.py")
        write(red_file, (
            "import pytest\n\n"
            "def test_asserts():\n    assert 1 == 2, 'flag missing'\n\n"
            "def test_import_breaks():\n    import module_that_does_not_exist\n    assert True\n\n"
            "def test_no_raise():\n    with pytest.raises(ValueError):\n        pass\n"
        ))
        red_map = os.path.join(d, "red_map.txt")
        write(red_map, "a -> test_asserts\nb -> test_import_breaks\nc -> test_no_raise\n"
                       "must-fail: test_asserts, test_import_breaks, test_no_raise\n")
        code, out = run(red_file, base, red_map)
        if code == 0 or "test_import_breaks" not in out or "errored" not in out:
            print(f"FAIL: an import error must not count as red, got: {out!r}")
            fail = 1
        if "test_asserts" in out or "test_no_raise" in out:
            print(f"FAIL: an assertion failure and a missing raise are red, got: {out!r}")
            fail = 1
        sig_ok = os.path.join(d, "sig_ok.txt")
        write(sig_ok, "a -> test_asserts\nc -> test_no_raise\n"
                      "must-fail: test_asserts ~ flag missing, test_no_raise ~ DID NOT RAISE\n")
        code, out = run(red_file, base, sig_ok)
        if code != 0:
            print(f"FAIL: matching signatures should pass, got: {out!r}")
            fail = 1
        sig_bad = os.path.join(d, "sig_bad.txt")
        write(sig_bad, "a -> test_asserts\nmust-fail: test_asserts ~ some other reason\n")
        code, out = run(red_file, base, sig_bad)
        if code == 0 or "stated signature" not in out:
            print(f"FAIL: a wrong-reason failure must be rejected, got: {out!r}")
            fail = 1

    if fail:
        print("test_test_acceptance.py: FAIL")
        return 1
    print("test_test_acceptance.py: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
