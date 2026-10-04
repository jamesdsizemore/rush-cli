#!/usr/bin/env python3
"""Gate a test author's work before it's accepted.

Usage: test-acceptance.py <test_file> <base_path> <map_file>

map_file lines:
  <bullet text> -> <test_id>
  must-fail: <test_id>[, <test_id> ...]

Checks:
  (a) AST: every test_* function has an assertion (assert / pytest.raises);
      if it also calls pytest.fail(...), an assert/pytest.raises must occur
      after that call.
  (b) every bullet is mapped to a test_id that exists as a function in the
      test file; no unmapped bullets.
  (c) running the file against <base_path>'s pyproject.toml, every test_id
      listed under must-fail actually fails (red phase).
"""

import ast
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def check_ast(test_file: str) -> list[str]:
    src = Path(test_file).read_text()
    tree = ast.parse(src, filename=test_file)
    errors = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
            continue
        asserts = []
        fails = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert):
                asserts.append(sub.lineno)
            elif isinstance(sub, ast.Call):
                func = sub.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name == "raises":
                    asserts.append(sub.lineno)
                elif name == "fail":
                    fails.append(sub.lineno)
        if not asserts:
            errors.append(f"{node.name}: no assert/pytest.raises found")
            continue
        for fail_line in fails:
            if not any(a > fail_line for a in asserts):
                errors.append(
                    f"{node.name}: pytest.fail at line {fail_line} with no assert/pytest.raises after it"
                )
    return errors


def test_function_names(test_file: str) -> set[str]:
    tree = ast.parse(Path(test_file).read_text(), filename=test_file)
    return {
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    }


def parse_map(map_file: str) -> tuple[dict[str, str], list[str]]:
    bullets: dict[str, str] = {}
    must_fail: list[str] = []
    for line in Path(map_file).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("must-fail:"):
            ids = line[len("must-fail:"):].split(",")
            must_fail.extend(i.strip() for i in ids if i.strip())
            continue
        if "->" not in line:
            continue
        bullet, test_id = line.split("->", 1)
        bullets[bullet.strip()] = test_id.strip()
    return bullets, must_fail


def check_bullets(bullets: dict[str, str], defined: set[str]) -> list[str]:
    errors = []
    for bullet, test_id in bullets.items():
        if not test_id:
            errors.append(f"bullet unmapped: {bullet!r}")
        elif test_id not in defined:
            errors.append(f"bullet {bullet!r} maps to {test_id!r}, which is not defined in the test file")
    return errors


def check_must_fail(test_file: str, base_path: str, must_fail: list[str]) -> list[str]:
    if not must_fail:
        return []
    pyproject = str(Path(base_path) / "pyproject.toml")
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        junit_path = tmp.name
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-c", pyproject, "--rootdir", base_path,
             f"--junitxml={junit_path}", "-q"],
            capture_output=True, text=True, check=False,
        )
        outcomes: dict[str, str] = {}
        texts: dict[str, str] = {}
        try:
            root = ET.parse(junit_path).getroot()
            for case in root.iter("testcase"):
                name = case.get("name", "")
                fail = case.find("failure")
                message = (fail.get("message") or "") if fail is not None else ""
                texts[name] = message + "\n" + ((fail.text or "") if fail is not None else "")
                # A red test fails on an assertion or on a pytest.raises block that did not raise;
                # an import error, a typo or a collection error is not red.
                if fail is not None and message.startswith(("assert", "AssertionError", "Failed: DID NOT RAISE")):
                    outcomes[name] = "failed"
                elif fail is not None or case.find("error") is not None:
                    outcomes[name] = "errored (not an assertion failure)"
                else:
                    outcomes[name] = "passed"
        except ET.ParseError:
            pass
    finally:
        Path(junit_path).unlink(missing_ok=True)

    errors = []
    for entry in must_fail:
        # `test_id` or `test_id ~ signature`: with a signature the failure text must contain it.
        test_id, _, signature = (p.strip() for p in entry.partition("~"))
        outcome = outcomes.get(test_id)
        if outcome is None:
            errors.append(f"must-fail test {test_id!r} not found in pytest results")
        elif outcome != "failed":
            errors.append(f"must-fail test {test_id!r} did not fail (outcome: {outcome})")
        elif signature and signature not in texts.get(test_id, ""):
            errors.append(f"must-fail test {test_id!r} failed, but not with the stated signature {signature!r}")
    return errors


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: test-acceptance.py <test_file> <base_path> <map_file>", file=sys.stderr)
        return 2
    test_file, base_path, map_file = sys.argv[1:4]

    errors = check_ast(test_file)
    bullets, must_fail = parse_map(map_file)
    errors += check_bullets(bullets, test_function_names(test_file))
    errors += check_must_fail(test_file, base_path, must_fail)

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
