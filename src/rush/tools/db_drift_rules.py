"""Database schema drift analysis rules, model collectors, and migration parsers."""

from __future__ import annotations

import ast
import re
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

_TYPE_MAP = {
    "int": "integer",
    "integer": "integer",
    "bigint": "integer",
    "str": "text",
    "string": "text",
    "text": "text",
    "varchar": "text",
    "bool": "boolean",
    "boolean": "boolean",
    "datetime": "timestamp",
    "timestamp": "timestamp",
}


def _name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    return ""


def _normalize_type(value: str) -> str | None:
    return _TYPE_MAP.get(value.lower())


def _annotation_type(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Subscript) and _name(node.value) in {"Mapped", "Optional"}:
        return _annotation_type(node.slice)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation_type(node.left) or _annotation_type(node.right)
    return _normalize_type(_name(node))


def _annotation_nullable(node: ast.AST | None) -> bool | None:
    if node is None:
        return None
    if isinstance(node, ast.Subscript):
        if _name(node.value) == "Optional":
            return True
        return _annotation_nullable(node.slice)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return any(
            (isinstance(item, ast.Constant) and item.value is None)
            or _name(item) in {"None", "NoneType"}
            for item in (node.left, node.right)
        )
    return False


def _constant_bool(call: ast.Call, keyword: str) -> bool | None:
    item = next((kw for kw in call.keywords if kw.arg == keyword), None)
    if item is None:
        return None
    return item.value.value if isinstance(item.value, ast.Constant) else None


def _declared_column_type(call: ast.Call, annotation: ast.AST | None) -> str | None:
    keyword = "sa_type" if _name(call.func) == "Field" else "type_"
    explicit = next((kw.value for kw in call.keywords if kw.arg == keyword), None)
    if explicit is not None:
        return _normalize_type(_name(explicit))
    if _name(call.func) == "Field":
        return _annotation_type(annotation)
    args = call.args
    if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
        args = args[1:]
    return _normalize_type(_name(args[0])) if args else _annotation_type(annotation)


def _column_state(annotation: ast.AST | None, call: ast.Call | None) -> dict[str, Any]:
    column_type = _annotation_type(annotation)
    nullable = _annotation_nullable(annotation)
    if call is not None:
        column_type = _declared_column_type(call, annotation)
        explicit_nullable = _constant_bool(call, "nullable")
        primary_key = _constant_bool(call, "primary_key")
        nullable = explicit_nullable if explicit_nullable is not None else nullable
        if primary_key is True and explicit_nullable is None:
            nullable = False
        elif nullable is None:
            nullable = True
    return {"type": column_type, "nullable": nullable}


def _field_parts(item: ast.stmt) -> tuple[str, ast.AST | None, ast.AST | None]:
    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
        return item.target.id, item.annotation, item.value
    if isinstance(item, ast.Assign) and len(item.targets) == 1:
        target = item.targets[0]
        if isinstance(target, ast.Name):
            return target.id, None, item.value
    return "", None, None


def _model_field_call(
    call: ast.Call | None, owner: str, field: str, incomplete: list[str]
) -> ast.Call | None:
    if call is None:
        return None
    call_name = _name(call.func)
    if call_name not in {"Column", "mapped_column", "Field"}:
        incomplete.append(f"unknown declaration function: {owner}.{field}")
        return None
    if call_name != "Field":
        return call
    sa_column = next((kw.value for kw in call.keywords if kw.arg == "sa_column"), None)
    if sa_column is None:
        return call
    if isinstance(sa_column, ast.Call) and _name(sa_column.func) == "Column":
        return sa_column
    incomplete.append(f"dynamic column declaration: {owner}.{field}")
    return call


def _physical_column_name(field: str, call: ast.Call | None) -> str:
    if call and _name(call.func) != "Field" and call.args:
        declared_name = _literal(call.args[0])
        if isinstance(declared_name, str):
            return declared_name
    return field


def _extract_model_fields(node: ast.ClassDef) -> tuple[dict[str, Any], list[str]]:
    fields: dict[str, Any] = {}
    incomplete: list[str] = []
    for item in node.body:
        field_name, annotation, value = _field_parts(item)
        if not field_name or field_name.startswith("_"):
            continue
        raw_call = value if isinstance(value, ast.Call) else None
        call = _model_field_call(raw_call, node.name, field_name, incomplete)
        if annotation is None and call is None:
            continue
        state = _column_state(annotation, call)
        fields[_physical_column_name(field_name, call)] = state
        if state["type"] is None:
            incomplete.append(f"unknown column type: {node.name}.{field_name}")
        if call and any(
            kw.arg in {"nullable", "primary_key"}
            and not isinstance(kw.value, ast.Constant)
            for kw in call.keywords
        ):
            incomplete.append(f"dynamic column declaration: {node.name}.{field_name}")
    return fields, incomplete


def _base_names(node: ast.ClassDef) -> set[str]:
    return {_name(base) for base in node.bases}


def _inherits(
    node: ast.ClassDef,
    classes: dict[str, ast.ClassDef],
    anchors: set[str],
    seen: set[str],
) -> bool:
    bases = _base_names(node)
    if bases & anchors:
        return True
    for base in bases - seen:
        parent = classes.get(base)
        if parent and _inherits(parent, classes, anchors, seen | {base}):
            return True
    return False


def _sqlmodel_table(node: ast.ClassDef, classes: dict[str, ast.ClassDef]) -> bool:
    table_kw = next((kw for kw in node.keywords if kw.arg == "table"), None)
    return bool(
        table_kw
        and isinstance(table_kw.value, ast.Constant)
        and table_kw.value.value is True
        and _inherits(node, classes, {"SQLModel"}, set())
    )


def _declared_table(node: ast.ClassDef) -> tuple[str | None, bool]:
    for item in node.body:
        targets: list[ast.expr] = item.targets if isinstance(item, ast.Assign) else []
        if isinstance(item, ast.AnnAssign):
            targets = [item.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in targets
        ):
            continue
        if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            return item.value.value, False
        return None, True
    return None, False


def _model_state(
    node: ast.ClassDef, classes: dict[str, ast.ClassDef]
) -> dict[str, Any] | None:
    table, dynamic_table = _declared_table(node)
    is_sqlmodel = _sqlmodel_table(node, classes)
    is_sqlalchemy = _inherits(node, classes, {"Base", "DeclarativeBase"}, set())
    if not is_sqlmodel and not (is_sqlalchemy and (table or dynamic_table)):
        return None
    columns, incomplete = _extract_model_fields(node)
    if dynamic_table:
        incomplete.append(f"dynamic table declaration: {node.name}")
    return {
        "table": table or (node.name.lower() if is_sqlmodel else None),
        "columns": columns,
        "incomplete": incomplete,
    }


def collect_models(project_root: Path) -> dict[str, dict[str, Any]]:
    """Collect declared SQLAlchemy and SQLModel table schemas from src/."""
    models: dict[str, dict[str, Any]] = {}
    src_dir = project_root / "src"
    if not src_dir.is_dir():
        return models

    for py_file in sorted(src_dir.glob("**/*.py")):
        try:
            code = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(code)
            classes = {
                node.name: node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
            }
            for node in classes.values():
                state = _model_state(node, classes)
                if state is not None:
                    models[node.name] = state
        except (OSError, SyntaxError) as exc:
            models[f"<parse:{py_file.relative_to(project_root)}>"] = {
                "table": None,
                "columns": {},
                "incomplete": [f"model parse failed: {type(exc).__name__}"],
            }
    return models


def _new_migration_state() -> dict[str, Any]:
    return {"tables": {}, "incomplete": [], "migration_files": 0}


def _sql_column(text: str) -> tuple[str, dict[str, Any]] | None:
    match = re.match(r'^[`"\[]?(\w+)[`"\]]?\s+([A-Za-z]+)', text.strip())
    if not match or match.group(1).upper() in {
        "PRIMARY",
        "FOREIGN",
        "UNIQUE",
        "CHECK",
        "CONSTRAINT",
    }:
        return None
    upper = text.upper()
    nullable = not ("NOT NULL" in upper or "PRIMARY KEY" in upper)
    return match.group(1).lower(), {
        "type": _normalize_type(match.group(2)),
        "nullable": nullable,
    }


def _create_sql_table(statement: str, state: dict[str, Any]) -> bool:
    match = re.match(
        r"^CREATE\s+TABLE(\s+IF\s+NOT\s+EXISTS)?\s+([\w.]+)\s*\((.*)\)$",
        statement,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return False
    table_name = match.group(2).lower()
    if table_name in state["tables"]:
        if match.group(1):
            return True
        state["incomplete"].append(f"duplicate CREATE TABLE {table_name}")
        return True
    columns = dict(
        filter(None, (_sql_column(part) for part in match.group(3).split(",")))
    )
    unknown = sorted(name for name, column in columns.items() if column["type"] is None)
    if unknown:
        state["incomplete"].append(
            f"unknown SQL column type in {table_name}: {', '.join(unknown)}"
        )
    state["tables"][table_name] = {"columns": columns}
    return True


def _alter_sql_table(statement: str, state: dict[str, Any]) -> bool:
    match = re.match(
        r"^ALTER\s+TABLE\s+([\w.]+)\s+(.+)$",
        statement,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return False
    table, action = match.group(1).lower(), match.group(2).strip()
    rename_table = re.match(r"^RENAME\s+TO\s+([\w.]+)$", action, re.IGNORECASE)
    if rename_table:
        destination = rename_table.group(1).lower()
        if table not in state["tables"] or destination in state["tables"]:
            state["incomplete"].append(f"invalid table rename {table} to {destination}")
            return True
        state["tables"][destination] = state["tables"].pop(table)
        return True
    if table not in state["tables"]:
        state["incomplete"].append(f"ALTER TABLE references missing table {table}")
        return True
    current = state["tables"][table]["columns"]
    return _alter_sql_columns(action, current, state, table)


def _alter_sql_columns(
    action: str, columns: dict[str, Any], state: dict[str, Any], table: str
) -> bool:
    rename = re.match(r"^RENAME\s+COLUMN\s+(\w+)\s+TO\s+(\w+)$", action, re.IGNORECASE)
    if rename:
        source, destination = rename.group(1).lower(), rename.group(2).lower()
        if source not in columns or destination in columns:
            state["incomplete"].append(
                f"invalid column rename {table}.{source} to {destination}"
            )
            return True
        columns[destination] = columns.pop(source)
        return True
    drop = re.match(r"^DROP\s+COLUMN\s+(IF\s+EXISTS\s+)?(\w+)$", action, re.IGNORECASE)
    if drop:
        name = drop.group(2).lower()
        if name not in columns and not drop.group(1):
            state["incomplete"].append(f"DROP COLUMN references missing {table}.{name}")
            return True
        columns.pop(name, None)
        return True
    add = re.match(r"^ADD\s+COLUMN\s+(.+)$", action, re.IGNORECASE | re.DOTALL)
    if add:
        parsed = _sql_column(add.group(1))
        if parsed:
            if parsed[0] in columns:
                state["incomplete"].append(f"ADD COLUMN duplicates {table}.{parsed[0]}")
            else:
                columns[parsed[0]] = parsed[1]
            if parsed[1]["type"] is None:
                state["incomplete"].append(
                    f"unknown SQL column type: {table}.{parsed[0]}"
                )
        return parsed is not None
    return _alter_sql_column(action, columns, state, table)


def _alter_sql_column(
    action: str, columns: dict[str, Any], state: dict[str, Any], table: str
) -> bool:
    type_change = re.match(
        r"^ALTER\s+COLUMN\s+(\w+)\s+TYPE\s+(\w+)$", action, re.IGNORECASE
    )
    if type_change:
        name = type_change.group(1).lower()
        if name not in columns:
            state["incomplete"].append(
                f"ALTER COLUMN references missing {table}.{name}"
            )
            return True
        column_type = _normalize_type(type_change.group(2))
        if column_type is None:
            state["incomplete"].append(f"unknown SQL column type: {table}.{name}")
            return True
        columns[name]["type"] = column_type
        return True
    null_change = re.match(
        r"^ALTER\s+COLUMN\s+(\w+)\s+(SET|DROP)\s+NOT\s+NULL$",
        action,
        re.IGNORECASE,
    )
    if null_change:
        name = null_change.group(1).lower()
        if name not in columns:
            state["incomplete"].append(
                f"ALTER COLUMN references missing {table}.{name}"
            )
            return True
        columns[name]["nullable"] = null_change.group(2).upper() == "DROP"
        return True
    return False


def _apply_sql(content: str, state: dict[str, Any], source: str) -> None:
    literals_removed = re.sub(r"'(?:''|[^'])*'", "''", content)
    stripped = re.sub(r"--[^\n]*", "", literals_removed)
    for raw in stripped.split(";"):
        statement = raw.strip()
        if not statement:
            continue
        if _create_sql_table(statement, state) or _alter_sql_table(statement, state):
            continue
        state["incomplete"].append(f"unsupported SQL migration in {source}")


def _assignment(tree: ast.Module, name: str) -> Any:
    for item in tree.body:
        target = item.target if isinstance(item, ast.AnnAssign) else None
        if isinstance(item, ast.Assign) and len(item.targets) == 1:
            target = item.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            try:
                return ast.literal_eval(item.value)
            except (ValueError, TypeError):
                return ...
    return ...


def _alembic_records(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for path in sorted(project_root.glob("**/migrations/**/*.py")):
        state["migration_files"] += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            state["incomplete"].append(f"migration parse failed: {type(exc).__name__}")
            continue
        revision = _assignment(tree, "revision")
        parent = _assignment(tree, "down_revision")
        if not isinstance(revision, str) or not revision or revision in records:
            state["incomplete"].append(f"dynamic or duplicate revision in {path.name}")
            continue
        valid_parent = isinstance(parent, str) or (
            isinstance(parent, tuple)
            and all(isinstance(item, str) and item for item in parent)
        )
        if parent is not None and not valid_parent:
            state["incomplete"].append(f"dynamic down_revision in {path.name}")
            continue
        records[revision] = {
            "parents": (parent,) if isinstance(parent, str) else tuple(parent or ()),
            "tree": tree,
            "path": path,
        }
    return records


def _topological(
    records: dict[str, Any], state: dict[str, Any]
) -> list[dict[str, Any]]:
    missing = sorted(
        {
            parent
            for item in records.values()
            for parent in item["parents"]
            if parent not in records
        }
    )
    if missing:
        state["incomplete"].append(f"missing parent revision: {', '.join(missing)}")
    graph = {
        revision: {parent for parent in item["parents"] if parent in records}
        for revision, item in records.items()
    }
    try:
        order = tuple(TopologicalSorter(graph).static_order())
    except CycleError:
        state["incomplete"].append("cycle in Alembic revision graph")
        return []
    return [records[revision] for revision in order]


def _literal(node: ast.AST | None) -> Any:
    try:
        return ast.literal_eval(node) if node is not None else None
    except (ValueError, TypeError):
        return ...


def _alembic_column(node: ast.AST) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(node, ast.Call) or _name(node.func) != "Column" or not node.args:
        return None
    name = _literal(node.args[0])
    if not isinstance(name, str):
        return None
    column_type = _normalize_type(_name(node.args[1])) if len(node.args) > 1 else None
    if len(node.args) > 1 and column_type is None:
        return None
    if any(
        kw.arg in {"nullable", "primary_key"}
        and not (
            isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool)
        )
        for kw in node.keywords
    ):
        return None
    nullable = _constant_bool(node, "nullable")
    primary_key = _constant_bool(node, "primary_key")
    if nullable is None:
        nullable = primary_key is not True
    return name.lower(), {"type": column_type, "nullable": nullable}


def _apply_alembic_call(call: ast.Call, state: dict[str, Any], source: str) -> bool:
    operation = _name(call.func)
    args = [_literal(arg) for arg in call.args[:2]]
    if operation == "create_table":
        return _op_create_table(call, args, state)
    if operation == "add_column":
        return _op_add_column(call, args, state)
    if operation == "drop_column":
        return _op_drop_column(args, state)
    if operation == "rename_table":
        return _op_rename_table(args, state)
    if operation == "alter_column":
        return _op_alter_column(call, args, state)
    if operation == "execute" and args and isinstance(args[0], str):
        _apply_sql(args[0], state, source)
        return True
    return False


def _op_create_table(call: ast.Call, args: list[Any], state: dict[str, Any]) -> bool:
    if not args or not isinstance(args[0], str):
        return False
    columns = [_alembic_column(arg) for arg in call.args[1:]]
    if any(column is None for column in columns):
        return False
    table_name = args[0].lower()
    if table_name in state["tables"]:
        state["incomplete"].append(f"duplicate create_table {table_name}")
        return True
    state["tables"][table_name] = {"columns": dict(columns)}
    return True


def _op_add_column(call: ast.Call, args: list[Any], state: dict[str, Any]) -> bool:
    if not args or not isinstance(args[0], str) or len(call.args) < 2:
        return False
    column = _alembic_column(call.args[1])
    if column is None:
        return False
    table_name = args[0].lower()
    if table_name not in state["tables"]:
        state["incomplete"].append(f"add_column references missing table {table_name}")
        return True
    table = state["tables"][table_name]
    if column[0] in table["columns"]:
        state["incomplete"].append(f"add_column duplicates {table_name}.{column[0]}")
        return True
    table["columns"][column[0]] = column[1]
    return True


def _op_drop_column(args: list[Any], state: dict[str, Any]) -> bool:
    if len(args) < 2 or not all(isinstance(arg, str) for arg in args):
        return False
    table_name, column_name = args[0].lower(), args[1].lower()
    if (
        table_name not in state["tables"]
        or column_name not in state["tables"][table_name]["columns"]
    ):
        state["incomplete"].append(
            f"drop_column references missing {table_name}.{column_name}"
        )
        return True
    state["tables"][table_name]["columns"].pop(column_name)
    return True


def _op_rename_table(args: list[Any], state: dict[str, Any]) -> bool:
    if len(args) < 2 or not all(isinstance(arg, str) for arg in args):
        return False
    source, destination = args[0].lower(), args[1].lower()
    if source not in state["tables"] or destination in state["tables"]:
        state["incomplete"].append(f"invalid rename_table {source} to {destination}")
        return True
    state["tables"][destination] = state["tables"].pop(source)
    return True


def _alter_column_values(
    column: dict[str, Any], kwargs: dict[str, ast.AST]
) -> tuple[bool, str | None]:
    new_name = _literal(kwargs.get("new_column_name"))
    if new_name is not None and not isinstance(new_name, str):
        return False, None
    if "type_" in kwargs:
        column_type = _normalize_type(_name(kwargs["type_"]))
        if column_type is None:
            return False, None
        column["type"] = column_type
    if "nullable" in kwargs:
        nullable = _literal(kwargs["nullable"])
        if not isinstance(nullable, bool):
            return False, None
        column["nullable"] = nullable
    return True, new_name


def _op_alter_column(call: ast.Call, args: list[Any], state: dict[str, Any]) -> bool:
    if len(args) < 2 or not all(isinstance(arg, str) for arg in args):
        return False
    table_name = args[0].lower()
    if table_name not in state["tables"]:
        state["incomplete"].append(
            f"alter_column references missing table {table_name}"
        )
        return True
    columns = state["tables"][table_name]["columns"]
    name = args[1].lower()
    if name not in columns:
        state["incomplete"].append(
            f"alter_column references missing {table_name}.{name}"
        )
        return True
    column = columns[name]
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    valid, new_name = _alter_column_values(column, kwargs)
    if not valid:
        return False
    if isinstance(new_name, str):
        if new_name.lower() in columns:
            state["incomplete"].append(
                f"alter_column rename conflicts with {table_name}.{new_name.lower()}"
            )
            return True
        columns[new_name.lower()] = columns.pop(name)
    return True


def _apply_alembic(
    record: dict[str, Any], state: dict[str, Any], project_root: Path
) -> None:
    tree = record["tree"]
    upgrade = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
        ),
        None,
    )
    source = str(record["path"].relative_to(project_root))
    if upgrade is None:
        state["incomplete"].append(f"missing upgrade() in {source}")
        return
    for statement in upgrade.body:
        call = (
            statement.value
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
            else None
        )
        if (
            call is None
            or not isinstance(call.func, ast.Attribute)
            or _name(call.func.value) != "op"
        ):
            state["incomplete"].append(f"unsupported dynamic migration in {source}")
            continue
        if not _apply_alembic_call(call, state, source):
            state["incomplete"].append(f"unsupported dynamic migration in {source}")


def collect_migrations(project_root: Path) -> dict[str, Any]:
    """Apply raw SQL lexically and Alembic revisions topologically to schema state."""
    state = _new_migration_state()
    sql_files = sorted(
        project_root.glob("**/*.sql"),
        key=lambda path: path.relative_to(project_root).as_posix(),
    )
    for path in sql_files:
        state["migration_files"] += 1
        try:
            _apply_sql(
                path.read_text(encoding="utf-8"),
                state,
                str(path.relative_to(project_root)),
            )
        except OSError as exc:
            state["incomplete"].append(f"migration read failed: {type(exc).__name__}")
    records = _alembic_records(project_root, state)
    for record in _topological(records, state):
        _apply_alembic(record, state, project_root)
    return state


def evaluate_drift(
    models: dict[str, dict[str, Any]], migrations: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compare table-keyed model and migration states without losing identity."""
    drift_issues: list[dict[str, Any]] = []
    if models and migrations.get("migration_files", 0) == 0:
        drift_issues.append(_incomplete_issue("no migration files found"))
    drift_issues.extend(
        _incomplete_issue(reason) for reason in migrations.get("incomplete", [])
    )
    tables = migrations.get("tables", {})
    for model_name, model in models.items():
        for reason in model.get("incomplete", []):
            drift_issues.append(_model_incomplete_issue(model_name, reason))
        table_name = model.get("table")
        if not table_name:
            continue
        if table_name.lower() not in tables:
            drift_issues.append(
                _missing_table_issue(model_name, table_name, model["columns"])
            )
            continue
        issue = _column_drift_issue(
            model_name,
            table_name,
            model["columns"],
            tables[table_name.lower()]["columns"],
        )
        if issue:
            drift_issues.append(issue)
    return drift_issues


def _incomplete_issue(reason: str) -> dict[str, Any]:
    return {
        "model": "<migration-history>",
        "table": None,
        "rule": "migration-history-incomplete",
        "unmigrated_fields": [],
        "details": reason,
    }


def _model_incomplete_issue(model: str, reason: str) -> dict[str, Any]:
    return {
        "model": model,
        "table": None,
        "rule": "model-declaration-incomplete",
        "unmigrated_fields": [],
        "details": reason,
    }


def _missing_table_issue(
    model: str, table: str, columns: dict[str, Any]
) -> dict[str, Any]:
    return {
        "model": model,
        "table": table,
        "rule": "missing-table",
        "unmigrated_fields": sorted(columns),
        "details": f"Model '{model}' table '{table}' is missing from migrations.",
    }


def _column_drift_issue(
    model: str, table: str, expected: dict[str, Any], actual: dict[str, Any]
) -> dict[str, Any] | None:
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    shared = sorted(set(expected) & set(actual))
    unresolved = [
        name
        for name in shared
        if expected[name]["type"] is None
        or expected[name]["nullable"] is None
        or actual[name]["type"] is None
        or actual[name]["nullable"] is None
    ]
    type_mismatches = [
        {
            "column": name,
            "model": expected[name]["type"],
            "migration": actual[name]["type"],
        }
        for name in shared
        if expected[name]["type"] is not None
        and actual[name]["type"] is not None
        and expected[name]["type"] != actual[name]["type"]
    ]
    nullability_mismatches = [
        {
            "column": name,
            "model": expected[name]["nullable"],
            "migration": actual[name]["nullable"],
        }
        for name in shared
        if expected[name]["nullable"] is not None
        and actual[name]["nullable"] is not None
        and expected[name]["nullable"] != actual[name]["nullable"]
    ]
    if not (
        missing or unexpected or unresolved or type_mismatches or nullability_mismatches
    ):
        return None
    return {
        "model": model,
        "table": table,
        "rule": "column-drift",
        "unmigrated_fields": missing,
        "unexpected_migrated_fields": unexpected,
        "unresolved_fields": unresolved,
        "type_mismatches": type_mismatches,
        "nullability_mismatches": nullability_mismatches,
        "details": (
            f"Model '{model}' and migrated table '{table}' differ; "
            f"unresolved columns: {unresolved}."
        ),
    }
