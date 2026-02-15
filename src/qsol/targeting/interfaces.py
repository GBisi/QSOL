from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from qsol.lower.ir import BackendArtifacts, GroundIR
from qsol.targeting.types import (
    CapabilityStatus,
    CompiledModel,
    RuntimeRunOptions,
    StandardRunResult,
    SupportIssue,
    TargetSelection,
)


class BackendPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    def capability_catalog(self) -> Mapping[str, CapabilityStatus]: ...

    def check_support(
        self, ground: GroundIR, *, required_capabilities: Collection[str]
    ) -> list[SupportIssue]: ...

    def compile_model(self, ground: GroundIR) -> CompiledModel: ...

    def export_model(
        self,
        compiled_model: CompiledModel,
        *,
        outdir: str,
        output_format: str,
    ) -> BackendArtifacts: ...


class RuntimePlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    def capability_catalog(self) -> Mapping[str, CapabilityStatus]: ...

    def compatible_backend_ids(self) -> Collection[str]: ...

    def check_support(
        self,
        compiled_model: CompiledModel,
        *,
        selection: TargetSelection,
    ) -> list[SupportIssue]: ...

    def run_model(
        self,
        compiled_model: CompiledModel,
        *,
        selection: TargetSelection,
        run_options: RuntimeRunOptions,
    ) -> StandardRunResult: ...


@dataclass(slots=True)
class PluginBundle:
    backends: Sequence[BackendPlugin] = field(default_factory=tuple)
    runtimes: Sequence[RuntimePlugin] = field(default_factory=tuple)
