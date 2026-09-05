"""Local file-based lock manager coordinating concurrent agent edits with capability verification."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

from rush.io import (
    AtomicFile,
    ContainmentError,
    PhysicalRoot,
    SanitizedJsonValue,
    VerifierError,
    VerifierRecord,
)
from rush.mcp_mesh.capabilities import (
    LockCapabilityInput,
    LockLeaseRecord,
    _calculate_entropy,
    create_capability,
)
from rush.safety.redactor import SecretRedactor


class MeshLockManager:
    """Provides file-level mutual exclusion locks with caller-retained capabilities and verifier records."""

    _proc_mutex = threading.Lock()
    _generation_counters: ClassVar[dict[str, int]] = {}

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.locks_dir = self.project_root / ".rush" / "locks"
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        self.physical_root = PhysicalRoot(self.project_root)
        self._atomic_file = AtomicFile(self.physical_root)
        self._legacy_capabilities: dict[str, str] = {}

    @classmethod
    def _lock_name(cls, target_path: Path | str) -> str:
        return str(target_path).replace("/", "_").replace("\\", "_").replace(":", "_")

    def _lock_file_for(self, target_path: Path | str) -> Path:
        sanitized = self._lock_name(target_path)
        return self.locks_dir / f"{sanitized}.lock"

    def _rel_lock_path(self, target_path: Path | str) -> Path:
        sanitized = self._lock_name(target_path)
        return Path(".rush") / "locks" / f"{sanitized}.lock"

    @classmethod
    def inspect(cls, project_root: Path, target_path: Path) -> dict[str, object]:
        """Read lock evidence without creating a lock directory or modifying lock state."""
        sanitized = cls._lock_name(target_path)
        lock_path = project_root / ".rush" / "locks" / f"{sanitized}.lock"
        if not lock_path.is_file():
            return {"state": "available", "owner": None}
        if lock_path.is_symlink():
            return {"state": "unavailable", "owner": None}
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            owner = data.get("owner_agent_id") or data.get("agent_id")
            acquired_at = data.get("acquired_at")
            expires_at = data.get("expires_at")
            generation = data.get("generation", 1)
            if not isinstance(owner, str) or not isinstance(acquired_at, (int, float)):
                return {"state": "unavailable", "owner": None}
            if expires_at is not None and time.time() > float(expires_at):
                return {
                    "state": "expired",
                    "owner": owner,
                    "acquired_at": acquired_at,
                    "generation": generation,
                }
            return {
                "state": "held",
                "owner": owner,
                "acquired_at": acquired_at,
                "generation": generation,
            }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {"state": "unavailable", "owner": None}

    def owner(self, file_path: Path) -> str | None:
        """Read the owner without acquiring, releasing, or modifying a lock."""
        owner = self.inspect(self.project_root, file_path).get("owner")
        return owner if isinstance(owner, str) else None

    def acquire(
        self,
        file_path: Path,
        agent_id: str,
        capability: LockCapabilityInput | str | None = None,
        timeout_s: float = 5.0,
        ttl_s: float = 60.0,
        return_capability: bool = False,
        **kwargs: Any,
    ) -> tuple[bool, LockCapabilityInput | None] | bool:
        """Acquire a non-blocking lock lease on target file with caller capability verification."""
        caller_provided = capability is not None
        if caller_provided:
            if isinstance(capability, LockCapabilityInput):
                token = capability.token
                agent_id = capability.agent_id or agent_id
            elif isinstance(capability, str):
                token = capability
            else:
                return False if not return_capability else (False, None)
        else:
            cap_input, token = create_capability(
                agent_id=agent_id, channel_type="stdin"
            )
            capability = cap_input

        clean_agent_id = SecretRedactor.redact_text(agent_id)

        # Enforce minimum entropy and length for capability token
        if len(token.strip()) < 16 or _calculate_entropy(token) < 2.5:
            return False if not return_capability else (False, None)

        try:
            vr = VerifierRecord.create(token)
        except VerifierError:
            return False if not return_capability else (False, None)

        lock_p = self._lock_file_for(file_path)
        rel_path = self._rel_lock_path(file_path)
        lock_key = self._lock_name(file_path)
        claim_p = self.locks_dir / f"{lock_key}.claim"

        start = time.time()
        while time.time() - start < timeout_s:
            with self._proc_mutex:
                can_claim = False
                existing_generation = 0
                if lock_p.exists():
                    if lock_p.is_symlink():
                        # Injected symlink on lock target: fail closed
                        return False if not return_capability else (False, None)
                    try:
                        existing_data = json.loads(lock_p.read_text(encoding="utf-8"))
                        exp = existing_data.get("expires_at")
                        ex_gen = existing_data.get("generation", 0)
                        if isinstance(ex_gen, int):
                            existing_generation = ex_gen
                        if exp is not None and time.time() > float(exp):
                            # Expired lock: eligible for reclaim with generation bump
                            can_claim = True
                        else:
                            can_claim = False
                    except (OSError, json.JSONDecodeError, TypeError, ValueError):
                        # Corrupted or crash leftover: recover fail-closed to new generation
                        can_claim = True
                else:
                    can_claim = True

                if can_claim:
                    try:
                        # Claim file for multi-process coordination
                        try:
                            claim_fd = os.open(
                                claim_p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                            )
                            os.close(claim_fd)
                        except FileExistsError:
                            try:
                                if time.time() - claim_p.stat().st_mtime > 5.0:
                                    claim_p.unlink(missing_ok=True)
                            except OSError:
                                pass
                            time.sleep(0.02)
                            continue
                        except OSError:
                            pass

                        known_gen = self._generation_counters.get(lock_key, 0)
                        generation = max(existing_generation, known_gen) + 1
                        self._generation_counters[lock_key] = generation

                        now = time.time()
                        lease = LockLeaseRecord(
                            resource_path=str(file_path),
                            owner_agent_id=clean_agent_id,
                            generation=generation,
                            verifier_record=vr.to_dict(),
                            acquired_at=now,
                            expires_at=now + ttl_s,
                            physical_root=str(self.physical_root.root_path),
                        )
                        self._atomic_file.write_json(
                            rel_path,
                            SanitizedJsonValue.from_value(lease.to_dict()),
                        )
                        claim_p.unlink(missing_ok=True)

                        if not caller_provided:
                            self._legacy_capabilities[lock_key] = token

                        if return_capability:
                            return (
                                True,
                                capability
                                if isinstance(capability, LockCapabilityInput)
                                else None,
                            )
                        return True
                    except Exception as exc:  # noqa: BLE001
                        claim_p.unlink(missing_ok=True)
                        if isinstance(exc, ContainmentError):
                            return False if not return_capability else (False, None)
            time.sleep(0.02)

        return False if not return_capability else (False, None)

    def renew(
        self,
        file_path: Path,
        capability: LockCapabilityInput | str,
        ttl_s: float = 60.0,
    ) -> bool:
        """Renew an existing lock lease in constant time and atomically increment generation."""
        token = (
            capability.token
            if isinstance(capability, LockCapabilityInput)
            else str(capability)
        )
        agent_id = (
            capability.agent_id if isinstance(capability, LockCapabilityInput) else None
        )

        if len(token.strip()) < 16 or _calculate_entropy(token) < 2.5:
            return False

        lock_p = self._lock_file_for(file_path)
        if not lock_p.exists() or lock_p.is_symlink():
            return False

        try:
            data = json.loads(lock_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return False

        exp = data.get("expires_at")
        if exp is not None and time.time() > float(exp):
            return False

        if agent_id is not None:
            clean_agent = SecretRedactor.redact_text(agent_id)
            owner = data.get("owner_agent_id") or data.get("agent_id")
            if owner != clean_agent:
                return False

        vr_dict = data.get("verifier_record")
        if not isinstance(vr_dict, dict):
            return False

        try:
            vr = VerifierRecord.from_dict(vr_dict)
        except (KeyError, ValueError, TypeError):
            return False

        if not vr.verify(token):
            return False

        with self._proc_mutex:
            lock_key = self._lock_name(file_path)
            current_gen = int(data.get("generation", 1))
            new_gen = current_gen + 1
            self._generation_counters[lock_key] = new_gen

            now = time.time()
            new_lease = LockLeaseRecord(
                resource_path=str(data.get("resource_path", file_path)),
                owner_agent_id=str(data.get("owner_agent_id", "")),
                generation=new_gen,
                verifier_record=vr.to_dict(),
                acquired_at=float(data.get("acquired_at", now)),
                expires_at=now + ttl_s,
                physical_root=str(self.physical_root.root_path),
            )
            try:
                self._atomic_file.write_json(
                    self._rel_lock_path(file_path),
                    SanitizedJsonValue.from_value(new_lease.to_dict()),
                )
                return True
            except (OSError, ContainmentError):
                return False

    def release(
        self,
        file_path: Path,
        capability: LockCapabilityInput | str | None = None,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> bool:
        """Release a lock lease after verifying caller capability or legacy agent_id."""
        lock_p = self._lock_file_for(file_path)
        if not lock_p.exists() or lock_p.is_symlink():
            return False

        try:
            data = json.loads(lock_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return False

        lock_key = self._lock_name(file_path)

        # Legacy release path: agent_id provided without capability
        if capability is None and agent_id is not None:
            clean_agent_id = SecretRedactor.redact_text(agent_id)
            owner = data.get("owner_agent_id") or data.get("agent_id")
            if owner == clean_agent_id:
                lock_p.unlink(missing_ok=True)
                self._legacy_capabilities.pop(lock_key, None)
                return True
            return False

        if capability is not None:
            token = (
                capability.token
                if isinstance(capability, LockCapabilityInput)
                else str(capability)
            )
            cap_agent_id = (
                capability.agent_id
                if isinstance(capability, LockCapabilityInput)
                else agent_id
            )

            if len(token.strip()) < 16 or _calculate_entropy(token) < 2.5:
                return False

            vr_dict = data.get("verifier_record")
            if not isinstance(vr_dict, dict):
                return False

            try:
                vr = VerifierRecord.from_dict(vr_dict)
            except (KeyError, ValueError, TypeError):
                return False

            if not vr.verify(token):
                return False

            if cap_agent_id is not None:
                clean_agent = SecretRedactor.redact_text(cap_agent_id)
                owner = data.get("owner_agent_id") or data.get("agent_id")
                if owner != clean_agent:
                    return False

            lock_p.unlink(missing_ok=True)
            self._legacy_capabilities.pop(lock_key, None)
            return True

        return False
