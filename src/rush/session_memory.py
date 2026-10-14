"""Sanitized Multi-Turn Session Memory (Control 7: Context Framing).

Architecture §8, Phase 29.
Maintains bounded turn history framed in strict XML boundary tags.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.sax import saxutils

from rush.logging import get_logger, log_subsystem
from rush.safety.redactor import SecretRedactor

if TYPE_CHECKING:
    from rush.memory.store import MemoryArtifact

# rush.memory.migration/store/trust are imported lazily inside record_turn()/format_for_mcp()
# below, not here at module level: this module sits on the pre-existing
# migration -> store -> hook -> tools -> continuity -> checkpoint_journal -> migration import
# cycle, and a module-level import here would break any caller (e.g. tests/test_session_memory.py,
# not editable by this task) that imports rush.session_memory before that cycle is otherwise
# resolved.

logger = get_logger("session_memory")

DEFAULT_MEMORY_FILE = Path(".rush") / "session_memory.json"


class _AttributionDenied:
    """72-T01 D4: `record_fix_attribution`'s value when the write is not authorized."""

    def __repr__(self) -> str:
        return "ATTRIBUTION_DENIED"


#: Returned by `record_fix_attribution` when the memory policy denies the link.
ATTRIBUTION_DENIED = _AttributionDenied()


@dataclass(frozen=True)
class SessionRecord:
    """Represents one turn of evaluation and remediation."""

    timestamp: str
    tool_name: str
    finding_count: int
    fixes_applied: int
    summary: str


class SessionMemoryManager:
    """Manages multi-turn history with prompt injection sanitization and XML framing."""

    def __init__(self, memory_file: Path | None = None, max_records: int = 50) -> None:
        # Absolute, not resolved: the root that authorizes a write comes from the path
        # as named, so a symlink cannot move it to its target's project.
        self.memory_file = (memory_file or DEFAULT_MEMORY_FILE).absolute()
        self.max_records = max_records
        # Canonical .rush files share the repository store; bare custom paths stay isolated.
        parent = self.memory_file.parent
        self._project_root = parent.parent if parent.name == ".rush" else parent

    def load_records(self) -> list[SessionRecord]:
        """Load session records from disk."""
        if not self.memory_file.is_file():
            return []
        try:
            data = json.loads(self.memory_file.read_text(encoding="utf-8"))
            records = [SessionRecord(**item) for item in data.get("records", [])]
            return records
        except Exception as exc:  # noqa: BLE001
            log_subsystem("memory", "ERROR", f"Failed to load session memory: {exc}")
            return []

    def record_turn(
        self,
        tool_name: str,
        findings: int,
        fixes: int,
        summary: str,
    ) -> None:
        """Sanitize and record an evaluation turn. 72-T01 D4: authorized through the
        shared writer gate first; a denial logs and writes nothing (never raises)."""
        from rush.io.physical_paths import ContainmentError
        from rush.memory.retrieval import RouteDenial, authorize_writer
        from rush.memory.store import MemoryAccessChanged

        with authorize_writer(
            self._project_root, "session_memory:record_turn"
        ) as granted:
            if isinstance(granted, RouteDenial):
                log_subsystem(
                    "memory",
                    "WARNING",
                    f"Session turn not recorded: {granted.code} ({granted.reason})",
                )
                return
            try:
                relative = self._contained_relative_path()
            except ContainmentError as exc:
                log_subsystem(
                    "memory",
                    "WARNING",
                    f"Session turn not recorded: {exc.code}",
                )
                return
            from rush.memory.retrieval import recheck_failure, writer_owner
            from rush.memory.store import MemoryArtifact, write_checked_artifact
            from rush.memory.trust import default_entry_tier

            records, origin_id, artifact_content = self._stage_turn(
                tool_name, findings, fixes, summary
            )
            try:
                write_checked_artifact(
                    self._project_root,
                    MemoryArtifact(
                        id=str(uuid.uuid4()),
                        family="experience",
                        subject="episodic",
                        trust_tier=default_entry_tier("local_tool"),
                        content=artifact_content,
                        source="session_memory:record_turn",
                        created_at=time.time(),
                        origin_kind="session_memory",
                        origin_id=origin_id,
                        owner_scope=writer_owner(granted),
                    ),
                    commit_check=lambda: recheck_failure(granted),
                )
            except MemoryAccessChanged as exc:
                log_subsystem(
                    "memory",
                    "WARNING",
                    f"Session turn not recorded: {exc.code} ({exc.reason})",
                )
                return
            try:
                self._publish_turn_file(tool_name, records, relative)
            except ContainmentError as exc:
                log_subsystem(
                    "memory",
                    "WARNING",
                    f"Session turn file not published: {exc.code}",
                )
        return

    def _contained_relative_path(self) -> Path:
        """The memory file's path relative to its project root, refused (before any
        store or file effect) when a symlink or reparse point lies on it. A root that
        does not exist yet holds no link; the authorized write creates it."""
        from rush.io.physical_paths import PhysicalRoot

        relative = self.memory_file.relative_to(self._project_root)
        if self._project_root.is_dir():
            PhysicalRoot(self._project_root).open_contained(relative, purpose="write")
        return relative

    def _stage_turn(
        self, tool_name: str, findings: int, fixes: int, summary: str
    ) -> tuple[list[SessionRecord], str, dict[str, Any]]:
        """Sanitize the turn without touching the filesystem; returns the records the
        session JSON file will hold plus the turn's `(origin_id, content)` for the
        forward-write."""
        records = self.load_records()

        # Sanitize summary before truncation
        cleaned_text = summary.replace("\x00", "").strip()
        redacted_summary = SecretRedactor.redact_text(cleaned_text)
        sanitized_summary = redacted_summary[:1024]
        new_record = SessionRecord(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            tool_name=tool_name,
            finding_count=findings,
            fixes_applied=fixes,
            summary=sanitized_summary,
        )

        records.append(new_record)
        if len(records) > self.max_records:
            records = records[-self.max_records :]

        from rush.safety.redactor import sanitize_value

        # Forward-write path (P61.5.2, T-61.23): sanitize-then-write into TypedArtifactStore,
        # same (sanitize_value -> write()) sequence FlightRecorder.record_event uses. Shares
        # migrate_session_memory()'s origin_id derivation so a pre-existing legacy record already
        # forward-written here is never re-inserted when migration later runs over the same file.
        origin_id = hashlib.sha256(
            f"{new_record.timestamp}{new_record.tool_name}{new_record.summary}".encode()
        ).hexdigest()
        return records, origin_id, sanitize_value(asdict(new_record)).value

    def _publish_turn_file(
        self, tool_name: str, records: list[SessionRecord], relative: Path
    ) -> None:
        """Publish the staged records to the session JSON file through the contained
        atomic writer; runs only after the checked typed-store write committed."""
        from rush.io.atomic_file import AtomicFile, SanitizedJsonValue
        from rush.io.physical_paths import PhysicalRoot

        AtomicFile(PhysicalRoot(self._project_root)).write_json(
            relative,
            SanitizedJsonValue.from_value({"records": [asdict(r) for r in records]}),
        )
        log_subsystem("memory", "DEBUG", f"Recorded session turn for {tool_name}")

    def format_for_mcp(self) -> str:
        """Format session memory in strict XML boundary frames to prevent prompt injection.

        Reads from `TypedArtifactStore` (via `migration.read_origin_kind`) instead of
        `load_records()`'s file read (P61.5.2) — same output shape, same `origin_kind`
        `record_turn()` forward-writes under.
        """
        from rush.memory.migration import read_origin_kind

        records = read_origin_kind(self._project_root, "session_memory")
        out = ["<rush_session_memory>"]
        for r in records[-self.max_records :]:
            clean_summary = saxutils.escape(r["summary"])
            clean_tool = saxutils.escape(r["tool_name"])
            out.append(
                f'  <record tool="{clean_tool}" findings="{r["finding_count"]}" '
                f'fixes="{r["fixes_applied"]}" time="{r["timestamp"]}">{clean_summary}</record>'
            )
        out.append("</rush_session_memory>")
        return "\n".join(out)


def record_fix_attribution(
    project_root: Path, commit: dict[str, Any], failure_id: str
) -> MemoryArtifact | _AttributionDenied | None:
    """Link a `GitTrailerParser`-classified `is_fix=True` commit's SHA to the failure record it fixed.

    Stores only the commit SHA (Phase 62 §6.5 Invariant 4) — never the commit body/diff. Keyed by
    `(commit sha, failure_id)` so a rerun over the same commit never duplicates the link.
    Returns the committed link (T19), or `None` when that link already existed. 72-T01
    D4: `ATTRIBUTION_DENIED` (nothing written) when the memory policy denies it.
    """
    from rush.memory.migration import write_if_new
    from rush.memory.retrieval import RouteDenial, authorize_writer
    from rush.memory.store import MemoryAccessChanged, TypedArtifactStore

    source = "provenance_ai:attribution_link"
    with authorize_writer(Path(project_root), source) as granted:
        if isinstance(granted, RouteDenial):
            return ATTRIBUTION_DENIED
        store = TypedArtifactStore(project_root)
        try:
            return write_if_new(
                store,
                family="experience",
                subject="episodic",
                content={"commit_sha": commit["hash"], "failure_id": failure_id},
                source=source,
                origin_kind="attribution_link",
                origin_id=f"{commit['hash']}:{failure_id}",
                symbol_ref=failure_id,
                access=granted,
            )
        except MemoryAccessChanged:
            return ATTRIBUTION_DENIED


def find_attribution_link(project_root: Path, failure_id: str) -> str | None:
    """Return the commit SHA linked to `failure_id` via `record_fix_attribution()`, if any."""
    from rush.memory.migration import read_origin_kind_by_symbol

    links = read_origin_kind_by_symbol(project_root, "attribution_link", failure_id)
    return links[-1]["commit_sha"] if links else None
