#!/usr/bin/env python3
"""Build and synchronize Phase 51 remediation governance manifests.

Usage:
    python scripts/build_remediation_manifests.py [--all] [--coverage] [--operations] [--engines] [--contracts]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from rush.governance.coverage_manifest import build_manifest, render_toml


def get_git_revision(root: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown-dev-revision"


def build_coverage_manifest(root: Path) -> Path:
    rev = get_git_revision(root)
    manifest = build_manifest(root, revision=rev)
    out_file = root / "governance" / "first-party-coverage.toml"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(render_toml(manifest), encoding="utf-8")
    print(f"[coverage] Generated {out_file} ({len(manifest.records)} records)")
    return out_file


def build_operations_manifest(root: Path) -> Path:
    from rush.governance.public_operations import (
        build_operations_inventory,
        render_operations_toml,
    )

    inventory = build_operations_inventory()
    out_file = root / "governance" / "public-operations.toml"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(render_operations_toml(inventory), encoding="utf-8")
    print(f"[operations] Generated {out_file} ({len(inventory)} operations)")
    return out_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 51 Governance Manifests")
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Repository root directory"
    )
    parser.add_argument("--all", action="store_true", help="Build all manifests")
    parser.add_argument(
        "--coverage", action="store_true", help="Build first-party coverage manifest"
    )
    parser.add_argument(
        "--operations", action="store_true", help="Build public operations manifest"
    )
    parser.add_argument(
        "--engines", action="store_true", help="Build engine support manifest"
    )
    parser.add_argument(
        "--contracts", action="store_true", help="Build remediation contracts manifest"
    )

    args = parser.parse_args()

    # Default to all if no specific manifest requested
    run_all = args.all or not (
        args.coverage or args.operations or args.engines or args.contracts
    )

    root = args.root.resolve()

    if run_all or args.coverage:
        build_coverage_manifest(root)

    if run_all or args.operations:
        build_operations_manifest(root)

    if run_all or args.engines:
        engines_file = root / "governance" / "engine-support.toml"
        if not engines_file.is_file():
            print(f"[engines] Warning: {engines_file} missing", file=sys.stderr)
        else:
            print(f"[engines] Verified {engines_file}")

    if run_all or args.contracts:
        contracts_file = root / "governance" / "remediation-contracts.toml"
        if not contracts_file.is_file():
            print(f"[contracts] Warning: {contracts_file} missing", file=sys.stderr)
        else:
            print(f"[contracts] Verified {contracts_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
