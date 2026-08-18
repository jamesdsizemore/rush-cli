"""Engine registry — single source of truth for engine lookup.

Architecture §4.2. Used by tools/common.py:run_engine() to find engines
by name. Adding a new engine = add it here AND to ENGINES.
"""

from __future__ import annotations

from .base import Engine
from .eslint import EslintEngine
from .jscpd import JscpdEngine
from .knip import KnipEngine
from .markdownlint import MarkdownlintEngine
from .mypy import MypyEngine
from .npm_audit import NpmAuditEngine
from .pip_audit import PipAuditEngine
from .prettier import PrettierEngine
from .pytest import PytestEngine
from .radon import RadonEngine
from .ruff import RuffEngine
from .sloppylint import SloppylintEngine
from .tsc import TscEngine
from .vitest import VitestEngine
from .vulture import VultureEngine

ENGINES: dict[str, Engine] = {
    "ruff": RuffEngine(),
    "eslint": EslintEngine(),
    "prettier": PrettierEngine(),
    "vitest": VitestEngine(),
    "pytest": PytestEngine(),
    "pip-audit": PipAuditEngine(),
    "npm-audit": NpmAuditEngine(),
    "mypy": MypyEngine(),
    "tsc": TscEngine(),
    "vulture": VultureEngine(),
    "knip": KnipEngine(),
    "radon": RadonEngine(),
    "jscpd": JscpdEngine(),
    "sloppylint": SloppylintEngine(),
    "markdownlint-cli2": MarkdownlintEngine(),
}

__all__ = ["ENGINES", "Engine"]
