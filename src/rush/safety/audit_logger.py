"""HMAC-SHA256 chained security audit logger."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path


class SecurityAuditLogger:
    """Maintains an append-only, cryptographically chained audit trail on sys.stderr and .rush/audit.log."""

    def __init__(
        self, repo_root: Path, secret_key: str = "rush_internal_audit_secret"
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.secret_key = secret_key.encode("utf-8")
        self.log_file = self.repo_root / ".rush" / "audit.log"
        self.last_hash = "0" * 64

    def log_security_event(self, event_type: str, details: dict) -> str:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.time()
        record_body = {
            "timestamp": timestamp,
            "event_type": event_type,
            "details": details,
            "prev_hash": self.last_hash,
        }
        record_bytes = json.dumps(record_body, sort_keys=True).encode("utf-8")
        current_hash = hmac.new(
            self.secret_key, record_bytes, hashlib.sha256
        ).hexdigest()
        record_body["hmac_sha256"] = current_hash
        self.last_hash = current_hash

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_body) + "\n")

        return current_hash
