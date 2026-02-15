from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from qsol.targeting.types import SupportIssue, TargetSelection

DEFAULT_BACKEND_ID = "dimod-cqm-v1"


@dataclass(slots=True)
class SelectionResolution:
    selection: TargetSelection | None
    plugin_specs: tuple[str, ...] = ()
    issues: list[SupportIssue] = field(default_factory=list)


def resolve_target_selection(
    *,
    instance_payload: Mapping[str, object] | None,
    cli_runtime: str | None,
    cli_backend: str | None,
    cli_plugin_specs: Sequence[str] = (),
) -> SelectionResolution:
    runtime_default, backend_default, instance_plugin_specs, issues = _instance_defaults(
        instance_payload
    )

    runtime = cli_runtime or runtime_default
    backend = cli_backend or backend_default or DEFAULT_BACKEND_ID
    plugin_specs = _merge_plugin_specs(instance_plugin_specs, cli_plugin_specs)
    if runtime is None:
        issues.append(
            SupportIssue(
                code="QSOL4006",
                message=(
                    "runtime is required; provide `--runtime` or set `execution.runtime` "
                    "in the instance JSON"
                ),
                stage="resolution",
            )
        )

    selection = (
        TargetSelection(runtime_id=runtime, backend_id=backend)
        if runtime is not None and backend is not None
        else None
    )
    return SelectionResolution(selection=selection, plugin_specs=plugin_specs, issues=issues)


def _instance_defaults(
    instance_payload: Mapping[str, object] | None,
) -> tuple[str | None, str | None, tuple[str, ...], list[SupportIssue]]:
    if instance_payload is None:
        return None, None, (), []

    execution = instance_payload.get("execution")
    if not isinstance(execution, Mapping):
        return None, None, (), []

    runtime_raw = execution.get("runtime")
    backend_raw = execution.get("backend")
    runtime = str(runtime_raw) if isinstance(runtime_raw, str) and runtime_raw.strip() else None
    backend = str(backend_raw) if isinstance(backend_raw, str) and backend_raw.strip() else None
    issues: list[SupportIssue] = []
    plugins: tuple[str, ...] = ()
    if "plugins" in execution:
        plugins_raw = execution.get("plugins")
        if not isinstance(plugins_raw, list):
            issues.append(
                SupportIssue(
                    code="QSOL4009",
                    message=(
                        "instance `execution.plugins` must be an array of non-empty "
                        "plugin specs (`module:attribute`)"
                    ),
                    stage="resolution",
                )
            )
        else:
            parsed_plugins: list[str] = []
            for idx, value in enumerate(plugins_raw):
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        SupportIssue(
                            code="QSOL4009",
                            message=(
                                "instance `execution.plugins` entries must be non-empty strings "
                                "(`module:attribute`)"
                            ),
                            stage="resolution",
                            detail={"path": f"execution.plugins[{idx}]"},
                        )
                    )
                    continue
                parsed_plugins.append(value)
            plugins = tuple(parsed_plugins)

    return runtime, backend, plugins, issues


def _merge_plugin_specs(
    instance_specs: Sequence[str],
    cli_specs: Sequence[str],
) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for spec in (*instance_specs, *cli_specs):
        if spec in seen:
            continue
        merged.append(spec)
        seen.add(spec)
    return tuple(merged)
