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
from typing import Any
from xml.sax import saxutils

from rush.logging import get_logger, log_subsystem
from rush.safety.redactor import SecretRedactor

# rush.memory.migration/store/trust are imported lazily inside record_turn()/format_for_mcp()
# below, not here at module level: this module sits on the pre-existing
# migration -> store -> hook -> tools -> continuity -> checkpoint_journal -> migration import
# cycle, and a module-level import here would break any caller (e.g. tests/test_session_memory.py,
# not editable by this task) that imports rush.session_memory before that cycle is otherwise
# resolved.

logger = get_logger("session_memory")

DEFAULT_MEMORY_FILE = Path(".rush") / "session_memory.json"


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
        self.memory_file = (memory_file or DEFAULT_MEMORY_FILE).resolve()
        self.max_records = max_records
        # ponytail: project root for the forward-write TypedArtifactStore is derived from the
        # memory file's own directory (not Path.cwd()) so callers that pass a bare tmp_path file
        # (no ".rush" wrapper) stay isolated per-instance instead of sharing a real repo's store.
        self._project_root = self.memory_file.parent

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
        """Sanitize and record an evaluation turn."""
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

        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        from rush.memory.store import MemoryArtifact, TypedArtifactStore
        from rush.memory.trust import default_entry_tier
        from rush.safety.redactor import sanitize_value

        clean_payload = sanitize_value({"records": [asdict(r) for r in records]}).value
        self.memory_file.write_text(
            json.dumps(clean_payload, indent=2),
            encoding="utf-8",
        )
        log_subsystem("memory", "DEBUG", f"Recorded session turn for {tool_name}")

        # Forward-write path (P61.5.2, T-61.23): sanitize-then-write into TypedArtifactStore,
        # same (sanitize_value -> write()) sequence FlightRecorder.record_event uses. Shares
        # migrate_session_memory()'s origin_id derivation so a pre-existing legacy record already
        # forward-written here is never re-inserted when migration later runs over the same file.
        origin_id = hashlib.sha256(
            f"{new_record.timestamp}{new_record.tool_name}{new_record.summary}".encode("utf-8")
        ).hexdigest()
        artifact_content = sanitize_value(asdict(new_record)).value
        TypedArtifactStore(self._project_root).write(
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
            )
        )

    def format_for_mcp(self) -> str:
        """Format session memory in strict XML boundary frames to prevent prompt injection.

        Reads from `TypedArtifactStore` (via `migration.read_origin_kind`) instead of
        `load_records()`'s file read (P61.5.2) — same output shape, same `origin_kind`
        `record_turn()` forward-writes under.
        """
        from rush.memory.migration import read_origin_kind

        records = read_origin_kind(self._project_root, "session_memory")
        out = ["<rush_session_memory>"]
        for r in records:
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
) -> None:
    """Link a `GitTrailerParser`-classified `is_fix=True` commit's SHA to the failure record it fixed.

    Stores only the commit SHA (Phase 62 §6.5 Invariant 4) — never the commit body/diff. Keyed by
    `(commit sha, failure_id)` so a rerun over the same commit never duplicates the link.
    """
    from rush.memory.migration import write_if_new
    from rush.memory.store import TypedArtifactStore

    store = TypedArtifactStore(project_root)
    write_if_new(
        store,
        family="experience",
        subject="episodic",
        content={"commit_sha": commit["hash"], "failure_id": failure_id},
        source="provenance_ai:attribution_link",
        origin_kind="attribution_link",
        origin_id=f"{commit['hash']}:{failure_id}",
        symbol_ref=failure_id,
    )


def find_attribution_link(project_root: Path, failure_id: str) -> str | None:
    """Return the commit SHA linked to `failure_id` via `record_fix_attribution()`, if any."""
    from rush.memory.migration import read_origin_kind_by_symbol

    links = read_origin_kind_by_symbol(project_root, "attribution_link", failure_id)
    return links[-1]["commit_sha"] if links else None
