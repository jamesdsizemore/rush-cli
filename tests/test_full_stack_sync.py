"""Tests for Phase 33: Full-Stack Static Synchronization & Type Safety Gates."""

from __future__ import annotations

import json
from pathlib import Path

from rush.sync.django_ninja import DjangoNinjaAstExtractor
from rush.sync.env_sync import EnvSchemaSynchronizer
from rush.sync.fastapi_extractor import FastApiAstExtractor
from rush.sync.openapi_checker import OpenApiContractChecker
from rush.sync.orm_validator import OrmMigrationDriftValidator
from rush.sync.ts_generator import TypeScriptContractGenerator


def test_typescript_contract_generator() -> None:
    schema = {
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "is_active": {"type": "boolean"},
                        "tags": {"type": "array"},
                    },
                    "required": ["id", "name"],
                }
            }
        }
    }
    ts_code = TypeScriptContractGenerator.generate_interfaces(json.dumps(schema))
    assert "export interface User {" in ts_code
    assert "id: number;" in ts_code
    assert "name: string;" in ts_code
    assert "is_active?: boolean;" in ts_code
    assert "tags?: any[];" in ts_code


def test_openapi_breaking_changes(tmp_path: Path) -> None:
    old_spec = {"paths": {"/users": {"get": {}, "post": {}}, "/items": {"get": {}}}}
    new_spec = {"paths": {"/users": {"get": {}}}}

    checker = OpenApiContractChecker(tmp_path / "spec.json")
    findings = checker.inspect_breaking_changes(json.dumps(old_spec), json.dumps(new_spec))
    assert len(findings) == 2
    assert any(f.endpoint_path == "/items" for f in findings)
    assert any(f.endpoint_path == "/users" and f.method == "POST" for f in findings)


def test_fastapi_ast_extractor() -> None:
    source = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
def get_users():
    return []

@app.post("/users/create")
async def create_user(data: dict):
    return {"status": "ok"}
"""
    endpoints = FastApiAstExtractor.extract_endpoints_from_source(source)
    assert len(endpoints) == 2
    assert endpoints[0].http_method == "GET"
    assert endpoints[0].path == "/users"
    assert endpoints[1].http_method == "POST"
    assert endpoints[1].path == "/users/create"


def test_django_ninja_ast_extractor() -> None:
    source = """
from ninja import Router
router = Router()

@router.get("/items")
def list_items(request):
    return []
"""
    endpoints = DjangoNinjaAstExtractor.extract_ninja_routes(source)
    assert len(endpoints) == 1
    assert endpoints[0].http_method == "GET"
    assert endpoints[0].path == "/items"


def test_env_schema_synchronizer(tmp_path: Path) -> None:
    env_example = tmp_path / ".env.example"
    env_example.write_text("DATABASE_URL=sqlite:///db.sqlite3\nREDIS_PORT=6379\n", encoding="utf-8")

    pydantic_settings = """
class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_PORT: int
    SECRET_KEY: str
"""
    example_keys = EnvSchemaSynchronizer.extract_env_keys_from_file(env_example)
    settings_keys = EnvSchemaSynchronizer.extract_settings_keys_from_pydantic(pydantic_settings)
    ok, missing = EnvSchemaSynchronizer.verify_env_parity(example_keys, settings_keys)
    assert ok is False
    assert "SECRET_KEY" in missing


def test_orm_migration_validator(tmp_path: Path) -> None:
    validator = OrmMigrationDriftValidator(tmp_path)
    ok, msg = validator.check_alembic()
    assert ok is True
    assert "not detected" in msg
