"""First-Party Coverage Manifest Generator (Phase 51: P51.1.2).

Classifies repository paths deterministically into first-party coverage categories
and generates byte-stable, auditable TOML records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoverageRecord:
    path: str
    classification: str
    inclusion_rule: str
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class CoverageManifest:
    revision: str
    generator_version: str
    records: list[CoverageRecord]


EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "build",
    ".worktrees",
    ".rush",
    ".hermes",
    "graft",
    ".codegraph",
    ".gemini",
    ".claude",
    ".repowise",
    ".repowise-workspace",
    ".vscode",
}


def classify_path(rel_path: str) -> CoverageRecord:
    """Classify a relative path into an auditable first-party category or raise ValueError."""
    normalized = rel_path.replace("\\", "/")
    normalized = normalized.removeprefix("./")

    # Local untracked research
    if normalized.startswith("research/") or normalized == "research":
        return CoverageRecord(
            path=normalized,
            classification="excluded",
            inclusion_rule="directory-boundary:research",
            exclusion_reason="Untracked local research artifacts governed by AGENTS.md",
        )

    # Source code
    if normalized.startswith("src/"):
        return CoverageRecord(
            path=normalized,
            classification="source",
            inclusion_rule="directory-tree:src/",
        )

    # Test suites
    if normalized.startswith("tests/"):
        return CoverageRecord(
            path=normalized,
            classification="test",
            inclusion_rule="directory-tree:tests/",
        )

    # Developer scripts
    if normalized.startswith("scripts/"):
        return CoverageRecord(
            path=normalized,
            classification="script",
            inclusion_rule="directory-tree:scripts/",
        )

    # Documentation
    if (
        normalized.startswith("docs/")
        or normalized
        in {
            "README.md",
            "README2.md",
            "README3.md",
            "AGENTS.md",
            "GEMINI.md",
            "LICENSE",
            "CHANGELOG.md",
        }
        or (normalized.endswith(".md") and "/" not in normalized)
    ):
        return CoverageRecord(
            path=normalized,
            classification="doc",
            inclusion_rule="doc-pattern:docs/|*.md|LICENSE",
        )

    # Templates
    if normalized.startswith("templates/") or "/templates/" in normalized:
        return CoverageRecord(
            path=normalized,
            classification="template",
            inclusion_rule="directory-tree:templates/",
        )

    # CI & Workflows
    if normalized.startswith(".github/"):
        return CoverageRecord(
            path=normalized,
            classification="workflow",
            inclusion_rule="directory-tree:.github/",
        )

    # Governance manifests and records
    if normalized.startswith("governance/"):
        return CoverageRecord(
            path=normalized,
            classification="governance",
            inclusion_rule="directory-tree:governance/",
        )

    # Packaging manifests (Homebrew, Scoop, Winget)
    if normalized.startswith("packaging/"):
        return CoverageRecord(
            path=normalized,
            classification="packaging",
            inclusion_rule="directory-tree:packaging/",
        )

    # Examples
    if normalized.startswith("examples/"):
        return CoverageRecord(
            path=normalized,
            classification="example",
            inclusion_rule="directory-tree:examples/",
        )

    # Project metadata and configuration files
    if (
        normalized
        in {
            ".git",
            "pyproject.toml",
            "uv.lock",
            ".gitignore",
            ".ignore",
            ".python-version",
            "rush.toml",
            ".tool-versions",
            "opencode.json",
            "phase50-adversarial-review.md",
        }
        or (normalized.endswith(".txt") and "/" not in normalized)
        or (normalized.endswith(".json") and "/" not in normalized)
    ):
        return CoverageRecord(
            path=normalized,
            classification="metadata",
            inclusion_rule="root-metadata-config",
        )

    raise ValueError(f"Unclassified first-party path: {normalized}")


def build_manifest(root: Path, revision: str) -> CoverageManifest:
    """Scan root and build an exhaustive, byte-stable coverage manifest."""
    records: list[CoverageRecord] = []

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue

        rel = file_path.relative_to(root).as_posix()

        # Skip .git file in worktrees or excluded directory trees
        if rel == ".git":
            continue

        parts = rel.split("/")
        if any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in parts):
            continue

        record = classify_path(rel)
        records.append(record)

    # Stable deterministic ordering
    records.sort(key=lambda r: r.path)

    return CoverageManifest(
        revision=revision,
        generator_version="1.0.0",
        records=records,
    )


def render_toml(manifest: CoverageManifest) -> str:
    """Render manifest as deterministic, byte-stable TOML."""
    lines = [
        "# First-Party Coverage Manifest (RM-P0-01)",
        "# Generated deterministically by rush.governance.coverage_manifest",
        "",
        "[manifest]",
        f'revision = "{manifest.revision}"',
        f'generator_version = "{manifest.generator_version}"',
        f"total_records = {len(manifest.records)}",
        "",
    ]

    for r in manifest.records:
        lines.append("[[records]]")
        lines.append(f'path = "{r.path}"')
        lines.append(f'classification = "{r.classification}"')
        lines.append(f'inclusion_rule = "{r.inclusion_rule}"')
        if r.exclusion_reason:
            lines.append(f'exclusion_reason = "{r.exclusion_reason}"')
        lines.append("")

    return "\n".join(lines)
