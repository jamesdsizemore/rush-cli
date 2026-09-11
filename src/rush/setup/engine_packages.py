"""Declarative engine and runtime provisioning registry.

Phase 65 §6.2 — the complete engine provisioning registry. Every key in
``rush.catalog.ENGINE_SPECS`` has exactly one row here naming its real
package identity, source registry, manager and prerequisites. This module
contains no network calls and no subprocess execution; it is pure static
data plus lookup helpers so the registry itself is exhaustively testable.

Only the declared allowlist below is installable. ``resolve_engine_package``
and ``resolve_project_manager_command`` are the only supported lookup paths;
there is no override mechanism for an arbitrary caller-supplied package or
command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

EngineSource = Literal[
    "pypi",
    "npm",
    "crates",
    "gem",
    "composer",
    "maven",
    "go",
    "github",
    "alias",
    "internal",
]


class UnknownEngineError(ValueError):
    """Raised when an engine id is not a member of the declared allowlist."""

    def __init__(self, engine_id: str) -> None:
        super().__init__(f"Unknown or unsupported engine id: {engine_id!r}")
        self.engine_id = engine_id


class UnknownProjectManagerError(ValueError):
    """Raised when a project dependency manager id is not declared."""

    def __init__(self, manager_id: str) -> None:
        super().__init__(f"Unknown or unsupported project manager id: {manager_id!r}")
        self.manager_id = manager_id


@dataclass(frozen=True)
class EnginePackage:
    """Exact installable identity and provisioning metadata for one engine."""

    engine_id: str
    package_id: str
    source: EngineSource
    manager: str
    binary: str
    version_policy: str
    platform_policy: str
    scan_class: str
    prerequisites: tuple[str, ...]
    probe: tuple[str, ...]


# --- Source classification (exhaustive, matches plan §6.2 groups exactly) --

_PYPI_ENGINES: Final[frozenset[str]] = frozenset(
    {
        "ruff",
        "pytest",
        "pip-audit",
        "mypy",
        "vulture",
        "radon",
        "sloppylint",
        "sqlfluff",
        "djlint",
        "checkov",
        "semgrep",
        "garak",
        "deepeval",
        "guardrails",
        "detect-secrets",
        "scancode",
        "pip-licenses",
        "schemathesis",
        "refurb",
        "fawltydeps",
        "zap",
        "cosmic-ray",
        "flake8-bugbear",
        "markdown-unfluff",
        "memray",
        "pyclean",
        "diff-cover",
        "pr-agent",
        "aislop",
        "tach",
        "medusa",
        "pyrefly",
    }
)

_NPM_ENGINES: Final[frozenset[str]] = frozenset(
    {
        "eslint",
        "prettier",
        "vitest",
        "tsc",
        "knip",
        "jscpd",
        "markdownlint-cli",
        "spectral",
        "cdxgen",
        "commitlint",
        "playwright",
        "axe",
        "promptfoo",
        "secretlint",
        "graphql-inspector",
        "newman",
        "depcruise",
        "biome",
        "ts-prune",
        "pa11y",
        "html-validate",
        "lighthouse",
        "blc",
        "pagespeed",
        "stryker",
        "lost-pixel",
        "backstop",
        "stylelint",
        "a11ywatch",
        "squoosh",
        "critical",
        "font-spider",
        "ast-grep",
        "squawk",
        "prisma-lint",
        "cspell",
        "alex",
        "readability",
        "no-jargon",
        "megalinter",
        "statoscope",
        "semantic-release",
        "safe-env",
        "wait-on",
        "ncu",
        "cejel",
    }
)

_CRATES_ENGINES: Final[frozenset[str]] = frozenset({"cargo-mutants", "clines"})
_GEM_ENGINES: Final[frozenset[str]] = frozenset({"undercover"})
_COMPOSER_ENGINES: Final[frozenset[str]] = frozenset({"infection"})
_MAVEN_ENGINES: Final[frozenset[str]] = frozenset({"pitest"})
_GO_SOURCE_ENGINES: Final[frozenset[str]] = frozenset({"zally"})
_ALIAS_ENGINES: Final[frozenset[str]] = frozenset({"npm-audit", "git-guard"})
_INTERNAL_ENGINES: Final[frozenset[str]] = frozenset({"semantic-drift"})

_GITHUB_REPOS: Final[dict[str, str]] = {
    "osv-scanner": "google/osv-scanner",
    "actionlint": "rhysd/actionlint",
    "hadolint": "hadolint/hadolint",
    "tflint": "terraform-linters/tflint",
    "gitleaks": "gitleaks/gitleaks",
    "lychee": "lycheeverse/lychee",
    "trivy": "aquasecurity/trivy",
    "grype": "anchore/grype",
    "cosign": "sigstore/cosign",
    "kubeconform": "yannh/kubeconform",
    "bearer": "Bearer/bearer",
    "trufflehog": "trufflesecurity/trufflehog",
    "horusec": "ZupIT/horusec",
    "scorecard": "ossf/scorecard",
    "slsa-verifier": "slsa-framework/slsa-verifier",
    "guac": "guacsec/guac",
    "terrascan": "tenable/terrascan",
    "kube-score": "zegl/kube-score",
    "conftest": "open-policy-agent/conftest",
    "polaris": "FairwindsOps/polaris",
    "kube-linter": "stackrox/kube-linter",
    "cherrybomb": "blst-security/cherrybomb",
    "scaphandre": "hubblo-org/scaphandre",
    "deadfinder": "hahwul/deadfinder",
    "comby": "comby-tools/comby",
    "atlas": "ariga/atlas",
    "vale": "errata-ai/vale",
    "redpen": "redpen-cc/redpen",
    "bloaty": "google/bloaty",
    "buf": "bufbuild/buf",
    "dockle": "goodwithtech/dockle",
    "wasm-tools": "bytecodealliance/wasm-tools",
    "globstar": "DeepSourceCorp/globstar",
    "sentrux": "sentrux/sentrux",
}

# package_id overrides -- everything else uses package_id == engine_id.
_PACKAGE_ID_OVERRIDES: Final[dict[str, str]] = {
    "guardrails": "guardrails-ai",
    "scancode": "scancode-toolkit",
    "zap": "zapcli",
    "tsc": "typescript",
    "spectral": "@stoplight/spectral-cli",
    "cdxgen": "@cyclonedx/cdxgen",
    "commitlint": "@commitlint/cli",
    "playwright": "@playwright/test",
    "axe": "@axe-core/cli",
    "graphql-inspector": "@graphql-inspector/cli",
    "depcruise": "dependency-cruiser",
    "biome": "@biomejs/biome",
    "blc": "broken-link-checker",
    "pagespeed": "psi",
    "stryker": "@stryker-mutator/core",
    "backstop": "backstopjs",
    "a11ywatch": "a11ywatch-cli",
    "squoosh": "@squoosh/cli",
    "ast-grep": "@ast-grep/cli",
    "squawk": "squawk-cli",
    "readability": "readability-cli",
    "megalinter": "mega-linter-runner",
    "statoscope": "@statoscope/cli",
    "ncu": "npm-check-updates",
    "cejel": "@cejel/cejel",
    "npm-audit": "node/npm",
    "git-guard": "git",
    "zally": "zalando/zally",
    "infection": "infection/infection",
    "pitest": "org.pitest:pitest-maven",
}

# EngineSpec.binary per engine_id, mirrored here so this registry is fully
# self-contained and does not need to import rush.catalog to build itself.
_ENGINE_BINARIES: Final[dict[str, str]] = {
    "ruff": "ruff",
    "eslint": "eslint",
    "prettier": "prettier",
    "pytest": "pytest",
    "vitest": "vitest",
    "pip-audit": "pip-audit",
    "npm-audit": "npm",
    "osv-scanner": "osv-scanner",
    "mypy": "mypy",
    "tsc": "tsc",
    "vulture": "vulture",
    "knip": "knip",
    "radon": "radon",
    "jscpd": "jscpd",
    "sloppylint": "sloppylint",
    "markdownlint-cli": "markdownlint",
    "actionlint": "actionlint",
    "spectral": "spectral",
    "sqlfluff": "sqlfluff",
    "djlint": "djlint",
    "hadolint": "hadolint",
    "tflint": "tflint",
    "checkov": "checkov",
    "gitleaks": "gitleaks",
    "cdxgen": "cdxgen",
    "commitlint": "commitlint",
    "semantic-drift": "semantic-drift",
    "semgrep": "semgrep",
    "lychee": "lychee",
    "trivy": "trivy",
    "grype": "grype",
    "cosign": "cosign",
    "kubeconform": "kubeconform",
    "playwright": "playwright",
    "axe": "axe",
    "promptfoo": "promptfoo",
    "garak": "garak",
    "deepeval": "deepeval",
    "guardrails": "guardrails",
    "bearer": "bearer",
    "trufflehog": "trufflehog",
    "horusec": "horusec",
    "secretlint": "secretlint",
    "detect-secrets": "detect-secrets",
    "scorecard": "scorecard",
    "scancode": "scancode",
    "slsa-verifier": "slsa-verifier",
    "guac": "guacone",
    "pip-licenses": "pip-licenses",
    "terrascan": "terrascan",
    "kube-score": "kube-score",
    "conftest": "conftest",
    "polaris": "polaris",
    "kube-linter": "kube-linter",
    "schemathesis": "schemathesis",
    "zally": "zally",
    "graphql-inspector": "graphql-inspector",
    "cherrybomb": "cherrybomb",
    "newman": "newman",
    "depcruise": "depcruise",
    "refurb": "refurb",
    "biome": "biome",
    "scaphandre": "scaphandre",
    "fawltydeps": "fawltydeps",
    "ts-prune": "ts-prune",
    "pa11y": "pa11y",
    "html-validate": "html-validate",
    "lighthouse": "lighthouse",
    "zap": "zap-cli",
    "deadfinder": "deadfinder",
    "blc": "blc",
    "pagespeed": "pagespeed-insights",
    "stryker": "stryker",
    "cosmic-ray": "cosmic-ray",
    "infection": "infection",
    "pitest": "mvn",
    "cargo-mutants": "cargo-mutants",
    "lost-pixel": "lost-pixel",
    "backstop": "backstop",
    "stylelint": "stylelint",
    "a11ywatch": "a11ywatch",
    "squoosh": "squoosh-cli",
    "critical": "critical",
    "font-spider": "font-spider",
    "ast-grep": "ast-grep",
    "flake8-bugbear": "flake8",
    "megalinter": "megalinter",
    "comby": "comby",
    "atlas": "atlas",
    "squawk": "squawk",
    "prisma-lint": "prisma-lint",
    "vale": "vale",
    "cspell": "cspell",
    "alex": "alex",
    "readability": "readability-cli",
    "redpen": "redpen",
    "no-jargon": "no-jargon",
    "markdown-unfluff": "markdown-unfluff",
    "memray": "memray",
    "statoscope": "statoscope",
    "bloaty": "bloaty",
    "buf": "buf",
    "dockle": "dockle",
    "wasm-tools": "wasm-tools",
    "pyclean": "pyclean",
    "diff-cover": "diff-cover",
    "git-guard": "git",
    "semantic-release": "semantic-release",
    "pr-agent": "pr-agent",
    "safe-env": "safe-env",
    "wait-on": "wait-on",
    "ncu": "ncu",
    "aislop": "aislop",
    "tach": "tach",
    "undercover": "undercover",
    "medusa": "medusa",
    "pyrefly": "pyrefly",
    "globstar": "globstar",
    "clines": "clines",
    "cejel": "cejel",
    "sentrux": "sentrux",
}

_SOURCE_MANAGER: Final[dict[EngineSource, str]] = {
    "pypi": "uv",
    "npm": "npm",
    "crates": "cargo",
    "gem": "gem",
    "composer": "composer",
    "maven": "maven",
    "go": "go",
    "github": "github",
    "alias": "alias",
    "internal": "internal",
}

_SOURCE_PREREQUISITES: Final[dict[EngineSource, tuple[str, ...]]] = {
    "pypi": ("uv", "python"),
    "npm": ("node", "npm"),
    "crates": ("rust", "cargo"),
    "gem": ("ruby",),
    "composer": ("php", "composer"),
    "maven": ("jvm", "maven"),
    "go": ("go",),
    "github": (),
    "alias": (),
    "internal": (),
}


def _classify(engine_id: str) -> EngineSource:
    if engine_id in _PYPI_ENGINES:
        return "pypi"
    if engine_id in _NPM_ENGINES:
        return "npm"
    if engine_id in _CRATES_ENGINES:
        return "crates"
    if engine_id in _GEM_ENGINES:
        return "gem"
    if engine_id in _COMPOSER_ENGINES:
        return "composer"
    if engine_id in _MAVEN_ENGINES:
        return "maven"
    if engine_id in _GO_SOURCE_ENGINES:
        return "go"
    if engine_id in _ALIAS_ENGINES:
        return "alias"
    if engine_id in _INTERNAL_ENGINES:
        return "internal"
    if engine_id in _GITHUB_REPOS:
        return "github"
    raise UnknownEngineError(engine_id)


def _package_id(engine_id: str, source: EngineSource) -> str:
    if engine_id in _PACKAGE_ID_OVERRIDES:
        return _PACKAGE_ID_OVERRIDES[engine_id]
    if source == "github":
        return _GITHUB_REPOS[engine_id]
    return engine_id


def _prerequisites(engine_id: str, source: EngineSource) -> tuple[str, ...]:
    if engine_id == "npm-audit":
        return ("node", "npm")
    if engine_id == "git-guard":
        return ("git",)
    if engine_id == "semantic-drift":
        return ()
    return _SOURCE_PREREQUISITES[source]


def _version_policy(engine_id: str, source: EngineSource) -> str:
    if engine_id == "zally":
        return "pinned:v2.1.1"
    if source == "maven":
        return "project_locked"
    if source == "internal":
        return "n/a"
    return "latest_stable"


def _scan_class(engine_id: str, source: EngineSource) -> str:
    if source == "maven":
        return "project_bound"
    if source == "internal":
        return "target_adapter"
    return "standalone"


def _probe(engine_id: str, binary: str, source: EngineSource) -> tuple[str, ...]:
    if source == "internal":
        return ()
    if engine_id == "pitest":
        return (binary, "--version")
    return (binary, "--version")


def _build_engine_packages() -> dict[str, EnginePackage]:
    packages: dict[str, EnginePackage] = {}
    for engine_id, binary in _ENGINE_BINARIES.items():
        source = _classify(engine_id)
        packages[engine_id] = EnginePackage(
            engine_id=engine_id,
            package_id=_package_id(engine_id, source),
            source=source,
            manager=_SOURCE_MANAGER[source],
            binary=binary,
            version_policy=_version_policy(engine_id, source),
            platform_policy="native_exact",
            scan_class=_scan_class(engine_id, source),
            prerequisites=_prerequisites(engine_id, source),
            probe=_probe(engine_id, binary, source),
        )
    return packages


ENGINE_PACKAGES: Final[dict[str, EnginePackage]] = _build_engine_packages()


def resolve_engine_package(engine_id: str) -> EnginePackage:
    """Return the declared package identity for ``engine_id``.

    Raises ``UnknownEngineError`` for any id outside the declared allowlist.
    There is no override mechanism -- arbitrary/unknown package input is
    always rejected here, before any plan or install step is reached.
    """
    try:
        return ENGINE_PACKAGES[engine_id]
    except KeyError:
        raise UnknownEngineError(engine_id) from None


# --- Runtime-only prerequisites (§6.2 paragraph on runtime resolution) -----


@dataclass(frozen=True)
class RuntimePackage:
    """Non-engine runtime/manager prerequisite resolution metadata."""

    runtime_id: str
    description: str
    resolve_source: str
    checksum_required: bool
    managed: bool  # True: Rush installs a private managed copy. False: OS-manager only.


RUNTIME_PACKAGES: Final[dict[str, RuntimePackage]] = {
    "uv": RuntimePackage(
        "uv", "uv package/Python manager", "github:astral-sh/uv releases", True, True
    ),
    "python": RuntimePackage(
        "python", "CPython managed by uv", "uv managed-python catalog", True, True
    ),
    "node": RuntimePackage(
        "node", "Node.js LTS runtime", "https://nodejs.org/dist/index.json", True, True
    ),
    "npm": RuntimePackage(
        "npm", "npm (bundled with Node)", "bundled with node", False, True
    ),
    "rust": RuntimePackage(
        "rust",
        "Rust toolchain",
        "https://static.rust-lang.org/dist/channel-rust-stable.toml",
        True,
        True,
    ),
    "cargo": RuntimePackage(
        "cargo", "Cargo (bundled with Rust)", "bundled with rust", False, True
    ),
    "go": RuntimePackage(
        "go", "Go toolchain", "https://go.dev/dl/?mode=json&include=all", True, True
    ),
    "jvm": RuntimePackage(
        "jvm",
        "Eclipse Adoptium JDK 21",
        "https://api.adoptium.net/v3/assets/latest/21/hotspot",
        True,
        True,
    ),
    "maven": RuntimePackage(
        "maven", "Apache Maven", "apache maven archive (SHA512)", True, True
    ),
    "gradle": RuntimePackage(
        "gradle", "Gradle", "gradle distribution (SHA256)", True, True
    ),
    "php": RuntimePackage("php", "PHP runtime", "os package manager", False, False),
    "ruby": RuntimePackage("ruby", "Ruby runtime", "os package manager", False, False),
    "erlang": RuntimePackage(
        "erlang", "Erlang/OTP runtime", "os package manager", False, False
    ),
    "elixir": RuntimePackage(
        "elixir", "Elixir runtime", "os package manager", False, False
    ),
    "git": RuntimePackage("git", "Git", "os package manager", False, False),
    "playwright-browsers": RuntimePackage(
        "playwright-browsers",
        "Managed Chromium for browser-dependent engines",
        "pinned @playwright/test browser install",
        True,
        True,
    ),
    "composer": RuntimePackage(
        "composer",
        "Composer (PHP dependency manager)",
        "getcomposer.org installer",
        True,
        True,
    ),
    "mix": RuntimePackage(
        "mix", "Mix (bundled with Elixir)", "bundled with elixir", False, True
    ),
}

# OS-manager-only prerequisites (§6.2): exact package names, no substitutes.
OS_PACKAGE_NAMES: Final[dict[str, dict[str, str]]] = {
    "php": {
        "brew": "php",
        "winget": "PHP.PHP.8.4",
        "apt": "php",
        "dnf": "php",
        "apk": "php",
    },
    "ruby": {
        "brew": "ruby",
        "winget": "RubyInstallerTeam.Ruby.3.4",
        "apt": "ruby",
        "dnf": "ruby",
        "apk": "ruby",
    },
    "erlang": {
        "brew": "erlang",
        "winget": "Erlang.ErlangOTP",
        "apt": "erlang-base",
        "dnf": "erlang",
        "apk": "erlang",
    },
    "elixir": {
        "brew": "elixir",
        "winget": "N/A",
        "apt": "elixir",
        "dnf": "elixir",
        "apk": "elixir",
    },
    "git": {
        "brew": "git",
        "winget": "Git.Git",
        "apt": "git",
        "dnf": "git",
        "apk": "git",
    },
}

# --- Project dependency manager commands (§6.2 last paragraph) ------------


@dataclass(frozen=True)
class ProjectManagerCommand:
    """Lockfile-preserving install command for one project dependency manager."""

    manager_id: str
    argv: tuple[str, ...]
    lockfile: str
    isolation_supported: bool
    build_script_grant_required: bool


PROJECT_MANAGER_COMMANDS: Final[dict[str, ProjectManagerCommand]] = {
    "npm": ProjectManagerCommand(
        "npm", ("npm", "ci", "--ignore-scripts"), "package-lock.json", False, True
    ),
    "pnpm": ProjectManagerCommand(
        "pnpm",
        ("pnpm", "install", "--frozen-lockfile", "--ignore-scripts"),
        "pnpm-lock.yaml",
        False,
        True,
    ),
    "yarn-classic": ProjectManagerCommand(
        "yarn-classic",
        ("yarn", "install", "--frozen-lockfile", "--ignore-scripts"),
        "yarn.lock",
        False,
        True,
    ),
    "yarn-berry": ProjectManagerCommand(
        "yarn-berry", ("yarn", "install", "--immutable"), "yarn.lock", False, True
    ),
    "uv": ProjectManagerCommand(
        "uv", ("uv", "sync", "--frozen"), "uv.lock", False, True
    ),
    "poetry": ProjectManagerCommand(
        "poetry", ("poetry", "install", "--sync"), "poetry.lock", False, True
    ),
    "go": ProjectManagerCommand(
        "go", ("go", "mod", "download"), "go.sum", False, False
    ),
    "composer": ProjectManagerCommand(
        "composer",
        ("composer", "install", "--no-interaction", "--no-scripts"),
        "composer.lock",
        True,
        True,
    ),
    "mix": ProjectManagerCommand(
        "mix", ("mix", "deps.get", "--check-locked"), "mix.lock", False, True
    ),
    "maven": ProjectManagerCommand(
        "maven", ("./mvnw", "-B", "verify"), "pom.xml", True, True
    ),
    "gradle": ProjectManagerCommand(
        "gradle", ("./gradlew", "build"), "build.gradle", True, True
    ),
}


def resolve_project_manager_command(manager_id: str) -> ProjectManagerCommand:
    """Return the declared lockfile-preserving command for ``manager_id``.

    Raises ``UnknownProjectManagerError`` for any manager outside the
    declared allowlist -- no arbitrary manager command is ever accepted.
    """
    try:
        return PROJECT_MANAGER_COMMANDS[manager_id]
    except KeyError:
        raise UnknownProjectManagerError(manager_id) from None


__all__ = [
    "ENGINE_PACKAGES",
    "OS_PACKAGE_NAMES",
    "PROJECT_MANAGER_COMMANDS",
    "RUNTIME_PACKAGES",
    "EnginePackage",
    "EngineSource",
    "ProjectManagerCommand",
    "RuntimePackage",
    "UnknownEngineError",
    "UnknownProjectManagerError",
    "resolve_engine_package",
    "resolve_project_manager_command",
]
