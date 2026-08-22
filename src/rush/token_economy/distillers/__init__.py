"""Distillers package registry."""

from src.rush.token_economy.distillers.base import BaseDistiller, DistilledResult
from src.rush.token_economy.distillers.cargo_distiller import CargoDistiller
from src.rush.token_economy.distillers.pytest_distiller import PytestDistiller
from src.rush.token_economy.distillers.ruff_distiller import RuffDistiller
from src.rush.token_economy.distillers.vitest_distiller import VitestDistiller

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
