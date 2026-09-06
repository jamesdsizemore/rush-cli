"""Continuity subsystem for state persistence, multi-agent coordination, and provider resumption."""

from __future__ import annotations

from .context import pack_context, retrieve_context
from .coordination import (
    check_coordination,
    preview_merge,
    recover_coordination,
)
from .providers import (
    provider_command,
    provider_handoff,
    provider_prompt,
    resume_omniroute,
    resume_provider,
    windows_cmd_command,
)
from .receipts import restore_receipt, save_receipt
from .results import ContinuityResult, build_continuity_result

__all__ = [
    "ContinuityResult",
    "build_continuity_result",
    "check_coordination",
    "pack_context",
    "preview_merge",
    "provider_command",
    "provider_handoff",
    "provider_prompt",
    "recover_coordination",
    "restore_receipt",
    "resume_omniroute",
    "resume_provider",
    "retrieve_context",
    "save_receipt",
    "windows_cmd_command",
]
