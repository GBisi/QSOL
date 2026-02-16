# Creating Custom Runtimes

QSOL allows you to extend its capabilities by adding custom runtime plugins. This is useful if you want to run models on a different solver, a cloud backend, or specialized hardware.

## 1. The `RuntimePlugin` Interface

A custom runtime must implement the `RuntimePlugin` protocol defined in `qsol.targeting.interfaces`.

```python
from typing import Collection, Mapping
from qsol.targeting.types import (
    CapabilityStatus, CompiledModel, RuntimeRunOptions,
    StandardRunResult, SupportIssue, TargetSelection
)

class MyCustomRuntime:
    @property
    def plugin_id(self) -> str:
        return "my-custom-runtime"

    @property
    def display_name(self) -> str:
        return "My Custom Runtime"

    def compatible_backend_ids(self) -> Collection[str]:
        # List backends this runtime can execute
        return {"dimod-cqm-v1"}

    def capability_catalog(self) -> Mapping[str, CapabilityStatus]:
        # Declare what features are supported
        return {
            "model.kind.cqm.v1": "full",
        }

    def check_support(
        self, compiled_model: CompiledModel, *, selection: TargetSelection
    ) -> list[SupportIssue]:
        issues = []
        # Add checks here (e.g., model size limits)
        return issues

    def run_model(
        self,
        compiled_model: CompiledModel,
        *,
        selection: TargetSelection,
        run_options: RuntimeRunOptions,
    ) -> StandardRunResult:
        # 1. Extract the backend model (e.g. CQM/BQM)
        cqm = compiled_model.cqm

        # 2. Extract runtime options
        options = run_options.options # dict passed via -x

        # 3. Solve the problem
        # result = my_solver.solve(cqm, **options)

        # 4. Return results
        return StandardRunResult(...)
```

## 2. Packaging a Plugin

Expose your plugin via a `PluginBundle` in a Python module.

```python
# my_plugin.py
from qsol.targeting.interfaces import PluginBundle
from .runtime import MyCustomRuntime

# This variable must be named `plugin_bundle` or matching the CLI arg
plugin_bundle = PluginBundle(
    runtimes=[MyCustomRuntime()],
    backends=[]
)
```

## 3. Loading the Plugin

Use the `--plugin` (or `-p`) option to load your custom runtime.

```bash
qsol solve model.qsol --plugin my_plugin:plugin_bundle --runtime my-custom-runtime
```

The format is `module_path:attribute_name`.
