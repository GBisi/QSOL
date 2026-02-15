from __future__ import annotations

import importlib.util
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
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


def _as_non_negative_int_option(params: Mapping[str, object], key: str, default: int) -> int:
    raw = params.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"runtime option `{key}` must be an integer")
    if raw < 0:
        raise ValueError(f"runtime option `{key}` must be >= 0")
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


def _probe_qiskit_core_dependencies() -> tuple[bool, list[str]]:  # pragma: no cover
    required_modules = {
        "qiskit": "qiskit",
        "qiskit_optimization": "qiskit-optimization",
        "qiskit_algorithms": "qiskit-algorithms",
    }
    missing = [
        package
        for module_name, package in required_modules.items()
        if importlib.util.find_spec(module_name) is None
    ]
    return len(missing) == 0, missing


def _probe_qiskit_qaoa_dependencies() -> tuple[bool, list[str]]:  # pragma: no cover
    required_modules = {
        "qiskit_ibm_runtime": "qiskit-ibm-runtime",
    }
    missing = [
        package
        for module_name, package in required_modules.items()
        if importlib.util.find_spec(module_name) is None
    ]
    return len(missing) == 0, missing


@dataclass(slots=True)
class _QiskitSolvePayload:  # pragma: no cover
    algorithm: str
    reads: int
    solutions: list[dict[str, object]]
    fake_backend: str | None = None
    openqasm_path: str | None = None


def _to_binary_sample(  # pragma: no cover
    vector: object, *, variable_names: list[str]
) -> dict[str, int]:
    try:
        raw_values = list(cast(Any, vector))
    except TypeError as exc:
        raise ValueError("qiskit solution vector is not iterable") from exc

    if len(raw_values) != len(variable_names):
        raise ValueError("qiskit solution vector length does not match variable names")

    sample: dict[str, int] = {}
    for idx, name in enumerate(variable_names):
        value = raw_values[idx]
        if isinstance(value, bool):
            sample[name] = int(value)
            continue
        if not isinstance(value, (int, float)):
            raise ValueError("qiskit solution vector contains non-numeric values")
        sample[name] = 1 if float(value) >= 0.5 else 0
    return sample


def _collect_qiskit_ranked_solutions(  # pragma: no cover
    *,
    result: Any,
    variable_names: list[str],
    varmap: Mapping[str, str],
    requested_solutions: int,
) -> list[dict[str, object]]:
    rows: list[
        tuple[
            float,
            tuple[tuple[str, int], ...],
            dict[str, int],
            list[dict[str, object]],
            float,
            str,
        ]
    ] = []

    raw_samples_obj = getattr(result, "samples", None)
    raw_samples: list[Any] = []
    if raw_samples_obj is not None:
        try:
            raw_samples = list(cast(Any, raw_samples_obj))
        except TypeError:
            raw_samples = []

    for sample_obj in raw_samples:
        vector = getattr(sample_obj, "x", None)
        if vector is None:
            continue
        energy_raw = getattr(sample_obj, "fval", None)
        if isinstance(energy_raw, bool) or not isinstance(energy_raw, (int, float)):
            continue
        status_obj = getattr(sample_obj, "status", None)
        status_name = str(getattr(status_obj, "name", status_obj or ""))
        probability_raw = getattr(sample_obj, "probability", 0.0)
        probability = (
            float(probability_raw)
            if isinstance(probability_raw, (int, float)) and not isinstance(probability_raw, bool)
            else 0.0
        )
        try:
            sample = _to_binary_sample(vector, variable_names=variable_names)
        except ValueError:
            continue
        rows.append(
            (
                float(energy_raw),
                _sample_signature(sample),
                sample,
                _selected_assignments_for_sample(sample, varmap=varmap),
                probability,
                status_name,
            )
        )

    success_rows = [row for row in rows if row[5] == "SUCCESS"]
    if success_rows:
        rows = success_rows

    if not rows:
        best_vector = getattr(result, "x", None)
        best_energy_raw = getattr(result, "fval", None)
        if best_vector is None:
            raise ValueError("qiskit optimizer returned no solutions")
        if isinstance(best_energy_raw, bool) or not isinstance(best_energy_raw, (int, float)):
            raise ValueError("qiskit optimizer returned invalid best solution energy")
        sample = _to_binary_sample(best_vector, variable_names=variable_names)
        rows = [
            (
                float(best_energy_raw),
                _sample_signature(sample),
                sample,
                _selected_assignments_for_sample(sample, varmap=varmap),
                1.0,
                "SUCCESS",
            )
        ]

    aggregated: dict[tuple[tuple[str, int], ...], dict[str, object]] = {}
    for energy, signature, sample, selected, probability, status_name in rows:
        entry = aggregated.get(signature)
        if entry is None:
            aggregated[signature] = {
                "energy": energy,
                "signature": signature,
                "sample": sample,
                "selected_assignments": selected,
                "probability": probability,
                "status": status_name,
            }
            continue
        prev_prob_raw = entry.get("probability", 0.0)
        prev_prob = float(prev_prob_raw) if isinstance(prev_prob_raw, (int, float)) else 0.0
        entry["probability"] = prev_prob + probability
        prev_energy_raw = entry.get("energy", energy)
        prev_energy = (
            float(prev_energy_raw) if isinstance(prev_energy_raw, (int, float)) else energy
        )
        if energy < prev_energy:
            entry["energy"] = energy
            entry["sample"] = sample
            entry["selected_assignments"] = selected
            entry["status"] = status_name

    ordered = sorted(
        aggregated.values(),
        key=lambda row: (
            float(cast(float, row["energy"])),
            cast(tuple[tuple[str, int], ...], row["signature"]),
        ),
    )

    ranked: list[dict[str, object]] = []
    for rank, row in enumerate(ordered, start=1):
        ranked.append(
            {
                "rank": rank,
                "energy": float(cast(float, row["energy"])),
                "sample": dict(cast(dict[str, int], row["sample"])),
                "selected_assignments": list(
                    cast(list[dict[str, object]], row["selected_assignments"])
                ),
                "probability": float(cast(float, row["probability"])),
                "status": str(row["status"]),
            }
        )
        if len(ranked) >= requested_solutions:
            break
    return ranked


def _build_quadratic_program_from_bqm(  # pragma: no cover
    bqm: dimod.BinaryQuadraticModel,
) -> tuple[Any, list[str]]:
    qiskit_optimization = import_module("qiskit_optimization")
    qp = qiskit_optimization.QuadraticProgram(name="qsol")

    variable_names = [str(var) for var in bqm.variables]
    for name in variable_names:
        qp.binary_var(name=name)

    qubo, offset = bqm.to_qubo()
    linear: dict[str, float] = {}
    quadratic: dict[tuple[str, str], float] = {}
    for (u_raw, v_raw), bias_raw in qubo.items():
        u = str(u_raw)
        v = str(v_raw)
        bias = float(bias_raw)
        if u == v:
            linear[u] = linear.get(u, 0.0) + bias
            continue
        key = (u, v) if u <= v else (v, u)
        quadratic[key] = quadratic.get(key, 0.0) + bias

    qp.minimize(constant=float(offset), linear=linear, quadratic=quadratic)
    return qp, variable_names


def _resolve_qaoa_class() -> Any:  # pragma: no cover
    for module_name in ("qiskit_optimization.minimum_eigensolvers", "qiskit_algorithms"):
        try:
            module = import_module(module_name)
        except Exception:
            continue
        qaoa_cls = getattr(module, "QAOA", None)
        if qaoa_cls is not None:
            return qaoa_cls
    raise RuntimeError("failed to import QAOA class from qiskit-optimization or qiskit-algorithms")


def _build_numpy_minimum_eigensolver() -> Any:  # pragma: no cover
    for module_name in ("qiskit_optimization.minimum_eigensolvers", "qiskit_algorithms"):
        try:
            module = import_module(module_name)
        except Exception:
            continue
        solver_cls = getattr(module, "NumPyMinimumEigensolver", None)
        if solver_cls is not None:
            return solver_cls()
    raise RuntimeError(
        "failed to import NumPyMinimumEigensolver from qiskit-optimization or qiskit-algorithms"
    )


def _build_minimum_eigen_optimizer(minimum_eigensolver: Any) -> Any:  # pragma: no cover
    qiskit_optimization_algorithms = import_module("qiskit_optimization.algorithms")
    return qiskit_optimization_algorithms.MinimumEigenOptimizer(minimum_eigensolver)


def _load_fake_backend(fake_backend_name: str) -> Any:  # pragma: no cover
    provider = import_module("qiskit_ibm_runtime.fake_provider")
    backend_cls = getattr(provider, fake_backend_name, None)
    if backend_cls is None:
        available = sorted(name for name in dir(provider) if name.startswith("Fake"))
        preview = ", ".join(available[:12])
        more = "" if len(available) <= 12 else ", ..."
        raise ValueError(f"unknown fake backend `{fake_backend_name}`; available: {preview}{more}")
    return backend_cls()


def _build_pass_manager(backend: Any, optimization_level: int) -> Any | None:  # pragma: no cover
    try:
        preset_passmanagers = import_module("qiskit.transpiler.preset_passmanagers")
        return preset_passmanagers.generate_preset_pass_manager(
            backend=backend, optimization_level=optimization_level
        )
    except Exception:
        return None


def _build_qaoa_sampler(  # pragma: no cover
    *, backend: Any, shots: int, seed: int | None
) -> Any:
    sampler_errors: list[str] = []

    try:
        runtime_mod = import_module("qiskit_ibm_runtime")
        kwargs: dict[str, object] = {"mode": backend}
        options: dict[str, object] = {"default_shots": shots}
        if seed is not None:
            options["seed_simulator"] = seed
        kwargs["options"] = options
        return runtime_mod.SamplerV2(**kwargs)
    except Exception as exc:  # pragma: no cover - depends on qiskit runtime versions
        sampler_errors.append(str(exc))

    try:
        primitives_mod = import_module("qiskit.primitives")
        kwargs = {"backend": backend}
        options = {"default_shots": shots}
        if seed is not None:
            options["seed_simulator"] = seed
        return primitives_mod.BackendSamplerV2(**kwargs, options=options)
    except Exception as exc:  # pragma: no cover - depends on qiskit runtime versions
        sampler_errors.append(str(exc))

    try:
        aer_primitives = import_module("qiskit_aer.primitives")
        kwargs = {"default_shots": shots}
        if seed is not None:
            kwargs["seed"] = seed
        return aer_primitives.SamplerV2(**kwargs)
    except Exception as exc:  # pragma: no cover - depends on qiskit runtime versions
        sampler_errors.append(str(exc))

    raise RuntimeError(
        "failed to initialize a QAOA sampler for fake backend execution: "
        + " | ".join(sampler_errors)
    )


def _instantiate_qaoa(  # pragma: no cover
    *,
    sampler: Any,
    reps: int,
    maxiter: int,
    pass_manager: Any | None,
) -> Any:
    qaoa_cls = _resolve_qaoa_class()
    optimizers_mod = import_module("qiskit_algorithms.optimizers")
    optimizer = optimizers_mod.COBYLA(maxiter=maxiter)

    attempts = [
        {
            "sampler": sampler,
            "optimizer": optimizer,
            "reps": reps,
            "transpiler": pass_manager,
            "transpiler_options": {},
        },
        {
            "sampler": sampler,
            "optimizer": optimizer,
            "reps": reps,
            "transpiler": pass_manager,
        },
        {
            "sampler": sampler,
            "optimizer": optimizer,
            "reps": reps,
        },
    ]

    last_exc: Exception | None = None
    for kwargs in attempts:
        if kwargs.get("transpiler") is None:
            kwargs = {
                k: v for k, v in kwargs.items() if k not in {"transpiler", "transpiler_options"}
            }
        try:
            return qaoa_cls(**kwargs)
        except TypeError as exc:
            last_exc = exc
            continue

    if last_exc is None:
        raise RuntimeError("failed to instantiate QAOA solver")
    raise RuntimeError(f"failed to instantiate QAOA solver: {last_exc}") from last_exc


def _write_openqasm3_for_qaoa(  # pragma: no cover
    *,
    outdir: str,
    qaoa_solver: Any,
    optimization_result: Any,
    pass_manager: Any | None,
) -> str:
    ansatz = getattr(qaoa_solver, "ansatz", None)
    if ansatz is None:
        raise RuntimeError("QAOA solver did not expose an ansatz circuit for OpenQASM export")

    circuit = ansatz
    min_eigen_result = getattr(optimization_result, "min_eigen_solver_result", None)
    optimal_point = getattr(min_eigen_result, "optimal_point", None)
    if optimal_point is not None:
        try:
            circuit = ansatz.assign_parameters(optimal_point, inplace=False)
        except Exception:
            circuit = ansatz

    if pass_manager is not None:
        try:
            circuit = pass_manager.run(circuit)
        except Exception:
            pass

    qasm3_mod = import_module("qiskit.qasm3")
    qasm_text = str(qasm3_mod.dumps(circuit))

    qasm_path = Path(outdir) / "qaoa.qasm"
    qasm_path.parent.mkdir(parents=True, exist_ok=True)
    qasm_path.write_text(qasm_text, encoding="utf-8")
    return str(qasm_path)


def _run_qiskit_solver(  # pragma: no cover
    *,
    bqm: dimod.BinaryQuadraticModel,
    varmap: Mapping[str, str],
    algorithm: str,
    requested_solutions: int,
    fake_backend: str,
    reps: int,
    maxiter: int,
    shots: int,
    seed: int | None,
    optimization_level: int,
    outdir: str | None,
) -> _QiskitSolvePayload:
    qp, variable_names = _build_quadratic_program_from_bqm(bqm)

    if algorithm == "numpy":
        minimum_eigensolver = _build_numpy_minimum_eigensolver()
        optimizer = _build_minimum_eigen_optimizer(minimum_eigensolver)
        result = optimizer.solve(qp)
        solutions = _collect_qiskit_ranked_solutions(
            result=result,
            variable_names=variable_names,
            varmap=varmap,
            requested_solutions=requested_solutions,
        )
        return _QiskitSolvePayload(
            algorithm=algorithm,
            reads=1,
            solutions=solutions,
        )

    qaoa_ready, qaoa_missing = _probe_qiskit_qaoa_dependencies()
    if not qaoa_ready:
        joined = ", ".join(sorted(qaoa_missing))
        raise RuntimeError(
            "qaoa execution requires optional dependency: "
            f"{joined}; install with `uv sync --extra qiskit`"
        )

    backend = _load_fake_backend(fake_backend)
    pass_manager = _build_pass_manager(backend, optimization_level)
    sampler = _build_qaoa_sampler(backend=backend, shots=shots, seed=seed)
    qaoa_solver = _instantiate_qaoa(
        sampler=sampler,
        reps=reps,
        maxiter=maxiter,
        pass_manager=pass_manager,
    )
    optimizer = _build_minimum_eigen_optimizer(qaoa_solver)
    result = optimizer.solve(qp)
    solutions = _collect_qiskit_ranked_solutions(
        result=result,
        variable_names=variable_names,
        varmap=varmap,
        requested_solutions=requested_solutions,
    )

    openqasm_path: str | None = None
    if outdir is not None:
        openqasm_path = _write_openqasm3_for_qaoa(
            outdir=outdir,
            qaoa_solver=qaoa_solver,
            optimization_result=result,
            pass_manager=pass_manager,
        )

    return _QiskitSolvePayload(
        algorithm=algorithm,
        reads=shots,
        solutions=solutions,
        fake_backend=fake_backend,
        openqasm_path=openqasm_path,
    )


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


@dataclass(slots=True)
class QiskitRuntimePlugin(RuntimePlugin):
    @property
    def plugin_id(self) -> str:
        return "qiskit"

    @property
    def display_name(self) -> str:
        return "Qiskit runtime (QAOA/NumPy on dimod-exported models)"

    def capability_catalog(self) -> Mapping[str, CapabilityStatus]:
        return {
            "model.kind.cqm.v1": "full",
            "solver.qaoa.v1": "full",
            "solver.numpy-minimum-eigensolver.v1": "full",
            "backend.fake-ibm.v1": "full",
            "export.openqasm3.v1": "full",
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
                    message="runtime requires a BQM view for qiskit optimization",
                    stage="runtime",
                )
            )

        deps_ready, missing = _probe_qiskit_core_dependencies()
        if not deps_ready:
            joined = ", ".join(sorted(missing))
            issues.append(
                SupportIssue(
                    code="QSOL4010",
                    message=(
                        f"runtime `{self.plugin_id}` is missing optional dependencies: {joined}; "
                        "install with `uv sync --extra qiskit`"
                    ),
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
        algorithm = _as_str_option(params, "algorithm", "qaoa").strip().lower()
        if algorithm not in {"qaoa", "numpy"}:
            raise ValueError("runtime option `algorithm` must be `qaoa` or `numpy`")

        requested_solutions = _as_int_option(params, "solutions", 1)
        energy_min = _as_optional_float_option(params, "energy_min")
        energy_max = _as_optional_float_option(params, "energy_max")
        if energy_min is not None and energy_max is not None and energy_min > energy_max:
            raise ValueError(
                "runtime options `energy_min` and `energy_max` must satisfy `energy_min <= energy_max`"
            )

        fake_backend = _as_str_option(params, "fake_backend", "FakeManilaV2")
        reps = _as_int_option(params, "reps", 1)
        maxiter = _as_int_option(params, "maxiter", 100)
        shots = _as_int_option(params, "shots", 1024)
        seed = _as_optional_int_option(params, "seed")
        optimization_level = _as_non_negative_int_option(params, "optimization_level", 1)

        t0 = time.perf_counter()
        payload = _run_qiskit_solver(
            bqm=compiled_model.bqm,
            varmap=compiled_model.varmap,
            algorithm=algorithm,
            requested_solutions=requested_solutions,
            fake_backend=fake_backend,
            reps=reps,
            maxiter=maxiter,
            shots=shots,
            seed=seed,
            optimization_level=optimization_level,
            outdir=run_options.outdir,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if not payload.solutions:
            raise ValueError("qiskit runtime returned no solutions")

        first = payload.solutions[0]
        first_energy_raw = first.get("energy")
        if isinstance(first_energy_raw, bool) or not isinstance(first_energy_raw, (int, float)):
            raise ValueError("runtime solution payload contains invalid best-solution energy")
        first_energy = float(first_energy_raw)
        best_sample = dict(cast(dict[str, int], first["sample"]))
        selected = list(cast(list[dict[str, object]], first["selected_assignments"]))
        threshold_passed, threshold_violations = _evaluate_energy_thresholds(
            solutions=payload.solutions,
            energy_min=energy_min,
            energy_max=energy_max,
        )

        extensions: dict[str, object] = {
            "runtime_options": params,
            "algorithm": payload.algorithm,
            "requested_solutions": requested_solutions,
            "returned_solutions": len(payload.solutions),
            "solutions": payload.solutions,
            "energy_threshold": {
                "min": energy_min,
                "max": energy_max,
                "scope": "all_returned",
                "inclusive": True,
                "passed": threshold_passed,
                "violations": threshold_violations,
            },
        }
        if payload.fake_backend is not None:
            extensions["fake_backend"] = payload.fake_backend
        if payload.openqasm_path is not None:
            extensions["openqasm_path"] = payload.openqasm_path

        return StandardRunResult(
            schema_version="1.0",
            runtime=selection.runtime_id,
            backend=selection.backend_id,
            status="ok" if threshold_passed else "threshold_failed",
            energy=first_energy,
            reads=payload.reads,
            best_sample=best_sample,
            selected_assignments=selected,
            timing_ms=elapsed_ms,
            capability_report_path="",
            extensions=extensions,
        )


def builtin_plugin_bundle() -> PluginBundle:
    return PluginBundle(
        backends=(DimodCQMBackendPlugin(),),
        runtimes=(LocalDimodRuntimePlugin(), QiskitRuntimePlugin()),
    )
