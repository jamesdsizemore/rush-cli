"""Offline validation for Rush documentation coverage and runtime references."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

SCHEMA = "rush-doc-coverage/v1"
REPORT_PATH = "docs/reports/phase-64-66-documentation-coverage.md"
BLOCK_RE = re.compile(r"```rush-doc-coverage-v1\s*\n(?P<payload>.*?)\n```", re.DOTALL)
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
TEXT_SUFFIXES = {".md", ".markdown", ".mdx"}
TEXT_RECORD_SUFFIXES = TEXT_SUFFIXES | {
    ".css",
    ".html",
    ".js",
    ".json",
    ".txt",
    ".yaml",
    ".yml",
}
REQUIRED_ENTRY_FIELDS = {
    "path",
    "sha256",
    "audience",
    "authority",
    "evidence",
    "owner",
    "media_type",
    "referrers",
    "source_state",
}
AUTHORITIES = {"current", "historical", "instruction", "planned", "generated"}
SOURCE_STATES = {"tracked", "untracked", "ignored"}


def document_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_body_digest(text: str) -> str:
    """Hash immutable history after optional leading current-status paragraph."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("Current status: "):
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def documentation_owner(relative_path: str) -> str:
    """Apply Phase 64 ordered ownership rules; first match wins."""
    path = PurePosixPath(relative_path)
    directories = path.parts[1:-1]
    if "goals" in directories or ".goalbuddy-board" in directories:
        return "legacy-evidence"
    if relative_path.startswith(
        ("docs/phase-plans/", "docs/templates/", "docs/agents/")
    ):
        return "plans-templates-agents"
    if (
        relative_path.startswith(
            ("docs/adr/", "docs/maintainers/adr/", "docs/reports/")
        )
        or "brainstorm" in directories
        or "research" in directories
        or (
            relative_path.startswith("docs/developer/") and "phase" in path.name.lower()
        )
    ):
        return "historical"
    if relative_path.startswith(("docs/tools/", "docs/specs/")) or relative_path in {
        "docs/ENGINES.md",
        "docs/TOOL_CATALOG.md",
    }:
        return "tool-docs"
    if relative_path.startswith(
        (
            "docs/getting-started/",
            "docs/tutorials/",
            "docs/user-guide/",
            "docs/integrations/",
            "docs/vibecoding/",
        )
    ):
        return "user-guides"
    if relative_path.startswith("docs/reference/") or relative_path in {
        "docs/CLI_REFERENCE.md",
        "docs/MCP_REFERENCE.md",
        "docs/CONFIGURATION.md",
    }:
        return "reference"
    if relative_path.startswith(("docs/developer/", "docs/maintainers/")):
        return "developer-maintainer"
    return "fallback"


def _git_paths(repo_root: Path, *args: str) -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", *args, "--", "docs"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        message = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"git documentation inventory failed: {message}")
    return {
        item.decode(errors="surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    }


def _source_states(repo_root: Path, paths: set[str]) -> dict[str, str]:
    tracked = _git_paths(repo_root, "--cached")
    visible = _git_paths(repo_root, "--cached", "--others", "--exclude-standard")
    return {
        path: "tracked"
        if path in tracked
        else "untracked"
        if path in visible
        else "ignored"
        for path in paths
    }


def _without_inline_code(text: str) -> str:
    runs = list(re.finditer(r"`+", text))
    visible = list(text)
    run_index = 0
    while run_index < len(runs):
        opener = runs[run_index]
        closer_index = next(
            (
                index
                for index in range(run_index + 1, len(runs))
                if len(runs[index].group()) == len(opener.group())
            ),
            None,
        )
        if closer_index is None:
            run_index += 1
            continue
        closer = runs[closer_index]
        visible[opener.start() : closer.end()] = " " * (closer.end() - opener.start())
        run_index = closer_index + 1
    return "".join(visible)


def _markdown_links(text: str) -> list[str]:
    outside_fences: list[str] = []
    fenced = False
    marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            token = stripped[:3]
            if not fenced:
                fenced, marker = True, token
            elif token == marker:
                fenced = False
            continue
        if not fenced:
            outside_fences.append(line)
    visible_text = _without_inline_code("\n".join(outside_fences))
    return [
        match.group(1) or match.group(2) for match in LINK_RE.finditer(visible_text)
    ]


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[`*_~]", "", value).strip().lower()
    value = "".join(
        char
        for char in value
        if char in "-_ " or char.isalnum() or unicodedata.category(char).startswith("M")
    )
    return re.sub(r"\s", "-", value)


def _anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    fenced = False
    marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            token = stripped[:3]
            if not fenced:
                fenced, marker = True, token
            elif token == marker:
                fenced = False
            continue
        if fenced:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = _slug(match.group(1))
        duplicate = counts.get(base, 0)
        counts[base] = duplicate + 1
        anchors.add(base if duplicate == 0 else f"{base}-{duplicate}")
    return anchors


def _json_default(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_default(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if type(value).__name__ == "Sentinel":
        return {"sentinel": value.name}
    return str(value)


def _click_type(parameter: Any) -> str:
    import click

    value_type = parameter.type
    if isinstance(value_type, click.Path):
        return "path"
    if isinstance(value_type, click.Choice):
        return "choice[" + ",".join(str(choice) for choice in value_type.choices) + "]"
    names = {
        "boolean": "bool",
        "integer": "integer",
        "float": "number",
        "text": "string",
    }
    return names.get(
        getattr(value_type, "name", ""),
        getattr(value_type, "name", type(value_type).__name__),
    )


def _cli_contracts() -> dict[str, Any]:
    import click

    from rush.cli import cli

    contracts: dict[str, Any] = {}

    def visit(command: click.Command, words: list[str]) -> None:
        context = click.Context(command)
        if words:
            parameters = []
            for parameter in command.params:
                if parameter.name == "help":
                    continue
                parameters.append(
                    {
                        "default": _json_default(parameter.default),
                        "kind": "argument"
                        if isinstance(parameter, click.Argument)
                        else "option",
                        "name": parameter.name,
                        "required": bool(parameter.required),
                        "type": _click_type(parameter),
                    }
                )
            contracts["rush " + " ".join(words)] = {
                "parameters": sorted(parameters, key=lambda item: item["name"])
            }
        if isinstance(command, click.Group):
            for name in sorted(command.list_commands(context)):
                child = command.get_command(context, name)
                if child is not None:
                    visit(child, [*words, name])

    visit(cli, [])
    return contracts


def _schema_type(schema: dict[str, Any]) -> str:
    if schema.get("format") == "path":
        return "string:path"
    if "enum" in schema:
        return "choice[" + ",".join(map(str, schema["enum"])) + "]"
    if "type" in schema:
        return str(schema["type"])
    alternatives = schema.get("anyOf", [])
    if alternatives:
        return "|".join(sorted({_schema_type(item) for item in alternatives}))
    return "any"


def _mcp_contracts() -> dict[str, Any]:
    from rush.mcp import mcp_server

    contracts: dict[str, Any] = {}
    for name, tool in sorted(mcp_server._tool_manager._tools.items()):
        schema = tool.parameters
        required = set(schema.get("required", []))
        parameters = [
            {
                "default": _json_default(parameter["default"])
                if "default" in parameter
                else {"sentinel": "UNSET"},
                "kind": "parameter",
                "name": parameter_name,
                "required": parameter_name in required,
                "type": _schema_type(parameter),
            }
            for parameter_name, parameter in sorted(
                schema.get("properties", {}).items()
            )
        ]
        contracts[name] = {"parameters": parameters}
    return contracts


def _catalog_contracts() -> dict[str, Any]:
    from rush.catalog import TOOL_SPECS

    contracts: dict[str, Any] = {}
    for name, spec in sorted(TOOL_SPECS.items()):
        parameters = []
        if spec.supports_path:
            parameters.append(
                {
                    "default": None,
                    "kind": "argument",
                    "name": "path",
                    "required": True,
                    "type": "path",
                }
            )
        parameters.extend(
            {
                "default": _json_default(option.default),
                "kind": "option",
                "name": option.name,
                "required": option.required,
                "type": option.value_type.__name__,
            }
            for option in spec.option_specs
        )
        contracts[name] = {
            "parameters": sorted(parameters, key=lambda item: item["name"])
        }
    return contracts


def collect_runtime_contracts(repo_root: Path) -> dict[str, Any]:
    """Read current checked-out CLI, MCP, and catalog registrations."""
    source = str(repo_root.resolve() / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    return {
        "cli": _cli_contracts(),
        "mcp": _mcp_contracts(),
        "catalog": _catalog_contracts(),
    }


def _all_document_paths(repo_root: Path) -> set[str]:
    docs = repo_root / "docs"
    if not docs.exists():
        return set()
    return {
        path.relative_to(repo_root).as_posix()
        for path in docs.rglob("*")
        if path.is_file()
    }


def _actual_referrers(repo_root: Path, all_paths: set[str]) -> dict[str, list[str]]:
    referrers: dict[str, set[str]] = {path: set() for path in all_paths}
    for relative in sorted(all_paths):
        source = repo_root / relative
        if source.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = source.read_text(encoding="utf-8")
        for raw_link in _markdown_links(text):
            split = urlsplit(raw_link)
            if split.scheme or split.netloc or not split.path:
                continue
            target = (source.parent / unquote(split.path)).resolve()
            try:
                target_relative = target.relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                continue
            if target_relative in referrers:
                referrers[target_relative].add(relative)
    return {path: sorted(values) for path, values in referrers.items()}


def build_document_inventory(repo_root: Path) -> list[dict[str, Any]]:
    """Build mechanical receipt fields; callers add audience/evidence semantics."""
    paths = _all_document_paths(repo_root)
    states = _source_states(repo_root, paths)
    referrers = _actual_referrers(repo_root, paths)
    entries = []
    for relative in sorted(paths):
        path = repo_root / relative
        owner = documentation_owner(relative)
        entry: dict[str, Any] = {
            "path": relative,
            "sha256": None if relative == REPORT_PATH else document_digest(path),
            "owner": owner,
            "media_type": mimetypes.guess_type(path.name)[0]
            or "application/octet-stream",
            "referrers": referrers[relative],
            "source_state": states[relative],
        }
        if owner == "historical" and path.suffix.lower() in TEXT_SUFFIXES:
            entry["immutable_body_sha256"] = historical_body_digest(
                path.read_text(encoding="utf-8")
            )
        entries.append(entry)
    return entries


def read_coverage_receipt(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    matches = list(BLOCK_RE.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"{path}: expected exactly one {SCHEMA} block")
    try:
        payload = json.loads(matches[0].group("payload"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid coverage JSON: {error.msg}") from error
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema must equal {SCHEMA}")
    return payload


def _check_links(
    repo_root: Path, all_paths: set[str], historical_paths: set[str]
) -> list[str]:
    errors: list[str] = []
    root = repo_root.resolve()
    for relative in sorted(all_paths):
        source = repo_root / relative
        if source.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = source.read_text(encoding="utf-8")
        if relative in historical_paths:
            text = text.split("\n\n", 1)[0]
        for raw_link in _markdown_links(text):
            split = urlsplit(raw_link)
            if split.scheme or split.netloc:
                continue
            target = source if not split.path else source.parent / unquote(split.path)
            resolved = target.resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                errors.append(f"{relative}: {raw_link}: target escapes repository")
                continue
            display = unquote(split.path) or relative
            if not resolved.exists():
                errors.append(f"{relative}: {display}: missing target")
                continue
            if (
                split.fragment
                and resolved.is_file()
                and resolved.suffix.lower() in TEXT_SUFFIXES
            ):
                anchor = unquote(split.fragment)
                try:
                    target_text = resolved.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    errors.append(
                        f"{relative}: {raw_link}: anchor target is not UTF-8 text"
                    )
                    continue
                if anchor not in _anchors(target_text):
                    errors.append(f"{relative}: {display}#{anchor}: missing anchor")
    return errors


def _check_contracts(actual: dict[str, Any], recorded: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(recorded, dict):
        return ["contracts: missing runtime contract object"]
    for surface in ("cli", "mcp", "catalog"):
        expected_commands = actual.get(surface, {})
        saved_commands = recorded.get(surface, {})
        if not isinstance(saved_commands, dict):
            errors.append(f"contracts.{surface}: expected command object")
            continue
        for command in sorted(set(expected_commands) - set(saved_commands)):
            errors.append(f"contracts.{surface}: missing registered command {command}")
        for command in sorted(set(saved_commands) - set(expected_commands)):
            errors.append(f"contracts.{surface}: stale unregistered command {command}")
        for command in sorted(set(expected_commands) & set(saved_commands)):
            saved_command = saved_commands[command]
            if not isinstance(saved_command, dict):
                errors.append(
                    f"contracts.{surface}.{command}: command must be an object"
                )
                continue
            saved_parameters = saved_command.get("parameters")
            if not isinstance(saved_parameters, list):
                errors.append(
                    f"contracts.{surface}.{command}: parameters must be a list"
                )
                continue
            expected_params = {
                item["name"]: item
                for item in expected_commands[command].get("parameters", [])
            }
            saved_params = {
                item.get("name"): item
                for item in saved_parameters
                if isinstance(item, dict) and item.get("name")
            }
            for name in sorted(set(expected_params) - set(saved_params)):
                errors.append(
                    f"contracts.{surface}.{command}: missing parameter {name}"
                )
            for name in sorted(set(saved_params) - set(expected_params)):
                errors.append(f"contracts.{surface}.{command}: stale parameter {name}")
            for name in sorted(set(expected_params) & set(saved_params)):
                if saved_params[name] != expected_params[name]:
                    errors.append(
                        f"contracts.{surface}.{command}.{name}: "
                        "default/required/type mismatch; "
                        f"expected {json.dumps(expected_params[name], sort_keys=True)}; "
                        f"recorded {json.dumps(saved_params[name], sort_keys=True)}"
                    )
    return errors


def check_docs(
    repo_root: Path, *, contracts: dict[str, Any] | None = None
) -> list[str]:
    """Return deterministic actionable errors; never rewrite documentation."""
    repo_root = repo_root.resolve()
    errors: list[str] = []
    all_paths = _all_document_paths(repo_root)
    try:
        git_paths = _git_paths(repo_root, "--cached", "--others", "--exclude-standard")
        states = _source_states(repo_root, all_paths)
    except ValueError as error:
        return [str(error)]
    for relative in sorted(git_paths - all_paths):
        errors.append(f"{relative}: Git inventory path missing from filesystem")

    report_path = repo_root / REPORT_PATH
    if not report_path.exists():
        return [f"{REPORT_PATH}: missing coverage report", *errors]
    try:
        receipt = read_coverage_receipt(report_path)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return [str(error), *errors]

    documents = receipt.get("documents")
    if not isinstance(documents, list):
        return [f"{REPORT_PATH}: documents must be a list", *errors]
    entries: dict[str, dict[str, Any]] = {}
    for position, entry in enumerate(documents):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            errors.append(f"{REPORT_PATH}: documents[{position}] needs string path")
            continue
        relative = entry["path"]
        if relative in entries:
            errors.append(f"{relative}: duplicate coverage receipt")
        entries[relative] = entry
        missing_fields = sorted(REQUIRED_ENTRY_FIELDS - set(entry))
        if missing_fields:
            errors.append(
                f"{relative}: missing receipt fields {', '.join(missing_fields)}"
            )

    for relative in sorted(all_paths - set(entries)):
        errors.append(f"{relative}: missing coverage receipt")
    for relative in sorted(set(entries) - all_paths):
        errors.append(f"{relative}: receipt path missing from filesystem")

    actual_referrers = _actual_referrers(repo_root, all_paths)
    for relative in sorted(all_paths & set(entries)):
        entry = entries[relative]
        path = repo_root / relative
        expected_owner = documentation_owner(relative)
        if entry.get("owner") != expected_owner:
            errors.append(f"{relative}: owner {entry.get('owner')} != {expected_owner}")
        recorded_state = entry.get("source_state")
        actual_state = states[relative]
        if recorded_state not in SOURCE_STATES:
            errors.append(f"{relative}: invalid source_state {recorded_state}")
        elif recorded_state != actual_state and not (
            recorded_state == "untracked" and actual_state == "tracked"
        ):
            errors.append(
                f"{relative}: source_state {recorded_state} != {actual_state}"
            )
        if not isinstance(entry.get("audience"), str) or not entry["audience"].strip():
            errors.append(f"{relative}: audience must be nonempty")
        if entry.get("authority") not in AUTHORITIES:
            errors.append(f"{relative}: invalid authority {entry.get('authority')}")
        evidence = entry.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(item, str) and item.strip() for item in evidence)
        ):
            errors.append(
                f"{relative}: evidence must contain exact nonempty references"
            )
        expected_digest = None if relative == REPORT_PATH else document_digest(path)
        if entry.get("sha256") != expected_digest:
            errors.append(f"{relative}: stale sha256")
        if relative != REPORT_PATH and entry.get("sha256") is None:
            errors.append(f"{relative}: sha256 null is reserved for coverage report")
        if (
            entry.get("authority") == "historical"
            and path.suffix.lower() in TEXT_SUFFIXES
        ):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"{relative}: historical text is not UTF-8")
            else:
                immutable_digest = entry.get("immutable_body_sha256")
                if immutable_digest is None:
                    errors.append(f"{relative}: missing immutable_body_sha256")
                elif immutable_digest != historical_body_digest(text):
                    errors.append(f"{relative}: historical body changed")
                if entry.get("superseded") is True and not text.startswith(
                    "Current status: "
                ):
                    errors.append(f"{relative}: missing current-status cross-reference")
        if path.suffix.lower() not in TEXT_RECORD_SUFFIXES:
            recorded_referrers = entry.get("referrers")
            if not isinstance(recorded_referrers, list):
                errors.append(f"{relative}: binary asset referrers must be a list")
            elif sorted(recorded_referrers) != actual_referrers[relative]:
                errors.append(
                    f"{relative}: referrers mismatch; expected "
                    f"{actual_referrers[relative]}; recorded {sorted(recorded_referrers)}"
                )

    errors.extend(
        _check_links(
            repo_root,
            all_paths,
            {
                relative
                for relative, entry in entries.items()
                if entry.get("authority") == "historical"
            },
        )
    )
    expected_contracts = (
        contracts if contracts is not None else collect_runtime_contracts(repo_root)
    )
    errors.extend(_check_contracts(expected_contracts, receipt.get("contracts")))
    return sorted(set(errors))


def main(
    argv: list[str] | None = None,
    *,
    repo_root: Path | None = None,
    contracts: dict[str, Any] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate documentation")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required")
    root = repo_root or Path(__file__).resolve().parent.parent
    errors = check_docs(root, contracts=contracts)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Documentation coverage and runtime contracts match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
