"""Engine registry — single source of truth for engine lookup.

Architecture §4.2. Used by tools/common.py:run_engine() to find engines
by name. Adding a new engine = add it here AND to ENGINES.
"""

from __future__ import annotations

from .base import Engine
from .ruff import RuffEngine
from .eslint import EslintEngine
from .prettier import PrettierEngine
from .vitest import VitestEngine
from .pytest import PytestEngine
from .pip_audit import PipAuditEngine
from .npm_audit import NpmAuditEngine

ENGINES: dict[str, Engine] = {
    "ruff": RuffEngine(),
    "eslint": EslintEngine(),
    "prettier": PrettierEngine(),
    "vitest": VitestEngine(),
    "pytest": PytestEngine(),
    "pip-audit": PipAuditEngine(),
    "npm-audit": NpmAuditEngine(),
}

__all__ = ["ENGINES", "Engine"]
