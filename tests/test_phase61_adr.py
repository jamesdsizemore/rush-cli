"""Governance test for Phase 61: ADR-0030 supersession by ADR-0049."""

from __future__ import annotations

from pathlib import Path

ADR_DIR = Path(__file__).resolve().parent.parent / "docs" / "adr"


def test_adr_0030_marked_superseded_and_0049_exists() -> None:
    """T-61.34: ADR-0030 carries a "Superseded by ADR-0049" pointer; ADR-0049 exists,
    Status is Accepted, and it references ADR-0030."""
    adr_0030 = (
        ADR_DIR / "0030-unified-dual-layer-agent-context-memory-subsystem.md"
    ).read_text(encoding="utf-8")
    assert "Superseded by [ADR-0049]" in adr_0030

    adr_0049 = (
        ADR_DIR / "0049-typed-artifact-memory-schema-and-trust-tiers.md"
    ).read_text(encoding="utf-8")

    lines = adr_0049.splitlines()
    status_idx = lines.index("## Status")
    assert lines[status_idx + 1].strip().startswith("Accepted")
    assert "0030" in adr_0049
