"""Builds a polyglot test repo fixture for live end-to-end scanner execution."""

from __future__ import annotations

import json
from pathlib import Path


def create_polyglot_test_repo(base_dir: Path) -> Path:
    repo_dir = base_dir / "live_polyglot_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    # 1. Python source
    src_py = repo_dir / "src"
    src_py.mkdir(exist_ok=True)
    (src_py / "app.py").write_text(
        "def calculate_total(price: float, tax: float) -> float:\n"
        "    # Deliberate slop comment: In this function we meticulously calculate the total price\n"
        "    return price + (price * tax)\n",
        encoding="utf-8",
    )

    # 2. JS/TS source
    (src_py / "index.js").write_text(
        "function greet(name) {\n    return 'Hello ' + name;\n}\nmodule.exports = { greet };\n",
        encoding="utf-8",
    )

    # 3. package.json
    (repo_dir / "package.json").write_text(
        json.dumps(
            {"name": "live-test-app", "version": "1.0.0", "main": "src/index.js"}
        ),
        encoding="utf-8",
    )

    # 4. SQL schema
    db_dir = repo_dir / "db"
    db_dir.mkdir(exist_ok=True)
    (db_dir / "schema.sql").write_text(
        "CREATE TABLE users (\n    id INTEGER PRIMARY KEY,\n    name VARCHAR(255) NOT NULL\n);\n",
        encoding="utf-8",
    )

    # 5. Templates HTML
    tmpl_dir = repo_dir / "templates"
    tmpl_dir.mkdir(exist_ok=True)
    (tmpl_dir / "index.html").write_text(
        "<!DOCTYPE html>\n<html>\n<head><title>App</title></head>\n<body><h1>Hello</h1></body>\n</html>\n",
        encoding="utf-8",
    )

    # 6. Markdown documentation
    (repo_dir / "README.md").write_text(
        "# Live Test App\n\nThis is a live polyglot test repository for Rush scanner validation.\n",
        encoding="utf-8",
    )

    # 7. GitHub Actions workflow
    wf_dir = repo_dir / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "ci.yml").write_text(
        "name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )

    # 8. YAML Config
    (repo_dir / "config.yaml").write_text(
        "app:\n  name: live-test-app\n  port: 8080\n",
        encoding="utf-8",
    )

    # 9. Dockerfile
    (repo_dir / "Dockerfile").write_text(
        'FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nCMD ["python", "src/app.py"]\n',
        encoding="utf-8",
    )

    # 10. Terraform IaC
    (repo_dir / "main.tf").write_text(
        'resource "local_file" "example" {\n  filename = "test.txt"\n  content  = "hello"\n}\n',
        encoding="utf-8",
    )

    return repo_dir
