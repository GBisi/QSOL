from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module, metadata
from typing import Any, cast

from qsol.targeting.interfaces import BackendPlugin, PluginBundle, RuntimePlugin
from qsol.targeting.plugins import builtin_plugin_bundle


@dataclass(slots=True)
class PluginRegistry:
    _backends: dict[str, BackendPlugin] = field(default_factory=dict)
    _runtimes: dict[str, RuntimePlugin] = field(default_factory=dict)

    @classmethod
    def from_discovery(cls, *, module_specs: list[str] | None = None) -> PluginRegistry:
        registry = cls()
        registry.register_bundle(builtin_plugin_bundle())
        registry.load_entry_points()
        for spec in module_specs or []:
            registry.load_module_bundle(spec)
        return registry

    def register_bundle(self, bundle: PluginBundle) -> None:
        for backend in bundle.backends:
            self.register_backend(backend)
        for runtime in bundle.runtimes:
            self.register_runtime(runtime)

    def register_backend(self, plugin: BackendPlugin) -> None:
        plugin_id = plugin.plugin_id
        if plugin_id in self._backends:
            raise ValueError(f"duplicate backend plugin id: {plugin_id}")
        self._backends[plugin_id] = plugin

    def register_runtime(self, plugin: RuntimePlugin) -> None:
        plugin_id = plugin.plugin_id
        if plugin_id in self._runtimes:
            raise ValueError(f"duplicate runtime plugin id: {plugin_id}")
        self._runtimes[plugin_id] = plugin

    def load_entry_points(self) -> None:
        for ep in _iter_entry_points("qsol.backends"):
            loaded = ep.load()
            plugin = loaded() if callable(loaded) else loaded
            self.register_backend(cast(BackendPlugin, plugin))

        for ep in _iter_entry_points("qsol.runtimes"):
            loaded = ep.load()
            plugin = loaded() if callable(loaded) else loaded
            self.register_runtime(cast(RuntimePlugin, plugin))

    def load_module_bundle(self, module_spec: str) -> None:
        module_name, attr_name = _parse_module_spec(module_spec)
        module = import_module(module_name)
        if not hasattr(module, attr_name):
            raise ValueError(f"module '{module_name}' has no attribute '{attr_name}'")
        value: Any = getattr(module, attr_name)
        bundle = value() if callable(value) else value
        if not isinstance(bundle, PluginBundle):
            raise ValueError(
                f"'{module_spec}' must resolve to a PluginBundle or callable returning one"
            )
        self.register_bundle(bundle)

    def backend(self, plugin_id: str) -> BackendPlugin | None:
        return self._backends.get(plugin_id)

    def runtime(self, plugin_id: str) -> RuntimePlugin | None:
        return self._runtimes.get(plugin_id)

    def require_backend(self, plugin_id: str) -> BackendPlugin:
        plugin = self.backend(plugin_id)
        if plugin is None:
            raise KeyError(plugin_id)
        return plugin

    def require_runtime(self, plugin_id: str) -> RuntimePlugin:
        plugin = self.runtime(plugin_id)
        if plugin is None:
            raise KeyError(plugin_id)
        return plugin

    def list_backends(self) -> list[BackendPlugin]:
        return [self._backends[k] for k in sorted(self._backends)]

    def list_runtimes(self) -> list[RuntimePlugin]:
        return [self._runtimes[k] for k in sorted(self._runtimes)]


def _iter_entry_points(group: str) -> list[metadata.EntryPoint]:
    entries = metadata.entry_points()
    if hasattr(entries, "select"):
        selected = entries.select(group=group)
        return list(selected)

    grouped = cast(dict[str, list[metadata.EntryPoint]], entries)
    return list(grouped.get(group, []))


def _parse_module_spec(module_spec: str) -> tuple[str, str]:
    module_name, sep, attr_name = module_spec.partition(":")
    if not sep or not module_name or not attr_name:
        raise ValueError(
            "plugin spec must use 'module:attribute', for example 'my_plugins:plugin_bundle'"
        )
    return module_name, attr_name
