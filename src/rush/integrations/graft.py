"""Local, opt-in Graft context integration; no network or source imports."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from ..tools.base import Finding


class GraftContextProvider(Protocol):
    def available(self, project_root: Path) -> bool: ...
    def context_for(self, path: Path) -> list[Finding]: ...


class LocalGraftContext:
    """Availability-only provider; callers may replace it with a local adapter."""

    def available(self, project_root: Path) -> bool:
        return (
            shutil.which("graft") is not None
            and (project_root / ".hermes/graft").exists()
        )

    def context_for(self, path: Path) -> list[Finding]:
        return []
