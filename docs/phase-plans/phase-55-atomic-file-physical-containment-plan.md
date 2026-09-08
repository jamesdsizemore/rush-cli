# Phase 55 Implementation Plan — AtomicFile, Physical Containment, and Verifier Records

## 1. Purpose and Status

- **Operation:** Create the comprehensive, fully specified implementation plan for remediation Phase 55 (Remediation Program Cycle 4).
- **Planning status:** Implementation-ready after §4 admission gate passes.
- **Implementation status:** Not authorized (Planning & Deep Review Phase).
- **Authority:** Governing Roadmap finding requirements (`docs/developer/repository-remediation-plan.md`) supporting:
  - **R-003** (Phase 56: Plugin trust store content digest & immutable identity).
  - **R-009** (Phase 58: Coordination mesh lock verified caller capability & safe release).
  - **R-010** (Phase 58: Persistence operations migration to AtomicFile with schema migration).
  - **R-016** (Phase 58: Patch workflow physical containment and atomic rollback).
- **Predecessor:**
  - Accepted Phase 53 sanitization kernel, write boundaries, and JSON-safe value contract (`src/rush/safety/redactor.py:sanitize_value`, `governance/remediation-phase-53.toml`).
  - Accepted Phase 54 ToolResultV1 schema kernel, finding models, legacy adapters, and operation taxonomy (`src/rush/contracts/`, `governance/remediation-phase-54.toml`).
- **Successors:**
  - Phase 56: Consumes `VerifierRecord` and `AtomicFile` for plugin trust ledger and snapshots.
  - Phase 58: Migrates lock acquisition (`src/rush/mcp_mesh/`), persistent journals (`src/rush/session_memory.py`, `src/rush/memory/`), and worktree sandboxes (`src/rush/core/git_sandbox.py`) to `AtomicFile` and `PhysicalRoot`. **Phase 61 note:** "Phase 58 owns memory-writer migration" is still true but incomplete — Phase 61 also touches these writers, reducing them to thin compatibility views over the unified `TypedArtifactStore` (`.rush/memory.db`).
- **Scope Boundary:** Establish the single authoritative file I/O primitives package `src/rush/io/`:
  - `PhysicalRoot`: Strict physical path boundary containment defeating symlinks, traversal (`..`), Windows reparse points, and target swaps.
  - `AtomicFile`: Same-directory atomic file replacement, permission preservation, fsync durability, and manager-owned fault cleanup accepting only sanitized contracts.
  - `VerifierRecord`: Cryptographically salted, one-way non-recoverable capability verification records defeating token leakage in state files.
  - Migrate NO existing runtime writers in this phase (migration is owned strictly by successor phases 56, 57, and 58).
- **Protected Boundaries:** Existing persistence writers, lock managers, plugin systems, AST redactor, result schema kernel, `pyproject.toml`, `uv.lock`.
- **Amendment Rule:** Any new public symbol, platform relaxation, dependency addition, or writer migration requires prior amendment to this plan.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite without explicit user instruction.

---

## 2. Authority, Evidence, and Closed Decisions

### 2.1 Authority Order
User Instructions → `AGENTS.md` → `GEMINI.md` → `docs/developer/repository-remediation-plan.md` (Roadmap) → `governance/remediation-contracts.toml` (R-003, R-009, R-010, R-016) → Phase 53 Sanitization Contract → Phase 54 Schema Kernel → current `src/rush/tools/common.py` and `src/rush/safety/path_confiner.py`.

### 2.2 Baseline Evidence and Defect Drivers
1. **Ad-Hoc Containment Logic:** `WorkspacePathConfiner` (`src/rush/safety/path_confiner.py`) relies on `Path.resolve().is_relative_to()`. Calling `.resolve()` evaluates symlinks before validating containment, permitting symlink target escapes where a symlink inside the workspace points to an external sensitive directory.
2. **Windows Reparse & Junction Blindspots:** Neither `WorkspacePathConfiner` nor `resolve_contained_output` (`src/rush/tools/common.py`) inspects Windows reparse attributes (`stat.FILE_ATTRIBUTE_REPARSE_POINT`). Directory junctions and Volume Mount Points on Windows can bypass string-based prefix checks.
3. **Duplicated & Fragile Atomic Writes:** `atomic_write_bytes` exists as a utility function in `src/rush/tools/common.py`, while other subsystems (`src/rush/session_memory.py`, `src/rush/memory/checkpoint_journal.py`, `src/rush/mcp_mesh/mesh_lock_daemon.py`, `src/rush/plugins/trust.py`) use direct `open(..., "w")`, `Path.write_text()`, or partial tempfile replacements without `fsync` or same-directory guarantees.
4. **Tempfile Cleanup Collateral Damage:** Current cleanup routines attempt `temp_path.unlink()`, but lack verification of manager ownership, risking accidental deletion of concurrent worker temp files if names collide or if cleanup handlers run over-broad wildcards.
5. **Raw Capability / Token Leakage in State Files:** Coordination lock tokens and plugin trust signatures are currently stored in plain text or raw JSON files, violating the principle of non-recoverable authorization storage (driving R-009 and R-003).

### 2.3 Closed Decisions (Immutable Architecture Invariants)
1. **Single I/O Authority:** `src/rush/io/` is the sole authorized primitive package for physical boundary validation, atomic writing, and capability verification. Ad-hoc implementations in `common.py` or `path_confiner.py` are deprecated for new code.
2. **Sanitized Contract Exclusivity:** `AtomicFile.write_bytes` and `AtomicFile.write_json` MUST accept ONLY sanitized contract wrappers (`SanitizedBytes`, `SanitizedJsonValue`, or `SanitizationResult`). Attempting to pass raw unsanitized bytes, raw strings, or untrusted dictionaries raises `TypeError` fail-closed.
3. **Strict Physical Containment:**
   - Absolute paths (starting with `/`, `\\`, or Windows drive letters `C:`) are strictly rejected.
   - Parent traversals (`..` components) are strictly rejected.
   - Symlinks (file or directory) are rejected along the ENTIRE path traversal down from root.
   - Windows Reparse Points / Junctions are rejected using `os.lstat()` attribute checks (`0x400`).
   - Resolved targets must strictly satisfy `resolved.is_relative_to(physical_root)`.
4. **Atomic Replacement Durability:**
   - Temp files are created strictly in the destination directory (`target.parent`).
   - Temp files use a dedicated unique prefix (`.rush_tmp_`).
   - Every write executes explicit `.flush()` followed by `os.fsync(fileno)` before rename.
   - Replacement uses atomic `os.replace(temp_path, target)`.
5. **Fail-Closed Fault Matrix (Old-or-New Invariant):**
   - On any injected or unexpected fault (write failure, partial write, flush error, fsync error, replace error), destination file is guaranteed to remain either in its original valid state or the new valid state. Partial or corrupted data NEVER persists at the target path.
   - Cleanup unlinks ONLY the manager-owned temporary file. Unowned files and existing destination files are NEVER deleted on failure.
6. **Non-Recoverable Verifier Records:**
   - Capability verification uses cryptographically salted, high-work-factor hashes (`pbkdf2_sha256`, 100,000 iterations, 32-byte salt).
   - Raw capabilities are NEVER stored, returned, logged, or serialized.
   - `VerifierRecord` exposes constant-time `verify(candidate)` via `hmac.compare_digest`.
   - Low-entropy or trivial tokens (< 16 characters or Shannon entropy < 2.5) are rejected at creation.
7. **Zero External Dependencies:** Pure Python 3.12 standard library (`pathlib`, `os`, `tempfile`, `hashlib`, `hmac`, `secrets`, `dataclasses`, `typing`, `json`, `datetime`). Zero third-party dependencies.

---

## 3. Goals, Outcomes, Exclusions, and Invariants

### 3.1 Outcomes
- New package `src/rush/io/` containing:
  - `src/rush/io/__init__.py`: Public symbol exports.
  - `src/rush/io/physical_paths.py`: `PhysicalRoot`, `ContainmentError`.
  - `src/rush/io/atomic_file.py`: `AtomicFile`, `SanitizedBytes`, `SanitizedJsonValue`, `AtomicWriteError`.
  - `src/rush/io/verifier_record.py`: `VerifierRecord`, `VerifierError`.
- Dedicated contract test suites:
  - `tests/test_phase55_atomic_file.py` (5 tests: T-55.01 through T-55.05): API ownership, sanitized contracts, raw secret rejection, fault injection old/new destination state, owned temp cleanup.
  - `tests/test_phase55_physical_containment.py` (3 tests: T-55.06 through T-55.08): Symlink escapes, junction/reparse points, parent swaps, outside sentinel preservation.
  - `tests/test_phase55_verifier_record.py` (3 tests: T-55.09 through T-55.11): Non-recoverable representation, wrong/stale/low-entropy rejection, constant-time verification.
- Total Phase 55 contract tests: 11 tests. Test baseline updates from 1,052 to 1,063 passed tests.
- Exhaustive documentation and governance synchronization across 28 files under `/docs` and repo root.

### 3.2 Exclusions
- Do NOT migrate existing persistence writers (`src/rush/session_memory.py`, `src/rush/cache.py`, `src/rush/memory/`) in Phase 55. Writer migration is owned by Phase 58 (R-010).
- Do NOT alter mesh lock acquisition implementation in Phase 55. Mesh lock migration is owned by Phase 58 (R-009).
- Do NOT alter plugin verification logic in Phase 55. Plugin migration is owned by Phase 56 (R-003).
- Do NOT alter Git worktree sandbox logic in Phase 55. Sandbox migration is owned by Phase 58 (R-016).
- Do NOT add dependencies to `pyproject.toml`.

### 3.3 Core Invariant: Zero Simulated Completion & Zero Downscoping
- Never propose, suggest, or execute downscoping to match degraded code.
- Zero placeholder or deferred stubs returning simulated records.
- Zero permissive test assertions (`assert status in ...` is forbidden; assert exact domain values and exceptions).
- Tests must assert physical filesystem states against realistic fixtures (real temp directories, symlinks, junctions where supported, and mock-injected faults).

---

## 4. Admission and Predecessor Gate

Before authorizing Phase 55 implementation, verify all predecessor gates:

```powershell
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 1. Verify Phase 54 completed and recorded in governance
.venv/Scripts/python.exe -c "import tomllib; d=tomllib.load(open('governance/remediation-phase-54.toml', 'rb')); assert d['phase']['status'] == 'completed'; print('Phase 54 Status: OK')"

# 2. Verify Phase 53 sanitization kernel is operational
.venv/Scripts/python.exe -c "from rush.safety.redactor import sanitize_value; res = sanitize_value({'key': 'sk-ant-api03-12345'}); assert 'sk-ant-api03-12345' not in str(res.value); print('Sanitizer Kernel: OK')"

# 3. Verify Phase 54 schema kernel contracts
.venv/Scripts/python.exe -c "from rush.contracts.results import ToolResultV1, SCHEMA_VERSION; assert SCHEMA_VERSION == '1.0.0'; print('Schema Kernel: OK')"

# 4. Verify test baseline (1,052 passing)
.venv/Scripts/python.exe -m pytest tests/ -q

# 5. Verify clean linter and formatting baseline
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
git diff --check
```

---

## 5. Requirement-Ownership Ledger

| Finding / Requirement | Description | Assigned Tasks | Verifiable Closure Proof |
|---|---|---|---|
| **REQ-55.1** | Sanitized-input contract types (`SanitizedBytes`, `SanitizedJsonValue`) | P55.1.1, P55.1.2 | `tests/test_phase55_atomic_file.py::test_atomic_file_accepts_only_sanitized_contracts` |
| **REQ-55.2** | Single authoritative atomic writer module ownership | P55.1.1, P55.1.2 | `tests/test_phase55_atomic_file.py::test_atomic_file_has_one_implementation_owner` |
| **REQ-55.3** | Raw secret wrapper rejection (fail-closed input guards) | P55.1.1, P55.1.2 | `tests/test_phase55_atomic_file.py::test_raw_secret_wrapper_is_rejected` |
| **REQ-55.4** | Physical path containment defeating symlink escapes | P55.2.1, P55.2.2 | `tests/test_phase55_physical_containment.py::test_file_and_directory_links_cannot_escape_root` |
| **REQ-55.5** | Windows reparse point / junction / swap race rejection | P55.2.1, P55.2.2 | `tests/test_phase55_physical_containment.py::test_junction_reparse_and_parent_target_swaps_fail_closed` |
| **REQ-55.6** | Outside sentinel preservation (zero writes outside root) | P55.2.1, P55.2.2 | `tests/test_phase55_physical_containment.py::test_unsupported_capability_writes_nothing` |
| **REQ-55.7** | Injected fault durability (old-or-new valid destination invariant) | P55.3.1, P55.3.2 | `tests/test_phase55_atomic_file.py::test_each_injected_fault_leaves_old_or_new_valid_destination` |
| **REQ-55.8** | Manager-owned temporary file identity cleanup | P55.3.1, P55.3.2 | `tests/test_phase55_atomic_file.py::test_cleanup_removes_only_owned_temp_identity` |
| **REQ-55.9** | Non-recoverable verifier records (zero raw capability retention) | P55.4.1, P55.4.2 | `tests/test_phase55_verifier_record.py::test_record_contains_no_raw_capability` |
| **REQ-55.10** | Verifier validation policy (entropy, wrong secret, staleness) | P55.4.1, P55.4.2 | `tests/test_phase55_verifier_record.py::test_wrong_reused_low_entropy_and_stale_values_fail` |
| **REQ-55.11** | Metadata non-invertibility & constant-time comparison | P55.4.1, P55.4.2 | `tests/test_phase55_verifier_record.py::test_metadata_cannot_recover_capability` |
| **REQ-55.12** | Exhaustive `/docs` updates & successor governance | P55.5.1 | 28 synchronized documentation & governance files |

---

## 6. Shared Contracts and Data Specifications

### 6.1 Sanitized Wrappers Specification (`src/rush/io/atomic_file.py`)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from rush.safety.redactor import SanitizationResult, sanitize_value


@dataclass(frozen=True)
class SanitizedBytes:
    data: bytes
    redaction_count: int = 0

    @classmethod
    def from_bytes(cls, raw: bytes) -> SanitizedBytes:
        """Sanitize UTF-8 decodable byte streams or wrap raw non-text binary data safely."""
        try:
            text = raw.decode("utf-8")
            res = sanitize_value(text)
            return cls(data=str(res.value).encode("utf-8"), redaction_count=res.redaction_count)
        except UnicodeDecodeError:
            # Binary data (images, bytecode) contains no string secrets; wrap directly
            return cls(data=raw, redaction_count=0)


@dataclass(frozen=True)
class SanitizedJsonValue:
    value: Any
    redaction_count: int = 0

    @classmethod
    def from_value(cls, raw: Any) -> SanitizedJsonValue:
        """Sanitize arbitrary Python data structures recursively before serialization."""
        res = sanitize_value(raw)
        return cls(value=res.value, redaction_count=res.redaction_count)
```

### 6.2 `PhysicalRoot` Specification (`src/rush/io/physical_paths.py`)

```python
from __future__ import annotations

import os
import stat
from pathlib import Path


class ContainmentError(Exception):
    """Raised when a path breaches physical workspace containment boundaries."""

    def __init__(self, code: str, message: str, path: str) -> None:
        super().__init__(f"[{code}] at '{path}': {message}")
        self.code = code
        self.message = message
        self.path = path


class PhysicalRoot:
    """Enforces strict physical filesystem containment within a designated root directory."""

    def __init__(self, root_path: Path | str) -> None:
        self.root_path = Path(root_path).resolve()
        if not self.root_path.exists():
            raise ValueError(f"Physical root path does not exist: {self.root_path}")
        if not self.root_path.is_dir():
            raise ValueError(f"Physical root path is not a directory: {self.root_path}")

    def open_contained(self, relative_path: Path | str, purpose: str = "read") -> Path:
        """Validate and resolve relative_path, ensuring it is physically contained within root.

        Guarantees:
        - Rejects absolute paths (leading '/', '\\', or Windows drive letters).
        - Rejects parent traversals ('..' in parts).
        - Rejects symlinks on the target or any directory component down from root.
        - Rejects Windows reparse points / directory junctions (0x400 attribute).
        - Revalidates resolved path containment via is_relative_to().
        - Returns physically validated Path object.
        """
        rel = Path(relative_path)
        rel_str = str(relative_path)

        # 1. Reject absolute paths
        if rel.is_absolute() or rel_str.startswith(("/", "\\")) or bool(rel.drive):
            raise ContainmentError("ABSOLUTE_PATH_DISALLOWED", "Path must be relative", rel_str)

        # 2. Reject parent traversal
        if ".." in rel.parts:
            raise ContainmentError("PARENT_TRAVERSAL_DISALLOWED", "Parent traversal '..' is forbidden", rel_str)

        candidate = self.root_path / rel

        # 3. Walk intermediate directory components to verify no symlinks or reparse points
        current = self.root_path
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise ContainmentError("SYMLINK_DISALLOWED", f"Symlink detected at component '{current}'", rel_str)
            if current.exists():
                try:
                    st = os.lstat(current)
                    if hasattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT"):
                        file_attrs = getattr(st, "st_file_attributes", 0)
                        if file_attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                            raise ContainmentError("REPARSE_POINT_DISALLOWED", f"Reparse point/junction at '{current}'", rel_str)
                except OSError:
                    pass

        # 4. Containment verification on resolved path
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root_path):
            raise ContainmentError("PATH_ESCAPE_DISALLOWED", f"Path escapes physical root: {resolved}", rel_str)

        if resolved.is_symlink():
            raise ContainmentError("SYMLINK_DISALLOWED", f"Target resolves to symlink: {resolved}", rel_str)

        return candidate
```

### 6.3 `AtomicFile` Specification (`src/rush/io/atomic_file.py`)

```python
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from rush.io.physical_paths import PhysicalRoot, ContainmentError
from rush.safety.redactor import SanitizationResult


class AtomicWriteError(Exception):
    """Raised when an atomic write operation encounters a failure."""

    def __init__(self, code: str, message: str, temp_path: str | None = None, target_path: str | None = None) -> None:
        super().__init__(f"[{code}] target '{target_path}': {message}")
        self.code = code
        self.message = message
        self.temp_path = temp_path
        self.target_path = target_path


class AtomicFile:
    """Provides fail-closed, durable atomic file replacement within a PhysicalRoot."""

    def __init__(self, physical_root: PhysicalRoot) -> None:
        self.physical_root = physical_root

    def write_bytes(self, relative_path: Path | str, content: SanitizedBytes | SanitizationResult) -> Path:
        """Write sanitized bytes atomically using same-directory temporary file and fsync durability."""
        if not isinstance(content, (SanitizedBytes, SanitizationResult)):
            raise TypeError("AtomicFile accepts only sanitized contracts (SanitizedBytes or SanitizationResult)")

        byte_data = content.data if isinstance(content, SanitizedBytes) else str(content.value).encode("utf-8")

        target = self.physical_root.open_contained(relative_path, purpose="write")
        target.parent.mkdir(parents=True, exist_ok=True)

        # Unique same-directory temporary file
        temp_file = tempfile.NamedTemporaryFile(dir=target.parent, prefix=".rush_tmp_", delete=False)
        temp_path = Path(temp_file.name)
        owned_temp = True

        try:
            temp_file.write(byte_data)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()

            # Pre-replace anti-swap TOCTOU verification
            if temp_path.is_symlink() or target.is_symlink():
                raise ContainmentError("SYMLINK_DISALLOWED", "Symlink introduced prior to replace", str(target))

            os.replace(temp_path, target)
            return target
        except Exception as exc:
            temp_file.close()
            if owned_temp and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            if isinstance(exc, ContainmentError):
                raise
            raise AtomicWriteError("WRITE_FAILED", str(exc), temp_path=str(temp_path), target_path=str(target)) from exc

    def write_json(self, relative_path: Path | str, content: SanitizedJsonValue | SanitizationResult) -> Path:
        """Serialize sanitized JSON structure and write atomically."""
        if not isinstance(content, (SanitizedJsonValue, SanitizationResult)):
            raise TypeError("AtomicFile accepts only sanitized contracts (SanitizedJsonValue or SanitizationResult)")

        raw_val = content.value
        serialized = json.dumps(raw_val, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        sanitized_bytes = SanitizedBytes(data=serialized, redaction_count=content.redaction_count)
        return self.write_bytes(relative_path, sanitized_bytes)
```

### 6.4 `VerifierRecord` Specification (`src/rush/io/verifier_record.py`)

```python
from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class VerifierError(Exception):
    """Raised when verifier creation or validation fails."""


def _calculate_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not text:
        return 0.0
    entropy = 0.0
    length = len(text)
    for char in set(text):
        p = text.count(char) / length
        entropy -= p * math.log2(p)
    return entropy


@dataclass(frozen=True)
class VerifierRecord:
    """A one-way non-recoverable capability verifier record."""

    version: str
    salt: str
    algorithm: str
    work_factor: int
    verifier: str
    created_at: str

    @classmethod
    def create(
        cls,
        raw_capability: str | bytes,
        *,
        work_factor: int = 100_000,
        algorithm: str = "pbkdf2_sha256",
    ) -> VerifierRecord:
        """Create a non-recoverable verifier record from a raw capability."""
        raw_str = raw_capability.decode("utf-8", errors="replace") if isinstance(raw_capability, bytes) else str(raw_capability)

        if len(raw_str.strip()) < 16:
            raise VerifierError("Capability length must be at least 16 characters")

        if _calculate_entropy(raw_str) < 2.5:
            raise VerifierError("Capability entropy too low (< 2.5 bits/symbol)")

        salt_bytes = secrets.token_bytes(32)
        raw_bytes = raw_str.encode("utf-8")

        digest = hashlib.pbkdf2_hmac("sha256", raw_bytes, salt_bytes, work_factor)
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return cls(
            version="1.0.0",
            salt=salt_bytes.hex(),
            algorithm=algorithm,
            work_factor=work_factor,
            verifier=digest.hex(),
            created_at=created_at,
        )

    def verify(self, candidate: str | bytes) -> bool:
        """Verify a candidate capability in constant time."""
        candidate_str = candidate.decode("utf-8", errors="replace") if isinstance(candidate, bytes) else str(candidate)
        candidate_bytes = candidate_str.encode("utf-8")
        salt_bytes = bytes.fromhex(self.salt)

        candidate_digest = hashlib.pbkdf2_hmac("sha256", candidate_bytes, salt_bytes, self.work_factor).hex()
        return hmac.compare_digest(self.verifier, candidate_digest)

    def to_dict(self) -> dict[str, Any]:
        """Serialize verifier metadata. Guaranteed to contain zero raw capability information."""
        return {
            "version": self.version,
            "salt": self.salt,
            "algorithm": self.algorithm,
            "work_factor": self.work_factor,
            "verifier": self.verifier,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifierRecord:
        """Reconstruct a VerifierRecord from serialized dictionary."""
        return cls(
            version=str(data["version"]),
            salt=str(data["salt"]),
            algorithm=str(data["algorithm"]),
            work_factor=int(data["work_factor"]),
            verifier=str(data["verifier"]),
            created_at=str(data["created_at"]),
        )
```

---

## 7. Contract-Test Inventory

The Phase 55 contract test suite contains exactly 11 tests across 3 test files:

| Test ID | File | Test Function | Purpose & Target Seam | Non-Permissive Assertion |
|---|---|---|---|---|
| **T-55.01** | `tests/test_phase55_atomic_file.py` | `test_atomic_file_accepts_only_sanitized_contracts` | Verify `write_bytes` and `write_json` accept `SanitizedBytes`, `SanitizedJsonValue`, and `SanitizationResult`. | `assert target.read_bytes() == b"clean_data"`; raw `bytes` or raw `dict` raises `TypeError`. |
| **T-55.02** | `tests/test_phase55_atomic_file.py` | `test_atomic_file_has_one_implementation_owner` | AST scan verifying `AtomicFile` resides exclusively in `src/rush/io/atomic_file.py` with zero rogue atomic writers. | `assert len(matches) == 1`; `assert matches[0].endswith("src/rush/io/atomic_file.py")`. |
| **T-55.03** | `tests/test_phase55_atomic_file.py` | `test_raw_secret_wrapper_is_rejected` | Verify that custom/mock wrappers bypassing sanitized types cannot be passed to `AtomicFile`. | `with pytest.raises(TypeError, match="sanitized contracts"): ...` |
| **T-55.04** | `tests/test_phase55_atomic_file.py` | `test_each_injected_fault_leaves_old_or_new_valid_destination` | Inject mock failures at write, flush, fsync, and replace; verify destination remains intact with old valid content. | `assert target.read_text() == "INITIAL_VALID_CONTENT"`; `assert not any(p.name.startswith(".rush_tmp_") for p in tmp_dir.iterdir())`. |
| **T-55.05** | `tests/test_phase55_atomic_file.py` | `test_cleanup_removes_only_owned_temp_identity` | Verify failure cleanup unlinks ONLY the `.rush_tmp_*` file created by this operation and does NOT delete adjacent files. | `assert adjacent_file.exists()`; `assert target.exists()`; `assert not owned_temp.exists()`. |
| **T-55.06** | `tests/test_phase55_physical_containment.py` | `test_file_and_directory_links_cannot_escape_root` | Verify symlinks pointing outside physical root are blocked fail-closed on read and write. | `with pytest.raises(ContainmentError, match="SYMLINK_DISALLOWED"): ...`; outside sentinel is unchanged. |
| **T-55.07** | `tests/test_phase55_physical_containment.py` | `test_junction_reparse_and_parent_target_swaps_fail_closed` | Test Windows directory junction points / reparse points and target parent swap race conditions. | `with pytest.raises(ContainmentError): ...`; outside files untouched. |
| **T-55.08** | `tests/test_phase55_physical_containment.py` | `test_unsupported_capability_writes_nothing` | Verify that containment failures or unsupported path constructs write zero bytes and create zero directories. | `assert not target_path.exists()`; `assert list(root.iterdir()) == []`. |
| **T-55.09** | `tests/test_phase55_verifier_record.py` | `test_record_contains_no_raw_capability` | Verify `VerifierRecord` instance, `to_dict()`, and `repr()` contain zero substrings of the input token. | `assert raw_token not in str(rec)`; `assert raw_token not in json.dumps(rec.to_dict())`. |
| **T-55.10** | `tests/test_phase55_verifier_record.py` | `test_wrong_reused_low_entropy_and_stale_values_fail` | Verify wrong token returns `False`, short/low-entropy token raises `VerifierError`, correct token returns `True`. | `assert rec.verify("wrong_token_12345") is False`; `assert rec.verify(raw_token) is True`. |
| **T-55.11** | `tests/test_phase55_verifier_record.py` | `test_metadata_cannot_recover_capability` | Verify metadata from `to_dict()` is strictly one-way and cannot be algorithmically reversed. | `assert len(rec.salt) == 64`; `assert len(rec.verifier) == 64`; `assert rec.work_factor == 100000`. |

---

## 8. File, Dependency, and Documentation Governance

### 8.1 File Creation and Modification Inventory

```text
[NEW FILES]
src/rush/io/__init__.py
src/rush/io/physical_paths.py
src/rush/io/atomic_file.py
src/rush/io/verifier_record.py
tests/test_phase55_atomic_file.py
tests/test_phase55_physical_containment.py
tests/test_phase55_verifier_record.py
governance/remediation-phase-55.toml
docs/developer/phase-55-implementation-evidence.md

[MODIFIED FILES]
governance/remediation-contracts.toml
docs/ARCHITECTURE.md
docs/SECURITY.md
docs/SAFETY.md
docs/PRIVACY.md
docs/API_REFERENCE.md
docs/GLOSSARY.md
docs/CLI_REFERENCE.md
docs/MCP.md
docs/developer/architecture.md
docs/developer/source-tree.md
docs/developer/testing-guide.md
docs/developer/debugging-guide.md
docs/developer/tool-development.md
docs/maintainers/incident-and-security.md
docs/maintainers/release-playbook.md
docs/maintainers/versioning-and-compatibility.md
docs/safety/security-model.md
docs/safety/permissions.md
docs/safety/privacy-and-data-handling.md
docs/getting-started/glossary.md
docs/reference/result-reference.md
docs/developer/backlog.md
docs/developer/issues.md
README.md
CHANGELOG.md
```

### 8.2 Comprehensive `/docs` Synchronization Inventory (28 Files across 3 Groups)

#### Group 1: Core Specifications & Public Contracts (8 files)
1. `docs/ARCHITECTURE.md`: Document `src/rush/io/` physical containment and atomic replacement architecture.
2. `docs/SECURITY.md`: Update Control 2 and defense-in-depth sections with `PhysicalRoot`, symlink rejection, and `VerifierRecord`.
3. `docs/SAFETY.md`: Document fail-closed physical containment and old-or-new valid destination atomic replacement.
4. `docs/PRIVACY.md`: Document `VerifierRecord` non-recoverable capability guarantees.
5. `docs/API_REFERENCE.md`: Document public API for `rush.io` (`PhysicalRoot`, `AtomicFile`, `SanitizedBytes`, `SanitizedJsonValue`, `VerifierRecord`).
6. `docs/GLOSSARY.md`: Add glossary entries for `PhysicalRoot`, `AtomicFile`, `VerifierRecord`, and `ContainmentError`.
7. `docs/CLI_REFERENCE.md`: Document output file write safety and boundary containment flags.
8. `docs/MCP.md`: Document stdio workspace physical boundary containment for MCP operations.

#### Group 2: Developer, Safety & Maintainer Guides (13 files)
9. `docs/developer/architecture.md`: Add Phase 55 section covering `src/rush/io/` primitive design.
10. `docs/developer/source-tree.md`: Add `src/rush/io/` directory layout, module roles, and boundaries.
11. `docs/developer/testing-guide.md`: Add Section 12 for Phase 55 contract test suites (`tests/test_phase55_*.py`).
12. `docs/developer/debugging-guide.md`: Add troubleshooting section for `ContainmentError` codes and atomic fault recovery.
13. `docs/developer/tool-development.md`: Add guidance for future tool disk writers using `rush.io.AtomicFile`.
14. `docs/maintainers/incident-and-security.md`: Document physical containment breach incident triage and verifier validation.
15. `docs/maintainers/release-playbook.md`: Add Phase 55 pre-release verification gates.
16. `docs/maintainers/versioning-and-compatibility.md`: Document `rush.io` compatibility and SemVer rules.
17. `docs/safety/security-model.md`: Detail physical path containment and anti-traversal guarantees.
18. `docs/safety/permissions.md`: Detail write permission boundaries and contained paths.
19. `docs/safety/privacy-and-data-handling.md`: Detail non-recoverable verifier storage.
20. `docs/getting-started/glossary.md`: Add beginner glossary terms for `AtomicFile` and `PhysicalRoot`.
21. `docs/reference/result-reference.md`: Cross-reference IO containment for exported reports.

#### Group 3: Governance, Evidence & Release Tracking (7 files)
22. `governance/remediation-phase-55.toml`: Create phase completion manifest with test counts and closed requirements.
23. `governance/remediation-contracts.toml`: Reconcile predecessor references for R-003, R-009, R-010, R-016.
24. `docs/developer/phase-55-implementation-evidence.md`: Record baseline and test execution logs for all 11 contract tests.
25. `docs/developer/backlog.md`: Mark Phase 55 as Complete in milestone table.
26. `docs/developer/issues.md`: Record resolution of containment and verifier tracking issues.
27. `README.md`: Update test badge from 1,052 to 1,063 passed.
28. `CHANGELOG.md`: Document Phase 55 primitives under `[0.3.0]`.

### 8.3 Dependency Constraints
- Zero new dependencies.
- Use only Python 3.12 standard library.

---

## 9. Ordered Workstreams and Atomic Task Cards

### P55.0 — Admission & Baseline Evidence

#### P55.0.1 — EVIDENCE: Record Platform and Primitive Boundaries
- **Task ID and binary outcome:** P55.0.1; One evidence record in `docs/developer/phase-55-implementation-evidence.md` listing current platform primitives, ad-hoc writers, and predecessor verification.
- **Start goal:** Verify clean test baseline (1,052 passed) and document filesystem capability boundaries.
- **Prerequisites:** §4 Admission Gate passed.
- **Documentation impact:** Create `docs/developer/phase-55-implementation-evidence.md`.
- **Dependency impact:** None.
- **Allowed writes:** `docs/developer/phase-55-implementation-evidence.md`.
- **Allowed reads:** `src/rush/safety/path_confiner.py`, `src/rush/tools/common.py`, `governance/remediation-contracts.toml`.
- **Prohibited:** Modifying runtime source, adding dependencies, writing production code.
- **Actions:**
  1. Inspect existing path confinement in `src/rush/safety/path_confiner.py` and atomic write logic in `src/rush/tools/common.py`.
  2. Record OS platform capabilities (Windows `stat.FILE_ATTRIBUTE_REPARSE_POINT`, POSIX symlinks).
  3. Create `docs/developer/phase-55-implementation-evidence.md` documenting the baseline (1,052 passed tests, zero errors).
- **Evidence:** Evidence markdown file with recorded baseline.
- **Stop condition:** Baseline pytest fails or uncommitted repository drift is found.
- **Verified outcome:** P55.1.1 through P55.4.1 test authoring may proceed.

---

### P55.1 — Public API & Sanitized Contracts

#### P55.1.1 — RED: Define Sanitized-Input and Single-Owner API Tests
- **Task ID and binary outcome:** P55.1.1; Three tests in `tests/test_phase55_atomic_file.py` fail because `src/rush/io` does not yet exist.
- **Start goal:** Pin `SanitizedBytes`, `SanitizedJsonValue`, and single implementation ownership via failing tests.
- **Prerequisites:** P55.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase55_atomic_file.py`.
- **Allowed reads:** `src/rush/safety/redactor.py`.
- **Prohibited:** Writing production source, modifying existing writers, skipping tests.
- **Actions:**
  1. Create `tests/test_phase55_atomic_file.py`.
  2. Author `test_atomic_file_accepts_only_sanitized_contracts` (T-55.01) asserting `write_bytes` and `write_json` succeed with sanitized wrappers and fail with `TypeError` on raw unsanitized types.
  3. Author `test_atomic_file_has_one_implementation_owner` (T-55.02) scanning AST across `src/rush/` asserting `AtomicFile` has exactly one definition in `src/rush/io/atomic_file.py`.
  4. Author `test_raw_secret_wrapper_is_rejected` (T-55.03) asserting mock or unsanitized wrappers cannot bypass `AtomicFile`.
  5. Run `.venv/Scripts/python.exe -m pytest tests/test_phase55_atomic_file.py -q` and verify import errors (RED).
- **Evidence:** Pytest output showing 3 failed tests due to missing module.
- **Stop condition:** Any test passes prematurely.
- **Verified outcome:** P55.1.2 may implement the public API.

#### P55.1.2 — GREEN: Implement Sanitized-Input Contracts and AtomicFile Export
- **Task ID and binary outcome:** P55.1.2; Tests T-55.01, T-55.02, T-55.03 pass.
- **Start goal:** Implement `SanitizedBytes`, `SanitizedJsonValue`, and `AtomicFile` class skeleton satisfying the API tests.
- **Prerequisites:** Recorded P55.1.1 RED evidence.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/io/__init__.py`, `src/rush/io/atomic_file.py`.
- **Allowed reads:** `src/rush/safety/redactor.py`.
- **Prohibited:** Migrating existing writers, modifying dependencies.
- **Actions:**
  1. Create `src/rush/io/__init__.py` exporting public symbols.
  2. Create `src/rush/io/atomic_file.py` defining `SanitizedBytes`, `SanitizedJsonValue`, `AtomicWriteError`, and `AtomicFile` skeleton with type enforcement.
  3. Re-run `pytest tests/test_phase55_atomic_file.py -q` and verify all 3 tests pass (GREEN).
- **Evidence:** Pytest output showing 3 passed tests.
- **Stop condition:** Type enforcement allows raw values to pass.
- **Verified outcome:** P55.2.1 may target physical containment.

---

### P55.2 — Physical Containment

#### P55.2.1 — RED: Define Link, Reparse, Junction, and Swap Containment Tests
- **Task ID and binary outcome:** P55.2.1; Three tests in `tests/test_phase55_physical_containment.py` fail because `PhysicalRoot` is not yet implemented.
- **Start goal:** Pin symlink rejection, reparse/junction rejection, and outside sentinel preservation.
- **Prerequisites:** P55.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase55_physical_containment.py`.
- **Allowed reads:** `src/rush/safety/path_confiner.py`.
- **Prohibited:** Writing production source, using mock assertions that skip platform checks.
- **Actions:**
  1. Create `tests/test_phase55_physical_containment.py`.
  2. Author `test_file_and_directory_links_cannot_escape_root` (T-55.06) creating real symlinks pointing outside workspace root and verifying `open_contained` raises `ContainmentError`.
  3. Author `test_junction_reparse_and_parent_target_swaps_fail_closed` (T-55.07) testing reparse attributes and parent swap race conditions.
  4. Author `test_unsupported_capability_writes_nothing` (T-55.08) verifying that on containment rejection, zero bytes or directories are written outside root.
  5. Run `pytest tests/test_phase55_physical_containment.py -q` and verify RED failures.
- **Evidence:** Pytest output showing 3 failed tests.
- **Stop condition:** Symlink test fails to create fixtures or passes prematurely.
- **Verified outcome:** P55.2.2 may implement `PhysicalRoot`.

#### P55.2.2 — GREEN: Implement PhysicalRoot Fail-Closed Path Containment
- **Task ID and binary outcome:** P55.2.2; Tests T-55.06, T-55.07, T-55.08 pass cleanly.
- **Start goal:** Implement `PhysicalRoot` and `ContainmentError` in `src/rush/io/physical_paths.py`.
- **Prerequisites:** Recorded P55.2.1 RED evidence.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/io/physical_paths.py`, `src/rush/io/__init__.py`.
- **Allowed reads:** Stdlib `os`, `stat`, `pathlib`.
- **Prohibited:** Relying on unsafe `Path.resolve()` without component traversal checks.
- **Actions:**
  1. Create `src/rush/io/physical_paths.py` implementing `PhysicalRoot` and `ContainmentError`.
  2. Enforce: absolute path rejection, traversal (`..`) rejection, component-by-component symlink check, Windows `stat.FILE_ATTRIBUTE_REPARSE_POINT` inspection, and `is_relative_to(root)` validation.
  3. Export `PhysicalRoot` and `ContainmentError` in `src/rush/io/__init__.py`.
  4. Run `pytest tests/test_phase55_physical_containment.py -q` and verify all 3 tests pass (GREEN).
- **Evidence:** Pytest output showing 3 passed containment tests.
- **Stop condition:** Any symlink escape succeeds.
- **Verified outcome:** P55.3.1 may integrate `PhysicalRoot` with `AtomicFile`.

---

### P55.3 — Atomic Replacement & Durability

#### P55.3.1 — RED: Define Injected Fault and Destination State Tests
- **Task ID and binary outcome:** P55.3.1; Two tests in `tests/test_phase55_atomic_file.py` fail because atomic durability and cleanup logic are incomplete.
- **Start goal:** Pin old-or-new valid destination invariant and owned-temp cleanup across all injected fault points.
- **Prerequisites:** P55.1.2 and P55.2.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase55_atomic_file.py`.
- **Allowed reads:** Stdlib `tempfile`, `os`.
- **Prohibited:** Writing production source.
- **Actions:**
  1. Add `test_each_injected_fault_leaves_old_or_new_valid_destination` (T-55.04) to `tests/test_phase55_atomic_file.py`, using `unittest.mock.patch` to inject errors at `write`, `flush`, `fsync`, and `replace`.
  2. Add `test_cleanup_removes_only_owned_temp_identity` (T-55.05) ensuring cleanup on failure unlinks only manager-owned `.rush_tmp_*` files and leaves neighboring files untouched.
  3. Run `pytest tests/test_phase55_atomic_file.py -k "fault or cleanup" -q` and record RED failures.
- **Evidence:** Pytest output showing 2 failed fault tests.
- **Stop condition:** Fault test passes before implementation.
- **Verified outcome:** P55.3.2 may implement atomic replacement.

#### P55.3.2 — GREEN: Implement Same-Directory Atomic Replacement & Owned Cleanup
- **Task ID and binary outcome:** P55.3.2; Tests T-55.04 and T-55.05 pass cleanly.
- **Start goal:** Complete `AtomicFile.write_bytes` and `AtomicFile.write_json` with fsync durability and owned cleanup.
- **Prerequisites:** Recorded P55.3.1 RED evidence.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/io/atomic_file.py`.
- **Allowed reads:** `src/rush/io/physical_paths.py`.
- **Prohibited:** Migrating existing tool writers.
- **Actions:**
  1. Implement same-directory tempfile creation with `.rush_tmp_` prefix.
  2. Implement write, flush, and `os.fsync(fileno())` sequence.
  3. Implement pre-replace TOCTOU anti-swap verification.
  4. Implement `os.replace` atomic destination swap.
  5. Implement `except` block ensuring owned tempfile is unlinked and original destination is preserved.
  6. Run `pytest tests/test_phase55_atomic_file.py -q` and verify all 5 tests pass (GREEN).
- **Evidence:** Pytest output showing 5 passed tests in `test_phase55_atomic_file.py`.
- **Stop condition:** Destination file corrupted by partial write.
- **Verified outcome:** P55.4.1 may target verifier records.

---

### P55.4 — Verifier Records

#### P55.4.1 — RED: Define Non-Recoverable Verifier Record Policy Tests
- **Task ID and binary outcome:** P55.4.1; Three tests in `tests/test_phase55_verifier_record.py` fail because `VerifierRecord` does not exist.
- **Start goal:** Pin non-recoverable storage, constant-time verification, entropy policy, and serialization.
- **Prerequisites:** P55.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase55_verifier_record.py`.
- **Allowed reads:** Stdlib `hashlib`, `hmac`, `secrets`.
- **Prohibited:** Writing production source, logging or persisting raw secrets in tests.
- **Actions:**
  1. Create `tests/test_phase55_verifier_record.py`.
  2. Author `test_record_contains_no_raw_capability` (T-55.09) asserting no raw token appears in `VerifierRecord` attributes, `to_dict()`, or `repr()`.
  3. Author `test_wrong_reused_low_entropy_and_stale_values_fail` (T-55.10) asserting low-entropy tokens (< 16 chars or entropy < 2.5) raise `VerifierError`, and wrong tokens return `False`.
  4. Author `test_metadata_cannot_recover_capability` (T-55.11) asserting `to_dict()` metadata contains only salt, work factor, algorithm, and verifier hash.
  5. Run `pytest tests/test_phase55_verifier_record.py -q` and verify RED failures.
- **Evidence:** Pytest output showing 3 failed verifier tests.
- **Stop condition:** Test asserts insecure token storage.
- **Verified outcome:** P55.4.2 may implement `VerifierRecord`.

#### P55.4.2 — GREEN: Implement Versioned One-Way Verifier Records
- **Task ID and binary outcome:** P55.4.2; Tests T-55.09, T-55.10, T-55.11 pass cleanly.
- **Start goal:** Implement `VerifierRecord` in `src/rush/io/verifier_record.py`.
- **Prerequisites:** Recorded P55.4.1 RED evidence.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/io/verifier_record.py`, `src/rush/io/__init__.py`.
- **Allowed reads:** Stdlib `hashlib`, `hmac`, `secrets`, `math`.
- **Prohibited:** Providing any raw capability getter or storing the original string.
- **Actions:**
  1. Create `src/rush/io/verifier_record.py` implementing `VerifierRecord` dataclass and `VerifierError`.
  2. Implement Shannon entropy validation and minimum length check (16 chars).
  3. Implement cryptographically secure salt generation (32 bytes hex) and PBKDF2-HMAC-SHA256 hash (100,000 rounds).
  4. Implement constant-time `verify(candidate)` via `hmac.compare_digest`.
  5. Export `VerifierRecord` and `VerifierError` in `src/rush/io/__init__.py`.
  6. Run `pytest tests/test_phase55_verifier_record.py -q` and verify all 3 tests pass (GREEN).
- **Evidence:** Pytest output showing 3 passed verifier tests.
- **Stop condition:** Raw token retrievable from record instance.
- **Verified outcome:** P55.5.1 may proceed with documentation and governance handoff.

---

### P55.5 — Documentation and Governance Synchronization

#### P55.5.1 — VERIFY/DOCS/HANDOFF: Synchronize Documentation and Governance Evidence
- **Task ID and binary outcome:** P55.5.1; All 28 documentation and governance files listed in §8.2 are updated and aligned with zero drift.
- **Start goal:** Document `src/rush/io/` primitives, record test evidence, and hand off to successor phases 56 and 58.
- **Prerequisites:** All 11 contract tests passing (P55.1.2, P55.2.2, P55.3.2, P55.4.2).
- **Documentation impact:** 28 files updated across `/docs` and repo root.
- **Dependency impact:** None.
- **Allowed writes:** All 28 files listed in §8.2.
- **Allowed reads:** Passing contract test logs and source implementations.
- **Prohibited:** Altering runtime code or test logic.
- **Actions:**
  1. Update Group 1 specifications (8 files): `ARCHITECTURE.md`, `SECURITY.md`, `SAFETY.md`, `PRIVACY.md`, `API_REFERENCE.md`, `GLOSSARY.md`, `CLI_REFERENCE.md`, `MCP.md`.
  2. Update Group 2 developer, safety & maintainer guides (13 files): `developer/architecture.md`, `developer/source-tree.md`, `developer/testing-guide.md`, `developer/debugging-guide.md`, `developer/tool-development.md`, `maintainers/incident-and-security.md`, `maintainers/release-playbook.md`, `maintainers/versioning-and-compatibility.md`, `safety/security-model.md`, `safety/permissions.md`, `safety/privacy-and-data-handling.md`, `getting-started/glossary.md`, `reference/result-reference.md`.
  3. Create `governance/remediation-phase-55.toml` documenting 11 contract tests, status completed, and predecessor/successor links.
  4. Update `governance/remediation-contracts.toml` noting Phase 55 completed.
  5. Update `docs/developer/phase-55-implementation-evidence.md` with full execution logs.
  6. Update `docs/developer/backlog.md`, `docs/developer/issues.md`, `README.md` (1,063 tests passed), and `CHANGELOG.md`.
  7. Run delivery gate (§10) and verify clean passes.
- **Evidence:** Git diff showing 28 synchronized documentation files and passing delivery gates.
- **Stop condition:** Any doc reference or test fails.
- **Verified outcome:** Phase 55 complete and ready for successor Phase 56.

---

## 10. Final Verification and Delivery Gate

Execute the following commands in sequence to verify Phase 55 delivery:

```powershell
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 1. Run all 11 focused Phase 55 contract tests
.venv/Scripts/python.exe -m pytest tests/test_phase55_atomic_file.py tests/test_phase55_physical_containment.py tests/test_phase55_verifier_record.py -v

# 2. Run targeted regression suites (Phase 53, Phase 54, and base tests)
.venv/Scripts/python.exe -m pytest tests/test_phase53_*.py tests/test_phase54_*.py tests/test_base.py -q

# 3. Run complete test suite (expecting 1,063 passed tests)
.venv/Scripts/python.exe -m pytest tests/ -q

# 4. Run Ruff lint check across entire codebase
.venv/Scripts/ruff.exe check src tests scripts

# 5. Run Ruff format check across entire codebase
.venv/Scripts/ruff.exe format --check src tests scripts

# 6. Verify Git diff whitespace and status hygiene
git diff --check
git diff --name-only
git status --short --branch
```

---

## 11. Exit Checklist and Successor Evidence

- [ ] Ordinary RED evidence precedes every GREEN task; zero skip, xfail, or permissive assertions.
- [ ] Single authoritative `src/rush/io/` package created containing `PhysicalRoot`, `AtomicFile`, `SanitizedBytes`, `SanitizedJsonValue`, and `VerifierRecord`.
- [ ] `AtomicFile` accepts strictly `SanitizedBytes`, `SanitizedJsonValue`, or `SanitizationResult`, rejecting raw unsanitized types with `TypeError`.
- [ ] `PhysicalRoot` rejects absolute paths, parent traversals (`..`), symlinks, and Windows reparse points (`stat.FILE_ATTRIBUTE_REPARSE_POINT`).
- [ ] `open_contained()` ensures zero writes can occur outside the physical root directory.
- [ ] Atomic file writes execute strictly in the destination directory using `.rush_tmp_` prefix with `flush()` and `os.fsync()`.
- [ ] Fault injection across write, flush, fsync, and replace guarantees the destination file remains in its old valid state or new valid state (zero partial/corrupted files).
- [ ] Failure cleanup unlinks ONLY manager-owned `.rush_tmp_*` files without collateral deletion of adjacent files.
- [ ] `VerifierRecord` stores cryptographically salted hashes (`pbkdf2_sha256`, 100k rounds) with zero raw capability exposure.
- [ ] `VerifierRecord.verify()` executes in constant time via `hmac.compare_digest`.
- [ ] Capabilities with low entropy (< 2.5) or length < 16 characters are rejected with `VerifierError`.
- [ ] Zero third-party dependencies introduced; 100% pure Python 3.12 standard library.
- [ ] All 11 contract tests in `tests/test_phase55_*.py` pass.
- [ ] Full pytest suite passes with 1,063 tests.
- [ ] All 28 documentation and governance files updated and synchronized across `/docs` and repo root.
- [ ] `governance/remediation-phase-55.toml` created with complete test and requirement records.
- [ ] Predecessors for R-003, R-009, R-010, and R-016 reconciled in `governance/remediation-contracts.toml`.
- [ ] Successor phases (Phase 56 plugin trust, Phase 58 mesh locks & persistence) unblocked with stable I/O interfaces.
