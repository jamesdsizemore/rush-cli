"""Engine registry — single source of truth for engine lookup.

Architecture §4.2. Used by tools/common.py:run_engine() to find engines
by name. Adding a new engine = add it here AND to ENGINES.
"""

from __future__ import annotations

from .a11ywatch import A11ywatchEngine
from .actionlint import ActionlintEngine
from .aislop import AislopEngine
from .alex import AlexEngine
from .ast_grep import AstGrepEngine
from .atlas import AtlasEngine
from .axe import AxeEngine
from .backstop import BackstopEngine
from .base import Engine
from .bearer import BearerEngine
from .biome import BiomeEngine
from .blc import BlcEngine
from .bloaty import BloatyEngine
from .buf import BufEngine
from .cargo_mutants import CargoMutantsEngine
from .cdxgen import CdxgenEngine
from .cejel import CejelEngine
from .checkov import CheckovEngine
from .cherrybomb import CherrybombEngine
from .clines import ClinesEngine
from .comby import CombyEngine
from .commitlint import CommitlintEngine
from .conftest import ConftestEngine
from .cosign import CosignEngine
from .cosmic_ray import CosmicRayEngine
from .critical import CriticalEngine
from .cspell import CspellEngine
from .deadfinder import DeadfinderEngine
from .deepeval import DeepevalEngine
from .depcruise import DepcruiseEngine
from .detect_secrets import DetectSecretsEngine
from .diff_cover import DiffCoverEngine
from .djlint import DjlintEngine
from .dockle import DockleEngine
from .eslint import EslintEngine
from .fawltydeps import FawltydepsEngine
from .flake8_bugbear import Flake8BugbearEngine
from .font_spider import FontSpiderEngine
from .garak import GarakEngine
from .git_guard import GitGuardEngine
from .gitleaks import GitleaksEngine
from .globstar import GlobstarEngine
from .graphql_inspector import GraphQLInspectorEngine
from .grype import GrypeEngine
from .guac import GuacEngine
from .guardrails import GuardrailsEngine
from .hadolint import HadolintEngine
from .horusec import HorusecEngine
from .html_validate import HtmlValidateEngine
from .infection import InfectionEngine
from .jscpd import JscpdEngine
from .knip import KnipEngine
from .kube_linter import KubeLinterEngine
from .kube_score import KubeScoreEngine
from .kubeconform import KubeconformEngine
from .lighthouse import LighthouseEngine
from .lost_pixel import LostPixelEngine
from .lychee import LycheeEngine
from .markdown_unfluff import MarkdownUnfluffEngine
from .markdownlint import MarkdownlintEngine
from .medusa import MedusaEngine
from .megalinter import MegalinterEngine
from .memray import MemrayEngine
from .mypy import MypyEngine
from .ncu import NcuEngine
from .newman import NewmanEngine
from .no_jargon import NoJargonEngine
from .npm_audit import NpmAuditEngine
from .osv import OsvScannerEngine
from .pa11y import Pa11yEngine
from .pagespeed import PagespeedEngine
from .pip_audit import PipAuditEngine
from .pip_licenses import PipLicensesEngine
from .pitest import PitestEngine
from .playwright import PlaywrightEngine
from .polaris import PolarisEngine
from .pr_agent import PrAgentEngine
from .prettier import PrettierEngine
from .prisma_lint import PrismaLintEngine
from .promptfoo import PromptfooEngine
from .pyclean import PycleanEngine
from .pyrefly import PyreflyEngine
from .pytest import PytestEngine
from .radon import RadonEngine
from .readability import ReadabilityEngine
from .redpen import RedpenEngine
from .refurb import RefurbEngine
from .ruff import RuffEngine
from .safe_env import SafeEnvEngine
from .scancode import ScancodeEngine
from .scaphandre import ScaphandreEngine
from .schemathesis import SchemathesisEngine
from .scorecard import ScorecardEngine
from .secretlint import SecretlintEngine
from .semantic_drift import SemanticDriftEngine
from .semantic_release import SemanticReleaseEngine
from .semgrep import SemgrepEngine
from .sentrux import SentruxEngine
from .sloppylint import SloppylintEngine
from .slsa_verifier import SlsaVerifierEngine
from .spectral import SpectralEngine
from .sqlfluff import SqlfluffEngine
from .squawk import SquawkEngine
from .squoosh import SquooshEngine
from .statoscope import StatoscopeEngine
from .stryker import StrykerEngine
from .stylelint import StylelintEngine
from .tach import TachEngine
from .terrascan import TerrascanEngine
from .tflint import TflintEngine
from .trivy import TrivyEngine
from .trufflehog import TruffleHogEngine
from .ts_prune import TsPruneEngine
from .tsc import TscEngine
from .undercover import UndercoverEngine
from .vale import ValeEngine
from .vitest import VitestEngine
from .vulture import VultureEngine
from .wait_on import WaitOnEngine
from .wasm_tools import WasmToolsEngine
from .zally import ZallyEngine
from .zap import ZapEngine

ENGINES: dict[str, Engine] = {
    "ruff": RuffEngine(),
    "eslint": EslintEngine(),
    "prettier": PrettierEngine(),
    "vitest": VitestEngine(),
    "pytest": PytestEngine(),
    "pip-audit": PipAuditEngine(),
    "npm-audit": NpmAuditEngine(),
    "osv-scanner": OsvScannerEngine(),
    "mypy": MypyEngine(),
    "tsc": TscEngine(),
    "vulture": VultureEngine(),
    "knip": KnipEngine(),
    "radon": RadonEngine(),
    "jscpd": JscpdEngine(),
    "sloppylint": SloppylintEngine(),
    "markdownlint-cli": MarkdownlintEngine(),
    "actionlint": ActionlintEngine(),
    "spectral": SpectralEngine(),
    "sqlfluff": SqlfluffEngine(),
    "djlint": DjlintEngine(),
    "hadolint": HadolintEngine(),
    "tflint": TflintEngine(),
    "checkov": CheckovEngine(),
    "commitlint": CommitlintEngine(),
    "gitleaks": GitleaksEngine(),
    "cdxgen": CdxgenEngine(),
    "semantic-drift": SemanticDriftEngine(),
    "semgrep": SemgrepEngine(),
    "lychee": LycheeEngine(),
    "trivy": TrivyEngine(),
    "grype": GrypeEngine(),
    "cosign": CosignEngine(),
    "kubeconform": KubeconformEngine(),
    "playwright": PlaywrightEngine(),
    "axe": AxeEngine(),
    # Phase 09
    "promptfoo": PromptfooEngine(),
    "garak": GarakEngine(),
    "deepeval": DeepevalEngine(),
    "guardrails": GuardrailsEngine(),
    # Phase 10
    "bearer": BearerEngine(),
    "trufflehog": TruffleHogEngine(),
    "horusec": HorusecEngine(),
    "secretlint": SecretlintEngine(),
    "detect-secrets": DetectSecretsEngine(),
    # Phase 11
    "scorecard": ScorecardEngine(),
    "scancode": ScancodeEngine(),
    "slsa-verifier": SlsaVerifierEngine(),
    "guac": GuacEngine(),
    "pip-licenses": PipLicensesEngine(),
    # Phase 12
    "terrascan": TerrascanEngine(),
    "kube-score": KubeScoreEngine(),
    "conftest": ConftestEngine(),
    "polaris": PolarisEngine(),
    "kube-linter": KubeLinterEngine(),
    # Phase 13
    "schemathesis": SchemathesisEngine(),
    "zally": ZallyEngine(),
    "graphql-inspector": GraphQLInspectorEngine(),
    "cherrybomb": CherrybombEngine(),
    "newman": NewmanEngine(),
    # Phase 14
    "depcruise": DepcruiseEngine(),
    "refurb": RefurbEngine(),
    "biome": BiomeEngine(),
    "scaphandre": ScaphandreEngine(),
    "fawltydeps": FawltydepsEngine(),
    "ts-prune": TsPruneEngine(),
    # Phase 15
    "pa11y": Pa11yEngine(),
    "html-validate": HtmlValidateEngine(),
    "lighthouse": LighthouseEngine(),
    "zap": ZapEngine(),
    "deadfinder": DeadfinderEngine(),
    "blc": BlcEngine(),
    "pagespeed": PagespeedEngine(),
    # Phase 16
    "stryker": StrykerEngine(),
    "cosmic-ray": CosmicRayEngine(),
    "infection": InfectionEngine(),
    "pitest": PitestEngine(),
    "cargo-mutants": CargoMutantsEngine(),
    # Phase 17
    "lost-pixel": LostPixelEngine(),
    "backstop": BackstopEngine(),
    "stylelint": StylelintEngine(),
    "a11ywatch": A11ywatchEngine(),
    "squoosh": SquooshEngine(),
    "critical": CriticalEngine(),
    "font-spider": FontSpiderEngine(),
    # Phase 18
    "ast-grep": AstGrepEngine(),
    "flake8-bugbear": Flake8BugbearEngine(),
    "megalinter": MegalinterEngine(),
    "comby": CombyEngine(),
    "atlas": AtlasEngine(),
    "squawk": SquawkEngine(),
    "prisma-lint": PrismaLintEngine(),
    # Phase 19
    "vale": ValeEngine(),
    "cspell": CspellEngine(),
    "alex": AlexEngine(),
    "readability": ReadabilityEngine(),
    "redpen": RedpenEngine(),
    "no-jargon": NoJargonEngine(),
    "markdown-unfluff": MarkdownUnfluffEngine(),
    "memray": MemrayEngine(),
    "statoscope": StatoscopeEngine(),
    "bloaty": BloatyEngine(),
    "buf": BufEngine(),
    "dockle": DockleEngine(),
    "wasm-tools": WasmToolsEngine(),
    "pyclean": PycleanEngine(),
    "diff-cover": DiffCoverEngine(),
    "git-guard": GitGuardEngine(),
    "semantic-release": SemanticReleaseEngine(),
    "pr-agent": PrAgentEngine(),
    "safe-env": SafeEnvEngine(),
    "wait-on": WaitOnEngine(),
    "ncu": NcuEngine(),
    # Innovation Extensions (CLAW Top-3)
    "aislop": AislopEngine(),
    "tach": TachEngine(),
    "undercover": UndercoverEngine(),
    "medusa": MedusaEngine(),
    "pyrefly": PyreflyEngine(),
    "globstar": GlobstarEngine(),
    "clines": ClinesEngine(),
    "cejel": CejelEngine(),
    "sentrux": SentruxEngine(),
}

__all__ = ["ENGINES", "Engine"]
