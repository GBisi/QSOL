from __future__ import annotations

import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Callable, cast

import dimod

from qsol.backend.dimod_codegen import CodegenResult, DimodCodegen
from qsol.backend.export import export_artifacts
from qsol.lower.ir import BackendArtifacts, GroundIR
from qsol.targeting.interfaces import BackendPlugin, PluginBundle, RuntimePlugin
from qsol.targeting.types import (
    CapabilityStatus,
    CompiledModel,
    RuntimeRunOptions,
    StandardRunResult,
    SupportIssue,
    TargetSelection,
)


def _sample_exact(bqm: dimod.BinaryQuadraticModel) -> Any:
    solver_ctor = cast(Callable[[], Any], dimod.ExactSolver)
    solver = solver_ctor()
    sample_fn = cast(Callable[[dimod.BinaryQuadraticModel], Any], solver.sample)
    return sample_fn(bqm)


def _sample_sa(bqm: dimod.BinaryQuadraticModel, sample_kwargs: dict[str, Any]) -> Any:
    sampler_ctor = cast(Callable[[], Any], dimod.SimulatedAnnealingSampler)
    sampler = sampler_ctor()
    sample_fn = cast(Callable[..., Any], sampler.sample)
    supported_params = set(getattr(sampler, "parameters", {}).keys())
    if supported_params:
        filtered_kwargs = {k: v for k, v in sample_kwargs.items() if k in supported_params}
        return sample_fn(bqm, **filtered_kwargs)
    return sample_fn(bqm, **sample_kwargs)


def _is_internal_variable(label: str) -> bool:
    return label.startswith("aux:") or label.startswith("slack:")


def _as_str_option(params: Mapping[str, object], key: str, default: str) -> str:
    raw = params.get(key, default)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"runtime option `{key}` must be a non-empty string")
    return raw


def _as_int_option(params: Mapping[str, object], key: str, default: int) -> int:
    raw = params.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"runtime option `{key}` must be an integer")
    if raw < 1:
        raise ValueError(f"runtime option `{key}` must be >= 1")
    return raw


def _as_optional_int_option(params: Mapping[str, object], key: str) -> int | None:
    raw = params.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"runtime option `{key}` must be an integer when provided")
    return raw


def _as_optional_float_option(params: Mapping[str, object], key: str) -> float | None:
    raw = params.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"runtime option `{key}` must be a number when provided")
    return float(raw)


def _sample_signature(sample: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(sample.items(), key=lambda item: item[0]))


def _selected_assignments_for_sample(
    sample: Mapping[str, int],
    *,
    varmap: Mapping[str, str],
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for label, value in sorted(sample.items(), key=lambda item: item[0]):
        if value != 1:
            continue
        if _is_internal_variable(label):
            continue
        meaning = varmap.get(label)
        if meaning is None:
            continue
        selected.append({"variable": label, "meaning": meaning, "value": value})
    return selected


def _collect_ranked_solutions(
    sampleset: Any,
    *,
    varmap: Mapping[str, str],
    requested_solutions: int,
) -> list[dict[str, object]]:
    aggregated = sampleset.aggregate()
    rows: list[
        tuple[
            float,
            tuple[tuple[str, int], ...],
            int,
            dict[str, int],
            list[dict[str, object]],
        ]
    ] = []
    for record in aggregated.data(fields=["sample", "energy", "num_occurrences"]):
        sample = {str(var): int(value) for var, value in record.sample.items()}
        rows.append(
            (
                float(record.energy),
                _sample_signature(sample),
                int(record.num_occurrences),
                sample,
                _selected_assignments_for_sample(sample, varmap=varmap),
            )
        )

    rows.sort(key=lambda row: (row[0], row[1]))

    ranked: list[dict[str, object]] = []
    for rank, (energy, _signature, occurrences, sample, selected) in enumerate(rows, start=1):
        ranked.append(
            {
                "rank": rank,
                "energy": energy,
                "num_occurrences": occurrences,
                "sample": sample,
                "selected_assignments": selected,
            }
        )
        if len(ranked) >= requested_solutions:
            break
    return ranked


def _evaluate_energy_thresholds(
    *,
    solutions: list[dict[str, object]],
    energy_min: float | None,
    energy_max: float | None,
) -> tuple[bool, list[dict[str, object]]]:
    violations: list[dict[str, object]] = []
    for solution in solutions:
        rank_raw = solution.get("rank")
        if isinstance(rank_raw, bool) or not isinstance(rank_raw, int):
            raise ValueError("runtime solution payload contains invalid `rank` value")
        rank = rank_raw
        energy_raw = solution.get("energy")
        if isinstance(energy_raw, bool) or not isinstance(energy_raw, (int, float)):
            raise ValueError("runtime solution payload contains invalid `energy` value")
        energy = float(energy_raw)
        reasons: list[str] = []
        if energy_min is not None and energy < energy_min:
            reasons.append(f"energy {energy} is lower than minimum {energy_min}")
        if energy_max is not None and energy > energy_max:
            reasons.append(f"energy {energy} is higher than maximum {energy_max}")
        if reasons:
            violations.append({"rank": rank, "energy": energy, "reasons": reasons})
    return len(violations) == 0, violations


@dataclass(slots=True)
class DimodCQMBackendPlugin(BackendPlugin):
    @property
    def plugin_id(self) -> str:
        return "dimod-cqm-v1"

    @property
    def display_name(self) -> str:
        return "dimod CQM backend (v1)"

    def capability_catalog(self) -> Mapping[str, CapabilityStatus]:
        return {
            "unknown.subset.v1": "full",
            "unknown.mapping.v1": "full",
            "unknown.custom.v1": "none",
            "constraint.compare.eq.v1": "full",
            "constraint.compare.ne.v1": "full",
            "constraint.compare.lt.v1": "full",
            "constraint.compare.le.v1": "full",
            "constraint.compare.gt.v1": "full",
            "constraint.compare.ge.v1": "full",
            "constraint.quantifier.forall.v1": "full",
            "constraint.quantifier.exists.v1": "partial",
            "objective.if_then_else.v1": "partial",
            "objective.sum.v1": "full",
            "expression.bool.and.v1": "full",
            "expression.bool.or.v1": "full",
            "expression.bool.implies.v1": "full",
            "expression.bool.not.v1": "full",
        }

    def check_support(
        self, ground: GroundIR, *, required_capabilities: Collection[str]
    ) -> list[SupportIssue]:
        _ = ground
        issues: list[SupportIssue] = []
        catalog = self.capability_catalog()
        for capability_id in sorted(required_capabilities):
            status = catalog.get(capability_id, "none")
            if status == "none":
                issues.append(
                    SupportIssue(
                        code="QSOL4010",
                        message=(
                            f"backend `{self.plugin_id}` does not support required capability "
                            f"`{capability_id}`"
                        ),
                        stage="backend",
                        capability_id=capability_id,
                    )
                )
        return issues

    def compile_model(self, ground: GroundIR) -> CompiledModel:
        codegen = DimodCodegen().compile(ground)
        stats: dict[str, float | int] = {
            "num_variables": int(len(codegen.bqm.variables)),
            "num_interactions": int(len(codegen.bqm.quadratic)),
            "num_constraints": int(len(codegen.cqm.constraints)),
        }
        return CompiledModel(
            kind="cqm",
            backend_id=self.plugin_id,
            cqm=codegen.cqm,
            bqm=codegen.bqm,
            varmap=dict(codegen.varmap),
            diagnostics=list(codegen.diagnostics),
            stats=stats,
        )

    def export_model(
        self,
        compiled_model: CompiledModel,
        *,
        outdir: str,
        output_format: str,
    ) -> BackendArtifacts:
        if compiled_model.bqm is None:
            raise ValueError("compiled model does not include BQM payload")
        codegen_result = CodegenResult(
            cqm=compiled_model.cqm,
            bqm=compiled_model.bqm,
            inverter=None,
            varmap=dict(compiled_model.varmap),
            diagnostics=list(compiled_model.diagnostics),
        )
        return export_artifacts(outdir, output_format, codegen_result)


@dataclass(slots=True)
class LocalDimodRuntimePlugin(RuntimePlugin):
    @property
    def plugin_id(self) -> str:
        return "local-dimod"

    @property
    def display_name(self) -> str:
        return "Local dimod runtime"

    def capability_catalog(self) -> Mapping[str, CapabilityStatus]:
        return {
            "model.kind.cqm.v1": "full",
            "sampler.exact.v1": "full",
            "sampler.simulated-annealing.v1": "full",
        }

    def compatible_backend_ids(self) -> Collection[str]:
        return {"dimod-cqm-v1"}

    def check_support(
        self,
        compiled_model: CompiledModel,
        *,
        selection: TargetSelection,
    ) -> list[SupportIssue]:
        issues: list[SupportIssue] = []
        if selection.backend_id not in self.compatible_backend_ids():
            issues.append(
                SupportIssue(
                    code="QSOL4008",
                    message=(
                        f"runtime `{self.plugin_id}` is incompatible with backend "
                        f"`{selection.backend_id}`"
                    ),
                    stage="pair",
                )
            )

        if compiled_model.kind != "cqm":
            issues.append(
                SupportIssue(
                    code="QSOL4010",
                    message=(
                        f"runtime `{self.plugin_id}` expects `cqm` models, got `{compiled_model.kind}`"
                    ),
                    stage="runtime",
                )
            )

        if compiled_model.bqm is None:
            issues.append(
                SupportIssue(
                    code="QSOL4010",
                    message="runtime requires a BQM view for local sampling",
                    stage="runtime",
                )
            )
        return issues

    def run_model(
        self,
        compiled_model: CompiledModel,
        *,
        selection: TargetSelection,
        run_options: RuntimeRunOptions,
    ) -> StandardRunResult:
        if compiled_model.bqm is None:
            raise ValueError("compiled model does not include BQM payload")

        params = dict(run_options.params)
        sampler = _as_str_option(params, "sampler", "simulated-annealing")
        if sampler not in {"exact", "simulated-annealing"}:
            raise ValueError("runtime option `sampler` must be `exact` or `simulated-annealing`")
        num_reads = _as_int_option(params, "num_reads", 100)
        seed = _as_optional_int_option(params, "seed")
        requested_solutions = _as_int_option(params, "solutions", 1)
        energy_min = _as_optional_float_option(params, "energy_min")
        energy_max = _as_optional_float_option(params, "energy_max")
        if energy_min is not None and energy_max is not None and energy_min > energy_max:
            raise ValueError(
                "runtime options `energy_min` and `energy_max` must satisfy `energy_min <= energy_max`"
            )

        t0 = time.perf_counter()
        if sampler == "exact":
            sampleset = _sample_exact(compiled_model.bqm)
        else:
            sample_kwargs: dict[str, Any] = {"num_reads": num_reads}
            if seed is not None:
                sample_kwargs["seed"] = seed
            sampleset = _sample_sa(compiled_model.bqm, sample_kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        solutions = _collect_ranked_solutions(
            sampleset,
            varmap=compiled_model.varmap,
            requested_solutions=requested_solutions,
        )
        if not solutions:
            raise ValueError("runtime sampler returned no solutions")
        first = solutions[0]
        first_energy_raw = first.get("energy")
        if isinstance(first_energy_raw, bool) or not isinstance(first_energy_raw, (int, float)):
            raise ValueError("runtime solution payload contains invalid best-solution energy")
        first_energy = float(first_energy_raw)
        best_sample = dict(cast(dict[str, int], first["sample"]))
        selected = list(cast(list[dict[str, object]], first["selected_assignments"]))
        threshold_passed, threshold_violations = _evaluate_energy_thresholds(
            solutions=solutions,
            energy_min=energy_min,
            energy_max=energy_max,
        )

        return StandardRunResult(
            schema_version="1.0",
            runtime=selection.runtime_id,
            backend=selection.backend_id,
            status="ok" if threshold_passed else "threshold_failed",
            energy=first_energy,
            reads=int(len(sampleset)),
            best_sample=best_sample,
            selected_assignments=selected,
            timing_ms=elapsed_ms,
            capability_report_path="",
            extensions={
                "runtime_options": params,
                "sampler": sampler,
                "num_reads": num_reads,
                "seed": seed,
                "requested_solutions": requested_solutions,
                "returned_solutions": len(solutions),
                "solutions": solutions,
                "energy_threshold": {
                    "min": energy_min,
                    "max": energy_max,
                    "scope": "all_returned",
                    "inclusive": True,
                    "passed": threshold_passed,
                    "violations": threshold_violations,
                },
            },
        )


def builtin_plugin_bundle() -> PluginBundle:
    return PluginBundle(
        backends=(DimodCQMBackendPlugin(),),
        runtimes=(LocalDimodRuntimePlugin(),),
    )
