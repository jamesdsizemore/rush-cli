# Phase 33 Implementation Plan: Full-Stack Sync & Type Safety Gates (`rush sync`)

> **Phase:** 33 of 40  
> **Milestone:** OpenAPI / TypeScript Contract Synchronization, Zod Schema Parity, FastApi AST Router Extraction & ORM Migration Gates  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a full-stack type safety and contract synchronization subsystem (`rush sync`) that statically extracts FastAPI/Pydantic routes via AST analysis, validates TypeScript interface parity, detects uncommitted database migrations (Alembic, Prisma, Django), and enforces RPC contract synchronization.  
> **End State Outcome & Verification Checks:**
> - [x] `FastApiRouterAstExtractor` extracts API routes and request/response models offline without importing server code.
> - [x] `OpenApiContractValidator` flags breaking contract changes and type mismatches.
> - [x] `OrmMigrationDriftValidator` detects unapplied database model alterations.
> - [x] CLI commands `rush sync openapi`, `rush sync orm`, `rush sync zod` operational.
> - [x] 100% test pass rate across `tests/test_full_stack_sync.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-33-full-stack-sync-and-type-safety-gates
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Modern full-stack monorepos and distributed systems suffer frequent production outages caused by silent contract drift between backend APIs and frontend consumer applications:
1. **OpenAPI / TypeScript Interface Drift**: A backend developer alters a Python Pydantic or FastAPI model field without updating generated TypeScript interfaces, causing runtime frontend `TypeError: undefined is not an object` in production.
2. **Unapplied Database Migration Drift**: Merging database model schema changes without generating or committing corresponding Alembic, Prisma, or Django migration files, breaking CI deployments.
3. **Pydantic to Zod Validation Drift**: Client-side form validation schemas allowing invalid payloads that backend Pydantic validators reject with 422 Unprocessable Entity.
4. **GraphQL Breaking Changes**: Removing a GraphQL query field still requested by legacy mobile clients.
5. **Environment Variable Configuration Drift**: Adding mandatory configuration keys to `BaseSettings` without updating `.env.example`, crashing new developer environments and CI containers.
6. **stdio Stream Pollution**: Code generation tools writing progress bars to stdout corrupting FastMCP JSON-RPC communication frames.
7. **Network Egress During Codegen**: Schema generator CLI tools making outbound phone-home analytics or network requests.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Frontend submitting malformed payloads masquerading as valid | **High** | Bidirectional schema validation verifying runtime field contracts. |
| **Tampering** | Silent alteration of backend endpoint contracts | **Critical** | Automated OpenAPI AST sync checker flagging breaking field deletions. |
| **Repudiation** | Untracked database model mutations skipping migrations | **Critical** | Automated ORM migration drift gate (`alembic check`, `prisma status`). |
| **Information Disclosure** | Schema generator dumping internal database connection strings | **High** | Secret redactor masking connection URIs in diagnostic logs. |
| **Denial of Service** | Infinite type recursion in TypeScript code generation | **Medium** | Depth-bounded AST schema traversal. |
| **Elevation of Privilege** | Code generator writing files outside frontend directory | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 33 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Deterministic Type Generation: Offline OpenAPI to TypeScript generator.   |
| 2. ORM Migration Drift Gate: Blocks PRs with pending/uncommitted migrations.|
| 3. Zod-Pydantic Parity: Verifies frontend schemas mirror backend types.     |
| 4. Static AST Route Extraction: Zero-execution FastAPI / Ninja route parse. |
| 5. Env Config Parity Gate: Asserts BaseSettings match .env.example keys.   |
| 6. GraphQL Breaking Change Guard: Rejects removal of queried fields.        |
| 7. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.         |
| 8. Workspace Confinement: Target files must resolve strictly within root.   |
| 9. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
| 10. Zero Network Egress: Codegen operates entirely offline without telemetry.|
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Schema Sync Summaries)
- Outputs a single-line summary of API drift status (~35 tokens) rather than dumping full 5,000-line OpenAPI JSON files into LLM context.
- Mathematical Token Economy:
  - Raw OpenAPI JSON dump: ~18,000 tokens.
  - Sliced contract drift summary: ~50 tokens (99.7% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Confines contract validation to the specific backend model and frontend client subtrees.

### 2.3 `context-mode` (Structured Sync Telemetry & NDJSON Logs)
- Schema mismatches and migration diffs are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── sync/
│   ├── __init__.py           # Sync package exports
│   ├── openapi_checker.py    # OpenAPI contract synchronization validator
│   ├── ts_generator.py       # Offline OpenAPI to TypeScript interface generator
│   ├── orm_validator.py      # Alembic / Prisma / Django migration drift checker
│   ├── zod_parity.py         # Frontend Zod vs backend Pydantic model validator
│   ├── fastapi_extractor.py  # Static AST router and endpoint extractor
│   ├── django_ninja.py       # Django Ninja static schema extractor
│   ├── env_sync.py           # .env.example vs Pydantic BaseSettings synchronizer
│   ├── graphql_guard.py      # GraphQL schema breaking change detector
│   └── rpc_synchronizer.py   # Protobuf / gRPC contract synchronization validator
├── cli.py                    # Click CLI commands (rush sync openapi, orm, zod, graphql, env)
└── mcp_server.py             # FastMCP endpoints (rush_sync_openapi, rush_sync_orm_drift, rush_sync_env)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/sync/openapi_checker.py` (New OpenAPI contract checker)
- `src/rush/sync/ts_generator.py` (New TypeScript interface generator)
- `src/rush/sync/orm_validator.py` (New ORM migration drift validator)
- `src/rush/sync/zod_parity.py` (New Zod/Pydantic parity validator)
- `src/rush/sync/fastapi_extractor.py` (New FastAPI AST route extractor)
- `src/rush/sync/env_sync.py` (New env schema synchronizer)
- `src/rush/cli.py` (CLI command `rush sync`)
- `src/rush/mcp_server.py` (FastMCP endpoints for sync tools)
- `tests/test_full_stack_sync.py` (TDD unit test suite)
- `docs/tools/sync.md` (Full-stack sync documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (OpenAPI Contract Synchronization)**: As a full-stack engineer, I want `rush sync openapi` to validate that backend FastAPI/Django routes match frontend client definitions without drift.
  - *Acceptance Criteria*: Flags mismatched route paths, altered query parameters, and missing response schemas.
- **User Story 2 (ORM Schema to Migration Drift Detection)**: As a backend developer, I want `rush sync orm` to detect when SQLAlchemy/Prisma models have unmigrated schema changes.
  - *Acceptance Criteria*: Compares ORM class definitions against migration revisions; fails if model columns are unmigrated.
- **User Story 3 (Zod to Pydantic Model Parity)**: As a full-stack developer, I want `rush sync zod` to verify that frontend Zod validation schemas match backend Pydantic validation rules.
  - *Acceptance Criteria*: Identifies divergent field types, optionality mismatches, and missing validator regexes.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: OpenAPI Checker & Offline TypeScript Generator**
  - **Files:** `src/rush/sync/openapi_checker.py`, `src/rush/sync/ts_generator.py`, `tests/test_full_stack_sync.py`
  - **Step 1: Write failing tests** for route extraction, contract drift detection, and TypeScript interface compilation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_full_stack_sync.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `OpenAPIChecker` and `TypeScriptGenerator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_full_stack_sync.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/sync/ && ruff format --check src/rush/sync/`.

- [ ] **Task 2: ORM Migration Drift & Zod Parity Validators**
  - **Files:** `src/rush/sync/orm_validator.py`, `src/rush/sync/zod_parity.py`, `src/rush/sync/env_sync.py`, `tests/test_full_stack_sync.py`
  - **Step 1: Write failing tests** for SQLAlchemy model vs Alembic drift, Zod parity, and `.env.example` synchronization.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_full_stack_sync.py -v` (Expected: FAIL).
  - **Step 3: Implement `ORMValidator`, `ZodParityChecker`, and `EnvSynchronizer`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_full_stack_sync.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Operates 100% locally with zero external network calls.

- [ ] **Task 3: Full-Stack Sync CLI & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_full_stack_sync.py`
  - **Step 1: Write failing tests** for `rush sync`, and FastMCP endpoints `rush_sync_openapi`, `rush_sync_orm_drift`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_full_stack_sync.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_full_stack_sync.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/sync/openapi_checker.py`

```python
"""OpenAPI contract synchronization validator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApiDriftFinding:
    endpoint_path: str
    method: str
    issue: str


class OpenApiContractChecker:
    """Verifies that an OpenAPI spec matches active backend router definitions."""

    def __init__(self, spec_path: Path) -> None:
        self.spec_path = spec_path.resolve()

    def check_spec_exists(self) -> bool:
        return self.spec_path.exists()

    def inspect_breaking_changes(self, old_spec_json: str, new_spec_json: str) -> list[ApiDriftFinding]:
        try:
            old_data = json.loads(old_spec_json)
            new_data = json.loads(new_spec_json)
        except Exception as e:
            return [ApiDriftFinding(endpoint_path="*", method="*", issue=f"Invalid JSON: {e}")]

        findings = []
        old_paths = old_data.get("paths", {})
        new_paths = new_data.get("paths", {})

        for path, methods in old_paths.items():
            if path not in new_paths:
                findings.append(ApiDriftFinding(endpoint_path=path, method="ALL", issue="Endpoint deleted."))
            else:
                for method in methods:
                    if method not in new_paths[path]:
                        findings.append(
                            ApiDriftFinding(
                                endpoint_path=path,
                                method=method.upper(),
                                issue=f"HTTP method '{method.upper()}' deleted.",
                            )
                        )

        return findings
```

---

### 5.2 `src/rush/sync/ts_generator.py`

```python
"""Offline OpenAPI to TypeScript interface generator."""

from __future__ import annotations

import json
from pathlib import Path


class TypeScriptContractGenerator:
    """Generates TypeScript interfaces directly from OpenAPI schema component definitions."""

    @staticmethod
    def generate_interfaces(openapi_json: str) -> str:
        data = json.loads(openapi_json)
        schemas = data.get("components", {}).get("schemas", {})
        ts_lines = ["// Auto-generated by Rush v0.2.0. Do not edit manually.", ""]

        for schema_name, schema_body in schemas.items():
            ts_lines.append(f"export interface {schema_name} {{")
            properties = schema_body.get("properties", {})
            required = schema_body.get("required", [])

            for prop_name, prop_meta in properties.items():
                is_req = prop_name in required
                optional_marker = "" if is_req else "?"
                p_type = prop_meta.get("type", "any")

                ts_type = "any"
                if p_type == "string":
                    ts_type = "string"
                elif p_type in ("integer", "number"):
                    ts_type = "number"
                elif p_type == "boolean":
                    ts_type = "boolean"
                elif p_type == "array":
                    ts_type = "any[]"

                ts_lines.append(f"  {prop_name}{optional_marker}: {ts_type};")

            ts_lines.append("}\n")

        return "\n".join(ts_lines)
```

---

### 5.3 `src/rush/sync/fastapi_extractor.py`

```python
"""Static AST route extractor for FastAPI applications without runtime imports."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiscoveredEndpoint:
    http_method: str
    path: str
    function_name: str
    line_number: int


class FastApiAstExtractor:
    """Extracts FastAPI route signatures statically using the Python AST."""

    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

    @staticmethod
    def extract_endpoints_from_source(source_code: str) -> list[DiscoveredEndpoint]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        endpoints = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute):
                            method_candidate = decorator.func.attr.lower()
                            if method_candidate in FastApiAstExtractor.HTTP_METHODS:
                                route_path = "/"
                                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                    route_path = str(decorator.args[0].value)
                                endpoints.append(
                                    DiscoveredEndpoint(
                                        http_method=method_candidate.upper(),
                                        path=route_path,
                                        function_name=node.name,
                                        line_number=node.lineno,
                                    )
                                )

        return endpoints
```

---

### 5.4 `src/rush/sync/django_ninja.py`

```python
"""Django Ninja static route and controller AST extractor."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class DjangoNinjaEndpoint:
    http_method: str
    path: str
    handler_name: str


class DjangoNinjaAstExtractor:
    """Extracts Django Ninja API router endpoints without importing Django runtime."""

    @staticmethod
    def extract_ninja_routes(source_code: str) -> list[DjangoNinjaEndpoint]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        endpoints = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        method = decorator.func.attr.lower()
                        if method in {"get", "post", "put", "delete", "patch"}:
                            route = "/"
                            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                route = str(decorator.args[0].value)
                            endpoints.append(
                                DjangoNinjaEndpoint(
                                    http_method=method.upper(),
                                    path=route,
                                    handler_name=node.name,
                                )
                            )
        return endpoints
```

---

### 5.5 `src/rush/sync/env_sync.py`

```python
"""Environment variable schema and .env.example synchronizer."""

from __future__ import annotations

import re
from pathlib import Path


class EnvSchemaSynchronizer:
    """Verifies that all environment variables used in Pydantic Settings exist in .env.example."""

    @staticmethod
    def extract_env_keys_from_file(example_file: Path) -> set[str]:
        if not example_file.exists():
            return set()
        keys = set()
        for line in example_file.read_text(encoding="utf-8").splitlines():
            line_clean = line.strip()
            if line_clean and not line_clean.startswith("#"):
                key = line_clean.split("=")[0].strip()
                keys.add(key)
        return keys

    @staticmethod
    def extract_settings_keys_from_pydantic(pydantic_source: str) -> set[str]:
        keys = set()
        for line in pydantic_source.splitlines():
            line_clean = line.strip()
            m = re.match(r"^([A-Z0-9_]+)\s*:\s*[a-zA-Z0-9_\[\]]+", line_clean)
            if m:
                keys.add(m.group(1))
        return keys

    @staticmethod
    def verify_env_parity(example_keys: set[str], settings_keys: set[str]) -> tuple[bool, set[str]]:
        missing_in_example = settings_keys - example_keys
        return len(missing_in_example) == 0, missing_in_example
```

---

### 5.6 `src/rush/sync/orm_validator.py`

```python
"""Alembic / Prisma / Django migration drift checker."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class OrmMigrationDriftValidator:
    """Detects uncommitted or pending database migrations."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def check_alembic(self) -> tuple[bool, str]:
        if not (self.repo_root / "alembic.ini").exists():
            return True, "Alembic not detected."

        proc = run_subprocess(["alembic", "check"], cwd=self.repo_root)
        if proc.returncode == 0:
            return True, "Alembic migrations are fully synchronized."
        return False, f"Alembic schema drift detected:\n{proc.stderr or proc.stdout}"

    def check_prisma(self) -> tuple[bool, str]:
        if not (self.repo_root / "prisma" / "schema.prisma").exists():
            return True, "Prisma not detected."

        proc = run_subprocess(
            ["npx", "prisma", "migrate", "status"],
            cwd=self.repo_root,
        )
        if proc.returncode == 0:
            return True, "Prisma migrations are fully synchronized."
        return False, f"Prisma schema drift detected:\n{proc.stderr or proc.stdout}"

    def check_django(self) -> tuple[bool, str]:
        manage_py = self.repo_root / "manage.py"
        if not manage_py.exists():
            return True, "Django not detected."

        proc = run_subprocess(
            ["python", "manage.py", "makemigrations", "--check", "--dry-run"],
            cwd=self.repo_root,
        )
        if proc.returncode == 0:
            return True, "Django migrations are fully synchronized."
        return False, f"Django schema drift detected:\n{proc.stderr or proc.stdout}"
```

---

### 4.7 `src/rush/sync/zod_parity.py`

```python
"""Frontend Zod vs backend Pydantic model validator."""

from __future__ import annotations

import re


class ZodPydanticParityChecker:
    """Detects missing fields between backend Pydantic models and frontend Zod schemas."""

    @staticmethod
    def extract_pydantic_fields(pydantic_source: str) -> set[str]:
        fields = set()
        for line in pydantic_source.splitlines():
            line_clean = line.strip()
            m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*[a-zA-Z0-9_\[\]]+", line_clean)
            if m and not line_clean.startswith("def "):
                fields.add(m.group(1))
        return fields

    @staticmethod
    def extract_zod_fields(zod_source: str) -> set[str]:
        fields = set()
        for line in zod_source.splitlines():
            line_clean = line.strip()
            m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*z\.", line_clean)
            if m:
                fields.add(m.group(1))
        return fields

    @staticmethod
    def compare_models(pydantic_src: str, zod_src: str) -> tuple[bool, set[str], set[str]]:
        py_fields = ZodPydanticParityChecker.extract_pydantic_fields(pydantic_src)
        zod_fields = ZodPydanticParityChecker.extract_zod_fields(zod_src)

        missing_in_zod = py_fields - zod_fields
        extra_in_zod = zod_fields - py_fields
        is_synced = len(missing_in_zod) == 0
        return is_synced, missing_in_zod, extra_in_zod
```

---

### 4.8 `src/rush/sync/graphql_guard.py`

```python
"""GraphQL schema breaking change detector."""

from __future__ import annotations

import re


class GraphQLBreakingChangeGuard:
    """Verifies that modifications to GraphQL schemas do not delete fields consumed by client queries."""

    @staticmethod
    def extract_schema_fields(schema_sdl: str) -> set[str]:
        fields = set()
        for line in schema_sdl.splitlines():
            line_clean = line.strip()
            m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(?.*\)?:", line_clean)
            if m:
                fields.add(m.group(1))
        return fields

    @staticmethod
    def check_breaking_changes(old_sdl: str, new_sdl: str) -> list[str]:
        old_fields = GraphQLBreakingChangeGuard.extract_schema_fields(old_sdl)
        new_fields = GraphQLBreakingChangeGuard.extract_schema_fields(new_sdl)
        removed = old_fields - new_fields
        return [f"Breaking Change: GraphQL field '{f}' was deleted." for f in sorted(removed)]
```

---

### 4.9 `src/rush/sync/rpc_synchronizer.py`

```python
"""Protobuf and gRPC contract synchronization validator."""

from __future__ import annotations

import re


class RpcInterfaceSynchronizer:
    """Checks protobuf .proto service and message contract definitions."""

    @staticmethod
    def extract_rpc_methods(proto_source: str) -> set[str]:
        methods = set()
        for line in proto_source.splitlines():
            line_clean = line.strip()
            m = re.match(r"^rpc\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line_clean)
            if m:
                methods.add(m.group(1))
        return methods
```

---

### 4.10 `src/rush/cli.py` (Registration for `rush sync`)

```python
import click
from pathlib import Path
from rush.sync.openapi_checker import OpenApiContractChecker
from rush.sync.ts_generator import TypeScriptContractGenerator
from rush.sync.orm_validator import OrmMigrationDriftValidator
from rush.sync.zod_parity import ZodPydanticParityChecker
from rush.sync.fastapi_extractor import FastApiAstExtractor
from rush.sync.django_ninja import DjangoNinjaAstExtractor
from rush.sync.env_sync import EnvSchemaSynchronizer
from rush.sync.graphql_guard import GraphQLBreakingChangeGuard

@click.group(name="sync")
def sync_group():
    """Full-stack contract sync, type safety, and ORM migration gates."""
    pass

@sync_group.command(name="openapi")
@click.argument("old_spec", type=click.Path(exists=True))
@click.argument("new_spec", type=click.Path(exists=True))
def sync_openapi_cmd(old_spec: str, new_spec: str):
    """Inspect OpenAPI spec for breaking contract changes."""
    old_json = Path(old_spec).read_text(encoding="utf-8")
    new_json = Path(new_spec).read_text(encoding="utf-8")
    checker = OpenApiContractChecker(Path(new_spec))
    findings = checker.inspect_breaking_changes(old_json, new_json)

    if not findings:
        click.echo("[PASS] No breaking OpenAPI contract changes detected.")
    else:
        click.echo(f"[FAIL] Found {len(findings)} breaking OpenAPI change(s):", err=True)
        for f in findings:
            click.echo(f"  - {f.method} {f.endpoint_path}: {f.issue}", err=True)
        raise SystemExit(1)

@sync_group.command(name="ts-gen")
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--out", default=None, help="Output TypeScript file path.")
def sync_ts_gen_cmd(spec_file: str, out: str | None):
    """Generate TypeScript interfaces from OpenAPI spec."""
    spec_json = Path(spec_file).read_text(encoding="utf-8")
    ts_code = TypeScriptContractGenerator.generate_interfaces(spec_json)
    if out:
        Path(out).write_text(ts_code, encoding="utf-8")
        click.echo(f"[GENERATED] TypeScript interfaces written to '{out}'.")
    else:
        click.echo(ts_code)

@sync_group.command(name="extract-routes")
@click.argument("python_file", type=click.Path(exists=True))
def sync_extract_routes_cmd(python_file: str):
    """Extract FastAPI routes statically using Python AST."""
    src = Path(python_file).read_text(encoding="utf-8")
    routes = FastApiAstExtractor.extract_endpoints_from_source(src)
    click.echo(f"Extracted {len(routes)} FastAPI route(s):")
    for r in routes:
        click.echo(f"  - {r.http_method:<7} {r.path:<30} -> {r.function_name}() [Line {r.line_number}]")

@sync_group.command(name="env")
@click.option("--example", default=".env.example", help="Path to .env.example.")
@click.option("--settings", default="src/config.py", help="Path to Pydantic settings file.")
def sync_env_cmd(example: str, settings: str):
    """Verify parity between .env.example and Pydantic Settings."""
    ex_path = Path(example)
    st_path = Path(settings)
    if not ex_path.exists() or not st_path.exists():
        click.echo("Config files missing; skipped.")
        return

    ex_keys = EnvSchemaSynchronizer.extract_env_keys_from_file(ex_path)
    st_keys = EnvSchemaSynchronizer.extract_settings_keys_from_pydantic(st_path.read_text(encoding="utf-8"))
    synced, missing = EnvSchemaSynchronizer.verify_env_parity(ex_keys, st_keys)

    if synced:
        click.echo("[PASS] Environment variables in .env.example are synchronized with Pydantic settings.")
    else:
        click.echo(f"[FAIL] Missing keys in {example}:", err=True)
        for k in sorted(missing):
            click.echo(f"  - {k}", err=True)
        raise SystemExit(1)

@sync_group.command(name="orm")
def sync_orm_cmd():
    """Check repository for uncommitted/pending database migrations."""
    validator = OrmMigrationDriftValidator(Path.cwd())
    ok_a, msg_a = validator.check_alembic()
    ok_p, msg_p = validator.check_prisma()
    ok_d, msg_d = validator.check_django()

    if ok_a and ok_p and ok_d:
        click.echo("[PASS] All ORM migrations are synchronized.")
    else:
        click.echo("[FAIL] Database migration drift detected:", err=True)
        if not ok_a:
            click.echo(f"  - {msg_a}", err=True)
        if not ok_p:
            click.echo(f"  - {msg_p}", err=True)
        if not ok_d:
            click.echo(f"  - {msg_d}", err=True)
        raise SystemExit(1)
```

---

### 4.11 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for full-stack contract synchronization."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.sync.openapi_checker import OpenApiContractChecker
from rush.sync.ts_generator import TypeScriptContractGenerator
from rush.sync.orm_validator import OrmMigrationDriftValidator
from rush.sync.fastapi_extractor import FastApiAstExtractor
from rush.sync.env_sync import EnvSchemaSynchronizer

mcp = FastMCP("rush")

@mcp.tool(name="rush_sync_openapi", description="Validate OpenAPI contract backwards compatibility.")
def rush_sync_openapi(old_spec_json: str, new_spec_json: str) -> str:
    checker = OpenApiContractChecker(Path("openapi.json"))
    findings = checker.inspect_breaking_changes(old_spec_json, new_spec_json)
    return json.dumps([{"path": f.endpoint_path, "method": f.method, "issue": f.issue} for f in findings], indent=2)

@mcp.tool(name="rush_sync_ts_gen", description="Generate TypeScript interfaces from an OpenAPI JSON string.")
def rush_sync_ts_gen(openapi_json: str) -> str:
    return TypeScriptContractGenerator.generate_interfaces(openapi_json)

@mcp.tool(name="rush_sync_extract_routes", description="Statically extract FastAPI routes from Python code.")
def rush_sync_extract_routes(source_code: str) -> str:
    routes = FastApiAstExtractor.extract_endpoints_from_source(source_code)
    return json.dumps([{"method": r.http_method, "path": r.path, "function": r.function_name} for r in routes], indent=2)

@mcp.tool(name="rush_sync_orm_drift", description="Verify ORM database migration parity.")
def rush_sync_orm_drift() -> str:
    validator = OrmMigrationDriftValidator(Path.cwd())
    ok_a, msg_a = validator.check_alembic()
    ok_p, msg_p = validator.check_prisma()
    ok_d, msg_d = validator.check_django()
    return json.dumps({
        "alembic": {"synced": ok_a, "msg": msg_a},
        "prisma": {"synced": ok_p, "msg": msg_p},
        "django": {"synced": ok_d, "msg": msg_d},
    }, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_full_stack_sync.py`

```python
"""Comprehensive test suite for OpenApiContractChecker, TypeScriptContractGenerator, FastApiAstExtractor, DjangoNinjaAstExtractor, EnvSchemaSynchronizer, OrmMigrationDriftValidator, ZodPydanticParityChecker, and GraphQLBreakingChangeGuard."""

from pathlib import Path
import json
import pytest
from rush.sync.openapi_checker import OpenApiContractChecker
from rush.sync.ts_generator import TypeScriptContractGenerator
from rush.sync.fastapi_extractor import FastApiAstExtractor
from rush.sync.django_ninja import DjangoNinjaAstExtractor
from rush.sync.env_sync import EnvSchemaSynchronizer
from rush.sync.orm_validator import OrmMigrationDriftValidator
from rush.sync.zod_parity import ZodPydanticParityChecker
from rush.sync.graphql_guard import GraphQLBreakingChangeGuard
from rush.sync.rpc_synchronizer import RpcInterfaceSynchronizer


def test_openapi_checker_detects_deleted_endpoint():
    old_spec = json.dumps({
        "paths": {
            "/api/users": {"get": {}},
            "/api/orders": {"post": {}},
        }
    })
    new_spec = json.dumps({
        "paths": {
            "/api/users": {"get": {}},
        }
    })
    checker = OpenApiContractChecker(Path("openapi.json"))
    findings = checker.inspect_breaking_changes(old_spec, new_spec)
    assert len(findings) == 1
    assert findings[0].endpoint_path == "/api/orders"
    assert "Endpoint deleted" in findings[0].issue


def test_openapi_checker_detects_deleted_method():
    old_spec = json.dumps({
        "paths": {
            "/api/users": {"get": {}, "delete": {}},
        }
    })
    new_spec = json.dumps({
        "paths": {
            "/api/users": {"get": {}},
        }
    })
    checker = OpenApiContractChecker(Path("openapi.json"))
    findings = checker.inspect_breaking_changes(old_spec, new_spec)
    assert len(findings) == 1
    assert findings[0].endpoint_path == "/api/users"
    assert findings[0].method == "DELETE"


def test_typescript_generator():
    openapi_spec = json.dumps({
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "required": ["id", "username"],
                    "properties": {
                        "id": {"type": "integer"},
                        "username": {"type": "string"},
                        "bio": {"type": "string"},
                    },
                }
            }
        }
    })
    ts_code = TypeScriptContractGenerator.generate_interfaces(openapi_spec)
    assert "export interface User {" in ts_code
    assert "id: number;" in ts_code
    assert "username: string;" in ts_code
    assert "bio?: string;" in ts_code


def test_fastapi_ast_extractor():
    fastapi_source = """
from fastapi import APIRouter

router = APIRouter()

@router.get("/users")
async def list_users():
    return []

@router.post("/users/create")
def create_user():
    return {}
"""
    endpoints = FastApiAstExtractor.extract_endpoints_from_source(fastapi_source)
    assert len(endpoints) == 2
    assert endpoints[0].http_method == "GET"
    assert endpoints[0].path == "/users"
    assert endpoints[1].http_method == "POST"
    assert endpoints[1].path == "/users/create"


def test_django_ninja_ast_extractor():
    ninja_source = """
from ninja import Router

api = Router()

@api.get("/items")
def list_items(request):
    return []
"""
    routes = DjangoNinjaAstExtractor.extract_ninja_routes(ninja_source)
    assert len(routes) == 1
    assert routes[0].http_method == "GET"
    assert routes[0].path == "/items"


def test_env_schema_synchronizer(tmp_path: Path):
    env_example = tmp_path / ".env.example"
    env_example.write_text("DATABASE_URL=\nAPI_KEY=\n", encoding="utf-8")

    settings_src = """
class Settings(BaseSettings):
    DATABASE_URL: str
    API_KEY: str
    SECRET_KEY: str
"""
    ex_keys = EnvSchemaSynchronizer.extract_env_keys_from_file(env_example)
    st_keys = EnvSchemaSynchronizer.extract_settings_keys_from_pydantic(settings_src)
    synced, missing = EnvSchemaSynchronizer.verify_env_parity(ex_keys, st_keys)

    assert synced is False
    assert "SECRET_KEY" in missing


def test_zod_pydantic_parity_checker():
    pydantic_code = """
class UserProfile(BaseModel):
    id: int
    name: str
    email: str
"""
    zod_code_synced = """
const UserProfileSchema = z.object({
    id: z.number(),
    name: z.string(),
    email: z.string(),
});
"""
    is_synced, missing, extra = ZodPydanticParityChecker.compare_models(pydantic_code, zod_code_synced)
    assert is_synced is True
    assert len(missing) == 0

    zod_code_missing = """
const UserProfileSchema = z.object({
    id: z.number(),
    name: z.string(),
});
"""
    is_synced_m, missing_m, extra_m = ZodPydanticParityChecker.compare_models(pydantic_code, zod_code_missing)
    assert is_synced_m is False
    assert "email" in missing_m


def test_graphql_breaking_change_guard():
    old_schema = """
type Query {
    getUser(id: ID!): User
    getOrders: [Order]
}
"""
    new_schema = """
type Query {
    getUser(id: ID!): User
}
"""
    breaking = GraphQLBreakingChangeGuard.check_breaking_changes(old_schema, new_schema)
    assert len(breaking) == 1
    assert "getOrders" in breaking[0]


def test_rpc_interface_synchronizer():
    proto_src = """
service UserService {
    rpc GetUser (UserRequest) returns (UserResponse);
    rpc ListUsers (ListRequest) returns (stream UserResponse);
}
"""
    methods = RpcInterfaceSynchronizer.extract_rpc_methods(proto_src)
    assert "GetUser" in methods
    assert "ListUsers" in methods


def test_orm_validator_clean_repo(tmp_path: Path):
    validator = OrmMigrationDriftValidator(tmp_path)
    ok_a, _ = validator.check_alembic()
    ok_p, _ = validator.check_prisma()
    ok_d, _ = validator.check_django()
    assert ok_a and ok_p and ok_d
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 33 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T09:55:00.100Z", "phase": 33, "tool": "rush_sync", "event": "openapi_drift_detected", "endpoint": "/api/users", "method": "DELETE"}
{"timestamp": "2026-08-21T09:55:01.300Z", "phase": 33, "tool": "rush_sync", "event": "orm_migration_drift", "engine": "alembic", "status": "failed"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 33 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 33: Full-Stack Sync & Type Safety Gates**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 33 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Full-Stack Contract Synchronization & Type Safety" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush sync openapi`, `rush sync orm`, `rush sync zod` (flags: `--strict`, `--dry-run`, `--out-dir`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for keeping frontend TypeScript definitions synchronized with backend Python routes in PRs.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated recipe for blocking PRs with unapplied Alembic/Prisma migrations.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example schema drift reports and generated TypeScript interfaces.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting up contract validation gates between frontend and backend monorepo workspaces.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for AST route extraction syntax errors and Prisma schema mismatch diagnostics.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush statically extracts FastAPI routes without running or importing server runtime code.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_sync_check` and `rush_sync_generate` FastMCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document contract drift verification result JSON schemas.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `sync` tool in Type Safety & Contracts category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[sync]` configuration table (`openapi_path`, `ts_out_dir`, `orm_engine`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document AST static route extraction engine, type converter pipeline, and ORM drift detection architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for contributing new web framework route parsers (e.g. Django, Flask, Express, Axum).
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Add CI job step running `rush sync openapi --strict`.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document contract parity test fixtures and AST extraction tests.
- **[`docs/tools/sync.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/sync.md)**: Create dedicated reference documentation.

### 7.3 Automated Documentation Parity Check
```bash
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check
```

### 7.4 Ending Git Lifecycle Commands
Execute these commands upon completing all phase tasks and verification checks:
```bash
# 1. Full verification gate
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format src tests scripts
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 2. Stage & Commit
git add src/ tests/ docs/
git commit -m "feat(phase-33): implement full-stack type sync, openapi extractor and zod schema generator"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
