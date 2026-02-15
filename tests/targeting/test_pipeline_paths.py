from __future__ import annotations

from pathlib import Path

import pytest

from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import (
    CompilationUnit,
    build_for_target,
    check_target_support,
    run_for_target,
)
from qsol.targeting.types import CompiledModel, RuntimeRunOptions, TargetSelection


def _model_text() -> str:
    return (
        """
problem Demo {
  set A;
  find S : Subset(A);
  must forall x in A: S.has(x);
  minimize sum(if S.has(x) then 1 else 0 for x in A);
}
""".strip()
        + "\n"
    )


def _instance_payload(*, with_execution: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "problem": "Demo",
        "sets": {"A": ["a1", "a2"]},
        "params": {},
    }
    if with_execution:
        payload["execution"] = {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}
    return payload


def test_check_target_support_requires_instance_grounding() -> None:
    unit = check_target_support(_model_text(), options=CompileOptions(filename="demo.qsol"))

    assert any(diag.code == "QSOL4006" for diag in unit.diagnostics)


def test_check_target_support_unknown_backend_and_runtime(tmp_path: Path) -> None:
    instance_payload = _instance_payload()

    backend_unknown = check_target_support(
        _model_text(),
        options=CompileOptions(
            filename="demo.qsol",
            instance_payload=instance_payload,
            runtime_id="local-dimod",
            backend_id="unknown-backend",
        ),
    )
    assert any(
        diag.code == "QSOL4007" and "backend" in diag.message
        for diag in backend_unknown.diagnostics
    )

    runtime_unknown = check_target_support(
        _model_text(),
        options=CompileOptions(
            filename="demo.qsol",
            instance_payload=instance_payload,
            runtime_id="unknown-runtime",
            backend_id="dimod-cqm-v1",
        ),
    )
    assert any(
        diag.code == "QSOL4007" and "runtime" in diag.message
        for diag in runtime_unknown.diagnostics
    )


def test_build_for_target_requires_outdir(tmp_path: Path) -> None:
    instance_payload = _instance_payload()

    unit = build_for_target(
        _model_text(),
        options=CompileOptions(
            filename="demo.qsol",
            instance_payload=instance_payload,
            runtime_id="local-dimod",
            backend_id="dimod-cqm-v1",
        ),
    )

    assert any(diag.code == "QSOL4001" for diag in unit.diagnostics)


def test_build_for_target_handles_missing_compiled_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_check_target_support(*_args, **_kwargs):
        return CompilationUnit()

    monkeypatch.setattr("qsol.compiler.pipeline.check_target_support", _fake_check_target_support)
    unit = build_for_target(
        "problem P {}", options=CompileOptions(filename="p.qsol", outdir="/tmp/out")
    )
    assert any(diag.code == "QSOL4005" for diag in unit.diagnostics)


def test_build_for_target_handles_plugin_export_load_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_unit = CompilationUnit(
        compiled_model=CompiledModel(
            kind="cqm",
            backend_id="dimod-cqm-v1",
            cqm=object(),
            bqm=object(),
            varmap={},
        ),
        target_selection=TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1"),
    )

    def _fake_check_target_support(*_args, **_kwargs):
        return fake_unit

    class _FailRegistry:
        @classmethod
        def from_discovery(cls, *, module_specs):
            _ = module_specs
            raise RuntimeError("boom")

    monkeypatch.setattr("qsol.compiler.pipeline.check_target_support", _fake_check_target_support)
    monkeypatch.setattr("qsol.compiler.pipeline.PluginRegistry", _FailRegistry)

    unit = build_for_target(
        "problem P {}", options=CompileOptions(filename="p.qsol", outdir="/tmp/out")
    )
    assert any(diag.code == "QSOL4009" for diag in unit.diagnostics)


def test_run_for_target_handles_missing_compiled_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_build_for_target(*_args, **_kwargs):
        return CompilationUnit()

    monkeypatch.setattr("qsol.compiler.pipeline.build_for_target", _fake_build_for_target)

    unit, result = run_for_target(
        "problem P {}",
        options=CompileOptions(filename="p.qsol", outdir="/tmp/out"),
        run_options=RuntimeRunOptions(),
    )

    assert result is None
    assert any(diag.code == "QSOL4005" for diag in unit.diagnostics)


def test_run_for_target_handles_runtime_plugin_load_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_unit = CompilationUnit(
        compiled_model=CompiledModel(
            kind="cqm",
            backend_id="dimod-cqm-v1",
            cqm=object(),
            bqm=object(),
            varmap={},
        ),
        target_selection=TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1"),
    )

    def _fake_build_for_target(*_args, **_kwargs):
        return fake_unit

    class _FailRegistry:
        @classmethod
        def from_discovery(cls, *, module_specs):
            _ = module_specs
            raise RuntimeError("fail")

    monkeypatch.setattr("qsol.compiler.pipeline.build_for_target", _fake_build_for_target)
    monkeypatch.setattr("qsol.compiler.pipeline.PluginRegistry", _FailRegistry)

    unit, result = run_for_target(
        "problem P {}",
        options=CompileOptions(filename="p.qsol", outdir="/tmp/out"),
        run_options=RuntimeRunOptions(),
    )

    assert result is None
    assert any(diag.code == "QSOL4009" for diag in unit.diagnostics)


def test_run_for_target_handles_runtime_execution_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_unit = CompilationUnit(
        compiled_model=CompiledModel(
            kind="cqm",
            backend_id="dimod-cqm-v1",
            cqm=object(),
            bqm=object(),
            varmap={},
        ),
        target_selection=TargetSelection(runtime_id="local-dimod", backend_id="dimod-cqm-v1"),
    )

    def _fake_build_for_target(*_args, **_kwargs):
        return fake_unit

    class _Runtime:
        def run_model(self, _compiled_model, *, selection, run_options):
            _ = selection, run_options
            raise RuntimeError("runtime blew up")

    class _Registry:
        @classmethod
        def from_discovery(cls, *, module_specs):
            _ = module_specs
            return cls()

        def require_runtime(self, _plugin_id):
            return _Runtime()

    monkeypatch.setattr("qsol.compiler.pipeline.build_for_target", _fake_build_for_target)
    monkeypatch.setattr("qsol.compiler.pipeline.PluginRegistry", _Registry)

    unit, result = run_for_target(
        "problem P {}",
        options=CompileOptions(filename="p.qsol", outdir="/tmp/out"),
        run_options=RuntimeRunOptions(),
    )

    assert result is None
    assert any(diag.code == "QSOL5001" for diag in unit.diagnostics)
