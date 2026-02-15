from __future__ import annotations

from dataclasses import dataclass

from qsol.diag.source import Span
from qsol.lower import ir
from qsol.parse import ast
from qsol.targeting.compatibility import check_pair_support, extract_required_capabilities
from qsol.targeting.plugins import (
    DimodCQMBackendPlugin,
    LocalDimodRuntimePlugin,
    QiskitRuntimePlugin,
)
from qsol.targeting.types import (
    CompiledModel,
    RuntimeRunOptions,
    StandardRunResult,
    SupportIssue,
    TargetSelection,
)


def _span() -> Span:
    return Span(
        start_offset=0,
        end_offset=1,
        line=1,
        col=1,
        end_line=1,
        end_col=2,
        filename="test.qsol",
    )


def _subset_find(name: str, set_name: str) -> ir.KFindDecl:
    span = _span()
    return ir.KFindDecl(
        span=span,
        name=name,
        unknown_type=ast.UnknownTypeRef(span=span, kind="Subset", args=(set_name,)),
    )


def _ground_program(*, custom_find: bool = False) -> ir.GroundIR:
    span = _span()
    x_name = ir.KName(span=span, name="x")
    has_x = ir.KMethodCall(
        span=span, target=ir.KName(span=span, name="S"), name="has", args=(x_name,)
    )

    find_decl = (
        ir.KFindDecl(
            span=span,
            name="C",
            unknown_type=ast.UnknownTypeRef(span=span, kind="Custom", args=()),
        )
        if custom_find
        else _subset_find("S", "A")
    )

    problem = ir.GroundProblem(
        span=span,
        name="P",
        set_values={"A": ["a1", "a2"]},
        params={},
        finds=(find_decl,),
        constraints=(
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=ir.KQuantifier(
                    span=span,
                    kind="forall",
                    var="x",
                    domain_set="A",
                    expr=ir.KCompare(
                        span=span,
                        op="=",
                        left=has_x,
                        right=ir.KNumLit(span=span, value=1.0),
                    ),
                ),
            ),
        ),
        objectives=(
            ir.KObjective(
                span=span,
                kind=ast.ObjectiveKind.MINIMIZE,
                expr=ir.KSum(
                    span=span,
                    comp=ir.KNumComprehension(
                        span=span,
                        term=ir.KIfThenElse(
                            span=span,
                            cond=has_x,
                            then_expr=ir.KNumLit(span=span, value=1.0),
                            else_expr=ir.KNumLit(span=span, value=0.0),
                        ),
                        var="x",
                        domain_set="A",
                    ),
                ),
            ),
        ),
    )
    return ir.GroundIR(span=span, problems=(problem,))


def test_extract_required_capabilities_includes_key_features() -> None:
    ground = _ground_program()
    required = extract_required_capabilities(ground)

    assert "unknown.subset.v1" in required
    assert "constraint.compare.eq.v1" in required
    assert "constraint.quantifier.forall.v1" in required
    assert "objective.sum.v1" in required
    assert "objective.if_then_else.v1" in required


def test_check_pair_support_full_support() -> None:
    ground = _ground_program()
    selection = TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1")

    result = check_pair_support(
        ground=ground,
        selection=selection,
        backend=DimodCQMBackendPlugin(),
        runtime=LocalDimodRuntimePlugin(),
    )

    assert result.report.supported
    assert result.compiled_model is not None
    assert not result.report.issues


def test_check_pair_support_reports_unsupported_capability() -> None:
    ground = _ground_program(custom_find=True)
    selection = TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1")

    result = check_pair_support(
        ground=ground,
        selection=selection,
        backend=DimodCQMBackendPlugin(),
        runtime=LocalDimodRuntimePlugin(),
    )

    assert not result.report.supported
    assert result.report.issues
    assert any(issue.capability_id == "unknown.custom.v1" for issue in result.report.issues)


@dataclass(slots=True)
class _RejectingRuntime:
    plugin_id: str = "rejecting-runtime"
    display_name: str = "Rejecting Runtime"

    def capability_catalog(self):
        return {"model.kind.cqm.v1": "full"}

    def compatible_backend_ids(self):
        return {"dimod-cqm-v1"}

    def check_support(self, _compiled_model, *, selection):
        _ = selection
        return [
            SupportIssue(
                code="QSOL4010",
                message="runtime policy rejected this model",
                stage="runtime",
            )
        ]

    def run_model(self, _compiled_model, *, selection, run_options: RuntimeRunOptions):
        _ = selection, run_options
        return StandardRunResult(
            schema_version="1.0",
            runtime=self.plugin_id,
            backend="dimod-cqm-v1",
            status="ok",
            energy=0.0,
            reads=1,
            best_sample={},
            selected_assignments=[],
            timing_ms=0.0,
            capability_report_path="",
        )


def test_check_pair_support_runtime_rejection() -> None:
    ground = _ground_program()
    selection = TargetSelection(runtime_id="rejecting-runtime", backend_id="dimod-cqm-v1")

    result = check_pair_support(
        ground=ground,
        selection=selection,
        backend=DimodCQMBackendPlugin(),
        runtime=_RejectingRuntime(),
    )

    assert not result.report.supported
    assert any(issue.stage == "runtime" for issue in result.report.issues)


def test_local_runtime_check_support_reports_kind_backend_and_bqm_issues() -> None:
    runtime = LocalDimodRuntimePlugin()
    model = CompiledModel(
        kind="bqm",
        backend_id="other-backend",
        cqm=object(),
        bqm=None,
        varmap={},
    )
    selection = TargetSelection(runtime_id="local-dimod", backend_id="other-backend")

    issues = runtime.check_support(model, selection=selection)
    assert len(issues) == 3
    assert any(issue.code == "QSOL4008" for issue in issues)
    assert any("expects `cqm` models" in issue.message for issue in issues)
    assert any("requires a BQM view" in issue.message for issue in issues)


def test_local_runtime_run_model_missing_bqm_raises() -> None:
    runtime = LocalDimodRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=None,
        varmap={},
    )
    selection = TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1")

    try:
        runtime.run_model(model, selection=selection, run_options=RuntimeRunOptions())
    except ValueError as exc:
        assert "does not include BQM" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_local_runtime_run_model_simulated_annealing_branch(monkeypatch) -> None:
    class _Record:
        def __init__(self, sample: dict[str, int], energy: float, num_occurrences: int) -> None:
            self.sample = sample
            self.energy = energy
            self.num_occurrences = num_occurrences

    class _AggregateSampleSet:
        def data(self, *, fields):
            assert fields == ["sample", "energy", "num_occurrences"]
            return iter(
                [
                    _Record({"x": 1, "aux:z": 1, "orphan": 1}, -1.0, 2),
                    _Record({"x": 0, "orphan": 1}, 0.0, 1),
                ]
            )

    class _SampleSet:
        def __len__(self) -> int:
            return 3

        def aggregate(self) -> _AggregateSampleSet:
            return _AggregateSampleSet()

    class _Sampler:
        parameters = {"num_reads": [], "seed": []}

        def sample(self, _bqm, **_kwargs):
            return _SampleSet()

    monkeypatch.setattr(
        "qsol.targeting.plugins.dimod.SimulatedAnnealingSampler", lambda: _Sampler()
    )

    runtime = LocalDimodRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=object(),
        varmap={"x": "X"},
    )
    selection = TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1")
    result = runtime.run_model(
        model,
        selection=selection,
        run_options=RuntimeRunOptions(
            params={"sampler": "simulated-annealing", "num_reads": 5, "seed": 7}
        ),
    )

    assert result.reads == 3
    assert result.energy == -1.0
    assert result.selected_assignments == [{"variable": "x", "meaning": "X", "value": 1}]
    assert result.extensions["returned_solutions"] == 1
    assert result.extensions["requested_solutions"] == 1
    assert result.extensions["energy_threshold"]["passed"] is True


def test_local_runtime_run_model_multi_solution_and_threshold_pass(monkeypatch) -> None:
    class _Record:
        def __init__(self, sample: dict[str, int], energy: float, num_occurrences: int) -> None:
            self.sample = sample
            self.energy = energy
            self.num_occurrences = num_occurrences

    class _AggregateSampleSet:
        def data(self, *, fields):
            assert fields == ["sample", "energy", "num_occurrences"]
            return iter(
                [
                    _Record({"y": 0, "x": 0}, 0.0, 1),
                    _Record({"x": 1, "y": 0}, 1.0, 3),
                    _Record({"x": 0, "y": 1}, 1.0, 2),
                ]
            )

    class _SampleSet:
        def __len__(self) -> int:
            return 6

        def aggregate(self) -> _AggregateSampleSet:
            return _AggregateSampleSet()

    class _Sampler:
        parameters = {"num_reads": [], "seed": []}

        def sample(self, _bqm, **_kwargs):
            return _SampleSet()

    monkeypatch.setattr(
        "qsol.targeting.plugins.dimod.SimulatedAnnealingSampler", lambda: _Sampler()
    )

    runtime = LocalDimodRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=object(),
        varmap={"x": "X", "y": "Y"},
    )
    selection = TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1")

    result = runtime.run_model(
        model,
        selection=selection,
        run_options=RuntimeRunOptions(
            params={
                "sampler": "simulated-annealing",
                "num_reads": 6,
                "solutions": 3,
                "energy_max": 1.0,
            }
        ),
    )

    assert result.status == "ok"
    assert result.energy == 0.0
    assert result.best_sample == {"x": 0, "y": 0}
    assert result.extensions["requested_solutions"] == 3
    assert result.extensions["returned_solutions"] == 3
    solutions = result.extensions["solutions"]
    assert [solution["rank"] for solution in solutions] == [1, 2, 3]
    assert [solution["energy"] for solution in solutions] == [0.0, 1.0, 1.0]
    # Tie on energy is ordered deterministically by sample signature.
    assert solutions[1]["sample"] == {"x": 0, "y": 1}
    assert solutions[2]["sample"] == {"x": 1, "y": 0}
    assert result.extensions["energy_threshold"]["passed"] is True


def test_local_runtime_run_model_threshold_failure(monkeypatch) -> None:
    class _Record:
        def __init__(self, sample: dict[str, int], energy: float, num_occurrences: int) -> None:
            self.sample = sample
            self.energy = energy
            self.num_occurrences = num_occurrences

    class _AggregateSampleSet:
        def data(self, *, fields):
            assert fields == ["sample", "energy", "num_occurrences"]
            return iter(
                [
                    _Record({"x": 0}, 0.0, 1),
                    _Record({"x": 1}, 1.0, 1),
                ]
            )

    class _SampleSet:
        def __len__(self) -> int:
            return 2

        def aggregate(self) -> _AggregateSampleSet:
            return _AggregateSampleSet()

    class _Sampler:
        parameters = {"num_reads": [], "seed": []}

        def sample(self, _bqm, **_kwargs):
            return _SampleSet()

    monkeypatch.setattr(
        "qsol.targeting.plugins.dimod.SimulatedAnnealingSampler", lambda: _Sampler()
    )

    runtime = LocalDimodRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=object(),
        varmap={"x": "X"},
    )
    selection = TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1")
    result = runtime.run_model(
        model,
        selection=selection,
        run_options=RuntimeRunOptions(
            params={
                "sampler": "simulated-annealing",
                "num_reads": 2,
                "solutions": 2,
                "energy_max": 0.0,
            }
        ),
    )

    assert result.status == "threshold_failed"
    assert result.energy == 0.0
    threshold = result.extensions["energy_threshold"]
    assert threshold["passed"] is False
    violations = threshold["violations"]
    assert len(violations) == 1
    assert violations[0]["rank"] == 2
    assert violations[0]["energy"] == 1.0


def test_local_runtime_run_model_invalid_runtime_options_raise() -> None:
    runtime = LocalDimodRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=object(),
        varmap={},
    )
    selection = TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1")

    try:
        runtime.run_model(
            model,
            selection=selection,
            run_options=RuntimeRunOptions(params={"sampler": "invalid"}),
        )
    except ValueError as exc:
        assert "sampler" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_qiskit_runtime_check_support_reports_missing_optional_deps(monkeypatch) -> None:
    runtime = QiskitRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=object(),
        varmap={},
    )
    selection = TargetSelection(runtime_id="qiskit", backend_id="dimod-cqm-v1")
    monkeypatch.setattr(
        "qsol.targeting.plugins._probe_qiskit_core_dependencies",
        lambda: (False, ["qiskit", "qiskit-optimization"]),
    )

    issues = runtime.check_support(model, selection=selection)
    assert any(issue.code == "QSOL4010" for issue in issues)
    assert any("uv sync --extra qiskit" in issue.message for issue in issues)


def test_qiskit_runtime_run_model_uses_solver_payload(monkeypatch) -> None:
    runtime = QiskitRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=object(),
        varmap={"x": "X", "y": "Y"},
    )
    selection = TargetSelection(runtime_id="qiskit", backend_id="dimod-cqm-v1")
    monkeypatch.setattr(
        "qsol.targeting.plugins._probe_qiskit_core_dependencies", lambda: (True, [])
    )

    def _fake_solver(**_kwargs):
        return type(
            "Payload",
            (),
            {
                "algorithm": "qaoa",
                "reads": 256,
                "solutions": [
                    {
                        "rank": 1,
                        "energy": -2.0,
                        "sample": {"x": 1, "y": 0},
                        "selected_assignments": [{"variable": "x", "meaning": "X", "value": 1}],
                        "probability": 0.75,
                        "status": "SUCCESS",
                    },
                    {
                        "rank": 2,
                        "energy": -1.0,
                        "sample": {"x": 0, "y": 1},
                        "selected_assignments": [{"variable": "y", "meaning": "Y", "value": 1}],
                        "probability": 0.25,
                        "status": "SUCCESS",
                    },
                ],
                "fake_backend": "FakeManilaV2",
                "openqasm_path": "/tmp/out/qaoa.qasm",
            },
        )()

    monkeypatch.setattr("qsol.targeting.plugins._run_qiskit_solver", _fake_solver)
    result = runtime.run_model(
        model,
        selection=selection,
        run_options=RuntimeRunOptions(
            params={"algorithm": "qaoa", "solutions": 2}, outdir="/tmp/out"
        ),
    )

    assert result.status == "ok"
    assert result.energy == -2.0
    assert result.reads == 256
    assert result.best_sample == {"x": 1, "y": 0}
    assert result.extensions["algorithm"] == "qaoa"
    assert result.extensions["returned_solutions"] == 2
    assert result.extensions["fake_backend"] == "FakeManilaV2"
    assert result.extensions["openqasm_path"] == "/tmp/out/qaoa.qasm"


def test_qiskit_runtime_rejects_invalid_algorithm_option() -> None:
    runtime = QiskitRuntimePlugin()
    model = CompiledModel(
        kind="cqm",
        backend_id="dimod-cqm-v1",
        cqm=object(),
        bqm=object(),
        varmap={},
    )
    selection = TargetSelection(runtime_id="qiskit", backend_id="dimod-cqm-v1")

    try:
        runtime.run_model(
            model,
            selection=selection,
            run_options=RuntimeRunOptions(params={"algorithm": "bad-algorithm"}),
        )
    except ValueError as exc:
        assert "algorithm" in str(exc)
    else:
        raise AssertionError("expected ValueError")
