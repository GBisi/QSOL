from qsol.targeting.compatibility import check_pair_support, extract_required_capabilities
from qsol.targeting.interfaces import BackendPlugin, PluginBundle, RuntimePlugin
from qsol.targeting.registry import PluginRegistry
from qsol.targeting.resolution import SelectionResolution, resolve_target_selection
from qsol.targeting.types import (
    CapabilityStatus,
    CompatibilityResult,
    CompiledModel,
    RuntimeRunOptions,
    StandardRunResult,
    SupportIssue,
    SupportReport,
    TargetSelection,
)

__all__ = [
    "BackendPlugin",
    "CapabilityStatus",
    "CompatibilityResult",
    "CompiledModel",
    "PluginBundle",
    "PluginRegistry",
    "RuntimePlugin",
    "RuntimeRunOptions",
    "SelectionResolution",
    "StandardRunResult",
    "SupportIssue",
    "SupportReport",
    "TargetSelection",
    "check_pair_support",
    "extract_required_capabilities",
    "resolve_target_selection",
]
