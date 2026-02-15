from __future__ import annotations

from dataclasses import dataclass

import pytest

from qsol.targeting.interfaces import PluginBundle
from qsol.targeting.registry import PluginRegistry
from qsol.targeting.types import CompiledModel, RuntimeRunOptions, StandardRunResult


@dataclass(slots=True)
class _DummyBackend:
    plugin_id: str = "dummy-backend"
    display_name: str = "Dummy Backend"

    def capability_catalog(self) -> dict[str, str]:
        return {"dummy.cap": "full"}

    def check_support(self, _ground, *, required_capabilities):
        _ = required_capabilities
        return []

    def compile_model(self, _ground):
        return CompiledModel(
            kind="cqm",
            backend_id=self.plugin_id,
            cqm=object(),
            bqm=object(),
            varmap={},
        )

    def export_model(self, _compiled_model, *, outdir: str, output_format: str):
        _ = outdir, output_format
        raise RuntimeError("not used")


@dataclass(slots=True)
class _DummyRuntime:
    plugin_id: str = "dummy-runtime"
    display_name: str = "Dummy Runtime"

    def capability_catalog(self) -> dict[str, str]:
        return {"dummy.run": "full"}

    def compatible_backend_ids(self):
        return {"dummy-backend"}

    def check_support(self, _compiled_model, *, selection):
        _ = selection
        return []

    def run_model(self, _compiled_model, *, selection, run_options: RuntimeRunOptions):
        _ = selection, run_options
        return StandardRunResult(
            schema_version="1.0",
            runtime=self.plugin_id,
            backend="dummy-backend",
            status="ok",
            energy=0.0,
            reads=1,
            best_sample={},
            selected_assignments=[],
            timing_ms=0.0,
            capability_report_path="",
        )


def test_registry_loads_builtin_plugins() -> None:
    registry = PluginRegistry.from_discovery(module_specs=[])

    assert registry.backend("dimod-cqm-v1") is not None
    assert registry.runtime("local-dimod") is not None
    assert registry.runtime("qiskit") is not None


def test_registry_loads_module_bundle(tmp_path, monkeypatch) -> None:
    module_file = tmp_path / "test_plugins.py"
    module_file.write_text(
        """
from qsol.targeting.interfaces import PluginBundle

class Backend:
    plugin_id = "custom-backend"
    display_name = "Custom Backend"

    def capability_catalog(self):
        return {"x": "full"}

    def check_support(self, _ground, *, required_capabilities):
        _ = required_capabilities
        return []

    def compile_model(self, _ground):
        from qsol.targeting.types import CompiledModel
        return CompiledModel(kind="cqm", backend_id=self.plugin_id, cqm=object(), bqm=object(), varmap={})

    def export_model(self, _compiled_model, *, outdir, output_format):
        raise RuntimeError("not used")

class Runtime:
    plugin_id = "custom-runtime"
    display_name = "Custom Runtime"

    def capability_catalog(self):
        return {"y": "full"}

    def compatible_backend_ids(self):
        return {"custom-backend"}

    def check_support(self, _compiled_model, *, selection):
        _ = selection
        return []

    def run_model(self, _compiled_model, *, selection, run_options):
        _ = selection, run_options
        from qsol.targeting.types import StandardRunResult
        return StandardRunResult(schema_version="1.0", runtime=self.plugin_id, backend="custom-backend", status="ok", energy=0.0, reads=1, best_sample={}, selected_assignments=[], timing_ms=0.0, capability_report_path="")

def plugin_bundle():
    return PluginBundle(backends=(Backend(),), runtimes=(Runtime(),))
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))

    registry = PluginRegistry.from_discovery(module_specs=["test_plugins:plugin_bundle"])
    assert registry.backend("custom-backend") is not None
    assert registry.runtime("custom-runtime") is not None


def test_registry_rejects_duplicate_ids() -> None:
    registry = PluginRegistry()
    registry.register_bundle(PluginBundle(backends=(_DummyBackend(),), runtimes=(_DummyRuntime(),)))

    with pytest.raises(ValueError, match="duplicate backend"):
        registry.register_backend(_DummyBackend())

    with pytest.raises(ValueError, match="duplicate runtime"):
        registry.register_runtime(_DummyRuntime())


def test_registry_load_entry_points(monkeypatch) -> None:
    class _EP:
        def __init__(self, value):
            self._value = value

        def load(self):
            return self._value

    def _fake_iter(group: str):
        if group == "qsol.backends":
            return [_EP(_DummyBackend)]
        if group == "qsol.runtimes":
            return [_EP(_DummyRuntime)]
        return []

    monkeypatch.setattr("qsol.targeting.registry._iter_entry_points", _fake_iter)
    registry = PluginRegistry()
    registry.load_entry_points()

    assert registry.backend("dummy-backend") is not None
    assert registry.runtime("dummy-runtime") is not None


def test_registry_rejects_bad_module_spec() -> None:
    registry = PluginRegistry()
    with pytest.raises(ValueError, match="module:attribute"):
        registry.load_module_bundle("invalid-spec")
