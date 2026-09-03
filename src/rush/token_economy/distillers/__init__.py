"""Distillers package registry."""

from .base import BaseDistiller, DistilledResult
from .cargo_distiller import CargoDistiller
from .pytest_distiller import PytestDistiller
from .ruff_distiller import RuffDistiller
from .vitest_distiller import VitestDistiller

__all__ = [
    "BaseDistiller",
    "CargoDistiller",
    "DistilledResult",
    "PytestDistiller",
    "RuffDistiller",
    "VitestDistiller",
    "get_distiller_for_command",
]

DISTILLERS: list[BaseDistiller] = [
    PytestDistiller(),
    CargoDistiller(),
    RuffDistiller(),
    VitestDistiller(),
]


def get_distiller_for_command(command: list[str]) -> BaseDistiller | None:
    """Finds a matching distiller for the given command line."""
    for d in DISTILLERS:
        if d.can_distill(command):
            return d
    return None
