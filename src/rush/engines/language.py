"""Check-only adapters for externally discovered language ecosystem CLIs."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class LanguageCommandEngine(Engine):
    """Run a non-mutating language CLI command and normalize its report text."""

    def __init__(self, name: str, binary: str, command: tuple[str, ...]) -> None:
        self.name = name
        self.binary = binary
        self.command = command
        self.file_extensions = ()

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, *self.command, *args],
            cwd=cwd or path,
            timeout=300,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        text = (raw.get("stdout") or raw.get("stderr") or "").strip()
        status = "ok" if raw.get("exit_code", 0) == 0 else "fail"
        findings = (
            []
            if status == "ok"
            else [
                {
                    "path": str(path),
                    "rule": self.name,
                    "severity": "error",
                    "message": text or f"{self.name} failed",
                }
            ]
        )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"{self.name}: {'clean' if status == 'ok' else 'failed'}",
            findings=findings,
            raw=None,
        )


LANGUAGE_TEST_ENGINES = {
    "go": LanguageCommandEngine("go-test", "go", ("test", "./...")),
    "rust": LanguageCommandEngine("cargo-test", "cargo", ("test",)),
    "ruby": LanguageCommandEngine("rspec", "rspec", ()),
    "jvm": LanguageCommandEngine("jvm-test", "mvn", ("test",)),
    "swift": LanguageCommandEngine("swift-test", "swift", ("test",)),
    "php": LanguageCommandEngine("phpunit", "phpunit", ()),
    "dotnet": LanguageCommandEngine("dotnet-test", "dotnet", ("test",)),
    "elixir": LanguageCommandEngine("exunit", "mix", ("test",)),
    "dart": LanguageCommandEngine("dart-test", "dart", ("test",)),
    "scala": LanguageCommandEngine("scala-test", "sbt", ("test",)),
}

LANGUAGE_TYPE_ENGINES = {
    "go": LanguageCommandEngine("go-vet", "go", ("vet", "./...")),
    "rust": LanguageCommandEngine(
        "cargo-clippy", "cargo", ("clippy", "--", "-Dwarnings")
    ),
    "ruby": LanguageCommandEngine("rubocop", "rubocop", ("--format", "json")),
    "jvm": LanguageCommandEngine("jvm-check", "mvn", ("verify",)),
    "swift": LanguageCommandEngine("swiftlint", "swiftlint", ("lint",)),
    "php": LanguageCommandEngine("phpstan", "phpstan", ("analyse",)),
    "dotnet": LanguageCommandEngine(
        "dotnet-format", "dotnet", ("format", "--verify-no-changes")
    ),
    "elixir": LanguageCommandEngine("credo", "mix", ("credo",)),
    "dart": LanguageCommandEngine("dart-analyze", "dart", ("analyze",)),
    "scala": LanguageCommandEngine("scalafix", "scalafix", ("--check",)),
    "nix": LanguageCommandEngine("statix", "statix", ("check",)),
}

LANGUAGE_LINT_ENGINES = {
    "go": LanguageCommandEngine("golangci-lint", "golangci-lint", ("run",)),
    "rust": LanguageCommandEngine(
        "cargo-clippy", "cargo", ("clippy", "--", "-Dwarnings")
    ),
    "ruby": LanguageCommandEngine("rubocop", "rubocop", ("--format", "json")),
    "jvm": LanguageCommandEngine("jvm-check", "mvn", ("verify",)),
    "swift": LanguageCommandEngine("swiftlint", "swiftlint", ("lint",)),
    "php": LanguageCommandEngine("phpcs", "phpcs", ()),
    "dotnet": LanguageCommandEngine(
        "dotnet-format", "dotnet", ("format", "--verify-no-changes")
    ),
    "elixir": LanguageCommandEngine("credo", "mix", ("credo",)),
    "dart": LanguageCommandEngine("dart-analyze", "dart", ("analyze",)),
    "scala": LanguageCommandEngine("scalafix", "scalafix", ("--check",)),
    "nix": LanguageCommandEngine("statix", "statix", ("check",)),
}
