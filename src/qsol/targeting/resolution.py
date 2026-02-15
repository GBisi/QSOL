from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from qsol.targeting.types import SupportIssue, TargetSelection


@dataclass(slots=True)
class SelectionResolution:
    selection: TargetSelection | None
    issues: list[SupportIssue] = field(default_factory=list)


def resolve_target_selection(
    *,
    instance_payload: Mapping[str, object] | None,
    cli_runtime: str | None,
    cli_backend: str | None,
) -> SelectionResolution:
    runtime_default, backend_default = _instance_defaults(instance_payload)

    runtime = cli_runtime or runtime_default
    backend = cli_backend or backend_default

    issues: list[SupportIssue] = []
    if runtime is None and backend is None:
        issues.append(
            SupportIssue(
                code="QSOL4006",
                message=(
                    "runtime and backend are required; provide `--runtime` and `--backend` "
                    "or set `execution.runtime` and `execution.backend` in the instance JSON"
                ),
                stage="resolution",
            )
        )
    elif runtime is None:
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
    elif backend is None:
        issues.append(
            SupportIssue(
                code="QSOL4006",
                message=(
                    "backend is required; provide `--backend` or set `execution.backend` "
                    "in the instance JSON"
                ),
                stage="resolution",
            )
        )

    if issues:
        return SelectionResolution(selection=None, issues=issues)

    assert runtime is not None
    assert backend is not None
    return SelectionResolution(selection=TargetSelection(runtime_id=runtime, backend_id=backend))


def _instance_defaults(
    instance_payload: Mapping[str, object] | None,
) -> tuple[str | None, str | None]:
    if instance_payload is None:
        return None, None
    execution = instance_payload.get("execution")
    if not isinstance(execution, Mapping):
        return None, None

    runtime_raw = execution.get("runtime")
    backend_raw = execution.get("backend")
    runtime = str(runtime_raw) if isinstance(runtime_raw, str) and runtime_raw.strip() else None
    backend = str(backend_raw) if isinstance(backend_raw, str) and backend_raw.strip() else None
    return runtime, backend
