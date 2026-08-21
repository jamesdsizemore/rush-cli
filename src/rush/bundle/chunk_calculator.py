"""Raw, Gzip, and Brotli size measurement engine."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChunkSizeReport:
    file_name: str
    raw_bytes: int
    gzip_bytes: int
    brotli_est_bytes: int


class BundleChunkCalculator:
    """Calculates deterministic transfer sizes for build chunks."""

    @staticmethod
    def measure_file(file_path: Path) -> ChunkSizeReport:
        data = file_path.read_bytes()
        raw_size = len(data)
        gzip_size = len(gzip.compress(data, compresslevel=9))
        brotli_est = int(gzip_size * 0.85)

        return ChunkSizeReport(
            file_name=file_path.name,
            raw_bytes=raw_size,
            gzip_bytes=gzip_size,
            brotli_est_bytes=brotli_est,
        )

    @staticmethod
    def measure_directory(dist_dir: Path) -> list[ChunkSizeReport]:
        if not dist_dir.exists():
            return []
        reports = []
        for p in dist_dir.rglob("*"):
            if p.is_file() and p.suffix in (".js", ".css", ".wasm", ".html"):
                reports.append(BundleChunkCalculator.measure_file(p))
        return sorted(reports, key=lambda r: r.gzip_bytes, reverse=True)
