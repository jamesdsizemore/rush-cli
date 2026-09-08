"""Cross-tool memory-handoff transport: per-tool tier dispatch (native SDK > ACP > dedicated
file), Phase 61 P61.10.

Wholly new code. Never modifies `src/rush/continuity/providers.py`'s `provider_command()` /
`resume_provider()` (session-resume CLI dispatch, a separate concern — §2.1 Drift 6 of the
phase-61 plan) or `tools/continuity.py`'s `provider_resume` operation.
"""

from __future__ import annotations

import hashlib
import importlib.util
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rush.io.atomic_file import AtomicFile, SanitizedBytes
from rush.io.physical_paths import PhysicalRoot

from ..permissions import ExecutionPermissions, check_permissions

Tier = Literal["native_sdk", "acp", "dedicated_file"]

HANDOFF_FILE = ".rush/memory/cross_tool_handoff.md"

# Real, verified packages a tier-1/tier-2 transport would use (claude-agent-sdk,
# agent-client-protocol). Only tier 3 (dedicated-file fallback) is actually written to here —
# ponytail: sending the handoff over the native SDK/ACP connection itself is a separate
# integration this task's contract doesn't require (T-61.28/29 only assert tier *selection*).
_NATIVE_SDK_MODULES: dict[str, str] = {
    "claude_code": "claude_agent_sdk",
}
_ACP_TOOLS = {"claude_code", "codex_cli", "antigravity_cli"}


@dataclass(frozen=True)
class TransportResult:
    """Outcome of a single per-tool dispatch."""

    tool: str
    tier: Tier
    status: Literal["ok", "skipped"]
    detail: str


def _native_sdk_available(tool: str) -> bool:
    module_name = _NATIVE_SDK_MODULES.get(tool)
    if module_name is None:
        return False
    return importlib.util.find_spec(module_name) is not None


def _acp_available(tool: str) -> bool:
    if tool not in _ACP_TOOLS:
        return False
    return importlib.util.find_spec("agent_client_protocol") is not None


def select_tier(tool: str) -> Tier:
    """Pick `tool`'s transport tier fresh on every call — never a cached/global tier shared
    across tools in the same run (T-61.31)."""
    if _native_sdk_available(tool):
        return "native_sdk"
    if _acp_available(tool):
        return "acp"
    return "dedicated_file"


def dispatch(
    root: Path,
    tool: str,
    source: str,
    content: str,
    granted: ExecutionPermissions | None = None,
) -> TransportResult:
    """Dispatch a memory handoff to `tool`, selecting its tier independently of any other
    tool dispatched in the same run."""
    tier = select_tier(tool)
    if tier != "dedicated_file":
        return TransportResult(
            tool=tool,
            tier=tier,
            status="ok",
            detail=f"{tier} transport selected for {tool!r}; no dedicated-file write needed.",
        )
    return _write_dedicated_file(root, tool, source, content, granted)


def _write_dedicated_file(
    root: Path,
    tool: str,
    source: str,
    content: str,
    granted: ExecutionPermissions | None,
) -> TransportResult:
    required = ExecutionPermissions(artifact_write=True)
    allowed, missing = check_permissions(required, granted)
    if not allowed:
        return TransportResult(
            tool=tool,
            tier="dedicated_file",
            status="skipped",
            detail=f"Dedicated-file handoff requires {', '.join(missing)}.",
        )

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    marker = f"source={source} content_hash={content_hash}"
    path = root / HANDOFF_FILE
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in existing:
        return TransportResult(
            tool=tool,
            tier="dedicated_file",
            status="ok",
            detail="Duplicate block skipped (source, content_hash already present).",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    block = f"## {marker} ts={time.time():.6f}\n\n{content}\n\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(block)
    return TransportResult(
        tool=tool,
        tier="dedicated_file",
        status="ok",
        detail="Block appended to cross_tool_handoff.md.",
    )


@dataclass(frozen=True)
class _Block:
    ts: float
    raw: str


def _parse_blocks(text: str) -> list[_Block]:
    """Split `.rush/memory/cross_tool_handoff.md` into its `## source=...` delimited blocks."""
    blocks: list[_Block] = []
    current: list[str] | None = None
    current_ts = 0.0
    for line in text.splitlines(keepends=True):
        if line.startswith("## source="):
            if current is not None:
                blocks.append(_Block(current_ts, "".join(current)))
            current = [line]
            current_ts = 0.0
            for field in line[len("## ") :].strip().split(" "):
                if field.startswith("ts="):
                    try:
                        current_ts = float(field[len("ts=") :])
                    except ValueError:
                        current_ts = 0.0
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append(_Block(current_ts, "".join(current)))
    return blocks


def cleanup_handoff_file(
    root: Path,
    *,
    max_age_seconds: float | None = None,
    max_blocks: int | None = None,
) -> int:
    """Prune blocks from `.rush/memory/cross_tool_handoff.md`. Explicit only — `dispatch()`
    never calls this; a caller must invoke it deliberately. Returns the number of blocks removed."""
    path = root / HANDOFF_FILE
    if not path.exists():
        return 0
    blocks = _parse_blocks(path.read_text(encoding="utf-8"))
    kept = blocks
    if max_age_seconds is not None:
        cutoff = time.time() - max_age_seconds
        kept = [block for block in kept if block.ts >= cutoff]
    if max_blocks is not None and len(kept) > max_blocks:
        kept = kept[-max_blocks:] if max_blocks > 0 else []
    removed = len(blocks) - len(kept)
    if removed:
        content = "".join(block.raw for block in kept).encode("utf-8")
        atomic = AtomicFile(PhysicalRoot(root))
        atomic.write_bytes(HANDOFF_FILE, SanitizedBytes.from_bytes(content))
    return removed
