"""Declarative metadata for Rush tools and externally discovered engines.

The catalog is deliberately dependency-free.  It describes Rush's own surface;
engine binaries remain optional and are resolved at runtime by ``run_engine``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ToolCategory = Literal["quality", "security", "test", "workflow"]
EngineCapability = Literal["lint", "format", "test", "security", "metrics", "workflow"]


@dataclass(frozen=True)
class ToolSpec:
    """Stable metadata shared by CLI help, MCP descriptions, and tests."""

    name: str
    category: ToolCategory
    description: str
    mcp_description: str
    engine_names: tuple[str, ...]
    supports_path: bool = True
    experimental: bool = False


@dataclass(frozen=True)
class EngineSpec:
    """Install and routing metadata for an external engine binary."""

    name: str
    binary: str
    install_hint: str
    file_extensions: tuple[str, ...]
    project_markers: tuple[str, ...]
    capability: EngineCapability


TOOL_SPECS: dict[str, ToolSpec] = {
    "review": ToolSpec(
        name="review",
        category="quality",
        description="Review code for deterministic heuristic quality signals.",
        mcp_description=(
            "Review <path> with deterministic heuristics. Returns {status, findings[], "
            "summary}; optional LLM use is explicit."
        ),
        engine_names=(),
    ),
    "lint": ToolSpec(
        name="lint",
        category="quality",
        description="Lint Python and JavaScript/TypeScript source files.",
        mcp_description=(
            "Lint Python/JS/TS files at <path>. Returns {status, findings[], summary}. "
            "Missing engines return status='skipped'."
        ),
        engine_names=("ruff", "eslint"),
    ),
    "format": ToolSpec(
        name="format",
        category="quality",
        description="Check formatting without silently rewriting files.",
        mcp_description=(
            "Check formatting at <path>. Returns {status, findings[], summary}. "
            "Missing engines return status='skipped'."
        ),
        engine_names=("ruff", "prettier"),
    ),
    "test": ToolSpec(
        name="test",
        category="test",
        description="Run the project test runner selected from project metadata.",
        mcp_description=(
            "Run tests at <path>. Returns {status, findings[], summary}. "
            "Missing engines return status='skipped'."
        ),
        engine_names=("pytest", "vitest"),
    ),
    "security": ToolSpec(
        name="security",
        category="security",
        description="Scan dependency manifests for known vulnerabilities.",
        mcp_description=(
            "Scan dependencies at <path>. Returns {status, findings[], summary}. "
            "Missing engines return status='skipped'."
        ),
        engine_names=("pip-audit", "npm-audit"),
    ),
    "typecheck": ToolSpec(
        name="typecheck",
        category="quality",
        description="Type-check Python and JavaScript/TypeScript source.",
        mcp_description="Type-check Python and JS/TS at <path>; missing mypy or tsc returns status='skipped'.",
        engine_names=("mypy", "tsc"),
    ),
    "dead": ToolSpec(
        name="dead",
        category="quality",
        description="Find unused Python and JavaScript/TypeScript code.",
        mcp_description=(
            "Find unused Python and JS/TS code at <path>; missing vulture or knip "
            "returns status='skipped'."
        ),
        engine_names=("vulture", "knip"),
    ),
    "complexity": ToolSpec(
        name="complexity",
        category="quality",
        description="Measure Python and JavaScript/TypeScript complexity.",
        mcp_description=(
            "Measure Python and JS/TS complexity at <path>; missing radon or jscpd "
            "returns status='skipped'."
        ),
        engine_names=("radon", "jscpd"),
    ),
    "slop": ToolSpec(
        name="slop",
        category="quality",
        description="Detect AI slop in Python and deterministic JS/TS noise signals.",
        mcp_description="Detect Python AI slop and deterministic JS/TS noise at <path>; missing sloppylint returns status='skipped'.",
        engine_names=("sloppylint",),
    ),
    "markdown": ToolSpec(
        name="markdown",
        category="quality",
        description="Check Markdown without rewriting files.",
        mcp_description="Check Markdown at <path> without rewriting; missing markdownlint-cli2 returns status='skipped'.",
        engine_names=("markdownlint-cli2",),
    ),
}


ENGINE_SPECS: dict[str, EngineSpec] = {
    "ruff": EngineSpec(
        "ruff", "ruff", "pip install ruff", ("py", "pyi"), ("pyproject.toml",), "lint"
    ),
    "eslint": EngineSpec(
        "eslint",
        "eslint",
        "npm install -g eslint",
        ("js", "jsx", "mjs", "cjs", "ts", "tsx"),
        ("package.json",),
        "lint",
    ),
    "prettier": EngineSpec(
        "prettier",
        "prettier",
        "npm install -g prettier",
        ("js", "jsx", "mjs", "cjs", "ts", "tsx", "json", "yaml", "yml", "md"),
        ("package.json",),
        "format",
    ),
    "pytest": EngineSpec(
        "pytest",
        "pytest",
        "pip install pytest",
        ("py", "pyi"),
        ("pyproject.toml",),
        "test",
    ),
    "vitest": EngineSpec(
        "vitest",
        "vitest",
        "npm install -D vitest",
        ("js", "jsx", "ts", "tsx"),
        ("package.json",),
        "test",
    ),
    "pip-audit": EngineSpec(
        "pip-audit",
        "pip-audit",
        "pip install pip-audit",
        (),
        ("pyproject.toml", "requirements.txt"),
        "security",
    ),
    "npm-audit": EngineSpec(
        "npm-audit", "npm", "ships with npm", (), ("package.json",), "security"
    ),
    "mypy": EngineSpec(
        "mypy", "mypy", "pip install mypy", ("py", "pyi"), ("pyproject.toml",), "lint"
    ),
    "tsc": EngineSpec(
        "tsc",
        "tsc",
        "npm install -D typescript",
        ("js", "jsx", "ts", "tsx"),
        ("package.json",),
        "lint",
    ),
    "vulture": EngineSpec(
        "vulture",
        "vulture",
        "pip install vulture",
        ("py", "pyi"),
        ("pyproject.toml",),
        "lint",
    ),
    "knip": EngineSpec(
        "knip",
        "knip",
        "npm install -D knip",
        ("js", "jsx", "ts", "tsx"),
        ("package.json",),
        "lint",
    ),
    "radon": EngineSpec(
        "radon",
        "radon",
        "pip install radon",
        ("py", "pyi"),
        ("pyproject.toml",),
        "metrics",
    ),
    "jscpd": EngineSpec(
        "jscpd",
        "jscpd",
        "npm install -D jscpd",
        ("js", "jsx", "ts", "tsx"),
        ("package.json",),
        "metrics",
    ),
    "sloppylint": EngineSpec(
        "sloppylint",
        "sloppylint",
        "pip install sloppylint",
        ("py", "pyi"),
        ("pyproject.toml",),
        "lint",
    ),
    "markdownlint-cli2": EngineSpec(
        "markdownlint-cli2",
        "markdownlint-cli2",
        "npm install -D markdownlint-cli2",
        ("md", "mdx"),
        (),
        "lint",
    ),
}


__all__ = ["ENGINE_SPECS", "TOOL_SPECS", "EngineSpec", "ToolSpec"]
