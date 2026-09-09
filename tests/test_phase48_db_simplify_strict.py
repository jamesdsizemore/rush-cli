"""Unit tests for Phase 48 DbDriftAuditor, ComplexityDecomposer, and TypeSynthesizer."""

from pathlib import Path

from rush.tools.db_drift import DbDriftAuditor
from rush.tools.simplify import ComplexityDecomposer
from rush.tools.strictify import TypeSynthesizer


def test_db_drift_detection(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    model_file = src / "models.py"
    model_file.write_text(
        """
class UserModel(Base):
    __tablename__ = "users"
    id: int
    username: str
    email: str
    phone_number: str
""",
        encoding="utf-8",
    )

    mig_file = tmp_path / "schema.sql"
    mig_file.write_text(
        """
CREATE TABLE users (
    id INTEGER,
    username VARCHAR,
    email VARCHAR
);
""",
        encoding="utf-8",
    )

    auditor = DbDriftAuditor(project_root=tmp_path)
    res = auditor.audit_drift()

    assert res["passed"] is False
    assert res["drift_count"] == 1
    assert "phone_number" in res["drift_issues"][0]["unmigrated_fields"]


def _write_db_models(root: Path, source: str) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "models.py").write_text(source, encoding="utf-8")


def test_db_drift_keeps_table_identity(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        """
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(nullable=False)
""",
    )
    schema = tmp_path / "schema.sql"
    schema.write_text(
        "CREATE TABLE news (id INTEGER NOT NULL, email TEXT NOT NULL);",
        encoding="utf-8",
    )
    wrong_table = DbDriftAuditor(tmp_path).audit_drift()
    assert wrong_table["passed"] is False
    assert wrong_table["drift_issues"][0]["rule"] == "missing-table"

    schema.unlink()
    missing = DbDriftAuditor(tmp_path).audit_drift()
    assert missing["passed"] is False
    assert missing["drift_issues"][0]["rule"] == "migration-history-incomplete"

    sql_dir = tmp_path / "migrations" / "sql"
    sql_dir.mkdir(parents=True)
    (sql_dir / "02_rename_and_drop.sql").write_text(
        """
ALTER TABLE old_users RENAME TO users;
ALTER TABLE users RENAME COLUMN old_email TO email;
ALTER TABLE users DROP COLUMN legacy;
""",
        encoding="utf-8",
    )
    (sql_dir / "01_create.sql").write_text(
        """
CREATE TABLE old_users (
    id INTEGER NOT NULL,
    old_email TEXT NOT NULL,
    legacy TEXT
);
""",
        encoding="utf-8",
    )
    renamed = DbDriftAuditor(tmp_path).audit_drift()
    assert renamed == {"passed": True, "drift_count": 0, "drift_issues": []}

    for migration in sql_dir.iterdir():
        migration.unlink()
    schema.write_text(
        """
CREATE TABLE users (id INTEGER NOT NULL, email TEXT NOT NULL);
ALTER TABLE users DROP COLUMN email;
""",
        encoding="utf-8",
    )
    dropped = DbDriftAuditor(tmp_path).audit_drift()
    assert dropped["passed"] is False
    assert dropped["drift_issues"][0]["unmigrated_fields"] == ["email"]


def test_db_drift_recognizes_declared_orm_models_only(tmp_path: Path) -> None:
    from rush.tools.db_drift_rules import collect_models

    _write_db_models(
        tmp_path,
        """
class DeclarativeBase: ...
class Base(DeclarativeBase): ...

class Ordinary:
    id: int
    noise: str

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

class Event(SQLModel, table=True):
    id: int = Field(primary_key=True)
    payload: str = Field(nullable=False)
""",
    )
    models = collect_models(tmp_path)
    assert set(models) == {"Account", "Event"}
    assert models["Account"]["table"] == "accounts"
    assert models["Event"]["table"] == "event"
    assert set(models["Event"]["columns"]) == {"id", "payload"}


def test_db_drift_compares_column_type_and_nullability(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        """
class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(nullable=False)
""",
    )
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE customers (id INTEGER NOT NULL, email INTEGER NULL);",
        encoding="utf-8",
    )
    result = DbDriftAuditor(tmp_path).audit_drift()
    assert result["passed"] is False
    issue = result["drift_issues"][0]
    assert issue["type_mismatches"] == [
        {"column": "email", "model": "text", "migration": "integer"}
    ]
    assert issue["nullability_mismatches"] == [
        {"column": "email", "model": False, "migration": True}
    ]

    (tmp_path / "schema.sql").write_text(
        """
CREATE TABLE customers (id INTEGER NOT NULL, email INTEGER NULL);
ALTER TABLE customers ALTER COLUMN email TYPE TEXT;
ALTER TABLE customers ALTER COLUMN email SET NOT NULL;
""",
        encoding="utf-8",
    )
    assert DbDriftAuditor(tmp_path).audit_drift()["passed"] is True


def test_db_drift_rejects_non_boolean_column_flags(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        "class Customer(Base):\n"
        '    __tablename__ = "customers"\n'
        '    email: Mapped[str] = mapped_column(nullable="False")\n',
    )
    from rush.tools.db_drift_rules import collect_models

    model = collect_models(tmp_path)["Customer"]
    assert model["incomplete"] == ["dynamic column declaration: Customer.email"]
    assert model["columns"]["email"]["nullable"] is False


def test_db_drift_orders_alembic_by_revision_graph(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        """
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(nullable=False)
""",
    )
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "z_create.py").write_text(
        """
revision: str = "base"
down_revision: str | None = None
def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True))
def downgrade():
    op.drop_table("users")
""",
        encoding="utf-8",
    )
    (versions / "a_child.py").write_text(
        """
revision: str = "child"
down_revision: str = "base"
def upgrade():
    op.add_column("users", sa.Column("email", sa.String(), nullable=False))
def downgrade():
    op.drop_column("users", "email")
""",
        encoding="utf-8",
    )
    assert DbDriftAuditor(tmp_path).audit_drift()["passed"] is True

    (versions / "z_create.py").write_text(
        'revision = "base"\ndown_revision = "child"\n', encoding="utf-8"
    )
    cycle = DbDriftAuditor(tmp_path).audit_drift()
    assert cycle["passed"] is False
    assert cycle["drift_issues"][0]["rule"] == "migration-history-incomplete"
    assert "cycle" in cycle["drift_issues"][0]["details"].lower()


def test_db_drift_rejects_dynamic_schema_declarations(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        """
class Dynamic(Base):
    __tablename__ = table_name()
    id: Mapped[int] = mapped_column(primary_key=True)
""",
    )
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "dynamic.py").write_text(
        """
revision = "dynamic"
down_revision = "missing-parent"
def upgrade():
    op.create_table(table_name, sa.Column("id", sa.Integer()))
""",
        encoding="utf-8",
    )
    result = DbDriftAuditor(tmp_path).audit_drift()
    assert result["passed"] is False
    details = " ".join(item["details"] for item in result["drift_issues"])
    assert "dynamic" in details.lower()
    assert "missing parent" in details.lower()


def test_db_drift_handles_optional_and_declared_column_names(tmp_path: Path) -> None:
    from rush.tools.db_drift_rules import collect_models

    _write_db_models(
        tmp_path,
        """
class Contact(Base):
    __tablename__: str = "contacts"
    id = Column("contact_id", Integer, primary_key=True)
    nickname: Mapped[str | None] = mapped_column("nickname")
    email_attr: Mapped[str] = mapped_column("email", nullable=False)
""",
    )
    (tmp_path / "schema.sql").write_text(
        """
CREATE TABLE contacts (
    contact_id INTEGER PRIMARY KEY,
    nickname VARCHAR NULL,
    email VARCHAR NOT NULL
);
""",
        encoding="utf-8",
    )
    models = collect_models(tmp_path)
    assert models["Contact"]["table"] == "contacts"
    assert set(models["Contact"]["columns"]) == {"contact_id", "nickname", "email"}
    assert models["Contact"]["columns"]["nickname"]["nullable"] is True
    assert DbDriftAuditor(tmp_path).audit_drift() == {
        "passed": True,
        "drift_count": 0,
        "drift_issues": [],
    }


def test_db_drift_rejects_unknown_model_and_sql_types(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        """
class Unknowns(Base):
    __tablename__ = "unknowns"
    id = Column(custom_type())
    payload: Mapped[str] = custom_field()
    field_value: str = Field(sa_column=dynamic_column())
""",
    )
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE unknowns (id INTEGER, payload MYSTERY, field_value TEXT);",
        encoding="utf-8",
    )
    result = DbDriftAuditor(tmp_path).audit_drift()
    assert result["passed"] is False
    details = " ".join(issue["details"] for issue in result["drift_issues"])
    assert "unknown" in details.lower() or "dynamic" in details.lower()
    assert "payload" in details


def test_db_drift_annotations_do_not_hide_dynamic_column_types(tmp_path: Path):
    for declaration, base, annotation in [
        ("Column(custom_type())", "Base", "Mapped[int]"),
        ("mapped_column(custom_type())", "Base", "Mapped[int]"),
        ("mapped_column(type_=custom_type())", "Base", "Mapped[int]"),
        ("Field(sa_type=custom_type())", "SQLModel, table=True", "int"),
    ]:
        _write_db_models(
            tmp_path,
            f"class Unknowns({base}):\n    __tablename__ = 'unknowns'\n    id: {annotation} = {declaration}\n",
        )
        (tmp_path / "schema.sql").write_text(
            "CREATE TABLE unknowns (id INTEGER NOT NULL);", encoding="utf-8"
        )
        result = DbDriftAuditor(tmp_path).audit_drift()
        assert result["passed"] is False, declaration
        assert "unknown column type" in " ".join(
            issue["details"] for issue in result["drift_issues"]
        )


def test_db_drift_field_default_is_not_a_column_name(tmp_path: Path):
    _write_db_models(
        tmp_path,
        "class Contact(SQLModel, table=True):\n    label: str = Field('default label')\n",
    )
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE contact (label TEXT NOT NULL);", encoding="utf-8"
    )
    assert DbDriftAuditor(tmp_path).audit_drift()["passed"] is True


def test_db_drift_sql_literals_do_not_change_nullability(tmp_path: Path):
    _write_db_models(
        tmp_path,
        "class Contact(Base):\n    __tablename__ = 'contacts'\n    label: Mapped[str]\n",
    )
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE contacts (label TEXT DEFAULT 'NOT NULL; -- literal');",
        encoding="utf-8",
    )
    result = DbDriftAuditor(tmp_path).audit_drift()
    assert result["passed"] is False
    assert result["drift_issues"][0]["nullability_mismatches"] == [
        {"column": "label", "model": False, "migration": True}
    ]


def test_db_drift_refuses_fabricated_migration_state(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        """
class User(Base):
    __tablename__ = "users"
    id = Column(Integer)
""",
    )
    (tmp_path / "schema.sql").write_text(
        """
ALTER TABLE missing RENAME TO users;
ALTER TABLE users ADD COLUMN id INTEGER;
ALTER TABLE users RENAME COLUMN absent TO id;
""",
        encoding="utf-8",
    )
    result = DbDriftAuditor(tmp_path).audit_drift()
    assert result["passed"] is False
    assert any(
        issue["rule"] == "migration-history-incomplete"
        for issue in result["drift_issues"]
    )


def test_db_drift_rejects_malformed_alembic_without_crashing(tmp_path: Path) -> None:
    _write_db_models(
        tmp_path,
        """
class User(Base):
    __tablename__ = "users"
    id = Column(Integer)
""",
    )
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "bad.py").write_text(
        """
revision = "bad"
down_revision = ("missing", 3)
def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), nullable=choice()))
    op.execute()
""",
        encoding="utf-8",
    )
    result = DbDriftAuditor(tmp_path).audit_drift()
    assert result["passed"] is False
    assert result["drift_issues"][0]["rule"] == "migration-history-incomplete"


def test_complexity_decomposer(tmp_path: Path):
    code_file = tmp_path / "spaghetti.py"
    code_file.write_text(
        """
def monolithic_function(x, y, z):
    if x > 0:
        if y > 0:
            while z > 0:
                for i in range(5):
                    if i % 2 == 0:
                        assert True
    return False
""",
        encoding="utf-8",
    )
    decomposer = ComplexityDecomposer(project_root=tmp_path)
    res = decomposer.decompose_file(code_file, max_complexity=4)

    assert res["needs_simplification"] is True
    assert res["complex_functions_count"] == 1
    assert res["candidates"][0]["function"] == "monolithic_function"
    assert res["candidates"][0]["complexity"] > 4


def test_grounded_db_drift_cli_mcp_parity(tmp_path: Path, monkeypatch):
    import json

    from click.testing import CliRunner

    from rush.cli import cli
    from rush.mcp import rush_db_drift

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "models.py").write_text(
        "class User(Base):\n"
        "    __tablename__ = 'users'\n"
        "    id = Column(Integer)\n"
        "    email = Column(String)\n",
        encoding="utf-8",
    )
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE news (id INTEGER, email VARCHAR);", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    direct = DbDriftAuditor(tmp_path).audit_drift()
    mcp_result = json.loads(rush_db_drift())
    command = CliRunner().invoke(cli, ["db-drift"])
    assert direct["passed"] is False
    assert mcp_result == direct
    assert command.exit_code == 1
    assert "schema drift hazards" in command.output


def test_grounded_strictify_cli_mcp_parity(tmp_path: Path, monkeypatch):
    import json

    from click.testing import CliRunner

    from rush.cli import cli
    from rush.mcp import rush_strictify

    target = tmp_path / "total.py"
    target.write_text("def total(values):\n    return sum(values)\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    direct = TypeSynthesizer(tmp_path).audit_and_synthesize(target)
    mcp_result = json.loads(rush_strictify(str(target)))
    command = CliRunner().invoke(cli, ["strictify", "--file", str(target)])
    assert direct["untyped_arguments"][0]["suggested_guard"] is None
    assert mcp_result == direct
    assert command.exit_code == 0
    assert "values" in command.output
    assert "assert isinstance" not in command.output


def test_type_synthesizer(tmp_path: Path):
    code_file = tmp_path / "untyped.py"
    code_file.write_text(
        """
def process_payload(data, status: str = "ok"):
    return data
""",
        encoding="utf-8",
    )

    synth = TypeSynthesizer(project_root=tmp_path)
    res = synth.audit_and_synthesize(code_file)

    assert res["untyped_count"] == 1
    assert res["untyped_arguments"][0]["argument"] == "data"


def test_strictify_preserves_valid_sequence_inputs(tmp_path: Path) -> None:
    code_file = tmp_path / "typed_sequences.py"
    code_file.write_text(
        """
from typing import Protocol

class SupportsValue(Protocol):
    def value(self) -> int: ...

def total(values, /, scale: int = 1, *items: int, limit: int = 0, **options: str):
    assert scale > 0
    return sum(values) * scale

def contradictory(value: int):
    return value + 'x' - 1

def accepts(protocol_value: SupportsValue):
    return protocol_value.value()
""",
        encoding="utf-8",
    )
    original = code_file.read_text(encoding="utf-8")

    result = TypeSynthesizer(project_root=tmp_path).audit_and_synthesize(code_file)
    arguments = {item["argument"]: item for item in result["untyped_arguments"]}
    assert {"values"} <= arguments.keys()
    values = arguments["values"]
    assert not values.get("suggested_guard")
    assert "numeric-iterable" in values["constraint"]
    assert code_file.read_text(encoding="utf-8") == original

    assert "scale" not in arguments
    assert "items" not in arguments
    assert "limit" not in arguments
    assert "options" not in arguments
    assert "protocol_value" not in arguments

    conflicts = [
        finding
        for finding in result["findings"]
        if finding["function"] == "contradictory"
    ]
    assert conflicts
    assert "conflict" in conflicts[0]["reason"].lower()
    assert not conflicts[0].get("suggested_guard")

    guards = result["guards"]["total"]
    namespace = {"scale": 2, "limit": 1, "items": (1, 2), "options": {"x": "ok"}}
    for guard in guards.values():
        exec(guard, {}, namespace)  # noqa: S102
    namespace.update(scale="bad", limit=1, items=(1,), options={"x": "ok"})
    try:
        exec(guards["scale"], {}, namespace)  # noqa: S102
    except AssertionError:
        pass
    else:
        raise AssertionError("annotation guard accepted incompatible operand")


def test_strictify_constraints_respect_operands_and_function_scope(tmp_path: Path):
    import ast

    import pytest

    target = tmp_path / "scoped.py"
    source = """
def total(values, /, *items: int, limit: int = 0, **options: str):
    return sum(values) + sum(items) + limit
def numeric(value: int):
    return (value + 1) - 1
def outer(value: int):
    def inner(value: str):
        assert isinstance(value, str)
        return value
    return value
def branched(value):
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
def contradiction(value: int):
    assert isinstance(value, str)
    return value
def wrong_operand(value: int):
    return value + 'x'
def widened(value: float):
    assert isinstance(value, int)
    return value + 1
"""
    target.write_text(source, encoding="utf-8")
    result = TypeSynthesizer(tmp_path).audit_and_synthesize(target)
    assert {item["function"] for item in result["findings"]} == {
        "contradiction",
        "wrong_operand",
    }
    assert "value" in result["guards"]["numeric"]
    assert "value" in result["guards"]["outer"]
    assert "contradiction" not in result["guards"]
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            checks = "\n".join(result["guards"].get(node.name, {}).values())
            node.body[:0] = ast.parse(checks).body
    namespace = {}
    exec(compile(ast.fix_missing_locations(tree), str(target), "exec"), namespace)  # noqa: S102
    for values in ([1, 2], (1, 2), (x for x in [1, 2])):
        assert namespace["total"](values, 3, limit=4, label="ok") == 10
    for args, kwargs in [
        (([1], "bad"), {}),
        (([1],), {"limit": "bad"}),
        (([1],), {"label": 3}),
    ]:
        with pytest.raises(AssertionError):
            namespace["total"](*args, **kwargs)
    assert namespace["numeric"](3) == 3
    assert namespace["outer"](3) == 3
    assert namespace["widened"](3) == 4


def test_strictify_does_not_assume_shadowed_builtin_annotations(tmp_path: Path):
    target = tmp_path / "protocol_alias.py"
    target.write_text(
        "from typing import Protocol\n"
        "class int(Protocol):\n    def value(self): ...\n"
        "def accepts(value: int):\n    return value.value()\n",
        encoding="utf-8",
    )
    result = TypeSynthesizer(tmp_path).audit_and_synthesize(target)
    assert "accepts" not in result["guards"]


def test_complexity_scopes_nested_definitions_and_async_methods(tmp_path: Path):
    target = tmp_path / "scoped_complexity.py"
    target.write_text(
        """
def outer(flag):
    choose = lambda first, second: first or second
    def inner(value):
        if value:
            for item in value:
                if item:
                    return item
        return None
    class Nested:
        def method(self, value):
            if value:
                while value:
                    break
            return value
    async def async_inner(value):
        if value:
            async for item in value:
                return item
            return value
        return None
    return inner([])
""",
        encoding="utf-8",
    )
    result = ComplexityDecomposer(tmp_path).decompose_file(target, max_complexity=0)
    actual = {item["function"]: item["complexity"] for item in result["candidates"]}
    assert actual == {"outer": 1, "inner": 4, "method": 3, "async_inner": 3}
