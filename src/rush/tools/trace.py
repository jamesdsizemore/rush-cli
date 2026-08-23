"""Spec-to-code and requirement-to-test traceability scanner."""

import re
from pathlib import Path
from typing import Any


class TraceScanner:
    """Scans for requirement tags (e.g. [REQ-001], FR-01-01) across docs, source AST, and test suites."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def scan_traceability(self) -> dict[str, Any]:
        req_tags: set[str] = set()
        code_impls: dict[str, list[str]] = {}
        test_covers: dict[str, list[str]] = {}

        # 1. Extract requirements from docs/specs
        for doc in self.project_root.glob("docs/**/*.md"):
            try:
                text = doc.read_text(encoding="utf-8", errors="ignore")
                matches = re.findall(r"\b(FR-\d{2}-\d{2}|REQ-\d{3,4})\b", text)
                for m in matches:
                    req_tags.add(m)
            except Exception:  # noqa: BLE001, S110
                pass

        # 2. Extract implementations from source code
        for py_file in (self.project_root / "src").glob("**/*.py"):
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                for req in req_tags:
                    if req in code:
                        rel = str(py_file.relative_to(self.project_root))
                        code_impls.setdefault(req, []).append(rel)
            except Exception:  # noqa: BLE001, S110
                pass

        # 3. Extract test coverage
        for test_file in (self.project_root / "tests").glob("**/*.py"):
            try:
                code = test_file.read_text(encoding="utf-8", errors="ignore")
                for req in req_tags:
                    if req in code:
                        rel = str(test_file.relative_to(self.project_root))
                        test_covers.setdefault(req, []).append(rel)
            except Exception:  # noqa: BLE001, S110
                pass

        matrix: list[dict[str, Any]] = []
        for req in sorted(req_tags):
            impls = code_impls.get(req, [])
            tests = test_covers.get(req, [])
            status = (
                "VERIFIED"
                if (impls and tests)
                else ("IMPLEMENTED" if impls else "SPEC_ONLY")
            )
            matrix.append(
                {
                    "requirement": req,
                    "status": status,
                    "implementations": impls,
                    "tests": tests,
                }
            )

        return {
            "total_requirements": len(req_tags),
            "matrix": matrix,
        }
