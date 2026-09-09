"""AGENTS.md multi-IDE rule file compiler."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from pathlib import Path

from rush.io.atomic_file import AtomicFile, SanitizedBytes
from rush.io.physical_paths import PhysicalRoot
from rush.safety.redactor import sanitize_value

IDE_TARGETS = {
    ".cursorrules": "Cursor IDE Rule File",
    ".windsurfrules": "Windsurf IDE Rule File",
    ".clinerules": "Cline / Roo-Code Rule File",
    ".github/copilot-instructions.md": "GitHub Copilot Instructions",
    ".gemini/antigravity/rules.md": "Antigravity CLI Rules",
}


@dataclass(frozen=True)
class SyncResult:
    target_path: str
    action: str
    sha256: str


class AgentsMdSynchronizer:
    """Compiles canonical AGENTS.md into multi-IDE governance rule files."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.canonical_file = self.repo_root / "AGENTS.md"

    def sync_all(self) -> list[SyncResult]:
        physical_root = PhysicalRoot(self.repo_root)
        canonical_file = physical_root.open_contained("AGENTS.md")
        if not canonical_file.exists():
            return []

        if not canonical_file.is_file():
            raise ValueError("AGENTS.md must be an ordinary file")
        canonical_text = canonical_file.read_text(encoding="utf-8")
        canonical_sha = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

        header = f"<!-- AUTO-GENERATED FROM AGENTS.md (SHA: {canonical_sha[:12]}) - DO NOT EDIT MANUALLY -->\n\n"
        full_content = SanitizedBytes.from_bytes(
            (header + canonical_text).encode("utf-8")
        )

        snapshots: dict[str, tuple[bytes | None, int | None]] = {}
        for rel_target in IDE_TARGETS:
            target = physical_root.open_contained(rel_target, purpose="write")
            try:
                target_stat = target.stat()
            except FileNotFoundError:
                snapshots[rel_target] = (None, None)
            else:
                if not stat.S_ISREG(target_stat.st_mode):
                    raise ValueError(
                        f"Governance target is not an ordinary file: {rel_target}"
                    )
                snapshots[rel_target] = (
                    target.read_bytes(),
                    stat.S_IMODE(target_stat.st_mode),
                )

        writer = AtomicFile(physical_root)
        written: list[str] = []
        results = []
        try:
            for rel_target, (original, mode) in snapshots.items():
                target = writer.write_bytes(rel_target, full_content)
                written.append(rel_target)
                if mode is not None:
                    target.chmod(mode)
                results.append(
                    SyncResult(
                        target_path=rel_target,
                        action="updated" if original is not None else "created",
                        sha256=canonical_sha,
                    )
                )
        except BaseException as exc:
            restore_errors = []
            for rel_target in reversed(written):
                original, mode = snapshots[rel_target]
                try:
                    target = physical_root.open_contained(rel_target, purpose="write")
                    if target.exists() and not target.is_file():
                        raise ValueError(
                            "Governance target is no longer an ordinary file"
                        )
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        # Restore captured user bytes exactly, including any existing secrets.
                        target = writer.write_bytes(
                            rel_target, SanitizedBytes(original)
                        )
                        assert mode is not None
                        target.chmod(mode)
                except Exception as restore_exc:  # noqa: BLE001 - restore remaining targets
                    restore_errors.append(f"{rel_target}: {restore_exc}")
            message = f"Governance synchronization failed: {exc}"
            if restore_errors:
                message += "; restoration failed: " + "; ".join(restore_errors)
            message = str(sanitize_value(message).value)
            if isinstance(exc, Exception):
                raise OSError(message) from None
            exc.args = (message,)
            raise exc from None

        return results
