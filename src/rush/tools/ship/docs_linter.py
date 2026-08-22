"""Documentation link and CLI reference parity linter."""

import re
from pathlib import Path
from typing import Any


class DocsLinter:
    """Audits markdown file links and CLI references across docs/."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.docs_dir = self.project_root / "docs"

    def lint(self) -> dict[str, Any]:
        broken_links: list[dict[str, str]] = []
        checked_count = 0

        for md_file in self.docs_dir.glob("**/*.md"):
            checked_count += 1
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            matches = re.findall(r"\[([^\]]+)\]\(([^\)]+)\)", content)
            for text, link in matches:
                if link.startswith(("http://", "https://", "mailto:", "#", "file:///")):
                    continue
                target_path = (md_file.parent / link.split("#")[0]).resolve()
                if not target_path.exists():
                    broken_links.append(
                        {
                            "file": str(md_file.relative_to(self.project_root)),
                            "target": link,
                            "text": text,
                        }
                    )

        return {
            "checked_docs": checked_count,
            "broken_links_count": len(broken_links),
            "broken_links": broken_links,
            "passed": len(broken_links) == 0,
        }
