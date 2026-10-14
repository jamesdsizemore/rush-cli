"""Local file-based lock manager coordinating concurrent agent edits with capability verification."""

from __future__ import annotations

import errno
import importlib
import json
import os
import secrets
import stat
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from rush.io import (
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

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_INVALID_HANDLE_VALUE = 2**64 - 1
_CLAIM_RETRY_S = 0.02
_LOCK_DIRS = (".rush", "locks")


class MeshLockManager:
    """Provides file-level mutual exclusion locks with caller-retained capabilities and verifier records."""

    _proc_mutex = threading.Lock()
    _generation_counters: ClassVar[dict[str, int]] = {}

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.locks_dir = self.project_root / ".rush" / "locks"
        # 72-T04 (D26): create `.rush/locks` by the contained walk; a link or
        # reparse point stays refused (and uncreated) without raising here.
        try:
            if sys.platform == "win32":
                for fd in self._pin_windows_dirs():
                    _close(fd)
            else:
                _close(self._walk_locks_dir(create=True))
        except (OSError, ContainmentError):
            pass
        self.physical_root = PhysicalRoot(self.project_root)
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
        """Acquire a lock lease on target file with caller capability verification.

        72-T04 (D26): the lease is read, judged and published only while holding the
        persistent per-key claim, so an expired lease is reclaimed by exactly one caller
        and a live holder is never overwritten."""
        fail: tuple[bool, None] | bool = (False, None) if return_capability else False
        caller_provided = capability is not None
        if caller_provided:
            if isinstance(capability, LockCapabilityInput):
                token = capability.token
                agent_id = capability.agent_id or agent_id
            elif isinstance(capability, str):
                token = capability
            else:
                return fail
        else:
            cap_input, token = create_capability(
                agent_id=agent_id, channel_type="stdin"
            )
            capability = cap_input

        clean_agent_id = SecretRedactor.redact_text(agent_id)

        # Enforce minimum entropy and length for capability token
        if len(token.strip()) < 16 or _calculate_entropy(token) < 2.5:
            return fail

        try:
            vr = VerifierRecord.create(token)
        except VerifierError:
            return fail

        lock_key = self._lock_name(file_path)
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return fail
            try:
                claim = self._open_claim(
                    lock_key, time.monotonic() + min(5.0, remaining), create_dirs=True
                )
            except (OSError, ValueError, ContainmentError):
                return fail
            if claim is None:
                return fail
            try:
                _lease_stat, data = self._read_lease(claim.locks_fd, lock_key)
                live = data is not None and _lease_live(data)
                if not live:
                    existing_generation = 0
                    if data is not None:
                        ex_gen = data.get("generation", 0)
                        if isinstance(ex_gen, int) and not isinstance(ex_gen, bool):
                            existing_generation = ex_gen
                    with self._proc_mutex:
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
                    self._publish_lease(claim.locks_fd, lock_key, _lease_bytes(lease))
            except (OSError, ValueError, ContainmentError):
                self._abandon_claim(claim, lock_key)
                return fail
            finally:
                self._drop_claim(claim)
            if live:
                time.sleep(_CLAIM_RETRY_S)
                continue

            if not caller_provided:
                self._legacy_capabilities[lock_key] = token
            if return_capability:
                return (
                    True,
                    capability if isinstance(capability, LockCapabilityInput) else None,
                )
            return True

    def renew(
        self,
        file_path: Path,
        capability: LockCapabilityInput | str,
        ttl_s: float = 60.0,
        timeout_s: float = 5.0,
    ) -> bool:
        """Renew this caller's unexpired lease and increment its generation.

        72-T04 (D26): the capability is verified first, then the lease is re-read under
        the claim and renewed only while its generation and verifier are unchanged."""
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

        lock_key = self._lock_name(file_path)
        reviewed = self._verified_lease(lock_key, token, agent_id)
        if reviewed is None or not _lease_live(reviewed):
            return False
        try:
            claim = self._open_claim(
                lock_key, time.monotonic() + timeout_s, create_dirs=False
            )
        except (OSError, ValueError, ContainmentError):
            return False
        if claim is None:
            return False
        try:
            _lease_stat, data = self._read_lease(claim.locks_fd, lock_key)
            if data is None or not _same_lease(data, reviewed) or not _lease_live(data):
                return False
            vr = VerifierRecord.from_dict(data["verifier_record"])
            with self._proc_mutex:
                new_gen = int(data.get("generation", 1)) + 1
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
            self._publish_lease(claim.locks_fd, lock_key, _lease_bytes(new_lease))
            return True
        except (OSError, ValueError, KeyError, TypeError, ContainmentError):
            return False
        finally:
            self._drop_claim(claim)

    def release(
        self,
        file_path: Path,
        capability: LockCapabilityInput | str | None = None,
        agent_id: str | None = None,
        timeout_s: float = 5.0,
        **kwargs: Any,
    ) -> bool:
        """Release a lock lease after verifying caller capability or legacy agent_id.

        72-T04 (D26): the owner/capability match is re-judged under the claim and the
        lease is unlinked only while it is still the exact file that was judged."""
        lock_key = self._lock_name(file_path)
        reviewed: dict[str, Any] | None = None
        clean_agent: str | None = None
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
            reviewed = self._verified_lease(lock_key, token, cap_agent_id)
            if reviewed is None:
                return False
        elif agent_id is not None:
            # Legacy release path: agent_id provided without capability
            clean_agent = SecretRedactor.redact_text(agent_id)
        else:
            return False

        try:
            claim = self._open_claim(
                lock_key, time.monotonic() + timeout_s, create_dirs=False
            )
        except (OSError, ValueError, ContainmentError):
            return False
        if claim is None:
            return False
        try:
            lease_stat, data = self._read_lease(claim.locks_fd, lock_key)
            if data is None or lease_stat is None:
                return False
            if reviewed is not None:
                if not _same_lease(data, reviewed):
                    return False
            elif (data.get("owner_agent_id") or data.get("agent_id")) != clean_agent:
                return False
            if not self._unlink_lease(claim.locks_fd, lock_key, lease_stat):
                return False
            self._legacy_capabilities.pop(lock_key, None)
            return True
        except (OSError, ValueError, ContainmentError):
            return False
        finally:
            self._drop_claim(claim)

    # --- 72-T04 (D26): contained lock directory, claim and lease file I/O -----------

    def _walk_locks_dir(self, *, create: bool) -> int:
        """Open `<root>/.rush/locks` one component at a time, never following a link."""
        name = str(self.project_root)
        fd = os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
        try:
            for name in _LOCK_DIRS:
                try:
                    child = os.open(
                        name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=fd
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(name, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    child = os.open(
                        name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=fd
                    )
                _close(fd)
                fd = child
        except OSError as exc:
            _close(fd)
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise ContainmentError(
                    "LOCK_DIR_LINK", "lock directory component is a link", name
                ) from exc
            raise
        return fd

    def _ancestry_ok(self, locks_fd: int | None) -> bool:
        """The held lock directory is still `<root>/.rush/locks` with no link above it.

        Windows (`locks_fd is None`) pins every directory open without delete sharing,
        so the pinned path cannot be renamed while the claim is held."""
        if locks_fd is None:
            return True
        try:
            fresh = self._walk_locks_dir(create=False)
        except (OSError, ContainmentError):
            return False
        try:
            return _identity(os.fstat(fresh)) == _identity(os.fstat(locks_fd))
        except OSError:
            return False
        finally:
            _close(fresh)

    def _open_claim(
        self, lock_key: str, deadline: float, *, create_dirs: bool
    ) -> _Claim | None:
        """Hold the persistent `<key>.claim` file lock; `None` when `deadline` passes."""
        if sys.platform == "win32":
            return self._open_claim_windows(lock_key, deadline)
        import fcntl

        locks_fd = self._walk_locks_dir(create=create_dirs)
        try:
            if not self._ancestry_ok(locks_fd):
                raise ContainmentError(
                    "LOCK_DIR_MOVED", "lock directory moved", "locks"
                )
            name = f"{lock_key}.claim"
            while True:
                created = True
                try:
                    claim_fd = os.open(
                        name,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_NONBLOCK,
                        0o600,
                        dir_fd=locks_fd,
                    )
                except FileExistsError:
                    created = False
                    try:
                        claim_fd = os.open(
                            name,
                            os.O_RDWR | _O_NOFOLLOW | _O_NONBLOCK,
                            dir_fd=locks_fd,
                        )
                    except FileNotFoundError:
                        if time.monotonic() >= deadline:
                            _close(locks_fd)
                            return None
                        continue
                try:
                    held = os.fstat(claim_fd)
                    if not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
                        raise ContainmentError(
                            "LOCK_CLAIM_SPECIAL", "claim is not a private file", name
                        )
                    while True:
                        try:
                            fcntl.flock(claim_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() >= deadline:
                                _close(claim_fd)
                                _close(locks_fd)
                                return None
                            time.sleep(_CLAIM_RETRY_S)
                    current = os.stat(name, dir_fd=locks_fd, follow_symlinks=False)
                    if _identity(current) != _identity(held):
                        _close(claim_fd)
                        continue
                    claim = _Claim(claim_fd, locks_fd, created, ())
                    if not self._ancestry_ok(locks_fd):
                        self._abandon_claim(claim, lock_key)
                        raise ContainmentError(
                            "LOCK_DIR_MOVED", "lock directory moved", "locks"
                        )
                    return claim
                except BaseException:
                    _close(claim_fd)
                    raise
        except BaseException:
            _close(locks_fd)
            raise

    def _pin_windows_dirs(self) -> tuple[int, ...]:
        """Windows: open root, `.rush` and `locks` without delete sharing; refuse any
        reparse point before anything inside them is created."""
        msvcrt: Any = importlib.import_module("msvcrt")
        kernel32 = _kernel32()
        pinned: list[int] = []
        try:
            path = self.project_root
            for name in ("", *_LOCK_DIRS):
                if name:
                    path = path / name
                    if not os.path.lexists(path):
                        os.mkdir(path)
                handle = kernel32.CreateFileW(
                    str(path), 0x81, 0x3, None, 3, 0x02200000, None
                )
                if handle in (None, 0, -1, _INVALID_HANDLE_VALUE):
                    raise OSError(errno.EACCES, "cannot pin lock directory", str(path))
                try:
                    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
                except BaseException:
                    kernel32.CloseHandle(handle)
                    raise
                pinned.append(fd)
                attributes = getattr(os.fstat(fd), "st_file_attributes", 0)
                if not attributes & _FILE_ATTRIBUTE_DIRECTORY or (
                    attributes & _FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise ContainmentError(
                        "LOCK_DIR_REPARSE",
                        "lock directory is a reparse point",
                        str(path),
                    )
        except BaseException:
            for fd in pinned:
                _close(fd)
            raise
        return tuple(pinned)

    def _open_claim_windows(self, lock_key: str, deadline: float) -> _Claim | None:
        msvcrt: Any = importlib.import_module("msvcrt")

        pinned = self._pin_windows_dirs()
        try:
            path = self.locks_dir / f"{lock_key}.claim"
            before = _lstat_regular_or_none(path)
            claim_fd = os.open(path, os.O_RDWR | os.O_CREAT | _O_BINARY, 0o600)
            try:
                held = os.fstat(claim_fd)
                if (
                    not stat.S_ISREG(held.st_mode)
                    or held.st_nlink != 1
                    or _identity(os.lstat(path)) != _identity(held)
                    or (before is not None and _identity(before) != _identity(held))
                ):
                    raise ContainmentError(
                        "LOCK_CLAIM_SPECIAL", "claim is not a private file", str(path)
                    )
                while True:
                    try:
                        os.lseek(claim_fd, 0, os.SEEK_SET)
                        msvcrt.locking(claim_fd, msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            _close(claim_fd)
                            for fd in pinned:
                                _close(fd)
                            return None
                        time.sleep(_CLAIM_RETRY_S)
                return _Claim(claim_fd, None, before is None, pinned)
            except BaseException:
                _close(claim_fd)
                raise
        except BaseException:
            for fd in pinned:
                _close(fd)
            raise

    def _drop_claim(self, claim: _Claim) -> None:
        """Release the claim lock and every descriptor it holds (never raises)."""
        if claim.locks_fd is None:
            try:
                msvcrt: Any = importlib.import_module("msvcrt")
                os.lseek(claim.claim_fd, 0, os.SEEK_SET)
                msvcrt.locking(claim.claim_fd, msvcrt.LK_UNLCK, 1)
            except (ImportError, OSError):
                pass
        _close(claim.claim_fd)
        _close(claim.locks_fd)
        for fd in claim.dir_handles:
            _close(fd)

    def _abandon_claim(self, claim: _Claim, lock_key: str) -> None:
        """Remove a claim file this call created, only while it is still the held file."""
        if not claim.created:
            return
        name = f"{lock_key}.claim"
        try:
            held = os.fstat(claim.claim_fd)
            if claim.locks_fd is not None:
                current = os.stat(name, dir_fd=claim.locks_fd, follow_symlinks=False)
                if _identity(current) == _identity(held):
                    os.unlink(name, dir_fd=claim.locks_fd)
            else:
                path = self.locks_dir / name
                if _identity(os.stat(path, follow_symlinks=False)) == _identity(held):
                    os.unlink(path)
        except OSError:
            pass

    def _open_in_locks(self, locks_fd: int | None, name: str, flags: int) -> int:
        if locks_fd is not None:
            return os.open(name, flags | _O_NOFOLLOW, 0o600, dir_fd=locks_fd)
        path = self.locks_dir / name
        before = None if flags & os.O_CREAT else _lstat_regular_or_none(path)
        if before is None and not flags & os.O_CREAT and not os.path.lexists(path):
            raise FileNotFoundError(errno.ENOENT, "no lease", str(path))
        fd = os.open(path, flags | _O_BINARY, 0o600)
        if before is not None and _identity(os.fstat(fd)) != _identity(before):
            _close(fd)
            raise ContainmentError("LOCK_LEASE_MOVED", "lease file changed", str(path))
        return fd

    def _read_lease(
        self, locks_fd: int | None, lock_key: str
    ) -> tuple[os.stat_result | None, dict[str, Any] | None]:
        """Read `<key>.lock`: `(None, None)` when absent, `(stat, None)` when corrupt."""
        name = f"{lock_key}.lock"
        try:
            fd = self._open_in_locks(locks_fd, name, os.O_RDONLY | _O_NONBLOCK)
        except FileNotFoundError:
            return None, None
        try:
            lease_stat = os.fstat(fd)
            if not stat.S_ISREG(lease_stat.st_mode):
                raise ContainmentError(
                    "LOCK_LEASE_SPECIAL", "lease is not a regular file", name
                )
            chunks: list[bytes] = []
            while chunk := os.read(fd, 65536):
                chunks.append(chunk)
        finally:
            _close(fd)
        try:
            data = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return lease_stat, None
        return lease_stat, data if isinstance(data, dict) else None

    def _verified_lease(
        self, lock_key: str, token: str, agent_id: str | None
    ) -> dict[str, Any] | None:
        """The current lease when `token` (and `agent_id`, when given) owns it."""
        try:
            locks_fd = (
                None if sys.platform == "win32" else self._walk_locks_dir(create=False)
            )
            try:
                _lease_stat, data = self._read_lease(locks_fd, lock_key)
            finally:
                _close(locks_fd)
        except (OSError, ValueError, ContainmentError):
            return None
        if data is None:
            return None
        if agent_id is not None:
            owner = data.get("owner_agent_id") or data.get("agent_id")
            if owner != SecretRedactor.redact_text(agent_id):
                return None
        vr_dict = data.get("verifier_record")
        if not isinstance(vr_dict, dict):
            return None
        try:
            vr = VerifierRecord.from_dict(vr_dict)
        except (KeyError, ValueError, TypeError):
            return None
        return data if vr.verify(token) else None

    def _publish_lease(
        self, locks_fd: int | None, lock_key: str, payload: bytes
    ) -> None:
        """Atomically replace `<key>.lock` inside the held lock directory."""
        if not self._ancestry_ok(locks_fd):
            raise ContainmentError("LOCK_DIR_MOVED", "lock directory moved", "locks")
        temp = f".rush-lock-{secrets.token_hex(8)}.tmp"
        target = f"{lock_key}.lock"
        fd = self._open_in_locks(locks_fd, temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view) :]
                os.fsync(fd)
            finally:
                _close(fd)
            if locks_fd is not None:
                os.replace(temp, target, src_dir_fd=locks_fd, dst_dir_fd=locks_fd)
                os.fsync(locks_fd)
            else:
                os.replace(self.locks_dir / temp, self.locks_dir / target)
        except BaseException:
            try:
                if locks_fd is not None:
                    os.unlink(temp, dir_fd=locks_fd)
                else:
                    os.unlink(self.locks_dir / temp)
            except OSError:
                pass
            raise
        if not self._ancestry_ok(locks_fd):
            raise ContainmentError("LOCK_DIR_MOVED", "lock directory moved", "locks")

    def _unlink_lease(
        self, locks_fd: int | None, lock_key: str, judged: os.stat_result
    ) -> bool:
        """Unlink `<key>.lock` only while it is the exact file that was judged."""
        if not self._ancestry_ok(locks_fd):
            return False
        name = f"{lock_key}.lock"
        if locks_fd is not None:
            current = os.stat(name, dir_fd=locks_fd, follow_symlinks=False)
            if _identity(current) != _identity(judged):
                return False
            os.unlink(name, dir_fd=locks_fd)
        else:
            path = self.locks_dir / name
            if _identity(os.stat(path, follow_symlinks=False)) != _identity(judged):
                return False
            os.unlink(path)
        return self._ancestry_ok(locks_fd)


@dataclass(frozen=True)
class _Claim:
    """A held `<key>.claim` lock and the contained lock directory it was opened in."""

    claim_fd: int
    locks_fd: int | None
    created: bool
    dir_handles: tuple[int, ...]


def _kernel32() -> Any:
    """Windows seam: kernel32 with the directory-pinning signatures set."""
    import ctypes

    loader: Any = ctypes
    kernel32 = loader.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel32


def _close(fd: int | None) -> None:
    """Close a descriptor; a failing close never turns a lease answer into a raise."""
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _identity(st: os.stat_result) -> tuple[int, int]:
    return st.st_dev, st.st_ino


def _lstat_regular_or_none(path: Path) -> os.stat_result | None:
    """Windows: the existing entry at `path`, refusing a link or reparse point."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode) or (
        getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise ContainmentError("LOCK_FILE_LINK", "lock file is a link", str(path))
    return st


def _lease_live(data: dict[str, Any]) -> bool:
    """A lease with no expiry, or an unexpired one; an unreadable expiry is expired."""
    expires_at = data.get("expires_at")
    if expires_at is None:
        return True
    try:
        return time.time() <= float(expires_at)
    except (TypeError, ValueError):
        return False


def _same_lease(current: dict[str, Any], reviewed: dict[str, Any]) -> bool:
    return current.get("generation") == reviewed.get("generation") and current.get(
        "verifier_record"
    ) == reviewed.get("verifier_record")


def _lease_bytes(lease: LockLeaseRecord) -> bytes:
    """The exact bytes `AtomicFile.write_json` writes for this lease."""
    return json.dumps(
        SanitizedJsonValue.from_value(lease.to_dict()).value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
