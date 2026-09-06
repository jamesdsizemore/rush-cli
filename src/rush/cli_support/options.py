"""CLI permission and execution options helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import click

from rush.permissions import ExecutionPermissions


def _extract_permissions(
    allow_network: bool = False,
    allow_download: bool = False,
    allow_cache_write: bool = False,
    allow_build: bool = False,
    allow_slow: bool = False,
    allow_artifact_write: bool = False,
    allow_browser: bool = False,
) -> ExecutionPermissions:
    return ExecutionPermissions(
        network=allow_network,
        download=allow_download,
        cache_write=allow_cache_write,
        build=allow_build,
        slow=allow_slow,
        artifact_write=allow_artifact_write,
        browser=allow_browser,
    )


def permission_options(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Add standard explicit execution permission flags to a Click command."""
    fn = click.option(
        "--allow-network",
        is_flag=True,
        help="Explicitly authorize external network access.",
    )(fn)
    fn = click.option(
        "--allow-download",
        is_flag=True,
        help="Explicitly authorize external downloads.",
    )(fn)
    fn = click.option(
        "--allow-cache-write",
        is_flag=True,
        help="Explicitly authorize local cache modification.",
    )(fn)
    fn = click.option(
        "--allow-build",
        is_flag=True,
        help="Explicitly authorize local build execution.",
    )(fn)
    fn = click.option(
        "--allow-slow",
        is_flag=True,
        help="Explicitly authorize long-running execution.",
    )(fn)
    fn = click.option(
        "--allow-artifact-write",
        is_flag=True,
        help="Explicitly authorize writing contained artifacts.",
    )(fn)
    fn = click.option(
        "--allow-browser",
        is_flag=True,
        help="Explicitly authorize browser runtime execution.",
    )(fn)
    return fn
