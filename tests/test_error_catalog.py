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


def test_error_catalog_uses_typescript_structure_for_real_throws(
    tmp_path: Path,
) -> None:
    ts_file = tmp_path / "handler.ts"
    ts_file.write_text(
        """import { NamedImportedError } from './errors';
// throw new CommentedFakeError('fake');
const stringFake = "throw new StringFakeError('fake')";
const templateFake = `throw new TemplateFakeError('fake')`;

export function handle(value: string) {
  throw new NamedImportedError(
    makeMessage(
      "real detail",
      value,
    ),
  );
}
""",
        encoding="utf-8",
    )

    result = ErrorCatalogTool().run(ts_file)

    assert result["status"] == "ok"
    assert result["raw"]["total_occurrences"] == 1
    assert [entry["code"] for entry in result["raw"]["catalog"]] == [
        "ERR_NAMED_IMPORTED"
    ]
    entry = result["raw"]["catalog"][0]
    assert entry["class_name"] == "NamedImportedError"
    assert entry["occurrences"] == [
        {
            "path": "handler.ts",
            "line": 7,
            "message": 'makeMessage(\n      "real detail",\n      value,\n    )',
        }
    ]


def test_error_catalog_reports_partial_typescript_parse_error(tmp_path: Path) -> None:
    ts_file = tmp_path / "broken.ts"
    ts_file.write_text("export function broken( {\n", encoding="utf-8")

    result = ErrorCatalogTool().run(ts_file)

    assert result["status"] == "error"
    assert result["raw"]["partial"] is True
    assert result["raw"]["catalog"] == []
    assert result["findings"][0]["rule"] == "error-catalog/parse-error"


def test_error_catalog_skips_comments_and_unwraps_parenthesized_throws(
    tmp_path: Path,
) -> None:
    ts_file = tmp_path / "comments.ts"
    ts_file.write_text(
        """export function first() {
  throw /* reason */ new NamedImportedError(/* detail */ "real");
}
export function second() {
  throw (new WrappedError("wrapped"));
}
""",
        encoding="utf-8",
    )

    result = ErrorCatalogTool().run(ts_file)

    assert result["status"] == "ok"
    assert [entry["code"] for entry in result["raw"]["catalog"]] == [
        "ERR_NAMED_IMPORTED",
        "ERR_WRAPPED",
    ]
    assert {
        entry["class_name"]: entry["occurrences"][0]["message"]
        for entry in result["raw"]["catalog"]
    } == {"NamedImportedError": "real", "WrappedError": "wrapped"}


def test_error_catalog_routes_tsx_and_jsx_to_jsx_grammar(tmp_path: Path) -> None:
    for suffix in (".tsx", ".jsx"):
        source_file = tmp_path / f"component{suffix}"
        source_file.write_text(
            "export function render() { throw new RenderError(<span>bad</span>); }",
            encoding="utf-8",
        )
        result = ErrorCatalogTool().run(source_file)

        assert result["status"] == "ok", suffix
        assert result["raw"]["total_occurrences"] == 1, suffix
        assert result["raw"]["catalog"][0]["class_name"] == "RenderError", suffix
        assert result["raw"]["catalog"][0]["detail"] == "<span>bad</span>", suffix


def test_locked_typescript_grammar_loads() -> None:
    import tree_sitter_typescript
    from tree_sitter import Language, Parser

    source = b"throw new LockedRuntimeError('boom');"
    languages = (
        Language(tree_sitter_typescript.language_typescript()),
        Language(tree_sitter_typescript.language_tsx()),
    )

    for language in languages:
        root = Parser(language).parse(source).root_node
        assert root.has_error is False
        assert any(node.type == "throw_statement" for node in root.children)


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
