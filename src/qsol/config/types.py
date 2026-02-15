from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SelectionMode(str, Enum):
    default = "default"
    all = "all"
    subset = "subset"


class CombineMode(str, Enum):
    intersection = "intersection"
    union = "union"


class FailurePolicy(str, Enum):
    run_all_fail = "run-all-fail"
    fail_fast = "fail-fast"
    best_effort = "best-effort"


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    runtime: str | None = None
    backend: str | None = None
    plugins: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SolveConfig:
    solutions: int | None = None
    energy_min: float | None = None
    energy_max: float | None = None


@dataclass(frozen=True, slots=True)
class SolveSettings:
    solutions: int
    energy_min: float | None = None
    energy_max: float | None = None


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    problem: str | None = None
    sets: dict[str, object] = field(default_factory=dict)
    params: dict[str, object] = field(default_factory=dict)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    solve: SolveConfig = field(default_factory=SolveConfig)


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    mode: SelectionMode = SelectionMode.default
    default_scenario: str | None = None
    subset: tuple[str, ...] = ()
    combine_mode: CombineMode | None = None
    failure_policy: FailurePolicy | None = None


@dataclass(frozen=True, slots=True)
class DefaultsConfig:
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    solve: SolveConfig = field(default_factory=SolveConfig)


@dataclass(frozen=True, slots=True)
class QsolConfig:
    schema_version: str
    selection: SelectionConfig = field(default_factory=SelectionConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    scenarios: dict[str, ScenarioConfig] = field(default_factory=dict)
