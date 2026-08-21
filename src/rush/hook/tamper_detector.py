"""Cryptographic SHA-256 hook signature validator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HOOK_NAMES = ["pre-commit", "commit-msg", "pre-push"]


class HookTamperDetector:
    """Detects unauthorized modifications or bypasses of Git hook scripts."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.hooks_dir = self.repo_root / ".git" / "hooks"
        self.sig_file = self.repo_root / ".rush" / "hook_signatures.json"

    def record_signatures(self) -> dict[str, str]:
        self.sig_file.parent.mkdir(parents=True, exist_ok=True)
        signatures = {}
        for name in HOOK_NAMES:
            p = self.hooks_dir / name
            if p.exists():
                signatures[name] = hashlib.sha256(p.read_bytes()).hexdigest()

        self.sig_file.write_text(json.dumps(signatures, indent=2), encoding="utf-8")
        return signatures

    def verify_signatures(self) -> tuple[bool, list[str]]:
        if not self.sig_file.exists():
            return False, ["Hook signatures not recorded in .rush/hook_signatures.json."]

        try:
            expected = json.loads(self.sig_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, [f"Corrupt hook signature file: {e}"]

        tampered = []
        for name, exp_sha in expected.items():
            p = self.hooks_dir / name
            if not p.exists():
                tampered.append(f"Hook '{name}' was deleted.")
            else:
                actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
                if actual_sha != exp_sha:
                    tampered.append(f"Hook '{name}' has been modified (tampered SHA: {actual_sha[:8]}).")

        return len(tampered) == 0, tampered
