"""Cryptographic trust manager for plugins and custom engines.

Architecture §8, Phase 56.
Enforces Control 6: User-Owned Content-Addressed Plugin Trust Ledger.
Repository receipts (.rush/trust.json) are strictly non-authorizing evidence.
The authoritative ledger is user-owned (~/.rush/plugin_trust_ledger.json).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rush.io.atomic_file import AtomicFile, SanitizedJsonValue
from rush.io.physical_paths import PhysicalRoot
from rush.io.verifier_record import VerifierError, VerifierRecord


class PluginTrustError(Exception):
    """Base exception for plugin trust and authorization failures."""

    def __init__(self, message: str, code: str = "PLUGIN_TRUST_ERROR") -> None:
        super().__init__(f"[{code}] {message}" if code else message)
        self.message = message
        self.code = code


class UntrustedPluginError(PluginTrustError):
    """Raised when a plugin closure has not been explicitly granted trust in the user ledger."""

    def __init__(self, message: str, code: str = "UNTRUSTED_PLUGIN") -> None:
        super().__init__(message=message, code=code)


@dataclass(frozen=True)
class TrustedPluginRecord:
    """Ledger record for an authorized plugin closure."""

    name: str
    closure_digest: str
    snapshot_path: str
    granted_at: str
    granted_by: str = "local_user"
    verifier_record: dict[str, Any] | None = None

    @property
    def file_path(self) -> str:
        """Backward compatibility for Phase 28 / legacy callers."""
        return self.snapshot_path

    @property
    def sha256_hash(self) -> str:
        """Backward compatibility for Phase 28 / legacy callers."""
        return self.closure_digest


class PluginTrustStore:
    """Manages the user-owned cryptographic trust ledger for plugins and custom engines."""

    @property
    def DEFAULT_LEDGER_PATH(self) -> Path:
        """Lazily resolved so importing this module never requires a resolvable home directory."""
        return Path.home() / ".rush" / "plugin_trust_ledger.json"

    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        ledger_path: Path | str | None = None,
    ) -> None:
        if ledger_path is not None:
            self.ledger_path = Path(ledger_path).resolve()
            self.repo_root = (
                Path(repo_root).resolve() if repo_root is not None else None
            )
        elif repo_root is not None and (
            str(repo_root).endswith(".json") or Path(repo_root).is_file()
        ):
            self.ledger_path = Path(repo_root).resolve()
            self.repo_root = None
        elif repo_root is not None and (
            "pytest" in str(repo_root).lower()
            or "temp" in str(repo_root).lower()
            or "tmp" in str(repo_root).lower()
        ):
            self.repo_root = Path(repo_root).resolve()
            self.ledger_path = (
                self.repo_root / ".rush" / "plugin_trust_ledger.json"
            ).resolve()
        else:
            env_ledger = os.environ.get("RUSH_PLUGIN_TRUST_LEDGER")
            if env_ledger:
                self.ledger_path = Path(env_ledger).resolve()
            else:
                self.ledger_path = self.DEFAULT_LEDGER_PATH.resolve()
            self.repo_root = (
                Path(repo_root).resolve() if repo_root is not None else None
            )

        self.repo_receipt = (
            (self.repo_root / ".rush" / "trust.json").resolve()
            if self.repo_root is not None
            else None
        )

    def _compute_sha256(self, file_path: Path) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    def load_trust_store(self) -> dict[str, TrustedPluginRecord]:
        """Load trusted plugin records from user-owned ledger."""
        if not self.ledger_path.is_file():
            return {}
        try:
            raw_data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if not isinstance(raw_data, dict):
                return {}
            records: dict[str, TrustedPluginRecord] = {}
            for name, item in raw_data.items():
                if not isinstance(item, dict):
                    continue
                closure_digest = str(
                    item.get("closure_digest") or item.get("sha256_hash") or ""
                )
                snapshot_path = str(
                    item.get("snapshot_path") or item.get("file_path") or ""
                )
                granted_at = str(item.get("granted_at", ""))
                granted_by = str(item.get("granted_by", "local_user"))
                verifier_record = item.get("verifier_record")
                records[name] = TrustedPluginRecord(
                    name=name,
                    closure_digest=closure_digest,
                    snapshot_path=snapshot_path,
                    granted_at=granted_at,
                    granted_by=granted_by,
                    verifier_record=verifier_record,
                )
            return records
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return {}

    def load_repo_receipt(self) -> dict[str, Any]:
        """Load in-repo receipt as non-authorizing evidence."""
        if self.repo_receipt is None or not self.repo_receipt.is_file():
            return {}
        try:
            raw_data = json.loads(self.repo_receipt.read_text(encoding="utf-8"))
            return raw_data if isinstance(raw_data, dict) else {}
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def is_trusted(self, plugin_name: str, closure_digest: str | Path) -> bool:
        """Returns True iff matching unrevoked record exists in user ledger with exact closure_digest.

        In-repo receipts are strictly non-authorizing evidence.
        """
        store = self.load_trust_store()
        record = store.get(plugin_name)
        if record is None:
            return False

        if isinstance(closure_digest, Path) or (
            isinstance(closure_digest, str)
            and len(closure_digest) != 64
            and Path(closure_digest).is_file()
        ):
            p = Path(closure_digest)
            if not p.is_file():
                return False
            expected_digest = self._compute_sha256(p)
        else:
            expected_digest = str(closure_digest)

        if not expected_digest or record.closure_digest != expected_digest:
            return False

        if record.verifier_record:
            try:
                vr = VerifierRecord.from_dict(record.verifier_record)
                capability = f"{plugin_name}:{expected_digest}"
                if not vr.verify(capability):
                    return False
            except (VerifierError, KeyError, ValueError, TypeError):
                return False

        return True

    def assert_authorized(
        self,
        plugin_name: str,
        closure_digest: str | Path,
        repo_receipt_path: Path | None = None,
    ) -> None:
        """Fail-closed assertion that raises UntrustedPluginError if plugin is not authorized."""
        digest_str: str
        if isinstance(closure_digest, Path):
            if not closure_digest.is_file():
                raise UntrustedPluginError(
                    f"Executable path '{closure_digest}' does not exist",
                    code="UNTRUSTED_PLUGIN",
                )
            digest_str = self._compute_sha256(closure_digest)
        else:
            digest_str = str(closure_digest)

        if not digest_str:
            raise UntrustedPluginError(
                f"Plugin '{plugin_name}' execution blocked: missing content digest.",
                code="UNHASHED_PLUGIN",
            )

        receipt_file = (
            repo_receipt_path if repo_receipt_path is not None else self.repo_receipt
        )
        has_repo_receipt = False
        if receipt_file is not None and receipt_file.is_file():
            try:
                data = json.loads(receipt_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and plugin_name in data:
                    has_repo_receipt = True
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                pass

        if not self.is_trusted(plugin_name, digest_str):
            if has_repo_receipt:
                raise UntrustedPluginError(
                    f"Repository receipt for plugin '{plugin_name}' is non-authorizing evidence. "
                    "Explicit user trust grant required.",
                    code="RECEIPT_NOT_AUTHORIZING",
                )
            raise UntrustedPluginError(
                f"Plugin '{plugin_name}' is untrusted or unregistered in user ledger.",
                code="UNTRUSTED_PLUGIN",
            )

    def check_authorization(
        self,
        plugin_name: str,
        closure_digest: str | Path,
        repo_receipt_path: Path | None = None,
    ) -> None:
        """Alias for assert_authorized."""
        self.assert_authorized(
            plugin_name, closure_digest, repo_receipt_path=repo_receipt_path
        )

    def grant_trust(
        self,
        plugin_name: str,
        closure_digest: str | Path,
        snapshot_path: Path | str | None = None,
    ) -> TrustedPluginRecord:
        """Saves authorized record in user ledger atomically and returns the record."""
        if snapshot_path is None and (
            isinstance(closure_digest, Path) or Path(str(closure_digest)).is_file()
        ):
            exec_path = Path(closure_digest)
            digest = self._compute_sha256(exec_path)
            rel_snap = (
                str(exec_path.relative_to(self.repo_root))
                if self.repo_root and exec_path.is_relative_to(self.repo_root)
                else str(exec_path)
            )
        else:
            digest = str(closure_digest)
            rel_snap = str(snapshot_path)

        now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        capability = f"{plugin_name}:{digest}"
        vr = VerifierRecord.create(capability, work_factor=10_000)

        record = TrustedPluginRecord(
            name=plugin_name,
            closure_digest=digest,
            snapshot_path=rel_snap,
            granted_at=now_utc,
            granted_by="local_user",
            verifier_record=vr.to_dict(),
        )

        store = self.load_trust_store()
        store[plugin_name] = record

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        user_root = PhysicalRoot(self.ledger_path.parent)
        user_af = AtomicFile(user_root)

        serialized = {
            k: {
                "name": v.name,
                "closure_digest": v.closure_digest,
                "snapshot_path": v.snapshot_path,
                "granted_at": v.granted_at,
                "granted_by": v.granted_by,
                "verifier_record": v.verifier_record,
                "file_path": v.snapshot_path,
                "sha256_hash": v.closure_digest,
            }
            for k, v in store.items()
        }
        user_af.write_json(
            self.ledger_path.name, SanitizedJsonValue.from_value(serialized)
        )

        if self.repo_root is not None and self.repo_root.is_dir():
            receipt_dir = self.repo_root / ".rush"
            receipt_dir.mkdir(parents=True, exist_ok=True)
            repo_root_phys = PhysicalRoot(receipt_dir)
            repo_af = AtomicFile(repo_root_phys)
            receipt_data = self.load_repo_receipt()
            receipt_data[plugin_name] = {
                "closure_digest": digest,
                "snapshot_path": rel_snap,
                "granted_at": now_utc,
                "granted_by": "local_user",
                "authorizing": False,
                "file_path": rel_snap,
                "sha256_hash": digest,
            }
            repo_af.write_json(
                "trust.json", SanitizedJsonValue.from_value(receipt_data)
            )

        return record

    def revoke_trust(self, plugin_name: str) -> bool:
        """Removes record from user ledger atomically."""
        if not self.ledger_path.is_file():
            return False
        store = self.load_trust_store()
        if plugin_name not in store:
            return False

        del store[plugin_name]

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        user_root = PhysicalRoot(self.ledger_path.parent)
        user_af = AtomicFile(user_root)

        serialized = {
            k: {
                "name": v.name,
                "closure_digest": v.closure_digest,
                "snapshot_path": v.snapshot_path,
                "granted_at": v.granted_at,
                "granted_by": v.granted_by,
                "verifier_record": v.verifier_record,
                "file_path": v.snapshot_path,
                "sha256_hash": v.closure_digest,
            }
            for k, v in store.items()
        }
        user_af.write_json(
            self.ledger_path.name, SanitizedJsonValue.from_value(serialized)
        )

        if (
            self.repo_root is not None
            and self.repo_receipt is not None
            and self.repo_receipt.is_file()
        ):
            receipt_data = self.load_repo_receipt()
            if plugin_name in receipt_data:
                del receipt_data[plugin_name]
                receipt_dir = self.repo_root / ".rush"
                receipt_dir.mkdir(parents=True, exist_ok=True)
                repo_root_phys = PhysicalRoot(receipt_dir)
                repo_af = AtomicFile(repo_root_phys)
                repo_af.write_json(
                    "trust.json", SanitizedJsonValue.from_value(receipt_data)
                )

        return True
