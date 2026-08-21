"""Multi-platform build matrix and target triple coordinator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetTripleConfig:
    os_name: str
    architecture: str
    triple: str
    binary_name: str


TARGET_TRIPLES = [
    TargetTripleConfig("linux", "x86_64", "x86_64-unknown-linux-gnu", "rush-linux-x86_64"),
    TargetTripleConfig("linux", "aarch64", "aarch64-unknown-linux-gnu", "rush-linux-aarch64"),
    TargetTripleConfig("darwin", "arm64", "aarch64-apple-darwin", "rush-darwin-arm64"),
    TargetTripleConfig("darwin", "x86_64", "x86_64-apple-darwin", "rush-darwin-x86_64"),
    TargetTripleConfig("windows", "x86_64", "x86_64-pc-windows-msvc", "rush-windows-x86_64.exe"),
]


class MultiArchCoordinator:
    """Coordinates cross-compilation target metadata across CI runner matrix."""

    @staticmethod
    def get_supported_targets() -> list[TargetTripleConfig]:
        return TARGET_TRIPLES

    @staticmethod
    def get_target_for_os(os_name: str, arch: str) -> TargetTripleConfig | None:
        for t in TARGET_TRIPLES:
            if t.os_name.lower() == os_name.lower() and t.architecture.lower() == arch.lower():
                return t
        return None
