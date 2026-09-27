"""`rush agent hook <host>`: the entrypoint the native plugins' hooks run.

Phase 70 T2 ships this adapter inert. Every Claude Code/Codex plugin hook
runs `<rush> agent hook <host>` after an edit; loading or installing the
plugin must never run a check or write anything. The adapter drains the
host's JSON payload (bounded), reads the activation record without
creating any file or directory (design brief X5: `lstat` + `json.loads`,
never `CASMapTransaction`), and prints nothing. T7 adds the opt-in check.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from rush.setup.provision import DataRootUnavailableError, default_data_root

HOOK_HOSTS = ("claude", "codex")
MAX_PAYLOAD_BYTES = 1024 * 1024


def activation_record_path(data_root: Path) -> Path:
    return data_root / "agent-hooks" / "activations.json"


def read_activation_record(data_root: Path) -> Any | None:
    """The parsed activation record, or None when absent or unreadable."""
    path = activation_record_path(data_root)
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


def run_agent_hook(host: str, payload: bytes, *, data_root: Path | None = None) -> str:
    """Return the text the hook prints on stdout; empty means no feedback."""
    if host not in HOOK_HOSTS or len(payload) > MAX_PAYLOAD_BYTES:
        return ""
    try:
        root = data_root or default_data_root()
    except DataRootUnavailableError:
        return ""
    if read_activation_record(root) is None:
        return ""
    # ponytail: an activation record changes nothing until T7 adds the gated
    # check run here.
    return ""


__all__ = [
    "HOOK_HOSTS",
    "MAX_PAYLOAD_BYTES",
    "activation_record_path",
    "read_activation_record",
    "run_agent_hook",
]
