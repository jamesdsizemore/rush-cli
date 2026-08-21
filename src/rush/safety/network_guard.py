"""Outbound network socket interceptor for hermetic sandbox execution."""

from __future__ import annotations

import socket


class NetworkEgressGuard:
    """Enforces network isolation within sandboxed subprocesses."""

    @staticmethod
    def block_network_sockets() -> None:
        """Monkey-patches Python socket creation to prevent egress in sandboxed plugins."""
        def guarded_socket(*args, **kwargs):
            raise PermissionError("Network access blocked: Sandbox operates in zero-network hermetic mode.")
        socket.socket = guarded_socket  # type: ignore
