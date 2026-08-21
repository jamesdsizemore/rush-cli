"""SemVer 2.0.0 parser and cross-manifest version validator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SEMVER_REGEX = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    def __str__(self) -> str:
        ver = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            ver += f"-{self.prerelease}"
        if self.build:
            ver += f"+{self.build}"
        return ver

    def bump_patch(self) -> SemVer:
        return SemVer(self.major, self.minor, self.patch + 1)

    def bump_minor(self) -> SemVer:
        return SemVer(self.major, self.minor + 1, 0)

    def bump_major(self) -> SemVer:
        return SemVer(self.major + 1, 0, 0)


class SemVerValidator:
    """Validates SemVer compliance and verifies consistency across project manifests."""

    @staticmethod
    def parse(version_str: str) -> SemVer | None:
        match = SEMVER_REGEX.match(version_str.strip())
        if not match:
            return None
        return SemVer(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("prerelease"),
            build=match.group("buildmetadata"),
        )

    @staticmethod
    def check_manifest_parity(repo_root: Path) -> dict[str, str]:
        versions: dict[str, str] = {}

        # 1. pyproject.toml
        pyproject = repo_root / "pyproject.toml"
        if pyproject.exists():
            match = re.search(r'version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"))
            if match:
                versions["pyproject.toml"] = match.group(1)

        # 2. package.json
        pkg_json = repo_root / "package.json"
        if pkg_json.exists():
            match = re.search(r'"version"\s*:\s*"([^"]+)"', pkg_json.read_text(encoding="utf-8"))
            if match:
                versions["package.json"] = match.group(1)

        # 3. Cargo.toml
        cargo = repo_root / "Cargo.toml"
        if cargo.exists():
            match = re.search(r'version\s*=\s*"([^"]+)"', cargo.read_text(encoding="utf-8"))
            if match:
                versions["Cargo.toml"] = match.group(1)

        return versions
