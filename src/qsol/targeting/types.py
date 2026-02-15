from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from qsol.diag.diagnostic import Diagnostic

CapabilityStatus = Literal["full", "partial", "none"]


@dataclass(frozen=True, slots=True)
class TargetSelection:
    runtime_id: str
    backend_id: str


@dataclass(frozen=True, slots=True)
class SupportIssue:
    code: str
    message: str
    stage: Literal["resolution", "backend", "runtime", "pair"]
    capability_id: str | None = None
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class SupportReport:
    selection: TargetSelection
    supported: bool
    issues: list[SupportIssue] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    backend_capabilities: dict[str, CapabilityStatus] = field(default_factory=dict)
    runtime_capabilities: dict[str, CapabilityStatus] = field(default_factory=dict)
    model_summary: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CompiledModel:
    kind: str
    backend_id: str
    cqm: Any
    bqm: Any | None
    varmap: dict[str, str]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    stats: dict[str, float | int] = field(default_factory=dict)


@dataclass(slots=True)
class StandardRunResult:
    schema_version: str
    runtime: str
    backend: str
    status: str
    energy: float | None
    reads: int
    best_sample: dict[str, int]
    selected_assignments: list[dict[str, object]]
    timing_ms: float
    capability_report_path: str
    extensions: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeRunOptions:
    params: dict[str, object] = field(default_factory=dict)
    outdir: str | None = None


@dataclass(slots=True)
class CompatibilityResult:
    report: SupportReport
    compiled_model: CompiledModel | None = None
