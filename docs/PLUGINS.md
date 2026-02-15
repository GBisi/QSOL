# QSOL Plugins Guide

This guide covers plugin architecture, how to write plugins, and all supported ways to load them.

## 1. Plugin Architecture

QSOL has two plugin types:
- Backend plugins: compile/export grounded models.
- Runtime plugins: execute compiled models.

A plugin module exports a `PluginBundle` with one or more backends/runtimes.

```python
from qsol.targeting.interfaces import PluginBundle

plugin_bundle = PluginBundle(
    backends=(...),
    runtimes=(...),
)
```

## 2. Required Interfaces

Interfaces are defined in `src/qsol/targeting/interfaces.py`.

Backend plugin contract:
- `plugin_id` and `display_name`
- `capability_catalog()`
- `check_support(ground, required_capabilities=...)`
- `compile_model(ground)`
- `export_model(compiled_model, outdir=..., output_format=...)`

Runtime plugin contract:
- `plugin_id` and `display_name`
- `capability_catalog()`
- `compatible_backend_ids()`
- `check_support(compiled_model, selection=...)`
- `run_model(compiled_model, selection=..., run_options=...)`

## 3. Minimal Runtime Plugin Example

```python
from dataclasses import dataclass

from qsol.targeting.interfaces import PluginBundle
from qsol.targeting.types import StandardRunResult


@dataclass(slots=True)
class DemoRuntime:
    plugin_id: str = "demo-runtime"
    display_name: str = "Demo Runtime"

    def capability_catalog(self):
        return {"model.kind.cqm.v1": "full"}

    def compatible_backend_ids(self):
        return {"dimod-cqm-v1"}

    def check_support(self, _compiled_model, *, selection):
        _ = selection
        return []

    def run_model(self, _compiled_model, *, selection, run_options):
        _ = run_options
        return StandardRunResult(
            schema_version="1.0",
            runtime=selection.runtime_id,
            backend=selection.backend_id,
            status="ok",
            energy=0.0,
            reads=1,
            best_sample={},
            selected_assignments=[],
            timing_ms=0.0,
            capability_report_path="",
            extensions={"sampler": "demo"},
        )


plugin_bundle = PluginBundle(runtimes=(DemoRuntime(),))
```

## 4. Minimal Backend Plugin Skeleton

```python
from dataclasses import dataclass

from qsol.targeting.interfaces import PluginBundle
from qsol.targeting.types import CompiledModel


@dataclass(slots=True)
class DemoBackend:
    plugin_id: str = "demo-backend"
    display_name: str = "Demo Backend"

    def capability_catalog(self):
        return {}

    def check_support(self, _ground, *, required_capabilities):
        _ = required_capabilities
        return []

    def compile_model(self, _ground):
        return CompiledModel(
            kind="cqm",
            backend_id=self.plugin_id,
            cqm=object(),
            bqm=None,
            varmap={},
        )

    def export_model(self, _compiled_model, *, outdir, output_format):
        _ = outdir, output_format
        raise NotImplementedError


plugin_bundle = PluginBundle(backends=(DemoBackend(),))
```

## 5. Capability and Compatibility Contract

- Backend capability catalogs describe backend feature support.
- Runtime capability catalogs describe runtime feature support.
- `targets check` computes required model capabilities, validates backend support, then validates runtime compatibility.
- Runtime compatibility is enforced by `compatible_backend_ids()` and `check_support(...)`.

## 6. Ways To Load Plugins

### 6.1 Python package entry points (automatic)

Define entry points in your package:

```toml
[project.entry-points."qsol.backends"]
demo_backend = "my_pkg.backend:backend_plugin"

[project.entry-points."qsol.runtimes"]
demo_runtime = "my_pkg.runtime:runtime_plugin"
```

Entry-point plugins are auto-discovered in `targets`, `build`, and `solve`.

### 6.2 CLI `--plugin module:attribute`

Load a plugin bundle explicitly from a module attribute:

```bash
uv run qsol targets list --plugin my_qsol_plugins:plugin_bundle
uv run qsol build model.qsol -i model.instance.json --plugin my_qsol_plugins:plugin_bundle
uv run qsol solve model.qsol -i model.instance.json --plugin my_qsol_plugins:plugin_bundle
```

### 6.3 Instance JSON `execution.plugins`

Declare plugin bundles in the instance file:

```json
{
  "execution": {
    "runtime": "demo-runtime",
    "plugins": ["my_qsol_plugins:plugin_bundle"]
  }
}
```

`execution.plugins` must be an array of non-empty `module:attribute` strings.

## 7. Effective Loading Order

For `targets check`, `build`, and `solve`, plugin specs are resolved in this order:

1. Built-in plugins
2. Installed entry-point plugins
3. Instance `execution.plugins`
4. CLI `--plugin`

Instance and CLI plugin specs are merged with stable order and exact-string deduplication.
Duplicate plugin ids still fail at registration time.

## 8. Troubleshooting

- `QSOL4009`: plugin config/load/registration failure.
  - Invalid `execution.plugins` shape.
  - Bad module spec (must be `module:attribute`).
  - Missing attribute on module.
  - Attribute is not a `PluginBundle` (or callable returning one).
  - Duplicate backend/runtime plugin ids.

- `QSOL4007`: selected runtime/backend id not found after plugin discovery.
- `QSOL4008`: runtime/backend incompatibility.
- `QSOL4010`: required capability unsupported by selected runtime/backend.
