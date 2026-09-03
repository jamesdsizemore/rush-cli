"""Unit tests for ErrorCatalogTool (PR50.3)."""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.error_catalog import ErrorCatalogTool


def test_error_catalog_extracts_python_ast_exceptions(tmp_path: Path) -> None:
    py_file = tmp_path / "service.py"
    py_file.write_text(
        """
def process_user(user_id: int):
    if user_id <= 0:
        raise ValueError("Invalid user_id: must be positive")
    if user_id == 404:
        raise NotFoundError("User not found in registry")
""",
        encoding="utf-8",
    )

    tool = ErrorCatalogTool()
    result = tool.run(tmp_path)

    assert result["tool"] == "error-catalog"
    assert result["status"] == "ok"
    assert result["raw"] is not None
    catalog = result["raw"]["catalog"]
    codes = {entry["code"] for entry in catalog}
    assert "ERR_VALUE" in codes or "ERR_VALUE_ERROR" in codes
    assert "ERR_NOT_FOUND" in codes or "ERR_NOT_FOUND_ERROR" in codes

    # Check RFC 7807 fields
    not_found = next(e for e in catalog if "NOT_FOUND" in e["code"])
    assert not_found["status"] == 404
    assert (
        "User not found" in not_found["detail"] or "NotFoundError" in not_found["title"]
    )
    assert not_found["type"].startswith("https://") or not_found["type"].startswith(
        "urn:"
    )


def test_error_catalog_extracts_typescript_exceptions(tmp_path: Path) -> None:
    ts_file = tmp_path / "api.ts"
    ts_file.write_text(
        """
export function fetchResource(id: string) {
    if (!id) {
        throw new ValidationError("Resource ID is required");
    }
    if (id === "denied") {
        throw new ForbiddenError("Access forbidden to resource");
    }
}
""",
        encoding="utf-8",
    )

    tool = ErrorCatalogTool()
    result = tool.run(tmp_path)

    assert result["status"] == "ok"
    catalog = result["raw"]["catalog"]
    codes = {entry["code"] for entry in catalog}
    assert any("VALIDATION" in c for c in codes)
    assert any("FORBIDDEN" in c for c in codes)

    forbidden = next(e for e in catalog if "FORBIDDEN" in e["code"])
    assert forbidden["status"] == 403


def test_error_catalog_markdown_export_requires_artifact_write_permission(
    tmp_path: Path,
) -> None:
    py_file = tmp_path / "app.py"
    py_file.write_text('raise PermissionError("Denied")\n', encoding="utf-8")
    export_file = tmp_path / "errors.md"

    tool = ErrorCatalogTool()

    # Without permission -> export is denied / skipped
    denied = tool.run(
        tmp_path,
        export_path=export_file,
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert denied["status"] in ("skipped", "warn")
    assert not export_file.exists()
    assert "--allow-artifact-write" in denied["summary"]

    # With permission -> export succeeds
    granted = tool.run(
        tmp_path,
        export_path=export_file,
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert granted["status"] == "ok"
    assert export_file.exists()
    content = export_file.read_text(encoding="utf-8")
    assert "# Error Catalog" in content or "RFC 7807" in content
    assert "ERR_PERMISSION" in content or "PermissionError" in content


def test_error_catalog_blocks_path_traversal_export(tmp_path: Path) -> None:
    py_file = tmp_path / "app.py"
    py_file.write_text('raise RuntimeError("Crash")\n', encoding="utf-8")
    escape_file = tmp_path.parent / "escape_errors.md"

    tool = ErrorCatalogTool()
    res = tool.run(
        tmp_path,
        export_path=escape_file,
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res["status"] == "error"
    assert not escape_file.exists()


def test_error_catalog_returns_skipped_for_empty_target(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    tool = ErrorCatalogTool()
    res = tool.run(empty_dir)
    assert res["status"] == "skipped"
    assert "no supported source files" in res["summary"].lower()


def test_error_catalog_canonical_schema_and_call_interface(tmp_path: Path) -> None:
    py_file = tmp_path / "handler.py"
    py_file.write_text('raise TimeoutError("Request timed out")\n', encoding="utf-8")

    tool = ErrorCatalogTool()
    res = tool(tmp_path)

    assert res["tool"] == "error-catalog"
    assert res["status"] == "ok"
    assert isinstance(res["duration_ms"], int)
    assert isinstance(res["findings"], list)
    assert len(res["findings"]) >= 1
    finding = res["findings"][0]
    assert "path" in finding
    assert "line" in finding
    assert finding["severity"] in ("info", "warn", "error")


def test_error_catalog_extracts_rust_exceptions(tmp_path: Path) -> None:
    rs_file = tmp_path / "lib.rs"
    rs_file.write_text(
        """
pub enum NetworkError {
    Timeout,
    ConnectionReset,
}

pub struct DatabaseError;

fn query() -> Result<(), NetworkError> {
    Err(NetworkError::Timeout)
}
""",
        encoding="utf-8",
    )

    tool = ErrorCatalogTool()
    res = tool.run(tmp_path)

    assert res["status"] == "ok"
    catalog = res["raw"]["catalog"]
    codes = {entry["code"] for entry in catalog}
    assert any("NETWORK" in c for c in codes)
    assert any("DATABASE" in c for c in codes)
