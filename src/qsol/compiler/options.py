from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompileOptions:
    filename: str = "<input>"
    instance_path: str | None = None
    outdir: str | None = None
    output_format: str = "qubo"
    verbose: bool = False
    runtime_id: str | None = None
    backend_id: str | None = None
    plugin_specs: tuple[str, ...] = ()
