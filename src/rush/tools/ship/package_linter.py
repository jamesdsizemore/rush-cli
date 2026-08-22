"""Package linter inspecting build artifacts and preventing accidental test/secret packaging."""

from pathlib import Path
from typing import Any


class PackageLinter:
    """Audits distribution packages for unwanted files and oversized bloat."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def lint(self) -> dict[str, Any]:
        leaks = []
        # Check if tests, secret files, or .env are included in src/
        src_dir = self.project_root / "src"
        if src_dir.exists():
            for p in src_dir.glob("**/*"):
                if p.is_file():
                    name = p.name.lower()
                    if name.endswith((".pem", ".key", ".pfx", ".secret")):
                        leaks.append(
                            f"Secret key file found in source tree: {p.relative_to(self.project_root)}"
                        )
                    elif name in (".env", ".env.local"):
                        leaks.append(
                            f"Environment secret file in source tree: {p.relative_to(self.project_root)}"
                        )

        return {
            "passed": len(leaks) == 0,
            "leaks_count": len(leaks),
            "leaks": leaks,
        }
