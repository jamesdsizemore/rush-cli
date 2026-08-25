"""Sanitized Multi-Turn Session Memory (Control 7: Context Framing).

Architecture §8, Phase 29.
Maintains bounded turn history framed in strict XML boundary tags.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.sax import saxutils

from rush.logging import get_logger, log_subsystem
from rush.safety.redactor import SecretRedactor

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

        # Sanitize summary (strip null bytes, truncate)
        sanitized_summary = SecretRedactor.redact_text(
            summary.replace("\x00", "").strip()[:1024]
        )
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
        self.memory_file.write_text(
            json.dumps({"records": [asdict(r) for r in records]}, indent=2),
            encoding="utf-8",
        )
        log_subsystem("memory", "DEBUG", f"Recorded session turn for {tool_name}")

    def format_for_mcp(self) -> str:
        """Format session memory in strict XML boundary frames to prevent prompt injection."""
        records = self.load_records()
        out = ["<rush_session_memory>"]
        for r in records:
            clean_summary = saxutils.escape(r.summary)
            clean_tool = saxutils.escape(r.tool_name)
            out.append(
                f'  <record tool="{clean_tool}" findings="{r.finding_count}" '
                f'fixes="{r.fixes_applied}" time="{r.timestamp}">{clean_summary}</record>'
            )
        out.append("</rush_session_memory>")
        return "\n".join(out)
