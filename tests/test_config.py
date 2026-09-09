"""Configuration preservation contracts."""

from __future__ import annotations

import pytest

from rush.config import RushConfigError, _parse


def test_preserves_catalogued_tool_configuration(tmp_path) -> None:
    config = _parse(
        {"tools": {"typecheck": {"engine_args": ["--strict"], "check": True}}},
        tmp_path / "rush.toml",
    )

    assert config.tools["typecheck"].engine_args == ["--strict"]
    assert config.tools["typecheck"].check is True


def test_rejects_unknown_tool_configuration(tmp_path) -> None:
    with pytest.raises(RushConfigError, match="unknown tool"):
        _parse({"tools": {"typo-tool": {}}}, tmp_path / "rush.toml")


def test_mutation_workload_options_preserve_paths_and_deadline(tmp_path) -> None:
    config = _parse(
        {
            "tools": {
                "mutation": {
                    "source_paths": ["src/arithmetic.py"],
                    "test_paths": ["tests/test_arithmetic.py"],
                    "timeout_seconds": 17,
                }
            }
        },
        tmp_path / "rush.toml",
    )
    assert dict(config.tools["mutation"].options) == {
        "source_paths": ("src/arithmetic.py",),
        "test_paths": ("tests/test_arithmetic.py",),
        "timeout_seconds": 17,
    }


@pytest.mark.parametrize("deadline", [0, -1, True, "slow"])
def test_mutation_rejects_invalid_deadline(tmp_path, deadline) -> None:
    with pytest.raises(RushConfigError, match="timeout_seconds"):
        _parse(
            {"tools": {"mutation": {"timeout_seconds": deadline}}},
            tmp_path / "rush.toml",
        )


def test_fuzz_options_preserve_workload_and_limits(tmp_path) -> None:
    options = {
        "harness": "fuzz/harness.py",
        "corpus": "fuzz/corpus",
        "seed": 7,
        "max_runs": 25,
        "timeout_seconds": 11,
    }
    config = _parse({"tools": {"fuzz": options}}, tmp_path / "rush.toml")
    assert dict(config.tools["fuzz"].options) == options


@pytest.mark.parametrize(
    "options",
    [
        {"harness": "../outside.py"},
        {"corpus": "/outside"},
        {"seed": -1},
        {"max_runs": 0},
        {"timeout_seconds": False},
    ],
)
def test_fuzz_rejects_unsafe_paths_and_limits(tmp_path, options) -> None:
    with pytest.raises(RushConfigError):
        _parse({"tools": {"fuzz": options}}, tmp_path / "rush.toml")


def test_contract_options_preserve_pacts_provider_and_timeout(tmp_path) -> None:
    options = {
        "pact_files": ["pacts/consumer.json", "pacts/second.json"],
        "provider_url": "http://127.0.0.1:18965/",
        "timeout_seconds": 8,
    }
    config = _parse({"tools": {"contract": options}}, tmp_path / "rush.toml")
    assert dict(config.tools["contract"].options) == {
        **options,
        "pact_files": tuple(options["pact_files"]),
    }


@pytest.mark.parametrize(
    "options",
    [
        {"pact_files": [False]},
        {"provider_url": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": True},
    ],
)
def test_contract_rejects_invalid_config(tmp_path, options) -> None:
    with pytest.raises(RushConfigError):
        _parse({"tools": {"contract": options}}, tmp_path / "rush.toml")


def test_load_options_preserve_target_and_limits(tmp_path) -> None:
    options = {
        "script": "load/scenario.js",
        "target_url": "http://127.0.0.1:18964/",
        "vus": 2,
        "duration_seconds": 3,
        "timeout_seconds": 8,
    }
    config = _parse({"tools": {"load": options}}, tmp_path / "rush.toml")
    assert dict(config.tools["load"].options) == options


@pytest.mark.parametrize(
    "options",
    [
        {"script": "../outside.js"},
        {"vus": 0},
        {"duration_seconds": -1},
        {"timeout_seconds": True},
    ],
)
def test_load_rejects_invalid_config_limits(tmp_path, options) -> None:
    with pytest.raises(RushConfigError):
        _parse({"tools": {"load": options}}, tmp_path / "rush.toml")


def test_parses_review_source_policy_markers_and_exclusions(tmp_path) -> None:
    config = _parse(
        {
            "review": {
                "scaffold_markers": ["TODO: replace this scaffold"],
                "source_policy_exclude": ["generated/**"],
            }
        },
        tmp_path / "rush.toml",
    )

    assert config.review.scaffold_markers == ["TODO: replace this scaffold"]
    assert config.review.source_policy_exclude == ["generated/**"]


def test_detect_project_stacks_python(tmp_path) -> None:
    from rush.discovery.stack import detect_project_stacks

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test'\n", encoding="utf-8"
    )
    stacks = detect_project_stacks(tmp_path)
    assert any(s.language == "python" for s in stacks)


def test_detect_project_stacks_typescript(tmp_path) -> None:
    from rush.discovery.stack import detect_project_stacks

    (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    stacks = detect_project_stacks(tmp_path)
    assert any(s.language == "typescript" for s in stacks)


def test_generate_initial_config(tmp_path) -> None:
    from rush.tools.init_config import generate_initial_config

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test'\n", encoding="utf-8"
    )
    cfg = generate_initial_config(tmp_path)
    assert "[project]" in cfg
    assert "[cache]" in cfg


def test_setup_wizard_non_interactive(tmp_path) -> None:
    from rush.tools.setup_wizard import run_setup_wizard

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test'\n", encoding="utf-8"
    )
    res = run_setup_wizard(tmp_path, non_interactive=True)
    assert "python" in res["stacks"]
    assert len(res["skipped"]) > 0


def test_install_engine_package_security_rejection() -> None:
    from rush.tools.setup_wizard import install_engine_package

    with pytest.raises(ValueError, match="Invalid or hostile package name"):
        install_engine_package("npm", "malicious; rm -rf /")


def test_tool_config_preserves_declared_typed_options(tmp_path) -> None:
    from rush.catalog import TOOL_SPECS, ToolOptionSpec, ToolSpec

    # Inject a temporary tool spec with typed options
    opt1 = ToolOptionSpec(name="prefix", value_type=str, default="ERR_")
    opt2 = ToolOptionSpec(
        name="since_days", value_type=int, default=90, minimum=1, maximum=3650
    )
    opt3 = ToolOptionSpec(
        name="ratio", value_type=float, default=0.5, minimum=0.0, maximum=1.0
    )
    opt4 = ToolOptionSpec(name="enabled", value_type=bool, default=True)
    opt5 = ToolOptionSpec(
        name="trailers", value_type=tuple, default=("Co-authored-by",)
    )
    opt6 = ToolOptionSpec(
        name="out_file", value_type=str, path_kind="file", default="out.json"
    )

    spec = ToolSpec(
        name="dummy-tool",
        category="security",
        description="dummy",
        mcp_description="dummy",
        engine_names=(),
        maturity="real_adapter",
        option_specs=(opt1, opt2, opt3, opt4, opt5, opt6),
    )
    TOOL_SPECS["dummy-tool"] = spec
    try:
        config = _parse(
            {
                "tools": {
                    "dummy-tool": {
                        "prefix": "CUSTOM_",
                        "since_days": 30,
                        "ratio": 0.8,
                        "enabled": False,
                        "trailers": ["AI-Author"],
                        "out_file": "dist/report.json",
                    }
                }
            },
            tmp_path / "rush.toml",
        )
        opts = config.tools["dummy-tool"].options
        assert opts["prefix"] == "CUSTOM_"
        assert opts["since_days"] == 30
        assert opts["ratio"] == 0.8
        assert opts["enabled"] is False
        assert opts["trailers"] == ("AI-Author",)
        assert opts["out_file"] == "dist/report.json"
    finally:
        TOOL_SPECS.pop("dummy-tool", None)


def test_tool_config_rejects_undeclared_option(tmp_path) -> None:
    from rush.catalog import TOOL_SPECS, ToolSpec

    spec = ToolSpec(
        name="dummy-strict",
        category="security",
        description="dummy",
        mcp_description="dummy",
        engine_names=(),
        maturity="real_adapter",
        option_specs=(),
    )
    TOOL_SPECS["dummy-strict"] = spec
    try:
        with pytest.raises(RushConfigError, match="unknown option"):
            _parse(
                {"tools": {"dummy-strict": {"unsupported_key": "val"}}},
                tmp_path / "rush.toml",
            )
    finally:
        TOOL_SPECS.pop("dummy-strict", None)


def test_tool_config_rejects_wrong_type_range_choice_and_path(tmp_path) -> None:
    from rush.catalog import TOOL_SPECS, ToolOptionSpec, ToolSpec

    opt_int = ToolOptionSpec(
        name="count", value_type=int, default=10, minimum=1, maximum=100
    )
    opt_choice = ToolOptionSpec(
        name="mode", value_type=str, default="static", choices=("static", "dynamic")
    )
    opt_path = ToolOptionSpec(name="path", value_type=str, path_kind="file")

    spec = ToolSpec(
        name="dummy-validated",
        category="security",
        description="dummy",
        mcp_description="dummy",
        engine_names=(),
        maturity="real_adapter",
        option_specs=(opt_int, opt_choice, opt_path),
    )
    TOOL_SPECS["dummy-validated"] = spec
    try:
        # bool passed for int
        with pytest.raises(RushConfigError):
            _parse(
                {"tools": {"dummy-validated": {"count": True}}}, tmp_path / "rush.toml"
            )
        # out of range
        with pytest.raises(RushConfigError):
            _parse(
                {"tools": {"dummy-validated": {"count": 200}}}, tmp_path / "rush.toml"
            )
        # invalid choice
        with pytest.raises(RushConfigError):
            _parse(
                {"tools": {"dummy-validated": {"mode": "invalid"}}},
                tmp_path / "rush.toml",
            )
        # absolute path
        with pytest.raises(RushConfigError):
            _parse(
                {"tools": {"dummy-validated": {"path": "/etc/passwd"}}},
                tmp_path / "rush.toml",
            )
        # parent traversing path
        with pytest.raises(RushConfigError):
            _parse(
                {"tools": {"dummy-validated": {"path": "../secret.txt"}}},
                tmp_path / "rush.toml",
            )
    finally:
        TOOL_SPECS.pop("dummy-validated", None)


def test_tool_config_options_are_immutable_and_precedence_is_default_config_explicit(
    tmp_path,
) -> None:
    """Tool options are immutable and merge default -> TOML -> invocation once."""
    import rush.config as config_module

    config = _parse(
        {"tools": {"benchmark": {"threshold_percent": 7.5}}},
        tmp_path / "rush.toml",
    )
    options = config.tools["benchmark"].options

    with pytest.raises(TypeError):
        options["threshold_percent"] = 9.0  # type: ignore[index]

    resolve = getattr(config_module, "resolve_tool_options", None)
    assert callable(resolve)
    assert resolve("benchmark") == {
        "threshold_percent": 5.0,
        "record": False,
        "operation": "check",
        "baseline_name": "default",
    }
    assert resolve("benchmark", options) == {
        "threshold_percent": 7.5,
        "record": False,
        "operation": "check",
        "baseline_name": "default",
    }
    assert (
        resolve("benchmark", options, {"threshold_percent": "3.5"})["threshold_percent"]
        == 3.5
    )

    with pytest.raises(RushConfigError, match="unknown option"):
        resolve("benchmark", options, {"unknown": True})
    with pytest.raises(RushConfigError, match="must be float"):
        resolve("benchmark", options, {"threshold_percent": "invalid"})

    # Underscore normalization
    assert "export_path" in resolve("error_catalog")
