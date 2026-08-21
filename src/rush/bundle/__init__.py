"""Frontend Asset & Bundle Optimization Engine."""

from __future__ import annotations

from rush.bundle.barrel_auditor import BarrelImportAuditor
from rush.bundle.budget_gate import BudgetViolation, PerformanceBudgetGate
from rush.bundle.chunk_calculator import BundleChunkCalculator, ChunkSizeReport
from rush.bundle.code_splitting import CodeSplittingValidator
from rush.bundle.css_duplication import CssDuplicationScanner
from rush.bundle.dead_assets import OrphanedAssetScanner
from rush.bundle.polyfill_auditor import PolyfillAuditor

__all__ = [
    "BarrelImportAuditor",
    "BudgetViolation",
    "BundleChunkCalculator",
    "ChunkSizeReport",
    "CodeSplittingValidator",
    "CssDuplicationScanner",
    "OrphanedAssetScanner",
    "PerformanceBudgetGate",
    "PolyfillAuditor",
]
