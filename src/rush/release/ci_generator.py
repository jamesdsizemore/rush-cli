"""Hardened 40-character SHA-pinned GitHub Actions workflow generator."""

from __future__ import annotations

from pathlib import Path

# Pinned immutable 40-character commit SHAs for core GitHub Actions
PINNED_ACTIONS = {
    "actions/checkout": "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",  # v4.2.2
    "actions/setup-python": "actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38",  # v5.4.0
    "astral-sh/setup-uv": "astral-sh/setup-uv@1edb4637821c054a75129d81411a547e614f6484",  # v5.3.0
}

HARDENED_CI_TEMPLATE = f"""name: CI Quality Gate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  quality-gate:
    name: Rush Comprehensive Quality Gate
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Hardened Checkout
        uses: {PINNED_ACTIONS["actions/checkout"]}
        with:
          persist-credentials: false

      - name: Setup Python
        uses: {PINNED_ACTIONS["actions/setup-python"]}
        with:
          python-version: "3.12"

      - name: Setup uv
        uses: {PINNED_ACTIONS["astral-sh/setup-uv"]}
        with:
          enable-cache: true

      - name: Install Dependencies
        run: uv sync --all-extras --dev

      - name: Run Test Suite
        run: uv run pytest tests/ -q

      - name: Verify Documentation Parity
        run: uv run python scripts/sync_docs.py --check

      - name: Ruff Lint & Format Check
        run: |
          uv run ruff check src tests scripts
          uv run ruff format --check src tests scripts
"""


class CIWorkflowGenerator:
    """Generates hardened GitHub Actions workflows with immutable SHA pinning."""

    @staticmethod
    def generate_ci_workflow(repo_root: Path) -> Path:
        workflow_dir = repo_root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        ci_file = workflow_dir / "ci.yml"
        ci_file.write_text(HARDENED_CI_TEMPLATE, encoding="utf-8")
        return ci_file
