"""RFC 7807 Standard Error Catalog Tool (PR50.3).

Extracts raised and thrown exceptions from Python AST and TypeScript/JavaScript source,
generates deterministic RFC 7807 Problem Details definitions, and exports formatted
catalog documentation guarded by artifact-write permission.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, ClassVar

from .base import Finding, ToolFn, ToolResult
from .common import elapsed_ms, now_ms, skipped_result


def _pascal_to_screaming_snake(name: str) -> str:
    """Convert PascalCase or camelCase class name into ERR_SCREAMING_SNAKE code."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", name)
    if not cleaned:
        return "ERR_UNKNOWN"
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", cleaned)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).upper()
    s2 = s2.removesuffix("_ERROR")
    s2 = s2.removesuffix("_EXCEPTION")
    if not s2.startswith("ERR_"):
        s2 = f"ERR_{s2}"
    return s2


def _infer_http_status(class_name: str, code: str) -> int:
    """Infer deterministic RFC 7807 HTTP status code based on error naming semantics."""
    upper = (class_name + "_" + code).upper()
    if any(k in upper for k in ("NOT_FOUND", "MISSING", "NO_SUCH", "NOTFOUND")):
        return 404
    if any(
        k in upper for k in ("UNAUTHORIZED", "UNAUTHENTICATED", "INVALID_TOKEN", "AUTH")
    ):
        return 401
    if any(
        k in upper for k in ("FORBIDDEN", "PERMISSION", "ACCESS_DENIED", "NOT_ALLOWED")
    ):
        return 403
    if any(k in upper for k in ("CONFLICT", "DUPLICATE", "ALREADY_EXISTS")):
        return 409
    if any(
        k in upper
        for k in (
            "VALIDATION",
            "VALUE_ERROR",
            "TYPE_ERROR",
            "INVALID",
            "SCHEMA",
            "BAD_REQUEST",
        )
    ):
        return 422
    if any(k in upper for k in ("RATE_LIMIT", "THROTTLE", "TOO_MANY_REQUESTS")):
        return 429
    if any(k in upper for k in ("TIMEOUT", "GATEWAY", "DEADLINE")):
        return 504
    if any(k in upper for k in ("NOT_IMPLEMENTED", "UNSUPPORTED")):
        return 501
    return 500


class ErrorCatalogTool(ToolFn):
    """Catalog raised/thrown exceptions into deterministic RFC 7807 problem details."""

    name = "error-catalog"

    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".py", ".ts", ".tsx", ".js", ".jsx"}

    @property
    def mcp_description(self) -> str:
        return (
            "Extract Python and TS exceptions at <path>, generate RFC 7807 problem "
            "catalog; export markdown requires --allow-artifact-write."
        )

    def __call__(
        self,
        path: Path,
        *,
        allow_artifact_write: bool = False,
        export_path: Path | str | None = None,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(artifact_write=allow_artifact_write)
        return self.run(path, export_path=export_path, permissions=permissions)

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        export_path: Path | str | None = None,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        perms = permissions or ExecutionPermissions()
        root = path.resolve() if path.is_dir() else path.parent.resolve()

        # Collect source files
        files: list[Path] = []
        if path.is_file():
            if path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                files = [path]
        elif path.is_dir():
            for p in sorted(path.rglob("*")):
                if p.is_file() and p.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    parts = set(p.parts)
                    if not parts.intersection(
                        {
                            ".git",
                            ".venv",
                            ".rush",
                            "node_modules",
                            "dist",
                            "build",
                            "__pycache__",
                        }
                    ):
                        files.append(p)

        if not files:
            res = skipped_result(
                self.name,
                "error-catalog",
                f"error-catalog: no supported source files found under {path}",
                duration_ms=elapsed_ms(start),
            )
            res["metadata"] = {
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="error-catalog",
                )
            }
            return res

        findings: list[Finding] = []
        raw_occurrences: list[dict[str, Any]] = []

        for src_file in files:
            rel_path = (
                str(src_file.relative_to(root))
                if src_file.is_relative_to(root)
                else str(src_file)
            )
            if src_file.suffix == ".py":
                self._extract_python_exceptions(
                    src_file, rel_path, raw_occurrences, findings
                )
            else:
                self._extract_ts_js_exceptions(
                    src_file, rel_path, raw_occurrences, findings
                )

        # Aggregate into RFC 7807 catalog entries
        catalog_map: dict[str, dict[str, Any]] = {}
        for occ in raw_occurrences:
            code = occ["code"]
            if code not in catalog_map:
                status_code = _infer_http_status(occ["class_name"], code)
                slug = code.lower().replace("_", "-")
                catalog_map[code] = {
                    "code": code,
                    "class_name": occ["class_name"],
                    "status": status_code,
                    "title": occ["class_name"],
                    "type": f"https://rush-cli.org/errors/{slug}",
                    "detail": occ["message"]
                    or f"An error of type {occ['class_name']} was encountered.",
                    "occurrences": [],
                }
            catalog_map[code]["occurrences"].append(
                {
                    "path": occ["path"],
                    "line": occ["line"],
                    "message": occ["message"],
                }
            )

        catalog_entries = list(catalog_map.values())
        catalog_entries.sort(key=lambda x: x["code"])

        # Handle Markdown export if requested
        artifacts: list[str] = []
        if export_path is not None:
            exp = Path(export_path)
            if not exp.is_absolute():
                exp = (root / exp).resolve()
            else:
                exp = exp.resolve()

            # Path traversal containment check
            if not exp.is_relative_to(root):
                return ToolResult(
                    tool=self.name,
                    engine="error-catalog",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary=f"error-catalog: export path '{export_path}' escapes target root '{root}'",
                    findings=[],
                    raw=None,
                    metadata={
                        "execution": build_execution_metadata(
                            mode="executed",
                            requested=perms,
                            granted=perms,
                            producer="error-catalog",
                        )
                    },
                )

            if not perms.artifact_write:
                res = ToolResult(
                    tool=self.name,
                    engine="error-catalog",
                    engine_version="1.0.0",
                    status="skipped",
                    duration_ms=elapsed_ms(start),
                    summary=(
                        f"error-catalog: writing export artifact to '{export_path}' "
                        "requires explicit --allow-artifact-write permission."
                    ),
                    findings=findings,
                    raw={
                        "catalog": catalog_entries,
                        "total_errors": len(raw_occurrences),
                    },
                    metadata={
                        "execution": build_execution_metadata(
                            mode="executed",
                            requested=perms,
                            granted=perms,
                            producer="error-catalog",
                        )
                    },
                )
                return res

            exp.parent.mkdir(parents=True, exist_ok=True)
            markdown_content = self.generate_markdown(catalog_entries)
            exp.write_text(markdown_content, encoding="utf-8")
            artifacts.append(str(exp))

        summary = (
            f"error-catalog: cataloged {len(catalog_entries)} unique RFC 7807 error types "
            f"({len(raw_occurrences)} occurrences across {len(files)} files)"
        )

        return ToolResult(
            tool=self.name,
            engine="error-catalog",
            engine_version="1.0.0",
            status="ok",
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            raw={
                "catalog": catalog_entries,
                "total_unique_errors": len(catalog_entries),
                "total_occurrences": len(raw_occurrences),
            },
            artifacts=artifacts if artifacts else None,
            metadata={
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="error-catalog",
                ),
                "export_path": str(export_path) if export_path else None,
            },
        )

    def _extract_python_exceptions(
        self,
        src_file: Path,
        rel_path: str,
        occurrences: list[dict[str, Any]],
        findings: list[Finding],
    ) -> None:
        try:
            tree = ast.parse(
                src_file.read_text(encoding="utf-8", errors="ignore"),
                filename=str(src_file),
            )
        except Exception:  # noqa: BLE001
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Raise):
                class_name = "RuntimeError"
                message = ""
                line = getattr(node, "lineno", 1)
                col = getattr(node, "col_offset", 0) + 1

                if node.exc is not None:
                    if isinstance(node.exc, ast.Call):
                        func = node.exc.func
                        if isinstance(func, ast.Name):
                            class_name = func.id
                        elif isinstance(func, ast.Attribute):
                            class_name = func.attr
                        if node.exc.args:
                            first_arg = node.exc.args[0]
                            if isinstance(first_arg, ast.Constant) and isinstance(
                                first_arg.value, str
                            ):
                                message = first_arg.value
                    elif isinstance(node.exc, ast.Name):
                        class_name = node.exc.id
                    elif isinstance(node.exc, ast.Attribute):
                        class_name = node.exc.attr

                code = _pascal_to_screaming_snake(class_name)
                occurrences.append(
                    {
                        "path": rel_path,
                        "line": line,
                        "class_name": class_name,
                        "code": code,
                        "message": message,
                    }
                )
                findings.append(
                    Finding(
                        path=rel_path,
                        line=line,
                        column=col,
                        rule="error-catalog",
                        rule_id=code,
                        severity="info",
                        message=f"{class_name}: {message}" if message else class_name,
                        fingerprint=f"{rel_path}:{line}:{code}",
                    )
                )

    def _extract_ts_js_exceptions(
        self,
        src_file: Path,
        rel_path: str,
        occurrences: list[dict[str, Any]],
        findings: list[Finding],
    ) -> None:
        try:
            content = src_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return

        lines = content.splitlines()
        throw_new_pattern = re.compile(
            r"""throw\s+new\s+([A-Za-z0-9_$]+)\s*\(\s*(?:['"`](.*?)['"`]|(.*?))\s*\)"""
        )
        throw_pattern = re.compile(
            r"""throw\s+([A-Za-z0-9_$]+)\s*\(\s*(?:['"`](.*?)['"`]|(.*?))\s*\)"""
        )
        throw_str_pattern = re.compile(r"""throw\s+['"`](.*?)['"`]""")

        for line_idx, line_text in enumerate(lines, start=1):
            if "throw" not in line_text:
                continue

            match = throw_new_pattern.search(line_text) or throw_pattern.search(
                line_text
            )
            if match:
                class_name = match.group(1)
                message = match.group(2) or match.group(3) or ""
            else:
                str_match = throw_str_pattern.search(line_text)
                if str_match:
                    class_name = "Error"
                    message = str_match.group(1)
                else:
                    continue

            code = _pascal_to_screaming_snake(class_name)
            occurrences.append(
                {
                    "path": rel_path,
                    "line": line_idx,
                    "class_name": class_name,
                    "code": code,
                    "message": message,
                }
            )
            findings.append(
                Finding(
                    path=rel_path,
                    line=line_idx,
                    column=1,
                    rule="error-catalog",
                    rule_id=code,
                    severity="info",
                    message=f"{class_name}: {message}" if message else class_name,
                    fingerprint=f"{rel_path}:{line_idx}:{code}",
                )
            )

    def generate_markdown(self, catalog: list[dict[str, Any]]) -> str:
        """Generate structured RFC 7807 Markdown documentation."""
        md = [
            "# Error Catalog (RFC 7807 Problem Details)",
            "",
            "Automated deterministic exception catalog generated by Rush CLI.",
            "",
            "| Error Code | HTTP Status | Title / Class | URI Type | Occurrences |",
            "|---|---|---|---|---|",
        ]
        for entry in catalog:
            md.append(
                f"| `{entry['code']}` | `{entry['status']}` | `{entry['title']}` | [{entry['type']}]({entry['type']}) | {len(entry['occurrences'])} |"
            )

        md.append("")
        md.append("## Error Details")
        md.append("")

        for entry in catalog:
            md.append(f"### `{entry['code']}` — {entry['title']}")
            md.append(f"- **HTTP Status**: `{entry['status']}`")
            md.append(f"- **Type URI**: `{entry['type']}`")
            md.append(f"- **Default Detail**: {entry['detail']}")
            md.append("- **Locations**:")
            for occ in entry["occurrences"]:
                msg_suffix = f' — *"{occ["message"]}"*' if occ["message"] else ""
                md.append(f"  - `{occ['path']}:{occ['line']}`{msg_suffix}")
            md.append("")

        return "\n".join(md)
